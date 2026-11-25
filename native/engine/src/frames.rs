//! Complete JSON and SSE frames, checked before any byte is used: the engine's event stream and the
//! server's MCP relay read them the same way.
use crate::{Error, StatusCode};
use base64::Engine;
use serde::{
    Deserialize, Deserializer,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::Value;
use std::{collections::HashSet, fmt};

pub const LIMIT: usize = 1024 * 1024;
fn rejected() -> Error {
    Error(
        StatusCode::BAD_GATEWAY,
        "Lumen MCP-Verbindung nicht verfügbar oder nicht mehr freigegeben.",
    )
}

pub fn text(value: &str, max: usize) -> bool {
    !value.is_empty() && value.len() <= max && value.bytes().all(|b| (32..127).contains(&b))
}

struct Unique;
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct Check;
        impl<'de> Visitor<'de> for Check {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON without duplicate fields")
            }
            fn visit_bool<E: de::Error>(self, _: bool) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_i64<E: de::Error>(self, _: i64) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_u64<E: de::Error>(self, _: u64) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_f64<E: de::Error>(self, _: f64) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_str<E: de::Error>(self, _: &str) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_none<E: de::Error>(self) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_unit<E: de::Error>(self) -> Result<Unique, E> {
                Ok(Unique)
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Unique, A::Error> {
                while seq.next_element::<Unique>()?.is_some() {}
                Ok(Unique)
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Unique, A::Error> {
                let mut keys = HashSet::new();
                while let Some(key) = map.next_key::<String>()? {
                    if !keys.insert(key) {
                        return Err(de::Error::custom("duplicate JSON field"));
                    }
                    map.next_value::<Unique>()?;
                }
                Ok(Unique)
            }
        }
        d.deserialize_any(Check)
    }
}

pub fn json(raw: &[u8]) -> Result<Value, Error> {
    if raw.len() > LIMIT {
        return Err(rejected());
    }
    serde_json::from_slice::<Unique>(raw).map_err(|_| rejected())?;
    serde_json::from_slice(raw).map_err(|_| rejected())
}

pub fn reflected(raw: &[u8], known: &[String]) -> bool {
    const QUOTE: &percent_encoding::AsciiSet = &percent_encoding::NON_ALPHANUMERIC
        .remove(b'-')
        .remove(b'_')
        .remove(b'.')
        .remove(b'~');
    let source = String::from_utf8_lossy(raw);
    let plus = source.replace('+', " ");
    let decoded = percent_encoding::percent_decode_str(&plus).decode_utf8_lossy();
    let lower = source.to_ascii_lowercase();
    known.iter().filter(|s| !s.is_empty()).any(|secret| {
        let hex = secret
            .as_bytes()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        if source.contains(secret) || decoded.contains(secret) || lower.contains(&hex) {
            return true;
        }
        let escaped = serde_json::to_string(secret).expect("string JSON");
        let escaped = escaped[1..escaped.len() - 1]
            .chars()
            .map(|c| {
                if c.is_ascii() {
                    c.to_string()
                } else {
                    c.encode_utf16(&mut [0; 2])
                        .iter()
                        .map(|v| format!("\\u{v:04x}"))
                        .collect()
                }
            })
            .collect::<String>();
        let encoded = percent_encoding::utf8_percent_encode(secret, QUOTE).to_string();
        if source.contains(&escaped) || source.contains(&encoded) {
            return true;
        }
        [
            base64::engine::general_purpose::STANDARD.encode(secret),
            base64::engine::general_purpose::URL_SAFE.encode(secret),
        ]
        .iter()
        .any(|s| source.contains(s) || source.contains(s.trim_end_matches('=')))
    })
}

pub fn inspect(raw: &[u8], known: &[String]) -> Result<Value, Error> {
    if reflected(raw, known) {
        return Err(rejected());
    }
    let value = json(raw)?;
    if reflected(value.to_string().as_bytes(), known) {
        return Err(rejected());
    }
    Ok(value)
}

#[derive(Default)]
pub struct Events {
    line: Vec<u8>,
    lines: Vec<Vec<u8>>,
    size: usize,
    cr: bool,
}
impl Events {
    fn line(&mut self, width: usize, frames: &mut Vec<Vec<Vec<u8>>>) -> Result<(), Error> {
        self.size += width;
        if self.size > LIMIT {
            return Err(rejected());
        }
        if self.line.is_empty() {
            frames.push(std::mem::take(&mut self.lines));
            self.size = 0;
        } else {
            self.lines.push(std::mem::take(&mut self.line));
        }
        Ok(())
    }
    pub fn push(&mut self, bytes: &[u8], ended: bool) -> Result<Vec<Vec<Vec<u8>>>, Error> {
        let mut frames = Vec::new();
        for &b in bytes {
            if self.cr {
                self.cr = false;
                self.line(if b == b'\n' { 2 } else { 1 }, &mut frames)?;
                if b == b'\n' {
                    continue;
                }
            }
            match b {
                b'\r' => self.cr = true,
                b'\n' => self.line(1, &mut frames)?,
                _ => {
                    self.line.push(b);
                    self.size += 1;
                }
            }
            if self.size > LIMIT {
                return Err(rejected());
            }
        }
        if ended {
            if self.cr {
                self.cr = false;
                self.line(1, &mut frames)?;
            }
            if !self.line.is_empty() || !self.lines.is_empty() {
                return Err(rejected());
            }
        }
        Ok(frames)
    }
}

/// One frame of an event stream: the frame with its `id` replaced by `alias`, and its JSON data.
pub fn event<F, E>(
    lines: Vec<Vec<u8>>,
    known: &[String],
    mut alias: F,
) -> Result<(Vec<u8>, Option<Value>), E>
where
    F: FnMut(&str) -> Result<String, E>,
    E: From<Error>,
{
    let mut raw = lines.join(&b'\n');
    raw.extend_from_slice(b"\n\n");
    std::str::from_utf8(&raw).map_err(|_| E::from(rejected()))?;
    if reflected(&raw, known) {
        return Err(rejected().into());
    }
    let mut data = Vec::new();
    let mut output = Vec::new();
    for (index, line) in lines.into_iter().enumerate() {
        let checked = if index == 0 {
            line.strip_prefix(b"\xef\xbb\xbf").unwrap_or(&line)
        } else {
            &line
        };
        let (field, value) = checked
            .iter()
            .position(|b| *b == b':')
            .map_or((checked, &b""[..]), |at| {
                (&checked[..at], &checked[at + 1..])
            });
        let value = value.strip_prefix(b" ").unwrap_or(value);
        if field == b"event" && value == b"endpoint" {
            return Err(rejected().into());
        }
        if field == b"data" {
            data.push(value.to_vec());
        }
        if field == b"id" && !value.is_empty() {
            let id = std::str::from_utf8(value).map_err(|_| E::from(rejected()))?;
            if !text(id, 4096) {
                return Err(rejected().into());
            }
            output.push(format!("id: {}", alias(id)?).into_bytes());
        } else {
            output.push(line);
        }
    }
    let value = if data.is_empty() {
        None
    } else {
        Some(inspect(&data.join(&b'\n'), known)?)
    };
    let mut bytes = output.join(&b'\n');
    bytes.extend_from_slice(b"\n\n");
    Ok((bytes, value))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_secret_encodings_duplicates_and_invalid_json() {
        let known = vec!["server/secret>token".to_owned()];
        for raw in [
            br#"{"a":1,"a":2}"#.as_slice(),
            br#"{"a":"server/secret>token"}"#,
            br#"{"a":"server%2fsecret%3etoken"}"#,
            b"NaN",
            b"Infinity",
            b"{}{}",
        ] {
            assert!(inspect(raw, &known).is_err());
        }
        let escaped = known[0]
            .chars()
            .map(|c| format!("\\u{:04x}", c as u32))
            .collect::<String>();
        assert!(inspect(format!("{{\"a\":\"{escaped}\"}}").as_bytes(), &known).is_err());
        for value in [
            base64::engine::general_purpose::STANDARD.encode(&known[0]),
            known[0]
                .as_bytes()
                .iter()
                .map(|b| format!("{b:02X}"))
                .collect::<String>(),
        ] {
            assert!(inspect(format!("{{\"a\":\"{value}\"}}").as_bytes(), &known).is_err());
        }
        assert!(inspect(br#"{"result":{"ok":true}}"#, &known).is_ok());
    }
    #[test]
    fn sse_keeps_complete_frames_and_masks_resume_ids() {
        for separator in ["\n", "\r\n", "\r"] {
            let input = [
                "id: upstream",
                "event: message",
                "data: {\"ok\":true}",
                "",
                "",
            ]
            .join(separator);
            let mut parser = Events::default();
            let mut output = Vec::new();
            for byte in input.as_bytes() {
                output.extend(
                    parser
                        .push(&[*byte], false)
                        .unwrap_or_else(|_| panic!("valid frame")),
                );
            }
            output.extend(
                parser
                    .push(&[], true)
                    .unwrap_or_else(|_| panic!("valid EOF")),
            );
            assert_eq!(output.len(), 1);
            let (raw, value) = event(output.remove(0), &[], |_| Ok::<_, Error>("opaque".into()))
                .unwrap_or_else(|_| panic!("valid event"));
            assert_eq!(raw, b"id: opaque\nevent: message\ndata: {\"ok\":true}\n\n");
            assert_eq!(value.unwrap()["ok"], true);
        }
        assert!(Events::default().push(b"data: {}", true).is_err());
        assert!(
            Events::default()
                .push(&vec![b'x'; LIMIT + 1], false)
                .is_err()
        );
        assert!(
            event(
                vec![b"\xef\xbb\xbfevent: endpoint".to_vec()],
                &[],
                |_| Ok::<_, Error>("opaque".into())
            )
            .is_err()
        );
        assert!(
            event(
                vec![b"data: {\"secret\":\"server-only\"}".to_vec()],
                &["server-only".into()],
                |_| Ok::<_, Error>("opaque".into())
            )
            .is_err()
        );
    }
}

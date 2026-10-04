//! Lumen admission profile, added 2026-10-05. Validate before recursive serde/model
//! conversion. Unsupported binary/icon tables are rejected, never silently dropped.
use super::ParseXmlError;
use quick_xml::{Reader, events::Event};
use std::collections::HashSet;
const MAX_XML: usize = 64 * 1024 * 1024;
fn invalid<T>() -> Result<T, ParseXmlError> {
    Err(ParseXmlError::Admission)
}
pub(super) fn check(data: &[u8]) -> Result<(), ParseXmlError> {
    if data.len() > MAX_XML {
        return invalid();
    }
    let mut reader = Reader::from_reader(data);
    let mut path: Vec<Vec<u8>> = Vec::new();
    let mut entry: Vec<(Option<Vec<u8>>, HashSet<String>)> = Vec::new();
    let mut custom: Vec<HashSet<String>> = Vec::new();
    let mut text = String::new();
    let mut events = 0usize;
    let mut ids = HashSet::new();
    let mut histories = 0;
    loop {
        events += 1;
        if events > 2_000_000 {
            return invalid();
        }
        match reader.read_event().map_err(|_| ParseXmlError::Admission)? {
            Event::Start(e) => {
                let tag = e.name().as_ref().as_bytes().to_vec();
                if path.len() >= 48 {
                    return invalid();
                }
                if tag == b"Binary" || tag == b"CustomIconUUID" || tag == b"Icon" {
                    return invalid();
                }
                if tag == b"CustomData" {
                    custom.push(HashSet::new());
                }
                if tag == b"History" {
                    histories += 1;
                    if histories > 1 {
                        return invalid();
                    }
                }
                if tag == b"Entry" {
                    if entry.len() >= 2 {
                        return invalid();
                    }
                    entry.push((None, HashSet::new()));
                }
                if tag == b"Key" || tag == b"UUID" {
                    text.clear();
                }
                path.push(tag);
            }
            Event::Empty(e) => {
                if e.name().as_ref() == "Key" {
                    return invalid();
                }
                if e.name().as_ref() == "History" && histories > 0 {
                    return invalid();
                }
                if [b"Binary".as_slice(), b"CustomIconUUID", b"Icon"]
                    .contains(&e.name().as_ref().as_bytes())
                {
                    return invalid();
                }
            }
            Event::Text(e) => {
                if e.len() > 32768 {
                    return invalid();
                }
                if path.last().is_some_and(|v| v == b"Key" || v == b"UUID") {
                    let raw = e.as_ref();
                    text.push_str(
                        &quick_xml::escape::unescape(raw).map_err(|_| ParseXmlError::Admission)?,
                    );
                    if text.len() > 128 {
                        return invalid();
                    }
                }
            }
            Event::GeneralRef(e) => {
                let escaped = format!("&{};", e.as_ref());
                let value =
                    quick_xml::escape::unescape(&escaped).map_err(|_| ParseXmlError::Admission)?;
                if path.last().is_some_and(|v| v == b"Key" || v == b"UUID") {
                    text.push_str(&value);
                    if text.len() > 128 {
                        return invalid();
                    }
                }
            }
            Event::CData(_) | Event::DocType(_) => return invalid(),
            Event::End(e) => {
                let name = e.name();
                let tag = name.as_ref().as_bytes();
                if path.pop().as_deref() != Some(tag) {
                    return invalid();
                }
                if tag == b"UUID" && path.last().is_some_and(|p| p == b"Entry" || p == b"Group") {
                    let id = text.as_bytes().to_vec();
                    if path.last().is_some_and(|p| p == b"Entry") {
                        if entry.len() == 2 && entry[0].0.as_ref() != Some(&id) {
                            return invalid();
                        }
                        if entry.len() == 1 && !ids.insert(id.clone()) {
                            return invalid();
                        }
                        let Some(last) = entry.last_mut() else {
                            return invalid();
                        };
                        last.0 = Some(id);
                    } else if !ids.insert(id) {
                        return invalid();
                    }
                }
                if tag == b"Key" && path.last().is_some_and(|p| p == b"String") {
                    let Some(last) = entry.last_mut() else {
                        return invalid();
                    };
                    if text.is_empty() || !last.1.insert(text.clone()) || last.1.len() > 64 {
                        return invalid();
                    }
                }
                if tag == b"Key" && path.last().is_some_and(|p| p == b"Item") && !custom.is_empty()
                {
                    let keys = custom.last_mut().ok_or(ParseXmlError::Admission)?;
                    if text.is_empty() || !keys.insert(text.clone()) || keys.len() > 64 {
                        return invalid();
                    }
                }
                if tag == b"CustomData" {
                    custom.pop();
                }
                if tag == b"Entry" {
                    let Some(done) = entry.pop() else {
                        return invalid();
                    };
                    if done.0.is_none() {
                        return invalid();
                    }
                }
                if tag == b"History" {
                    histories -= 1;
                }
            }
            Event::Eof => break,
            _ => (),
        }
    }
    if !path.is_empty() || !entry.is_empty() || !custom.is_empty() {
        return invalid();
    }
    Ok(())
}

#[cfg(test)]
mod lumen_tests {
    use super::*;
    #[test]
    fn bounded_xml_rejects_duplicate_ids_fields_and_nested_history() {
        for xml in [
            "<Entry><UUID>A</UUID><String><Key>x</Key></String><String><Key>x</Key></String></Entry>",
            "<Entry><UUID>A</UUID><History><Entry><UUID>B</UUID></Entry></History></Entry>",
            "<Entry><UUID>A</UUID><History><Entry><UUID>A</UUID><History/></Entry></History></Entry>",
            "<Root><Entry><UUID>A</UUID></Entry><Entry><UUID>A</UUID></Entry></Root>",
            "<Root><Binary>AAAA</Binary></Root>",
            "<!DOCTYPE KeePassFile><Root/>",
            "<CustomData><Item><Key/><Value>a</Value></Item><Item><Key/><Value>b</Value></Item></CustomData>",
            "<CustomData><Item><Key>x</Key><Value>a</Value></Item><Item><Key>x</Key><Value>b</Value></Item></CustomData>",
        ] {
            assert!(check(xml.as_bytes()).is_err(), "accepted malformed profile");
        }
        assert!(
            check(
                b"<Root><CustomData><Item><Key>x</Key><Value>a</Value></Item></CustomData></Root>"
            )
            .is_ok()
        );
        let deep = format!("{}{}", "<Group>".repeat(50), "</Group>".repeat(50));
        assert!(check(deep.as_bytes()).is_err());
        assert!(check(b"<Entry><UUID>A</UUID><String><Key>a&amp;b</Key></String><History><Entry><UUID>A</UUID></Entry></History></Entry>").is_ok());
    }
}

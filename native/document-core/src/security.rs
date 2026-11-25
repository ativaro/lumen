//! PDF standard security handlers (revisions 2 to 6), from ISO 32000 clause 7.6.4. Key derivation,
//! object decryption and filter selection are Lumen code; SASLprep is the `stringprep` crate;
//! MD5, SHA-2 and the AES block cipher are general primitives from RustCrypto.
use std::rc::Rc;

use aes::cipher::{BlockCipherDecrypt, BlockCipherEncrypt, KeyInit};
use md5::{Digest, Md5};
use sha2::{Sha256, Sha384, Sha512};

use crate::pdf::{Dict, Error, Outcome, Ref, Stream, Value, integer};

const PAD: [u8; 32] = [
    0x28, 0xbf, 0x4e, 0x5e, 0x4e, 0x75, 0x8a, 0x41, 0x64, 0x00, 0x4e, 0x56, 0xff, 0xfa, 0x01, 0x08,
    0x2e, 0x2e, 0x00, 0xb6, 0xd0, 0x68, 0x3e, 0x80, 0x2f, 0x0c, 0xa9, 0xfe, 0x64, 0x53, 0x69, 0x7a,
];

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

fn unsupported<T>(text: &str) -> Outcome<T> {
    Err(Error::Unsupported(text.into()))
}

/// The message that asks the Reader for a password.
pub const PASSWORD: &str = "PDF-Passwort erforderlich oder nicht korrekt.";

fn rc4(key: &[u8], data: &[u8]) -> Outcome<Vec<u8>> {
    if !(5..=16).contains(&key.len()) {
        return bad("Ungültiger PDF-RC4-Schlüssel.");
    }
    let mut state: Vec<u8> = (0..=255).collect();
    let mut j = 0u8;
    for i in 0..256 {
        j = j.wrapping_add(state[i]).wrapping_add(key[i % key.len()]);
        state.swap(i, j as usize);
    }
    let (mut i, mut j) = (0u8, 0u8);
    Ok(data
        .iter()
        .map(|byte| {
            i = i.wrapping_add(1);
            j = j.wrapping_add(state[i as usize]);
            state.swap(i as usize, j as usize);
            byte ^ state[state[i as usize].wrapping_add(state[j as usize]) as usize]
        })
        .collect())
}

enum Cipher {
    Small(Box<aes::Aes128>),
    Large(Box<aes::Aes256>),
}

impl Cipher {
    fn new(key: &[u8]) -> Outcome<Cipher> {
        let invalid =
            |_| Error::Pdf("Ungültiger PDF-AES-Schlüssel oder Initialisierungsvektor.".into());
        match key.len() {
            16 => Ok(Cipher::Small(Box::new(
                aes::Aes128::new_from_slice(key).map_err(invalid)?,
            ))),
            32 => Ok(Cipher::Large(Box::new(
                aes::Aes256::new_from_slice(key).map_err(invalid)?,
            ))),
            _ => bad("Ungültiger PDF-AES-Schlüssel oder Initialisierungsvektor."),
        }
    }
    fn decrypt(&self, block: &mut [u8]) {
        let block = <&mut aes::Block>::try_from(block).expect("AES works on 16-byte blocks");
        match self {
            Cipher::Small(cipher) => cipher.decrypt_block(block),
            Cipher::Large(cipher) => cipher.decrypt_block(block),
        }
    }
    fn encrypt(&self, block: &mut [u8]) {
        let block = <&mut aes::Block>::try_from(block).expect("AES works on 16-byte blocks");
        match self {
            Cipher::Small(cipher) => cipher.encrypt_block(block),
            Cipher::Large(cipher) => cipher.encrypt_block(block),
        }
    }
}

const FAILED: &str = "PDF-Entschlüsselung fehlgeschlagen oder Daten beschädigt.";

/// AES in CBC mode; with `padding` the PKCS#7 padding is checked and removed.
fn cbc_decrypt(key: &[u8], iv: &[u8], data: &[u8], padding: bool) -> Outcome<Vec<u8>> {
    if iv.len() != 16 || !data.len().is_multiple_of(16) || data.len() > 512 * 1024 * 1024 {
        return bad(FAILED);
    }
    let cipher = Cipher::new(key)?;
    let mut out = data.to_vec();
    let mut previous = iv.to_vec();
    for block in out.chunks_mut(16) {
        let stored = block.to_vec();
        cipher.decrypt(block);
        for (byte, mask) in block.iter_mut().zip(&previous) {
            *byte ^= mask;
        }
        previous = stored;
    }
    if padding {
        let count = *out.last().ok_or(Error::Pdf(FAILED.into()))? as usize;
        if !(1..=16).contains(&count)
            || count > out.len()
            || out[out.len() - count..]
                .iter()
                .any(|byte| *byte as usize != count)
        {
            return bad(FAILED);
        }
        out.truncate(out.len() - count);
    }
    Ok(out)
}

fn cbc_encrypt(key: &[u8], iv: &[u8], data: &[u8]) -> Outcome<Vec<u8>> {
    if iv.len() != 16 || !data.len().is_multiple_of(16) {
        return bad(FAILED);
    }
    let cipher = Cipher::new(key)?;
    let mut out = data.to_vec();
    let mut previous = iv.to_vec();
    for block in out.chunks_mut(16) {
        for (byte, mask) in block.iter_mut().zip(&previous) {
            *byte ^= mask;
        }
        cipher.encrypt(block);
        previous = block.to_vec();
    }
    Ok(out)
}

/// The password hash of revisions 5 and 6 (ISO 32000-2, algorithm 2.B).
fn hash6(password: &[u8], salt: &[u8], user: &[u8], revision: i64) -> Outcome<Vec<u8>> {
    let mut result = Sha256::digest([password, salt, user].concat()).to_vec();
    if revision == 5 {
        return Ok(result);
    }
    let (mut rounds, mut end) = (0i64, 0i64);
    while rounds < 64 || end > rounds - 32 {
        let block = [password, &result, user].concat().repeat(64);
        let encoded = cbc_encrypt(&result[..16], &result[16..32], &block)?;
        result = match encoded[..16]
            .iter()
            .map(|byte| u32::from(*byte))
            .sum::<u32>()
            % 3
        {
            0 => Sha256::digest(&encoded).to_vec(),
            1 => Sha384::digest(&encoded).to_vec(),
            _ => Sha512::digest(&encoded).to_vec(),
        };
        rounds += 1;
        end = i64::from(*encoded.last().unwrap_or(&0));
        if rounds > 288 {
            return bad("PDF-Passworthash überschreitet sein Budget.");
        }
    }
    result.truncate(32);
    Ok(result)
}

#[derive(Clone, Copy, PartialEq)]
enum Method {
    Identity,
    V2,
    AesV2,
    AesV3,
}

pub struct Security {
    key: Vec<u8>,
    streams: Method,
    strings: Method,
    metadata: bool,
}

impl Security {
    /// `attrs` is the resolved encryption dictionary, `identifiers` the trailer's ID entry.
    pub fn new(attrs: &Dict, identifiers: Option<&Value>, password: &str) -> Outcome<Security> {
        if attrs.get("Filter").and_then(Value::name) != Some("Standard") {
            return unsupported("PDF-Sicherheitsverfahren wird nicht unterstützt.");
        }
        let revision = integer(attrs.get("R").unwrap_or(&Value::Null), 2, 6)?;
        let version = attrs.get("V").and_then(|v| {
            if let Value::Int(v) = v {
                Some(*v)
            } else {
                None
            }
        });
        let metadata = match attrs.get("EncryptMetadata") {
            None => true,
            Some(Value::Bool(flag)) => *flag,
            _ => return bad("Ungültige PDF-Metadatenverschlüsselung."),
        };
        // A set of 32 flags: most writers give it as a negative number, some as the same bits unsigned.
        let permissions = (integer(
            attrs.get("P").unwrap_or(&Value::Null),
            -(1 << 31),
            (1 << 32) - 1,
        )? as u32)
            .to_le_bytes();
        if password.chars().count() > 10000 {
            return bad("PDF-Passwort zu lang oder ungültig.");
        }
        let password: Vec<u8> = if revision < 5 {
            let latin: Option<Vec<u8>> = password
                .chars()
                .map(|c| u8::try_from(c as u32).ok())
                .collect();
            let Some(mut latin) = latin else {
                return bad("PDF-Passwort ist nicht korrekt.");
            };
            latin.truncate(32);
            latin
        } else {
            match unicode_password(password, revision) {
                Some(prepared) => prepared,
                None => return bad("PDF-Passwort ist nicht korrekt."),
            }
        };
        let text = |key: &str, size: usize| -> Option<&[u8]> {
            match attrs.get(key) {
                Some(Value::Text(bytes)) if bytes.len() == size => Some(bytes.as_slice()),
                _ => None,
            }
        };
        let expected = if revision >= 5 { 48 } else { 32 };
        let (Some(owner), Some(user)) = (text("O", expected), text("U", expected)) else {
            return bad("Ungültige PDF-Passwortdaten.");
        };
        let key = if revision >= 5 {
            let length = attrs.get("Length").cloned().unwrap_or(Value::Int(256));
            if version != Some(5) || !matches!(length, Value::Int(256)) {
                return unsupported("Unbekannte PDF-AES-256-Konfiguration.");
            }
            let (Some(owner_key), Some(user_key), Some(perms)) =
                (text("OE", 32), text("UE", 32), text("Perms", 16))
            else {
                return bad("Ungültige PDF-Schlüsseldaten.");
            };
            let mut key = None;
            for (entry, encrypted, salt_user) in
                [(owner, owner_key, user), (user, user_key, &[][..])]
            {
                if hash6(&password, &entry[32..40], salt_user, revision)? == entry[..32] {
                    key = Some(cbc_decrypt(
                        &hash6(&password, &entry[40..48], salt_user, revision)?,
                        &[0; 16],
                        encrypted,
                        false,
                    )?);
                    break;
                }
            }
            let Some(key) = key else { return bad(PASSWORD) };
            let mut check = perms.to_vec();
            Cipher::new(&key)?.decrypt(&mut check);
            if check[..4] != permissions
                || check[4..8] != [0xff; 4]
                || check[8..12] != [if metadata { b'T' } else { b'F' }, b'a', b'd', b'b']
            {
                return bad("PDF-Berechtigungsprüfung fehlgeschlagen.");
            }
            key
        } else {
            if !matches!(version, Some(1 | 2 | 4)) {
                return unsupported("Unbekannte ältere PDF-Verschlüsselung.");
            }
            let first = match identifiers
                .and_then(Value::array)
                .and_then(|list| list.first())
            {
                Some(Value::Text(first)) => (**first).clone(),
                _ => return bad("PDF-Dateikennung zur Entschlüsselung fehlt."),
            };
            let bits = match attrs.get("Length") {
                None => 40,
                Some(Value::Int(bits)) if (40..=128).contains(bits) && bits % 8 == 0 => *bits,
                _ => return bad("Ungültige PDF-Schlüssellänge."),
            };
            let length = if revision == 2 { 5 } else { bits as usize / 8 };
            let padded = |candidate: &[u8]| [candidate, &PAD].concat()[..32].to_vec();
            let key_for = |candidate: &[u8]| -> Vec<u8> {
                let mut raw = [
                    padded(candidate),
                    owner.to_vec(),
                    permissions.to_vec(),
                    first.clone(),
                ]
                .concat();
                if revision == 4 && !metadata {
                    raw.extend([0xff; 4]);
                }
                let mut digest = Md5::digest(&raw).to_vec();
                if revision >= 3 {
                    for _ in 0..50 {
                        digest = Md5::digest(&digest[..length]).to_vec();
                    }
                }
                digest[..length].to_vec()
            };
            let valid = |candidate: &[u8]| -> Outcome<Option<Vec<u8>>> {
                let key = key_for(candidate);
                let expected = if revision == 2 {
                    rc4(&key, &PAD)?
                } else {
                    let mut expected = rc4(&key, &Md5::digest([&PAD[..], &first].concat()))?;
                    for turn in 1..20u8 {
                        expected = rc4(
                            &key.iter().map(|byte| byte ^ turn).collect::<Vec<_>>(),
                            &expected,
                        )?;
                    }
                    expected
                };
                Ok((expected[..] == user[..expected.len()]).then_some(key))
            };
            let mut key = valid(&password)?;
            if key.is_none() {
                let mut digest = Md5::digest(padded(&password)).to_vec();
                if revision >= 3 {
                    for _ in 0..50 {
                        digest = Md5::digest(&digest).to_vec();
                    }
                }
                let owner_key = &digest[..length];
                let mut candidate = owner.to_vec();
                let turns: Vec<u8> = if revision >= 3 {
                    (0..20).rev().collect()
                } else {
                    vec![0]
                };
                for turn in turns {
                    candidate = rc4(
                        &owner_key.iter().map(|byte| byte ^ turn).collect::<Vec<_>>(),
                        &candidate,
                    )?;
                }
                key = valid(&candidate)?;
            }
            let Some(key) = key else { return bad(PASSWORD) };
            key
        };
        let method = |slot: &str| -> Outcome<Method> {
            if version.unwrap_or(0) < 4 {
                return Ok(Method::V2);
            }
            let selected = attrs.get(slot).and_then(Value::name).unwrap_or("Identity");
            if selected == "Identity" {
                return Ok(Method::Identity);
            }
            let filter = "PDF-Kryptofilter wird nicht unterstützt.";
            let info = attrs
                .get("CF")
                .and_then(Value::dict)
                .and_then(|filters| filters.get(selected))
                .and_then(Value::dict);
            let Some(info) = info.filter(|info| {
                info.get("AuthEvent")
                    .and_then(Value::name)
                    .unwrap_or("DocOpen")
                    == "DocOpen"
            }) else {
                return unsupported(filter);
            };
            match (info.get("CFM").and_then(Value::name), revision >= 5) {
                (Some("AESV3"), true) => Ok(Method::AesV3),
                (Some("V2"), false) => Ok(Method::V2),
                (Some("AESV2"), false) => Ok(Method::AesV2),
                _ => unsupported(filter),
            }
        };
        Ok(Security {
            streams: method("StmF")?,
            strings: method("StrF")?,
            key,
            metadata,
        })
    }

    fn decrypt(&self, data: &[u8], reference: Ref, method: Method) -> Outcome<Vec<u8>> {
        let key = match method {
            Method::Identity => return Ok(data.to_vec()),
            Method::AesV3 => self.key.clone(),
            _ => {
                let mut material = [
                    &self.key[..],
                    &(reference.number as u32).to_le_bytes()[..3],
                    &(reference.generation as u32).to_le_bytes()[..2],
                ]
                .concat();
                if method == Method::AesV2 {
                    material.extend(b"sAlT");
                }
                Md5::digest(&material)[..(self.key.len() + 5).min(16)].to_vec()
            }
        };
        if method == Method::V2 {
            return rc4(&key, data);
        }
        if data.len() < 32 || !data.len().is_multiple_of(16) {
            return bad("Ungültige verschlüsselte PDF-Daten.");
        }
        cbc_decrypt(&key, &data[..16], &data[16..], true)
    }

    /// An object as it reads after decryption: its strings and its stream data.
    pub fn value(
        &self,
        value: &Value,
        reference: Ref,
        resolve: &dyn Fn(&Value) -> Outcome<Value>,
    ) -> Outcome<Value> {
        Ok(match value {
            Value::Stream(stream) => {
                if stream.attrs.get("Type").and_then(Value::name) == Some("XRef") {
                    return Ok(value.clone());
                }
                let attrs = self.dict(&stream.attrs, reference, resolve)?;
                let mut method = self.streams;
                if attrs.get("Type").and_then(Value::name) == Some("Metadata") && !self.metadata {
                    method = Method::Identity;
                }
                let filters = match resolve(attrs.get("Filter").unwrap_or(&Value::Null))? {
                    Value::Null => Vec::new(),
                    Value::Name(name) => vec![Value::Name(name)],
                    Value::Array(filters) => (*filters).clone(),
                    _ => return bad("Ungültige PDF-Kryptofilterkette."),
                };
                for filter in &filters {
                    if resolve(filter)?.name() == Some("Crypt") {
                        return unsupported(
                            "Expliziter PDF-Stream-Kryptofilter wird noch nicht unterstützt.",
                        );
                    }
                }
                Value::Stream(Rc::new(Stream {
                    raw: self.decrypt(&stream.raw, reference, method)?,
                    attrs,
                }))
            }
            Value::Text(bytes) => {
                Value::Text(Rc::new(self.decrypt(bytes, reference, self.strings)?))
            }
            Value::Array(items) => Value::Array(Rc::new(
                items
                    .iter()
                    .map(|item| self.value(item, reference, resolve))
                    .collect::<Outcome<_>>()?,
            )),
            Value::Dict(dict) => Value::Dict(Rc::new(self.dict(dict, reference, resolve)?)),
            other => other.clone(),
        })
    }

    fn dict(
        &self,
        dict: &Dict,
        reference: Ref,
        resolve: &dyn Fn(&Value) -> Outcome<Value>,
    ) -> Outcome<Dict> {
        dict.iter()
            .map(|(key, value)| Ok((key.clone(), self.value(value, reference, resolve)?)))
            .collect()
    }
}

/// The bytes of a password for AES-256: prepared with SASLprep (RFC 4013) in revision 6, at most 127 bytes.
/// None when SASLprep forbids it; such a password cannot be the right one.
fn unicode_password(password: &str, revision: i64) -> Option<Vec<u8>> {
    let prepared = if revision == 6 {
        stringprep::saslprep(password).ok()?.into_owned()
    } else {
        password.to_string()
    };
    Some(prepared.as_bytes()[..prepared.len().min(127)].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hex(text: &str) -> Vec<u8> {
        (0..text.len() / 2)
            .map(|i| u8::from_str_radix(&text[2 * i..2 * i + 2], 16).unwrap())
            .collect()
    }

    #[test]
    fn permission_flags_are_read_signed_or_unsigned() {
        // pypdf writes the 32 flags as an unsigned number; the handler is reached all the same and
        // asks for the password instead of refusing the number.
        let attrs = |flags: i64| {
            let text = |byte: u8| Value::Text(Rc::new(vec![byte; 32]));
            Dict::from_iter([
                ("Filter".to_string(), Value::Name("Standard".into())),
                ("V".to_string(), Value::Int(2)),
                ("R".to_string(), Value::Int(3)),
                ("Length".to_string(), Value::Int(128)),
                ("P".to_string(), Value::Int(flags)),
                ("O".to_string(), text(1)),
                ("U".to_string(), text(2)),
            ])
        };
        let identifiers = Value::Array(Rc::new(vec![Value::Text(Rc::new(b"file".to_vec()))]));
        let asked = |flags: i64| {
            let refused = Security::new(&attrs(flags), Some(&identifiers), "").err();
            refused.map(|error| error.to_string())
        };
        assert_eq!(asked(-4).as_deref(), Some(PASSWORD));
        assert_eq!(asked(4_294_967_292).as_deref(), Some(PASSWORD));
        assert_ne!(asked(4_294_967_296).as_deref(), Some(PASSWORD));
    }

    #[test]
    fn revision_six_passwords_are_prepared_with_saslprep() {
        // RFC 4013, section 3.
        assert_eq!(unicode_password("I\u{AD}X", 6).unwrap(), b"IX");
        assert_eq!(unicode_password("user", 6).unwrap(), b"user");
        assert_eq!(unicode_password("\u{AA}", 6).unwrap(), b"a");
        assert_eq!(unicode_password("\u{2168}", 6).unwrap(), b"IX");
        assert!(unicode_password("\u{7}", 6).is_none());
        // Revision 5 takes the UTF-8 bytes as they are.
        assert_eq!(
            unicode_password("\u{2168}", 5).unwrap(),
            "\u{2168}".as_bytes()
        );
        assert_eq!(unicode_password(&"ä".repeat(100), 6).unwrap().len(), 127);
    }

    #[test]
    fn primitives_match_their_published_vectors() {
        assert_eq!(
            rc4(&hex("0102030405"), &[0; 16]).unwrap(),
            hex("b2396305f03dc027ccc3524a0a1118a8")
        );
        let key = hex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4");
        let iv = hex("000102030405060708090a0b0c0d0e0f");
        let plain = hex("6bc1bee22e409f96e93d7e117393172a");
        let coded = cbc_encrypt(&key, &iv, &plain).unwrap();
        assert_eq!(coded, hex("f58c4c04d6e5f1ba779eabfb5f7bfbd6"));
        assert_eq!(cbc_decrypt(&key, &iv, &coded, false).unwrap(), plain);
        assert!(cbc_decrypt(&key, &iv, &coded, true).is_err());
        assert!(rc4(&[1, 2], &[0]).is_err());
        assert_eq!(hash6(b"", &[0; 8], &[], 5).unwrap().len(), 32);
        assert_eq!(hash6(b"", &[0; 8], &[], 6).unwrap().len(), 32);
    }
}

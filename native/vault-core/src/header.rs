//! Bounded public-header admission, BEFORE the third-party parser or KDF runs.
//! This is format validation, not a replacement for KDBX authentication.
use crate::{Error, Result};
use std::collections::BTreeMap;

pub const MAX_FILE: usize = 64 * 1024 * 1024;
const MAX_HEADER: usize = 64 * 1024;
const ARGON2ID: &[u8] = &hex_bytes();
const fn hex_bytes() -> [u8; 16] {
    [
        0x9e, 0x29, 0x8b, 0x19, 0x56, 0xdb, 0x47, 0x73, 0xb2, 0x3d, 0xfc, 0x3e, 0xc6, 0xf0, 0xa1,
        0xe6,
    ]
}
const AES256: &[u8] = &[
    0x31, 0xc1, 0xf2, 0xe6, 0xbf, 0x71, 0x43, 0x50, 0xbe, 0x58, 0x05, 0x21, 0x6a, 0xfc, 0x5a, 0xff,
];

fn take<'a>(bytes: &mut &'a [u8], n: usize) -> Result<&'a [u8]> {
    if n > bytes.len() {
        return Err(Error::InvalidFile);
    }
    let (part, rest) = bytes.split_at(n);
    *bytes = rest;
    Ok(part)
}
fn number(bytes: &mut &[u8], n: usize) -> Result<u64> {
    Ok(take(bytes, n)?
        .iter()
        .enumerate()
        .fold(0, |v, (i, b)| v | (u64::from(*b) << (8 * i))))
}

#[derive(Debug, PartialEq, Eq)]
pub struct Profile {
    pub memory: u64,
    pub iterations: u64,
    pub parallelism: u64,
}

pub fn inspect(blob: &[u8]) -> Result<Profile> {
    if blob.len() > MAX_FILE {
        return Err(Error::Limit);
    }
    let mut bytes = blob;
    let signature = take(&mut bytes, 12)?;
    if signature[..8] != [0x03, 0xd9, 0xa2, 0x9a, 0x67, 0xfb, 0x4b, 0xb5]
        || ![&[0, 0, 4, 0][..], &[1, 0, 4, 0][..]].contains(&&signature[8..])
    {
        return Err(Error::Unsupported);
    }
    let mut fields = BTreeMap::new();
    loop {
        let tag = number(&mut bytes, 1)?;
        let size = number(&mut bytes, 4)? as usize;
        if size > MAX_HEADER || blob.len() - bytes.len() + size > MAX_HEADER {
            return Err(Error::Limit);
        }
        let value = take(&mut bytes, size)?;
        if fields.insert(tag, value).is_some() {
            return Err(Error::InvalidFile);
        }
        if tag == 0 {
            if !value.is_empty() && value != b"\r\n\r\n" {
                return Err(Error::InvalidFile);
            }
            break;
        }
        if ![1, 2, 3, 4, 7, 11].contains(&tag) {
            return Err(Error::Unsupported);
        }
    }
    if fields.get(&2).copied() != Some(AES256) {
        return Err(Error::Unsupported);
    }
    // Only uncompressed or gzip; decompression is bounded in the vendored parser.
    if ![Some(&[0, 0, 0, 0][..]), Some(&[1, 0, 0, 0][..])].contains(&fields.get(&3).copied()) {
        return Err(Error::Unsupported);
    }
    if fields.get(&4).map(|v| v.len()) != Some(32) || fields.get(&7).map(|v| v.len()) != Some(16) {
        return Err(Error::InvalidFile);
    }
    let mut variants = *fields.get(&11).ok_or(Error::InvalidFile)?;
    if take(&mut variants, 2)? != [0, 1] {
        return Err(Error::Unsupported);
    }
    let mut kdf = BTreeMap::new();
    loop {
        let kind = number(&mut variants, 1)?;
        if kind == 0 {
            break;
        }
        let size = number(&mut variants, 4)? as usize;
        if size > 32 {
            return Err(Error::Limit);
        }
        let key = take(&mut variants, size)?;
        let size = number(&mut variants, 4)? as usize;
        if size > 64 {
            return Err(Error::Limit);
        }
        let value = take(&mut variants, size)?;
        if kdf.insert(key, (kind, value)).is_some() {
            return Err(Error::InvalidFile);
        }
    }
    if !variants.is_empty() || kdf.len() != 6 {
        return Err(Error::Unsupported);
    }
    if kdf.get(&b"$UUID"[..]).copied() != Some((0x42, ARGON2ID)) {
        return Err(Error::Unsupported);
    }
    match kdf.get(&b"S"[..]) {
        Some((0x42, v)) if v.len() == 32 => (),
        _ => return Err(Error::InvalidFile),
    }
    let read = |key: &[u8], kind, width| -> Result<u64> {
        let (t, mut v) = kdf.get(key).copied().ok_or(Error::InvalidFile)?;
        if t != kind || v.len() != width {
            return Err(Error::InvalidFile);
        }
        number(&mut v, width)
    };
    if read(b"V", 4, 4)? != 0x13 {
        return Err(Error::Unsupported);
    }
    let p = Profile {
        memory: read(b"M", 5, 8)?,
        iterations: read(b"I", 5, 8)?,
        parallelism: read(b"P", 4, 4)?,
    };
    if !(8 * 1024 * 1024..=256 * 1024 * 1024).contains(&p.memory)
        || p.memory % 1024 != 0
        || !(1..=16).contains(&p.iterations)
        || !(1..=4).contains(&p.parallelism)
    {
        return Err(Error::Limit);
    }
    Ok(p)
}

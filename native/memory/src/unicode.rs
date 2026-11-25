//! The Unicode 16 identities of Notes and the memory search, independent of Rust's Unicode version:
//! what Python 3 (Unicode 16.0.0) calls alphanumeric, digit and wide, and its folding.
use caseless::Caseless;
use unicode_normalization::UnicodeNormalization;
#[path = "unicode_data.rs"]
mod data;

fn contains(table: &[(u32, u32)], ch: char) -> bool {
    let n = u32::from(ch);
    table
        .get(table.partition_point(|(_, end)| *end < n))
        .is_some_and(|(start, _)| *start <= n)
}
/// Python's `str.isalnum()` or `_` (the `\w` of its regular expressions).
pub fn word(ch: char) -> bool {
    contains(data::WORD, ch)
}
/// Python's `str.isdigit()`.
pub fn digit(ch: char) -> bool {
    contains(data::DIGIT, ch)
}
/// Python's `str.isspace()`: Unicode white space and the separators U+001C..U+001F.
pub fn whitespace(ch: char) -> bool {
    ch.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&ch)
}
/// The identity of a Notes tag: NFC, then case folded.
pub fn tag_fold(value: &str) -> String {
    value.nfc().default_case_fold().collect()
}
/// East Asian width wide or fullwidth.
pub fn wide(ch: char) -> bool {
    contains(data::WIDE, ch)
}
/// The form searches compare: NFKC, then case folded.
pub fn search_fold(value: &str) -> String {
    value.nfkc().default_case_fold().collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};

    #[test]
    fn all_unicode_scalars_match_independent_python_reference() {
        assert_eq!(caseless::UNICODE_VERSION, (16, 0, 0));
        assert_eq!(unicode_normalization::UNICODE_VERSION, (16, 0, 0));
        let mut digest = Sha256::new();
        for ch in (0..=0x10ffff).filter_map(char::from_u32) {
            digest.update([u8::from(word(ch)), u8::from(digit(ch))]);
            let value = ch.to_string();
            for text in [
                caseless::default_case_fold_str(&value),
                value.nfc().collect::<String>(),
                search_fold(&value),
            ] {
                digest.update(u16::try_from(text.len()).unwrap().to_le_bytes());
                digest.update(text.as_bytes());
            }
        }
        let actual: String = digest
            .finalize()
            .iter()
            .map(|v| format!("{v:02x}"))
            .collect();
        assert_eq!(actual, data::SCALAR_DIGEST);
    }
}

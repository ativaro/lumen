//! Experimental qualification core. Not yet approved for real credentials.
//! No engine errors or field contents are formatted into errors.
pub const PRODUCTION_READY: bool = false;
pub mod header;
#[derive(Debug, PartialEq, Eq)]
pub enum Error {
    Io,
    InvalidFile,
    Unsupported,
    Limit,
    UnlockFailed,
    Busy,
    Conflict,
    InvalidInput,
    Locked,
    Compatibility,
}
pub type Result<T> = std::result::Result<T, Error>;
impl From<std::io::Error> for Error {
    fn from(_: std::io::Error) -> Self {
        Self::Io
    }
}

mod store;

mod probe;
pub use probe::qualify;

/// Fixed default length; website-specific rules belong to a later native UI.
fn generate_password() -> Result<zeroize::Zeroizing<String>> {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
    let mut random = zeroize::Zeroizing::new([0u8; 24]);
    getrandom::fill(random.as_mut()).map_err(|_| Error::Io)?;
    // Exactly 64 symbols: masking samples uniformly, without modulo bias.
    Ok(zeroize::Zeroizing::new(
        random
            .iter()
            .map(|b| ALPHABET[(b & 63) as usize] as char)
            .collect(),
    ))
}
#[cfg(test)]
mod generator_tests {
    #[test]
    fn os_generator_returns_fixed_length_url_safe_passwords() {
        let a = super::generate_password().unwrap();
        let b = super::generate_password().unwrap();
        assert_eq!(a.len(), 24);
        assert!(
            a.bytes()
                .all(|v| v.is_ascii_alphanumeric() || b"_-".contains(&v))
        );
        assert_ne!(a, b);
    }
}

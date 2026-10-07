#[cfg(feature = "save_kdbx4")]
use flate2::Compression as Flate2Compression;
use flate2::read::GzDecoder;
#[cfg(feature = "save_kdbx4")]
use flate2::write::GzEncoder;
use std::io::Read;
#[cfg(feature = "save_kdbx4")]
use std::io::Write;

pub trait Compression {
    #[cfg(feature = "save_kdbx4")]
    fn compress(&self, in_buffer: &[u8]) -> Result<Vec<u8>, std::io::Error>;
    fn decompress(&self, in_buffer: &[u8]) -> Result<Vec<u8>, std::io::Error>;
}

pub struct NoCompression;

impl Compression for NoCompression {
    #[cfg(feature = "save_kdbx4")]
    fn compress(&self, in_buffer: &[u8]) -> Result<Vec<u8>, std::io::Error> {
        Ok(in_buffer.to_vec())
    }
    fn decompress(&self, in_buffer: &[u8]) -> Result<Vec<u8>, std::io::Error> {
        Ok(in_buffer.to_vec())
    }
}

pub struct GZipCompression;

impl Compression for GZipCompression {
    #[cfg(feature = "save_kdbx4")]
    fn compress(&self, in_buffer: &[u8]) -> Result<Vec<u8>, std::io::Error> {
        let mut res = Vec::new();
        let mut encoder = GzEncoder::new(&mut res, Flate2Compression::default());
        encoder.write_all(in_buffer)?;
        encoder.flush()?;
        encoder.finish()?;
        Ok(res)
    }
    fn decompress(&self, in_buffer: &[u8]) -> Result<Vec<u8>, std::io::Error> {
        let mut res = Vec::new();
        let mut decoder = GzDecoder::new(in_buffer).take(64 * 1024 * 1024 + 1);
        decoder.read_to_end(&mut res)?;
        if res.len() > 64 * 1024 * 1024 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "decompressed payload limit",
            ));
        }
        Ok(res)
    }
}

#[cfg(all(test, feature = "save_kdbx4"))]
mod lumen_tests {
    use super::*;
    #[test]
    fn gzip_expansion_is_bounded() {
        let compressed = GZipCompression
            .compress(&vec![b'x'; 64 * 1024 * 1024 + 1])
            .unwrap();
        assert!(GZipCompression.decompress(&compressed).is_err());
        let text = b"bounded synthetic data";
        assert_eq!(
            GZipCompression
                .decompress(&GZipCompression.compress(text).unwrap())
                .unwrap(),
            text
        );
    }
}

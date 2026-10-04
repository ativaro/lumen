//! Execute the exact vendored admission source without upstream fixture dependencies.
#[derive(Debug)]
enum ParseXmlError {
    Admission,
}
#[path = "../vendor/keepass/src/format/xml_db/admission.rs"]
mod admission;
#[allow(unexpected_cfgs, dead_code)]
#[path = "../vendor/keepass/src/compression.rs"]
mod compression;
#[test]
fn gzip_output_cannot_exceed_bound() {
    use compression::Compression;
    use std::io::Write;
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::fast());
    let block = [b'x'; 65536];
    for _ in 0..1025 {
        encoder.write_all(&block).unwrap();
    }
    let data = encoder.finish().unwrap();
    assert!(compression::GZipCompression.decompress(&data).is_err());
}

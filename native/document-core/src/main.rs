//! `lumen-document office <file> [--label German=Translation]...` prints `{"title": ..., "sections": [...]}`.
use std::collections::HashMap;
use std::process::ExitCode;

fn json(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Page count, title, outline and, per page, its box and a fingerprint of its decoded content.
fn pdf_info(path: &str) -> Result<String, lumen_document::pdf::Error> {
    use lumen_document::pdf::{Document, Value};
    let document = Document::open(std::path::Path::new(path), &password())?;
    let toc: Vec<String> = document
        .toc()?
        .iter()
        .map(|(level, title, page)| format!("[{level}, {}, {page}]", json(title)))
        .collect();
    let mut pages = Vec::new();
    for (index, page) in document.pages.iter().enumerate() {
        let content = document.contents(index)?;
        // A checksum is enough to see that both readers decoded the same bytes.
        let mut sum = flate2::Crc::new();
        sum.update(&content);
        let print = sum.sum();
        let corners: Vec<String> = page
            .get("MediaBox")
            .and_then(Value::array)
            .map(|b| {
                b.iter()
                    .map(|v| v.number().unwrap_or(0.0).to_string())
                    .collect()
            })
            .unwrap_or_default();
        pages.push(format!(
            "{{\"box\": [{}], \"length\": {}, \"print\": {print}}}",
            corners.join(", "),
            content.len()
        ));
    }
    let title = document.metadata.get("title").cloned().unwrap_or_default();
    Ok(format!(
        "{{\"pages\": {}, \"title\": {}, \"toc\": [{}], \"content\": [{}]}}",
        document.pages.len(),
        json(&title),
        toc.join(", "),
        pages.join(", ")
    ))
}

/// The words of pages `first .. first + count`, one JSON object per page; a page that cannot be read carries its message.
fn pdf_words(path: &str, first: usize, count: usize) -> Result<String, lumen_document::pdf::Error> {
    let document = lumen_document::pdf::Document::open(std::path::Path::new(path), &password())?;
    let mut pages = Vec::new();
    for index in first..document.pages.len().min(first + count) {
        pages.push(match lumen_document::text::Page::words(&document, index) {
            Ok((width, height, words)) => {
                let words: Vec<String> = words
                    .iter()
                    .map(|w| {
                        format!(
                            "[{}, {}, {}, {}, {}, {}]",
                            w.left,
                            w.top,
                            w.right,
                            w.bottom,
                            json(&w.text),
                            w.line
                        )
                    })
                    .collect();
                format!(
                    "{{\"width\": {width}, \"height\": {height}, \"words\": [{}]}}",
                    words.join(", ")
                )
            }
            Err(error) => format!("{{\"error\": {}}}", json(&error.to_string())),
        });
    }
    Ok(format!("[{}]", pages.join(", ")))
}

/// The password for an encrypted PDF: one line on standard input when `LUMEN_PDF_PASSWORD_STDIN` is set,
/// so that it never appears in an argument list. Without it the empty password is tried.
fn password() -> String {
    static GIVEN: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    GIVEN
        .get_or_init(|| {
            let mut line = String::new();
            if std::env::var_os("LUMEN_PDF_PASSWORD_STDIN").is_some() {
                let _ = std::io::stdin().read_line(&mut line);
            }
            line.trim_end_matches(['\r', '\n']).to_string()
        })
        .clone()
}

fn base64(data: &[u8]) -> String {
    const LETTERS: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let bits = u32::from(chunk[0]) << 16
            | u32::from(*chunk.get(1).unwrap_or(&0)) << 8
            | u32::from(*chunk.get(2).unwrap_or(&0));
        for index in 0..4 {
            out.push(if index <= chunk.len() {
                LETTERS[(bits >> (18 - 6 * index) & 63) as usize] as char
            } else {
                '='
            });
        }
    }
    out
}

/// What the Reader asks for: the document's outline data, and for `page` also that page's words and picture.
fn pdf_reader(path: &str, page: Option<usize>) -> Result<String, lumen_document::pdf::Error> {
    use lumen_document::pdf::{Document, Error};
    let document = Document::open(std::path::Path::new(path), &password())?;
    let toc: Vec<String> = document
        .toc()?
        .iter()
        .take(2000)
        .map(|(level, title, page)| format!("[{level}, {}, {page}]", json(title)))
        .collect();
    let title = document.metadata.get("title").cloned().unwrap_or_default();
    let mut out = format!(
        "{{\"pages\": {}, \"title\": {}, \"toc\": [{}]",
        document.pages.len(),
        json(&title),
        toc.join(", ")
    );
    if let Some(index) = page {
        if index >= document.pages.len() {
            return Err(Error::Pdf("Seite nicht vorhanden.".into()));
        }
        let (width, height, words) = lumen_document::text::Page::words(&document, index)?;
        let scale = f64::min(2.0, f64::min(1800.0 / width, 2600.0 / height));
        let picture = lumen_document::render::render(&document, index, scale)?;
        let png = picture
            .encode_png()
            .map_err(|_| Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into()))?;
        let words: Vec<String> = words
            .iter()
            .map(|w| {
                format!(
                    "[{}, {}, {}, {}, {}, 0, {}]",
                    w.left,
                    w.top,
                    w.right,
                    w.bottom,
                    json(&w.text),
                    w.line
                )
            })
            .collect();
        out.push_str(&format!(", \"page\": {index}, \"width\": {width}, \"height\": {height}, \"words\": [{}], \"png\": \"{}\"", words.join(", "), base64(&png)));
    }
    out.push('}');
    Ok(out)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() == 5 && args[0] == "pdf-render" {
        // pdf-render <file> <page> <scale> <png>
        let drawn =
            lumen_document::pdf::Document::open(std::path::Path::new(&args[1]), &password())
                .and_then(|document| {
                    lumen_document::render::render(
                        &document,
                        args[2].parse().unwrap_or(0),
                        args[3].parse().unwrap_or(1.0),
                    )
                });
        return match drawn.map(|picture| picture.save_png(&args[4])) {
            Ok(Ok(())) => ExitCode::SUCCESS,
            Ok(Err(error)) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        };
    }
    if (args.len() == 3 || args.len() == 4)
        && args[0] == "pdf-reader"
        && matches!(args[2].as_str(), "metadata" | "page")
    {
        // pdf-reader <file> metadata | pdf-reader <file> page <index>
        let page = if args[2] == "page" {
            args.get(3).and_then(|index| index.parse().ok())
        } else {
            None
        };
        if (args[2] == "page") != page.is_some() {
            eprintln!("usage: lumen-document pdf-reader <file> metadata | page <index>");
            return ExitCode::from(2);
        }
        return match pdf_reader(&args[1], page) {
            Ok(text) => {
                println!("{text}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        };
    }
    if args.len() == 4 && args[0] == "pdf-words" {
        return match pdf_words(
            &args[1],
            args[2].parse().unwrap_or(0),
            args[3].parse().unwrap_or(1),
        ) {
            Ok(text) => {
                println!("{text}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        };
    }
    if args.len() == 2 && args[0] == "pdf-info" {
        return match pdf_info(&args[1]) {
            Ok(text) => {
                println!("{text}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        };
    }
    if args.len() < 2 || args[0] != "office" {
        eprintln!("usage: lumen-document office <file> [--label German=Translation]...");
        return ExitCode::from(2);
    }
    let mut labels = HashMap::new();
    let mut rest = args[2..].iter();
    while let Some(flag) = rest.next() {
        match (
            flag.as_str(),
            rest.next().and_then(|pair| pair.split_once('=')),
        ) {
            ("--label", Some((key, value))) => labels.insert(key.to_string(), value.to_string()),
            _ => {
                eprintln!("usage: lumen-document office <file> [--label German=Translation]...");
                return ExitCode::from(2);
            }
        };
    }
    match lumen_document::office::read(std::path::Path::new(&args[1]), &labels) {
        Ok(document) => {
            let sections: Vec<String> = document
                .sections
                .iter()
                .map(|section| json(section))
                .collect();
            println!(
                "{{\"title\": {}, \"sections\": [{}]}}",
                json(&document.title),
                sections.join(", ")
            );
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

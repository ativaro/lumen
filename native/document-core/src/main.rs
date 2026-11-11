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
    let document = Document::open(std::path::Path::new(path))?;
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
    let document = lumen_document::pdf::Document::open(std::path::Path::new(path))?;
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

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
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

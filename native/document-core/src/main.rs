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

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
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

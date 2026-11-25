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
        let picture = lumen_document::render::render_file(
            std::path::Path::new(path),
            &password(),
            index,
            scale,
            0,
        )?;
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

/// Text, document information and a rendered page for Files, search and the workshop:
/// `pdf-cli text|info|render <file> [--page n] [--rotation degrees] [--max-scale n] [--pages n] [--scale-to n]
/// [--output png] [--limit bytes] [--characters n]`.
fn pdf_cli(args: &[String]) -> ExitCode {
    let [action, path, options @ ..] = args else {
        eprintln!("usage: lumen-document pdf-cli text|info|render <file> [options]");
        return ExitCode::from(2);
    };
    let option = |name: &str| {
        options
            .iter()
            .position(|o| o == name)
            .and_then(|at| options.get(at + 1))
    };
    let whole = |name: &str, default: i64| {
        option(name).map_or(Some(default), |value| value.parse::<i64>().ok())
    };
    let run = || -> Result<Vec<u8>, String> {
        use lumen_document::pdf::Document;
        let invalid = || "Ungültige PDF-Ganzzahl oder überschrittenes Limit.".to_string();
        let mut document = Document::open(std::path::Path::new(path), &password())
            .map_err(|error| error.to_string())?;
        match action.as_str() {
            "info" => Ok(format!(
                "{{\"pages\": {}, \"title\": {}, \"encrypted\": {}}}\n",
                document.pages.len(),
                json(document.metadata.get("title").map_or("", String::as_str)),
                document.encrypted()
            )
            .into_bytes()),
            "render" => {
                let index = whole("--page", 0)
                    .filter(|index| (0..document.pages.len() as i64).contains(index))
                    .ok_or_else(invalid)? as usize;
                let edge = whole("--scale-to", 1500)
                    .filter(|edge| (1..=6000).contains(edge))
                    .ok_or_else(invalid)? as f64;
                let turn = whole("--rotation", 0).ok_or_else(invalid)?;
                let most = whole("--max-scale", 4)
                    .filter(|most| (1..=4).contains(most))
                    .ok_or_else(invalid)? as f64;
                document
                    .turn(index, turn)
                    .map_err(|error| error.to_string())?;
                let (width, height, _) = lumen_document::text::Page::words(&document, index)
                    .map_err(|error| error.to_string())?;
                let picture = lumen_document::render::render_file(
                    std::path::Path::new(path),
                    &password(),
                    index,
                    f64::min(most, edge / width.max(height)),
                    turn,
                )
                .map_err(|error| error.to_string())?;
                let target =
                    option("--output").ok_or("PDF-Vorschau konnte nicht gespeichert werden.")?;
                picture
                    .save_png(target)
                    .map_err(|_| "PDF-Vorschau konnte nicht gespeichert werden.".to_string())?;
                Ok(Vec::new())
            }
            "text" => {
                let mut remaining = whole("--limit", 2 * 1024 * 1024)
                    .filter(|limit| (1..=16 * 1024 * 1024).contains(limit))
                    .ok_or_else(invalid)? as usize;
                let pages = whole("--pages", 10000)
                    .filter(|pages| (1..=10000).contains(pages))
                    .ok_or_else(invalid)? as usize;
                let most = match option("--characters") {
                    Some(value) => Some(
                        value
                            .parse::<usize>()
                            .ok()
                            .filter(|most| (1..=1_000_000).contains(most))
                            .ok_or_else(invalid)?,
                    ),
                    None => None,
                };
                let (mut out, mut characters) = (Vec::new(), 0);
                for index in 0..document.pages.len().min(pages) {
                    let (_, _, words) = lumen_document::text::Page::words(&document, index)
                        .map_err(|error| error.to_string())?;
                    let value = lumen_document::text::text(&words) + "\u{c}";
                    characters += value.chars().count();
                    if let Some(most) = most.filter(|most| characters > *most) {
                        return Err(format!(
                            "Mehr als {most} PDF-Textzeichen; bitte einen kürzeren Auszug importieren."
                        ));
                    }
                    out.extend_from_slice(&value.as_bytes()[..value.len().min(remaining)]);
                    remaining = remaining.saturating_sub(value.len());
                    if remaining == 0 {
                        break;
                    }
                }
                Ok(out)
            }
            _ => Err("Unbekannte PDF-Aktion.".into()),
        }
    };
    match run() {
        Ok(out) => {
            use std::io::Write;
            if std::io::stdout().write_all(&out).is_err() {
                return ExitCode::FAILURE;
            }
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

/// `pdf-export`: a JSON request `{"pages": [{"path", "page", "rotation", "boxes", "stamp"}], "target", "dpi", "ocr"}`
/// on standard input. One line per page reports progress.
fn pdf_export() -> ExitCode {
    use lumen_document::json::Json;
    use std::io::Read;
    let request = || -> Option<(Vec<lumen_document::write::Item>, std::path::PathBuf, u32, Option<String>)> {
        let mut data = Vec::new();
        std::io::stdin()
            .take(4 * 1024 * 1024 + 1)
            .read_to_end(&mut data)
            .ok()?;
        let request = lumen_document::json::parse(&data)?;
        let mut items = Vec::new();
        for page in request.get("pages")?.list()? {
            let stamp: Vec<i64> = page
                .get("stamp")?
                .list()?
                .iter()
                .map(Json::whole)
                .collect::<Option<_>>()?;
            let mut boxes = Vec::new();
            for area in page.get("boxes").and_then(Json::list).unwrap_or(&[]) {
                let sides: Vec<f64> = area
                    .list()?
                    .iter()
                    .map(Json::number)
                    .collect::<Option<_>>()?;
                boxes.push(<[f64; 4]>::try_from(sides).ok()?);
            }
            items.push(lumen_document::write::Item {
                path: page.get("path")?.text()?.into(),
                page: usize::try_from(page.get("page")?.whole()?).ok()?,
                rotation: page.get("rotation").map_or(Some(0), Json::whole)?,
                boxes,
                stamp: stamp.try_into().ok()?,
            });
        }
        let dpi = request.get("dpi").map_or(Some(200), Json::whole)?;
        Some((
            items,
            request.get("target")?.text()?.into(),
            u32::try_from(dpi).ok()?,
            request.get("ocr").and_then(Json::text).map(str::to_string),
        ))
    };
    let Some((items, target, dpi, ocr)) = request() else {
        eprintln!("Ungültige Seitenauswahl oder Qualität.");
        return ExitCode::FAILURE;
    };
    let mut progress = |page: usize, pages: usize| println!("Seite {page} von {pages}");
    match lumen_document::write::export(&items, &target, dpi, ocr.as_deref(), &mut progress) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

/// `pdf-translate`: `{"action": "inspect", "path"}` prints the blocks to translate;
/// `{"action": "write", "manifest", "translations", "output"}` writes the translated copy.
fn pdf_translate() -> ExitCode {
    use lumen_document::translate;
    use std::io::Read;
    let mut data = Vec::new();
    let request = std::io::stdin()
        .take(64 * 1024 * 1024 + 1)
        .read_to_end(&mut data)
        .ok()
        .and_then(|_| lumen_document::json::parse(&data));
    let Some(request) = request else {
        eprintln!("Ungültiger PDF-Textauftrag.");
        return ExitCode::FAILURE;
    };
    let text = |key: &str| request.get(key).and_then(lumen_document::json::Json::text);
    let result = match text("action") {
        Some("inspect") => {
            let path = std::path::Path::new(text("path").unwrap_or(""));
            translate::inspect(path).map(|found| translate::inspection_json(path, &found))
        }
        Some("write") => {
            let (Some(manifest), Some(translations), Some(output)) = (
                request.get("manifest"),
                request.get("translations"),
                text("output"),
            ) else {
                eprintln!("Ungültiger PDF-Textauftrag.");
                return ExitCode::FAILURE;
            };
            let output = std::path::Path::new(output);
            translate::write(manifest, translations, output).map(|(pages, reduced)| {
                let reduced: Vec<String> = reduced
                    .iter()
                    .map(|(page, block, scale)| {
                        format!(
                            "{{\"page\": {page}, \"block\": {}, \"scale\": {scale}}}",
                            json(block)
                        )
                    })
                    .collect();
                format!(
                    "{{\"path\": {}, \"pages\": {pages}, \"reduced\": [{}]}}",
                    json(&output.to_string_lossy()),
                    reduced.join(", ")
                )
            })
        }
        _ => {
            eprintln!("Unknown PDF action");
            return ExitCode::FAILURE;
        }
    };
    match result {
        Ok(text) => {
            println!("{text}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if matches!(args.first().map(String::as_str), Some("blocks" | "view")) {
        // blocks <format> <scratch> [<first page>] | view <pdf|image> <scratch> <page>
        return lumen_document::blocks::command(&args);
    }
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
    if args.len() == 1 && args[0] == "index" {
        // `index`: the text of every file below a folder for the knowledge index, as JSON lines.
        use std::io::Read;
        let mut data = Vec::new();
        let _ = std::io::stdin()
            .take(4 * 1024 * 1024 + 1)
            .read_to_end(&mut data);
        let Some(request) = lumen_document::json::parse(&data)
            .as_ref()
            .and_then(lumen_document::search::Index::from_json)
        else {
            println!("{{\"type\": \"error\", \"message\": \"Ungültiger Indexauftrag.\"}}");
            return ExitCode::FAILURE;
        };
        let mut out = std::io::BufWriter::new(std::io::stdout().lock());
        return match lumen_document::search::index(&request, &mut out) {
            Ok(()) => ExitCode::SUCCESS,
            Err(_) => ExitCode::FAILURE,
        };
    }
    if args.len() == 1 && args[0] == "search" {
        // `search`: one JSON request on standard input, one JSON line per event on standard output.
        use std::io::Read;
        let mut data = Vec::new();
        let _ = std::io::stdin()
            .take(4 * 1024 * 1024 + 1)
            .read_to_end(&mut data);
        let Some(request) = lumen_document::json::parse(&data)
            .as_ref()
            .and_then(lumen_document::search::Request::from_json)
        else {
            println!("{{\"type\": \"error\", \"message\": \"Ungültiger Suchauftrag.\"}}");
            return ExitCode::FAILURE;
        };
        let mut out = std::io::BufWriter::new(std::io::stdout().lock());
        return match lumen_document::search::run(&request, &mut out) {
            Ok(()) => ExitCode::SUCCESS,
            Err(_) => ExitCode::FAILURE,
        };
    }
    if args.len() == 1 && args[0] == "pdf-export" {
        return pdf_export();
    }
    if args.len() == 1 && args[0] == "pdf-translate" {
        return pdf_translate();
    }
    if args.len() >= 3 && args[0] == "pdf-cli" {
        return pdf_cli(&args[1..]);
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
    if args.len() == 3 && args[0] == "office-text" {
        // `office-text <file> <.suffix>`: the plain text for a search.
        return match lumen_document::office::text(std::path::Path::new(&args[1]), &args[2]) {
            Ok(text) => {
                use std::io::Write;
                let _ = std::io::stdout().write_all(text.as_bytes());
                ExitCode::SUCCESS
            }
            Err(message) => {
                eprintln!("{message}");
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

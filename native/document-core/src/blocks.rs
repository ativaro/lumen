//! What the Lumen server reads of a document: `blocks` prints its text as located blocks, `view`
//! writes the picture of one page. The document is standard input, a regular file that is never
//! opened by name; a scratch folder is the only place written to.
use std::collections::HashMap;
use std::ffi::OsString;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::fd::AsFd;
use std::path::Path;
use std::process::{Command, ExitCode, Stdio};
use std::time::{Duration, Instant};

use roxmltree::Node;

use crate::office::{Pack, R, parse};
use crate::search::quote;
use crate::text::Page;

/// One of the codes the server knows, and the core's own message.
#[derive(Debug)]
pub struct Failure {
    pub code: &'static str,
    pub detail: String,
}

type Outcome<T> = Result<T, Failure>;

fn failed<T>(detail: impl Into<String>) -> Outcome<T> {
    Err(Failure::from(detail.into()))
}

impl From<String> for Failure {
    fn from(detail: String) -> Failure {
        Failure {
            code: "parse_failed",
            detail,
        }
    }
}

impl From<std::io::Error> for Failure {
    fn from(error: std::io::Error) -> Failure {
        Failure::from(error.to_string())
    }
}

impl From<crate::pdf::Error> for Failure {
    fn from(error: crate::pdf::Error) -> Failure {
        let detail = error.to_string();
        Failure {
            code: if detail == crate::security::PASSWORD {
                "password_required"
            } else {
                "parse_failed"
            },
            detail,
        }
    }
}

/// Python's `str.isspace`: the separators U+001C to U+001F count as well.
fn space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

fn strip(text: &str) -> &str {
    text.trim_matches(space)
}

fn line(out: &mut dyn Write, text: &str) -> Outcome<()> {
    // The server reads a stream and may stop the program once it has enough.
    writeln!(out, "{text}")?;
    Ok(out.flush()?)
}

fn block(out: &mut dyn Write, text: &str, location: &str, method: &str) -> Outcome<()> {
    if text.contains('\0') {
        return failed("Steuerzeichen im Dokumenttext.");
    }
    line(
        out,
        &format!(
            "{{\"text\": {}, \"location\": {location}, \"method\": \"{method}\"}}",
            quote(text)
        ),
    )
}

// ---- Tools ----

/// A tool found in this process's `PATH`, which inherits nothing else of its environment.
// The program is started by its full path: for a bare name together with a changed environment the
// standard library starts the child through fork, and that opens a socket pair, which the server's
// sandbox denies.
fn tool(name: &str) -> Outcome<Command> {
    use std::os::unix::fs::PermissionsExt;
    let path = std::env::var_os("PATH").unwrap_or_default();
    let runs = |file: &std::path::PathBuf| {
        std::fs::metadata(file).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
    };
    let folders = std::env::split_paths(&path).filter(|folder| folder.is_absolute());
    let Some(program) = folders.map(|folder| folder.join(name)).find(runs) else {
        return Err(Failure {
            code: "parser_unavailable",
            detail: format!("{name}: nicht gefunden."),
        });
    };
    let mut command = Command::new(program);
    command
        .env_clear()
        .env("PATH", path)
        .env("LANG", "C.UTF-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    Ok(command)
}

/// ImageMagick within the reader's budget: a picture too large for it is refused, not swapped out.
fn convert() -> Outcome<Command> {
    let mut command = tool("convert")?;
    command.args(["-limit", "memory", "1GiB", "-limit", "area", "128MP"]);
    command.args(["-limit", "map", "0", "-limit", "disk", "0"]);
    command.args(["-limit", "thread", "2"]);
    Ok(command)
}

/// What the tool printed, if it ended well within `seconds`.
fn run(command: &mut Command, seconds: u64) -> Outcome<Vec<u8>> {
    let program = Path::new(command.get_program());
    let name = program
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .into_owned();
    let mut child = command.spawn().map_err(|error| Failure {
        code: "parser_unavailable",
        detail: format!("{name}: {error}"),
    })?;
    let output = child.stdout.take();
    // Read beside the wait, or a full pipe would hold the tool until the time limit.
    let reader = std::thread::spawn(move || {
        let mut data = Vec::new();
        if let Some(output) = output {
            let _ = output.take(8 * 1024 * 1024).read_to_end(&mut data);
        }
        data
    });
    let deadline = Instant::now() + Duration::from_secs(seconds);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(10)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(Failure {
                    code: "resource_limit",
                    detail: format!("{name}: Zeitlimit von {seconds} Sekunden überschritten."),
                });
            }
        }
    };
    let data = reader.join().unwrap_or_default();
    if !status.success() {
        return failed(format!("{name} fehlgeschlagen."));
    }
    Ok(data)
}

/// `png:/folder/name`: the coder is always named, so that ImageMagick never guesses one.
fn coded(kind: &str, path: &Path, tail: &str) -> OsString {
    let mut argument = OsString::from(format!("{kind}:"));
    argument.push(path);
    argument.push(tail);
    argument
}

/// The picture type by its first bytes; the name of a file says nothing.
fn magic(head: &[u8]) -> Option<&'static str> {
    let has = |brand: &[u8]| head.windows(4).any(|window| window == brand);
    let boxed = head.get(4..8) == Some(b"ftyp");
    Some(if head.starts_with(b"\xff\xd8\xff") {
        "jpeg"
    } else if head.starts_with(b"\x89PNG\r\n\x1a\n") {
        "png"
    } else if head.starts_with(b"GIF87a") || head.starts_with(b"GIF89a") {
        "gif"
    } else if head.starts_with(b"BM") {
        "bmp"
    } else if head.starts_with(b"II*\0") || head.starts_with(b"MM\0*") {
        "tiff"
    } else if head.starts_with(b"RIFF") && head.get(8..12) == Some(b"WEBP") {
        "webp"
    } else if boxed && has(b"avif") {
        "avif"
    } else if boxed && [b"heic", b"heif", b"heix", b"mif1"].iter().any(|b| has(*b)) {
        "heic"
    } else if head.starts_with(b"\xff\x0a") || head.starts_with(b"\0\0\0\x0cJXL \r\n\x87\n") {
        "jxl"
    } else {
        return None;
    })
}

/// Writes the picture in `source` as an upright 8-bit PNG to `target`, no larger than `most` allows.
fn normalise(source: &mut dyn Read, scratch: &Path, target: &Path, most: &str) -> Outcome<()> {
    let (original, decoded) = (scratch.join("original"), scratch.join("jxl-source.png"));
    let mut write = || {
        let mut head = Vec::new();
        (&mut *source).take(32).read_to_end(&mut head)?;
        let mut file = File::create(&original)?;
        file.write_all(&head)?;
        std::io::copy(source, &mut file)?;
        drop(file);
        let (kind, picture) = match magic(&head) {
            Some("jxl") => {
                let mut command = tool("djxl")?;
                command.arg(&original).arg(&decoded);
                run(command.args(["--num_threads=2", "--bits_per_sample=8"]), 60)?;
                ("png", &decoded)
            }
            Some(kind) => (kind, &original),
            None => return failed("Unbekanntes Bildformat."),
        };
        let mut command = convert()?;
        command.arg(coded(kind, picture, "[0]"));
        command.args(["-auto-orient", "-resize", most, "-depth", "8"]);
        command.arg(coded("png", target, ""));
        run(&mut command, 60).map(|_| ())
    };
    let done = write();
    let _ = std::fs::remove_file(original);
    let _ = std::fs::remove_file(decoded);
    done
}

/// The text Tesseract reads in `ocr.png`, which is removed afterwards.
fn recognise(scratch: &Path) -> Outcome<String> {
    let picture = scratch.join("ocr.png");
    let mut command = tool("tesseract")?;
    command.arg(&picture).env("OMP_THREAD_LIMIT", "2");
    let read = run(command.args(["stdout", "-l", "deu+eng", "--psm", "3"]), 45);
    let _ = std::fs::remove_file(picture);
    let text = String::from_utf8(read?).map_err(|error| error.to_string())?;
    Ok(strip(&text).to_string())
}

/// The block of a picture, if any text is seen in it.
fn seen(source: &mut dyn Read, scratch: &Path) -> Outcome<Option<String>> {
    normalise(source, scratch, &scratch.join("ocr.png"), "8000000@>")?;
    let text = recognise(scratch)?;
    Ok((!text.is_empty()).then(|| format!("Image 1\n{text}\n")))
}

// ---- Text ----

/// A byte outside UTF-8 read as Windows-1252; its five unused places stay control characters.
fn windows(byte: u8) -> char {
    match crate::text::WINDOWS.chars().nth(usize::from(byte ^ 0x80)) {
        Some(c) if c != '\0' => c,
        _ => char::from(byte),
    }
}

/// Decodes as much of `data` as is complete and leaves the rest for the next call; at the `end`
/// nothing is left. `wide` is the byte order of UTF-16: big-endian when true.
fn decode(data: &mut Vec<u8>, wide: Option<bool>, end: bool) -> String {
    let mut text = String::new();
    if let Some(big) = wide {
        let mut units: Vec<u16> = data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| match big {
                true => u16::from_be_bytes(*pair),
                false => u16::from_le_bytes(*pair),
            })
            .collect();
        // The first half of a pair waits for its second half in the next block.
        if !end && units.last().is_some_and(|u| (0xD800..0xDC00).contains(u)) {
            units.pop();
        }
        let mut used = units.len() * 2;
        text.extend(char::decode_utf16(units).map(|c| c.unwrap_or('\u{FFFD}')));
        if end && data.len() > used {
            text.push('\u{FFFD}');
            used = data.len();
        }
        data.drain(..used);
        return text;
    }
    let mut rest = &data[..];
    while !rest.is_empty() {
        let error = match std::str::from_utf8(rest) {
            Ok(valid) => {
                text.push_str(valid);
                rest = &[];
                break;
            }
            Err(error) => error,
        };
        let (valid, after) = rest.split_at(error.valid_up_to());
        text.push_str(&String::from_utf8_lossy(valid));
        let wrong = match error.error_len() {
            Some(length) => length,
            None if end => after.len(),
            None => {
                rest = after;
                break;
            }
        };
        text.extend(after[..wrong].iter().map(|byte| windows(*byte)));
        rest = &after[wrong..];
    }
    let used = data.len() - rest.len();
    data.drain(..used);
    text
}

/// A text file in blocks of at most 65536 characters: UTF-8, UTF-16 with a byte-order mark, and
/// Windows-1252 for bytes that are not UTF-8.
fn plain_text(input: &mut File, out: &mut dyn Write) -> Outcome<()> {
    let (mut data, mut wide, mut first) = (Vec::new(), None, true);
    loop {
        let wanted = 65536 - data.len();
        let end = (&mut *input).take(wanted as u64).read_to_end(&mut data)? < wanted;
        if first {
            first = false;
            if data.starts_with(b"\xff\xfe") || data.starts_with(b"\xfe\xff") {
                wide = Some(data[0] == 0xfe);
                data.drain(..2);
            } else if data.starts_with(b"\xef\xbb\xbf") {
                data.drain(..3);
            }
        }
        let text = decode(&mut data, wide, end);
        if !text.is_empty() {
            block(out, &text, "{}", "text")?;
        }
        if end {
            return Ok(());
        }
    }
}

// ---- WAV ----

/// A float as Python's `repr` writes it: the shortest digits that read back, an exponent below
/// 1e-4 and from 1e16.
fn python_float(value: f64) -> String {
    if !value.is_finite() {
        return value.to_string();
    }
    let short = format!("{value:e}");
    let (mantissa, exponent) = short.split_once('e').unwrap_or((&short, "0"));
    let sign = if mantissa.starts_with('-') { "-" } else { "" };
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let point = exponent.parse::<i64>().unwrap_or(0) + 1;
    let count = digits.len() as i64;
    if point <= -4 || point > 16 {
        let fraction = if count > 1 { "." } else { "" };
        let (first, rest) = digits.split_at(1);
        let mark = if point > 0 { '+' } else { '-' };
        let power = (point - 1).abs();
        return format!("{sign}{first}{fraction}{rest}e{mark}{power:02}");
    }
    if point <= 0 {
        format!("{sign}0.{}{digits}", "0".repeat(-point as usize))
    } else if point >= count {
        format!("{sign}{digits}{}.0", "0".repeat((point - count) as usize))
    } else {
        let (whole, fraction) = digits.split_at(point as usize);
        format!("{sign}{whole}.{fraction}")
    }
}

/// The facts of a WAV header as Python's `wave` module reads them, written like `json.dumps`.
/// Nothing of the sound itself is read.
fn wav(input: &mut (impl Read + Seek)) -> Outcome<String> {
    const PCM: [u8; 16] = *b"\x01\0\0\0\0\0\x10\0\x80\0\0\xaa\0\x38\x9b\x71";
    let wrong = || Failure::from("Keine unkomprimierte WAV-Datei.".to_string());
    let half = |data: &[u8], at: usize| u16::from_le_bytes([data[at], data[at + 1]]);
    let whole = |data: &[u8], at: usize| {
        u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
    };
    let mut head = [0u8; 12];
    input.read_exact(&mut head).map_err(|_| wrong())?;
    if &head[..4] != b"RIFF" || &head[8..] != b"WAVE" {
        return Err(wrong());
    }
    let end = 8 + u64::from(whole(&head, 4));
    let (mut at, mut format) = (12u64, None);
    while at + 8 <= end {
        let mut chunk = [0u8; 8];
        input.seek(SeekFrom::Start(at))?;
        input.read_exact(&mut chunk).map_err(|_| wrong())?;
        let size = whole(&chunk, 4);
        if &chunk[..4] == b"fmt " {
            let mut data = Vec::new();
            (&mut *input)
                .take(u64::from(size.min(40)))
                .read_to_end(&mut data)?;
            let extensible = data.len() >= 16 && half(&data, 0) == 0xFFFE;
            if data.len() < 16
                || !(half(&data, 0) == 1 || extensible)
                || extensible && data.get(24..40) != Some(&PCM[..])
            {
                return Err(wrong());
            }
            let (channels, rate) = (u64::from(half(&data, 2)), whole(&data, 4));
            let width = u64::from(half(&data, 14)).div_ceil(8);
            if channels == 0 || rate == 0 || width == 0 {
                return Err(wrong());
            }
            format = Some((channels, rate, width));
        } else if &chunk[..4] == b"data" {
            let (channels, rate, width) = format.ok_or_else(wrong)?;
            let frames = u64::from(size) / (channels * width);
            return Ok(format!(
                "{{\"channels\": {channels}, \"sample_rate\": {rate}, \"bits_per_sample\": {}, \"frames\": {frames}, \"duration_seconds\": {}, \"compression\": \"NONE\"}}",
                width * 8,
                python_float(frames as f64 / f64::from(rate))
            ));
        }
        at += 8 + u64::from(size) + u64::from(size & 1);
    }
    Err(wrong())
}

// ---- Office ----

fn named(node: Node, names: &[&str]) -> bool {
    node.is_element() && names.contains(&node.tag_name().name())
}

/// All text below a node, as ElementTree's `itertext`.
fn inner(node: Node) -> String {
    node.descendants()
        .filter_map(|n| n.text().filter(|_| n.is_text()))
        .collect()
}

/// The text before a node's first child element, as ElementTree's `text`.
fn own(node: Node) -> String {
    node.children()
        .take_while(|child| !child.is_element())
        .filter_map(|child| child.text().filter(|_| child.is_text()))
        .collect()
}

/// The own text of every element of these names in and below a node.
fn runs(node: Node, names: &[&str]) -> Vec<String> {
    node.descendants()
        .filter(|n| named(*n, names))
        .map(own)
        .collect()
}

/// Every node from `root` down in document order: when it starts, and with `true` when it ends.
fn walk<'a, 'i>(
    root: Node<'a, 'i>,
    visit: &mut dyn FnMut(Node<'a, 'i>, bool) -> Outcome<()>,
) -> Outcome<()> {
    let mut node = root;
    loop {
        visit(node, false)?;
        if let Some(child) = node.first_child() {
            node = child;
            continue;
        }
        loop {
            visit(node, true)?;
            match (node == root, node.next_sibling(), node.parent()) {
                (false, Some(next), _) => {
                    node = next;
                    break;
                }
                (false, None, Some(parent)) => node = parent,
                _ => return Ok(()),
            }
        }
    }
}

/// The elements of these names that lie in no other one of them.
fn outermost<'a, 'i>(root: Node<'a, 'i>, names: &[&str]) -> Vec<Node<'a, 'i>> {
    let (mut found, mut open) = (Vec::new(), 0);
    let _ = walk(root, &mut |node, ended| {
        if named(node, names) && !ended {
            open += 1;
        } else if named(node, names) {
            open -= 1;
            if open == 0 {
                found.push(node);
            }
        }
        Ok(())
    });
    found
}

/// The last attribute of this local name, whatever its namespace.
fn attribute(node: Node, name: &str) -> Option<String> {
    let found = node.attributes().rev().find(|a| a.name() == name);
    found.map(|a| a.value().to_string())
}

/// An XML part; any document type declaration is refused, not only one with entities.
fn part(pack: &Pack, name: &str) -> Result<String, String> {
    let text = pack.part(name)?;
    if text.to_ascii_lowercase().contains("<!doctype") {
        return Err("XML-Deklarationen in Office-Dateien werden nicht geladen.".into());
    }
    Ok(text)
}

/// Where the relationships of a part lead inside the file. Links out of the file and paths that
/// climb with `..` are left out.
fn relationships(
    pack: &Pack,
    name: &str,
    folder: &str,
) -> Result<HashMap<Option<String>, String>, String> {
    let text = part(pack, name)?;
    let mut result = HashMap::new();
    for row in parse(&text)?
        .root_element()
        .children()
        .filter(Node::is_element)
    {
        if row.attribute("TargetMode") == Some("External") {
            continue;
        }
        let target = row.attribute("Target").unwrap_or("");
        let joined = match target.starts_with('/') {
            true => target.to_string(),
            false => format!("{folder}/{target}"),
        };
        let steps: Vec<&str> = joined
            .split('/')
            .filter(|s| !s.is_empty() && *s != ".")
            .collect();
        if !steps.contains(&"..") {
            let path = if steps.is_empty() {
                ".".into()
            } else {
                steps.join("/")
            };
            result.insert(row.attribute("Id").map(str::to_string), path);
        }
    }
    Ok(result)
}

fn linked<'a>(links: &'a HashMap<Option<String>, String>, node: Node) -> Result<&'a str, String> {
    let found = links.get(&node.attribute((R, "id")).map(str::to_string));
    found
        .map(String::as_str)
        .ok_or_else(|| "Office-Datei unvollständig: Beziehung fehlt.".into())
}

/// How often a row or a cell repeats.
fn repeated(node: Node, name: &str, most: u64) -> Result<u64, String> {
    let count = attribute(node, name).map_or(Some(1), |value| value.trim().parse().ok());
    count
        .filter(|count| (1..=most).contains(count))
        .ok_or_else(|| "Ungültige Wiederholung in der Tabelle.".into())
}

/// The text of an Office file, one line per paragraph, table row, cell or slide paragraph, each
/// naming its place. The server's former Python reader is the specification, down to the numbering.
// ponytail: a part is parsed into a tree as the reading view does; a streaming reader if sheets
// near the 64 MiB entry limit matter.
fn office(pack: &Pack, format: &str, emit: &mut dyn FnMut(String) -> Outcome<()>) -> Outcome<()> {
    match format {
        "odp" => {
            let text = part(pack, "content.xml")?;
            let document = parse(&text)?;
            let pages = outermost(document.root(), &["page"]);
            for (index, page) in pages.into_iter().enumerate() {
                let values: Vec<String> = page
                    .descendants()
                    .filter(|n| named(*n, &["p"]))
                    .map(inner)
                    .collect();
                if values.iter().any(|value| !strip(value).is_empty()) {
                    emit(format!("Slide {}\n{}\n", index + 1, values.join("\n")))?;
                }
            }
        }
        "odt" => {
            let text = part(pack, "content.xml")?;
            let document = parse(&text)?;
            let paragraphs = outermost(document.root(), &["p"]);
            for (index, paragraph) in paragraphs.into_iter().enumerate() {
                let value = inner(paragraph);
                if !strip(&value).is_empty() {
                    emit(format!("Paragraph {}: {value}\n", index + 1))?;
                }
            }
        }
        "ods" => {
            let text = part(pack, "content.xml")?;
            let document = parse(&text)?;
            let (mut sheet, mut row) = (String::new(), 0u64);
            walk(document.root(), &mut |node, ended| {
                if !ended && named(node, &["table"]) {
                    let name = node.attributes().find(|a| a.name() == "name");
                    (sheet, row) = (name.map_or("", |a| a.value()).to_string(), 0);
                }
                // A row is read when it ends, after any table inside it.
                if !ended || !named(node, &["table-row"]) {
                    return Ok(());
                }
                let repeats = repeated(node, "number-rows-repeated", 1_048_576)?;
                let mut column = 1;
                for cell in node.children() {
                    if !named(cell, &["table-cell", "covered-table-cell"]) {
                        continue;
                    }
                    let count = repeated(cell, "number-columns-repeated", 16384)?;
                    let paragraphs = cell.children().filter(|p| named(*p, &["p"]));
                    let mut value = paragraphs.map(inner).collect::<Vec<_>>().join(" ");
                    if value.is_empty() {
                        value = attribute(cell, "value")
                            .or_else(|| attribute(cell, "date-value"))
                            .unwrap_or_default();
                    }
                    if let Some(formula) = attribute(cell, "formula").filter(|f| !f.is_empty()) {
                        value += &format!(" [formula: {formula}]");
                    }
                    if !value.is_empty() {
                        let note = match repeats > 1 || count > 1 {
                            true => format!(" [repeated rows={repeats}, columns={count}]"),
                            false => String::new(),
                        };
                        emit(format!("{sheet}!R{}C{column}: {value}{note}\n", row + 1))?;
                    }
                    column += count;
                }
                row += repeats;
                Ok(())
            })?;
        }
        "pptx" | "pptm" => {
            // Without a presentation part the slides come in the order of their numbers.
            let number = |name: &str| {
                let digits = name
                    .strip_prefix("ppt/slides/slide")?
                    .strip_suffix(".xml")?;
                let whole = !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit());
                let digits = digits.trim_start_matches('0');
                whole.then(|| (digits.len(), digits.to_string()))
            };
            let mut names: Vec<String> = pack
                .ordered()
                .into_iter()
                .filter(|name| number(name).is_some())
                .collect();
            names.sort_by_key(|name| number(name));
            if pack.names.contains("ppt/presentation.xml") {
                let links = relationships(pack, "ppt/_rels/presentation.xml.rels", "ppt")?;
                let text = part(pack, "ppt/presentation.xml")?;
                names.clear();
                let document = parse(&text)?;
                let lists = document.root_element().children();
                for list in lists.filter(|n| named(*n, &["sldIdLst"])) {
                    for slide in list.children().filter(|n| named(*n, &["sldId"])) {
                        names.push(linked(&links, slide)?.to_string());
                    }
                }
            }
            for (index, name) in names.iter().enumerate() {
                let text = part(pack, name)?;
                let document = parse(&text)?;
                for paragraph in outermost(document.root(), &["p"]) {
                    let value = runs(paragraph, &["t"]).join(" ");
                    if !strip(&value).is_empty() {
                        emit(format!("Slide {}\n{value}\n", index + 1))?;
                    }
                }
            }
        }
        "xlsx" | "xlsm" => {
            let mut strings = Vec::new();
            if pack.names.contains("xl/sharedStrings.xml") {
                let text = part(pack, "xl/sharedStrings.xml")?;
                let document = parse(&text)?;
                let rows = outermost(document.root(), &["si"]);
                strings = rows
                    .into_iter()
                    .map(|row| runs(row, &["t"]).concat())
                    .collect();
            }
            let links = relationships(pack, "xl/_rels/workbook.xml.rels", "xl")?;
            let workbook = part(pack, "xl/workbook.xml")?;
            let workbook = parse(&workbook)?;
            for sheet in workbook.descendants().filter(|n| named(*n, &["sheet"])) {
                let text = part(pack, linked(&links, sheet)?)?;
                let document = parse(&text)?;
                for cell in outermost(document.root(), &["c"]) {
                    let values = runs(cell, &["v", "t"]);
                    let mut value = values.join(" ");
                    if let (Some("s"), Some(first)) = (cell.attribute("t"), values.first()) {
                        let index = first.trim().parse::<usize>().ok();
                        value = index
                            .and_then(|index| strings.get(index))
                            .ok_or_else(|| "Ungültiger Textverweis in der Tabelle.".to_string())?
                            .clone();
                    }
                    // Saved values only: formulas and workbook links are never worked out.
                    let formulas: Vec<String> = cell
                        .children()
                        .filter(|n| named(*n, &["f"]))
                        .map(own)
                        .collect();
                    if !formulas.is_empty() {
                        let formulas = formulas.join(" ");
                        value = match value.is_empty() {
                            true => format!("[formula; no saved value] {formulas}"),
                            false => format!("{value} [saved value; formula: {formulas}]"),
                        };
                    }
                    if !value.is_empty() {
                        let name = sheet.attribute("name").unwrap_or("");
                        let place = cell.attribute("r").unwrap_or("?");
                        emit(format!("{name}!{place}: {value}\n"))?;
                    }
                }
            }
        }
        _ => {
            let margin = |name: &String| {
                let number = name
                    .strip_prefix("word/header")
                    .or(name.strip_prefix("word/footer"));
                number
                    .and_then(|rest| rest.strip_suffix(".xml"))
                    .is_some_and(|digits| {
                        !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit())
                    })
            };
            let mut margins: Vec<String> =
                pack.names.iter().filter(|n| margin(n)).cloned().collect();
            margins.sort();
            let fixed = [
                "word/document.xml",
                "word/footnotes.xml",
                "word/endnotes.xml",
            ];
            for name in fixed
                .iter()
                .copied()
                .chain(margins.iter().map(String::as_str))
            {
                if !pack.names.contains(name) {
                    continue;
                }
                let text = part(pack, name)?;
                let document = parse(&text)?;
                let found = outermost(document.root(), &["p", "tr"]);
                // Empty paragraphs count: the number is the place in the part.
                for (index, node) in found.into_iter().enumerate() {
                    let row = named(node, &["tr"]);
                    let value = match row {
                        true => node
                            .children()
                            .filter(|cell| named(*cell, &["tc"]))
                            .map(|cell| runs(cell, &["t"]).join(" "))
                            .collect::<Vec<_>>()
                            .join("\t"),
                        false => runs(node, &["t"]).concat(),
                    };
                    if !strip(&value).is_empty() {
                        let kind = if row { "Table row" } else { "Paragraph" };
                        emit(format!("{name} · {kind} {}: {value}\n", index + 1))?;
                    }
                }
            }
        }
    }
    Ok(())
}

// ---- PDF ----

fn pdf(input: &mut File) -> Outcome<crate::pdf::Document> {
    let mut data = Vec::new();
    let most = crate::pdf::MAX_FILE as u64 + 1;
    (&mut *input).take(most).read_to_end(&mut data)?;
    Ok(crate::pdf::Document::new(data)?)
}

/// Whether a page's text layer can be trusted: it has text, and at most 2 % of it are replacement
/// characters, private-use characters or noncharacters.
// Rust has no table of unassigned characters, which the Python reader counted as well.
fn reliable(text: &str) -> bool {
    let (mut meaningful, mut bad) = (0.0, 0.0);
    for code in text.chars().filter(|c| !space(*c)).map(u32::from) {
        meaningful += 1.0;
        if code == 0xFFFD
            || (0xE000..=0xF8FF).contains(&code)
            || (0xFDD0..=0xFDEF).contains(&code)
            || code >= 0xF0000
            || code & 0xFFFE == 0xFFFE
        {
            bad += 1.0;
        }
    }
    meaningful > 0.0 && bad <= meaningful * 0.02 && !text.contains('\0')
}

fn save(picture: &tiny_skia::Pixmap, path: &Path) -> Outcome<()> {
    let saved = picture.save_png(path);
    saved.map_err(|_| Failure::from("Seitenbild konnte nicht gespeichert werden.".to_string()))
}

/// The text of a page and how it was read; nothing for a page without any.
fn page_text(
    document: &crate::pdf::Document,
    index: usize,
    scratch: &Path,
) -> Outcome<Option<(String, &'static str)>> {
    let (mut text, mut method, mut refused) = (String::new(), "text", None);
    let (width, height, scanned) = match Page::words_and_images(document, index) {
        Ok((width, height, words, pictures)) => {
            text = strip(&crate::text::text(&words).replace("\r\n", "\n")).to_string();
            // A small text header over a scanned page must not hide the actual document.
            let scanned = pictures > width * height * 0.6 && text.chars().count() < 120;
            (width, height, scanned)
        }
        // A text layer the core cannot read: the page's picture is recognised instead.
        Err(error) => {
            let page = Page::prepare(document, index)?;
            refused = Some(error);
            (page.width, page.height, true)
        }
    };
    if scanned || !reliable(&text) {
        let scale = f64::min(200.0 / 72.0, 3200.0 / width.max(height));
        let picture = crate::render::render(document, index, scale)?;
        save(&picture, &scratch.join("ocr.png"))?;
        let recognised = recognise(scratch)?;
        if !recognised.is_empty() {
            (text, method) = (recognised, "ocr");
        } else if let Some(error) = refused {
            return Err(error.into());
        }
    }
    Ok((!text.is_empty()).then_some((text, method)))
}

fn pdf_blocks(input: &mut File, scratch: &Path, first: usize, out: &mut dyn Write) -> Outcome<()> {
    let document = pdf(input)?;
    let pages = document.pages.len();
    line(out, &format!("{{\"info\": {{\"pages\": {pages}}}}}"))?;
    for index in first..pages {
        let page = index + 1;
        match page_text(&document, index, scratch) {
            Ok(Some((text, method))) => {
                let location = format!("{{\"page\": {page}}}");
                block(out, &format!("Page {page}\n{text}\n"), &location, method)?;
            }
            Ok(None) => line(out, &format!("{{\"blank\": {page}}}"))?,
            // One page the core cannot read does not end the document; a missing or stalled tool does.
            Err(failure) if failure.code == "parse_failed" => {
                let detail = quote(&failure.detail);
                line(
                    out,
                    &format!("{{\"unread\": {page}, \"detail\": {detail}}}"),
                )?;
            }
            Err(failure) => return Err(failure),
        }
    }
    Ok(())
}

// ---- Commands ----

/// The last suffix of an entry's file name in lower case, as Python's `Path(name).suffix` gives it:
/// a name of nothing but leading periods and letters has none.
fn suffix(name: &str) -> String {
    let file = name.trim_end_matches('/').rsplit('/').next().unwrap_or("");
    let dot = file
        .rfind('.')
        .filter(|at| file[..*at].chars().any(|c| c != '.'));
    dot.map_or(String::new(), |at| file[at..].to_lowercase())
}

/// The document: standard input, a regular file read from its start.
fn input() -> Outcome<File> {
    let mut file = File::from(std::io::stdin().as_fd().try_clone_to_owned()?);
    file.rewind()?;
    Ok(file)
}

fn blocks(format: &str, scratch: &Path, first: usize, out: &mut dyn Write) -> Outcome<()> {
    let mut input = input()?;
    match format {
        "text" => plain_text(&mut input, out),
        "pdf" => pdf_blocks(&mut input, scratch, first, out),
        "image" => match seen(&mut input, scratch)? {
            Some(text) => block(out, &text, "{\"image\": 1}", "ocr"),
            None => Ok(()),
        },
        "wav" => {
            let audio = wav(&mut input)?;
            line(
                out,
                &format!("{{\"info\": {{\"content_read\": false, \"audio\": {audio}}}}}"),
            )?;
            let text = format!(
                "Observed WAV header (not transcribed; does not establish speech or topic): {audio}"
            );
            block(out, &text, "{}", "metadata")
        }
        "docx" | "docm" | "xlsx" | "xlsm" | "pptx" | "pptm" | "odt" | "ods" | "odp" => {
            let pack = Pack::from_file(input, &HashMap::new())?;
            office(&pack, format, &mut |text| {
                let location = match format {
                    "xlsx" | "xlsm" | "ods" => {
                        format!(
                            "{{\"sheet\": {}}}",
                            quote(text.split('!').next().unwrap_or(""))
                        )
                    }
                    "docx" | "docm" => {
                        format!(
                            "{{\"part\": {}}}",
                            quote(text.split(" · ").next().unwrap_or(""))
                        )
                    }
                    "odt" => "{}".to_string(),
                    _ => {
                        let slide = text.lines().next().and_then(|l| l.split(' ').nth(1));
                        format!("{{\"slide\": {}}}", slide.unwrap_or("0"))
                    }
                };
                block(out, &text, &location, "office")
            })?;
            let mut pictures: Vec<&String> = pack
                .names
                .iter()
                .filter(|name| name.starts_with("word/media/") || name.starts_with("ppt/media/"))
                .filter(|name| [".jpg", ".jpeg", ".png", ".webp"].contains(&&*suffix(name)))
                .collect();
            pictures.sort();
            for name in pictures {
                if let Some(text) = seen(&mut &pack.bytes(name)?[..], scratch)? {
                    let location = format!("{{\"embedded_image\": {}}}", quote(name));
                    block(out, &format!("{name}\n{text}"), &location, "ocr")?;
                }
            }
            Ok(())
        }
        _ => failed("Unbekanntes Dokumentformat."),
    }
}

/// Writes `view.jpg`, the picture of a page within 1600 pixels and 90000 bytes, and returns its size.
fn view(kind: &str, scratch: &Path, page: usize) -> Outcome<(u32, u32)> {
    let mut input = input()?;
    let (png, jpeg) = (scratch.join("view.png"), scratch.join("view.jpg"));
    match kind {
        "pdf" => {
            let document = pdf(&mut input)?;
            if page == 0 || page > document.pages.len() {
                return failed("Seite nicht vorhanden.");
            }
            let (width, height) = {
                let page = Page::prepare(&document, page - 1)?;
                (page.width, page.height)
            };
            let scale = f64::min(2.0, 1600.0 / width.max(height));
            save(&crate::render::render(&document, page - 1, scale)?, &png)?;
        }
        // Shrunk at once: the picture in full size may be larger than the reader may write.
        "image" if page == 1 => normalise(&mut input, scratch, &png, "1600x1600>")?,
        _ => return failed("Seitenbilder gibt es für PDF-Dateien und Rasterbilder."),
    }
    let mut size = "1600x1600>".to_string();
    loop {
        // ponytail: ImageMagick is the JPEG encoder because the server already has it; an encoder
        // in Rust would replace this call and the PNG between.
        let mut command = convert()?;
        command
            .arg(coded("png", &png, ""))
            .args(["-background", "white", "-flatten"]);
        command
            .args(["-resize", &size, "-quality", "75"])
            .arg(coded("jpeg", &jpeg, ""));
        run(&mut command, 60)?;
        let mut decoder = jpeg_decoder::Decoder::new(std::io::BufReader::new(File::open(&jpeg)?));
        decoder.read_info().map_err(|error| error.to_string())?;
        let info = decoder
            .info()
            .ok_or_else(|| "Seitenbild ohne Größe.".to_string())?;
        if std::fs::metadata(&jpeg)?.len() <= 90_000 {
            return Ok((info.width.into(), info.height.into()));
        }
        if info.width.max(info.height) <= 400 {
            return failed("Seitenbild überschreitet sein Budget.");
        }
        size = format!(
            "{}x{}",
            u32::from(info.width) * 4 / 5,
            u32::from(info.height) * 4 / 5
        );
    }
}

/// `blocks <format> <scratch> [<first page>]` and `view <pdf|image> <scratch> <page>`: JSON lines
/// on standard output, the last one `{"error": ..., "detail": ...}` when the document cannot be read.
pub fn command(args: &[String]) -> ExitCode {
    let mut out = std::io::stdout().lock();
    let number = |at: usize| {
        args.get(at)
            .map_or(Some(0), |value| value.parse::<usize>().ok())
    };
    // The pictures between the steps go; only a finished view keeps its picture.
    let done = match (args[0].as_str(), args.len(), number(3)) {
        ("blocks", 3 | 4, Some(first)) => {
            let scratch = Path::new(&args[2]);
            let done = blocks(&args[1], scratch, first, &mut out);
            let _ = std::fs::remove_file(scratch.join("ocr.png"));
            done
        }
        ("view", 4, Some(page)) => {
            let scratch = Path::new(&args[2]);
            let done = view(&args[1], scratch, page).and_then(|(width, height)| {
                line(
                    &mut out,
                    &format!("{{\"width\": {width}, \"height\": {height}}}"),
                )
            });
            let _ = std::fs::remove_file(scratch.join("view.png"));
            if done.is_err() {
                let _ = std::fs::remove_file(scratch.join("view.jpg"));
            }
            done
        }
        _ => failed(
            "usage: lumen-document blocks <format> <scratch> [<first page>] | view <pdf|image> <scratch> <page>",
        ),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(failure) => {
            let detail = quote(&failure.detail);
            let _ = line(
                &mut out,
                &format!("{{\"error\": \"{}\", \"detail\": {detail}}}", failure.code),
            );
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const WORD: &str = "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"";
    const LINKS: &str =
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"";
    const OPEN: &str = "xmlns:office=\"urn:oasis:names:tc:opendocument:xmlns:office:1.0\" xmlns:text=\"urn:oasis:names:tc:opendocument:xmlns:text:1.0\" xmlns:table=\"urn:oasis:names:tc:opendocument:xmlns:table:1.0\" xmlns:draw=\"urn:oasis:names:tc:opendocument:xmlns:drawing:1.0\"";

    /// The lines of an Office file with these parts, or why it is refused. The expected lines are
    /// what the server's Python reader gave for the same parts.
    fn lines(format: &str, parts: &[(&str, String)]) -> Result<Vec<String>, String> {
        static FILES: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let number = FILES.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let name = format!("lumen-blocks-{}-{number}.zip", std::process::id());
        let path = std::env::temp_dir().join(name);
        let file = File::options()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path);
        let mut writer = zip::ZipWriter::new(file.unwrap());
        let _ = std::fs::remove_file(&path);
        for (name, text) in parts {
            let options = zip::write::SimpleFileOptions::default();
            writer.start_file(*name, options).unwrap();
            writer.write_all(text.as_bytes()).unwrap();
        }
        let pack = Pack::from_file(writer.finish().unwrap(), &HashMap::new())?;
        let mut lines = Vec::new();
        let read = office(&pack, format, &mut |line| {
            lines.push(line);
            Ok(())
        });
        read.map(|()| lines).map_err(|failure| failure.detail)
    }

    fn paragraph(text: &str) -> String {
        format!("<w:p><w:r><w:t>{text}</w:t></w:r></w:p>")
    }

    #[test]
    fn word_lines_count_every_paragraph_and_keep_a_nested_table_in_its_row() {
        let p = paragraph;
        let document = format!(
            "<w:document {WORD}><w:body>{}<w:p/><w:p><w:r><w:t>Zwei </w:t></w:r><w:r><w:t>Läufe<!-- c -->&amp; mehr</w:t></w:r></w:p>\
             <w:tbl><w:tr><w:tc>{}{}</w:tc><w:tc>{}</w:tc></w:tr>\
             <w:tr><w:tc>{}<w:tbl><w:tr><w:tc>{}</w:tc><w:tc>{}</w:tc></w:tr></w:tbl></w:tc><w:tc><w:p/></w:tc></w:tr>\
             <w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl>\
             <w:p><w:r><w:t>Rahmen</w:t></w:r><w:r><w:txbxContent>{}</w:txbxContent></w:r></w:p>\
             <w:p><w:r><w:t>   </w:t></w:r></w:p>{}</w:body></w:document>",
            p("Erster Absatz"),
            p("A1"),
            p("zweite Zeile"),
            p("B1"),
            p("außen"),
            p("innen 1"),
            p("innen 2"),
            p("im Textfeld"),
            p("Letzter")
        );
        let notes = format!(
            "<w:footnotes {WORD}><w:footnote><w:p/></w:footnote><w:footnote>{}</w:footnote></w:footnotes>",
            p("Fußnote eins")
        );
        let margin = |text: &str| format!("<w:hdr {WORD}>{}</w:hdr>", p(text));
        let parts = [
            ("word/header2.xml", margin("Kopf zwei")),
            ("word/header10.xml", margin("Kopf zehn")),
            ("word/headerx.xml", margin("kein Kopf")),
            ("word/footer1.xml", margin("Fuß · eins")),
            ("word/footnotes.xml", notes),
            ("word/document.xml", document),
        ];
        assert_eq!(
            lines("docx", &parts).unwrap(),
            [
                "word/document.xml · Paragraph 1: Erster Absatz\n",
                "word/document.xml · Paragraph 3: Zwei Läufe& mehr\n",
                "word/document.xml · Table row 4: A1 zweite Zeile\tB1\n",
                "word/document.xml · Table row 5: außen innen 1 innen 2\t\n",
                "word/document.xml · Paragraph 7: Rahmenim Textfeld\n",
                "word/document.xml · Paragraph 9: Letzter\n",
                "word/footnotes.xml · Paragraph 2: Fußnote eins\n",
                "word/footer1.xml · Paragraph 1: Fuß · eins\n",
                "word/header10.xml · Paragraph 1: Kopf zehn\n",
                "word/header2.xml · Paragraph 1: Kopf zwei\n",
            ]
        );
        for declared in ["<!DOCTYPE d [<!ENTITY x \"y\">]>", "<!doctype d>"] {
            let text = format!("{declared}<w:document {WORD}>{}</w:document>", p("x"));
            assert!(
                lines("docx", &[("word/document.xml", text)]).is_err(),
                "{declared}"
            );
        }
    }

    #[test]
    fn sheet_lines_show_saved_values_formulas_and_repetitions() {
        let sheet = |cells: &str| {
            format!("<worksheet><sheetData><row>{cells}</row></sheetData></worksheet>")
        };
        let rels = |rows: &str| format!("<Relationships>{rows}</Relationships>");
        let workbook = format!(
            "<workbook {LINKS}><sheets><sheet name=\"Zahlen\" r:id=\"rId1\"/><sheet name=\"Zwei\" r:id=\"rId2\"/></sheets></workbook>"
        );
        let parts = [
            ("xl/workbook.xml", workbook.clone()),
            (
                "xl/_rels/workbook.xml.rels",
                rels("<Relationship Id=\"rId1\" Target=\"worksheets/sheet1.xml\"/><Relationship Id=\"rId2\" Target=\"/xl/worksheets/./sheet2.xml\"/>"),
            ),
            (
                "xl/sharedStrings.xml",
                "<sst><si><t>Name</t></si><si><r><t>reich</t></r><r><t> formatiert</t></r></si></sst>".to_string(),
            ),
            (
                "xl/worksheets/sheet1.xml",
                sheet("<c r=\"A1\" t=\"s\"><v>0</v></c><c r=\"B1\" t=\"s\"><v> 1 </v></c><c r=\"C1\"/><c r=\"A2\"><v>41.5</v></c>\
                       <c r=\"B2\"><f>A2*2</f><v>83</v></c><c r=\"C2\"><f>NOW()</f></c><c r=\"D2\" t=\"inlineStr\"><is><t>inline</t></is></c>\
                       <c t=\"e\"><v>#DIV/0!</v></c>"),
            ),
            ("xl/worksheets/sheet2.xml", sheet("<c r=\"A1\"><v>8</v><c r=\"Z9\"><v>nested</v></c></c>")),
        ];
        assert_eq!(
            lines("xlsx", &parts).unwrap(),
            [
                "Zahlen!A1: Name\n",
                "Zahlen!B1: reich formatiert\n",
                "Zahlen!A2: 41.5\n",
                "Zahlen!B2: 83 [saved value; formula: A2*2]\n",
                "Zahlen!C2: [formula; no saved value] NOW()\n",
                "Zahlen!D2: inline\n",
                "Zahlen!?: #DIV/0!\n",
                "Zwei!A1: 8 nested\n",
            ]
        );
        // A sheet that is linked out of the file, climbs out of its folder or names no text is refused.
        for (target, cell) in [
            (
                "Target=\"file:///etc/passwd\" TargetMode=\"External\"",
                "<c/>",
            ),
            ("Target=\"../sheet.xml\"", "<c/>"),
            (
                "Target=\"worksheets/sheet1.xml\"",
                "<c t=\"s\"><v>0</v></c>",
            ),
            (
                "Target=\"worksheets/sheet1.xml\"",
                "<c t=\"s\"><v>-1</v></c>",
            ),
        ] {
            let parts = [
                (
                    "xl/workbook.xml",
                    workbook.replace("<sheet name=\"Zwei\" r:id=\"rId2\"/>", ""),
                ),
                (
                    "xl/_rels/workbook.xml.rels",
                    rels(&format!("<Relationship Id=\"rId1\" {target}/>")),
                ),
                ("xl/worksheets/sheet1.xml", sheet(cell)),
                ("sheet.xml", sheet(cell)),
            ];
            assert!(lines("xlsx", &parts).is_err(), "{target} {cell}");
        }
        let content = format!(
            "<office:document-content {OPEN}><table:table table:name=\"Blatt 1\">\
             <table:table-row><table:table-cell><text:p>Kopf</text:p><text:p>zweite</text:p></table:table-cell><table:table-cell table:number-columns-repeated=\"3\"/><table:table-cell office:value=\"12.5\"/></table:table-row>\
             <table:table-row table:number-rows-repeated=\"4\"><table:table-cell table:number-columns-repeated=\"2\" office:value=\"1\"><text:p>eins</text:p></table:table-cell><table:covered-table-cell/><table:table-cell office:date-value=\"2026-11-16\"/><table:table-cell table:formula=\"of:=SUM([.A1:.A2])\" office:value=\"3\"><text:p>3</text:p></table:table-cell></table:table-row>\
             <table:table-row><table:table-cell><table:table table:name=\"Innen\"><table:table-row><table:table-cell><text:p>innen</text:p></table:table-cell></table:table-row></table:table><text:p>außen</text:p></table:table-cell></table:table-row>\
             </table:table><table:table><table:table-row><table:table-cell><text:p>ohne Namen</text:p></table:table-cell></table:table-row></table:table></office:document-content>"
        );
        assert_eq!(
            lines("ods", &[("content.xml", content.clone())]).unwrap(),
            [
                "Blatt 1!R1C1: Kopf zweite\n",
                "Blatt 1!R1C5: 12.5\n",
                "Blatt 1!R2C1: eins [repeated rows=4, columns=2]\n",
                "Blatt 1!R2C4: 2026-11-16 [repeated rows=4, columns=1]\n",
                "Blatt 1!R2C5: 3 [formula: of:=SUM([.A1:.A2])] [repeated rows=4, columns=1]\n",
                // The Python reader names an outer row by the table that ended inside it.
                "Innen!R1C1: innen\n",
                "Innen!R2C1: außen\n",
                "!R1C1: ohne Namen\n",
            ]
        );
        let endless = content.replace(
            "number-rows-repeated=\"4\"",
            "number-rows-repeated=\"1048577\"",
        );
        assert!(lines("ods", &[("content.xml", endless)]).is_err());
    }

    #[test]
    fn slides_follow_the_presentation_or_their_numbers() {
        let slide = |texts: &[&str]| {
            let runs: String = texts
                .iter()
                .map(|text| format!("<a:r><a:t>{text}</a:t></a:r>"))
                .collect();
            format!(
                "<p:sld xmlns:p=\"urn:p\" xmlns:a=\"urn:a\"><a:p>{runs}</a:p><a:p><a:r><a:t> </a:t></a:r></a:p></p:sld>"
            )
        };
        let mut parts = vec![
            ("ppt/slides/slide10.xml", slide(&["zehn"])),
            ("ppt/slides/slide2.xml", slide(&["zwei", "und mehr"])),
            ("ppt/slides/slide1.xml", slide(&["eins"])),
            ("ppt/slides/slideX.xml", slide(&["keine Folie"])),
        ];
        assert_eq!(
            lines("pptx", &parts).unwrap(),
            [
                "Slide 1\neins\n",
                "Slide 2\nzwei und mehr\n",
                "Slide 3\nzehn\n"
            ]
        );
        parts.push((
            "ppt/presentation.xml",
            format!("<p:presentation xmlns:p=\"urn:p\" {LINKS}><p:sldIdLst><p:sldId r:id=\"rId3\"/><p:sldId r:id=\"rId2\"/></p:sldIdLst></p:presentation>"),
        ));
        assert!(lines("pptx", &parts).is_err());
        parts.push((
            "ppt/_rels/presentation.xml.rels",
            "<Relationships><Relationship Id=\"rId2\" Target=\"slides/slide1.xml\"/><Relationship Id=\"rId3\" Target=\"slides/slide2.xml\"/></Relationships>".to_string(),
        ));
        assert_eq!(
            lines("pptx", &parts).unwrap(),
            ["Slide 1\nzwei und mehr\n", "Slide 2\neins\n"]
        );
        let pages = format!(
            "<office:document-content {OPEN}><draw:page><text:p>Titel</text:p><text:p/><text:p>Punkt <text:span>eins</text:span></text:p>\
             <text:p>Notiz<text:p>innen</text:p>Ende</text:p></draw:page><draw:page><text:p>  </text:p></draw:page>\
             <draw:page><text:p>Dritte</text:p></draw:page></office:document-content>"
        );
        assert_eq!(
            lines("odp", &[("content.xml", pages)]).unwrap(),
            [
                "Slide 1\nTitel\n\nPunkt eins\nNotizinnenEnde\ninnen\n",
                "Slide 3\nDritte\n"
            ]
        );
        let text = format!(
            "<office:document-content {OPEN}><text:h>Titel</text:h><text:p>Eins</text:p><text:p/>\
             <text:p>Rahmen<draw:frame><text:p>innen</text:p></draw:frame> danach</text:p>\
             <table:table><table:table-row><table:table-cell><text:p>Zelle</text:p></table:table-cell></table:table-row></table:table></office:document-content>"
        );
        assert_eq!(
            lines("odt", &[("content.xml", text)]).unwrap(),
            [
                "Paragraph 1: Eins\n",
                "Paragraph 3: Rahmeninnen danach\n",
                "Paragraph 4: Zelle\n"
            ]
        );
    }

    #[test]
    fn text_is_decoded_across_block_borders() {
        let blocks = |parts: &[&[u8]], wide: Option<bool>| {
            let (mut data, mut text) = (Vec::new(), String::new());
            for (index, part) in parts.iter().enumerate() {
                data.extend_from_slice(part);
                text += &decode(&mut data, wide, index + 1 == parts.len());
            }
            assert!(data.is_empty());
            text
        };
        assert_eq!(
            blocks(&[b"Ma\xc3", b"\x9f \xf0\x9f", b"\x98\x80"], None),
            "Maß 😀"
        );
        // Windows-1252 where the bytes are not UTF-8, also for a sequence that only begins.
        assert_eq!(
            blocks(&[b"Gr\xf6\xdfe \x80 \x84x\x93 \x81", b"\xe2\x82"], None),
            "Größe € „x“ \u{81}â‚"
        );
        assert_eq!(blocks(&[b"\xe2", b"\x82a"], None), "â‚a");
        assert_eq!(
            blocks(&[b"h\0\x3d\xd8", b"\x00\xde!\0"], Some(false)),
            "h😀!"
        );
        assert_eq!(
            blocks(&[b"\0h\xd8\x3d", b"\0!\0"], Some(true)),
            "h\u{FFFD}!\u{FFFD}"
        );
    }

    #[test]
    fn wave_headers_and_floats_read_as_in_python() {
        for (value, text) in [
            (2.0, "2.0"),
            (0.5, "0.5"),
            (0.0, "0.0"),
            (1.0 / 44100.0, "2.2675736961451248e-05"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (1234.5, "1234.5"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (-1.5e-7, "-1.5e-07"),
        ] {
            assert_eq!(python_float(value), text);
        }
        let chunk = |name: &[u8; 4], data: &[u8]| {
            let mut out = [name.as_slice(), &(data.len() as u32).to_le_bytes(), data].concat();
            out.resize(out.len() + data.len() % 2, 0);
            out
        };
        let file = |chunks: &[Vec<u8>]| {
            let body = [b"WAVE".to_vec(), chunks.concat()].concat();
            std::io::Cursor::new(
                [
                    b"RIFF".to_vec(),
                    (body.len() as u32).to_le_bytes().to_vec(),
                    body,
                ]
                .concat(),
            )
        };
        let format = |tag: u16, channels: u16, rate: u32, bits: u16| {
            let mut out = [tag.to_le_bytes(), channels.to_le_bytes()].concat();
            out.extend(
                rate.to_le_bytes()
                    .iter()
                    .chain(&[0; 6])
                    .chain(&bits.to_le_bytes()),
            );
            out
        };
        let plain = file(&[
            chunk(b"LIST", b"odd"),
            chunk(b"fmt ", &format(1, 2, 44100, 16)),
            chunk(b"data", &[0; 400]),
        ]);
        assert_eq!(
            wav(&mut { plain }).unwrap(),
            "{\"channels\": 2, \"sample_rate\": 44100, \"bits_per_sample\": 16, \"frames\": 100, \"duration_seconds\": 0.0022675736961451248, \"compression\": \"NONE\"}"
        );
        let mut extended = format(0xFFFE, 1, 48000, 20);
        extended.extend([22, 0, 20, 0, 4, 0, 0, 0]);
        extended.extend(b"\x01\0\0\0\0\0\x10\0\x80\0\0\xaa\0\x38\x9b\x71");
        let known = file(&[chunk(b"fmt ", &extended), chunk(b"data", &[0; 72000])]);
        assert!(
            wav(&mut { known })
                .unwrap()
                .contains("\"bits_per_sample\": 24, \"frames\": 24000, \"duration_seconds\": 0.5,")
        );
        extended[24] = 3;
        for refused in [
            file(&[chunk(b"fmt ", &extended), chunk(b"data", &[0; 8])]),
            file(&[
                chunk(b"fmt ", &format(3, 1, 48000, 32)),
                chunk(b"data", &[0; 8]),
            ]),
            file(&[
                chunk(b"fmt ", &format(1, 1, 0, 16)),
                chunk(b"data", &[0; 8]),
            ]),
            file(&[
                chunk(b"data", &[0; 8]),
                chunk(b"fmt ", &format(1, 1, 48000, 16)),
            ]),
            file(&[chunk(b"fmt ", &format(1, 1, 48000, 16))]),
            std::io::Cursor::new(b"RIFF\x04\0\0\0AVI ".to_vec()),
        ] {
            assert!(wav(&mut { refused }).is_err());
        }
    }

    #[test]
    fn pictures_are_known_by_their_first_bytes_and_text_layers_are_judged() {
        for (head, kind) in [
            (&b"\xff\xd8\xff\xe0\0\x10JFIF"[..], Some("jpeg")),
            (b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR", Some("png")),
            (b"GIF89a", Some("gif")),
            (b"BM\x36\0\0\0", Some("bmp")),
            (b"II*\0\x08\0\0\0", Some("tiff")),
            (b"MM\0*\0\0\0\x08", Some("tiff")),
            (b"RIFF\x24\0\0\0WEBPVP8 ", Some("webp")),
            (b"RIFF\x24\0\0\0WAVEfmt ", None),
            (b"\0\0\0\x1cftypavif\0\0\0\0avifmif1miaf", Some("avif")),
            (b"\0\0\0\x18ftypheic\0\0\0\0mif1heic", Some("heic")),
            (b"\0\0\0\x18ftypmif1\0\0\0\0mif1heic", Some("heic")),
            (b"\0\0\0\x18ftypisom\0\0\0\0isomiso2", None),
            (b"\xff\x0a\0\0", Some("jxl")),
            (b"\0\0\0\x0cJXL \r\n\x87\n", Some("jxl")),
            (b"%PDF-1.7\n", None),
            (b"<svg xmlns=", None),
            (b"", None),
        ] {
            assert_eq!(magic(head), kind, "{head:?}");
        }
        assert!(reliable("Ein Satz mit Größe."));
        assert!(!reliable(" \n\u{1c}"));
        assert!(!reliable("nul\0"));
        // Up to 2 % of the characters may be unreadable.
        assert!(reliable(&format!("{}\u{FFFD}", "a".repeat(49))));
        assert!(!reliable(&format!("{}\u{E000}", "a".repeat(48))));
        assert!(!reliable(&format!("{}\u{FDD0}\u{10FFFF}", "a".repeat(90))));
        assert_eq!(strip("\u{1f} a\u{a0}\n"), "a");
    }

    #[test]
    fn a_page_that_cannot_be_read_does_not_end_the_document() {
        let font = "<< /Type /Font /Subtype /Type3 /FontBBox [0 0 500 500] /FontMatrix [0.001 0 0 0.001 0 0] \
                    /CharProcs << /ff 7 0 R /germandbls 7 0 R >> /Encoding << /Differences [65 /ff /germandbls] >> \
                    /FirstChar 65 /LastChar 66 /Widths [500 500] >>";
        let stream =
            |data: &str| format!("<< /Length {} >>\nstream\n{data}\nendstream", data.len());
        let page = |content: usize| {
            format!(
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << /Font << /F1 6 0 R >> >> /Contents {content} 0 R >>"
            )
        };
        let file = crate::pdf::assemble(&[
            "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
            "<< /Type /Pages /Count 3 /Kids [3 0 R 4 0 R 5 0 R] >>".to_string(),
            page(8),
            page(9),
            page(8),
            font.to_string(),
            stream("500 0 d0 0 0 500 500 re f"),
            stream("BT /F1 10 Tf 10 50 Td (AB) Tj ET"),
            stream("BT /F1 10 Tf 10 50 Td (AB) Tj ET BOGUS"),
        ]);
        let path = std::env::temp_dir().join(format!("lumen-blocks-{}.pdf", std::process::id()));
        std::fs::write(&path, file).unwrap();
        let mut input = File::open(&path).unwrap();
        let _ = std::fs::remove_file(&path);
        let mut out = Vec::new();
        // Neither page needs a tool: two have a text layer, and one can be neither read nor drawn.
        pdf_blocks(&mut input, &std::env::temp_dir(), 0, &mut out).unwrap();
        assert_eq!(
            String::from_utf8(out).unwrap().lines().collect::<Vec<_>>(),
            [
                "{\"info\": {\"pages\": 3}}",
                "{\"text\": \"Page 1\\nﬀß\\n\", \"location\": {\"page\": 1}, \"method\": \"text\"}",
                "{\"unread\": 2, \"detail\": \"PDF-Grafikoperator noch nicht unterstützt: BOGUS\"}",
                "{\"text\": \"Page 3\\nﬀß\\n\", \"location\": {\"page\": 3}, \"method\": \"text\"}",
            ]
        );
        // Embedded pictures are chosen by the suffix Python's `Path(name).suffix.lower()` gave.
        for (name, found) in [
            ("word/media/a.PNG", ".png"),
            ("word/media/b.png.txt", ".txt"),
            ("word/media/.png", ""),
            ("word/media/..png", ""),
            ("word/media.d/c", ""),
            ("word/media/d.jpeg/", ".jpeg"),
            ("word/media/e.", "."),
        ] {
            assert_eq!(suffix(name), found, "{name}");
        }
    }

    #[test]
    fn the_area_of_a_page_s_images_is_summed_in_page_units() {
        // An image over the lower half of the page, drawn directly and through a form scaled by a half.
        let content = "q 600 0 0 400 0 0 cm /Im Do Q q 0.5 0 0 0.5 0 0 cm /Fm Do Q";
        let inner = "q 1200 0 0 800 0 0 cm /Im Do Q";
        let objects = [
            "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
            "<< /Type /Pages /Count 1 /Kids [3 0 R] >>".to_string(),
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Rotate 90 /Resources << /XObject << /Im 4 0 R /Fm 5 0 R >> >> /Contents 6 0 R >>".to_string(),
            "<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n0\nendstream".to_string(),
            format!("<< /Type /XObject /Subtype /Form /BBox [0 0 1200 1600] /Resources << /XObject << /Im 4 0 R >> >> /Length {} >>\nstream\n{inner}\nendstream", inner.len()),
            format!("<< /Length {} >>\nstream\n{content}\nendstream", content.len()),
        ];
        let (mut file, mut offsets) = ("%PDF-1.4\n".to_string(), Vec::new());
        for (index, object) in objects.iter().enumerate() {
            offsets.push(file.len());
            file += &format!("{} 0 obj\n{object}\nendobj\n", index + 1);
        }
        let start = file.len();
        file += "xref\n0 7\n0000000000 65535 f \n";
        for offset in offsets {
            file += &format!("{offset:010} 00000 n \n");
        }
        file += &format!("trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n");
        let document = crate::pdf::Document::new(file.into_bytes()).unwrap();
        let (width, height, words, area) = Page::words_and_images(&document, 0).unwrap();
        assert_eq!((width, height, words.len()), (800.0, 600.0, 0));
        assert_eq!(area, 2.0 * 600.0 * 400.0);
    }
}

//! Word, Excel, PowerPoint and OpenDocument files as reading HTML: headings, emphasis, lists,
//! tables and pictures. A reading view, not the printed layout. The output is the same text the
//! Python reader (`files/lumen_office.py`) produced, so both can be compared file by file.
use std::cell::RefCell;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::File;
use std::io::Read;
use std::path::Path;

use roxmltree::{Document, Node, ParsingOptions};

const W: &str = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const WP: &str = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing";
const A: &str = "http://schemas.openxmlformats.org/drawingml/2006/main";
const R: &str = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const S: &str = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
const P: &str = "http://schemas.openxmlformats.org/presentationml/2006/main";
const TEXT: &str = "urn:oasis:names:tc:opendocument:xmlns:text:1.0";
const TABLE: &str = "urn:oasis:names:tc:opendocument:xmlns:table:1.0";
const DRAW: &str = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0";
const STYLE: &str = "urn:oasis:names:tc:opendocument:xmlns:style:1.0";
const FO: &str = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0";
const SVG: &str = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0";
const OFFICE: &str = "urn:oasis:names:tc:opendocument:xmlns:office:1.0";
const XLINK: &str = "http://www.w3.org/1999/xlink";
const DC: &str = "http://purl.org/dc/elements/1.1/";
const PICTURES: [&str; 5] = [".png", ".jpg", ".jpeg", ".gif", ".bmp"];
/// Characters of HTML per document; more is cut with a visible note.
const MAX_HTML: usize = 4 * 1024 * 1024;
const MAX_ROWS: usize = 1000;
const MAX_COLUMNS: usize = 40;
/// Reading width in px inside the page margins.
const PAGE: f64 = 536.0;

pub struct Reading {
    pub title: String,
    /// One HTML section per document, sheet or slide.
    pub sections: Vec<String>,
}

type Outcome<T> = Result<T, String>;

/// Like Python's `html.escape`: text and attribute values share one form.
fn escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            c => out.push(c),
        }
    }
    out
}

fn is(node: Node, space: &str, name: &str) -> bool {
    node.is_element()
        && node.tag_name().name() == name
        && node.tag_name().namespace() == Some(space)
}

fn child<'a, 'i>(node: Node<'a, 'i>, space: &str, name: &str) -> Option<Node<'a, 'i>> {
    node.children().find(|c| is(*c, space, name))
}

fn children<'a, 'i: 'a>(
    node: Node<'a, 'i>,
    space: &'a str,
    name: &'a str,
) -> impl Iterator<Item = Node<'a, 'i>> {
    node.children().filter(move |c| is(*c, space, name))
}

/// The node itself and everything below it, in document order.
fn all<'a, 'i: 'a>(
    node: Node<'a, 'i>,
    space: &'a str,
    name: &'a str,
) -> impl Iterator<Item = Node<'a, 'i>> {
    node.descendants().filter(move |c| is(*c, space, name))
}

fn digits(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit())
}

struct Pack {
    names: HashSet<String>,
    archive: RefCell<zip::ZipArchive<File>>,
    labels: HashMap<String, String>,
    /// The most sheet rows and columns read: the reading view is cut, the search is not.
    rows: usize,
    columns: usize,
    hidden: bool,
}

impl Pack {
    fn open(path: &Path, labels: &HashMap<String, String>) -> Outcome<Pack> {
        let damaged = || "Geschützte oder beschädigte Office-Datei.".to_string();
        let mut archive = zip::ZipArchive::new(File::open(path).map_err(|_| damaged())?)
            .map_err(|_| damaged())?;
        let mut names = HashSet::new();
        let mut total = 0u64;
        let mut refused = archive.len() > 10000;
        for index in 0..archive.len() {
            let Ok(entry) = archive.by_index_raw(index) else {
                return Err(damaged());
            };
            total += entry.size();
            refused |= entry.size() > 64 * 1024 * 1024
                || entry.encrypted()
                || !names.insert(entry.name().to_string());
        }
        if refused || total > 256 * 1024 * 1024 {
            return Err("Diese Office-Datei enthält zu viele, doppelte, verschlüsselte oder zu große Inhalte.".into());
        }
        Ok(Pack {
            names,
            archive: RefCell::new(archive),
            labels: labels.clone(),
            rows: MAX_ROWS,
            columns: MAX_COLUMNS,
            hidden: false,
        })
    }

    fn label(&self, key: &str) -> String {
        self.labels
            .get(key)
            .cloned()
            .unwrap_or_else(|| key.to_string())
    }

    /// The text of an XML part. Entity declarations are refused, so nothing is expanded or fetched.
    fn part(&self, name: &str) -> Outcome<String> {
        let missing = || format!("Office-Datei unvollständig: {name}");
        if !self.names.contains(name) {
            return Err(missing());
        }
        let mut raw = Vec::new();
        self.archive
            .borrow_mut()
            .by_name(name)
            .map_err(|_| missing())?
            .read_to_end(&mut raw)
            .map_err(|_| missing())?;
        if raw
            .to_ascii_uppercase()
            .windows(8)
            .any(|w| w == b"<!ENTITY")
        {
            return Err("XML-Entitäten im EPUB werden nicht geladen.".into());
        }
        let text = String::from_utf8(raw).map_err(|_| missing())?;
        Ok(text
            .strip_prefix('\u{feff}')
            .map(str::to_string)
            .unwrap_or(text))
    }

    /// Targets of a part's relationships, as archive names; links out of the file are left out.
    fn relations(&self, name: &str) -> Outcome<HashMap<String, String>> {
        let (folder, file) = name.rsplit_once('/').unwrap_or(("", name));
        let path = join(&join(folder, "_rels"), &format!("{file}.rels"));
        let mut result = HashMap::new();
        if !self.names.contains(&path) {
            return Ok(result);
        }
        let text = self.part(&path)?;
        let document = parse(&text)?;
        for item in document.root_element().children().filter(Node::is_element) {
            if item.attribute("TargetMode") == Some("External") {
                continue;
            }
            let target = item.attribute("Target").unwrap_or("");
            let resolved = if target.starts_with('/') {
                target.trim_start_matches('/').to_string()
            } else {
                normal(&join(folder, target))
            };
            if let Some(identity) = item.attribute("Id") {
                result.insert(identity.to_string(), resolved);
            }
        }
        Ok(result)
    }

    fn picture(&self, name: &str, mut width: f64, mut height: f64) -> String {
        let lower = name.to_lowercase();
        if !self.names.contains(name) || !PICTURES.iter().any(|suffix| lower.ends_with(suffix)) {
            return format!(
                "<p><i>{}</i></p>",
                escape(&self.label("[Bild in diesem Format nicht darstellbar]"))
            );
        }
        if width > PAGE {
            (width, height) = (PAGE, height * PAGE / width);
        }
        let size = if width >= 1.0 && height >= 1.0 {
            format!(
                " width=\"{}\" height=\"{}\"",
                width.round_ties_even() as i64,
                height.round_ties_even() as i64
            )
        } else if width == 0.0 {
            format!(" width=\"{}\"", PAGE as i64)
        } else {
            String::new()
        };
        format!("<img src=\"/{}\"{size}>", escape(name))
    }
}

fn parse(text: &str) -> Outcome<Document<'_>> {
    Document::parse_with_options(
        text,
        ParsingOptions {
            allow_dtd: true,
            ..ParsingOptions::default()
        },
    )
    .map_err(|error| format!("Office-Datei unvollständig: {error}"))
}

fn join(folder: &str, name: &str) -> String {
    if name.starts_with('/') || folder.is_empty() {
        name.to_string()
    } else if folder.ends_with('/') {
        format!("{folder}{name}")
    } else {
        format!("{folder}/{name}")
    }
}

/// POSIX path normalisation: `a/./b/../c` becomes `a/c`.
fn normal(path: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for piece in path.split('/') {
        match piece {
            "" | "." => {}
            ".." if parts.last().is_some_and(|last| *last != "..") => {
                parts.pop();
            }
            ".." if path.starts_with('/') => {}
            piece => parts.push(piece),
        }
    }
    let joined = parts.join("/");
    if path.starts_with('/') {
        format!("/{joined}")
    } else if joined.is_empty() {
        ".".into()
    } else {
        joined
    }
}

fn emu(node: Option<Node>) -> (f64, f64) {
    let side = |name| {
        node.and_then(|n| n.attribute(name))
            .and_then(|v: &str| v.parse::<i64>().ok())
            .unwrap_or(0) as f64
            / 9525.0
    };
    if node.is_some() {
        (side("cx"), side("cy"))
    } else {
        (0.0, 0.0)
    }
}

// ---- Word ----

struct Word<'p> {
    pack: &'p Pack,
    links: HashMap<String, String>,
    headings: HashMap<String, usize>,
    /// numId -> level -> number format (None when the level names none).
    formats: HashMap<String, HashMap<String, Option<String>>>,
    counters: RefCell<HashMap<(String, String), usize>>,
}

fn enabled(properties: Node, tag: &str) -> bool {
    child(properties, W, tag).is_some_and(|node| {
        !matches!(
            node.attribute((W, "val")).unwrap_or("true"),
            "0" | "false" | "none"
        )
    })
}

impl Word<'_> {
    fn run(&self, node: Node) -> String {
        let properties = child(node, W, "rPr");
        let mut text = String::new();
        for part in node.children().filter(Node::is_element) {
            if is(part, W, "t") {
                text.push_str(&escape(part.text().unwrap_or("")));
            } else if is(part, W, "tab") {
                text.push_str("&emsp;");
            } else if (is(part, W, "br") || is(part, W, "cr"))
                && part.attribute((W, "type")) != Some("page")
            {
                text.push_str("<br>");
            } else if is(part, W, "drawing") || is(part, W, "pict") {
                for blip in all(part, A, "blip") {
                    let (width, height) = emu(all(part, WP, "extent").next());
                    let name = blip
                        .attribute((R, "embed"))
                        .and_then(|id| self.links.get(id))
                        .map(String::as_str)
                        .unwrap_or("");
                    text.push_str(&self.pack.picture(name, width, height));
                }
            }
        }
        let Some(properties) = properties else {
            return text;
        };
        if text.is_empty() {
            return text;
        }
        for (tag, mark) in [("b", "b"), ("i", "i"), ("strike", "s"), ("u", "u")] {
            if enabled(properties, tag) {
                text = format!("<{mark}>{text}</{mark}>");
            }
        }
        match child(properties, W, "vertAlign").and_then(|node| node.attribute((W, "val"))) {
            Some("superscript") => text = format!("<sup>{text}</sup>"),
            Some("subscript") => text = format!("<sub>{text}</sub>"),
            _ => {}
        }
        if let Some(colour) =
            child(properties, W, "color").and_then(|node| node.attribute((W, "val")))
            && colour.len() == 6
            && colour.bytes().all(|b| b.is_ascii_hexdigit())
        {
            text = format!("<span style=\"color:#{colour}\">{text}</span>");
        }
        text
    }

    fn inline(&self, node: Node) -> String {
        let mut text = String::new();
        for part in node.children().filter(Node::is_element) {
            if is(part, W, "r") {
                text.push_str(&self.run(part));
            } else if [
                "hyperlink",
                "ins",
                "smartTag",
                "sdt",
                "sdtContent",
                "fldSimple",
            ]
            .iter()
            .any(|name| is(part, W, name))
            {
                text.push_str(&self.inline(part));
            }
        }
        text
    }

    fn paragraph(&self, node: Node) -> String {
        let properties = child(node, W, "pPr");
        let text = self.inline(node);
        let filled = !text.trim().is_empty();
        let style = properties
            .and_then(|p| child(p, W, "pStyle"))
            .and_then(|s| s.attribute((W, "val")));
        if let Some(level) = style
            .and_then(|s| self.headings.get(s))
            .filter(|level| **level > 0 && filled)
        {
            let level = (*level).min(6);
            return format!("<h{level}>{text}</h{level}>");
        }
        let align = match properties
            .and_then(|p| child(p, W, "jc"))
            .and_then(|j| j.attribute((W, "val")))
        {
            Some("center") => " align=\"center\"",
            Some("right" | "end") => " align=\"right\"",
            Some("both") => " align=\"justify\"",
            _ => "",
        };
        if let Some(listing) = properties
            .and_then(|p| child(p, W, "numPr"))
            .filter(|_| filled)
        {
            let depth = child(listing, W, "ilvl")
                .map(|n| n.attribute((W, "val")).unwrap_or("0"))
                .unwrap_or("0");
            let number = child(listing, W, "numId")
                .and_then(|n| n.attribute((W, "val")))
                .unwrap_or("");
            if number != "0" {
                let level = depth.parse::<i64>().unwrap_or(0);
                let mut counters = self.counters.borrow_mut();
                let count = *counters
                    .entry((number.to_string(), depth.to_string()))
                    .and_modify(|c| *c += 1)
                    .or_insert(1);
                counters
                    .retain(|key, _| key.0 != number || key.1.parse::<i64>().unwrap_or(0) <= level);
                let format = self
                    .formats
                    .get(number)
                    .and_then(|levels| levels.get(depth))
                    .cloned()
                    .unwrap_or(Some("bullet".into()));
                let mark = if format.as_deref() == Some("bullet") {
                    "•".to_string()
                } else {
                    format!("{count}.")
                };
                return format!(
                    "<p style=\"margin-left:{}px\">{mark}&nbsp;{text}</p>",
                    20 * (level.min(8) + 1)
                );
            }
        }
        format!(
            "<p{align}>{}</p>",
            if text.is_empty() { "&nbsp;" } else { &text }
        )
    }

    fn table(&self, node: Node) -> String {
        let mut rows = String::new();
        for row in children(node, W, "tr") {
            let mut cells = String::new();
            for cell in children(row, W, "tc") {
                let properties = child(cell, W, "tcPr");
                let span = properties.and_then(|p| child(p, W, "gridSpan"));
                let merge = properties.and_then(|p| child(p, W, "vMerge"));
                // A continued vertical merge is an empty cell here; the text stands in the first one.
                let content = if merge.is_some_and(|m| m.attribute((W, "val")) != Some("restart")) {
                    String::new()
                } else {
                    self.blocks(cell)
                };
                let colspan = span
                    .map(|s| {
                        format!(
                            " colspan=\"{}\"",
                            s.attribute((W, "val"))
                                .and_then(|v| v.parse::<i64>().ok())
                                .unwrap_or(1)
                        )
                    })
                    .unwrap_or_default();
                cells.push_str(&format!("<td{colspan}>{content}</td>"));
            }
            rows.push_str(&format!("<tr>{cells}</tr>"));
        }
        format!(
            "<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\" width=\"100%\">{rows}</table>"
        )
    }

    fn blocks(&self, node: Node) -> String {
        let mut result = String::new();
        for part in node.children().filter(Node::is_element) {
            if is(part, W, "p") {
                result.push_str(&self.paragraph(part));
            } else if is(part, W, "tbl") {
                result.push_str(&self.table(part));
            } else if is(part, W, "sdt") || is(part, W, "sdtContent") {
                result.push_str(&self.blocks(part));
            }
        }
        result
    }
}

fn word(pack: &Pack) -> Outcome<Vec<String>> {
    let text = pack.part("word/document.xml")?;
    let document = parse(&text)?;
    let mut reader = Word {
        pack,
        links: pack.relations("word/document.xml")?,
        headings: HashMap::new(),
        formats: HashMap::new(),
        counters: RefCell::new(HashMap::new()),
    };
    if pack.names.contains("word/styles.xml") {
        let text = pack.part("word/styles.xml")?;
        for style in all(parse(&text)?.root_element(), W, "style") {
            let name = child(style, W, "name")
                .and_then(|n| n.attribute((W, "val")))
                .unwrap_or("")
                .to_lowercase();
            let level = match name.strip_prefix("heading ") {
                Some(digit)
                    if digit.chars().count() == 1 && digit.chars().all(char::is_numeric) =>
                {
                    digit
                        .chars()
                        .next()
                        .and_then(|c| c.to_digit(10))
                        .map(|d| d as usize)
                }
                _ if name == "title" => Some(1),
                _ => None,
            };
            if let (Some(level), Some(identity)) = (level, style.attribute((W, "styleId"))) {
                reader.headings.insert(identity.to_string(), level);
            }
        }
    }
    if pack.names.contains("word/numbering.xml") {
        let text = pack.part("word/numbering.xml")?;
        let numbering = parse(&text)?;
        let mut templates: HashMap<String, HashMap<String, Option<String>>> = HashMap::new();
        for item in all(numbering.root_element(), W, "abstractNum") {
            let levels = all(item, W, "lvl")
                .filter_map(|level| {
                    let format = match child(level, W, "numFmt") {
                        Some(format) => format.attribute((W, "val")).map(str::to_string),
                        None => Some("bullet".to_string()),
                    };
                    level
                        .attribute((W, "ilvl"))
                        .map(|depth| (depth.to_string(), format))
                })
                .collect();
            if let Some(identity) = item.attribute((W, "abstractNumId")) {
                templates.insert(identity.to_string(), levels);
            }
        }
        for item in all(numbering.root_element(), W, "num") {
            if let (Some(reference), Some(identity)) = (
                child(item, W, "abstractNumId"),
                item.attribute((W, "numId")),
            ) {
                reader.formats.insert(
                    identity.to_string(),
                    reference
                        .attribute((W, "val"))
                        .and_then(|id| templates.get(id))
                        .cloned()
                        .unwrap_or_default(),
                );
            }
        }
    }
    let body = child(document.root_element(), W, "body").ok_or("Word-Dokument ohne Inhalt.")?;
    Ok(vec![reader.blocks(body)])
}

// ---- Excel ----

/// Python's `format(number, '.10g')` with a decimal comma, or the plain integer.
pub fn cell_text(value: &str) -> Option<String> {
    let number: f64 = value.trim().parse().ok()?;
    if number.is_finite() && number.fract() == 0.0 && number.abs() < 1e15 {
        return Some(format!("{}", number as i64));
    }
    if !number.is_finite() {
        return Some(if number.is_nan() {
            "nan".into()
        } else if number > 0.0 {
            "inf".into()
        } else {
            "-inf".into()
        });
    }
    // Ten significant digits, correctly rounded once; the decimal point is then placed by hand.
    let scientific = format!("{:.9e}", number.abs());
    let (mantissa, exponent) = scientific.split_once('e')?;
    let exponent: i32 = exponent.parse().ok()?;
    let figures: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let sign = if number < 0.0 { "-" } else { "" };
    let text = if !(-4..10).contains(&exponent) {
        let rest = figures[1..].trim_end_matches('0');
        format!(
            "{sign}{}{}{}e{}{:02}",
            &figures[..1],
            if rest.is_empty() { "" } else { "." },
            rest,
            if exponent < 0 { '-' } else { '+' },
            exponent.abs()
        )
    } else if exponent < 0 {
        format!(
            "{sign}0.{}{}",
            "0".repeat((-exponent - 1) as usize),
            figures.trim_end_matches('0')
        )
    } else {
        let whole = (exponent + 1) as usize;
        let rest = figures[whole..].trim_end_matches('0');
        format!(
            "{sign}{}{}{}",
            &figures[..whole],
            if rest.is_empty() { "" } else { "." },
            rest
        )
    };
    Some(text.replace('.', ","))
}

/// A number format without its quoted text, bracketed sections and escaped characters.
fn pattern(code: &str) -> String {
    let mut out = String::new();
    let mut letters = code.chars();
    while let Some(c) = letters.next() {
        match c {
            '"' | '[' => {
                let close = if c == '"' { '"' } else { ']' };
                let rest: String = letters.clone().collect();
                match rest.find(close) {
                    Some(end) => letters = letters.as_str()[end + close.len_utf8()..].chars(),
                    None => out.push(c),
                }
            }
            '\\' => {
                if letters.clone().next().is_some_and(|next| next != '\n') {
                    letters.next();
                } else {
                    out.push(c);
                }
            }
            c => out.push(c),
        }
    }
    out
}

/// Day, month, year, hour and minute for a serial day number; None outside the years 1 to 9999.
fn moment(epoch_days: i64, serial: f64) -> Option<(i64, u32, u32, u32, u32)> {
    let micros = (serial * 86_400_000_000.0).round_ties_even();
    if !micros.is_finite() || micros.abs() > 4e17 {
        return None;
    }
    let micros = micros as i64;
    let days = epoch_days + micros.div_euclid(86_400_000_000);
    let seconds = micros.rem_euclid(86_400_000_000) / 1_000_000;
    // Civil date from days since 1970-01-01 (Howard Hinnant's algorithm).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let year = yoe + era * 400 + i64::from(month <= 2);
    (1..=9999).contains(&year).then_some((
        year,
        month,
        day,
        (seconds / 3600) as u32,
        (seconds % 3600 / 60) as u32,
    ))
}

fn spreadsheet(pack: &Pack) -> Outcome<Vec<String>> {
    let text = pack.part("xl/workbook.xml")?;
    let workbook = parse(&text)?;
    let links = pack.relations("xl/workbook.xml")?;
    let mut strings = Vec::new();
    if pack.names.contains("xl/sharedStrings.xml") {
        let text = pack.part("xl/sharedStrings.xml")?;
        for item in children(parse(&text)?.root_element(), S, "si") {
            // Phonetic guides (rPh) repeat the text and are not part of it.
            strings.push(
                item.children()
                    .filter(|part| part.is_element() && !is(*part, S, "rPh"))
                    .flat_map(|part| all(part, S, "t"))
                    .map(|t| t.text().unwrap_or(""))
                    .collect::<String>(),
            );
        }
    }
    let (mut dates, mut percents) = (Vec::new(), Vec::new());
    if pack.names.contains("xl/styles.xml") {
        let text = pack.part("xl/styles.xml")?;
        let styles = parse(&text)?;
        let custom: HashMap<&str, &str> = all(styles.root_element(), S, "numFmt")
            .filter_map(|item| {
                Some((
                    item.attribute("numFmtId")?,
                    item.attribute("formatCode").unwrap_or(""),
                ))
            })
            .collect();
        if let Some(formats) = child(styles.root_element(), S, "cellXfs") {
            for item in formats.children().filter(Node::is_element) {
                let identity = item.attribute("numFmtId").unwrap_or("0");
                let code = pattern(custom.get(identity).copied().unwrap_or(""));
                let builtin = digits(identity)
                    && identity.parse::<u32>().is_ok_and(|id| {
                        (14..=22).contains(&id)
                            || (27..=36).contains(&id)
                            || (45..=47).contains(&id)
                            || (50..=58).contains(&id)
                    });
                dates.push(builtin || code.chars().any(|c| "ymdhsYMDHS".contains(c)));
                percents.push(identity == "9" || identity == "10" || code.contains('%'));
            }
        }
    }
    let late = child(workbook.root_element(), S, "workbookPr")
        .is_some_and(|p| matches!(p.attribute("date1904"), Some("1" | "true")));
    let epoch_days = if late { -24_107 } else { -25_569 }; // 1904-01-01 and 1899-12-30, in days since 1970-01-01
    let mut result = Vec::new();
    for sheet in all(workbook.root_element(), S, "sheet") {
        if !pack.hidden && matches!(sheet.attribute("state"), Some("hidden" | "veryHidden")) {
            continue;
        }
        let Some(name) = sheet
            .attribute((R, "id"))
            .and_then(|id| links.get(id))
            .filter(|name| !name.is_empty())
        else {
            continue;
        };
        let text = pack.part(name)?;
        let mut rows: BTreeMap<usize, BTreeMap<usize, (String, bool)>> = BTreeMap::new();
        let mut cut = false;
        for row in all(parse(&text)?.root_element(), S, "row") {
            for cell in children(row, S, "c") {
                let reference = cell.attribute("r").unwrap_or("");
                let letters = reference.bytes().take_while(u8::is_ascii_uppercase).count();
                let figures = &reference[letters..];
                if !(1..=3).contains(&letters)
                    || !(1..=7).contains(&figures.len())
                    || !digits(figures)
                {
                    continue;
                }
                let column = reference[..letters]
                    .bytes()
                    .fold(0usize, |sum, letter| sum * 26 + (letter - 64) as usize);
                let line: usize = figures.parse().unwrap_or(0);
                if line > pack.rows || column > pack.columns {
                    cut = true;
                    continue;
                }
                let kind = cell.attribute("t").unwrap_or("n");
                let value = child(cell, S, "v")
                    .map(|v| v.text().unwrap_or(""))
                    .unwrap_or("");
                let style = cell
                    .attribute("s")
                    .filter(|s| digits(s))
                    .and_then(|s| s.parse::<usize>().ok())
                    .unwrap_or(0);
                let mut numeric = false;
                // What cannot be read as its type is shown as it stands in the file.
                let text = match kind {
                    "s" => value
                        .trim()
                        .parse::<usize>()
                        .ok()
                        .and_then(|index| strings.get(index).cloned())
                        .unwrap_or_else(|| value.to_string()),
                    "inlineStr" => all(cell, S, "t").map(|t| t.text().unwrap_or("")).collect(),
                    "b" => pack.label(if value == "1" { "WAHR" } else { "FALSCH" }),
                    "str" | "e" => value.to_string(),
                    _ if value.is_empty() => String::new(),
                    _ if dates.get(style).copied().unwrap_or(false) => value
                        .trim()
                        .parse::<f64>()
                        .ok()
                        .and_then(|serial| {
                            let (year, month, day, hour, minute) = moment(epoch_days, serial)?;
                            Some(if serial < 1.0 {
                                format!("{hour:02}:{minute:02}")
                            } else if serial.fract() == 0.0 {
                                format!("{day:02}.{month:02}.{year:04}")
                            } else {
                                format!("{day:02}.{month:02}.{year:04} {hour:02}:{minute:02}")
                            })
                        })
                        .unwrap_or_else(|| value.to_string()),
                    _ if percents.get(style).copied().unwrap_or(false) => match value
                        .trim()
                        .parse::<f64>()
                        .ok()
                        .and_then(|share| cell_text(&format!("{:.8}", share * 100.0)))
                    {
                        Some(text) => {
                            numeric = true;
                            format!("{text} %")
                        }
                        None => value.to_string(),
                    },
                    _ => match cell_text(value) {
                        Some(text) => {
                            numeric = true;
                            text
                        }
                        None => value.to_string(),
                    },
                };
                if !text.is_empty() {
                    rows.entry(line)
                        .or_default()
                        .insert(column, (text, numeric));
                }
            }
        }
        let title = format!("<h2>{}</h2>", escape(sheet.attribute("name").unwrap_or("")));
        let (Some(first), Some(last)) = (
            rows.keys().next().copied(),
            rows.keys().next_back().copied(),
        ) else {
            result.push(format!(
                "{title}<p><i>{}</i></p>",
                escape(&pack.label("Leeres Tabellenblatt"))
            ));
            continue;
        };
        let width = rows
            .values()
            .filter_map(|row| row.keys().next_back().copied())
            .max()
            .unwrap_or(0);
        let mut body = String::new();
        for line in first..=last {
            body.push_str("<tr>");
            for column in 1..=width {
                match rows.get(&line).and_then(|row| row.get(&column)) {
                    Some((text, numeric)) => body.push_str(&format!(
                        "<td{}>{}</td>",
                        if *numeric { " align=\"right\"" } else { "" },
                        escape(text)
                    )),
                    None => body.push_str("<td></td>"),
                }
            }
            body.push_str("</tr>");
        }
        let note = if cut {
            format!(
                "<p><i>{}</i></p>",
                escape(
                    &pack
                        .label("Gekürzt auf {0} Zeilen und {1} Spalten.")
                        .replace("{0}", &pack.rows.to_string())
                        .replace("{1}", &pack.columns.to_string())
                )
            )
        } else {
            String::new()
        };
        result.push(format!("{title}<table border=\"1\" cellspacing=\"0\" cellpadding=\"3\" style=\"font-size:{}px\">{body}</table>{note}", if width > 6 { 11 } else { 13 }));
    }
    if result.is_empty() {
        return Err("Arbeitsmappe ohne sichtbares Tabellenblatt.".into());
    }
    Ok(result)
}

// ---- PowerPoint ----

fn slide_text(body: Node, bullets: bool) -> String {
    let mut text = String::new();
    for paragraph in children(body, A, "p") {
        let properties = child(paragraph, A, "pPr");
        let mut line = String::new();
        for part in paragraph.children().filter(Node::is_element) {
            if is(part, A, "r") || is(part, A, "fld") {
                let mut piece = escape(
                    &children(part, A, "t")
                        .map(|t| t.text().unwrap_or(""))
                        .collect::<String>(),
                );
                if let Some(style) = child(part, A, "rPr").filter(|_| !piece.is_empty()) {
                    if style.attribute("b") == Some("1") {
                        piece = format!("<b>{piece}</b>");
                    }
                    if style.attribute("i") == Some("1") {
                        piece = format!("<i>{piece}</i>");
                    }
                    if style.attribute("u").unwrap_or("none") != "none" {
                        piece = format!("<u>{piece}</u>");
                    }
                }
                line.push_str(&piece);
            } else if is(part, A, "br") {
                line.push_str("<br>");
            }
        }
        if line.trim().is_empty() {
            continue;
        }
        let depth = properties
            .and_then(|p| p.attribute("lvl"))
            .filter(|level| digits(level))
            .and_then(|level| level.parse::<usize>().ok())
            .unwrap_or(0)
            .min(8);
        let marked = match properties {
            None => bullets,
            Some(p) => {
                child(p, A, "buNone").is_none()
                    && (bullets
                        || child(p, A, "buChar").is_some()
                        || child(p, A, "buAutoNum").is_some())
            }
        };
        text.push_str(&format!(
            "<p style=\"margin-left:{}px\">{}{line}</p>",
            20 * depth + if marked { 16 } else { 0 },
            if marked { "•&nbsp;" } else { "" }
        ));
    }
    text
}

/// Text with every tag replaced by a space, for a slide title.
fn untagged(html: &str) -> String {
    let mut out = String::new();
    let mut rest = html;
    while let Some(start) = rest.find('<') {
        match rest[start + 1..].find('>') {
            Some(end) if end > 0 => {
                out.push_str(&rest[..start]);
                out.push(' ');
                rest = &rest[start + end + 2..];
            }
            _ => {
                out.push_str(&rest[..=start]);
                rest = &rest[start + 1..];
            }
        }
    }
    out.push_str(rest);
    out.trim().to_string()
}

fn shapes(pack: &Pack, tree: Node, own: &HashMap<String, String>) -> (String, String) {
    let (mut title, mut content) = (String::new(), String::new());
    for shape in tree.children().filter(Node::is_element) {
        if is(shape, P, "sp") {
            let Some(body) = child(shape, P, "txBody") else {
                continue;
            };
            let holder = child(shape, P, "nvSpPr")
                .and_then(|n| child(n, P, "nvPr"))
                .and_then(|n| child(n, P, "ph"));
            let kind = holder.map(|h| h.attribute("type").unwrap_or("body"));
            if matches!(kind, Some("title" | "ctrTitle")) && title.is_empty() {
                title = untagged(&slide_text(body, false));
            } else if !matches!(kind, Some("sldNum" | "dt" | "ftr")) {
                content.push_str(&slide_text(body, matches!(kind, Some("body" | "obj"))));
            }
        } else if is(shape, P, "pic") {
            let (width, height) = emu(all(shape, A, "ext").next());
            if let Some(blip) = all(shape, A, "blip").next() {
                let name = blip
                    .attribute((R, "embed"))
                    .and_then(|id| own.get(id))
                    .map(String::as_str)
                    .unwrap_or("");
                content.push_str(&format!(
                    "<p>{}</p>",
                    pack.picture(name, width / 2.0, height / 2.0)
                ));
            }
        } else if is(shape, P, "graphicFrame") {
            for table in all(shape, A, "tbl") {
                content.push_str(
                    "<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\" width=\"100%\">",
                );
                for row in children(table, A, "tr") {
                    content.push_str("<tr>");
                    for cell in children(row, A, "tc") {
                        content.push_str(&format!(
                            "<td>{}</td>",
                            child(cell, A, "txBody")
                                .map(|body| slide_text(body, false))
                                .unwrap_or_default()
                        ));
                    }
                    content.push_str("</tr>");
                }
                content.push_str("</table>");
            }
        } else if is(shape, P, "grpSp") {
            let (inner, more) = shapes(pack, shape, own);
            if title.is_empty() {
                title = inner;
            }
            content.push_str(&more);
        }
    }
    (title, content)
}

fn slides(pack: &Pack) -> Outcome<Vec<String>> {
    let text = pack.part("ppt/presentation.xml")?;
    let presentation = parse(&text)?;
    let links = pack.relations("ppt/presentation.xml")?;
    let mut result = Vec::new();
    let order = child(presentation.root_element(), P, "sldIdLst");
    for (index, entry) in order
        .iter()
        .flat_map(|order| order.children().filter(Node::is_element))
        .enumerate()
    {
        let Some(name) = entry
            .attribute((R, "id"))
            .and_then(|id| links.get(id))
            .filter(|name| !name.is_empty())
        else {
            continue;
        };
        let text = pack.part(name)?;
        let slide = parse(&text)?;
        let own = pack.relations(name)?;
        let tree = child(slide.root_element(), P, "cSld").and_then(|c| child(c, P, "spTree"));
        let (title, content) = tree
            .map(|tree| shapes(pack, tree, &own))
            .unwrap_or_default();
        let heading = if title.is_empty() {
            String::new()
        } else {
            format!(" · {title}")
        };
        let content = if content.is_empty() {
            format!("<p><i>{}</i></p>", escape(&pack.label("Folie ohne Text")))
        } else {
            content
        };
        result.push(format!(
            "<h2>{} {}{heading}</h2>{content}",
            escape(&pack.label("Folie")),
            index + 1
        ));
    }
    if result.is_empty() {
        return Err("Präsentation ohne Folien.".into());
    }
    Ok(result)
}

// ---- OpenDocument ----

/// An OpenDocument length such as 5.2cm, in reading pixels.
fn length(value: Option<&str>) -> f64 {
    let value = value.unwrap_or("");
    for (unit, factor) in [
        ("cm", 37.8),
        ("mm", 3.78),
        ("in", 96.0),
        ("pt", 96.0 / 72.0),
        ("px", 1.0),
    ] {
        if let Some(number) = value.strip_suffix(unit)
            && !number.is_empty()
            && number.bytes().all(|b| b.is_ascii_digit() || b == b'.')
        {
            return number.parse::<f64>().map(|n| n * factor).unwrap_or(0.0);
        }
    }
    0.0
}

struct Open<'p> {
    pack: &'p Pack,
    marks: HashMap<String, Vec<&'static str>>,
}

impl Open<'_> {
    fn inline(&self, node: Node) -> String {
        let mut text = String::new();
        for part in node.children() {
            if part.is_text() {
                text.push_str(&escape(part.text().unwrap_or("")));
            } else if is(part, TEXT, "s") {
                text.push_str(
                    &"&nbsp;".repeat(
                        part.attribute((TEXT, "c"))
                            .and_then(|c| c.parse::<usize>().ok())
                            .unwrap_or(1)
                            .min(40),
                    ),
                );
            } else if is(part, TEXT, "tab") {
                text.push_str("&emsp;");
            } else if is(part, TEXT, "line-break") {
                text.push_str("<br>");
            } else if is(part, DRAW, "frame") {
                text.push_str(&self.frame(part));
            } else if is(part, TEXT, "span") || is(part, TEXT, "a") {
                let mut piece = self.inline(part);
                for mark in part
                    .attribute((TEXT, "style-name"))
                    .and_then(|name| self.marks.get(name))
                    .into_iter()
                    .flatten()
                {
                    piece = format!("<{mark}>{piece}</{mark}>");
                }
                text.push_str(&piece);
            }
        }
        text
    }

    fn frame(&self, node: Node) -> String {
        let mut result = String::new();
        for image in children(node, DRAW, "image") {
            let name = image
                .attribute((XLINK, "href"))
                .unwrap_or("")
                .trim_start_matches(['.', '/']);
            result.push_str(&self.pack.picture(
                name,
                length(node.attribute((SVG, "width"))),
                length(node.attribute((SVG, "height"))),
            ));
        }
        for text_box in children(node, DRAW, "text-box") {
            result.push_str(&self.blocks(text_box, 0));
        }
        result
    }

    fn table(&self, node: Node) -> String {
        let mut body = String::new();
        let mut lines = 0;
        for row in all(node, TABLE, "table-row") {
            let mut cells = String::new();
            let mut filled = false;
            for cell in children(row, TABLE, "table-cell") {
                let text = self.blocks(cell, 0);
                let repeat = cell
                    .attribute((TABLE, "number-columns-repeated"))
                    .filter(|r| digits(r))
                    .and_then(|r| r.parse::<usize>().ok())
                    .unwrap_or(1);
                filled |= !text.is_empty();
                if cells.matches("<td").count() + if text.is_empty() { 0 } else { repeat }
                    > self.pack.columns
                {
                    break;
                }
                let span = cell
                    .attribute((TABLE, "number-columns-spanned"))
                    .filter(|s| digits(s))
                    .and_then(|s| s.parse::<u64>().ok());
                let one = format!(
                    "<td{}>{text}</td>",
                    span.map(|s| format!(" colspan=\"{s}\""))
                        .unwrap_or_default()
                );
                cells.push_str(
                    &one.repeat(if !text.is_empty() || repeat <= self.pack.columns {
                        repeat
                    } else {
                        1
                    }),
                );
            }
            // Sheets are padded with repeated empty rows and cells down to their last line.
            if !filled {
                continue;
            }
            lines += 1;
            if lines > self.pack.rows {
                break;
            }
            let mut kept = cells.as_str();
            while let Some(shorter) = kept.strip_suffix("<td></td>") {
                kept = shorter;
            }
            body.push_str(&format!(
                "<tr>{}</tr>",
                if kept.is_empty() { "<td></td>" } else { kept }
            ));
        }
        if body.is_empty() {
            String::new()
        } else {
            format!("<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\">{body}</table>")
        }
    }

    fn blocks(&self, node: Node, depth: usize) -> String {
        let mut result = String::new();
        for part in node.children().filter(Node::is_element) {
            if is(part, TEXT, "h") {
                let level = part.attribute((TEXT, "outline-level")).unwrap_or("1");
                let level = if digits(level) {
                    level.parse::<u64>().unwrap_or(6).min(6)
                } else {
                    1
                };
                result.push_str(&format!("<h{level}>{}</h{level}>", self.inline(part)));
            } else if is(part, TEXT, "p") {
                let text = self.inline(part);
                if !text.trim().is_empty() {
                    result.push_str(&format!(
                        "<p style=\"margin-left:{}px\">{}{text}</p>",
                        20 * depth,
                        if depth > 0 { "•&nbsp;" } else { "" }
                    ));
                }
            } else if is(part, TEXT, "list") {
                for item in children(part, TEXT, "list-item") {
                    result.push_str(&self.blocks(item, (depth + 1).min(8)));
                }
            } else if is(part, TABLE, "table") {
                result.push_str(&self.table(part));
            } else if is(part, DRAW, "frame") {
                result.push_str(&self.frame(part));
            } else if is(part, TEXT, "section")
                || ["g", "custom-shape", "rect"]
                    .iter()
                    .any(|name| is(part, DRAW, name))
            {
                result.push_str(&self.blocks(part, depth));
            }
        }
        result
    }
}

fn open_document(pack: &Pack, kind: &str) -> Outcome<Vec<String>> {
    let text = pack.part("content.xml")?;
    let content = parse(&text)?;
    let mut reader = Open {
        pack,
        marks: HashMap::new(),
    };
    for style in all(content.root_element(), STYLE, "style") {
        if let (Some(properties), Some(name)) = (
            child(style, STYLE, "text-properties"),
            style.attribute((STYLE, "name")),
        ) {
            let mut marks = Vec::new();
            if properties.attribute((FO, "font-weight")) == Some("bold") {
                marks.push("b");
            }
            if properties.attribute((FO, "font-style")) == Some("italic") {
                marks.push("i");
            }
            if properties
                .attribute((STYLE, "text-underline-style"))
                .unwrap_or("none")
                != "none"
            {
                marks.push("u");
            }
            reader.marks.insert(name.to_string(), marks);
        }
    }
    let empty = || "OpenDocument-Datei ohne Inhalt.".to_string();
    let root = child(content.root_element(), OFFICE, "body")
        .and_then(|body| body.children().find(Node::is_element))
        .ok_or_else(empty)?;
    let result: Vec<String> = match kind {
        ".ods" => children(root, TABLE, "table")
            .map(|sheet| {
                let table = reader.table(sheet);
                let body = if table.is_empty() {
                    format!(
                        "<p><i>{}</i></p>",
                        escape(&pack.label("Leeres Tabellenblatt"))
                    )
                } else {
                    table
                };
                format!(
                    "<h2>{}</h2>{body}",
                    escape(sheet.attribute((TABLE, "name")).unwrap_or(""))
                )
            })
            .collect(),
        ".odp" => children(root, DRAW, "page")
            .enumerate()
            .map(|(index, page)| {
                let blocks = reader.blocks(page, 0);
                let body = if blocks.is_empty() {
                    format!("<p><i>{}</i></p>", escape(&pack.label("Folie ohne Text")))
                } else {
                    blocks
                };
                format!(
                    "<h2>{} {}</h2>{body}",
                    escape(&pack.label("Folie")),
                    index + 1
                )
            })
            .collect(),
        _ => vec![reader.blocks(root, 0)],
    };
    if result.is_empty() {
        return Err(empty());
    }
    Ok(result)
}

fn parts(pack: &Pack, kind: &str) -> Outcome<Vec<String>> {
    match kind {
        ".docx" | ".docm" => word(pack),
        ".xlsx" | ".xlsm" => spreadsheet(pack),
        ".pptx" | ".pptm" => slides(pack),
        ".odt" | ".ods" | ".odp" => open_document(pack, kind),
        _ => Err("Geschützte oder beschädigte Office-Datei.".into()),
    }
}

/// A section as plain text: one line per paragraph, heading and table row, cells apart by a tab.
fn plain(html: &str) -> String {
    let mut out = String::new();
    let mut rest = html;
    while let Some(start) = rest.find('<') {
        out.push_str(&rest[..start]);
        let Some(end) = rest[start..].find('>') else {
            break;
        };
        match rest[start + 1..start + end]
            .split(' ')
            .next()
            .unwrap_or_default()
        {
            "/p" | "/h2" | "/tr" | "br" => out.push('\n'),
            "/td" => out.push('\t'),
            _ => {}
        }
        rest = &rest[start + end + 1..];
    }
    out.push_str(rest);
    // `&amp;` last, so that an escaped entity stays text.
    out.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
}

/// The whole text for a search, one form-feed separated page per sheet or slide: every sheet row and column, hidden sheets, and Word's footnotes and
/// endnotes, which the reading view leaves out. `kind` is the lower-case suffix, since a searched file may be
/// opened through a descriptor without a name.
pub fn text(path: &Path, kind: &str) -> Outcome<String> {
    let mut pack = Pack::open(path, &HashMap::new())?;
    (pack.rows, pack.columns, pack.hidden) = (usize::MAX, usize::MAX, true);
    // A form feed between sheets and slides, as between PDF pages, so that a hit names its page.
    let sections: Vec<String> = parts(&pack, kind)?.iter().map(|part| plain(part)).collect();
    let mut out = vec![sections.join("\u{c}")];
    for name in ["word/footnotes.xml", "word/endnotes.xml"] {
        if matches!(kind, ".docx" | ".docm") && pack.names.contains(name) {
            let notes = pack.part(name)?;
            for paragraph in all(parse(&notes)?.root_element(), W, "p") {
                out.push(
                    all(paragraph, W, "t")
                        .filter_map(|run| run.text())
                        .collect(),
                );
            }
        }
    }
    Ok(out.join("\n"))
}

/// Title and one HTML section per document, sheet or slide. `labels` translates the few words the
/// reader writes itself; a missing entry leaves the German word.
pub fn read(path: &Path, labels: &HashMap<String, String>) -> Outcome<Reading> {
    let pack = Pack::open(path, labels)?;
    let kind = path
        .extension()
        .map(|e| format!(".{}", e.to_string_lossy().to_lowercase()))
        .unwrap_or_default();
    let parts = parts(&pack, &kind)?;
    let mut title = String::new();
    for name in ["docProps/core.xml", "meta.xml"] {
        if pack.names.contains(name) {
            let text = pack.part(name)?;
            let found = all(parse(&text)?.root_element(), DC, "title")
                .next()
                .and_then(|node| node.text().map(|t| t.trim().to_string()))
                .filter(|t| !t.is_empty());
            if let Some(found) = found {
                title = found.chars().take(200).collect();
                break;
            }
        }
    }
    let mut sections = Vec::new();
    let mut size = 0;
    for part in parts {
        size += part.chars().count();
        if size > MAX_HTML {
            sections.push(format!(
                "<p><i>{}</i></p>",
                escape(
                    &pack.label(
                        "Das Dokument ist zu groß für die Leseansicht und wurde hier gekürzt."
                    )
                )
            ));
            break;
        }
        sections.push(part);
    }
    Ok(Reading { title, sections })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_follow_the_ten_figure_general_format() {
        for (value, text) in [
            ("3.0", "3"),
            ("1234.5", "1234,5"),
            ("0.1", "0,1"),
            ("1234.5600000001", "1234,56"),
            ("0.000012345", "1,2345e-05"),
            ("1e16", "1e+16"),
            ("-2.5", "-2,5"),
            ("12.5", "12,5"),
            ("123456789012.345", "1,23456789e+11"),
            ("0.30000000000000004", "0,3"),
        ] {
            assert_eq!(cell_text(value).as_deref(), Some(text), "{value}");
        }
        assert_eq!(cell_text("abc"), None);
    }

    #[test]
    fn serial_days_become_dates() {
        assert_eq!(moment(-25_569, 46000.0), Some((2025, 12, 9, 0, 0)));
        assert_eq!(moment(-25_569, 0.75), Some((1899, 12, 30, 18, 0)));
        assert_eq!(moment(-24_107, 0.0), Some((1904, 1, 1, 0, 0)));
        assert_eq!(moment(-25_569, 1e12), None);
    }

    #[test]
    fn paths_formats_and_titles_are_cleaned_like_the_python_reader() {
        assert_eq!(normal("ppt/slides/../media/a.png"), "ppt/media/a.png");
        assert_eq!(normal("word/./media/b.png"), "word/media/b.png");
        assert_eq!(pattern("[$-407]d.m.yyyy\\ \"h\""), "d.m.yyyy");
        assert_eq!(pattern("0.00\"%\""), "0.00");
        assert_eq!(
            untagged("<p style=\"x\"><b>Strategie</b> 2027</p>"),
            "Strategie  2027"
        );
        assert_eq!(escape("a<b>&\"'"), "a&lt;b&gt;&amp;&quot;&#x27;");
        assert_eq!(length(Some("5cm")), 189.0);
        assert_eq!(
            plain(
                "<h2>A &amp;amp; B</h2><table border=\"1\"><tr><td>1</td><td>&lt;2&gt;</td></tr></table><p>x<br>y</p>"
            ),
            "A &amp; B\n1\t<2>\t\nx\ny\n"
        );
    }
}

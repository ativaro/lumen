//! PDF translation: the text blocks of a PDF, and a new PDF with translated text set in their place.
//! Lumen's own code; shaping is `rustybuzz`, line break opportunities are `unicode-linebreak`.
//! The source file is never changed.
use std::collections::{HashMap, HashSet};
use std::io::Read;
use std::path::Path;
use std::rc::Rc;

use sha2::{Digest, Sha256};
use unicode_linebreak::BreakOpportunity;

use crate::json::Json;
use crate::pdf::{Dict, Document, Error, Outcome, Ref, Syntax, Value};
use crate::text::{Matrix, Page, Span, font_file, format_mark, right_to_left};
use crate::write::{Writer, packed, publish, serialize};

const MAX_FILE: u64 = 50 * 1024 * 1024;
const MAX_CHARS: usize = 100_000;
const SMALLEST: f64 = 0.6;

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

#[derive(Debug, Clone, PartialEq)]
pub struct Style {
    pub size: f64,
    pub colour: u32,
    pub bold: bool,
    pub italic: bool,
}

/// A block of text to translate: its page, its box (left, top, right, bottom, upright and counted from the
/// MediaBox top), its pieces with their styles, and the angle it is turned by.
#[derive(Debug, Clone, PartialEq)]
pub struct Segment {
    pub page: usize,
    pub rect: [f64; 4],
    pub parts: Vec<String>,
    pub styles: Vec<Style>,
    pub angle: f64,
}

pub struct Inspection {
    pub fingerprint: String,
    pub pages: usize,
    pub segments: Vec<Segment>,
    pub characters: usize,
}

/// SHA-256 of the file, which may not be larger than 50 MiB.
pub fn fingerprint(path: &Path) -> Outcome<String> {
    let failed = || Error::Pdf("Bitte eine PDF-Datei auswählen.".into());
    let mut file = std::fs::File::open(path).map_err(|_| failed())?;
    let (mut digest, mut buffer, mut total) = (Sha256::new(), vec![0u8; 1 << 20], 0u64);
    loop {
        let read = file.read(&mut buffer).map_err(|_| failed())?;
        if read == 0 {
            break;
        }
        total += read as u64;
        if total > MAX_FILE {
            return bad("PDF ist größer als 50 MiB.");
        }
        digest.update(&buffer[..read]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

/// Neighbouring spans on one line become one block; a wider gap between them is a space.
fn blocks(spans: &[Span], page: usize) -> Vec<Segment> {
    let mut groups: Vec<Segment> = Vec::new();
    for span in spans {
        if span.text.trim().is_empty() {
            continue;
        }
        let (left, top) = (span.rect.x, span.rect.y);
        let (right, bottom) = (left + span.rect.w, top + span.rect.h);
        let style = Style {
            size: span.size,
            colour: span.colour,
            bold: span.bold,
            italic: span.italic,
        };
        if let Some(group) = groups.last_mut() {
            let last = group.styles.last().map_or(0.0, |style| style.size);
            let gap = left - group.rect[2];
            if group.angle == span.angle
                && (group.rect[1] - top).abs() < style.size.max(last) * 0.4
                && (-0.5..=style.size * 2.0).contains(&gap)
            {
                let space = if gap > style.size * 0.15 { " " } else { "" };
                group.parts.push(format!("{space}{}", span.text));
                group.styles.push(style);
                group.rect = [
                    group.rect[0].min(left),
                    group.rect[1].min(top),
                    group.rect[2].max(right),
                    group.rect[3].max(bottom),
                ];
                continue;
            }
        }
        groups.push(Segment {
            page,
            rect: [left, top, right, bottom],
            parts: vec![span.text.clone()],
            styles: vec![style],
            angle: span.angle,
        });
    }
    groups
}

/// The blocks of a PDF that can be translated, or why it cannot be.
pub fn inspect(path: &Path) -> Outcome<Inspection> {
    let pdf = path
        .extension()
        .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"));
    if !pdf || !path.is_file() {
        return bad("Bitte eine PDF-Datei auswählen.");
    }
    let stamp = fingerprint(path)?;
    let document = Document::open(path, "")?;
    if document.encrypted() {
        return bad("Die PDF ist verschlüsselt. Bitte zuerst eine entsperrte Kopie erstellen.");
    }
    let present = |key: &str| document.catalog.get(key).is_some_and(Value::truthy);
    if present("AcroForm") || present("Perms") {
        return bad(
            "Formulare und signierte PDFs werden nicht verändert. Bitte eine normale PDF-Kopie verwenden.",
        );
    }
    if !(1..=100).contains(&document.pages.len()) {
        return bad("Bitte eine PDF mit 1 bis 100 Seiten verwenden.");
    }
    let (mut segments, mut total) = (Vec::new(), 0);
    for (index, attrs) in document.pages.iter().enumerate() {
        let annotations = document.resolve(attrs.get("Annots").unwrap_or(&Value::Null))?;
        for annotation in annotations.array().map(|a| a.to_vec()).unwrap_or_default() {
            let annotation = document.resolve(&annotation)?;
            let entries = annotation.dict();
            let link =
                entries.is_some_and(|e| e.get("Subtype").and_then(Value::name) == Some("Link"));
            if !link || entries.is_some_and(|e| e.get("AP").is_some_and(Value::truthy)) {
                return bad(
                    "PDF-Anmerkungen zuerst in einer separaten Kopie entfernen, damit die Übersetzung keine Markierungen verändert.",
                );
            }
        }
        let (spans, images) = Page::spans(&document, index)?;
        let groups = blocks(&spans, index);
        if groups.is_empty() && images > 0 {
            return bad(
                "Diese PDF enthält Bildseiten ohne Textschicht. Zuerst OCR ausführen; Bildtext wird nicht automatisch übersetzt.",
            );
        }
        for group in groups {
            total += group.parts.iter().map(|p| p.chars().count()).sum::<usize>();
            if total > MAX_CHARS || segments.len() >= 1500 {
                return bad("PDF enthält zu viel Text. Bitte in kleinere Dokumente teilen.");
            }
            segments.push(group);
        }
    }
    if segments.is_empty() {
        return bad("Keine Textschicht gefunden. Bitte zuerst OCR ausführen.");
    }
    if fingerprint(path)? != stamp {
        return bad("Die Quelldatei wurde während des Lesens verändert.");
    }
    Ok(Inspection {
        fingerprint: stamp,
        pages: document.pages.len(),
        segments,
        characters: total,
    })
}

/// A PDF number as the writer spells it.
fn number(value: f64) -> String {
    let mut out = Vec::new();
    let _ = serialize(&mut out, &Value::Real(value), 0);
    String::from_utf8(out).unwrap_or_default()
}

fn quoted(text: &str) -> String {
    let mut out = String::from("\"");
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// The inspection as JSON, in the shape `translate_pdf.py` hands on.
pub fn inspection_json(path: &Path, found: &Inspection) -> String {
    let segments: Vec<String> = found
        .segments
        .iter()
        .enumerate()
        .map(|(id, s)| {
            let styles: Vec<String> = s
                .styles
                .iter()
                .map(|t| {
                    format!(
                        "{{\"size\": {}, \"color\": {}, \"bold\": {}, \"italic\": {}}}",
                        t.size, t.colour, t.bold, t.italic
                    )
                })
                .collect();
            format!(
                "{{\"id\": \"{id}\", \"page\": {}, \"rect\": [{}], \"parts\": [{}], \"styles\": [{}], \"angle\": {}}}",
                s.page,
                s.rect.map(|v| v.to_string()).join(", "),
                s.parts.iter().map(|p| quoted(p)).collect::<Vec<_>>().join(", "),
                styles.join(", "),
                s.angle
            )
        })
        .collect();
    format!(
        "{{\"path\": {}, \"fingerprint\": \"{}\", \"pages\": {}, \"segments\": [{}], \"characters\": {}}}",
        quoted(&path.to_string_lossy()),
        found.fingerprint,
        found.pages,
        segments.join(", "),
        found.characters
    )
}

/// Whether the blocks a caller sends back are the ones found now.
fn same_segments(given: &Json, found: &[Segment]) -> bool {
    let Some(given) = given.list() else {
        return false;
    };
    let close = |json: Option<&Json>, value: f64| json.and_then(Json::number) == Some(value);
    given.len() == found.len()
        && given.iter().zip(found).enumerate().all(|(id, (g, s))| {
            let parts = g.get("parts").and_then(Json::list).unwrap_or(&[]);
            let styles = g.get("styles").and_then(Json::list).unwrap_or(&[]);
            let rect = g.get("rect").and_then(Json::list).unwrap_or(&[]);
            g.get("id").and_then(Json::text) == Some(id.to_string().as_str())
                && g.get("page").and_then(Json::whole) == Some(s.page as i64)
                && rect.len() == 4
                && rect.iter().zip(s.rect).all(|(r, v)| close(Some(r), v))
                && close(g.get("angle"), s.angle)
                && parts.len() == s.parts.len()
                && parts
                    .iter()
                    .zip(&s.parts)
                    .all(|(p, q)| p.text() == Some(q.as_str()))
                && styles.len() == s.styles.len()
                && styles.iter().zip(&s.styles).all(|(j, t)| {
                    close(j.get("size"), t.size)
                        && j.get("color").and_then(Json::whole) == Some(i64::from(t.colour))
                        && j.get("bold") == Some(&Json::Bool(t.bold))
                        && j.get("italic") == Some(&Json::Bool(t.italic))
                })
        })
}

/// The content without the operators that show text; the text state stays as it was.
fn without_text(data: &[u8]) -> Outcome<Vec<u8>> {
    let mut syntax = Syntax::new(data, 0);
    let (mut start, mut operands, mut out) = (0, Vec::new(), Vec::new());
    loop {
        syntax.skip();
        if syntax.pos >= data.len() {
            break;
        }
        let value = syntax.value()?;
        let Value::Operator(operator) = &value else {
            operands.push(value);
            continue;
        };
        match &**operator {
            "Tj" | "TJ" => {}
            "'" => out.extend_from_slice(b"T*\n"),
            "\"" => {
                if operands.len() != 3 {
                    return bad("Ungültiger PDF-Textoperator.");
                }
                serialize(&mut out, &operands[0], 0)?;
                out.extend_from_slice(b" Tw ");
                serialize(&mut out, &operands[1], 0)?;
                out.extend_from_slice(b" Tc T*\n");
            }
            _ => {
                out.extend_from_slice(&data[start..syntax.pos]);
                out.push(b'\n');
            }
        }
        start = syntax.pos;
        operands.clear();
    }
    Ok(out)
}

/// The fonts the translation may use, in order of preference: regular, bold, italic, bold italic.
const FAMILIES: [[&str; 4]; 4] = [
    [
        "LiberationSans-Regular.ttf",
        "LiberationSans-Bold.ttf",
        "LiberationSans-Italic.ttf",
        "LiberationSans-BoldItalic.ttf",
    ],
    [
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    ],
    [
        "NotoSans-Regular.ttf",
        "NotoSans-Bold.ttf",
        "NotoSans-Italic.ttf",
        "NotoSans-BoldItalic.ttf",
    ],
    ["NotoSansMath-Regular.ttf"; 4],
];

fn style_index(style: &Style) -> usize {
    usize::from(style.bold) + 2 * usize::from(style.italic)
}

/// A font as it is embedded: its PDF objects and the glyphs used so far, each with its code.
struct Embedded {
    name: String,
    parent: Ref,
    child: Ref,
    codes: HashMap<(u16, String), u16>,
    /// Glyph, text and width in thousandths of the size, by code from 1.
    mapping: Vec<(u16, String, f64)>,
}

/// One shaped glyph in the block, its position in points before the line is placed.
#[derive(Clone)]
struct Glyph {
    gid: u16,
    /// Byte index of its cluster in the block text.
    cluster: usize,
    advance: f64,
    dx: f64,
    dy: f64,
    part: usize,
}

/// A set block: its content stream, the fonts it uses by resource name, and the scale it took.
pub type Set = (Vec<u8>, Vec<(String, Ref)>, f64);

/// A block set smaller than its original: page from 1, block id, scale.
pub type Reduced = (usize, String, f64);

pub struct Typesetter {
    files: HashMap<&'static str, Option<Rc<Vec<u8>>>>,
    embedded: HashMap<&'static str, Embedded>,
}

impl Default for Typesetter {
    fn default() -> Self {
        Typesetter::new()
    }
}

impl Typesetter {
    pub fn new() -> Typesetter {
        Typesetter {
            files: HashMap::new(),
            embedded: HashMap::new(),
        }
    }

    fn file(&mut self, name: &'static str) -> Option<Rc<Vec<u8>>> {
        self.files
            .entry(name)
            .or_insert_with(|| font_file(name).map(Rc::new))
            .clone()
    }

    /// The first family whose faces for every style hold every character.
    fn family(&mut self, text: &str, styles: &[Style]) -> Outcome<[&'static str; 4]> {
        let characters: HashSet<char> = text
            .chars()
            .filter(|c| *c != '\u{2028}' && !c.is_control() && !format_mark(*c))
            .collect();
        'family: for family in FAMILIES {
            for style in styles {
                let Some(data) = self.file(family[style_index(style)]) else {
                    continue 'family;
                };
                let Ok(face) = ttf_parser::Face::parse(&data, 0) else {
                    continue 'family;
                };
                if characters.iter().any(|c| face.glyph_index(*c).is_none()) {
                    continue 'family;
                }
            }
            return Ok(family);
        }
        bad("Für diesen Text fehlt eine vollständig passende einbettbare Schrift.")
    }

    fn embed(
        &mut self,
        writer: &mut Writer,
        file: &'static str,
        bold: bool,
        italic: bool,
    ) -> Outcome<()> {
        if self.embedded.contains_key(file) {
            return Ok(());
        }
        let data = self.file(file).ok_or_else(|| {
            Error::Pdf("Für diesen Text fehlt eine einbettbare statische TrueType-Schrift.".into())
        })?;
        let program = truetype(&data)?;
        let face = ttf_parser::Face::parse(&data, 0).map_err(|_| {
            Error::Pdf("Für diesen Text fehlt eine einbettbare statische TrueType-Schrift.".into())
        })?;
        let scale = 1000.0 / f64::from(face.units_per_em());
        let name = format!(
            "LumenFont{}{}{}",
            self.embedded.len() + 1,
            if bold { "-Bold" } else { "" },
            if italic { "-Italic" } else { "" }
        );
        let n = |v: f64| Value::Real(v);
        let font_file = writer.stream(
            &program,
            Dict::from_iter([("Length1".to_string(), Value::Int(program.len() as i64))]),
        )?;
        let descriptor = writer.add(Value::Dict(Rc::new(Dict::from_iter([
            ("Type".to_string(), Value::Name("FontDescriptor".into())),
            ("FontName".to_string(), Value::Name(name.clone().into())),
            ("Flags".to_string(), Value::Int(4)),
            (
                "FontBBox".to_string(),
                Value::Array(Rc::new([-2000, -2000, 4000, 4000].map(Value::Int).to_vec())),
            ),
            (
                "ItalicAngle".to_string(),
                Value::Int(if italic { -12 } else { 0 }),
            ),
            ("Ascent".to_string(), n(f64::from(face.ascender()) * scale)),
            (
                "Descent".to_string(),
                n(f64::from(face.descender()) * scale),
            ),
            (
                "CapHeight".to_string(),
                n(f64::from(face.capital_height().unwrap_or(face.ascender())) * scale),
            ),
            ("StemV".to_string(), Value::Int(80)),
            ("FontFile2".to_string(), Value::Ref(font_file)),
        ]))))?;
        let child = writer.add(Value::Dict(Rc::new(Dict::from_iter([
            ("Type".to_string(), Value::Name("Font".into())),
            ("Subtype".to_string(), Value::Name("CIDFontType2".into())),
            ("BaseFont".to_string(), Value::Name(name.clone().into())),
            (
                "CIDSystemInfo".to_string(),
                Value::Dict(Rc::new(Dict::from_iter([
                    (
                        "Registry".to_string(),
                        Value::Text(Rc::new(b"Adobe".to_vec())),
                    ),
                    (
                        "Ordering".to_string(),
                        Value::Text(Rc::new(b"Identity".to_vec())),
                    ),
                    ("Supplement".to_string(), Value::Int(0)),
                ]))),
            ),
            ("FontDescriptor".to_string(), Value::Ref(descriptor)),
            ("DW".to_string(), Value::Int(1000)),
        ]))))?;
        let parent = writer.add(Value::Dict(Rc::new(Dict::from_iter([
            ("Type".to_string(), Value::Name("Font".into())),
            ("Subtype".to_string(), Value::Name("Type0".into())),
            ("BaseFont".to_string(), Value::Name(name.clone().into())),
            ("Encoding".to_string(), Value::Name("Identity-H".into())),
            (
                "DescendantFonts".to_string(),
                Value::Array(Rc::new(vec![Value::Ref(child)])),
            ),
        ]))))?;
        self.embedded.insert(
            file,
            Embedded {
                name,
                parent,
                child,
                codes: HashMap::new(),
                mapping: Vec::new(),
            },
        );
        Ok(())
    }

    /// Writes the fonts' glyph maps, widths and text maps once every block is set.
    pub fn finish(&mut self, writer: &mut Writer) -> Outcome<()> {
        for font in self.embedded.values() {
            let mut gidmap = vec![0u8, 0];
            for (gid, ..) in &font.mapping {
                gidmap.extend_from_slice(&gid.to_be_bytes());
            }
            let gidmap = writer.stream(&gidmap, Dict::new())?;
            let widths = Value::Array(Rc::new(vec![
                Value::Int(1),
                Value::Array(Rc::new(
                    font.mapping.iter().map(|m| Value::Real(m.2)).collect(),
                )),
            ]));
            let Value::Dict(child) = writer.objects[font.child.number as usize - 1].clone() else {
                return bad("PDF-Exportprüfung fehlgeschlagen.");
            };
            let mut child = (*child).clone();
            child.insert("CIDToGIDMap".into(), Value::Ref(gidmap));
            child.insert("W".into(), widths);
            writer.put(font.child, Value::Dict(Rc::new(child)));
            let mut cmap = b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /LumenUnicode def /CMapType 2 def 1 begincodespacerange <0000> <ffff> endcodespacerange\n".to_vec();
            for (batch, entries) in font.mapping.chunks(100).enumerate() {
                cmap.extend_from_slice(format!("{} beginbfchar\n", entries.len()).as_bytes());
                for (offset, (_, text, _)) in entries.iter().enumerate() {
                    let code = batch * 100 + offset + 1;
                    let target: String = text.encode_utf16().map(|u| format!("{u:04x}")).collect();
                    cmap.extend_from_slice(format!("<{code:04x}> <{target}>\n").as_bytes());
                }
                cmap.extend_from_slice(b"endbfchar\n");
            }
            cmap.extend_from_slice(
                b"endcmap CMapName currentdict /CMap defineresource pop end end",
            );
            let unicode = writer.stream(&cmap, Dict::new())?;
            let Value::Dict(parent) = writer.objects[font.parent.number as usize - 1].clone()
            else {
                return bad("PDF-Exportprüfung fehlgeschlagen.");
            };
            let mut parent = (*parent).clone();
            parent.insert("ToUnicode".into(), Value::Ref(unicode));
            writer.put(font.parent, Value::Dict(Rc::new(parent)));
        }
        Ok(())
    }

    /// Sets `parts` in their styles into the top-left box `rect` of a page whose MediaBox ends at `top`, shrinking
    /// the text down to 60 % if needed. Returns the content stream, the fonts it uses and the scale it took.
    pub fn block(
        &mut self,
        writer: &mut Writer,
        top: f64,
        rect: [f64; 4],
        parts: &[String],
        styles: &[Style],
        angle: f64,
    ) -> Outcome<Set> {
        if !(rect[2] > rect[0] && rect[3] > rect[1]) {
            return bad("Leeres PDF-Rechteck.");
        }
        let (x0, y0, width, height) = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]);
        let text: String = parts.concat().replace('\n', "\u{2028}");
        if text.is_empty() {
            return Ok((Vec::new(), Vec::new(), 1.0));
        }
        if text.chars().any(right_to_left) {
            return bad(
                "Rechts-nach-links-Text kann noch nicht zuverlässig in PDF geschrieben werden.",
            );
        }
        if text.chars().count() > 100_000 || parts.len() != styles.len() || !angle.is_finite() {
            return bad("Ungültiger PDF-Textauftrag.");
        }
        let family = self.family(&text, styles)?;
        // Each part is shaped once in units of the em; the scale only multiplies.
        let mut shaped: Vec<Glyph> = Vec::new();
        let mut metrics = Vec::new();
        let mut at = 0;
        for (index, part) in parts.iter().enumerate() {
            // Control characters such as tabs are set as spaces; the text behind them keeps them.
            let part: String = part
                .replace('\n', "\u{2028}")
                .chars()
                .map(|c| if c.is_ascii_control() { ' ' } else { c })
                .collect();
            let data = self
                .file(family[style_index(&styles[index])])
                .ok_or_else(|| {
                    Error::Pdf(
                        "Für diesen Text fehlt eine vollständig passende einbettbare Schrift."
                            .into(),
                    )
                })?;
            let face = rustybuzz::Face::from_slice(&data, 0).ok_or_else(|| {
                Error::Pdf(
                    "Für diesen Text fehlt eine einbettbare statische TrueType-Schrift.".into(),
                )
            })?;
            let em = f64::from(face.units_per_em());
            metrics.push((
                f64::from(face.ascender()) / em,
                -f64::from(face.descender()) / em,
            ));
            if !part.is_empty() {
                let mut buffer = rustybuzz::UnicodeBuffer::new();
                buffer.push_str(&part);
                buffer.guess_segment_properties();
                buffer.set_direction(rustybuzz::Direction::LeftToRight);
                let output = rustybuzz::shape(&face, &[], buffer);
                for (info, position) in output.glyph_infos().iter().zip(output.glyph_positions()) {
                    shaped.push(Glyph {
                        gid: info.glyph_id as u16,
                        cluster: at + info.cluster as usize,
                        advance: f64::from(position.x_advance) / em,
                        dx: f64::from(position.x_offset) / em,
                        dy: f64::from(position.y_offset) / em,
                        part: index,
                    });
                }
            }
            at += part.len();
        }
        let breaks: Vec<(usize, BreakOpportunity)> = unicode_linebreak::linebreaks(&text).collect();
        let char_at = |byte: usize| text[byte..].chars().next().unwrap_or(' ');
        // Lines as ranges of glyphs, and each glyph's position, at the largest size that fits.
        let mut chosen = None;
        for step in 0..=20 {
            let scale = 1.0 - (1.0 - SMALLEST) * f64::from(step) / 20.0;
            let size = |part: usize| (styles[part].size * scale).max(0.5);
            if let Some(placed) =
                lay_out(&shaped, &breaks, &char_at, &size, &metrics, width, height)
            {
                chosen = Some((scale, placed));
                break;
            }
        }
        let Some((scale, placed)) = chosen else {
            return bad(
                "Übersetzung passt nicht in den ursprünglichen Textbereich. Bitte kürzer formulieren lassen.",
            );
        };
        let size = |part: usize| (styles[part].size * scale).max(0.5);
        // The text of a glyph runs from its cluster to the next drawn cluster.
        let mut order: Vec<usize> = (0..shaped.len())
            .filter(|i| char_at(shaped[*i].cluster) != '\u{2028}')
            .collect();
        order.sort_by_key(|i| shaped[*i].cluster);
        let mut clusters: Vec<usize> = order.iter().map(|i| shaped[*i].cluster).collect();
        clusters.dedup();
        clusters.push(text.len());
        let mut fonts_used = Vec::new();
        let mut content = Vec::new();
        let mut seen = HashSet::new();
        for index in order {
            let glyph = &shaped[index];
            let (x, y) = placed[index];
            let (x, y) = (x0 + x, top - y0 - y);
            let style = &styles[glyph.part];
            let rgb = [16, 8, 0].map(|shift| f64::from(style.colour >> shift & 255) / 255.0);
            let colour = rgb.map(number).join(" ");
            let file = family[style_index(style)];
            let value = if seen.insert(glyph.cluster) {
                let next = clusters[clusters.partition_point(|c| *c <= glyph.cluster)];
                text[glyph.cluster..next].replace('\u{2028}', "\n")
            } else {
                String::new()
            };
            let data = self
                .file(file)
                .ok_or_else(|| Error::Pdf("PDF-Exportprüfung fehlgeschlagen.".into()))?;
            if value.is_empty() {
                // Further glyphs of one cluster are drawn as outlines; only the first carries the text.
                let face = ttf_parser::Face::parse(&data, 0)
                    .map_err(|_| Error::Pdf("PDF-Exportprüfung fehlgeschlagen.".into()))?;
                let mut path = Outline {
                    out: String::new(),
                    scale: size(glyph.part) / f64::from(face.units_per_em()),
                    last: (0.0, 0.0),
                };
                face.outline_glyph(ttf_parser::GlyphId(glyph.gid), &mut path);
                content.extend_from_slice(
                    format!(
                        "q {colour} rg 1 0 0 1 {} {} cm {}f Q\n",
                        number(x),
                        number(y),
                        path.out
                    )
                    .as_bytes(),
                );
                continue;
            }
            if glyph.gid == 0 && !value.trim().is_empty() {
                return bad("In den installierten Schriften fehlt ein Zeichen der Übersetzung.");
            }
            self.embed(writer, file, style.bold, style.italic)?;
            let face = ttf_parser::Face::parse(&data, 0)
                .map_err(|_| Error::Pdf("PDF-Exportprüfung fehlgeschlagen.".into()))?;
            let width = f64::from(
                face.glyph_hor_advance(ttf_parser::GlyphId(glyph.gid))
                    .unwrap_or(0),
            ) * 1000.0
                / f64::from(face.units_per_em());
            let font = self
                .embedded
                .get_mut(file)
                .ok_or_else(|| Error::Pdf("PDF-Exportprüfung fehlgeschlagen.".into()))?;
            let code = match font.codes.get(&(glyph.gid, value.clone())) {
                Some(code) => *code,
                None => {
                    if font.mapping.len() >= 65535 {
                        return bad("Zu viele Schriftzeichen im PDF-Export.");
                    }
                    font.mapping.push((glyph.gid, value.clone(), width));
                    let code = font.mapping.len() as u16;
                    font.codes.insert((glyph.gid, value), code);
                    code
                }
            };
            if !fonts_used.iter().any(|(name, _)| *name == font.name) {
                fonts_used.push((font.name.clone(), font.parent));
            }
            content.extend_from_slice(
                format!(
                    "q BT 0 Tc 0 Tw 100 Tz 0 Ts 0 Tr /{} {} Tf {colour} rg 1 0 0 1 {} {} Tm <{code:04x}> Tj ET Q\n",
                    font.name,
                    number(size(glyph.part)),
                    number(x),
                    number(y)
                )
                .as_bytes(),
            );
        }
        if angle != 0.0 {
            let flip = Matrix::new(&[1.0, 0.0, 0.0, -1.0, 0.0, top]);
            let turn = flip.then(Matrix::rotation(angle)).then(flip);
            let mut turned = format!(
                "q {} cm\n",
                [turn.m11, turn.m12, turn.m21, turn.m22, turn.dx, turn.dy]
                    .map(number)
                    .join(" ")
            )
            .into_bytes();
            turned.extend_from_slice(&content);
            turned.extend_from_slice(b"Q\n");
            content = turned;
        }
        Ok((content, fonts_used, scale))
    }
}

/// Positions of every glyph (x and baseline y from the box's top left), or None when the text does not fit.
/// Lines break greedily at Unicode break opportunities, anywhere inside a word wider than the box.
fn lay_out(
    glyphs: &[Glyph],
    breaks: &[(usize, BreakOpportunity)],
    char_at: &dyn Fn(usize) -> char,
    size: &dyn Fn(usize) -> f64,
    metrics: &[(f64, f64)],
    width: f64,
    height: f64,
) -> Option<Vec<(f64, f64)>> {
    let advance = |g: &Glyph| g.advance * size(g.part);
    let metric = |part: usize| (metrics[part].0 * size(part), metrics[part].1 * size(part));
    // Pieces between break opportunities, each a range of glyphs and whether a line must end after it.
    let mut pieces: Vec<(std::ops::Range<usize>, bool)> = Vec::new();
    let mut first = 0;
    for (end, kind) in breaks {
        let last = first
            + glyphs[first..]
                .iter()
                .take_while(|g| g.cluster < *end)
                .count();
        if last > first || matches!(kind, BreakOpportunity::Mandatory) {
            pieces.push((first..last, matches!(kind, BreakOpportunity::Mandatory)));
        }
        first = last;
    }
    let blank = |g: &Glyph| char_at(g.cluster).is_whitespace();
    // Width without the trailing white space, and with it.
    let measure = |range: std::ops::Range<usize>| {
        let all: f64 = glyphs[range.clone()].iter().map(advance).sum();
        let trailing: f64 = glyphs[range]
            .iter()
            .rev()
            .take_while(|g| blank(g))
            .map(advance)
            .sum();
        (all - trailing, all)
    };
    let mut lines: Vec<std::ops::Range<usize>> = Vec::new();
    let mut line: Option<std::ops::Range<usize>> = None;
    let mut used = 0.0;
    for (piece, mandatory) in pieces {
        let (visible, full) = measure(piece.clone());
        if let Some(open) = &line
            && used + visible > width + 0.01
        {
            lines.push(open.clone());
            line = None;
            used = 0.0;
        }
        if line.is_none() && visible > width + 0.01 {
            // A word wider than the box breaks between its clusters.
            let mut start = piece.start;
            let mut index = piece.start;
            let mut taken = 0.0;
            while index < piece.end {
                let cluster = glyphs[index].cluster;
                let end = index
                    + glyphs[index..piece.end]
                        .iter()
                        .take_while(|g| g.cluster == cluster)
                        .count();
                let wide: f64 = glyphs[index..end].iter().map(advance).sum();
                if index > start && taken + wide > width + 0.01 {
                    lines.push(start..index);
                    start = index;
                    taken = 0.0;
                }
                taken += wide;
                index = end;
            }
            line = Some(start..piece.end);
            used = taken;
        } else {
            line = Some(match line {
                Some(open) => open.start..piece.end,
                None => piece.clone(),
            });
            used += full;
        }
        if mandatory {
            lines.push(line.take().unwrap_or(piece.end..piece.end));
            used = 0.0;
        }
    }
    if let Some(open) = line {
        lines.push(open);
    }
    let mut placed = vec![(0.0, 0.0); glyphs.len()];
    let mut y = 0.0;
    for range in lines {
        // A line without glyphs takes the metrics of the glyph before it.
        let fallback = glyphs
            .get(range.start.saturating_sub(1))
            .or(glyphs.first())
            .map_or(0, |g| g.part);
        let (ascent, descent) = if range.is_empty() {
            metric(fallback)
        } else {
            glyphs[range.clone()]
                .iter()
                .map(|g| metric(g.part))
                .fold((0.0f64, 0.0f64), |a, m| (a.0.max(m.0), a.1.max(m.1)))
        };
        if measure(range.clone()).0 > width + 0.01 {
            return None;
        }
        let mut x = 0.0;
        for index in range {
            let glyph = &glyphs[index];
            let points = size(glyph.part);
            placed[index] = (x + glyph.dx * points, y + ascent - glyph.dy * points);
            x += advance(glyph);
        }
        y += ascent + descent;
        if y > height + 0.01 {
            return None;
        }
    }
    Some(placed)
}

/// A glyph outline as PDF path operators, in points with y up.
struct Outline {
    out: String,
    scale: f64,
    last: (f64, f64),
}

impl Outline {
    fn point(&self, x: f32, y: f32) -> String {
        format!(
            "{} {}",
            number(f64::from(x) * self.scale),
            number(f64::from(y) * self.scale)
        )
    }
}

impl ttf_parser::OutlineBuilder for Outline {
    fn move_to(&mut self, x: f32, y: f32) {
        self.out += &format!("{} m\n", self.point(x, y));
        self.last = (f64::from(x), f64::from(y));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.out += &format!("{} l\n", self.point(x, y));
        self.last = (f64::from(x), f64::from(y));
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        let (x0, y0) = self.last;
        let (qx, qy) = (f64::from(x1), f64::from(y1));
        let c1 = (x0 + 2.0 / 3.0 * (qx - x0), y0 + 2.0 / 3.0 * (qy - y0));
        let c2 = (
            f64::from(x) + 2.0 / 3.0 * (qx - f64::from(x)),
            f64::from(y) + 2.0 / 3.0 * (qy - f64::from(y)),
        );
        self.out += &format!(
            "{} {} {} c\n",
            self.point(c1.0 as f32, c1.1 as f32),
            self.point(c2.0 as f32, c2.1 as f32),
            self.point(x, y)
        );
        self.last = (f64::from(x), f64::from(y));
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        self.out += &format!(
            "{} {} {} c\n",
            self.point(x1, y1),
            self.point(x2, y2),
            self.point(x, y)
        );
        self.last = (f64::from(x), f64::from(y));
    }
    fn close(&mut self) {
        self.out += "h\n";
    }
}

/// The font file to embed: its static TrueType tables, rebuilt with fresh checksums.
fn truetype(data: &[u8]) -> Outcome<Vec<u8>> {
    let missing =
        || Error::Pdf("Für diesen Text fehlt eine einbettbare statische TrueType-Schrift.".into());
    let face = ttf_parser::RawFace::parse(data, 0).map_err(|_| missing())?;
    let table = |tag: &[u8; 4]| face.table(ttf_parser::Tag::from_bytes(tag));
    let required: [&[u8; 4]; 7] = [
        b"head", b"hhea", b"hmtx", b"maxp", b"glyf", b"loca", b"cmap",
    ];
    if required.iter().any(|tag| table(tag).is_none()) || table(b"fvar").is_some() {
        return Err(missing());
    }
    if let Some(os2) = table(b"OS/2").filter(|t| t.len() >= 10)
        && u16::from_be_bytes([os2[8], os2[9]]) & 0x202 != 0
    {
        return bad("Diese Schrift erlaubt keine PDF-Einbettung als Konturen.");
    }
    let tags: [&[u8; 4]; 18] = [
        b"OS/2", b"cmap", b"cvt ", b"fpgm", b"gasp", b"glyf", b"head", b"hhea", b"hmtx", b"kern",
        b"loca", b"maxp", b"name", b"post", b"prep", b"GDEF", b"GPOS", b"GSUB",
    ];
    let mut tables: Vec<([u8; 4], Vec<u8>)> = tags
        .iter()
        .filter_map(|tag| {
            table(tag)
                .filter(|t| !t.is_empty())
                .map(|t| (**tag, t.to_vec()))
        })
        .collect();
    tables.sort_by_key(|table| table.0);
    for (tag, bytes) in &mut tables {
        if tag == b"head" && bytes.len() >= 12 {
            bytes[8..12].fill(0);
        }
    }
    let checksum = |bytes: &[u8]| -> u32 {
        bytes
            .chunks(4)
            .map(|c| {
                let mut word = [0u8; 4];
                word[..c.len()].copy_from_slice(c);
                u32::from_be_bytes(word)
            })
            .fold(0u32, u32::wrapping_add)
    };
    let count = tables.len() as u16;
    let power = 15 - count.leading_zeros() as u16;
    let range = 16 * (1u16 << power);
    let mut out = Vec::new();
    for value in [count, range, power, 16 * count - range] {
        out.extend_from_slice(&value.to_be_bytes());
    }
    out.splice(0..0, 0x10000u32.to_be_bytes());
    let mut offset = 12 + 16 * tables.len();
    let mut head = 0;
    for (tag, bytes) in &tables {
        if tag == b"head" {
            head = offset;
        }
        out.extend_from_slice(tag);
        out.extend_from_slice(&checksum(bytes).to_be_bytes());
        out.extend_from_slice(&(offset as u32).to_be_bytes());
        out.extend_from_slice(&(bytes.len() as u32).to_be_bytes());
        offset += bytes.len().div_ceil(4) * 4;
    }
    for (_, bytes) in &tables {
        out.extend_from_slice(bytes);
        out.resize(out.len().div_ceil(4) * 4, 0);
    }
    let adjustment = 0xB1B0_AFBAu32.wrapping_sub(checksum(&out));
    out[head + 8..head + 12].copy_from_slice(&adjustment.to_be_bytes());
    Ok(out)
}

/// The value of a writer object, following one reference.
fn held(writer: &Writer, value: Option<&Value>) -> Value {
    match value {
        Some(Value::Ref(reference)) => writer
            .objects
            .get(reference.number as usize - 1)
            .cloned()
            .unwrap_or(Value::Null),
        Some(other) => other.clone(),
        None => Value::Null,
    }
}

/// Writes the translated copy of the manifest's PDF to `output`. Returns the page count and the blocks set
/// smaller than their original (page from 1, block id, scale).
pub fn write(
    manifest: &Json,
    translations: &Json,
    output: &Path,
) -> Outcome<(usize, Vec<Reduced>)> {
    let refused =
        "Bitte einen neuen PDF-Dateinamen wählen. Vorhandene Dateien werden nicht überschrieben.";
    let source = Path::new(manifest.get("path").and_then(Json::text).unwrap_or(""));
    let pdf = output
        .extension()
        .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"));
    let same = output
        .parent()
        .and_then(|folder| folder.canonicalize().ok())
        .zip(output.file_name())
        .map(|(folder, name)| folder.join(name))
        .is_some_and(|target| source.canonicalize().is_ok_and(|s| s == target));
    if !pdf || output.symlink_metadata().is_ok() || same {
        return bad(refused);
    }
    let current = inspect(source)?;
    let changed = "Die Quelldatei wurde verändert. Bitte erneut übersetzen.";
    if manifest.get("fingerprint").and_then(Json::text) != Some(current.fingerprint.as_str())
        || !manifest
            .get("segments")
            .is_some_and(|s| same_segments(s, &current.segments))
    {
        return bad(changed);
    }
    let Some(Json::Object(given)) = Some(translations).filter(|t| matches!(t, Json::Object(_)))
    else {
        return bad("Die Übersetzung ist unvollständig. Es wurde keine PDF gespeichert.");
    };
    let ids: Vec<String> = (0..current.segments.len())
        .map(|id| id.to_string())
        .collect();
    if given.len() != ids.len() || ids.iter().any(|id| !given.contains_key(id)) {
        return bad("Die Übersetzung ist unvollständig. Es wurde keine PDF gespeichert.");
    }
    let mut texts: Vec<Vec<String>> = Vec::new();
    for (id, segment) in ids.iter().zip(&current.segments) {
        let parts = given[id].list().unwrap_or(&[]);
        let strings: Option<Vec<String>> =
            parts.iter().map(|p| p.text().map(str::to_string)).collect();
        let valid = strings.as_ref().is_some_and(|strings| {
            strings.len() == segment.parts.len()
                && strings.iter().zip(&segment.parts).all(|(p, o)| {
                    (o.trim().is_empty() || !p.trim().is_empty()) && p.chars().count() <= 30000
                })
        });
        match strings.filter(|_| valid) {
            Some(strings) => texts.push(strings),
            None => return bad("Ungültige Übersetzung für die PDF."),
        }
    }
    let document = Document::open(source, "")?;
    let mut writer = Writer::new();
    let mut setter = Typesetter::new();
    let mut reduced = Vec::new();
    for index in 0..document.pages.len() {
        writer.copy_page(0, &document, index, 0)?;
        let reference = *writer
            .page_refs
            .last()
            .ok_or_else(|| Error::Pdf(changed.into()))?;
        let Value::Dict(page) = writer.objects[reference.number as usize - 1].clone() else {
            return bad("PDF-Exportprüfung fehlgeschlagen.");
        };
        let mut page = (*page).clone();
        let mut stripped = b"q\n".to_vec();
        stripped.extend(without_text(&document.contents(index)?)?);
        stripped.extend_from_slice(b"\nQ\n");
        let mut contents = vec![Value::Ref(writer.stream(&stripped, Dict::new())?)];
        let mut resources = held(&writer, page.get("Resources"))
            .dict()
            .map(|d| (**d).clone())
            .unwrap_or_default();
        let mut fonts = held(&writer, resources.get("Font"))
            .dict()
            .map(|d| (**d).clone())
            .unwrap_or_default();
        let top = document
            .resolve(
                document.pages[index]
                    .get("MediaBox")
                    .unwrap_or(&Value::Null),
            )?
            .array()
            .and_then(|c| c.get(3).and_then(Value::number))
            .ok_or_else(|| Error::Pdf("Ungültiges PDF-Rechteck.".into()))?;
        for (id, segment) in current
            .segments
            .iter()
            .enumerate()
            .filter(|(_, s)| s.page == index)
        {
            let (content, used, scale) = setter.block(
                &mut writer,
                top,
                segment.rect,
                &texts[id],
                &segment.styles,
                segment.angle,
            )?;
            for (name, font) in used {
                fonts.insert(name, Value::Ref(font));
            }
            if !content.is_empty() {
                contents.push(Value::Ref(writer.stream(&content, Dict::new())?));
            }
            if scale < 0.99 {
                reduced.push((index + 1, id.to_string(), (scale * 1000.0).round() / 1000.0));
            }
        }
        resources.insert("Font".into(), Value::Dict(Rc::new(fonts)));
        page.insert("Resources".into(), Value::Dict(Rc::new(resources)));
        page.insert("Contents".into(), Value::Array(Rc::new(contents)));
        writer.put(reference, Value::Dict(Rc::new(page)));
    }
    // The original page streams are no longer referenced; they and every form lose their text too.
    let mut pages_content = HashSet::new();
    for attrs in &document.pages {
        let listed = match attrs.get("Contents") {
            Some(value) => match document.resolve(value)? {
                Value::Array(items) => items.to_vec(),
                _ => vec![value.clone()],
            },
            None => Vec::new(),
        };
        for item in listed {
            if let Value::Ref(reference) = item {
                pages_content.insert(reference);
            }
        }
    }
    let imported: Vec<(Ref, Ref)> = writer
        .imported
        .iter()
        .map(|((_, old), new)| (*old, *new))
        .collect();
    for (old, new) in imported {
        let Value::Stream(original) = document.resolve(&Value::Ref(old))? else {
            continue;
        };
        let form = original.attrs.get("Subtype").and_then(Value::name) == Some("Form");
        if !form && !pages_content.contains(&old) {
            continue;
        }
        let Value::Stream(copied) = writer.objects[new.number as usize - 1].clone() else {
            continue;
        };
        let mut attrs = copied.attrs.clone();
        for key in ["Length", "Filter", "DecodeParms"] {
            attrs.remove(key);
        }
        let data = without_text(&document.decode(&original)?)?;
        writer.put(new, packed(&data, attrs)?);
    }
    setter.finish(&mut writer)?;
    if fingerprint(source)? != current.fingerprint {
        return bad(changed);
    }
    let bytes = writer.bytes()?;
    if Document::new(bytes.clone())?.pages.len() != current.pages {
        return bad("PDF-Exportprüfung fehlgeschlagen.");
    }
    publish(&bytes, output)?;
    Ok((current.pages, reduced))
}

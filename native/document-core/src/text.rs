//! The words of a PDF page with their positions: fonts, the text operators of the content
//! stream, forms, layers and replacement text. It follows the text path of
//! `files/lumen_pdf_page.py`; drawing operators are passed over here and belong to the renderer.
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;

use crate::pdf::{Dict, Document, Error, Outcome, Stream, Syntax, Value, integer, text_string};

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

fn unsupported<T>(text: impl Into<String>) -> Outcome<T> {
    Err(Error::Unsupported(text.into()))
}

/// Operands of a drawing or text operator: finite numbers of a sane size, and as many as expected.
fn numbers(values: &[Value], count: Option<usize>) -> Outcome<Vec<f64>> {
    let read: Option<Vec<f64>> = values
        .iter()
        .map(|value| value.number().filter(|n| n.is_finite() && n.abs() <= 1e8))
        .collect();
    match read {
        Some(read) if count.is_none_or(|count| count == read.len()) => Ok(read),
        _ => bad("Ungültige PDF-Grafikoperanden."),
    }
}

/// An affine map in Qt's convention: `x' = m11 x + m21 y + dx`, and `a.then(b)` applies `a` first.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Matrix {
    m11: f64,
    m12: f64,
    m21: f64,
    m22: f64,
    dx: f64,
    dy: f64,
}

impl Matrix {
    const IDENTITY: Matrix = Matrix {
        m11: 1.0,
        m12: 0.0,
        m21: 0.0,
        m22: 1.0,
        dx: 0.0,
        dy: 0.0,
    };

    fn new(v: &[f64]) -> Matrix {
        Matrix {
            m11: v[0],
            m12: v[1],
            m21: v[2],
            m22: v[3],
            dx: v[4],
            dy: v[5],
        }
    }

    fn then(self, o: Matrix) -> Matrix {
        Matrix {
            m11: self.m11 * o.m11 + self.m12 * o.m21,
            m12: self.m11 * o.m12 + self.m12 * o.m22,
            m21: self.m21 * o.m11 + self.m22 * o.m21,
            m22: self.m21 * o.m12 + self.m22 * o.m22,
            dx: self.dx * o.m11 + self.dy * o.m21 + o.dx,
            dy: self.dx * o.m12 + self.dy * o.m22 + o.dy,
        }
    }

    fn inverted(self) -> Matrix {
        let determinant = self.m11 * self.m22 - self.m12 * self.m21;
        if determinant == 0.0 {
            return Matrix::IDENTITY;
        }
        let inverse = 1.0 / determinant;
        Matrix {
            m11: self.m22 * inverse,
            m12: -self.m12 * inverse,
            m21: -self.m21 * inverse,
            m22: self.m11 * inverse,
            dx: (self.m21 * self.dy - self.m22 * self.dx) * inverse,
            dy: (self.m12 * self.dx - self.m11 * self.dy) * inverse,
        }
    }

    /// A rotation by degrees, exact for the quarter turns.
    fn rotation(degrees: f64) -> Matrix {
        let (sine, cosine) = if degrees == 0.0 {
            (0.0, 1.0)
        } else if degrees == 90.0 || degrees == -270.0 {
            (1.0, 0.0)
        } else if degrees == 270.0 || degrees == -90.0 {
            (-1.0, 0.0)
        } else if degrees == 180.0 || degrees == -180.0 {
            (0.0, -1.0)
        } else {
            degrees.to_radians().sin_cos()
        };
        Matrix {
            m11: cosine,
            m12: sine,
            m21: -sine,
            m22: cosine,
            dx: 0.0,
            dy: 0.0,
        }
    }

    fn map(self, x: f64, y: f64) -> (f64, f64) {
        (
            self.m11 * x + self.m21 * y + self.dx,
            self.m12 * x + self.m22 * y + self.dy,
        )
    }

    fn map_rect(self, r: Rect) -> Rect {
        if self.m12 == 0.0 && self.m21 == 0.0 {
            let (mut x, mut w) = (self.m11 * r.x + self.dx, self.m11 * r.w);
            let (mut y, mut h) = (self.m22 * r.y + self.dy, self.m22 * r.h);
            if w < 0.0 {
                w = -w;
                x -= w;
            }
            if h < 0.0 {
                h = -h;
                y -= h;
            }
            return Rect { x, y, w, h };
        }
        let corners = [
            self.map(r.x, r.y),
            self.map(r.x + r.w, r.y),
            self.map(r.x + r.w, r.y + r.h),
            self.map(r.x, r.y + r.h),
        ];
        let (left, right) = corners.iter().fold((f64::MAX, f64::MIN), |(low, high), p| {
            (low.min(p.0), high.max(p.0))
        });
        let (top, bottom) = corners.iter().fold((f64::MAX, f64::MIN), |(low, high), p| {
            (low.min(p.1), high.max(p.1))
        });
        Rect {
            x: left,
            y: top,
            w: right - left,
            h: bottom - top,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Rect {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}

impl Rect {
    fn right(self) -> f64 {
        self.x + self.w
    }
    fn bottom(self) -> f64 {
        self.y + self.h
    }
    /// The smallest rectangle around both; a rectangle without any size does not count.
    fn united(self, o: Rect) -> Rect {
        if self.w == 0.0 && self.h == 0.0 {
            return o;
        }
        if o.w == 0.0 && o.h == 0.0 {
            return self;
        }
        let span = |start: f64, size: f64| {
            if size < 0.0 {
                (start + size, start)
            } else {
                (start, start + size)
            }
        };
        let ((l1, r1), (l2, r2)) = (span(self.x, self.w), span(o.x, o.w));
        let ((t1, b1), (t2, b2)) = (span(self.y, self.h), span(o.y, o.h));
        Rect {
            x: l1.min(l2),
            y: t1.min(t2),
            w: r1.max(r2) - l1.min(l2),
            h: b1.max(b2) - t1.min(t2),
        }
    }
    fn intersected(self, o: Rect) -> Rect {
        let (left, right) = (self.x.max(o.x), self.right().min(o.right()));
        let (top, bottom) = (self.y.max(o.y), self.bottom().min(o.bottom()));
        if left >= right || top >= bottom {
            Rect {
                x: 0.0,
                y: 0.0,
                w: 0.0,
                h: 0.0,
            }
        } else {
            Rect {
                x: left,
                y: top,
                w: right - left,
                h: bottom - top,
            }
        }
    }
}

/// A PDF rectangle with a positive size.
fn rectangle(value: &Value) -> Outcome<Rect> {
    let Some(corners) = value.array() else {
        return bad("Ungültiges PDF-Rechteck.");
    };
    let c = numbers(corners, Some(4))?;
    if c[2] <= c[0] || c[3] <= c[1] {
        return bad("Leeres PDF-Rechteck.");
    }
    Ok(Rect {
        x: c[0],
        y: c[1],
        w: c[2] - c[0],
        h: c[3] - c[1],
    })
}

/// Python's `round(value, places)`: the nearest decimal, ties to even on the exact binary value.
fn rounded(value: f64, places: usize) -> f64 {
    format!("{value:.places$}").parse().unwrap_or(value)
}

/// Python's `str.isspace` for one character.
fn blank(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

fn all_blank(text: &str) -> bool {
    !text.is_empty() && text.chars().all(blank)
}

fn stripped_empty(text: &str) -> bool {
    text.chars().all(blank)
}

const WINDOWS: &str = "€\u{0}‚ƒ„…†‡ˆ‰Š‹Œ\u{0}Ž\u{0}\u{0}‘’“”•–—˜™š›œ\u{0}žŸ";
const MACINTOSH: &str = "ÄÅÇÉÑÖÜáàâäãåçéèêëíìîïñóòôöõúùûü†°¢£§•¶ß®©™´¨≠ÆØ∞±≤≥¥µ∂∑∏π∫ªºΩæø¿¡¬√ƒ≈∆«»…\u{a0}ÀÃÕŒœ–—“”‘’÷◊ÿŸ⁄€‹›ﬁﬂ‡·‚„‰ÂÊÁËÈÍÎÏÌÓÔ\u{f8ff}ÒÚÛÙıˆ˜¯˘˙˚¸˝˛ˇ";

/// The ToUnicode map of a font: character code to text.
fn unicode_map(
    document: &Document,
    reference: Option<&Value>,
) -> Outcome<HashMap<Vec<u8>, String>> {
    let mut result = HashMap::new();
    let Some(reference) = reference.filter(|value| !matches!(value, Value::Null)) else {
        return Ok(result);
    };
    let Value::Stream(stream) = document.resolve(reference)? else {
        return unsupported("Benannte Unicode-CMaps noch nicht unterstützt.");
    };
    let data = document.decode(&stream)?;
    let mut syntax = Syntax::new(&data, 0);
    let mut values = Vec::new();
    loop {
        syntax.skip();
        if syntax.pos == data.len() {
            break;
        }
        values.push(syntax.value()?);
        if values.len() > 200_000 {
            return bad("PDF-Unicode-CMap zu groß.");
        }
    }
    let mut expanded = 0usize;
    let mut add = |code: &[u8], text: &Value, expanded: &mut usize| -> Outcome<()> {
        let Value::Text(text) = text else {
            return bad("Ungültiges PDF-Unicode-Zeichen.");
        };
        if !(1..=4).contains(&code.len()) || text.len() % 2 != 0 {
            return bad("Ungültiges PDF-Unicode-Zeichen.");
        }
        *expanded += text.len();
        if text.len() > 256 || *expanded > 1024 * 1024 {
            return bad("PDF-Unicode-Expansionsbudget überschritten.");
        }
        let units = text
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u16::from_be_bytes(*pair));
        match char::decode_utf16(units).collect::<Result<String, _>>() {
            Ok(decoded) => {
                result.insert(code.to_vec(), decoded);
                Ok(())
            }
            Err(_) => bad("Ungültiges Unicode im PDF."),
        }
    };
    for (index, value) in values.iter().enumerate() {
        let Value::Operator(operator) = value else {
            continue;
        };
        if &**operator == "usecmap" {
            return unsupported("Vererbte PDF-Unicode-CMap noch nicht unterstützt.");
        }
        let ranges = &**operator == "beginbfrange";
        if !ranges && &**operator != "beginbfchar" {
            continue;
        }
        let count = integer(
            index
                .checked_sub(1)
                .map(|i| &values[i])
                .unwrap_or(&Value::Null),
            0,
            65536,
        )?;
        let width = if ranges { 3 } else { 2 };
        let mut pos = index + 1;
        for _ in 0..count {
            let operands = values.get(pos..pos + width).unwrap_or(&[]);
            pos += width;
            let (Some(Value::Text(first)), true) = (operands.first(), operands.len() == width)
            else {
                return bad("Ungültige PDF-Unicode-Zuordnung.");
            };
            if !ranges {
                add(first, &operands[1], &mut expanded)?;
                continue;
            }
            let Value::Text(last) = &operands[1] else {
                return bad("Ungültiger PDF-Unicode-Bereich.");
            };
            if first.len() != last.len() || !(1..=4).contains(&first.len()) {
                return bad("Ungültiger PDF-Unicode-Bereich.");
            }
            let number = |bytes: &[u8]| {
                bytes
                    .iter()
                    .fold(0i64, |sum, byte| sum << 8 | i64::from(*byte))
            };
            let (a, b) = (number(first), number(last));
            if !(0..=65536).contains(&(b - a)) {
                return bad("PDF-Unicode-Bereich zu groß.");
            }
            let code = |n: i64| n.to_be_bytes()[8 - first.len()..].to_vec();
            match &operands[2] {
                Value::Array(targets) => {
                    if targets.len() as i64 != b - a + 1 {
                        return bad("Unvollständiger PDF-Unicode-Bereich.");
                    }
                    for (n, target) in (a..=b).zip(targets.iter()) {
                        add(&code(n), target, &mut expanded)?;
                    }
                }
                Value::Text(target) => {
                    if target.is_empty()
                        || target.len() > 256
                        || expanded + (b - a + 1) as usize * target.len() > 1024 * 1024
                    {
                        return bad("PDF-Unicode-Expansionsbudget überschritten.");
                    }
                    let mut current = (**target).clone();
                    for n in a..=b {
                        add(
                            &code(n),
                            &Value::Text(Rc::new(current.clone())),
                            &mut expanded,
                        )?;
                        // The next target is one more, as one big number.
                        let mut carried = true;
                        for byte in current.iter_mut().rev() {
                            (*byte, carried) = byte.overflowing_add(u8::from(carried));
                            if !carried {
                                break;
                            }
                        }
                        if carried && n < b {
                            return bad("PDF-Unicode-Bereich läuft über.");
                        }
                    }
                }
                _ => return bad("Ungültiges PDF-Unicode-Ziel."),
            }
        }
    }
    Ok(result)
}

/// Character codes of a symbolic TrueType font: its (3,0) or (1,0) cmap, formats 0, 4 and 6.
fn symbol_cmap(table: &[u8]) -> Option<(u16, HashMap<u32, u16>)> {
    let short = |at: usize| {
        table
            .get(at..at + 2)
            .map(|b| u16::from_be_bytes([b[0], b[1]]))
    };
    let long = |at: usize| {
        table
            .get(at..at + 4)
            .map(|b| u32::from_be_bytes([b[0], b[1], b[2], b[3]]) as usize)
    };
    let count = short(2)? as usize;
    let mut found: HashMap<u16, usize> = HashMap::new();
    for index in 0..count.min(32) {
        let (platform, encoding, offset) = (
            short(4 + index * 8)?,
            short(6 + index * 8)?,
            long(8 + index * 8)?,
        );
        if (platform, encoding) == (3, 0) || (platform, encoding) == (1, 0) {
            found.insert(platform, offset);
        }
    }
    let platform = if found.contains_key(&3) { 3 } else { 1 };
    let offset = *found.get(&platform)?;
    let mut codes = HashMap::new();
    match short(offset)? {
        0 => {
            for (code, gid) in table
                .get(offset + 6..offset + 262)
                .unwrap_or(table.get(offset + 6..)?)
                .iter()
                .enumerate()
            {
                if *gid != 0 {
                    codes.insert(code as u32, u16::from(*gid));
                }
            }
        }
        6 => {
            let (first, number) = (short(offset + 6)? as u32, short(offset + 8)? as usize);
            for index in 0..number {
                let gid = short(offset + 10 + index * 2)?;
                if gid != 0 {
                    codes.insert(first + index as u32, gid);
                }
            }
        }
        4 => {
            let segments = short(offset + 6)? as usize / 2;
            let base = offset + 14;
            let (starts, deltas, ranges) = (
                base + 2 + segments * 2,
                base + 2 + segments * 4,
                base + 2 + segments * 6,
            );
            for index in 0..segments {
                let (start, end) = (
                    short(starts + index * 2)? as u32,
                    short(base + index * 2)? as u32,
                );
                if start > end || codes.len() > 65536 {
                    continue;
                }
                let (shift, delta) = (
                    short(ranges + index * 2)? as usize,
                    short(deltas + index * 2)?,
                );
                for code in start..=end {
                    if code == 0xFFFF {
                        continue;
                    }
                    let mut gid = if shift == 0 {
                        code as u16
                    } else {
                        short(ranges + index * 2 + shift + (code - start) as usize * 2)?
                    };
                    if gid != 0 || shift == 0 {
                        gid = gid.wrapping_add(delta);
                    }
                    if gid != 0 {
                        codes.insert(code, gid);
                    }
                }
            }
        }
        _ => return None,
    }
    Some((platform, codes))
}

enum Program {
    /// TrueType or OpenType data.
    Open(Vec<u8>),
    /// A bare CFF table, as PDF embeds Type 1C fonts.
    Compact(Vec<u8>),
}

impl Program {
    /// The glyph for a text piece, 0 when the font has none.
    fn glyph(&self, text: &str) -> u16 {
        let Some(first) = text.chars().next() else {
            return 0;
        };
        match self {
            Program::Open(data) => {
                let Ok(face) = ttf_parser::Face::parse(data, 0) else {
                    return 0;
                };
                if let Some(found) = face.glyph_index(first) {
                    return found.0;
                }
                // A font with only a Macintosh or symbol table is still asked by character, as FreeType does:
                // through the character's Mac Roman code, or its code in the symbol range.
                let Some((platform, codes)) = face
                    .raw_face()
                    .table(ttf_parser::Tag::from_bytes(b"cmap"))
                    .and_then(symbol_cmap)
                else {
                    return 0;
                };
                let code = first as u32;
                let found = if platform == 1 {
                    let roman = if code < 0x80 {
                        Some(code)
                    } else {
                        MACINTOSH
                            .chars()
                            .position(|c| c == first)
                            .map(|at| at as u32 + 0x80)
                    };
                    roman.and_then(|roman| codes.get(&roman))
                } else {
                    codes
                        .get(&code)
                        .or_else(|| codes.get(&(0xF000 + code)).filter(|_| code < 0x100))
                };
                found.copied().unwrap_or(0)
            }
            // ponytail: a bare CFF font has no Unicode table and the name list is not consulted here, so
            // every character counts as present. The renderer needs the Adobe glyph list; use it here then.
            Program::Compact(_) => 1,
        }
    }

    /// Advance of a glyph in thousandths of the font size.
    fn advance(&self, gid: u16) -> f64 {
        match self {
            Program::Open(data) => ttf_parser::Face::parse(data, 0)
                .ok()
                .and_then(|face| {
                    Some(
                        f64::from(face.glyph_hor_advance(ttf_parser::GlyphId(gid))?) * 1000.0
                            / f64::from(face.units_per_em()),
                    )
                })
                .unwrap_or(0.0),
            Program::Compact(data) => ttf_parser::cff::Table::parse(data)
                .and_then(|table| table.glyph_width(ttf_parser::GlyphId(gid)))
                .map(f64::from)
                .unwrap_or(0.0),
        }
    }

    /// Ascent and descent in thousandths of the font size; the descent is negative.
    fn vertical(&self) -> (f64, f64) {
        match self {
            Program::Open(data) => match ttf_parser::Face::parse(data, 0) {
                Ok(face) => (
                    f64::from(face.ascender()) * 1000.0 / f64::from(face.units_per_em()),
                    f64::from(face.descender()) * 1000.0 / f64::from(face.units_per_em()),
                ),
                Err(_) => (750.0, -250.0),
            },
            Program::Compact(_) => (750.0, -250.0),
        }
    }

    /// Every glyph name with its glyph, and for every name the first character the font shows with it.
    fn names(&self) -> (HashMap<String, u16>, HashMap<String, String>) {
        let (mut glyphs, mut texts) = (HashMap::new(), HashMap::new());
        match self {
            Program::Open(data) => {
                let Ok(face) = ttf_parser::Face::parse(data, 0) else {
                    return (glyphs, texts);
                };
                for gid in 0..face.number_of_glyphs() {
                    if let Some(name) = face.glyph_name(ttf_parser::GlyphId(gid)) {
                        glyphs.insert(name.to_string(), gid);
                    }
                }
                for code in (32..65536u32).filter_map(char::from_u32) {
                    if let Some(name) = face
                        .glyph_index(code)
                        .filter(|gid| gid.0 != 0)
                        .and_then(|gid| face.glyph_name(gid))
                    {
                        texts
                            .entry(name.to_string())
                            .or_insert_with(|| code.to_string());
                    }
                }
            }
            Program::Compact(data) => {
                let Some(table) = ttf_parser::cff::Table::parse(data) else {
                    return (glyphs, texts);
                };
                for gid in 0..table.number_of_glyphs() {
                    if let Some(name) = table.glyph_name(ttf_parser::GlyphId(gid)) {
                        glyphs.insert(name.to_string(), gid);
                    }
                }
            }
        }
        (glyphs, texts)
    }
}

/// The metric-compatible Liberation font for a font the file does not carry.
fn substitute(family: &str, bold: bool, italic: bool) -> Option<Vec<u8>> {
    let style = match (bold, italic) {
        (false, false) => "Regular",
        (true, false) => "Bold",
        (false, true) => "Italic",
        (true, true) => "BoldItalic",
    };
    let wanted = format!(
        "Liberation{}-{style}.ttf",
        family.trim_start_matches("Liberation ").replace(' ', "")
    );
    let mut folders: Vec<std::path::PathBuf> =
        vec!["/usr/share/fonts".into(), "/usr/local/share/fonts".into()];
    if let Some(home) = std::env::var_os("HOME") {
        folders.push(std::path::Path::new(&home).join(".local/share/fonts"));
        folders.push(std::path::Path::new(&home).join(".fonts"));
    }
    let mut depth = 0;
    while !folders.is_empty() && depth < 5 {
        let mut deeper = Vec::new();
        for folder in &folders {
            for entry in std::fs::read_dir(folder).into_iter().flatten().flatten() {
                let path = entry.path();
                if path.file_name().is_some_and(|name| name == wanted.as_str()) {
                    return std::fs::read(path).ok();
                }
                if path.is_dir() {
                    deeper.push(path);
                }
            }
        }
        folders = deeper;
        depth += 1;
    }
    None
}

pub struct Font {
    composite: bool,
    widths: HashMap<u32, f64>,
    default_width: Option<Value>,
    differences: HashMap<u32, String>,
    symbols: Option<(u16, HashMap<u32, u16>)>,
    mapping: HashMap<Vec<u8>, String>,
    encoding: String,
    /// None for the identity map of a composite font.
    gidmap: Option<Vec<u8>>,
    program: Program,
    glyph_names: HashMap<String, u16>,
    name_text: HashMap<String, String>,
    ascent: f64,
    descent: f64,
}

struct Glyph {
    cid: u32,
    text: String,
    width: f64,
}

impl Font {
    fn new(document: &Document, attrs: &Rc<Dict>) -> Outcome<Font> {
        let get = |dict: &Dict, key: &str| dict.get(key).cloned().unwrap_or(Value::Null);
        let subtype = attrs.get("Subtype").and_then(Value::name).unwrap_or("");
        if !matches!(subtype, "Type0" | "Type1" | "TrueType") {
            return unsupported(format!(
                "PDF-Schrifttyp noch nicht unterstützt: {}",
                if subtype.is_empty() { "None" } else { subtype }
            ));
        }
        let composite = subtype == "Type0";
        let mapping = unicode_map(document, attrs.get("ToUnicode"))?;
        let base = attrs
            .get("BaseFont")
            .and_then(Value::name)
            .unwrap_or("")
            .to_string();
        let lower = base.to_lowercase();
        let (bold, italic) = (
            lower.contains("bold"),
            lower.contains("italic") || lower.contains("oblique"),
        );
        let (mut widths, mut default_width, mut gidmap) = (HashMap::new(), None, None);
        let mut inner = attrs.clone();
        if composite {
            if attrs.get("Encoding").and_then(Value::name) != Some("Identity-H") {
                return unsupported("PDF-CID-Schrift benötigt derzeit Identity-H.");
            }
            let descendants = document.resolve(&get(attrs, "DescendantFonts"))?;
            let Some(descendant) = descendants.array().filter(|list| list.len() == 1) else {
                return bad("Ungültige PDF-CID-Schrift.");
            };
            let Value::Dict(descendant) = document.resolve(&descendant[0])? else {
                return bad("Ungültige PDF-CID-Schrift.");
            };
            inner = descendant;
            default_width = Some(inner.get("DW").cloned().unwrap_or(Value::Int(1000)));
            let entries = match inner.get("W") {
                None => Rc::new(Vec::new()),
                Some(value) => document
                    .resolve(value)?
                    .array()
                    .cloned()
                    .ok_or(Error::Pdf("Ungültige PDF-Schriftbreiten.".into()))?,
            };
            let mut pos = 0;
            let next = |pos: &mut usize| -> Outcome<Value> {
                *pos += 1;
                entries
                    .get(*pos - 1)
                    .cloned()
                    .ok_or(Error::Pdf("Ungültige PDF-Schriftbreiten.".into()))
            };
            while pos < entries.len() {
                let start = integer(&next(&mut pos)?, 0, 65535)?;
                let group = document.resolve(&next(&mut pos)?)?;
                if let Some(list) = group.array() {
                    let list = numbers(list, None)?;
                    if start as usize + list.len() > 65536 {
                        return bad("PDF-Schriftbreiten außerhalb des Bereichs.");
                    }
                    widths.extend(
                        list.iter()
                            .enumerate()
                            .map(|(i, width)| (start as u32 + i as u32, *width)),
                    );
                } else {
                    let end = integer(&group, start, 65535)?;
                    let width = numbers(&[next(&mut pos)?], None)?[0];
                    widths.extend((start..=end).map(|cid| (cid as u32, width)));
                }
            }
            match document.resolve(
                inner
                    .get("CIDToGIDMap")
                    .unwrap_or(&Value::Name("Identity".into())),
            )? {
                Value::Stream(stream) => gidmap = Some(document.decode(&stream)?),
                Value::Name(name) if &*name == "Identity" => {}
                _ => return unsupported("PDF-CID-Zuordnung noch nicht unterstützt."),
            }
        } else {
            let entries = match attrs.get("Widths") {
                None => Rc::new(Vec::new()),
                Some(value) => document
                    .resolve(value)?
                    .array()
                    .cloned()
                    .ok_or(Error::Pdf("Ungültige PDF-Schriftbreiten.".into()))?,
            };
            let list = numbers(&entries, None)?;
            let first = integer(attrs.get("FirstChar").unwrap_or(&Value::Int(0)), 0, 255)? as usize;
            if first + list.len() > 256 {
                return bad("PDF-Schriftbreiten außerhalb des Bereichs.");
            }
            widths.extend(
                list.iter()
                    .enumerate()
                    .map(|(i, width)| ((first + i) as u32, *width)),
            );
        }
        let descriptor = match inner.get("FontDescriptor") {
            None => Rc::new(Dict::new()),
            Some(value) => document
                .resolve(value)?
                .dict()
                .cloned()
                .ok_or(Error::Pdf("Ungültiger PDF-Schriftdeskriptor.".into()))?,
        };
        let truthy = |key: &str| {
            descriptor
                .get(key)
                .filter(|value| !matches!(value, Value::Null))
        };
        let file = truthy("FontFile2")
            .or_else(|| truthy("FontFile3"))
            .or_else(|| truthy("FontFile"));
        let mut symbols = None;
        let program = if let Some(file) = file {
            let Value::Stream(stream) = document.resolve(file)? else {
                return bad("PDF-Schriftdatei fehlt.");
            };
            let data = document.decode(&stream)?;
            if ttf_parser::Face::parse(&data, 0).is_ok() {
                if subtype == "TrueType" && !attrs.contains_key("Encoding") {
                    // A symbolic TrueType font without an encoding selects glyphs through its own cmap, not by character name.
                    symbols = ttf_parser::Face::parse(&data, 0).ok().and_then(|face| {
                        face.raw_face()
                            .table(ttf_parser::Tag::from_bytes(b"cmap"))
                            .and_then(symbol_cmap)
                    });
                }
                Program::Open(data)
            } else if ttf_parser::cff::Table::parse(&data).is_some() {
                Program::Compact(data)
            } else {
                return unsupported("Eingebettetes PDF-Schriftformat wird noch nicht unterstützt.");
            }
        } else {
            let name = base.rsplit('+').next().unwrap_or("");
            if composite {
                return unsupported(format!(
                    "Nicht eingebettete PDF-CID-Schrift noch nicht verfügbar: {name}"
                ));
            }
            // A font the file does not carry is replaced by the metric-compatible Liberation family of the same
            // kind; the widths still come from the PDF, so the layout stays where the author put it.
            let flags = match descriptor.get("Flags") {
                Some(Value::Int(flags)) => *flags,
                _ => 0,
            };
            let name = name.to_lowercase();
            let has = |parts: &[&str]| parts.iter().any(|part| name.contains(part));
            let family = if flags & 1 != 0 || has(&["courier", "mono", "consol"]) {
                "Liberation Mono"
            } else if flags & 2 != 0
                || has(&[
                    "times", "serif", "georgia", "garamond", "cambria", "palatino",
                ]) && !name.contains("sans")
            {
                "Liberation Serif"
            } else {
                "Liberation Sans"
            };
            Program::Open(
                substitute(family, bold, italic)
                    .ok_or(Error::Pdf("Systemschrift für PDF fehlt.".into()))?,
            )
        };
        let (own_ascent, own_descent) = program.vertical();
        let metric = |key: &str, own: f64| -> Outcome<f64> {
            match descriptor.get(key) {
                None => Ok(own),
                Some(value) => Ok(numbers(std::slice::from_ref(value), None)?[0]),
            }
        };
        let (ascent, descent) = (
            metric("Ascent", own_ascent)?,
            metric("Descent", own_descent)?,
        );
        let mut differences = HashMap::new();
        let mut encoding = document.resolve(
            attrs
                .get("Encoding")
                .unwrap_or(&Value::Name("StandardEncoding".into())),
        )?;
        if let Value::Dict(details) = &encoding {
            let listed = match details.get("Differences") {
                None => Rc::new(Vec::new()),
                Some(value) => document
                    .resolve(value)?
                    .array()
                    .cloned()
                    .ok_or(Error::Pdf("Ungültige PDF-Schriftkodierung.".into()))?,
            };
            let mut cursor = 0;
            for value in listed.iter() {
                match value {
                    Value::Int(_) => cursor = integer(value, 0, 255)?,
                    Value::Name(name) => {
                        differences.insert(
                            integer(&Value::Int(cursor), 0, 255)? as u32,
                            name.to_string(),
                        );
                        cursor += 1;
                    }
                    _ => return bad("Ungültige PDF-Zeichenkodierung."),
                }
            }
            encoding = details
                .get("BaseEncoding")
                .cloned()
                .unwrap_or(Value::Name("StandardEncoding".into()));
        }
        let encoding = encoding.name().unwrap_or("").to_string();
        if !composite
            && !matches!(
                encoding.as_str(),
                "WinAnsiEncoding" | "MacRomanEncoding" | "StandardEncoding"
            )
        {
            return unsupported(format!(
                "PDF-Schriftkodierung noch nicht unterstützt: {encoding}"
            ));
        }
        let (glyph_names, name_text) = if differences.is_empty() {
            (HashMap::new(), HashMap::new())
        } else {
            program.names()
        };
        Ok(Font {
            composite,
            widths,
            default_width,
            differences,
            symbols,
            mapping,
            encoding,
            gidmap,
            program,
            glyph_names,
            name_text,
            ascent,
            descent,
        })
    }

    fn glyphs(&self, data: &[u8]) -> Outcome<Vec<Glyph>> {
        let size = if self.composite { 2 } else { 1 };
        if !data.len().is_multiple_of(size) {
            return bad("Ungültige PDF-Textzeichenfolge.");
        }
        let mut result = Vec::with_capacity(data.len() / size);
        for code in data.chunks(size) {
            let cid = code
                .iter()
                .fold(0u32, |sum, byte| sum << 8 | u32::from(*byte));
            let mut text = self.mapping.get(code).cloned();
            let gid;
            if self.composite {
                if text.is_none() {
                    return unsupported("PDF-CID-Schrift ohne vollständige Unicode-Zuordnung.");
                }
                gid = match &self.gidmap {
                    None => cid as u16,
                    Some(map) => map
                        .get(cid as usize * 2..cid as usize * 2 + 2)
                        .map(|pair| u16::from_be_bytes([pair[0], pair[1]]))
                        .unwrap_or(0),
                };
            } else if let Some(name) = self.differences.get(&cid) {
                let found = self.glyph_names.get(name).copied();
                if text.is_none() {
                    text = self.name_text.get(name).cloned();
                    let hexadecimal = |digits: &str| {
                        !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_hexdigit())
                    };
                    if text.is_none()
                        && let Some(digits) = name
                            .strip_prefix("uni")
                            .filter(|digits| digits.len() % 4 == 0 && hexadecimal(digits))
                    {
                        let units: Vec<u16> = (0..digits.len() / 4)
                            .filter_map(|i| u16::from_str_radix(&digits[i * 4..i * 4 + 4], 16).ok())
                            .collect();
                        text = char::decode_utf16(units)
                            .collect::<Result<String, _>>()
                            .ok();
                    }
                    if text.is_none()
                        && let Some(digits) = name
                            .strip_prefix('u')
                            .filter(|digits| (4..=6).contains(&digits.len()) && hexadecimal(digits))
                    {
                        text = u32::from_str_radix(digits, 16)
                            .ok()
                            .and_then(char::from_u32)
                            .map(String::from);
                    }
                }
                match (found, &text) {
                    (Some(found), Some(_)) => gid = found,
                    _ => {
                        return unsupported(format!(
                            "PDF-Zeichenname noch nicht unterstützt: {name}"
                        ));
                    }
                }
            } else if let Some(symbol) = self.symbols.as_ref().and_then(|(platform, codes)| {
                let tries: &[u32] = if *platform == 3 {
                    &[0, 0xF000, 0xF100, 0xF200]
                } else {
                    &[0]
                };
                tries
                    .iter()
                    .find_map(|offset| codes.get(&(offset + cid)).copied())
            }) {
                gid = symbol;
                if text.is_none() {
                    if !(32..=126).contains(&cid) {
                        return unsupported("PDF-Symbolschrift ohne Unicode-Zuordnung.");
                    }
                    text = char::from_u32(cid).map(String::from);
                }
            } else {
                let visible = match self.encoding.as_str() {
                    "StandardEncoding" => {
                        if !(32..=126).contains(&cid) {
                            return unsupported(
                                "Erweiterte PDF-StandardEncoding noch nicht unterstützt.",
                            );
                        }
                        match cid {
                            39 => '’',
                            96 => '‘',
                            other => other as u8 as char,
                        }
                    }
                    "WinAnsiEncoding" => match cid {
                        0x80..=0x9f => match WINDOWS.chars().nth(cid as usize - 0x80) {
                            Some(found) if found != '\0' => found,
                            _ => return bad("Nicht zugeordnetes PDF-Zeichen."),
                        },
                        other => other as u8 as char,
                    },
                    _ => match cid {
                        0x80..=0xff => MACINTOSH.chars().nth(cid as usize - 0x80).unwrap_or(' '),
                        other => other as u8 as char,
                    },
                }
                .to_string();
                gid = self.program.glyph(&visible);
                if text.is_none() {
                    text = Some(visible);
                }
            }
            let text = text.unwrap_or_default();
            if gid == 0 && !stripped_empty(&text) {
                return unsupported("PDF-Zeichen fehlt in der ausgewählten Schrift.");
            }
            let width = match self.widths.get(&cid) {
                Some(width) => *width,
                None => match &self.default_width {
                    Some(width) => numbers(std::slice::from_ref(width), None)?[0],
                    None => self.program.advance(gid),
                },
            };
            result.push(Glyph { cid, text, width });
        }
        Ok(result)
    }
}

/// A word: left, top, right, bottom in page pixels, its text and its line.
#[derive(Debug, Clone, PartialEq)]
pub struct Word {
    pub left: f64,
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
    pub text: String,
    pub line: usize,
}

struct Character {
    letter: String,
    angle: f64,
    area: Rect,
}

#[derive(Clone)]
struct State {
    ctm: Matrix,
    font: Option<Rc<Font>>,
    size: f64,
    charspace: f64,
    wordspace: f64,
    scale: f64,
    leading: f64,
    rise: f64,
}

pub struct Page<'d> {
    document: &'d Document,
    pub width: f64,
    pub height: f64,
    area: Rect,
    transform: Matrix,
    hidden_layers: Vec<Rc<Dict>>,
    hidden: usize,
    fonts: RefCell<HashMap<usize, Rc<Font>>>,
    characters: Vec<Character>,
    operations: usize,
    character_units: usize,
}

const KNOWN: &[&str] = &[
    "b", "b*", "B", "B*", "BX", "c", "cs", "CS", "d", "EX", "f", "f*", "F", "g", "G", "gs", "h",
    "i", "j", "J", "k", "K", "l", "m", "M", "MP", "DP", "n", "re", "rg", "RG", "ri", "s", "S",
    "sc", "SC", "scn", "SCN", "sh", "v", "w", "W", "W*", "y",
];

impl<'d> Page<'d> {
    /// Reads the page's text. Drawing is not checked here.
    pub fn words(document: &'d Document, index: usize) -> Outcome<(f64, f64, Vec<Word>)> {
        let Some(attrs) = document.pages.get(index) else {
            return bad("Ungültige PDF-Ganzzahl oder überschrittenes Limit.");
        };
        let rotation = match attrs.get("Rotate") {
            None | Some(Value::Null) => 0,
            Some(Value::Int(turn)) if turn % 90 == 0 => turn.rem_euclid(360),
            Some(value)
                if !value.number().is_some_and(|n| n != 0.0)
                    && !matches!(value, Value::Real(_) | Value::Int(_)) =>
            {
                0
            }
            Some(Value::Real(turn)) if *turn == 0.0 => 0,
            _ => return bad("Ungültige PDF-Seitendrehung."),
        };
        let unit = match attrs.get("UserUnit") {
            None => 1.0,
            Some(value) => numbers(&[document.resolve(value)?], None)?[0],
        };
        if !(unit > 0.0 && unit <= 75000.0) {
            return bad("Ungültige PDF-Seiteneinheit.");
        }
        let media = rectangle(attrs.get("MediaBox").unwrap_or(&Value::Null))?;
        let crop = match attrs.get("CropBox") {
            Some(value)
                if value.array().is_some_and(|a| !a.is_empty())
                    || !matches!(value, Value::Null | Value::Array(_)) =>
            {
                rectangle(value)?
            }
            _ => media,
        };
        let area = media.intersected(crop);
        if area.w <= 0.0 || area.h <= 0.0 {
            return bad("Leerer PDF-Seitenausschnitt.");
        }
        let (x, y, w, h) = (area.x, area.y, area.w, area.h);
        let turned = match rotation {
            90 => Matrix::new(&[0.0, 1.0, 1.0, 0.0, -y, -x]),
            180 => Matrix::new(&[-1.0, 0.0, 0.0, 1.0, x + w, -y]),
            270 => Matrix::new(&[0.0, -1.0, -1.0, 0.0, y + h, x + w]),
            _ => Matrix::new(&[1.0, 0.0, 0.0, -1.0, -x, y + h]),
        };
        let transform = turned.then(Matrix::new(&[unit, 0.0, 0.0, unit, 0.0, 0.0]));
        let (width, height) = if rotation % 180 != 0 {
            (h * unit, w * unit)
        } else {
            (w * unit, h * unit)
        };
        let mut page = Page {
            document,
            width,
            height,
            area,
            transform,
            hidden_layers: Vec::new(),
            hidden: 0,
            fonts: RefCell::new(HashMap::new()),
            characters: Vec::new(),
            operations: 0,
            character_units: 0,
        };
        page.hidden_layers = page.layers()?;
        let resources = match document.resolve(attrs.get("Resources").unwrap_or(&Value::Null))? {
            Value::Dict(resources) => resources,
            _ => Rc::new(Dict::new()),
        };
        let content = document.contents(index)?;
        let state = State {
            ctm: Matrix::IDENTITY,
            font: None,
            size: 0.0,
            charspace: 0.0,
            wordspace: 0.0,
            scale: 1.0,
            leading: 0.0,
            rise: 0.0,
        };
        page.interpret(&content, &resources, &mut Vec::new(), 0, state)?;
        let words = page.build()?;
        Ok((width, height, words))
    }

    /// Layer groups that the document's default configuration switches off.
    fn layers(&self) -> Outcome<Vec<Rc<Dict>>> {
        let resolve = |value: Option<&Value>| self.document.resolve(value.unwrap_or(&Value::Null));
        let properties = resolve(self.document.catalog.get("OCProperties"))?;
        if matches!(properties, Value::Null) {
            return Ok(Vec::new());
        }
        let invalid = || Error::Pdf("Ungültige PDF-Ebenen.".into());
        let properties = properties.dict().ok_or_else(invalid)?;
        let config = match properties.get("D") {
            None => Rc::new(Dict::new()),
            Some(value) => resolve(Some(value))?.dict().cloned().ok_or_else(invalid)?,
        };
        let listed = |holder: &Dict, key: &str| -> Outcome<Vec<Value>> {
            let entries = match holder.get(key) {
                None => return Ok(Vec::new()),
                Some(value) => resolve(Some(value))?,
            };
            let entries = match &entries {
                Value::Array(entries) if entries.len() <= 10000 => entries.clone(),
                Value::Null => return Ok(Vec::new()),
                _ => return Err(invalid()),
            };
            entries
                .iter()
                .map(|entry| self.document.resolve(entry))
                .collect()
        };
        let groups = match properties.get("OCGs") {
            None => Vec::new(),
            Some(_) => listed(properties, "OCGs").map_err(|_| invalid())?,
        };
        let mut off = listed(&config, "OFF")?;
        if config.get("BaseState").and_then(Value::name) == Some("OFF") {
            let on = listed(&config, "ON")?;
            let same = |a: &Value, b: &Value| matches!((a, b), (Value::Dict(a), Value::Dict(b)) if Rc::ptr_eq(a, b));
            off = groups
                .into_iter()
                .filter(|group| !on.iter().any(|shown| same(group, shown)))
                .collect();
        }
        Ok(off
            .iter()
            .filter_map(|group| group.dict().cloned())
            .collect())
    }

    /// Whether content tagged with this layer group or membership dictionary is shown.
    fn visible(&self, reference: Option<&Value>) -> Outcome<bool> {
        let value = self.document.resolve(reference.unwrap_or(&Value::Null))?;
        let dict = match &value {
            Value::Null => return Ok(true),
            Value::Dict(dict) => dict,
            _ => return bad("Ungültige PDF-Ebenenzuordnung."),
        };
        let off = |group: &Rc<Dict>| {
            self.hidden_layers
                .iter()
                .any(|hidden| Rc::ptr_eq(hidden, group))
        };
        if dict.get("Type").and_then(Value::name) != Some("OCMD") {
            return Ok(!off(dict));
        }
        if dict.contains_key("VE") {
            return unsupported("PDF-Ebenenausdruck noch nicht unterstützt.");
        }
        let members = match dict.get("OCGs") {
            None => Vec::new(),
            Some(value) => match self.document.resolve(value)? {
                Value::Array(members) => members.iter().take(10000).cloned().collect(),
                other => vec![other],
            },
        };
        let mut states = Vec::new();
        for member in members {
            match self.document.resolve(&member)? {
                Value::Null => {}
                Value::Dict(group) => states.push(!off(&group)),
                _ => states.push(true),
            }
        }
        if states.is_empty() {
            return Ok(true);
        }
        Ok(match dict.get("P").and_then(Value::name) {
            Some("AllOn") => states.iter().all(|s| *s),
            Some("AnyOff") => !states.iter().all(|s| *s),
            Some("AllOff") => !states.iter().any(|s| *s),
            _ => states.iter().any(|s| *s),
        })
    }

    fn resource(&self, resources: &Dict, category: &str, name: &str) -> Outcome<Value> {
        let missing = || Error::Pdf(format!("PDF-Ressource fehlt: {name}"));
        let dictionary = match resources.get(category) {
            None => return Err(missing()),
            Some(value) => self.document.resolve(value)?,
        };
        let entry = dictionary
            .dict()
            .and_then(|dictionary| dictionary.get(name))
            .ok_or_else(missing)?;
        self.document.resolve(entry)
    }

    fn font(&self, resources: &Dict, name: &str) -> Outcome<Rc<Font>> {
        let Value::Dict(attrs) = self.resource(resources, "Font", name)? else {
            return bad("PDF-Schrift fehlt.");
        };
        let key = Rc::as_ptr(&attrs) as usize;
        if let Some(font) = self.fonts.borrow().get(&key) {
            return Ok(font.clone());
        }
        if self.fonts.borrow().len() >= 64 {
            return bad("Zu viele PDF-Schriften auf einer Seite.");
        }
        let font = Rc::new(Font::new(self.document, &attrs)?);
        self.fonts.borrow_mut().insert(key, font.clone());
        Ok(font)
    }

    fn show(
        &mut self,
        data: &[u8],
        state: &State,
        matrix: &mut Matrix,
        in_text: bool,
    ) -> Outcome<()> {
        let Some(font) = state.font.clone().filter(|_| in_text && state.size > 0.0) else {
            return bad("PDF-Text ohne Schrift oder Textobjekt.");
        };
        let normal = Matrix::new(&[1.0, 0.0, 0.0, -1.0, -self.area.x, self.area.bottom()]);
        let to_normal = self.transform.inverted().then(normal);
        let painter = state.ctm.then(self.transform);
        let baseline = matrix.then(painter).then(to_normal);
        let angle = rounded(
            (baseline.m12 * state.scale)
                .atan2(baseline.m11 * state.scale)
                .to_degrees(),
            6,
        );
        let straight = Matrix::rotation(-angle);
        for glyph in font.glyphs(data)? {
            let advance = (glyph.width / 1000.0 * state.size
                + state.charspace
                + if glyph.cid == 32 && !font.composite {
                    state.wordspace
                } else {
                    0.0
                })
                * state.scale;
            let text_transform = Matrix::new(&[
                state.size / 1000.0 * state.scale,
                0.0,
                0.0,
                -state.size / 1000.0,
                0.0,
                state.rise,
            ])
            .then(*matrix);
            let glyph_transform = text_transform.then(painter);
            let rect = Rect {
                x: 0.0,
                y: -font.ascent,
                w: glyph.width.max(1.0),
                h: font.ascent - font.descent,
            };
            self.character_units += glyph.text.chars().count();
            if self.character_units > 500_000 {
                return bad("Zu viele PDF-Textzeichen auf einer Seite.");
            }
            if self.hidden == 0 {
                self.characters.push(Character {
                    letter: glyph.text,
                    angle,
                    area: glyph_transform
                        .then(to_normal)
                        .then(straight)
                        .map_rect(rect),
                });
            }
            *matrix = Matrix::new(&[1.0, 0.0, 0.0, 1.0, advance, 0.0]).then(*matrix);
        }
        Ok(())
    }

    fn form(
        &mut self,
        stream: &Rc<Stream>,
        resources: &Rc<Dict>,
        forms: &mut Vec<usize>,
        depth: usize,
        state: &State,
    ) -> Outcome<()> {
        let identity = Rc::as_ptr(stream) as usize;
        if forms.contains(&identity) {
            return bad("Zyklische PDF-Form.");
        }
        let corners = match stream.attrs.get("BBox") {
            Some(value) => self.document.resolve(value)?.array().cloned(),
            None => None,
        };
        let Some(corners) = corners else {
            return bad("Ungültiges PDF-Rechteck.");
        };
        let corners = numbers(&corners, Some(4))?;
        if corners[0] == corners[2] || corners[1] == corners[3] {
            return Ok(()); // a form without area shows nothing
        }
        let matrix = match stream.attrs.get("Matrix") {
            None => Matrix::IDENTITY,
            Some(value) => match self.document.resolve(value)?.array() {
                Some(values) => Matrix::new(&numbers(values, Some(6))?),
                None => return bad("Ungültige PDF-Grafikoperanden."),
            },
        };
        let own = match stream.attrs.get("Resources") {
            None => resources.clone(),
            Some(value) => match self.document.resolve(value)? {
                Value::Dict(own) => own,
                _ => Rc::new(Dict::new()),
            },
        };
        let mut inner = state.clone();
        inner.ctm = matrix.then(state.ctm);
        let data = self.document.decode(stream)?;
        forms.push(identity);
        let result = self.interpret(&data, &own, forms, depth + 1, inner);
        forms.pop();
        result
    }

    fn interpret(
        &mut self,
        data: &[u8],
        resources: &Rc<Dict>,
        forms: &mut Vec<usize>,
        depth: usize,
        mut state: State,
    ) -> Outcome<()> {
        if depth > 32 {
            return bad("PDF-Formen zu tief verschachtelt.");
        }
        let mut syntax = Syntax::new(data, 0);
        let (mut operands, mut stack): (Vec<Value>, Vec<State>) = (Vec::new(), Vec::new());
        // Marked spans: whether the span is hidden, its replacement text and where its characters begin.
        let mut marks: Vec<(bool, Option<String>, usize)> = Vec::new();
        let (mut in_text, mut matrix, mut line) = (false, Matrix::IDENTITY, Matrix::IDENTITY);
        loop {
            syntax.skip();
            if syntax.pos == data.len() {
                break;
            }
            let value = syntax.value()?;
            let Value::Operator(operator) = &value else {
                operands.push(value);
                if operands.len() > 100_000 {
                    return bad("Zu viele PDF-Operanden.");
                }
                continue;
            };
            let a = std::mem::take(&mut operands);
            self.operations += 1;
            if self.operations > 1_000_000 {
                return bad("PDF-Grafikbudget überschritten.");
            }
            match &**operator {
                "q" => {
                    numbers(&a, Some(0))?;
                    stack.push(state.clone());
                    if stack.len() > 64 {
                        return bad("PDF-Grafikstack zu tief.");
                    }
                }
                "Q" => {
                    numbers(&a, Some(0))?;
                    let Some(saved) = stack.pop() else {
                        return bad("PDF-Grafikstack ist leer.");
                    };
                    state = saved;
                }
                "cm" => state.ctm = Matrix::new(&numbers(&a, Some(6))?).then(state.ctm),
                "BT" => {
                    numbers(&a, Some(0))?;
                    if in_text {
                        return bad("Verschachteltes PDF-Textobjekt.");
                    }
                    (in_text, matrix, line) = (true, Matrix::IDENTITY, Matrix::IDENTITY);
                }
                "ET" => {
                    numbers(&a, Some(0))?;
                    if !in_text {
                        return bad("PDF-Textende ohne Beginn.");
                    }
                    in_text = false;
                }
                "Tf" => {
                    let (Some(Value::Name(name)), 2) = (a.first(), a.len()) else {
                        return bad("Ungültige PDF-Schriftauswahl.");
                    };
                    state.size = numbers(&a[1..], None)?[0];
                    state.font = Some(self.font(resources, name)?);
                }
                "Tc" | "Tw" | "Tz" | "TL" | "Ts" => {
                    let value = numbers(&a, Some(1))?[0];
                    match &**operator {
                        "Tc" => state.charspace = value,
                        "Tw" => state.wordspace = value,
                        "Tz" => state.scale = value / 100.0,
                        "TL" => state.leading = value,
                        _ => state.rise = value,
                    }
                }
                "Tr" => {
                    if a.len() != 1 {
                        return bad("Ungültiger PDF-Textmodus.");
                    }
                    if integer(&a[0], 0, 7)? >= 4 {
                        return unsupported("PDF-Text-Clipping noch nicht unterstützt.");
                    }
                }
                "Tm" => {
                    matrix = Matrix::new(&numbers(&a, Some(6))?);
                    line = matrix;
                }
                "Td" | "TD" => {
                    let move_by = numbers(&a, Some(2))?;
                    if &**operator == "TD" {
                        state.leading = -move_by[1];
                    }
                    line = Matrix::new(&[1.0, 0.0, 0.0, 1.0, move_by[0], move_by[1]]).then(line);
                    matrix = line;
                }
                "T*" => {
                    numbers(&a, Some(0))?;
                    line = Matrix::new(&[1.0, 0.0, 0.0, 1.0, 0.0, -state.leading]).then(line);
                    matrix = line;
                }
                "Tj" | "TJ" | "'" | "\"" => {
                    let mut a = a;
                    if &**operator == "'" || &**operator == "\"" {
                        if &**operator == "\"" {
                            if a.len() != 3 {
                                return bad("Ungültiger PDF-Textoperator.");
                            }
                            let spacing = numbers(&a[..2], None)?;
                            (state.wordspace, state.charspace) = (spacing[0], spacing[1]);
                            a.drain(..2);
                        }
                        line = Matrix::new(&[1.0, 0.0, 0.0, 1.0, 0.0, -state.leading]).then(line);
                        matrix = line;
                    }
                    if a.len() != 1 {
                        return bad("Ungültiger PDF-Textoperator.");
                    }
                    let spaced = &**operator == "TJ";
                    let chunks: Vec<Value> = match &a[0] {
                        Value::Array(chunks) if spaced => (**chunks).clone(),
                        _ => a,
                    };
                    for chunk in &chunks {
                        match chunk {
                            Value::Text(text) => self.show(text, &state, &mut matrix, in_text)?,
                            Value::Int(_) | Value::Real(_) if spaced => {
                                let shift = numbers(std::slice::from_ref(chunk), None)?[0];
                                matrix = Matrix::new(&[
                                    1.0,
                                    0.0,
                                    0.0,
                                    1.0,
                                    -shift / 1000.0 * state.size * state.scale,
                                    0.0,
                                ])
                                .then(matrix);
                            }
                            _ => return bad("Ungültiger PDF-Textoperator."),
                        }
                    }
                }
                "Do" => {
                    let (Some(Value::Name(name)), 1) = (a.first(), a.len()) else {
                        return bad("Ungültiges PDF-XObject.");
                    };
                    let Value::Stream(object) = self.resource(resources, "XObject", name)? else {
                        return bad("PDF-XObject ist kein Stream.");
                    };
                    if !self.visible(object.attrs.get("OC"))? {
                        continue;
                    }
                    match object.attrs.get("Subtype").and_then(Value::name) {
                        Some("Image") => {}
                        Some("Form") => self.form(&object, resources, forms, depth, &state)?,
                        _ => return unsupported("PDF-XObject-Typ noch nicht unterstützt."),
                    }
                }
                // A marked span can sit on a hidden layer, or carry the text to read in place of its glyphs.
                "BMC" => marks.push((false, None, 0)),
                "BDC" => {
                    if a.len() != 2 {
                        return bad("Ungültige PDF-Inhaltsmarkierung.");
                    }
                    let properties = match &a[1] {
                        Value::Name(name) => self.resource(resources, "Properties", name)?,
                        other => other.clone(),
                    };
                    let Some(properties) = properties.dict().filter(|_| marks.len() < 64) else {
                        return bad("Ungültige PDF-Inhaltsmarkierung.");
                    };
                    let hide = a[0].name() == Some("OC")
                        && !self.visible(Some(&Value::Dict(properties.clone())))?;
                    let actual = match properties.get("ActualText") {
                        None => Value::Null,
                        Some(value) => self.document.resolve(value)?,
                    };
                    let actual = match &actual {
                        Value::Null => None,
                        Value::Text(_) => Some(
                            text_string(&actual)
                                .chars()
                                .filter(|c| !format_mark(*c))
                                .collect::<String>(),
                        ),
                        _ => return bad("Ungültiger PDF-Markierungstext."),
                    };
                    self.hidden += usize::from(hide);
                    marks.push((hide, actual, self.characters.len()));
                }
                "EMC" => {
                    if let Some((hide, actual, start)) = marks.pop() {
                        self.hidden -= usize::from(hide);
                        if let (Some(actual), true) = (actual, self.characters.len() > start) {
                            let span = self.characters.split_off(start);
                            if !stripped_empty(&actual) {
                                let area = span[1..].iter().fold(span[0].area, |sum, character| {
                                    sum.united(character.area)
                                });
                                self.characters.push(Character {
                                    letter: actual,
                                    angle: span[0].angle,
                                    area,
                                });
                            }
                        }
                    }
                }
                other if KNOWN.contains(&other) => {}
                other => {
                    return unsupported(format!(
                        "PDF-Grafikoperator noch nicht unterstützt: {other}"
                    ));
                }
            }
        }
        if !operands.is_empty() || in_text {
            return bad("Unvollständiger PDF-Grafikstream.");
        }
        self.hidden -= marks.iter().filter(|mark| mark.0).count();
        Ok(())
    }

    fn build(&self) -> Outcome<Vec<Word>> {
        struct Draft {
            rect: Rect,
            text: String,
            angle: f64,
        }
        let mut drafts: Vec<Draft> = Vec::new();
        let (mut text, mut rect): (String, Option<Rect>) = (String::new(), None);
        let (mut previous, mut last_angle): (Option<Rect>, f64) = (None, 0.0);
        let normal = Matrix::new(&[1.0, 0.0, 0.0, -1.0, -self.area.x, self.area.bottom()]);
        let to_display = self.transform.inverted().then(normal).inverted();
        for character in &self.characters {
            if character.letter.chars().any(right_to_left) {
                return unsupported(
                    "Rechts-nach-links-PDF-Text wird noch nicht zuverlässig gelesen.",
                );
            }
            let bounds = character.area;
            // Many writers position words without drawing a space; a tenth of the line height separates them, kerning stays below it.
            let gap = previous.is_some_and(|previous| {
                character.angle != last_angle
                    || (bounds.y - previous.y).abs() > f64::max(2.0, bounds.h * 0.4)
                    || bounds.x - previous.right() > f64::max(1.0, bounds.h * 0.1)
            });
            let space = all_blank(&character.letter);
            if (space || gap) && !text.is_empty() {
                drafts.push(Draft {
                    rect: rect.take().unwrap_or(bounds),
                    text: std::mem::take(&mut text),
                    angle: last_angle,
                });
            }
            if !space {
                text.push_str(&character.letter);
                rect = Some(rect.map_or(bounds, |rect| rect.united(bounds)));
            }
            previous = Some(bounds);
            last_angle = character.angle;
        }
        if !text.is_empty() {
            drafts.push(Draft {
                rect: rect.unwrap_or(Rect {
                    x: 0.0,
                    y: 0.0,
                    w: 0.0,
                    h: 0.0,
                }),
                text,
                angle: last_angle,
            });
        }
        // Stable geometric order is local to this backend.
        drafts.sort_by(|a, b| {
            a.angle
                .total_cmp(&b.angle)
                .then(rounded(a.rect.y, 1).total_cmp(&rounded(b.rect.y, 1)))
                .then(a.rect.x.total_cmp(&b.rect.x))
        });
        let mut words = Vec::with_capacity(drafts.len());
        let (mut line, mut last): (usize, Option<(f64, f64)>) = (0, None);
        for draft in drafts {
            let fresh = match last {
                None => false,
                Some((y, angle)) => {
                    draft.angle != angle
                        || (draft.rect.y - y).abs() > f64::max(2.0, draft.rect.h * 0.4)
                }
            };
            if fresh {
                line += 1;
            }
            if fresh || last.is_none() {
                last = Some((draft.rect.y, draft.angle));
            }
            let mapped = Matrix::rotation(draft.angle)
                .then(to_display)
                .map_rect(draft.rect);
            words.push(Word {
                left: mapped.x,
                top: mapped.y,
                right: mapped.right(),
                bottom: mapped.bottom(),
                text: draft.text,
                line,
            });
        }
        Ok(words)
    }
}

/// Unicode format characters (category Cf), which a replacement text may consist of.
fn format_mark(c: char) -> bool {
    matches!(c as u32, 0xAD | 0x600..=0x605 | 0x61C | 0x6DD | 0x70F | 0x8E2 | 0x180E | 0x200B..=0x200F | 0x202A..=0x202E | 0x2060..=0x2064 | 0x2066..=0x206F | 0xFEFF | 0xFFF9..=0xFFFB | 0xE0001 | 0xE0020..=0xE007F)
}

/// ponytail: strong right-to-left characters by block, not the full Unicode bidi table. Such text is
/// refused as in the Python reader; a missed block would be read in visual order instead.
fn right_to_left(c: char) -> bool {
    matches!(c as u32, 0x590..=0x5FF | 0x608 | 0x60B | 0x60D | 0x61B..=0x64A | 0x66D..=0x66F | 0x671..=0x6D5 | 0x6E5..=0x6E6 | 0x6EE..=0x6EF | 0x6FA..=0x8FF | 0x200F | 0x202B | 0x202E | 0x2067 | 0xFB1D..=0xFD3D | 0xFD50..=0xFDFC | 0xFE70..=0xFEFC | 0x10800..=0x10FFF | 0x1E800..=0x1EFFF)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matrices_follow_qt() {
        let turned = Matrix::new(&[1.0, 0.0, 0.0, -1.0, -10.0, 500.0]);
        assert_eq!(turned.map(20.0, 100.0), (10.0, 400.0));
        assert_eq!(turned.then(turned.inverted()).map(3.0, 4.0), (3.0, 4.0));
        let quarter = Matrix::rotation(90.0);
        assert_eq!(quarter.map(1.0, 0.0), (0.0, 1.0));
        let rect = Matrix::new(&[2.0, 0.0, 0.0, -2.0, 0.0, 10.0]).map_rect(Rect {
            x: 1.0,
            y: 1.0,
            w: 2.0,
            h: 3.0,
        });
        assert_eq!(
            rect,
            Rect {
                x: 2.0,
                y: 2.0,
                w: 4.0,
                h: 6.0
            }
        );
        assert_eq!(
            quarter.map_rect(Rect {
                x: 0.0,
                y: 0.0,
                w: 2.0,
                h: 1.0
            }),
            Rect {
                x: -1.0,
                y: 0.0,
                w: 1.0,
                h: 2.0
            }
        );
        assert_eq!(rounded(2.25, 1), 2.2);
        assert_eq!(rounded(0.35, 1), 0.3);
    }

    #[test]
    fn rectangles_unite_and_intersect() {
        let a = Rect {
            x: 0.0,
            y: 0.0,
            w: 2.0,
            h: 2.0,
        };
        let b = Rect {
            x: 1.0,
            y: 1.0,
            w: 3.0,
            h: 1.0,
        };
        assert_eq!(
            a.united(b),
            Rect {
                x: 0.0,
                y: 0.0,
                w: 4.0,
                h: 2.0
            }
        );
        assert_eq!(
            a.intersected(b),
            Rect {
                x: 1.0,
                y: 1.0,
                w: 1.0,
                h: 1.0
            }
        );
        assert_eq!(
            a.united(Rect {
                x: 9.0,
                y: 9.0,
                w: 0.0,
                h: 0.0
            }),
            a
        );
    }

    #[test]
    fn symbolic_fonts_name_glyphs_by_code() {
        let mut byte = vec![
            0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 12, 0, 0, 1, 6, 0, 0, 0, 5, 6,
        ];
        byte.resize(12 + 6 + 256, 0);
        assert_eq!(
            symbol_cmap(&byte),
            Some((1, HashMap::from([(1, 5), (2, 6)])))
        );
        let mut segments = vec![0, 0, 0, 1, 0, 3, 0, 0, 0, 0, 0, 12];
        for value in [
            4u16,
            32,
            0,
            4,
            4,
            1,
            0,
            0xF002,
            0xFFFF,
            0,
            0xF001,
            0xFFFF,
            3u16.wrapping_sub(0xF001),
            1,
            0,
            0,
        ] {
            segments.extend_from_slice(&value.to_be_bytes());
        }
        assert_eq!(
            symbol_cmap(&segments),
            Some((3, HashMap::from([(0xF001, 3), (0xF002, 4)])))
        );
        assert_eq!(symbol_cmap(&[0, 0, 0, 1, 0, 3]), None);
    }

    #[test]
    fn code_pages_match_python() {
        assert_eq!(WINDOWS.chars().count(), 32);
        assert_eq!(MACINTOSH.chars().count(), 128);
        assert_eq!(WINDOWS.chars().nth(0x93 - 0x80), Some('“'));
        assert_eq!(MACINTOSH.chars().nth(0xDB - 0x80), Some('€'));
        assert!(
            right_to_left('א')
                && right_to_left('ب')
                && !right_to_left('a')
                && format_mark('\u{200b}')
        );
    }
}

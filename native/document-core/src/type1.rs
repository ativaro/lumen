//! Type 1 font programs as PDF embeds them (`FontFile`): the encrypted private part, glyph names,
//! advances and outlines. Hints are read past; they do not change the shapes drawn here.
use std::collections::HashMap;

pub struct Font {
    /// Glyph names in the order of their numbers; number 0 is `.notdef`.
    pub names: Vec<String>,
    programs: Vec<Vec<u8>>,
    subroutines: Vec<Vec<u8>>,
    index: HashMap<String, u16>,
    /// The font's own encoding: character code to glyph name, where the program lists one.
    pub encoding: HashMap<u8, String>,
    /// Lowest and highest y of the font's bounding box, in thousandths of the font size.
    pub vertical: Option<(f64, f64)>,
}

/// The cipher of the private part and of every glyph program (Adobe Type 1 Font Format, chapter 7).
fn decrypt(data: &[u8], mut key: u16, skip: usize) -> Vec<u8> {
    let mut plain = Vec::with_capacity(data.len());
    for byte in data {
        plain.push(byte ^ (key >> 8) as u8);
        key = (u16::from(*byte).wrapping_add(key))
            .wrapping_mul(52845)
            .wrapping_add(22719);
    }
    plain.split_off(skip.min(plain.len()))
}

fn find(data: &[u8], pattern: &[u8], from: usize) -> Option<usize> {
    data.get(from..)?
        .windows(pattern.len())
        .position(|window| window == pattern)
        .map(|at| at + from)
}

fn blank(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\r' | b'\n' | 0x0c | 0)
}

/// The next token from `at`: its text and the position after it.
fn token(data: &[u8], mut at: usize) -> Option<(&[u8], usize)> {
    while at < data.len() && blank(data[at]) {
        at += 1;
    }
    let start = at;
    if at < data.len() && data[at] == b'/' {
        at += 1;
    }
    while at < data.len() && !blank(data[at]) && !b"/[]{}()".contains(&data[at]) {
        at += 1;
    }
    if at == start {
        at += 1;
    }
    (start < data.len()).then(|| (&data[start..at.min(data.len())], at.min(data.len())))
}

fn number(text: &[u8]) -> Option<usize> {
    std::str::from_utf8(text).ok()?.parse().ok()
}

impl Font {
    /// Reads a font program; `clear` is the length of its unencrypted head when the PDF states it.
    pub fn parse(data: &[u8], clear: Option<usize>) -> Option<Font> {
        // A PFB file wraps its parts in six-byte segment headers.
        let mut joined;
        let mut data = data;
        if data.first() == Some(&0x80) {
            joined = Vec::with_capacity(data.len());
            let mut at = 0;
            while at + 6 <= data.len() && data[at] == 0x80 && data[at + 1] != 3 {
                let size =
                    u32::from_le_bytes([data[at + 2], data[at + 3], data[at + 4], data[at + 5]])
                        as usize;
                joined.extend_from_slice(data.get(at + 6..at + 6 + size)?);
                at += 6 + size;
            }
            data = &joined;
        }
        if !data.starts_with(b"%!") {
            return None;
        }
        let marker = find(data, b"eexec", 0)?;
        let mut start = clear
            .filter(|length| *length >= marker + 5 && *length < data.len())
            .unwrap_or(marker + 5);
        while start < data.len() && blank(data[start]) && clear.is_none() {
            start += 1;
        }
        let head = &data[..marker];
        let mut cipher = data[start..].to_vec();
        // The private part is binary, or written as hexadecimal digits.
        if cipher.len() >= 4
            && cipher[..4]
                .iter()
                .all(|byte| byte.is_ascii_hexdigit() || blank(*byte))
        {
            let digits: Vec<u8> = cipher
                .iter()
                .copied()
                .filter(u8::is_ascii_hexdigit)
                .collect();
            cipher = digits
                .as_chunks::<2>()
                .0
                .iter()
                .filter_map(|pair| u8::from_str_radix(std::str::from_utf8(pair).ok()?, 16).ok())
                .collect();
        }
        let private = decrypt(&cipher, 55665, 4);
        let skip = find(&private, b"/lenIV", 0)
            .and_then(|at| token(&private, at + 6))
            .and_then(|(text, _)| number(text))
            .unwrap_or(4);
        // `dup <index> <length> RD <bytes>` and `/<name> <length> RD <bytes>`: the binary follows one blank after RD.
        let binary = |after_name: usize| -> Option<(Vec<u8>, usize)> {
            let (length, at) = token(&private, after_name)?;
            let length = number(length)?;
            let (_, at) = token(&private, at)?;
            let bytes = private.get(at + 1..at + 1 + length)?;
            Some((decrypt(bytes, 4330, skip), at + 1 + length))
        };
        let mut subroutines = Vec::new();
        if let Some(at) = find(&private, b"/Subrs", 0) {
            let (count, mut at) = token(&private, at + 6)?;
            subroutines = vec![Vec::new(); number(count)?.min(65536)];
            let end = find(&private, b"/CharStrings", at).unwrap_or(private.len());
            while let Some(found) = find(&private, b"dup", at).filter(|found| *found < end) {
                let Some((index, after)) = token(&private, found + 3) else {
                    break;
                };
                at = found + 3;
                if let (Some(index), Some((program, next))) = (number(index), binary(after))
                    && index < subroutines.len()
                {
                    subroutines[index] = program;
                    at = next;
                }
            }
        }
        let mut at = find(&private, b"/CharStrings", 0)? + 12;
        at = find(&private, b"begin", at)? + 5;
        let (mut names, mut programs) = (vec![".notdef".to_string()], vec![Vec::new()]);
        while let Some((name, after)) = token(&private, at) {
            if name == b"end" || names.len() > 65535 {
                break;
            }
            at = after;
            let Some(name) = name.strip_prefix(b"/") else {
                continue;
            };
            let Some((program, next)) = binary(after) else {
                continue;
            };
            at = next;
            let name = String::from_utf8_lossy(name).into_owned();
            if name == ".notdef" {
                programs[0] = program;
            } else {
                names.push(name);
                programs.push(program);
            }
        }
        if names.len() < 2 {
            return None;
        }
        let mut encoding = HashMap::new();
        let mut at = find(head, b"/Encoding", 0).unwrap_or(head.len());
        let end = find(head, b"readonly def", at).unwrap_or(head.len());
        while let Some(found) = find(head, b"dup", at).filter(|found| *found < end) {
            at = found + 3;
            if let Some((code, after)) = token(head, at)
                && let Some((name, _)) = token(head, after)
                && let (Some(code), Some(name)) = (
                    number(code).and_then(|code| u8::try_from(code).ok()),
                    name.strip_prefix(b"/"),
                )
            {
                encoding.insert(code, String::from_utf8_lossy(name).into_owned());
            }
        }
        let vertical = find(head, b"/FontBBox", 0).and_then(|at| {
            let text = std::str::from_utf8(head.get(at + 9..(at + 120).min(head.len()))?).ok()?;
            let values: Vec<f64> = text
                .split(|c: char| !(c.is_ascii_digit() || c == '-' || c == '.'))
                .filter(|part| !part.is_empty())
                .take(4)
                .filter_map(|part| part.parse().ok())
                .collect();
            (values.len() == 4 && values[3] > values[1]).then(|| (values[1], values[3]))
        });
        let index = names
            .iter()
            .enumerate()
            .map(|(number, name)| (name.clone(), number as u16))
            .collect();
        Some(Font {
            names,
            programs,
            subroutines,
            index,
            encoding,
            vertical,
        })
    }

    pub fn glyph(&self, name: &str) -> u16 {
        self.index.get(name).copied().unwrap_or(0)
    }

    /// The advance of a glyph in font units.
    pub fn advance(&self, glyph: u16) -> f64 {
        struct Nothing;
        impl ttf_parser::OutlineBuilder for Nothing {
            fn move_to(&mut self, _: f32, _: f32) {}
            fn line_to(&mut self, _: f32, _: f32) {}
            fn quad_to(&mut self, _: f32, _: f32, _: f32, _: f32) {}
            fn curve_to(&mut self, _: f32, _: f32, _: f32, _: f32, _: f32, _: f32) {}
            fn close(&mut self) {}
        }
        self.outline(glyph, &mut Nothing).unwrap_or(0.0)
    }

    /// Draws a glyph in font units and returns its advance; None when its program cannot be read.
    pub fn outline(&self, glyph: u16, builder: &mut dyn ttf_parser::OutlineBuilder) -> Option<f64> {
        let mut run = Run {
            font: self,
            builder,
            stack: Vec::new(),
            saved: Vec::new(),
            x: 0.0,
            y: 0.0,
            width: 0.0,
            open: false,
            flex: None,
            steps: 0,
            done: false,
            offset: (0.0, 0.0),
        };
        run.execute(self.programs.get(glyph as usize)?, 0)?;
        if run.open {
            run.builder.close();
        }
        Some(run.width)
    }
}

/// Glyph names of the codes that accented characters are built from (the standard encoding).
fn standard(code: u8) -> Option<&'static str> {
    Some(match code {
        193 => "grave",
        194 => "acute",
        195 => "circumflex",
        196 => "tilde",
        197 => "macron",
        198 => "breve",
        199 => "dotaccent",
        200 => "dieresis",
        202 => "ring",
        203 => "cedilla",
        205 => "hungarumlaut",
        206 => "ogonek",
        207 => "caron",
        245 => "dotlessi",
        _ => return None,
    })
}

struct Run<'f, 'b> {
    font: &'f Font,
    builder: &'b mut dyn ttf_parser::OutlineBuilder,
    stack: Vec<f64>,
    /// Values handed back by the built-in procedures (`callothersubr`), taken with `pop`.
    saved: Vec<f64>,
    x: f64,
    y: f64,
    width: f64,
    open: bool,
    /// While a flex is being described: its reference point and the points that follow.
    flex: Option<Vec<(f64, f64)>>,
    steps: usize,
    done: bool,
    /// Where an accent of a composed character is moved to.
    offset: (f64, f64),
}

impl Run<'_, '_> {
    fn go(&mut self, dx: f64, dy: f64) {
        self.x += dx;
        self.y += dy;
    }

    fn start(&mut self, dx: f64, dy: f64) {
        self.go(dx, dy);
        if let Some(points) = &mut self.flex {
            points.push((self.x, self.y));
            return;
        }
        if self.open {
            self.builder.close();
        }
        self.builder.move_to(
            (self.x + self.offset.0) as f32,
            (self.y + self.offset.1) as f32,
        );
        self.open = true;
    }

    fn line(&mut self, dx: f64, dy: f64) {
        self.go(dx, dy);
        self.builder.line_to(
            (self.x + self.offset.0) as f32,
            (self.y + self.offset.1) as f32,
        );
    }

    fn curve(&mut self, d: [f64; 6]) {
        let (x1, y1) = (self.x + d[0], self.y + d[1]);
        let (x2, y2) = (x1 + d[2], y1 + d[3]);
        (self.x, self.y) = (x2 + d[4], y2 + d[5]);
        let (ox, oy) = self.offset;
        self.builder.curve_to(
            (x1 + ox) as f32,
            (y1 + oy) as f32,
            (x2 + ox) as f32,
            (y2 + oy) as f32,
            (self.x + ox) as f32,
            (self.y + oy) as f32,
        );
    }

    fn execute(&mut self, program: &[u8], depth: usize) -> Option<()> {
        if depth > 10 {
            return None;
        }
        let mut at = 0;
        while at < program.len() && !self.done {
            self.steps += 1;
            if self.steps > 20000 || self.stack.len() > 48 {
                return None;
            }
            let byte = program[at];
            at += 1;
            if byte >= 32 {
                let value = match byte {
                    32..=246 => f64::from(byte) - 139.0,
                    247..=250 => {
                        (f64::from(byte) - 247.0) * 256.0 + f64::from(*program.get(at)?) + 108.0
                    }
                    251..=254 => {
                        -(f64::from(byte) - 251.0) * 256.0 - f64::from(*program.get(at)?) - 108.0
                    }
                    _ => f64::from(i32::from_be_bytes(
                        program.get(at..at + 4)?.try_into().ok()?,
                    )),
                };
                at += match byte {
                    32..=246 => 0,
                    247..=254 => 1,
                    _ => 4,
                };
                self.stack.push(value);
                continue;
            }
            let s = std::mem::take(&mut self.stack);
            let arg = |index: usize| s.get(index).copied();
            match byte {
                1 | 3 => {}
                4 => self.start(0.0, arg(0)?),
                5 => self.line(arg(0)?, arg(1)?),
                6 => self.line(arg(0)?, 0.0),
                7 => self.line(0.0, arg(0)?),
                8 => self.curve([arg(0)?, arg(1)?, arg(2)?, arg(3)?, arg(4)?, arg(5)?]),
                9 => {
                    if self.open {
                        self.builder.close();
                        self.open = false;
                    }
                }
                10 => {
                    let index = arg(s.len().checked_sub(1)?)? as usize;
                    self.stack = s[..s.len() - 1].to_vec();
                    let routine = self.font.subroutines.get(index)?.clone();
                    self.execute(&routine, depth + 1)?;
                }
                11 => {
                    self.stack = s;
                    return Some(());
                }
                13 => {
                    (self.x, self.y, self.width) = (arg(0)?, 0.0, arg(1)?);
                }
                14 => self.done = true,
                21 => self.start(arg(0)?, arg(1)?),
                22 => self.start(arg(0)?, 0.0),
                30 => self.curve([0.0, arg(0)?, arg(1)?, arg(2)?, arg(3)?, 0.0]),
                31 => self.curve([arg(0)?, 0.0, arg(1)?, arg(2)?, 0.0, arg(3)?]),
                12 => {
                    let second = *program.get(at)?;
                    at += 1;
                    match second {
                        0..=2 => {}
                        6 => {
                            // An accented character: a base glyph and an accent moved into place.
                            let (bearing, dx, dy) = (arg(0)?, arg(1)?, arg(2)?);
                            let (base, accent) = (arg(3)? as u8, arg(4)? as u8);
                            let name = |code: u8| {
                                standard(code).map(str::to_string).or_else(|| {
                                    code.is_ascii_alphabetic()
                                        .then(|| (code as char).to_string())
                                })
                            };
                            let (origin, width) = (self.x, self.width);
                            for (code, offset) in
                                [(base, (0.0, 0.0)), (accent, (origin - bearing + dx, dy))]
                            {
                                let glyph = self.font.glyph(&name(code)?);
                                let program = self.font.programs.get(glyph as usize)?.clone();
                                (self.done, self.stack, self.offset) = (false, Vec::new(), offset);
                                self.execute(&program, depth + 1)?;
                            }
                            self.offset = (0.0, 0.0);
                            (self.width, self.done) = (width, true);
                        }
                        7 => {
                            (self.x, self.y, self.width) = (arg(0)?, arg(1)?, arg(2)?);
                        }
                        12 => {
                            let (a, b) = (arg(s.len().checked_sub(2)?)?, arg(s.len() - 1)?);
                            self.stack = s[..s.len() - 2].to_vec();
                            self.stack.push(if b == 0.0 { 0.0 } else { a / b });
                        }
                        16 => {
                            let which = arg(s.len().checked_sub(1)?)? as i64;
                            let count = arg(s.len().checked_sub(2)?)? as usize;
                            let args = s
                                .get(s.len().checked_sub(2 + count)?..s.len() - 2)?
                                .to_vec();
                            self.stack = s[..s.len() - 2 - count].to_vec();
                            match which {
                                1 => self.flex = Some(Vec::new()),
                                2 => {}
                                0 => {
                                    let points = self.flex.take()?;
                                    if points.len() == 7 {
                                        for curve in [&points[1..4], &points[4..7]] {
                                            let (ox, oy) = self.offset;
                                            self.builder.curve_to(
                                                (curve[0].0 + ox) as f32,
                                                (curve[0].1 + oy) as f32,
                                                (curve[1].0 + ox) as f32,
                                                (curve[1].1 + oy) as f32,
                                                (curve[2].0 + ox) as f32,
                                                (curve[2].1 + oy) as f32,
                                            );
                                        }
                                    }
                                    // The end point is handed back for the `setcurrentpoint` that follows.
                                    self.saved = vec![*args.get(2)?, *args.get(1)?];
                                }
                                _ => self.saved = args.into_iter().rev().collect(),
                            }
                        }
                        17 => {
                            self.stack = s;
                            self.stack.push(self.saved.pop()?);
                        }
                        33 => {
                            (self.x, self.y) = (arg(0)?, arg(1)?);
                        }
                        _ => return None,
                    }
                }
                _ => return None,
            }
        }
        Some(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn encrypt(plain: &[u8], mut key: u16, lead: usize) -> Vec<u8> {
        let mut out = Vec::new();
        for byte in std::iter::repeat_n(&0u8, lead).chain(plain) {
            let coded = byte ^ (key >> 8) as u8;
            key = (u16::from(coded).wrapping_add(key))
                .wrapping_mul(52845)
                .wrapping_add(22719);
            out.push(coded);
        }
        out
    }

    struct Trace(Vec<String>);

    impl ttf_parser::OutlineBuilder for Trace {
        fn move_to(&mut self, x: f32, y: f32) {
            self.0.push(format!("M{x},{y}"));
        }
        fn line_to(&mut self, x: f32, y: f32) {
            self.0.push(format!("L{x},{y}"));
        }
        fn quad_to(&mut self, _: f32, _: f32, _: f32, _: f32) {}
        fn curve_to(&mut self, _: f32, _: f32, _: f32, _: f32, x: f32, y: f32) {
            self.0.push(format!("C{x},{y}"));
        }
        fn close(&mut self) {
            self.0.push("Z".into());
        }
    }

    #[test]
    fn a_small_font_program_gives_names_advances_and_outlines() {
        // A: hsbw 50 600, rmoveto 0 0, rlineto 100 0, vlineto 200, callsubr 0 (closepath), endchar.
        let num = |v: i32| -> Vec<u8> {
            if (-107..=107).contains(&v) {
                vec![(v + 139) as u8]
            } else {
                vec![
                    255,
                    (v >> 24) as u8,
                    (v >> 16) as u8,
                    (v >> 8) as u8,
                    v as u8,
                ]
            }
        };
        let glyph: Vec<u8> = [
            num(50),
            num(600),
            vec![13],
            num(0),
            num(0),
            vec![21],
            num(100),
            num(0),
            vec![5],
            num(200),
            vec![7],
            num(0),
            vec![10],
            vec![14],
        ]
        .concat();
        let (glyph, routine) = (encrypt(&glyph, 4330, 4), encrypt(&[9, 11], 4330, 4));
        let mut private =
            b"dup /Private 5 dict dup begin /lenIV 4 def /Subrs 1 array dup 0 ".to_vec();
        private.extend(format!("{} RD ", routine.len()).bytes());
        private.extend(&routine);
        private.extend(b" NP ND 2 index /CharStrings 2 dict dup begin /A ");
        private.extend(format!("{} RD ", glyph.len()).bytes());
        private.extend(&glyph);
        private.extend(b" ND /.notdef 1 RD x ND end end");
        let mut file = b"%!PS-AdobeFont-1.0: Test\n/FontBBox {-10 -200 700 800} readonly def\n/Encoding 256 array dup 65 /A put readonly def\ncurrentfile eexec\n".to_vec();
        let clear = file.len();
        file.extend(encrypt(&private, 55665, 4));
        let font = Font::parse(&file, Some(clear)).unwrap();
        assert_eq!(font.names, [".notdef", "A"]);
        assert_eq!((font.glyph("A"), font.glyph("B")), (1, 0));
        assert_eq!(font.encoding.get(&65).map(String::as_str), Some("A"));
        assert_eq!(font.vertical, Some((-200.0, 800.0)));
        let mut trace = Trace(Vec::new());
        assert_eq!(font.outline(1, &mut trace), Some(600.0));
        assert_eq!(trace.0, ["M50,0", "L150,0", "L150,200", "Z"]);
        assert_eq!(font.advance(1), 600.0);
        assert!(Font::parse(b"not a font", None).is_none());
    }
}

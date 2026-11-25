//! What the notebook files and settings hold as Python wrote and read them: `json.loads` and
//! `json.dumps` (key order kept, arbitrary integers, `NaN`/`Infinity`, both escapings), `repr` of
//! floats and `str()` of any JSON value, the `uuid.UUID(hex)` reading and the message of a failed
//! UTF-8 decode.

/// A JSON value as Python holds it: integers keep every digit, objects keep their key order.
#[derive(Clone, Debug, PartialEq)]
pub enum Py {
    None,
    Bool(bool),
    /// Decimal digits with an optional `-`, as `str(int)` prints it.
    Int(String),
    Float(f64),
    Str(String),
    List(Vec<Py>),
    Dict(Vec<(String, Py)>),
}

impl Py {
    pub fn str(value: &str) -> Self {
        Py::Str(value.to_owned())
    }
    pub fn int(value: i64) -> Self {
        Py::Int(value.to_string())
    }
    pub fn get(&self, key: &str) -> Option<&Py> {
        match self {
            Py::Dict(items) => items.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Py::Str(value) => Some(value),
            _ => None,
        }
    }
    /// `dict[key] = value`: an existing key keeps its place.
    pub fn set(&mut self, key: &str, value: Py) {
        if let Py::Dict(items) = self {
            match items.iter_mut().find(|(k, _)| k == key) {
                Some(item) => item.1 = value,
                None => items.push((key.to_owned(), value)),
            }
        }
    }
    /// Python's truth value.
    pub fn truthy(&self) -> bool {
        match self {
            Py::None => false,
            Py::Bool(value) => *value,
            Py::Int(digits) => digits.trim_start_matches('-') != "0",
            Py::Float(value) => *value != 0.0,
            Py::Str(value) => !value.is_empty(),
            Py::List(items) => !items.is_empty(),
            Py::Dict(items) => !items.is_empty(),
        }
    }
}

/// Deeper nesting than Python's decoder reaches with the stack it had is read as invalid.
const DEPTH: usize = 50_000;

/// `json.loads`: `None` where Python raised a `ValueError`.
pub fn loads(text: &str) -> Option<Py> {
    let mut reader = Reader {
        text: text.as_bytes(),
        at: 0,
    };
    reader.space();
    let value = reader.value(0)?;
    reader.space();
    (reader.at == reader.text.len()).then_some(value)
}

struct Reader<'a> {
    text: &'a [u8],
    at: usize,
}

impl Reader<'_> {
    fn space(&mut self) {
        while matches!(self.text.get(self.at), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.at += 1;
        }
    }
    fn literal(&mut self, word: &str) -> bool {
        let found = self.text[self.at..].starts_with(word.as_bytes());
        if found {
            self.at += word.len();
        }
        found
    }
    fn value(&mut self, depth: usize) -> Option<Py> {
        if depth > DEPTH {
            return None;
        }
        match *self.text.get(self.at)? {
            b'{' => {
                self.at += 1;
                let mut items: Vec<(String, Py)> = Vec::new();
                self.space();
                if self.literal("}") {
                    return Some(Py::Dict(items));
                }
                loop {
                    self.space();
                    if self.text.get(self.at) != Some(&b'"') {
                        return None;
                    }
                    let key = self.string()?;
                    self.space();
                    if !self.literal(":") {
                        return None;
                    }
                    self.space();
                    let value = self.value(depth + 1)?;
                    // A repeated key keeps its first place and takes the last value, as dict() does.
                    match items.iter_mut().find(|(k, _)| *k == key) {
                        Some(item) => item.1 = value,
                        None => items.push((key, value)),
                    }
                    self.space();
                    if self.literal("}") {
                        return Some(Py::Dict(items));
                    }
                    if !self.literal(",") {
                        return None;
                    }
                }
            }
            b'[' => {
                self.at += 1;
                let mut items = Vec::new();
                self.space();
                if self.literal("]") {
                    return Some(Py::List(items));
                }
                loop {
                    self.space();
                    items.push(self.value(depth + 1)?);
                    self.space();
                    if self.literal("]") {
                        return Some(Py::List(items));
                    }
                    if !self.literal(",") {
                        return None;
                    }
                }
            }
            b'"' => self.string().map(Py::Str),
            b'n' if self.literal("null") => Some(Py::None),
            b't' if self.literal("true") => Some(Py::Bool(true)),
            b'f' if self.literal("false") => Some(Py::Bool(false)),
            b'N' if self.literal("NaN") => Some(Py::Float(f64::NAN)),
            b'I' if self.literal("Infinity") => Some(Py::Float(f64::INFINITY)),
            b'-' if self.literal("-Infinity") => Some(Py::Float(f64::NEG_INFINITY)),
            _ => self.number(),
        }
    }
    fn number(&mut self) -> Option<Py> {
        let start = self.at;
        let digits = |reader: &mut Self| {
            let from = reader.at;
            while reader.text.get(reader.at).is_some_and(u8::is_ascii_digit) {
                reader.at += 1;
            }
            reader.at - from
        };
        self.literal("-");
        if self.literal("0") {
        } else if digits(self) == 0 {
            return None;
        }
        let integer = self.at;
        let mut float = false;
        if self.text.get(self.at) == Some(&b'.')
            && self.text.get(self.at + 1).is_some_and(u8::is_ascii_digit)
        {
            self.at += 1;
            digits(self);
            float = true;
        }
        if matches!(self.text.get(self.at), Some(b'e' | b'E')) {
            let mark = self.at;
            self.at += 1;
            let _sign = self.literal("-") || self.literal("+");
            if digits(self) == 0 {
                self.at = mark;
            } else {
                float = true;
            }
        }
        let text = std::str::from_utf8(&self.text[start..self.at]).ok()?;
        if float {
            return text.parse().ok().map(Py::Float);
        }
        let digits = &self.text[start..integer];
        let digits = std::str::from_utf8(digits).ok()?;
        Some(Py::Int(if digits == "-0" {
            "0".into()
        } else {
            digits.into()
        }))
    }
    /// A string after its opening quote. A lone surrogate, which Python keeps, becomes U+FFFD.
    fn string(&mut self) -> Option<String> {
        self.at += 1;
        let mut out = String::new();
        loop {
            let rest = &self.text[self.at..];
            let run = rest
                .iter()
                .position(|c| matches!(c, b'"' | b'\\') || *c < 0x20)?;
            out.push_str(std::str::from_utf8(&rest[..run]).ok()?);
            self.at += run;
            match self.text[self.at] {
                b'"' => {
                    self.at += 1;
                    return Some(out);
                }
                b'\\' => {
                    self.at += 1;
                    let escape = *self.text.get(self.at)?;
                    self.at += 1;
                    out.push(match escape {
                        b'"' => '"',
                        b'\\' => '\\',
                        b'/' => '/',
                        b'b' => '\u{8}',
                        b'f' => '\u{c}',
                        b'n' => '\n',
                        b'r' => '\r',
                        b't' => '\t',
                        b'u' => {
                            let first = self.hex4()?;
                            if (0xd800..0xdc00).contains(&first)
                                && self.text[self.at..].starts_with(b"\\u")
                            {
                                let mark = self.at;
                                self.at += 2;
                                let second = self.hex4()?;
                                if (0xdc00..0xe000).contains(&second) {
                                    char::from_u32(
                                        0x10000 + ((first - 0xd800) << 10) + (second - 0xdc00),
                                    )?
                                } else {
                                    self.at = mark;
                                    '\u{fffd}'
                                }
                            } else {
                                char::from_u32(first).unwrap_or('\u{fffd}')
                            }
                        }
                        _ => return None,
                    });
                }
                // Python's strict decoder refuses raw control characters.
                _ => return None,
            }
        }
    }
    fn hex4(&mut self) -> Option<u32> {
        let digits = self.text.get(self.at..self.at + 4)?;
        if !digits.iter().all(u8::is_ascii_hexdigit) {
            return None;
        }
        self.at += 4;
        u32::from_str_radix(std::str::from_utf8(digits).ok()?, 16).ok()
    }
}

/// `json.dumps(value, ensure_ascii=ascii)` with the default separators.
pub fn dumps(value: &Py, ascii: bool) -> String {
    let mut out = String::new();
    dump(value, ascii, &mut out);
    out
}

fn dump(value: &Py, ascii: bool, out: &mut String) {
    match value {
        Py::None => out.push_str("null"),
        Py::Bool(true) => out.push_str("true"),
        Py::Bool(false) => out.push_str("false"),
        Py::Int(digits) => out.push_str(digits),
        Py::Float(value) if value.is_nan() => out.push_str("NaN"),
        Py::Float(value) if value.is_infinite() => out.push_str(if *value > 0.0 {
            "Infinity"
        } else {
            "-Infinity"
        }),
        Py::Float(value) => out.push_str(&float_repr(*value)),
        Py::Str(text) => quote(text, ascii, out),
        Py::List(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                dump(item, ascii, out);
            }
            out.push(']');
        }
        Py::Dict(items) => {
            out.push('{');
            for (i, (key, item)) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                quote(key, ascii, out);
                out.push_str(": ");
                dump(item, ascii, out);
            }
            out.push('}');
        }
    }
}

/// A JSON string as Python's encoder writes it.
pub fn quote(text: &str, ascii: bool, out: &mut String) {
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ch if ch < ' ' || (ascii && ch > '~') => {
                let mut units = [0u16; 2];
                for unit in ch.encode_utf16(&mut units) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
            ch => out.push(ch),
        }
    }
    out.push('"');
}

/// `repr(float)`: the shortest digits that read back, fixed between 1e-4 and 1e16.
pub fn float_repr(value: f64) -> String {
    if value.is_nan() {
        return "nan".into();
    }
    if value.is_infinite() {
        return if value > 0.0 { "inf" } else { "-inf" }.into();
    }
    let scientific = format!("{:e}", value.abs());
    let (mantissa, exponent) = scientific.split_once('e').expect("exponent");
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let point = exponent.parse::<i32>().expect("exponent") + 1;
    let sign = if value.is_sign_negative() { "-" } else { "" };
    let count = digits.len() as i32;
    if point <= -4 || point > 16 {
        let tail = if count > 1 {
            format!(".{}", &digits[1..])
        } else {
            String::new()
        };
        let exp = point - 1;
        return format!(
            "{sign}{}{tail}e{}{:02}",
            &digits[..1],
            if exp < 0 { '-' } else { '+' },
            exp.abs()
        );
    }
    if point <= 0 {
        format!("{sign}0.{}{digits}", "0".repeat((-point) as usize))
    } else if point >= count {
        format!("{sign}{digits}{}.0", "0".repeat((point - count) as usize))
    } else {
        let (whole, fraction) = digits.split_at(point as usize);
        format!("{sign}{whole}.{fraction}")
    }
}

/// `str(value)` for a value from JSON.
pub fn py_str(value: &Py) -> String {
    match value {
        Py::Str(text) => text.clone(),
        other => py_repr(other),
    }
}

/// `repr(value)` for a value from JSON.
pub fn py_repr(value: &Py) -> String {
    match value {
        Py::None => "None".into(),
        Py::Bool(true) => "True".into(),
        Py::Bool(false) => "False".into(),
        Py::Int(digits) => digits.clone(),
        Py::Float(value) => float_repr(*value),
        Py::Str(text) => str_repr(text),
        Py::List(items) => format!(
            "[{}]",
            items.iter().map(py_repr).collect::<Vec<_>>().join(", ")
        ),
        Py::Dict(items) => format!(
            "{{{}}}",
            items
                .iter()
                .map(|(k, v)| format!("{}: {}", str_repr(k), py_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

/// `repr(str)`: single quotes unless only the double quote is free, non-printable characters escaped.
pub fn str_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::from(quote);
    for ch in text.chars() {
        match ch {
            ch if ch == quote || ch == '\\' => {
                out.push('\\');
                out.push(ch);
            }
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            ch if ch < ' ' || ch == '\u{7f}' => out.push_str(&format!("\\x{:02x}", ch as u32)),
            ch if ch.is_ascii() || printable(ch) => out.push(ch),
            ch if (ch as u32) <= 0xff => out.push_str(&format!("\\x{:02x}", ch as u32)),
            ch if (ch as u32) <= 0xffff => out.push_str(&format!("\\u{:04x}", ch as u32)),
            ch => out.push_str(&format!("\\U{:08x}", ch as u32)),
        }
    }
    out.push(quote);
    out
}

fn printable(ch: char) -> bool {
    let n = u32::from(ch);
    let at = NOT_PRINTABLE.partition_point(|(_, end)| *end < n);
    !NOT_PRINTABLE.get(at).is_some_and(|(start, _)| *start <= n)
}

/// `str(uuid.UUID(value))`, or `None` where Python raised `ValueError`. Like Python it takes
/// braces, hyphens and `urn:`/`uuid:` anywhere, and reads the 32 characters as `int(…, 16)` does:
/// white space around, a sign, a `0x` prefix, single underscores between digits, and decimal digits
/// of any script.
pub fn uuid(value: &str) -> Option<String> {
    let value = value.replace("urn:", "").replace("uuid:", "");
    let value = value.trim_matches(['{', '}']).replace('-', "");
    if value.chars().count() != 32 {
        return None;
    }
    // _PyUnicode_TransformDecimalAndSpaceToASCII
    let mut ascii = String::new();
    for ch in value.chars() {
        if (ch as u32) < 127 {
            ascii.push(ch);
        } else if whitespace(ch) {
            ascii.push(' ');
        } else {
            ascii.push(char::from(b'0' + decimal(ch)?));
        }
    }
    let text = ascii.trim_matches([' ', '\t', '\n', '\r', '\u{b}', '\u{c}']);
    let (negative, text) = match text.as_bytes().first() {
        Some(b'-') => (true, &text[1..]),
        Some(b'+') => (false, &text[1..]),
        _ => (false, text),
    };
    let text = text
        .strip_prefix("0x")
        .or_else(|| text.strip_prefix("0X"))
        .map(|rest| rest.strip_prefix('_').unwrap_or(rest))
        .unwrap_or(text);
    if text.is_empty()
        || text.starts_with('_')
        || text.ends_with('_')
        || text.contains("__")
        || !text.bytes().all(|c| c.is_ascii_hexdigit() || c == b'_')
    {
        return None;
    }
    let number = u128::from_str_radix(&text.replace('_', ""), 16).ok()?;
    if negative && number != 0 {
        return None;
    }
    let hex = format!("{number:032x}");
    Some(format!(
        "{}-{}-{}-{}-{}",
        &hex[..8],
        &hex[8..12],
        &hex[12..16],
        &hex[16..20],
        &hex[20..]
    ))
}

/// Python's `str.isspace()`.
pub fn whitespace(ch: char) -> bool {
    ch.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&ch)
}

/// The decimal value of a Unicode decimal digit (category Nd), as `int()` reads it.
fn decimal(ch: char) -> Option<u8> {
    let n = u32::from(ch);
    // Every Nd block is ten consecutive code points starting at a zero.
    let at = DECIMAL_ZEROS.partition_point(|zero| zero + 9 < n);
    let zero = *DECIMAL_ZEROS.get(at)?;
    (zero <= n).then(|| (n - zero) as u8)
}

/// The message of Python's `UnicodeDecodeError` for bytes that are no UTF-8.
pub fn decode_error(data: &[u8], error: std::str::Utf8Error) -> String {
    let start = error.valid_up_to();
    let (end, reason) = match error.error_len() {
        None => (data.len(), "unexpected end of data"),
        Some(length) if matches!(data[start], 0xc2..=0xf4) => {
            (start + length, "invalid continuation byte")
        }
        Some(length) => (start + length, "invalid start byte"),
    };
    if end - start == 1 {
        format!(
            "'utf-8' codec can't decode byte 0x{:02x} in position {start}: {reason}",
            data[start]
        )
    } else {
        format!(
            "'utf-8' codec can't decode bytes in position {start}-{}: {reason}",
            end - 1
        )
    }
}

// Generated with Python 3.14 (Unicode 16.0.0): the first code point of every run of ten decimal
// digits (category Nd).
#[rustfmt::skip]
const DECIMAL_ZEROS: &[u32] = &[
    0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66,
    0xde6, 0xe50, 0xed0, 0xf20, 0x1040, 0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90,
    0x1b50, 0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0, 0xaa50, 0xabf0, 0xff10,
    0x104a0, 0x10d30, 0x10d40, 0x11066, 0x110f0, 0x11136, 0x111d0, 0x112f0, 0x11450, 0x114d0,
    0x11650, 0x116c0, 0x116d0, 0x116da, 0x11730, 0x118e0, 0x11950, 0x11bf0, 0x11c50, 0x11d50,
    0x11da0, 0x11f50, 0x16130, 0x16a60, 0x16ac0, 0x16b50, 0x16d70, 0x1ccf0, 0x1d7ce, 0x1d7d8,
    0x1d7e2, 0x1d7ec, 0x1d7f6, 0x1e140, 0x1e2f0, 0x1e4f0, 0x1e5f1, 0x1e950, 0x1fbf0,
];

// Generated with Python 3.14 (Unicode 16.0.0): the code points `str.isprintable()` refuses.
#[rustfmt::skip]
const NOT_PRINTABLE: &[(u32, u32)] = &[
    (0x0, 0x1f), (0x7f, 0xa0), (0xad, 0xad), (0x378, 0x379), (0x380, 0x383), (0x38b, 0x38b),
    (0x38d, 0x38d), (0x3a2, 0x3a2), (0x530, 0x530), (0x557, 0x558), (0x58b, 0x58c), (0x590, 0x590),
    (0x5c8, 0x5cf), (0x5eb, 0x5ee), (0x5f5, 0x605), (0x61c, 0x61c), (0x6dd, 0x6dd), (0x70e, 0x70f),
    (0x74b, 0x74c), (0x7b2, 0x7bf), (0x7fb, 0x7fc), (0x82e, 0x82f), (0x83f, 0x83f), (0x85c, 0x85d),
    (0x85f, 0x85f), (0x86b, 0x86f), (0x88f, 0x896), (0x8e2, 0x8e2), (0x984, 0x984), (0x98d, 0x98e),
    (0x991, 0x992), (0x9a9, 0x9a9), (0x9b1, 0x9b1), (0x9b3, 0x9b5), (0x9ba, 0x9bb), (0x9c5, 0x9c6),
    (0x9c9, 0x9ca), (0x9cf, 0x9d6), (0x9d8, 0x9db), (0x9de, 0x9de), (0x9e4, 0x9e5), (0x9ff, 0xa00),
    (0xa04, 0xa04), (0xa0b, 0xa0e), (0xa11, 0xa12), (0xa29, 0xa29), (0xa31, 0xa31), (0xa34, 0xa34),
    (0xa37, 0xa37), (0xa3a, 0xa3b), (0xa3d, 0xa3d), (0xa43, 0xa46), (0xa49, 0xa4a), (0xa4e, 0xa50),
    (0xa52, 0xa58), (0xa5d, 0xa5d), (0xa5f, 0xa65), (0xa77, 0xa80), (0xa84, 0xa84), (0xa8e, 0xa8e),
    (0xa92, 0xa92), (0xaa9, 0xaa9), (0xab1, 0xab1), (0xab4, 0xab4), (0xaba, 0xabb), (0xac6, 0xac6),
    (0xaca, 0xaca), (0xace, 0xacf), (0xad1, 0xadf), (0xae4, 0xae5), (0xaf2, 0xaf8), (0xb00, 0xb00),
    (0xb04, 0xb04), (0xb0d, 0xb0e), (0xb11, 0xb12), (0xb29, 0xb29), (0xb31, 0xb31), (0xb34, 0xb34),
    (0xb3a, 0xb3b), (0xb45, 0xb46), (0xb49, 0xb4a), (0xb4e, 0xb54), (0xb58, 0xb5b), (0xb5e, 0xb5e),
    (0xb64, 0xb65), (0xb78, 0xb81), (0xb84, 0xb84), (0xb8b, 0xb8d), (0xb91, 0xb91), (0xb96, 0xb98),
    (0xb9b, 0xb9b), (0xb9d, 0xb9d), (0xba0, 0xba2), (0xba5, 0xba7), (0xbab, 0xbad), (0xbba, 0xbbd),
    (0xbc3, 0xbc5), (0xbc9, 0xbc9), (0xbce, 0xbcf), (0xbd1, 0xbd6), (0xbd8, 0xbe5), (0xbfb, 0xbff),
    (0xc0d, 0xc0d), (0xc11, 0xc11), (0xc29, 0xc29), (0xc3a, 0xc3b), (0xc45, 0xc45), (0xc49, 0xc49),
    (0xc4e, 0xc54), (0xc57, 0xc57), (0xc5b, 0xc5c), (0xc5e, 0xc5f), (0xc64, 0xc65), (0xc70, 0xc76),
    (0xc8d, 0xc8d), (0xc91, 0xc91), (0xca9, 0xca9), (0xcb4, 0xcb4), (0xcba, 0xcbb), (0xcc5, 0xcc5),
    (0xcc9, 0xcc9), (0xcce, 0xcd4), (0xcd7, 0xcdc), (0xcdf, 0xcdf), (0xce4, 0xce5), (0xcf0, 0xcf0),
    (0xcf4, 0xcff), (0xd0d, 0xd0d), (0xd11, 0xd11), (0xd45, 0xd45), (0xd49, 0xd49), (0xd50, 0xd53),
    (0xd64, 0xd65), (0xd80, 0xd80), (0xd84, 0xd84), (0xd97, 0xd99), (0xdb2, 0xdb2), (0xdbc, 0xdbc),
    (0xdbe, 0xdbf), (0xdc7, 0xdc9), (0xdcb, 0xdce), (0xdd5, 0xdd5), (0xdd7, 0xdd7), (0xde0, 0xde5),
    (0xdf0, 0xdf1), (0xdf5, 0xe00), (0xe3b, 0xe3e), (0xe5c, 0xe80), (0xe83, 0xe83), (0xe85, 0xe85),
    (0xe8b, 0xe8b), (0xea4, 0xea4), (0xea6, 0xea6), (0xebe, 0xebf), (0xec5, 0xec5), (0xec7, 0xec7),
    (0xecf, 0xecf), (0xeda, 0xedb), (0xee0, 0xeff), (0xf48, 0xf48), (0xf6d, 0xf70), (0xf98, 0xf98),
    (0xfbd, 0xfbd), (0xfcd, 0xfcd), (0xfdb, 0xfff), (0x10c6, 0x10c6), (0x10c8, 0x10cc),
    (0x10ce, 0x10cf), (0x1249, 0x1249), (0x124e, 0x124f), (0x1257, 0x1257), (0x1259, 0x1259),
    (0x125e, 0x125f), (0x1289, 0x1289), (0x128e, 0x128f), (0x12b1, 0x12b1), (0x12b6, 0x12b7),
    (0x12bf, 0x12bf), (0x12c1, 0x12c1), (0x12c6, 0x12c7), (0x12d7, 0x12d7), (0x1311, 0x1311),
    (0x1316, 0x1317), (0x135b, 0x135c), (0x137d, 0x137f), (0x139a, 0x139f), (0x13f6, 0x13f7),
    (0x13fe, 0x13ff), (0x1680, 0x1680), (0x169d, 0x169f), (0x16f9, 0x16ff), (0x1716, 0x171e),
    (0x1737, 0x173f), (0x1754, 0x175f), (0x176d, 0x176d), (0x1771, 0x1771), (0x1774, 0x177f),
    (0x17de, 0x17df), (0x17ea, 0x17ef), (0x17fa, 0x17ff), (0x180e, 0x180e), (0x181a, 0x181f),
    (0x1879, 0x187f), (0x18ab, 0x18af), (0x18f6, 0x18ff), (0x191f, 0x191f), (0x192c, 0x192f),
    (0x193c, 0x193f), (0x1941, 0x1943), (0x196e, 0x196f), (0x1975, 0x197f), (0x19ac, 0x19af),
    (0x19ca, 0x19cf), (0x19db, 0x19dd), (0x1a1c, 0x1a1d), (0x1a5f, 0x1a5f), (0x1a7d, 0x1a7e),
    (0x1a8a, 0x1a8f), (0x1a9a, 0x1a9f), (0x1aae, 0x1aaf), (0x1acf, 0x1aff), (0x1b4d, 0x1b4d),
    (0x1bf4, 0x1bfb), (0x1c38, 0x1c3a), (0x1c4a, 0x1c4c), (0x1c8b, 0x1c8f), (0x1cbb, 0x1cbc),
    (0x1cc8, 0x1ccf), (0x1cfb, 0x1cff), (0x1f16, 0x1f17), (0x1f1e, 0x1f1f), (0x1f46, 0x1f47),
    (0x1f4e, 0x1f4f), (0x1f58, 0x1f58), (0x1f5a, 0x1f5a), (0x1f5c, 0x1f5c), (0x1f5e, 0x1f5e),
    (0x1f7e, 0x1f7f), (0x1fb5, 0x1fb5), (0x1fc5, 0x1fc5), (0x1fd4, 0x1fd5), (0x1fdc, 0x1fdc),
    (0x1ff0, 0x1ff1), (0x1ff5, 0x1ff5), (0x1fff, 0x200f), (0x2028, 0x202f), (0x205f, 0x206f),
    (0x2072, 0x2073), (0x208f, 0x208f), (0x209d, 0x209f), (0x20c1, 0x20cf), (0x20f1, 0x20ff),
    (0x218c, 0x218f), (0x242a, 0x243f), (0x244b, 0x245f), (0x2b74, 0x2b75), (0x2b96, 0x2b96),
    (0x2cf4, 0x2cf8), (0x2d26, 0x2d26), (0x2d28, 0x2d2c), (0x2d2e, 0x2d2f), (0x2d68, 0x2d6e),
    (0x2d71, 0x2d7e), (0x2d97, 0x2d9f), (0x2da7, 0x2da7), (0x2daf, 0x2daf), (0x2db7, 0x2db7),
    (0x2dbf, 0x2dbf), (0x2dc7, 0x2dc7), (0x2dcf, 0x2dcf), (0x2dd7, 0x2dd7), (0x2ddf, 0x2ddf),
    (0x2e5e, 0x2e7f), (0x2e9a, 0x2e9a), (0x2ef4, 0x2eff), (0x2fd6, 0x2fef), (0x3000, 0x3000),
    (0x3040, 0x3040), (0x3097, 0x3098), (0x3100, 0x3104), (0x3130, 0x3130), (0x318f, 0x318f),
    (0x31e6, 0x31ee), (0x321f, 0x321f), (0xa48d, 0xa48f), (0xa4c7, 0xa4cf), (0xa62c, 0xa63f),
    (0xa6f8, 0xa6ff), (0xa7ce, 0xa7cf), (0xa7d2, 0xa7d2), (0xa7d4, 0xa7d4), (0xa7dd, 0xa7f1),
    (0xa82d, 0xa82f), (0xa83a, 0xa83f), (0xa878, 0xa87f), (0xa8c6, 0xa8cd), (0xa8da, 0xa8df),
    (0xa954, 0xa95e), (0xa97d, 0xa97f), (0xa9ce, 0xa9ce), (0xa9da, 0xa9dd), (0xa9ff, 0xa9ff),
    (0xaa37, 0xaa3f), (0xaa4e, 0xaa4f), (0xaa5a, 0xaa5b), (0xaac3, 0xaada), (0xaaf7, 0xab00),
    (0xab07, 0xab08), (0xab0f, 0xab10), (0xab17, 0xab1f), (0xab27, 0xab27), (0xab2f, 0xab2f),
    (0xab6c, 0xab6f), (0xabee, 0xabef), (0xabfa, 0xabff), (0xd7a4, 0xd7af), (0xd7c7, 0xd7ca),
    (0xd7fc, 0xf8ff), (0xfa6e, 0xfa6f), (0xfada, 0xfaff), (0xfb07, 0xfb12), (0xfb18, 0xfb1c),
    (0xfb37, 0xfb37), (0xfb3d, 0xfb3d), (0xfb3f, 0xfb3f), (0xfb42, 0xfb42), (0xfb45, 0xfb45),
    (0xfbc3, 0xfbd2), (0xfd90, 0xfd91), (0xfdc8, 0xfdce), (0xfdd0, 0xfdef), (0xfe1a, 0xfe1f),
    (0xfe53, 0xfe53), (0xfe67, 0xfe67), (0xfe6c, 0xfe6f), (0xfe75, 0xfe75), (0xfefd, 0xff00),
    (0xffbf, 0xffc1), (0xffc8, 0xffc9), (0xffd0, 0xffd1), (0xffd8, 0xffd9), (0xffdd, 0xffdf),
    (0xffe7, 0xffe7), (0xffef, 0xfffb), (0xfffe, 0xffff), (0x1000c, 0x1000c), (0x10027, 0x10027),
    (0x1003b, 0x1003b), (0x1003e, 0x1003e), (0x1004e, 0x1004f), (0x1005e, 0x1007f),
    (0x100fb, 0x100ff), (0x10103, 0x10106), (0x10134, 0x10136), (0x1018f, 0x1018f),
    (0x1019d, 0x1019f), (0x101a1, 0x101cf), (0x101fe, 0x1027f), (0x1029d, 0x1029f),
    (0x102d1, 0x102df), (0x102fc, 0x102ff), (0x10324, 0x1032c), (0x1034b, 0x1034f),
    (0x1037b, 0x1037f), (0x1039e, 0x1039e), (0x103c4, 0x103c7), (0x103d6, 0x103ff),
    (0x1049e, 0x1049f), (0x104aa, 0x104af), (0x104d4, 0x104d7), (0x104fc, 0x104ff),
    (0x10528, 0x1052f), (0x10564, 0x1056e), (0x1057b, 0x1057b), (0x1058b, 0x1058b),
    (0x10593, 0x10593), (0x10596, 0x10596), (0x105a2, 0x105a2), (0x105b2, 0x105b2),
    (0x105ba, 0x105ba), (0x105bd, 0x105bf), (0x105f4, 0x105ff), (0x10737, 0x1073f),
    (0x10756, 0x1075f), (0x10768, 0x1077f), (0x10786, 0x10786), (0x107b1, 0x107b1),
    (0x107bb, 0x107ff), (0x10806, 0x10807), (0x10809, 0x10809), (0x10836, 0x10836),
    (0x10839, 0x1083b), (0x1083d, 0x1083e), (0x10856, 0x10856), (0x1089f, 0x108a6),
    (0x108b0, 0x108df), (0x108f3, 0x108f3), (0x108f6, 0x108fa), (0x1091c, 0x1091e),
    (0x1093a, 0x1093e), (0x10940, 0x1097f), (0x109b8, 0x109bb), (0x109d0, 0x109d1),
    (0x10a04, 0x10a04), (0x10a07, 0x10a0b), (0x10a14, 0x10a14), (0x10a18, 0x10a18),
    (0x10a36, 0x10a37), (0x10a3b, 0x10a3e), (0x10a49, 0x10a4f), (0x10a59, 0x10a5f),
    (0x10aa0, 0x10abf), (0x10ae7, 0x10aea), (0x10af7, 0x10aff), (0x10b36, 0x10b38),
    (0x10b56, 0x10b57), (0x10b73, 0x10b77), (0x10b92, 0x10b98), (0x10b9d, 0x10ba8),
    (0x10bb0, 0x10bff), (0x10c49, 0x10c7f), (0x10cb3, 0x10cbf), (0x10cf3, 0x10cf9),
    (0x10d28, 0x10d2f), (0x10d3a, 0x10d3f), (0x10d66, 0x10d68), (0x10d86, 0x10d8d),
    (0x10d90, 0x10e5f), (0x10e7f, 0x10e7f), (0x10eaa, 0x10eaa), (0x10eae, 0x10eaf),
    (0x10eb2, 0x10ec1), (0x10ec5, 0x10efb), (0x10f28, 0x10f2f), (0x10f5a, 0x10f6f),
    (0x10f8a, 0x10faf), (0x10fcc, 0x10fdf), (0x10ff7, 0x10fff), (0x1104e, 0x11051),
    (0x11076, 0x1107e), (0x110bd, 0x110bd), (0x110c3, 0x110cf), (0x110e9, 0x110ef),
    (0x110fa, 0x110ff), (0x11135, 0x11135), (0x11148, 0x1114f), (0x11177, 0x1117f),
    (0x111e0, 0x111e0), (0x111f5, 0x111ff), (0x11212, 0x11212), (0x11242, 0x1127f),
    (0x11287, 0x11287), (0x11289, 0x11289), (0x1128e, 0x1128e), (0x1129e, 0x1129e),
    (0x112aa, 0x112af), (0x112eb, 0x112ef), (0x112fa, 0x112ff), (0x11304, 0x11304),
    (0x1130d, 0x1130e), (0x11311, 0x11312), (0x11329, 0x11329), (0x11331, 0x11331),
    (0x11334, 0x11334), (0x1133a, 0x1133a), (0x11345, 0x11346), (0x11349, 0x1134a),
    (0x1134e, 0x1134f), (0x11351, 0x11356), (0x11358, 0x1135c), (0x11364, 0x11365),
    (0x1136d, 0x1136f), (0x11375, 0x1137f), (0x1138a, 0x1138a), (0x1138c, 0x1138d),
    (0x1138f, 0x1138f), (0x113b6, 0x113b6), (0x113c1, 0x113c1), (0x113c3, 0x113c4),
    (0x113c6, 0x113c6), (0x113cb, 0x113cb), (0x113d6, 0x113d6), (0x113d9, 0x113e0),
    (0x113e3, 0x113ff), (0x1145c, 0x1145c), (0x11462, 0x1147f), (0x114c8, 0x114cf),
    (0x114da, 0x1157f), (0x115b6, 0x115b7), (0x115de, 0x115ff), (0x11645, 0x1164f),
    (0x1165a, 0x1165f), (0x1166d, 0x1167f), (0x116ba, 0x116bf), (0x116ca, 0x116cf),
    (0x116e4, 0x116ff), (0x1171b, 0x1171c), (0x1172c, 0x1172f), (0x11747, 0x117ff),
    (0x1183c, 0x1189f), (0x118f3, 0x118fe), (0x11907, 0x11908), (0x1190a, 0x1190b),
    (0x11914, 0x11914), (0x11917, 0x11917), (0x11936, 0x11936), (0x11939, 0x1193a),
    (0x11947, 0x1194f), (0x1195a, 0x1199f), (0x119a8, 0x119a9), (0x119d8, 0x119d9),
    (0x119e5, 0x119ff), (0x11a48, 0x11a4f), (0x11aa3, 0x11aaf), (0x11af9, 0x11aff),
    (0x11b0a, 0x11bbf), (0x11be2, 0x11bef), (0x11bfa, 0x11bff), (0x11c09, 0x11c09),
    (0x11c37, 0x11c37), (0x11c46, 0x11c4f), (0x11c6d, 0x11c6f), (0x11c90, 0x11c91),
    (0x11ca8, 0x11ca8), (0x11cb7, 0x11cff), (0x11d07, 0x11d07), (0x11d0a, 0x11d0a),
    (0x11d37, 0x11d39), (0x11d3b, 0x11d3b), (0x11d3e, 0x11d3e), (0x11d48, 0x11d4f),
    (0x11d5a, 0x11d5f), (0x11d66, 0x11d66), (0x11d69, 0x11d69), (0x11d8f, 0x11d8f),
    (0x11d92, 0x11d92), (0x11d99, 0x11d9f), (0x11daa, 0x11edf), (0x11ef9, 0x11eff),
    (0x11f11, 0x11f11), (0x11f3b, 0x11f3d), (0x11f5b, 0x11faf), (0x11fb1, 0x11fbf),
    (0x11ff2, 0x11ffe), (0x1239a, 0x123ff), (0x1246f, 0x1246f), (0x12475, 0x1247f),
    (0x12544, 0x12f8f), (0x12ff3, 0x12fff), (0x13430, 0x1343f), (0x13456, 0x1345f),
    (0x143fb, 0x143ff), (0x14647, 0x160ff), (0x1613a, 0x167ff), (0x16a39, 0x16a3f),
    (0x16a5f, 0x16a5f), (0x16a6a, 0x16a6d), (0x16abf, 0x16abf), (0x16aca, 0x16acf),
    (0x16aee, 0x16aef), (0x16af6, 0x16aff), (0x16b46, 0x16b4f), (0x16b5a, 0x16b5a),
    (0x16b62, 0x16b62), (0x16b78, 0x16b7c), (0x16b90, 0x16d3f), (0x16d7a, 0x16e3f),
    (0x16e9b, 0x16eff), (0x16f4b, 0x16f4e), (0x16f88, 0x16f8e), (0x16fa0, 0x16fdf),
    (0x16fe5, 0x16fef), (0x16ff2, 0x16fff), (0x187f8, 0x187ff), (0x18cd6, 0x18cfe),
    (0x18d09, 0x1afef), (0x1aff4, 0x1aff4), (0x1affc, 0x1affc), (0x1afff, 0x1afff),
    (0x1b123, 0x1b131), (0x1b133, 0x1b14f), (0x1b153, 0x1b154), (0x1b156, 0x1b163),
    (0x1b168, 0x1b16f), (0x1b2fc, 0x1bbff), (0x1bc6b, 0x1bc6f), (0x1bc7d, 0x1bc7f),
    (0x1bc89, 0x1bc8f), (0x1bc9a, 0x1bc9b), (0x1bca0, 0x1cbff), (0x1ccfa, 0x1ccff),
    (0x1ceb4, 0x1ceff), (0x1cf2e, 0x1cf2f), (0x1cf47, 0x1cf4f), (0x1cfc4, 0x1cfff),
    (0x1d0f6, 0x1d0ff), (0x1d127, 0x1d128), (0x1d173, 0x1d17a), (0x1d1eb, 0x1d1ff),
    (0x1d246, 0x1d2bf), (0x1d2d4, 0x1d2df), (0x1d2f4, 0x1d2ff), (0x1d357, 0x1d35f),
    (0x1d379, 0x1d3ff), (0x1d455, 0x1d455), (0x1d49d, 0x1d49d), (0x1d4a0, 0x1d4a1),
    (0x1d4a3, 0x1d4a4), (0x1d4a7, 0x1d4a8), (0x1d4ad, 0x1d4ad), (0x1d4ba, 0x1d4ba),
    (0x1d4bc, 0x1d4bc), (0x1d4c4, 0x1d4c4), (0x1d506, 0x1d506), (0x1d50b, 0x1d50c),
    (0x1d515, 0x1d515), (0x1d51d, 0x1d51d), (0x1d53a, 0x1d53a), (0x1d53f, 0x1d53f),
    (0x1d545, 0x1d545), (0x1d547, 0x1d549), (0x1d551, 0x1d551), (0x1d6a6, 0x1d6a7),
    (0x1d7cc, 0x1d7cd), (0x1da8c, 0x1da9a), (0x1daa0, 0x1daa0), (0x1dab0, 0x1deff),
    (0x1df1f, 0x1df24), (0x1df2b, 0x1dfff), (0x1e007, 0x1e007), (0x1e019, 0x1e01a),
    (0x1e022, 0x1e022), (0x1e025, 0x1e025), (0x1e02b, 0x1e02f), (0x1e06e, 0x1e08e),
    (0x1e090, 0x1e0ff), (0x1e12d, 0x1e12f), (0x1e13e, 0x1e13f), (0x1e14a, 0x1e14d),
    (0x1e150, 0x1e28f), (0x1e2af, 0x1e2bf), (0x1e2fa, 0x1e2fe), (0x1e300, 0x1e4cf),
    (0x1e4fa, 0x1e5cf), (0x1e5fb, 0x1e5fe), (0x1e600, 0x1e7df), (0x1e7e7, 0x1e7e7),
    (0x1e7ec, 0x1e7ec), (0x1e7ef, 0x1e7ef), (0x1e7ff, 0x1e7ff), (0x1e8c5, 0x1e8c6),
    (0x1e8d7, 0x1e8ff), (0x1e94c, 0x1e94f), (0x1e95a, 0x1e95d), (0x1e960, 0x1ec70),
    (0x1ecb5, 0x1ed00), (0x1ed3e, 0x1edff), (0x1ee04, 0x1ee04), (0x1ee20, 0x1ee20),
    (0x1ee23, 0x1ee23), (0x1ee25, 0x1ee26), (0x1ee28, 0x1ee28), (0x1ee33, 0x1ee33),
    (0x1ee38, 0x1ee38), (0x1ee3a, 0x1ee3a), (0x1ee3c, 0x1ee41), (0x1ee43, 0x1ee46),
    (0x1ee48, 0x1ee48), (0x1ee4a, 0x1ee4a), (0x1ee4c, 0x1ee4c), (0x1ee50, 0x1ee50),
    (0x1ee53, 0x1ee53), (0x1ee55, 0x1ee56), (0x1ee58, 0x1ee58), (0x1ee5a, 0x1ee5a),
    (0x1ee5c, 0x1ee5c), (0x1ee5e, 0x1ee5e), (0x1ee60, 0x1ee60), (0x1ee63, 0x1ee63),
    (0x1ee65, 0x1ee66), (0x1ee6b, 0x1ee6b), (0x1ee73, 0x1ee73), (0x1ee78, 0x1ee78),
    (0x1ee7d, 0x1ee7d), (0x1ee7f, 0x1ee7f), (0x1ee8a, 0x1ee8a), (0x1ee9c, 0x1eea0),
    (0x1eea4, 0x1eea4), (0x1eeaa, 0x1eeaa), (0x1eebc, 0x1eeef), (0x1eef2, 0x1efff),
    (0x1f02c, 0x1f02f), (0x1f094, 0x1f09f), (0x1f0af, 0x1f0b0), (0x1f0c0, 0x1f0c0),
    (0x1f0d0, 0x1f0d0), (0x1f0f6, 0x1f0ff), (0x1f1ae, 0x1f1e5), (0x1f203, 0x1f20f),
    (0x1f23c, 0x1f23f), (0x1f249, 0x1f24f), (0x1f252, 0x1f25f), (0x1f266, 0x1f2ff),
    (0x1f6d8, 0x1f6db), (0x1f6ed, 0x1f6ef), (0x1f6fd, 0x1f6ff), (0x1f777, 0x1f77a),
    (0x1f7da, 0x1f7df), (0x1f7ec, 0x1f7ef), (0x1f7f1, 0x1f7ff), (0x1f80c, 0x1f80f),
    (0x1f848, 0x1f84f), (0x1f85a, 0x1f85f), (0x1f888, 0x1f88f), (0x1f8ae, 0x1f8af),
    (0x1f8bc, 0x1f8bf), (0x1f8c2, 0x1f8ff), (0x1fa54, 0x1fa5f), (0x1fa6e, 0x1fa6f),
    (0x1fa7d, 0x1fa7f), (0x1fa8a, 0x1fa8e), (0x1fac7, 0x1facd), (0x1fadd, 0x1fade),
    (0x1faea, 0x1faef), (0x1faf9, 0x1faff), (0x1fb93, 0x1fb93), (0x1fbfa, 0x1ffff),
    (0x2a6e0, 0x2a6ff), (0x2b73a, 0x2b73f), (0x2b81e, 0x2b81f), (0x2cea2, 0x2ceaf),
    (0x2ebe1, 0x2ebef), (0x2ee5e, 0x2f7ff), (0x2fa1e, 0x2ffff), (0x3134b, 0x3134f),
    (0x323b0, 0xe00ff), (0xe01f0, 0x10ffff),
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn floats_print_as_python_repr() {
        for (value, text) in [
            (1.0, "1.0"),
            (0.1, "0.1"),
            (1e16, "1e+16"),
            (1e15, "1000000000000000.0"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (-0.0, "-0.0"),
            (1700000000.5, "1700000000.5"),
            (5e-324, "5e-324"),
            (1.7976931348623157e308, "1.7976931348623157e+308"),
            (123456.789, "123456.789"),
            (1e22, "1e+22"),
            (9999999999999998.0, "9999999999999998.0"),
        ] {
            assert_eq!(float_repr(value), text);
        }
    }

    #[test]
    fn json_reads_and_writes_as_python() {
        let value = loads(r#"{"b": 1, "a": [1.5, -0, 1e2, "ä😀", null, true], "b": 2}"#).unwrap();
        assert_eq!(
            dumps(&value, false),
            "{\"b\": 2, \"a\": [1.5, 0, 100.0, \"ä😀\", null, true]}"
        );
        assert_eq!(
            dumps(&value, true),
            "{\"b\": 2, \"a\": [1.5, 0, 100.0, \"\\u00e4\\ud83d\\ude00\", null, true]}"
        );
        for invalid in [
            "",
            "{",
            "[1,]",
            "{\"a\" 1}",
            "01",
            "\"a\u{1}\"",
            "1.",
            ".5",
            "[1] x",
        ] {
            assert_eq!(loads(invalid), None, "{invalid:?}");
        }
        assert_eq!(
            loads(" 12345678901234567890123 "),
            Some(Py::Int("12345678901234567890123".into()))
        );
        assert_eq!(loads("1E400"), Some(Py::Float(f64::INFINITY)));
        assert_eq!(dumps(&Py::Float(f64::NEG_INFINITY), true), "-Infinity");
    }

    #[test]
    fn values_print_as_python_str() {
        let value =
            loads("[1, \"it's\", \"say \\\"x\\\"\", null, true, 2.5, [], {\"k\": \"v\"}, \"\\u0085ä😀\\u200b\"]")
                .unwrap();
        assert_eq!(
            py_str(&value),
            "[1, \"it's\", 'say \"x\"', None, True, 2.5, [], {'k': 'v'}, '\\x85ä😀\\u200b']"
        );
    }

    #[test]
    fn uuids_read_as_python_reads_them() {
        let id = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";
        for (value, expected) in [
            (id.to_uppercase(), Some(id)),
            (format!("{{{id}}}"), Some(id)),
            (format!("urn:uuid:{id}"), Some(id)),
            (id.replace('-', ""), Some(id)),
            ("abc".into(), None),
            (
                " a1b2c3d4e5f4a6b8c7d9e0f1a2b3c4d".into(),
                Some("0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"),
            ),
            (
                "0a1b2c3d4e5f4a6b_c7d9e0f1a2b3c4d".into(),
                Some("00a1b2c3-d4e5-f4a6-bc7d-9e0f1a2b3c4d"),
            ),
            ("0a1b2c3d4e5f4a6b__7d9e0f1a2b3c4d".into(), None),
            ("-0a1b2c3d4e5f4a6b8c7d9e0f1a2b3c4".into(), None),
            ("-0000000000000000000000000000000".into(), None),
            (
                "+0000000000000000000000000000000".into(),
                Some("00000000-0000-0000-0000-000000000000"),
            ),
            (
                "0x0a1b2c3d4e5f4a6b8c7d9e0f1a2b3c".into(),
                Some("000a1b2c-3d4e-5f4a-6b8c-7d9e0f1a2b3c"),
            ),
            ("٠a1b2c3d4e5f4a6b8c7d9e0f1a2b3c4d".into(), Some(id)),
        ] {
            assert_eq!(uuid(&value).as_deref(), expected, "{value}");
        }
    }

    #[test]
    fn decode_errors_read_as_python_reports_them() {
        for (data, message) in [
            (
                &b"ab\xff"[..],
                "'utf-8' codec can't decode byte 0xff in position 2: invalid start byte",
            ),
            (
                b"ab\xc3",
                "'utf-8' codec can't decode byte 0xc3 in position 2: unexpected end of data",
            ),
            (
                b"a\xe2\x82",
                "'utf-8' codec can't decode bytes in position 1-2: unexpected end of data",
            ),
            (
                b"a\xe2(\xa1",
                "'utf-8' codec can't decode byte 0xe2 in position 1: invalid continuation byte",
            ),
            (
                b"\xed\xa0\x80",
                "'utf-8' codec can't decode byte 0xed in position 0: invalid continuation byte",
            ),
            (
                b"\xc0\x80",
                "'utf-8' codec can't decode byte 0xc0 in position 0: invalid start byte",
            ),
        ] {
            let error = std::str::from_utf8(data).unwrap_err();
            assert_eq!(decode_error(data, error), message);
        }
    }
}

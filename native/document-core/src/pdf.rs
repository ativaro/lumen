//! Lumen's own PDF object reader: syntax, filters and file structure (PDF Reference 1.7, chapter 3).
//! Unsupported features are errors, never a request to repair or guess the file. The checks and
//! their messages follow `files/lumen_pdf.py`, so both readers can be compared file by file.
use std::cell::{Cell, RefCell};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::rc::Rc;

pub const MAX_FILE: usize = 512 * 1024 * 1024;
pub const MAX_STREAM: usize = 64 * 1024 * 1024;
pub const MAX_OBJECTS: i64 = 200_000;
const MAX_DEPTH: usize = 64;
const MAX_ITEMS: usize = 1_000_000;

#[derive(Debug, Clone, PartialEq)]
pub enum Error {
    /// The file is damaged or outside a limit.
    Pdf(String),
    /// The file uses something this reader does not do yet.
    Unsupported(String),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Error::Pdf(text) | Error::Unsupported(text) => f.write_str(text),
        }
    }
}

pub type Outcome<T> = Result<T, Error>;

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Ref {
    pub number: i64,
    pub generation: i64,
}

pub type Dict = BTreeMap<String, Value>;

#[derive(Debug)]
pub struct Stream {
    pub attrs: Dict,
    pub raw: Vec<u8>,
}

/// A PDF object. Containers are shared, so a value is cheap to pass on and keeps its identity.
#[derive(Debug, Clone)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Real(f64),
    Text(Rc<Vec<u8>>),
    Name(Rc<str>),
    Array(Rc<Vec<Value>>),
    Dict(Rc<Dict>),
    Stream(Rc<Stream>),
    Ref(Ref),
    Operator(Rc<str>),
}

impl Value {
    pub fn name(&self) -> Option<&str> {
        if let Value::Name(name) = self {
            Some(name)
        } else {
            None
        }
    }
    pub fn dict(&self) -> Option<&Rc<Dict>> {
        if let Value::Dict(dict) = self {
            Some(dict)
        } else {
            None
        }
    }
    pub fn array(&self) -> Option<&Rc<Vec<Value>>> {
        if let Value::Array(array) = self {
            Some(array)
        } else {
            None
        }
    }
    pub fn number(&self) -> Option<f64> {
        match self {
            Value::Int(value) => Some(*value as f64),
            Value::Real(value) => Some(*value),
            _ => None,
        }
    }
    fn is_null(&self) -> bool {
        matches!(self, Value::Null)
    }
    /// Python truthiness, for the places where the Python reader says `value or default`.
    fn truthy(&self) -> bool {
        match self {
            Value::Null => false,
            Value::Bool(value) => *value,
            Value::Int(value) => *value != 0,
            Value::Real(value) => *value != 0.0,
            Value::Text(value) => !value.is_empty(),
            Value::Name(value) | Value::Operator(value) => !value.is_empty(),
            Value::Array(value) => !value.is_empty(),
            Value::Dict(value) => !value.is_empty(),
            Value::Stream(_) | Value::Ref(_) => true,
        }
    }
}

/// An integer inside its limits; anything else is an error.
pub fn integer(value: &Value, low: i64, high: i64) -> Outcome<i64> {
    match value {
        Value::Int(number) if (low..=high).contains(number) => Ok(*number),
        _ => bad("Ungültige PDF-Ganzzahl oder überschrittenes Limit."),
    }
}

fn space(byte: u8) -> bool {
    matches!(byte, 0 | b'\t' | b'\n' | 0x0c | b'\r' | b' ')
}

fn delimiter(byte: u8) -> bool {
    space(byte) || b"()<>[]{}/%".contains(&byte)
}

pub struct Syntax<'a> {
    pub data: &'a [u8],
    pub pos: usize,
    items: usize,
}

impl<'a> Syntax<'a> {
    pub fn new(data: &'a [u8], position: usize) -> Self {
        Syntax {
            data,
            pos: position,
            items: 0,
        }
    }

    pub fn skip(&mut self) {
        while self.pos < self.data.len() {
            if space(self.data[self.pos]) {
                self.pos += 1;
            } else if self.data[self.pos] == b'%' {
                self.pos = match self.data[self.pos..]
                    .iter()
                    .position(|b| *b == b'\r' || *b == b'\n')
                {
                    Some(end) => self.pos + end + 1,
                    None => self.data.len(),
                };
            } else {
                break;
            }
        }
    }

    pub fn word(&mut self) -> Outcome<&'a [u8]> {
        self.skip();
        let start = self.pos;
        while self.pos < self.data.len() && !delimiter(self.data[self.pos]) {
            self.pos += 1;
        }
        if self.pos == start {
            return bad("Unerwartetes PDF-Zeichen.");
        }
        Ok(&self.data[start..self.pos])
    }

    pub fn expect(&mut self, expected: &str) -> Outcome<()> {
        if self.word()? != expected.as_bytes() {
            return Err(Error::Pdf(format!("Ungültige PDF-Struktur: {expected}")));
        }
        Ok(())
    }

    pub fn value(&mut self) -> Outcome<Value> {
        self.nested(0)
    }

    fn nested(&mut self, depth: usize) -> Outcome<Value> {
        if depth > MAX_DEPTH || self.items >= MAX_ITEMS {
            return bad("PDF-Verschachtelung oder Objektgröße überschritten.");
        }
        self.items += 1;
        self.skip();
        let data = self.data;
        let start = self.pos;
        if start >= data.len() {
            return bad("Unerwartetes PDF-Ende.");
        }
        if data[start..].starts_with(b"<<") {
            self.pos += 2;
            let mut result = Dict::new();
            loop {
                self.skip();
                if data[self.pos.min(data.len())..].starts_with(b">>") {
                    self.pos += 2;
                    return Ok(Value::Dict(Rc::new(result)));
                }
                let key = match self.nested(depth + 1)? {
                    Value::Name(key) if !result.contains_key(&*key) => key,
                    _ => return bad("Ungültiger oder doppelter PDF-Dictionary-Schlüssel."),
                };
                let value = self.nested(depth + 1)?;
                result.insert(key.to_string(), value);
            }
        }
        let first = data[start];
        self.pos += 1;
        match first {
            b'[' => {
                let mut result = Vec::new();
                loop {
                    self.skip();
                    if self.pos < data.len() && data[self.pos] == b']' {
                        self.pos += 1;
                        return Ok(Value::Array(Rc::new(result)));
                    }
                    result.push(self.nested(depth + 1)?);
                }
            }
            b'(' => self.literal(),
            b'<' => {
                let Some(end) = data[self.pos..].iter().position(|b| *b == b'>') else {
                    return bad("Nicht abgeschlossene PDF-Hexzeichenfolge.");
                };
                let raw: Vec<u8> = data[self.pos..self.pos + end]
                    .iter()
                    .copied()
                    .filter(|b| !space(*b))
                    .collect();
                if raw.len() > MAX_STREAM * 2 {
                    return bad("PDF-Hexzeichenfolge zu groß.");
                }
                self.pos += end + 1;
                match hex(&raw) {
                    Some(bytes) => Ok(Value::Text(Rc::new(bytes))),
                    None => bad("Ungültige PDF-Hexzeichenfolge."),
                }
            }
            b'/' => {
                let mut end = self.pos;
                while end < data.len() && !delimiter(data[end]) {
                    end += 1;
                }
                let raw = &data[self.pos..end];
                self.pos = end;
                let mut name = String::with_capacity(raw.len());
                let mut index = 0;
                while index < raw.len() {
                    if raw[index] == b'#' {
                        let code = raw.get(index + 1..index + 3).and_then(hex).filter(|bytes| {
                            bytes.len() == 1
                                && raw[index + 1..index + 3].iter().all(u8::is_ascii_hexdigit)
                        });
                        let Some(code) = code else {
                            return bad("Ungültiger PDF-Name.");
                        };
                        name.push(code[0] as char);
                        index += 3;
                    } else {
                        name.push(raw[index] as char);
                        index += 1;
                    }
                }
                Ok(Value::Name(name.into()))
            }
            _ => {
                self.pos = start;
                let token = self.word()?;
                self.token(token)
            }
        }
    }

    fn literal(&mut self) -> Outcome<Value> {
        let data = self.data;
        let mut result = Vec::new();
        let mut nesting = 1;
        while self.pos < data.len() {
            let mut byte = data[self.pos];
            self.pos += 1;
            match byte {
                b'\\' => {
                    if self.pos == data.len() {
                        break;
                    }
                    byte = data[self.pos];
                    self.pos += 1;
                    if byte == b'\r' || byte == b'\n' {
                        if byte == b'\r' && data.get(self.pos) == Some(&b'\n') {
                            self.pos += 1;
                        }
                        continue;
                    }
                    if (b'0'..=b'7').contains(&byte) {
                        let mut code = u32::from(byte - b'0');
                        for _ in 0..2 {
                            match data.get(self.pos) {
                                Some(next) if (b'0'..=b'7').contains(next) => {
                                    code = code * 8 + u32::from(next - b'0');
                                    self.pos += 1;
                                }
                                _ => break,
                            }
                        }
                        result.push((code & 255) as u8);
                    } else {
                        result.push(match byte {
                            b'n' => 10,
                            b'r' => 13,
                            b't' => 9,
                            b'b' => 8,
                            b'f' => 12,
                            other => other,
                        });
                    }
                }
                b'(' => {
                    nesting += 1;
                    if nesting > MAX_DEPTH {
                        return bad("PDF-Zeichenfolge zu tief verschachtelt.");
                    }
                    result.push(byte);
                }
                b')' => {
                    nesting -= 1;
                    if nesting == 0 {
                        return Ok(Value::Text(Rc::new(result)));
                    }
                    result.push(byte);
                }
                b'\r' => {
                    if data.get(self.pos) == Some(&b'\n') {
                        self.pos += 1;
                    }
                    result.push(10);
                }
                other => result.push(other),
            }
            if result.len() > MAX_STREAM {
                return bad("PDF-Zeichenfolge zu groß.");
            }
        }
        bad("Nicht abgeschlossene PDF-Zeichenfolge.")
    }

    fn token(&mut self, token: &[u8]) -> Outcome<Value> {
        match token {
            b"true" => return Ok(Value::Bool(true)),
            b"false" => return Ok(Value::Bool(false)),
            b"null" => return Ok(Value::Null),
            _ => {}
        }
        let unsigned = token
            .strip_prefix(b"+")
            .or_else(|| token.strip_prefix(b"-"))
            .unwrap_or(token);
        // Presentation exporters sometimes append a signed tail to a zero real. Match established
        // readers' zero-prefix recovery; never reinterpret an integer, a reference or an operator so.
        if token.len() <= 100 && unsigned.starts_with(b"0.0") {
            let zeros = unsigned[2..].iter().take_while(|b| **b == b'0').count();
            let tail = &unsigned[2 + zeros..];
            if tail.len() >= 2
                && (tail[0] == b'+' || tail[0] == b'-')
                && tail[1..].iter().all(u8::is_ascii_digit)
            {
                return Ok(Value::Real(0.0));
            }
        }
        let digits = unsigned.iter().filter(|b| b.is_ascii_digit()).count();
        let dots = unsigned.iter().filter(|b| **b == b'.').count();
        if digits > 0 && dots <= 1 && digits + dots == unsigned.len() {
            if token.len() > 100 {
                return bad("PDF-Zahl zu lang.");
            }
            let text = std::str::from_utf8(token).unwrap_or("");
            if dots == 1 {
                return match text.parse::<f64>() {
                    Ok(number) if number.is_finite() => Ok(Value::Real(number)),
                    _ => bad("Ungültige PDF-Zahl."),
                };
            }
            let Ok(number) = text.parse::<i64>() else {
                return bad("Ungültige PDF-Zahl.");
            };
            if number >= 0 {
                let saved = self.pos;
                // PDF comments are whitespace, including between reference tokens.
                if let Ok(second) = self.word()
                    && second.len() <= 5
                    && second.iter().all(u8::is_ascii_digit)
                    && self.word().is_ok_and(|third| third == b"R")
                    && (1..=MAX_OBJECTS).contains(&number)
                {
                    let generation = second
                        .iter()
                        .fold(0i64, |sum, digit| sum * 10 + i64::from(digit - b'0'));
                    if generation <= 65535 {
                        return Ok(Value::Ref(Ref { number, generation }));
                    }
                }
                self.pos = saved;
            }
            return Ok(Value::Int(number));
        }
        match std::str::from_utf8(token) {
            Ok(text) if text.is_ascii() => Ok(Value::Operator(text.into())),
            _ => bad("Ungültiger PDF-Operator."),
        }
    }
}

/// Hexadecimal digits to bytes; an odd digit count ends in an implied zero.
fn hex(raw: &[u8]) -> Option<Vec<u8>> {
    let digit = |byte: u8| (byte as char).to_digit(16).map(|d| d as u8);
    let mut bytes = Vec::with_capacity(raw.len() / 2 + 1);
    for pair in raw.chunks(2) {
        bytes.push(digit(pair[0])? << 4 | if pair.len() == 2 { digit(pair[1])? } else { 0 });
    }
    Some(bytes)
}

fn bounded(data: Vec<u8>) -> Outcome<Vec<u8>> {
    if data.len() > MAX_STREAM {
        return bad("Dekomprimierter PDF-Stream zu groß.");
    }
    Ok(data)
}

fn predict(data: Vec<u8>, params: &Dict) -> Outcome<Vec<u8>> {
    let option = |key: &str, default: i64| params.get(key).cloned().unwrap_or(Value::Int(default));
    let predictor = option("Predictor", 1);
    if matches!(predictor, Value::Int(1)) || predictor.number() == Some(1.0) {
        return Ok(data);
    }
    let columns = integer(&option("Columns", 1), 1, 100_000)? as usize;
    let colors = integer(&option("Colors", 1), 1, 32)? as usize;
    let bits = match option("BitsPerComponent", 8) {
        Value::Int(bits @ (1 | 2 | 4 | 8 | 16)) => bits as usize,
        _ => {
            return Err(Error::Unsupported(
                "PDF-Prädiktor mit unbekannter Bittiefe.".into(),
            ));
        }
    };
    let stride = (columns * colors * bits).div_ceil(8);
    let bpp = (colors * bits).div_ceil(8).max(1);
    if stride > MAX_STREAM {
        return bad("PDF-Bildzeile zu groß.");
    }
    let predictor = predictor.number().unwrap_or(0.0);
    if predictor == 2.0 {
        if bits != 8 {
            return Err(Error::Unsupported(
                "TIFF-PDF-Prädiktor unterstützt derzeit 8 Bit.".into(),
            ));
        }
        if !data.len().is_multiple_of(stride) {
            return bad("Unvollständige TIFF-PDF-Zeile.");
        }
        let mut result = data;
        for row in result.chunks_mut(stride) {
            for column in bpp..stride {
                row[column] = row[column].wrapping_add(row[column - bpp]);
            }
        }
        return Ok(result);
    }
    if !(10.0..=15.0).contains(&predictor) {
        return Err(Error::Unsupported("Unbekannter PDF-Prädiktor.".into()));
    }
    if !data.len().is_multiple_of(stride + 1) {
        return bad("Unvollständige PNG-PDF-Zeile.");
    }
    let mut result = Vec::with_capacity(data.len());
    let mut previous = vec![0u8; stride];
    for line in data.chunks(stride + 1) {
        let kind = line[0];
        let mut row = line[1..].to_vec();
        if kind > 4 {
            return bad("Ungültiger PNG-PDF-Prädiktor.");
        }
        for i in 0..stride {
            let left = if i >= bpp { i32::from(row[i - bpp]) } else { 0 };
            let up = i32::from(previous[i]);
            let corner = if i >= bpp {
                i32::from(previous[i - bpp])
            } else {
                0
            };
            let value = match kind {
                1 => left,
                2 => up,
                3 => (left + up) / 2,
                4 => {
                    let p = left + up - corner;
                    let distances = [(p - left).abs(), (p - up).abs(), (p - corner).abs()];
                    let nearest = distances.iter().min().copied().unwrap_or(0);
                    [left, up, corner][distances.iter().position(|d| *d == nearest).unwrap_or(0)]
                }
                _ => 0,
            };
            row[i] = ((i32::from(row[i]) + value) & 255) as u8;
        }
        result.extend_from_slice(&row);
        previous = row;
    }
    Ok(result)
}

/// zlib data, bounded. Complete data whose closing checksum a writer left out is accepted; data
/// cut short, or with a wrong checksum, is not.
fn inflate(data: &[u8]) -> Outcome<Vec<u8>> {
    use flate2::{Decompress, FlushDecompress, Status};
    let run = |decoder: &mut Decompress, input: &[u8]| -> Result<(Vec<u8>, bool), ()> {
        let mut output = Vec::with_capacity((input.len() * 4).clamp(4096, MAX_STREAM + 1));
        loop {
            let consumed = decoder.total_in() as usize;
            if output.len() == output.capacity() {
                if output.len() > MAX_STREAM {
                    return Ok((output, false));
                }
                output.reserve((output.len()).clamp(4096, MAX_STREAM + 1 - output.len()));
            }
            match decoder.decompress_vec(&input[consumed..], &mut output, FlushDecompress::None) {
                Ok(Status::StreamEnd) => return Ok((output, true)),
                Ok(_)
                    if decoder.total_in() as usize == input.len()
                        && output.len() < output.capacity() =>
                {
                    return Ok((output, false));
                }
                Ok(_) => {}
                Err(_) => return Err(()),
            }
        }
    };
    let (output, ended) = run(&mut Decompress::new(true), data)
        .map_err(|_| Error::Pdf("Beschädigter PDF-Stream.".into()))?;
    let output = bounded(output)?;
    if ended {
        return Ok(output);
    }
    // The stream did not end. It is complete exactly when the Deflate data itself ends and only
    // (part of) the four checksum bytes is missing.
    if data.len() >= 2 {
        let mut raw = Decompress::new(false);
        if let Ok((_, true)) = run(&mut raw, &data[2..])
            && data.len() - 2 - (raw.total_in() as usize) < 4
        {
            return Ok(output);
        }
    }
    bad("Beschädigter oder zu großer Flate-PDF-Stream.")
}

fn lzw(data: &[u8], early: i64) -> Outcome<Vec<u8>> {
    let fresh = || {
        (0..=255u8)
            .map(|byte| vec![byte])
            .chain([Vec::new(), Vec::new()])
            .collect::<Vec<_>>()
    };
    let (mut bit, mut width, mut table, mut result) = (0usize, 9usize, fresh(), Vec::new());
    let mut previous: Option<Vec<u8>> = None;
    let mut ended = false;
    while bit + width <= data.len() * 8 {
        let (start, shift) = (bit / 8, bit % 8);
        let count = (shift + width).div_ceil(8);
        let chunk = data[start..start + count]
            .iter()
            .fold(0u32, |sum, byte| sum << 8 | u32::from(*byte));
        let code = ((chunk >> (count * 8 - shift - width)) & ((1 << width) - 1)) as usize;
        bit += width;
        if code == 257 {
            ended = true;
            break;
        }
        if code == 256 {
            table.truncate(258);
            width = 9;
            previous = None;
            continue;
        }
        let entry = if code < table.len() {
            table[code].clone()
        } else if let (true, Some(previous)) = (code == table.len(), &previous) {
            let mut entry = previous.clone();
            entry.push(previous[0]);
            entry
        } else {
            return bad("Ungültiger LZW-PDF-Code.");
        };
        result.extend_from_slice(&entry);
        if result.len() > MAX_STREAM {
            return bad("Dekomprimierter PDF-Stream zu groß.");
        }
        if let Some(previous) = &previous
            && table.len() < 4096
        {
            let mut longer = previous.clone();
            longer.extend(entry.first());
            table.push(longer);
            if width < 12 && table.len() + early as usize == 1 << width {
                width += 1;
            }
        }
        previous = Some(entry);
    }
    if !ended {
        return bad("LZW-PDF-Ende fehlt.");
    }
    Ok(result)
}

/// Ascii85 without the Adobe frame, as Python's `base64.a85decode` reads it.
fn ascii85(encoded: &[u8]) -> Option<Vec<u8>> {
    let mut result = Vec::with_capacity(encoded.len() / 5 * 4 + 4);
    let mut group = Vec::with_capacity(5);
    let flush = |group: &mut Vec<u8>, result: &mut Vec<u8>| -> Option<()> {
        let value = group.iter().try_fold(0u64, |sum, digit| {
            Some(sum * 85 + u64::from(digit.checked_sub(b'!').filter(|d| *d < 85)?))
        })?;
        result.extend_from_slice(&u32::try_from(value).ok()?.to_be_bytes());
        group.clear();
        Some(())
    };
    for byte in encoded {
        match byte {
            b'!'..=b'u' => {
                group.push(*byte);
                if group.len() == 5 {
                    flush(&mut group, &mut result)?;
                }
            }
            b'z' if group.is_empty() => result.extend_from_slice(&[0; 4]),
            _ => return None,
        }
    }
    if !group.is_empty() {
        let padding = 5 - group.len();
        group.resize(5, b'u');
        flush(&mut group, &mut result)?;
        result.truncate(result.len() - padding);
    }
    Some(result)
}

fn run_length(data: &[u8]) -> Outcome<Vec<u8>> {
    let (mut result, mut pos) = (Vec::new(), 0);
    while pos < data.len() {
        let count = data[pos] as usize;
        pos += 1;
        if count == 128 {
            return Ok(result);
        }
        if count < 128 {
            if pos + count + 1 > data.len() {
                return bad("Unvollständiger RunLength-PDF-Stream.");
            }
            result.extend_from_slice(&data[pos..pos + count + 1]);
            pos += count + 1;
        } else {
            if pos == data.len() {
                return bad("Unvollständiger RunLength-PDF-Stream.");
            }
            result.resize(result.len() + 257 - count, data[pos]);
            pos += 1;
        }
        if result.len() > MAX_STREAM {
            return bad("Dekomprimierter PDF-Stream zu groß.");
        }
    }
    bad("RunLength-PDF-Ende fehlt.")
}

/// The stream's data with its filter chain undone. `resolve` follows references in the filter entries.
pub fn decoded(stream: &Stream, resolve: &dyn Fn(&Value) -> Outcome<Value>) -> Outcome<Vec<u8>> {
    if ["F", "FFilter", "FDecodeParms"]
        .iter()
        .any(|key| stream.attrs.contains_key(*key))
    {
        return Err(Error::Unsupported(
            "Externe PDF-Streamdaten werden nicht geöffnet.".into(),
        ));
    }
    let entry = |key: &str| -> Outcome<Value> {
        let value = resolve(stream.attrs.get(key).unwrap_or(&Value::Null))?;
        Ok(if value.truthy() {
            value
        } else {
            Value::Array(Rc::new(Vec::new()))
        })
    };
    let (mut filters, mut params) = (entry("Filter")?, entry("DecodeParms")?);
    if filters.name().is_some() {
        let single = if params.truthy() && params.array().is_none_or(|a| !a.is_empty()) {
            params.clone()
        } else {
            Value::Dict(Rc::new(Dict::new()))
        };
        (filters, params) = (
            Value::Array(Rc::new(vec![filters])),
            Value::Array(Rc::new(vec![single])),
        );
    }
    let Some(filters) = filters.array().filter(|filters| filters.len() <= 8) else {
        return bad("Ungültige PDF-Filterkette.");
    };
    let Some(params) = params.array() else {
        return bad("Ungültige PDF-Filterparameter.");
    };
    if stream.raw.len() > MAX_STREAM * 2 {
        return bad("Kodierter PDF-Stream zu groß.");
    }
    let mut data = stream.raw.clone();
    for (index, name) in filters.iter().enumerate() {
        let name = resolve(name)?;
        let options = match params.get(index) {
            Some(options) => resolve(options)?,
            None => Value::Null,
        };
        let empty = Rc::new(Dict::new());
        let options = if options.truthy() {
            options
                .dict()
                .cloned()
                .ok_or(Error::Pdf("Ungültige PDF-Filterparameter.".into()))?
        } else {
            empty
        };
        data = match name.name() {
            Some("FlateDecode" | "Fl") => predict(inflate(&data)?, &options)?,
            Some("LZWDecode" | "LZW") => {
                let early = integer(options.get("EarlyChange").unwrap_or(&Value::Int(1)), 0, 1)?;
                predict(lzw(&data, early)?, &options)?
            }
            Some("ASCIIHexDecode" | "AHx") => {
                let raw: Vec<u8> = data.iter().copied().filter(|b| !space(*b)).collect();
                let Some(digits) = raw.strip_suffix(b">") else {
                    return bad("ASCIIHex-PDF-Ende fehlt.");
                };
                hex(digits).ok_or(Error::Pdf("Beschädigter PDF-Stream.".into()))?
            }
            Some("ASCII85Decode" | "A85") => {
                let raw: Vec<u8> = data.iter().copied().filter(|b| !space(*b)).collect();
                let Some(encoded) = raw.strip_suffix(b"~>") else {
                    return bad("ASCII85-PDF-Ende fehlt.");
                };
                let short = encoded.iter().filter(|b| **b == b'z').count();
                let ordinary = encoded.len() - short;
                if short * 4 + ordinary / 5 * 4 + (ordinary % 5).saturating_sub(1) > MAX_STREAM {
                    return bad("Dekomprimierter ASCII85-PDF-Stream zu groß.");
                }
                ascii85(encoded).ok_or(Error::Pdf("Beschädigter PDF-Stream.".into()))?
            }
            Some("RunLengthDecode" | "RL") => run_length(&data)?,
            _ => {
                let shown = match &name {
                    Value::Name(name) => name.to_string(),
                    Value::Null => "None".into(),
                    other => format!("{other:?}"),
                };
                return Err(Error::Unsupported(format!(
                    "PDF-Filter noch nicht unterstützt: {shown}"
                )));
            }
        };
        data = bounded(data)?;
    }
    bounded(data)
}

/// A PDF text string: UTF-16 or UTF-8 with its mark, otherwise PDFDocEncoding.
pub fn text_string(value: &Value) -> String {
    let Value::Text(bytes) = value else {
        return String::new();
    };
    if let Some(rest) = bytes.strip_prefix(&[0xfe, 0xff]) {
        let units = rest
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u16::from_be_bytes(*pair));
        let mut text: String = char::decode_utf16(units)
            .map(|unit| unit.unwrap_or('\u{fffd}'))
            .collect();
        if rest.len() % 2 == 1 {
            text.push('\u{fffd}');
        }
        return text;
    }
    if let Some(rest) = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]) {
        return String::from_utf8_lossy(rest).into_owned();
    }
    // PDFDocEncoding differs from Latin-1 in these ranges (PDF 1.7, appendix D).
    let specials: Vec<char> = "˘ˇˆ˙˝˛˚˜".chars().collect();
    let extended: Vec<char> = "•†‡…—–ƒ⁄‹›−‰„“”‘’‚™ﬁﬂŁŒŠŸŽıłœšž".chars().collect();
    bytes
        .iter()
        .map(|byte| match *byte {
            24..=31 => specials[(*byte - 24) as usize],
            128..=158 => extended[(*byte - 128) as usize],
            160 => '€',
            other => other as char,
        })
        .collect()
}

type ObjectStream = (Vec<u8>, usize, Vec<(i64, usize)>);

pub struct Document {
    data: Vec<u8>,
    xref: HashMap<i64, (u64, u64, u64)>,
    cache: RefCell<HashMap<Ref, Value>>,
    active: RefCell<HashSet<Ref>>,
    object_streams: RefCell<HashMap<i64, Rc<ObjectStream>>>,
    decoded_size: Cell<usize>,
    security: Option<crate::security::Security>,
    pub trailer: Dict,
    pub catalog: Rc<Dict>,
    /// Page attributes with the inherited ones filled in.
    pub pages: Vec<Dict>,
    pub page_refs: Vec<Ref>,
    /// Document information with lower-case keys.
    pub metadata: BTreeMap<String, String>,
}

fn is_name(value: Option<&Value>, name: &str) -> bool {
    value.and_then(Value::name) == Some(name)
}

impl Document {
    /// Opens a file; `password` is tried as user and as owner password of an encrypted one.
    pub fn open(path: &std::path::Path, password: &str) -> Outcome<Document> {
        use std::io::Read;
        let mut data = Vec::new();
        let file = std::fs::File::open(path)
            .map_err(|_| Error::Pdf("Lesedatei fehlt oder ist größer als 200 MiB.".into()))?;
        file.take(MAX_FILE as u64 + 1)
            .read_to_end(&mut data)
            .map_err(|_| Error::Pdf("Lesedatei fehlt oder ist größer als 200 MiB.".into()))?;
        Document::with_password(data, password)
    }

    pub fn new(data: Vec<u8>) -> Outcome<Document> {
        Document::with_password(data, "")
    }

    pub fn with_password(data: Vec<u8>, password: &str) -> Outcome<Document> {
        if data.len() > MAX_FILE {
            return bad("PDF größer als 512 MiB.");
        }
        let head = data.len() >= 9
            && data.starts_with(b"%PDF-")
            && matches!(data[5], b'1' | b'2')
            && data[6] == b'.'
            && data[7].is_ascii_digit()
            && matches!(data[8], b'\r' | b'\n');
        if !head {
            return bad("PDF-Kopf fehlt.");
        }
        let Some(start) = start_of_references(&data[data.len().saturating_sub(4096)..]) else {
            return bad("PDF-Abschluss oder Querverweis fehlt.");
        };
        let mut document = Document {
            data,
            xref: HashMap::new(),
            cache: RefCell::new(HashMap::new()),
            active: RefCell::new(HashSet::new()),
            object_streams: RefCell::new(HashMap::new()),
            decoded_size: Cell::new(0),
            security: None,
            trailer: Dict::new(),
            catalog: Rc::new(Dict::new()),
            pages: Vec::new(),
            page_refs: Vec::new(),
            metadata: BTreeMap::new(),
        };
        document.references(start)?;
        if let Some(encrypt) = document
            .trailer
            .get("Encrypt")
            .filter(|value| !value.is_null())
            .cloned()
        {
            // The encryption dictionary and its crypt filters are read before any key exists.
            let Value::Dict(listed) = document.resolve(&encrypt)? else {
                return Err(Error::Unsupported(
                    "PDF-Sicherheitsverfahren wird nicht unterstützt.".into(),
                ));
            };
            let mut attrs = Dict::new();
            for (key, value) in listed.iter() {
                attrs.insert(key.clone(), document.resolve(value)?);
            }
            if let Some(Value::Dict(filters)) = attrs.get("CF").cloned() {
                let mut resolved = Dict::new();
                for (key, value) in filters.iter() {
                    resolved.insert(key.clone(), document.resolve(value)?);
                }
                attrs.insert("CF".into(), Value::Dict(Rc::new(resolved)));
            }
            document.security = Some(crate::security::Security::new(
                &attrs,
                document.trailer.get("ID"),
                password,
            )?);
        }
        let catalog = document.resolve(document.trailer.get("Root").unwrap_or(&Value::Null))?;
        match catalog.dict() {
            Some(catalog) if is_name(catalog.get("Type"), "Catalog") => {
                document.catalog = catalog.clone()
            }
            _ => return bad("PDF-Katalog fehlt."),
        }
        let root = document
            .catalog
            .get("Pages")
            .cloned()
            .unwrap_or(Value::Null);
        let (mut pages, mut page_refs) = (Vec::new(), Vec::new());
        document.tree(
            &root,
            &Dict::new(),
            &mut HashSet::new(),
            0,
            &mut pages,
            &mut page_refs,
        )?;
        if pages.is_empty() {
            return bad("PDF hat keine Seiten.");
        }
        (document.pages, document.page_refs) = (pages, page_refs);
        let information = document.resolve(document.trailer.get("Info").unwrap_or(&Value::Null))?;
        if information.truthy() {
            let Some(information) = information.dict() else {
                return bad("Ungültige PDF-Metadaten.");
            };
            for (key, value) in information.iter() {
                let text = text_string(&document.resolve(value)?);
                document.metadata.insert(key.to_lowercase(), text);
            }
        }
        Ok(document)
    }

    fn indirect(
        &self,
        offset: &Value,
        expected: Option<Ref>,
        bootstrap: bool,
    ) -> Outcome<(Ref, Value)> {
        let offset = integer(offset, 0, self.data.len() as i64 - 1)? as usize;
        let mut syntax = Syntax::new(&self.data, offset);
        let number = integer(&syntax.value()?, 1, MAX_OBJECTS)?;
        let generation = integer(&syntax.value()?, 0, 65535)?;
        syntax.expect("obj")?;
        let reference = Ref { number, generation };
        if expected.is_some_and(|expected| expected != reference) {
            return bad("PDF-Objekt und Querverweis stimmen nicht überein.");
        }
        let mut value = syntax.value()?;
        syntax.skip();
        if let (Value::Dict(attrs), true) = (&value, self.data[syntax.pos..].starts_with(b"stream"))
        {
            syntax.pos += 6;
            if self.data[syntax.pos..].starts_with(b"\r\n") {
                syntax.pos += 2;
            } else if self.data[syntax.pos..].starts_with(b"\n") {
                syntax.pos += 1;
            } else {
                return bad("PDF-Stream-Zeilenumbruch fehlt.");
            }
            let mut length = attrs.get("Length").cloned().unwrap_or(Value::Null);
            if !bootstrap {
                length = self.resolve(&length)?;
            }
            let end = syntax.pos + integer(&length, 0, MAX_FILE as i64)? as usize;
            if end > self.data.len() {
                return bad("PDF-Stream reicht über Dateiende.");
            }
            value = Value::Stream(Rc::new(Stream {
                attrs: (**attrs).clone(),
                raw: self.data[syntax.pos..end].to_vec(),
            }));
            syntax.pos = end;
            syntax.expect("endstream")?;
        }
        syntax.expect("endobj")?;
        Ok((reference, value))
    }

    #[allow(clippy::type_complexity)]
    fn section(&self, offset: &Value) -> Outcome<(Dict, Vec<(i64, (u64, u64, u64))>)> {
        let position = integer(offset, 0, self.data.len() as i64 - 1)? as usize;
        let mut syntax = Syntax::new(&self.data, position);
        syntax.skip();
        let mut entries: Vec<(i64, (u64, u64, u64))> = Vec::new();
        let mut seen = HashSet::new();
        if self.data[syntax.pos..].starts_with(b"xref") {
            syntax.expect("xref")?;
            loop {
                syntax.skip();
                if self.data[syntax.pos.min(self.data.len())..].starts_with(b"trailer") {
                    syntax.expect("trailer")?;
                    break;
                }
                let start = integer(&syntax.value()?, 0, MAX_OBJECTS)?;
                let count = integer(&syntax.value()?, 0, MAX_OBJECTS)?;
                if start + count > MAX_OBJECTS || entries.len() as i64 + count > MAX_OBJECTS {
                    return bad("Zu viele PDF-Objekte.");
                }
                for number in start..start + count {
                    let position = integer(
                        &syntax.value()?,
                        0,
                        (self.data.len() as i64).max(MAX_OBJECTS),
                    )?;
                    let generation = integer(&syntax.value()?, 0, 65536)?;
                    let flag = syntax.word()?;
                    // Pillow emits 65536 for the unused free entry. It is never resolved.
                    if flag == b"n" && (generation > 65535 || position >= self.data.len() as i64) {
                        return bad("Ungültiger PDF-Querverweis.");
                    }
                    if (flag != b"n" && flag != b"f") || !seen.insert(number) {
                        return bad("Ungültiger PDF-Querverweis.");
                    }
                    entries.push((
                        number,
                        (u64::from(flag == b"n"), position as u64, generation as u64),
                    ));
                }
            }
            return match syntax.value()? {
                Value::Dict(trailer) => Ok(((*trailer).clone(), entries)),
                _ => bad("Ungültiger PDF-Trailer."),
            };
        }
        let stream = match self.indirect(offset, None, true)?.1 {
            Value::Stream(stream) if is_name(stream.attrs.get("Type"), "XRef") => stream,
            _ => return bad("PDF-Querverweisstream fehlt."),
        };
        let attrs = &stream.attrs;
        let size = integer(attrs.get("Size").unwrap_or(&Value::Null), 0, MAX_OBJECTS)?;
        let widths = match attrs.get("W").and_then(Value::array) {
            Some(widths) if widths.len() == 3 => widths
                .iter()
                .map(|width| integer(width, 0, 8).map(|w| w as usize))
                .collect::<Outcome<Vec<_>>>()?,
            _ => return bad("Ungültige PDF-Querverweisbreiten."),
        };
        let stride: usize = widths.iter().sum();
        if stride == 0 {
            return bad("Leerer PDF-Querverweis.");
        }
        let whole = Value::Array(Rc::new(vec![Value::Int(0), Value::Int(size)]));
        let indices = match attrs.get("Index").unwrap_or(&whole).array() {
            Some(indices) if indices.len() % 2 == 0 => indices.clone(),
            _ => return bad("Ungültiger PDF-Querverweisindex."),
        };
        let data = decoded(&stream, &|value| Ok(value.clone()))?;
        let mut pos = 0;
        for pair in indices.chunks(2) {
            let start = integer(&pair[0], 0, MAX_OBJECTS)?;
            let count = integer(&pair[1], 0, MAX_OBJECTS)?;
            if start + count > size || entries.len() as i64 + count > MAX_OBJECTS {
                return bad("PDF-Querverweisindex außerhalb des Bereichs.");
            }
            for number in start..start + count {
                if pos + stride > data.len() || !seen.insert(number) {
                    return bad("Ungültiger PDF-Querverweisstream.");
                }
                let mut fields = [0u64; 3];
                for (column, width) in widths.iter().enumerate() {
                    fields[column] = if *width > 0 {
                        data[pos..pos + width]
                            .iter()
                            .fold(0, |sum, byte| sum << 8 | u64::from(*byte))
                    } else {
                        u64::from(column == 0)
                    };
                    pos += width;
                }
                if fields[0] > 2 {
                    return Err(Error::Unsupported("Unbekannter PDF-Querverweistyp.".into()));
                }
                entries.push((number, (fields[0], fields[1], fields[2])));
            }
        }
        if pos != data.len() {
            return bad("PDF-Querverweislänge stimmt nicht.");
        }
        Ok((attrs.clone(), entries))
    }

    /// Reads the newest cross-reference section and every earlier revision behind it.
    fn references(&mut self, start: Value) -> Outcome<()> {
        let mut visited: Vec<Value> = Vec::new();
        let seen = |visited: &[Value], offset: &Value| {
            visited
                .iter()
                .any(|v| v.number().is_some() && v.number() == offset.number())
        };
        let mut offset = start;
        loop {
            if seen(&visited, &offset) || visited.len() >= 256 {
                return bad("Zyklische oder zu viele PDF-Revisionen.");
            }
            visited.push(offset.clone());
            let (trailer, mut entries) = self.section(&offset)?;
            if let Some(hybrid) = trailer.get("XRefStm").filter(|value| !value.is_null()) {
                if seen(&visited, hybrid) {
                    return bad("Zyklischer hybrider PDF-Querverweis.");
                }
                visited.push(hybrid.clone());
                let more = self.section(hybrid)?.1;
                // The stream's entries replace the table's for the same object.
                let replaced: HashSet<i64> = more.iter().map(|entry| entry.0).collect();
                entries.retain(|entry| !replaced.contains(&entry.0));
                entries.extend(more);
            }
            for (number, entry) in entries {
                self.xref.entry(number).or_insert(entry);
            }
            if self.xref.len() as i64 > MAX_OBJECTS {
                return bad("Zu viele PDF-Objekte.");
            }
            let previous = trailer
                .get("Prev")
                .cloned()
                .filter(|value| !value.is_null());
            for (key, value) in trailer {
                self.trailer.entry(key).or_insert(value);
            }
            match previous {
                Some(previous) => {
                    integer(&previous, 0, self.data.len() as i64 - 1)?;
                    offset = previous;
                }
                None => break,
            }
        }
        integer(
            self.trailer.get("Size").unwrap_or(&Value::Null),
            0,
            MAX_OBJECTS,
        )
        .map(|_| ())
    }

    /// The object a reference points to; any other value is returned as it is.
    pub fn resolve(&self, value: &Value) -> Outcome<Value> {
        let Value::Ref(reference) = value else {
            return Ok(value.clone());
        };
        if let Some(found) = self.cache.borrow().get(reference) {
            return Ok(found.clone());
        }
        if self.active.borrow().contains(reference) || self.active.borrow().len() > MAX_DEPTH {
            return bad("Zyklische PDF-Objektauflösung.");
        }
        // ISO 32000-1 7.3.10: an undefined indirect object denotes PDF null.
        // Required objects are still validated by their consuming structures.
        let Some(entry) = self
            .xref
            .get(&reference.number)
            .copied()
            .filter(|entry| entry.0 != 0)
        else {
            return Ok(Value::Null);
        };
        if (entry.0 == 1 && entry.2 != reference.generation as u64)
            || (entry.0 == 2 && reference.generation != 0)
        {
            return Ok(Value::Null);
        }
        self.active.borrow_mut().insert(*reference);
        let result = self.load(*reference, entry);
        self.active.borrow_mut().remove(reference);
        let mut result = result?;
        if let (1, Some(security)) = (entry.0, &self.security) {
            result = security.value(&result, *reference, &|value| self.resolve(value))?;
        }
        if matches!(result, Value::Ref(_) | Value::Operator(_)) {
            return bad("Ungültiger indirekter PDF-Objektwert.");
        }
        self.cache.borrow_mut().insert(*reference, result.clone());
        Ok(result)
    }

    fn load(&self, reference: Ref, entry: (u64, u64, u64)) -> Outcome<Value> {
        if entry.0 == 1 {
            let offset = i64::try_from(entry.1)
                .map(Value::Int)
                .unwrap_or(Value::Null);
            return Ok(self.indirect(&offset, Some(reference), false)?.1);
        }
        let Ok(holder) = i64::try_from(entry.1) else {
            return bad("PDF-Objektstream fehlt.");
        };
        let known = self.object_streams.borrow().get(&holder).cloned();
        let pack = match known {
            Some(pack) => pack,
            None => {
                let stream = match self.resolve(&Value::Ref(Ref {
                    number: holder,
                    generation: 0,
                }))? {
                    Value::Stream(stream) if is_name(stream.attrs.get("Type"), "ObjStm") => stream,
                    _ => return bad("PDF-Objektstream fehlt."),
                };
                let data = self.decode(&stream)?;
                let count = integer(
                    stream.attrs.get("N").unwrap_or(&Value::Null),
                    0,
                    MAX_OBJECTS,
                )?;
                let first = integer(
                    stream.attrs.get("First").unwrap_or(&Value::Null),
                    0,
                    data.len() as i64,
                )? as usize;
                let mut syntax = Syntax::new(&data[..first], 0);
                let mut headers = Vec::new();
                for _ in 0..count {
                    let number = integer(&syntax.value()?, 1, MAX_OBJECTS)?;
                    headers.push((
                        number,
                        integer(&syntax.value()?, 0, (data.len() - first) as i64)? as usize,
                    ));
                }
                syntax.skip();
                let numbers: HashSet<i64> = headers.iter().map(|header| header.0).collect();
                if syntax.pos != first || numbers.len() != headers.len() {
                    return bad("Ungültiger PDF-Objektstream-Kopf.");
                }
                if !headers.windows(2).all(|pair| pair[0].1 < pair[1].1) {
                    return bad("Ungültige PDF-Objektstream-Offsets.");
                }
                let pack = Rc::new((data, first, headers));
                self.object_streams
                    .borrow_mut()
                    .insert(holder, pack.clone());
                pack
            }
        };
        let (data, first, headers) = &*pack;
        let index = entry.2 as usize;
        if entry.2 >= headers.len() as u64 || headers[index].0 != reference.number {
            return bad("PDF-Objektstream-Index stimmt nicht.");
        }
        let end = headers
            .get(index + 1)
            .map(|next| first + next.1)
            .unwrap_or(data.len());
        let slice = &data[first + headers[index].1..end];
        let mut syntax = Syntax::new(slice, 0);
        let result = syntax.value()?;
        syntax.skip();
        if syntax.pos != slice.len() {
            return bad("Ungültiger PDF-Objektstream-Inhalt.");
        }
        Ok(result)
    }

    /// A stream's decoded data, counted against the document's decompression budget.
    pub fn decode(&self, stream: &Stream) -> Outcome<Vec<u8>> {
        let result = decoded(stream, &|value| self.resolve(value))?;
        self.decoded_size
            .set(self.decoded_size.get() + result.len());
        if self.decoded_size.get() > 1024 * 1024 * 1024 {
            return bad("PDF-Dekompressionsbudget überschritten.");
        }
        Ok(result)
    }

    fn tree(
        &self,
        reference: &Value,
        inherited: &Dict,
        visited: &mut HashSet<Ref>,
        depth: usize,
        pages: &mut Vec<Dict>,
        page_refs: &mut Vec<Ref>,
    ) -> Outcome<()> {
        if depth > MAX_DEPTH || visited.len() as i64 > MAX_OBJECTS {
            return bad("PDF-Seitenbaum zu groß.");
        }
        let reference = match reference {
            Value::Ref(reference) if visited.insert(*reference) => *reference,
            _ => return bad("Zyklischer oder ungültiger PDF-Seitenbaum."),
        };
        let node = self.resolve(&Value::Ref(reference))?;
        let Some(node) = node.dict() else {
            return bad("Ungültiger PDF-Seitenknoten.");
        };
        let inheritable = ["Resources", "MediaBox", "CropBox", "Rotate"];
        let mut attrs = inherited.clone();
        for key in inheritable {
            if let Some(value) = node.get(key) {
                attrs.insert(key.into(), self.resolve(value)?);
            }
        }
        if is_name(node.get("Type"), "Pages") {
            let kids = self.resolve(node.get("Kids").unwrap_or(&Value::Null))?;
            let Some(kids) = kids.array() else {
                return bad("PDF-Seitenliste fehlt.");
            };
            let before = pages.len();
            for kid in kids.iter() {
                self.tree(kid, &attrs, visited, depth + 1, pages, page_refs)?;
            }
            if node.get("Count").and_then(Value::number) != Some((pages.len() - before) as f64) {
                return bad("PDF-Seitenzahl und Seitenbaum stimmen nicht überein.");
            }
        } else if is_name(node.get("Type"), "Page") {
            for (key, value) in node.iter() {
                attrs.insert(key.clone(), value.clone());
            }
            for key in inheritable {
                let value = attrs
                    .get(key)
                    .or_else(|| inherited.get(key))
                    .cloned()
                    .unwrap_or(Value::Null);
                attrs.insert(key.into(), self.resolve(&value)?);
            }
            let corners: Option<Vec<f64>> = attrs
                .get("MediaBox")
                .and_then(Value::array)
                .filter(|b| b.len() == 4)
                .and_then(|b| {
                    b.iter()
                        .map(|v| v.number().filter(|n| n.is_finite()))
                        .collect()
                });
            match corners {
                Some(b) if b[0] < b[2] && b[1] < b[3] => {
                    if b.iter().any(|v| v.abs() > 1_000_000.0) {
                        return bad("PDF-Seitenkoordinaten zu groß.");
                    }
                }
                _ => return bad("Ungültige PDF-Seitengröße."),
            }
            pages.push(attrs);
            page_refs.push(reference);
            if pages.len() > 10000 {
                return bad("Mehr als 10.000 PDF-Seiten.");
            }
        } else {
            return bad("Unbekannter PDF-Seitenknoten.");
        }
        Ok(())
    }

    /// Resolves both legacy /Dests and the PDF name tree (ISO 32000-1 12.3.2) to a destination array.
    pub fn destination(&self, value: &Value) -> Outcome<Option<Rc<Vec<Value>>>> {
        self.target(value, 0, &mut HashSet::new())
    }

    fn target(
        &self,
        value: &Value,
        depth: usize,
        seen: &mut HashSet<(bool, Vec<u8>)>,
    ) -> Outcome<Option<Rc<Vec<Value>>>> {
        if depth > MAX_DEPTH {
            return bad("PDF-Seitenverweis zu tief.");
        }
        let value = self.resolve(value)?;
        let latin = |name: &str| name.chars().map(|c| c as u32 as u8).collect::<Vec<u8>>();
        let (named, wanted) = match &value {
            Value::Name(name) => (true, latin(name)),
            Value::Text(text) => (false, (**text).clone()),
            Value::Dict(dict) => {
                return self.target(dict.get("D").unwrap_or(&Value::Null), depth + 1, seen);
            }
            Value::Array(array) => return Ok(Some(array.clone())),
            _ => return Ok(None),
        };
        if !seen.insert((named, wanted.clone())) {
            return bad("Zyklischer PDF-Seitenverweis.");
        }
        let legacy = self.resolve(self.catalog.get("Dests").unwrap_or(&Value::Null))?;
        let mut found = match (&value, legacy.dict()) {
            (Value::Name(name), Some(legacy)) => {
                legacy.get(&**name).cloned().filter(|v| !v.is_null())
            }
            _ => None,
        };
        if found.is_none() {
            let names = self.resolve(self.catalog.get("Names").unwrap_or(&Value::Null))?;
            let root = match names.dict().and_then(|names| names.get("Dests")) {
                Some(root) => self.resolve(root)?,
                None => Value::Null,
            };
            if !root.is_null() {
                found = self
                    .search(&root, &wanted, 0, &mut HashSet::new())?
                    .filter(|v| !v.is_null());
            }
        }
        match found {
            Some(found) => self.target(&found, depth + 1, seen),
            None => Ok(None),
        }
    }

    fn search(
        &self,
        node: &Value,
        wanted: &[u8],
        level: usize,
        visited: &mut HashSet<usize>,
    ) -> Outcome<Option<Value>> {
        let node = self.resolve(node)?;
        let invalid = || Error::Pdf("Ungültiger PDF-Zielnamenbaum.".into());
        let dict = node.dict().ok_or_else(invalid)?;
        if level > MAX_DEPTH
            || visited.len() as i64 >= MAX_OBJECTS
            || !visited.insert(Rc::as_ptr(dict) as usize)
        {
            return Err(invalid());
        }
        let list = |key: &str| -> Outcome<Option<Rc<Vec<Value>>>> {
            match dict.get(key) {
                None => Ok(Some(Rc::new(Vec::new()))),
                Some(value) => Ok(self.resolve(value)?.array().cloned()),
            }
        };
        let Some(entries) = list("Names")?.filter(|entries| entries.len() % 2 == 0) else {
            return bad("Ungültige PDF-Zielnamenliste.");
        };
        for pair in entries.chunks(2) {
            if matches!(self.resolve(&pair[0])?, Value::Text(key) if key.as_slice() == wanted) {
                return Ok(Some(pair[1].clone()));
            }
        }
        let children = list("Kids")?.ok_or_else(invalid)?;
        for kid in children.iter() {
            if let Some(result) = self.search(kid, wanted, level + 1, visited)? {
                return Ok(Some(result));
            }
        }
        Ok(None)
    }

    /// The outline as (level, title, page number from one).
    pub fn toc(&self) -> Outcome<Vec<(usize, String, usize)>> {
        let outlines = self.resolve(self.catalog.get("Outlines").unwrap_or(&Value::Null))?;
        if !outlines.truthy() {
            return Ok(Vec::new());
        }
        let invalid = || Error::Pdf("Ungültiges PDF-Inhaltsverzeichnis.".into());
        let outlines = outlines.dict().ok_or_else(invalid)?;
        let numbers: HashMap<Ref, usize> = self
            .page_refs
            .iter()
            .enumerate()
            .map(|(index, reference)| (*reference, index + 1))
            .collect();
        let mut result = Vec::new();
        self.outline(
            outlines.get("First").cloned().unwrap_or(Value::Null),
            1,
            &numbers,
            &mut HashSet::new(),
            &mut result,
        )?;
        Ok(result)
    }

    fn outline(
        &self,
        mut item: Value,
        level: usize,
        numbers: &HashMap<Ref, usize>,
        visited: &mut HashSet<Ref>,
        result: &mut Vec<(usize, String, usize)>,
    ) -> Outcome<()> {
        let invalid = || Error::Pdf("Ungültiges PDF-Inhaltsverzeichnis.".into());
        while !item.is_null() {
            let reference = match item {
                Value::Ref(reference)
                    if visited.len() < 2000 && level <= 32 && visited.insert(reference) =>
                {
                    reference
                }
                _ => return Err(invalid()),
            };
            let node = self.resolve(&Value::Ref(reference))?;
            let node = node.dict().ok_or_else(invalid)?;
            let mut destination = self.resolve(node.get("Dest").unwrap_or(&Value::Null))?;
            if destination.is_null() {
                let action = self.resolve(node.get("A").unwrap_or(&Value::Null))?;
                if let Some(action) = action
                    .dict()
                    .filter(|action| is_name(action.get("S"), "GoTo"))
                {
                    destination = self.resolve(action.get("D").unwrap_or(&Value::Null))?;
                }
            }
            if let Some(target) = self.destination(&destination)?
                && let Some(Value::Ref(page)) = target.first()
                && let Some(number) = numbers.get(page)
            {
                result.push((
                    level,
                    text_string(&self.resolve(node.get("Title").unwrap_or(&Value::Null))?),
                    *number,
                ));
            }
            if let Some(first) = node.get("First").filter(|first| first.truthy()) {
                self.outline(first.clone(), level + 1, numbers, visited, result)?;
            }
            item = node.get("Next").cloned().unwrap_or(Value::Null);
        }
        Ok(())
    }

    /// The page's content streams, decoded and joined with line breaks.
    pub fn contents(&self, index: usize) -> Outcome<Vec<u8>> {
        let contents = self.resolve(self.pages[index].get("Contents").unwrap_or(&Value::Null))?;
        let items = match &contents {
            Value::Null => return Ok(Vec::new()),
            Value::Array(items) => (**items).clone(),
            other => vec![other.clone()],
        };
        let mut result = Vec::new();
        for item in items {
            match self.resolve(&item)? {
                Value::Stream(stream) => result.extend(self.decode(&stream)?),
                _ => return bad("PDF-Stream erwartet."),
            }
            result.push(b'\n');
            if result.len() > MAX_STREAM {
                return bad("Dekomprimierter PDF-Stream zu groß.");
            }
        }
        Ok(result)
    }
}

/// The offset after the last `startxref`, when the file ends as `startxref <offset> %%EOF`.
fn start_of_references(tail: &[u8]) -> Option<Value> {
    let blank = |byte: &u8| matches!(*byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c);
    let mut from = 0;
    while let Some(found) = tail[from..]
        .windows(9)
        .position(|window| window == b"startxref")
    {
        let rest = &tail[from + found + 9..];
        from += found + 1;
        let gap = rest.iter().take_while(|b| blank(b)).count();
        let digits = rest[gap..]
            .iter()
            .take_while(|b| b.is_ascii_digit())
            .count();
        let after = &rest[gap + digits..];
        let second = after.iter().take_while(|b| blank(b)).count();
        if gap == 0
            || digits == 0
            || second == 0
            || !after[second..].starts_with(b"%%EOF")
            || !after[second + 5..].iter().all(&blank)
        {
            continue;
        }
        let number = std::str::from_utf8(&rest[gap..gap + digits])
            .ok()?
            .parse::<i64>()
            .ok();
        // A number too large for the file fails the offset check with the usual message.
        return Some(number.map(Value::Int).unwrap_or(Value::Null));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn read(text: &[u8]) -> Value {
        Syntax::new(text, 0).value().unwrap()
    }

    #[test]
    fn syntax_reads_every_object_kind() {
        let value =
            read(b"<< /A#20B [(escaped\\(text\\)\\053) <123> -1.25 true null] /Ref 2 0 R >>");
        let dict = value.dict().unwrap();
        let items = dict["A B"].array().unwrap();
        assert!(matches!(&items[0], Value::Text(text) if text.as_slice() == b"escaped(text)+"));
        assert!(matches!(&items[1], Value::Text(text) if text.as_slice() == [0x12, 0x30]));
        assert!(matches!(items[2], Value::Real(number) if number == -1.25));
        assert!(matches!(
            (&items[3], &items[4]),
            (Value::Bool(true), Value::Null)
        ));
        assert!(matches!(
            dict["Ref"],
            Value::Ref(Ref {
                number: 2,
                generation: 0
            })
        ));
        assert!(matches!(read(b"0.00-12"), Value::Real(number) if number == 0.0));
        assert!(matches!(read(b"12 % comment\n 0 obj"), Value::Int(12)));
        assert!(matches!(read(b"BT"), Value::Operator(op) if &*op == "BT"));
        assert!(Syntax::new(b"<< /A 1 /A 2 >>", 0).value().is_err());
        assert!(Syntax::new(b"/A#G0", 0).value().is_err());
    }

    #[test]
    fn filters_decode_and_refuse_what_python_refuses() {
        let stream = |filter: &str, raw: &[u8]| Stream {
            attrs: Dict::from([("Filter".to_string(), Value::Name(filter.into()))]),
            raw: raw.to_vec(),
        };
        let plain = |value: &Value| Ok(value.clone());
        assert_eq!(
            decoded(&stream("ASCIIHexDecode", b"48 65 6c6C 6f>"), &plain).unwrap(),
            b"Hello"
        );
        assert_eq!(
            decoded(&stream("ASCII85Decode", b"87cURD]i,\"Ebo80~>"), &plain).unwrap(),
            b"Hello World!"
        );
        assert_eq!(
            decoded(
                &stream("RunLengthDecode", &[2, b'a', b'b', b'c', 254, b'x', 128]),
                &plain
            )
            .unwrap(),
            b"abcxxx"
        );
        assert_eq!(
            decoded(
                &stream(
                    "LZWDecode",
                    &[0x80, 0x0b, 0x60, 0x50, 0x22, 0x0c, 0x0c, 0x85, 0x01]
                ),
                &plain
            )
            .unwrap(),
            b"-----A---B"
        );
        // zlib.compress(b"PDF filters" * 3): complete, without its checksum, and cut short.
        let packed = [
            0x78, 0x9c, 0x0b, 0x70, 0x71, 0x53, 0x48, 0xcb, 0xcc, 0x29, 0x49, 0x2d, 0x2a, 0x0e,
            0xc0, 0xca, 0x04, 0x00, 0xc2, 0x34, 0x0b, 0xda,
        ];
        let whole = b"PDF filters".repeat(3);
        assert_eq!(
            decoded(&stream("FlateDecode", &packed), &plain).unwrap(),
            whole
        );
        assert_eq!(
            decoded(&stream("FlateDecode", &packed[..packed.len() - 4]), &plain).unwrap(),
            whole
        );
        assert_eq!(
            decoded(&stream("FlateDecode", &packed[..packed.len() - 1]), &plain).unwrap(),
            whole
        );
        assert!(decoded(&stream("FlateDecode", &packed[..packed.len() - 6]), &plain).is_err());
        let mut wrong = packed;
        wrong[21] ^= 1;
        assert_eq!(
            decoded(&stream("FlateDecode", &wrong), &plain),
            Err(Error::Pdf("Beschädigter PDF-Stream.".into()))
        );
        assert!(matches!(
            decoded(&stream("JBIG2Decode", b""), &plain),
            Err(Error::Unsupported(_))
        ));
    }

    #[test]
    fn text_strings_use_their_encoding() {
        let text = |bytes: &[u8]| text_string(&Value::Text(Rc::new(bytes.to_vec())));
        assert_eq!(text(&[0xfe, 0xff, 0, b'A', 0x20, 0xac]), "A€");
        assert_eq!(text(&[0xef, 0xbb, 0xbf, 0xc3, 0xa4]), "ä");
        assert_eq!(text(&[b'a', 0x80, 0xa0, 0xe4]), "a•€ä");
    }

    #[test]
    fn the_end_of_file_names_the_reference_table() {
        assert!(matches!(
            start_of_references(b"junk startxref\n1234\n%%EOF\n"),
            Some(Value::Int(1234))
        ));
        assert!(start_of_references(b"startxref 12 %%EOF trailing").is_none());
        assert!(matches!(
            start_of_references(b"startxref 1 %%EOX startxref\r\n77\r\n%%EOF"),
            Some(Value::Int(77))
        ));
    }
}

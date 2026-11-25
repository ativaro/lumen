//! Reading a JSON request. Numbers keep their digits: file stamps in nanoseconds do not fit a float.
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Number(String),
    Text(String),
    List(Vec<Json>),
    Object(BTreeMap<String, Json>),
}

impl Json {
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(entries) => entries.get(key),
            _ => None,
        }
    }
    pub fn text(&self) -> Option<&str> {
        match self {
            Json::Text(text) => Some(text),
            _ => None,
        }
    }
    pub fn list(&self) -> Option<&[Json]> {
        match self {
            Json::List(items) => Some(items),
            _ => None,
        }
    }
    /// A whole number written without fraction or exponent.
    pub fn whole(&self) -> Option<i64> {
        match self {
            Json::Number(digits) => digits.parse().ok(),
            _ => None,
        }
    }
    pub fn number(&self) -> Option<f64> {
        match self {
            Json::Number(digits) => digits.parse().ok().filter(|value: &f64| value.is_finite()),
            _ => None,
        }
    }
}

struct Reader<'a> {
    data: &'a [u8],
    at: usize,
}

impl Reader<'_> {
    fn space(&mut self) {
        while self
            .data
            .get(self.at)
            .is_some_and(|b| b" \t\r\n".contains(b))
        {
            self.at += 1;
        }
    }

    fn word(&mut self, word: &str, value: Json) -> Option<Json> {
        self.data[self.at..].starts_with(word.as_bytes()).then(|| {
            self.at += word.len();
            value
        })
    }

    fn text(&mut self) -> Option<String> {
        let mut out = String::new();
        self.at += 1;
        loop {
            let start = self.at;
            while !matches!(self.data.get(self.at)?, b'"' | b'\\') {
                self.at += 1;
            }
            out.push_str(std::str::from_utf8(&self.data[start..self.at]).ok()?);
            self.at += 1;
            if self.data[self.at - 1] == b'"' {
                return Some(out);
            }
            let escape = *self.data.get(self.at)?;
            self.at += 1;
            match escape {
                b'n' => out.push('\n'),
                b't' => out.push('\t'),
                b'r' => out.push('\r'),
                b'b' => out.push('\u{8}'),
                b'f' => out.push('\u{c}'),
                b'"' | b'\\' | b'/' => out.push(escape as char),
                b'u' => {
                    let mut unit = self.unit()?;
                    // Characters beyond the basic plane come as a pair of escapes.
                    if (0xD800..0xDC00).contains(&unit) && self.data[self.at..].starts_with(b"\\u")
                    {
                        self.at += 2;
                        unit =
                            0x10000 + ((unit - 0xD800) << 10) + self.unit()?.checked_sub(0xDC00)?;
                    }
                    out.push(char::from_u32(unit)?);
                }
                _ => return None,
            }
        }
    }

    fn unit(&mut self) -> Option<u32> {
        let digits = std::str::from_utf8(self.data.get(self.at..self.at + 4)?).ok()?;
        self.at += 4;
        u32::from_str_radix(digits, 16).ok()
    }

    fn value(&mut self, depth: usize) -> Option<Json> {
        if depth > 32 {
            return None;
        }
        self.space();
        match *self.data.get(self.at)? {
            b'n' => self.word("null", Json::Null),
            b't' => self.word("true", Json::Bool(true)),
            b'f' => self.word("false", Json::Bool(false)),
            b'"' => self.text().map(Json::Text),
            b'[' => {
                self.at += 1;
                let mut items = Vec::new();
                loop {
                    self.space();
                    if *self.data.get(self.at)? == b']' && items.is_empty() {
                        break;
                    }
                    items.push(self.value(depth + 1)?);
                    self.space();
                    match *self.data.get(self.at)? {
                        b',' => self.at += 1,
                        b']' => break,
                        _ => return None,
                    }
                }
                self.at += 1;
                Some(Json::List(items))
            }
            b'{' => {
                self.at += 1;
                let mut entries = BTreeMap::new();
                loop {
                    self.space();
                    if *self.data.get(self.at)? == b'}' && entries.is_empty() {
                        break;
                    }
                    if *self.data.get(self.at)? != b'"' {
                        return None;
                    }
                    let key = self.text()?;
                    self.space();
                    if *self.data.get(self.at)? != b':' {
                        return None;
                    }
                    self.at += 1;
                    entries.insert(key, self.value(depth + 1)?);
                    self.space();
                    match *self.data.get(self.at)? {
                        b',' => self.at += 1,
                        b'}' => break,
                        _ => return None,
                    }
                }
                self.at += 1;
                Some(Json::Object(entries))
            }
            b'-' | b'0'..=b'9' => {
                let start = self.at;
                while self
                    .data
                    .get(self.at)
                    .is_some_and(|b| b"+-.eE0123456789".contains(b))
                {
                    self.at += 1;
                }
                let digits = std::str::from_utf8(&self.data[start..self.at]).ok()?;
                digits.parse::<f64>().ok()?;
                Some(Json::Number(digits.to_string()))
            }
            _ => None,
        }
    }
}

/// The one value in `data`, or nothing if it is not JSON.
pub fn parse(data: &[u8]) -> Option<Json> {
    let mut reader = Reader { data, at: 0 };
    let value = reader.value(0)?;
    reader.space();
    (reader.at == data.len()).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requests_are_read_and_damage_is_refused() {
        let value = parse(br#" {"a": [1, -2.5e0, 1794393977123456789], "t": "x\n\u00e4\ud83d\ude00\"", "n": null, "e": {}, "l": []} "#).unwrap();
        let numbers = value.get("a").unwrap().list().unwrap();
        assert_eq!(numbers[0].whole(), Some(1));
        assert_eq!(numbers[1].number(), Some(-2.5));
        assert_eq!(numbers[1].whole(), None);
        assert_eq!(numbers[2].whole(), Some(1_794_393_977_123_456_789));
        assert_eq!(value.get("t").unwrap().text(), Some("x\nä😀\""));
        assert_eq!(value.get("n"), Some(&Json::Null));
        for damaged in [
            "",
            "{",
            "[1,]",
            "{\"a\" 1}",
            "\"open",
            "1 2",
            "nul",
            "[\"\\x\"]",
        ] {
            assert_eq!(parse(damaged.as_bytes()), None, "{damaged}");
        }
    }
}

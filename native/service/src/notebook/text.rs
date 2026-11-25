//! A note's bytes as the earlier Python `wissen_data.parse` read them and `encode` wrote them: the
//! `<!-- lumen: {…} -->` header (source, legacy token, portable ID, creation time), the title (the
//! first level-one heading, else the file name), tags from the body and the front matter, links,
//! the front-matter properties and the revision (SHA-256 of the bytes). Offsets and lengths count
//! Unicode code points, as Python's do; `\w`, `\s`, `isdigit` and case folding follow Python 3.14
//! (Unicode 16) through `lumen_memory::unicode`.
use super::python::{self, Py};
use super::yaml::{self, Value};
use super::{Failure, tr};
use caseless::Caseless;
use lumen_memory::unicode::{digit, whitespace, word};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::sync::LazyLock;
use unicode_normalization::UnicodeNormalization;

pub const MAX_NOTE: usize = 1024 * 1024;
/// Larger front matter is not read as properties.
const MAX_FRONT: usize = 65536;

pub fn digest(raw: &[u8]) -> String {
    Sha256::digest(raw)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// A creation time Python kept: an int or float (not a bool) between 0 and the year 10000.
pub fn timestamp(value: &Py) -> Py {
    let valid = match value {
        Py::Float(v) => *v > 0.0 && *v < 253402214400.0,
        Py::Int(digits) => {
            !digits.starts_with('-')
                && digits != "0"
                && (digits.len() < 12 || (digits.len() == 12 && digits.as_str() < "253402214400"))
        }
        _ => false,
    };
    if valid { value.clone() } else { Py::int(0) }
}

/// One `{"kind": "text"|"date", "value": …}` of the front matter.
#[derive(Clone, Debug, PartialEq)]
pub struct Property {
    pub kind: &'static str,
    pub value: String,
}

impl Property {
    /// `{"kind": …, "value": …}`.
    pub fn to_py(&self) -> Py {
        Py::Dict(vec![
            ("kind".into(), Py::str(self.kind)),
            ("value".into(), Py::str(&self.value)),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Note {
    pub path: String,
    pub note_id: String,
    pub title: String,
    pub text: String,
    pub source: String,
    pub legacy: String,
    /// `0`, an int or a float, as the header held it.
    pub created: Py,
    pub tags: Vec<String>,
    pub links: Vec<String>,
    pub hash: String,
    pub raw_size: usize,
    pub properties_source: String,
    pub properties: Vec<(String, Property)>,
}

impl Note {
    /// The dict Python returned, in its key order.
    pub fn to_py(&self) -> Py {
        let strings = |values: &[String]| Py::List(values.iter().map(|v| Py::str(v)).collect());
        Py::Dict(vec![
            ("id".into(), Py::str(&self.path)),
            ("path".into(), Py::str(&self.path)),
            ("note_id".into(), Py::str(&self.note_id)),
            ("title".into(), Py::str(&self.title)),
            ("text".into(), Py::str(&self.text)),
            ("source".into(), Py::str(&self.source)),
            ("legacy".into(), Py::str(&self.legacy)),
            ("created".into(), self.created.clone()),
            ("tags".into(), strings(&self.tags)),
            ("links".into(), strings(&self.links)),
            ("hash".into(), Py::str(&self.hash)),
            ("raw_size".into(), Py::int(self.raw_size as i64)),
            (
                "_properties_source".into(),
                Py::str(&self.properties_source),
            ),
            (
                "_properties".into(),
                Py::Dict(
                    self.properties
                        .iter()
                        .map(|(name, p)| (name.clone(), p.to_py()))
                        .collect(),
                ),
            ),
        ])
    }
}

/// `UnicodeDecodeError`: the bytes are no UTF-8.
#[derive(Debug, PartialEq)]
pub struct Undecodable(pub String);

pub fn parse(path: &str, raw: &[u8]) -> Result<Note, Undecodable> {
    let body = raw.strip_prefix(b"\xef\xbb\xbf").unwrap_or(raw);
    let decoded =
        std::str::from_utf8(body).map_err(|e| Undecodable(python::decode_error(body, e)))?;
    let (meta, text) = match header(decoded) {
        Some((Py::Dict(items), end)) => (Py::Dict(items), &decoded[end..]),
        _ => (Py::Dict(Vec::new()), decoded),
    };
    let note_id = python::uuid(&python::py_str(meta.get("note_id").unwrap_or(&Py::str(""))))
        .unwrap_or_default();
    let title = title(text).unwrap_or_else(|| stem(path));
    let text_field = |key: &str, limit: usize| {
        python::py_str(meta.get(key).unwrap_or(&Py::str("")))
            .chars()
            .take(limit)
            .collect::<String>()
    };
    let (properties_source, properties) = properties(text);
    Ok(Note {
        path: path.to_owned(),
        note_id,
        title: title.chars().take(300).collect(),
        text: text.to_owned(),
        source: text_field("source", 2000),
        legacy: text_field("legacy", 200),
        created: timestamp(meta.get("created").unwrap_or(&Py::None)),
        tags: tags(text),
        links: links(text),
        hash: digest(raw),
        raw_size: raw.len(),
        properties_source,
        properties,
    })
}

/// `^<!-- lumen: (\{[^\n]*\}) -->\n?`: the JSON and where the text after the header begins.
fn header(text: &str) -> Option<(Py, usize)> {
    const OPEN: &str = "<!-- lumen: {";
    if !text.starts_with(OPEN) {
        return None;
    }
    let line = &text[..text.find('\n').unwrap_or(text.len())];
    // The greedy group ends at the last `} -->` of the first line.
    let close = line.rfind("} -->").filter(|at| *at >= OPEN.len())?;
    let mut end = close + "} -->".len();
    if text[end..].starts_with('\n') {
        end += 1;
    }
    Some((python::loads(&text[OPEN.len() - 1..=close])?, end))
}

/// `Path(path).name`: the last component that is not empty or `.`.
pub fn name(path: &str) -> &str {
    path.rsplit('/')
        .find(|p| !p.is_empty() && *p != ".")
        .unwrap_or("")
}

/// `Path(path).suffix` as Python 3.14 has it: leading dots belong to the stem.
pub fn suffix(path: &str) -> &str {
    let trimmed = name(path).trim_start_matches('.');
    trimmed.rfind('.').map_or("", |at| &trimmed[at..])
}

/// `Path(path).stem`.
pub fn stem(path: &str) -> String {
    let name = name(path);
    name[..name.len() - suffix(path).len()].to_owned()
}

/// `str.splitlines(keepends=True)`.
pub fn lines(text: &str) -> Vec<&str> {
    let mut result = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((at, ch)) = chars.next() {
        let end = match ch {
            '\r' if chars.peek().map(|(_, c)| *c) == Some('\n') => {
                chars.next();
                at + 2
            }
            '\n' | '\r' | '\u{b}' | '\u{c}' | '\u{1c}' | '\u{1d}' | '\u{1e}' | '\u{85}'
            | '\u{2028}' | '\u{2029}' => at + ch.len_utf8(),
            _ => continue,
        };
        result.push(&text[start..end]);
        start = end;
    }
    if start < text.len() {
        result.push(&text[start..]);
    }
    result
}

static FRONT: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\A---\r?\n((?s:.)*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)").expect("front")
});

/// The front matter: the YAML inside and the byte length of the whole block.
pub fn front(text: &str) -> Option<(&str, usize)> {
    let found = FRONT.captures(text)?;
    Some((
        found.get(1).expect("group").as_str(),
        found.get(0).expect("match").end(),
    ))
}

fn strip_is_empty(text: impl IntoIterator<Item = char>) -> bool {
    text.into_iter().all(whitespace)
}

/// `note_tags.body_mask`: the text with front matter, fenced blocks, inline code and link targets
/// replaced by spaces, character for character.
pub fn body_mask(text: &str) -> Vec<char> {
    let mut chars: Vec<char> = text.chars().collect();
    if let Some((_, end)) = front(text) {
        let count = text[..end].chars().count();
        chars[..count].fill(' ');
    }
    let mut offset = 0;
    let mut fence: Option<(char, usize)> = None;
    for line in lines(text) {
        let length = line.chars().count();
        let spaces = line
            .chars()
            .take(4)
            .take_while(|c| *c == ' ')
            .count()
            .min(3);
        let rest: Vec<char> = line.chars().skip(spaces).collect();
        let marker = rest
            .first()
            .filter(|c| matches!(c, '`' | '~'))
            .map(|c| (*c, rest.iter().take_while(|v| *v == c).count()))
            .filter(|(_, count)| *count >= 3);
        let was_fenced = fence.is_some();
        if let Some((kind, count)) = marker {
            match fence {
                None => fence = Some((kind, count)),
                Some((open, size))
                    if open == kind
                        && count >= size
                        && strip_is_empty(rest[count..].iter().copied()) =>
                {
                    fence = None
                }
                _ => {}
            }
        }
        if was_fenced || marker.is_some() {
            chars[offset..offset + length].fill(' ');
        }
        offset += length;
    }
    mask_spans(&mut chars);
    chars
}

/// `re.sub(r'(`+)[\s\S]*?\1|\]\([^\n)]*\)', spaces, masked)`, the backreference resolved by hand.
fn mask_spans(chars: &mut [char]) {
    // Maximal runs of backticks in the text the expression reads.
    let mut runs: Vec<(usize, usize)> = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '`' {
            let start = i;
            while i < chars.len() && chars[i] == '`' {
                i += 1;
            }
            runs.push((start, i - start));
        } else {
            i += 1;
        }
    }
    let original = chars.to_vec();
    let mut i = 0;
    while i < original.len() {
        let end = if original[i] == '`' {
            let run = runs.partition_point(|(start, len)| start + len <= i);
            let (start, len) = runs[run];
            let size = start + len - i;
            // The group gives back backticks until the lazy body finds as many again.
            (1..=size).rev().find_map(|m| {
                if size - m >= m {
                    return Some(i + 2 * m);
                }
                runs[run + 1..]
                    .iter()
                    .find(|(_, len)| *len >= m)
                    .map(|(start, _)| start + m)
            })
        } else if original[i] == ']' && original.get(i + 1) == Some(&'(') {
            original[i + 2..]
                .iter()
                .position(|c| matches!(c, ')' | '\n'))
                .filter(|at| original[i + 2 + at] == ')')
                .map(|at| i + 2 + at + 1)
        } else {
            None
        };
        match end {
            Some(end) => {
                chars[i..end].fill(' ');
                i = end;
            }
            None => i += 1,
        }
    }
}

/// `[\s\x1c-\x1f]`, Python's `\s`.
const SPACE: &str = r"[\s\x1c-\x1f]";

static ATX: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(&format!(
        r"\A {{0,3}}(#{{1,6}}){SPACE}+(.+?){SPACE}*#*{SPACE}*\z"
    ))
    .expect("atx")
});
static SETEXT: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(&format!(r"\A {{0,3}}(?:=+|-+){SPACE}*\z")).expect("setext"));
static LINK_TEXT: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[([^\]]+)\]\([^)]*\)").expect("link text"));
static MARKUP: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[*_`~]").expect("markup"));

/// `notes_structure.heading_name`.
fn heading_name(value: &str) -> String {
    let value = LINK_TEXT.replace_all(value, "${1}");
    MARKUP
        .replace_all(&value, "")
        .trim_matches(whitespace)
        .to_owned()
}

/// A heading (`level` 1 to 6) or a block ID (`^id`, level 0) of `notes_structure.targets`: its title
/// and the code point where it starts.
#[derive(Debug, PartialEq)]
pub struct Target {
    pub title: String,
    pub start: usize,
    pub level: usize,
}

/// `notes_structure.targets`: ATX and underlined headings and block IDs outside code, with their
/// positions in the unchanged text. A standalone block ID names the paragraph above it.
pub fn targets(text: &str) -> Vec<Target> {
    let mask = body_mask(text);
    let lines = lines(text);
    let mut offsets = vec![0];
    for line in &lines {
        offsets.push(offsets.last().unwrap() + line.chars().count());
    }
    let masked: Vec<&[char]> = (0..lines.len())
        .map(|i| &mask[offsets[i]..offsets[i + 1]])
        .collect();
    let visible = |i: usize| !strip_is_empty(masked[i].iter().copied());
    let mut result = Vec::new();
    for (index, line) in lines.iter().enumerate() {
        if let Some(found) = ATX.captures(line.trim_end_matches(['\r', '\n']))
            && visible(index)
        {
            result.push(Target {
                title: heading_name(&found[2]),
                start: offsets[index],
                level: found[1].len(),
            });
        } else if index + 1 < lines.len()
            && visible(index)
            && SETEXT.is_match(&masked[index + 1].iter().collect::<String>())
        {
            result.push(Target {
                title: heading_name(line.trim_matches(whitespace)),
                start: offsets[index],
                level: if lines[index + 1].contains('=') { 1 } else { 2 },
            });
        }
        if let Some((at, id)) = block(masked[index]) {
            let mut start = offsets[index];
            if strip_is_empty(line.chars().take(at)) {
                let mut previous = index;
                while previous > 0 && strip_is_empty(lines[previous - 1].chars()) {
                    previous -= 1;
                }
                while previous > 0 && visible(previous - 1) {
                    start = offsets[previous - 1];
                    previous -= 1;
                }
            }
            result.push(Target {
                title: format!("^{id}"),
                start,
                level: 0,
            });
        }
    }
    result
}

/// `re.search(r'(?:^|\s)\^([\w-]+)\s*$', visible.rstrip('\r\n'))`: where the match starts and the ID.
/// Word characters and `-` are no white space, so the only match ends the line.
fn block(visible: &[char]) -> Option<(usize, String)> {
    let mut end = visible.len();
    while end > 0 && matches!(visible[end - 1], '\r' | '\n') {
        end -= 1;
    }
    while end > 0 && whitespace(visible[end - 1]) {
        end -= 1;
    }
    let mut start = end;
    while start > 0 && (word(visible[start - 1]) || visible[start - 1] == '-') {
        start -= 1;
    }
    if start == end || start == 0 || visible[start - 1] != '^' {
        return None;
    }
    let id = visible[start..end].iter().collect();
    match start - 1 {
        0 => Some((0, id)),
        caret if whitespace(visible[caret - 1]) => Some((caret - 1, id)),
        _ => None,
    }
}

/// The first level-one heading (ATX or `===` underlined).
fn title(text: &str) -> Option<String> {
    targets(text)
        .into_iter()
        .find(|t| t.level == 1)
        .map(|t| t.title)
}

static CODE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?s)```.*?```|~~~.*?~~~|`[^`]*`").expect("code"));
static WIKI: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\[\[([^\]\n]+)\]\]").expect("wiki"));
static MARKDOWN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[[^\]\n]*\]\(([^)\n]+)\)").expect("markdown"));

/// Wiki links, then Markdown links that are no images, outside code.
fn links(text: &str) -> Vec<String> {
    let plain = CODE.replace_all(text, "");
    let mut result: Vec<String> = WIKI
        .captures_iter(&plain)
        .map(|c| c[1].to_owned())
        .collect();
    // `(?<!!)`: a match after `!` is skipped and the search goes on one character later.
    let mut at = 0;
    while let Some(found) = MARKDOWN.captures_at(&plain, at) {
        let start = found.get(0).expect("match").start();
        if plain[..start].ends_with('!') {
            at = start + 1;
            continue;
        }
        result.push(found[1].to_owned());
        at = found.get(0).expect("match").end();
    }
    result
}

/// `note_tags.identity`: NFC, case folded, word characters, `/` and `-`, not only digits.
pub fn identity(value: &str) -> Option<String> {
    let value: String = value
        .trim_matches(whitespace)
        .trim_start_matches('#')
        .nfc()
        .default_case_fold()
        .collect();
    let valid = !value.is_empty()
        && value.chars().all(|c| word(c) || matches!(c, '/' | '-'))
        && value.chars().any(|c| !digit(c) && c != '/')
        && value.split('/').all(|part| !part.is_empty());
    valid.then_some(value)
}

/// `TAG.finditer(body_mask(text))` of `note_tags`: where each `#tag` of the visible body starts and
/// ends, `(?<![\w/#\\])#([\w/-]+)`.
pub fn hashtags(masked: &[char]) -> Vec<(usize, usize)> {
    let mut result = Vec::new();
    let mut i = 0;
    while i < masked.len() {
        let free = i == 0 || !(word(masked[i - 1]) || matches!(masked[i - 1], '/' | '#' | '\\'));
        if masked[i] == '#' && free {
            let mut j = i + 1;
            while j < masked.len() && (word(masked[j]) || matches!(masked[j], '/' | '-')) {
                j += 1;
            }
            if j > i + 1 {
                result.push((i, j));
                i = j;
                continue;
            }
        }
        i += 1;
    }
    result
}

/// `note_tags.tags`: `#tags` of the visible body and the front matter's `tags`, at most 100.
pub fn tags(text: &str) -> Vec<String> {
    let masked = body_mask(text);
    let mut values: Vec<String> = hashtags(&masked)
        .into_iter()
        .map(|(start, end)| masked[start + 1..end].iter().collect())
        .collect();
    if let Ok(Some((front, Some((_, value))))) = tag_front(text)
        && let Some(document) = &front.document
        && let Some(more) = tag_values(document, value)
    {
        values.extend(more);
    }
    let mut result: Vec<String> = values.iter().filter_map(|v| identity(v)).collect();
    result.sort();
    result.dedup();
    result.truncate(100);
    result
}

/// The front matter of a text: its YAML, where that starts and ends (code points of the text)
/// and its nodes (`None` for an empty document).
pub struct Front<'t> {
    pub yaml: &'t str,
    pub start: usize,
    pub end: usize,
    pub document: Option<yaml::Document>,
}

impl Front<'_> {
    /// The YAML's composed root.
    pub fn root(&self) -> Option<&yaml::Node> {
        self.document.as_ref().map(|d| &d.nodes[d.root])
    }

    /// The node `id` of the YAML.
    pub fn node(&self, id: usize) -> &yaml::Node {
        &self.document.as_ref().expect("a node of a document").nodes[id]
    }

    /// The mapping's key and value ids.
    pub fn pairs(&self) -> &[(usize, usize)] {
        match self.root().map(|n| &n.value) {
            Some(Value::Mapping(pairs)) => pairs,
            _ => &[],
        }
    }

    /// The text of a scalar node.
    pub fn scalar(&self, id: usize) -> Option<&str> {
        match &self.node(id).value {
            Value::Scalar(value) => Some(value),
            _ => None,
        }
    }
}

/// `FRONT.match(text)` composed as `yaml.compose`: `None` without front matter, a refusal for front
/// matter above 64 KiB or that is no YAML.
fn compose(text: &str) -> Result<Option<Front<'_>>, Failure> {
    let Some(found) = FRONT.captures(text) else {
        return Ok(None);
    };
    let group = found.get(1).expect("group");
    let yaml = group.as_str();
    let length = yaml.chars().count();
    if length > MAX_FRONT {
        return Err(tr("Notizeigenschaften sind zu groß."));
    }
    let document = yaml::compose(yaml).map_err(|_| tr("Ungültige Notizeigenschaften."))?;
    let start = text[..group.start()].chars().count();
    Ok(Some(Front {
        yaml,
        start,
        end: start + length,
        document,
    }))
}

/// A front matter and the key and value ids of its `tags`.
pub type TagFront<'t> = (Front<'t>, Option<(usize, usize)>);

/// `note_tags.frontmatter`: the front matter and its `tags` key and value, refused as Python
/// refused it.
pub fn tag_front(text: &str) -> Result<Option<TagFront<'_>>, Failure> {
    let Some(front) = compose(text)? else {
        return Ok(None);
    };
    if front
        .root()
        .is_some_and(|root| !matches!(root.value, Value::Mapping(_)))
    {
        return Err(tr("Notizeigenschaften benötigen benannte Felder."));
    }
    let tagged: Vec<(usize, usize)> = front
        .pairs()
        .iter()
        .filter(|(key, _)| front.scalar(*key) == Some("tags"))
        .copied()
        .collect();
    match tagged.as_slice() {
        [] => Ok(Some((front, None))),
        [pair] => Ok(Some((front, Some(*pair)))),
        _ => Err(tr("Das Tags-Feld ist mehrfach vorhanden.")),
    }
}

/// `note_tags.yaml_tags`: the texts of a `tags` value (a list's items, else split at commas);
/// `None` where Python refused a value that is no text.
pub fn tag_values(document: &yaml::Document, value: usize) -> Option<Vec<String>> {
    let (items, sequence) = match &document.nodes[value].value {
        Value::Sequence(items) => (items.clone(), true),
        _ => (vec![value], false),
    };
    let mut result = Vec::new();
    for id in items {
        let node = &document.nodes[id];
        let Value::Scalar(value) = &node.value else {
            return None;
        };
        if node.tag.ends_with(":null") {
            continue;
        }
        if sequence {
            result.push(value.clone());
        } else {
            result.extend(value.split(',').map(str::to_owned));
        }
    }
    Some(result)
}

/// `notes_properties.for_note`: the front matter's text and its simple named values.
fn properties(text: &str) -> (String, Vec<(String, Property)>) {
    let source = front(text)
        .map(|(yaml, _)| yaml.to_owned())
        .unwrap_or_default();
    let values = property_values(text).unwrap_or_default();
    (source, values)
}

/// `[\w][\w .-]{0,79}`.
pub fn property_name(name: &str) -> bool {
    let mut chars = name.chars();
    chars.next().is_some_and(word)
        && name.chars().count() <= 80
        && chars.all(|c| word(c) || matches!(c, ' ' | '.' | '-'))
}

/// `notes_properties.document`: front matter of named YAML lines with text names that occur once.
pub fn property_document(text: &str) -> Result<Option<Front<'_>>, Failure> {
    let Some(front) = compose(text)? else {
        return if text.starts_with("---\n") || text.starts_with("---\r\n") {
            Err(tr("Ungültige Notizeigenschaften."))
        } else {
            Ok(None)
        };
    };
    if front
        .root()
        .is_some_and(|root| !matches!(root.value, Value::Mapping(_)) || root.flow)
    {
        return Err(tr("Eigenschaften zuerst als benannte YAML-Zeilen anlegen."));
    }
    let keys = front.pairs().iter().map(|(key, _)| *key);
    if keys
        .clone()
        .any(|key| front.scalar(key).is_none() || !front.node(key).tag.ends_with(":str"))
    {
        return Err(tr("Eigenschaftsnamen müssen Text sein."));
    }
    let mut names: Vec<&str> = keys.filter_map(|key| front.scalar(key)).collect();
    let count = names.len();
    names.sort_unstable();
    names.dedup();
    if names.len() != count {
        return Err(tr("Eine Eigenschaft ist mehrfach vorhanden."));
    }
    Ok(Some(front))
}

/// `notes_properties.values`.
pub fn property_values(text: &str) -> Result<Vec<(String, Property)>, Failure> {
    let Some(front) = property_document(text)? else {
        return Ok(Vec::new());
    };
    let chars: Vec<char> = front.yaml.chars().collect();
    let mut result = Vec::new();
    for (key, value) in front.pairs() {
        let (key, value) = (front.node(*key), front.node(*value));
        let (Value::Scalar(name), Value::Scalar(content)) = (&key.value, &value.value) else {
            continue;
        };
        if name == "tags" || !property_name(name) {
            continue;
        }
        let date = value.tag.ends_with(":timestamp");
        if !(value.tag.ends_with(":str") || date) {
            continue;
        }
        // An alias (its node lies before the key) or an anchored value stays as it is.
        if value.start.index < key.end.index
            || matches!(chars.get(value.start.index), Some('&' | '*'))
        {
            continue;
        }
        if date && !iso_date(content) {
            continue;
        }
        result.push((
            name.clone(),
            Property {
                kind: if date { "date" } else { "text" },
                value: content.clone(),
            },
        ));
    }
    Ok(result)
}

/// `date.fromisoformat` for what YAML resolved as a timestamp: only `YYYY-MM-DD` is a date.
pub fn iso_date(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return false;
    }
    let number = |range: std::ops::Range<usize>| {
        value
            .get(range)
            .filter(|v| v.bytes().all(|b| b.is_ascii_digit()))
            .and_then(|v| v.parse::<u32>().ok())
    };
    let (Some(year), Some(month), Some(day)) = (number(0..4), number(5..7), number(8..10)) else {
        return false;
    };
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    year >= 1 && (1..=12).contains(&month) && day >= 1 && day <= days[month as usize - 1]
}

/// `encode`: the header (when any of its values is set) and the text, as UTF-8.
pub fn encode(
    text: &str,
    source: &Py,
    legacy: &Py,
    created: &Py,
    note_id: &str,
) -> Result<Vec<u8>, EncodeError> {
    let mut meta = Py::Dict(vec![
        ("source".into(), source.clone()),
        ("legacy".into(), legacy.clone()),
    ]);
    if !note_id.is_empty() {
        meta.set(
            "note_id",
            Py::str(&python::uuid(note_id).ok_or(EncodeError::Uuid)?),
        );
    }
    let valid_created = timestamp(created).truthy();
    if valid_created {
        meta.set("created", created.clone());
    }
    let mut raw = String::new();
    if source.truthy() || legacy.truthy() || valid_created || !note_id.is_empty() {
        raw.push_str("<!-- lumen: ");
        raw.push_str(&python::dumps(&meta, false));
        raw.push_str(" -->\n");
    }
    raw.push_str(text);
    if raw.len() > MAX_NOTE {
        return Err(EncodeError::Large);
    }
    Ok(raw.into_bytes())
}

#[derive(Debug, PartialEq)]
pub enum EncodeError {
    /// `ValueError('badly formed hexadecimal UUID string')`.
    Uuid,
    Large,
}

/// The stop words of `content_search.STOP_WORDS`, which the Python search still uses.
pub const STOP_WORDS: &str = "der die das den dem des ein eine einen einem einer eines für fuer von vom zum zur zu \
und oder mit ohne im in auf am an aus bei nach über ueber unter ich du mir mich mein \
meine meinen meinem meiner meines bitte suche suchen finde finden zeige zeigen wo ist \
sind liegt liegen habe haben hast hat hatte wurde wurden es sich welche welcher welches \
datei dateien dokument dokumente the a an for of with and or in on my me find show is are";

/// `excerpt`: up to `limit` characters around the first query term, `…` where text was left out.
/// Like Python it finds the term in the case-folded text and cuts the original at that index.
pub fn excerpt(text: &str, query: &str, limit: usize) -> String {
    let stop: Vec<&str> = STOP_WORDS.split(' ').collect();
    let query: String = query.chars().default_case_fold().collect();
    let mut terms: Vec<String> = Vec::new();
    let mut current = String::new();
    for ch in query.chars().chain([' ']) {
        if word(ch) {
            current.push(ch);
        } else if !current.is_empty() {
            terms.push(std::mem::take(&mut current));
        }
    }
    let terms: Vec<String> = terms
        .into_iter()
        .filter(|t| !stop.contains(&t.as_str()) && t.chars().count() > 1)
        .take(12)
        .collect();
    let folded: String = text.chars().default_case_fold().collect();
    let start = terms
        .iter()
        .filter_map(|t| {
            folded
                .find(t.as_str())
                .map(|at| folded[..at].chars().count())
        })
        .min()
        .map(|first| first.saturating_sub(limit / 4))
        .unwrap_or(0);
    let length = text.chars().count();
    let mut out = String::new();
    if start > 0 {
        out.push_str("…\n");
    }
    out.extend(text.chars().skip(start).take(limit));
    if start + limit < length {
        out.push_str("\n…");
    }
    out
}

/// `re.sub(r'[^\w .-]', '-', title).strip('. ')[:100] or 'Notiz'`, the file name of a new note.
pub fn file_stem(title: &str) -> String {
    let replaced: String = title
        .chars()
        .map(|c| {
            if word(c) || matches!(c, ' ' | '.' | '-') {
                c
            } else {
                '-'
            }
        })
        .collect();
    let stem: String = replaced
        .trim_matches(['.', ' '])
        .chars()
        .take(100)
        .collect();
    if stem.is_empty() {
        "Notiz".into()
    } else {
        stem
    }
}

/// `' '.join(title.split()).strip()[:200]`.
pub fn clean_title(title: &str) -> String {
    title
        .split(whitespace)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(200)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lines_split_where_python_splits_them() {
        assert_eq!(
            lines("a\r\nb\rc\nd\u{2028}e\u{85}f\u{1c}g"),
            [
                "a\r\n",
                "b\r",
                "c\n",
                "d\u{2028}",
                "e\u{85}",
                "f\u{1c}",
                "g"
            ]
        );
        assert_eq!(lines(""), Vec::<&str>::new());
        assert_eq!(lines("x\n"), ["x\n"]);
    }

    #[test]
    fn stems_follow_pathlib() {
        for (path, stem_) in [
            ("a.md", "a"),
            ("a.", "a"),
            (".md", ".md"),
            ("x/.hidden.md", ".hidden"),
            ("", ""),
            (".", ""),
            ("x//y.md", "y"),
            ("x/", "x"),
            ("a..md", "a."),
        ] {
            assert_eq!(stem(path), stem_, "{path}");
        }
    }

    #[test]
    fn backtick_spans_mask_as_the_backreference_does() {
        let mask = |text: &str| -> String { body_mask(text).into_iter().collect() };
        assert_eq!(mask("``"), "  ");
        assert_eq!(mask("```"), "   ");
        assert_eq!(mask("a `b` c"), "a     c");
        assert_eq!(mask("`` a ` b ``"), "           ");
        assert_eq!(mask("` x"), "` x");
        assert_eq!(mask("[t](u) ](v"), "[t     ](v");
    }
}

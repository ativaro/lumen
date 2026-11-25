//! `yaml.compose(text, Loader=yaml.SafeLoader)` of PyYAML 6, which the earlier Python Notes read
//! front matter with: its reader, scanner, parser and composer ported statement by statement, so
//! the same front matter is accepted or refused and yields the same nodes, tags and marks (code
//! point indexes). Only what composing needs is kept: no constructor, no error texts.
use std::collections::{BTreeMap, HashMap, VecDeque};

/// A refusal: PyYAML raised a `YAMLError`, or Python's recursion limit would have been reached.
#[derive(Debug, PartialEq)]
pub struct Invalid;

type Result<T> = std::result::Result<T, Invalid>;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Mark {
    pub index: usize,
    line: usize,
    column: usize,
}

#[derive(Debug)]
pub enum Value {
    Scalar(String),
    Sequence(Vec<usize>),
    /// Key and value ids in turn.
    Mapping(Vec<(usize, usize)>),
}

#[derive(Debug)]
pub struct Node {
    pub tag: String,
    pub value: Value,
    pub start: Mark,
    pub end: Mark,
    pub flow: bool,
}

pub struct Document {
    pub nodes: Vec<Node>,
    pub root: usize,
}

/// Nesting deeper than this hit Python's recursion limit in `compose_node`.
const DEPTH: usize = 450;

pub fn compose(text: &str) -> Result<Option<Document>> {
    // Reader.check_printable
    if !text.chars().all(|c| {
        matches!(c, '\t' | '\n' | '\r' | ' '..='~' | '\u{85}' | '\u{a0}'..='\u{d7ff}' | '\u{e000}'..='\u{fffd}' | '\u{10000}'..)
    }) {
        return Err(Invalid);
    }
    let mut parser = Parser::new(text);
    let mut composer = Composer {
        nodes: Vec::new(),
        anchors: HashMap::new(),
    };
    // get_single_node
    parser.get_event()?;
    let mut root = None;
    if !matches!(parser.peek_event()?, Event::StreamEnd) {
        root = Some(composer.document(&mut parser)?);
    }
    if !matches!(parser.peek_event()?, Event::StreamEnd) {
        return Err(Invalid);
    }
    parser.get_event()?;
    Ok(root.map(|root| Document {
        nodes: composer.nodes,
        root,
    }))
}

// ------------------------------------------------------------------ reader and scanner

const BREAKZ: &str = "\0 \t\r\n\u{85}\u{2028}\u{2029}";
const LINE_BREAKS: &str = "\r\n\u{85}\u{2028}\u{2029}";

fn among(ch: char, set: &str) -> bool {
    set.contains(ch)
}

fn ascii_word(ch: char) -> bool {
    ch.is_ascii_alphanumeric() || ch == '-' || ch == '_'
}

#[derive(Debug)]
enum Kind {
    StreamStart,
    StreamEnd,
    Directive(String, Option<(u64, u64)>, Option<(String, String)>),
    DocumentStart,
    DocumentEnd,
    BlockSequenceStart,
    BlockMappingStart,
    BlockEnd,
    FlowSequenceStart,
    FlowMappingStart,
    FlowSequenceEnd,
    FlowMappingEnd,
    BlockEntry,
    FlowEntry,
    Key,
    Value,
    Alias(String),
    Anchor(String),
    Tag(Option<String>, String),
    Scalar(String, bool),
}

#[derive(Debug)]
struct Token {
    kind: Kind,
    start: Mark,
    end: Mark,
}

struct SimpleKey {
    token_number: usize,
    required: bool,
    index: usize,
    line: usize,
    column: usize,
    mark: Mark,
}

struct Scanner {
    buffer: Vec<char>,
    pointer: usize,
    line: usize,
    column: usize,
    done: bool,
    flow_level: usize,
    tokens: VecDeque<Token>,
    tokens_taken: usize,
    indent: i64,
    indents: Vec<i64>,
    allow_simple_key: bool,
    possible_simple_keys: BTreeMap<usize, SimpleKey>,
}

impl Scanner {
    fn new(text: &str) -> Self {
        let mut buffer: Vec<char> = text.chars().collect();
        buffer.push('\0');
        let mut scanner = Scanner {
            buffer,
            pointer: 0,
            line: 0,
            column: 0,
            done: false,
            flow_level: 0,
            tokens: VecDeque::new(),
            tokens_taken: 0,
            indent: -1,
            indents: Vec::new(),
            allow_simple_key: true,
            possible_simple_keys: BTreeMap::new(),
        };
        let mark = scanner.mark();
        scanner.tokens.push_back(Token {
            kind: Kind::StreamStart,
            start: mark,
            end: mark,
        });
        scanner
    }

    // Reader
    fn peek(&self, index: usize) -> Result<char> {
        self.buffer
            .get(self.pointer + index)
            .copied()
            .ok_or(Invalid)
    }
    fn ch(&self) -> char {
        self.buffer[self.pointer]
    }
    fn prefix(&self, length: usize) -> String {
        let end = (self.pointer + length).min(self.buffer.len());
        self.buffer[self.pointer..end].iter().collect()
    }
    fn forward(&mut self, length: usize) -> Result<()> {
        for _ in 0..length {
            let ch = *self.buffer.get(self.pointer).ok_or(Invalid)?;
            self.pointer += 1;
            if among(ch, "\n\u{85}\u{2028}\u{2029}")
                || (ch == '\r' && self.buffer.get(self.pointer) != Some(&'\n'))
            {
                self.line += 1;
                self.column = 0;
            } else if ch != '\u{feff}' {
                self.column += 1;
            }
        }
        Ok(())
    }
    fn mark(&self) -> Mark {
        Mark {
            index: self.pointer,
            line: self.line,
            column: self.column,
        }
    }

    fn check_token(&mut self, choices: &[fn(&Kind) -> bool]) -> Result<bool> {
        while self.need_more_tokens()? {
            self.fetch_more_tokens()?;
        }
        Ok(self
            .tokens
            .front()
            .is_some_and(|t| choices.is_empty() || choices.iter().any(|c| c(&t.kind))))
    }
    fn peek_token(&mut self) -> Result<Option<&Token>> {
        while self.need_more_tokens()? {
            self.fetch_more_tokens()?;
        }
        Ok(self.tokens.front())
    }
    fn get_token(&mut self) -> Result<Option<Token>> {
        while self.need_more_tokens()? {
            self.fetch_more_tokens()?;
        }
        let token = self.tokens.pop_front();
        if token.is_some() {
            self.tokens_taken += 1;
        }
        Ok(token)
    }
    fn need_more_tokens(&mut self) -> Result<bool> {
        if self.done {
            return Ok(false);
        }
        if self.tokens.is_empty() {
            return Ok(true);
        }
        self.stale_possible_simple_keys()?;
        Ok(self.next_possible_simple_key() == Some(self.tokens_taken))
    }
    fn fetch_more_tokens(&mut self) -> Result<()> {
        self.scan_to_next_token()?;
        self.stale_possible_simple_keys()?;
        self.unwind_indent(self.column as i64);
        let ch = self.ch();
        if ch == '\0' {
            return self.fetch_stream_end();
        }
        if ch == '%' && self.column == 0 {
            return self.fetch_directive();
        }
        if ch == '-' && self.check_document_indicator("---")? {
            return self.fetch_document_indicator(Kind::DocumentStart);
        }
        if ch == '.' && self.check_document_indicator("...")? {
            return self.fetch_document_indicator(Kind::DocumentEnd);
        }
        match ch {
            '[' => return self.fetch_flow_collection_start(Kind::FlowSequenceStart),
            '{' => return self.fetch_flow_collection_start(Kind::FlowMappingStart),
            ']' => return self.fetch_flow_collection_end(Kind::FlowSequenceEnd),
            '}' => return self.fetch_flow_collection_end(Kind::FlowMappingEnd),
            ',' => return self.fetch_flow_entry(),
            _ => {}
        }
        if ch == '-' && among(self.peek(1)?, BREAKZ) {
            return self.fetch_block_entry();
        }
        if ch == '?' && (self.flow_level > 0 || among(self.peek(1)?, BREAKZ)) {
            return self.fetch_key();
        }
        if ch == ':' && (self.flow_level > 0 || among(self.peek(1)?, BREAKZ)) {
            return self.fetch_value();
        }
        match ch {
            '*' => return self.fetch_anchor(true),
            '&' => return self.fetch_anchor(false),
            '!' => return self.fetch_tag(),
            '|' if self.flow_level == 0 => return self.fetch_block_scalar(false),
            '>' if self.flow_level == 0 => return self.fetch_block_scalar(true),
            '\'' => return self.fetch_flow_scalar(false),
            '"' => return self.fetch_flow_scalar(true),
            _ => {}
        }
        if self.check_plain()? {
            return self.fetch_plain();
        }
        Err(Invalid)
    }

    fn next_possible_simple_key(&self) -> Option<usize> {
        self.possible_simple_keys
            .values()
            .map(|k| k.token_number)
            .min()
    }
    fn stale_possible_simple_keys(&mut self) -> Result<()> {
        let levels: Vec<usize> = self.possible_simple_keys.keys().copied().collect();
        for level in levels {
            let key = &self.possible_simple_keys[&level];
            if key.line != self.line || self.pointer - key.index > 1024 {
                if key.required {
                    return Err(Invalid);
                }
                self.possible_simple_keys.remove(&level);
            }
        }
        Ok(())
    }
    fn save_possible_simple_key(&mut self) -> Result<()> {
        let required = self.flow_level == 0 && self.indent == self.column as i64;
        if self.allow_simple_key {
            self.remove_possible_simple_key()?;
            let token_number = self.tokens_taken + self.tokens.len();
            let key = SimpleKey {
                token_number,
                required,
                index: self.pointer,
                line: self.line,
                column: self.column,
                mark: self.mark(),
            };
            self.possible_simple_keys.insert(self.flow_level, key);
        }
        Ok(())
    }
    fn remove_possible_simple_key(&mut self) -> Result<()> {
        if let Some(key) = self.possible_simple_keys.get(&self.flow_level) {
            if key.required {
                return Err(Invalid);
            }
            self.possible_simple_keys.remove(&self.flow_level);
        }
        Ok(())
    }
    fn unwind_indent(&mut self, column: i64) {
        if self.flow_level > 0 {
            return;
        }
        while self.indent > column {
            let mark = self.mark();
            self.indent = self.indents.pop().unwrap_or(-1);
            self.tokens.push_back(Token {
                kind: Kind::BlockEnd,
                start: mark,
                end: mark,
            });
        }
    }
    fn add_indent(&mut self, column: i64) -> bool {
        if self.indent < column {
            self.indents.push(self.indent);
            self.indent = column;
            return true;
        }
        false
    }
    fn push(&mut self, kind: Kind, start: Mark) {
        let end = self.mark();
        self.tokens.push_back(Token { kind, start, end });
    }

    fn fetch_stream_end(&mut self) -> Result<()> {
        self.unwind_indent(-1);
        self.remove_possible_simple_key()?;
        self.allow_simple_key = false;
        self.possible_simple_keys.clear();
        let mark = self.mark();
        self.tokens.push_back(Token {
            kind: Kind::StreamEnd,
            start: mark,
            end: mark,
        });
        self.done = true;
        Ok(())
    }
    fn fetch_directive(&mut self) -> Result<()> {
        self.unwind_indent(-1);
        self.remove_possible_simple_key()?;
        self.allow_simple_key = false;
        let token = self.scan_directive()?;
        self.tokens.push_back(token);
        Ok(())
    }
    fn check_document_indicator(&self, indicator: &str) -> Result<bool> {
        Ok(self.column == 0 && self.prefix(3) == indicator && among(self.peek(3)?, BREAKZ))
    }
    fn fetch_document_indicator(&mut self, kind: Kind) -> Result<()> {
        self.unwind_indent(-1);
        self.remove_possible_simple_key()?;
        self.allow_simple_key = false;
        let start = self.mark();
        self.forward(3)?;
        self.push(kind, start);
        Ok(())
    }
    fn fetch_flow_collection_start(&mut self, kind: Kind) -> Result<()> {
        self.save_possible_simple_key()?;
        self.flow_level += 1;
        self.allow_simple_key = true;
        let start = self.mark();
        self.forward(1)?;
        self.push(kind, start);
        Ok(())
    }
    fn fetch_flow_collection_end(&mut self, kind: Kind) -> Result<()> {
        self.remove_possible_simple_key()?;
        // Python's flow_level may go below zero here; the parser then refuses the token.
        self.flow_level = self.flow_level.saturating_sub(1);
        self.allow_simple_key = false;
        let start = self.mark();
        self.forward(1)?;
        self.push(kind, start);
        Ok(())
    }
    fn fetch_flow_entry(&mut self) -> Result<()> {
        self.allow_simple_key = true;
        self.remove_possible_simple_key()?;
        let start = self.mark();
        self.forward(1)?;
        self.push(Kind::FlowEntry, start);
        Ok(())
    }
    fn fetch_block_entry(&mut self) -> Result<()> {
        if self.flow_level == 0 {
            if !self.allow_simple_key {
                return Err(Invalid);
            }
            if self.add_indent(self.column as i64) {
                let mark = self.mark();
                self.tokens.push_back(Token {
                    kind: Kind::BlockSequenceStart,
                    start: mark,
                    end: mark,
                });
            }
        }
        self.allow_simple_key = true;
        self.remove_possible_simple_key()?;
        let start = self.mark();
        self.forward(1)?;
        self.push(Kind::BlockEntry, start);
        Ok(())
    }
    fn fetch_key(&mut self) -> Result<()> {
        if self.flow_level == 0 {
            if !self.allow_simple_key {
                return Err(Invalid);
            }
            if self.add_indent(self.column as i64) {
                let mark = self.mark();
                self.tokens.push_back(Token {
                    kind: Kind::BlockMappingStart,
                    start: mark,
                    end: mark,
                });
            }
        }
        self.allow_simple_key = self.flow_level == 0;
        self.remove_possible_simple_key()?;
        let start = self.mark();
        self.forward(1)?;
        self.push(Kind::Key, start);
        Ok(())
    }
    fn fetch_value(&mut self) -> Result<()> {
        if let Some(key) = self.possible_simple_keys.remove(&self.flow_level) {
            let at = key.token_number - self.tokens_taken;
            self.tokens.insert(
                at,
                Token {
                    kind: Kind::Key,
                    start: key.mark,
                    end: key.mark,
                },
            );
            if self.flow_level == 0 && self.add_indent(key.column as i64) {
                self.tokens.insert(
                    at,
                    Token {
                        kind: Kind::BlockMappingStart,
                        start: key.mark,
                        end: key.mark,
                    },
                );
            }
            self.allow_simple_key = false;
        } else {
            if self.flow_level == 0 && !self.allow_simple_key {
                return Err(Invalid);
            }
            if self.flow_level == 0 && self.add_indent(self.column as i64) {
                let mark = self.mark();
                self.tokens.push_back(Token {
                    kind: Kind::BlockMappingStart,
                    start: mark,
                    end: mark,
                });
            }
            self.allow_simple_key = self.flow_level == 0;
            self.remove_possible_simple_key()?;
        }
        let start = self.mark();
        self.forward(1)?;
        self.push(Kind::Value, start);
        Ok(())
    }
    fn fetch_anchor(&mut self, alias: bool) -> Result<()> {
        self.save_possible_simple_key()?;
        self.allow_simple_key = false;
        let token = self.scan_anchor(alias)?;
        self.tokens.push_back(token);
        Ok(())
    }
    fn fetch_tag(&mut self) -> Result<()> {
        self.save_possible_simple_key()?;
        self.allow_simple_key = false;
        let token = self.scan_tag()?;
        self.tokens.push_back(token);
        Ok(())
    }
    fn fetch_block_scalar(&mut self, folded: bool) -> Result<()> {
        self.allow_simple_key = true;
        self.remove_possible_simple_key()?;
        let token = self.scan_block_scalar(folded)?;
        self.tokens.push_back(token);
        Ok(())
    }
    fn fetch_flow_scalar(&mut self, double: bool) -> Result<()> {
        self.save_possible_simple_key()?;
        self.allow_simple_key = false;
        let token = self.scan_flow_scalar(double)?;
        self.tokens.push_back(token);
        Ok(())
    }
    fn fetch_plain(&mut self) -> Result<()> {
        self.save_possible_simple_key()?;
        self.allow_simple_key = false;
        let token = self.scan_plain()?;
        self.tokens.push_back(token);
        Ok(())
    }
    fn check_plain(&self) -> Result<bool> {
        let ch = self.ch();
        Ok(
            !among(ch, "\0 \t\r\n\u{85}\u{2028}\u{2029}-?:,[]{}#&*!|>'\"%@`")
                || (!among(self.peek(1)?, BREAKZ)
                    && (ch == '-' || (self.flow_level == 0 && among(ch, "?:")))),
        )
    }

    fn scan_to_next_token(&mut self) -> Result<()> {
        if self.pointer == 0 && self.ch() == '\u{feff}' {
            self.forward(1)?;
        }
        loop {
            while self.ch() == ' ' {
                self.forward(1)?;
            }
            if self.ch() == '#' {
                while !among(self.ch(), "\0\r\n\u{85}\u{2028}\u{2029}") {
                    self.forward(1)?;
                }
            }
            if self.scan_line_break()?.is_empty() {
                return Ok(());
            }
            if self.flow_level == 0 {
                self.allow_simple_key = true;
            }
        }
    }
    fn scan_directive(&mut self) -> Result<Token> {
        let start = self.mark();
        self.forward(1)?;
        let name = self.scan_directive_name()?;
        let (mut version, mut tag) = (None, None);
        let end;
        if name == "YAML" {
            version = Some(self.scan_yaml_directive_value()?);
            end = self.mark();
        } else if name == "TAG" {
            tag = Some(self.scan_tag_directive_value()?);
            end = self.mark();
        } else {
            end = self.mark();
            while !among(self.ch(), "\0\r\n\u{85}\u{2028}\u{2029}") {
                self.forward(1)?;
            }
        }
        self.scan_directive_ignored_line()?;
        Ok(Token {
            kind: Kind::Directive(name, version, tag),
            start,
            end,
        })
    }
    fn scan_directive_name(&mut self) -> Result<String> {
        let mut length = 0;
        while ascii_word(self.peek(length)?) {
            length += 1;
        }
        if length == 0 {
            return Err(Invalid);
        }
        let value = self.prefix(length);
        self.forward(length)?;
        if !among(self.ch(), "\0 \r\n\u{85}\u{2028}\u{2029}") {
            return Err(Invalid);
        }
        Ok(value)
    }
    fn scan_yaml_directive_value(&mut self) -> Result<(u64, u64)> {
        while self.ch() == ' ' {
            self.forward(1)?;
        }
        let major = self.scan_yaml_directive_number()?;
        if self.ch() != '.' {
            return Err(Invalid);
        }
        self.forward(1)?;
        let minor = self.scan_yaml_directive_number()?;
        if !among(self.ch(), "\0 \r\n\u{85}\u{2028}\u{2029}") {
            return Err(Invalid);
        }
        Ok((major, minor))
    }
    fn scan_yaml_directive_number(&mut self) -> Result<u64> {
        if !self.ch().is_ascii_digit() {
            return Err(Invalid);
        }
        let mut length = 0;
        while self.peek(length)?.is_ascii_digit() {
            length += 1;
        }
        // int() of any length; only `== 1` matters later.
        let digits = self.prefix(length);
        let value = digits.trim_start_matches('0').parse::<u64>().unwrap_or(
            if digits.trim_start_matches('0').is_empty() {
                0
            } else {
                u64::MAX
            },
        );
        self.forward(length)?;
        Ok(value)
    }
    fn scan_tag_directive_value(&mut self) -> Result<(String, String)> {
        while self.ch() == ' ' {
            self.forward(1)?;
        }
        let handle = self.scan_tag_handle()?;
        if self.ch() != ' ' {
            return Err(Invalid);
        }
        while self.ch() == ' ' {
            self.forward(1)?;
        }
        let prefix = self.scan_tag_uri()?;
        if !among(self.ch(), "\0 \r\n\u{85}\u{2028}\u{2029}") {
            return Err(Invalid);
        }
        Ok((handle, prefix))
    }
    fn scan_directive_ignored_line(&mut self) -> Result<()> {
        while self.ch() == ' ' {
            self.forward(1)?;
        }
        if self.ch() == '#' {
            while !among(self.ch(), "\0\r\n\u{85}\u{2028}\u{2029}") {
                self.forward(1)?;
            }
        }
        if !among(self.ch(), "\0\r\n\u{85}\u{2028}\u{2029}") {
            return Err(Invalid);
        }
        self.scan_line_break()?;
        Ok(())
    }
    fn scan_anchor(&mut self, alias: bool) -> Result<Token> {
        let start = self.mark();
        self.forward(1)?;
        let mut length = 0;
        while ascii_word(self.peek(length)?) {
            length += 1;
        }
        if length == 0 {
            return Err(Invalid);
        }
        let value = self.prefix(length);
        self.forward(length)?;
        if !among(self.ch(), "\0 \t\r\n\u{85}\u{2028}\u{2029}?:,]}%@`") {
            return Err(Invalid);
        }
        let end = self.mark();
        Ok(Token {
            kind: if alias {
                Kind::Alias(value)
            } else {
                Kind::Anchor(value)
            },
            start,
            end,
        })
    }
    fn scan_tag(&mut self) -> Result<Token> {
        let start = self.mark();
        let ch = self.peek(1)?;
        let (handle, suffix);
        if ch == '<' {
            handle = None;
            self.forward(2)?;
            suffix = self.scan_tag_uri()?;
            if self.ch() != '>' {
                return Err(Invalid);
            }
            self.forward(1)?;
        } else if among(ch, BREAKZ) {
            handle = None;
            suffix = "!".to_owned();
            self.forward(1)?;
        } else {
            let mut length = 1;
            let mut use_handle = false;
            let mut ch = ch;
            while !among(ch, "\0 \r\n\u{85}\u{2028}\u{2029}") {
                if ch == '!' {
                    use_handle = true;
                    break;
                }
                length += 1;
                ch = self.peek(length)?;
            }
            if use_handle {
                handle = Some(self.scan_tag_handle()?);
            } else {
                handle = Some("!".to_owned());
                self.forward(1)?;
            }
            suffix = self.scan_tag_uri()?;
        }
        if !among(self.ch(), "\0 \r\n\u{85}\u{2028}\u{2029}") {
            return Err(Invalid);
        }
        let end = self.mark();
        Ok(Token {
            kind: Kind::Tag(handle, suffix),
            start,
            end,
        })
    }
    fn scan_block_scalar(&mut self, folded: bool) -> Result<Token> {
        let mut chunks = String::new();
        let start = self.mark();
        self.forward(1)?;
        let (chomping, increment) = self.scan_block_scalar_indicators()?;
        self.scan_block_scalar_ignored_line()?;
        let min_indent = (self.indent + 1).max(1) as usize;
        let (mut breaks, indent, mut end);
        match increment {
            None => {
                let (b, max_indent, e) = self.scan_block_scalar_indentation()?;
                breaks = b;
                end = e;
                indent = min_indent.max(max_indent);
            }
            Some(increment) => {
                indent = min_indent + increment - 1;
                let (b, e) = self.scan_block_scalar_breaks(indent)?;
                breaks = b;
                end = e;
            }
        }
        let mut line_break = String::new();
        while self.column == indent && self.ch() != '\0' {
            chunks.extend(breaks.drain(..));
            let leading_non_space = !among(self.ch(), " \t");
            let mut length = 0;
            while !among(self.peek(length)?, "\0\r\n\u{85}\u{2028}\u{2029}") {
                length += 1;
            }
            chunks.push_str(&self.prefix(length));
            self.forward(length)?;
            line_break = self.scan_line_break()?;
            let (b, e) = self.scan_block_scalar_breaks(indent)?;
            breaks = b;
            end = e;
            if self.column == indent && self.ch() != '\0' {
                if folded && line_break == "\n" && leading_non_space && !among(self.ch(), " \t") {
                    if breaks.is_empty() {
                        chunks.push(' ');
                    }
                } else {
                    chunks.push_str(&line_break);
                }
            } else {
                break;
            }
        }
        if chomping != Some(false) {
            chunks.push_str(&line_break);
        }
        if chomping == Some(true) {
            chunks.extend(breaks.drain(..));
        }
        Ok(Token {
            kind: Kind::Scalar(chunks, false),
            start,
            end,
        })
    }
    fn scan_block_scalar_indicators(&mut self) -> Result<(Option<bool>, Option<usize>)> {
        let (mut chomping, mut increment) = (None, None);
        let ch = self.ch();
        if among(ch, "+-") {
            chomping = Some(ch == '+');
            self.forward(1)?;
            let ch = self.ch();
            if ch.is_ascii_digit() {
                increment = Some(ch as usize - '0' as usize);
                if increment == Some(0) {
                    return Err(Invalid);
                }
                self.forward(1)?;
            }
        } else if ch.is_ascii_digit() {
            increment = Some(ch as usize - '0' as usize);
            if increment == Some(0) {
                return Err(Invalid);
            }
            self.forward(1)?;
            let ch = self.ch();
            if among(ch, "+-") {
                chomping = Some(ch == '+');
                self.forward(1)?;
            }
        }
        if !among(self.ch(), "\0 \r\n\u{85}\u{2028}\u{2029}") {
            return Err(Invalid);
        }
        Ok((chomping, increment))
    }
    fn scan_block_scalar_ignored_line(&mut self) -> Result<()> {
        self.scan_directive_ignored_line()
    }
    fn scan_block_scalar_indentation(&mut self) -> Result<(Vec<String>, usize, Mark)> {
        let mut chunks = Vec::new();
        let mut max_indent = 0;
        let mut end = self.mark();
        while among(self.ch(), " \r\n\u{85}\u{2028}\u{2029}") {
            if self.ch() != ' ' {
                chunks.push(self.scan_line_break()?);
                end = self.mark();
            } else {
                self.forward(1)?;
                max_indent = max_indent.max(self.column);
            }
        }
        Ok((chunks, max_indent, end))
    }
    fn scan_block_scalar_breaks(&mut self, indent: usize) -> Result<(Vec<String>, Mark)> {
        let mut chunks = Vec::new();
        let mut end = self.mark();
        while self.column < indent && self.ch() == ' ' {
            self.forward(1)?;
        }
        while among(self.ch(), LINE_BREAKS) {
            chunks.push(self.scan_line_break()?);
            end = self.mark();
            while self.column < indent && self.ch() == ' ' {
                self.forward(1)?;
            }
        }
        Ok((chunks, end))
    }
    fn scan_flow_scalar(&mut self, double: bool) -> Result<Token> {
        let mut chunks = String::new();
        let start = self.mark();
        let quote = self.ch();
        self.forward(1)?;
        self.scan_flow_scalar_non_spaces(double, &mut chunks)?;
        while self.ch() != quote {
            self.scan_flow_scalar_spaces(&mut chunks)?;
            self.scan_flow_scalar_non_spaces(double, &mut chunks)?;
        }
        self.forward(1)?;
        let end = self.mark();
        Ok(Token {
            kind: Kind::Scalar(chunks, false),
            start,
            end,
        })
    }
    fn scan_flow_scalar_non_spaces(&mut self, double: bool, chunks: &mut String) -> Result<()> {
        loop {
            let mut length = 0;
            while !among(self.peek(length)?, "'\"\\\0 \t\r\n\u{85}\u{2028}\u{2029}") {
                length += 1;
            }
            if length > 0 {
                chunks.push_str(&self.prefix(length));
                self.forward(length)?;
            }
            let ch = self.ch();
            if !double && ch == '\'' && self.peek(1)? == '\'' {
                chunks.push('\'');
                self.forward(2)?;
            } else if (double && ch == '\'') || (!double && among(ch, "\"\\")) {
                chunks.push(ch);
                self.forward(1)?;
            } else if double && ch == '\\' {
                self.forward(1)?;
                let ch = self.ch();
                let replacement = match ch {
                    '0' => Some('\0'),
                    'a' => Some('\u{7}'),
                    'b' => Some('\u{8}'),
                    't' | '\t' => Some('\t'),
                    'n' => Some('\n'),
                    'v' => Some('\u{b}'),
                    'f' => Some('\u{c}'),
                    'r' => Some('\r'),
                    'e' => Some('\u{1b}'),
                    ' ' => Some(' '),
                    '"' => Some('"'),
                    '\\' => Some('\\'),
                    '/' => Some('/'),
                    'N' => Some('\u{85}'),
                    '_' => Some('\u{a0}'),
                    'L' => Some('\u{2028}'),
                    'P' => Some('\u{2029}'),
                    _ => None,
                };
                if let Some(replacement) = replacement {
                    chunks.push(replacement);
                    self.forward(1)?;
                } else if let Some(length) = match ch {
                    'x' => Some(2),
                    'u' => Some(4),
                    'U' => Some(8),
                    _ => None,
                } {
                    self.forward(1)?;
                    for k in 0..length {
                        if !self.peek(k)?.is_ascii_hexdigit() {
                            return Err(Invalid);
                        }
                    }
                    let code =
                        u32::from_str_radix(&self.prefix(length), 16).map_err(|_| Invalid)?;
                    // chr() refuses more than U+10FFFF; a surrogate, which Python keeps, becomes U+FFFD.
                    if code > 0x10ffff {
                        return Err(Invalid);
                    }
                    chunks.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                    self.forward(length)?;
                } else if among(ch, LINE_BREAKS) {
                    self.scan_line_break()?;
                    self.scan_flow_scalar_breaks(chunks)?;
                } else {
                    return Err(Invalid);
                }
            } else {
                return Ok(());
            }
        }
    }
    fn scan_flow_scalar_spaces(&mut self, chunks: &mut String) -> Result<()> {
        let mut length = 0;
        while among(self.peek(length)?, " \t") {
            length += 1;
        }
        let whitespaces = self.prefix(length);
        self.forward(length)?;
        let ch = self.ch();
        if ch == '\0' {
            return Err(Invalid);
        } else if among(ch, LINE_BREAKS) {
            let line_break = self.scan_line_break()?;
            let mut breaks = String::new();
            let count = self.scan_flow_scalar_breaks(&mut breaks)?;
            if line_break != "\n" {
                chunks.push_str(&line_break);
            } else if count == 0 {
                chunks.push(' ');
            }
            chunks.push_str(&breaks);
        } else {
            chunks.push_str(&whitespaces);
        }
        Ok(())
    }
    /// The line breaks it added.
    fn scan_flow_scalar_breaks(&mut self, chunks: &mut String) -> Result<usize> {
        let mut count = 0;
        loop {
            let prefix = self.prefix(3);
            if (prefix == "---" || prefix == "...") && among(self.peek(3)?, BREAKZ) {
                return Err(Invalid);
            }
            while among(self.ch(), " \t") {
                self.forward(1)?;
            }
            if among(self.ch(), LINE_BREAKS) {
                chunks.push_str(&self.scan_line_break()?);
                count += 1;
            } else {
                return Ok(count);
            }
        }
    }
    fn scan_plain(&mut self) -> Result<Token> {
        let mut chunks = String::new();
        let start = self.mark();
        let mut end = start;
        let indent = self.indent + 1;
        let mut spaces: Option<String> = Some(String::new());
        loop {
            let mut length = 0;
            if self.ch() == '#' {
                break;
            }
            loop {
                let ch = self.peek(length)?;
                if among(ch, BREAKZ)
                    || (ch == ':'
                        && (among(self.peek(length + 1)?, BREAKZ)
                            || (self.flow_level > 0 && among(self.peek(length + 1)?, ",[]{}"))))
                    || (self.flow_level > 0 && among(ch, ",?[]{}"))
                {
                    break;
                }
                length += 1;
            }
            if length == 0 {
                break;
            }
            self.allow_simple_key = false;
            chunks.push_str(spaces.as_deref().unwrap_or_default());
            chunks.push_str(&self.prefix(length));
            self.forward(length)?;
            end = self.mark();
            spaces = self.scan_plain_spaces()?;
            if spaces.as_deref().is_none_or(str::is_empty)
                || self.ch() == '#'
                || (self.flow_level == 0 && (self.column as i64) < indent)
            {
                break;
            }
        }
        Ok(Token {
            kind: Kind::Scalar(chunks, true),
            start,
            end,
        })
    }
    /// `None` where Python returned `None` (a document separator), else the folded white space.
    fn scan_plain_spaces(&mut self) -> Result<Option<String>> {
        let mut chunks = String::new();
        let mut length = 0;
        while self.peek(length)? == ' ' {
            length += 1;
        }
        let whitespaces = self.prefix(length);
        self.forward(length)?;
        let ch = self.ch();
        if among(ch, LINE_BREAKS) {
            let line_break = self.scan_line_break()?;
            self.allow_simple_key = true;
            let separator = |s: &Self| -> Result<bool> {
                let prefix = s.prefix(3);
                Ok((prefix == "---" || prefix == "...") && among(s.peek(3)?, BREAKZ))
            };
            if separator(self)? {
                return Ok(None);
            }
            let mut breaks = String::new();
            let mut count = 0;
            while among(self.ch(), " \r\n\u{85}\u{2028}\u{2029}") {
                if self.ch() == ' ' {
                    self.forward(1)?;
                } else {
                    breaks.push_str(&self.scan_line_break()?);
                    count += 1;
                    if separator(self)? {
                        return Ok(None);
                    }
                }
            }
            if line_break != "\n" {
                chunks.push_str(&line_break);
            } else if count == 0 {
                chunks.push(' ');
            }
            chunks.push_str(&breaks);
        } else if !whitespaces.is_empty() {
            chunks.push_str(&whitespaces);
        }
        Ok(Some(chunks))
    }
    fn scan_tag_handle(&mut self) -> Result<String> {
        if self.ch() != '!' {
            return Err(Invalid);
        }
        let mut length = 1;
        let mut ch = self.peek(length)?;
        if ch != ' ' {
            while ascii_word(ch) {
                length += 1;
                ch = self.peek(length)?;
            }
            if ch != '!' {
                return Err(Invalid);
            }
            length += 1;
        }
        let value = self.prefix(length);
        self.forward(length)?;
        Ok(value)
    }
    fn scan_tag_uri(&mut self) -> Result<String> {
        let mut chunks = String::new();
        let mut length = 0;
        let mut ch = self.peek(length)?;
        while ch.is_ascii_alphanumeric() || among(ch, "-;/?:@&=+$,_.!~*'()[]%") {
            if ch == '%' {
                chunks.push_str(&self.prefix(length));
                self.forward(length)?;
                length = 0;
                chunks.push_str(&self.scan_uri_escapes()?);
            } else {
                length += 1;
            }
            ch = self.peek(length)?;
        }
        if length > 0 {
            chunks.push_str(&self.prefix(length));
            self.forward(length)?;
        }
        if chunks.is_empty() {
            return Err(Invalid);
        }
        Ok(chunks)
    }
    fn scan_uri_escapes(&mut self) -> Result<String> {
        let mut codes = Vec::new();
        while self.ch() == '%' {
            self.forward(1)?;
            for k in 0..2 {
                if !self.peek(k)?.is_ascii_hexdigit() {
                    return Err(Invalid);
                }
            }
            codes.push(u8::from_str_radix(&self.prefix(2), 16).map_err(|_| Invalid)?);
            self.forward(2)?;
        }
        String::from_utf8(codes).map_err(|_| Invalid)
    }
    fn scan_line_break(&mut self) -> Result<String> {
        let ch = self.ch();
        if among(ch, "\r\n\u{85}") {
            if self.prefix(2) == "\r\n" {
                self.forward(2)?;
            } else {
                self.forward(1)?;
            }
            return Ok("\n".into());
        }
        if among(ch, "\u{2028}\u{2029}") {
            self.forward(1)?;
            return Ok(ch.to_string());
        }
        Ok(String::new())
    }
}

// ------------------------------------------------------------------ parser

#[derive(Clone, Debug)]
enum Event {
    StreamStart,
    StreamEnd,
    DocumentStart,
    DocumentEnd,
    Alias(String),
    Scalar {
        anchor: Option<String>,
        tag: Option<String>,
        plain_implicit: bool,
        value: String,
        start: Mark,
        end: Mark,
    },
    SequenceStart {
        anchor: Option<String>,
        tag: Option<String>,
        start: Mark,
        flow: bool,
    },
    SequenceEnd(Mark),
    MappingStart {
        anchor: Option<String>,
        tag: Option<String>,
        start: Mark,
        flow: bool,
    },
    MappingEnd(Mark),
}

#[derive(Clone, Copy)]
enum State {
    ImplicitDocumentStart,
    DocumentStart,
    DocumentEnd,
    DocumentContent,
    BlockNode,
    BlockSequenceFirstEntry,
    BlockSequenceEntry,
    IndentlessSequenceEntry,
    BlockMappingFirstKey,
    BlockMappingKey,
    BlockMappingValue,
    FlowSequenceFirstEntry,
    FlowSequenceEntry,
    FlowSequenceEntryMappingKey,
    FlowSequenceEntryMappingValue,
    FlowSequenceEntryMappingEnd,
    FlowMappingFirstKey,
    FlowMappingKey,
    FlowMappingValue,
    FlowMappingEmptyValue,
}

macro_rules! is {
    ($($pattern:pat_param)|+) => {
        |kind: &Kind| matches!(kind, $($pattern)|+)
    };
}

struct Parser {
    scanner: Scanner,
    current: Option<Event>,
    tag_handles: HashMap<String, String>,
    states: Vec<State>,
    state: Option<State>,
    started: bool,
}

impl Parser {
    fn new(text: &str) -> Self {
        Parser {
            scanner: Scanner::new(text),
            current: None,
            tag_handles: HashMap::new(),
            states: Vec::new(),
            state: None,
            started: false,
        }
    }
    fn next(&mut self) -> Result<Option<Event>> {
        if !self.started {
            self.started = true;
            self.scanner.get_token()?;
            self.state = Some(State::ImplicitDocumentStart);
            return Ok(Some(Event::StreamStart));
        }
        match self.state {
            Some(state) => self.run(state).map(Some),
            None => Ok(None),
        }
    }
    fn peek_event(&mut self) -> Result<&Event> {
        if self.current.is_none() {
            self.current = self.next()?;
        }
        self.current.as_ref().ok_or(Invalid)
    }
    fn get_event(&mut self) -> Result<Event> {
        if self.current.is_none() {
            self.current = self.next()?;
        }
        self.current.take().ok_or(Invalid)
    }
    fn pop_state(&mut self) -> Result<()> {
        self.state = Some(self.states.pop().ok_or(Invalid)?);
        Ok(())
    }
    fn token_start(&mut self) -> Result<Mark> {
        Ok(self.scanner.peek_token()?.ok_or(Invalid)?.start)
    }
    fn take(&mut self) -> Result<Token> {
        self.scanner.get_token()?.ok_or(Invalid)
    }
    fn empty_scalar(mark: Mark) -> Event {
        Event::Scalar {
            anchor: None,
            tag: None,
            plain_implicit: true,
            value: String::new(),
            start: mark,
            end: mark,
        }
    }

    fn run(&mut self, state: State) -> Result<Event> {
        use State::*;
        match state {
            ImplicitDocumentStart => {
                if !self.scanner.check_token(&[is!(Kind::Directive(..)
                    | Kind::DocumentStart
                    | Kind::StreamEnd)])?
                {
                    self.tag_handles = default_tags();
                    self.states.push(DocumentEnd);
                    self.state = Some(BlockNode);
                    Ok(Event::DocumentStart)
                } else {
                    self.run(DocumentStart)
                }
            }
            DocumentStart => {
                while self.scanner.check_token(&[is!(Kind::DocumentEnd)])? {
                    self.take()?;
                }
                if !self.scanner.check_token(&[is!(Kind::StreamEnd)])? {
                    self.process_directives()?;
                    if !self.scanner.check_token(&[is!(Kind::DocumentStart)])? {
                        return Err(Invalid);
                    }
                    self.take()?;
                    self.states.push(DocumentEnd);
                    self.state = Some(DocumentContent);
                    Ok(Event::DocumentStart)
                } else {
                    self.take()?;
                    self.state = None;
                    Ok(Event::StreamEnd)
                }
            }
            DocumentEnd => {
                if self.scanner.check_token(&[is!(Kind::DocumentEnd)])? {
                    self.take()?;
                }
                self.state = Some(DocumentStart);
                Ok(Event::DocumentEnd)
            }
            DocumentContent => {
                if self.scanner.check_token(&[is!(Kind::Directive(..)
                    | Kind::DocumentStart
                    | Kind::DocumentEnd
                    | Kind::StreamEnd)])?
                {
                    let mark = self.token_start()?;
                    self.pop_state()?;
                    Ok(Self::empty_scalar(mark))
                } else {
                    self.parse_node(true, false)
                }
            }
            BlockNode => self.parse_node(true, false),
            BlockSequenceFirstEntry => {
                self.take()?;
                self.run(BlockSequenceEntry)
            }
            BlockSequenceEntry => {
                if self.scanner.check_token(&[is!(Kind::BlockEntry)])? {
                    let token = self.take()?;
                    if !self
                        .scanner
                        .check_token(&[is!(Kind::BlockEntry | Kind::BlockEnd)])?
                    {
                        self.states.push(BlockSequenceEntry);
                        return self.parse_node(true, false);
                    }
                    self.state = Some(BlockSequenceEntry);
                    return Ok(Self::empty_scalar(token.end));
                }
                if !self.scanner.check_token(&[is!(Kind::BlockEnd)])? {
                    return Err(Invalid);
                }
                let token = self.take()?;
                self.pop_state()?;
                Ok(Event::SequenceEnd(token.end))
            }
            IndentlessSequenceEntry => {
                if self.scanner.check_token(&[is!(Kind::BlockEntry)])? {
                    let token = self.take()?;
                    if !self.scanner.check_token(&[is!(Kind::BlockEntry
                        | Kind::Key
                        | Kind::Value
                        | Kind::BlockEnd)])?
                    {
                        self.states.push(IndentlessSequenceEntry);
                        return self.parse_node(true, false);
                    }
                    self.state = Some(IndentlessSequenceEntry);
                    return Ok(Self::empty_scalar(token.end));
                }
                let mark = self.token_start()?;
                self.pop_state()?;
                Ok(Event::SequenceEnd(mark))
            }
            BlockMappingFirstKey => {
                self.take()?;
                self.run(BlockMappingKey)
            }
            BlockMappingKey => {
                if self.scanner.check_token(&[is!(Kind::Key)])? {
                    let token = self.take()?;
                    if !self
                        .scanner
                        .check_token(&[is!(Kind::Key | Kind::Value | Kind::BlockEnd)])?
                    {
                        self.states.push(BlockMappingValue);
                        return self.parse_node(true, true);
                    }
                    self.state = Some(BlockMappingValue);
                    return Ok(Self::empty_scalar(token.end));
                }
                if !self.scanner.check_token(&[is!(Kind::BlockEnd)])? {
                    return Err(Invalid);
                }
                let token = self.take()?;
                self.pop_state()?;
                Ok(Event::MappingEnd(token.end))
            }
            BlockMappingValue => {
                if self.scanner.check_token(&[is!(Kind::Value)])? {
                    let token = self.take()?;
                    if !self
                        .scanner
                        .check_token(&[is!(Kind::Key | Kind::Value | Kind::BlockEnd)])?
                    {
                        self.states.push(BlockMappingKey);
                        return self.parse_node(true, true);
                    }
                    self.state = Some(BlockMappingKey);
                    return Ok(Self::empty_scalar(token.end));
                }
                self.state = Some(BlockMappingKey);
                let mark = self.token_start()?;
                Ok(Self::empty_scalar(mark))
            }
            FlowSequenceFirstEntry => {
                self.take()?;
                self.flow_sequence_entry(true)
            }
            FlowSequenceEntry => self.flow_sequence_entry(false),
            FlowSequenceEntryMappingKey => {
                let token = self.take()?;
                if !self
                    .scanner
                    .check_token(&[is!(Kind::Value | Kind::FlowEntry | Kind::FlowSequenceEnd)])?
                {
                    self.states.push(FlowSequenceEntryMappingValue);
                    return self.parse_node(false, false);
                }
                self.state = Some(FlowSequenceEntryMappingValue);
                Ok(Self::empty_scalar(token.end))
            }
            FlowSequenceEntryMappingValue => {
                if self.scanner.check_token(&[is!(Kind::Value)])? {
                    let token = self.take()?;
                    if !self
                        .scanner
                        .check_token(&[is!(Kind::FlowEntry | Kind::FlowSequenceEnd)])?
                    {
                        self.states.push(FlowSequenceEntryMappingEnd);
                        return self.parse_node(false, false);
                    }
                    self.state = Some(FlowSequenceEntryMappingEnd);
                    return Ok(Self::empty_scalar(token.end));
                }
                self.state = Some(FlowSequenceEntryMappingEnd);
                let mark = self.token_start()?;
                Ok(Self::empty_scalar(mark))
            }
            FlowSequenceEntryMappingEnd => {
                self.state = Some(FlowSequenceEntry);
                let mark = self.token_start()?;
                Ok(Event::MappingEnd(mark))
            }
            FlowMappingFirstKey => {
                self.take()?;
                self.flow_mapping_key(true)
            }
            FlowMappingKey => self.flow_mapping_key(false),
            FlowMappingValue => {
                if self.scanner.check_token(&[is!(Kind::Value)])? {
                    let token = self.take()?;
                    if !self
                        .scanner
                        .check_token(&[is!(Kind::FlowEntry | Kind::FlowMappingEnd)])?
                    {
                        self.states.push(FlowMappingKey);
                        return self.parse_node(false, false);
                    }
                    self.state = Some(FlowMappingKey);
                    return Ok(Self::empty_scalar(token.end));
                }
                self.state = Some(FlowMappingKey);
                let mark = self.token_start()?;
                Ok(Self::empty_scalar(mark))
            }
            FlowMappingEmptyValue => {
                self.state = Some(FlowMappingKey);
                let mark = self.token_start()?;
                Ok(Self::empty_scalar(mark))
            }
        }
    }

    fn process_directives(&mut self) -> Result<()> {
        let mut version = None;
        self.tag_handles = HashMap::new();
        while self.scanner.check_token(&[is!(Kind::Directive(..))])? {
            let Kind::Directive(name, value, tag) = self.take()?.kind else {
                return Err(Invalid);
            };
            if name == "YAML" {
                if version.is_some() {
                    return Err(Invalid);
                }
                let (major, _) = value.ok_or(Invalid)?;
                if major != 1 {
                    return Err(Invalid);
                }
                version = value;
            } else if name == "TAG" {
                let (handle, prefix) = tag.ok_or(Invalid)?;
                if self.tag_handles.contains_key(&handle) {
                    return Err(Invalid);
                }
                self.tag_handles.insert(handle, prefix);
            }
        }
        for (key, value) in default_tags() {
            self.tag_handles.entry(key).or_insert(value);
        }
        Ok(())
    }

    fn flow_sequence_entry(&mut self, first: bool) -> Result<Event> {
        if !self.scanner.check_token(&[is!(Kind::FlowSequenceEnd)])? {
            if !first {
                if self.scanner.check_token(&[is!(Kind::FlowEntry)])? {
                    self.take()?;
                } else {
                    return Err(Invalid);
                }
            }
            if self.scanner.check_token(&[is!(Kind::Key)])? {
                let start = self.token_start()?;
                self.state = Some(State::FlowSequenceEntryMappingKey);
                return Ok(Event::MappingStart {
                    anchor: None,
                    tag: None,
                    start,
                    flow: true,
                });
            } else if !self.scanner.check_token(&[is!(Kind::FlowSequenceEnd)])? {
                self.states.push(State::FlowSequenceEntry);
                return self.parse_node(false, false);
            }
        }
        let token = self.take()?;
        self.pop_state()?;
        Ok(Event::SequenceEnd(token.end))
    }

    fn flow_mapping_key(&mut self, first: bool) -> Result<Event> {
        if !self.scanner.check_token(&[is!(Kind::FlowMappingEnd)])? {
            if !first {
                if self.scanner.check_token(&[is!(Kind::FlowEntry)])? {
                    self.take()?;
                } else {
                    return Err(Invalid);
                }
            }
            if self.scanner.check_token(&[is!(Kind::Key)])? {
                let token = self.take()?;
                if !self
                    .scanner
                    .check_token(&[is!(Kind::Value | Kind::FlowEntry | Kind::FlowMappingEnd)])?
                {
                    self.states.push(State::FlowMappingValue);
                    return self.parse_node(false, false);
                }
                self.state = Some(State::FlowMappingValue);
                return Ok(Self::empty_scalar(token.end));
            } else if !self.scanner.check_token(&[is!(Kind::FlowMappingEnd)])? {
                self.states.push(State::FlowMappingEmptyValue);
                return self.parse_node(false, false);
            }
        }
        let token = self.take()?;
        self.pop_state()?;
        Ok(Event::MappingEnd(token.end))
    }

    fn parse_node(&mut self, block: bool, indentless_sequence: bool) -> Result<Event> {
        if self.scanner.check_token(&[is!(Kind::Alias(_))])? {
            let token = self.take()?;
            let Kind::Alias(name) = token.kind else {
                return Err(Invalid);
            };
            self.pop_state()?;
            return Ok(Event::Alias(name));
        }
        let (mut anchor, mut tag, mut start, mut end) = (None, None, None, None);
        if self.scanner.check_token(&[is!(Kind::Anchor(_))])? {
            let token = self.take()?;
            (start, end) = (Some(token.start), Some(token.end));
            if let Kind::Anchor(name) = token.kind {
                anchor = Some(name);
            }
            if self.scanner.check_token(&[is!(Kind::Tag(..))])? {
                let token = self.take()?;
                end = Some(token.end);
                if let Kind::Tag(handle, suffix) = token.kind {
                    tag = Some((handle, suffix));
                }
            }
        } else if self.scanner.check_token(&[is!(Kind::Tag(..))])? {
            let token = self.take()?;
            (start, end) = (Some(token.start), Some(token.end));
            if let Kind::Tag(handle, suffix) = token.kind {
                tag = Some((handle, suffix));
            }
            if self.scanner.check_token(&[is!(Kind::Anchor(_))])? {
                let token = self.take()?;
                end = Some(token.end);
                if let Kind::Anchor(name) = token.kind {
                    anchor = Some(name);
                }
            }
        }
        let tag = match tag {
            Some((Some(handle), suffix)) => Some(format!(
                "{}{suffix}",
                self.tag_handles.get(&handle).ok_or(Invalid)?
            )),
            Some((None, suffix)) => Some(suffix),
            None => None,
        };
        let (start, end) = match (start, end) {
            (Some(start), Some(end)) => (start, end),
            _ => {
                let mark = self.token_start()?;
                (mark, mark)
            }
        };
        if indentless_sequence && self.scanner.check_token(&[is!(Kind::BlockEntry)])? {
            self.state = Some(State::IndentlessSequenceEntry);
            return Ok(Event::SequenceStart {
                anchor,
                tag,
                start,
                flow: false,
            });
        }
        if self.scanner.check_token(&[is!(Kind::Scalar(..))])? {
            let token = self.take()?;
            let Kind::Scalar(value, plain) = token.kind else {
                return Err(Invalid);
            };
            let plain_implicit = (plain && tag.is_none()) || tag.as_deref() == Some("!");
            self.pop_state()?;
            return Ok(Event::Scalar {
                anchor,
                tag,
                plain_implicit,
                value,
                start,
                end: token.end,
            });
        }
        if self.scanner.check_token(&[is!(Kind::FlowSequenceStart)])? {
            self.state = Some(State::FlowSequenceFirstEntry);
            return Ok(Event::SequenceStart {
                anchor,
                tag,
                start,
                flow: true,
            });
        }
        if self.scanner.check_token(&[is!(Kind::FlowMappingStart)])? {
            self.state = Some(State::FlowMappingFirstKey);
            return Ok(Event::MappingStart {
                anchor,
                tag,
                start,
                flow: true,
            });
        }
        if block && self.scanner.check_token(&[is!(Kind::BlockSequenceStart)])? {
            self.state = Some(State::BlockSequenceFirstEntry);
            return Ok(Event::SequenceStart {
                anchor,
                tag,
                start,
                flow: false,
            });
        }
        if block && self.scanner.check_token(&[is!(Kind::BlockMappingStart)])? {
            self.state = Some(State::BlockMappingFirstKey);
            return Ok(Event::MappingStart {
                anchor,
                tag,
                start,
                flow: false,
            });
        }
        if anchor.is_some() || tag.is_some() {
            // An empty scalar with properties; it ends where they end.
            let plain_implicit = tag.is_none() || tag.as_deref() == Some("!");
            self.pop_state()?;
            return Ok(Event::Scalar {
                anchor,
                tag,
                plain_implicit,
                value: String::new(),
                start,
                end,
            });
        }
        Err(Invalid)
    }
}

fn default_tags() -> HashMap<String, String> {
    HashMap::from([
        ("!".to_owned(), "!".to_owned()),
        ("!!".to_owned(), "tag:yaml.org,2002:".to_owned()),
    ])
}

// ------------------------------------------------------------------ composer and resolver

struct Composer {
    nodes: Vec<Node>,
    anchors: HashMap<String, usize>,
}

impl Composer {
    fn document(&mut self, parser: &mut Parser) -> Result<usize> {
        parser.get_event()?;
        let node = self.node(parser, 0)?;
        parser.get_event()?;
        self.anchors.clear();
        Ok(node)
    }
    fn node(&mut self, parser: &mut Parser, depth: usize) -> Result<usize> {
        if depth > DEPTH {
            return Err(Invalid);
        }
        if let Event::Alias(..) = parser.peek_event()? {
            let Event::Alias(name) = parser.get_event()? else {
                return Err(Invalid);
            };
            return self.anchors.get(&name).copied().ok_or(Invalid);
        }
        let anchor = match parser.peek_event()? {
            Event::Scalar { anchor, .. }
            | Event::SequenceStart { anchor, .. }
            | Event::MappingStart { anchor, .. } => anchor.clone(),
            _ => return Err(Invalid),
        };
        if anchor
            .as_ref()
            .is_some_and(|a| self.anchors.contains_key(a))
        {
            return Err(Invalid);
        }
        let id = match parser.get_event()? {
            Event::Scalar {
                tag,
                plain_implicit,
                value,
                start,
                end,
                ..
            } => {
                let tag = match tag.as_deref() {
                    None | Some("!") => resolve(&value, plain_implicit),
                    Some(tag) => tag.to_owned(),
                };
                self.nodes.push(Node {
                    tag,
                    value: Value::Scalar(value),
                    start,
                    end,
                    flow: false,
                });
                let id = self.nodes.len() - 1;
                if let Some(anchor) = anchor {
                    self.anchors.insert(anchor, id);
                }
                id
            }
            Event::SequenceStart {
                tag, start, flow, ..
            } => {
                let tag = tag
                    .filter(|t| t != "!")
                    .unwrap_or_else(|| "tag:yaml.org,2002:seq".into());
                self.nodes.push(Node {
                    tag,
                    value: Value::Sequence(Vec::new()),
                    start,
                    end: start,
                    flow,
                });
                let id = self.nodes.len() - 1;
                if let Some(anchor) = anchor {
                    self.anchors.insert(anchor, id);
                }
                while !matches!(parser.peek_event()?, Event::SequenceEnd(_)) {
                    let item = self.node(parser, depth + 1)?;
                    if let Value::Sequence(items) = &mut self.nodes[id].value {
                        items.push(item);
                    }
                }
                if let Event::SequenceEnd(end) = parser.get_event()? {
                    self.nodes[id].end = end;
                }
                id
            }
            Event::MappingStart {
                tag, start, flow, ..
            } => {
                let tag = tag
                    .filter(|t| t != "!")
                    .unwrap_or_else(|| "tag:yaml.org,2002:map".into());
                self.nodes.push(Node {
                    tag,
                    value: Value::Mapping(Vec::new()),
                    start,
                    end: start,
                    flow,
                });
                let id = self.nodes.len() - 1;
                if let Some(anchor) = anchor {
                    self.anchors.insert(anchor, id);
                }
                while !matches!(parser.peek_event()?, Event::MappingEnd(_)) {
                    let key = self.node(parser, depth + 1)?;
                    let value = self.node(parser, depth + 1)?;
                    if let Value::Mapping(pairs) = &mut self.nodes[id].value {
                        pairs.push((key, value));
                    }
                }
                if let Event::MappingEnd(end) = parser.get_event()? {
                    self.nodes[id].end = end;
                }
                id
            }
            _ => return Err(Invalid),
        };
        Ok(id)
    }
}

/// `Resolver.resolve(ScalarNode, value, implicit)`: YAML 1.1's implicit tags for a plain scalar
/// (or one tagged `!`), tried by the first character in the order PyYAML registered them.
fn resolve(value: &str, plain_implicit: bool) -> String {
    use regex::Regex;
    use std::sync::LazyLock;
    static RESOLVERS: LazyLock<Vec<(&'static str, Regex, &'static str)>> = LazyLock::new(|| {
        // `$` of Python's `re.match` also matches before a final line break.
        let rule = |tag, pattern: &str, first| {
            (
                tag,
                Regex::new(&format!(r"\A(?:{pattern})\n?\z")).expect("resolver"),
                first,
            )
        };
        vec![
            rule(
                "bool",
                "yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF",
                "yYnNtTfFoO",
            ),
            rule(
                "float",
                r"[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)",
                "-+0123456789.",
            ),
            rule(
                "int",
                r"[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+",
                "-+0123456789",
            ),
            rule("merge", "<<", "<"),
            rule("null", "~|null|Null|NULL|", "~nN"),
            rule(
                "timestamp",
                r"[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?",
                "0123456789",
            ),
            rule("value", "=", "="),
            rule("yaml", r"!|&|\*", "!&*"),
        ]
    });
    if plain_implicit {
        let first = value.chars().next();
        for (tag, pattern, starts) in RESOLVERS.iter() {
            let applies = match first {
                None => *tag == "null",
                Some(ch) => starts.contains(ch),
            };
            if applies && pattern.is_match(value) {
                return format!("tag:yaml.org,2002:{tag}");
            }
        }
    }
    "tag:yaml.org,2002:str".into()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tags(text: &str) -> Option<Vec<(String, String)>> {
        let document = compose(text).ok()??;
        let Value::Mapping(pairs) = &document.nodes[document.root].value else {
            return None;
        };
        Some(
            pairs
                .iter()
                .map(|(k, v)| {
                    let key = match &document.nodes[*k].value {
                        Value::Scalar(s) => s.clone(),
                        _ => "?".into(),
                    };
                    (key, document.nodes[*v].tag.clone())
                })
                .collect(),
        )
    }

    #[test]
    fn composes_as_pyyaml() {
        assert_eq!(
            tags(
                "a: 1\nb: yes\nc: 2024-01-05\nd: \"x\"\ne:\nf: ! 12\ng: !!str 1\nh: 1.5\ni: 0o7\n"
            ),
            Some(vec![
                ("a".into(), "tag:yaml.org,2002:int".into()),
                ("b".into(), "tag:yaml.org,2002:bool".into()),
                ("c".into(), "tag:yaml.org,2002:timestamp".into()),
                ("d".into(), "tag:yaml.org,2002:str".into()),
                ("e".into(), "tag:yaml.org,2002:null".into()),
                ("f".into(), "tag:yaml.org,2002:int".into()),
                ("g".into(), "tag:yaml.org,2002:str".into()),
                ("h".into(), "tag:yaml.org,2002:float".into()),
                ("i".into(), "tag:yaml.org,2002:str".into()),
            ])
        );
        // PyYAML keeps quoted scalars at column 0 that YAML 1.2 parsers refuse.
        assert!(tags("title: \"A long\ntitle\"\n").is_some());
        assert_eq!(compose("").map(|d| d.is_none()), Ok(true));
        assert_eq!(compose("# nur\n").map(|d| d.is_none()), Ok(true));
        assert!(compose("a: [1\n").is_err());
        assert!(compose("a: 1\n--- b\n").is_err());
        assert!(compose("a: &x 1\nb: &x 2\n").is_err());
        assert!(compose("a: *nope\n").is_err());
        assert!(compose("a: \u{7}\n").is_err());
    }
}

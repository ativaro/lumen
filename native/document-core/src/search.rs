//! Content search: walks a folder breadth first, reads text, PDF and Office files and reports the
//! passage where all term groups occur. Directories and files are opened relative to their pinned
//! parent, without following links, so a folder swapped during the search cannot lead outside the root.
//! Pictures and pictures inside PDFs are recognised by the caller; this hands them on as `visual` events.
use crate::json::Json;
use std::collections::{HashMap, VecDeque};
use std::fs::File;
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::time::{Duration, Instant};

pub const MAX_TEXT: usize = 1024 * 1024;
const READ_SECONDS: u64 = 12;

/// What the caller asks for. `kinds` maps a lower-case suffix to `text`, `image` or `media`, from the
/// caller's own type table; `encodings` and `aliases` are its suffixes for compression and renaming.
/// `texts` are suffixes read as text by their own name.
pub struct Request {
    pub root: PathBuf,
    pub groups: Vec<Vec<String>>,
    pub hidden: bool,
    pub max_hits: usize,
    pub max_entries: usize,
    pub visual: bool,
    pub ocr: bool,
    pub thumbnails: bool,
    pub kinds: HashMap<String, String>,
    pub texts: Vec<String>,
    pub encodings: Vec<String>,
    pub aliases: HashMap<String, String>,
    pub cache: Option<PathBuf>,
    pub messages: HashMap<String, String>,
}

impl Request {
    pub fn from_json(value: &Json) -> Option<Request> {
        let strings = |key: &str| -> Option<HashMap<String, String>> {
            match value.get(key) {
                Some(Json::Object(entries)) => entries
                    .iter()
                    .map(|(k, v)| Some((k.clone(), v.text()?.to_string())))
                    .collect(),
                None => Some(HashMap::new()),
                _ => None,
            }
        };
        let flag = |key: &str| matches!(value.get(key), Some(Json::Bool(true)));
        let groups = value
            .get("groups")?
            .list()?
            .iter()
            .map(|group| {
                group
                    .list()?
                    .iter()
                    .map(|term| term.text().map(str::to_string))
                    .collect::<Option<Vec<_>>>()
            })
            .collect::<Option<Vec<_>>>()?;
        if !(1..=8).contains(&groups.len()) || groups.iter().any(|g| !(1..=6).contains(&g.len())) {
            return None;
        }
        let count = |key: &str, default: i64| -> Option<usize> {
            usize::try_from(value.get(key).map_or(Some(default), Json::whole)?).ok()
        };
        Some(Request {
            root: value.get("root")?.text()?.into(),
            groups,
            hidden: flag("hidden"),
            max_hits: count("max_hits", 500)?,
            max_entries: count("max_entries", 100_000)?,
            visual: flag("visual"),
            ocr: flag("ocr"),
            thumbnails: flag("thumbnails"),
            kinds: strings("kinds")?,
            texts: value
                .get("texts")
                .and_then(Json::list)
                .unwrap_or(&[])
                .iter()
                .map(|e| e.text().map(str::to_string))
                .collect::<Option<_>>()?,
            encodings: value
                .get("encodings")
                .and_then(Json::list)
                .unwrap_or(&[])
                .iter()
                .map(|e| e.text().map(str::to_string))
                .collect::<Option<_>>()?,
            aliases: strings("aliases")?,
            cache: value.get("cache").and_then(Json::text).map(PathBuf::from),
            messages: strings("messages")?,
        })
    }

    fn say(&self, text: &str) -> String {
        self.messages
            .get(text)
            .cloned()
            .unwrap_or_else(|| text.to_string())
    }

    /// The kind of a name the way the caller's type table sees it: a compression suffix is looked through,
    /// a renaming suffix replaced.
    fn kind(&self, name: &str) -> Option<&'static str> {
        let lower = name.to_lowercase();
        let suffix = |text: &str| {
            text.rfind('.')
                .filter(|at| *at > 0)
                .map(|at| text[at..].to_string())
        };
        let real = suffix(&lower)?;
        let mut stem = lower.clone();
        let mut last = real.clone();
        if let Some(alias) = self.aliases.get(&last) {
            stem = format!("{}{alias}", &stem[..stem.len() - last.len()]);
            last = suffix(&stem).unwrap_or_default();
        }
        if self.encodings.contains(&last) {
            stem.truncate(stem.len() - last.len());
            last = suffix(&stem).unwrap_or_default();
        }
        // The same order as the caller's own check: picture, PDF, sound or film, text, Office.
        match self.kinds.get(&last).map(String::as_str) {
            Some("image") => Some("image"),
            _ if real == ".pdf" => Some("pdf"),
            Some("media") => None,
            Some("text") => Some("text"),
            _ if self.texts.contains(&real) => Some("text"),
            _ if OFFICE.contains(&real.as_str()) => Some("office"),
            _ => None,
        }
    }
}

pub const OFFICE: [&str; 9] = [
    ".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm", ".odt", ".ods", ".odp",
];

// ---- Matching ----

fn word(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

fn same(a: char, b: char) -> bool {
    a == b || a.to_lowercase().eq(b.to_lowercase())
}

/// The length of `term` matched at `text[at..]`, where a space in the term stands for any run of space.
fn matches_at(text: &[char], at: usize, term: &[char]) -> Option<usize> {
    let mut i = at;
    for &t in term {
        if t == ' ' {
            let start = i;
            while i < text.len() && text[i].is_whitespace() {
                i += 1;
            }
            if i == start {
                return None;
            }
        } else if i < text.len() && same(text[i], t) {
            i += 1;
        } else {
            return None;
        }
    }
    Some(i - at)
}

/// The first place a group matches: at a word start, the first term that fits, then the rest of that word.
fn first(text: &[char], group: &[Vec<char>]) -> Option<(usize, usize)> {
    for at in 0..text.len() {
        if at > 0 && word(text[at - 1]) {
            continue;
        }
        if let Some(length) = group.iter().find_map(|term| matches_at(text, at, term)) {
            let mut end = at + length;
            while end < text.len() && word(text[end]) {
                end += 1;
            }
            return Some((at, end));
        }
    }
    None
}

pub struct Passage {
    pub snippet: String,
    pub page: usize,
    pub line: usize,
}

/// The passage around the last of the first matches of all groups, or nothing if one group is missing.
pub fn passage(text: &str, groups: &[Vec<String>]) -> Option<Passage> {
    let text: Vec<char> = text.chars().collect();
    let mut anchor = (0, 0);
    for group in groups {
        let terms: Vec<Vec<char>> = group.iter().map(|t| t.chars().collect()).collect();
        let found = first(&text, &terms)?;
        if found.0 >= anchor.0 {
            anchor = found;
        }
    }
    let feed = '\u{c}';
    let page_end = text[anchor.1..]
        .iter()
        .position(|c| *c == feed)
        .map(|p| p + anchor.1);
    let page_start = text[..anchor.0]
        .iter()
        .rposition(|c| *c == feed)
        .map_or(0, |p| p + 1);
    let start = page_start.max(anchor.0.saturating_sub(100));
    let end = page_end.unwrap_or(text.len()).min(anchor.1 + 220);
    let before = &text[..anchor.0];
    Some(Passage {
        snippet: text[start..end.max(start)]
            .iter()
            .collect::<String>()
            .trim()
            .to_string(),
        page: before.iter().filter(|c| **c == feed).count() + 1,
        line: before.iter().filter(|c| **c == '\n').count() + 1,
    })
}

// ---- Files ----

fn open_in(folder: &File, name: &str, directory: bool) -> std::io::Result<File> {
    let flags = libc::O_NOFOLLOW
        | if directory {
            libc::O_DIRECTORY
        } else {
            libc::O_NONBLOCK
        };
    std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(flags)
        .open(beside(folder, name))
}

fn beside(folder: &File, name: &str) -> PathBuf {
    use std::os::fd::AsRawFd;
    PathBuf::from(format!("/proc/self/fd/{}", folder.as_raw_fd())).join(name)
}

/// The folder `relative` below the pinned root, each step opened without following links.
fn folder(root: &File, relative: &[String]) -> std::io::Result<File> {
    let mut current = root.try_clone()?;
    for part in relative {
        current = open_in(&current, part, true)?;
    }
    Ok(current)
}

pub type Stamp = [i64; 5];

fn stamp(info: &std::fs::Metadata) -> Stamp {
    [
        info.dev() as i64,
        info.ino() as i64,
        info.size() as i64,
        info.mtime() * 1_000_000_000 + info.mtime_nsec(),
        info.ctime() * 1_000_000_000 + info.ctime_nsec(),
    ]
}

/// Text and whether it is incomplete; an error is already worded for the person.
type Reading = Result<(String, bool), String>;

/// The bytes a reader child writes, at most `MAX_TEXT + 1`, within the time limit.
fn child(file: &File, arguments: &[&str]) -> Result<(Vec<u8>, bool, Option<String>), String> {
    let program = std::env::current_exe().map_err(|error| error.to_string())?;
    // The child reads the pinned file through its standard input, so a renamed path cannot swap it.
    let mut process = std::process::Command::new(program)
        .args(arguments)
        .stdin(file.try_clone().map_err(|e| e.to_string())?)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    let mut output = process.stdout.take().ok_or("")?;
    let mut errors = process.stderr.take().ok_or("")?;
    let (sender, received) = mpsc::channel();
    std::thread::spawn(move || {
        let mut data = Vec::new();
        let _ = (&mut output)
            .take(MAX_TEXT as u64 + 1)
            .read_to_end(&mut data);
        let _ = sender.send(data);
    });
    let error = std::thread::spawn(move || {
        let mut text = Vec::new();
        let _ = (&mut errors).take(4096).read_to_end(&mut text);
        text
    });
    let deadline = Instant::now() + Duration::from_secs(READ_SECONDS);
    let data = received.recv_timeout(deadline.saturating_duration_since(Instant::now()));
    let (data, cut) = match data {
        Ok(data) => {
            let cut = data.len() > MAX_TEXT;
            (data, cut)
        }
        Err(_) => (Vec::new(), true),
    };
    if cut {
        let _ = process.kill();
    }
    let status = process.wait().map_err(|e| e.to_string())?;
    let error = String::from_utf8_lossy(&error.join().unwrap_or_default())
        .chars()
        .take(600)
        .collect::<String>();
    let failed = (!status.success() && !cut).then(|| error.trim().to_string());
    Ok((data, cut, failed))
}

fn decode(data: &[u8]) -> String {
    if data.starts_with(b"\xff\xfe") || data.starts_with(b"\xfe\xff") {
        let big = data.starts_with(b"\xfe\xff");
        let units = data[2..].chunks(2).map(|pair| match pair {
            [a, b] if big => u16::from_be_bytes([*a, *b]),
            [a, b] => u16::from_le_bytes([*a, *b]),
            _ => 0xFFFD,
        });
        return char::decode_utf16(units)
            .map(|c| c.unwrap_or('\u{FFFD}'))
            .collect();
    }
    let controls = data
        .iter()
        .filter(|b| **b < 9 || (14..32).contains(*b))
        .count();
    if data.contains(&0) || (!data.is_empty() && controls as f64 / data.len() as f64 > 0.03) {
        return String::new();
    }
    String::from_utf8_lossy(data.strip_prefix(b"\xef\xbb\xbf").unwrap_or(data)).into_owned()
}

/// Reads one file opened in `parent`, as the caller's `read_content` does.
fn read(messages: &HashMap<String, String>, parent: &File, name: &str, kind: &str) -> Reading {
    let say = |text: &str| {
        messages
            .get(text)
            .cloned()
            .unwrap_or_else(|| text.to_string())
    };
    let file = open_in(parent, name, false).map_err(|e| e.to_string())?;
    let info = file.metadata().map_err(|e| e.to_string())?;
    if !info.is_file() {
        return Ok((String::new(), false));
    }
    let suffix = name
        .rfind('.')
        .map(|at| name[at..].to_lowercase())
        .unwrap_or_default();
    let (data, mut partial) = match kind {
        "office" | "pdf" => {
            let office = kind == "office";
            if info.size() > if office { 64 } else { 128 } * 1024 * 1024 {
                if office {
                    return Err(say("Office-Datei zu groß."));
                }
                return Ok((String::new(), true));
            }
            let limit = (MAX_TEXT + 1).to_string();
            let arguments: Vec<&str> = if office {
                vec!["office-text", "/dev/stdin", &suffix]
            } else {
                vec!["pdf-cli", "text", "/dev/stdin", "--limit", &limit]
            };
            let (data, cut, failed) = child(&file, &arguments)?;
            if let Some(failed) = failed {
                let what = if office {
                    "Office-Datei nicht lesbar."
                } else {
                    "PDF nicht lesbar."
                };
                return Err(format!("{} {failed}", say(what)));
            }
            (data, cut)
        }
        _ => {
            let mut data = Vec::new();
            (&file)
                .take(MAX_TEXT as u64 + 1)
                .read_to_end(&mut data)
                .map_err(|e| e.to_string())?;
            (data, false)
        }
    };
    let now = std::fs::symlink_metadata(beside(parent, name)).map_err(|e| e.to_string())?;
    let held = file.metadata().map_err(|e| e.to_string())?;
    if stamp(&info) != stamp(&now) || stamp(&info) != stamp(&held) {
        return Err(say("Datei während der Suche verändert."));
    }
    partial |= data.len() > MAX_TEXT;
    let data = &data[..data.len().min(MAX_TEXT)];
    Ok((decode(data), partial))
}

/// The cached recognition and description of a picture or PDF, valid while the file is unchanged.
fn cached(request: &Request, path: &Path, signature: &Stamp) -> Option<Json> {
    use sha2::Digest;
    let folder = request.cache.as_ref()?;
    let name = path.to_str()?;
    let digest: String = sha2::Sha256::digest(name.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    let mut data = Vec::new();
    File::open(folder.join(digest + ".json"))
        .ok()?
        .take(16 * 1024 * 1024)
        .read_to_end(&mut data)
        .ok()?;
    let value = crate::json::parse(&data)?;
    let kept: Vec<i64> = value
        .get("stamp")?
        .list()?
        .iter()
        .map(Json::whole)
        .collect::<Option<_>>()?;
    (kept.as_slice() == signature.as_slice()).then_some(value)
}

// ---- The walk ----

/// Runs `work` for every job on all cores and hands the results to `each` in the order of the jobs,
/// until `each` answers false.
fn emit(written: &mut std::io::Result<()>, line: String, out: &mut dyn std::io::Write) {
    if written.is_ok() {
        *written = writeln!(out, "{line}").and_then(|_| out.flush());
    }
}

fn ordered<J: Sync, R: Send>(
    jobs: &[J],
    work: impl Fn(&J) -> R + Sync,
    mut each: impl FnMut(usize, R) -> bool,
) {
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    let workers = std::thread::available_parallelism()
        .map_or(4, |n| n.get())
        .min(16);
    let (sender, received) = mpsc::channel::<(usize, R)>();
    let (next, stop) = (AtomicUsize::new(0), AtomicBool::new(false));
    std::thread::scope(|scope| {
        for _ in 0..workers {
            let sender = sender.clone();
            let (work, next, stop) = (&work, &next, &stop);
            scope.spawn(move || {
                loop {
                    let at = next.fetch_add(1, Ordering::Relaxed);
                    if at >= jobs.len()
                        || stop.load(Ordering::Relaxed)
                        || sender.send((at, work(&jobs[at]))).is_err()
                    {
                        break;
                    }
                }
            });
        }
        drop(sender);
        let mut waiting: HashMap<usize, R> = HashMap::new();
        'order: for index in 0..jobs.len() {
            let result = loop {
                if let Some(result) = waiting.remove(&index) {
                    break result;
                }
                match received.recv() {
                    Ok((at, result)) => {
                        waiting.insert(at, result);
                    }
                    Err(_) => break 'order,
                }
            };
            if !each(index, result) {
                break;
            }
        }
        stop.store(true, Ordering::Relaxed);
        drop(received);
    });
}

struct Job {
    relative: Vec<String>,
    name: String,
    kind: &'static str,
    /// Entries visited when this file was reached, for the summary if the search stops here.
    visited: usize,
}

enum Outcome {
    /// Text, whether it is incomplete, and whether the caller must look at the picture.
    Done(String, bool, bool),
    Failed(String),
}

pub fn quote(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn process(request: &Request, root: &File, job: &Job) -> Outcome {
    let parent = match folder(root, &job.relative) {
        Ok(parent) => parent,
        Err(error) => return Outcome::Failed(error.to_string()),
    };
    let (mut text, mut partial) = if job.kind == "image" {
        (String::new(), false)
    } else {
        match read(&request.messages, &parent, &job.name, job.kind) {
            Ok(read) => read,
            Err(error) => return Outcome::Failed(error),
        }
    };
    let mut look = false;
    if request.visual && matches!(job.kind, "image" | "pdf") {
        let info = match std::fs::symlink_metadata(beside(&parent, &job.name)) {
            Ok(info) => info,
            Err(error) => return Outcome::Failed(error.to_string()),
        };
        if info.size() > 128 * 1024 * 1024 {
            return Outcome::Done(text, true, false);
        }
        let path = request.root.join(job.relative.join("/")).join(&job.name);
        let cache = cached(request, &path, &stamp(&info));
        let has = |key: &str| cache.as_ref().and_then(|c| c.get(key)).is_some();
        look = (request.ocr && !has("ocr"))
            || (request.thumbnails && job.kind == "image" && !has("caption"));
        if !look && let Some(cache) = &cache {
            if let Some(found) = cache.get("ocr").and_then(Json::text) {
                text = found.to_string();
            }
            if let Some(caption) = cache
                .get("caption")
                .and_then(Json::text)
                .filter(|c| !c.is_empty())
            {
                text = format!("{text}\n{caption}");
            }
            if let Some(Json::Bool(cut)) = cache.get("partial") {
                partial = *cut;
            }
        }
    }
    Outcome::Done(text, partial, look)
}

/// Runs the search and writes one JSON line per event to `out`.
pub fn run(request: &Request, out: &mut dyn std::io::Write) -> std::io::Result<()> {
    let started = Instant::now();
    let root_path = match request.root.canonicalize() {
        Ok(path) => path,
        Err(error) => {
            return writeln!(
                out,
                "{{\"type\": \"error\", \"message\": {}}}",
                quote(&error.to_string())
            );
        }
    };
    let request = Request {
        root: root_path,
        ..clone(request)
    };
    let root = match std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open(&request.root)
    {
        Ok(root) => root,
        Err(error) => {
            return writeln!(
                out,
                "{{\"type\": \"error\", \"message\": {}}}",
                quote(&error.to_string())
            );
        }
    };
    // The walk itself is cheap and stays in order; reading runs on all cores.
    let mut jobs = Vec::new();
    let mut errors = Vec::new();
    let mut queue: VecDeque<Vec<String>> = VecDeque::from([Vec::new()]);
    let mut visited = 0;
    let mut limit = String::new();
    while let Some(relative) = queue.pop_front() {
        if !limit.is_empty() {
            break;
        }
        let place = request.root.join(relative.join("/"));
        let listing = folder(&root, &relative)
            .and_then(|dir| std::fs::read_dir(beside(&dir, "")).map(|l| (dir, l)));
        let (_dir, listing) = match listing {
            Ok(found) => found,
            Err(error) => {
                errors.push((place.display().to_string(), error.to_string()));
                continue;
            }
        };
        for entry in listing {
            let entry = match entry {
                Ok(entry) => entry,
                Err(error) => {
                    errors.push((place.display().to_string(), error.to_string()));
                    break;
                }
            };
            let Some(name) = entry.file_name().to_str().map(str::to_string) else {
                continue;
            };
            if !request.hidden && name.starts_with('.') {
                continue;
            }
            if visited >= request.max_entries {
                limit = request.say("Eintragslimit");
                break;
            }
            visited += 1;
            match entry.file_type() {
                Ok(kind) if kind.is_symlink() => {}
                Ok(kind) if kind.is_dir() => {
                    let mut next = relative.clone();
                    next.push(name);
                    queue.push_back(next);
                }
                Ok(kind) if kind.is_file() => {
                    if let Some(kind) = request.kind(&name) {
                        jobs.push(Job {
                            relative: relative.clone(),
                            name,
                            kind,
                            visited,
                        });
                    }
                }
                Ok(_) => {}
                Err(error) => {
                    errors.push((place.join(&name).display().to_string(), error.to_string()))
                }
            }
        }
    }
    let walk_errors = errors.len();
    let (mut scanned, mut hits, mut partial, mut empty, mut failed) = (0, 0, 0, 0, walk_errors);
    let mut details: Vec<(String, String)> = errors.into_iter().take(12).collect();
    let mut reached = visited;
    let mut written = Ok(());
    let mut last = Instant::now();
    ordered(
        &jobs,
        |job| process(&request, &root, job),
        |index, outcome| {
            let job = &jobs[index];
            scanned += 1;
            let path = request.root.join(job.relative.join("/")).join(&job.name);
            let shown = quote(&path.display().to_string());
            match outcome {
                Outcome::Failed(error) => {
                    failed += 1;
                    if details.len() < 12 {
                        details.push((
                            path.display().to_string(),
                            error.chars().take(200).collect(),
                        ));
                    }
                }
                Outcome::Done(text, cut, true) => {
                    // The caller recognises the picture and counts this file itself.
                    scanned -= 1;
                    emit(
                        &mut written,
                        format!(
                            "{{\"type\": \"visual\", \"path\": {shown}, \"relative\": {}, \"name\": {}, \"kind\": {}, \"text\": {}, \"partial\": {cut}}}",
                            quote(&job.relative.join("/")),
                            quote(&job.name),
                            quote(job.kind),
                            quote(&text)
                        ),
                        out,
                    );
                }
                Outcome::Done(text, cut, false) => {
                    partial += usize::from(cut);
                    empty += usize::from(text.trim().is_empty());
                    if let Some(found) = (!text.is_empty())
                        .then(|| passage(&text, &request.groups))
                        .flatten()
                    {
                        hits += 1;
                        emit(
                            &mut written,
                            format!(
                                "{{\"type\": \"hit\", \"snippet\": {}, \"page\": {}, \"line\": {}, \"path\": {shown}, \"partial\": {cut}, \"pdf\": {}, \"image\": {}}}",
                                quote(&found.snippet),
                                found.page,
                                found.line,
                                job.kind == "pdf",
                                job.kind == "image"
                            ),
                            out,
                        );
                        if hits >= request.max_hits {
                            limit = request.say("Trefferlimit");
                            reached = job.visited;
                            return false;
                        }
                    }
                }
            }
            if last.elapsed() > Duration::from_millis(150) {
                emit(
                    &mut written,
                    format!(
                        "{{\"type\": \"progress\", \"scanned\": {scanned}, \"visited\": {}, \"hits\": {hits}}}",
                        job.visited
                    ),
                    out,
                );
                last = Instant::now();
            }
            written.is_ok()
        },
    );
    written?;
    let details: Vec<String> = details
        .iter()
        .map(|(path, error)| format!("{{\"path\": {}, \"error\": {}}}", quote(path), quote(error)))
        .collect();
    writeln!(
        out,
        "{{\"type\": \"done\", \"scanned\": {scanned}, \"visited\": {reached}, \"hits\": {hits}, \"errors\": {failed}, \"partial\": {partial}, \"empty\": {empty}, \"limit\": {}, \"error_details\": [{}], \"elapsed\": {}}}",
        quote(&limit),
        details.join(", "),
        started.elapsed().as_secs_f64()
    )?;
    out.flush()
}

/// What the knowledge index asks for: the text of every readable file, depth first, as the index
/// counts entries and bytes.
pub struct Index {
    pub root: PathBuf,
    pub excluded: Vec<String>,
    pub suffixes: Vec<String>,
    pub max_entries: usize,
    pub max_bytes: usize,
    pub messages: HashMap<String, String>,
}

impl Index {
    pub fn from_json(value: &Json) -> Option<Index> {
        let list = |key: &str| -> Option<Vec<String>> {
            value
                .get(key)?
                .list()?
                .iter()
                .map(|e| e.text().map(str::to_string))
                .collect()
        };
        let count = |key: &str, default: i64| -> Option<usize> {
            usize::try_from(value.get(key).map_or(Some(default), Json::whole)?).ok()
        };
        Some(Index {
            root: value.get("root")?.text()?.into(),
            excluded: list("excluded")?,
            suffixes: list("suffixes")?,
            max_entries: count("max_entries", 10_000)?,
            max_bytes: count("max_bytes", 32 * 1024 * 1024)?,
            messages: match value.get("messages") {
                Some(Json::Object(entries)) => entries
                    .iter()
                    .map(|(k, v)| Some((k.clone(), v.text()?.to_string())))
                    .collect::<Option<_>>()?,
                _ => HashMap::new(),
            },
        })
    }
}

struct Entry {
    relative: Vec<String>,
    name: String,
    kind: &'static str,
    stamp: String,
}

/// Writes a `text` line per file and a `done` line with the number of entries, whether a limit cut the
/// index short, and how many files could not be read.
pub fn index(request: &Index, out: &mut dyn std::io::Write) -> std::io::Result<()> {
    let opened = request.root.canonicalize().and_then(|root| {
        let pinned = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open(&root)?;
        Ok((root, pinned))
    });
    let (root_path, root) = match opened {
        Ok(found) => found,
        Err(error) => {
            return writeln!(
                out,
                "{{\"type\": \"error\", \"message\": {}}}",
                quote(&error.to_string())
            );
        }
    };
    let mut entries = Vec::new();
    let mut stack: Vec<Vec<String>> = vec![Vec::new()];
    let mut count = 0;
    let mut cut = false;
    'walk: while let Some(relative) = stack.pop() {
        let listing = folder(&root, &relative)
            .and_then(|dir| std::fs::read_dir(beside(&dir, "")).map(|l| (dir, l)));
        let (dir, listing) = match listing {
            Ok(found) => found,
            Err(error) => {
                return writeln!(
                    out,
                    "{{\"type\": \"error\", \"message\": {}}}",
                    quote(&error.to_string())
                );
            }
        };
        for entry in listing.flatten() {
            count += 1;
            if count > request.max_entries {
                cut = true;
                break 'walk;
            }
            let Some(name) = entry.file_name().to_str().map(str::to_string) else {
                continue;
            };
            let lower = name.to_lowercase();
            let stem = match lower.rfind('.') {
                Some(at) if at > 0 => &lower[..at],
                _ => lower.as_str(),
            };
            if name.starts_with('.') || request.excluded.iter().any(|x| *x == lower || x == stem) {
                continue;
            }
            match entry.file_type() {
                Ok(kind) if kind.is_symlink() => {}
                Ok(kind) if kind.is_dir() => {
                    let mut next = relative.clone();
                    next.push(name);
                    stack.push(next);
                }
                Ok(kind) if kind.is_file() => {
                    let suffix = match lower.rfind('.') {
                        Some(at) if at > 0 => &lower[at..],
                        _ => "",
                    };
                    if !request.suffixes.iter().any(|s| s == suffix) {
                        continue;
                    }
                    let Ok(info) = std::fs::symlink_metadata(beside(&dir, &name)) else {
                        continue;
                    };
                    let kind = if suffix == ".pdf" {
                        "pdf"
                    } else if OFFICE.contains(&suffix) {
                        "office"
                    } else {
                        "text"
                    };
                    entries.push(Entry {
                        relative: relative.clone(),
                        name,
                        kind,
                        stamp: format!(
                            "{}:{}",
                            info.mtime() * 1_000_000_000 + info.mtime_nsec(),
                            info.size()
                        ),
                    });
                }
                _ => {}
            }
        }
    }
    cut |= !stack.is_empty() || count >= request.max_entries;
    let (mut size, mut errors) = (0, 0);
    let mut written = Ok(());
    ordered(
        &entries,
        |entry| {
            folder(&root, &entry.relative)
                .map_err(|e| e.to_string())
                .and_then(|parent| read(&request.messages, &parent, &entry.name, entry.kind))
        },
        |index, result| {
            if size >= request.max_bytes {
                cut = true;
                return false;
            }
            let entry = &entries[index];
            match result {
                Ok((text, _)) if !text.is_empty() => {
                    size += text.len();
                    let path = root_path.join(entry.relative.join("/")).join(&entry.name);
                    emit(
                        &mut written,
                        format!(
                            "{{\"type\": \"text\", \"path\": {}, \"stamp\": {}, \"text\": {}}}",
                            quote(&path.display().to_string()),
                            quote(&entry.stamp),
                            quote(&text)
                        ),
                        out,
                    );
                }
                Ok(_) => {}
                Err(_) => errors += 1,
            }
            written.is_ok()
        },
    );
    written?;
    cut |= size >= request.max_bytes;
    writeln!(
        out,
        "{{\"type\": \"done\", \"limited\": {cut}, \"errors\": {errors}}}"
    )?;
    out.flush()
}

fn clone(request: &Request) -> Request {
    Request {
        root: request.root.clone(),
        groups: request.groups.clone(),
        hidden: request.hidden,
        max_hits: request.max_hits,
        max_entries: request.max_entries,
        visual: request.visual,
        ocr: request.ocr,
        thumbnails: request.thumbnails,
        kinds: request.kinds.clone(),
        texts: request.texts.clone(),
        encodings: request.encodings.clone(),
        aliases: request.aliases.clone(),
        cache: request.cache.clone(),
        messages: request.messages.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn groups(terms: &[&[&str]]) -> Vec<Vec<String>> {
        terms
            .iter()
            .map(|g| g.iter().map(|t| t.to_string()).collect())
            .collect()
    }

    #[test]
    fn passages_follow_the_word_start_rule_and_name_their_page_and_line() {
        let text = "Kopf\n\u{c}Die Rechnungen vom März\nfür den Monitorarm und Zubehör";
        let found = passage(text, &groups(&[&["rechnung"], &["monitor", "bildschirm"]])).unwrap();
        assert_eq!((found.page, found.line), (2, 3));
        assert_eq!(
            found.snippet,
            "Die Rechnungen vom März\nfür den Monitorarm und Zubehör"
        );
        assert!(passage(text, &groups(&[&["echnung"]])).is_none());
        assert!(passage("ab_rechnung", &groups(&[&["rechnung"]])).is_none());
        assert_eq!(passage("ÄPFEL", &groups(&[&["äpfel"]])).unwrap().line, 1);
        assert!(passage("neue  \n rechnung", &groups(&[&["neue rechnung"]])).is_some());
    }

    #[test]
    fn decoding_refuses_binary_and_reads_byte_orders() {
        assert_eq!(decode(b"\xef\xbb\xbfhallo"), "hallo");
        assert_eq!(decode(b"a\0b"), "");
        assert_eq!(decode(b"\xff\xfeh\0i\0"), "hi");
        assert_eq!(decode(b"\xfe\xff\0h\0i"), "hi");
        assert_eq!(decode(b"caf\xe9"), "caf\u{FFFD}");
    }
}

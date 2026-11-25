//! The notebook core against the golden corpus the Python code it replaces recorded
//! (`tests/notebook-golden.json`, made by `make_golden.py` from `files/wissen_data.py` at
//! `ee2046ca`; `LUMEN_NOTEBOOK_GOLDEN` names the full corpus). Results, refusals, written bytes,
//! file modes, history rows, settings rows and drafts must be identical.
use super::*;
use sha2::{Digest, Sha256};
use std::os::unix::fs::{FileTypeExt, MetadataExt};

fn golden() -> Py {
    let path = std::env::var("LUMEN_NOTEBOOK_GOLDEN").unwrap_or_else(|_| {
        concat!(env!("CARGO_MANIFEST_DIR"), "/tests/notebook-golden.json").into()
    });
    python::loads(&std::fs::read_to_string(path).expect("golden corpus")).expect("golden JSON")
}

fn items(value: &Py) -> &[Py] {
    match value {
        Py::List(items) => items,
        _ => &[],
    }
}

fn text<'a>(value: &'a Py, key: &str) -> &'a str {
    value.get(key).and_then(Py::as_str).unwrap_or_default()
}

fn b64(data: &str) -> Vec<u8> {
    base64::engine::general_purpose::STANDARD
        .decode(data)
        .expect("base64")
}

/// A recorded value: itself, or `sha256:` of a long one.
fn same(expected: &str, actual: &str) -> bool {
    match expected.strip_prefix("sha256:") {
        Some(hash) => digest(actual.as_bytes()) == hash,
        None => expected == actual,
    }
}

/// Python's exception type and message for a refusal.
fn python_error(failure: &Failure) -> (String, String) {
    match failure {
        Failure::Refused(text) => ("ValueError".into(), (*text).into()),
        Failure::Value(text) => ("ValueError".into(), text.clone()),
        Failure::Unicode(text) => ("UnicodeDecodeError".into(), text.clone()),
        Failure::Os {
            errno,
            filename,
            path,
        } => {
            let kind = match *errno {
                libc::ENOENT => "FileNotFoundError",
                libc::EEXIST => "FileExistsError",
                libc::ENOTDIR => "NotADirectoryError",
                libc::EISDIR => "IsADirectoryError",
                libc::EACCES | libc::EPERM => "PermissionError",
                _ => "OSError",
            };
            let strerror = std::io::Error::from_raw_os_error(*errno).to_string();
            let strerror = strerror
                .split(" (os error")
                .next()
                .unwrap_or_default()
                .to_owned();
            let name = filename.as_deref().map(|f| {
                if *path {
                    format!("PosixPath({})", python::str_repr(f))
                } else {
                    python::str_repr(f)
                }
            });
            (
                kind.into(),
                match name {
                    Some(name) => format!("[Errno {errno}] {strerror}: {name}"),
                    None => format!("[Errno {errno}] {strerror}"),
                },
            )
        }
    }
}

#[test]
fn parse_matches_python() {
    let golden = golden();
    let cases = items(golden.get("parse").unwrap());
    assert!(cases.len() > 150);
    for case in cases {
        let raw = b64(text(case, "raw"));
        let result = case.get("result").unwrap();
        match parse(text(case, "path"), &raw) {
            Ok(note) => {
                let expected = text(result, "ok");
                let actual = python::dumps(&note.to_py(), false);
                assert!(
                    same(expected, &actual),
                    "{}\nexpected {expected}\nactual   {actual}",
                    text(case, "name")
                );
            }
            Err(error) => {
                assert_eq!(
                    text(result, "error"),
                    "UnicodeDecodeError",
                    "{}",
                    text(case, "name")
                );
                assert_eq!(text(result, "message"), error.0, "{}", text(case, "name"));
            }
        }
    }
}

#[test]
fn encode_matches_python() {
    let golden = golden();
    let cases = items(golden.get("encode").unwrap());
    assert!(cases.len() > 400);
    for case in cases {
        let body = match case.get("text_repeat") {
            Some(Py::List(repeat)) => repeat[0]
                .as_str()
                .unwrap()
                .repeat(python::py_str(&repeat[1]).parse().unwrap()),
            _ => text(case, "text").to_owned(),
        };
        let created = case.get("created").unwrap();
        let result = case.get("result").unwrap();
        let actual = text::encode(
            &body,
            case.get("source").unwrap(),
            case.get("legacy").unwrap(),
            created,
            text(case, "note_id"),
        );
        match (result.get("ok"), actual) {
            (Some(Py::Str(expected)), Ok(raw)) => assert!(
                same(expected, encoded(&raw).as_str().unwrap()) || b64(expected) == raw,
                "{created:?}"
            ),
            (None, Err(text::EncodeError::Large)) => assert_eq!(
                text(result, "message"),
                "Notiz größer als 1 MiB. Bitte aufteilen."
            ),
            (None, Err(text::EncodeError::Uuid)) => assert_eq!(
                text(result, "message"),
                "badly formed hexadecimal UUID string"
            ),
            (expected, actual) => panic!("{created:?}: {expected:?} != {actual:?}"),
        }
    }
}

#[test]
fn excerpts_match_python() {
    let golden = golden();
    for case in items(golden.get("excerpt").unwrap()) {
        let limit: usize = python::py_str(case.get("limit").unwrap()).parse().unwrap();
        assert_eq!(
            excerpt(text(case, "text"), text(case, "query"), limit),
            text(case, "result"),
            "{}",
            text(case, "query")
        );
    }
}

/// The clock and UUIDs the corpus was recorded with.
fn replayed(clock: (f64, f64)) -> Env {
    let calls = std::sync::Arc::new(std::sync::Mutex::new((0u64, 0u64)));
    let (times, ids) = (calls.clone(), calls);
    Env {
        now: Box::new(move || {
            let mut calls = times.lock().unwrap();
            let value = clock.0 + calls.0 as f64 * clock.1;
            calls.0 += 1;
            value
        }),
        random: Box::new(move || {
            let mut calls = ids.lock().unwrap();
            let seed = Sha256::digest(format!("lumen-golden-{}", calls.1).as_bytes());
            calls.1 += 1;
            seed[..16].try_into().unwrap()
        }),
    }
}

fn snapshot(store: &Path, root: &Path) -> Py {
    fn collect(dir: &Path, paths: &mut Vec<PathBuf>) {
        for entry in std::fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            paths.push(path.clone());
            if path.symlink_metadata().unwrap().is_dir() {
                collect(&path, paths);
            }
        }
    }
    fn walk(base: &Path, prefix: &str, out: &mut Vec<(String, Py)>) {
        let mut paths = Vec::new();
        collect(base, &mut paths);
        for path in paths {
            let name = path.file_name().unwrap().to_string_lossy();
            if name.starts_with("notes-index-")
                || name == "lumen.sqlite3"
                || name == "library.sqlite"
                || name.ends_with("-journal")
            {
                continue;
            }
            let meta = path.symlink_metadata().unwrap();
            let relative = format!("{prefix}{}", path.strip_prefix(base).unwrap().display());
            let mode = Py::Str(format!("0o{:o}", meta.mode() & 0o7777));
            let value = if meta.file_type().is_symlink() {
                dict(vec![(
                    "link",
                    Py::Str(std::fs::read_link(&path).unwrap().display().to_string()),
                )])
            } else if meta.is_dir() {
                dict(vec![("mode", mode), ("dir", Py::Bool(true))])
            } else if meta.file_type().is_fifo() {
                dict(vec![("mode", mode), ("special", Py::Bool(true))])
            } else {
                let data = std::fs::read(&path).unwrap();
                if data.len() > 65536 {
                    dict(vec![("mode", mode), ("sha256", Py::Str(digest(&data)))])
                } else {
                    dict(vec![("mode", mode), ("data", encoded(&data))])
                }
            };
            out.push((relative, value));
        }
    }
    let mut files = Vec::new();
    walk(store, "store/", &mut files);
    walk(root, "book/", &mut files);
    let db = rusqlite::Connection::open(store.join("lumen.sqlite3")).unwrap();
    let settings: Vec<Py> = db
        .prepare("SELECT key, value FROM settings ORDER BY key")
        .unwrap()
        .query_map([], |r| {
            Ok(Py::List(vec![Py::Str(r.get(0)?), Py::Str(r.get(1)?)]))
        })
        .unwrap()
        .map(|r| r.unwrap())
        .collect();
    let mut history = Vec::new();
    let database = store.join("wissen-history/library.sqlite");
    if database.exists() {
        let db = rusqlite::Connection::open(database).unwrap();
        history = db
            .prepare("SELECT id, title, data, archived, updated FROM records ORDER BY rowid")
            .unwrap()
            .query_map([], |r| {
                Ok(Py::List(vec![
                    Py::Str(r.get(0)?),
                    Py::Str(r.get(1)?),
                    Py::Str(r.get(2)?),
                    Py::int(r.get(3)?),
                    Py::Str(python::float_repr(r.get(4)?)),
                ]))
            })
            .unwrap()
            .map(|r| r.unwrap())
            .collect();
    }
    dict(vec![
        ("files", Py::Dict(files)),
        ("settings", Py::List(settings)),
        ("history", Py::List(history)),
    ])
}

/// Python's results name the folders it ran in and the folder's identity; both differ here.
fn portable(text: &str, places: &[(&str, &str)]) -> String {
    let mut text = text.to_owned();
    for (from, to) in places {
        text = text.replace(from, to);
    }
    let identity =
        regex::Regex::new(r#"\[(\\?)"fsid:[0-9]+\\?", [0-9]+\]|\[[0-9]+, [0-9]+\]"#).unwrap();
    identity.replace_all(&text, "IDENTITY").into_owned()
}

/// A result with the places and the folder identity made portable; scans in path order, as the
/// order of a folder's entries is the file system's own.
fn comparable(value: &Py, places: &[(&str, &str)], operation: &str) -> Py {
    fn walk(value: &Py, places: &[(&str, &str)]) -> Py {
        match value {
            Py::Str(text) => Py::Str(portable(text, places)),
            Py::List(items) => Py::List(items.iter().map(|v| walk(v, places)).collect()),
            Py::Dict(items) => Py::Dict(
                items
                    .iter()
                    .map(|(k, v)| {
                        (
                            k.clone(),
                            if k == "identity" {
                                Py::None
                            } else {
                                walk(v, places)
                            },
                        )
                    })
                    .collect(),
            ),
            other => other.clone(),
        }
    }
    let mut value = walk(value, places);
    if operation == "scan"
        && let Py::Dict(items) = &mut value
        && let Some((_, Py::List(notes))) = items.iter_mut().find(|(k, _)| k == "notes")
    {
        notes.sort_by_key(path_of);
    }
    value
}

/// Equal, a recorded `sha256:` standing for the long text it hashes.
fn matches(expected: &Py, actual: &Py) -> bool {
    match (expected, actual) {
        (Py::Str(e), Py::Str(a)) => same(e, a),
        (Py::List(e), Py::List(a)) => {
            e.len() == a.len() && e.iter().zip(a).all(|(e, a)| matches(e, a))
        }
        (Py::Dict(e), Py::Dict(a)) => {
            e.len() == a.len()
                && e.iter()
                    .zip(a)
                    .all(|((ek, ev), (ak, av))| ek == ak && matches(ev, av))
        }
        (e, a) => e == a,
    }
}

/// The files of a snapshot in path order; a draft, named by the digest of the folder's path and
/// holding that path, as its JSON text under the note's path.
fn sorted_files(snapshot: &Py) -> Py {
    let Some(Py::Dict(files)) = snapshot.get("files") else {
        return Py::None;
    };
    let mut files: Vec<(String, Py)> = files
        .iter()
        .map(
            |(name, value)| match (name.starts_with("store/wissen-drafts/"), value.get("data")) {
                (true, Some(Py::Str(data))) => {
                    let text = String::from_utf8(b64(data)).unwrap();
                    let draft = python::loads(&text).unwrap();
                    (
                        format!("store/wissen-drafts/{}", text_of(&draft, "path")),
                        dict(vec![
                            ("mode", value.get("mode").unwrap().clone()),
                            ("text", Py::Str(text)),
                        ]),
                    )
                }
                _ => (name.clone(), value.clone()),
            },
        )
        .collect();
    files.sort_by(|a, b| a.0.cmp(&b.0));
    Py::Dict(files)
}

fn text_of(value: &Py, key: &str) -> String {
    text(value, key).to_owned()
}

fn strip(mut note: Py) -> Py {
    if let Py::Dict(items) = &mut note {
        items.retain(|(k, _)| k != "modified");
    }
    note
}

#[test]
fn operations_match_python() {
    let golden = golden();
    let clock = items(golden.get("clock").unwrap());
    let clock = (
        python::py_str(&clock[0]).parse().unwrap(),
        python::py_str(&clock[1]).parse().unwrap(),
    );
    let base = std::env::temp_dir().join(format!("lumen-notebook-golden-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    for sequence in items(golden.get("sequences").unwrap()) {
        let name = text(sequence, "name");
        let (store_dir, root) = (base.join(name).join("store"), base.join(name).join("book"));
        std::fs::create_dir_all(&store_dir).unwrap();
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&root)
            .unwrap();
        let db = rusqlite::Connection::open(store_dir.join("lumen.sqlite3")).unwrap();
        db.execute_batch("CREATE TABLE memories (id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, updated REAL NOT NULL); CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);").unwrap();
        for row in items(sequence.get("memories").unwrap()) {
            let row = items(row);
            let updated: f64 = python::py_str(&row[4]).parse().unwrap();
            db.execute(
                "INSERT INTO memories VALUES (?,?,?,?,?)",
                rusqlite::params![
                    row[0].as_str(),
                    row[1].as_str(),
                    row[2].as_str(),
                    row[3].as_str(),
                    updated
                ],
            )
            .unwrap();
        }
        drop(db);
        for entry in items(sequence.get("tree").unwrap()) {
            let entry = items(entry);
            let target = root.join(entry[1].as_str().unwrap());
            match entry[0].as_str().unwrap() {
                "dir" => std::fs::create_dir(&target).unwrap(),
                "file" => std::fs::write(&target, b64(entry[2].as_str().unwrap())).unwrap(),
                "repeat" => {
                    let repeat = items(&entry[2]);
                    std::fs::write(
                        &target,
                        repeat[0]
                            .as_str()
                            .unwrap()
                            .repeat(python::py_str(&repeat[1]).parse().unwrap()),
                    )
                    .unwrap()
                }
                "link" => std::os::unix::fs::symlink(entry[2].as_str().unwrap(), &target).unwrap(),
                "fifo" => assert!(
                    std::process::Command::new("mkfifo")
                        .arg(&target)
                        .status()
                        .unwrap()
                        .success()
                ),
                kind => panic!("{kind}"),
            }
        }
        let store = Store {
            directory: store_dir.clone(),
        };
        let env = replayed(clock);
        let root_text = root.to_string_lossy().into_owned();
        let places = [
            (text(sequence, "root"), root_text.as_str()),
            (text(sequence, "store"), store_dir.to_str().unwrap()),
        ];
        let book = Notebook::open(&store, &env, Some(&root_text), false, None).unwrap();
        for step in items(sequence.get("steps").unwrap()) {
            let operation = text(step, "operation");
            let a = step.get("resolved").unwrap();
            // Long arguments are recorded as `repeat:<character>:<count>`.
            let s = |key: &str| match text(a, key)
                .strip_prefix("repeat:")
                .and_then(|r| r.split_once(':'))
            {
                Some((ch, count)) => ch.repeat(count.parse().unwrap()),
                None => text(a, key).to_owned(),
            };
            let opt = |key: &str| a.get(key).filter(|v| **v != Py::None).cloned();
            let result: Result<Py> = match operation {
                "create" => book
                    .create(
                        &s("title"),
                        &s("text"),
                        &opt("source").unwrap_or(Py::str("")),
                        &opt("legacy").unwrap_or(Py::str("")),
                        a.get("folder").and_then(Py::as_str).unwrap_or("."),
                        &s("note_id"),
                    )
                    .map(strip),
                "create_collection" => book.create_collection(&s("name")).map(Py::Str),
                "write" => book
                    .write(
                        &s("path"),
                        &s("text"),
                        &s("expected"),
                        opt("source"),
                        opt("legacy"),
                        opt("created"),
                        opt("note_id").map(|v| python::py_str(&v)),
                    )
                    .map(strip),
                "read" => book.read(&s("path")).map(strip),
                "raw" => book.raw(&s("path")).map(|r| encoded(&r)),
                "image" => book.image(&s("path")).map(|r| encoded(&r)),
                "remove" => book.remove(&s("path"), &s("expected")).map(Py::Str),
                "versions" => book
                    .versions(a.get("path").and_then(Py::as_str))
                    .map(Py::List),
                "restore" => book.restore(&s("key"), &s("expected")).map(strip),
                "context" => {
                    let paths: Vec<String> = items(a.get("paths").unwrap())
                        .iter()
                        .map(python::py_str)
                        .collect();
                    book.context(&paths, &s("query"))
                        .map(|n| Py::List(n.into_iter().map(strip).collect()))
                }
                "capture" => book
                    .capture(
                        &s("title"),
                        &s("text"),
                        &opt("source").unwrap_or(Py::str("")),
                        a.get("memory").and_then(Py::as_str),
                    )
                    .map(Py::Str),
                "memory_path" => book.memory_path(&s("memory")).map(Py::Str),
                "migrate" => book.migrate().map(|n| Py::int(n as i64)),
                "activate" => {
                    activate(&store, &env, a.get("root").and_then(Py::as_str)).map(Py::Str)
                }
                "draft" => draft(
                    &store,
                    &root_text,
                    &s("path"),
                    a.get("text").and_then(Py::as_str),
                    &s("expected"),
                )
                .map(|d| d.unwrap_or(Py::None)),
                "clear_draft" => clear_draft(&store, &root_text, &s("path")).map(|()| Py::None),
                "scan" => book.scan(&Limits::default()).map(|scan| {
                    dict(vec![
                        (
                            "notes",
                            Py::List(scan.notes.into_iter().map(strip).collect()),
                        ),
                        (
                            "folders",
                            Py::List(scan.folders.iter().map(|f| Py::str(f)).collect()),
                        ),
                        ("errors", Py::int(scan.errors as i64)),
                        ("limited", Py::Bool(scan.limited)),
                        ("root", Py::str(&root_text)),
                        ("identity", book.identity.clone()),
                    ])
                }),
                other => panic!("{other}"),
            };
            let expected = step.get("result").unwrap();
            let label = format!(
                "{name}: {operation} {}",
                python::dumps(step.get("arguments").unwrap(), false)
                    .chars()
                    .take(120)
                    .collect::<String>()
            );
            match (expected.get("ok"), result) {
                (Some(expected), Ok(actual)) => {
                    let (expected, actual) = (
                        comparable(expected, &places, operation),
                        comparable(&actual, &[], operation),
                    );
                    assert!(
                        matches(&expected, &actual),
                        "{label}\nexpected {}\nactual   {}",
                        python::dumps(&expected, false),
                        python::dumps(&actual, false)
                    );
                }
                (None, Err(failure)) => {
                    let (kind, message) = python_error(&failure);
                    let expected_message = portable(text(expected, "message"), &places);
                    assert_eq!(
                        (text(expected, "error"), expected_message.as_str()),
                        (kind.as_str(), portable(&message, &[]).as_str()),
                        "{label}"
                    );
                }
                (expected, actual) => panic!("{label}\nexpected {expected:?}\nactual   {actual:?}"),
            }
        }
        let expected = sequence.get("snapshot").unwrap();
        let actual = snapshot(&store_dir, &root);
        let normal =
            |value: &Py, places: &[(&str, &str)]| portable(&python::dumps(value, false), places);
        let (e, a) = (
            normal(&sorted_files(expected), &places),
            normal(&sorted_files(&actual), &[]),
        );
        let at = e
            .chars()
            .zip(a.chars())
            .position(|(x, y)| x != y)
            .unwrap_or(e.len().min(a.len()));
        assert_eq!(
            e,
            a,
            "{name}: files differ at {at}: {:?} / {:?}",
            e.chars()
                .skip(at.saturating_sub(300))
                .take(500)
                .collect::<String>(),
            a.chars()
                .skip(at.saturating_sub(300))
                .take(500)
                .collect::<String>()
        );
        assert_eq!(
            normal(expected.get("settings").unwrap(), &places),
            normal(actual.get("settings").unwrap(), &[]),
            "{name}: settings"
        );
        assert_eq!(
            normal(expected.get("history").unwrap(), &places),
            normal(actual.get("history").unwrap(), &[]),
            "{name}: history"
        );
    }
    std::fs::remove_dir_all(&base).unwrap();
}

/// A store with the settings table and an empty notebook folder, removed when dropped.
struct Place(PathBuf);

impl Place {
    fn new(name: &str) -> Self {
        let base =
            std::env::temp_dir().join(format!("lumen-notebook-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(base.join("store")).unwrap();
        std::fs::create_dir_all(base.join("book")).unwrap();
        rusqlite::Connection::open(base.join("store/lumen.sqlite3"))
            .unwrap()
            .execute_batch("CREATE TABLE memories (id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, updated REAL NOT NULL); CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
            .unwrap();
        Place(base)
    }
    fn store(&self) -> Store {
        Store {
            directory: self.0.join("store"),
        }
    }
    fn root(&self) -> String {
        self.0.join("book").to_string_lossy().into_owned()
    }
}

impl Drop for Place {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

#[test]
fn scan_limits_are_exact_and_excess_is_explicit() {
    let place = Place::new("limits");
    let (store, env) = (place.store(), Env::default());
    let book = Notebook::open(&store, &env, Some(&place.root()), false, None).unwrap();
    std::fs::write(book.root.join("one.md"), "# One").unwrap();
    let limits = |bytes, notes, entries| Limits {
        bytes,
        notes,
        entries,
    };
    assert!(
        !book
            .scan(&limits(MAX_SCAN_BYTES, 1, MAX_SCAN_ENTRIES))
            .unwrap()
            .limited
    );
    std::fs::write(book.root.join("two.md"), "# Two").unwrap();
    assert!(
        book.scan(&limits(MAX_SCAN_BYTES, 1, MAX_SCAN_ENTRIES))
            .unwrap()
            .limited
    );
    assert!(
        !book
            .scan(&limits(10, MAX_SCAN_NOTES, MAX_SCAN_ENTRIES))
            .unwrap()
            .limited
    );
    assert!(
        book.scan(&limits(9, MAX_SCAN_NOTES, MAX_SCAN_ENTRIES))
            .unwrap()
            .limited
    );
    assert!(
        !book
            .scan(&limits(MAX_SCAN_BYTES, MAX_SCAN_NOTES, 2))
            .unwrap()
            .limited
    );
    assert!(
        book.scan(&limits(MAX_SCAN_BYTES, MAX_SCAN_NOTES, 1))
            .unwrap()
            .limited
    );
    File::create(book.root.join("oversized.md"))
        .unwrap()
        .set_len(MAX_NOTE as u64 + 1)
        .unwrap();
    let scan = book.scan(&Limits::default()).unwrap();
    assert_eq!((scan.notes.len(), scan.errors, scan.limited), (2, 1, false));
}

#[test]
fn concurrent_writers_never_lose_an_edit_or_leave_a_temporary_file() {
    let place = Place::new("writers");
    let (store, env) = (place.store(), Env::default());
    let book = Notebook::open(&store, &env, Some(&place.root()), false, None).unwrap();
    book.write("shared.md", "# Start", "", None, None, None, None)
        .unwrap();
    let saved = std::sync::Mutex::new(Vec::new());
    std::thread::scope(|scope| {
        for writer in 0..6 {
            let (store, root, saved) = (&store, place.root(), &saved);
            scope.spawn(move || {
                let env = Env::default();
                let book = Notebook::open(store, &env, Some(&root), false, None).unwrap();
                for round in 0..15 {
                    let current = book.read("shared.md").unwrap();
                    let text = format!("# Writer {writer} round {round}");
                    match book.write(
                        "shared.md",
                        &text,
                        text_of(&current, "hash").as_str(),
                        None,
                        None,
                        None,
                        None,
                    ) {
                        Ok(_) => saved.lock().unwrap().push(text),
                        Err(Failure::Refused(message)) => {
                            assert!(message.starts_with("CONFLICT:"), "{message}")
                        }
                        Err(other) => panic!("{other:?}"),
                    }
                }
            });
        }
    });
    let saved = saved.into_inner().unwrap();
    // Every accepted write kept the bytes it replaced; the file holds the last one.
    assert!(!saved.is_empty());
    assert_eq!(book.versions(Some("shared.md")).unwrap().len(), saved.len());
    let last = text_of(&book.read("shared.md").unwrap(), "text");
    assert!(saved.contains(&last));
    let leftovers: Vec<_> = std::fs::read_dir(&book.root)
        .unwrap()
        .map(|e| e.unwrap().file_name())
        .filter(|n| n.to_string_lossy().starts_with(".lumen-"))
        .collect();
    assert!(leftovers.is_empty(), "{leftovers:?}");
}

#[test]
fn requests_answer_with_python_refusals() {
    let place = Place::new("requests");
    let env = Env::default();
    let request = |op: &str, values: serde_json::Value| {
        let mut request =
            serde_json::json!({"op": op, "store": place.0.join("store"), "root": place.root()});
        request
            .as_object_mut()
            .unwrap()
            .extend(values.as_object().unwrap().clone());
        request
    };
    let note = answer(
        &request("notes.create", serde_json::json!({"title": "Erste"})),
        b"",
        &env,
    )
    .unwrap();
    assert_eq!(text(&note, "title"), "Erste");
    let missing = answer(
        &request("notes.read", serde_json::json!({"path": "fehlt.md"})),
        b"",
        &env,
    )
    .unwrap_err();
    assert_eq!(
        missing,
        Failure::Os {
            errno: libc::ENOENT,
            filename: Some("fehlt.md".into()),
            path: false
        }
    );
    let refusal = refusal(&request("notes.read", serde_json::json!({})), &missing);
    assert_eq!(
        python::dumps(&refusal, false),
        r#"{"failed": "", "kind": "os", "errno": 2, "filename": "fehlt.md", "path_object": false}"#
    );
    let unknown = answer(&request("notes.nothing", serde_json::json!({})), b"", &env).unwrap_err();
    assert_eq!(unknown, Failure::Refused("Unbekannte Notizaktion."));
    let path = answer(
        &request("notes.attach", serde_json::json!({"size": 3})),
        b"png",
        &env,
    )
    .unwrap();
    let path = text(&path, "path").to_owned();
    assert!(path.starts_with("attachments/") && path.ends_with(".png"));
    assert_eq!(
        std::fs::read(Path::new(&place.root()).join(&path)).unwrap(),
        b"png"
    );
    let parsed = answer(
        &serde_json::json!({"op": "notes.parse", "path": "x.md", "raw": "IyBUCiNh"}),
        b"",
        &env,
    )
    .unwrap();
    assert_eq!(items(parsed.get("tags").unwrap()), &[Py::str("a")]);
}

/// The editor's derivations and edits against the Python modules they replace
/// (`tests/editor-golden.json`, made by `make_editor_golden.py` of the R10 measurements from
/// `files/note_tags.py`, `notes_properties.py` and `notes_structure.py` at `2ee18980`;
/// `LUMEN_EDITOR_GOLDEN` names a larger corpus).
#[test]
fn editor_derivations_and_edits_match_python() {
    let path = std::env::var("LUMEN_EDITOR_GOLDEN").unwrap_or_else(|_| {
        concat!(env!("CARGO_MANIFEST_DIR"), "/tests/editor-golden.json").into()
    });
    let golden: Value =
        serde_json::from_str(&std::fs::read_to_string(path).expect("editor corpus"))
            .expect("editor JSON");
    let refused = |failure: Failure| match failure {
        Failure::Refused(text) => serde_json::json!({"error": text}),
        other => panic!("{other:?}"),
    };
    // An edited text as recorded: the unchanged prefix and suffix and the new middle.
    let edited = |before: &str, result: Result<String>| match result {
        Ok(after) => {
            let (a, b): (Vec<char>, Vec<char>) =
                (before.chars().collect(), after.chars().collect());
            let prefix = a.iter().zip(&b).take_while(|(x, y)| x == y).count();
            let shorter = a.len().min(b.len()) - prefix;
            let suffix = a
                .iter()
                .rev()
                .zip(b.iter().rev())
                .take(shorter)
                .take_while(|(x, y)| x == y)
                .count();
            serde_json::json!({"ok": [prefix, suffix, b[prefix..b.len() - suffix].iter().collect::<String>()]})
        }
        Err(failure) => refused(failure),
    };
    let edits = golden["property_edits"].as_array().unwrap();
    let mut checked = 0;
    for record in golden["texts"].as_array().unwrap() {
        let (name, source) = (
            record["name"].as_str().unwrap(),
            record["text"].as_str().unwrap(),
        );
        assert_eq!(
            serde_json::json!(text::tags(source)),
            record["tags"],
            "tags {name}"
        );
        let targets: Vec<Value> = text::targets(source)
            .into_iter()
            .map(|t| serde_json::json!({"title": t.title, "anchor": t.title, "start": t.start, "level": t.level}))
            .collect();
        assert_eq!(Value::from(targets), record["targets"], "targets {name}");
        let chars: Vec<char> = source.chars().collect();
        let mask = text::body_mask(source);
        let mut runs: Vec<[usize; 2]> = Vec::new();
        for (i, (a, b)) in chars.iter().zip(&mask).enumerate() {
            match runs.last_mut() {
                Some(run) if a != b && run[1] == i => run[1] = i + 1,
                _ if a != b => runs.push([i, i + 1]),
                _ => {}
            }
        }
        assert_eq!(serde_json::json!(runs), record["mask"], "mask {name}");
        let properties = match text::property_values(source) {
            Ok(values) => {
                let values: serde_json::Map<String, Value> = values
                    .into_iter()
                    .map(|(n, p)| (n, serde_json::json!({"kind": p.kind, "value": p.value})))
                    .collect();
                serde_json::json!({"ok": values})
            }
            Err(failure) => refused(failure),
        };
        assert_eq!(properties, record["properties"], "properties {name}");
        for case in record["add_tag"].as_array().unwrap() {
            let tag = case[0].as_str().unwrap();
            assert_eq!(
                edited(source, edit::add_tag(source, tag)),
                case[1],
                "add_tag {name} {tag}"
            );
            checked += 1;
        }
        for case in record["rename_tag"].as_array().unwrap() {
            let (old, new, below) = (
                case[0].as_str().unwrap(),
                case[1].as_str().unwrap(),
                case[2].as_bool().unwrap(),
            );
            assert_eq!(
                edited(source, edit::rename_tag(source, old, new, below)),
                case[3],
                "rename_tag {name} {old} {new}"
            );
            checked += 1;
        }
        let own = record["change_own"].as_array().unwrap();
        let cases = edits.iter().zip(record["change"].as_array().unwrap());
        for (case, result) in cases.chain(own.iter().map(|c| (c, &c[4]))) {
            let (n, k, v, r) = (
                case[0].as_str().unwrap(),
                case[1].as_str().unwrap(),
                case[2].as_str().unwrap(),
                case[3].as_bool().unwrap(),
            );
            assert_eq!(
                edited(source, edit::set_property(source, n, k, v, r)),
                *result,
                "change {name} {n} {k} {r}"
            );
            checked += 1;
        }
    }
    for case in golden["identity"].as_array().unwrap() {
        let value = case[0].as_str().unwrap();
        let expected = match text::identity(value) {
            Some(tag) => serde_json::json!({"ok": tag}),
            None => serde_json::json!({"error": "Ungültiger Tag."}),
        };
        assert_eq!(expected, case[1], "identity {value}");
    }
    assert!(checked > 20000, "{checked} edits");
}

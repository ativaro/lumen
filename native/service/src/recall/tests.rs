//! The memory against the recorded Python memory domain (`tests/memory-golden.json`, made by
//! `measure/memory/make_golden.py` of the R10 measurements; `LUMEN_MEMORY_GOLDEN` names another
//! corpus): each step's answer or refusal, the server requests and searches it made, the calls of the
//! clock and the identifiers, and afterwards the Store rows, files with their modes, history rows and
//! index rows must be the Python code's, byte for byte.
use super::*;
use crate::learning;
use std::cell::RefCell;
use std::os::unix::fs::MetadataExt;
use std::sync::{Arc, Mutex};

fn golden() -> Py {
    let path = std::env::var("LUMEN_MEMORY_GOLDEN").unwrap_or_else(|_| {
        concat!(env!("CARGO_MANIFEST_DIR"), "/tests/memory-golden.json").into()
    });
    python::loads(&std::fs::read_to_string(path).expect("golden corpus")).expect("golden JSON")
}

fn replayed(clock: (f64, f64), calls: Arc<Mutex<(u64, u64)>>) -> Env {
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

fn oct(mode: u32) -> String {
    format!("0o{:o}", mode & 0o7777)
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    for entry in std::fs::read_dir(dir).into_iter().flatten().flatten() {
        let path = entry.path();
        out.push(path.clone());
        if path.symlink_metadata().unwrap().is_dir() {
            walk(&path, out);
        }
    }
}

struct Case {
    base: PathBuf,
    identities: RefCell<Vec<(String, Py)>>,
}

impl Case {
    fn replace(&self, mut text: String, ascii: bool) -> String {
        for (name, identity) in self.identities.borrow().iter() {
            text = text.replace(
                &python::dumps(identity, ascii),
                &python::dumps(&Py::Str(format!("<IDENTITY:{name}>")), ascii),
            );
        }
        text.replace(&*self.base.to_string_lossy(), "<BASE>")
    }

    fn normal(&self, value: &Py) -> Py {
        python::loads(&self.replace(python::dumps(value, false), false)).unwrap()
    }

    fn expand(&self, value: &Py) -> Py {
        let text = python::dumps(value, false).replace("<BASE>", &self.base.to_string_lossy());
        python::loads(&text).unwrap()
    }

    fn learn(&self, name: &str, root: &Path) {
        let Ok(fd) = rustix::fs::open(
            root,
            rustix::fs::OFlags::RDONLY | rustix::fs::OFlags::DIRECTORY,
            rustix::fs::Mode::empty(),
        ) else {
            return;
        };
        let stat = rustix::fs::fstat(&fd).unwrap();
        let fsid = rustix::fs::fstatvfs(&fd).unwrap().f_fsid;
        let first = if fsid != 0 {
            Py::Str(format!("fsid:{fsid}"))
        } else {
            Py::Int(stat.st_dev.to_string())
        };
        self.identities.borrow_mut().push((
            name.into(),
            Py::List(vec![first, Py::Int(stat.st_ino.to_string())]),
        ));
    }

    fn snapshot(&self) -> Py {
        let db = rusqlite::Connection::open(self.base.join("state/lumen.sqlite3")).unwrap();
        let rows: Vec<(String, String)> = db
            .prepare("SELECT key,value FROM settings WHERE key LIKE 'memory/%' OR key LIKE 'knowledge/%' ORDER BY key")
            .unwrap()
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
            .unwrap()
            .collect::<rusqlite::Result<_>>()
            .unwrap();
        let settings = rows
            .into_iter()
            .map(|(key, value)| (key, Py::Str(self.replace(value, true))))
            .collect();
        let mut files = Vec::new();
        for folder in [
            "state/lumen-memory",
            "state/wissen",
            "state/wissen-history/assets",
            "state/wissen-drafts",
            "state/memory-index",
        ] {
            let mut paths = Vec::new();
            walk(&self.base.join(folder), &mut paths);
            paths.sort();
            for path in paths {
                let name = path
                    .strip_prefix(&self.base)
                    .unwrap()
                    .to_string_lossy()
                    .into_owned();
                let meta = path.metadata().unwrap();
                let mode = ("mode", Py::Str(oct(meta.mode())));
                let value = if meta.is_dir() {
                    dict(vec![mode])
                } else if name.ends_with(".sqlite3") {
                    let db = rusqlite::Connection::open(&path).unwrap();
                    let index = db
                        .prepare("SELECT id,revision,digest,complete FROM records ORDER BY id")
                        .and_then(|mut q| {
                            q.query_map([], |r| {
                                Ok(Py::List(vec![
                                    Py::Str(r.get(0)?),
                                    Py::Str(r.get(1)?),
                                    Py::Str(r.get(2)?),
                                    Py::int(r.get(3)?),
                                ]))
                            })?
                            .collect::<rusqlite::Result<Vec<_>>>()
                        })
                        .map_or(Py::None, Py::List);
                    dict(vec![mode, ("index", index)])
                } else if ["-journal", "-wal", "-shm"]
                    .iter()
                    .any(|s| name.ends_with(s))
                {
                    continue;
                } else {
                    let data = std::fs::read(&path).unwrap();
                    if data.len() <= 512 {
                        use base64::Engine;
                        let b64 = base64::engine::general_purpose::STANDARD.encode(&data);
                        dict(vec![mode, ("b64", Py::Str(b64))])
                    } else {
                        dict(vec![
                            mode,
                            ("sha256", Py::Str(engine_hex(&Sha256::digest(&data)))),
                            ("size", Py::int(data.len() as i64)),
                        ])
                    }
                };
                files.push((name, value));
            }
        }
        let mut history = Vec::new();
        let library = self.base.join("state/wissen-history/library.sqlite");
        if library.exists() {
            let db = rusqlite::Connection::open(&library).unwrap();
            history = db
                .prepare("SELECT id,title,data,archived,updated FROM records ORDER BY id")
                .unwrap()
                .query_map([], |r| {
                    Ok(Py::List(vec![
                        Py::Str(r.get(0)?),
                        Py::Str(r.get(1)?),
                        Py::Str(r.get(2)?),
                        Py::int(r.get(3)?),
                        Py::Float(r.get(4)?),
                    ]))
                })
                .unwrap()
                .collect::<rusqlite::Result<_>>()
                .unwrap();
        }
        self.normal(&dict(vec![
            ("settings", Py::Dict(settings)),
            ("files", Py::Dict(files)),
            ("history", Py::List(history)),
        ]))
    }
}

/// Python's type and `str()` of a refusal, as the binding raises it.
fn outcome(result: Result<Py>, t: &Texts) -> Py {
    let (kind, message) = match result {
        Ok(value) => return dict(vec![("ok", value)]),
        Err(Failure::Refused(text)) => ("ValueError".to_owned(), t.tr(text)),
        Err(Failure::Value(text)) => ("ValueError".to_owned(), text),
        Err(Failure::Unicode(text)) => ("UnicodeDecodeError".to_owned(), text),
        Err(Failure::Os {
            errno,
            filename,
            path,
        }) => {
            let kind = match errno {
                libc::ENOENT => "FileNotFoundError",
                libc::EEXIST => "FileExistsError",
                libc::ENOTDIR => "NotADirectoryError",
                libc::EISDIR => "IsADirectoryError",
                libc::EACCES | libc::EPERM => "PermissionError",
                _ => "OSError",
            };
            let strerror = std::io::Error::from_raw_os_error(errno).to_string();
            let strerror = strerror.split(" (os error").next().unwrap_or_default();
            let message = match filename {
                Some(f) if path => {
                    format!(
                        "[Errno {errno}] {strerror}: PosixPath({})",
                        python::str_repr(&f)
                    )
                }
                Some(f) => format!("[Errno {errno}] {strerror}: {}", python::str_repr(&f)),
                None => format!("[Errno {errno}] {strerror}"),
            };
            (kind.to_owned(), message)
        }
    };
    dict(vec![
        ("error", Py::Str(kind)),
        ("message", Py::Str(message)),
    ])
}

/// The urllib failures of the recording are the stub's text refusals here.
fn comparable(value: &Py) -> Py {
    match s(value, "error") {
        "URLError" | "TimeoutError" | "HTTPError" => {
            let mut value = value.clone();
            value.set("error", text("ValueError"));
            value
        }
        _ => value.clone(),
    }
}

/// A search's entries come in scan order.
fn entries_sorted(calls: &Py) -> Py {
    Py::List(
        list(calls)
            .iter()
            .map(|call| {
                let mut call = call.clone();
                let mut entries = list(&or(&call, "entries", Py::None)).to_vec();
                entries.sort_by_key(|e| python::dumps(e, false));
                call.set("entries", Py::List(entries));
                call
            })
            .collect(),
    )
}

fn in_path_order(value: &Py) -> Py {
    let sort = |notes: &Py| {
        let mut notes = list(notes).to_vec();
        notes.sort_by(|a, b| s(a, "path").cmp(s(b, "path")));
        Py::List(notes)
    };
    let mut value = value.clone();
    match get(&value, "ok").cloned() {
        Some(Py::List(_)) => value.set("ok", sort(get(&value, "ok").unwrap())),
        Some(mut ok @ Py::Dict(_)) => {
            ok.set("notes", sort(&or(&ok, "notes", Py::List(Vec::new()))));
            value.set("ok", ok);
        }
        _ => {}
    }
    value
}

fn strip_modified(value: &Py) -> Py {
    match value {
        Py::Dict(items) => Py::Dict(
            items
                .iter()
                .filter(|(k, _)| k != "modified")
                .map(|(k, v)| (k.clone(), strip_modified(v)))
                .collect(),
        ),
        Py::List(items) => Py::List(items.iter().map(strip_modified).collect()),
        other => other.clone(),
    }
}

/// The scripted server's answer to a request, as the recorder's `request` gave it.
fn scripted(answers: &RefCell<Py>, path: &str, config_root: &Path) -> Result<Py> {
    let answer = {
        let mut table = answers.borrow_mut();
        let key = match table.get(path) {
            Some(_) => Some(path.to_owned()),
            None => items(&table)
                .iter()
                .find(|(k, _)| k.ends_with('*') && path.starts_with(&k[..k.len() - 1]))
                .map(|(k, _)| k.clone()),
        };
        match (key, &mut *table) {
            (Some(key), Py::Dict(fields)) => {
                let slot = &mut fields.iter_mut().find(|(k, _)| *k == key).unwrap().1;
                match slot {
                    Py::List(list) if list.len() > 1 => Some(list.remove(0)),
                    Py::List(list) => list.first().cloned(),
                    other => Some(other.clone()),
                }
            }
            _ => None,
        }
    };
    let fail = answer
        .as_ref()
        .map(|a| s(a, "fail").to_owned())
        .unwrap_or_default();
    let Some(answer) = answer.filter(|a| get(a, "fail").is_none()) else {
        return Err(Failure::Value(match fail.as_str() {
            "timeout" => "timed out".into(),
            status if status.starts_with("status:") => {
                format!("HTTP Error {}: Refused", &status[7..])
            }
            _ => "<urlopen error [Errno 111] Connection refused>".into(),
        }));
    };
    if let Some(config) = get(&answer, "pairing") {
        write_pairing(config_root, config);
    }
    Ok(or(&answer, "json", Py::None))
}

fn write_pairing(config_root: &Path, config: &Py) {
    let folder = config_root.join("lumen-server");
    std::fs::create_dir_all(&folder).unwrap();
    std::fs::set_permissions(&folder, std::fs::Permissions::from_mode(0o700)).unwrap();
    let path = folder.join("connection.json");
    if matches!(config, Py::None) {
        let _ = std::fs::remove_file(&path);
        return;
    }
    std::fs::write(&path, python::dumps(config, true)).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
}

/// A learning profile without what differs by design: the program its tools run with and the
/// folders of the recording; the engine configuration and the event compared as values.
fn profile_view(value: &Py) -> Py {
    let Some(ok) = get(value, "ok") else {
        return value.clone();
    };
    fn sorted(value: &Py) -> Py {
        match value {
            Py::Dict(items) => {
                let mut items: Vec<_> = items.iter().map(|(k, v)| (k.clone(), sorted(v))).collect();
                items.sort_by(|a, b| a.0.cmp(&b.0));
                Py::Dict(items)
            }
            Py::List(items) => Py::List(items.iter().map(sorted).collect()),
            other => other.clone(),
        }
    }
    let mut environment = or(ok, "environment", empty());
    let mut engine = python::loads(s(&environment, "OPENCODE_CONFIG_CONTENT")).unwrap_or(Py::None);
    let mut mcp = or(&engine, "mcp", empty());
    let mut tools = or(&mcp, "lumen_learning", empty());
    tools.set("command", text("<the learning tools>"));
    let mut variables = or(&tools, "environment", empty());
    variables.set("XDG_CONFIG_HOME", text("<config>"));
    variables.set("XDG_DATA_HOME", text("<data>"));
    tools.set("environment", variables);
    mcp.set("lumen_learning", tools);
    engine.set("mcp", mcp);
    environment.set("OPENCODE_CONFIG_CONTENT", engine);
    let mut files = or(ok, "files", empty());
    if let Some(event) = get(&files, "event.json").cloned() {
        let mut event = event;
        event.set("text", python::loads(s(&event, "text")).unwrap_or(Py::None));
        files.set("event.json", event);
    }
    let mut ok = ok.clone();
    ok.set("environment", environment);
    ok.set("files", files);
    sorted(&dict(vec![("ok", ok)]))
}

#[test]
fn the_memory_matches_the_recorded_python_domain() {
    let golden = golden();
    let clock = list(get(&golden, "clock").unwrap());
    let clock = (number(&clock[0]).unwrap(), number(&clock[1]).unwrap());
    let work = std::env::temp_dir().join(format!("lumen-memory-golden-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&work);
    let catalogue = concat!(env!("CARGO_MANIFEST_DIR"), "/../../files/translations/en");
    let mut failures = Vec::new();
    let mut steps = 0;
    for (index, case) in list(get(&golden, "cases").unwrap()).iter().enumerate() {
        let base = work.join(format!("case-{index}"));
        for folder in ["state", "tools", "home", "config", "data"] {
            std::fs::create_dir_all(base.join(folder)).unwrap();
        }
        let state = base.join("state");
        std::fs::set_permissions(&state, std::fs::Permissions::from_mode(0o700)).unwrap();
        rusqlite::Connection::open(state.join("lumen.sqlite3"))
            .unwrap()
            .execute_batch(
                "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                 CREATE TABLE memories (id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, updated REAL NOT NULL);
                 PRAGMA user_version=3;",
            )
            .unwrap();
        let counters = Arc::new(Mutex::new((0, 0)));
        let env = replayed(clock, counters.clone());
        let mut vars = crate::engine::Env::new();
        for (key, value) in [
            ("HOME", "home"),
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"),
            ("LUMEN_TOOLS_DATA", "tools"),
            ("LUMEN_MEMORY_HOME", "no-model"),
        ] {
            vars.insert(key.into(), base.join(value).to_string_lossy().into_owned());
        }
        let this = Case {
            base: base.clone(),
            identities: RefCell::default(),
        };
        let store = Store { directory: state };
        let answers = RefCell::new(Py::Dict(Vec::new()));
        let server_calls = RefCell::new(Vec::new());
        let stub: RefCell<Option<Py>> = RefCell::new(None);
        let search_calls = RefCell::new(Vec::new());
        let language = RefCell::new("de".to_owned());
        let config_root = base.join("config");
        let mut last = Py::None;
        for (number_, step) in list(get(case, "steps").unwrap()).iter().enumerate() {
            steps += 1;
            let t = Texts::of(
                &json!({"texts": {"language": *language.borrow(), "catalogue": catalogue}}),
            );
            let server = |_: &Map<String, Value>, path: &str, body: Option<&Py>, timeout: u64| {
                server_calls.borrow_mut().push(dict(vec![
                    ("path", text(path)),
                    ("body", body.cloned().unwrap_or(Py::None)),
                    ("timeout", Py::int(timeout as i64)),
                ]));
                scripted(&answers, path, &config_root)
            };
            let retrieve = |ctx: &Ctx,
                            entries: &[Entry],
                            query: &str,
                            boundary: &str,
                            cache: &Path,
                            project: &str| {
                let Some(stub) = stub.borrow().clone() else {
                    return retrieve_local(ctx, entries, query, boundary, cache, project);
                };
                let listed = entries
                    .iter()
                    .map(|e| Py::List(vec![text(&e.id), text(&e.revision), text(&e.title)]))
                    .collect();
                search_calls.borrow_mut().push(dict(vec![
                    ("query", text(query)),
                    ("project", text(project)),
                    ("entries", Py::List(listed)),
                ]));
                if on(&stub, "raise") {
                    return Err(Failure::Value("search failed".into()));
                }
                let default = dict(vec![
                    ("mode", text("hybrid")),
                    ("reason", text("")),
                    ("ready", Py::int(1)),
                    ("total", Py::int(1)),
                ]);
                let mut found = Retrieved::of(or(&stub, "state", default));
                let (scores, excerpts) =
                    (or(&stub, "scores", empty()), or(&stub, "excerpts", empty()));
                for e in entries {
                    let key = (e.id.clone(), e.revision.clone());
                    if let Some(score) = get(&scores, &e.title).and_then(number) {
                        found.scores.insert(key.clone(), score);
                    }
                    if let Some(excerpt) = get(&excerpts, &e.title).and_then(Py::as_str) {
                        found.excerpts.insert(key, excerpt.to_owned());
                    }
                }
                Ok(found)
            };
            let search = |_: Value, _: Duration| None;
            let ctx = Ctx {
                env: &env,
                t: &t,
                vars: &vars,
                server: &server,
                retrieve: &retrieve,
                search: &search,
            };
            server_calls.borrow_mut().clear();
            search_calls.borrow_mut().clear();
            let op = s(step, "op").to_owned();
            let recorded = ["op", "result", "server", "search", "clock", "ids", "after"];
            let args = this.expand(&Py::Dict(
                items(step)
                    .iter()
                    .filter(|(k, _)| !recorded.contains(&k.as_str()))
                    .cloned()
                    .collect(),
            ));
            let arg = |k: &str| or(&args, k, Py::None);
            let solutions = get(&args, "solutions").is_none_or(Py::truthy);
            let result: Result<Py> = (|| match op.as_str() {
                "setup.activate" => {
                    let root = notebook::activate(&store, &env, None)?;
                    this.learn("user", Path::new(&root));
                    Ok(Py::Str(root))
                }
                "setup.memory" => {
                    let memory = Memory::open(&store, &ctx)?;
                    this.learn("memory", &root(&store));
                    Ok(text(memory.namespace()))
                }
                "setup.note" | "setup.write" => {
                    let place = root(&store).to_string_lossy().into_owned();
                    let book = if s(&args, "area") == "user" {
                        Notebook::open(&store, &env, None, false, None)?
                    } else {
                        Memory::open(&store, &ctx)?;
                        Notebook::open(&store, &env, Some(&place), true, None)?
                    };
                    if op == "setup.note" {
                        book.create(
                            s(&args, "title"),
                            s(&args, "text"),
                            &or(&args, "source", text("")),
                            &text(""),
                            get(&args, "folder").and_then(Py::as_str).unwrap_or("."),
                            s(&args, "note_id"),
                        )
                    } else {
                        let note_id = get(&args, "note_id").map(python::py_str);
                        let (path, body) = (s(&args, "path"), s(&args, "text"));
                        book.write(path, body, s(&args, "expected"), None, None, None, note_id)
                    }
                }
                "setup.setting" => {
                    store.set_setting(s(&args, "key"), &arg("value"))?;
                    Ok(Py::None)
                }
                "setup.dir" => {
                    std::fs::create_dir_all(base.join(s(&args, "path"))).unwrap();
                    Ok(Py::None)
                }
                "setup.workbench" => {
                    workbench(&ctx)?;
                    let library = base.join("tools/workbench/library.sqlite");
                    rusqlite::Connection::open(library)
                        .unwrap()
                        .execute(
                            "INSERT INTO records VALUES (?,?,?,?,?)",
                            rusqlite::params![
                                s(&args, "id"),
                                s(&args, "title"),
                                python::dumps(&or(&args, "data", empty()), true),
                                0,
                                number(&arg("updated")).unwrap()
                            ],
                        )
                        .unwrap();
                    Ok(Py::None)
                }
                "setup.pair" => {
                    write_pairing(&config_root, &arg("config"));
                    Ok(Py::None)
                }
                "setup.cache" => {
                    let path = config_root.join("lumen-server/memory.sqlite3");
                    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
                    let _ = std::fs::remove_file(&path);
                    if !matches!(arg("scope"), Py::None) {
                        let db = rusqlite::Connection::open(&path).unwrap();
                        db.execute_batch("CREATE TABLE memory_owner(scope TEXT); CREATE TABLE memories(id TEXT PRIMARY KEY,title TEXT,body TEXT,revision INT,source TEXT)").unwrap();
                        db.execute("INSERT INTO memory_owner VALUES (?)", [s(&args, "scope")])
                            .unwrap();
                        for row in list(&arg("rows")) {
                            db.execute(
                                "INSERT INTO memories VALUES (?,?,?,?,?)",
                                rusqlite::params![
                                    s(row, "id"),
                                    s(row, "title"),
                                    s(row, "body"),
                                    number(&or(row, "revision", Py::int(0))).unwrap() as i64,
                                    s(&args, "source")
                                ],
                            )
                            .unwrap();
                        }
                    }
                    Ok(Py::None)
                }
                "setup.server" => {
                    *answers.borrow_mut() = arg("answers");
                    Ok(Py::None)
                }
                "setup.search" => {
                    *stub.borrow_mut() = Some(arg("stub")).filter(|v| !matches!(v, Py::None));
                    Ok(Py::None)
                }
                "setup.auth" => {
                    let auth = base.join("data/opencode/auth.json");
                    std::fs::create_dir_all(auth.parent().unwrap()).unwrap();
                    match arg("credentials") {
                        Py::None => std::fs::remove_file(&auth).unwrap(),
                        credentials => {
                            std::fs::write(&auth, python::dumps(&credentials, true)).unwrap()
                        }
                    }
                    Ok(Py::None)
                }
                "setup.language" => {
                    *language.borrow_mut() = s(&args, "language").to_owned();
                    Ok(Py::None)
                }
                "memory.stamp" => stamp(&store, &ctx),
                "memory.server_stamp" => Ok(Py::Str(memory_stamp(&ctx))),
                "memory.fingerprint" => Ok(Py::List(
                    list(&arg("texts"))
                        .iter()
                        .map(|t| Py::Str(fingerprint(&python::py_str(t))))
                        .collect(),
                )),
                "learning.validate" => Ok(Py::List(learning::validated_items(
                    &arg("items"),
                    &arg("user_text"),
                    &arg("context"),
                    solutions,
                ))),
                "learning.previous" => Ok(learning::previous_answer(list(&arg("messages")))),
                "learning.session" => {
                    let mut session = learning::Session::new(
                        &arg("text"),
                        &arg("candidates"),
                        &arg("context"),
                        solutions,
                    )
                    .map_err(Failure::Value)?;
                    let mut results = Vec::new();
                    for call in list(&arg("calls")) {
                        let call = list(call);
                        results.push(match session.call(&python::py_str(&call[0]), &call[1]) {
                            Ok(value) => dict(vec![("ok", value)]),
                            Err(message) => dict(vec![
                                ("error", text("ValueError")),
                                ("message", Py::Str(message)),
                            ]),
                        });
                    }
                    Ok(dict(vec![
                        ("results", Py::List(results)),
                        ("items", session.items.clone().unwrap_or(Py::None)),
                    ]))
                }
                "learning.profile" => {
                    let folder = base.join("learning");
                    let _ = std::fs::remove_dir_all(&folder);
                    std::fs::create_dir_all(&folder).unwrap();
                    let program = Path::new("<PROGRAM>");
                    let environment = learning::profile(
                        &folder,
                        &value(&arg("config")),
                        s(&args, "model"),
                        &arg("event"),
                        &vars,
                        program,
                    )
                    .map_err(Failure::Value)?;
                    let mut paths = Vec::new();
                    walk(&folder, &mut paths);
                    paths.sort();
                    let mut files = Vec::new();
                    for path in paths {
                        let meta = path.metadata().unwrap();
                        let mut entry = dict(vec![("mode", Py::Str(oct(meta.mode())))]);
                        if meta.is_file() {
                            entry.set("text", Py::Str(std::fs::read_to_string(&path).unwrap()));
                        }
                        let name = path
                            .strip_prefix(&folder)
                            .unwrap()
                            .to_string_lossy()
                            .into_owned();
                        files.push((name, entry));
                    }
                    let environment = environment
                        .into_iter()
                        .map(|(k, v)| (k, Py::Str(v)))
                        .collect();
                    Ok(dict(vec![
                        ("environment", Py::Dict(environment)),
                        ("files", Py::Dict(files)),
                    ]))
                }
                "turn.context" => {
                    let mut memory = Memory::open(&store, &ctx)?;
                    let prepared = memory.prepare(s(&args, "query"), s(&args, "directory"))?;
                    let context = s(&prepared, "context");
                    let shown = if context.is_empty() {
                        String::new()
                    } else {
                        block(&t, context)
                    };
                    Ok(dict(vec![
                        ("prepared", prepared),
                        ("block", Py::Str(shown)),
                    ]))
                }
                "turn.session" => {
                    let (saved, current) = (arg("saved"), arg("current"));
                    let previous = (!matches!(saved, Py::None)).then_some(&saved);
                    let mut row = current.clone();
                    row.set("notes", session_notes(previous, &current));
                    let mut fresh = current.clone();
                    fresh.set("notes", session_notes(None, &current));
                    Ok(dict(vec![
                        (
                            "changed",
                            Py::Bool(session_memory_changed(&saved, &current)),
                        ),
                        ("row", row),
                        ("fresh", fresh),
                    ]))
                }
                _ => {
                    let mut request = args.clone();
                    request.set("op", Py::Str(op.clone()));
                    request.set(
                        "store",
                        Py::Str(store.directory.to_string_lossy().into_owned()),
                    );
                    answer(&request, &ctx)
                }
            })();
            let mut found = this.normal(&strip_modified(&outcome(result, &t)));
            let mut expected = comparable(get(step, "result").unwrap());
            // The order of a folder's entries is the file system's own: scans in path order.
            let scanned = op == "memory.scan" || (op == "memory.eligible" && !on(&args, "query"));
            if scanned {
                found = in_path_order(&found);
                expected = in_path_order(&expected);
            }
            if op == "learning.profile" {
                found = profile_view(&found);
                expected = profile_view(&expected);
            }
            let (clock_calls, id_calls) = *counters.lock().unwrap();
            let after = match get(step, "after") {
                Some(Py::Str(same)) if same == "same" => last.clone(),
                Some(after) => after.clone(),
                None => Py::None,
            };
            let checks = [
                ("result", found, expected),
                (
                    "server",
                    this.normal(&Py::List(server_calls.borrow().clone())),
                    or(step, "server", Py::None),
                ),
                (
                    "search",
                    entries_sorted(&this.normal(&Py::List(search_calls.borrow().clone()))),
                    entries_sorted(&or(step, "search", Py::None)),
                ),
                (
                    "clock",
                    Py::int(clock_calls as i64),
                    or(step, "clock", Py::None),
                ),
                ("ids", Py::int(id_calls as i64), or(step, "ids", Py::None)),
                ("after", this.snapshot(), after.clone()),
            ];
            for (what, found, expected) in checks {
                if found != expected {
                    failures.push(format!(
                        "case {index} ({}) step {number_} {op} {what}:\n  rust:   {}\n  python: {}",
                        s(case, "name"),
                        head(&python::dumps(&found, false), 2500),
                        head(&python::dumps(&expected, false), 2500)
                    ));
                }
            }
            last = after;
        }
    }
    let _ = std::fs::remove_dir_all(&work);
    assert!(steps > 0);
    assert!(
        failures.is_empty(),
        "{} differences in {steps} steps, the first:\n{}",
        failures.len(),
        failures
            .iter()
            .take(8)
            .cloned()
            .collect::<Vec<_>>()
            .join("\n")
    );
}

#[test]
fn identities_paths_and_queries_are_pythons() {
    let namespace = uuid_bytes("fbd90444-6347-4257-8e77-e2067b48e1b9");
    // uuid.uuid5(uuid.UUID('fbd90444-…'), 'Ärger/ä.md')
    assert_eq!(
        uuid5(&namespace, "Ärger/ä.md"),
        "72be2482-b488-58e5-85ac-3c3fd4a55c0a"
    );
    assert_eq!(pure("./a//b/"), "a/b");
    assert_eq!(pure(""), ".");
    assert_eq!(pure("/tmp/"), "/tmp");
    assert!(relative_to("a/b", "."));
    assert!(relative_to("/a/b", "/a"));
    assert!(!relative_to("/ab", "/a"));
    assert_eq!(resolve("/nonexistent/x/../y"), "/nonexistent/y");
    assert_eq!(
        quote("Grüße & ?=/%~._-"),
        "Gr%C3%BC%C3%9Fe%20%26%20%3F%3D/%25~._-"
    );
}

/// A private state folder with a Store for a test of its own.
struct Fixture {
    base: PathBuf,
    store: Store,
    vars: crate::engine::Env,
    env: Env,
    t: Texts,
}

impl Fixture {
    fn new(name: &str) -> Self {
        let base = std::env::temp_dir().join(format!("lumen-memory-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        for folder in ["state", "tools", "home", "config", "data"] {
            std::fs::create_dir_all(base.join(folder)).unwrap();
        }
        rusqlite::Connection::open(base.join("state/lumen.sqlite3"))
            .unwrap()
            .execute_batch(
                "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); PRAGMA user_version=3;",
            )
            .unwrap();
        let mut vars = crate::engine::Env::new();
        for (key, value) in [
            ("HOME", "home"),
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"),
            ("LUMEN_TOOLS_DATA", "tools"),
            ("LUMEN_MEMORY_HOME", "no-model"),
        ] {
            vars.insert(key.into(), base.join(value).to_string_lossy().into_owned());
        }
        Fixture {
            store: Store {
                directory: base.join("state"),
            },
            base,
            vars,
            env: Env::default(),
            t: Texts::default(),
        }
    }

    fn with<T>(&self, retrieve: &Retrieve, work: impl FnOnce(&Ctx) -> T) -> T {
        let server = |_: &Pairing, _: &str, _: Option<&Py>, _: u64| -> Result<Py> {
            Err(Failure::Value("no server".into()))
        };
        let search = |_: Value, _: Duration| None;
        work(&Ctx {
            env: &self.env,
            t: &self.t,
            vars: &self.vars,
            server: &server,
            retrieve,
            search: &search,
        })
    }

    /// The memory's folder takes no new files: every write of a note fails.
    fn read_only(&self, on: bool) {
        let mode = if on { 0o500 } else { 0o700 };
        std::fs::set_permissions(root(&self.store), std::fs::Permissions::from_mode(mode)).unwrap();
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::set_permissions(root(&self.store), std::fs::Permissions::from_mode(0o700));
        let _ = std::fs::remove_dir_all(&self.base);
    }
}

fn plain(_: &Ctx, _: &[Entry], _: &str, _: &str, _: &Path, _: &str) -> Result<Retrieved> {
    Ok(Retrieved::of(dict(vec![
        ("mode", text("text")),
        ("reason", text("not_installed")),
    ])))
}

fn note_text(value: &Py) -> String {
    s(value, "text").to_owned()
}

#[test]
fn an_interrupted_new_memory_keeps_its_scope_and_is_never_approved() {
    let fixture = Fixture::new("interrupted-new");
    let alpha = fixture.base.join("alpha");
    std::fs::create_dir_all(&alpha).unwrap();
    let alpha = alpha.to_string_lossy().into_owned();
    fixture.with(&plain, |ctx| {
        let memory = Memory::open(&fixture.store, ctx).unwrap();
        memory.configure(true, false, None, None, None).unwrap();
        fixture.read_only(true);
        let failed = memory.remember(
            "Neu",
            &text("Privater Alpha-Text"),
            &text("Test"),
            "fact",
            &alpha,
            false,
            "",
            "",
            "",
            "",
        );
        fixture.read_only(false);
        assert!(matches!(failed, Err(Failure::Os { .. })));
        // The record of the note that never came about is private and keeps its scope.
        let records = memory.records().unwrap();
        let (path, pending) = &items(&records)[0];
        assert!(path.starts_with("pending-"));
        assert_eq!(get(pending, "allowed"), Some(&Py::Bool(false)));
        assert_eq!(s(pending, "scope"), alpha);
        assert!(memory.eligible(&alpha).unwrap().is_empty());
        // The next memory goes through, and the pending record does not come back.
        let saved = memory
            .remember(
                "Neu",
                &text("Jetzt"),
                &text("Test"),
                "fact",
                "",
                false,
                "",
                "",
                "",
                "",
            )
            .unwrap();
        assert!(get(&or(&saved, "memory", empty()), "allowed").is_none());
        assert_eq!(items(&memory.records().unwrap()).len(), 2);
    });
}

#[test]
fn a_failed_body_write_keeps_the_metadata_and_the_grant() {
    let fixture = Fixture::new("failed-body");
    fixture.with(&plain, |ctx| {
        let memory = Memory::open(&fixture.store, ctx).unwrap();
        memory.configure(true, false, None, None, None).unwrap();
        let original = memory
            .remember(
                "Alt",
                &text("Alter Text"),
                &text("Test"),
                "fact",
                "",
                false,
                "",
                "",
                "",
                "",
            )
            .unwrap();
        let before = python::dumps(&memory.records().unwrap(), true);
        fixture.read_only(true);
        let failed = memory.remember(
            "Neu",
            &text("Neuer Text"),
            &text("Test"),
            "fact",
            "",
            false,
            "",
            s(&original, "path"),
            s(&original, "hash"),
            "",
        );
        fixture.read_only(false);
        assert!(failed.is_err());
        assert_eq!(python::dumps(&memory.records().unwrap(), true), before);
        assert_eq!(
            note_text(&memory.book.read(s(&original, "path")).unwrap()),
            note_text(&original)
        );
        assert_eq!(
            memory
                .eligible(&fixture.base.to_string_lossy())
                .unwrap()
                .len(),
            1
        );
    });
}

#[test]
fn an_interrupted_migration_keeps_the_scope_and_the_manual_protection() {
    let fixture = Fixture::new("interrupted-migration");
    fixture.with(&plain, |ctx| {
        let memory = Memory::open(&fixture.store, ctx).unwrap();
        memory.configure(true, true, None, None, None).unwrap();
        let note = memory
            .book
            .create("Legacy", "Private project", &text(""), &text(""), ".", "")
            .unwrap();
        let records = dict(vec![(
            s(&note, "path"),
            dict(vec![
                ("scope", text("/project-a")),
                ("automatic", Py::Bool(false)),
                ("hash", or(&note, "hash", Py::None)),
            ]),
        )]);
        fixture
            .store
            .set_setting("memory/records", &records)
            .unwrap();
        fixture.read_only(true);
        assert!(memory.migrate(false).is_err());
        fixture.read_only(false);
        let report = memory.migrate(false).unwrap();
        assert_eq!(get(&report, "changed"), Some(&Py::int(1)));
        assert!(memory.eligible("/project-b").unwrap().is_empty());
        let current = memory.eligible("/project-a").unwrap();
        assert_eq!(current.len(), 1);
        let meta = or(&current[0], "memory", empty());
        assert!(!on(&meta, "automatic"));
        assert_eq!(s(&meta, "scope"), "/project-a");
        assert!(on(&current[0], "note_id"));
    });
}

#[test]
fn an_interrupted_project_copy_is_never_global_or_approved() {
    let fixture = Fixture::new("interrupted-copy");
    let folder = fixture.base.join("project");
    std::fs::create_dir_all(&folder).unwrap();
    let project = "1f0e2d3c-4b5a-4968-8776-655443322110";
    fixture.with(&plain, |ctx| {
        workbench(ctx).unwrap();
        rusqlite::Connection::open(fixture.base.join("tools/workbench/library.sqlite"))
            .unwrap()
            .execute(
                "INSERT INTO records VALUES (?,?,?,?,?)",
                rusqlite::params![project, "Projekt", "{}", 0, 1.0],
            )
            .unwrap();
        let memory = Memory::open(&fixture.store, ctx).unwrap();
        memory.configure(true, false, None, None, None).unwrap();
        let original = memory
            .remember(
                "Persönlich",
                &text("Private Vorliebe"),
                &text("Test"),
                "fact",
                "",
                false,
                "",
                "",
                "",
                "",
            )
            .unwrap();
        fixture.read_only(true);
        let failed = memory.project_configure(
            project,
            &folder.to_string_lossy(),
            &empty(),
            s(&original, "path"),
            s(&original, "hash"),
        );
        fixture.read_only(false);
        assert!(failed.is_err());
        let copy = items(&memory.records().unwrap())
            .iter()
            .find(|(p, _)| p.starts_with("project-"))
            .map(|(_, m)| m.clone())
            .unwrap();
        assert_eq!(get(&copy, "allowed"), Some(&Py::Bool(false)));
        assert!(s(&copy, "scope").starts_with("project:"));
        let ids: Vec<_> = memory
            .eligible(&folder.to_string_lossy())
            .unwrap()
            .iter()
            .map(|n| s(n, "id").to_owned())
            .collect();
        assert_eq!(ids, [s(&original, "id")]);
    });
}

#[test]
fn an_edit_or_a_revocation_during_the_search_is_never_returned_as_current() {
    let fixture = Fixture::new("search-change");
    let directory = fixture.base.to_string_lossy().into_owned();
    let path = RefCell::new(String::new());
    let action = RefCell::new("edit");
    // The search runs under memory-state.lock: the notebook is written as another window writes it.
    let changing = |ctx: &Ctx, _: &[Entry], _: &str, _: &str, _: &Path, _: &str| {
        let place = root(&fixture.store).to_string_lossy().into_owned();
        let book = Notebook::open(&fixture.store, ctx.env, Some(&place), false, None)?;
        let note = book.read(&path.borrow())?;
        match *action.borrow() {
            "edit" => {
                book.write(
                    &path.borrow(),
                    "# Server\nSQLite",
                    s(&note, "hash"),
                    None,
                    None,
                    None,
                    None,
                )?;
            }
            _ => {
                changed(&fixture.store, true)?;
            }
        }
        plain(ctx, &[], "", "", Path::new("/"), "")
    };
    fixture.with(&plain, |ctx| {
        let memory = Memory::open(&fixture.store, ctx).unwrap();
        memory.configure(true, false, None, None, None).unwrap();
        let note = memory
            .remember(
                "Server",
                &text("PostgreSQL"),
                &text("Test"),
                "fact",
                "",
                false,
                "",
                "",
                "",
                "",
            )
            .unwrap();
        *path.borrow_mut() = s(&note, "path").to_owned();
    });
    fixture.with(&changing, |ctx| {
        let result = Memory::open(&fixture.store, ctx)
            .unwrap()
            .prepare("PostgreSQL", &directory)
            .unwrap();
        assert_eq!(
            (
                s(&result, "context"),
                list(&or(&result, "notes", Py::None)).len()
            ),
            ("", 0)
        );
        *action.borrow_mut() = "revoke";
        let result = Memory::open(&fixture.store, ctx)
            .unwrap()
            .prepare("SQLite", &directory)
            .unwrap();
        assert_eq!(s(&result, "context"), "");
        assert_eq!(
            s(&result, "warning"),
            "Das Gedächtnis wurde während der Suche geändert. Bitte erneut fragen."
        );
    });
    fixture.with(&plain, |ctx| {
        let result = Memory::open(&fixture.store, ctx)
            .unwrap()
            .prepare("SQLite", &directory)
            .unwrap();
        let context = s(&result, "context");
        assert!(context.contains("SQLite") && length(context) <= 18000);
        for source in list(&or(&result, "notes", Py::None)) {
            assert!(context.contains(s(source, "id")) && context.contains(s(source, "revision")));
        }
    });
}

#[test]
fn a_turn_gives_up_on_a_memory_that_keeps_changing_and_keeps_its_rows() {
    let fixture = Fixture::new("turn-drift");
    let directory = fixture.base.to_string_lossy().into_owned();
    let searches = RefCell::new(0);
    // Every search sees the memory change: the turn prepares three times, then fails.
    let drifting = |ctx: &Ctx, _: &[Entry], _: &str, _: &str, _: &Path, _: &str| {
        *searches.borrow_mut() += 1;
        changed(&fixture.store, true)?;
        plain(ctx, &[], "", "", Path::new("/"), "")
    };
    fixture.with(&plain, |ctx| {
        let memory = Memory::open(&fixture.store, ctx).unwrap();
        memory.configure(true, false, None, None, None).unwrap();
        memory
            .remember(
                "Stil",
                &text("Kurze Antworten"),
                &text("Test"),
                "preference",
                "",
                false,
                "",
                "",
                "",
                "",
            )
            .unwrap();
    });
    let notices = RefCell::new(Vec::new());
    let notify = |_: &Py, _: &str, notice: Option<String>| notices.borrow_mut().push(notice);
    fixture.with(&drifting, |ctx| {
        let failed = for_turn(&fixture.store, ctx, "", "Antworten", &directory, &notify);
        assert!(matches!(failed, Err(Failure::Refused(text)) if text.starts_with("Das Gedächtnis konnte nicht konsistent")));
    });
    assert_eq!(*searches.borrow(), 3);
    assert_eq!(notices.borrow().len(), 3);
    // A calm memory: the context, its rows; a session whose row names another stamp begins anew.
    fixture.with(&plain, |ctx| {
        let memory = for_turn(&fixture.store, ctx, "", "Antworten", &directory, &notify).unwrap();
        assert!(
            memory.block.contains("<lumen-memory>") && memory.block.contains("Kurze Antworten")
        );
        assert!(!memory.renew && memory.enabled);
        assert_eq!(get(&memory.row, "notes"), Some(&Py::List(Vec::new())));
        let stale = dict(vec![
            ("local", Py::List(vec![Py::Bool(true)])),
            ("account", text("")),
            ("notes", Py::List(Vec::new())),
        ]);
        fixture
            .store
            .set_setting("memory/session/ses_old", &stale)
            .unwrap();
        assert!(
            for_turn(
                &fixture.store,
                ctx,
                "ses_old",
                "Antworten",
                &directory,
                &notify
            )
            .unwrap()
            .renew
        );
        fixture
            .store
            .set_setting("memory/session/ses_same", &memory.row)
            .unwrap();
        assert!(
            !for_turn(
                &fixture.store,
                ctx,
                "ses_same",
                "Antworten",
                &directory,
                &notify
            )
            .unwrap()
            .renew
        );
    });
}

#[test]
fn a_conversation_survives_other_server_notes_but_not_changed_ones() {
    // The cases of the earlier files/test_session_memory.py.
    let row = |notes: &[(&str, i64)], account: &str, local: i64| {
        dict(vec![
            (
                "local",
                Py::List(vec![Py::Bool(true), Py::int(local), text("x")]),
            ),
            ("account", text(account)),
            (
                "notes",
                Py::List(
                    notes
                        .iter()
                        .map(|(id, r)| {
                            dict(vec![("remote_id", text(id)), ("revision", Py::int(*r))])
                        })
                        .collect(),
                ),
            ),
        ])
    };
    let saved = row(&[("n1", 3), ("n2", 1)], "a1", 1);
    for following in [&[][..], &[("n3", 7)], &[("n1", 3)], &[("n2", 1), ("n4", 2)]] {
        assert!(!session_memory_changed(&saved, &row(following, "a1", 1)));
    }
    let saved = row(&[("n1", 3)], "a1", 1);
    assert!(session_memory_changed(&saved, &row(&[("n1", 4)], "a1", 1)));
    assert!(session_memory_changed(&saved, &row(&[], "a2", 1)));
    assert!(session_memory_changed(&saved, &row(&[], "a1", 2)));
    let older = Py::List(vec![Py::Bool(true), Py::int(1), text("x")]);
    assert!(session_memory_changed(&older, &row(&[], "a1", 1)));
    let merged = session_notes(
        Some(&row(&[("n1", 3), ("n2", 1)], "a1", 1)),
        &row(&[("n2", 1), ("n3", 5)], "a1", 1),
    );
    let revisions: Vec<_> = list(&merged)
        .iter()
        .map(|n| (s(n, "remote_id").to_owned(), or(n, "revision", Py::None)))
        .collect();
    assert_eq!(
        revisions,
        [
            ("n1".into(), Py::int(3)),
            ("n2".into(), Py::int(1)),
            ("n3".into(), Py::int(5))
        ]
    );
    let mut current = row(&[], "a1", 1);
    current.set("notes", merged);
    assert!(session_memory_changed(
        &current,
        &row(&[("n1", 9)], "a1", 1)
    ));
}

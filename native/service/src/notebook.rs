//! Lumen Notes' notebook core, the one implementation of the earlier `files/wissen_data.py`: a
//! folder of portable Markdown notes, opened by its path and checked against its identity on every
//! access, private history and drafts in the Lumen state folder (`lumen.sqlite3` beside it holds
//! the notebook's settings rows), and the `notes.*` requests of the Qt side's binding
//! (`files/wissen_data.py`). Files are read and written byte for byte as the Python code did: the
//! same header, JSON spelling, locks, modes, temporary names, syncs and refusals.
mod edit;
pub(crate) mod python;
mod text;
mod yaml;

pub use python::Py;
pub use text::{Note, digest, excerpt, parse};

use base64::Engine;
use rustix::fs::{AtFlags, FileType, Mode, OFlags};
use serde_json::Value;
use std::fs::File;
use std::io::{Read, Write};
use std::os::fd::{AsFd, OwnedFd};
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use text::MAX_NOTE;

use crate::texts::Texts;

pub const MAX_SCAN_BYTES: usize = 128 * 1024 * 1024;
pub const MAX_SCAN_NOTES: usize = 10000;
pub const MAX_SCAN_ENTRIES: usize = 30000;
const MAX_IMAGE: usize = 16 * 1024 * 1024;
/// An attachment the binding has made a PNG of (at most 2400 × 2400 pixels).
const MAX_ATTACHMENT: usize = 64 * 1024 * 1024;

/// Why an operation was refused, as the Python exception it replaces.
#[derive(Debug, PartialEq)]
pub enum Failure {
    /// `ValueError` with a German source text the answer translates.
    Refused(&'static str),
    /// `ValueError` (or another error) with a text that stays as it is.
    Value(String),
    /// `OSError(errno, strerror, filename)`; `path` when Python named the file by a `Path`.
    Os {
        errno: i32,
        filename: Option<String>,
        path: bool,
    },
    /// `UnicodeDecodeError`.
    Unicode(String),
}

pub(crate) type Result<T> = std::result::Result<T, Failure>;

/// The German text marks the message for `files/translations/en` (`test_i18n.py` reads them).
fn tr(text: &'static str) -> Failure {
    Failure::Refused(text)
}

fn os(error: rustix::io::Errno, filename: &str) -> Failure {
    Failure::Os {
        errno: error.raw_os_error(),
        filename: Some(filename.to_owned()),
        path: false,
    }
}

fn io(error: std::io::Error, filename: &str, path: bool) -> Failure {
    match error.raw_os_error() {
        Some(errno) => Failure::Os {
            errno,
            filename: Some(filename.to_owned()),
            path,
        },
        None => Failure::Value(error.to_string()),
    }
}

fn not_found(failure: &Failure) -> bool {
    matches!(failure, Failure::Os { errno, .. } if *errno == libc::ENOENT)
}

/// The clock and the random identifiers; the tests replay Python's with fixed ones.
pub struct Env {
    pub now: Box<dyn Fn() -> f64 + Send>,
    pub random: Box<dyn Fn() -> [u8; 16] + Send>,
}

impl Default for Env {
    fn default() -> Self {
        Env {
            // time.time(): nanoseconds as a float, divided by 1e9.
            now: Box::new(|| {
                let ns = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_nanos())
                    .unwrap_or(0);
                if ns.is_multiple_of(1_000_000_000) {
                    (ns / 1_000_000_000) as f64
                } else {
                    ns as f64 / 1e9
                }
            }),
            random: Box::new(|| {
                let mut bytes = [0; 16];
                File::open("/dev/urandom")
                    .and_then(|mut f| f.read_exact(&mut bytes))
                    .expect("random bytes");
                bytes
            }),
        }
    }
}

impl Env {
    /// `uuid.uuid4().hex`.
    pub(crate) fn uuid4(&self) -> String {
        let mut bytes = (self.random)();
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }
}

/// `lumen_store.Store`: the state folder and its `settings` rows (JSON as `json.dumps` wrote them).
pub struct Store {
    pub directory: PathBuf,
}

impl Store {
    fn connect(&self) -> Result<rusqlite::Connection> {
        let path = self.directory.join("lumen.sqlite3");
        let db = rusqlite::Connection::open_with_flags(
            &path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_WRITE,
        )
        .map_err(|e| Failure::Value(e.to_string()))?;
        db.busy_timeout(std::time::Duration::from_secs(15))
            .map_err(|e| Failure::Value(e.to_string()))?;
        Ok(db)
    }
    pub fn setting(&self, key: &str) -> Result<Option<Py>> {
        let db = self.connect()?;
        let value: Option<String> = db
            .query_row("SELECT value FROM settings WHERE key=?", [key], |row| {
                row.get(0)
            })
            .map(Some)
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                e => Err(Failure::Value(e.to_string())),
            })?;
        value
            .map(|v| python::loads(&v).ok_or_else(|| Failure::Value("invalid setting".into())))
            .transpose()
    }
    pub fn set_setting(&self, key: &str, value: &Py) -> Result<()> {
        self.connect()?
            .execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)",
                [key, &python::dumps(value, true)],
            )
            .map(|_| ())
            .map_err(|e| Failure::Value(e.to_string()))
    }
    /// `SELECT * FROM memories ORDER BY updated` as dicts.
    fn memories(&self) -> Result<Vec<Py>> {
        let db = self.connect()?;
        let mut query = db
            .prepare("SELECT * FROM memories ORDER BY updated")
            .map_err(|e| Failure::Value(e.to_string()))?;
        let names: Vec<String> = query.column_names().map(|n| n.to_string()).collect();
        let rows = query
            .query_map([], |row| {
                (0..names.len())
                    .map(|i| {
                        use rusqlite::types::ValueRef;
                        Ok((
                            names[i].clone(),
                            match row.get_ref(i)? {
                                ValueRef::Null => Py::None,
                                ValueRef::Integer(v) => Py::int(v),
                                ValueRef::Real(v) => Py::Float(v),
                                ValueRef::Text(v) => {
                                    Py::Str(String::from_utf8_lossy(v).into_owned())
                                }
                                // json.dumps refuses bytes when it reaches this row; a list marks it.
                                ValueRef::Blob(_) => Py::List(Vec::new()),
                            },
                        ))
                    })
                    .collect::<rusqlite::Result<Vec<_>>>()
                    .map(Py::Dict)
            })
            .map_err(|e| Failure::Value(e.to_string()))?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|e| Failure::Value(e.to_string()))
    }
}

/// A relative note path as `Notebook.relative` admitted it.
struct NotePath {
    /// `str(Path(path))`.
    normalized: String,
    parent: String,
    name: String,
}

/// `Path(path)`'s parts of a relative path.
fn parts(path: &str) -> Vec<&str> {
    path.split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect()
}

fn split(path: &str) -> NotePath {
    let parts = parts(path);
    let (name, parent) = parts.split_last().map_or(("", &[][..]), |(n, p)| (*n, p));
    NotePath {
        normalized: if parts.is_empty() {
            ".".into()
        } else {
            parts.join("/")
        },
        parent: if parent.is_empty() {
            ".".into()
        } else {
            parent.join("/")
        },
        name: name.to_owned(),
    }
}

fn relative(path: &str) -> Result<NotePath> {
    let parts = parts(path);
    if path.starts_with('/')
        || parts.contains(&"..")
        || parts.is_empty()
        || parts.iter().any(|p| p.starts_with('.'))
        || text::suffix(path).to_lowercase() != ".md"
    {
        return Err(tr(
            "Bitte eine Markdown-Notiz innerhalb des gewählten Ordners wählen.",
        ));
    }
    Ok(split(path))
}

fn nul_free(name: &str) -> Result<&str> {
    if name.contains('\0') {
        return Err(Failure::Value("embedded null byte".into()));
    }
    Ok(name)
}

fn open_dir(at: &impl AsFd, name: &str) -> Result<OwnedFd> {
    rustix::fs::openat(
        at,
        nul_free(name)?,
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(|e| os(e, name))
}

/// `directory_identity`: the file system's ID survives a remount, `st_dev` is a number of this boot.
fn directory_identity(fd: &impl AsFd) -> Result<Py> {
    let stat = rustix::fs::fstat(fd).map_err(|e| os(e, "."))?;
    let fsid = rustix::fs::fstatvfs(fd).map_err(|e| os(e, "."))?.f_fsid;
    Ok(Py::List(if fsid != 0 {
        vec![
            Py::Str(format!("fsid:{fsid}")),
            Py::Int(stat.st_ino.to_string()),
        ]
    } else {
        vec![
            Py::Int(stat.st_dev.to_string()),
            Py::Int(stat.st_ino.to_string()),
        ]
    }))
}

fn root_identity(root: &Path) -> Result<Py> {
    let name = root
        .to_str()
        .ok_or(Failure::Value("root is no text".into()))?;
    let fd = rustix::fs::open(
        nul_free(name)?,
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(|e| Failure::Os {
        errno: e.raw_os_error(),
        filename: Some(name.into()),
        path: true,
    })?;
    directory_identity(&fd)
}

/// `st_mtime`: seconds and nanoseconds as Python adds them.
fn mtime(stat: &rustix::fs::Stat) -> f64 {
    stat.st_mtime as f64 + stat.st_mtime_nsec as f64 * 1e-9
}

/// `pathlib.Path.mkdir(parents=True, exist_ok=True, mode=…)`: parents get the default mode.
pub(crate) fn make_dirs(path: &Path, mode: u32) -> std::io::Result<()> {
    match std::fs::DirBuilder::new().mode(mode).create(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound && path.parent().is_some() => {
            make_dirs(path.parent().unwrap(), 0o777)?;
            make_dirs(path, mode)
        }
        Err(e) if path.is_dir() => {
            let _ = e;
            Ok(())
        }
        Err(e) => Err(e),
    }
}

pub struct Notebook<'a> {
    pub store: &'a Store,
    pub root: PathBuf,
    pub identity: Py,
    env: &'a Env,
}

/// A held `flock` on a file in the state folder, released when dropped.
pub(crate) struct Lock(#[allow(dead_code)] OwnedFd);

impl<'a> Notebook<'a> {
    /// `Notebook(store, root, create, identity)`; `root` is absolute (the binding expanded it).
    pub fn open(
        store: &'a Store,
        env: &'a Env,
        root: Option<&str>,
        create: bool,
        identity: Option<Py>,
    ) -> Result<Self> {
        let chosen = match root.filter(|r| !r.is_empty()) {
            Some(root) => Py::str(root),
            None => store.setting("knowledge/notebook")?.unwrap_or(Py::str("")),
        };
        if !chosen.truthy() {
            return Err(tr(
                "Lumen Notes zuerst öffnen und einen Notizordner wählen.",
            ));
        }
        let chosen = PathBuf::from(python::py_str(&chosen));
        if create {
            make_dirs(&chosen, 0o700).map_err(|e| io(e, &chosen.to_string_lossy(), true))?;
        }
        let root =
            std::fs::canonicalize(&chosen).map_err(|e| io(e, &chosen.to_string_lossy(), false))?;
        let root_text = root.to_string_lossy().into_owned();
        let identity = match identity.filter(Py::truthy) {
            Some(identity) => identity,
            None => {
                let stored = if store.setting("knowledge/notebook")? == Some(Py::str(&root_text)) {
                    store.setting("knowledge/identity")?.filter(Py::truthy)
                } else {
                    None
                };
                match stored {
                    Some(identity) => identity,
                    None => root_identity(&root)?,
                }
            }
        };
        let book = Notebook {
            store,
            root,
            identity,
            env,
        };
        // Python made the history (`Library('wissen-history', …)`) with every notebook it opened.
        book.history()?;
        Ok(book)
    }

    pub(crate) fn root_text(&self) -> String {
        self.root.to_string_lossy().into_owned()
    }

    /// `Notebook.directory`: the folder below the root, opened component by component without
    /// following links, after checking the root is still the chosen folder.
    fn directory(&self, relative: &str) -> Result<OwnedFd> {
        let name = self.root_text();
        let fd = rustix::fs::open(
            nul_free(&name)?,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(|e| Failure::Os {
            errno: e.raw_os_error(),
            filename: Some(name.clone()),
            path: true,
        })?;
        let fsid =
            matches!(&self.identity, Py::List(items) if matches!(items.first(), Some(Py::Str(_))));
        let actual = if fsid {
            directory_identity(&fd)?
        } else {
            let stat = rustix::fs::fstat(&fd).map_err(|e| os(e, &name))?;
            Py::List(vec![
                Py::Int(stat.st_dev.to_string()),
                Py::Int(stat.st_ino.to_string()),
            ])
        };
        if actual != self.identity {
            return Err(tr(
                "Der Notizordner wurde ersetzt oder getrennt. Erneut auswählen.",
            ));
        }
        if relative.starts_with('/') || parts(relative).contains(&"..") {
            return Err(tr("Pfad außerhalb des Notizordners."));
        }
        let mut current = fd;
        for part in parts(relative) {
            current = open_dir(&current, part)?;
        }
        Ok(current)
    }

    pub(crate) fn lock(&self, name: &str) -> Result<Lock> {
        let path = self.store.directory.join(name);
        let fd = rustix::fs::open(
            &path,
            OFlags::RDWR | OFlags::CREATE | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )
        .map_err(|e| Failure::Os {
            errno: e.raw_os_error(),
            filename: Some(path.to_string_lossy().into()),
            path: true,
        })?;
        rustix::fs::flock(&fd, rustix::fs::FlockOperation::LockExclusive)
            .map_err(|e| os(e, name))?;
        Ok(Lock(fd))
    }

    /// `_read`: the bytes of a regular note of at most 1 MiB and its modification time.
    fn read_raw(&self, path: &str) -> Result<(Vec<u8>, f64)> {
        let path = relative(path)?;
        let parent = self.directory(&path.parent)?;
        let fd = rustix::fs::openat(
            &parent,
            nul_free(&path.name)?,
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(|e| os(e, &path.name))?;
        let stat = rustix::fs::fstat(&fd).map_err(|e| os(e, &path.name))?;
        if FileType::from_raw_mode(stat.st_mode) != FileType::RegularFile {
            return Err(tr("Keine reguläre Notizdatei."));
        }
        let mut raw = Vec::new();
        File::from(fd.try_clone().map_err(|e| io(e, &path.name, false))?)
            .take(MAX_NOTE as u64 + 1)
            .read_to_end(&mut raw)
            .map_err(|e| io(e, &path.name, false))?;
        if raw.len() > MAX_NOTE {
            return Err(tr("Notiz größer als 1 MiB."));
        }
        let stat = rustix::fs::fstat(&fd).map_err(|e| os(e, &path.name))?;
        Ok((raw, mtime(&stat)))
    }

    pub fn raw(&self, path: &str) -> Result<Vec<u8>> {
        Ok(self.read_raw(path)?.0)
    }

    fn parsed(path: &str, raw: &[u8], modified: f64) -> Result<Py> {
        let mut note = parse(path, raw).map_err(|e| Failure::Unicode(e.0))?.to_py();
        note.set("modified", Py::Float(modified));
        Ok(note)
    }

    pub fn read(&self, path: &str) -> Result<Py> {
        let (raw, modified) = self.read_raw(path)?;
        Self::parsed(path, &raw, modified)
    }

    /// The private history (`tools_data.Library('wissen-history', store)`), created as it did.
    fn history(&self) -> Result<(PathBuf, rusqlite::Connection)> {
        let root = self.store.directory.join("wissen-history");
        make_dirs(&root, 0o700).map_err(|e| io(e, &root.to_string_lossy(), true))?;
        let assets = root.join("assets");
        make_dirs(&assets, 0o700).map_err(|e| io(e, &assets.to_string_lossy(), true))?;
        let path = root.join("library.sqlite");
        let db = rusqlite::Connection::open(&path).map_err(|e| Failure::Value(e.to_string()))?;
        db.busy_timeout(std::time::Duration::from_secs(10))
            .map_err(|e| Failure::Value(e.to_string()))?;
        db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, title TEXT NOT NULL, data TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL)", [])
            .map_err(|e| Failure::Value(e.to_string()))?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))
            .map_err(|e| io(e, &path.to_string_lossy(), true))?;
        Ok((assets, db))
    }

    /// `Library.asset`: a plain file name in the assets folder.
    fn asset(assets: &Path, name: &str) -> Result<PathBuf> {
        if name.is_empty() || text::name(name) != name {
            return Err(tr("Ungültige lokale Datei."));
        }
        Ok(assets.join(name))
    }

    /// `backup`: the earlier bytes as a private history entry; its key.
    fn backup(&self, path: &str, raw: &[u8]) -> Result<String> {
        let (assets, db) = self.history()?;
        let asset = format!("{}.md", self.env.uuid4());
        let target = Self::asset(&assets, &asset)?;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
            .map_err(|e| io(e, &target.to_string_lossy(), true))?;
        std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o600))
            .map_err(|e| io(e, &target.to_string_lossy(), true))?;
        file.write_all(raw)
            .map_err(|e| io(e, &target.to_string_lossy(), true))?;
        drop(file);
        let created = (self.env.now)();
        let title = text::name(path).trim_matches(python::whitespace).to_owned();
        if title.is_empty() {
            return Err(tr("Bitte einen Namen angeben."));
        }
        let data = Py::Dict(vec![
            ("root".into(), Py::str(&self.root_text())),
            ("path".into(), Py::str(path)),
            ("asset".into(), Py::str(&asset)),
            ("created".into(), Py::Float(created)),
        ]);
        let key = self.env.uuid4();
        db.execute(
            "INSERT INTO records VALUES (?,?,?,?,?)",
            rusqlite::params![key, title, python::dumps(&data, true), 0, (self.env.now)()],
        )
        .map_err(|e| Failure::Value(e.to_string()))?;
        Ok(key)
    }

    /// `write`: the new text under the path's lock, refused when the file is no longer at
    /// `expected`, the earlier bytes kept in the history, a synced temporary file renamed over it.
    #[allow(clippy::too_many_arguments)] // Python's `write` signature.
    pub fn write(
        &self,
        path: &str,
        text: &str,
        expected: &str,
        source: Option<Py>,
        legacy: Option<Py>,
        created: Option<Py>,
        note_id: Option<String>,
    ) -> Result<Py> {
        let path = relative(path)?;
        let _lock = self.lock("wissen.lock")?;
        let (before, mut modified) = match self.read_raw(&path.normalized) {
            Ok((raw, modified)) => (Some(raw), modified),
            Err(e) if not_found(&e) => (None, 0.0),
            Err(e) => return Err(e),
        };
        if before.as_deref().map(digest).unwrap_or_default() != expected {
            return Err(tr(
                "CONFLICT: Die Datei wurde außerhalb dieses Fensters geändert. Entwurf bleibt erhalten.",
            ));
        }
        let old = match &before {
            Some(raw) => Some(parse(&path.normalized, raw).map_err(|e| Failure::Unicode(e.0))?),
            None => None,
        };
        let created_at = match &old {
            None => created.unwrap_or_else(|| Py::Float((self.env.now)())),
            Some(old) if old.created.truthy() => old.created.clone(),
            Some(_) => text::timestamp(&created.unwrap_or(Py::None)),
        };
        let source =
            source.unwrap_or_else(|| Py::str(old.as_ref().map_or("", |o| o.source.as_str())));
        let legacy =
            legacy.unwrap_or_else(|| Py::str(old.as_ref().map_or("", |o| o.legacy.as_str())));
        let note_id =
            note_id.unwrap_or_else(|| old.as_ref().map_or(String::new(), |o| o.note_id.clone()));
        let raw =
            text::encode(text, &source, &legacy, &created_at, &note_id).map_err(|e| match e {
                text::EncodeError::Uuid => {
                    Failure::Value("badly formed hexadecimal UUID string".into())
                }
                text::EncodeError::Large => tr("Notiz größer als 1 MiB. Bitte aufteilen."),
            })?;
        if before.as_deref() == Some(&raw[..]) {
            return Self::parsed(&path.normalized, &raw, modified);
        }
        if let Some(before) = &before {
            self.backup(&path.normalized, before)?;
        }
        let parent = self.directory(&path.parent)?;
        let temporary = format!(".lumen-{}", self.env.uuid4());
        let fd = rustix::fs::openat(
            &parent,
            temporary.as_str(),
            OFlags::CREATE | OFlags::EXCL | OFlags::WRONLY | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )
        .map_err(|e| os(e, &temporary))?;
        let outcome = (|| {
            let mut file = File::from(fd);
            file.write_all(&raw).map_err(|e| io(e, &temporary, false))?;
            file.sync_all().map_err(|e| io(e, &temporary, false))?;
            modified = mtime(&rustix::fs::fstat(&file).map_err(|e| os(e, &temporary))?);
            drop(file);
            let latest = match self.raw(&path.normalized) {
                Ok(raw) => Some(raw),
                Err(e) if not_found(&e) => None,
                Err(e) => return Err(e),
            };
            if latest != before {
                return Err(tr(
                    "CONFLICT: Die Datei wurde während des Speicherns geändert.",
                ));
            }
            rustix::fs::renameat(&parent, temporary.as_str(), &parent, path.name.as_str())
                .map_err(|e| os(e, &temporary))?;
            rustix::fs::fsync(&parent).map_err(|e| os(e, &path.parent))
        })();
        match rustix::fs::unlinkat(&parent, temporary.as_str(), AtFlags::empty()) {
            Err(e) if e != rustix::io::Errno::NOENT && outcome.is_ok() => {
                return Err(os(e, &temporary));
            }
            _ => {}
        }
        outcome?;
        Self::parsed(&path.normalized, &raw, modified)
    }

    /// `create`: a new note named after its title in `folder`.
    pub fn create(
        &self,
        title: &str,
        body: &str,
        source: &Py,
        legacy: &Py,
        folder: &str,
        note_id: &str,
    ) -> Result<Py> {
        let title = text::clean_title(title);
        if title.is_empty() {
            return Err(tr("Bitte einen Titel eingeben."));
        }
        let name = format!("{}-{}.md", text::file_stem(&title), &self.env.uuid4()[..8]);
        // `str(Path(folder) / name)`: an absolute folder stays absolute, and `write` refuses it.
        let path = format!(
            "{}{}",
            if folder.starts_with('/') { "/" } else { "" },
            split(&format!("{folder}/{name}")).normalized
        );
        self.write(
            &path,
            &format!("# {title}\n\n{body}"),
            "",
            Some(source.clone()),
            Some(legacy.clone()),
            None,
            Some(note_id.to_owned()),
        )
    }

    pub fn create_collection(&self, name: &str) -> Result<String> {
        let name = name.trim_matches(python::whitespace);
        if name.is_empty()
            || name.starts_with('.')
            || name
                .chars()
                .any(|c| matches!(c, '/' | '\\' | '\0'..='\u{1f}' | '\u{7f}'))
            || name.len() > 200
            || name == "attachments"
        {
            return Err(tr(
                "Bitte einen Sammlungsnamen ohne Schrägstriche eingeben (nicht versteckt oder „attachments“).",
            ));
        }
        let _lock = self.lock("wissen.lock")?;
        let parent = self.directory(".")?;
        rustix::fs::mkdirat(&parent, name, Mode::from_raw_mode(0o700)).map_err(|e| os(e, name))?;
        rustix::fs::fsync(&parent).map_err(|e| os(e, "."))?;
        Ok(name.to_owned())
    }

    /// `remove`: the note goes to the history, then from the folder.
    pub fn remove(&self, path: &str, expected: &str) -> Result<String> {
        let _lock = self.lock("wissen.lock")?;
        let raw = self.raw(path)?;
        if digest(&raw) != expected {
            return Err(tr(
                "CONFLICT: Die Notiz wurde geändert. Neu laden, bevor sie entfernt wird.",
            ));
        }
        let key = self.backup(path, &raw)?;
        let path = relative(path)?;
        let parent = self.directory(&path.parent)?;
        rustix::fs::unlinkat(&parent, path.name.as_str(), AtFlags::empty())
            .map_err(|e| os(e, &path.name))?;
        Ok(key)
    }

    /// `history.get(key)`: the path and asset of a history entry, of any folder.
    pub(crate) fn history_entry(&self, key: &str) -> Result<(String, String)> {
        let (_, db) = self.history()?;
        let data: Option<String> = db
            .query_row("SELECT data FROM records WHERE id=?", [key], |row| {
                row.get(0)
            })
            .map(Some)
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                e => Err(Failure::Value(e.to_string())),
            })?;
        let row = data
            .ok_or(tr("Dieser Eintrag ist nicht mehr vorhanden."))
            .and_then(|d| {
                python::loads(&d).ok_or(Failure::Value("invalid history record".into()))
            })?;
        let field = |key: &str| {
            row.get(key)
                .map(python::py_str)
                .ok_or_else(|| Failure::Value(format!("'{key}'")))
        };
        Ok((field("path")?, field("asset")?))
    }

    /// `history.asset(name)`: the file of a history entry.
    pub(crate) fn history_asset(&self, name: &str) -> Result<PathBuf> {
        let (assets, _) = self.history()?;
        Self::asset(&assets, name)
    }

    /// Removes a history entry's row (`DELETE FROM records WHERE id=?`).
    pub(crate) fn history_delete(&self, id: &str) -> Result<()> {
        let (_, db) = self.history()?;
        db.execute("DELETE FROM records WHERE id=?", [id])
            .map(|_| ())
            .map_err(|e| Failure::Value(e.to_string()))
    }

    /// `Library.all()` (newest first) of this folder, of one path when given.
    pub fn versions(&self, path: Option<&str>) -> Result<Vec<Py>> {
        let (_, db) = self.history()?;
        let mut query = db
            .prepare("SELECT id, title, data FROM records WHERE archived=? ORDER BY updated DESC")
            .map_err(|e| Failure::Value(e.to_string()))?;
        let rows: Vec<(String, String, String)> = query
            .query_map([0], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
            .and_then(|rows| rows.collect())
            .map_err(|e| Failure::Value(e.to_string()))?;
        let root = Py::str(&self.root_text());
        let mut result = Vec::new();
        for (id, title, data) in rows {
            let Some(Py::Dict(data)) = python::loads(&data) else {
                return Err(Failure::Value("invalid history record".into()));
            };
            let mut record = vec![
                ("id".to_owned(), Py::Str(id)),
                ("title".to_owned(), Py::Str(title)),
            ];
            record.extend(data);
            let record = Py::Dict(record);
            if record.get("root") == Some(&root)
                && path.is_none_or(|p| record.get("path") == Some(&Py::str(p)))
            {
                result.push(record);
            }
        }
        Ok(result)
    }

    pub fn restore(&self, key: &str, expected: &str) -> Result<Py> {
        let (assets, db) = self.history()?;
        let data: Option<String> = db
            .query_row("SELECT data FROM records WHERE id=?", [key], |row| {
                row.get(0)
            })
            .map(Some)
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                e => Err(Failure::Value(e.to_string())),
            })?;
        let row = data
            .and_then(|d| python::loads(&d))
            .ok_or(tr("Dieser Eintrag ist nicht mehr vorhanden."))?;
        if row.get("root") != Some(&Py::str(&self.root_text())) {
            return Err(tr("Die Sicherung gehört zu einem anderen Ordner."));
        }
        let path = row
            .get("path")
            .and_then(Py::as_str)
            .unwrap_or_default()
            .to_owned();
        let asset = Self::asset(
            &assets,
            row.get("asset").and_then(Py::as_str).unwrap_or_default(),
        )?;
        let raw = std::fs::read(&asset).map_err(|e| io(e, &asset.to_string_lossy(), true))?;
        let note = parse(&path, &raw).map_err(|e| Failure::Unicode(e.0))?;
        let note_id = (!note.note_id.is_empty()).then(|| note.note_id.clone());
        self.write(
            &path,
            &note.text,
            expected,
            Some(Py::Str(note.source)),
            Some(Py::Str(note.legacy)),
            Some(note.created),
            note_id,
        )
    }

    pub fn memory_path(&self, memory: &str) -> Result<String> {
        if memory.ends_with(".md") {
            return Ok(memory.to_owned());
        }
        let imports = self
            .store
            .setting("knowledge/imports")?
            .unwrap_or(Py::Dict(Vec::new()));
        let imported = imports.get(memory).cloned().unwrap_or(Py::Dict(Vec::new()));
        if imported.get("root") != Some(&Py::str(&self.root_text())) {
            return Err(tr("Die alte Erinnerung zuerst im Lumen-Gedächtnis öffnen."));
        }
        imported
            .get("path")
            .map(python::py_str)
            .ok_or(Failure::Value("'path'".into()))
    }

    pub fn capture(
        &self,
        title: &str,
        text: &str,
        source: &Py,
        memory: Option<&str>,
    ) -> Result<String> {
        let Some(memory) = memory.filter(|m| !m.is_empty()) else {
            return Ok(path_of(&self.create(
                title,
                text,
                source,
                &Py::str(""),
                ".",
                "",
            )?));
        };
        let memory = self.memory_path(memory)?;
        let note = self.read(&memory)?;
        let hash = note
            .get("hash")
            .and_then(Py::as_str)
            .unwrap_or_default()
            .to_owned();
        let body = format!("# {}\n\n{text}", title.trim_matches(python::whitespace));
        Ok(path_of(&self.write(
            &memory,
            &body,
            &hash,
            Some(source.clone()),
            None,
            None,
            None,
        )?))
    }

    /// `migrate`: memories of the Store's old table become notes once (`knowledge/imports`).
    pub fn migrate(&self) -> Result<usize> {
        let _lock = self.lock("wissen-import.lock")?;
        let mut imported = self
            .store
            .setting("knowledge/imports")?
            .unwrap_or(Py::Dict(Vec::new()));
        let mut changed = 0;
        let mut existing: Option<Vec<(String, String)>> = None;
        for row in self.store.memories()? {
            let Py::Dict(items) = &row else { continue };
            if items.iter().any(|(_, v)| matches!(v, Py::List(_))) {
                return Err(Failure::Value(
                    "Object of type bytes is not JSON serializable".into(),
                ));
            }
            let mut sorted = items.clone();
            sorted.sort_by(|a, b| a.0.cmp(&b.0));
            let version = digest(python::dumps(&Py::Dict(sorted), true).as_bytes());
            let id = row.get("id").map(python::py_str).unwrap_or_default();
            let old = imported.get(&id).cloned().unwrap_or(Py::Dict(Vec::new()));
            if old.get("version") == Some(&Py::str(&version)) {
                continue;
            }
            // Never overwrite a Markdown edit with a late legacy-window update.
            let token = format!("{id}@{version}");
            if existing.is_none() {
                existing = Some(
                    self.scan(&Limits::default())?
                        .notes
                        .iter()
                        .filter_map(|n| {
                            let legacy = n.get("legacy").and_then(Py::as_str)?;
                            (!legacy.is_empty()).then(|| (legacy.to_owned(), path_of(n)))
                        })
                        .collect(),
                );
            }
            let found = existing
                .as_ref()
                .and_then(|e| e.iter().rev().find(|(l, _)| *l == token))
                .map(|(_, p)| p.clone());
            let path = match found {
                Some(path) => path,
                None => {
                    let field = |key| row.get(key).cloned().unwrap_or(Py::str(""));
                    let title = python::py_str(&field("title"));
                    let body = python::py_str(&field("text"));
                    path_of(&self.create(
                        &title,
                        &body,
                        &field("source"),
                        &Py::Str(token),
                        ".",
                        "",
                    )?)
                }
            };
            imported.set(
                &id,
                Py::Dict(vec![
                    ("version".into(), Py::Str(version)),
                    ("path".into(), Py::Str(path)),
                    ("root".into(), Py::str(&self.root_text())),
                ]),
            );
            self.store.set_setting("knowledge/imports", &imported)?;
            changed += 1;
        }
        Ok(changed)
    }

    /// `_scan`: the notes below the root, depth first as Python's list and `os.scandir` gave them.
    pub fn scan(&self, limits: &Limits) -> Result<Scan> {
        let mut scan = Scan {
            notes: Vec::new(),
            folders: Vec::new(),
            errors: 0,
            limited: false,
        };
        let mut queue = vec![".".to_owned()];
        let (mut count, mut size) = (0, 0);
        while let Some(relative) = queue.pop() {
            if scan.limited {
                break;
            }
            let parent = self.directory(&relative)?;
            let mut entries = rustix::fs::Dir::read_from(&parent).map_err(|e| os(e, &relative))?;
            for entry in entries.by_ref() {
                let entry = entry.map_err(|e| os(e, &relative))?;
                let bytes = entry.file_name().to_bytes();
                if bytes == b"." || bytes == b".." {
                    continue;
                }
                count += 1;
                if count > limits.entries {
                    scan.limited = true;
                    break;
                }
                let Ok(name) = std::str::from_utf8(bytes) else {
                    // Python kept such names as surrogate escapes; the service cannot.
                    scan.errors += usize::from(bytes.to_ascii_lowercase().ends_with(b".md"));
                    continue;
                };
                let mut kind = entry.file_type();
                if kind == FileType::Unknown {
                    match rustix::fs::statat(&parent, name, AtFlags::SYMLINK_NOFOLLOW) {
                        Ok(stat) => kind = FileType::from_raw_mode(stat.st_mode),
                        Err(_) => continue,
                    }
                }
                if name.starts_with('.') || kind == FileType::Symlink {
                    continue;
                }
                let path = if relative == "." {
                    name.to_owned()
                } else {
                    format!("{relative}/{name}")
                };
                if kind == FileType::Directory {
                    queue.push(path.clone());
                    if parts(&path)[0] != "attachments" {
                        scan.folders.push(path);
                    }
                } else if name.to_lowercase().ends_with(".md") && kind == FileType::RegularFile {
                    let read = (|| {
                        let length = rustix::fs::statat(&parent, name, AtFlags::SYMLINK_NOFOLLOW)
                            .map_err(|e| os(e, name))?
                            .st_size as usize;
                        if length > MAX_NOTE {
                            return Ok(None);
                        }
                        if scan.notes.len() >= limits.notes || size + length > limits.bytes {
                            return Ok(Some(None));
                        }
                        let (raw, modified) = self.read_raw(&path)?;
                        Ok::<_, Failure>(Some(Some((
                            Self::parsed(&path, &raw, modified)?,
                            raw.len(),
                        ))))
                    })();
                    match read {
                        Ok(None) | Err(_) => scan.errors += 1,
                        Ok(Some(None)) => {
                            scan.limited = true;
                            break;
                        }
                        Ok(Some(Some((note, length)))) => {
                            if size + length > limits.bytes {
                                scan.limited = true;
                                break;
                            }
                            scan.notes.push(note);
                            size += length;
                        }
                    }
                }
            }
        }
        scan.folders.sort();
        Ok(scan)
    }

    pub fn context(&self, paths: &[String], query: &str) -> Result<Vec<Py>> {
        if !(1..=8).contains(&paths.len()) {
            return Err(tr("Eine bis acht Quellen auswählen."));
        }
        let mut seen: Vec<&String> = Vec::new();
        let mut result = Vec::new();
        for path in paths {
            if seen.contains(&path) {
                continue;
            }
            seen.push(path);
            let mut note = self.read(path)?;
            let text = excerpt(
                note.get("text").and_then(Py::as_str).unwrap_or_default(),
                query,
                3000,
            );
            note.set("text", Py::Str(text));
            result.push(note);
        }
        Ok(result)
    }

    /// `image`: a picture inside the folder, at most 16 MiB.
    pub fn image(&self, path: &str) -> Result<Vec<u8>> {
        let names = parts(path);
        let suffix = text::suffix(path).to_lowercase();
        if path.starts_with('/')
            || names.contains(&"..")
            || names.iter().any(|p| p.starts_with('.'))
            || ![".png", ".jpg", ".jpeg", ".webp", ".gif"].contains(&suffix.as_str())
        {
            return Err(tr("Kein lokales Notizbild."));
        }
        let path = split(path);
        let parent = self.directory(&path.parent)?;
        let fd = rustix::fs::openat(
            &parent,
            nul_free(&path.name)?,
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(|e| os(e, &path.name))?;
        if FileType::from_raw_mode(
            rustix::fs::fstat(&fd)
                .map_err(|e| os(e, &path.name))?
                .st_mode,
        ) != FileType::RegularFile
        {
            return Err(tr("Kein reguläres Bild."));
        }
        let mut raw = Vec::new();
        File::from(fd)
            .take(MAX_IMAGE as u64 + 1)
            .read_to_end(&mut raw)
            .map_err(|e| io(e, &path.name, false))?;
        if raw.len() > MAX_IMAGE {
            return Err(tr("Bild größer als 16 MiB."));
        }
        Ok(raw)
    }

    /// The writing half of `add_image`: the PNG the binding made, as a new file in `attachments/`.
    pub fn attach(&self, png: &[u8]) -> Result<String> {
        let root = self.directory(".")?;
        match rustix::fs::mkdirat(&root, "attachments", Mode::from_raw_mode(0o700)) {
            Err(e) if e != rustix::io::Errno::EXIST => return Err(os(e, "attachments")),
            _ => {}
        }
        let name = format!("{}.png", self.env.uuid4());
        let parent = self.directory("attachments")?;
        let fd = rustix::fs::openat(
            &parent,
            name.as_str(),
            OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )
        .map_err(|e| os(e, &name))?;
        let mut file = File::from(fd);
        file.write_all(png).map_err(|e| io(e, &name, false))?;
        file.sync_all().map_err(|e| io(e, &name, false))?;
        Ok(format!("attachments/{name}"))
    }

    /// `notes_move.raw_write`: one note's bytes replaced, the earlier ones in the history.
    pub fn replace(&self, path: &str, before: &[u8], after: &[u8]) -> Result<()> {
        if before == after {
            return Ok(());
        }
        if self.raw(path)? != before {
            return Err(tr("Notizen wurden geändert. Vorschau erneut öffnen."));
        }
        self.backup(path, before)?;
        let target = split(path);
        let parent = self.directory(&target.parent)?;
        let temporary = format!(".lumen-move-{}", self.env.uuid4());
        let fd = rustix::fs::openat(
            &parent,
            temporary.as_str(),
            OFlags::CREATE | OFlags::EXCL | OFlags::WRONLY | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )
        .map_err(|e| os(e, &temporary))?;
        let outcome = (|| {
            let mut file = File::from(fd);
            file.write_all(after)
                .map_err(|e| io(e, &temporary, false))?;
            file.sync_all().map_err(|e| io(e, &temporary, false))?;
            drop(file);
            if self.raw(path)? != before {
                return Err(tr("Notizen wurden während des Verschiebens geändert."));
            }
            rustix::fs::renameat(&parent, temporary.as_str(), &parent, target.name.as_str())
                .map_err(|e| os(e, &temporary))?;
            rustix::fs::fsync(&parent).map_err(|e| os(e, &target.parent))
        })();
        match rustix::fs::unlinkat(&parent, temporary.as_str(), AtFlags::empty()) {
            Err(e) if e != rustix::io::Errno::NOENT && outcome.is_ok() => {
                return Err(os(e, &temporary));
            }
            _ => {}
        }
        outcome
    }

    /// `st_dev` and `st_ino` of the folder `path` (opened as `directory()` opens it), or of the
    /// entry `path` without following a link; `None` when the entry does not exist.
    pub fn stat(&self, path: &str, folder: bool) -> Result<Option<(u64, u64)>> {
        let stat = if folder {
            rustix::fs::fstat(&self.directory(path)?).map_err(|e| os(e, path))?
        } else {
            let target = split(path);
            let parent = self.directory(&target.parent)?;
            match rustix::fs::statat(&parent, nul_free(&target.name)?, AtFlags::SYMLINK_NOFOLLOW) {
                Ok(stat) => stat,
                Err(rustix::io::Errno::NOENT) => return Ok(None),
                Err(e) => return Err(os(e, &target.name)),
            }
        };
        Ok(Some((stat.st_dev, stat.st_ino)))
    }
}

fn path_of(note: &Py) -> String {
    note.get("path")
        .and_then(Py::as_str)
        .unwrap_or_default()
        .to_owned()
}

pub struct Limits {
    pub bytes: usize,
    pub notes: usize,
    pub entries: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Limits {
            bytes: MAX_SCAN_BYTES,
            notes: MAX_SCAN_NOTES,
            entries: MAX_SCAN_ENTRIES,
        }
    }
}

pub struct Scan {
    pub notes: Vec<Py>,
    pub folders: Vec<String>,
    pub errors: usize,
    pub limited: bool,
}

/// `activate`: the chosen (or the remembered, else a new private) notebook with its legacy
/// memories imported, remembered with its identity in the Store.
pub fn activate(store: &Store, env: &Env, root: Option<&str>) -> Result<String> {
    let remembered = store.setting("knowledge/notebook")?.unwrap_or(Py::str(""));
    let root = root.filter(|r| !r.is_empty());
    let chosen = match root {
        Some(root) => root.to_owned(),
        None if remembered.truthy() => python::py_str(&remembered),
        None => store
            .directory
            .join("wissen")
            .to_string_lossy()
            .into_owned(),
    };
    let identity = match root {
        Some(root) => Some(root_identity(
            &std::fs::canonicalize(root).map_err(|e| io(e, root, false))?,
        )?),
        None => None,
    };
    let book = Notebook::open(
        store,
        env,
        Some(&chosen),
        root.is_none() && !remembered.truthy(),
        identity,
    )?;
    book.migrate()?;
    store.set_setting("knowledge/notebook", &Py::str(&book.root_text()))?;
    store.set_setting("knowledge/identity", &book.identity)?;
    Ok(book.root_text())
}

/// `draft`: the unsaved text of a note in the private `wissen-drafts` folder; read without `text`.
pub fn draft(
    store: &Store,
    root: &str,
    path: &str,
    text: Option<&str>,
    expected: &str,
) -> Result<Option<Py>> {
    let directory = store.directory.join("wissen-drafts");
    match std::fs::DirBuilder::new().mode(0o700).create(&directory) {
        Err(e) if !(e.kind() == std::io::ErrorKind::AlreadyExists && directory.is_dir()) => {
            return Err(io(e, &directory.to_string_lossy(), true));
        }
        _ => {}
    }
    let name = digest(format!("{root}\0{path}").as_bytes());
    let target = directory.join(format!("{name}.json"));
    let Some(text) = text else {
        if !target.exists() {
            return Ok(None);
        }
        let data = std::fs::read(&target).map_err(|e| io(e, &target.to_string_lossy(), true))?;
        let data = std::str::from_utf8(&data)
            .map_err(|e| Failure::Unicode(python::decode_error(&data, e)))?;
        return python::loads(data).map(Some).ok_or(Failure::Value(
            "Expecting value: line 1 column 1 (char 0)".into(),
        ));
    };
    let data = Py::Dict(vec![
        ("root".into(), Py::str(root)),
        ("path".into(), Py::str(path)),
        ("text".into(), Py::str(text)),
        ("expected".into(), Py::str(expected)),
    ]);
    let temporary = directory.join(format!("{name}.tmp"));
    let fd = rustix::fs::open(
        &temporary,
        OFlags::WRONLY | OFlags::CREATE | OFlags::TRUNC | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o600),
    )
    .map_err(|e| Failure::Os {
        errno: e.raw_os_error(),
        filename: Some(temporary.to_string_lossy().into()),
        path: true,
    })?;
    let mut file = File::from(fd);
    file.write_all(python::dumps(&data, false).as_bytes())
        .map_err(|e| io(e, &temporary.to_string_lossy(), true))?;
    file.sync_all()
        .map_err(|e| io(e, &temporary.to_string_lossy(), true))?;
    std::fs::rename(&temporary, &target).map_err(|e| io(e, &temporary.to_string_lossy(), true))?;
    Ok(Some(data))
}

pub fn clear_draft(store: &Store, root: &str, path: &str) -> Result<()> {
    let target = store.directory.join("wissen-drafts").join(format!(
        "{}.json",
        digest(format!("{root}\0{path}").as_bytes())
    ));
    match std::fs::remove_file(&target) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
            Err(io(e, &target.to_string_lossy(), true))
        }
        _ => Ok(()),
    }
}

// ------------------------------------------------------------------ requests of the binding

/// A JSON value of a request as Python held it.
pub(crate) fn py(value: &Value) -> Py {
    match value {
        Value::Null => Py::None,
        Value::Bool(v) => Py::Bool(*v),
        Value::Number(n) if n.is_f64() => Py::Float(n.as_f64().unwrap_or(f64::NAN)),
        Value::Number(n) => Py::Int(n.to_string()),
        Value::String(v) => Py::str(v),
        Value::Array(items) => Py::List(items.iter().map(py).collect()),
        Value::Object(items) => Py::Dict(items.iter().map(|(k, v)| (k.clone(), py(v))).collect()),
    }
}

fn string<'r>(request: &'r Value, key: &str) -> &'r str {
    request[key].as_str().unwrap_or_default()
}

fn optional(request: &Value, key: &str) -> Option<Py> {
    request.get(key).filter(|v| !v.is_null()).map(py)
}

fn bytes(request: &Value, key: &str) -> Result<Vec<u8>> {
    base64::engine::general_purpose::STANDARD
        .decode(string(request, key))
        .map_err(|e| Failure::Value(e.to_string()))
}

fn encoded(data: &[u8]) -> Py {
    Py::Str(base64::engine::general_purpose::STANDARD.encode(data))
}

fn dict(items: Vec<(&str, Py)>) -> Py {
    Py::Dict(items.into_iter().map(|(k, v)| (k.to_owned(), v)).collect())
}

/// One `notes.*` request; `payload` is what followed its line (an attachment's bytes).
pub fn answer(request: &Value, payload: &[u8], env: &Env) -> Result<Py> {
    let op = string(request, "op");
    match op {
        "notes.parse" => {
            return Ok(parse(string(request, "path"), &bytes(request, "raw")?)
                .map_err(|e| Failure::Unicode(e.0))?
                .to_py());
        }
        "notes.tags" => {
            let tags = text::tags(string(request, "text"));
            return Ok(dict(vec![(
                "tags",
                Py::List(tags.iter().map(|t| Py::str(t)).collect()),
            )]));
        }
        "notes.mask" => {
            let mask = text::body_mask(string(request, "text"));
            return Ok(dict(vec![("mask", Py::Str(mask.into_iter().collect()))]));
        }
        "notes.targets" => {
            let targets = text::targets(string(request, "text"));
            return Ok(dict(vec![(
                "targets",
                Py::List(
                    targets
                        .into_iter()
                        .map(|t| {
                            dict(vec![
                                ("title", Py::str(&t.title)),
                                ("anchor", Py::Str(t.title)),
                                ("start", Py::int(t.start as i64)),
                                ("level", Py::int(t.level as i64)),
                            ])
                        })
                        .collect(),
                ),
            )]));
        }
        "notes.identity" => {
            let tag =
                text::identity(string(request, "value")).ok_or_else(|| tr("Ungültiger Tag."))?;
            return Ok(dict(vec![("tag", Py::Str(tag))]));
        }
        "notes.properties" => {
            let values = text::property_values(string(request, "text"))?;
            return Ok(dict(vec![(
                "properties",
                Py::Dict(
                    values
                        .into_iter()
                        .map(|(name, p)| (name, p.to_py()))
                        .collect(),
                ),
            )]));
        }
        "notes.add_tag" => {
            let text = edit::add_tag(string(request, "text"), string(request, "tag"))?;
            return Ok(dict(vec![("text", Py::Str(text))]));
        }
        "notes.rename_tag" => {
            let text = edit::rename_tag(
                string(request, "text"),
                string(request, "old"),
                string(request, "new"),
                request["descendants"].as_bool().unwrap_or(true),
            )?;
            return Ok(dict(vec![("text", Py::Str(text))]));
        }
        "notes.set_property" => {
            let text = edit::set_property(
                string(request, "text"),
                string(request, "name"),
                request["kind"].as_str().unwrap_or("text"),
                string(request, "value"),
                request["remove"].as_bool().unwrap_or(false),
            )?;
            return Ok(dict(vec![("text", Py::Str(text))]));
        }
        "notes.excerpt" => {
            let limit = request["limit"].as_u64().unwrap_or(3000) as usize;
            return Ok(dict(vec![(
                "text",
                Py::Str(excerpt(
                    string(request, "text"),
                    string(request, "query"),
                    limit,
                )),
            )]));
        }
        _ => {}
    }
    let store = Store {
        directory: PathBuf::from(string(request, "store")),
    };
    if !store.directory.is_absolute() {
        return Err(Failure::Value("the state folder must be absolute".into()));
    }
    match op {
        "notes.activate" => {
            return Ok(dict(vec![(
                "root",
                Py::Str(activate(&store, env, request["root"].as_str())?),
            )]));
        }
        "notes.draft" => {
            let saved = draft(
                &store,
                string(request, "root"),
                string(request, "path"),
                request["text"].as_str(),
                string(request, "expected"),
            )?;
            return Ok(dict(vec![("draft", saved.unwrap_or(Py::None))]));
        }
        "notes.clear_draft" => {
            clear_draft(&store, string(request, "root"), string(request, "path"))?;
            return Ok(dict(vec![]));
        }
        _ => {}
    }
    let book = Notebook::open(
        &store,
        env,
        request["root"].as_str(),
        request["create"].as_bool().unwrap_or(false),
        optional(request, "identity"),
    )?;
    let note = |result: Result<Py>| result;
    Ok(match op {
        "notes.open" => dict(vec![
            ("root", Py::str(&book.root_text())),
            ("identity", book.identity.clone()),
        ]),
        "notes.read" => note(book.read(string(request, "path")))?,
        "notes.raw" => dict(vec![("raw", encoded(&book.raw(string(request, "path"))?))]),
        "notes.write" => book.write(
            string(request, "path"),
            string(request, "text"),
            string(request, "expected"),
            optional(request, "source"),
            optional(request, "legacy"),
            optional(request, "created"),
            optional(request, "note_id").map(|v| python::py_str(&v)),
        )?,
        "notes.create" => book.create(
            string(request, "title"),
            string(request, "text"),
            &optional(request, "source").unwrap_or(Py::str("")),
            &optional(request, "legacy").unwrap_or(Py::str("")),
            request["folder"].as_str().unwrap_or("."),
            string(request, "note_id"),
        )?,
        "notes.create_collection" => dict(vec![(
            "name",
            Py::Str(book.create_collection(string(request, "name"))?),
        )]),
        "notes.remove" => dict(vec![(
            "key",
            Py::Str(book.remove(string(request, "path"), string(request, "expected"))?),
        )]),
        "notes.versions" => dict(vec![(
            "versions",
            Py::List(book.versions(request["path"].as_str())?),
        )]),
        "notes.restore" => book.restore(string(request, "key"), string(request, "expected"))?,
        "notes.capture" => dict(vec![(
            "path",
            Py::Str(book.capture(
                string(request, "title"),
                string(request, "text"),
                &optional(request, "source").unwrap_or(Py::str("")),
                request["memory"].as_str(),
            )?),
        )]),
        "notes.memory_path" => dict(vec![(
            "path",
            Py::Str(book.memory_path(string(request, "memory"))?),
        )]),
        "notes.migrate" => dict(vec![("changed", Py::int(book.migrate()? as i64))]),
        "notes.scan" => {
            if request["migrate"].as_bool().unwrap_or(false) {
                book.migrate()?;
            }
            let scan = book.scan(&Limits::default())?;
            let mut notes = scan.notes;
            let mut fields = Vec::new();
            if let Some(known) = request.get("known").and_then(Value::as_object) {
                // `known` holds `[hash, repr(modified)]`, so the time compares exactly.
                let same = |n: &Py| {
                    let path = path_of(n);
                    let Some([Value::String(hash), Value::String(modified)]) = known
                        .get(&path)
                        .and_then(Value::as_array)
                        .map(Vec::as_slice)
                    else {
                        return false;
                    };
                    Some(&Py::str(hash)) == n.get("hash")
                        && modified.parse::<f64>().ok().map(Py::Float).as_ref() == n.get("modified")
                };
                let unchanged: Vec<Py> = notes
                    .iter()
                    .filter(|n| same(n))
                    .map(|n| Py::Str(path_of(n)))
                    .collect();
                notes.retain(|n| !same(n));
                fields.push(("unchanged", Py::List(unchanged)));
            }
            let mut result = vec![
                ("notes", Py::List(notes)),
                (
                    "folders",
                    Py::List(scan.folders.iter().map(|f| Py::str(f)).collect()),
                ),
                ("errors", Py::int(scan.errors as i64)),
                ("limited", Py::Bool(scan.limited)),
                ("root", Py::str(&book.root_text())),
                ("identity", book.identity.clone()),
            ];
            result.extend(fields);
            dict(result)
        }
        "notes.context" => {
            let paths: Vec<String> = request["paths"]
                .as_array()
                .map(|p| {
                    p.iter()
                        .map(|v| v.as_str().unwrap_or_default().to_owned())
                        .collect()
                })
                .unwrap_or_default();
            dict(vec![(
                "notes",
                Py::List(book.context(&paths, string(request, "query"))?),
            )])
        }
        "notes.image" => dict(vec![(
            "raw",
            encoded(&book.image(string(request, "path"))?),
        )]),
        "notes.attach" => dict(vec![("path", Py::Str(book.attach(payload)?))]),
        "notes.replace" => {
            book.replace(
                string(request, "path"),
                &bytes(request, "before")?,
                &bytes(request, "after")?,
            )?;
            dict(vec![])
        }
        "notes.stat" => dict(vec![(
            "stat",
            book.stat(
                string(request, "path"),
                request["folder"].as_bool().unwrap_or(false),
            )?
            .map_or(Py::None, |(dev, ino)| {
                Py::List(vec![Py::Int(dev.to_string()), Py::Int(ino.to_string())])
            }),
        )]),
        "notes.relative" => {
            relative(string(request, "path"))?;
            dict(vec![])
        }
        _ => return Err(tr("Unbekannte Notizaktion.")),
    })
}

/// Serves one `notes.*` connection on its own thread: one answer line, then the connection closes.
pub fn serve(mut stream: UnixStream, request: Value, mut leftover: Vec<u8>) {
    let size = request["size"].as_u64().unwrap_or(0) as usize;
    if size > 0 {
        if size > MAX_ATTACHMENT {
            leftover.clear();
        } else {
            let missing = size.saturating_sub(leftover.len());
            let _ = (&stream).take(missing as u64).read_to_end(&mut leftover);
        }
    }
    let env = Env::default();
    let mut answer = match (
        size > MAX_ATTACHMENT || leftover.len() < size,
        answer(&request, &leftover, &env),
    ) {
        (true, _) => refusal(
            &request,
            &Failure::Value("attachment incomplete or too large".into()),
        ),
        (false, Ok(answer)) => answer,
        (false, Err(failure)) => refusal(&request, &failure),
    };
    answer.set("v", Py::int(crate::VERSION as i64));
    let mut line = python::dumps(&answer, false);
    line.push('\n');
    let _ = stream.set_write_timeout(Some(std::time::Duration::from_secs(60)));
    let _ = stream.write_all(line.as_bytes());
}

pub(crate) fn refusal(request: &Value, failure: &Failure) -> Py {
    let (kind, message, errno, filename, path) = match failure {
        Failure::Refused(text) => ("value", Texts::of(request).tr(text), None, None, false),
        Failure::Value(text) => ("value", text.clone(), None, None, false),
        Failure::Unicode(text) => ("unicode", text.clone(), None, None, false),
        Failure::Os {
            errno,
            filename,
            path,
        } => ("os", String::new(), Some(*errno), filename.clone(), *path),
    };
    dict(vec![
        ("failed", Py::Str(message)),
        ("kind", Py::str(kind)),
        ("errno", errno.map_or(Py::None, |e| Py::int(i64::from(e)))),
        ("filename", filename.map_or(Py::None, Py::Str)),
        ("path_object", Py::Bool(path)),
    ])
}

#[cfg(test)]
mod tests;

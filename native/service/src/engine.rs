//! The OpenCode engines of the desktop's conversations: the service starts, supervises and ends
//! them. One engine serves one profile (the view's environment, directory and options); a profile
//! asked for again reuses its engine while it answers. Engines end when they have been idle for ten
//! minutes, when the view stops them, with `quit` and when the service ends; each leads its own
//! process group, which is ended with it, and is told to end should the service die first.
use crate::texts::Texts;
use lumen_engine::{Client, python};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::cell::{Cell, RefCell};
use std::collections::{BTreeMap, HashMap};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::time::Duration;
use tokio::io::AsyncReadExt;
use tokio::process::{Child, Command};
use tokio::time::Instant;

/// How much of an engine's output is kept for the startup diagnosis.
const LOG: usize = 8000;
/// The largest engine answer the desktop reads: a conversation's newest hundred messages with their
/// tool output.
const ANSWER: usize = 16 * 1024 * 1024;
const IDLE: Duration = Duration::from_secs(600);

pub type Env = BTreeMap<String, String>;

/// A refusal in the request's language; `reset` when the conversation must start anew, `facts`
/// for the diagnosis (the engine's startup, an answer's summary). An empty message is a request the
/// service cannot read.
#[derive(Debug)]
pub struct Failure {
    pub message: String,
    pub reset: bool,
    pub facts: Value,
}

impl Failure {
    pub fn new(message: String) -> Self {
        Self {
            message,
            reset: false,
            facts: Value::Null,
        }
    }
    fn reset(message: String) -> Self {
        Self {
            reset: true,
            ..Self::new(message)
        }
    }
    pub fn invalid() -> Self {
        Self::new(String::new())
    }
    /// The answer to the view: `{"failed": …, "reset": …}`, or `invalid_request`.
    pub fn answer(self) -> Value {
        if self.message.is_empty() {
            return json!({"error": "invalid_request"});
        }
        let mut answer = json!({"failed": self.message, "reset": self.reset});
        if let Value::Object(facts) = self.facts {
            for (key, value) in facts {
                answer[key] = value;
            }
        }
        answer
    }
}

/// Why the server binding of an engine no longer holds: the pairing or the inherited
/// configuration broke, or the pairing changed since the engine started.
fn unbound(t: &Texts, now: Option<&String>, then: Option<&String>) -> Option<Failure> {
    match now {
        None => Some(Failure::reset(t.tr("Die private Server-Werkzeugkonfiguration ist ungültig. Bitte die Serververbindung prüfen."))),
        Some(now) if then.is_some_and(|then| then != now) => Some(Failure::reset(t.tr(
            "Die Serververbindung wurde geändert. Bitte die Nachricht in einem neuen Gespräch erneut senden.",
        ))),
        Some(_) => None,
    }
}

/// Which engine a request means: one the service manages for the view's profile, or one the caller
/// started itself (`url` and `password`), which is used as it is.
pub enum Spec {
    Managed {
        key: String,
        directory: String,
        env: Env,
        /// The view's own environment: the engine program and its database are the view's also
        /// for a learning engine, whose profile has folders of its own.
        view: Env,
        project_config: bool,
        research: bool,
        local: String,
    },
    Attached {
        url: String,
        password: String,
        directory: String,
    },
}

pub fn strings(value: &Value) -> Option<Env> {
    value
        .as_object()?
        .iter()
        .map(|(k, v)| Some((k.clone(), v.as_str()?.to_owned())))
        .collect()
}

impl Spec {
    /// `"engine": {"directory", "env", "project_config", "research", "environment"}` or
    /// `{"url", "password", "directory"}`, with the model policy that may pin a local model.
    pub fn of(request: &Value, t: &Texts) -> Result<Self, Failure> {
        let engine = &request["engine"];
        let invalid = Failure::invalid;
        let directory = engine["directory"]
            .as_str()
            .filter(|d| d.starts_with('/'))
            .ok_or_else(invalid)?
            .to_owned();
        if let Some(url) = engine["url"].as_str() {
            return Ok(Self::Attached {
                url: url.into(),
                password: engine["password"].as_str().ok_or_else(invalid)?.into(),
                directory,
            });
        }
        let view = strings(&engine["env"]).ok_or_else(invalid)?;
        let mut env = view.clone();
        // A learning engine's own profile: its folders, configuration and tools only.
        env.extend(strings(&engine["environment"]).unwrap_or_default());
        let policy = &request["policy"];
        let local = if policy["privacy"] == "local" {
            let model = policy["local_model"].as_str().unwrap_or_default();
            if !model.contains('/') {
                return Err(Failure::new(t.tr(
                    "Für lokale Verarbeitung zuerst ein lokales Modell auswählen.",
                )));
            }
            model.to_owned()
        } else {
            String::new()
        };
        let project_config = engine["project_config"] != false;
        let research = engine["research"] == true;
        let identity = json!({"directory": directory, "env": env, "project_config": project_config,
            "research": research, "local": local});
        Ok(Self::Managed {
            key: hex(&Sha256::digest(identity.to_string())),
            directory,
            env,
            view,
            project_config,
            research,
            local,
        })
    }
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn data_home(env: &Env) -> PathBuf {
    match env.get("XDG_DATA_HOME").filter(|v| !v.is_empty()) {
        Some(path) => PathBuf::from(path),
        None => Path::new(env.get("HOME").map_or("", String::as_str)).join(".local/share"),
    }
}

/// The engine Lumen installs for itself (`lumen_setup.install_engine`).
pub fn managed(env: &Env) -> PathBuf {
    data_home(env)
        .join("lumen/engine")
        .join(lumen_engine::VERSION)
        .join("opencode")
}

fn executable(path: &Path) -> bool {
    std::fs::metadata(path).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
}

/// `LUMEN_OPENCODE_BIN`, else the managed engine, else `opencode` on `PATH`, else the upstream
/// installer's place.
pub fn binary(env: &Env) -> String {
    if let Some(path) = env.get("LUMEN_OPENCODE_BIN").filter(|v| !v.is_empty()) {
        return path.clone();
    }
    let own = managed(env);
    if executable(&own) {
        return own.display().to_string();
    }
    env.get("PATH")
        .into_iter()
        .flat_map(|path| path.split(':'))
        .filter(|folder| !folder.is_empty())
        .map(|folder| Path::new(folder).join("opencode"))
        .find(|path| executable(path))
        .map(|path| path.display().to_string())
        .unwrap_or_else(|| {
            format!(
                "{}/.opencode/bin/opencode",
                env.get("HOME").map_or("", String::as_str)
            )
        })
}

/// The database the engine opens: the configured one, except that the managed engine keeps away
/// from a foreign schema in the shared folder and then keeps its own `lumen-v1.db`. Nothing is
/// written or migrated here.
pub fn database(binary: &str, configured: &str, env: &Env) -> String {
    if Path::new(binary) != managed(env) || configured == ":memory:" {
        return configured.into();
    }
    let data = data_home(env).join("opencode");
    let isolated = data.join("lumen-v1.db");
    // Reuse the chosen store after a restart, even if the shared database changes.
    if isolated.is_file() {
        return isolated.display().to_string();
    }
    let shared = data.join(if configured.is_empty() {
        "opencode.db"
    } else {
        configured
    });
    if !shared.is_file() {
        return configured.into();
    }
    let flags = rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_URI;
    let found = rusqlite::Connection::open_with_flags(&shared, flags).and_then(|db| {
        db.busy_timeout(Duration::from_millis(100))?;
        db.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='session'), \
             EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%')",
            [],
            |row| Ok((row.get::<_, bool>(0)?, row.get::<_, bool>(1)?)),
        )
    });
    match found {
        // Permission, corruption and locking failures need their original diagnosis.
        Ok((false, true)) => isolated.display().to_string(),
        _ => configured.into(),
    }
}

/// `str(pathlib.PurePosixPath(text))`: repeated and trailing slashes and `.` parts dropped, two
/// leading slashes kept. The binding stamp is computed over this form.
fn pure(text: &str) -> String {
    let root = if text.starts_with("//") && !text.starts_with("///") {
        "//"
    } else if text.starts_with('/') {
        "/"
    } else {
        ""
    };
    let parts: Vec<_> = text
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    let joined = format!("{root}{}", parts.join("/"));
    if joined.is_empty() {
        ".".into()
    } else {
        joined
    }
}

/// Python's `urlsplit` checks of a paired server address: `https://host[:port]` and nothing else.
fn server_address(server: &str) -> bool {
    let Some(netloc) = server.strip_prefix("https://") else {
        return false;
    };
    if netloc.contains(['/', '?', '#', '@']) || netloc.ends_with(':') {
        return false;
    }
    let (host, port) = if let Some(rest) = netloc.strip_prefix('[') {
        let Some((host, after)) = rest.split_once(']') else {
            return false;
        };
        let valid = if let Some(future) = host.strip_prefix('v') {
            future.split_once('.').is_some_and(|(version, address)| {
                !version.is_empty()
                    && version.chars().all(|c| c.is_ascii_hexdigit())
                    && !address.is_empty()
            })
        } else {
            host.parse::<std::net::Ipv6Addr>().is_ok()
        };
        if !valid || after.contains(['[', ']']) || !(after.is_empty() || after.starts_with(':')) {
            return false;
        }
        (host, after.strip_prefix(':').unwrap_or_default())
    } else {
        if netloc.contains([']']) {
            return false;
        }
        netloc.split_once(':').unwrap_or((netloc, ""))
    };
    !host.is_empty()
        && (port.is_empty()
            || port.bytes().all(|b| b.is_ascii_digit())
                && port.parse::<u32>().is_ok_and(|p| (1..=65535).contains(&p)))
}

fn pairing_valid(pairing: &Map<String, Value>) -> bool {
    let (Some(server), Some(token), Some(device)) = (
        pairing.get("server").and_then(Value::as_str),
        pairing.get("token").and_then(Value::as_str),
        pairing.get("device_id").and_then(Value::as_str),
    ) else {
        return false;
    };
    let device_ok = device.len() == 36
        && device.char_indices().all(|(i, c)| match i {
            8 | 13 | 18 | 23 => c == '-',
            _ => c.is_ascii_digit() || ('a'..='f').contains(&c),
        });
    server.chars().count() <= 4096
        && !server
            .chars()
            .any(|c| c.is_whitespace() || (c as u32) < 32 || c as u32 == 127 || "\\%{}".contains(c))
        && server_address(server)
        && device_ok
        && !token.is_empty()
        && token.chars().count() <= 1000
        && token
            .chars()
            .all(|c| (33..=126).contains(&(c as u32)) && c != '{' && c != '}')
}

/// The binding stamp Python wrote: `sha256(json.dumps([home, root, fields], sort_keys=True))`;
/// serde_json's maps are ordered by key, as `sort_keys` orders them.
fn stamp(home: &str, root: &str, fields: Option<Map<String, Value>>) -> String {
    let text = python::python_ascii(&python::python_json(&json!([home, root, fields])));
    hex(&Sha256::digest(text.as_bytes()))
}

/// The home and configuration folders of `env` (`XDG_CONFIG_HOME`, else `HOME/.config`) as pathlib
/// writes them; `None` unless both are absolute.
fn folders(env: &Env) -> Option<(String, String)> {
    let home = env.get("HOME").map_or("", String::as_str);
    let root = match env.get("XDG_CONFIG_HOME").filter(|v| !v.is_empty()) {
        Some(root) => pure(root),
        None => pure(&format!("{home}/.config")),
    };
    let home = pure(home);
    (home.starts_with('/') && root.starts_with('/')).then_some((home, root))
}

/// The paired server of the view's environment (`lumen-server/connection.json` in its configuration
/// folder), read without following links and only when it is the user's own private file of at most
/// 64 KiB with a valid pairing: `Ok(None)` without one, `Err(())` when it cannot be used.
pub fn pairing(env: &Env) -> Result<Option<Map<String, Value>>, ()> {
    let (_, root) = folders(env).ok_or(())?;
    Ok(pairing_file(&Path::new(&root).join("lumen-server/connection.json"))?.map(|(p, _)| p))
}

/// `pairing.read` of `lumen_connect.read_config` (the connector's `--config-dir` profiles name
/// their own file): `{"pairing": "<the file's text>"}`, `null` without one, or `failed`.
pub fn read_pairing(request: &Map<String, Value>) -> Value {
    let path = Path::new(
        request
            .get("path")
            .and_then(Value::as_str)
            .unwrap_or_default(),
    );
    match path.is_absolute().then(|| pairing_file(path)) {
        Some(Ok(found)) => json!({"pairing": found.map(|(_, text)| text)}),
        _ => json!({"failed": "unusable"}),
    }
}

/// A pairing and the text of its file.
type Pairing = (Map<String, Value>, String);

/// The pairing in `path` and its text, by the rules of [`pairing`].
fn pairing_file(path: &Path) -> Result<Option<Pairing>, ()> {
    let mut file = match std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
    {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(()),
        Ok(file) => file,
    };
    let meta = file.metadata().map_err(|_| ())?;
    if !meta.is_file()
        || meta.uid() != crate::sys::uid()
        || meta.mode() & 0o077 != 0
        || meta.size() > 65536
    {
        return Err(());
    }
    let mut raw = Vec::new();
    std::io::Read::read_to_end(&mut std::io::Read::take(&mut file, 65537), &mut raw)
        .map_err(|_| ())?;
    match serde_json::from_slice(&raw) {
        Ok(Value::Object(pairing)) if raw.len() <= 65536 && pairing_valid(&pairing) => {
            // Valid JSON is UTF-8; the caller parses the text itself and keeps its key order.
            Ok(Some((pairing, String::from_utf8(raw).map_err(|_| ())?)))
        }
        _ => Err(()),
    }
}

/// The engine configuration for `env` with the paired server's tools (or a disabled entry that
/// masks an inherited one), and the stamp of that binding. Never writes a configuration or token
/// file. `None` when the pairing or the inherited configuration is unusable.
pub fn configuration(env: &Env) -> Option<(Map<String, Value>, String)> {
    let (home, root) = folders(env)?;
    let inherited = env
        .get("OPENCODE_CONFIG_CONTENT")
        .filter(|v| !v.is_empty())
        .map_or("{}", String::as_str);
    let Ok(Value::Object(mut config)) = serde_json::from_str(inherited) else {
        return None;
    };
    if config.get("mcp").is_some_and(|mcp| !mcp.is_object()) {
        return None;
    }
    let pairing = pairing(env).ok()?;
    let fields = pairing.as_ref().map(|p| {
        ["server", "device_id", "token", "account", "ca_file"]
            .iter()
            .map(|k| ((*k).to_owned(), p.get(*k).cloned().unwrap_or(Value::Null)))
            .collect::<Map<_, _>>()
    });
    let stamp = stamp(&home, &root, fields);
    let entry = match &pairing {
        None => json!({"enabled": false}),
        Some(p) => {
            let server = p["server"].as_str().unwrap_or_default();
            let skills = config
                .entry("skills")
                .or_insert_with(|| json!({}))
                .as_object_mut()?;
            let urls = skills.entry("urls").or_insert_with(|| json!([]));
            let urls = urls.as_array_mut()?;
            if urls.iter().any(|u| !u.is_string()) {
                return None;
            }
            let shared = json!(format!("{server}/api/skills/"));
            if !urls.contains(&shared) {
                urls.push(shared);
            }
            json!({"type": "remote", "url": format!("{server}/mcp/"),
                "headers": {"Authorization": format!("Bearer {}", p["token"].as_str().unwrap_or_default())},
                "enabled": true, "oauth": false})
        }
    };
    let mcp = config.entry("mcp").or_insert_with(|| json!({}));
    mcp.as_object_mut()?.insert("lumen-server".into(), entry);
    Some((config, stamp))
}

/// The startup failure classes the diagnosis names, without paths, configuration or log text.
pub fn startup_summary(outcome: &str, log: &[u8], elapsed: u128, code: Option<i32>) -> Value {
    let text = String::from_utf8_lossy(log).to_lowercase();
    let hints: [(&str, &[&str]); 7] = [
        (
            "invalid_config",
            &[
                "configuration is invalid",
                "is not valid json(c)",
                "configinvaliderror",
                "configjsonerror",
            ],
        ),
        (
            "permission_denied",
            &["eacces", "eperm", "permission denied"],
        ),
        ("disk_full", &["enospc", "no space left on device"]),
        (
            "database_schema",
            &["database is not empty and has no session table"],
        ),
        (
            "database",
            &[
                "sqlite_",
                "sqliteerror",
                "database is locked",
                "unable to open database",
            ],
        ),
        ("address_in_use", &["eaddrinuse", "address already in use"]),
        (
            "tls",
            &[
                "certificate_verify_failed",
                "unable_to_verify_leaf_signature",
                "unable to verify the first certificate",
            ],
        ),
    ];
    let hint = hints
        .iter()
        .find(|(_, markers)| markers.iter().any(|m| text.contains(m)))
        .map_or("unknown", |(name, _)| name);
    let mut result = json!({"outcome": outcome, "hint": hint, "elapsed_ms": elapsed as u64,
        "captured_bytes": log.len()});
    if let Some(code) = code {
        result["exit_code"] = json!(code);
    }
    if outcome == "start_error" {
        // QProcess::FailedToStart, as the earlier diagnosis named it.
        result["process_error"] = json!(0);
    }
    result
}

/// The view's message for a failed start, with the class the diagnosis found.
fn startup_message(t: &Texts, summary: &Value) -> String {
    let outcome = summary["outcome"].as_str().unwrap_or_default();
    let mut message = match summary["hint"].as_str() {
        Some("invalid_config") => t.tr("OpenCode kann seine Konfiguration nicht laden. Bitte die OpenCode-Konfiguration prüfen; eine Neuinstallation der Engine behebt das nicht."),
        Some("permission_denied") => t.tr("OpenCode fehlen Dateizugriffsrechte. Bitte die Rechte des OpenCode-Benutzerprofils prüfen."),
        Some("database" | "database_schema") => t.tr("OpenCode kann seine Datenbank nicht öffnen. Bitte Diagnose kopieren; die Datenbank nicht löschen."),
        Some("disk_full") => t.tr("OpenCode konnte wegen fehlendem Speicherplatz nicht starten."),
        _ => match outcome {
            "start_error" => t.tr("OpenCode konnte nicht gestartet werden. Installation und Pfad prüfen."),
            "timeout" => t.tr("Die Hintergrund-Engine antwortet nicht. Bitte erneut versuchen."),
            _ => t.tr("Die Hintergrund-Engine wurde beendet."),
        },
    };
    if let Some(code) = summary["exit_code"].as_i64() {
        message.push(' ');
        message.push_str(&t.tr_args(
            "Prozess beendet: Code {0} ({1}).",
            &[&code.to_string(), outcome],
        ));
    }
    message
}

/// One running engine.
pub struct Engine {
    pub client: Client,
    /// The engine's own process; `None` for an engine the caller started.
    child: RefCell<Option<Child>>,
    log: Rc<RefCell<Vec<u8>>>,
    /// The paired server binding the engine was configured with; `None` for a caller's engine.
    pub stamp: Option<String>,
    env: Env,
    pub facts: Value,
    turns: Cell<usize>,
    used: Cell<Instant>,
}

impl Engine {
    /// Holds the engine for a turn: it is neither reaped nor stopped while one runs.
    pub fn turn(self: &Rc<Self>) -> Hold {
        self.turns.set(self.turns.get() + 1);
        Hold(self.clone())
    }

    pub fn managed(&self) -> bool {
        self.stamp.is_some()
    }

    /// Whether the engine's server binding still holds; a changed or broken pairing ends its turn.
    pub fn binding(&self, t: &Texts) -> Result<(), Failure> {
        if self.stamp.is_none() {
            return Ok(());
        }
        let now = configuration(&self.env).map(|(_, stamp)| stamp);
        unbound(t, now.as_ref(), self.stamp.as_ref()).map_or(Ok(()), Err)
    }

    fn exited(&self) -> bool {
        self.child
            .borrow_mut()
            .as_mut()
            .is_some_and(|child| !matches!(child.try_wait(), Ok(None)))
    }

    /// Why the engine stopped answering, when its process has ended.
    pub fn failure(&self, t: &Texts) -> Option<String> {
        let mut child = self.child.borrow_mut();
        let status = child.as_mut()?.try_wait().ok()??;
        use std::os::unix::process::ExitStatusExt;
        let (outcome, code) = match status.signal() {
            Some(signal) => ("crashed", signal),
            None => ("exited", status.code().unwrap_or_default()),
        };
        let summary = startup_summary(outcome, &self.log.borrow(), 0, Some(code));
        Some(startup_message(t, &summary))
    }
}

pub struct Hold(Rc<Engine>);

impl Drop for Hold {
    fn drop(&mut self) {
        self.0.turns.set(self.0.turns.get() - 1);
        self.0.used.set(Instant::now());
    }
}

/// Keeps the newest output of the engine for the diagnosis, and keeps its pipes from filling.
fn drain(stream: impl tokio::io::AsyncRead + Unpin + 'static, log: Rc<RefCell<Vec<u8>>>) {
    tokio::task::spawn_local(async move {
        let mut stream = stream;
        let mut buffer = [0; 8192];
        while let Ok(n) = stream.read(&mut buffer).await {
            if n == 0 {
                break;
            }
            let mut log = log.borrow_mut();
            log.extend_from_slice(&buffer[..n]);
            let excess = log.len().saturating_sub(LOG);
            log.drain(..excess);
        }
    });
}

/// The port of `http://127.0.0.1:<port>` in the engine's output.
fn listening(log: &[u8]) -> Option<u16> {
    let marker = b"http://127.0.0.1:";
    let at = log.windows(marker.len()).position(|w| w == marker)? + marker.len();
    let digits: Vec<u8> = log[at..]
        .iter()
        .copied()
        .take_while(u8::is_ascii_digit)
        .collect();
    // The line may still be arriving: wait for the character after the number.
    if at + digits.len() >= log.len() {
        return None;
    }
    std::str::from_utf8(&digits).ok()?.parse().ok()
}

fn password() -> Result<String, std::io::Error> {
    let mut bytes = [0; 32];
    std::io::Read::read_exact(&mut std::fs::File::open("/dev/urandom")?, &mut bytes)?;
    Ok(hex(&bytes))
}

/// The engines of all views, by profile.
pub struct Engines {
    current: RefCell<HashMap<String, Rc<Engine>>>,
    /// Stopped or replaced engines that still carry a turn; reaped once it ends.
    retiring: RefCell<Vec<Rc<Engine>>>,
    plugin: String,
    starting: tokio::sync::Mutex<()>,
    /// What finished turns left to learn from, and each view's learning queue.
    pub learning: crate::learning::Learning,
}

/// The compaction plugin is written next to the socket, so every engine loads the crate's copy;
/// the answer is its file URL.
pub fn plugin(folder: &Path) -> Result<String, String> {
    let path = folder.join("lumen-continuity.mjs");
    let partial = folder.join(".lumen-continuity.mjs.partial");
    std::fs::write(&partial, lumen_engine::PLUGIN).map_err(|e| e.to_string())?;
    std::fs::set_permissions(&partial, std::fs::Permissions::from_mode(0o600))
        .map_err(|e| e.to_string())?;
    std::fs::rename(&partial, &path).map_err(|e| e.to_string())?;
    Ok(format!("file://{}", path.display()))
}

impl Engines {
    pub fn new(plugin: String) -> Self {
        Self {
            current: RefCell::default(),
            retiring: RefCell::default(),
            plugin,
            starting: tokio::sync::Mutex::new(()),
            learning: crate::learning::Learning::default(),
        }
    }

    /// The engine for `spec`: the running one when it still answers and its binding still holds,
    /// else a new one. A changed or broken server binding is refused and its engine stopped.
    pub async fn get(&self, spec: &Spec, t: &Texts) -> Result<Rc<Engine>, Failure> {
        let _starting = self.starting.lock().await;
        let (key, directory, env, view, project_config, research, local) = match spec {
            Spec::Attached {
                url,
                password,
                directory,
            } => {
                let client = Client::attached(url, password)
                    .map_err(|_| {
                        Failure::new(t.tr("Die Engine muss auf dem lokalen Rechner laufen."))
                    })?
                    .directory(directory)
                    .limit(ANSWER)
                    .page(100);
                return Ok(Rc::new(Engine {
                    client,
                    child: RefCell::new(None),
                    log: Rc::default(),
                    stamp: None,
                    env: Env::new(),
                    facts: json!({"database": "default", "startup": {"outcome": "attached"}}),
                    turns: Cell::new(0),
                    used: Cell::new(Instant::now()),
                }));
            }
            Spec::Managed {
                key,
                directory,
                env,
                view,
                project_config,
                research,
                local,
            } => (key, directory, env, view, *project_config, *research, local),
        };
        let configured = configuration(env);
        let stamp = configured.as_ref().map(|(_, stamp)| stamp.clone());
        let invalid = || unbound(t, None, None).expect("a broken binding is refused");
        let running = self.current.borrow().get(key).cloned();
        if let Some(engine) = running {
            if let Some(failure) = unbound(t, stamp.as_ref(), engine.stamp.as_ref()) {
                self.retire(&engine);
                return Err(failure);
            }
            if !engine.exited() && engine.client.health(Duration::from_secs(2)).await {
                engine.used.set(Instant::now());
                return Ok(engine);
            }
            self.retire(&engine);
        }
        let (mut config, stamp) = configured.ok_or_else(invalid)?;
        let plugins = config.entry("plugin").or_insert_with(|| json!([]));
        let plugins = plugins.as_array_mut().ok_or_else(invalid)?;
        if !plugins
            .iter()
            .any(|row| row == self.plugin.as_str() || row[0] == self.plugin.as_str())
        {
            plugins.push(json!(self.plugin));
        }
        let mut env = env.clone();
        let binding_env = env.clone();
        for key in ["OPENCODE", "OPENCODE_PID"] {
            env.remove(key);
        }
        // As the earlier view chose them: from its own environment, not a learning profile's.
        let binary = binary(view);
        let configured = view.get("OPENCODE_DB").cloned().unwrap_or_default();
        let chosen = database(&binary, &configured, view);
        let source = if chosen != configured {
            "lumen"
        } else if configured.is_empty() {
            "default"
        } else {
            "inherited"
        };
        if !chosen.is_empty() {
            env.insert("OPENCODE_DB".into(), chosen);
        }
        let password = password().map_err(|_| invalid())?;
        env.insert("OPENCODE_SERVER_PASSWORD".into(), password.clone());
        env.insert("OPENCODE_SERVER_USERNAME".into(), "opencode".into());
        if research && !env.contains_key("OPENCODE_ENABLE_PARALLEL") {
            env.insert("OPENCODE_ENABLE_EXA".into(), "true".into());
        }
        if !project_config || !local.is_empty() {
            env.insert("OPENCODE_DISABLE_PROJECT_CONFIG".into(), "true".into());
        }
        if let Some((provider, _)) = local.split_once('/') {
            config.insert("model".into(), json!(local));
            config.insert("small_model".into(), json!(local));
            config.insert("enabled_providers".into(), json!([provider]));
        }
        env.insert(
            "OPENCODE_CONFIG_CONTENT".into(),
            Value::Object(config).to_string(),
        );
        let started = Instant::now();
        let mut command = Command::new(&binary);
        command
            .args(["serve", "--hostname", "127.0.0.1", "--port", "0"])
            .env_clear()
            .envs(&env)
            .current_dir(directory)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .process_group(0);
        crate::sys::end_with_service(&mut command);
        let log: Rc<RefCell<Vec<u8>>> = Rc::default();
        let elapsed = || started.elapsed().as_millis();
        let fail = |summary: Value| Failure {
            message: startup_message(t, &summary),
            reset: false,
            facts: json!({"engine": {"database": source, "binary": binary, "startup": summary}}),
        };
        let mut child = command
            .spawn()
            .map_err(|_| fail(startup_summary("start_error", &[], elapsed(), None)))?;
        if let Some(out) = child.stdout.take() {
            drain(out, log.clone());
        }
        if let Some(err) = child.stderr.take() {
            drain(err, log.clone());
        }
        let deadline = started + Duration::from_secs(25);
        let port = loop {
            if let Some(port) = listening(&log.borrow()) {
                break port;
            }
            if let Ok(Some(status)) = child.try_wait() {
                // The last output may still be in the pipe.
                tokio::time::sleep(Duration::from_millis(50)).await;
                use std::os::unix::process::ExitStatusExt;
                let (outcome, code) = match status.signal() {
                    Some(signal) => ("crashed", signal),
                    None => ("exited", status.code().unwrap_or_default()),
                };
                lumen_engine::reap(&mut child, true).await;
                return Err(fail(startup_summary(
                    outcome,
                    &log.borrow(),
                    elapsed(),
                    Some(code),
                )));
            }
            if Instant::now() >= deadline {
                lumen_engine::reap(&mut child, true).await;
                return Err(fail(startup_summary(
                    "timeout",
                    &log.borrow(),
                    elapsed(),
                    None,
                )));
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        };
        let client = Client::attached(&format!("http://127.0.0.1:{port}/"), &password)
            .map_err(|_| invalid())?
            .directory(directory)
            .limit(ANSWER)
            .page(100);
        let engine = Rc::new(Engine {
            client,
            child: RefCell::new(Some(child)),
            log,
            stamp: Some(stamp),
            env: binding_env,
            facts: json!({"database": source, "binary": binary,
                "startup": {"outcome": "ready", "elapsed_ms": elapsed() as u64}}),
            turns: Cell::new(0),
            used: Cell::new(Instant::now()),
        });
        self.current
            .borrow_mut()
            .insert(key.clone(), engine.clone());
        Ok(engine)
    }

    /// No new request reaches the engine; it ends once no turn uses it.
    pub fn retire(&self, engine: &Rc<Engine>) {
        self.current
            .borrow_mut()
            .retain(|_, e| !Rc::ptr_eq(e, engine));
        let mut retiring = self.retiring.borrow_mut();
        if engine.child.borrow().is_some() && !retiring.iter().any(|e| Rc::ptr_eq(e, engine)) {
            retiring.push(engine.clone());
        }
    }

    /// Stops the engine of `spec`, if one runs.
    pub fn stop(&self, spec: &Spec) {
        if let Spec::Managed { key, .. } = spec {
            let engine = self.current.borrow().get(key).cloned();
            if let Some(engine) = engine {
                self.retire(&engine);
            }
        }
    }

    /// Ends retired engines without a turn and engines idle for ten minutes.
    pub async fn tidy(&self) {
        let idle: Vec<_> = self
            .current
            .borrow()
            .values()
            .filter(|e| e.turns.get() == 0 && e.used.get().elapsed() >= IDLE)
            .cloned()
            .collect();
        for engine in &idle {
            self.retire(engine);
        }
        let done: Vec<_> = {
            let mut retiring = self.retiring.borrow_mut();
            let (done, keep) = retiring.drain(..).partition(|e| e.turns.get() == 0);
            *retiring = keep;
            done
        };
        end(done).await;
    }

    /// Ends every engine, also those with a turn.
    pub async fn shutdown(&self) {
        let all: Vec<_> = self.current.borrow_mut().drain().map(|(_, e)| e).collect();
        let mut all = all;
        all.append(&mut self.retiring.borrow_mut());
        end(all).await;
    }
}

/// TERM to each engine's process group at once, then up to five seconds before KILL.
async fn end(engines: Vec<Rc<Engine>>) {
    let reaps: Vec<_> = engines
        .iter()
        .filter_map(|e| e.child.borrow_mut().take())
        .map(|mut child| {
            tokio::task::spawn_local(async move { lumen_engine::reap(&mut child, true).await })
        })
        .collect();
    for reap in reaps {
        let _ = reap.await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paired_server_addresses_follow_pythons_urlsplit() {
        for good in [
            "https://staging.invalid",
            "https://host.invalid:8443",
            "https://[::1]:8443",
            "https://[v1.x]",
            "https://bücher.invalid",
        ] {
            assert!(server_address(good), "{good}");
        }
        for bad in [
            "http://host.invalid",
            "HTTPS://host.invalid",
            "https://user@host.invalid",
            "https://@host.invalid",
            "https://host.invalid/path",
            "https://host.invalid/",
            "https://host.invalid?",
            "https://host.invalid#",
            "https://host.invalid:0",
            "https://host.invalid:",
            "https://host.invalid:70000",
            "https://host.invalid:+1",
            "https://host.invalid:1:2",
            "https://:443",
            "https://",
            "https://[127.0.0.1]",
            "https://[::1",
            "https://::1]",
            "https://a[::1]",
            "https://[::1]x",
        ] {
            assert!(!server_address(bad), "{bad}");
        }
    }

    #[test]
    fn paths_are_written_as_pathlib_writes_them() {
        for (text, expected) in [
            ("/home/a/", "/home/a"),
            ("/home//a/./b", "/home/a/b"),
            ("//home", "//home"),
            ("///home", "/home"),
            ("", "."),
            ("relative/x", "relative/x"),
        ] {
            assert_eq!(pure(text), expected);
        }
    }

    fn folder(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "lumen-service-engine-{name}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("config/lumen-server")).unwrap();
        root
    }

    fn pair(root: &Path, changes: Value) -> PathBuf {
        let mut value = json!({"server": "https://staging.invalid", "token": "synthetic-device-token",
            "device_id": "a5c704e4-c826-479b-bcde-41b2c8dc8efb"});
        for (k, v) in changes.as_object().unwrap() {
            value[k] = v.clone();
        }
        let path = root.join("config/lumen-server/connection.json");
        let _ = std::fs::remove_file(&path);
        std::fs::write(&path, value.to_string()).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        path
    }

    fn env(root: &Path, content: &str) -> Env {
        [
            ("HOME", root.display().to_string()),
            ("XDG_CONFIG_HOME", root.join("config").display().to_string()),
            ("OPENCODE_CONFIG_CONTENT", content.into()),
        ]
        .into_iter()
        .map(|(k, v)| (k.into(), v))
        .collect()
    }

    #[test]
    fn the_pairing_adds_the_server_tools_and_skills_and_keeps_the_rest() {
        let root = folder("pairing");
        let path = pair(&root, json!({}));
        let before = std::fs::read(&path).unwrap();
        let original = json!({"model": "provider/model", "permission": {"edit": "ask"},
            "mcp": {"other": {"type": "local", "command": ["true"]},
                "lumen-server": {"type": "remote", "url": "https://stale.invalid/mcp/", "enabled": false}},
            "skills": {"paths": ["/own/skills"], "urls": ["https://own.invalid/skills/"]}});
        let (config, stamp) = configuration(&env(&root, &original.to_string())).unwrap();
        assert_eq!(
            config["mcp"]["lumen-server"],
            json!({"type": "remote", "url": "https://staging.invalid/mcp/",
            "headers": {"Authorization": "Bearer synthetic-device-token"}, "enabled": true, "oauth": false})
        );
        assert_eq!(config["mcp"]["other"], original["mcp"]["other"]);
        assert_eq!(config["model"], "provider/model");
        assert_eq!(
            config["skills"],
            json!({"paths": ["/own/skills"],
            "urls": ["https://own.invalid/skills/", "https://staging.invalid/api/skills/"]})
        );
        assert_eq!(std::fs::read(&path).unwrap(), before);
        // python3 -c 'import hashlib,json; print(hashlib.sha256(json.dumps(["/r", "/r/config",
        //   {"server": "https://staging.invalid", "device_id": "a5c704e4-c826-479b-bcde-41b2c8dc8efb",
        //    "token": "synthetic-device-token", "account": None, "ca_file": None}], sort_keys=True).encode()).hexdigest())'
        // for the root "/r": the stamp covers exactly this text.
        let text = python::python_ascii(&python::python_json(&json!([
            root.display().to_string(),
            root.join("config").display().to_string(),
            {"account": null, "ca_file": null, "device_id": "a5c704e4-c826-479b-bcde-41b2c8dc8efb",
             "server": "https://staging.invalid", "token": "synthetic-device-token"}
        ])));
        assert_eq!(stamp, hex(&Sha256::digest(text.as_bytes())));
        // A model change keeps the binding; another token changes it.
        let (_, same) = configuration(&env(&root, r#"{"model": "another/model"}"#)).unwrap();
        assert_eq!(same, stamp);
        pair(&root, json!({"token": "replacement-token"}));
        assert_ne!(configuration(&env(&root, "{}")).unwrap().1, stamp);
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn the_stamp_is_the_one_python_wrote() {
        let fields = json!({"server": "https://staging.invalid", "device_id": "a5c704e4-c826-479b-bcde-41b2c8dc8efb",
            "token": "synthetic-device-token", "account": "Änne", "ca_file": null});
        // Computed with the earlier files/server_mcp_binding.py formula.
        assert_eq!(
            stamp("/r", "/r/config", fields.as_object().cloned()),
            "2ae5605ddb8ddd3da91fa1342ad025d08596e014e69ef956617f44ad02db1f45"
        );
        assert_eq!(
            stamp("/r", "/r/config", None),
            "bd856a2328e6eaca7a5e74aa9d3772c471102412cc1829990d539f19580ee5a6"
        );
    }

    #[test]
    fn python_writes_the_stamp_text_this_way() {
        // python3 -c 'import json; print(json.dumps(["/h", "/h/.config", {"server": "s", "device_id": "d",
        //   "token": "t", "account": "ä", "ca_file": None}], sort_keys=True))'
        let text = python::python_ascii(&python::python_json(&json!(["/h", "/h/.config",
            {"server": "s", "device_id": "d", "token": "t", "account": "ä", "ca_file": null}])));
        assert_eq!(
            text,
            r#"["/h", "/h/.config", {"account": "\u00e4", "ca_file": null, "device_id": "d", "server": "s", "token": "t"}]"#
        );
    }

    #[test]
    fn without_a_pairing_an_inherited_server_entry_is_masked() {
        let root = folder("masked");
        let (config, _) = configuration(&env(
            &root,
            r#"{"model": "p/m", "mcp": {"other": {"enabled": false}, "lumen-server": {"url": "https://old.invalid/mcp/"}}}"#,
        ))
        .unwrap();
        assert_eq!(config["mcp"]["lumen-server"], json!({"enabled": false}));
        assert_eq!(config["mcp"]["other"], json!({"enabled": false}));
        assert!(config.get("skills").is_none());
        // The home fallback is the effective home, also with an empty XDG_CONFIG_HOME.
        let home = root.join("alternate");
        std::fs::create_dir_all(home.join(".config")).unwrap();
        std::fs::create_dir_all(root.join("config/lumen-server")).unwrap();
        let path = pair(&root, json!({}));
        let alternate = home.join(".config/lumen-server");
        std::fs::create_dir_all(&alternate).unwrap();
        std::fs::copy(&path, alternate.join("connection.json")).unwrap();
        let mut fallback = env(&root, "{}");
        fallback.insert("HOME".into(), home.display().to_string());
        fallback.insert("XDG_CONFIG_HOME".into(), String::new());
        let (config, _) = configuration(&fallback).unwrap();
        assert_eq!(
            config["mcp"]["lumen-server"]["url"],
            "https://staging.invalid/mcp/"
        );
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn the_connector_reads_its_pairing_through_the_service() {
        let root = folder("read");
        let path = root.join("config/lumen-server/connection.json");
        let read = |path: &Path| read_pairing(json!({"path": path}).as_object().unwrap());
        assert_eq!(read(&path), json!({"pairing": null}));
        // The text as written: the connector keeps its key order when it saves the pairing again.
        let text = r#"{"token": "synthetic-device-token", "server": "https://staging.invalid", "device_id": "a5c704e4-c826-479b-bcde-41b2c8dc8efb", "system_access": {"version": 2}}"#;
        std::fs::write(&path, text).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(read(&path), json!({"pairing": text}));
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o640)).unwrap();
        assert_eq!(read(&path), json!({"failed": "unusable"}));
        pair(&root, json!({"server": "http://staging.invalid"}));
        assert_eq!(read(&path), json!({"failed": "unusable"}));
        pair(&root, json!({}));
        assert_eq!(
            read(Path::new("config/lumen-server/connection.json")),
            json!({"failed": "unusable"})
        );
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn an_invalid_pairing_or_configuration_fails_closed() {
        let root = folder("invalid");
        for changes in [
            json!({"server": "http://host.invalid"}),
            json!({"server": "https://user@host.invalid"}),
            json!({"server": "https://host.invalid/path"}),
            json!({"server": "https://host.invalid:0"}),
            json!({"server": "https://host.invalid\\@other.invalid"}),
            json!({"token": "secret\r\nHeader: no"}),
            json!({"token": "{env:SECRET}"}),
            json!({"token": ""}),
            json!({"device_id": "invalid"}),
            json!({"device_id": "A5C704E4-C826-479B-BCDE-41B2C8DC8EFB"}),
        ] {
            pair(&root, changes.clone());
            assert!(configuration(&env(&root, "{}")).is_none(), "{changes}");
        }
        let path = pair(&root, json!({}));
        for raw in ["null", "[]", r#"{"mcp": []}"#, r#"{"mcp": null}"#, "{bad"] {
            assert!(configuration(&env(&root, raw)).is_none(), "{raw}");
        }
        assert!(configuration(&env(&root, r#"{"skills": {"urls": [1]}}"#)).is_none());
        for kind in ["malformed", "oversize", "public", "symlink", "fifo"] {
            pair(&root, json!({}));
            match kind {
                "malformed" => std::fs::write(&path, "null").unwrap(),
                "oversize" => std::fs::write(&path, " ".repeat(65537)).unwrap(),
                "public" => {
                    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap()
                }
                "symlink" => {
                    std::fs::rename(&path, path.with_extension("target")).unwrap();
                    std::os::unix::fs::symlink(path.with_extension("target"), &path).unwrap();
                }
                _ => {
                    std::fs::remove_file(&path).unwrap();
                    let status = std::process::Command::new("mkfifo")
                        .arg("-m600")
                        .arg(&path)
                        .status()
                        .unwrap();
                    assert!(status.success());
                }
            }
            assert!(configuration(&env(&root, "{}")).is_none(), "{kind}");
            std::fs::remove_file(&path).unwrap();
        }
        let mut relative = env(&root, "{}");
        relative.insert("HOME".into(), String::new());
        relative.insert("XDG_CONFIG_HOME".into(), String::new());
        assert!(configuration(&relative).is_none());
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn the_managed_engine_keeps_away_from_a_foreign_database_without_changing_it() {
        let root = folder("database");
        let mut env = env(&root, "{}");
        env.insert("XDG_DATA_HOME".into(), root.display().to_string());
        let own = managed(&env);
        std::fs::create_dir_all(own.parent().unwrap()).unwrap();
        std::fs::write(&own, "#!/bin/sh\n").unwrap();
        std::fs::set_permissions(&own, std::fs::Permissions::from_mode(0o700)).unwrap();
        assert_eq!(binary(&env), own.display().to_string());
        env.insert("LUMEN_OPENCODE_BIN".into(), "/elsewhere/opencode".into());
        assert_eq!(binary(&env), "/elsewhere/opencode");
        let binary = own.display().to_string();
        let data = root.join("opencode");
        std::fs::create_dir_all(&data).unwrap();
        let foreign = data.join("opencode2.db");
        rusqlite::Connection::open(&foreign)
            .unwrap()
            .execute_batch("CREATE TABLE foreign_session (id TEXT)")
            .unwrap();
        let before = std::fs::read(&foreign).unwrap();
        assert_eq!(
            database("/other/opencode", "opencode2.db", &env),
            "opencode2.db"
        );
        assert_eq!(database(&binary, ":memory:", &env), ":memory:");
        assert_eq!(database(&binary, "missing.db", &env), "missing.db");
        let isolated = data.join("lumen-v1.db").display().to_string();
        assert_eq!(database(&binary, "opencode2.db", &env), isolated);
        assert_eq!(std::fs::read(&foreign).unwrap(), before);
        let shared = data.join("opencode.db");
        rusqlite::Connection::open(&shared)
            .unwrap()
            .execute_batch("CREATE TABLE session (id TEXT)")
            .unwrap();
        assert_eq!(database(&binary, "", &env), "");
        // An absolute configured store is inspected where it is.
        let custom = root.join("custom.db");
        rusqlite::Connection::open(&custom)
            .unwrap()
            .execute_batch("CREATE TABLE foreign_session (id TEXT)")
            .unwrap();
        let configured = custom.display().to_string();
        assert_eq!(database(&binary, &configured, &env), isolated);
        assert!(
            !data.join("lumen-v1.db").exists(),
            "only OpenCode creates its schema"
        );
        // Empty, corrupt, locked and WAL databases are never reset and keep their diagnosis.
        std::fs::remove_file(&shared).unwrap();
        std::fs::write(&shared, "").unwrap();
        assert_eq!(database(&binary, "", &env), "");
        std::fs::write(&shared, "not a database").unwrap();
        assert_eq!(database(&binary, "", &env), "");
        assert_eq!(std::fs::read(&shared).unwrap(), b"not a database");
        std::fs::remove_file(&shared).unwrap();
        let locked = rusqlite::Connection::open(&shared).unwrap();
        locked
            .execute_batch("CREATE TABLE foreign_session (id TEXT); BEGIN EXCLUSIVE; INSERT INTO foreign_session VALUES ('x')")
            .unwrap();
        let started = std::time::Instant::now();
        assert_eq!(database(&binary, "", &env), "");
        assert!(started.elapsed() < Duration::from_secs(1));
        drop(locked);
        std::fs::remove_file(&shared).unwrap();
        let wal = rusqlite::Connection::open(&shared).unwrap();
        wal.execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE foreign_session (id TEXT); CREATE TABLE session (id TEXT)")
            .unwrap();
        assert_eq!(database(&binary, "", &env), "");
        drop(wal);
        std::fs::write(data.join("lumen-v1.db"), "").unwrap();
        assert_eq!(database(&binary, "", &env), isolated);
        assert_eq!(database("/custom/opencode", "", &env), "");
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn startup_failures_are_classified_without_their_text() {
        let summary = startup_summary(
            "exited",
            b"Error: ConfigJSONError at /home/secret/opencode.json",
            12,
            Some(1),
        );
        assert_eq!(
            summary,
            json!({"outcome": "exited", "hint": "invalid_config", "elapsed_ms": 12, "captured_bytes": 52, "exit_code": 1})
        );
        assert!(!summary.to_string().contains("secret"));
        let t = Texts::default();
        assert_eq!(
            startup_message(&t, &summary),
            "OpenCode kann seine Konfiguration nicht laden. Bitte die OpenCode-Konfiguration prüfen; eine Neuinstallation der Engine behebt das nicht. Prozess beendet: Code 1 (exited)."
        );
        assert_eq!(
            startup_summary("start_error", b"", 0, None)["process_error"],
            0
        );
        assert_eq!(
            startup_message(&t, &startup_summary("timeout", b"EADDRINUSE", 0, None)),
            "Die Hintergrund-Engine antwortet nicht. Bitte erneut versuchen."
        );
        assert_eq!(
            listening(b"listening on http://127.0.0.1:4096\n"),
            Some(4096)
        );
        assert_eq!(listening(b"listening on http://127.0.0.1:40"), None);
        for (hint, raw) in [
            ("database", "SQLiteError: /private/profile"),
            (
                "database_schema",
                "Database is not empty and has no session table",
            ),
            ("permission_denied", "EACCES: private-file"),
            ("disk_full", "ENOSPC: secret"),
            ("address_in_use", "EADDRINUSE: private-host"),
            ("tls", "CERTIFICATE_VERIFY_FAILED: secret"),
            ("unknown", "some completely private output"),
        ] {
            let summary = startup_summary("exited", raw.as_bytes(), 100, Some(1));
            assert_eq!(summary["hint"], hint);
            assert!(!summary.to_string().contains(raw));
        }
    }
}

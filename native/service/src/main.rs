//! `lumen-service`: Lumen's one desktop service, a user process per session that does the work the
//! Qt processes leave to Rust: the memory's meaning search (`memory.rs`), the conversations with
//! the OpenCode engines it runs for them (`engine.rs`, `turn.rs`) in the user's persona
//! (`persona.rs`), the connection to the user's Lumen Server (`bridge.rs`) and the notebook core of
//! Lumen Notes (`notebook.rs`).
//!
//! It listens on `$XDG_RUNTIME_DIR/lumen/service.sock` (folder 0700, socket 0600, both the user's)
//! and answers only processes of the same user. A lock file beside the socket keeps one service
//! per user. Each connection carries one JSON request, ended by a newline or by the client closing
//! its side, and gets one JSON answer, or for `engine.turn` and `bridge.receive` a line per event;
//! all carry the protocol version `"v": 1`. Requests name an operation in `"op"`: `hello` (the build
//! identity, the SHA-256 of the running program), `quit`, `memory.search` and the `engine.*`,
//! `persona.*`, `bridge.*`, `notes.*` and the memory's `memory.*` operations (`recall.rs`,
//! `learning.rs`). `lumen-service learning-mcp <event.json>` serves the learning engine's two tools on
//! stdio. The protocol is
//! described in `README.md`; the Qt side's bindings are `files/lumen_service.py` and
//! `files/assistant_backend.py`.
mod bridge;
mod engine;
mod learning;
mod memory;
mod notebook;
mod persona;
mod recall;
mod store;
mod texts;
mod turn;

use std::fs::{File, OpenOptions, Permissions};
use std::io::{BufRead, ErrorKind, Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::mpsc::RecvTimeoutError;
use std::time::Duration;

use serde_json::{Value, json};
use sha2::{Digest, Sha256};

/// The protocol version of every request and answer.
const VERSION: u64 = 1;
/// A window image of 12 MiB travels as base64 in a turn request.
const MAX_INPUT: u64 = 32 * 1024 * 1024;

fn failed<E: std::fmt::Display>(error: E) -> String {
    error.to_string()
}

fn sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(failed)?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0u8; 1 << 16];
    loop {
        let read = file.read(&mut buffer).map_err(failed)?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

/// The C library calls std has no stable form of: the peer check (`UnixStream::peer_cred` is
/// unstable in Rust 1.99), giving freed memory back to the system and tying an engine's life to the
/// service's.
#[allow(unsafe_code)]
mod sys {
    use std::os::fd::AsRawFd;
    use std::os::unix::net::UnixStream;

    /// The engine started by `command` is sent TERM when the service ends, also when it is killed.
    /// The engine thread lives as long as the service, so the signal follows the service itself.
    pub fn end_with_service(command: &mut tokio::process::Command) {
        let service = std::process::id() as libc::pid_t;
        // SAFETY: the closure runs in the child between fork and exec and calls only the
        // async-signal-safe prctl and getppid; it allocates nothing.
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                // The service ended before the signal was set up.
                if libc::getppid() != service {
                    return Err(std::io::Error::from_raw_os_error(libc::ESRCH));
                }
                Ok(())
            });
        }
    }

    pub fn uid() -> u32 {
        // SAFETY: geteuid has no preconditions and cannot fail.
        unsafe { libc::geteuid() }
    }

    /// Returns the heap's free pages to the system; without it about 240 MB of a dropped model
    /// stay resident (279 instead of 21 MB).
    pub fn trim() {
        // SAFETY: malloc_trim has no preconditions; it only releases free heap memory.
        unsafe { libc::malloc_trim(0) };
    }

    /// The user of the process at the other end of a connection.
    pub fn peer(stream: &UnixStream) -> Option<u32> {
        let mut cred = libc::ucred {
            pid: 0,
            uid: 0,
            gid: 0,
        };
        let mut size = size_of::<libc::ucred>() as libc::socklen_t;
        // SAFETY: the descriptor is open for the call; `cred` and `size` describe a writable ucred.
        let result = unsafe {
            libc::getsockopt(
                stream.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                (&raw mut cred).cast(),
                &mut size,
            )
        };
        (result == 0 && size as usize == size_of::<libc::ucred>()).then_some(cred.uid)
    }
}

/// A folder only this user can open: no link, owned by the user, nothing for group or others.
fn private(path: &Path, uid: u32) -> Result<(), String> {
    let meta = std::fs::symlink_metadata(path).map_err(failed)?;
    if meta.is_dir() && meta.uid() == uid && meta.mode() & 0o077 == 0 {
        return Ok(());
    }
    Err(format!(
        "{} must be a folder of this user that only it can open (0700)",
        path.display()
    ))
}

/// `$XDG_RUNTIME_DIR/lumen`, created 0700. Without the session's private runtime folder there is
/// no safe place for the socket, so the service refuses to start rather than guess a shared one.
fn folder(uid: u32) -> Result<PathBuf, String> {
    let runtime = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .ok_or("XDG_RUNTIME_DIR is not set to the session's private runtime folder")?;
    private(&runtime, uid)?;
    let folder = runtime.join("lumen");
    match std::fs::DirBuilder::new().mode(0o700).create(&folder) {
        Err(error) if error.kind() != ErrorKind::AlreadyExists => return Err(failed(error)),
        _ => {}
    }
    private(&folder, uid)?;
    Ok(folder)
}

/// One request, ended by a newline or by the client closing its side, and what the client sent
/// after it (a turn's `cancel` may follow at once).
fn read(stream: &mut UnixStream) -> (Option<Value>, Vec<u8>) {
    let ready = stream.set_nonblocking(false).is_ok()
        && stream
            .set_read_timeout(Some(Duration::from_secs(10)))
            .is_ok()
        && stream
            .set_write_timeout(Some(Duration::from_secs(10)))
            .is_ok();
    if !ready {
        return (None, Vec::new());
    }
    let mut reader = std::io::BufReader::new((&*stream).take(MAX_INPUT + 1));
    let mut data = Vec::new();
    if reader.read_until(b'\n', &mut data).is_err() || data.len() as u64 > MAX_INPUT {
        return (None, Vec::new());
    }
    (serde_json::from_slice(&data).ok(), reader.buffer().to_vec())
}

/// What the main thread is given: a connection of this user, or a meaning search a memory
/// operation of another thread asks for (answered on its channel).
enum Incoming {
    Connection(UnixStream),
    Search(Value, std::sync::mpsc::Sender<Value>),
}

/// The main thread's queue, for the memory operations' meaning searches.
static INCOMING: std::sync::OnceLock<std::sync::Mutex<std::sync::mpsc::Sender<Incoming>>> =
    std::sync::OnceLock::new();

/// One `memory.search` on the main thread, `None` when it does not answer within `wait`.
fn search(request: Value, wait: Duration) -> Option<Value> {
    let (sender, answer) = std::sync::mpsc::channel();
    INCOMING
        .get()?
        .lock()
        .ok()?
        .send(Incoming::Search(request, sender))
        .ok()?;
    answer.recv_timeout(wait).ok()
}

/// A JSON request to the paired server for a memory operation (`lumen_connect.request`): the answer
/// of a 2xx status, every other outcome as the `ValueError`/`OSError` urllib raised.
fn server(
    pairing: &serde_json::Map<String, Value>,
    path: &str,
    body: Option<&notebook::Py>,
    timeout: u64,
) -> notebook::Result<notebook::Py> {
    use notebook::{Failure, python};
    let text = |key: &str| {
        pairing
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned()
    };
    let connection = bridge::Connection {
        server: text("server"),
        token: text("token"),
        ca_file: text("ca_file"),
        home: std::env::var_os("HOME").map(Into::into),
    };
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| Failure::Value(e.to_string()))?;
    let body = body.map(|b| python::dumps(b, true).into_bytes());
    let reply = runtime
        .block_on(bridge::request(
            &connection,
            path,
            body,
            Duration::from_secs(timeout),
        ))
        .map_err(|failure| {
            let answer = failure.answer();
            match answer["failure"].as_str() {
                Some("too_large") => Failure::Value("Serverantwort ist zu groß.".into()),
                _ => Failure::Os {
                    errno: answer["errno"].as_i64().unwrap_or(libc::EIO.into()) as i32,
                    filename: None,
                    path: false,
                },
            }
        })?;
    if !(200..300).contains(&reply.status) {
        return Err(Failure::Value(format!(
            "HTTP Error {}: {}",
            reply.status, reply.reason
        )));
    }
    std::str::from_utf8(&reply.body)
        .ok()
        .and_then(python::loads)
        .ok_or_else(|| Failure::Value("Expecting value: line 1 column 1 (char 0)".into()))
}

/// A memory operation with what its request brings: the state folder (`store`, the folder or its
/// `lumen.sqlite3`), the view's environment (`env`, or `engine.env` of an engine request) and texts.
pub(crate) fn memory_request<T>(
    request: &Value,
    work: impl FnOnce(&notebook::Store, &recall::Ctx) -> notebook::Result<T>,
) -> notebook::Result<T> {
    let store = request["store"].as_str().unwrap_or_default();
    let directory = Path::new(store);
    let directory = if directory.file_name().is_some_and(|n| n == "lumen.sqlite3") {
        directory.parent().unwrap_or(directory)
    } else {
        directory
    };
    let vars = engine::strings(if request["env"].is_object() {
        &request["env"]
    } else {
        &request["engine"]["env"]
    })
    .unwrap_or_default();
    let env = notebook::Env::default();
    let t = texts::Texts::of(request);
    let store = notebook::Store {
        directory: directory.to_path_buf(),
    };
    work(
        &store,
        &recall::Ctx {
            env: &env,
            t: &t,
            vars: &vars,
            server: &server,
            retrieve: &recall::retrieve_local,
            search: &search,
        },
    )
}

/// Serves one `memory.*` connection on its own thread: `{"result": …}` or a refusal as `notes.*`
/// answers it.
fn memory_serve(mut stream: UnixStream, request: Value) {
    use notebook::{Py, python};
    let py = notebook::py(&request);
    let mut answer = match memory_request(&request, |_, ctx| recall::answer(&py, ctx)) {
        Ok(result) => Py::Dict(vec![("result".into(), result)]),
        Err(failure) => notebook::refusal(&request, &failure),
    };
    answer.set("v", Py::int(VERSION as i64));
    let mut line = python::dumps(&answer, false);
    line.push('\n');
    let _ = stream.set_write_timeout(Some(Duration::from_secs(60)));
    let _ = stream.write_all(line.as_bytes());
}

/// What the engine thread is given: a connection with its request, or the order to end every
/// engine (answered once they have ended).
enum Job {
    Connection(UnixStream, Value, Vec<u8>),
    Shutdown(std::sync::mpsc::Sender<()>),
}

/// The engines, turns and server requests run on one thread of their own, so they never wait for
/// the memory search and the engines' parent thread lives as long as the service. TERM, INT or HUP end every
/// engine before the service ends, and so does the end of the session: when its runtime folder is
/// removed or another service has taken the socket.
fn engines(
    folder: &Path,
    socket: PathBuf,
) -> Result<tokio::sync::mpsc::UnboundedSender<Job>, String> {
    let plugin = engine::plugin(folder)?;
    let ours = std::fs::metadata(&socket).map_err(failed)?.ino();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(failed)?;
    let (sender, mut jobs) = tokio::sync::mpsc::unbounded_channel();
    std::thread::spawn(move || {
        let local = tokio::task::LocalSet::new();
        local.block_on(&runtime, async move {
            use tokio::signal::unix::{SignalKind, signal};
            let engines = std::rc::Rc::new(engine::Engines::new(plugin));
            let (tidy, place) = (engines.clone(), socket.clone());
            tokio::task::spawn_local(async move {
                loop {
                    // Stopped engines end within seconds; idle ones after ten minutes.
                    tokio::time::sleep(Duration::from_secs(2)).await;
                    if std::fs::metadata(&place).map(|m| m.ino()).ok() != Some(ours) {
                        tidy.shutdown().await;
                        std::process::exit(0);
                    }
                    tidy.tidy().await;
                }
            });
            let (Ok(mut term), Ok(mut interrupt), Ok(mut hangup)) = (
                signal(SignalKind::terminate()),
                signal(SignalKind::interrupt()),
                signal(SignalKind::hangup()),
            ) else {
                return;
            };
            loop {
                let job = tokio::select! {
                    job = jobs.recv() => job,
                    _ = term.recv() => None,
                    _ = interrupt.recv() => None,
                    _ = hangup.recv() => None,
                };
                match job {
                    Some(Job::Connection(stream, request, leftover)) => {
                        tokio::task::spawn_local(engine_request(
                            engines.clone(),
                            stream,
                            request,
                            leftover,
                        ));
                    }
                    Some(Job::Shutdown(done)) => {
                        engines.shutdown().await;
                        let _ = done.send(());
                        return;
                    }
                    None => {
                        engines.shutdown().await;
                        let _ = std::fs::remove_file(&socket);
                        std::process::exit(0);
                    }
                }
            }
        });
    });
    Ok(sender)
}

async fn engine_request(
    engines: std::rc::Rc<engine::Engines>,
    stream: UnixStream,
    request: Value,
    leftover: Vec<u8>,
) {
    let Ok(stream) = stream
        .set_nonblocking(true)
        .and_then(|()| tokio::net::UnixStream::from_std(stream))
    else {
        return;
    };
    let op = request["op"].as_str().unwrap_or_default().to_owned();
    if op.starts_with("bridge.") {
        return bridge::serve(stream, request).await;
    }
    if op == "engine.turn" {
        return turn::turn(engines, stream, request, leftover).await;
    }
    if op == "memory.learn" {
        return learning::learn(engines, stream, request, leftover).await;
    }
    let mut answer = if op == "engine.info" {
        turn::info(&request)
    } else if op.starts_with("persona.") {
        persona::once(&op, &request, &texts::Texts::of(&request)).await
    } else {
        turn::once(&engines, &op, &request, &texts::Texts::of(&request)).await
    };
    answer["v"] = json!(VERSION);
    let mut line = answer.to_string();
    line.push('\n');
    let mut stream = stream;
    use tokio::io::AsyncWriteExt;
    let _ = stream.write_all(line.as_bytes()).await;
    let _ = stream.shutdown().await;
}

/// The answer to one request, and whether the service is to quit. A request in another protocol
/// version gets an error and nothing is done.
fn respond(memory: &mut memory::Memory, build: &str, request: Option<Value>) -> (Value, bool) {
    let Some(Value::Object(mut request)) = request else {
        return (json!({"v": VERSION, "error": "invalid_request"}), false);
    };
    if request.get("v") != Some(&json!(VERSION)) {
        return (json!({"v": VERSION, "error": "unsupported_version"}), false);
    }
    match request.remove("op").as_ref().and_then(Value::as_str) {
        Some("hello") => (json!({"v": VERSION, "build": build}), false),
        Some("quit") => (json!({"v": VERSION}), true),
        Some("pairing.read") => {
            let mut answer = engine::read_pairing(&request);
            answer["v"] = json!(VERSION);
            (answer, false)
        }
        Some("memory.search") => {
            let mut answer = memory.search(Value::Object(request));
            answer["v"] = json!(VERSION);
            (answer, false)
        }
        _ => (json!({"v": VERSION, "error": "unknown_op"}), false),
    }
}

fn serve() -> Result<(), String> {
    let uid = sys::uid();
    let folder = folder(uid)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .mode(0o600)
        .open(folder.join("service.lock"))
        .map_err(failed)?;
    match lock.try_lock() {
        Ok(()) => {}
        // Another service runs for this user; it answers.
        Err(std::fs::TryLockError::WouldBlock) => return Ok(()),
        Err(std::fs::TryLockError::Error(error)) => return Err(failed(error)),
    }
    // What runs, even when an update has replaced the installed program since.
    let build = sha256(Path::new("/proc/self/exe"))?;
    let socket = folder.join("service.sock");
    // Left behind by a service that was killed: the lock says none runs.
    let _ = std::fs::remove_file(&socket);
    let listener = UnixListener::bind(&socket).map_err(failed)?;
    std::fs::set_permissions(&socket, Permissions::from_mode(0o600)).map_err(failed)?;
    let engines = engines(&folder, socket.clone())?;
    // A thread waits for connections and hands those of this user over at once; requests that
    // arrive while the model loads wait in the channel. Others are closed unanswered.
    let (sender, connections) = std::sync::mpsc::channel();
    let _ = INCOMING.set(std::sync::Mutex::new(sender.clone()));
    std::thread::spawn(move || {
        for stream in listener.incoming().flatten() {
            if sys::peer(&stream) == Some(uid) && sender.send(Incoming::Connection(stream)).is_err()
            {
                break;
            }
        }
    });
    let mut memory = memory::Memory::new();
    loop {
        // Without a loaded model nothing is left to do until the next request.
        let next = match memory.wait() {
            Some(wait) => connections.recv_timeout(wait),
            None => connections
                .recv()
                .map_err(|_| RecvTimeoutError::Disconnected),
        };
        match next {
            Ok(Incoming::Search(request, answer)) => {
                let _ = answer.send(memory.search(request));
            }
            Ok(Incoming::Connection(mut stream)) => {
                let (request, leftover) = read(&mut stream);
                // Notebook requests wait for locks and the disk: each runs on a thread of its own.
                if let Some(request) = request.as_ref().filter(|r| {
                    r["v"] == json!(VERSION)
                        && r["op"].as_str().is_some_and(|op| op.starts_with("notes."))
                }) {
                    let request = request.clone();
                    let _ = std::thread::Builder::new()
                        .stack_size(64 << 20)
                        .spawn(move || notebook::serve(stream, request, leftover));
                    continue;
                }
                // Memory operations wait for locks, the disk and the server: each runs on a thread.
                if let Some(request) = request.as_ref().filter(|r| {
                    r["v"] == json!(VERSION)
                        && r["op"].as_str().is_some_and(|op| {
                            op.starts_with("memory.")
                                && op != "memory.search"
                                && op != "memory.learn"
                        })
                }) {
                    let request = request.clone();
                    let _ = std::thread::Builder::new()
                        .stack_size(64 << 20)
                        .spawn(move || memory_serve(stream, request));
                    continue;
                }
                if let Some(request) = request.as_ref().filter(|r| {
                    r["v"] == json!(VERSION)
                        && r["op"].as_str().is_some_and(|op| {
                            op == "memory.learn"
                                || ["engine.", "persona.", "bridge."]
                                    .iter()
                                    .any(|prefix| op.starts_with(prefix))
                        })
                }) {
                    let _ = engines.send(Job::Connection(stream, request.clone(), leftover));
                    continue;
                }
                let (answer, quit) = respond(&mut memory, &build, request);
                if quit {
                    // Socket and lock go before the answer, so a service started after it
                    // finds both free.
                    let _ = std::fs::remove_file(&socket);
                    let _ = lock.unlock();
                }
                let _ = stream.write_all(answer.to_string().as_bytes());
                if quit {
                    drop(stream);
                    // Every engine ends (TERM, then KILL after five seconds) before the service.
                    let (done, ended) = std::sync::mpsc::channel();
                    if engines.send(Job::Shutdown(done)).is_ok() {
                        let _ = ended.recv_timeout(Duration::from_secs(15));
                    }
                    return Ok(());
                }
            }
            Err(RecvTimeoutError::Timeout) => memory.idle(),
            Err(RecvTimeoutError::Disconnected) => break,
        }
    }
    let _ = std::fs::remove_file(&socket);
    let (done, ended) = std::sync::mpsc::channel();
    if engines.send(Job::Shutdown(done)).is_ok() {
        let _ = ended.recv_timeout(Duration::from_secs(15));
    }
    Ok(())
}

fn main() -> ExitCode {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    if let [command, event] = &arguments[..]
        && command == "learning-mcp"
    {
        return match learning::mcp(Path::new(event)) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("lumen-service learning-mcp: {error}");
                ExitCode::FAILURE
            }
        };
    }
    if !arguments.is_empty() {
        eprintln!("usage: lumen-service (Lumen starts it on demand)");
        return ExitCode::from(2);
    }
    match serve() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("lumen-service: {error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn another_protocol_version_gets_an_error_and_nothing_is_done() {
        let mut memory = memory::Memory::new();
        for request in [
            json!({"v": 2, "op": "quit"}),
            json!({"op": "quit"}),
            json!({"v": "1", "op": "quit"}),
        ] {
            let (answer, quit) = respond(&mut memory, "b", Some(request));
            assert_eq!(
                (answer, quit),
                (json!({"v": 1, "error": "unsupported_version"}), false)
            );
        }
        let search = json!({"v": 2, "op": "memory.search", "home": "/m", "checksums": ["a", "b", "c"],
            "path": "/m/i.sqlite3", "query": "q", "entries": []});
        assert_eq!(
            respond(&mut memory, "b", Some(search)).0["error"],
            "unsupported_version"
        );
        assert_eq!(memory.wait(), None);
    }

    #[test]
    fn operations_answer_in_version_one() {
        let mut memory = memory::Memory::new();
        let mut ask = |request| respond(&mut memory, "abc", Some(request));
        assert_eq!(
            ask(json!({"v": 1, "op": "hello"})),
            (json!({"v": 1, "build": "abc"}), false)
        );
        assert_eq!(ask(json!({"v": 1, "op": "quit"})), (json!({"v": 1}), true));
        assert_eq!(
            ask(json!({"v": 1, "op": "nothing"})).0,
            json!({"v": 1, "error": "unknown_op"})
        );
        assert_eq!(
            ask(json!({"v": 1, "op": "memory.search"})).0,
            json!({"v": 1, "mode": "text", "reason": "unavailable", "scores": []})
        );
        assert_eq!(
            respond(&mut memory, "abc", None).0,
            json!({"v": 1, "error": "invalid_request"})
        );
        assert_eq!(
            respond(&mut memory, "abc", Some(json!([1]))).0["error"],
            "invalid_request"
        );
    }

    #[test]
    fn only_a_private_folder_of_this_user_is_used() {
        let root =
            std::env::temp_dir().join(format!("lumen-service-folder-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir(&root).unwrap();
        let uid = sys::uid();
        std::fs::set_permissions(&root, Permissions::from_mode(0o700)).unwrap();
        assert!(private(&root, uid).is_ok());
        assert!(private(&root, uid + 1).is_err());
        std::fs::set_permissions(&root, Permissions::from_mode(0o750)).unwrap();
        assert!(private(&root, uid).is_err());
        std::fs::set_permissions(&root, Permissions::from_mode(0o700)).unwrap();
        let link = root.with_extension("link");
        let _ = std::fs::remove_file(&link);
        std::os::unix::fs::symlink(&root, &link).unwrap();
        assert!(private(&link, uid).is_err());
        std::fs::remove_file(&link).unwrap();
        std::fs::remove_dir(&root).unwrap();
    }

    #[test]
    fn a_request_ends_with_a_newline_or_with_the_clients_side() {
        let (mut client, mut service) = UnixStream::pair().unwrap();
        client
            .write_all(b"{\"v\":1,\"op\":\"engine.turn\"}\n{\"op\":\"cancel\"}\n")
            .unwrap();
        let (request, leftover) = read(&mut service);
        assert_eq!(request, Some(json!({"v": 1, "op": "engine.turn"})));
        assert_eq!(leftover, b"{\"op\":\"cancel\"}\n");
        let (mut client, mut service) = UnixStream::pair().unwrap();
        client.write_all(b"{\"v\":1,\"op\":\"hello\"}").unwrap();
        client.shutdown(std::net::Shutdown::Write).unwrap();
        assert_eq!(
            read(&mut service),
            (Some(json!({"v": 1, "op": "hello"})), Vec::new())
        );
    }

    #[test]
    fn a_connection_names_the_user_at_the_other_end() {
        let (a, _b) = UnixStream::pair().unwrap();
        assert_eq!(sys::peer(&a), Some(sys::uid()));
    }
}

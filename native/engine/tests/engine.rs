//! The client and the reply loop against a deterministic local engine.
use lumen_engine::{Client, Error, FAILED, Observer, StatusCode, TIMEOUT, response};
use serde_json::{Value, json};
use std::{
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
    time::Duration,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    time::Instant,
};

/// What the local engine sends back for one request.
enum Reply {
    Json(Value),
    Raw(u16, &'static str, Vec<u8>),
    /// An event stream: each piece after a pause, then the flag is raised and the connection closes.
    Stream(Vec<Vec<u8>>, Option<Arc<AtomicBool>>),
}

struct Request {
    method: String,
    target: String,
    authorization: String,
}

type Handler = dyn Fn(&Request) -> Reply + Send + Sync;

/// An HTTP/1.1 engine on a free loopback port; every answer closes its connection.
async fn engine(handler: Arc<Handler>) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = format!("http://{}", listener.local_addr().unwrap());
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            tokio::spawn(answer(stream, handler.clone()));
        }
    });
    address
}

async fn answer(mut stream: TcpStream, handler: Arc<Handler>) {
    let mut raw = Vec::new();
    let mut buffer = [0; 4096];
    let head = loop {
        if let Some(at) = raw.windows(4).position(|w| w == b"\r\n\r\n") {
            break at;
        }
        match stream.read(&mut buffer).await {
            Ok(0) | Err(_) => return,
            Ok(n) => raw.extend_from_slice(&buffer[..n]),
        }
    };
    let text = String::from_utf8_lossy(&raw[..head]).into_owned();
    let mut lines = text.split("\r\n");
    let mut first = lines.next().unwrap_or_default().split(' ');
    let (method, target) = (
        first.next().unwrap_or_default(),
        first.next().unwrap_or_default(),
    );
    let header = |name: &str| {
        text.split("\r\n")
            .find_map(|line| {
                line.split_once(':')
                    .filter(|(key, _)| key.eq_ignore_ascii_case(name))
                    .map(|(_, value)| value.trim().to_owned())
            })
            .unwrap_or_default()
    };
    let length: usize = header("content-length").parse().unwrap_or(0);
    let mut body = raw[head + 4..].to_vec();
    while body.len() < length {
        match stream.read(&mut buffer).await {
            Ok(0) | Err(_) => return,
            Ok(n) => body.extend_from_slice(&buffer[..n]),
        }
    }
    let request = Request {
        method: method.into(),
        target: target.into(),
        authorization: header("authorization"),
    };
    let (status, kind, pieces, sent) = match handler(&request) {
        Reply::Json(value) => (
            200,
            "application/json",
            vec![value.to_string().into_bytes()],
            None,
        ),
        Reply::Raw(status, kind, body) => (status, kind, vec![body], None),
        Reply::Stream(pieces, sent) => (200, "text/event-stream", pieces, sent),
    };
    let streamed = kind == "text/event-stream";
    let mut head = format!("HTTP/1.1 {status} X\r\nContent-Type: {kind}\r\nConnection: close\r\n");
    if !streamed {
        head += &format!("Content-Length: {}\r\n", pieces[0].len());
    }
    head += "\r\n";
    if stream.write_all(head.as_bytes()).await.is_err() {
        return;
    }
    for piece in pieces {
        if streamed {
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        // Split inside UTF-8, as a real network packet may do.
        for bytes in piece.chunks(if streamed { 7 } else { piece.len().max(1) }) {
            if stream.write_all(bytes).await.is_err() || stream.flush().await.is_err() {
                return;
            }
        }
    }
    if let Some(sent) = sent {
        sent.store(true, Ordering::SeqCst);
    }
}

fn frames(values: &[Value]) -> Vec<Vec<u8>> {
    values
        .iter()
        .map(|value| format!("data: {value}\r\n\r\n").into_bytes())
        .collect()
}

fn client(address: &str) -> Client {
    Client::attached(address, "test-only").unwrap()
}

#[derive(Default)]
struct Watch {
    values: Mutex<Vec<String>>,
    revoked: AtomicBool,
    stop_after_text: bool,
    /// `waiting` answers `true` this many times.
    hold: AtomicUsize,
    asked: AtomicUsize,
}
impl Observer for Watch {
    type Error = Error;
    async fn check(&self) -> Result<(), Error> {
        if self.revoked.load(Ordering::SeqCst) {
            Err(Error(StatusCode::FORBIDDEN, "revoked"))
        } else {
            Ok(())
        }
    }
    async fn text(&self, text: &str) -> Result<(), Error> {
        self.values.lock().unwrap().push(text.into());
        if self.stop_after_text {
            self.revoked.store(true, Ordering::SeqCst);
        }
        Ok(())
    }
    async fn waiting(&self) -> Result<bool, Error> {
        self.asked.fetch_add(1, Ordering::SeqCst);
        let held = self.hold.load(Ordering::SeqCst) > 0;
        if held {
            self.hold.fetch_sub(1, Ordering::SeqCst);
        }
        Ok(held)
    }
}

/// The engine of the reply-loop tests: a first stream with foreign and private parts, then a
/// second one with a repeated delta, after which the answer is complete.
#[derive(Default)]
struct Peer {
    done: Arc<AtomicBool>,
    starts: AtomicUsize,
    streams: AtomicUsize,
}

fn peer(state: Arc<Peer>) -> Arc<Handler> {
    Arc::new(move |request: &Request| {
        assert_eq!(request.authorization, "Basic b3BlbmNvZGU6dGVzdC1vbmx5");
        match request.target.as_str() {
            "/event" => {
                let stream = state.streams.fetch_add(1, Ordering::SeqCst);
                let values = if stream == 0 {
                    vec![
                        json!({"type":"message.updated","properties":{"info":{"id":"answer","sessionID":"s","role":"assistant"}}}),
                        json!({"type":"message.part.updated","properties":{"part":{"id":"secret","messageID":"answer","sessionID":"s","type":"reasoning","text":"PRIVATE_REASONING"}}}),
                        json!({"type":"message.part.updated","properties":{"part":{"id":"a","messageID":"answer","sessionID":"other","type":"text","text":"FOREIGN"}}}),
                        json!({"type":"message.part.updated","properties":{"part":{"id":"a","messageID":"answer","sessionID":"s","type":"text","text":"Hallo"}}}),
                    ]
                } else {
                    vec![
                        json!({"type":"message.part.delta","id":"delta-once","data":{"sessionID":"s","messageID":"answer","partID":"a","field":"text","delta":" 🌍"}});
                        2
                    ]
                };
                Reply::Stream(frames(&values), (stream > 0).then(|| state.done.clone()))
            }
            "/session/s/prompt_async" => {
                state.starts.fetch_add(1, Ordering::SeqCst);
                Reply::Json(json!({}))
            }
            "/session/s/message" => Reply::Json(if state.done.load(Ordering::SeqCst) {
                json!([{"info":{"id":"answer","sessionID":"s","role":"assistant","finish":"stop","time":{"completed":1}},"parts":[{"id":"a","sessionID":"s","messageID":"answer","type":"text","text":"Hallo 🌍"}]}])
            } else {
                json!([{"info":{"id":"answer","sessionID":"s","role":"assistant","finish":"tool-calls","time":{"completed":1}},"parts":[{"id":"a","sessionID":"s","messageID":"answer","type":"text","text":"Intermediate tool result"}]}])
            }),
            "/session/status" => Reply::Json(
                json!({"s":{"type":if state.done.load(Ordering::SeqCst){"idle"}else{"busy"}}}),
            ),
            other => panic!("unexpected request {other}"),
        }
    })
}

#[tokio::test]
async fn stream_reconnect_keeps_one_prompt_and_final_text() {
    let state = Arc::new(Peer::default());
    let engine = client(&engine(peer(state.clone())).await);
    let watch = Watch::default();
    let deadline = Instant::now() + Duration::from_secs(4);
    let value = response(&engine, "/session/s", json!({}), deadline, true, &watch)
        .await
        .unwrap_or_else(|e| panic!("{} {}", e.0, e.1));
    assert_eq!(value["parts"][0]["text"], "Hallo 🌍");
    assert_eq!(state.starts.load(Ordering::SeqCst), 1);
    assert!(state.streams.load(Ordering::SeqCst) >= 2);
    let values = watch.values.lock().unwrap();
    assert!(values.iter().any(|v| v == "Hallo"));
    assert!(values.iter().any(|v| v == "Hallo 🌍"));
    assert!(values.iter().all(|v| !v.contains("PRIVATE_REASONING")
        && !v.contains("FOREIGN")
        && !v.contains("🌍 🌍")));
}

#[tokio::test]
async fn revoked_stream_cannot_emit_a_later_result() {
    let state = Arc::new(Peer::default());
    let engine = client(&engine(peer(state.clone())).await);
    let watch = Watch {
        stop_after_text: true,
        ..Watch::default()
    };
    let deadline = Instant::now() + Duration::from_secs(4);
    let error = response(&engine, "/session/s", json!({}), deadline, true, &watch)
        .await
        .unwrap_err();
    assert_eq!(error.0, StatusCode::FORBIDDEN);
    assert_eq!(state.starts.load(Ordering::SeqCst), 1);
    let values = watch.values.lock().unwrap();
    assert_eq!(values.len(), 1);
    assert_ne!(values[0], "Hallo 🌍");
}

#[tokio::test]
async fn deadline_stops_a_live_stream() {
    let state = Arc::new(Peer::default());
    let engine = client(&engine(peer(state.clone())).await);
    let start = Instant::now();
    let error = response(
        &engine,
        "/session/s",
        json!({}),
        start + Duration::from_millis(120),
        true,
        &Watch::default(),
    )
    .await
    .unwrap_err();
    assert_eq!(error, TIMEOUT);
    assert!(start.elapsed() < Duration::from_millis(750));
    assert_eq!(state.starts.load(Ordering::SeqCst), 1);
}

/// A session that already holds a finished answer to an earlier prompt; the reply to the new
/// prompt appears only after a while.
struct Continuing {
    prompts: AtomicUsize,
    polls: AtomicUsize,
    /// The reply to the new prompt carries this text and finish.
    text: Option<&'static str>,
}
fn continuing(state: Arc<Continuing>) -> Arc<Handler> {
    Arc::new(move |request: &Request| match request.target.as_str() {
        "/event" => Reply::Raw(404, "application/json", b"{}".to_vec()),
        "/session/s/prompt_async" => {
            state.prompts.fetch_add(1, Ordering::SeqCst);
            Reply::Json(json!({}))
        }
        "/session/s/message" => {
            let polls = state.polls.fetch_add(1, Ordering::SeqCst);
            let mut rows = vec![
                json!({"info":{"id":"q1","sessionID":"s","role":"user"},"parts":[{"type":"text","text":"Erste Frage"}]}),
                json!({"info":{"id":"a1","sessionID":"s","role":"assistant","parentID":"q1","finish":"stop","time":{"completed":1}},"parts":[{"id":"p1","sessionID":"s","messageID":"a1","type":"text","text":"Alte Antwort"}]}),
                json!({"info":{"id":"q2","sessionID":"s","role":"user"},"parts":[{"type":"text","text":"Neue Frage"}]}),
            ];
            if polls >= 2 {
                let parts = state.text.map_or(json!([]), |text| {
                    json!([{"id":"p2","sessionID":"s","messageID":"a2","type":"text","text":text}])
                });
                rows.push(json!({"info":{"id":"a2","sessionID":"s","role":"assistant","parentID":"q2","finish":"stop","time":{"completed":2}},"parts":parts}));
            }
            Reply::Json(json!(rows))
        }
        "/session/status" => Reply::Json(json!({})),
        other => panic!("unexpected request {other}"),
    })
}

#[tokio::test]
async fn continuing_session_ignores_the_earlier_answer() {
    let state = Arc::new(Continuing {
        prompts: AtomicUsize::new(0),
        polls: AtomicUsize::new(0),
        text: Some("Neue Antwort"),
    });
    let engine = client(&engine(continuing(state.clone())).await);
    let watch = Watch::default();
    let deadline = Instant::now() + Duration::from_secs(6);
    let payload = json!({"messageID":"q2","parts":[{"type":"text","text":"Neue Frage"}]});
    let value = response(&engine, "/session/s", payload, deadline, true, &watch)
        .await
        .unwrap();
    assert_eq!(value["info"]["id"], "a2");
    assert_eq!(state.prompts.load(Ordering::SeqCst), 1);
    assert!(state.polls.load(Ordering::SeqCst) >= 3);
    assert!(
        watch
            .values
            .lock()
            .unwrap()
            .iter()
            .all(|v| !v.contains("Alte Antwort"))
    );
}

#[tokio::test]
async fn empty_reply_completes_only_for_a_named_prompt() {
    for named in [true, false] {
        let state = Arc::new(Continuing {
            prompts: AtomicUsize::new(0),
            polls: AtomicUsize::new(2),
            text: None,
        });
        let engine = client(&engine(continuing(state.clone())).await);
        let payload = if named {
            json!({"messageID":"q2"})
        } else {
            json!({})
        };
        let result = response(
            &engine,
            "/session/s",
            payload,
            Instant::now() + Duration::from_millis(1500),
            true,
            &Watch::default(),
        )
        .await;
        if named {
            assert_eq!(result.unwrap()["info"]["id"], "a2");
        } else {
            // Without a named prompt an empty last reply is no answer: the loop waits until its
            // deadline.
            assert_eq!(result.unwrap_err(), TIMEOUT);
        }
        assert_eq!(state.prompts.load(Ordering::SeqCst), 1);
    }
}

#[tokio::test]
async fn waiting_holds_completion() {
    let state = Arc::new(Continuing {
        prompts: AtomicUsize::new(0),
        polls: AtomicUsize::new(2),
        text: Some("Neue Antwort"),
    });
    let engine = client(&engine(continuing(state.clone())).await);
    let watch = Watch {
        hold: AtomicUsize::new(2),
        ..Watch::default()
    };
    let started = Instant::now();
    let value = response(
        &engine,
        "/session/s",
        json!({"messageID":"q2"}),
        Instant::now() + Duration::from_secs(6),
        true,
        &watch,
    )
    .await
    .unwrap();
    assert_eq!(value["info"]["id"], "a2");
    // Two held polls, one second apart, before the completing one.
    assert_eq!(watch.asked.load(Ordering::SeqCst), 3);
    assert!(started.elapsed() >= Duration::from_secs(2));
    assert_eq!(state.prompts.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn directory_page_and_limit_shape_every_request() {
    let targets = Arc::new(Mutex::new(Vec::new()));
    let seen = targets.clone();
    let address = engine(Arc::new(move |request: &Request| {
        seen.lock()
            .unwrap()
            .push((request.method.clone(), request.target.clone()));
        let path = request.target.split('?').next().unwrap_or_default();
        match path {
            "/event" => Reply::Raw(404, "application/json", b"{}".to_vec()),
            "/global/health" => Reply::Json(json!({"healthy":true})),
            "/session/s/prompt_async" => Reply::Json(json!({})),
            "/session/s/message" => Reply::Json(json!([
                {"info":{"id":"a","sessionID":"s","role":"assistant","parentID":"m","finish":"stop","time":{"completed":1}},"parts":[{"id":"p","sessionID":"s","messageID":"a","type":"text","text":"ok"}]}
            ])),
            "/session/status" => Reply::Json(json!({})),
            "/large" => Reply::Json(json!("x".repeat(64))),
            "/refused" => Reply::Raw(404, "application/json", br#"{"data":{"message":"Session not found"}}"#.to_vec()),
            "/html" => Reply::Raw(500, "text/html", b"<html>".to_vec()),
            "/html-ok" => Reply::Raw(200, "text/html", b"<html>".to_vec()),
            other => panic!("unexpected request {other}"),
        }
    }))
    .await;
    let engine = client(&address).directory("/home/ü x").page(100);
    assert!(engine.health(Duration::from_secs(1)).await);
    response(
        &engine,
        "/session/s",
        json!({"messageID":"m"}),
        Instant::now() + Duration::from_secs(4),
        true,
        &Watch::default(),
    )
    .await
    .unwrap();
    let directory = "directory=%2Fhome%2F%C3%BC%20x";
    let targets = targets.lock().unwrap().clone();
    for (method, target) in [
        ("GET", format!("/global/health?{directory}")),
        ("GET", format!("/event?{directory}")),
        ("POST", format!("/session/s/prompt_async?{directory}")),
        ("GET", format!("/session/s/message?limit=100&{directory}")),
        ("GET", format!("/session/status?{directory}")),
    ] {
        assert!(
            targets.contains(&(method.into(), target.clone())),
            "{method} {target} in {targets:?}"
        );
    }
    let small = client(&address).limit(32);
    assert_eq!(
        small
            .request(lumen_engine::Method::GET, "/large", None)
            .await
            .unwrap_err(),
        FAILED
    );
    assert!(
        client(&address)
            .request(lumen_engine::Method::GET, "/large", None)
            .await
            .is_ok()
    );
    let plain = client(&address);
    assert_eq!(
        plain
            .call(lumen_engine::Method::GET, "/refused", None)
            .await
            .unwrap(),
        (
            StatusCode::NOT_FOUND,
            json!({"data":{"message":"Session not found"}})
        )
    );
    assert_eq!(
        plain
            .call(lumen_engine::Method::GET, "/html", None)
            .await
            .unwrap(),
        (StatusCode::INTERNAL_SERVER_ERROR, Value::Null)
    );
    assert_eq!(
        plain
            .call(lumen_engine::Method::GET, "/html-ok", None)
            .await
            .unwrap_err(),
        FAILED
    );
    assert_eq!(
        plain
            .request(lumen_engine::Method::GET, "/refused", None)
            .await
            .unwrap_err(),
        FAILED
    );
    // `raw` hands over any answer as it came, for the desktop's diagnosis.
    let (status, kind, body) = plain
        .raw(lumen_engine::Method::GET, "/html-ok", None)
        .await
        .unwrap();
    assert_eq!(
        (status, kind.starts_with("text/html"), body.is_empty()),
        (StatusCode::OK, true, false)
    );
    assert_eq!(
        small
            .raw(lumen_engine::Method::GET, "/large", None)
            .await
            .unwrap_err(),
        FAILED
    );
}

#[test]
fn only_a_loopback_engine_is_attached() {
    for url in [
        "https://127.0.0.1:4096/",
        "http://localhost:4096/",
        "http://127.0.0.1/",
        "http://127.0.0.1:4096/api",
        "http://127.0.0.1:4096/?a=1",
        "http://user:pw@127.0.0.1:4096/",
        "http://example.invalid:4096/",
    ] {
        assert_eq!(Client::attached(url, "pw").err(), Some(FAILED), "{url}");
    }
    assert!(Client::attached("http://127.0.0.1:4096", "").is_err());
    assert!(Client::attached("http://127.0.0.1:4096", &"p".repeat(257)).is_err());
    let attached = Client::attached("http://127.0.0.1:4096/", "pw").unwrap();
    assert_eq!(attached.url(), "http://127.0.0.1:4096");
}

fn gone(pid: i32) -> bool {
    std::fs::read_to_string(format!("/proc/{pid}/stat")).map_or(true, |stat| {
        stat.rsplit(") ")
            .next()
            .is_some_and(|rest| rest.starts_with('Z'))
    })
}

/// A shell that starts a long-running tool and prints its process ID, like an engine running a
/// command.
async fn shell(group: bool) -> (tokio::process::Child, i32) {
    let mut command = tokio::process::Command::new("/bin/sh");
    command
        .args(["-c", "sleep 60 & echo $!; wait"])
        .stdout(std::process::Stdio::piped());
    if group {
        command.process_group(0);
    }
    let mut child = command.spawn().unwrap();
    let mut stdout = child.stdout.take().unwrap();
    let mut line = Vec::new();
    let mut byte = [0];
    while stdout.read(&mut byte).await.unwrap() == 1 && byte[0] != b'\n' {
        line.push(byte[0]);
    }
    (child, String::from_utf8(line).unwrap().parse().unwrap())
}

#[tokio::test]
async fn group_reap_ends_the_tools_of_the_engine() {
    let (mut child, tool) = shell(true).await;
    let started = Instant::now();
    lumen_engine::reap(&mut child, true).await;
    while !gone(tool) {
        assert!(started.elapsed() < Duration::from_secs(3), "tool survived");
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    // Without the group only the engine itself is signalled; its tool is left behind.
    let (mut child, tool) = shell(false).await;
    lumen_engine::reap(&mut child, false).await;
    tokio::time::sleep(Duration::from_millis(200)).await;
    assert!(!gone(tool));
    let _ = std::process::Command::new("kill")
        .args(["-KILL", &tool.to_string()])
        .status();
}

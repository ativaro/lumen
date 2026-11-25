# Lumen engine control

`lumen-engine` is Lumen's one implementation of talking to the OpenCode engine (`opencode serve`,
release `VERSION` = 1.18.34). The server uses it for every model run; the desktop's service
`lumen-service` (`native/service`) uses it for the conversations of the Qt views. The server
keeps a pinned, hash-checked copy in `rust/shared/engine` (`scripts/update_shared_crates.py`).

The crate speaks only to an engine that already runs. Starting it, its profile and sandbox, the
session policy (who may create which session with which permissions) and tenancy stay with each
side.

## Contents

- `Client`: the loopback connection. Only `http://127.0.0.1:<port>` with a password is accepted;
  Basic authentication as `opencode`, no proxy, no redirects, no automatic retries (a prompt is
  never sent twice), 2 s to connect, 20 s per request (190 s for a synchronous `POST …/message`) and
  2 MiB per answer. `directory()` adds `?directory=` to every request, `limit()` changes the answer
  limit and `page()` makes the reply loop read only the newest messages of a session. `request()`
  wants a successful JSON answer; `call()` also returns a refusal with its status, for callers that
  show the engine's own message; `raw()` returns status, content type and body of any answer (the
  desktop's setup diagnosis counts them). `health()` and `events()` are the health check and the
  event stream.
- `reap()`: TERM, five seconds, then KILL; with `group` the whole process group of the engine.
- `response()`: one prompt (`prompt_async`, or `POST …/message` with a structured `format`) and its
  final assistant message. Message polls (one per second) decide completion; the event stream only
  brings text sooner and is reopened when it drops, without repeating the prompt. An `Observer`
  sees text, messages and phases and may stop the loop at every step. Provider errors come back as
  a fixed message without the provider's text.
  - A payload that names its `messageID` belongs to a session that continues: only replies whose
    `parentID` is that message count (an earlier answer in the session is never taken for the new
    one), and a finished reply completes even without text. Without a `messageID` the session is the
    run's own and its last assistant message with text is the answer, as the server uses it.
  - `Observer::waiting()` is asked after every poll; while it answers `true` (an open permission or
    question) the reply does not complete.
- `frames`: complete SSE and JSON frames, checked before use (duplicate keys, size, secrets that
  must not be reflected); the engine's event stream and the server's MCP relay read them alike.
- `python`: JSON text as Python's `json.dumps` writes it, for digests and stamps that must stay
  byte-identical with ones Python wrote.
- `PLUGIN`: the compaction plugin (`src/lumen-continuity.mjs`) both sides load into every engine.

## Checks

```bash
python3 ../document-core/check-licenses.py .
cargo fmt --check
cargo clippy --locked --offline --release --all-targets -- -D warnings
cargo test --locked --offline --release
```

The dependencies are frozen in `../service/vendor`; the build never reaches the network. tokio,
reqwest, rustix and percent-encoding are pinned to the versions the server locks, so both sides run
the same HTTP client. The tests run a deterministic engine on a loopback port and a shell for the
process-group reap.

//! Lumen's local meaning search for the memory: a service that keeps the sentence model loaded
//! between questions and ends itself after ten minutes without one.
//!
//! `lumen-memory serve <home> <socket> <model sha256> <tokenizer sha256>` listens on a private Unix
//! socket. A request is one JSON object `{"path", "entries": [{"id", "revision", "title", "text",
//! "digest"}], "query"}`; the answer is the index state with scores and excerpts. The caller
//! (`files/memory_local.py`) prepares the index rows and their digests; this program only fills in
//! vectors for rows it finds unchanged, and scores only rows whose revision and digest still match.
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tract_onnx::prelude::*;

/// How long the model stays loaded after the last question.
const IDLE: Duration = Duration::from_secs(600);
const MAX_INPUT: u64 = 16 * 1024 * 1024;
const DIMENSIONS: usize = 384;
/// Fragments of 126 tokens, each starting 102 tokens after the previous one.
const WINDOW: usize = 126;
const STEP: usize = 102;

type Model = std::sync::Arc<TypedSimplePlan>;

struct Encoder {
    model: Model,
    tokenizer: tokenizers::Tokenizer,
    start: i64,
    end: i64,
}

fn failed<E: std::fmt::Display>(error: E) -> String {
    error.to_string()
}

fn sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(failed)?;
    let mut digest = Sha256::new();
    std::io::copy(&mut file, &mut digest).map_err(failed)?;
    Ok(digest
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

impl Encoder {
    fn load(directory: &Path, model_sum: &str, tokenizer_sum: &str) -> Result<Encoder, String> {
        for (name, expected) in [("model.onnx", model_sum), ("tokenizer.json", tokenizer_sum)] {
            if sha256(&directory.join(name))? != expected {
                return Err(format!("Memory model checksum mismatch: {name}"));
            }
        }
        let mut tokenizer =
            tokenizers::Tokenizer::from_file(directory.join("tokenizer.json")).map_err(failed)?;
        // The file asks for truncation to one window; long notes are split into windows here instead.
        tokenizer.with_truncation(None).map_err(failed)?;
        tokenizer.with_padding(None);
        let id = |token| {
            tokenizer
                .token_to_id(token)
                .map(i64::from)
                .ok_or("Tokenizer without sentence marks")
        };
        let (start, end) = (id("<s>")?, id("</s>")?);
        let model = tract_onnx::onnx()
            .model_for_path(directory.join("model.onnx"))
            .and_then(|model| model.into_optimized())
            .and_then(|model| model.into_runnable())
            .map_err(failed)?;
        Ok(Encoder {
            model,
            tokenizer,
            start,
            end,
        })
    }

    fn tokens(&self, text: &str) -> Result<tokenizers::Encoding, String> {
        if text.chars().count() > 21000 {
            return Err("Memory embedding input exceeds budget".into());
        }
        self.tokenizer
            .encode_char_offsets(text, false)
            .map_err(failed)
    }

    /// The token ids of `text` and where each fragment from fragment `start` on begins; long notes are not truncated.
    fn windows(&self, text: &str, start: usize) -> Result<(Vec<i64>, Vec<usize>), String> {
        let tokens: Vec<i64> = self
            .tokens(text)?
            .get_ids()
            .iter()
            .map(|&id| i64::from(id))
            .collect();
        let mut offsets = Vec::new();
        let mut offset = start * STEP;
        while offset < tokens.len().max(1) {
            offsets.push(offset);
            if offset + WINDOW >= tokens.len() {
                break;
            }
            offset += STEP;
        }
        Ok((tokens, offsets))
    }

    /// The mean-pooled, normalised vector of the fragment at token `offset`.
    fn window(&self, tokens: &[i64], offset: usize) -> Result<Vec<f32>, String> {
        self.fragment(&tokens[offset.min(tokens.len())..(offset + WINDOW).min(tokens.len())])
    }

    /// Every fragment's vector.
    fn encode(&self, text: &str) -> Result<Vec<Vec<f32>>, String> {
        let (tokens, offsets) = self.windows(text, 0)?;
        offsets
            .iter()
            .map(|&offset| self.window(&tokens, offset))
            .collect()
    }

    fn fragment(&self, tokens: &[i64]) -> Result<Vec<f32>, String> {
        let ids: Vec<i64> = std::iter::once(self.start)
            .chain(tokens.iter().copied())
            .chain([self.end])
            .collect();
        let n = ids.len();
        let array = |values: Vec<i64>| -> Result<TValue, String> {
            Ok(tract_ndarray::Array2::from_shape_vec((1, n), values)
                .map_err(failed)?
                .into_tensor()
                .into())
        };
        let output = self
            .model
            .run(tvec!(array(ids)?, array(vec![1; n])?, array(vec![0; n])?))
            .map_err(failed)?;
        let hidden = output[0].clone().into_tensor();
        let hidden = hidden.to_plain_array_view::<f32>().map_err(failed)?;
        if hidden.shape() != [1, n, DIMENSIONS] {
            return Err("Invalid memory embedding output".into());
        }
        let mut pooled = vec![0f32; DIMENSIONS];
        for token in 0..n {
            for (dimension, value) in pooled.iter_mut().enumerate() {
                *value += hidden[[0, token, dimension]] / n as f32;
            }
        }
        let norm = pooled.iter().map(|v| v * v).sum::<f32>().sqrt().max(1e-12);
        let vector: Vec<f32> = pooled.iter().map(|v| v / norm).collect();
        if !vector.iter().all(|v| v.is_finite()) {
            return Err("Invalid memory embedding output".into());
        }
        Ok(vector)
    }

    /// About 125 tokens of `text` from fragment `position`, at most 1600 characters.
    fn excerpt(&self, text: &str, position: usize) -> Result<String, String> {
        let encoding = self.tokens(text)?;
        let offsets = encoding.get_offsets();
        let start = position * STEP;
        if start >= offsets.len() {
            return Ok(String::new());
        }
        let (from, to) = (
            offsets[start].0,
            offsets[(start + WINDOW - 1).min(offsets.len() - 1)].1,
        );
        Ok(text
            .chars()
            .skip(from)
            .take(to.saturating_sub(from))
            .take(1600)
            .collect())
    }
}

struct Entry {
    id: String,
    revision: String,
    text: String,
    digest: String,
}

fn entries(request: &Value) -> Result<Vec<Entry>, String> {
    let field =
        |entry: &Value, key: &str| entry.get(key).and_then(Value::as_str).map(str::to_string);
    request
        .get("entries")
        .and_then(Value::as_array)
        .ok_or("Invalid memory request")?
        .iter()
        .map(|entry| {
            let (title, text) = (field(entry, "title"), field(entry, "text"));
            Some(Entry {
                id: field(entry, "id")?,
                revision: field(entry, "revision")?,
                text: format!("{}\n{}", title?, text?),
                digest: field(entry, "digest")?,
            })
        })
        .collect::<Option<_>>()
        .ok_or_else(|| "Invalid memory entry".to_string())
}

fn open(path: &str) -> Result<rusqlite::Connection, String> {
    if !path.ends_with(".sqlite3") {
        return Err("Invalid memory index".into());
    }
    let db = rusqlite::Connection::open(path).map_err(failed)?;
    db.busy_timeout(Duration::from_secs(2)).map_err(failed)?;
    db.execute_batch(
        "PRAGMA foreign_keys=ON; PRAGMA secure_delete=ON; PRAGMA max_page_count=65536;",
    )
    .map_err(failed)?;
    Ok(db)
}

/// Bounded indexing work, committed per fragment; it resumes after an interruption.
fn advance(
    db: &rusqlite::Connection,
    entries: &[Entry],
    encoder: &Encoder,
    chunks: usize,
) -> Result<usize, String> {
    let mut remaining = chunks;
    for entry in entries {
        let row: Option<(String, String, i64)> = db
            .query_row(
                "SELECT revision,digest,complete FROM records WHERE id=?",
                [&entry.id],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .ok();
        if row.as_ref() != Some(&(entry.revision.clone(), entry.digest.clone(), 0)) {
            continue;
        }
        let start: i64 = db
            .query_row(
                "SELECT count(*) FROM vectors WHERE id=?",
                [&entry.id],
                |r| r.get(0),
            )
            .map_err(failed)?;
        let mut changed = false;
        let (tokens, offsets) = encoder.windows(&entry.text, start as usize)?;
        for (index, &offset) in offsets.iter().enumerate() {
            if remaining == 0 {
                return Ok(chunks);
            }
            let vector = encoder.window(&tokens, offset)?;
            let bytes: Vec<u8> = vector.iter().flat_map(|v| v.to_le_bytes()).collect();
            let tx =
                rusqlite::Transaction::new_unchecked(db, rusqlite::TransactionBehavior::Immediate)
                    .map_err(failed)?;
            let still: Option<(String, String)> = tx
                .query_row(
                    "SELECT revision,digest FROM records WHERE id=?",
                    [&entry.id],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .ok();
            if still != Some((entry.revision.clone(), entry.digest.clone())) {
                changed = true;
                break;
            }
            tx.execute(
                "INSERT OR REPLACE INTO vectors VALUES (?,?,?)",
                rusqlite::params![entry.id, start + index as i64, bytes],
            )
            .map_err(failed)?;
            tx.commit().map_err(failed)?;
            remaining -= 1;
        }
        if !changed {
            db.execute(
                "UPDATE records SET complete=1 WHERE id=? AND revision=? AND digest=?",
                rusqlite::params![entry.id, entry.revision, entry.digest],
            )
            .map_err(failed)?;
        }
    }
    Ok(chunks - remaining)
}

fn status(db: &rusqlite::Connection) -> Result<(i64, i64), String> {
    db.query_row(
        "SELECT coalesce(sum(complete),0),count(*) FROM records",
        [],
        |r| Ok((r.get(0)?, r.get(1)?)),
    )
    .map_err(failed)
}

/// The best fragment score of every current entry; cached vectors count only for the same revision and digest.
fn scores(
    db: &rusqlite::Connection,
    entries: &[Entry],
    query: &str,
    encoder: &Encoder,
) -> Result<Vec<(usize, f32, usize)>, String> {
    let query: String = query.chars().take(6000).collect();
    let needles = encoder.encode(&query)?;
    let mut statement = db
        .prepare(
            "SELECT v.vector,v.position FROM vectors v JOIN records r ON r.id=v.id \
             WHERE r.id=? AND r.revision=? AND r.digest=? AND r.complete=1 ORDER BY v.position",
        )
        .map_err(failed)?;
    let mut found = Vec::new();
    for (index, entry) in entries.iter().enumerate() {
        let rows = statement
            .query_map(
                rusqlite::params![entry.id, entry.revision, entry.digest],
                |r| Ok((r.get::<_, Vec<u8>>(0)?, r.get::<_, i64>(1)?)),
            )
            .map_err(failed)?;
        let mut best: Option<(f32, usize)> = None;
        for row in rows {
            let (blob, position) = row.map_err(failed)?;
            if blob.len() != DIMENSIONS * 4 {
                continue;
            }
            let vector: Vec<f32> = blob
                .as_chunks::<4>()
                .0
                .iter()
                .map(|b| f32::from_le_bytes(*b))
                .collect();
            if !vector.iter().all(|v| v.is_finite()) {
                continue;
            }
            let score = needles
                .iter()
                .map(|needle| needle.iter().zip(&vector).map(|(a, b)| a * b).sum::<f32>())
                .fold(f32::NEG_INFINITY, f32::max);
            if best.is_none_or(|(value, _)| score > value) {
                best = Some((score, position as usize));
            }
        }
        if let Some((score, position)) = best {
            found.push((index, score, position));
        }
    }
    Ok(found)
}

fn state(ready: i64, total: i64) -> &'static str {
    if ready == total { "hybrid" } else { "indexing" }
}

fn answer(encoder: &Encoder, request: &Value) -> Result<Value, String> {
    let entries = entries(request)?;
    let db = open(
        request
            .get("path")
            .and_then(Value::as_str)
            .ok_or("Invalid memory request")?,
    )?;
    advance(&db, &entries, encoder, 32)?;
    let (ready, total) = status(&db)?;
    let query = request.get("query").and_then(Value::as_str).unwrap_or("");
    let mut found = scores(&db, &entries, query, encoder)?;
    let list: Vec<Value> = found
        .iter()
        .map(|&(index, score, _)| json!([entries[index].id, entries[index].revision, score]))
        .collect();
    found.sort_by(|a, b| {
        b.1.total_cmp(&a.1).then_with(|| {
            (&entries[a.0].id, &entries[a.0].revision)
                .cmp(&(&entries[b.0].id, &entries[b.0].revision))
        })
    });
    let mut excerpts = Vec::new();
    for &(index, score, position) in found.iter().take(12) {
        if score >= 0.35 {
            let entry = &entries[index];
            excerpts.push(json!([
                entry.id,
                entry.revision,
                encoder.excerpt(&entry.text, position)?
            ]));
        }
    }
    Ok(
        json!({"ready": ready, "total": total, "mode": state(ready, total), "reason": "", "scores": list, "excerpts": excerpts}),
    )
}

/// One small indexing step for a request; true when nothing is left to do.
fn step(encoder: &Encoder, request: &Value) -> Result<bool, String> {
    let entries = entries(request)?;
    let db = open(
        request
            .get("path")
            .and_then(Value::as_str)
            .ok_or("Invalid memory request")?,
    )?;
    let processed = advance(&db, &entries, encoder, 8)?;
    let (ready, total) = status(&db)?;
    Ok(processed == 0 || ready == total)
}

fn handle(encoder: &Encoder, mut stream: UnixStream) -> Option<Value> {
    stream.set_nonblocking(false).ok()?;
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .ok()?;
    let mut data = Vec::new();
    (&mut stream)
        .take(MAX_INPUT + 1)
        .read_to_end(&mut data)
        .ok()?;
    let request: Option<Value> = (data.len() as u64 <= MAX_INPUT)
        .then(|| serde_json::from_slice(&data).ok())
        .flatten();
    let reply = match request.as_ref().map(|request| answer(encoder, request)) {
        Some(Ok(reply)) => reply,
        _ => json!({"mode": "text", "reason": "unavailable", "scores": []}),
    };
    let _ = stream.write_all(reply.to_string().as_bytes());
    drop(stream);
    request.filter(|_| reply["mode"] == "indexing")
}

fn serve(home: &Path, socket: &Path, model_sum: &str, tokenizer_sum: &str) -> Result<(), String> {
    // One model per installation: a second service leaves at once.
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .mode(0o600)
        .open(home.join("model.lock"))
        .map_err(failed)?;
    if lock.try_lock().is_err() {
        return Ok(());
    }
    let folder = socket.parent().ok_or("Invalid socket path")?;
    std::fs::create_dir_all(folder).map_err(failed)?;
    std::fs::set_permissions(folder, std::fs::Permissions::from_mode(0o700)).map_err(failed)?;
    let _ = std::fs::remove_file(socket);
    let listener = UnixListener::bind(socket).map_err(failed)?;
    std::fs::set_permissions(socket, std::fs::Permissions::from_mode(0o600)).map_err(failed)?;
    // A thread waits for connections and hands them over at once; questions that arrive while the
    // model loads wait in the channel.
    let (sender, connections) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        for stream in listener.incoming().flatten() {
            if sender.send(stream).is_err() {
                break;
            }
        }
    });
    let encoder = Encoder::load(&home.join("model"), model_sum, tokenizer_sum);
    let mut last = Instant::now();
    let mut filling: Option<(Value, Instant)> = None;
    loop {
        // While indexing goes on, only look whether a question waits; otherwise wait for one until the pause ends.
        let wait = if filling.is_some() || encoder.is_err() {
            Duration::ZERO
        } else {
            IDLE.saturating_sub(last.elapsed())
        };
        match connections.recv_timeout(wait) {
            Ok(stream) => {
                filling = match &encoder {
                    Ok(encoder) => handle(encoder, stream)
                        .map(|request| (request, Instant::now() + Duration::from_secs(20))),
                    Err(_) => {
                        let mut stream = stream;
                        let _ = stream
                            .write_all(br#"{"mode":"text","reason":"unavailable","scores":[]}"#);
                        None
                    }
                };
                last = Instant::now();
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                // Indexing goes on in small steps after an answer, for up to twenty seconds; a new question comes first.
                if let (Some((request, deadline)), Ok(encoder)) = (&filling, &encoder) {
                    if Instant::now() >= *deadline || step(encoder, request).unwrap_or(true) {
                        filling = None;
                    }
                    last = Instant::now();
                    continue;
                }
                if last.elapsed() >= IDLE || encoder.is_err() {
                    break;
                }
            }
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
        }
    }
    let _ = std::fs::remove_file(socket);
    Ok(())
}

fn main() -> std::process::ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let [command, home, socket, model_sum, tokenizer_sum] = args.as_slice() else {
        eprintln!("usage: lumen-memory serve <home> <socket> <model sha256> <tokenizer sha256>");
        return std::process::ExitCode::from(2);
    };
    if command != "serve" {
        eprintln!("usage: lumen-memory serve <home> <socket> <model sha256> <tokenizer sha256>");
        return std::process::ExitCode::from(2);
    }
    match serve(
        &PathBuf::from(home),
        &PathBuf::from(socket),
        model_sum,
        tokenizer_sum,
    ) {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn index_state_follows_complete_rows() {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch(
            "CREATE TABLE records (id TEXT PRIMARY KEY, revision TEXT NOT NULL, digest TEXT NOT NULL, complete INT NOT NULL DEFAULT 0);
             INSERT INTO records VALUES ('a','1','d',1),('b','1','e',0);",
        )
        .unwrap();
        assert_eq!(status(&db).unwrap(), (1, 2));
        assert_eq!(state(1, 2), "indexing");
        assert_eq!(state(2, 2), "hybrid");
        assert!(open("/tmp/not-an-index.db").is_err());
    }

    #[test]
    fn requests_need_every_entry_field() {
        let good = json!({"entries": [{"id": "a", "revision": "1", "title": "T", "text": "x", "digest": "d"}]});
        let read = entries(&good).unwrap();
        assert_eq!(
            (read[0].text.as_str(), read[0].digest.as_str()),
            ("T\nx", "d")
        );
        assert!(
            entries(&json!({"entries": [{"id": "a", "revision": "1", "title": "T", "text": "x"}]}))
                .is_err()
        );
        assert!(entries(&json!({})).is_err());
    }
}

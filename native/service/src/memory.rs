//! The memory's local meaning search: `memory.search` keeps the sentence model of one model folder
//! loaded between questions and drops it after ten minutes without one.
//!
//! The model runs in Lumen's sentence encoder (`native/sentence-encoder`) once its files and the
//! ONNX Runtime library in `<home>/runtime` match the checksums of the request. The memory
//! (`recall.rs`) prepares the index rows and their digests; this part only fills in
//! vectors for rows it finds unchanged, and scores only rows whose revision and digest still match.
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use lumen_sentence_encoder::{DIMENSIONS, Encoder};
use serde_json::{Value, json};

use crate::{failed, sha256};

/// How long the model stays loaded after the last question.
const IDLE: Duration = Duration::from_secs(600);
/// How long indexing goes on in small steps after an answer.
const FILL: Duration = Duration::from_secs(20);
/// The pinned ONNX Runtime library, installed beside the model.
const RUNTIME: &str = "runtime/libonnxruntime.so.1.30.0";

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

/// An absolute path from the request: the service runs in `/`, not in the caller's folder.
fn absolute(request: &Value, key: &str) -> Result<PathBuf, String> {
    request
        .get(key)
        .and_then(Value::as_str)
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .ok_or_else(|| "Invalid memory request".to_string())
}

fn open(path: &Path) -> Result<rusqlite::Connection, String> {
    if path
        .extension()
        .is_none_or(|extension| extension != "sqlite3")
    {
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
    encoder: &mut Encoder,
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
            let vector = encoder.vector(&tokens, offset)?;
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
    encoder: &mut Encoder,
) -> Result<Vec<(usize, f32, usize)>, String> {
    let query: String = query.chars().take(6000).collect();
    let needles = encoder.encode(&query, 0)?;
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

fn answer(encoder: &mut Encoder, request: &Value) -> Result<Value, String> {
    let entries = entries(request)?;
    let db = open(&absolute(request, "path")?)?;
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
fn step(encoder: &mut Encoder, request: &Value) -> Result<bool, String> {
    let entries = entries(request)?;
    let db = open(&absolute(request, "path")?)?;
    let processed = advance(&db, &entries, encoder, 8)?;
    let (ready, total) = status(&db)?;
    Ok(processed == 0 || ready == total)
}

/// `LUMEN_MEMORY_THREADS`: ONNX Runtime threads for one fragment (default 1, at most 8).
fn threads() -> usize {
    std::env::var("LUMEN_MEMORY_THREADS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(1usize)
        .clamp(1, 8)
}

/// The encoder, after model, tokenizer and runtime library matched their checksums.
fn load(home: &Path, sums: &[String; 3]) -> Result<Encoder, String> {
    let files = ["model/model.onnx", "model/tokenizer.json", RUNTIME].map(|name| home.join(name));
    for (path, expected) in files.iter().zip(sums) {
        if sha256(path)? != *expected {
            return Err(format!(
                "Memory model checksum mismatch: {}",
                path.display()
            ));
        }
    }
    Encoder::load(&files[0], &files[1], &files[2], threads())
}

/// The model folder and checksums of a request: `home` and `checksums` (model, tokenizer, runtime).
fn model(request: &Value) -> Result<(PathBuf, [String; 3]), String> {
    let sums = request
        .get("checksums")
        .and_then(Value::as_array)
        .and_then(|sums| {
            sums.iter()
                .map(|sum| sum.as_str().map(str::to_string))
                .collect::<Option<Vec<_>>>()
        })
        .and_then(|sums| <[String; 3]>::try_from(sums).ok())
        .ok_or("Invalid memory request")?;
    Ok((absolute(request, "home")?, sums))
}

struct Model {
    home: PathBuf,
    sums: [String; 3],
    encoder: Encoder,
}

/// The memory search between questions: the loaded model and the request it goes on indexing for.
pub struct Memory {
    model: Option<Model>,
    filling: Option<(Value, Instant)>,
    last: Instant,
}

impl Memory {
    pub fn new() -> Memory {
        Memory {
            model: None,
            filling: None,
            last: Instant::now(),
        }
    }

    /// How long the service may wait for a question before `idle` has work: not at all while
    /// indexing, the rest of the pause while the model is loaded, without limit otherwise.
    pub fn wait(&self) -> Option<Duration> {
        if self.filling.is_some() {
            return Some(Duration::ZERO);
        }
        self.model
            .as_ref()
            .map(|_| IDLE.saturating_sub(self.last.elapsed()))
    }

    /// Work between questions: one small indexing step, or dropping the model after the pause.
    pub fn idle(&mut self) {
        if let (Some((request, deadline)), Some(model)) = (&self.filling, &mut self.model) {
            if Instant::now() >= *deadline || step(&mut model.encoder, request).unwrap_or(true) {
                self.filling = None;
            }
            self.last = Instant::now();
        } else if self.last.elapsed() >= IDLE {
            self.model = None;
            self.filling = None;
            crate::sys::trim();
        }
    }

    fn encoder(&mut self, request: &Value) -> Result<&mut Encoder, String> {
        let (home, sums) = model(request)?;
        if self
            .model
            .as_ref()
            .is_none_or(|model| model.home != home || model.sums != sums)
        {
            // Another model folder or other checksums: the old model goes before the new one loads.
            self.model = None;
            self.filling = None;
            let encoder = load(&home, &sums)?;
            self.model = Some(Model {
                home,
                sums,
                encoder,
            });
        }
        self.model
            .as_mut()
            .map(|model| &mut model.encoder)
            .ok_or_else(|| "No memory model".to_string())
    }

    /// `memory.search`: the index state with scores and excerpts, or the text fallback.
    pub fn search(&mut self, request: Value) -> Value {
        let reply = match self
            .encoder(&request)
            .and_then(|encoder| answer(encoder, &request))
        {
            Ok(reply) => reply,
            Err(_) => json!({"mode": "text", "reason": "unavailable", "scores": []}),
        };
        self.filling = (reply["mode"] == "indexing").then(|| (request, Instant::now() + FILL));
        self.last = Instant::now();
        reply
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
        assert!(open(Path::new("/tmp/not-an-index.db")).is_err());
    }

    #[test]
    fn files_with_another_checksum_are_not_loaded() {
        let home = std::env::temp_dir().join(format!("lumen-service-test-{}", std::process::id()));
        for folder in ["model", "runtime"] {
            std::fs::create_dir_all(home.join(folder)).unwrap();
        }
        for name in ["model/model.onnx", "model/tokenizer.json", RUNTIME] {
            std::fs::write(home.join(name), name).unwrap();
        }
        let sums = ["model/model.onnx", "model/tokenizer.json"]
            .map(|name| sha256(&home.join(name)).unwrap());
        let error = load(&home, &[sums[0].clone(), sums[1].clone(), "0".into()])
            .err()
            .unwrap();
        std::fs::remove_dir_all(&home).unwrap();
        assert!(error.starts_with("Memory model checksum mismatch") && error.ends_with(RUNTIME));
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

    #[test]
    fn requests_name_an_absolute_model_folder_and_three_checksums() {
        let sums = json!(["a", "b", "c"]);
        let (home, read) = model(&json!({"home": "/m", "checksums": sums})).unwrap();
        assert_eq!(
            (home, read),
            (PathBuf::from("/m"), ["a", "b", "c"].map(String::from))
        );
        assert!(model(&json!({"home": "m", "checksums": sums})).is_err());
        assert!(model(&json!({"home": "/m", "checksums": ["a", "b"]})).is_err());
        assert!(absolute(&json!({"path": "index.sqlite3"}), "path").is_err());
    }

    #[test]
    fn a_failed_load_answers_the_text_fallback_and_keeps_nothing_loaded() {
        let mut memory = Memory::new();
        let reply = memory.search(json!({"home": "/nonexistent", "checksums": ["a", "b", "c"],
            "path": "/nonexistent/index.sqlite3", "query": "q", "entries": []}));
        assert_eq!(reply["reason"], "unavailable");
        assert_eq!(memory.wait(), None);
    }
}

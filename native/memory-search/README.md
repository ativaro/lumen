# Lumen memory meaning search

`lumen-memory serve <home> <socket> <model sha256> <tokenizer sha256>` keeps Lumen's local sentence
model loaded between questions and ends itself after ten minutes without one. It listens on a
private Unix socket (folder 0700, socket 0600) and holds the model lock, so only one model runs per
installation.

`files/memory_local.py` prepares the index rows and their digests, starts the service when none
listens and sends one JSON request per question: `{"path", "query", "entries": [{"id", "revision",
"title", "text", "digest"}]}`. The service fills in vectors only for rows it finds unchanged, scores
only rows whose revision and digest still match, and answers with the index state, the scores and up
to twelve excerpts. After an answer it goes on indexing in small steps for up to twenty seconds; a new
question comes first.

The model (`paraphrase-multilingual-MiniLM-L12-v2`, quantized ONNX) runs in `tract`; tokens come from
`tokenizers` with the file's own truncation switched off, so long notes are split into overlapping
windows of 126 tokens every 102 tokens. Compared with the earlier Python worker on 34 real notes:
the same 41 windows, vectors with cosine 0.993 or more, scores within 0.017; a question takes about
10 ms instead of about 550 ms.

## Checks

```bash
python3 ../document-core/check-licenses.py .
cargo fmt --check
cargo clippy --locked --release --all-targets -- -D warnings
cargo test --locked --release
```

## Frozen sources

`vendor/` holds the sources the build uses; the build never reaches the network. Packages that are
never compiled on Linux (Windows, WebAssembly) keep only their `Cargo.toml` and an empty
`src/lib.rs`, so the lockfile still resolves while the sources stay small. Only freely usable
licences are accepted.

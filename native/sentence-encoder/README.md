# Lumen sentence encoder

`lumen_sentence_encoder::Encoder` turns text into the vectors of Lumen's memory search. It is the one
implementation for desktop and server: the desktop's service `lumen-service` (`native/service`) and the
server's memory search both use this crate, so the same text gives the same vector on both sides.

The model (`paraphrase-multilingual-MiniLM-L12-v2`, quantized ONNX, 384 dimensions) runs in ONNX
Runtime 1.30.0. The library is loaded at run time from the path the caller gives (`ort` with
`load-dynamic`); the build links and downloads nothing. Tokens come from `tokenizers` with the file's
own truncation switched off, so long texts are split into overlapping windows of 126 tokens every
102 tokens. Each window is mean-pooled and normalised in float64, as the earlier Python encoder did
with numpy: on its 56 reference texts (134 windows) the vectors are bit-identical.

Callers verify the checksums of model, tokenizer and library before `Encoder::load`; the crate reads
the files as they are.

The process needs `ORT_DISABLE_TELEMETRY=1` in its environment, or `Encoder::load` refuses: ONNX
Runtime 1.30 otherwise writes a device identifier and an upload queue to
`~/.cache/Microsoft/DeveloperTools/.onnxruntime`, even with telemetry switched off through its API.

## Checks

```bash
cargo fmt --check
cargo clippy --locked --offline --release --all-targets -- -D warnings
cargo test --locked --offline --release
```

With `ORT_DISABLE_TELEMETRY=1` and `LUMEN_TEST_MEMORY_HOME` pointing at an installed memory search (`model/` and `runtime/`), the
tests also run the model and compare its vectors with kept reference vectors.

## Frozen sources

The dependencies are the ones frozen in `../service/vendor` (`.cargo/config.toml` points there);
the build never reaches the network.

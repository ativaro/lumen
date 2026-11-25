# Local memory search

Optional unmodified quantized Sentence Transformers model:
https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
Revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42. Apache-2.0; see LICENSE and original MODEL.md.
Lumen applies mean pooling and overlapping text windows; weights are unmodified.

# Local memory search program

The model runs in Lumen's own Rust service `lumen-service` (`native/service`), built from
frozen sources under freely usable licences; see `THIRD_PARTY_NOTICES.md` in Lumen. It loads the
unmodified ONNX Runtime 1.30.0 library `runtime/libonnxruntime.so.1.30.0` (MIT License), taken from
the pinned `onnxruntime-1.30.0-cp314-cp314-manylinux_2_28_x86_64.whl` (SHA-256
8b611d24db2954545ce6bd9acd4670183cb368e4642450de7a9ab6474eb374ec). Its original `LICENSE` and
`ThirdPartyNotices.txt` are kept next to it in `runtime/`. No Python environment is installed.

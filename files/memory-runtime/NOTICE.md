# Local memory search

Optional unmodified quantized Sentence Transformers model:
https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
Revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42. Apache-2.0; see LICENSE and original MODEL.md.
Lumen applies mean pooling and overlapping text windows; weights are unmodified.

# Local memory search program

The model runs in Lumen's own Rust program `lumen-memory` (`native/memory-search`), built from
frozen sources under freely usable licences; see `THIRD_PARTY_NOTICES.md` in Lumen.

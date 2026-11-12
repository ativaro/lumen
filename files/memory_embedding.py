"""The local sentence model for meaning search: its version and file checksums. No network access.

`lumen-memory` (native/memory-search) loads and runs it; the version is part of every index digest,
so vectors from another model are never mixed in."""

MODEL_VERSION = 'minilm-multilingual-e8f8c211-avx2-int8-mean-v1'
MODEL_FILES = {
    'model.onnx': '98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f',
    'tokenizer.json': '2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8',
}
DIMENSIONS = 384

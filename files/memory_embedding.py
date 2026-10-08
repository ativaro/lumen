"""Optional local sentence embeddings. No network access or automatic downloads."""
import hashlib
from pathlib import Path

MODEL_VERSION = 'minilm-multilingual-e8f8c211-avx2-int8-mean-v1'
MODEL_FILES = {
    'model.onnx': '98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f',
    'tokenizer.json': '2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8',
}
DIMENSIONS = 384


class Encoder:
    def __init__(self, directory):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        directory = Path(directory)
        for name, expected in MODEL_FILES.items():
            with (directory / name).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('Memory model checksum mismatch: ' + name)
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = options.enable_mem_pattern = False
        self.session = ort.InferenceSession(str(directory / 'model.onnx'), options,
                                           providers=['CPUExecutionProvider'])
        self.inputs = {value.name for value in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.start = self.tokenizer.token_to_id('<s>')
        self.end = self.tokenizer.token_to_id('</s>')

    def excerpt(self, text, position):
        offsets = self.tokenizer.encode(text, add_special_tokens=False).offsets
        start = position * 102
        if start >= len(offsets):
            return ''
        return text[offsets[start][0]:offsets[min(start + 125, len(offsets)-1)][1]][:1600]

    def encode(self, text, start=0):
        """One vector per overlapping fragment; long notes are not silently truncated."""
        if not isinstance(text, str) or len(text) > 21000:
            raise ValueError('Memory embedding input exceeds budget')
        np = self.np
        tokens = self.tokenizer.encode(text, add_special_tokens=False).ids
        for offset in range(start * 102, max(1, len(tokens)), 102):
            ids = [self.start, *tokens[offset:offset + 126], self.end]
            values = {'input_ids': np.array([ids], dtype=np.int64),
                      'attention_mask': np.ones((1, len(ids)), dtype=np.int64),
                      'token_type_ids': np.zeros((1, len(ids)), dtype=np.int64)}
            hidden = self.session.run(None, {k: v for k, v in values.items() if k in self.inputs})[0]
            mask = values['attention_mask'][..., None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(1)
            vector = (pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(1e-12))[0]
            if vector.shape != (DIMENSIONS,) or not np.isfinite(vector).all():
                raise ValueError('Invalid memory embedding output')
            yield vector.astype('<f4')
            if offset + 126 >= len(tokens):
                break

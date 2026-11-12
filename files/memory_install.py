"""Explicit optional installation; callbacks reuse each platform's setup runner."""
import fcntl
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile

if __package__:
    from .memory_embedding import MODEL_FILES
else:
    from memory_embedding import MODEL_FILES

BASE = ('https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/'
        'resolve/e8f8c211226b894fcb81acc59f3b34ba3efd5f42/')
ASSETS = Path(__file__).with_name('memory-runtime')
FILES = (('model.onnx', 'onnx/model_quint8_avx2.onnx', 118453870),
         ('tokenizer.json', 'tokenizer.json', 9081518))


def supported():
    return sys.platform == 'linux' and platform.machine() == 'x86_64'


def verified(path, expected):
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == expected


def install(home, *, run, download, report, check=lambda: None):
    """No user data touched: only the model files, checked by their checksums, and Lumen's own notices."""
    if not supported():
        raise ValueError('Bedeutungssuche benötigt Linux x86_64. Textsuche bleibt verfügbar.')
    home = Path(home).absolute()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (home / 'setup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Die Bedeutungssuche wird bereits eingerichtet.') from None
        check()
        if shutil.disk_usage(home).free < 512 * 1024**2:
            raise ValueError('Für die Einrichtung werden mindestens 512 MiB freier Speicher benötigt.')
        model = home / 'model'
        model.mkdir(exist_ok=True, mode=0o700)
        for name, remote, size in FILES:
            check()
            if not verified(model / name, MODEL_FILES[name]):
                report('Bedeutungsmodell herunterladen …')
                download(BASE + remote, model / name, MODEL_FILES[name], size)
            if not verified(model / name, MODEL_FILES[name]):
                raise ValueError('Die Prüfsumme des Suchmodells stimmt nicht.')
        report('Bedeutungssuche lokal prüfen …')
        from memory_local import ask
        with tempfile.TemporaryDirectory(prefix='lumen-memory-check-') as folder:
            request = json.dumps({'path': str(Path(folder) / 'check.sqlite3'), 'query': 'Lumen memory', 'entries': []}).encode()
            from memory_index import Index
            Index(Path(folder) / 'check.sqlite3').close()
            if ask(home, request, timeout=60).get('mode') != 'hybrid':
                raise ValueError('Die Bedeutungssuche konnte das Modell nicht laden.')
        check()
        for name in ('LICENSE', 'MODEL.md', 'NOTICE.md'):
            shutil.copyfile(ASSETS / name, home / name)
        report('Bedeutungssuche eingerichtet. Gedächtnisfreigaben bleiben unverändert.')

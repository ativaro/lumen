"""Explicit optional installation; callbacks reuse each platform's setup runner."""
import fcntl
import hashlib
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import zipfile

BASE = ('https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/'
        'resolve/e8f8c211226b894fcb81acc59f3b34ba3efd5f42/')
ASSETS = Path(__file__).with_name('memory-runtime')
FILES = (('model/model.onnx', 'onnx/model_quint8_avx2.onnx', 118453870),
         ('model/tokenizer.json', 'tokenizer.json', 9081518))
# ONNX Runtime comes from the pinned onnxruntime 1.30.0 wheel: the library and its original notices.
RUNTIME = 'runtime/libonnxruntime.so.1.30.0'
WHEEL = ('https://files.pythonhosted.org/packages/f1/38/8138eed225c5bc6ddfc05879ecac7dacc63c34b9b6f99be72839c1f6dc49/'
         'onnxruntime-1.30.0-cp314-cp314-manylinux_2_28_x86_64.whl',
         '8b611d24db2954545ce6bd9acd4670183cb368e4642450de7a9ab6474eb374ec', 23586333)
MEMBERS = ('onnxruntime/LICENSE', 'onnxruntime/ThirdPartyNotices.txt', 'onnxruntime/capi/libonnxruntime.so.1.30.0')


def supported():
    return sys.platform == 'linux' and platform.machine() == 'x86_64'


def verified(path, expected):
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == expected


def model_files():
    """The model's files and their SHA-256 as the service checks them before it loads the model."""
    from lumen_memory import model
    return model()['files']


def install_runtime(home, download, MODEL_FILES):
    """The library and its notices from the verified wheel; the library is checked and published last."""
    target = (home / RUNTIME).parent
    target.mkdir(exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=home, prefix='.setup-') as staging:
        staging = Path(staging)
        download(WHEEL[0], staging / 'wheel', WHEEL[1], WHEEL[2])
        with zipfile.ZipFile(staging / 'wheel') as wheel:
            for member in MEMBERS:
                with wheel.open(member) as source, (staging / Path(member).name).open('wb') as output:
                    shutil.copyfileobj(source, output)
                    output.flush(); os.fsync(output.fileno())
        if not verified(staging / Path(RUNTIME).name, MODEL_FILES[RUNTIME]):
            raise ValueError('Die Prüfsumme des Suchmodells stimmt nicht.')
        for member in MEMBERS:
            os.replace(staging / Path(member).name, target / Path(member).name)


def install(home, *, run, download, report, check=lambda: None):
    """No user data touched: only the model files and the runtime library, checked by their checksums, and Lumen's own notices."""
    if not supported():
        raise ValueError('Bedeutungssuche benötigt Linux x86_64. Textsuche bleibt verfügbar.')
    home = Path(home).absolute()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    MODEL_FILES = model_files()
    with (home / 'setup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Die Bedeutungssuche wird bereits eingerichtet.') from None
        check()
        if shutil.disk_usage(home).free < 512 * 1024**2:
            raise ValueError('Für die Einrichtung werden mindestens 512 MiB freier Speicher benötigt.')
        (home / 'model').mkdir(exist_ok=True, mode=0o700)
        for name, remote, size in FILES:
            check()
            if not verified(home / name, MODEL_FILES[name]):
                report('Bedeutungsmodell herunterladen …')
                download(BASE + remote, home / name, MODEL_FILES[name], size)
        check()
        if not verified(home / RUNTIME, MODEL_FILES[RUNTIME]):
            report('Suchlaufzeit herunterladen …')
            install_runtime(home, download, MODEL_FILES)
        if not all(verified(home / name, checksum) for name, checksum in MODEL_FILES.items()):
            raise ValueError('Die Prüfsumme des Suchmodells stimmt nicht.')
        report('Bedeutungssuche lokal prüfen …')
        from lumen_memory import verify
        if verify(home) != 'hybrid':
            raise ValueError('Die Bedeutungssuche konnte das Modell nicht laden.')
        check()
        for name in ('LICENSE', 'MODEL.md', 'NOTICE.md'):
            shutil.copyfile(ASSETS / name, home / name)
        report('Bedeutungssuche eingerichtet. Gedächtnisfreigaben bleiben unverändert.')

"""Explicit optional installation; callbacks reuse each platform's setup runner."""
import fcntl
import hashlib
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from uuid import uuid4

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
    return (sys.platform == 'linux' and platform.machine() == 'x86_64'
            and sys.version_info[:2] == (3, 14)
            and 'avx2' in Path('/proc/cpuinfo').read_text().split())


def verified(path, expected):
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == expected


def install(home, *, run, download, report, check=lambda: None):
    """No user data touched. Failed/cancelled setup never publishes a partial env."""
    if not supported():
        raise ValueError('Bedeutungssuche benötigt Linux x86_64, AVX2 und Python 3.14. Textsuche bleibt verfügbar.')
    home = Path(home).absolute()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (home / 'setup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Die Bedeutungssuche wird bereits eingerichtet.') from None
        check()
        if shutil.disk_usage(home).free < 1024**3:
            raise ValueError('Für die Einrichtung wird mindestens 1 GiB freier Speicher benötigt.')
        # One pinned runtime, no resolver upgrades inside the main application environment.
        requirement = ASSETS / 'requirements.txt'
        version = hashlib.sha256(requirement.read_bytes()).hexdigest()
        env = home / 'env'
        ready = ((env / 'bin/python').is_file() and (env / '.lumen-version').is_file()
                 and (env / '.lumen-version').read_text() == version)
        if env.exists() and not env.is_symlink() and not ready:
            raise ValueError('Vorhandene Suchumgebung ist nicht verwaltet. Bitte ein neues Installationsverzeichnis wählen.')
        stage = None
        try:
            if not ready:
                report('Getrennte Suchumgebung einrichten …')
                stage = Path(tempfile.mkdtemp(prefix='.env-', dir=home))
                run([sys.executable, '-m', 'venv', str(stage)])
                run([str(stage / 'bin/python'), '-m', 'pip', '--isolated', '--disable-pip-version-check',
                     'install', '--no-cache-dir', '--only-binary=:all:', '--require-hashes',
                     '--index-url', 'https://pypi.org/simple', '-r', str(requirement)])
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
            python = (stage or env) / 'bin/python'
            run([str(python), '-c',
                 'import sys;sys.path.insert(0,sys.argv[1]);from memory_embedding import Encoder;'
                 'assert len(next(Encoder(sys.argv[2]).encode("Lumen memory")))==384',
                 str(Path(__file__).parent), str(model)])
            check()
            for name in ('LICENSE', 'MODEL.md', 'NOTICE.md', 'requirements.txt'):
                shutil.copyfile(ASSETS / name, home / name)
            if stage:
                (stage / '.lumen-version').write_text(version)
                link = home / ('.activate-' + uuid4().hex)
                try:
                    link.symlink_to(stage.name, target_is_directory=True)
                    os.replace(link, env)
                finally:
                    link.unlink(missing_ok=True)
                stage = None  # now referenced by env; retain any previous runtime for rollback
            report('Bedeutungssuche eingerichtet. Gedächtnisfreigaben bleiben unverändert.')
        finally:
            if stage:
                shutil.rmtree(stage)

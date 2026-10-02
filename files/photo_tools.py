"""Bounded local image indexing and explainable review candidates; never deletes."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
from image_edit import file_stamp
from lumen_store import Store, state_path

MODEL_VERSION = 'clip-multilingual-v1'
MODELS = (
    ('image', 'sentence-transformers/clip-ViT-B-32', '327ab6726d33c0e22f920c83f2ff9e4bd38ca37f'),
    ('text', 'sentence-transformers/clip-ViT-B-32-multilingual-v1', '58edf8cada9e398793dca955574a48cbb7f18be2'),
)
SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}


def runtime():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'lumen/vision'


def available():
    return ((runtime() / 'env-v1/bin/python').is_file() and (runtime() / 'ready-v1').is_file()
            and all((runtime() / kind / 'modules.json').is_file() for kind, _, _ in MODELS))


def emit(**data): print(json.dumps(data, ensure_ascii=False), flush=True)


class BackgroundGate:
    def __init__(self, override=False):
        self.override = override; self.checked = 0; self.store = Store()

    def wait(self):
        if self.override or time.monotonic() - self.checked < 5: return
        from lumen_hardware import background_reason
        while reason := background_reason(self.store):
            emit(status=reason + ' · wird automatisch fortgesetzt', paused=True)
            time.sleep(5)
        self.checked = time.monotonic()


def images(root, limit=10000):
    """No hidden folders/symlinks, bounded enumeration, errors are reported."""
    count = 0
    def error(exc): emit(status='Ordner nicht lesbar: ' + str(exc.filename))
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=error):
        count += len(dirs)
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            count += 1
            if count > limit:
                emit(status=f'Grenze von {limit} Dateien erreicht. Bitte einen kleineren Unterordner wählen.', limited=True)
                return
            path = Path(folder) / name
            if not name.startswith('.') and path.suffix.lower() in SUFFIXES and not path.is_symlink(): yield path


def read_image(path):
    from PIL import Image, ImageOps
    if path.resolve() != path: raise ValueError('Verknüpfung übersprungen')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno()); stamp = file_stamp(info)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 128 * 1024 * 1024: raise ValueError('Bild zu groß')
        with Image.open(stream) as source:
            if source.width * source.height > 80_000_000 or getattr(source, 'n_frames', 1) != 1:
                raise ValueError('Bild zu groß oder animiert')
            exif = source.getexif()
            try: details = exif.get_ifd(34665)
            except (ValueError, KeyError, TypeError): details = {}
            taken = details.get(36867) or exif.get(36867) or exif.get(306)
            try: taken = datetime.strptime(str(taken), '%Y:%m:%d %H:%M:%S').timestamp()
            except ValueError: taken = None
            meta = {'stamp': stamp, 'bytes': info.st_size, 'taken': taken,
                    'camera': str(exif.get(272, '')), 'software': str(exif.get(305, ''))}
            source.thumbnail((1024, 1024))
            image = ImageOps.exif_transpose(source).convert('RGB')
        if stamp != file_stamp(path.stat()): raise ValueError('Bild inzwischen verändert')
    return image, meta


def quality(image):
    from PIL import Image
    pixels = list(image.convert('L').resize((128, 128), Image.Resampling.BILINEAR).getdata())
    laplace = [4 * pixels[i] - pixels[i-1] - pixels[i+1] - pixels[i-128] - pixels[i+128]
               for y in range(1, 127) for x in range(1, 127) for i in (y*128+x,)]
    mean = sum(laplace) / len(laplace)
    sharpness = sum((v-mean)**2 for v in laplace) / len(laplace)
    small = list(image.convert('L').resize((9, 8), Image.Resampling.BILINEAR).getdata())
    fingerprint = sum((small[y*9+x] > small[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8))
    return round(sharpness, 2), fingerprint


def tidy(root, gate):
    photos = []; errors = 0
    for path in images(root, 3000):
        gate.wait()
        try:
            image, meta = read_image(path); score, fingerprint = quality(image)
            photos.append(dict(meta, path=str(path), score=score, fingerprint=fingerprint))
            image.close()
        except (OSError, ValueError): errors += 1
        if len(photos) % 20 == 0: emit(status=f'{len(photos)} Bilder geprüft · {errors} übersprungen')
    ordered = sorted((p for p in photos if p['taken'] is not None), key=lambda p:p['taken'])
    groups = []
    for p in ordered:
        last = groups[-1][-1] if groups else None
        if (last and p['camera'] == last['camera'] and Path(p['path']).parent == Path(last['path']).parent
                and p['taken'] - last['taken'] <= 3 and (p['fingerprint'] ^ last['fingerprint']).bit_count() <= 14):
            groups[-1].append(p)
        else: groups.append([p])
    for i, group in enumerate(g for g in groups if len(g) > 1):
        best = max(group, key=lambda p:p['score'])
        for p in group:
            emit(item={**p, 'group': f'Bildserie {i+1}', 'reason': 'Höchster Detailwert der Serie · behalten prüfen' if p is best else 'Ähnliches Motiv innerhalb von 3 Sekunden'})
    for p in photos:
        if p['score'] < 35:
            emit(item={**p, 'group': 'Wenig Details', 'reason': 'Möglicherweise unscharf · ruhige Motive können ebenfalls hier erscheinen'})
        if any(s in (Path(p['path']).name + ' ' + p['software']).casefold() for s in ('screenshot', 'bildschirmfoto', 'spectacle', 'screencapture')):
            emit(item={**p, 'group': 'Screenshots', 'reason': 'Dateiname oder Metadaten weisen auf eine Bildschirmaufnahme hin'})
    emit(done=True, status=f'{len(photos)} Bilder geprüft · {errors} übersprungen · nichts automatisch ausgewählt')


def model(kind):
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    return SentenceTransformer(str(runtime() / kind), device='cpu', local_files_only=True, trust_remote_code=False)


def install_models():
    from huggingface_hub import snapshot_download
    for kind, name, revision in MODELS:
        emit(status='Lokales Bildsuchmodell herunterladen: ' + kind)
        snapshot_download(name, revision=revision, local_dir=runtime()/kind,
                          allow_patterns=['*.json', '*.txt', '*.safetensors', 'README.md', 'LICENSE*'],
                          ignore_patterns=['onnx/*', 'openvino/*'])
    from PIL import Image
    image = model('image').encode([Image.new('RGB', (224,224), 'blue')], normalize_embeddings=True)
    text = model('text').encode(['Ein blaues Bild'], normalize_embeddings=True)
    if image.shape != text.shape or image.shape != (1, 512): raise ValueError('Bildmodellprüfung fehlgeschlagen')
    (runtime()/'ready-v1').write_text(MODEL_VERSION)
    emit(done=True, status='Lokale Bildsuche mit deutschen Suchbegriffen ist bereit.')


def search(root, query, gate):
    import numpy as np
    gate.wait(); emit(status='Lokale Bildmodelle laden …')
    encoder = model('image')
    directory = state_path(); directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    dbpath = directory / 'photos.sqlite3'
    db = sqlite3.connect(dbpath, timeout=15); os.chmod(dbpath, 0o600)
    db.execute('CREATE TABLE IF NOT EXISTS images (path TEXT PRIMARY KEY, stamp TEXT, model TEXT, vector BLOB)')
    candidates = []; errors = 0
    try:
        for path in images(root):
            gate.wait()
            try:
                stamp = file_stamp(path.stat()); stored = db.execute('SELECT stamp,model,vector FROM images WHERE path=?', (str(path),)).fetchone()
                if stored and json.loads(stored[0]) == stamp and stored[1] == MODEL_VERSION:
                    vector = np.frombuffer(stored[2], dtype=np.float32)
                else:
                    image, meta = read_image(path)
                    vector = encoder.encode([image], normalize_embeddings=True)[0].astype(np.float32); image.close()
                    stamp = meta['stamp']
                    with db: db.execute('INSERT OR REPLACE INTO images VALUES (?,?,?,?)', (str(path), json.dumps(stamp), MODEL_VERSION, vector.tobytes()))
                if vector.shape == (512,) and np.isfinite(vector).all(): candidates.append((str(path), stamp, vector))
            except (OSError, ValueError): errors += 1
            if len(candidates) % 10 == 0: emit(status=f'{len(candidates)} Bilder im lokalen Index · {errors} übersprungen')
        del encoder
        gate.wait(); emit(status='Bildmotive vergleichen …')
        needle = model('text').encode([query], normalize_embeddings=True)[0]
        ranked = sorted(((float(vector @ needle), path, stamp) for path, stamp, vector in candidates), reverse=True)
        for score, path, stamp in ranked[:100]:
            try:
                if file_stamp(Path(path).stat()) != stamp or Path(path).resolve() != Path(path): continue
            except OSError: continue
            emit(item={'path':path, 'stamp':stamp, 'group':f'Ähnlichkeit {score:.2f}', 'reason':'Motivähnlichkeit · kein Sicherheitswert'})
        emit(done=True, status=f'{len(candidates)} Bilder lokal verglichen · {errors} übersprungen · beste Motive zuerst')
    finally: db.close()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['search','tidy','install'])
    parser.add_argument('directory', nargs='?'); parser.add_argument('--query', default=''); parser.add_argument('--override', action='store_true')
    args = parser.parse_args()
    try:
        try: os.nice(10)
        except OSError: pass
        if args.action == 'install': install_models(); return 0
        root = Path(args.directory).expanduser().resolve(strict=True)
        if not root.is_dir(): raise ValueError('Bitte einen erreichbaren Ordner auswählen.')
        gate = BackgroundGate(args.override)
        if args.action == 'tidy': tidy(root, gate)
        else:
            if not args.query.strip(): raise ValueError('Bitte ein Bildmotiv eingeben.')
            search(root, args.query[:500], gate)
        return 0
    except Exception as error:
        emit(error=str(error)); return 1


if __name__ == '__main__': sys.exit(main())

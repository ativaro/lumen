"""Dependency discovery and explicit setup jobs; no work happens on import."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

FEATURES = {
    'engine': ('Lumen-Assistent', ('opencode',), ('opencode',)),
    'documents': ('PDF-Vorschau und Inhaltsuche', ('pdfinfo', 'pdftoppm', 'pdftotext'), ('poppler',)),
    'media': ('Video- und Audiovorschau', ('ffmpeg', 'ffprobe'), ('ffmpeg',)),
    'network': ('NAS und Netzwerkordner', ('kio-fuse', 'kioclient'), ('kio-fuse', 'kio-extras', 'kde-cli-tools')),
    'capture': ('Bildschirmaufnahme', ('spectacle',), ('spectacle',)),
}
VERSION = '1.9.4'
SOURCE_URL = f'https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/refs/tags/v{VERSION}'
SOURCE_HASH = '57e280cee375ab02425b806ad5146b99f6eb9357e3c2b31357c8a6af2e2e44ae'
MODEL_URL = ('https://huggingface.co/ggerganov/whisper.cpp/resolve/'
             '5359861c739e955e79d9a303bcbc70fb988958b1/ggml-small-q5_1.bin')
MODEL_HASH = 'ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'
MODEL_SIZE = 190085487


def speech_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'lumen/speech'


def executable(name):
    if name == 'opencode':
        from assistant_backend import opencode_binary
        return opencode_binary()
    if name == 'whisper-cli':
        return shutil.which(name) or _executable(speech_root() / f'whisper-{VERSION}')
    return shutil.which(name) or next((_executable(Path(folder) / name) for folder in
        ('/usr/lib', '/usr/lib/kf6') if _executable(Path(folder) / name)), '')


def _executable(path):
    return str(path) if path.is_file() and os.access(path, os.X_OK) else ''


def missing_packages(groups):
    packages = set()
    for group in groups:
        _title, commands, names = FEATURES[group]
        if not all(executable(command) for command in commands): packages.update(names)
    return sorted(packages)


def report(message, percent=-1, cancellable=True, **extra):
    print(json.dumps({'message': message, 'percent': percent, 'cancellable': cancellable, **extra}), flush=True)


def run(command, timeout=1200):
    # No shell and no credentials in command arguments. Capture build/package noise.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, stdout=output, stderr=output, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
        if code:
            output.seek(max(0, output.tell() - 1800))
            raise RuntimeError(output.read().decode(errors='replace').strip() or 'Einrichtung fehlgeschlagen.')


def install_packages(packages):
    allowed = {p for _title, _commands, names in FEATURES.values() for p in names}
    allowed.update(('cmake', 'gcc', 'make', 'pipewire-audio'))
    if not set(packages) <= allowed: raise ValueError('Unbekannte Paketauswahl.')
    if not packages: return
    if not Path('/usr/bin/pacman').exists() or not shutil.which('pkexec'):
        raise RuntimeError('Automatische Paketinstallation benötigt Arch/CachyOS und Polkit. '
                           'Bitte diese Pakete über deine Paketverwaltung installieren: ' + ', '.join(packages))
    report('Systempakete installieren · gegebenenfalls das Passwort im Systemdialog eingeben.', cancellable=False)
    run(['pkexec', '/usr/bin/pacman', '-S', '--needed', '--noconfirm', '--', *packages])


def download(url, destination, checksum, size):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    received = 0; previous = -1
    # Replace only after verification. Interrupted/failed downloads preserve old files.
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        partial = Path(output.name)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                if not response.url.startswith('https://'): raise ValueError('Unsicheres Downloadziel.')
                while chunk := response.read(256 * 1024):
                    received += len(chunk)
                    if received > size: raise ValueError('Der Download ist unerwartet groß.')
                    digest.update(chunk); output.write(chunk)
                    percent = int(received * 100 / size)
                    if percent != previous:
                        report('Herunterladen …', percent); previous = percent
            if received != size or digest.hexdigest() != checksum:
                raise ValueError('Die Prüfsumme stimmt nicht. Bitte den Download erneut versuchen.')
            output.flush(); os.fsync(output.fileno())
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)


def install_dictation():
    packages = []
    if not executable('pw-record'): packages.append('pipewire-audio')
    if not executable('whisper-cli'):
        packages.extend(package for command, package in (('cmake', 'cmake'), ('g++', 'gcc'), ('make', 'make'))
                        if not shutil.which(command))
    install_packages(packages)
    root = speech_root(); root.mkdir(parents=True, exist_ok=True)
    if not executable('whisper-cli'):
        with tempfile.TemporaryDirectory(prefix='build-', dir=root) as folder:
            folder = Path(folder); archive = folder / 'whisper.tar.gz'
            report('Spracherkennung herunterladen · whisper.cpp ' + VERSION)
            download(SOURCE_URL, archive, SOURCE_HASH, 9353438)
            with tarfile.open(archive) as source: source.extractall(folder, filter='data')
            report('Spracherkennung für diesen Rechner vorbereiten …')
            build = folder / 'build'
            run(['cmake', '-S', str(folder / f'whisper.cpp-{VERSION}'), '-B', str(build),
                 '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF', '-DWHISPER_BUILD_TESTS=OFF',
                 '-DWHISPER_CURL=OFF', '-DGGML_NATIVE=OFF'])
            run(['cmake', '--build', str(build), '--target', 'whisper-cli', '-j', str(min(4, os.cpu_count() or 1))])
            binary = build / 'bin/whisper-cli'
            run([str(binary), '--help'], timeout=20)
            binary.chmod(0o755); os.replace(binary, root / f'whisper-{VERSION}')
    model = root / 'ggml-small-q5_1.bin'
    valid = model.is_file() and model.stat().st_size == MODEL_SIZE
    if valid:
        with model.open('rb') as file: valid = hashlib.file_digest(file, 'sha256').hexdigest() == MODEL_HASH
    if not valid:
        report('Mehrsprachiges Diktiermodell herunterladen · 190 MB')
        download(MODEL_URL, model, MODEL_HASH, MODEL_SIZE)
    report('Lokales Diktieren ist vorbereitet.', 100, model=str(model))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('packages', 'dictation'))
    parser.add_argument('groups', nargs='*', choices=tuple(FEATURES))
    args = parser.parse_args()
    def interrupted(*_): raise InterruptedError('Einrichtung abgebrochen. Bereits fertige Bestandteile bleiben verfügbar.')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.action == 'dictation': install_dictation()
        else:
            install_packages(missing_packages(args.groups))
            missing = missing_packages(args.groups)
            if missing: raise RuntimeError('Noch nicht verfügbar: ' + ', '.join(missing))
            report('Ausgewählte Erweiterungen sind verfügbar.', 100)
        return 0
    except Exception as error:
        report(str(error)); return 1


if __name__ == '__main__': sys.exit(main())

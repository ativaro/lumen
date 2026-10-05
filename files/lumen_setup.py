"""Dependency discovery and explicit setup jobs; no work happens on import."""
from lumen_i18n import worker_environment, tr
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import sys
import tarfile
import tempfile
import urllib.request

FEATURES = {
    'translate_pdf': (tr('Translate: PDF-Layoutübersetzung'), ('pymupdf',), ('python-pymupdf',)),
    'sound': (tr('Sound: Lautstärke und App-Ausgänge'), ('pactl',), ('libpulse',)),
    'reader': (tr('Reader: PDF- und EPUB-Lesen'), ('pymupdf',), ('python-pymupdf',)),
    'keyring': (tr('System-Schlüsselbund für Vault und Inbox'), ('secret-tool',), ('libsecret',)),
    'hardware': (tr('Hardware-Messwerte'), ('sensors',), ('lm_sensors',)),
    'engine': (tr('Lumen-Assistent'), ('opencode',), ('opencode',)),
    'documents': (tr('PDF-Vorschau und Inhaltsuche'), ('pdfinfo', 'pdftoppm', 'pdftotext'), ('poppler',)),
    'media': (tr('Video- und Audiovorschau'), ('ffmpeg', 'ffprobe'), ('ffmpeg',)),
    'network': (tr('NAS und Netzwerkordner'), ('kio-fuse', 'kioclient', 'kio-smb', 'gvfsd-smb', 'gvfsd-fuse', 'gvfsd-wsdd', 'smbclient'), ('kio-fuse', 'kio-extras', 'kde-cli-tools', 'gvfs', 'gvfs-smb', 'gvfs-wsdd', 'smbclient')),
    'workshop': (tr('PDF-Dokumentenwerkstatt'), ('pymupdf',), ('python-pymupdf',)),
    'ocr': (tr('Texterkennung in Bildern und Scans'), ('tesseract', 'tessdata-deu', 'tessdata-eng'), ('tesseract', 'tesseract-data-deu', 'tesseract-data-eng')),
    'capture': (tr('Bildschirmaufnahme'), ('spectacle',), ('spectacle',)),
}
VERSION = '1.9.4'
SOURCE_URL = f'https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/refs/tags/v{VERSION}'
SOURCE_HASH = '57e280cee375ab02425b806ad5146b99f6eb9357e3c2b31357c8a6af2e2e44ae'
MODEL_URL = ('https://huggingface.co/ggerganov/whisper.cpp/resolve/'
             '5359861c739e955e79d9a303bcbc70fb988958b1/ggml-small-q5_1.bin')
MODEL_HASH = 'ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'
MODEL_SIZE = 190085487
QUALITY_MODEL = 'ggml-large-v3-turbo-q8_0.bin'
QUALITY_HASH = '317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1'
QUALITY_SIZE = 874188075


def speech_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'lumen/speech'


def executable(name):
    if name == 'pymupdf':
        import importlib.util
        return 'python-pymupdf' if importlib.util.find_spec('pymupdf') else ''
    if name.startswith('tessdata-'):
        path = Path('/usr/share/tessdata') / (name.removeprefix('tessdata-') + '.traineddata')
        return str(path) if path.is_file() else ''
    if name == 'kio-smb':
        path = Path('/usr/lib/qt6/plugins/kf6/kio/smb.so')
        return str(path) if path.is_file() else ''
    if name == 'opencode':
        from assistant_backend import opencode_binary
        return shutil.which(opencode_binary()) or ''
    if name == 'piper-tts':
        return _executable(speech_root() / 'piper-env/bin/piper')
    if name == 'voice-vad':
        return _executable(speech_root()/'vad-env/bin/python') if (speech_root()/'vad-env/.ready').is_file() else ''
    if name == 'whisper-cli':
        return shutil.which(name) or _executable(speech_root() / f'whisper-{VERSION}')
    return shutil.which(name) or next((_executable(Path(folder) / name) for folder in
        ('/usr/lib', '/usr/lib/kf6', '/usr/lib/gvfs') if _executable(Path(folder) / name)), '')


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
        process = subprocess.Popen(command, env=worker_environment(), stdout=output, stderr=output, start_new_session=True)
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
            raise RuntimeError(output.read().decode(errors='replace').strip() or tr('Einrichtung fehlgeschlagen.'))


def install_packages(packages):
    allowed = {p for _title, _commands, names in FEATURES.values() for p in names}
    allowed.update(('cmake', 'gcc', 'make', 'pipewire-audio'))
    if not set(packages) <= allowed: raise ValueError(tr('Unbekannte Paketauswahl.'))
    if not packages: return
    if not Path('/usr/bin/pacman').exists() or not shutil.which('pkexec'):
        raise RuntimeError(tr('Automatische Paketinstallation benötigt Arch/CachyOS und Polkit. '
                           'Bitte diese Pakete über deine Paketverwaltung installieren: ') + ', '.join(packages))
    report(tr('Systempakete installieren · gegebenenfalls das Passwort im Systemdialog eingeben.'), cancellable=False)
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
                if not response.url.startswith('https://'): raise ValueError(tr('Unsicheres Downloadziel.'))
                while chunk := response.read(256 * 1024):
                    received += len(chunk)
                    if received > size: raise ValueError(tr('Der Download ist unerwartet groß.'))
                    digest.update(chunk); output.write(chunk)
                    percent = int(received * 100 / size)
                    if percent != previous:
                        report(tr('Herunterladen …'), percent); previous = percent
            if received != size or digest.hexdigest() != checksum:
                raise ValueError(tr('Die Prüfsumme stimmt nicht. Bitte den Download erneut versuchen.'))
            output.flush(); os.fsync(output.fileno())
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)


def install_engine():
    """Install Lumen's verified v1 engine without replacing a user's OpenCode."""
    from assistant_backend import ENGINE_VERSION, managed_opencode
    if os.environ.get('LUMEN_OPENCODE_BIN'):
        raise RuntimeError(tr('LUMEN_OPENCODE_BIN überschreibt die Engine. Bitte diese Vorgabe zuerst entfernen.'))
    assets = {
        'x86_64': ('x64-baseline', 60665421, '24b0d458d21ef548b2752166303defcf7f4945b049fb4876ab78dfaf86d81b27'),
        'aarch64': ('arm64', 60479105, 'bbdb3f00c2c51e42e315525233151309724226a8776da8e9145e3b0fa3d5310f'),
    }
    if sys.platform != 'linux' or platform.machine() not in assets:
        raise RuntimeError(tr('Die kompatible Engine ist für Linux x86_64 und ARM64 verfügbar.'))
    target = managed_opencode()
    target.parent.mkdir(parents=True, exist_ok=True)
    arch, size, checksum = assets[platform.machine()]
    report(tr('Kompatible Engine für Lumen einrichten …'))
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        archive = Path(tmp)/'engine.tar.gz'; candidate = Path(tmp)/'opencode'
        download(f'https://github.com/anomalyco/opencode/releases/download/v{ENGINE_VERSION}/opencode-linux-{arch}.tar.gz',
                 archive, checksum, size)
        with tarfile.open(archive, 'r:gz') as bundle:
            member = bundle.getmember('opencode')
            if not member.isfile() or member.size > 300_000_000:
                raise ValueError(tr('Ungültiges Engine-Archiv.'))
            with bundle.extractfile(member) as source, candidate.open('wb') as destination:
                shutil.copyfileobj(source, destination)
        candidate.chmod(0o700)
        result = subprocess.run([str(candidate), '--version'], capture_output=True, text=True,
                                env=worker_environment(), timeout=15, check=True)
        if result.stdout.strip() != ENGINE_VERSION:
            raise ValueError(tr('Die Engine-Version stimmt nicht mit der geprüften Version überein.'))
        os.replace(candidate, target)
    report(tr('Kompatible Engine eingerichtet. Vorhandenes OpenCode und Zugangsdaten bleiben erhalten.'), 100)


def install_vad():
    if executable('voice-vad'): return
    # Some Python versions need to compile the small WebRTC extension.
    install_packages([] if shutil.which('gcc') else ['gcc'])
    environment = speech_root() / 'vad-env'
    report(tr('Lokale Erkennung von Sprechpausen vorbereiten …'))
    python = environment / 'bin/python'
    if not python.is_file(): run([sys.executable, '-m', 'venv', str(environment)])
    run([str(python), '-m', 'pip', '--disable-pip-version-check', 'install', 'webrtcvad-wheels==2.0.14'])
    run([str(python), '-c', "import webrtcvad; assert not webrtcvad.Vad(2).is_speech(bytes(640), 16000)"], timeout=20)
    (environment / '.ready').write_text('webrtcvad-wheels==2.0.14\n')


def install_dictation(existing_model='', quality=False):
    if existing_model and not Path(existing_model).is_file():
        raise ValueError(tr('Das gewählte Sprachmodell ist nicht mehr erreichbar.'))
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
            report(tr('Spracherkennung herunterladen · whisper.cpp ') + VERSION)
            download(SOURCE_URL, archive, SOURCE_HASH, 9353438)
            with tarfile.open(archive) as source: source.extractall(folder, filter='data')
            report(tr('Spracherkennung für diesen Rechner vorbereiten …'))
            build = folder / 'build'
            # Reuse an installed Vulkan development stack; CPU remains the default elsewhere.
            vulkan = bool(shutil.which('glslc') and all(Path(path).is_file() for path in
                ('/usr/share/cmake/SPIRV-Headers/SPIRV-HeadersConfig.cmake', '/usr/include/vulkan/vulkan.h', '/usr/lib/libvulkan.so')))
            run(['cmake', '-S', str(folder / f'whisper.cpp-{VERSION}'), '-B', str(build),
                 '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF', '-DWHISPER_BUILD_TESTS=OFF',
                 '-DWHISPER_CURL=OFF', '-DGGML_NATIVE=OFF', '-DGGML_VULKAN=' + ('ON' if vulkan else 'OFF')])
            run(['cmake', '--build', str(build), '--target', 'whisper-cli', '-j', str(min(4, os.cpu_count() or 1))])
            binary = build / 'bin/whisper-cli'
            run([str(binary), '--help'], timeout=20)
            binary.chmod(0o755); os.replace(binary, root / f'whisper-{VERSION}')
    install_vad()
    if existing_model and not quality:
        report(tr('Spracherkennung bereit · dein vorhandenes Modell bleibt ausgewählt.'), 100, model=existing_model)
        return
    model = root / (QUALITY_MODEL if quality else 'ggml-small-q5_1.bin')
    checksum, size = (QUALITY_HASH, QUALITY_SIZE) if quality else (MODEL_HASH, MODEL_SIZE)
    valid = model.is_file() and model.stat().st_size == size
    if valid:
        with model.open('rb') as file: valid = hashlib.file_digest(file, 'sha256').hexdigest() == checksum
    if not valid:
        report(tr('Whisper Large v3 Turbo herunterladen · 874 MB') if quality else tr('Mehrsprachiges Diktiermodell herunterladen · 190 MB'))
        download(MODEL_URL.rsplit('/', 1)[0] + '/' + model.name, model, checksum, size)
    report(tr('Lokales Diktieren ist vorbereitet.'), 100, model=str(model))


def install_voice(existing_model=''):
    install_dictation(existing_model)
    root = speech_root(); environment = root / 'piper-env'
    report(tr('Lokale Sprachausgabe vorbereiten · Piper'))
    if not (environment / 'bin/python').is_file(): run([sys.executable, '-m', 'venv', str(environment)])
    run([str(environment / 'bin/python'), '-m', 'pip', '--disable-pip-version-check', 'install', 'piper-tts==1.8.0'])
    base = 'https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/thorsten/medium/'
    for name, checksum, size in [
        ('de_DE-thorsten-medium.onnx', '7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819', 63201294),
        ('de_DE-thorsten-medium.onnx.json', '974adee790533adb273a1ac88f49027d2a1b8f0f2cf4905954a4791e79264e85', 4819),
        ('MODEL_CARD', '5196b5ab0794e6056263a1f37c18bec407b61ac187529bee29d1c366871e5c9e', 285)]:
        target = root / name
        valid = target.is_file() and target.stat().st_size == size
        if valid:
            with target.open('rb') as stream: valid = hashlib.file_digest(stream, 'sha256').hexdigest() == checksum
        if not valid: download(base + name, target, checksum, size)
    report(tr('Sprachgespräch eingerichtet · Whisper und deutsche Piper-Stimme lokal.'), 100)


def install_image_search():
    from photo_tools import runtime
    environment = runtime() / 'env-v1'; python = str(environment / 'bin/python')
    report(tr('Lokale Bildsuche vorbereiten · CPU-Laufzeit und mehrsprachige CLIP-Modelle, ca. 2 GB Download'))
    if not Path(python).is_file(): run([sys.executable, '-m', 'venv', str(environment)])
    run([python, '-m', 'pip', '--disable-pip-version-check', 'install', 'torch==2.14.1', '--index-url', 'https://download.pytorch.org/whl/cpu'])
    run([python, '-m', 'pip', '--disable-pip-version-check', 'install', 'sentence-transformers==6.1.0', 'Pillow==12.3.0'])
    report(tr('Bildmodelle herunterladen und mit lokaler Inferenz prüfen …'))
    run([python, str(Path(__file__).with_name('photo_tools.py')), 'install'], timeout=1800)
    report(tr('Lokale Bildsuche ist bereit. In Files über „Bilder nach Motiv suchen“.'), 100)


def install_multilingual_voice():
    from speech_model import MODEL_REPO, MODEL_REVISION, MODEL_FILES
    root = speech_root(); environment = root/'qwen-env'; model = root/'qwen-0.6b'
    report(tr('Mehrsprachige Stimme vorbereiten · eigene Laufzeit, mehrere GB Download.'))
    if not (environment/'bin/python').is_file(): run([sys.executable, '-m', 'venv', str(environment)])
    run([str(environment/'bin/python'), '-m', 'pip', '--disable-pip-version-check', 'install',
         'qwen-tts==0.1.1', 'torch==2.14.1', 'torchaudio==2.11.0'])
    model.mkdir(parents=True, exist_ok=True)
    for name, checksum, size in MODEL_FILES:
        target = model/name
        valid = target.is_file() and target.stat().st_size == size
        if valid:
            with target.open('rb') as stream: valid = hashlib.file_digest(stream, 'sha256').hexdigest() == checksum
        if not valid:
            report(tr('Mehrsprachiges Sprachmodell herunterladen · ca. 2,5 GB.'))
            download(f'https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}', target, checksum, size)
    report(tr('Mehrsprachige Stimme lokal prüfen …'))
    run([str(environment/'bin/python'), str(Path(__file__).with_name('speech_worker.py')), '--check'], timeout=600)
    (model/'.ready').write_text(MODEL_REVISION+'\n')
    report(tr('Mehrsprachige Sprachausgabe ist bereit. Deutsch und Englisch werden gemeinsam verarbeitet.'), 100)


def install_vault():
    import bz2
    import platform
    archives = {'x86_64': ('amd64', 'f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c', 10107515),
                'aarch64': ('arm64', 'a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465', 9044264)}
    if platform.machine() not in archives: raise ValueError(tr('Restic bitte über die Paketverwaltung installieren.'))
    arch, checksum, size = archives[platform.machine()]
    root = speech_root().parent / 'vault'; root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        archive = Path(tmp)/'restic.bz2'; binary = Path(tmp)/'restic'
        report(tr('Verschlüsselte Sicherungen vorbereiten · Restic 0.19.1'))
        download(f'https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_{arch}.bz2',archive,checksum,size)
        with bz2.open(archive,'rb') as src, binary.open('wb') as dst:
            shutil.copyfileobj(src,dst)
        binary.chmod(0o755); run([str(binary),'version'],timeout=10)
        os.replace(binary,root/'restic-0.19.1')
    report(tr('Vault bereit. Ziel und Sicherungspasswort in Lumen Vault auswählen.'),100)


def install_inbox():
    root = speech_root().parent / 'inbox-env-v1'; python = str(root / 'bin/python')
    report(tr('Kalenderanbindung für Inbox vorbereiten'))
    if not Path(python).is_file(): run([sys.executable,'-m','venv',str(root)])
    run([python,'-m','pip','--disable-pip-version-check','install','caldav==3.3.1','icalendar==7.3.0','recurring-ical-events==3.8.2'])
    run([python,'-c','import caldav, icalendar'],timeout=20)
    report(tr('IMAP/SMTP und Kalenderanbindung bereit. Proton Mail benötigt zusätzlich die angemeldete Proton Mail Bridge.'),100)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('packages', 'engine', 'dictation', 'dictation-quality', 'voice', 'voice-multilingual', 'desktop', 'image-search', 'vault', 'inbox'))
    parser.add_argument('groups', nargs='*', choices=tuple(FEATURES))
    parser.add_argument('--existing-model', default='')
    from appearance import DESIGNS
    parser.add_argument('--theme', choices=[name for _, name in DESIGNS], default='glass')
    args = parser.parse_args()
    def interrupted(*_): raise InterruptedError(tr('Einrichtung abgebrochen. Bereits fertige Bestandteile bleiben verfügbar.'))
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.action == 'desktop':
            from lumen_desktop_setup import configure_desktop
            report(tr('Desktop-Konfiguration sichern und Lumen-Desktop aktivieren …'), cancellable=False)
            configure_desktop(args.theme, replace_panels=True)
            report(tr('Lumen-Desktop eingerichtet. Die vorherige Konfiguration wurde lokal gesichert.'), 100, cancellable=False)
        elif args.action == 'engine': install_engine()
        elif args.action == 'dictation': install_dictation(args.existing_model)
        elif args.action == 'dictation-quality': install_dictation(quality=True)
        elif args.action == 'voice': install_voice(args.existing_model)
        elif args.action == 'voice-multilingual': install_multilingual_voice()
        elif args.action == 'image-search': install_image_search()
        elif args.action == 'vault': install_vault()
        elif args.action == 'inbox': install_inbox()
        else:
            if 'engine' in args.groups: install_engine()
            install_packages(missing_packages([group for group in args.groups if group != 'engine']))
            missing = missing_packages(args.groups)
            if missing: raise RuntimeError(tr('Noch nicht verfügbar: ') + ', '.join(missing))
            report(tr('Ausgewählte Erweiterungen sind verfügbar.'), 100)
        return 0
    except Exception as error:
        report(str(error)); return 1


if __name__ == '__main__': sys.exit(main())

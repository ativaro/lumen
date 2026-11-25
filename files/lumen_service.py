"""The Qt side's binding to Lumen's desktop service `lumen-service` (native/service).

Starts the service on demand as a user process, replaces one that runs from another build than the
installed program, and sends it one request per connection over `$XDG_RUNTIME_DIR/lumen/service.sock`.
The protocol is described in native/service/README.md; the logic lives in the service. The engine
conversations stream over the same socket (assistant_backend.py), and so do the requests to the Lumen
Server (lumen_connect.py), the persona's catalogue and preview (persona_settings.py) and Lumen Notes'
notebook (wissen_data.py).
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import threading
import time

VERSION = 1
MAX_INPUT = 16 * 1024 * 1024
_checked = None  # socket and installed program whose build answered last


def program():
    from lumen_office import program as find
    return find('lumen-service', 'service')


def channel():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise OSError('XDG_RUNTIME_DIR is not set; the Lumen service needs the private runtime folder')
    return Path(runtime) / 'lumen' / 'service.sock'


def unit():
    """Whether this process runs in a systemd service unit (the server connection, a timer's job)."""
    try:
        return Path('/proc/self/cgroup').read_text().strip().endswith('.service')
    except OSError:
        return False


def start(binary, scope=True):
    """A second service started at the same time finds the lock taken and leaves. Started from a systemd
    unit, the service gets a scope of its own: the unit's end would otherwise end the service the views share."""
    command = [binary]
    if scope and unit() and shutil.which('systemd-run'):
        command = ['systemd-run', '--user', '--scope', '--quiet', '--collect', '--description=Lumen service', '--', binary]
    # Without the variable ONNX Runtime 1.30 keeps a device identifier below HOME; the service refuses to load it.
    service = subprocess.Popen(command, cwd='/', start_new_session=True, env={**os.environ, 'ORT_DISABLE_TELEMETRY': '1'},
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def reap():
        # The service outlives requests and may quit (update, session end) while the view runs: reap it then.
        # systemd-run without a user manager to ask fails at once; the service then starts in this unit.
        if service.wait() > 0 and command[0] == 'systemd-run':
            start(binary, scope=False)
    threading.Thread(target=reap, name='lumen-service-reaper', daemon=True).start()


def connect(binary, path, deadline):
    """A connection to this user's service, started when none listens. TimeoutError when it takes too long."""
    started = False
    while True:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(max(.05, deadline - time.monotonic()))
            connection.connect(str(path))
            _, uid, _ = struct.unpack('iII', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.geteuid():
                raise PermissionError('The Lumen service socket belongs to another user')
            return connection
        except (FileNotFoundError, ConnectionRefusedError):
            connection.close()
            if not started:
                start(binary)
                started = True
            if time.monotonic() >= deadline:
                raise TimeoutError('Lumen service did not start') from None
            time.sleep(.01)
        except BaseException:
            connection.close()
            raise


def encode(request):
    data = json.dumps({'v': VERSION, **request}).encode()
    if len(data) > MAX_INPUT:
        raise OverflowError('Lumen service request too large')
    return data


def decode(data):
    answer = json.loads(data)
    if not isinstance(answer, dict) or answer.get('v') != VERSION or 'error' in answer:
        raise ValueError('Lumen service refused the request: ' + str(answer)[:200])
    del answer['v']
    return answer


def exchange(binary, path, request, deadline, limit=2 * MAX_INPUT, payload=b''):
    """One answer of at most `limit` bytes, starting the service when none listens. A `payload`
    (an attachment's bytes) follows the request's line. TimeoutError when it takes too long."""
    data = encode(request)
    with connect(binary, path, deadline) as connection:
        connection.sendall(data + b'\n' + payload if payload else data)
        connection.shutdown(socket.SHUT_WR)
        answer = bytearray()
        while chunk := connection.recv(1 << 16):
            answer += chunk
            if len(answer) > limit:
                raise ValueError('Lumen service answer too large')
    return decode(answer)


def stream(request, idle, check=None):
    """The answer lines of a request that streams (`bridge.receive`). The connection stays open while they are
    read; closing it, also through an exception of `check` (run at least every 0.1 s), cancels the request.
    TimeoutError after `idle` seconds without a line."""
    binary, path, deadline = ensure()
    with connect(binary, path, deadline) as connection:
        connection.sendall(encode(request) + b'\n')
        connection.settimeout(.1)
        buffer, quiet = bytearray(), time.monotonic() + idle
        while True:
            if check:
                check()
            try:
                chunk = connection.recv(1 << 16)
            except TimeoutError:
                if time.monotonic() > quiet:
                    raise TimeoutError('The Lumen service did not answer in time') from None
                continue
            if not chunk:
                raise ConnectionError('The Lumen service ended the request')
            buffer += chunk
            quiet = time.monotonic() + idle
            while (end := buffer.find(b'\n')) >= 0:
                line = bytes(buffer[:end])
                del buffer[:end + 1]
                yield decode(line)


def ensure(timeout=3, revive=False):
    """The service runs the installed program: before the first request to a newly installed program the
    running service is asked for its build; one from another build is told to quit and the new one starts.
    `revive` starts a service that has ended since. Returns what `exchange` needs."""
    global _checked
    deadline, binary, path = time.monotonic() + timeout, program(), channel()
    info = os.stat(binary)
    installed = (str(path), binary, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if installed != _checked:
        with open(binary, 'rb') as stream:
            build = hashlib.file_digest(stream, 'sha256').hexdigest()
        if exchange(binary, path, {'op': 'hello'}, deadline).get('build') != build:
            exchange(binary, path, {'op': 'quit'}, deadline)
            if exchange(binary, path, {'op': 'hello'}, deadline).get('build') != build:
                raise ValueError('The Lumen service does not run the installed program')
        _checked = installed
    elif revive:
        exchange(binary, path, {'op': 'hello'}, deadline)
    return binary, path, deadline


def ask(request, timeout=3, limit=2 * MAX_INPUT, payload=b''):
    """The service's answer to `{'op': ..., ...}`."""
    binary, path, deadline = ensure(timeout)
    return exchange(binary, path, request, deadline, limit, payload)


def refused(answer):
    """Raises the exception a refusal of `notes.*` or `memory.*` stands for, as the earlier Python code raised
    it: ValueError, UnicodeError or OSError(errno, strerror, filename)."""
    if 'failed' not in answer:
        return
    if answer['kind'] == 'os':
        errno, name = answer['errno'], answer['filename']
        if name is None:
            raise OSError(errno, os.strerror(errno))
        raise OSError(errno, os.strerror(errno), Path(name) if answer['path_object'] else name)
    raise (UnicodeError if answer['kind'] == 'unicode' else ValueError)(answer['failed'])


def texts():
    """The window's language and the English catalogue the service translates with (src/texts.rs)."""
    from lumen_i18n import language
    return {'language': language(), 'catalogue': str(Path(__file__).with_name('translations') / 'en')}


_persona = {}  # the persona catalogue by language; it is compiled into the service


def persona_catalogue():
    """The persona's `presets` (`id`, `title`, `description`) and `fields` (`id`, `title`, `options`) with their
    titles in the window's language (`persona.catalog`)."""
    request = {'op': 'persona.catalog', 'texts': texts()}
    language = request['texts']['language']
    if language not in _persona:
        _persona[language] = ask(request)
    return _persona[language]


def persona_presets():
    """The IDs of the persona presets; none while the service cannot be reached."""
    try:
        return [row['id'] for row in persona_catalogue()['presets']]
    except (OSError, ValueError):
        return []


def persona_preview(profile, choice=''):
    """`{'profile': …, 'preview': …}`: the profile the JSON text `profile` stands for, with the traits of the
    preset `choice` when one is named, and its illustrative preview in the window's language."""
    return ask({'op': 'persona.preview', 'texts': texts(), 'profile': profile, 'choice': choice})


def engine_info(environment=None):
    """The OpenCode release the service controls (`version`), Lumen's own engine (`managed`) and the
    program the service would start (`binary`) for this environment."""
    return ask({'op': 'engine.info', 'env': dict(os.environ if environment is None else environment)})

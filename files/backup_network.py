"""Bounded, headless SMB discovery/mount helper. Credentials use pipes only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit, unquote


def address(value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid network address')
    if not value.startswith('smb://'):
        value = 'smb://' + value
    url = urlsplit(value)
    if url.scheme != 'smb' or url.username or url.password or url.query or url.fragment or url.port:
        raise ValueError('Use an SMB address without credentials')
    return 'smb://' + url.netloc + (url.path or '/')


def mounted_path(file, timeout=2):
    """GVfs can announce a share before its FUSE directory is available."""
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '')) / 'gvfs'
    if not runtime.is_absolute() or not os.path.ismount(runtime):
        return None
    deadline = time.monotonic() + timeout
    while True:
        path = file.get_path()
        if path:
            candidate = Path(path)
            if not candidate.resolve().is_relative_to(runtime.resolve()):
                return None
            if candidate.is_dir():
                return str(candidate)
        if time.monotonic() >= deadline:
            return None
        time.sleep(.05)


def worker(request, discovery_uri=None):
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
    if request.get('op') == 'discover':
        rows = []
        for endpoint in ('wsdd:///', 'smb:///'):
            try:
                result = worker({'op': 'browse'}, discovery_uri=endpoint)
                rows.extend(result.get('items', []))
            except GLib.Error: pass
        return {'items': list({row['uri']: row for row in rows}.values())}
    uri = discovery_uri or address(request.get('uri', 'smb://'))
    file = Gio.File.new_for_uri(uri)
    username, password = request.get('username', ''), request.get('password', '')
    domain = request.get('domain', '')
    if any(not isinstance(v, str) or len(v) > 4096 or any(c in v for c in '\r\n\x00') for v in (username, password, domain)):
        return {'error': 'invalid_credentials'}
    if password:
        # An existing GVfs mount may use a different cached password. Verify the
        # supplied credential separately before offering to remember it.
        url = urlsplit(uri); share = unquote(url.path).strip('/').split('/')[0]
        args = ['smbclient', '-A', '/dev/stdin', '-t', '10']
        args += ['//'+url.hostname+'/'+share, '-c', 'quit'] if share else ['-L', url.hostname or '', '-g']
        auth = 'username = '+username+'\npassword = '+password+'\ndomain = '+domain+'\n'
        try:
            checked = subprocess.run(args, input=auth.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            if checked.returncode: return {'error': 'auth_required'}
        except (OSError, subprocess.TimeoutExpired):
            return {'error': 'auth_required'}
    mount = Gio.MountOperation(); asked = []
    def ask(operation, _message, _default_user, _default_domain, _flags):
        if asked or not username or not password:
            operation.reply(Gio.MountOperationResult.ABORTED); return
        asked.append(True)
        operation.set_username(username); operation.set_password(password); operation.set_domain(domain)
        operation.set_password_save(Gio.PasswordSave.FOR_SESSION)
        operation.reply(Gio.MountOperationResult.HANDLED)
    mount.connect('ask-password', ask)
    mount.connect('ask-question', lambda op, *_: op.reply(Gio.MountOperationResult.ABORTED))
    def connect():
        loop = GLib.MainLoop(); errors = []
        def done(f, result):
            try: f.mount_enclosing_volume_finish(result)
            except GLib.Error as error:
                if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED): errors.append(True)
            loop.quit()
        file.mount_enclosing_volume(Gio.MountMountFlags.NONE, mount, None, done)
        loop.run()
        return not errors
    try:
        enumerator = file.enumerate_children('standard::name,standard::display-name,standard::type,standard::target-uri', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
    except GLib.Error:
        if not connect(): return {'error': 'auth_required' if uri != 'smb:///' else 'unreachable'}
        try:
            enumerator = file.enumerate_children('standard::name,standard::display-name,standard::type,standard::target-uri', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
        except GLib.Error: return {'error': 'unreachable'}
    rows = []
    try:
        for _ in range(300):
            item = enumerator.next_file(None)
            if item is None: break
            if item.get_file_type() not in (Gio.FileType.DIRECTORY, Gio.FileType.MOUNTABLE, Gio.FileType.SHORTCUT): continue
            child = item.get_attribute_string('standard::target-uri') or file.get_child(item.get_name()).get_uri()
            try: child = address(child)
            except ValueError: continue
            rows.append({'label': item.get_display_name()[:256], 'uri': child})
    finally: enumerator.close(None)
    path = file.get_path()
    if request.get('op') == 'mount':
        path = mounted_path(file)
        if not path:
            return {'error': 'path_unavailable'}
        try: file.find_enclosing_mount(None)
        except GLib.Error: return {'error': 'path_unavailable'}
    return {'uri': uri, 'path': path or '', 'items': rows}


def call(request, job):
    import signal
    proc = subprocess.Popen([sys.executable, __file__], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    payload = json.dumps(request).encode()
    try:
        import time
        deadline = time.monotonic() + 45
        while True:
            job.check()
            if time.monotonic() >= deadline: raise ValueError('Network connection timed out')
            try:
                output, _ = proc.communicate(input=payload, timeout=.25)
                break
            except subprocess.TimeoutExpired: payload = None
        if proc.returncode or len(output) > 1024*1024: raise ValueError('Network service unavailable')
        return json.loads(output)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL); proc.communicate()


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384: raise ValueError()
        result = worker(json.loads(raw))
    except Exception:
        result = {'error': 'unavailable'}
    print(json.dumps(result))

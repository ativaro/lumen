"""In-memory server MCP configuration for the current private engine profile."""
import hashlib
import json
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
from uuid import UUID


class BindingError(ValueError):
    def __init__(self):
        super().__init__('Die private Server-Werkzeugkonfiguration ist ungültig.')


def configuration(environment):
    """Never consult lumen_connect's import-time profile or write a token export."""
    try:
        home = Path(environment.get('HOME') or '')
        root = Path(environment.get('XDG_CONFIG_HOME') or home/'.config')
        if not home.is_absolute() or not root.is_absolute():raise BindingError()
        config = json.loads(environment.get('OPENCODE_CONFIG_CONTENT') or '{}')
        if not isinstance(config, dict) or not isinstance(config.get('mcp', {}), dict):raise BindingError()
        path = root/'lumen-server/connection.json'
        pairing = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077 or info.st_size > 65536):raise BindingError()
                raw = stream.read(65537)
                if len(raw) > 65536:raise BindingError()
                pairing = json.loads(raw)
            if not isinstance(pairing, dict):raise BindingError()
            server, token, device = (pairing.get(k) for k in ('server', 'token', 'device_id'))
            if (not isinstance(server, str) or len(server) > 4096
                    or any(c.isspace() or ord(c)<32 or ord(c)==127 or c in '\\%{}' for c in server)):
                raise BindingError()
            url = urlsplit(server)
            if (url.scheme != 'https' or not url.hostname or url.geturl() != server or url.path
                    or url.query or url.fragment or url.username is not None or url.password is not None
                    or url.netloc.endswith(':') or url.port is not None and not 0 < url.port <= 65535
                    or str(UUID(device)) != device or not isinstance(token, str) or not 0 < len(token) <= 1000
                    or any(not 33 <= ord(c) <= 126 or c in '{}' for c in token)):
                raise BindingError()
        # An explicit disabled override also masks an older global MCP entry.
        entry = {'enabled':False} if pairing is None else dict(type='remote',
            url=server+'/mcp/', headers={'Authorization':'Bearer '+token}, enabled=True, oauth=False)
        stamp = hashlib.sha256(json.dumps([str(home),str(root),
            {k:pairing.get(k) for k in ('server','device_id','token','account','ca_file')}
            if pairing is not None else None], sort_keys=True).encode()).hexdigest()
        if pairing is not None:
            skills = config.setdefault('skills', {})
            if not isinstance(skills, dict): raise BindingError()
            urls = skills.setdefault('urls', [])
            if not isinstance(urls, list) or any(not isinstance(url, str) for url in urls): raise BindingError()
            shared = server + '/api/skills/'
            if shared not in urls: urls.append(shared)
        config['mcp'] = dict(config.get('mcp', {}), **{'lumen-server':entry})
        return json.dumps(config), stamp
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError):
        raise BindingError() from None

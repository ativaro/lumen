"""Native app-session boundary. No renderer, settings lookup or automatic writes."""
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit
from uuid import UUID
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.request

import lumen_connect


APPS = {'notes': ('note', 'notes'), 'projects': ('projects', 'projects'),
        'code': ('code', 'code'), 'compose': ('translate', 'translate'), 'audio': ('media', 'media'),
        'vault': ('vault', 'vault_sync'), 'inbox': ('inbox', 'inbox')}
APP_NAMES = {'notes': ('Lumen Notes', 'lumen-wissen'), 'projects': ('Lumen Projekte', 'lumen-workbench'),
             'code': ('Lumen Code', 'lumen-code'), 'audio': ('Lumen Audio Studio', 'lumen-meetings'),
             'vault': ('Lumen Vault', 'lumen-vault'), 'inbox': ('Lumen Inbox', 'lumen-inbox')}


class SessionError(ValueError):
    def __init__(self, kind='unavailable'):
        self.kind = kind
        super().__init__('Die Lumen-App-Sitzung ist nicht verfügbar.')


def origin(value):
    if not isinstance(value, str) or len(value) > 4096 or any(
            c.isspace() or ord(c) < 32 or ord(c) == 127 or c in '\\%' for c in value):
        raise SessionError('identity')
    try:
        u = urlsplit(value)
        if (u.scheme != 'https' or not u.hostname or u.geturl() != value or u.path
                or u.query or u.fragment or u.username is not None or u.password is not None
                or u.netloc.endswith(':') or u.port is not None and not 0 < u.port <= 65535):
            raise ValueError
    except ValueError:
        raise SessionError('identity') from None
    return value


@dataclass(frozen=True)
class Binding:
    origin: str
    account: str
    device: str
    app: str

    def __post_init__(self):
        origin(self.origin)
        try:
            if self.app not in APPS or any(str(UUID(x)) != x for x in (self.account, self.device)):
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            raise SessionError('identity') from None

    @property
    def url(self):
        return self.origin + '/?app=' + APPS[self.app][0] + '&presentation=desktop'

    def navigation(self, value):
        """Only this single app document; no arbitrary links or secret query fields."""
        try:
            if not isinstance(value, str) or any(ord(c)<32 or ord(c)==127 or c=='\\' for c in value):return False
            u = urlsplit(value)
            query=parse_qs(u.query, keep_blank_values=True, strict_parsing=True)
            key={'notes':'note','projects':'project','code':'entry','audio':'record'}.get(self.app)
            selected=None
            if key and key in query:
                selected=query.pop(key)
                if len(selected)!=1 or str(UUID(selected[0]))!=selected[0]:return False
            if self.app=='projects' and 'project_task' in query:
                item=query.pop('project_task')
                if not selected or len(item)!=1 or str(UUID(item[0]))!=item[0]:return False
            return (value.startswith(self.origin + '/') and origin(u.scheme+'://'+u.netloc) == self.origin
                    and u.path == '/' and u.fragment in ('', 'main-content')
                    and query == {
                        'app': [APPS[self.app][0]], 'presentation': ['desktop']})
        except (ValueError, SessionError):
            return False

    def reference_url(self, reference):
        from server_app_links import navigation
        if not isinstance(reference,dict) or reference.get('app')!=APPS[self.app][0]:raise SessionError('identity')
        try:route=navigation(reference,dict(server=self.origin,account=self.account))['route']
        except ValueError:raise SessionError('identity') from None
        value=self.origin+route+'&presentation=desktop'
        if not self.navigation(value):raise SessionError('identity')
        return value

    def resource(self, value):
        try:
            if not isinstance(value, str) or any(ord(c)<32 or ord(c)==127 or c=='\\' for c in value):return False
            u = urlsplit(value)
            return (value.startswith(self.origin + '/') and origin(u.scheme+'://'+u.netloc) == self.origin
                    and not u.username and not u.password)
        except (ValueError, SessionError):
            return False


class AppSession:
    def __init__(self, config, binding, *, now=None, clock=time.monotonic):
        if (origin(config.get('server')) != binding.origin or config.get('device_id') != binding.device
                or not isinstance(config.get('token'), str) or not config['token']
                or len(config['token']) > 200 or any(not 33 <= ord(c) <= 126 for c in config['token'])):
            raise SessionError('identity')
        self.binding = binding
        self._config = {k:config[k] for k in ('server', 'device_id', 'token', 'ca_file') if k in config}
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._clock = clock
        self._cookie = b''
        self._csrf = ''
        self._deadline = 0
        self._draft = ''
        self._write_seen = False
        self._generation = 0
        self.uncertain = False
        self.state = 'disconnected'
        self.access = 'read'

    @property
    def url(self):
        return self.binding.url

    @property
    def usable(self):
        if self._cookie and self._clock() >= self._deadline and self.state!='expired':
            self._generation += 1
            self.state = 'expired'
        return bool(self._cookie) and self.state == 'ready' and not self.uncertain

    @property
    def has_cookie(self):
        return bool(self._cookie) and self._clock() < self._deadline

    @property
    def can_renew(self):
        return bool(self._cookie) and not self.uncertain and self.state not in ('identity','revoked')

    def _ttl(self, value, maximum):
        try:
            ttl = (datetime.fromisoformat(value.replace('Z', '+00:00')) - self._now()).total_seconds()
            if not 0 < ttl <= maximum:raise ValueError
            return ttl
        except (TypeError, ValueError, AttributeError):
            raise SessionError('expired') from None

    def _http(self, path, body=None, *, max_bytes=65536):
        headers = {'Origin': self.binding.origin}
        if body is not None:headers['Content-Type'] = 'application/json'
        if self._cookie:
            headers['Cookie'] = 'lumen_session=' + self._cookie.decode('ascii')
            headers['X-Lumen-CSRF'] = self._csrf
        request = urllib.request.Request(self.binding.origin + path, headers=headers,
                                        data=json.dumps(body).encode() if body is not None else None)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=lumen_connect.tls_context(self._config)), lumen_connect.NoRedirect())
        with opener.open(request, timeout=10) as response:
            raw = response.read(max_bytes+1)
            if len(raw) > max_bytes:raise SessionError()
            return json.loads(raw), response.headers

    def request(self, path, body=None, *, max_bytes=65536):
        """Native reviewed handoffs use the same restricted app cookie and live proof."""
        if (type(max_bytes) is not int or not 1<=max_bytes<=1024**2 or not isinstance(path,str)
                or len(path)>4096 or any(c.isspace() or ord(c)<32 or ord(c)==127 or c=='\\' for c in path)):
            raise SessionError('request')
        target=urlsplit(path)
        if (target.scheme or target.netloc or target.fragment or target.geturl()!=path
                or not target.path.startswith('/api/') or '%' in target.path
                or any(part in ('','.','..') for part in target.path.split('/')[1:])):
            raise SessionError('request')
        if not self.check() or not self.usable:raise SessionError(self.state)
        generation=self._generation
        writing=body is not None
        if writing:self.observe_write()
        try:
            result,_=self._http(path,body,max_bytes=max_bytes)
        except urllib.error.HTTPError as error:
            if generation!=self._generation or not self.usable:
                error.close()
                if writing:self.uncertain=True
                raise SessionError(self.state) from None
            if error.code in (401,403):self.close('revoked')
            if 400<=error.code<500 and error.code!=408:
                if error.code not in (401,403) and not self.check():
                    error.close()
                    if writing:self.uncertain=True
                    raise SessionError(self.state) from None
                raise
            error.close()
            if writing:self.uncertain=True
            self.suspend()
            raise SessionError(self.state) from None
        except Exception:
            if writing:self.uncertain=True
            self.suspend()
            raise SessionError(self.state) from None
        if generation!=self._generation or not self.usable or not self.check():
            if writing:self.uncertain=True
            raise SessionError(self.state)
        return result

    def connect(self):
        if self.uncertain:raise SessionError('uncertain')
        self.close()
        generation = self._generation
        try:
            me = lumen_connect.request(self._config, '/bridge/me', timeout=10)
            if generation != self._generation:raise SessionError('disconnected')
            if (me.get('id') != self.binding.account or me.get('device_id') != self.binding.device
                    or APPS[self.binding.app][1] not in me.get('capabilities', [])):
                raise SessionError('identity')
            verifier = secrets.token_urlsafe(32)
            ticket = lumen_connect.request(self._config, '/bridge/apps/session-ticket',
                {'app':self.binding.app, 'challenge':hashlib.sha256(verifier.encode()).hexdigest()}, timeout=10)
            if generation != self._generation:raise SessionError('disconnected')
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket.get('ticket', '')):raise SessionError()
            self._ttl(ticket.get('expires'), 30)
            result, headers = self._http('/api/auth/desktop/exchange',
                dict(ticket=ticket['ticket'], verifier=verifier, user_id=self.binding.account,
                     device_id=self.binding.device, app=self.binding.app))
            if generation != self._generation:raise SessionError('disconnected')
            if (result.get('user_id'), result.get('device_id'), result.get('app')) != (
                    self.binding.account, self.binding.device, self.binding.app):raise SessionError('identity')
            if result.get('access') not in ('read', 'read_write'):raise SessionError()
            ttl = self._ttl(result.get('expires'), 900)
            values = headers.get_all('Set-Cookie', [])
            cookie = SimpleCookie()
            if len(values) != 1:raise SessionError()
            cookie.load(values[0])
            if set(cookie) != {'lumen_session'}:raise SessionError()
            c = cookie['lumen_session']
            if (not re.fullmatch(r'(?:[A-Za-z0-9_-]{43}|[A-Za-z0-9_-]{64})', c.value) or not c['secure'] or not c['httponly']
                    or c['samesite'].lower() != 'strict' or c['domain'] or c['path'] != '/'
                    or not c['max-age'].isdigit() or not 0 < int(c['max-age']) <= 900):raise SessionError()
            csrf = result.get('csrf')
            if not isinstance(csrf, str) or not csrf or len(csrf) > 256:raise SessionError()
            self._cookie = c.value.encode('ascii'); self._csrf = csrf
            self._deadline = self._clock() + min(ttl, int(c['max-age']))
            self.access = result['access']
            if not self.check():raise SessionError(self.state)
        except SessionError as e:
            self.close(e.kind); raise
        except Exception:
            self.close('unavailable'); raise SessionError() from None

    def check(self):
        if not self._cookie:
            self.close('expired'); return False
        try:
            generation = self._generation
            if self.can_renew and self._deadline-self._clock()<=60:
                renewal = lumen_connect.request(self._config, '/bridge/apps/session-renew',
                    dict(app=self.binding.app, session_hash=hashlib.sha256(self._cookie).hexdigest()), timeout=10)
                if generation!=self._generation:return False
                if (renewal.get('user_id'),renewal.get('device_id'),renewal.get('app')) != (
                        self.binding.account,self.binding.device,self.binding.app):raise SessionError('identity')
                self._deadline=self._clock()+self._ttl(renewal.get('expires'),900)
            if self._clock()>=self._deadline:return False
            value, _ = self._http('/api/me')
            if generation != self._generation:return False
            user = value.get('user', {})
            if (user.get('id') != self.binding.account or user.get('device_id') != self.binding.device
                    or user.get('desktop_app') != self.binding.app or user.get('device_kind') != 'desktop'
                    or user.get('admin') is not False or user.get('capabilities') != [APPS[self.binding.app][1]]
                    or user.get('csrf') != self._csrf):
                self.close('identity'); return False
            self.state = 'uncertain' if self.uncertain else 'ready'
            return self.usable
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 410):self.close('revoked')
            else:self.suspend('offline')
            e.close()
        except SessionError as e:
            self.close(e.kind)
        except Exception:
            self.suspend('offline')
        return False

    def web_cookie(self):
        if not self.usable:raise SessionError(self.state)
        return b'lumen_session=' + self._cookie + b'; Path=/; Secure; HttpOnly; SameSite=Strict'

    def observe_write(self):
        self._write_seen = True
        if self.state != 'ready':self.uncertain = True;self.state = 'uncertain'

    def suspend(self, reason='offline'):
        self._generation += 1
        self.uncertain = self.uncertain or self._write_seen
        self.state = reason if reason == 'identity' else 'uncertain' if self.uncertain else reason

    def remember_draft(self, text):
        if not isinstance(text, str) or len(text.encode('utf-8')) > 1024*1024:raise SessionError('draft')
        self._draft = text

    def draft(self, binding):
        if binding != self.binding:raise SessionError('identity')
        return self._draft

    def close(self, state='disconnected'):
        self._generation += 1
        self._cookie = b''; self._csrf = ''; self._deadline = 0
        self.state = state

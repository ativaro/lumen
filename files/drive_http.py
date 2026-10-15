"""One verified, identity-scoped HTTPS connection for a transfer worker."""

from contextlib import contextmanager
from http.client import HTTPSConnection
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlsplit
import lumen_connect


class Session:
    def __init__(self, config):
        self.config = dict(config)
        self.origin = urlsplit(config['server'])
        if (self.origin.scheme != 'https' or not self.origin.hostname
                or self.origin.username or self.origin.password
                or self.origin.path not in ('', '/') or self.origin.query or self.origin.fragment):
            raise ValueError('Invalid Drive server origin')
        self.context = None
        self.connection = None

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @contextmanager
    def open(self, request, timeout=90):
        target = urlsplit(request.full_url)
        if (target.scheme != self.origin.scheme or target.netloc != self.origin.netloc
                or target.fragment or not target.path.startswith('/bridge/drive/')
                or request.get_header('Authorization') != 'Bearer ' + self.config['token']):
            raise ValueError('Drive request does not match transfer identity')
        response = None
        try:
            if self.context is None:
                self.context = lumen_connect.tls_context(self.config)
            if self.connection is None:
                self.connection = HTTPSConnection(self.origin.hostname, self.origin.port,
                                                  context=self.context, timeout=timeout)
            self.connection.timeout = timeout
            if self.connection.sock is not None:
                self.connection.sock.settimeout(timeout)
            path = target.path + ('?' + target.query if target.query else '')
            self.connection.request(request.get_method(), path, body=request.data,
                                    headers=dict(request.header_items()))
            response = self.connection.getresponse()
            if response.status >= 300:
                raise HTTPError(request.full_url, response.status, response.reason,
                                response.headers, BytesIO(response.read(1024 * 1024 + 1)))
            yield response
        except BaseException:
            # A lost response may follow a committed write; resume explicitly, never replay here.
            self.close()
            raise
        finally:
            if response is not None:
                if not response.isclosed():
                    self.close()
                response.close()

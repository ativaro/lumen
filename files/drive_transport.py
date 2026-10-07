"""Bounded binary transfers using the existing paired HTTPS identity."""

import hashlib
import json
import mimetypes
import os
import urllib.request
from uuid import uuid4, UUID
import lumen_connect
import drive_local as local
from lumen_i18n import tr


def opener(config):
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=lumen_connect.tls_context(config)),
        lumen_connect.NoRedirect(),
    )


def upload(
    config,
    root,
    path,
    workspace,
    folder,
    request_id,
    expected_hash,
    previous=None,
    progress=lambda *_: None,
    filename=None,
):
    boundary = "lumen-" + uuid4().hex
    fields = dict(workspace=workspace, request_id=request_id, sha256=expected_hash)
    if folder:
        fields["folder"] = str(UUID(folder))
    if previous:
        fields.update(replaces=previous["id"], revision=previous["revision"])
    head = b"".join(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
        for key, value in fields.items()
    )
    name = local.relative(filename or path).name.replace(chr(34), chr(92) + chr(34))
    head += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: {mimetypes.guess_type(name)[0] or "application/octet-stream"}\r\n\r\n'
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    with local.source(root, path) as stream:
        size = os.fstat(stream.fileno()).st_size

        def chunks():
            yield head
            count = 0
            while count < size:
                chunk = stream.read(min(128 * 1024, size - count))
                if not chunk:
                    raise ValueError(tr("Datei während Übertragung verändert."))
                count += len(chunk)
                progress(count, size)
                yield chunk
            yield tail

        request = urllib.request.Request(
            config["server"] + "/bridge/drive/upload",
            data=chunks(),
            headers={
                "Authorization": "Bearer " + config["token"],
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                "Content-Length": str(len(head) + size + len(tail)),
            },
            method="POST",
        )
        with opener(config).open(request, timeout=60) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError(tr("Serverantwort zu groß."))
        return json.loads(raw)


def download(config, root, row, progress=lambda *_: None):
    if not 0 <= row["size"] <= local.LIMIT:
        raise ValueError(tr("Maximal 64 MB pro Datei."))
    local.capacity(root, row["size"])
    local.mkdir(root, ".lumen-drive")
    staged = ".lumen-drive/stage-" + uuid4().hex
    request = urllib.request.Request(
        config["server"] + "/bridge/drive/files/" + str(UUID(row["id"])) + "/content",
        headers={"Authorization": "Bearer " + config["token"]},
    )
    with local.directory(root, ".lumen-drive") as parent:
        fd = os.open(
            staged.split("/")[-1], os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=parent
        )
        try:
            with os.fdopen(fd, "wb") as stream, opener(config).open(request, timeout=60) as response:
                digest = hashlib.sha256()
                count = 0
                while chunk := response.read(128 * 1024):
                    count += len(chunk)
                    if count > row["size"]:
                        raise ValueError(tr("Dateigröße stimmt nicht."))
                    stream.write(chunk)
                    digest.update(chunk)
                    progress(count, row["size"])
                if count != row["size"] or digest.hexdigest() != row["sha256"]:
                    raise ValueError(tr("Dateiprüfung fehlgeschlagen."))
                stream.flush()
                os.fsync(stream.fileno())
            return staged
        except BaseException:
            os.unlink(staged.split("/")[-1], dir_fd=parent)
            raise

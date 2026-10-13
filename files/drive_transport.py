"""Bounded binary transfers using the existing paired HTTPS identity."""

import fcntl
import stat
import hashlib
import json
import mimetypes
import os
import urllib.request
from urllib.error import HTTPError
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


def legacy_upload(
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


def request(config, path, body=None, method="POST", content_type="application/json"):
    data = json.dumps(body).encode() if content_type == "application/json" and body is not None else body
    req = urllib.request.Request(config["server"] + "/bridge/drive" + path, data=data,
        headers={"Authorization": "Bearer " + config["token"], "Content-Type": content_type}, method=method)
    with opener(config).open(req, timeout=90) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError(tr("Serverantwort zu groß."))
    return json.loads(raw)


def upload(config, root, path, workspace, folder, request_id, expected_hash,
           previous=None, progress=lambda *_: None, filename=None):
    name = local.relative(filename or path).name
    with local.source(root, path) as stream:
        before = local.signature(os.fstat(stream.fileno()))
        size = before[2]
        body = dict(workspace=str(UUID(workspace)), name=name, size=size, sha256=expected_hash,
                    folder=folder, replaces=previous["id"] if previous else None,
                    revision=previous["revision"] if previous else None,
                    mime=mimetypes.guess_type(name)[0] or "application/octet-stream")
        progress(0, size)
        try:
            state = request(config, "/uploads/" + str(UUID(request_id)), body)
        except HTTPError as error:
            if error.code not in (404, 405): raise
            return legacy_upload(config, root, path, workspace, folder, request_id, expected_hash,
                                 previous, progress, filename)
        key = str(UUID(state["id"]))
        offset = state["offset"]
        if not 0 <= offset <= size or state["size"] != size:
            raise ValueError(tr("Ungültiger Übertragungsstand."))
        stream.seek(offset)
        progress(offset, size)
        while offset < size:
            chunk = stream.read(min(4 * 1024**2, size - offset))
            if not chunk or local.signature(os.fstat(stream.fileno())) != before:
                raise ValueError(tr("Datei während Übertragung verändert."))
            state = request(config, f"/uploads/{key}?offset={offset}", chunk, "PUT", "application/octet-stream")
            if state["offset"] != offset + len(chunk):
                raise ValueError(tr("Ungültiger Übertragungsstand."))
            offset += len(chunk)
            progress(offset, size)
        return request(config, f"/uploads/{key}/finish")


def download(config, root, row, progress=lambda *_: None):
    if not 0 <= row["size"] <= local.LIMIT:
        raise ValueError(tr("Ungültige Dateigröße."))
    local.mkdir(root, ".lumen-drive")
    staged = ".lumen-drive/stage-" + str(UUID(row["id"]))
    with local.directory(root, ".lumen-drive") as parent:
        fd = os.open(staged.split("/")[-1], os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        with os.fdopen(fd, "r+b") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError(tr("Ungültige Teildatei."))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            count = os.fstat(stream.fileno()).st_size
            if count > row["size"]:
                raise ValueError(tr("Teildatei hat eine unerwartete Größe."))
            local.capacity(root, row["size"] - count)
            digest = hashlib.sha256()
            while chunk := stream.read(1024**2):
                digest.update(chunk)
                progress(stream.tell(), row["size"])
            if count < row["size"] or not count:
                headers = {"Authorization": "Bearer " + config["token"], "Accept-Encoding": "identity"}
                if count: headers.update(Range=f"bytes={count}-", **{"If-Range": '"' + row["sha256"] + '"'})
                req = urllib.request.Request(config["server"] + "/bridge/drive/files/" + str(UUID(row["id"])) + "/content", headers=headers)
                with opener(config).open(req, timeout=60) as response:
                    status = getattr(response, "status", 200)
                    if count and status == 206:
                        if response.headers.get("Content-Range") != f"bytes {count}-{row['size'] - 1}/{row['size']}" or response.headers.get("ETag") != '"' + row["sha256"] + '"':
                            raise ValueError(tr("Server bestätigt die Fortsetzung nicht."))
                    elif status == 200:
                        stream.seek(0); stream.truncate(); count = 0; digest = hashlib.sha256()
                    else:
                        raise ValueError(tr("Unerwartete Antwort des Downloadservers."))
                    try:
                        while chunk := response.read(128 * 1024):
                            count += len(chunk)
                            if count > row["size"]: raise ValueError(tr("Dateigröße stimmt nicht."))
                            stream.write(chunk); digest.update(chunk)
                            progress(count, row["size"])
                    finally:
                        stream.flush(); os.fsync(stream.fileno()); os.fsync(parent)
            if count != row["size"]:
                raise ValueError(tr("Download unvollständig; Fortsetzen ist möglich."))
            if digest.hexdigest() != row["sha256"]:
                os.unlink(staged.split("/")[-1], dir_fd=parent)
                raise ValueError(tr("Dateiprüfung fehlgeschlagen. Bitte erneut versuchen."))
            return staged

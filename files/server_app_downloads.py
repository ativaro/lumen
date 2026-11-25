"""Reviewed exports from the private server page; no automatic filesystem writes."""
import os
import re
from pathlib import Path
import shutil
from uuid import uuid4

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
from server_audio_permissions import context, current, fresh
from lumen_i18n import tr

LIMIT = 64 * 1024**2


def download(window, request):
    proof = context(window)
    url = request.url().toString()
    origin = window._binding.origin
    if (window._binding.app=='code' and request.page() is window.page and current(window,proof)
            and re.fullmatch(re.escape(origin)+r'/api/code-library/[0-9a-fA-F-]{36}/runtime/(?:export|file\?path=.+|patch\?tree=[a-f0-9]{40,64}&head=[a-f0-9]{40,64}|jobs/[a-f0-9]{32}/log)',url)):
        def check():
            if not fresh(window,proof): raise ValueError('App-Sitzung geändert.')
        return save_download(window, request, check)
    if (window._binding.app not in ('vault', 'inbox', 'photos') or request.page() is not window.page
            or not current(window, proof)
            or not (window._binding.resource(url) or url.startswith('blob:' + origin + '/'))
            or window._binding.app=='vault' and request.totalBytes() > LIMIT):
        request.cancel(); return
    suggested = Path(request.suggestedFileName().replace('\\', '/')).name
    destination, _ = QFileDialog.getSaveFileName(window, tr('Lumen · Datei speichern'), suggested)
    if not destination or not fresh(window, proof):
        request.cancel(); return
    target = Path(destination)
    if not target.is_absolute() or target.exists() or target.is_symlink():
        request.cancel()
        QMessageBox.warning(window, window._app_title, tr('Bitte einen neuen Dateinamen wählen. Bestehende Dateien werden nicht überschrieben.'))
        return
    temporary = Path(window._temporary.name) / ('export-' + uuid4().hex)
    bounded=window._binding.app=='vault'
    def has_space():
        try:
            expected=max(request.totalBytes(),request.receivedBytes(),0)
            return (shutil.disk_usage(temporary.parent).free>128*1024**2 and
                    shutil.disk_usage(target.parent).free>expected+128*1024**2)
        except OSError:
            return False
    if not has_space():
        request.cancel()
        QMessageBox.warning(window,window._app_title,tr('Für diese Datei reicht der freie Speicher nicht aus. Bitte einen anderen Speicherort wählen.'))
        return
    request.setDownloadDirectory(str(temporary.parent))
    request.setDownloadFileName(temporary.name)

    def finish():
        state = request.state()
        if state not in (QWebEngineDownloadRequest.DownloadCompleted,
                         QWebEngineDownloadRequest.DownloadCancelled,
                         QWebEngineDownloadRequest.DownloadInterrupted): return
        def publish():
            created = False
            try:
                if state != QWebEngineDownloadRequest.DownloadCompleted or not fresh(window, proof): return
                if temporary.is_symlink() or not temporary.is_file() or bounded and temporary.stat().st_size > LIMIT:
                    raise ValueError
                # Exclusive creation prevents overwriting a file added during the download.
                if not has_space():raise OSError('Storage reserve reached')
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                created = True
                with os.fdopen(fd, 'wb') as output, temporary.open('rb') as source:
                    shutil.copyfileobj(source, output)
            except (OSError, ValueError, RuntimeError):
                if created: target.unlink(missing_ok=True)
                QMessageBox.warning(window, window._app_title, tr('Die Datei konnte nicht gespeichert werden. Die Serverdaten bleiben erhalten.'))
            finally:
                temporary.unlink(missing_ok=True)
        QTimer.singleShot(0, publish)
    def progress():
        try:
            if (bounded and request.receivedBytes()>LIMIT) or not has_space():request.cancel()
        except OSError:request.cancel()
    request.receivedBytesChanged.connect(progress)
    request.stateChanged.connect(finish)
    request.accept()


def save_download(parent, request, check):
    """Use the native reviewed save target; Code files have no product size ceiling."""
    try:
        check()
        suggested = Path(request.suggestedFileName().replace('\\','/')).name
        destination, _ = QFileDialog.getSaveFileName(parent, tr('Datei speichern'), suggested)
        check()
        if not destination: request.cancel(); return
        target = Path(destination)
        if not target.is_absolute(): request.cancel(); return
        request.setDownloadDirectory(str(target.parent)); request.setDownloadFileName(target.name)
        request.accept()
    except Exception:
        request.cancel()

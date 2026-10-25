"""Explicit native inputs for Audio Studio and Vault."""
from pathlib import Path
import os
import stat

from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEnginePermission
from interop_dialogs import run_job
from lumen_i18n import tr
from lumen_qt import is_deleted


def context(window):
    return (window.page,window.profile,window.session,window._generation,window.session._generation)


def current(window, proof):
    page,profile,session,generation,session_generation=proof
    return bool(not is_deleted(window) and not window._disposed and not window._closing
        and window._live and window._loaded and window._binding.app in ('audio','code','vault','inbox')
        and page is window.page and profile is window.profile and profile is window._bound_profile
        and session is window.session and session.binding==window._binding
        and generation==window._generation and session_generation==session._generation
        and not is_deleted(page) and not is_deleted(profile) and window.view.page() is page and page.profile() is profile
        and session.usable and window._cookie_valid() and window._pilot_current())


def fresh(window, proof):
    if not current(window,proof):return False
    def check(job):
        job.check()
        okay=proof[2].check()
        job.check()
        return okay
    return run_job(window,window._app_title+' · '+tr('Gerätefreigabe wird geprüft …'),check) is True and current(window,proof)


def choose(window, mode):
    if window._binding.app not in ('audio','vault'):return []
    audio=window._binding.app=='audio'
    if mode!=QWebEnginePage.FileSelectionMode.FileSelectOpen:return []
    proof=context(window)
    if not current(window,proof):return []
    if audio:
        path,_=QFileDialog.getOpenFileName(window,tr('Aufnahme für Lumen Audio Studio auswählen'),'',tr('Audio (*.wav *.mp3 *.ogg *.m4a *.flac *.webm)'))
    else:
        path,_=QFileDialog.getOpenFileName(window,tr('Lumen Vault · Schlüsseldatei auswählen'),'')
    if not path or not fresh(window,proof):return []
    try:
        value=Path(path);info=value.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size>(64*1024**2 if audio else 1024**2):raise ValueError
        if audio and (not info.st_size or value.suffix.lower() not in ('.wav','.mp3','.ogg','.m4a','.flac','.webm')):raise ValueError
        return [path] if current(window,proof) else []
    except (OSError,ValueError):
        QMessageBox.warning(window,window._app_title,tr('Die Auswahl ist nicht geeignet. Bitte unterstützte Dateien innerhalb der Größenbegrenzung auswählen.'))
        return []


def permission(window, request):
    proof=context(window)
    if (window._binding.app!='audio' or not request.isValid() or request.permissionType()!=QWebEnginePermission.PermissionType.MediaAudioCapture
            or request.origin().toString().rstrip('/')!=window._binding.origin or not current(window,proof)):
        request.deny();return
    accepted=QMessageBox.question(window,tr('Lumen Audio Studio'),
        tr('Mikrofon für diese Aufnahme verwenden? Die Aufnahme wird erst durch „Speichern“ hochgeladen.'),
        QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
    if accepted==QMessageBox.StandardButton.Yes and request.isValid() and fresh(window,proof):
        from topbar_context import install_audio
        install_audio(window)
        request.grant()
    else:request.deny()

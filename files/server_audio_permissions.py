"""Explicit native inputs for the current private Code or Audio Studio session."""
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
    if window._binding.app not in ('audio','code','vault'):return []
    audio=window._binding.app=='audio'
    vault=window._binding.app=='vault'
    modes=(QWebEnginePage.FileSelectionMode.FileSelectOpen,) if audio or vault else (
        QWebEnginePage.FileSelectionMode.FileSelectOpen,QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple)
    if mode not in modes:return []
    proof=context(window)
    if not current(window,proof):return []
    if audio:
        path,_=QFileDialog.getOpenFileName(window,tr('Aufnahme für Lumen Audio Studio auswählen'),'',tr('Audio (*.wav *.mp3 *.ogg *.m4a *.flac *.webm)'))
        paths=[path] if path else []
    elif vault:
        path,_=QFileDialog.getOpenFileName(window,tr('Lumen Vault · Schlüsseldatei auswählen'),'')
        paths=[path] if path else []
    else:
        paths,_=QFileDialog.getOpenFileNames(window,tr('Textdateien für Lumen Code auswählen'),'')
    if not paths or not fresh(window,proof):return []
    try:
        if len(paths)>(1 if audio or vault else 256):raise ValueError
        names=set();total=0
        for name in paths:
            value=Path(name);info=value.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size>(1024**2 if vault else 64*1024**2 if audio else 512*1024):raise ValueError
            if audio:
                if not info.st_size or value.suffix.lower() not in ('.wav','.mp3','.ogg','.m4a','.flac','.webm'):raise ValueError
            elif not vault:
                if (value.name in names or value.name in ('.git','.ssh','.aws','.gitmodules','.gitattributes')
                        or value.name.startswith('.env') or value.name.endswith(('.pem','.key'))):raise ValueError
                names.add(value.name)
                with os.fdopen(os.open(value,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
                    opened=os.fstat(stream.fileno())
                    if (not stat.S_ISREG(opened.st_mode) or opened.st_size>512*1024
                            or (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino)):raise ValueError
                    total+=opened.st_size
                    if total>8*1024**2:raise ValueError
                    raw=stream.read(512*1024+1)
                    after=os.fstat(stream.fileno())
                    if (len(raw)!=opened.st_size or (after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                            !=(opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)):raise ValueError
                text=raw.decode('utf-8')
                if '\0' in text:raise ValueError
        return paths if current(window,proof) else []
    except (OSError,ValueError,UnicodeError):
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
    if accepted==QMessageBox.StandardButton.Yes and request.isValid() and fresh(window,proof):request.grant()
    else:request.deny()

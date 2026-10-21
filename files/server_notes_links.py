"""Explicit native file-link confirmation for the bound Server Notes window."""
from dataclasses import dataclass
from pathlib import Path
import threading
import re
from urllib.parse import parse_qs,urlsplit
from uuid import UUID

from PySide6.QtCore import QObject,Qt
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QMessageBox,QVBoxLayout
from interop_data import Registry,validate_ref
from interop_dialogs import run_job
from interop_open import open_url
from desktop_design import AppHeader,MENU_STYLE,PAGE_MARGIN,PAGE_SPACING
from lumen_i18n import tr
from lumen_qt import is_deleted
import drive_references as drive
import lumen_connect
from server_app_session import SessionError


@dataclass(frozen=True)
class Context:
    window:object
    page:object
    profile:object
    view:object
    session:object
    binding:object
    generation:int
    session_generation:int
    connection:tuple
    destroyed:object
    thread:int

    def check(self):
        from server_app_window import _connection
        w=self.window;config,stamp=_connection()
        private={key:config[key] for key in ('server','device_id','token','ca_file') if key in config}
        if (private!=self.session._config or stamp!=self.connection or self.destroyed.is_set() or w._disposed or w._closing or w._import_close
                or not w._live or not w._loaded or w._generation!=self.generation
                or w.session is not self.session or self.session.binding!=self.binding
                or self.session._generation!=self.session_generation or not self.session.usable
                or w.page is not self.page or w.profile is not self.profile or w.view is not self.view):raise SessionError('identity')

    def gui(self):
        if threading.get_ident()!=self.thread:raise SessionError('thread')
        self.check()
        if (any(is_deleted(value) for value in (self.window,self.page,self.profile,self.view))
                or self.view.page() is not self.page or not self.window._cookie_valid()):raise SessionError('identity')


def _profile(context,job,revision=None,needs_drive=False):
    from server_app_window import _connection
    job.check();context.check()
    if context.binding.app!='notes':raise SessionError('identity')
    if not context.session.check():raise SessionError(context.session.state)
    config,_=_connection();me=lumen_connect.request(config,'/bridge/me',timeout=10)
    job.check();context.check()
    if not isinstance(me,dict):raise SessionError('identity')
    current=me.get('permissions_revision')
    if (me.get('id')!=context.binding.account or me.get('device_id')!=context.binding.device
            or type(current) is not int or current<0 or revision is not None and current!=revision
            or not isinstance(me.get('capabilities'),list) or 'notes' not in me['capabilities']
            or needs_drive and 'drive' not in me['capabilities']):raise SessionError('identity')
    return config,current


def _drive_row(ref,row):
    if (row.get('trashed') is not False or row.get('current') is not True
            or row.get('family')!=ref['id']
            or any(type(row.get(key)) is not int or row[key]<1 for key in ('version','revision'))):
        raise ValueError(tr('Die verknüpfte Drive-Datei ist nicht mehr aktuell verfügbar.'))
    if (type(row.get('size')) is not int or row['size']<0 or not isinstance(row.get('name'),str)
            or not row['name'] or len(row['name'])>4096 or not isinstance(row.get('sha256'),str)
            or not re.fullmatch(r'[a-f0-9]{64}',row['sha256'])
            or str(UUID(row.get('id','')))!=row['id']
            or row.get('folder_id') is not None and str(UUID(row['folder_id']))!=row['folder_id']):
        raise ValueError(tr('Ungültiger Drive-Dateibeleg.'))
    return {key:row[key] for key in drive.COPY_RECEIPT_FIELDS}


def _resolve(context,url,job,revision=None):
    """Return only a known local file or an authorized current Drive reference."""
    config,revision=_profile(context,job,revision)
    if not isinstance(url,str) or len(url)>8192 or any(ord(c)<32 or c=='\\' for c in url):
        raise ValueError(tr('Ungültige Dateiverknüpfung.'))
    parts=urlsplit(url);registry=Registry();row=None
    if parts.scheme=='lumen' and parts.netloc=='object':
        ref=validate_ref(registry.resolve(url))
    else:
        query=parse_qs(parts.query,keep_blank_values=True,strict_parsing=True)
        if (parts.scheme!='https' or parts.netloc!=urlsplit(context.binding.origin).netloc
                or parts.path!='/' or parts.fragment or set(query)!={'app','file'}
                or query['app']!=['files'] or len(query['file'])!=1
                or str(UUID(query['file'][0]))!=query['file'][0]):
            raise ValueError(tr('Nur registrierte Dateien dieses Servers können in Lumen Files geöffnet werden.'))
        _profile(context,job,revision,needs_drive=True)
        cache=drive.sync.inventory(config,job=job)
        matches=[value for value in cache['files'].values() if value.get('id')==query['file'][0]]
        if len(matches)!=1:raise ValueError(tr('Die verknüpfte Drive-Fassung ist nicht mehr verfügbar.'))
        row=matches[0]
        ref=drive.validate(dict(app='files',kind='drive_file',id=row['family'],title=row['name'],
            locator=dict(server=context.binding.origin,account=context.binding.account)))
    if ref['app']!='files' or ref.get('version') is not None:
        raise ValueError(tr('Diese Verknüpfung gehört nicht zu Lumen Files.'))
    if ref['kind'] in ('drive_file','drive_folder'):
        if ref['locator']!=dict(server=context.binding.origin,account=context.binding.account):raise SessionError('identity')
        _profile(context,job,revision,needs_drive=True)
        config,rows=drive.resolve([ref],job);current=rows[0]
        if row is not None and _drive_row(ref,row)!=_drive_row(ref,current):raise SessionError('identity')
        if ref['kind']=='drive_file':pin=_drive_row(ref,current)
        else:
            if current.get('id')!=ref['id'] or current.get('trashed') is not False or type(current.get('revision')) is not int:
                raise ValueError(tr('Der verknüpfte Drive-Ordner ist nicht verfügbar.'))
            pin={key:current[key] for key in ('id','revision','name','parent_id')}
        ref=dict(ref,title=current['name']);location=tr('Lumen Drive · {0}',context.binding.origin)
    elif ref['kind'] in ('file','folder'):
        path=ref.get('path');value=Path(path) if isinstance(path,str) else None
        if value is None or not value.is_absolute() or ref['id']!=path or not value.exists():
            raise ValueError(tr('Die registrierte Originaldatei ist nicht mehr verfügbar.'))
        info=value.stat();pin=dict(path=path,device=info.st_dev,inode=info.st_ino)
        location=path
    else:raise ValueError(tr('Diese Verknüpfung gehört nicht zu einer Datei.'))
    _profile(context,job,revision,needs_drive=ref['kind'].startswith('drive_'))
    return dict(reference=ref,revision=revision,pin=pin,location=location)


def resolve(context,url,job,revision=None):
    try:return _resolve(context,url,job,revision)
    except (KeyError,TypeError,AttributeError):
        raise ValueError(tr('Die Dateiverknüpfung konnte nicht eindeutig bestätigt werden.')) from None


def sources(context,note_id,job):
    """Only current readable Notes and their already committed native handoffs."""
    if not isinstance(note_id,str) or str(UUID(note_id))!=note_id:raise ValueError(tr('Zuerst eine Notiz öffnen.'))
    _,revision=_profile(context,job)
    note=context.session.request('/api/documents/'+note_id,max_bytes=1024**2)
    if (not isinstance(note,dict) or note.get('id')!=note_id or note.get('kind')!='note'
            or note.get('deleted') is not False or not isinstance(note.get('title'),str)):
        raise ValueError(tr('Die aktuelle Notiz ist nicht mehr verfügbar.'))
    registry=Registry();ref=validate_ref(dict(version=2,app='note',id=note_id,title=note['title'],
        locator=dict(server=context.binding.origin,account=context.binding.account)))
    url=registry.register(ref)
    with registry.library.connect() as db:
        rows=db.execute("SELECT id FROM handoffs WHERE target='wissen' AND state='done' AND result=? LIMIT 41",(url,)).fetchall()
    if len(rows)>40:raise ValueError(tr('Zu viele Dateiverweise für diese Ansicht.'))
    found={}
    def add(value):
        value=validate_ref(value)
        if value.get('app')!='files' or value.get('kind') not in ('file','folder','drive_file','drive_folder'):return
        if value['kind'].startswith('drive_') and value['locator']!=ref['locator']:return
        target=registry.register(value);found[target]=value
    for row in rows:
        job.check();request=registry.request(row['id'])
        if request['action']!='wissen.import':continue
        payload=request['payload']
        if payload.get('source'):add(payload['source'])
        for value in payload.get('references',[]):add(value)
        for path in payload.get('paths',[]):add(dict(app='files',kind='file',id=path,path=path,title=Path(path).name or path))
        if len(found)>40:raise ValueError(tr('Zu viele Dateiverweise. Bitte die Datei direkt in Lumen Files öffnen.'))
    _profile(context,job,revision)
    return note['title'],[dict(url=url,reference=ref) for url,ref in found.items()]


class Links(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.pending=False

    def menu(self,point):
        w=self.window
        if w._disposed or w._closing or self.pending:return
        menu=w.view.createStandardContextMenu();menu.setStyleSheet(MENU_STYLE)
        menu.addSeparator();action=menu.addAction(tr('Dateiverweise in Lumen Files …'))
        action.setObjectName('lumen-notes-file-references')
        action.setEnabled(w._live and w._loaded and w.session.usable and not w._import_running)
        chosen=menu.exec(w.view.mapToGlobal(w.view.rect().center() if point.x()<0 else point))
        if not is_deleted(menu):menu.deleteLater()
        if chosen is action and not is_deleted(w) and not w._disposed and not w._closing:self.current_sources()

    def current_sources(self):
        w=self.window
        if self.pending or w._import_running or w._worker is not None:return
        from server_app_window import _connection
        try:
            context=Context(w,w.page,w.profile,w.view,w.session,w._binding,w._generation,w.session._generation,
                _connection()[1],w._import_destroyed,threading.get_ident());context.gui()
        except (ValueError,OSError,RuntimeError):return
        self.pending=True
        def received(note_id):
            owned=False
            try:
                context.gui()
                if w._import_running or w._worker is not None:return
                w._import_running=True;owned=True
                result=run_job(w,tr('Lumen Notes · Dateiverweise laden …'),lambda job:sources(context,note_id,job))
                if result is None:return
                context.gui();title,rows=result
                if not rows:
                    QMessageBox.information(w,'Lumen Notes',tr('Für diese Notiz sind auf diesem Gerät keine bestätigten Dateiverweise vorhanden.'));return
                dialog=QDialog(w);dialog.setWindowTitle(tr('Lumen Notes · Dateiverweise'));dialog.resize(620,400)
                layout=QVBoxLayout(dialog);layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
                heading=AppHeader(tr('Dateiverweise'),title);heading.subtitle.setTextFormat(Qt.PlainText);layout.addWidget(heading)
                listing=QListWidget();listing.setAccessibleName(tr('Dateiverweise dieser Notiz'));listing.setWordWrap(True)
                listing.setStyleSheet('QListWidget::item { padding:10px 12px; }');listing.setSpacing(4)
                for row in rows:
                    ref=row['reference'];where=tr('Lumen Drive') if ref['kind'].startswith('drive_') else ref.get('path',ref['id'])
                    item=QListWidgetItem(ref['title']+'\n'+where);item.setData(Qt.UserRole,row['url']);listing.addItem(item)
                listing.setCurrentRow(0);layout.addWidget(listing)
                buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Cancel).setDefault(True)
                buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);listing.itemActivated.connect(lambda *_:dialog.accept());layout.addWidget(buttons)
                if dialog.exec()!=QDialog.Accepted:return
                context.gui();item=listing.currentItem()
                if item is not None:
                    w._import_running=False;owned=False;self.open(context,item.data(Qt.UserRole))
            except (ValueError,OSError,RuntimeError) as error:
                if not is_deleted(w) and not w._disposed and not w._closing and not w._import_close:QMessageBox.warning(w,'Lumen Notes',str(error))
            finally:
                self.pending=False
                if owned and not is_deleted(w):
                    w._import_running=False
                    if w._import_close:w._import_close=False;w.close()
        w.page.runJavaScript("document.querySelector('.knowledge-editor')?.dataset.documentId ?? ''",0,received)

    def open(self,context,url):
        w=self.window;owned=False
        try:
            context.gui()
            if w._import_running or w._worker is not None:return
            w._import_running=True;owned=True
            target=run_job(w,tr('Lumen Files · Verknüpfung prüfen …'),lambda job:resolve(context,url,job))
            if target is None:return
            context.gui()
            dialog=QMessageBox(w);dialog.setWindowTitle(tr('Lumen Files · Verknüpfung öffnen'))
            dialog.setTextFormat(Qt.PlainText);dialog.setText(tr('In Lumen Files öffnen?\n\n{0}\n{1}',target['reference']['title'],target['location']))
            dialog.setStandardButtons(QMessageBox.Yes|QMessageBox.Cancel);dialog.setDefaultButton(QMessageBox.Cancel)
            dialog.button(QMessageBox.Yes).setText(tr('In Lumen Files öffnen'))
            if dialog.exec()!=QMessageBox.Yes:return
            context.gui()
            fresh=run_job(w,tr('Lumen Files · Freigabe erneut prüfen …'),lambda job:resolve(context,url,job,target['revision']))
            if fresh is None:return
            context.gui()
            if fresh!=target:raise ValueError(tr('Die Dateiverknüpfung wurde während der Bestätigung geändert. Bitte erneut öffnen.'))
            registry=Registry();registered=registry.register(fresh['reference']);context.gui()
            open_url(registered)
        except (ValueError,OSError,RuntimeError) as error:
            if not is_deleted(w) and not w._disposed and not w._closing and not w._import_close:
                QMessageBox.warning(w,'Lumen Files',str(error))
        finally:
            self.pending=False
            if owned and not is_deleted(w):
                w._import_running=False
                if w._import_close:w._import_close=False;w.close()


def controller(window):
    if not hasattr(window,'_notes_link_controller'):window._notes_link_controller=Links(window)
    return window._notes_link_controller


def install(window):
    value=controller(window)
    window.view.setContextMenuPolicy(Qt.CustomContextMenu)
    window.view.customContextMenuRequested.connect(value.menu)

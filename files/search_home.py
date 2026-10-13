"""Search overview using native tasks, app routes and desktop recent documents."""
import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QProcess, QUrl
from PySide6.QtGui import QDesktopServices
from lumen_i18n import tr, worker_process


def recent_documents(data=None):
    data=Path(data or os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    entries={}
    def add(url,title,updated,icon='text-x-generic'):
        value=QUrl(url)
        if not value.isLocalFile() or not value.toLocalFile().startswith('/'):return
        path=value.toLocalFile()
        entries[path]=dict(path=path,title=title or Path(path).name,detail=str(Path(path).parent),updated=updated,icon=icon)
    recent=data/'recently-used.xbel'
    try:
        if recent.stat().st_size<=2*1024**2:
            from datetime import datetime
            for bookmark in ET.parse(recent).getroot().findall('bookmark')[-200:]:
                try:stamp=datetime.fromisoformat(bookmark.get('modified','').replace('Z','+00:00')).timestamp()
                except ValueError:stamp=0
                add(bookmark.get('href',''),bookmark.findtext('title',''),stamp)
    except (OSError,ET.ParseError):pass
    try:
        paths=sorted((data/'RecentDocuments').glob('*.desktop'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]
        for path in paths:
            try:
                if path.stat().st_size>65536:continue
                config=configparser.ConfigParser(interpolation=None);config.read(path,encoding='utf-8')
                row=config['Desktop Entry'];add(row.get('URL',''),row.get('Name',''),path.stat().st_mtime,row.get('Icon','text-x-generic'))
            except (OSError,configparser.Error,KeyError,UnicodeError):continue
    except OSError:pass
    return sorted(entries.values(),key=lambda r:r['updated'],reverse=True)[:20]


def snapshot():
    from lumen_panel import snapshot as task_snapshot
    result=task_snapshot(task_limit=40)
    return dict(tasks=result['active']+result['recent'],recent=recent_documents(),error=result['error'])


class SearchHome(QObject):
    changed=Signal(); failed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self._tasks=[];self._recent=[];self._error='';self.process=None
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.refresh)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.cancel)
        from lumen_apps import catalogue
        rows={key:dict(id=key,title=title.removeprefix('Lumen '),icon='lumen-'+key) for key,title,detail,icon in catalogue()}
        self.all_apps = [value for key,value in rows.items() if key != 'lumen']; self.expanded_apps = False
        self._apps=[rows[key] for key in ('files','wissen','workbench','vault','inbox')]+[dict(id='apps',title=tr('Alle Apps'),icon='view-grid')]
    tasks=Property('QVariantList',lambda s:s._tasks,notify=changed)
    recent=Property('QVariantList',lambda s:s._recent,notify=changed)
    apps=Property('QVariantList',lambda s:s._apps,notify=changed)

    @Slot()
    def show_all_apps(self):
        self.expanded_apps = True
        self._apps = self.all_apps + [dict(id='apps',title=tr('Weniger Apps'),icon='go-up')]
        self.changed.emit()

    status=Property(str,lambda s:tr('Übersicht nicht vollständig verfügbar') if s._error else tr('Bereit'),notify=changed)
    detail=Property(str,lambda s:s._error or tr('{0} aktive Aufträge',sum(t['status'] not in ('completed','cancelled','failed') for t in s._tasks)),notify=changed)

    @Slot()
    def start(self):self.refresh();self.timer.start()
    @Slot()
    def stop(self):self.timer.stop();self.cancel()
    def cancel(self):
        if self.process:self.process.kill()

    def shutdown(self):
        self.timer.stop()
        proc=self.process
        if proc:proc.kill();proc.waitForFinished(1000)
    @Slot()
    def refresh(self):
        if self.process:return
        proc=worker_process(self);self.process=proc;buffer=bytearray()
        def read():
            buffer.extend(bytes(proc.readAllStandardOutput()))
            if len(buffer)>512000:proc.kill()
        def done(code=0,*_):
            if self.process is not proc:return
            read();self.timeout.stop();self.process=None
            try:
                if code:raise ValueError(tr('Übersicht konnte nicht aktualisiert werden.'))
                data=json.loads(buffer);self._tasks=data['tasks'];self._recent=data['recent'];self._error=data['error']
            except (ValueError,KeyError):self._error=tr('Übersicht konnte nicht aktualisiert werden.')
            self.changed.emit();proc.deleteLater()
        proc.readyReadStandardOutput.connect(read);proc.finished.connect(done)
        proc.errorOccurred.connect(lambda error:done(-1) if error==QProcess.FailedToStart else None)
        proc.start(sys.executable,[str(Path(__file__).resolve()),'--snapshot']);self.timeout.start(4000)

    @Slot(str)
    def launch_app(self,key):
        if key == 'apps':
            if not self.expanded_apps: self.show_all_apps()
            else:
                self.expanded_apps = False
                self._apps = [row for row in self.all_apps if row['id'] in ('files','wissen','workbench','vault','inbox')] + [dict(id='apps',title=tr('Alle Apps'),icon='view-grid')]
                self.changed.emit()
            return
        try:
            from lumen_apps import launch
            launch(key)
        except (OSError,ValueError) as e:self.failed.emit(str(e))
    @Slot(str)
    def open_task(self,key):
        if not any(t['id']==key for t in self._tasks):return
        self.launch_desktop(['--task',key])
    @Slot(str)
    def open_page(self,page):
        if page in ('tasks','system','files'):self.launch_desktop(['--page',page])
    def launch_desktop(self,args):
        try:
            from lumen_launch import executable
            subprocess.Popen([executable('lumen-agent-app'),*args],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except OSError as e:self.failed.emit(str(e))
    @Slot(str)
    def dismiss(self,key):
        if not any(t['id']==key and t['status'] in ('completed','cancelled') for t in self._tasks):return
        try:
            from lumen_store import Store
            Store().dismiss_task(key);self.refresh()
        except (OSError,ValueError) as e:self.failed.emit(str(e))
    @Slot(str)
    def open_recent(self,path):
        if any(r['path']==path for r in self._recent):
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):self.failed.emit(tr('Datei konnte nicht geöffnet werden.'))


if __name__=='__main__':
    print(json.dumps(snapshot(),ensure_ascii=False))

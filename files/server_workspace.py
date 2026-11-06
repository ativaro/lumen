"""Native device management over the existing paired server services."""
import json
from uuid import uuid4
from urllib.error import HTTPError
from urllib.parse import urlencode
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QComboBox, QSplitter, QListWidget, QListWidgetItem, QMessageBox
from shiboken6 import isValid
from tools_ui import Job, button, label, row
from lumen_i18n import tr
import hashlib
from sync_identity import scope as stable_scope
import lumen_connect

TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted', 'declined')
STATES = {'queued': 'Wartet', 'running': 'Läuft', 'pending': 'Wartet auf Gerät',
          'claimed': 'Wird ausgeführt', 'completed': 'Abgeschlossen', 'failed': 'Fehlgeschlagen',
          'cancelled': 'Abgebrochen', 'interrupted': 'Unterbrochen', 'paused': 'Pausiert', 'open': 'Offen', 'declined':'Abgelehnt', 'waiting_device':'Wartet auf Gerät'}
OPERATIONS = {'services': 'Dienste prüfen', 'update-check': 'Updates prüfen',
              'restart-watch': 'Wächter neu starten', 'restart-jobs': 'Auftragsdienst neu starten'}


def selected(widget):
    item = widget.currentItem()
    return item.data(Qt.UserRole) if item else None


def fill(widget, values, title):
    old = (selected(widget) or {}).get('id'); widget.blockSignals(True); widget.clear()
    for value in values:
        item = QListWidgetItem(title(value)); item.setData(Qt.UserRole, value); widget.addItem(item)
        if value.get('id') == old: widget.setCurrentItem(item)
    if widget.currentRow() < 0 and widget.count(): widget.setCurrentRow(0)
    widget.blockSignals(False)


class RemotePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.job = None; self.account = ''; self.server = ''; self.caps = []; self.generation = 0
        self.setObjectName('serverPage')
        self.setStyleSheet('''QWidget#serverPage QTabWidget::pane { border: none; background: transparent; }
            QWidget#serverPage QListWidget { border: 1px solid palette(mid); border-radius: 10px; padding: 5px; }
            QWidget#serverPage QListWidget::item { padding: 12px 10px; border-radius: 7px; }
            QWidget#serverPage QListWidget::item:selected { background: palette(alternate-base); color: palette(text); }
            QWidget#serverPage QScrollArea { border: none; background: transparent; }
            QWidget#serverPage QSplitter { background: transparent; }''')
        self.box = QVBoxLayout(self); self.box.setSpacing(14)
        self.status = label(tr('Mit deinem verbundenen Lumen Server arbeiten.'), 'muted')
        self.box.addWidget(self.status)
        self.content = QWidget(); self.body = QVBoxLayout(self.content); self.body.setContentsMargins(0,0,0,0)
        self.box.addWidget(self.content, 1)
        self.timer = QTimer(self); self.timer.setInterval(5000); self.timer.timeout.connect(self.poll)
        self.timer.start()

    def call(self, function, done, connect=False, quiet=False):
        if self.job: return
        generation, account = self.generation, self.account
        def run(_):
            config = lumen_connect.read_config(); identity = stable_scope(config, ['projects'], hashlib.sha256((config['server']+'\0'+config['token']).encode()).hexdigest())
            if not connect and identity != account:
                raise ValueError(tr('Serverkonto geändert. Ansicht neu laden.'))
            def request(path, body=None):
                try: return lumen_connect.request(config, path, body)
                except HTTPError as error:
                    detail = ''
                    try: detail = json.loads(error.read(4096)).get('detail', '')
                    except (ValueError, AttributeError): pass
                    raise ValueError(f'HTTP {error.code} · {detail}' if isinstance(detail,str) else f'HTTP {error.code}') from None
            return identity, config['server'], function(request)
        # Keep a bounded network job alive even if its containing window closes.
        app = QApplication.instance(); job = Job(run, app); self.job = job
        if not hasattr(app, '_server_jobs'):
            app._server_jobs = set()
            app.aboutToQuit.connect(lambda: [j.wait() for j in list(app._server_jobs)])
        app._server_jobs.add(job)
        if not quiet: self.content.setEnabled(False); self.status.setText(tr('Server wird abgefragt …'))
        outcome = {}
        job.result.connect(lambda value: outcome.update(value=value))
        job.failed.connect(lambda message: outcome.update(error=message))
        def finished():
            app._server_jobs.discard(job)
            if isValid(self):
                self.job = None; self.content.setEnabled(True)
                if generation != self.generation:
                    QTimer.singleShot(0, self.resume)
                elif 'error' in outcome:
                    self.status.setText(outcome['error'])
                    self.clear_sensitive()
                elif 'value' in outcome:
                    self.account, self.server, data = outcome['value']
                    self.status.setText(self.server)
                    try: done(data)
                    except Exception as error: self.status.setText(str(error))
            job.deleteLater()
        job.finished.connect(finished); job.start()

    def resume(self): self.reload()

    def clear_sensitive(self): pass

    def showEvent(self, event):
        super().showEvent(event)
        if not self.account: QTimer.singleShot(0, self.reload)

    def poll(self): pass

    def web(self, app, **params):
        try: server=lumen_connect.read_config()['server']
        except (OSError,ValueError,KeyError) as error:
            self.status.setText(str(error));return
        QDesktopServices.openUrl(QUrl(server+'/?'+urlencode(dict(app=app, **params))))




class ServerDevices(RemotePage):
    def __init__(self,parent=None):
        super().__init__(parent);self.receipt=None;self.pending=None
        self.body.addWidget(row(label(tr('Verbundene Geräte')),button(tr('Aktualisieren'),self.reload,'view-refresh'),button(tr('Geräte verbinden / Freigaben'),lambda:self.web('devices'))))
        split=QSplitter();self.body.addWidget(split,1);self.devices=QListWidget();self.devices.setAccessibleName(tr('Servergeräte'));split.addWidget(self.devices)
        panel=QWidget();box=QVBoxLayout(panel);split.addWidget(panel);split.setStretchFactor(1,2)
        self.details=label('');box.addWidget(self.details)
        self.operation=QComboBox();self.operation.setAccessibleName(tr('Geräteaktion'));self.run=button(tr('Ausführen'),self.execute)
        self.wake=button(tr('Aufwecken'),lambda:self.execute(wake=True));box.addWidget(row(self.operation,self.run,self.wake))
        self.progress_title=label('', 'muted');box.addWidget(self.progress_title)
        self.progress=QListWidget();self.progress.setAccessibleName(tr('Aktionsfortschritt'));box.addWidget(self.progress,1)
        self.devices.currentRowChanged.connect(self.device_changed)

    def clear_sensitive(self):
        self.devices.clear();self.details.clear();self.progress.clear();self.progress_title.clear();self.device_changed()

    def reload(self):
        def load(r):
            me=r('/bridge/me')
            if 'device_control' not in me['capabilities']:
                raise ValueError(tr('Auf dem Server unter Geräte die Freigabe „Andere Servergeräte von diesem Desktop verwalten“ aktivieren.'))
            return me,r('/bridge/management')
        self.call(load,self.loaded,connect=True)

    def loaded(self,value):
        me,rows=value;self.caps=me['capabilities']
        if self.receipt and self.receipt[0]!=self.account:self.receipt=None;self.pending=None;self.progress.clear();self.progress_title.clear()
        fill(self.devices,rows,lambda d:d['name']+'\n'+tr('Zuletzt verbunden: ')+str(d.get('last_seen') or tr('Noch nicht')))
        self.device_changed()

    def device_changed(self):
        device=selected(self.devices) or {};inventory=device.get('inventory') or {}
        self.details.setText(device.get('name','')+'\n'+' · '.join(str(inventory[k]) for k in ('hostname','os','architecture','lumen') if inventory.get(k)))
        self.operation.clear()
        for op,title in OPERATIONS.items():
            if op in device.get('operations',[]):self.operation.addItem(tr(title),op)
        self.run.setEnabled(self.operation.count()>0 and not self.pending)
        self.wake.setEnabled(bool(device.get('wake_ready') and 'wake' in self.caps and not self.pending))

    def execute(self,wake=False):
        device=selected(self.devices)
        if not device:return
        op='wake' if wake else self.operation.currentData()
        if not op:return
        if op.startswith('restart') and QMessageBox.question(self,tr('Lumen Geräte'),tr('Dienst auf diesem Gerät neu starten?'))!=QMessageBox.Yes:return
        # Retain this request ID after a timeout: polling and retry cannot duplicate it.
        key=(self.account,device['id'],op)
        if not self.pending or self.pending[0]!=key:self.pending=(key,str(uuid4()))
        identity=self.pending[1]
        self.progress_title.setText(device['name']+' · '+tr('Aufwecken' if wake else OPERATIONS[op]))
        path=f"/bridge/management/{device['id']}/wake" if wake else '/bridge/management'
        body=dict(request_id=identity) if wake else dict(request_id=identity,devices=[device['id']],operation=op)
        self.receipt=(self.account,f'/bridge/management/{identity}'+('/wake' if wake else ''))
        self.call(lambda r:r(path,body),self.show_progress)

    def show_progress(self,data):
        actions=data.get('actions',[data]);values=[];active=False
        for action in actions:
            state='interrupted' if action.get('expired') else action['state'];active|=state not in TERMINAL
            values.append(tr(STATES.get(state,state)))
            progress=action.get('progress') or {};result=action.get('result') or {}
            for name,check in progress.get('checks',{}).items():
                values.append(name+' · '+tr('In Ordnung' if check['state']=='active' or (check['state']=='inactive' and check['expected'] in ('optional','on-demand')) else 'Prüfen')+' · '+check['state'])
            if progress.get('current'):values.append(tr('Wird geprüft: ')+progress['current'])
            if not progress.get('checks'):
                for name,state in result.get('services',{}).items():values.append(name+' · '+str(state))
            if action.get('error'):values.append(str(action['error']))
            for k,v in result.items():
                if k not in ('services','operation'):values.append(str(k)+' · '+(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)))
        self.progress.clear();self.progress.addItems(values)
        if not active:self.pending=None;self.receipt=None
        self.device_changed()

    def poll(self):
        if self.isVisible() and self.receipt and not self.job:
            self.call(lambda r:r(self.receipt[1]),self.show_progress,quiet=True)

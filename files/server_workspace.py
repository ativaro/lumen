"""Native views over the existing paired project, scheduler and device services."""
import json
from uuid import uuid4
from urllib.error import HTTPError
from urllib.parse import urlencode
from PySide6.QtCore import Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QTabWidget, QSplitter, QListWidget, QListWidgetItem, QScrollArea, QDialog,
    QDialogButtonBox, QFormLayout, QLineEdit, QPlainTextEdit, QSpinBox, QMessageBox)
from shiboken6 import isValid
from tools_ui import Job, button, label, row
from answer_widget import AnswerBody
from lumen_i18n import tr
from projects_sync import scope
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
            config = lumen_connect.read_config(); identity = scope(config)
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


class ServerWorkspace(RemotePage):
    def __init__(self, parent=None, project_id=None):
        super().__init__(parent); self.fixed = project_id; self.room = ''; self.data = {}; self.requests = {}
        self.preferences = QSettings('Lumen','ServerWorkspaces')
        self.project = QComboBox(); self.project.setAccessibleName(tr('Serverprojekt'))
        self.bind = button(tr('Mit Projekt verbinden'), self.bind_room, 'insert-link')
        self.body.addWidget(row(self.project, self.bind, button(tr('Aktualisieren'),self.reload,'view-refresh'),
                                button(tr('Auf Server öffnen'),lambda:self.web('projects',project=self.project.currentData() or ''))))
        self.hint = label(tr('Diese Verbindung zeigt Serverinhalte. Lokale Dateien werden nicht hochgeladen.'),'muted');self.body.addWidget(self.hint)
        self.tabs = QTabWidget(); self.body.addWidget(self.tabs,1)
        work = QWidget(); box = QVBoxLayout(work); split = QSplitter(); box.addWidget(split,1)
        self.items = QListWidget(); self.items.setWordWrap(True); self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.items.setAccessibleName(tr('Projektaufgaben'));split.addWidget(self.items)
        right = QWidget(); right_box=QVBoxLayout(right);split.addWidget(right);split.setStretchFactor(1,2)
        self.runs = QListWidget(); self.runs.setAccessibleName(tr('Durchläufe')); self.runs.setMaximumHeight(105);right_box.addWidget(self.runs)
        self.start = button(tr('Auf Server starten'),self.start_item,'media-playback-start')
        self.stop = button(tr('Stoppen'),lambda:self.task_action('cancel'),'media-playback-stop')
        self.again = button(tr('Erneut ausführen'),lambda:self.task_action('rerun'),'view-refresh')
        right_box.addWidget(row(self.start,self.stop,self.again))
        area=QScrollArea();area.setWidgetResizable(True);self.answer=AnswerBody(QSettings('Lumen','Assistant'));area.setWidget(self.answer);right_box.addWidget(area,1)
        self.tabs.addTab(work,tr('Aufträge & Ergebnisse').replace('&','&&'))
        schedule=QWidget();box=QVBoxLayout(schedule);self.schedules=QListWidget();self.schedules.setAccessibleName(tr('Zeitpläne'));box.addWidget(self.schedules,1)
        self.schedule_edit=button(tr('Zeitplan bearbeiten'),self.edit_schedule,'document-edit')
        self.schedule_toggle=button(tr('Aktivieren / Pausieren'),self.toggle_schedule,'media-playback-pause')
        box.addWidget(row(self.schedule_edit,self.schedule_toggle));box.addWidget(label(tr('Läuft auf dem Server weiter, auch wenn dieser Desktop ausgeschaltet ist.'),'muted'))
        self.tabs.addTab(schedule,tr('Zeitpläne'))
        people=QWidget();box=QVBoxLayout(people);self.members=QListWidget();self.members.setAccessibleName(tr('Mitglieder und Rollen'));box.addWidget(label(tr('Mitglieder und Rollen')));box.addWidget(self.members)
        self.material=QListWidget();self.material.setAccessibleName(tr('Gemeinsame Materialien'));box.addWidget(label(tr('Gemeinsame Materialien')));box.addWidget(self.material)
        box.addWidget(button(tr('Freigaben auf Server verwalten'),lambda:self.web('projects',project=self.project.currentData() or '')))
        self.tabs.addTab(people,tr('Zusammenarbeit'))
        self.project.currentIndexChanged.connect(self.project_changed)
        self.items.currentRowChanged.connect(self.show_runs);self.runs.currentRowChanged.connect(self.show_result)
        self.schedules.currentRowChanged.connect(self.controls)
        self.bind.setVisible(not project_id);self.controls()

    def set_room(self, identity):
        if identity == self.room: return
        self.room=identity;self.generation+=1;self.account='';self.data={};self.clear()
        if self.isVisible(): self.reload()

    def key(self): return f'{self.account}/{self.room}'

    def clear(self):
        for widget in (self.items,self.runs,self.schedules,self.members,self.material): widget.clear()
        self.answer.set_answer('',None);self.controls()

    def resume(self):
        if self.account:self.load()
        else:self.reload()

    def clear_sensitive(self):
        self.data={};self.clear()

    def reload(self):
        if self.job: return
        def load(r):
            me=r('/bridge/me')
            if not {'projects','tasks'} <= set(me['capabilities']):
                raise ValueError(tr('Auf dem Server unter Geräte „Projekte synchronisieren“ und „Serveraufträge“ für diesen Desktop freigeben.'))
            from projects_sync import available
            import lumen_connect
            return me,available(lumen_connect.read_config())
        self.call(load,self.connected,connect=True)

    def connected(self, value):
        me, projects=value;self.caps=me['capabilities']
        desired=self.fixed or self.preferences.value(self.key(),'')
        self.project.blockSignals(True);self.project.clear();self.project.addItem(tr('Serverprojekt auswählen …'),None)
        for project in projects: self.project.addItem(project['title'],project['id'])
        index=self.project.findData(desired);self.project.setCurrentIndex(max(0,index));self.project.blockSignals(False)
        self.project.setEnabled(not self.fixed);self.clear()
        QTimer.singleShot(0,self.project_changed)

    def bind_room(self):
        if not self.room: return
        self.preferences.setValue(self.key(),self.project.currentData() or '');self.preferences.sync()
        self.hint.setText(tr('Verbindung gespeichert. Inhalte bleiben an ihrem ursprünglichen Ort.'))

    def project_changed(self):
        self.generation+=1;self.data={};self.clear()
        if self.project.currentData(): self.load()

    def load(self):
        project_id=self.project.currentData()
        if project_id and not self.job:
            self.call(lambda r:r('/bridge/projects/'+project_id+'/activity'),self.loaded,quiet=True)

    def loaded(self, data):
        self.data=data
        self.timer.setInterval(5000 if any(t['state'] not in TERMINAL for t in data['tasks']) else 30000)
        fill(self.items,[i for i in data['items'] if i['kind'] != 'initiative' and not i['archived']],
             lambda i:i['title']+'\n'+tr(STATES.get(i['state'],i['state'])))
        fill(self.schedules,[i for i in data['items'] if i['kind']=='automation' and not i['archived']],
             lambda i:i['title']+' · '+(tr('Aktiv') if (i.get('automation') or {}).get('enabled') else tr('Pausiert'))+' · '+str(i['interval_minutes'])+' min'+
             ('\n'+tr('Nächster Lauf: ')+str(i['automation']['next_run']) if (i.get('automation') or {}).get('enabled') else '')+
             ('\n'+str(i['automation']['project_error']) if (i.get('automation') or {}).get('project_error') else ''))
        fill(self.members,[dict(m,id=m.get('id',m.get('email'))) for m in data['members']],lambda m:m['name']+' · '+tr({'manager':'Verwalter','editor':'Bearbeiten','reader':'Lesen'}.get(m['role'],m['role'])))
        fill(self.material,[dict(n,source='Lumen Notes') for n in data['notes']]+[dict(f,source='Lumen Drive') for f in data['files']],lambda m:m.get('title',m.get('name',''))+' · '+m['source'])
        self.show_runs();self.controls()

    def show_runs(self):
        item=selected(self.items)
        fill(self.runs,[t for t in self.data.get('tasks',[]) if item and t.get('project_item_id')==item['id']],
             lambda t:tr(STATES.get(t['state'],t['state']))+' · '+str(t['created']))
        self.show_result()

    def show_result(self):
        task=selected(self.runs);item=selected(self.items)
        value=(task.get('result') or task.get('error') or task.get('progress') or tr('Auftrag wartet auf Verarbeitung.')) if task else (item or {}).get('goal','')
        self.answer.set_answer(str(value), (self.account,self.project.currentData(),(task or item or {}).get('id')));self.controls()

    def controls(self, *_):
        writable=self.data.get('role') in ('manager','editor') and 'tasks' in self.caps
        item=selected(self.items);task=selected(self.runs);schedule=selected(self.schedules)
        self.start.setEnabled(bool(writable and item and item['kind'] in ('analysis','research','automation') and not (task and task['state'] not in TERMINAL)))
        self.stop.setEnabled(bool(writable and task and task['state'] not in TERMINAL))
        self.again.setEnabled(bool(writable and task and task['state'] in TERMINAL))
        self.schedule_edit.setEnabled(bool(writable and schedule));self.schedule_toggle.setEnabled(bool(writable and schedule))
        self.bind.setEnabled(bool(self.room and self.account))

    def mutate(self,path,body,key=None):
        def applied(_):
            if key:self.requests.pop(key,None)
            self.load()
        self.call(lambda r:r(path,body),applied)

    def start_item(self):
        item=selected(self.items)
        if not item:return
        path=f"/bridge/projects/{self.project.currentData()}/items/{item['id']}/runs"
        key=(path,item['revision'])
        self.mutate(path,dict(revision=item['revision'],request_id=self.requests.setdefault(key,str(uuid4()))),key)

    def task_action(self, action):
        task=selected(self.runs)
        if not task:return
        path=f"/bridge/projects/{self.project.currentData()}/tasks/{task['id']}/{action}"
        key=(path,task['revision'])
        self.mutate(path,{} if action=='cancel' else dict(revision=task['revision'],request_id=self.requests.setdefault(key,str(uuid4()))),key)

    def toggle_schedule(self):
        item=selected(self.schedules)
        if not item:return
        routine=item.get('automation') or {}
        self.mutate(f"/bridge/projects/{self.project.currentData()}/items/{item['id']}/automation",
                    dict(revision=item['revision'],routine_revision=routine.get('revision',0),enabled=not routine.get('enabled',False)))

    def edit_schedule(self):
        item=selected(self.schedules)
        if not item:return
        dialog=QDialog(self);dialog.setWindowTitle(tr('Lumen Zeitplan'));form=QFormLayout(dialog)
        title=QLineEdit(item['title']);goal=QPlainTextEdit(item['goal']);interval=QSpinBox();interval.setRange(60,525600);interval.setValue(item['interval_minutes']);interval.setSuffix(' min')
        operation=QComboBox();operation.addItem(tr('Analysieren'),'analysis');operation.addItem(tr('Recherchieren'),'research');operation.setCurrentIndex(max(0,operation.findData(item['operation'])))
        form.addRow(tr('Titel'),title);form.addRow(tr('Ziel'),goal);form.addRow(tr('Aktion'),operation);form.addRow(tr('Intervall'),interval)
        form.addRow(label(tr('Änderungen pausieren den Zeitplan. Anschließend ausdrücklich aktivieren.')))
        controls=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(controls);controls.accepted.connect(dialog.accept);controls.rejected.connect(dialog.reject)
        if dialog.exec()!=QDialog.Accepted:return
        body={k:item[k] for k in ('revision','title','notes','goal','attachments','depends','done','operation','interval_minutes')}
        body.update(title=title.text(),goal=goal.toPlainText(),operation=operation.currentData(),interval_minutes=interval.value())
        self.mutate(f"/bridge/projects/{self.project.currentData()}/items/{item['id']}",body)

    def poll(self):
        if self.isVisible() and self.account and not self.job:self.load()


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

"""Project orchestration with one workspace and its dedicated sidebar editor."""
from lumen_i18n import tr
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QPlainTextEdit, QListWidget, QListWidgetItem,
    QTabWidget, QWidget, QVBoxLayout, QTreeWidgetItem, QDialog, QDialogButtonBox, QMenu)
from tools_data import web_url
from tools_ui import ToolWindow, button, label, row, open_path


class Workbench(ToolWindow):
    def __init__(self,root=None):
        super().__init__('workbench',tr('Lumen Projekte'),tr('Projekte, Vorhaben und ihre nächsten Schritte.'),'folder-development',root)
        from projects_data import Projects
        self.projects=Projects(self.library); self.scope=''; self.initiative=''; self.runner=None
        from projects_runner import recover
        recover(self.projects)
        self.loaded_fields={}; self.loaded_record={}; self.loaded_updated=None; self.interop_path_revision=0
        from project_editor import ProjectEditor
        self.editor=ProjectEditor(self)
        self.setup_projects()
        from interop_workflow_ui import install_menu
        install_menu(self)
        self.editor.workflow_action=self.editor.more_menu.addMenu(self._workflow_menu)
        from projects_sync_ui import install
        install(self)

        from lumen_workplace import Workplace
        from lumen_workspace import Workspace
        self.room_files = None
        self.workplace = Workplace(self, files_provider=self.workspace_files)
        self.workplace.remote_conversations = True
        self.automations = Workspace(self, store=self.workplace.store, sections=('flows',))
        self.recurring=QListWidget();self.recurring.setAccessibleName(tr('Wiederkehrende Projektaufgaben'));self.recurring.setMaximumHeight(160)
        self.recurring.itemActivated.connect(lambda item:self.safe(self.navigate,*item.data(Qt.UserRole)))
        self.recurring.itemClicked.connect(lambda item:self.safe(self.navigate,*item.data(Qt.UserRole)))
        self.automations.flows_page.layout().insertWidget(1,label(tr('Wiederkehrende Projektaufgaben'),'heading'))
        self.automations.flows_page.layout().insertWidget(2,self.recurring)
        management = self.takeCentralWidget()
        self.areas = QTabWidget(); self.areas.setAccessibleName(tr('Projektbereiche'))
        self.areas.setStyleSheet('QTabWidget::pane { border: none; }')
        self.areas.addTab(management, tr('Archiv und Serverabgleich'))
        self.areas.addTab(self.workplace, tr('Projekte'))
        self.areas.addTab(self.automations.flows_page, tr('Automationen'))
        self.areas.tabBar().hide()
        from projects_home import ProjectHome
        self.home = ProjectHome(self)
        self.areas.addTab(self.home,tr('Projekt'))
        self.home.editor_layout.addWidget(self.editor)
        shell=QWidget();layout=QVBoxLayout(shell);layout.setContentsMargins(0,0,0,0)
        self.back_home=button(tr('‹ Projekte'),lambda:self.safe(self.show_home),'go-previous')
        self.flow_entry=button(tr('Alle Automationen'),lambda:self.safe(self.open_section,'automations'))
        self.flow_entry.setToolTip(tr('Bestehende Abläufe mit Schritten, Zeit- oder Ordnerauslösern.'))
        navigation=row(self.back_home,self.flow_entry);navigation.layout().insertStretch(1,1);navigation.layout().setContentsMargins(16,4,16,4)
        layout.addWidget(navigation);layout.addWidget(self.areas,1)
        self.setCentralWidget(shell)
        self.areas.currentChanged.connect(self.refresh_area)
        self.show_home()

    def show_home(self):
        if not self.editor.allow_leave():return
        self.editor.hide();self.home.refresh();self.areas.setCurrentIndex(3);self.back_home.hide()

    def focus_record(self,key):
        if not self.editor.allow_leave():return
        self.editor.discard()
        super().focus_record(key)
        if hasattr(self,'home'):
            self.home.project_id=key;self.home.room_id=(self.home.links.room(key) or {}).get('id','');self.home.scope='';self.home.refresh()
            self.editor.present(self.library.get(key))
            self.loaded_fields=self.editor_fields();self.areas.setCurrentIndex(3)

    def edited(self,*_):
        if not self.loading:
            text=tr('Ungespeicherte Änderungen · Speichern übernimmt die Eingabe.');self.status.setText(text)
            if hasattr(self,'editor'):self.editor.feedback.setText(text)

    def workspace_files(self):
        if self.room_files is None or getattr(self.room_files, '_closed', False):
            from app import Window
            self.room_files = Window(str(Path.home()))
        return self.room_files

    def refresh_area(self, index):
        self.back_home.setVisible(index!=3)
        if index == 1: self.workplace.refresh_projects()
        elif index == 2:
            self.automations.refresh_flows();self.recurring.clear()
            for project in self.library.all():
                for task in self.projects.items(project['id']):
                    if task['kind']=='automation' or task.get('enabled') or task.get('next_run'):
                        item=QListWidgetItem(project['title']+' · '+task['title']+' · '+tr('Aktiv' if task.get('enabled') else 'Pausiert'))
                        item.setData(Qt.UserRole,(project['id'],task['id']));self.recurring.addItem(item)

    def open_section(self, section, request=None):
        if section not in ('projects','rooms','automations','household'): raise ValueError(tr('Unbekannter Projektbereich.'))
        if section in ('projects','rooms'):self.show_home();return
        if not self.editor.allow_leave():return
        self.editor.hide()
        self.areas.setCurrentIndex({'automations':2,'household':1}[section])
        if section == 'household':
            self.workplace.rooms.open_household(all_rooms=True)
            if request: self.workplace.rooms.household.activate(request)


    def create(self):
        self.new_entry('project')

    def new_entry(self,kind):
        if kind=='project' and self.home.prompt.text().strip():raise ValueError(tr('Bitte den Gesprächsentwurf zuerst besprechen oder leeren.'))
        if not self.editor.allow_leave():return
        self.editor.discard()
        if kind=='project':self.current='';self.scope='';self.initiative=''
        else:
            self.current=self.home.ensure_project();self.scope='';self.initiative=self.home.scope
        value=dict(title='',notes='',resources=[],kind='research' if kind=='task' else kind)
        self.editor.draft_kind=kind
        self.loading=True
        try:
            self.load_fields(value);self.editor.present(value,kind);self.loaded_fields=self.editor_fields()
        finally:self.loading=False
        self.areas.setCurrentIndex(3)

    def load(self,r):
        self.scope=''; self.initiative=''
        self.projects.migrate(r['id'])
        self.load_fields(r); self.refresh_tasks(); self.refresh()

    def load_fields(self,r):
        from interop_paths import update_window
        self.interop_path_revision=r.get('interop_path_revision',0)
        self.title.setText(r['title']); self.notes.setPlainText(r.get('notes','')); self.resources.clear()
        for resource in r.get('resources',[]):
            item=QListWidgetItem(resource['title']+'\n'+resource['target']); item.setData(Qt.UserRole,resource); self.resources.addItem(item)
        update_window(self)
        self.load_task_fields(r)
        self.loaded_fields=self.editor_fields()
        owner=self.library.get(self.current) if self.current else {}
        readonly=owner.get('server_bound') and owner.get('server_role')=='reader'
        self.title.setReadOnly(bool(readonly));self.notes.setReadOnly(bool(readonly))
        self.new_task.setEnabled(not readonly)
        if owner.get('server_bound'):
            self.status.setText(tr('Lumen Server · Änderungen werden synchronisiert') if owner.get('server_role')!='reader' else tr('Lumen Server · Nur lesen'))
        self.server_material.clear()
        for reference in r.get('server_attachments',[]):
            item=QListWidgetItem(reference.get('title') or reference['kind']+' · '+str(reference['id'])[:8]);item.setData(Qt.UserRole,reference);self.server_material.addItem(item)
        self.server_material.setVisible(bool(r.get('server_attachments')))
        self.loaded_record=dict(r)
        with self.library.connect() as db:
            table='project_items' if self.scope else 'records'
            stored=db.execute('SELECT updated FROM '+table+' WHERE id=?',(self.scope or self.current,)).fetchone()
            self.loaded_updated=str(stored['updated']) if stored else None

    def editor_fields(self):
        value=dict(title=self.title.text(),notes=self.notes.toPlainText(),resources=[self.resources.item(i).data(Qt.UserRole) for i in range(self.resources.count())],interop_path_revision=self.interop_path_revision)
        if self.editor.is_task():
            value.update(goal=self.goal.toPlainText(),depends=[self.dependencies.item(i).data(Qt.UserRole) for i in range(self.dependencies.count()) if self.dependencies.item(i).checkState()==Qt.Checked],deep=self.deep.isChecked(),operation=self.operation.currentData(),interval=self.interval.currentData(),enabled=self.schedule.isChecked())
        return value

    def save(self):
        self.save_timer.stop()
        if self.loading or not (self.current or self.editor.draft_kind):return
        if self.editor.environment is not None:
            if not self.editor.apply.isEnabled():raise ValueError(tr('Dieses Projekt ist schreibgeschützt.'))
            self.editor.environment.save();return
        if self.editor.draft_kind=='room-note':self.editor.save_room_note();return
        if self.editor.material.dirty():self.editor.material.stage_all()
        from interop_paths import update_window
        update_window(self)
        fields=self.editor_fields();changes={k:v for k,v in fields.items() if v!=self.loaded_fields.get(k)}
        draft=self.editor.draft_kind
        if not changes and not draft:return
        if not fields['title'].strip():raise ValueError(tr('Bitte einen Namen angeben.'))
        scheduled=fields.get('enabled',False)
        if self.editor.draft_kind=='task' and self.editor.kind.currentData()=='manual':
            fields['enabled']=False;scheduled=False
        if draft=='task' and not self.editor.owner.currentData():raise ValueError(tr('Bitte zuerst ein Vorhaben anlegen.'))
        if self.current and self.library.get(self.current).get('server_bound') and ('enabled' in changes or 'interval' in changes):
            raise ValueError(tr('Zeitpläne dieses Projekts werden auf Lumen Server verwaltet.'))
        if scheduled and (draft or not self.loaded_fields.get('enabled')):
            from projects_runner import install_timer
            import time
            install_timer(self.library.root.parent);fields['next_run']=time.time()+int(fields['interval']);changes['next_run']=fields['next_run']
        if draft=='project':
            title=fields.pop('title');self.current=self.library.create(title,**fields)
            if self.editor.location.currentData()=='server':
                from projects_sync import configure
                configure(self.library,True,self.current)
        elif draft:
            title=fields.pop('title');kind='initiative' if draft=='initiative' else self.editor.kind.currentData()
            parent='' if draft=='initiative' else self.editor.owner.currentData()
            self.scope=self.projects.add(self.current,parent,title,kind,**fields)
            self.initiative=self.scope if kind=='initiative' else parent
        elif self.scope:self.projects.update(self.scope,expected_updated=self.edit_revision(),**changes)
        else:self.library.update(self.current,expected_updated=self.edit_revision(),**changes)
        self.editor.draft_kind='';self.editor.material.reset()
        self.loading=True
        try:self.load_fields(self.projects.get(self.scope) if self.scope else self.library.get(self.current))
        finally:self.loading=False
        self.home.project_id=self.current;self.home.room_id=(self.home.links.room(self.current) or {}).get('id','');self.home.scope=self.initiative
        self.status.setText(tr('Gespeichert'));self.refresh();self.home.refresh()

    def edit_revision(self):
        """Accept recorded file relocations, but never overwrite another content edit."""
        from interop_paths import moves,mapped
        from copy import deepcopy
        import json
        changes=moves(self.library.root.parent,self.loaded_record.get('interop_path_revision',0))
        if not changes:return self.loaded_updated
        expected=deepcopy(self.loaded_record)
        for resource in expected.get('resources',[]):
            if resource.get('kind')=='file':resource['target']=mapped(resource['target'],changes)
        for item in expected.get('reading_list',[]):item['path']=mapped(item['path'],changes)
        with self.library.connect() as db:
            table='project_items' if self.scope else 'records'
            row=db.execute('SELECT * FROM '+table+' WHERE id=?',(self.scope or self.current,)).fetchone()
            if not row:return self.loaded_updated
            actual=self.projects.unpack(row) if self.scope else dict(json.loads(row['data']),id=row['id'],title=row['title'],_archived=bool(row['archived']))
            for record in (expected,actual):
                record.pop('updated',None);record.pop('interop_path_revision',None)
            return str(row['updated']) if expected==actual else self.loaded_updated

    def add_resource(self,kind,target,title):
        self.editor.material.append(kind,target,title)

    def add_files(self):self.open_material_editor('file')
    def add_folder(self):self.open_material_editor('folder')
    def add_link(self):self.open_material_editor('url')

    def open_material_editor(self,kind=None):
        self.editor.show_page(1)
        if kind:self.editor.material.kind.setCurrentIndex(self.editor.material.kind.findData(kind))

    def open_server_material(self):
        from projects_sync_ui import open_server
        import lumen_connect
        from uuid import UUID
        item=self.server_material.currentItem()
        if not item:return
        reference=item.data(Qt.UserRole)
        if reference['kind']=='file':
            config=lumen_connect.read_config();QDesktopServices.openUrl(QUrl(config['server']+'/api/files/'+str(UUID(str(reference['id'])))+'/content'))
        else:open_server(self)

    def open_resource(self):
        from interop_paths import update_window
        update_window(self)
        item=self.resources.currentItem()
        if not item: return
        value=item.data(Qt.UserRole)
        if value['target'].startswith('lumen:'):
            from interop_open import open_url
            open_url(value['target'],self.library.root.parent)
            return
        if value['kind']=='file': open_path(value['target'])
        elif not QDesktopServices.openUrl(QUrl(web_url(value['target']))): raise ValueError(tr('Browser konnte nicht geöffnet werden.'))

    def remove_resource(self):
        i=self.resources.currentRow()
        if i>=0: self.resources.takeItem(i); self.edited()

    def export(self):
        self.save(); r=self.library.get(self.current)
        text='# '+r['title']+'\n\n'+r.get('notes','')+tr('\n\n## Fragen\n\n')
        text+='\n'.join(('- [x] ' if q['done'] else '- [ ] ')+q['text'] for q in r.get('questions',[]))
        text+=tr('\n\n## Material\n\n')+'\n'.join('- '+v['title']+': '+v['target'] for v in r.get('resources',[]))
        for initiative in self.projects.items(self.current,''):
            text+='\n\n## '+initiative['title']+'\n\n'+initiative.get('notes','')
            for task in self.projects.items(self.current,initiative['id']):
                text+='\n\n### '+task['title']+'\n\n'+task.get('goal','')+'\n\n'+task.get('notes','')
                text+='\n'+ '\n'.join('- '+v['title']+': '+v['target'] for v in task.get('resources',[]))
                for run in self.projects.runs(task['id']):
                    text+='\n\n'+self.stamp(run['started'])+' · '+run['status']+'\n\n'+run.get('result','')+'\n'+run.get('error','')
        self.export_text(text,'projekt.md')

    @staticmethod
    def stamp(value):
        from datetime import datetime
        return datetime.fromtimestamp(value).strftime('%d.%m.%Y %H:%M') if value else '—'

    def setup_projects(self):
        old=self.entries;old.currentItemChanged.disconnect(self.select)
        from interop_drag import EntryTree,EntryList
        self.entries=EntryTree(self);self.entries.setHeaderHidden(True);self.entries.setAccessibleName(tr('Projekte und Vorhaben'))
        self.sidebar.layout().replaceWidget(old,self.entries);old.deleteLater();self.entries.currentItemChanged.connect(self.select)
        self.search.setPlaceholderText(tr('Projekte und Aufgaben suchen …'))
        middle=QWidget();self.task_pane=middle;box=QVBoxLayout(middle)
        self.task_heading=label(tr('Aufgaben'),'heading');box.addWidget(self.task_heading)
        self.new_task=button(tr('Aufgabe anlegen'),lambda:self.safe(self.create_task));box.addWidget(self.new_task)
        self.task_list=EntryList(self);self.task_list.setAccessibleName(tr('Aufgaben'));self.task_list.currentItemChanged.connect(self.select_task);box.addWidget(self.task_list,1)
        self.task_archive=button(tr('Aufgabe archivieren'),lambda:self.safe(self.archive_task));box.addWidget(self.task_archive)
        self.split.insertWidget(1,middle);self.resize(1380,900)
        self.content.addWidget(button(tr('Projektübersicht exportieren'),lambda:self.safe(self.export)));self.content.addStretch(1)
        self.add_button.hide();self.new_task.hide()
        self.poll_timer=QTimer(self);self.poll_timer.setInterval(5000);self.poll_timer.timeout.connect(lambda:self.safe(self.poll_runs));self.poll_timer.start()

    def refresh(self,*_):
        if not hasattr(self,'projects'): return
        self.entries.blockSignals(True); self.entries.clear(); query=self.search.text().casefold(); selected=None
        archive=self.archived.isChecked()
        projects=self.library.all()+self.library.all(True) if archive else self.library.all()
        for project in projects:
            self.projects.migrate(project['id']); children=self.projects.items(project['id'])+self.projects.items(project['id'],archived=True)
            if archive:
                if not self.library.get(project['id'])['_archived'] and not any(c['archived'] for c in children):continue
                parents={c['parent'] for c in children if c['archived']}
                visible=children if self.library.get(project['id'])['_archived'] else [c for c in children if c['archived'] or c['id'] in parents]
            else:visible=[c for c in children if not c['archived']]
            if query and query not in str(project).casefold() and not any(query in str(c).casefold() for c in children): continue
            node=QTreeWidgetItem([project['title']]); node.setData(0,Qt.UserRole,(project['id'],'')); self.entries.addTopLevelItem(node)
            if self.current==project['id'] and not self.initiative: selected=node
            for child in visible:
                if child['kind']!='initiative': continue
                leaf=QTreeWidgetItem([child['title']]); leaf.setData(0,Qt.UserRole,(project['id'],child['id'])); node.addChild(leaf)
                if self.current==project['id'] and self.initiative==child['id']: selected=leaf
            node.setExpanded(True)
        self.entries.setCurrentItem(selected); self.entries.blockSignals(False)
        self.archive_button.setEnabled(bool(self.current))
        archived=self.projects.get(self.initiative)['archived'] if self.initiative else self.library.get(self.current)['_archived'] if self.current else False
        self.archive_button.setText(tr('Vorhaben wiederherstellen') if archived and self.initiative else tr('Vorhaben archivieren') if self.initiative else tr('Projekt wiederherstellen') if archived else tr('Projekt archivieren'))
        self.refresh_tasks()

    def select(self,item,old):
        if not item:return
        project,scope=item.data(0,Qt.UserRole)
        self.safe(self.navigate,project,scope)

    def navigate(self,project,scope=''):
        if not self.editor.allow_leave():return False
        self.editor.discard();self.current=project;self.projects.migrate(project);self.open_scope(scope);return True

    def open_scope(self,key=''):
        value=self.projects.get(key) if key else self.library.get(self.current)
        if key and value['project']!=self.current:raise ValueError(tr('Dieser Eintrag gehört zu einem anderen Projekt.'))
        self.scope=key;self.initiative=(key if value['kind']=='initiative' else value['parent']) if key else ''
        self.editor.draft_kind='';self.loading=True
        try:
            self.load_fields(value)
            if hasattr(self,'home'):
                self.home.project_id=self.current;self.home.room_id=(self.home.links.room(self.current) or {}).get('id','');self.home.scope=self.initiative;self.home.refresh();self.editor.present(value)
            self.loaded_fields=self.editor_fields()
        finally:self.loading=False
        self.body.setEnabled(True);self.refresh()
        if hasattr(self,'areas'):self.areas.setCurrentIndex(3)

    def refresh_tasks(self):
        if not hasattr(self,'task_list'): return
        from projects_data import KINDS,STATES
        self.task_list.blockSignals(True); self.task_list.clear(); selected=None
        values=(self.projects.items(self.current)+self.projects.items(self.current,archived=True)) if self.current else []
        parents={v['id']:v for v in values if v['kind']=='initiative'}
        query=self.search.text().casefold()
        for task in values:
            if task['kind']=='initiative' or (self.initiative and task['parent']!=self.initiative): continue
            archived=bool(task['archived'] or parents.get(task['parent'],{}).get('archived') or self.library.get(self.current)['_archived'])
            if archived!=self.archived.isChecked():continue
            if query and query not in str(task).casefold() and query not in self.library.get(self.current)['title'].casefold():continue
            state=tr(STATES.get(task.get('status','open'),'Offen'))
            item=QListWidgetItem(task['title']+'\n'+tr(KINDS[task['kind']])+' · '+state); item.setData(Qt.UserRole,task['id']); self.task_list.addItem(item)
            if task['id']==self.scope:selected=item
        self.task_list.setCurrentItem(selected); self.task_list.blockSignals(False)
        self.new_task.setEnabled(bool(self.current) and not self.archived.isChecked())
        current=self.projects.get(self.scope) if selected else {}
        parent_archived=bool(current and (parents.get(current['parent'],{}).get('archived') or self.library.get(self.current)['_archived']))
        self.task_archive.setEnabled(bool(selected) and not parent_archived)
        self.task_archive.setText(tr('Wiederherstellen') if current.get('archived') else tr('Aufgabe archivieren'))
        self.task_heading.setText(tr('Aufgaben')+' · '+str(self.task_list.count()))

    def select_task(self,item,old):
        if item:self.safe(self.navigate,self.current,item.data(Qt.UserRole))

    def create_initiative(self):self.new_entry('initiative')
    def create_task(self):self.new_entry('task')

    def load_task_fields(self,value):
        from projects_data import KINDS,STATES
        task=bool(self.editor.draft_kind=='task' or self.scope and value.get('kind')!='initiative')
        self.tabs.setCurrentIndex(2 if task else 0)
        self.goal.setPlainText(value.get('goal','')); self.deep.setChecked(value.get('deep',False)); self.deep.setVisible(value.get('kind') in ('research','automation'))
        self.operation.setCurrentIndex(max(0,self.operation.findData(value.get('operation','analysis'))))
        interval=value.get('interval',86400)
        if self.interval.findData(interval)<0:self.interval.addItem(tr('Alle {0} Sekunden',interval),interval)
        self.interval.setCurrentIndex(self.interval.findData(interval))
        self.schedule.setChecked(value.get('enabled',False)); self.schedule_row.setVisible(value.get('kind') in ('research','analysis','automation'))
        self.operation.setVisible(value.get('kind')=='automation')
        self.schedule_status.setText(tr('Letzter Lauf: {0} · Nächster Lauf: {1}',self.stamp(value.get('last_run')),self.stamp(value.get('next_run')) if value.get('enabled') else tr('Pausiert')) if value.get('kind') in ('research','analysis','automation') else '')
        self.task_meta.setText((tr(KINDS.get(value.get('kind'),'Manuell'))+' · '+tr(STATES.get(value.get('status','open'),'Offen'))+'\n'+tr('Erstellt: {0} · Geändert: {1}',self.stamp(value.get('created')),self.stamp(value.get('updated')))) if task else '')
        self.dependencies.clear()
        if task:
            for other in self.projects.items(self.current):
                if other['kind']=='initiative' or other['id']==self.scope:continue
                item=QListWidgetItem(other['title']); item.setData(Qt.UserRole,other['id']); item.setFlags(item.flags()|Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked if other['id'] in value.get('depends',[]) else Qt.Unchecked); self.dependencies.addItem(item)
        self.dependencies.setVisible(bool(self.dependencies.count())); self.dependency_heading.setVisible(bool(self.dependencies.count()))
        self.start_task.setVisible(task and not self.editor.draft_kind and value.get('kind')!='manual'); self.complete_task.setVisible(task and not self.editor.draft_kind and value.get('kind')=='manual')
        self.complete_task.setText(tr('Wieder öffnen') if value.get('status')=='done' else tr('Als erledigt markieren'))
        self.load_runs()

    def load_runs(self):
        runs=self.projects.runs(self.scope) if self.scope else []
        if runs==getattr(self,'displayed_runs',None):return
        selected=(self.history.currentData() or {}).get('id'); self.displayed_runs=runs
        self.history.blockSignals(True); self.history.clear()
        from projects_data import STATES
        for run in runs:self.history.addItem(self.stamp(run['started'])+' · '+tr(STATES.get(run['status'],'Offen')),run)
        for index,run in enumerate(runs):
            if run['id']==selected:self.history.setCurrentIndex(index)
        self.history.blockSignals(False); self.show_run()

    def show_run(self,*_):
        run=self.history.currentData() or {}
        text=run.get('result','') or run.get('error','')
        if self.result.toPlainText()!=text:self.result.setPlainText(text)

    def show_sources(self):
        run=self.history.currentData() or {}; snapshot=run.get('snapshot',{})
        if not snapshot:raise ValueError(tr('Noch kein Ergebnis vorhanden.'))
        text=snapshot.get('title','')+'\n'+snapshot.get('goal','')+'\n'+self.stamp(snapshot.get('captured'))
        for source in snapshot.get('sources',[]):text+='\n\n'+source['title']+'\n'+source.get('path',source.get('url',''))+'\n'+source.get('revision','')+'\n'+source.get('text','')
        for stage in run.get('stages',[]):
            text+='\n\n'+stage['title']+' · '+self.stamp(stage['finished'])+'\n'+stage['result']
            for source in stage.get('web_sources',[]):text+='\n\n'+str(source['input'])+'\n'+source['output']
        dialog=QDialog(self); dialog.setWindowTitle(tr('Auftrag, Quellen und Arbeitsschritte')); dialog.resize(760,650); layout=QVBoxLayout(dialog)
        editor=QPlainTextEdit(text); editor.setReadOnly(True); layout.addWidget(editor)
        buttons=QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons); dialog.exec()

    def complete(self):
        self.save(); value=self.projects.get(self.scope)
        self.projects.update(self.scope,status='open' if value.get('status')=='done' else 'done'); self.open_scope(self.scope)

    def archive_task(self):
        self.save(); self.projects.update(self.scope,archived=not self.projects.get(self.scope)['archived'],enabled=False); self.open_scope(self.initiative)

    def archive(self):
        if self.initiative:
            self.save(); key=self.initiative
            self.projects.update(key,archived=not self.projects.get(key)['archived'])
            for task in self.projects.items(self.current,key):self.projects.update(task['id'],enabled=False)
            self.open_scope('')
        else:
            self.save()
            if not self.current:return
            archived=not self.library.get(self.current)['_archived']
            if archived:
                for task in self.projects.items(self.current):
                    if task.get('enabled'):self.projects.update(task['id'],enabled=False)
            self.library.archive(self.current,archived); self.current=''; self.scope=''
            self.body.setEnabled(False);self.editor.hide();self.home.project_id='';self.home.room_id='';self.home.scope='';self.home.refresh();self.refresh()

    def run_task(self):
        self.save()
        if self.runner and self.runner.busy:raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
        if self.runner:self.runner.deleteLater()
        from projects_runner import Runner
        self.runner=Runner(self.projects,self); self.runner.status.connect(self.status.setText); self.runner.finished.connect(self.run_finished)
        self.runner.start(self.scope); self.cancel_button.show(); self.progress.show();self.editor.stop.setVisible(True)

    def begin(self,text):
        super().begin(text);self.task_pane.setEnabled(False);self.home.setEnabled(False)

    def end(self):
        super().end();self.task_pane.setEnabled(True);self.home.setEnabled(True)

    def run_finished(self,success,message):
        self.cancel_button.hide(); self.progress.hide(); self.editor.stop.hide();self.refresh_tasks(); self.load_runs()
        self.refresh_run_status()
        self.status.setText(tr('Ausführung beendet. Das Ergebnis bleibt an der Aufgabe.') if success else message)
        if self.scope==self.runner.task:
            for index in range(self.history.count()):
                if self.history.itemData(index)['id']==self.runner.run:self.history.setCurrentIndex(index)
            self.tabs.setCurrentIndex(3)

    def cancel(self):
        if self.runner and self.runner.busy:self.runner.cancel()
        super().cancel()

    def poll_runs(self):
        with self.library.connect() as db:
            revision=tuple(tuple(r) for r in db.execute('SELECT id,updated,archived FROM records UNION ALL SELECT id,updated,archived FROM project_items ORDER BY id'))
        if revision!=getattr(self,'tree_revision',None):
            self.refresh(); self.tree_revision=revision
        if not self.current or self.editor.draft_kind:return
        if not self.editor.dirty() and self.editor_fields()==self.loaded_fields:
            record=self.projects.get(self.scope) if self.scope else self.library.get(self.current)
            if any(record.get(key)!=self.loaded_record.get(key) for key in self.loaded_fields):
                self.loading=True
                page=self.tabs.currentIndex()
                try:self.load_fields(record);self.tabs.setCurrentIndex(page)
                finally:self.loading=False
        self.refresh_tasks()
        self.refresh_run_status()
        if not self.save_timer.isActive():self.load_runs()

    def refresh_run_status(self):
        if not self.scope:return
        from projects_data import KINDS,STATES
        value=self.projects.get(self.scope)
        if value['kind']=='initiative':return
        self.task_meta.setText(tr(KINDS[value['kind']])+' · '+tr(STATES.get(value.get('status','open'),'Offen'))+'\n'+tr('Erstellt: {0} · Geändert: {1}',self.stamp(value.get('created')),self.stamp(value.get('updated'))))
        if not self.editor.dirty():self.schedule.setChecked(value.get('enabled',False))
        self.schedule_status.setText(tr('Letzter Lauf: {0} · Nächster Lauf: {1}',self.stamp(value.get('last_run')),self.stamp(value.get('next_run')) if value.get('enabled') else tr('Pausiert')) if value['kind'] in ('research','analysis','automation') else '')

    def save_result(self):
        run=self.history.currentData() or {}
        if not run.get('result'):raise ValueError(tr('Noch kein Ergebnis vorhanden.'))
        from interop_ui import reviewed_send
        payload=self.interop_payload(); payload['text']=run['result']; payload['paths']=[]; payload['items']=[]
        reviewed_send(self,payload,'wissen.import')

    def backup(self):
        self.save()
        from interop_ui import reviewed_send
        reviewed_send(self,self.interop_payload(),'vault.sources')

    def material_menu(self,position):
        item=self.resources.itemAt(position)
        if not item:return
        self.resources.setCurrentItem(item); value=item.data(Qt.UserRole); menu=QMenu(self)
        menu.addAction(tr('Öffnen'),lambda:self.safe(self.open_resource))
        if value.get('kind')=='file' and Path(value['target']).is_file():
            from interop_sources import from_paths
            from interop_ui import reviewed_send
            menu.addAction(tr('In Lumen Reader lesen'),lambda:self.safe(reviewed_send,self,from_paths([value['target']]),'reader.import'))
        menu.addAction(tr('Verknüpfung entfernen'),lambda:self.safe(self.remove_resource)); menu.exec(self.resources.mapToGlobal(position))

    def open_legacy_question(self,value):
        from interop_parts import match_part
        questions=self.library.get(self.current).get('questions',[])
        index=match_part('question',value,questions)
        for item in self.projects.items(self.current)+self.projects.items(self.current,archived=True):
            if item.get('legacy_question')==index and item.get('legacy_text')==questions[index]['text']:
                self.open_scope(item['id']);return
        raise ValueError(tr('Die verknüpfte Aufgabe ist nicht mehr vorhanden.'))

    def interop_payload(self):
        from interop_sources import _ref,_payload,_resource
        source=_ref('workbench',self.current,self.title.text())
        if self.scope:source['position']=dict(part='item:'+self.scope)
        if self.tabs.currentIndex()==3 and self.history.currentData():
            return _payload(source,self.result.textCursor().selectedText() or self.result.toPlainText())
        materials=[_resource(self.resources.item(i).data(Qt.UserRole)) for i in range(self.resources.count())]
        if self.tabs.currentIndex()==1 and self.resources.currentItem():
            if not self.scope:
                from interop_parts import capture_part
                source['position']=dict(part=capture_part(self,'resource',self.resources.currentRow()))
            materials=[_resource(self.resources.currentItem().data(Qt.UserRole))]
            value=materials[0]
            return _payload(source,value['title'],paths=[value['path']],items=materials,url=value['url'])
        selected=self.notes.textCursor().selectedText()
        if selected:return _payload(source,selected)
        text=self.notes.toPlainText()
        if not self.scope:
            text+='\n\n'+'\n'.join(('- [x] ' if q.get('done') else '- [ ] ')+q['text'] for q in self.library.get(self.current).get('questions',[]))
        if self.scope and self.projects.get(self.scope)['kind']!='initiative':text=self.goal.toPlainText()+'\n\n'+text
        return _payload(source,text,paths=[v['path'] for v in materials],items=materials)

    def closeEvent(self,event):
        if hasattr(self,'home') and self.home.prompt.text().strip():
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(self,tr('Gesprächsentwurf behalten?'),tr('Der Entwurf im Projekt ist noch nicht in Lumen geöffnet. Trotzdem schließen?'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:
                event.ignore();return
        if not self.workplace.can_close() or self.workplace.busy or not self.automations.can_close():
            self.status.setText(tr('Bitte den laufenden Vorgang abschließen.')); event.ignore(); return
        if self.room_files is not None and not self.room_files.close(): event.ignore(); return
        if getattr(self,'project_sync_job',None):
            self.sync_close_requested=True;event.ignore();return
        if self.runner and self.runner.busy:
            self.runner.cancel(); self.status.setText(tr('Abbruch läuft. Danach kann das Fenster geschlossen werden.')); event.ignore();return
        if not self.editor.allow_leave():event.ignore();return
        super().closeEvent(event)
        if event.isAccepted():
            self.home.timer.stop()
            self.poll_timer.stop(); self.workplace.shutdown(); self.automations.shutdown()

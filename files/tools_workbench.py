"""Projects, initiatives, tasks and their material in a native three-column view."""
from lumen_i18n import tr
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem,
    QInputDialog, QFileDialog, QTabWidget, QWidget, QVBoxLayout, QTreeWidget,
    QTreeWidgetItem, QComboBox, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QMenu)
from tools_data import web_url
from tools_ui import ToolWindow, button, label, row, open_path


class Workbench(ToolWindow):
    def __init__(self,root=None):
        super().__init__('workbench',tr('Lumen Projekte'),tr('Projekte, Vorhaben und ihre nächsten Schritte.'),'folder-development',root)
        from projects_data import Projects
        self.projects=Projects(self.library); self.scope=''; self.initiative=''; self.runner=None
        from projects_runner import recover
        recover(self.projects)
        self.add_button.setText(tr('Projekt anlegen'))
        self.title=QLineEdit(); self.title.setPlaceholderText(tr('Lege dein erstes Projekt an')); self.title.setAccessibleName(tr('Projektname')); self.title.textEdited.connect(self.edited)
        self.content.addWidget(self.title)
        self.tabs=QTabWidget(); self.content.addWidget(self.tabs,1)
        self.tabs.setStyleSheet('QTabBar::tab { min-width: 0; padding: 8px 12px; }')
        notes_page=QWidget(); notes_layout=QVBoxLayout(notes_page); notes_layout.setContentsMargins(0,12,0,0)
        notes_layout.addWidget(label(tr('Gedanken & Notizen'),'heading'))
        self.notes=QPlainTextEdit(); self.notes.setAccessibleName(tr('Projektnotizen')); self.notes.setPlaceholderText(tr('Worum geht es? Was ist der nächste Schritt?\n\nDeine Notizen werden automatisch gespeichert.')); self.notes.textChanged.connect(self.edited); notes_layout.addWidget(self.notes,2)
        self.legacy_heading=label(tr('Offene Fragen'),'heading'); notes_layout.addWidget(self.legacy_heading)
        self.questions=QListWidget(); self.questions.setObjectName('searchResults'); self.questions.setAccessibleName(tr('Offene Fragen')); self.questions.itemChanged.connect(self.edited); notes_layout.addWidget(self.questions,1)
        self.question=QLineEdit(); self.question.setPlaceholderText(tr('Neue Frage …')); self.question.setAccessibleName(tr('Neue Frage')); self.question.textEdited.connect(self.edited); self.question.returnPressed.connect(lambda:self.safe(self.add_question))
        self.legacy_controls=row(self.question,button(tr('Hinzufügen'),lambda:self.safe(self.add_question),'list-add'),button(tr('Entfernen'),lambda:self.safe(self.remove_question),'list-remove')); notes_layout.addWidget(self.legacy_controls)
        self.tabs.addTab(notes_page,tr('Notizen'))
        resources=QWidget(); resources_layout=QVBoxLayout(resources); resources_layout.setContentsMargins(0,12,0,0)
        resources_layout.addWidget(label(tr('Dateien & Webseiten'),'heading'))
        resources_layout.addWidget(label(tr('Dateien bleiben an ihrem Ort – auch auf eingebundenen Netzlaufwerken. Ein Doppelklick öffnet sie in ihrer Anwendung.'), 'muted'))
        self.resources=QListWidget(); self.resources.setObjectName('searchResults'); self.resources.setAccessibleName(tr('Projektmaterial')); self.resources.itemDoubleClicked.connect(lambda _:self.safe(self.open_resource)); resources_layout.addWidget(self.resources,1)
        resources_layout.addWidget(row(button(tr('Dateien'),lambda:self.safe(self.add_files),'document-open',True),button(tr('Ordner'),lambda:self.safe(self.add_folder),'folder'),
            button(tr('Webseite'),lambda:self.safe(self.add_link),'internet-web-browser'),button(tr('Öffnen'),lambda:self.safe(self.open_resource),'document-open'),button(tr('Entfernen'),lambda:self.safe(self.remove_resource),'list-remove')))
        self.tabs.addTab(resources,tr('Material'))
        self.content.addWidget(button(tr('Projektübersicht exportieren'),lambda:self.safe(self.export),'document-export'))
        self.setup_projects()
        self.body.setEnabled(False); self.refresh()
        from interop_workflow_ui import install_menu
        install_menu(self)
        self.server_material=QListWidget();self.server_material.setAccessibleName(tr('Material auf Lumen Server'));self.server_material.setMaximumHeight(110);self.server_material.hide();self.content.addWidget(self.server_material)
        self.server_material.itemDoubleClicked.connect(lambda _:self.safe(self.open_server_material))
        from projects_sync_ui import install
        install(self)

    def create(self):
        title,ok=QInputDialog.getText(self,tr('Neues Projekt'),tr('Projektname'))
        if ok and title.strip():
            self.save()
            from projects_sync import read_state,configure
            location=tr('Lokal')
            if read_state(self.library)['enabled']:
                location,ok=QInputDialog.getItem(self,tr('Neues Projekt'),tr('Speicherort'),[tr('Lumen Server'),tr('Lokal')],0,False)
                if not ok:return
            key=self.library.create(title,notes='',questions=[],resources=[])
            if location==tr('Lumen Server'):configure(self.library,True,key)
            self.focus_record(key)

    def load(self,r):
        self.scope=''; self.initiative=''
        self.projects.migrate(r['id'])
        self.load_fields(r); self.refresh_tasks(); self.refresh()

    def load_fields(self,r):
        from interop_paths import update_window
        self.interop_path_revision=r.get('interop_path_revision',0)
        self.title.setText(r['title']); self.notes.setPlainText(r.get('notes','')); self.questions.clear(); self.resources.clear()
        for q in r.get('questions',[]):
            item=QListWidgetItem(q['text']); item.setFlags(item.flags()|Qt.ItemIsEditable|Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if q.get('done') else Qt.Unchecked); self.questions.addItem(item)
        for resource in r.get('resources',[]):
            item=QListWidgetItem(resource['title']+'\n'+resource['target']); item.setData(Qt.UserRole,resource); self.resources.addItem(item)
        self.question.setText(r.get('question_draft','')); self.status.setText(tr('Änderungen werden automatisch gespeichert · Dateien bleiben an ihrem Ort'))
        self.legacy_controls.setVisible(not self.scope and bool(r.get('question_draft')))
        update_window(self)
        self.load_task_fields(r)
        self.loaded_fields=self.editor_fields()
        owner=self.library.get(self.current)
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
        if self.scope:
            if self.projects.get(self.scope)['kind']!='initiative':
                value.update(goal=self.goal.toPlainText(),depends=[self.dependencies.item(i).data(Qt.UserRole) for i in range(self.dependencies.count()) if self.dependencies.item(i).checkState()==Qt.Checked],deep=self.deep.isChecked(),operation=self.operation.currentData(),interval=self.interval.currentData())
        else:value.update(questions=[dict(text=self.questions.item(i).text(),done=self.questions.item(i).checkState()==Qt.Checked) for i in range(self.questions.count())],question_draft=self.question.text())
        return value

    def save(self):
        super().save()
        if not self.current or self.loading: return
        from interop_paths import update_window
        update_window(self)
        fields=self.editor_fields(); changes={k:v for k,v in fields.items() if v!=self.loaded_fields.get(k)}
        if not changes:return
        if self.scope:self.projects.update(self.scope,expected_updated=self.loaded_updated if self.library.get(self.current).get('server_bound') else None,**changes)
        else:self.library.update(self.current,expected_updated=self.loaded_updated if self.library.get(self.current).get('server_bound') else None,**changes)
        with self.library.connect() as db:
            table='project_items' if self.scope else 'records'
            self.loaded_updated=str(db.execute('SELECT updated FROM '+table+' WHERE id=?',(self.scope or self.current,)).fetchone()['updated'])
        self.loaded_fields=fields
        self.status.setText(tr('Lokal gespeichert')); self.refresh(); self.refresh_run_status()

    def add_question(self):
        text=self.question.text().strip()
        if not text: return
        item=QListWidgetItem(text); item.setFlags(item.flags()|Qt.ItemIsEditable|Qt.ItemIsUserCheckable); item.setCheckState(Qt.Unchecked)
        self.questions.addItem(item); self.question.clear(); self.save()

    def remove_question(self):
        i=self.questions.currentRow()
        if i>=0: self.questions.takeItem(i); self.save()

    def add_resource(self,kind,target,title):
        from interop_paths import update_window
        update_window(self)
        if any(self.resources.item(i).data(Qt.UserRole)['target']==target for i in range(self.resources.count())): return
        item=QListWidgetItem(title+'\n'+target); item.setData(Qt.UserRole,dict(kind=kind,target=target,title=title)); self.resources.addItem(item); self.save()

    def add_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,tr('Dateien verknüpfen'),str(Path.home()))
        for path in paths: self.add_resource('file',path,Path(path).name)

    def add_folder(self):
        path=QFileDialog.getExistingDirectory(self,tr('Ordner verknüpfen'),str(Path.home()))
        if path: self.add_resource('file',path,Path(path).name)

    def add_link(self):
        value,ok=QInputDialog.getText(self,tr('Webseite verknüpfen'),tr('Webadresse'))
        if ok and value.strip():
            address=web_url(value); self.add_resource('url',address,QUrl(address).host())

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
        if i>=0: self.resources.takeItem(i); self.save(); self.status.setText(tr('Verknüpfung entfernt. Die Datei bleibt erhalten.'))

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
        old=self.entries; old.currentItemChanged.disconnect(self.select)
        from interop_drag import EntryTree
        self.entries=EntryTree(self); self.entries.setHeaderHidden(True); self.entries.setAccessibleName(tr('Projekte und Vorhaben'))
        self.sidebar.layout().replaceWidget(old,self.entries); old.deleteLater()
        self.entries.currentItemChanged.connect(self.select)
        self.sidebar.layout().insertWidget(2,button(tr('Vorhaben anlegen'),lambda:self.safe(self.create_initiative),'list-add'))
        self.search.setPlaceholderText(tr('Projekte und Aufgaben suchen …'))
        middle=QWidget(); self.task_pane=middle; layout=QVBoxLayout(middle); layout.setContentsMargins(8,0,8,0)
        self.task_heading=label(tr('Aufgaben'),'heading'); layout.addWidget(self.task_heading)
        self.new_task=button(tr('Aufgabe anlegen'),lambda:self.safe(self.create_task),'list-add',True); layout.addWidget(self.new_task)
        from interop_drag import EntryList
        self.task_list=EntryList(self); self.task_list.setObjectName('searchResults'); self.task_list.setAccessibleName(tr('Aufgaben'))
        self.task_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.task_list.setTextElideMode(Qt.ElideRight)
        self.task_list.currentItemChanged.connect(self.select_task); layout.addWidget(self.task_list,1)
        self.task_archive=button(tr('Aufgabe archivieren'),lambda:self.safe(self.archive_task),'archive-insert'); layout.addWidget(self.task_archive)
        self.split.insertWidget(1,middle); self.split.setSizes([240,300,590]); self.resize(1320,850)
        self.questions.hide(); self.legacy_heading.hide(); self.legacy_controls.hide()
        detail=QWidget(); form=QVBoxLayout(detail)
        self.task_meta=label('','muted'); form.addWidget(self.task_meta)
        self.goal=QPlainTextEdit(); self.goal.setPlaceholderText(tr('Was soll am Ende vorliegen?')); self.goal.setAccessibleName(tr('Gewünschtes Ergebnis')); self.goal.setMaximumHeight(100); self.goal.textChanged.connect(self.edited)
        form.addWidget(label(tr('Gewünschtes Ergebnis'),'heading')); form.addWidget(self.goal)
        form.addWidget(label(tr('Notizen und Material des Projekts und Vorhabens werden mitverwendet.'),'muted'))
        self.deep=QCheckBox('Deep Research'); self.deep.setToolTip(tr('Deep Research: recherchieren, gegenprüfen, zusammenfassen')); self.deep.toggled.connect(self.edited); form.addWidget(self.deep)
        self.operation=QComboBox(); self.operation.addItem(tr('Analyse'),'analysis'); self.operation.addItem(tr('Recherche'),'research'); self.operation.currentIndexChanged.connect(self.edited)
        self.interval=QComboBox()
        for text,seconds in [('Alle 60 Minuten',3600),('Alle 24 Stunden',86400),('Alle 7 Tage',604800)]: self.interval.addItem(tr(text),seconds)
        self.interval.currentIndexChanged.connect(self.edited)
        self.schedule=QCheckBox(tr('Automatisch ausführen')); self.schedule.clicked.connect(lambda enabled:self.safe(self.set_schedule,enabled))
        self.schedule_row=QWidget(); schedule_layout=QVBoxLayout(self.schedule_row); schedule_layout.setContentsMargins(0,0,0,0)
        schedule_layout.addWidget(row(self.operation,self.interval)); schedule_layout.addWidget(self.schedule); form.addWidget(self.schedule_row)
        self.schedule_status=label('','muted'); form.addWidget(self.schedule_status)
        self.dependencies=QListWidget(); self.dependencies.setMaximumHeight(95); self.dependencies.setAccessibleName(tr('Vorausgesetzte Aufgaben')); self.dependencies.itemChanged.connect(self.edited)
        self.dependency_heading=label(tr('Nach diesen Aufgaben starten'),'heading'); form.addWidget(self.dependency_heading); form.addWidget(self.dependencies)
        self.start_task=button(tr('Jetzt ausführen'),lambda:self.safe(self.run_task),'media-playback-start',True)
        self.complete_task=button(tr('Als erledigt markieren'),lambda:self.safe(self.complete),'dialog-ok')
        form.addWidget(row(self.start_task,self.complete_task))
        self.tabs.addTab(detail,tr('Aufgabe'))
        results=QWidget(); results_layout=QVBoxLayout(results)
        self.history=QComboBox(); self.history.setAccessibleName(tr('Ausführungsverlauf')); self.history.currentIndexChanged.connect(self.show_run); results_layout.addWidget(self.history)
        self.result=QPlainTextEdit(); self.result.setReadOnly(True); self.result.setAccessibleName(tr('Ergebnis')); self.result.setPlaceholderText(tr('Hier erscheint das Ergebnis mit Zeitpunkt und verwendeten Quellen.')); results_layout.addWidget(self.result,1)
        results_layout.addWidget(button(tr('Auftrag, Quellen und Arbeitsschritte ansehen'),lambda:self.safe(self.show_sources),'document-open'))
        results_layout.addWidget(button(tr('Ergebnis in Lumen Wissen speichern'),lambda:self.safe(self.save_result),'document-save'))
        results_layout.addWidget(button(tr('Mit Lumen Vault sichern'),lambda:self.safe(self.backup),'document-save'))
        self.tabs.addTab(results,tr('Ergebnisse'))
        form.addStretch(1)
        self.resources.setContextMenuPolicy(Qt.CustomContextMenu); self.resources.customContextMenuRequested.connect(self.material_menu)
        self.poll_timer=QTimer(self); self.poll_timer.setInterval(5000); self.poll_timer.timeout.connect(self.poll_runs); self.poll_timer.start()

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
        self.save(); archive=self.archived.isChecked()
        if project!=self.current: self.focus_record(project)
        self.archived.setChecked(archive)
        self.open_scope(scope)

    def open_scope(self,key=''):
        value=self.projects.get(key) if key else self.library.get(self.current)
        if key and value['project']!=self.current: raise ValueError(tr('Dieser Eintrag gehört zu einem anderen Projekt.'))
        self.scope=key
        self.initiative=(key if value['kind']=='initiative' else value['parent']) if key else ''
        if key and (value['archived'] or (value['kind']!='initiative' and self.projects.get(value['parent'])['archived'])):
            self.archived.setChecked(True)
        self.loading=True
        try:self.load_fields(value)
        finally:self.loading=False
        self.body.setEnabled(True); self.refresh()

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

    def create_initiative(self):
        if not self.current: self.create()
        if not self.current:return
        title,ok=QInputDialog.getText(self,tr('Neues Vorhaben'),tr('Was möchtest du erreichen?'))
        if ok and title.strip():
            self.save(); self.open_scope(self.projects.add(self.current,'',title,'initiative'))

    def create_task(self):
        if not self.current:return
        self.save(); owners=self.projects.items(self.current,'')
        if not owners:
            self.create_initiative(); owners=self.projects.items(self.current,'')
        if not owners:return
        from projects_data import KINDS
        dialog=QDialog(self); dialog.setWindowTitle(tr('Neue Aufgabe')); form=QFormLayout(dialog)
        title=QLineEdit(); title.setAccessibleName(tr('Aufgabenname')); form.addRow(tr('Aufgabe'),title)
        owner=QComboBox()
        for item in owners:owner.addItem(item['title'],item['id'])
        owner.setCurrentIndex(max(0,owner.findData(self.initiative))); form.addRow(tr('Vorhaben'),owner)
        kind=QComboBox()
        for key,text in KINDS.items():kind.addItem(tr(text),key)
        form.addRow(tr('Art'),kind)
        goal=QPlainTextEdit(); goal.setPlaceholderText(tr('Was soll am Ende vorliegen?')); form.addRow(tr('Gewünschtes Ergebnis'),goal)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec()==QDialog.Accepted:
            self.open_scope(self.projects.add(self.current,owner.currentData(),title.text(),kind.currentData(),goal=goal.toPlainText()))

    def load_task_fields(self,value):
        from projects_data import KINDS,STATES
        task=bool(self.scope and value.get('kind')!='initiative'); self.tabs.setTabVisible(2,task); self.tabs.setTabVisible(3,task)
        self.tabs.setCurrentIndex(2 if task else 0)
        self.goal.setPlainText(value.get('goal','')); self.deep.setChecked(value.get('deep',False)); self.deep.setVisible(value.get('kind') in ('research','automation'))
        self.operation.setCurrentIndex(max(0,self.operation.findData(value.get('operation','analysis')))); self.interval.setCurrentIndex(max(0,self.interval.findData(value.get('interval',86400))))
        self.schedule.setChecked(value.get('enabled',False)); self.schedule_row.setVisible(value.get('kind')=='automation')
        self.schedule_status.setText(tr('Letzter Lauf: {0} · Nächster Lauf: {1}',self.stamp(value.get('last_run')),self.stamp(value.get('next_run')) if value.get('enabled') else tr('Pausiert')) if value.get('kind')=='automation' else '')
        self.task_meta.setText((tr(KINDS.get(value.get('kind'),'Manuell'))+' · '+tr(STATES.get(value.get('status','open'),'Offen'))+'\n'+tr('Erstellt: {0} · Geändert: {1}',self.stamp(value.get('created')),self.stamp(value.get('updated')))) if task else '')
        self.dependencies.clear()
        if task:
            for other in self.projects.items(self.current):
                if other['kind']=='initiative' or other['id']==self.scope:continue
                item=QListWidgetItem(other['title']); item.setData(Qt.UserRole,other['id']); item.setFlags(item.flags()|Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked if other['id'] in value.get('depends',[]) else Qt.Unchecked); self.dependencies.addItem(item)
        self.dependencies.setVisible(bool(self.dependencies.count())); self.dependency_heading.setVisible(bool(self.dependencies.count()))
        self.start_task.setVisible(task and value.get('kind')!='manual'); self.complete_task.setVisible(task and value.get('kind')=='manual')
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
                    if task['kind']=='automation':self.projects.update(task['id'],enabled=False)
            self.library.archive(self.current,archived); self.current=''; self.scope=''
            self.body.setEnabled(False); self.refresh()

    def run_task(self):
        self.save()
        if self.runner and self.runner.busy:raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
        if self.runner:self.runner.deleteLater()
        from projects_runner import Runner
        self.runner=Runner(self.projects,self); self.runner.status.connect(self.status.setText); self.runner.finished.connect(self.run_finished)
        self.runner.start(self.scope); self.cancel_button.show(); self.progress.show()

    def begin(self,text):
        super().begin(text); self.task_pane.setEnabled(False)

    def end(self):
        super().end(); self.task_pane.setEnabled(True)

    def run_finished(self,success,message):
        self.cancel_button.hide(); self.progress.hide(); self.refresh_tasks(); self.load_runs()
        self.refresh_run_status()
        self.status.setText(tr('Ausführung beendet. Das Ergebnis bleibt an der Aufgabe.') if success else message)
        if self.scope==self.runner.task:
            for index in range(self.history.count()):
                if self.history.itemData(index)['id']==self.runner.run:self.history.setCurrentIndex(index)
            self.tabs.setCurrentIndex(3)

    def cancel(self):
        if self.runner and self.runner.busy:self.runner.cancel()
        super().cancel()

    def set_schedule(self,enabled):
        self.save()
        if self.library.get(self.current).get('server_bound'):
            raise ValueError(tr('Zeitpläne dieses Projekts werden auf Lumen Server verwaltet.'))
        from projects_runner import install_timer
        try:
            if enabled:install_timer(self.library.root.parent)
            import time
            self.projects.update(self.scope,enabled=enabled,next_run=time.time()+int(self.interval.currentData()))
        finally:
            self.schedule.setChecked(self.projects.get(self.scope).get('enabled',False))
        self.open_scope(self.scope)

    def poll_runs(self):
        with self.library.connect() as db:
            revision=tuple(tuple(r) for r in db.execute('SELECT id,updated,archived FROM records UNION ALL SELECT id,updated,archived FROM project_items ORDER BY id'))
        if revision!=getattr(self,'tree_revision',None):
            self.refresh(); self.tree_revision=revision
        if not self.current:return
        if not self.save_timer.isActive() and self.editor_fields()==self.loaded_fields:
            record=self.projects.get(self.scope) if self.scope else self.library.get(self.current)
            if any(record.get(key)!=self.loaded_record.get(key) for key in self.loaded_fields):
                self.loading=True
                try:self.load_fields(record)
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
        self.schedule.setChecked(value.get('enabled',False))
        self.schedule_status.setText(tr('Letzter Lauf: {0} · Nächster Lauf: {1}',self.stamp(value.get('last_run')),self.stamp(value.get('next_run')) if value.get('enabled') else tr('Pausiert')) if value['kind']=='automation' else '')

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

    def interop_payload(self):
        from interop_sources import _ref,_payload,_resource
        source=_ref('workbench',self.current,self.title.text())
        if self.scope:source['position']=dict(part='item:'+self.scope)
        if self.tabs.currentIndex()==3 and self.history.currentData():
            return _payload(source,self.result.textCursor().selectedText() or self.result.toPlainText())
        materials=[_resource(self.resources.item(i).data(Qt.UserRole)) for i in range(self.resources.count())]
        if self.tabs.currentIndex()==1 and self.resources.currentItem():
            materials=[_resource(self.resources.currentItem().data(Qt.UserRole))]
            value=materials[0]
            return _payload(source,value['title'],paths=[value['path']],items=materials,url=value['url'])
        selected=self.notes.textCursor().selectedText()
        if selected:return _payload(source,selected)
        text=self.notes.toPlainText()
        if self.scope and self.projects.get(self.scope)['kind']!='initiative':text=self.goal.toPlainText()+'\n\n'+text
        return _payload(source,text,paths=[v['path'] for v in materials],items=materials)

    def closeEvent(self,event):
        if getattr(self,'project_sync_job',None):
            self.sync_close_requested=True;event.ignore();return
        if self.runner and self.runner.busy:
            self.runner.cancel(); self.status.setText(tr('Abbruch läuft. Danach kann das Fenster geschlossen werden.')); event.ignore();return
        super().closeEvent(event)
        if event.isAccepted():self.poll_timer.stop()

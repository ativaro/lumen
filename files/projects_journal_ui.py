"""Project journal composed from existing records, references and execution history."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QPlainTextEdit, QMenu, QTabBar, QPushButton, QDialog, QComboBox, QDialogButtonBox
from lumen_i18n import tr
from tools_ui import label, button, row
from projects_data import KINDS, STATES



STYLE = """
QWidget#projectJournal QLabel#journalTitle { font-size:24px;font-weight:500;padding:7px 0 18px; }
QWidget#projectJournal QLabel#journalEyebrow { color:palette(highlight);font-size:10px;letter-spacing:1px; }
QWidget#projectJournal QLabel#journalSection { font-size:13px;font-weight:600; }
QWidget#projectJournal QLabel#journalMuted { color:palette(placeholder-text);font-size:12px; }
QWidget#projectJournal QLabel#journalDescription { color:palette(placeholder-text);font-size:13px; }
QWidget#projectJournal QLabel#journalSmall { color:palette(placeholder-text);font-size:11px; }
QWidget#projectJournal QLabel#journalSummary { font-size:24px;font-weight:400; }
QWidget#projectJournal QTabBar { border-bottom:1px solid palette(mid); }
QWidget#projectJournal QTabBar::tab { color:palette(placeholder-text);background:transparent;border:0;border-radius:0;border-bottom:2px solid transparent;padding:12px 0;margin-right:22px;font-size:12px; }
QWidget#projectJournal QTabBar::tab:selected { color:palette(window-text);border-bottom-color:palette(highlight); }
QWidget#projectJournal QTabBar::tab:focus { color:palette(highlight); }
QWidget#projectJournal QWidget#journalComposer { background:palette(alternate-base);border:1px solid palette(highlight);border-radius:10px; }
QWidget#projectJournal QPlainTextEdit { background:transparent;color:palette(window-text);border:0;padding:0;font-size:13px; }
QWidget#projectJournal QWidget#journalSectionBlock { border-top:1px solid palette(mid); }
QWidget#projectJournal QWidget#journalOverview { border-bottom:1px solid palette(mid); }
QWidget#projectJournal QWidget#journalTimeline { border-left:1px solid palette(mid); }
QWidget#projectJournal QPushButton#journalAction { background:transparent;border:1px solid palette(mid);border-radius:7px;padding:8px 10px;font-size:11px; }
QWidget#projectJournal QPushButton#journalIntegration { background:transparent;border:0;border-radius:7px;text-align:left;padding:8px 0;font-size:12px; }
QWidget#projectJournal QPushButton#journalEntry { background:transparent;border:0;padding:0;text-align:left;min-height:46px; }
QWidget#projectJournal QLabel#journalEntryTitle { font-size:16px;font-weight:500; }
QWidget#projectJournal QPushButton:hover,QWidget#projectJournal QPushButton:focus { color:palette(highlight);border-color:palette(highlight); }
QWidget#projectJournal QScrollArea,QWidget#projectJournal QWidget#journalPage { background:palette(window);border:0; }
"""


def question_prompt(project, question):
    return (tr('Frage zum Lumen-Projekt') + ' ' + project + ':\n\n' + question.strip() + '\n\n' +
            tr('Durchsuche verknüpfte lokale Ordner mit lumen_project_search und nenne Suchgrenzen. ') + tr('Lies das Projekt über die Projektwerkzeuge. Nutze zugeordnete Quellen nur soweit sie zugänglich sind, nenne verwendete Belege und kennzeichne nicht gelesene oder fehlende Inhalte. Starte oder ändere keine Aufgaben allein durch diese Frage.'))


class ProjectJournal(QWidget):
    VIEWS = [('journal', 'Projektjournal'), ('material', 'Quellen'), ('conversations', 'Gespräche'), ('results', 'Analysen & Recherchen'), ('tasks', 'Aufgaben')]

    ASSIGNABLE = {'journal': {'file','folder','url','note','chat','task'}, 'material': {'file','folder','url','note'}, 'conversations': {'chat'}, 'results': {'analysis','research'}, 'tasks': {'task'}}

    def __init__(self, window):
        super().__init__(window)
        self.window=window;self.project='';self.drafts={};self.view='journal';self.record=None
        self.setObjectName('projectJournal')
        self.setStyleSheet(STYLE)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,12,0,0);layout.setSpacing(0)
        layout.addWidget(label(tr('LUMEN PROJEKTE'),'journalEyebrow'))
        self.title=label('','journalTitle')
        self.edit=button(tr('Bearbeiten'),lambda:window.safe(self.edit_project));self.edit.setObjectName('journalAction')
        heading=row(self.title,self.edit);heading.layout().setStretch(0,1);layout.addWidget(heading)
        self.archive=label(tr('Archiviert – Originalinhalte bleiben erhalten.'),'journalMuted');layout.addWidget(self.archive);self.archive.hide()
        self.tabs=QTabBar();self.tabs.setAccessibleName(tr('Projektansichten'));self.tabs.setExpanding(False);self.tabs.setDrawBase(False);self.tabs.setUsesScrollButtons(True);self.tabs.setMinimumWidth(0)
        for key,title in self.VIEWS:self.tabs.addTab(tr(title).replace('&','&&'))
        self.tabs.currentChanged.connect(self.change_view);layout.addWidget(self.tabs);layout.addSpacing(26)
        scroll=QScrollArea();self.scroll=scroll;scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);scroll.setAccessibleName(tr('Projektjournal'));layout.addWidget(scroll,1)
        self.page=QWidget();self.page.setObjectName('journalPage');self.page.setAttribute(Qt.WA_StyledBackground);scroll.setWidget(self.page)
        self.grid=QGridLayout(self.page);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(28)
        self.main=QWidget();self.main_box=QVBoxLayout(self.main);self.main_box.setContentsMargins(0,0,0,0);self.main_box.setSpacing(0)
        self.side=QWidget();self.side.setObjectName('journalAside');self.side.setAttribute(Qt.WA_StyledBackground)
        side=QVBoxLayout(self.side);side.setContentsMargins(24,0,0,0);side.setSpacing(12);self.side_box=side
        self.grid.addWidget(self.main,0,0);self.grid.addWidget(self.side,0,1);self.grid.setColumnStretch(0,1)
        side.addWidget(label(tr('Weiterdenken mit Lumen'),'journalSection'))
        self.question_hint=label('','journalMuted');side.addWidget(self.question_hint)
        composer=QWidget();composer.setObjectName('journalComposer');composer.setAttribute(Qt.WA_StyledBackground)
        compose=QVBoxLayout(composer);compose.setContentsMargins(12,12,12,12);compose.setSpacing(9)
        self.question=QPlainTextEdit();self.question.setAccessibleName(tr('Frage zum Projekt'));self.question.setPlaceholderText(tr('Was möchtest du über dein Projekt wissen?'));self.question.setFixedHeight(100)
        self.question.textChanged.connect(self.keep_draft);compose.addWidget(self.question)
        self.ask_button=button(tr('In Lumen öffnen'),lambda:window.safe(self.ask),'go-up');self.ask_button.setObjectName('journalAction');compose.addWidget(self.ask_button,0,Qt.AlignRight)
        side.addWidget(composer)
        integrations=QWidget();integrations.setObjectName('journalSectionBlock');integrations.setAttribute(Qt.WA_StyledBackground)
        add=QVBoxLayout(integrations);add.setContentsMargins(0,21,0,0);add.setSpacing(8)
        add.addWidget(label(tr('Aus Lumen hinzufügen'),'journalSection'));add.addWidget(label(tr('Originale und ihre Freigaben bleiben erhalten.'),'journalMuted'))
        self.add_controls=[];self.context_controls=[]
        for kind,title,fn,icon in [('file','Lumen Drive · Dateien',self.add_files,'document-open'),('note','Lumen Notes · Notizen',self.add_note,'document-new'),('chat','Lumen · Gespräche',lambda:self.pick_reference('chat'),'dialog-messages')]:
            control=button(tr(title),lambda _checked=False,fn=fn:window.safe(fn),icon);control.setObjectName('journalIntegration');self.add_controls.append(control);add.addWidget(control);self.context_controls.append((control,{kind}))
        self.add_source=button(tr('Inhalt zuordnen'),lambda:window.safe(self.pick_content),'insert-link');self.add_source.setObjectName('journalAction');self.source_actions=[];self.add_controls.append(self.add_source)
        for kind,title,fn in [('file','Dateien hinzufügen',self.add_files),('folder','Ordner verknüpfen',self.add_folder),('url','Weblink hinzufügen',self.add_link),('note','Lumen Notes · Notiz zuordnen',self.add_note),('chat','Gespräch zuordnen',lambda:self.pick_reference('chat')),('task','Auftrag zuordnen',lambda:self.pick_reference('task')),('analysis','Analyse planen',lambda:self.plan_result('analysis')),('research','Recherche planen',lambda:self.plan_result('research'))]:
            action=QAction(tr(title),self);action.triggered.connect(lambda _checked=False,fn=fn:window.safe(fn));self.source_actions.append(action);action.setData(kind);self.add_controls.append(action);self.context_controls.append((action,{kind}))
        more=button(tr('Weitere Aktionen'),lambda:None);more.setObjectName('journalIntegration');menu=QMenu(more);more.setMenu(menu);add.addWidget(more)
        for views,title,fn in [({'journal'},'Vorhaben anlegen',window.create_initiative),({'journal','tasks'},'Aufgabe planen',window.create_task),({'journal','tasks','results'},'Analyse planen',lambda:window.create_task('analysis')),({'journal','tasks','results'},'Recherche planen',lambda:window.create_task('research')),({'journal','tasks'},'Ablauf zuordnen',lambda:window.home.attach_flow())]:
            action=menu.addAction(tr(title),lambda _checked=False,fn=fn:window.safe(fn));self.add_controls.append(action);action.setData(views)
        self.more_menu=menu
        menu.addSeparator()
        source_action=menu.addAction(tr('Quelle hinzufügen'),lambda:window.safe(self.add_files));self.add_controls.append(source_action);self.context_controls.append((source_action,{'file'}))
        self.project_archive=menu.addAction(tr('Projekt archivieren'),lambda:window.safe(self.archive_project))
        menu.addAction(tr('Gespräche und Aufträge'),lambda:window.home.references.setVisible(not window.home.references.isVisible()))
        side.addWidget(integrations)
        next_section=QWidget();next_section.setObjectName('journalSectionBlock');next_section.setAttribute(Qt.WA_StyledBackground)
        pending=QVBoxLayout(next_section);pending.setContentsMargins(0,21,0,0);pending.setSpacing(12)
        pending.addWidget(label(tr('Offene Aufgaben'),'journalSection'))
        self.next=QWidget();self.next_box=QVBoxLayout(self.next);self.next_box.setContentsMargins(0,0,0,0);self.next_box.setSpacing(8);pending.addWidget(self.next)
        all_tasks=button(tr('Alle zugeordneten Aufgaben ansehen'),lambda:self.tabs.setCurrentIndex(4));all_tasks.setObjectName('journalIntegration');pending.addWidget(all_tasks)
        side.addWidget(next_section);side.addStretch(1)
        self.reflow()

    def archive_project(self):
        if self.window.home.plan(scope=''):
            self.window.archive();self.window.editor.hide()

    def edit_project(self):
        from project_dialogs import open_dialog
        return open_dialog(self.window)

    def pick_content(self):
        if self.view=='material':
            from project_dialogs import open_dialog
            return open_dialog(self.window,'file')
        if self.readonly:raise ValueError(tr('Dieses Projekt ist schreibgeschützt.'))
        project,view=self.project,self.view
        dialog=QDialog(self);self.source_picker=dialog;dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowTitle(tr('Lumen Projekte · Inhalt zuordnen'));dialog.setMinimumWidth(440)
        box=QVBoxLayout(dialog);box.setContentsMargins(24,24,24,24);box.setSpacing(16)
        box.addWidget(label(tr('Inhalt zuordnen'),'heading'));box.addWidget(label(tr('Art'),'muted'))
        choice=QComboBox();choice.setAccessibleName(tr('Art'));box.addWidget(choice)
        for action in self.source_actions:
            if action.isVisible() and action.isEnabled():choice.addItem(action.text(),action.data())
        hint=label('','muted');hint.setWordWrap(True);box.addWidget(hint)
        def explain():
            hint.setText(tr('Der Ordner bleibt verknüpft. Lumen durchsucht aktuelle Textdateien und PDFs bei Bedarf, einschließlich Unterordnern. Lokale Ordner werden nicht automatisch auf den Server übertragen.' if choice.currentData()=='folder' else 'Originale bleiben an ihrem Ort. Im nächsten Schritt wählst du den Inhalt aus.'))
            hint.setMinimumHeight(hint.heightForWidth(392));dialog.adjustSize()
        choice.currentIndexChanged.connect(explain);explain()
        controls=QDialogButtonBox(QDialogButtonBox.Cancel);go=controls.addButton(tr('Weiter'),QDialogButtonBox.AcceptRole);box.addWidget(controls)
        controls.rejected.connect(dialog.reject)
        def select():
            if self.project!=project or self.view!=view or self.readonly:
                dialog.reject();return
            kind=choice.currentData();dialog.accept()
            for action in self.source_actions:
                if action.data()==kind and action.isVisible() and action.isEnabled():action.trigger();break
        go.clicked.connect(select);dialog.open()

    def change_view(self,index):
        self.view=self.VIEWS[index][0]
        if self.record:
            self.load(self.record,self.readonly)
            QTimer.singleShot(0,self.scroll,lambda:self.scroll.verticalScrollBar().setValue(0))

    def reflow(self):
        narrow=self.width()<760
        self.grid.addWidget(self.side,1 if narrow else 0,0 if narrow else 1)
        self.side.setMaximumWidth(16777215 if narrow else 280)
        self.side.setMinimumWidth(0 if narrow else 230)
        self.side_box.setContentsMargins(0 if narrow else 24,22 if narrow else 0,0,0)
        self.side.setStyleSheet('QWidget#journalAside { border-'+('top' if narrow else 'left')+':1px solid palette(mid); }')

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()

    @staticmethod
    def clear(box):
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().hide();item.widget().deleteLater()

    def keep_draft(self):
        if self.project: self.drafts[self.project] = self.question.toPlainText()
        self.ask_button.setEnabled(bool(self.question.toPlainText().strip()) and len(self.question.toPlainText()) <= 12000)

    def ask(self):
        question = self.question.toPlainText().strip()
        if not question or len(question) > 12000: raise ValueError(tr('Bitte eine Frage mit höchstens 12.000 Zeichen eingeben.'))
        self.window.save()
        record = self.window.library.get(self.project)
        if record.get('server_bound') and not any(r.get('kind')=='folder' for r in record.get('resources',[])):
            from projects_question_ui import ProjectQuestion
            self.server_question = ProjectQuestion(self, question)
            self.server_question.show()
            return
        command = [str(Path(__file__).resolve().parents[1] / 'agent-app/main.py'), '--page', 'chat', '--action', 'open', '--draft', question_prompt(self.project, question)]
        started, _ = QProcess.startDetached(sys.executable, command)
        if not started: raise OSError(tr('Lumen konnte nicht geöffnet werden.'))
        self.question.clear()

    def load(self, record, readonly=False):
        window=self.window;children=window.projects.items(record['id'])
        if self.project!=record['id']:
            self.view='journal';self.tabs.blockSignals(True);self.tabs.setCurrentIndex(0);self.tabs.blockSignals(False)
        signature=(record,readonly,children,self.view)
        if signature==getattr(self,'signature',None):return
        self.signature=signature;self.record=record;self.readonly=readonly;self.project=record['id']
        self.title.setText(record['title']);self.edit.setVisible(record.get('server_role')!='reader');self.archive.setVisible(bool(record.get('_archived')))
        self.question.blockSignals(True);self.question.setPlainText(self.drafts.get(self.project,''));self.question.blockSignals(False);self.keep_draft()
        bound=record.get('server_bound') and not any(r.get('kind')=='folder' for r in record.get('resources',[]))
        self.ask_button.setText(tr('Quellen auswählen' if bound else 'In Lumen öffnen'))
        self.ask_button.setAccessibleName(self.ask_button.text())
        self.question_hint.setText(tr('Stelle Fragen zu deinen ausgewählten Projektquellen. Antworten öffnen sich als Gespräch mit Quellenbelegen.' if bound else 'Eine Frage zu diesem Projekt als Gesprächsentwurf öffnen. Quellen werden erst im Gespräch gelesen.'))
        self.project_archive.setEnabled(record.get('server_role')!='reader')
        self.project_archive.setText(tr('Projekt wiederherstellen' if record.get('_archived') else 'Projekt archivieren'))
        for control in self.add_controls:control.setEnabled(not readonly)
        for control,kinds in self.context_controls:control.setVisible(bool(kinds & self.ASSIGNABLE[self.view]))
        for action in self.more_menu.actions():
            if isinstance(action.data(),set):action.setVisible(self.view in action.data())
        self.add_source.setText(tr('Analyse oder Recherche planen' if self.view=='results' else 'Quelle hinzufügen' if self.view=='material' else 'Inhalt zuordnen'))
        # Keep the shared menu button alive when its old heading is rebuilt.
        self.add_source.setParent(self)
        self.clear(self.main_box);self.clear(self.next_box)
        parents={item['id'] for item in children if item['kind']=='initiative'}
        tasks=[item for item in children if item['kind']!='initiative' and item['parent'] in parents]
        entries=[]
        for item in children:
            if item['kind']!='initiative' and item not in tasks:continue
            category='journal' if item['kind']=='initiative' else 'results' if item['kind'] in ('analysis','research') else 'tasks'
            kind='Vorhaben' if item['kind']=='initiative' else KINDS[item['kind']]
            entries.append(dict(title=item['title'],kind=kind,category=category,updated=item['updated'],detail=tr(STATES.get(item.get('status'),'Offen')),open=lambda key=item['id']:window.safe(window.navigate,record['id'],key)))
        for index,resource in enumerate(record.get('resources',[])):
            kind={'file':'Datei','folder':'Ordner','url':'Weblink','wissen':'Notiz'}.get(resource.get('kind'),'Quelle')
            entries.append(dict(title=resource['title'],kind=kind,category='material',updated=None,detail='',resource=resource,open=lambda i=index:self.open_material(i)))
        for index,ref in enumerate(record.get('references',[])):
            entries.append(dict(title=ref['title'],kind='Gespräch' if ref['kind']=='chat' else 'Auftrag',category='conversations' if ref['kind']=='chat' else 'tasks',updated=None,detail='',open=lambda i=index:self.open_reference(i)))
        for index,ref in enumerate(record.get('server_attachments',[])):
            entries.append(dict(title=ref.get('title') or tr('Zugeordneter Inhalt'),kind={'file':'Datei','note':'Notiz','task':'Auftrag','conversation':'Gespräch'}.get(ref['kind'],'Quelle'),category='material' if ref['kind'] in ('file','note') else 'conversations' if ref['kind']=='conversation' else 'tasks',updated=None,detail='',open=lambda i=index:self.open_server_material(i)))
        with window.library.connect() as db:
            linked={row[0] for row in db.execute('SELECT flow FROM project_flows WHERE project=?',(record['id'],))} if db.execute("SELECT 1 FROM sqlite_master WHERE name='project_flows'").fetchone() else set()
        for flow in window.project_store.workflows():
            if flow['id'] in linked:entries.append(dict(title=flow['name'],kind='Ablauf',category='tasks',updated=None,detail='',open=lambda key=flow['id']:window.safe(window.home.open_flow,key)))
        if self.view=='journal':
            overview=QWidget();overview.setObjectName('journalOverview');overview.setAttribute(Qt.WA_StyledBackground)
            box=QVBoxLayout(overview);box.setContentsMargins(0,5,0,24);box.setSpacing(15)
            box.addWidget(label(tr('PROJEKTSTAND'),'journalEyebrow'))
            box.addWidget(label(tr('Was wir festgehalten haben') if record.get('notes') else tr('Ein Ort für alles, was dazugehört.'),'journalSummary'))
            box.addWidget(label(record.get('notes') or tr('Füge Quellen, Gespräche und Aufgaben hinzu. Hier bleiben ihre Zusammenhänge sichtbar.'),'journalDescription'))
            counts=tr('{0} zugeordnete Inhalte',len(entries))+'     '+tr('{0} Aufgaben',sum(e['category'] in ('tasks','results') for e in entries))+'     '+tr('{0} Analysen & Recherchen',sum(e['category']=='results' for e in entries))
            box.addWidget(label(counts,'journalSmall'));self.main_box.addWidget(overview);self.main_box.addSpacing(24)
        heading=row(label(tr('Zugeordnete Inhalte') if self.view=='journal' else tr(dict(self.VIEWS)[self.view]),'journalSection'),self.add_source);heading.layout().setStretch(0,1);self.add_source.setVisible(not readonly);self.main_box.addWidget(heading);self.main_box.addSpacing(20)
        shown=[e for e in entries if self.view=='journal' or e['category']==self.view or self.view=='tasks' and e['category']=='results']
        if self.view=='results':self.main_box.addWidget(label(tr('Vorhandene Analysen und Recherchen bleiben mit ihren Aufgaben und Ergebnissen verbunden.'),'journalMuted'));self.main_box.addSpacing(16)
        self.visible_titles=[];self.material_controls={}
        for entry in sorted(shown,key=lambda e:e['updated'] or 0,reverse=True):self.add_entry(entry)
        if not shown:self.main_box.addWidget(label(tr('Noch nichts zugeordnet.'),'journalMuted'))
        for task in sorted(tasks,key=lambda item:item['updated'],reverse=True):
            if task.get('status','open') not in ('done','cancelled','failed') and self.next_box.count()<5:
                control=button(task['title'],lambda _checked=False,key=task['id']:window.safe(window.navigate,record['id'],key));control.setObjectName('journalIntegration');self.next_box.addWidget(control)
        if not self.next_box.count():self.next_box.addWidget(label(tr('Keine offenen Aufgaben.'),'journalMuted'))
        self.main_box.addStretch(1)

    def add_entry(self,entry):
        self.visible_titles.append(entry['title'])
        line=QWidget();layout=QHBoxLayout(line);layout.setContentsMargins(0,0,0,0);layout.setSpacing(16)
        if self.view=='journal':
            date=label(self.window.stamp(entry['updated']) if entry['updated'] else '','journalSmall');date.setFixedWidth(94);layout.addWidget(date,0,Qt.AlignTop)
        body=QWidget();body.setObjectName('journalTimeline' if self.view=='journal' else 'journalResource');body.setAttribute(Qt.WA_StyledBackground)
        box=QVBoxLayout(body);box.setContentsMargins(20 if self.view=='journal' else 0,0,0,25);box.setSpacing(10)
        if self.view=='journal':box.addWidget(label(tr(entry['kind'])+' · '+tr('Zugeordnet'),'journalEyebrow'))
        control=QPushButton();control.setObjectName('journalEntry');control.setAccessibleName(entry['title']);control.setCursor(Qt.PointingHandCursor)
        content=QVBoxLayout(control);content.setContentsMargins(0,0,0,0);content.setSpacing(5)
        content.addWidget(label(entry['title'],'journalEntryTitle'));content.addWidget(label(' · '.join(filter(None,(tr(entry['kind']),entry['detail']))),'journalMuted'))
        for child in control.findChildren(QWidget):child.setAttribute(Qt.WA_TransparentForMouseEvents)
        if 'resource' in entry:
            self.material_controls[entry['resource']['target']]=control
            control.setContextMenuPolicy(Qt.CustomContextMenu)
            def context(position):
                menu=QMenu(control);menu.addAction(tr('Öffnen'),entry['open'])
                if not self.readonly:
                    from project_dialogs import remove_source
                    menu.addAction(tr('Verknüpfung entfernen'),lambda:self.window.safe(remove_source,self.window,self.project,entry['resource']))
                menu.exec(control.mapToGlobal(position))
            control.customContextMenuRequested.connect(context)
        control.clicked.connect(lambda _checked=False,fn=entry['open']:fn());box.addWidget(control);layout.addWidget(body,1);self.main_box.addWidget(line)

    def open_server_material(self,index):
        if not self.window.home.plan(scope=''):return
        self.window.server_material.setCurrentRow(index);self.window.safe(self.window.open_server_material)

    def require_assignment(self,kind):
        if self.readonly or kind not in self.ASSIGNABLE[self.view]:
            raise ValueError(tr('Dieser Inhalt passt nicht zur aktuellen Projektansicht.'))

    def plan_result(self,kind):
        self.require_assignment(kind)
        self.window.create_task(kind)

    def add_files(self):
        self.require_assignment('file')
        from project_dialogs import open_dialog
        return open_dialog(self.window,'file')

    def add_folder(self):
        self.require_assignment('folder')
        from project_dialogs import open_dialog
        return open_dialog(self.window,'folder')

    def add_link(self):
        self.require_assignment('url')
        from project_dialogs import open_dialog
        return open_dialog(self.window,'url')

    def pick_reference(self,kind):
        self.require_assignment(kind)
        if self.window.home.plan(scope=''):self.window.reference_pane.pick(kind)

    def focus_material(self,index):
        resource=self.window.library.get(self.project)['resources'][index]
        self.tabs.setCurrentIndex(1)
        control=self.material_controls[resource['target']]
        control.setFocus()
        QTimer.singleShot(0,control,lambda:self.scroll.ensureWidgetVisible(control))

    def open_material(self, index):
        resource=self.window.library.get(self.project)['resources'][index]
        self.window.safe(self.window.open_resource_value,resource)

    def add_note(self):
        self.require_assignment('note')
        from project_dialogs import open_dialog
        return open_dialog(self.window,'wissen')

    def open_reference(self, index):
        self.window.reference_pane.items.setCurrentRow(index); self.window.safe(self.window.reference_pane.open)

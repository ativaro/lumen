"""Independent project journal; originals remain in their Lumen applications."""
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QStackedWidget,QInputDialog
from lumen_i18n import tr
from tools_ui import button,label,row


class ProjectHome(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.project_id='';self.scope=''
        from projects_overview import ProjectOverview, STYLE
        self.setObjectName('projectHome');self.setAttribute(Qt.WA_StyledBackground);self.setStyleSheet(STYLE)
        from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
        outer=QVBoxLayout(self);outer.setContentsMargins(PAGE_MARGIN,20,PAGE_MARGIN,20);outer.setSpacing(PAGE_SPACING)
        self.app_header=AppHeader(tr('Lumen Projekte'),tr('Ein Ort für deine Quellen, Gespräche und nächsten Schritte.'))
        self.new_project=button(tr('Neues Projekt'),lambda:window.safe(window.create),'list-add',True)
        self.new_project.setObjectName('primary');self.app_header.actions.addWidget(self.new_project);outer.addWidget(self.app_header)
        self.pages=QStackedWidget();outer.addWidget(self.pages,1)
        self.overview=ProjectOverview(window);self.overview.selected.connect(lambda key:window.safe(self.choose,key));self.pages.addWidget(self.overview)
        self.detail=QWidget();detail=QVBoxLayout(self.detail);detail.setContentsMargins(0,12,0,0);detail.setSpacing(16);self.pages.addWidget(self.detail)
        controls=row(button(tr('Alle Projekte'),lambda:window.safe(window.show_home),'go-previous'),button(tr('Serverabgleich'),lambda:window.safe(self.management)))
        controls.layout().addStretch(1)
        detail.addWidget(controls)
        self.editor_layout=QHBoxLayout();detail.addLayout(self.editor_layout,1)
        pane=QWidget();self.pane=pane;box=QVBoxLayout(pane);box.setContentsMargins(0,0,0,0);self.editor_layout.addWidget(pane,1)
        from projects_references_ui import ReferencesPane
        self.references=ReferencesPane(window);window.reference_pane=self.references
        from projects_journal_ui import ProjectJournal
        self.journal=ProjectJournal(window);window.journal=self.journal;self.prompt=self.journal.question
        box.addWidget(self.journal,1);box.addWidget(self.references);self.references.hide()
        self.empty=label(tr('Wähle ein Projekt oder lege eines an.'),'muted');box.addWidget(self.empty)
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(lambda:window.safe(self.poll));self.timer.start()
        self.refresh()

    def refresh(self):
        records=self.window.library.all()
        if self.project_id and self.project_id not in {r['id'] for r in records}:
            records += [r for r in self.window.library.all(True) if r['id']==self.project_id]
        self.overview.refresh()
        current=next((r for r in records if r['id']==self.project_id),None)
        self.journal.setVisible(current is not None);self.empty.setVisible(current is None)
        if current:
            current=self.window.project_trash.project(self.project_id)
            readonly=bool(current.get('_archived') or current.get('server_role')=='reader')
            self.journal.load(current,readonly);self.references.load(current,readonly)

    def choose(self,identity):
        if not identity:return
        if self.project_id!=identity and self.prompt.toPlainText().strip():
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(self,tr('Lumen Projekte'),tr('Ungespeicherte Änderungen verwerfen?'))!=QMessageBox.Yes:return
        if not self.window.editor.allow_leave():return
        self.window.focus_record(identity);self.window.editor.hide();self.scope='';self.refresh()

    def show_overview(self):
        self.pages.setCurrentWidget(self.overview);self.overview.refresh()

    def show_detail(self):
        self.pages.setCurrentWidget(self.detail)

    def ensure_project(self):
        if not self.project_id:raise ValueError(tr('Bitte zuerst ein Projekt anlegen.'))
        return self.project_id

    def plan(self,scope=None,tab=None):
        if not self.window.navigate(self.ensure_project(),self.scope if scope is None else scope):return False
        if tab is not None:self.window.editor.show_page(tab)
        return True

    def select_initiative(self,identity):
        item=self.window.projects.get(identity)
        if item['project']!=self.project_id or item['kind']!='initiative':raise ValueError(tr('Ungültiges Vorhaben.'))
        self.scope=identity

    def add_task(self):self.window.create_task()
    def add_initiative(self):self.window.create_initiative()
    def edit_material(self):self.plan(tab=1)

    def management(self):
        from projects_sync_ui import configure
        configure(self.window)

    def open_flow(self,key):
        self.window.open_section('automations');listing=self.window.automations.flows
        for i in range(listing.count()):
            if listing.item(i).data(Qt.UserRole)['id']==key:listing.setCurrentRow(i);return
        raise ValueError(tr('Ablauf nicht mehr vorhanden.'))

    def attach_flow(self):
        project=self.ensure_project();record=self.window.library.get(project)
        if record.get('_archived') or record.get('server_role')=='reader':raise ValueError(tr('Dieses Projekt ist schreibgeschützt.'))
        flows=self.window.project_store.workflows()
        if not flows:raise ValueError(tr('Noch kein Ablauf vorhanden. Über „Alle Automationen“ einen Ablauf anlegen.'))
        names=[f['name']+' · '+f['id'][:8] for f in flows]
        name,ok=QInputDialog.getItem(self,tr('Lumen Projekte · Ablauf zuordnen'),tr('Vorhandener Ablauf'),names,0,False)
        if not ok:return
        with self.window.library.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS project_flows(flow TEXT PRIMARY KEY,project TEXT NOT NULL,scope TEXT NOT NULL DEFAULT '')")
            key=flows[names.index(name)]['id'];current=db.execute('SELECT project FROM project_flows WHERE flow=?',(key,)).fetchone()
            if current and current[0]!=project:raise ValueError(tr('Dieser Ablauf gehört bereits zu einem anderen Projekt.'))
            db.execute('INSERT OR IGNORE INTO project_flows VALUES(?,?,?)',(key,project,self.scope))
        self.journal.signature=None;self.refresh()

    def poll(self):
        if not self.window.job:self.refresh()

    def reflow(self):
        editing=not self.window.editor.isHidden();split=self.width()>=1160
        self.pane.setVisible(not editing or split)
        self.journal.side.setVisible(not editing)
        self.window.editor.setMinimumWidth(520 if split else 440)
        self.window.editor.setMaximumWidth(560 if split else 16777215)


    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()

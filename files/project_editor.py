"""The project planning editor embedded beside the journal."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea, QStackedWidget, QTabBar,
    QLineEdit, QPlainTextEdit, QListWidget, QComboBox, QCheckBox, QMessageBox, QMenu, QToolButton)
from lumen_i18n import tr
from tools_ui import button, label, row


class ProjectEditor(QWidget):
    def __init__(self, window):
        super().__init__(); self.window=window; self.draft_kind=''; self.return_focus=None
        self.setObjectName('projectEditor');self.setAttribute(Qt.WA_StyledBackground);self.setMinimumWidth(440)
        self.setStyleSheet('''
QWidget#projectEditor { background:palette(window);border-left:1px solid palette(mid); }
QWidget#projectEditor QLabel#editorTitle { font-size:20px;font-weight:500; }
QWidget#projectEditor QLabel#editorField { font-size:14px;font-weight:500; }
QWidget#projectEditor QTabBar { border-bottom:1px solid palette(mid); }
QWidget#projectEditor QTabBar::tab { background:transparent;color:palette(placeholder-text);border:0;border-radius:0;border-bottom:2px solid transparent;padding:12px 8px;margin-right:16px;min-width:0; }
QWidget#projectEditor QTabBar::tab:selected { color:palette(text);border-bottom-color:palette(highlight); }
QWidget#projectEditor QTabBar::tab:focus { color:palette(highlight); }
QWidget#projectEditor QScrollArea { background:transparent;border:0; }
QWidget#projectEditor QWidget#editorFooter { border-top:1px solid palette(mid); }
QWidget#projectEditor QToolButton { background:transparent;color:palette(text);border:1px solid transparent;border-radius:6px;padding:8px 4px; }
QWidget#projectEditor QToolButton:hover,QWidget#projectEditor QToolButton:focus { background:palette(midlight);border-color:palette(highlight); }
''')
        layout=QVBoxLayout(self);layout.setContentsMargins(24,16,0,0);layout.setSpacing(12)
        self.heading=label('', 'editorTitle')
        close=button('',lambda:window.safe(self.close_editor),'window-close');close.setAccessibleName(tr('Seitenleiste schließen'));close.setToolTip(tr('Schließen'))
        self.more=button('',lambda:None,'view-more-symbolic');self.more.setAccessibleName(tr('Weitere Aktionen'));self.more.setToolTip(tr('Weitere Aktionen'));self.more_menu=QMenu(self.more);self.more.setMenu(self.more_menu)
        header=row(self.heading,self.more,close);header.layout().setStretch(0,1);layout.addWidget(header)
        self.context=label('','muted');layout.addWidget(self.context)
        self.navigation=QTabBar();self.navigation.setAccessibleName(tr('Aufgabenansichten'));self.navigation.setExpanding(False);self.navigation.setDrawBase(False)
        for title in ('Aufgabe','Material','Ergebnisse'):self.navigation.addTab(tr(title))
        self.navigation.currentChanged.connect(lambda index:self.show_page((2 if self.is_task() else 0,1,3)[index]))
        layout.addWidget(self.navigation)
        self.archive=self.more_menu.addAction(tr('Archivieren'),lambda:window.safe(window.archive_task if self.is_task() else window.archive))
        self.stop=button(tr('Ausführung stoppen'),window.cancel,'process-stop');layout.addWidget(self.stop);self.stop.hide()
        scroll=QScrollArea();self.scroll=scroll;scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);layout.addWidget(scroll,1)
        content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(0,8,8,0);box.setSpacing(16);scroll.setWidget(content)
        window.title=QLineEdit();window.title.setAccessibleName(tr('Bezeichnung'));window.title.textChanged.connect(window.edited)
        self.title_label=label(tr('Bezeichnung'),'editorField');self.title_label.setBuddy(window.title);box.addWidget(self.title_label);box.addWidget(window.title)
        window.tabs=QStackedWidget();box.addWidget(window.tabs,1)
        self.record=QWidget();self.record_layout=QVBoxLayout(self.record);self.record_layout.setContentsMargins(0,0,0,0)
        window.notes=QPlainTextEdit();window.notes.setAccessibleName(tr('Notizen'));window.notes.setPlaceholderText(tr('Ziel, Gedanken und nächste Schritte …'));window.notes.setMaximumHeight(145);window.notes.textChanged.connect(window.edited)
        self.location=QComboBox();self.location.setAccessibleName(tr('Speicherort'));self.record_layout.addWidget(self.location)
        self.notes_field=QWidget();notes_box=QVBoxLayout(self.notes_field);notes_box.setContentsMargins(0,0,0,0);notes_box.setSpacing(8)
        notes_label=label(tr('Notizen'),'editorField');notes_label.setBuddy(window.notes);notes_box.addWidget(notes_label);notes_box.addWidget(window.notes)
        self.record_layout.addWidget(self.notes_field);self.record_layout.addStretch()
        window.tabs.addWidget(self.record)
        from project_material_editor import MaterialEditor
        self.material=MaterialEditor(window);window.tabs.addWidget(self.material)
        task=QWidget();form=QVBoxLayout(task);form.setContentsMargins(0,0,0,0);form.setSpacing(16);self.task_layout=form
        self.owner=QComboBox();self.owner.setAccessibleName(tr('Vorhaben'));self.owner.currentIndexChanged.connect(window.edited)
        self.assignment=QWidget();assignment=QVBoxLayout(self.assignment);assignment.setContentsMargins(0,0,0,0);assignment.setSpacing(8)
        self.owner_label=label(tr('Vorhaben'),'editorField');self.owner_label.setBuddy(self.owner);assignment.addWidget(self.owner_label);assignment.addWidget(self.owner)
        self.missing=button(tr('Zuerst ein Vorhaben anlegen'),lambda:window.safe(window.create_initiative),'list-add');assignment.addWidget(self.missing)
        self.kind=QComboBox();self.kind.setAccessibleName(tr('Bearbeitung'))
        for text,value in [('Selbst erledigen','manual'),('Recherche mit Lumen','research'),('Analyse mit Lumen','analysis')]:self.kind.addItem(tr(text),value)
        self.kind.currentIndexChanged.connect(self.kind_changed)
        kind_label=label(tr('Bearbeitung'),'editorField');kind_label.setBuddy(self.kind);assignment.addWidget(kind_label);assignment.addWidget(self.kind)
        window.task_meta=label('','muted');window.task_meta.setWordWrap(True)
        window.goal=QPlainTextEdit();window.goal.setAccessibleName(tr('Gewünschtes Ergebnis'));window.goal.setPlaceholderText(tr('Was soll am Ende vorliegen?'));window.goal.setMinimumHeight(120);window.goal.setMaximumHeight(160);window.goal.textChanged.connect(window.edited)
        goal_label=label(tr('Gewünschtes Ergebnis'),'editorField');goal_label.setBuddy(window.goal);form.addWidget(goal_label);form.addWidget(window.goal)
        context=label(tr('Material und Notizen aus Projekt und Vorhaben werden einbezogen.'),'muted');context.setWordWrap(True);form.addWidget(context)
        form.addWidget(self.assignment)
        window.deep=QCheckBox('Deep Research');window.deep.toggled.connect(window.edited)
        window.operation=QComboBox();window.operation.addItem(tr('Analyse'),'analysis');window.operation.addItem(tr('Recherche'),'research');window.operation.currentIndexChanged.connect(window.edited)
        window.interval=QComboBox();window.interval.setAccessibleName(tr('Rhythmus'))
        for text,seconds in [('Alle 60 Minuten',3600),('Alle 24 Stunden',86400),('Alle 7 Tage',604800)]:window.interval.addItem(tr(text),seconds)
        window.interval.currentIndexChanged.connect(window.edited)
        window.schedule=QCheckBox(tr('Aufgabe wiederholen'));window.schedule.toggled.connect(window.edited)
        window.schedule_row=QWidget();repeat=QVBoxLayout(window.schedule_row);repeat.setContentsMargins(0,8,0,0);repeat.setSpacing(12);repeat.addWidget(window.schedule);repeat.addWidget(window.interval);form.addWidget(window.schedule_row)
        window.schedule.toggled.connect(window.interval.setVisible)
        window.schedule_status=label('','muted');window.schedule_status.setWordWrap(True)
        self.more_fields=QToolButton();self.more_fields.setText(tr('Weitere Angaben'));self.more_fields.setCheckable(True);self.more_fields.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);self.more_fields.setArrowType(Qt.RightArrow);self.more_fields.setAccessibleName(tr('Weitere Angaben'));form.addWidget(self.more_fields)
        self.more_fields.toggled.connect(lambda checked:self.more_fields.setArrowType(Qt.DownArrow if checked else Qt.RightArrow))
        self.advanced=QWidget();self.advanced_layout=QVBoxLayout(self.advanced);self.advanced_layout.setContentsMargins(0,0,0,0);form.addWidget(self.advanced);self.advanced.hide();self.more_fields.toggled.connect(self.advanced.setVisible)
        self.advanced_layout.addWidget(window.task_meta);self.advanced_layout.addWidget(window.schedule_status);self.advanced_layout.addWidget(window.deep);self.advanced_layout.addWidget(window.operation)
        window.dependencies=QListWidget();window.dependencies.setMaximumHeight(100);window.dependencies.setAccessibleName(tr('Vorausgesetzte Aufgaben'));window.dependencies.itemChanged.connect(window.edited)
        window.dependency_heading=label(tr('Nach diesen Aufgaben starten'),'muted');self.advanced_layout.addWidget(window.dependency_heading);self.advanced_layout.addWidget(window.dependencies)
        window.start_task=button(tr('Jetzt ausführen'),lambda:window.safe(window.run_task),'media-playback-start')
        window.complete_task=button(tr('Als erledigt markieren'),lambda:window.safe(window.complete),'dialog-ok')
        actions=row(window.start_task,window.complete_task);actions.layout().addStretch(1);form.addWidget(actions);form.addStretch();window.tabs.addWidget(task)
        results=QWidget();result_box=QVBoxLayout(results);result_box.setContentsMargins(0,0,0,0)
        window.history=QComboBox();window.history.setAccessibleName(tr('Ausführungsverlauf'));window.history.setPlaceholderText(tr('Noch keine Ausführung'));window.history.currentIndexChanged.connect(window.show_run);result_box.addWidget(window.history)
        window.result=QPlainTextEdit();window.result.setReadOnly(True);window.result.setAccessibleName(tr('Ergebnis'));window.result.setPlaceholderText(tr('Noch kein Ergebnis vorhanden.'));result_box.addWidget(window.result,1)
        for text,method in [('Auftrag, Quellen und Arbeitsschritte ansehen',window.show_sources),('Ergebnis in Lumen Notes speichern',window.save_result),('Mit Lumen Vault sichern',window.backup)]:result_box.addWidget(button(tr(text),lambda _=False,f=method:window.safe(f)))
        window.tabs.addWidget(results)
        self.feedback=label('','muted');self.feedback.setWordWrap(True);layout.addWidget(self.feedback)
        self.apply=button(tr('Speichern'),lambda:window.safe(self.commit),'document-save',True)
        footer=row(button(tr('Abbrechen'),lambda:window.safe(self.close_editor)),self.apply);footer.setObjectName('editorFooter');footer.setAttribute(Qt.WA_StyledBackground);footer.layout().setContentsMargins(0,16,0,0);footer.layout().insertStretch(0,1);layout.addWidget(footer)
        self.record_heading='';window.tabs.currentChanged.connect(self.page_changed)
        chain=(window.title,window.goal,self.owner,self.kind,window.schedule,window.interval,self.more_fields,window.notes,window.deep,window.operation,window.dependencies,window.start_task,window.complete_task,self.apply)
        for first,second in zip(chain,chain[1:]):QWidget.setTabOrder(first,second)
        self.escape=QShortcut(QKeySequence(Qt.Key_Escape),self);self.escape.setContext(Qt.WidgetWithChildrenShortcut);self.escape.activated.connect(lambda:window.safe(self.close_editor))
        self.hide()

    def page_changed(self,index):
        self.window.title.setVisible(index in (0,2))
        self.title_label.setVisible(index in (0,2))
        self.navigation.blockSignals(True);self.navigation.setCurrentIndex({0:0,2:0,1:1,3:2}.get(index,0));self.navigation.blockSignals(False)
        self.heading.setText(tr('Material hinzufügen') if index==1 else tr('Ergebnisse') if index==3 else tr('Projektumgebung bearbeiten') if index==4 else self.record_heading)

    def is_task(self):
        return self.draft_kind=='task' or bool(not self.draft_kind and self.window.scope and self.window.projects.get(self.window.scope)['kind']!='initiative')

    def dirty(self):
        w=self.window
        return bool(w.current or self.draft_kind) and (w.editor_fields()!=getattr(w,'loaded_fields',{}) or self.material.dirty())

    def allow_leave(self):
        if not self.dirty():
            if self.draft_kind:self.discard()
            return True
        choice=QMessageBox.question(self,tr('Änderungen behalten?'),tr('Die Seitenleiste enthält ungespeicherte Änderungen.'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if choice==QMessageBox.Cancel:return False
        if choice==QMessageBox.Save:self.window.save()
        else:self.discard()
        return True

    def discard(self):
        w=self.window;self.material.reset()
        if self.draft_kind:self.draft_kind='';w.scope='';w.initiative='';w.current='';w.loaded_fields={}
        elif w.current:
            w.loading=True
            try:w.load_fields(w.projects.get(w.scope) if w.scope else w.library.get(w.current))
            finally:w.loading=False

    def close_editor(self):
        if not self.allow_leave():return
        self.draft_kind='';self.hide();self.window.home.reflow()
        if self.return_focus:
            try:self.return_focus.setFocus()
            except RuntimeError:pass

    def hideEvent(self,event):
        super().hideEvent(event)
        if hasattr(self.window,'home'):self.window.home.reflow()

    def show_page(self,index):
        self.window.tabs.setCurrentIndex(index);self.show();self.window.home.reflow()

    def present(self,value,new=''):
        w=self.window;self.draft_kind=new;self.material.reset()
        self.return_focus=w.focusWidget();task=self.is_task()
        self.context.setText((w.library.get(w.current)['title'] if w.current else tr('Neues Projekt'))+((' / '+w.projects.get(w.initiative)['title']) if w.initiative else ''))
        self.record_heading=tr({'project':'Projekt anlegen','initiative':'Vorhaben anlegen','task':'Aufgabe anlegen'}.get(new,'Aufgabe bearbeiten' if task else 'Vorhaben bearbeiten' if w.scope else 'Projekt bearbeiten'))
        self.heading.setText(self.record_heading)
        self.location.clear();self.location.addItem(tr('Lokal'),'local')
        from projects_sync import read_state
        if read_state(w.library)['enabled']:self.location.addItem(tr('Lumen Server'),'server')
        self.location.setVisible(new=='project')
        self.navigation.setVisible(not bool(new));self.archive.setVisible(not bool(new));self.more.setVisible(not bool(new))
        self.navigation.setTabText(0,tr('Aufgabe' if task else 'Vorhaben' if w.scope else 'Projekt'));self.navigation.setTabVisible(2,task)
        if hasattr(self,'workflow_action'):self.workflow_action.setVisible(not new and not w.scope)
        self.archive.setText(tr('Wiederherstellen') if value.get('archived') or value.get('_archived') else tr('Archivieren'))
        self.owner.blockSignals(True);self.owner.clear()
        for item in w.projects.items(w.current,'') if w.current else []:self.owner.addItem(item['title'],item['id'])
        self.owner.setCurrentIndex(max(0,self.owner.findData(w.initiative)));self.owner.blockSignals(False)
        self.owner.setEnabled(bool(new));self.missing.setVisible(task and self.owner.count()==0)
        self.kind.blockSignals(True)
        legacy=self.kind.findData('automation')
        if legacy>=0 and value.get('kind')!='automation':self.kind.removeItem(legacy)
        if self.kind.findData(value.get('kind'))<0 and value.get('kind')=='automation':self.kind.addItem(tr('Bestehende Automation'),'automation')
        self.kind.setCurrentIndex(max(0,self.kind.findData(value.get('kind','research'))));self.kind.blockSignals(False);self.kind.setEnabled(bool(new))
        self.assignment.setVisible(bool(new));w.interval.setVisible(w.schedule.isChecked())
        if task and not new:self.context.setText(self.context.text()+' · '+self.kind.currentText())
        self.apply.setText(tr('Anlegen') if new else tr('Speichern'))
        owner=w.library.get(w.current) if w.current else {}
        readonly=bool(owner.get('_archived') or owner.get('server_role')=='reader' or value.get('archived') or value.get('status')=='running')
        if task and w.initiative:readonly=readonly or bool(w.projects.get(w.initiative)['archived'])
        self.apply.setEnabled(not readonly and (not task or self.owner.count()>0));w.title.setReadOnly(readonly);w.notes.setReadOnly(readonly);w.goal.setReadOnly(readonly)
        self.material.set_readonly(readonly);w.deep.setEnabled(not readonly);w.schedule.setEnabled(not readonly and not owner.get('server_bound'));w.interval.setEnabled(not readonly and not owner.get('server_bound'));w.dependencies.setEnabled(not readonly);w.operation.setEnabled(not readonly);w.start_task.setEnabled(not readonly);w.complete_task.setEnabled(not readonly);self.archive.setEnabled(owner.get('server_role')!='reader');self.feedback.setText(tr('Nur lesen · archiviert, in Ausführung oder ohne Schreibrecht.') if readonly else '')
        (self.advanced_layout if task else self.record_layout).insertWidget(0,self.notes_field)
        self.more_fields.setChecked(False)
        w.tabs.setCurrentIndex(2 if task else 0);self.page_changed(w.tabs.currentIndex());self.show();self.kind_changed();w.home.reflow();w.title.setFocus()

    def kind_changed(self,*_):
        w=self.window;kind=self.kind.currentData();w.deep.setVisible(kind in ('research','automation'));w.schedule_row.setVisible(kind in ('research','analysis','automation'));w.operation.setVisible(kind=='automation')
        if self.draft_kind:w.edited()

    def commit(self):
        self.window.save();self.window.home.refresh();self.close_editor()

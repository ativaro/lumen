"""Describe, try and review small app changes before replacing the saved version."""
import copy
import difflib
import sqlite3
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
    QFrame, QLineEdit, QPlainTextEdit, QTabBar, QGridLayout, QScrollArea, QToolButton,
    QMessageBox)
from lumen_i18n import tr
from tools_ui import button, label, row
from code_design import shell, navigation
from code_edit_window import field
from code_app_edit import Drafts, check, proposal, parse_result


class AppWindow(QDialog):
    def __init__(self,collection,identity,parent=None):
        super().__init__(parent);self.collection=collection;self.item=collection.get(identity)
        if self.item['archived']:raise ValueError(tr('Die App ist archiviert.'))
        collection.used(identity)
        self.drafts=Drafts(collection);self.draft=self.drafts.open(identity);self.persisted=copy.deepcopy(self.draft)
        self.engine=None;self.loading=True;self.closed=False;self.inputs=[];self.switch=0;self.restore_pending=False
        self.setWindowTitle(tr('Lumen · Kleine App'));self.resize(1240,850)
        main,nav,self.footer=shell(self);navigation(nav,self.reject,lambda _:self.reject())['app'].setChecked(True)
        box=QVBoxLayout(main);box.setContentsMargins(28,20,28,20);box.setSpacing(12)
        self.context=label('','codeMuted');box.addWidget(self.context)
        self.heading=QBoxLayout(QBoxLayout.LeftToRight);box.addLayout(self.heading)
        self.title=label('','codeTitle');self.heading.addWidget(self.title,1)
        self.discard_button=button(tr('Verwerfen'),self.discard)
        self.review_button=button(tr('Änderungen prüfen'),self.review,primary=True)
        self.actions=row(self.review_button,self.discard_button)
        self.status=label('','codeMuted');self.status.setAccessibleName(tr('Speicherstatus'))
        self.error=label('','codeError');self.error.hide();box.addWidget(self.error)
        self.mode=QTabBar();self.mode.setExpanding(False);self.mode.addTab(tr('Benutzen'));self.mode.addTab(tr('Bearbeiten'));self.mode.setAccessibleName(tr('App-Modus'));self.mode.setObjectName('appSegments');self.heading.addWidget(self.mode)
        self.subtitle=label(self.item['description'],'codeSubtitle');box.addWidget(self.subtitle)
        self.banner=label('','codeMuted');box.addWidget(self.banner)
        self.body_area=QScrollArea();self.body_area.setWidgetResizable(True);self.body_area.setMinimumHeight(140)
        self.body_area.viewport().installEventFilter(self)
        body=QWidget();self.columns=QBoxLayout(QBoxLayout.LeftToRight,body);self.columns.setContentsMargins(0,0,0,0);self.columns.setSpacing(22)
        self.body_area.setWidget(body);box.addWidget(self.body_area,1);box.addWidget(self.status)
        self.editor=QScrollArea();self.editor.setWidgetResizable(True);self.editor.setMinimumWidth(260)
        contents=QWidget();left=QVBoxLayout(contents);left.setContentsMargins(0,4,4,4);left.setSpacing(12);self.editor.setWidget(contents);self.columns.addWidget(self.editor,2)
        left.addWidget(label(tr('Was möchtest du ändern?'),'codeCardTitle'))
        left.addWidget(label(tr('Beschreibe die Änderung. Lumen erstellt eine Fassung, die du direkt ausprobieren kannst.'),'codeMuted'))
        left.addWidget(label(tr('Änderung beschreiben'),'codeMuted'))
        self.request=QPlainTextEdit();self.request.setAccessibleName(tr('Änderung beschreiben'));self.request.setFixedHeight(130)
        self.request.setPlaceholderText(tr('Zum Beispiel: Zeige fehlende Eingaben direkt am Feld.'));left.addWidget(self.request)
        ideas=QGridLayout();ideas.setSpacing(6);left.addLayout(ideas)
        for i,(caption,text) in enumerate([('Eingaben prüfen','Eingaben verständlich prüfen'),('Ergebnis klarer','Ergebnis übersichtlicher zeigen'),('Schmale Fenster','Für schmale Fenster anpassen')]):
            control=button(tr(caption),lambda _=False,t=text:self.request.setPlainText(tr(t)));control.setObjectName('appIdea');ideas.addWidget(control,i//2,i%2)
        self.generate_button=button(tr('Änderung ausprobieren'),self.generate,primary=True)
        self.stop_button=button(tr('Stoppen'),self.stop);self.stop_button.hide();left.addWidget(row(self.generate_button,self.stop_button))
        left.addWidget(label(tr('App-Code und Auftrag gehen an deine eingerichtete KI. Deine Beispieleingaben bleiben in diesem Fenster.'),'codeMuted'))
        left.addSpacing(8);self.change_title=label(tr('In deinem Entwurf'),'codeCardTitle');left.addWidget(self.change_title)
        self.changes=label('','codeMuted');left.addWidget(self.changes);left.addWidget(self.actions)
        settings=QToolButton();settings.setText(tr('Name & Beschreibung').replace('&','&&'));settings.setCheckable(True);settings.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);settings.setArrowType(Qt.RightArrow);left.addWidget(settings)
        self.settings=QWidget();fields=QVBoxLayout(self.settings);fields.setContentsMargins(0,0,0,0)
        self.name=field(fields,'Name',QLineEdit());self.name.setMaxLength(160)
        self.purpose=field(fields,'Beschreibung',QPlainTextEdit());self.purpose.setFixedHeight(90)
        left.addWidget(self.settings);self.settings.hide()
        settings.toggled.connect(lambda value:(self.settings.setVisible(value),settings.setArrowType(Qt.DownArrow if value else Qt.RightArrow)))
        settings.toggled.connect(self.layout_columns)
        advanced=QToolButton();advanced.setText(tr('App-Code bearbeiten'));advanced.setCheckable(True);left.addWidget(advanced)
        self.source=QPlainTextEdit();self.source.setAccessibleName(tr('App-Inhalt (HTML)'));self.source.setMinimumHeight(220);left.addWidget(self.source);self.source.hide()
        advanced.toggled.connect(self.source.setVisible)
        self.apply_source=button(tr('Code ausprobieren'),self.apply_code);left.addWidget(self.apply_source);self.apply_source.hide();advanced.toggled.connect(self.apply_source.setVisible)
        advanced.toggled.connect(self.layout_columns)
        if self.item.get('last_task'):left.addWidget(button(tr('App aus Auftrag übernehmen'),self.adopt))
        left.addWidget(button(tr('Sammlungsdetails'),lambda:self.done(2)))
        self.reload_button=button(tr('Aktuelle Fassung laden'),self.reload_saved);left.addWidget(self.reload_button);left.addStretch()
        left.insertWidget(left.count()-1,button(tr('Frühere App-Fassungen'),self.restore_version))
        self.preview_panel=QFrame();self.preview_panel.setObjectName('codeLogic');right=QVBoxLayout(self.preview_panel);right.setContentsMargins(16,16,16,16);right.setSpacing(12);self.columns.addWidget(self.preview_panel,4)
        self.preview_panel.setAccessibleName(tr('Deine App · direkt ausprobieren'))
        self.version=QTabBar();self.version.addTab(tr('Gespeichert'));self.version.addTab(tr('Entwurf'));self.version.setAccessibleName(tr('Vorschaufassung'));self.version.setObjectName('appSegments')
        self.width_choice=QTabBar();self.width_choice.addTab(tr('Ganze Breite'));self.width_choice.addTab(tr('Schmal'));self.width_choice.setAccessibleName(tr('Vorschaubreite'));self.width_choice.setObjectName('appSegments')
        right.addWidget(row(self.version,self.width_choice))
        self.preview_state=label('','codeMuted')
        self.preview_host=QWidget();host=QHBoxLayout(self.preview_host);host.setContentsMargins(0,0,0,0);host.setAlignment(Qt.AlignHCenter)
        self.preview=None
        try:
            from code_app_preview import Preview
            self.preview=Preview();self.preview.setMinimumHeight(220);host.addWidget(self.preview,1);self.preview.loaded.connect(self.preview_loaded)
        except ImportError:
            host.addWidget(label(tr('Die eingebettete Vorschau benötigt Qt WebEngine. Die gespeicherte App bleibt über die bisherige Detailansicht verfügbar.')))
            host.addWidget(button(tr('Sammlungsdetails'),lambda:self.done(2)))
        right.addWidget(self.preview_host,1);right.addWidget(self.preview_state)
        right.addWidget(button(tr('Beispieleingaben zurücksetzen'),self.reset_inputs))
        right.addWidget(button(tr('Prüfbeispiele'),self.open_checks))
        right.addWidget(button(tr('Mit Lumen-Daten arbeiten'),self.open_data))
        right.addWidget(label(tr('Eingaben bleiben nur während dieser geöffneten App erhalten. Gespeichert wird der App-Code.'),'codeMuted'))
        self.autosave=QTimer(self);self.autosave.setSingleShot(True);self.autosave.setInterval(350);self.autosave.timeout.connect(self.persist)
        self.mode.currentChanged.connect(self.mode_changed);self.version.currentChanged.connect(self.refresh_preview)
        self.width_choice.currentChanged.connect(self.preview_width)
        self.setStyleSheet(self.styleSheet()+'''
QTabBar#appSegments { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 7px; padding: 3px; }
QTabBar#appSegments::tab { min-width: 0; padding: 7px 9px; margin: 0; background: transparent; color: palette(placeholder-text); border: none; border-radius: 5px; font-size: 12px; }
QTabBar#appSegments::tab:selected { background: palette(base); color: palette(text); }
QPushButton#appIdea { background: transparent; border: 1px solid palette(mid); border-radius: 5px; padding: 6px 8px; font-size: 11px; }
''')
        for control in (self.request,self.purpose,self.source):control.textChanged.connect(self.changed)
        self.name.textChanged.connect(self.changed)
        self.reset_fields();self.loading=False
        self.mode.setCurrentIndex(1 if self.dirty() or self.request.toPlainText() or not self.saved_value()['html'] else 0)
        self.mode_changed();self.update_status()

    def saved_value(self):
        return dict(title=self.item['title'],description=self.item['description'],html=self.item['definition'].get('html',''))

    def open_checks(self):
        try:
            from code_app_checks_ui import ChecksDialog
            ChecksDialog(self).exec()
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error)

    def open_data(self):
        try:
            from code_app_data_ui import DataDialog
            DataDialog(self).exec()
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error)

    def restore_version(self):
        from PySide6.QtWidgets import QInputDialog
        try:
            versions=self.collection.records.versions(self.item['id'])
            if not versions:self.fail(tr('Noch keine frühere App-Fassung gespeichert.'));return
            labels=[tr('Version')+' '+str(v['revision']) for v in versions]
            selected,ok=QInputDialog.getItem(self,tr('Lumen · Frühere App-Fassungen'),tr('Als Entwurf laden'),labels,0,False)
            if not ok:return
            if self.dirty() and QMessageBox.question(self,tr('Lumen · Entwurf ersetzen'),tr('Den offenen Entwurf durch die frühere Fassung ersetzen?'))!=QMessageBox.Yes:return
            revision=versions[labels.index(selected)]['revision'];value=self.collection.records.version(self.item['id'],revision)
            self.name.setText(value['title']);self.purpose.setPlainText(value['description']);self.source.setPlainText(value['html'])
            self.draft['changes']=[tr('Frühere Fassung als Entwurf geladen')+' · v'+str(revision)];self.persist();self.mode.setCurrentIndex(1);self.version.setCurrentIndex(1);self.refresh_preview();self.update_status()
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error)

    def reset_fields(self):
        self.loading=True
        self.name.setText(self.draft['value']['title']);self.purpose.setPlainText(self.draft['value']['description']);self.source.setPlainText(self.draft['value']['html'])
        self.request.setPlainText(self.draft['request'] or (self.item['definition'].get('prompt','') if not self.draft['value']['html'] else ''))
        self.loading=False

    def value(self):return dict(title=self.name.text(),description=self.purpose.toPlainText(),html=self.source.toPlainText())
    def busy(self):return bool(self.engine and self.engine.busy)
    def dirty(self):return self.value()!=self.saved_value()

    def fail(self,error):self.error.setText(tr(str(error)));self.error.show()

    def changed(self):
        if self.loading or self.closed:return
        if self.sender() is self.source:self.draft['changes']=[tr('App-Code manuell geändert.')]
        self.update_status();self.autosave.start()

    def persist(self):
        self.autosave.stop()
        if self.closed:return False
        try:
            value={**self.draft,'value':self.value(),'request':self.request.toPlainText()}
            if value==self.persisted:return True
            self.draft=self.drafts.write(value);self.persisted=copy.deepcopy(self.draft);return True
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error);return False

    def update_status(self):
        edit=self.mode.currentIndex()==1
        self.title.setText(self.item['title']);self.context.setText(tr('Kleine Apps')+' · '+tr('Version {0}',self.item['revision']));self.subtitle.setText(self.item['description'])
        self.actions.setVisible(edit and (self.dirty() or bool(self.request.toPlainText())))
        self.banner.setText(tr('Du bearbeitest einen Entwurf. Änderungen gelten nach deiner Prüfung.' if edit else 'Ein Entwurf ist noch offen. Hier benutzt du die gespeicherte App.'))
        self.banner.setVisible(not edit and self.dirty())
        self.status.setText(tr('Entwurf · noch nicht übernommen' if self.dirty() else 'Gespeicherte Fassung'))
        self.change_title.setVisible(self.dirty());self.changes.setVisible(self.dirty())
        self.changes.setText('\n\n'.join('• '+v for v in self.draft['changes']) or tr('Deine nächste Änderung erscheint hier.'))
        busy=self.busy();self.review_button.setEnabled(self.dirty() and not busy);self.discard_button.setEnabled((self.dirty() or bool(self.request.toPlainText())) and not busy)
        self.generate_button.setEnabled(not busy and bool(self.request.toPlainText().strip()) and self.preview is not None)
        for control in (self.name,self.purpose,self.source,self.request,self.apply_source,self.reload_button):control.setEnabled(not busy)
        self.stop_button.setVisible(busy)
        self.footer.setText(tr('Änderungen werden erst nach deiner Prüfung zur gespeicherten App.'))
        self.layout_columns()

    def mode_changed(self,*_):
        edit=self.mode.currentIndex()==1;self.editor.setVisible(edit);self.version.setVisible(edit)
        if edit and self.dirty():self.version.setCurrentIndex(1)
        self.refresh_preview();self.update_status()

    def refresh_preview(self,*_,capture=True):
        if not self.preview or self.closed:return
        self.switch+=1;token=self.switch
        draft=self.mode.currentIndex()==1 and self.version.currentIndex()==1
        source=self.value()['html'] if draft else self.saved_value()['html']
        self.preview_state.setText(tr('Entwurf · Änderungen ausprobieren' if draft else 'Gespeichert · Version {0}',self.item['revision']))
        def show(values):
            if self.closed or token!=self.switch:return
            if values:self.inputs=values
            if self.preview.source==source and self.preview.ready:return
            self.restore_pending=True;self.preview.set_source(source or '<p>'+tr('Beschreibe links deine App und erstelle die erste Fassung.')+'</p>')
        if capture:self.preview.snapshot(show)
        else:show([])

    def preview_loaded(self,ok):
        if ok and self.restore_pending:
            self.restore_pending=False;self.preview.restore(self.inputs)

    def preview_width(self):
        if self.preview:self.preview.setMaximumWidth(360 if self.width_choice.currentIndex() else 16777215)

    def reset_inputs(self):
        self.inputs=[]
        if self.preview:self.preview.source=None;self.refresh_preview(capture=False)

    def apply_code(self):
        try:check(self.value());self.persist();self.version.setCurrentIndex(1);self.refresh_preview();self.update_status()
        except ValueError as error:self.fail(error)

    def generate(self):
        if self.busy():return
        try:
            prompt=proposal(self.value()['html'],self.request.toPlainText())
            if not self.persist():return
            if self.engine is None:
                from assistant_backend import OpenCodeBackend
                folder=self.collection.store.directory/'app-edits'/self.item['id'];folder.mkdir(parents=True,exist_ok=True,mode=0o700)
                self.engine=OpenCodeBackend(folder,self,project_config=False);self.engine.completed.connect(self.generated)
            self.error.hide();self.engine.send(prompt,proposal=True,title='Lumen Kleine App');self.update_status()
            self.status.setText(tr('Lumen erstellt deinen Entwurf …'))
        except (ValueError,OSError,RuntimeError) as error:self.fail(error);self.update_status()

    def generated(self,success,result):
        if self.closed:return
        try:
            if not success:raise ValueError(tr('Erstellung fehlgeschlagen oder gestoppt. Die bisherige Fassung bleibt erhalten.'))
            value=parse_result(result);self.source.setPlainText(value['html']);self.draft['changes']=value['changes']
            self.persist();self.mode.setCurrentIndex(1);self.version.setCurrentIndex(1);self.refresh_preview()
        except ValueError as error:self.fail(error)
        self.update_status()

    def stop(self):
        if self.busy():self.engine.stop()

    def adopt(self):
        try:
            from code_library_execution import generated_html
            source=generated_html(self.collection,self.item['id']);self.source.setPlainText(source)
            self.draft['changes']=[tr('App-Inhalt aus dem abgeschlossenen Auftrag übernommen.')];self.apply_code();self.update_status()
        except (ValueError,OSError) as error:self.fail(error)

    def review(self):
        if self.busy() or not self.dirty():return
        try:
            from code_library_contract import definition
            value=self.value();definition('app',value['title'],value['description'],{'html':value['html']})
            if not value['html'].strip():raise ValueError(tr('Bitte zuerst eine App-Fassung erstellen und ausprobieren.'))
            if not self.persist():return
            reviewed=copy.deepcopy(self.draft);saved=self.saved_value()
            dialog=QDialog(self);dialog.setWindowTitle(tr('Lumen · Änderungen prüfen'));dialog.resize(780,420)
            box=QVBoxLayout(dialog);box.addWidget(label(tr('Neue App-Fassung übernehmen'),'codeCardTitle'))
            box.addWidget(label(tr('Prüfe die tatsächlichen Änderungen. Beim Benutzen gilt danach diese Fassung.'),'codeMuted'))
            details=QPlainTextEdit();details.setReadOnly(True);details.setAccessibleName(tr('Vorher und nachher'))
            metadata='\n\n'.join(tr('{0}\nBisher: {1}\nNeu: {2}',tr(title),saved[key],value[key]) for key,title in [('title','Name'),('description','Beschreibung')] if saved[key]!=value[key])
            diff='\n'.join(difflib.unified_diff(saved['html'].splitlines(),value['html'].splitlines(),fromfile=tr('Gespeichert'),tofile=tr('Entwurf'),lineterm=''))
            box.addWidget(label('\n'.join('• '+text for text in reviewed['changes']),'codeMuted'))
            if metadata:box.addWidget(label(metadata,'codeMuted'))
            toggle=QToolButton();toggle.setText(tr('App-Inhalt (HTML)'));toggle.setCheckable(True);toggle.setArrowType(Qt.RightArrow);toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);box.addWidget(toggle)
            details.setPlainText(diff);box.addWidget(details,1);details.hide()
            toggle.toggled.connect(lambda opened:(details.setVisible(opened),toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow),dialog.resize(780,650 if opened else 420)))
            box.addWidget(row(button(tr('Zurück'),dialog.reject),button(tr('Version speichern'),dialog.accept,primary=True)))
            if dialog.exec()!=QDialog.Accepted:return
            if self.value()!=reviewed['value'] or self.request.toPlainText()!=reviewed['request']:raise ValueError(tr('Der Entwurf wurde während der Prüfung geändert. Bitte erneut prüfen.'))
            self.autosave.stop();self.item=self.drafts.commit(reviewed);self.draft=self.drafts.open(self.item['id']);self.persisted=copy.deepcopy(self.draft);self.reset_fields();self.error.hide();self.update_status();self.refresh_preview()
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error)

    def discard(self,*_,confirm=True):
        if self.busy():return
        if confirm and QMessageBox.question(self,tr('Lumen · Änderungen verwerfen'),tr('Diesen Entwurf verwerfen? Die gespeicherte App und deine Beispieleingaben bleiben erhalten.'))!=QMessageBox.Yes:return
        try:
            self.autosave.stop();self.drafts.discard(self.draft);self.item=self.collection.get(self.item['id']);self.draft=self.drafts.open(self.item['id'])
            self.persisted=copy.deepcopy(self.draft)
            self.reset_fields();self.error.hide();self.update_status();self.refresh_preview()
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error)

    def reload_saved(self):
        if self.busy():return
        try:
            self.item=self.collection.get(self.item['id'])
            if self.item['archived']:raise ValueError(tr('Die App ist archiviert.'))
            self.draft['base_revision']=self.item['revision']
            if self.persist():self.error.hide();self.update_status();self.refresh_preview()
        except (ValueError,OSError,sqlite3.Error) as error:self.fail(error)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.layout_columns()

    def eventFilter(self,receiver,event):
        if event.type()==QEvent.Resize:QTimer.singleShot(0,self.layout_columns)
        return False

    def layout_columns(self,*_):
        if self.closed:return
        if hasattr(self,'columns'):
            compact=self.width()<1000 or self.body_area.viewport().height()<self.preview_panel.minimumSizeHint().height()
            self.columns.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
            body=self.body_area.widget()
            body.setMinimumHeight(0 if compact else self.body_area.viewport().height())
            body.setMaximumHeight(16777215 if compact else self.body_area.viewport().height())
            content=self.editor.widget();content.layout().activate()
            height=max(content.sizeHint().height(),content.layout().totalHeightForWidth(self.editor.viewport().width()))+12
            self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff if compact else Qt.ScrollBarAsNeeded)
            self.editor.setMinimumHeight(height if compact else 0)
            self.editor.setMaximumHeight(height if compact else 16777215)
            self.heading.setDirection(QBoxLayout.TopToBottom if self.width()<1000 else QBoxLayout.LeftToRight)
            self.findChild(QFrame,'codeRail').setVisible(self.width()>=800)

    def done(self,result):
        if self.closed:return
        if not self.persist():
            if QMessageBox.question(self,tr('Lumen · Entwurf nicht gespeichert'),tr('Der Entwurf konnte nicht gesichert werden. Trotzdem schließen und die Eingaben dieses Fensters verlieren?'))!=QMessageBox.Yes:return
        self.closed=True;self.autosave.stop()
        if self.engine:self.engine.shutdown()
        if self.preview:self.preview.shutdown()
        super().done(result)

    def reject(self):self.done(QDialog.Rejected)

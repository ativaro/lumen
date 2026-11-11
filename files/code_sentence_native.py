"""Sentence presentation of a file action over native steps; no runner conversion."""
import json
from html import escape
from PySide6.QtCore import QObject, QEvent, QTimer, Qt, QLocale
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)
from code_sentence_ui import SentenceFlow, SentencePart, STYLE
from code_design import STYLE as CODE_STYLE
from desktop_design import AppHeader, PAGE_SPACING
from lumen_actions import ACTIONS
from lumen_i18n import tr, language
from studio_design import font, icon
from tools_ui import button, label

PHRASES={'open':'eine Datei, einen Ordner oder eine Webseite öffnen','launch':'eine Anwendung starten',
         'layout':'Fenster nebeneinander anordnen','write':'eine Textdatei erstellen oder ersetzen',
         'copy':'eine Datei kopieren','diagnose':'den Systemzustand messen',
         'restart_service':'einen Dienst neu starten und prüfen','install_packages':'Pakete installieren und prüfen',
         'snapshot':'einen System-Snapshot anlegen'}
ICONS={'open':'document-open','launch':'system-run','layout':'view-split-left-right',
       'write':'document-save','copy':'edit-copy','diagnose':'utilities-system-monitor',
       'restart_service':'view-refresh','install_packages':'system-software-install','snapshot':'document-save-all'}


def part(text, callback, glyph, full_text=None):
    item=SentencePart(text,callback)
    # The shared helper snapshot exposes its first layout child as the icon label.
    item.layout().itemAt(0).widget().setPixmap(icon(glyph).pixmap(20,20))
    item.setToolTip('<qt>'+escape(full_text or text)+'</qt>')
    item.setAccessibleDescription(full_text or text)
    return item


def style_step(dialog, box, step):
    dialog.setWindowTitle(tr('Lumen · Aktion bearbeiten') if step else tr('Lumen · Aktion ergänzen'))
    dialog.setFont(font(14));dialog.resize(620,480)
    box.setContentsMargins(24,20,24,20);box.setSpacing(PAGE_SPACING)
    box.insertWidget(0,AppHeader(tr('Aktion bearbeiten') if step else tr('Aktion ergänzen')))
    dialog.form.setSpacing(12);dialog.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    dialog.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    for i in range(dialog.action.count()):
        dialog.action.setItemIcon(i,icon(ICONS[dialog.action.itemData(i)]))


class NativeSentence(QObject):
    def __init__(self,d,task,box):
        super().__init__(d);self.d=d;self.parts=[];self.shown=False
        d.setWindowTitle(tr('Eigene Dateiaktion'));d.resize(1040,720);d.setFont(font(14))
        d.setObjectName('codeShell');d.setStyleSheet(CODE_STYLE+STYLE);box.setSpacing(PAGE_SPACING)
        box.addWidget(AppHeader(tr('Eigene Dateiaktion'),tr('Eine Aktion, die du lesen kannst.')))
        d.name=QLineEdit(task.get('title',task.get('name','')));d.name.setPlaceholderText(tr('Name der Dateiaktion'))
        d.name.setAccessibleName(tr('Name'));d.name.setObjectName('codeFlowTitle');box.addWidget(d.name)
        self.scratch=QWidget(d);self.scratch.hide()
        d.steps=QListWidget(self.scratch);d.steps.setAccessibleName(tr('Native Schritte'))
        d.step_preview=QPlainTextEdit(self.scratch);d.step_preview.setReadOnly(True)
        d.steps.currentItemChanged.connect(lambda current,_:d.step_preview.setPlainText(self.description(current.data(Qt.UserRole)) if current else ''))
        for step in task.get('steps',[]):d.add_step_item(step)
        d.prompt=QPlainTextEdit(task.get('prompt',''),self.scratch);d.prompt.setAccessibleName(tr('KI-Auftrag'))
        d.roots=QListWidget(self.scratch)
        for root in task.get('roots',[]):self.add_root_item(d.roots,root)
        d.approve=QCheckBox(tr('Diese Schritte und Ordner freigeben'),self.scratch)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame)
        body=QWidget();content=QVBoxLayout(body);content.setContentsMargins(0,0,0,0);content.setSpacing(16)
        self.sentence=QFrame();self.sentence.setObjectName('sentence');self.lines=QVBoxLayout(self.sentence)
        self.lines.setContentsMargins(24,24,24,24);self.lines.setSpacing(12);content.addWidget(self.sentence)
        action_bar=QWidget();actions=SentenceFlow(action_bar)
        actions.addWidget(button(tr('Aktion ergänzen'),d.add_step,'list-add'))
        actions.addWidget(button(tr('KI-Auftrag bearbeiten'),self.prompt,'tools-wizard'))
        permissions=button(tr('Ordner & Freigabe').replace('&','&&'),self.permissions,'dialog-password')
        permissions.setAccessibleName(tr('Ordner & Freigabe'));actions.addWidget(permissions);content.addWidget(action_bar)
        content.addWidget(label(tr('Jeder hervorgehobene Satzteil ist bearbeitbar. Freigabedetails legst du bei Bedarf fest.'),'muted'))
        self.summary=label('','muted');content.addWidget(self.summary);content.addStretch();scroll.setWidget(body);box.addWidget(scroll,1)
        d.error=label('');d.error.setWordWrap(True);box.addWidget(d.error)
        footer=QVBoxLayout();hint=label(tr('Änderungen gelten erst nach dem Speichern.'),'muted');hint.setWordWrap(True);footer.addWidget(hint)
        buttons=QHBoxLayout();buttons.addStretch();buttons.addWidget(button(tr('Abbrechen'),d.reject))
        save=button(tr('Speichern'),d.save,'document-save',True);save.setDefault(True);buttons.addWidget(save);footer.addLayout(buttons);box.addLayout(footer)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        for signal in (d.name.textChanged,d.prompt.textChanged,d.steps.model().rowsInserted,d.steps.model().rowsRemoved,
                       d.steps.model().dataChanged,d.roots.model().rowsInserted,d.roots.model().rowsRemoved,d.approve.toggled):signal.connect(self.queue)
        self.baseline=self.snapshot();d.installEventFilter(self);self.refresh()

    def description(self,step):
        from plan_dialog import step_description
        return step_description(step)

    @staticmethod
    def add_root_item(view,path):
        item=QListWidgetItem(path);item.setData(Qt.UserRole,path);item.setToolTip('<qt>'+escape(path)+'</qt>');view.addItem(item)

    def snapshot(self):
        d=self.d
        return json.dumps([d.name.text(),[d.steps.item(i).data(Qt.UserRole) for i in range(d.steps.count())],
            d.prompt.toPlainText(),[d.roots.item(i).data(Qt.UserRole) for i in range(d.roots.count())],d.approve.isChecked()],sort_keys=True)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Show:
            if not self.shown:self.baseline=self.snapshot();self.shown=True
            self.queue()
        elif event.type()==QEvent.PaletteChange:self.queue()
        return False

    def queue(self,*_):self.timer.start(0)

    def refresh(self):
        while self.lines.count():
            item=self.lines.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.parts=[];self.menu_buttons=[];host=QWidget();flow=SentenceFlow(host);self.lines.addWidget(host);d=self.d
        def text(value):
            item=label(value,'sentenceText');flow.addWidget(item)
        def chip(value,callback,glyph,full_text=None):
            item=part(value,callback,glyph,full_text);flow.addWidget(item);self.parts.append(item);return item
        metrics=QFontMetrics(font(23))
        text(tr('Auf Knopfdruck'));text(tr('soll Lumen'))
        for i in range(d.steps.count()):
            step=d.steps.item(i).data(Qt.UserRole)
            if i:text(tr('und danach'))
            chip(tr(PHRASES[step['action']]),lambda index=i:self.edit(index),ICONS[step['action']])
            for key in ACTIONS[step['action']][1]:
                if key=='text':continue
                value=step[key]
                if key in ('source','path'):text(tr('von') if key=='source' else tr('nach') if step['action'] in ('copy','write') else tr('für'))
                value=tr('Benutzer') if key=='scope' and value=='user' else tr('System (Authentifizierung)') if key=='scope' else value
                path=key in ('source','path')
                caption=metrics.elidedText(value,Qt.ElideMiddle,480) if path and metrics.horizontalAdvance(value)>700 else value
                chip(caption,lambda index=i:self.edit(index),'folder' if path else ICONS[step['action']],value)
            more=button('⋯',lambda _=False,index=i:self.manage(index));more.setAccessibleName(tr('Aktion {0} verwalten',i+1));flow.addWidget(more);self.menu_buttons.append(more)
        if d.prompt.toPlainText().strip():
            if d.steps.count():text(tr('oder'))
            chip(tr('diesen KI-Auftrag ausführen'),self.prompt,'tools-wizard')
        elif not d.steps.count():chip(tr('eine Aktion ausführen'),d.add_step,'list-add')
        text('.')
        roots=tr('1 freigegebener Ordner') if d.roots.count()==1 else tr('{0} freigegebene Ordner',QLocale(language()).toString(d.roots.count()))
        self.summary.setText(roots+' · '+(tr('Freigabe bestätigt') if d.approve.isChecked() else tr('Freigabe noch erforderlich')))

    def edit(self,index):self.d.steps.setCurrentRow(index);self.d.edit_step()

    def manage(self,index):
        d=self.d;d.steps.setCurrentRow(index);menu=QMenu(d)
        edit=menu.addAction(icon('document-edit'),tr('Bearbeiten'));up=menu.addAction(icon('go-up'),tr('Nach oben'));down=menu.addAction(icon('go-down'),tr('Nach unten'));remove=menu.addAction(icon('list-remove'),tr('Entfernen'))
        up.setEnabled(index>0);down.setEnabled(index+1<d.steps.count())
        anchor=self.menu_buttons[index];chosen=menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        if chosen is edit:d.edit_step()
        elif chosen is up:d.move_step(-1)
        elif chosen is down:d.move_step(1)
        elif chosen is remove:d.steps.takeItem(index)
        menu.deleteLater()

    def detail(self,title):
        dialog=QDialog(self.d);dialog.setWindowTitle('Lumen · '+tr(title));dialog.setFont(font(14));dialog.resize(620,480)
        dialog.setObjectName('codeShell');dialog.setStyleSheet(CODE_STYLE)
        box=QVBoxLayout(dialog);box.setContentsMargins(24,20,24,20);box.setSpacing(16);box.addWidget(AppHeader(tr(title)))
        return dialog,box

    @staticmethod
    def detail_buttons(dialog,box):
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);box.addWidget(buttons)

    def permissions(self):
        d=self.d;dialog,box=self.detail('Ordner & Freigabe');roots=QListWidget();roots.setObjectName('codeSteps');roots.setAccessibleName(tr('Freigegebene Ordner'));roots.setWordWrap(True);box.addWidget(roots,1)
        for i in range(d.roots.count()):self.add_root_item(roots,d.roots.item(i).data(Qt.UserRole))
        row=QHBoxLayout()
        def add():
            path=QFileDialog.getExistingDirectory(dialog,tr('Ordner freigeben'))
            if path:self.add_root_item(roots,path)
        row.addWidget(button(tr('Ordner hinzufügen'),add,'folder-new'));row.addWidget(button(tr('Ordner entfernen'),lambda:roots.takeItem(roots.currentRow()),'list-remove'));row.addStretch();box.addLayout(row)
        approve=QCheckBox(d.approve.text());approve.setChecked(d.approve.isChecked());box.addWidget(approve)
        box.addWidget(label(tr('Freigabe gilt für genau diese gespeicherten Schritte. KI-Werkzeuge behalten ihre eigenen Rückfragen.'),'muted'));self.detail_buttons(dialog,box)
        if dialog.exec():
            d.roots.clear()
            for i in range(roots.count()):self.add_root_item(d.roots,roots.item(i).data(Qt.UserRole))
            d.approve.setChecked(approve.isChecked())
        dialog.deleteLater();self.refresh()

    def prompt(self):
        d=self.d;dialog,box=self.detail('KI-Auftrag bearbeiten');editor=QPlainTextEdit(d.prompt.toPlainText());editor.setAccessibleName(tr('KI-Auftrag'));box.addWidget(editor,1)
        box.addWidget(label(tr('Verwende entweder feste Schritte oder einen KI-Auftrag. KI-Werkzeuge behalten ihre eigenen Rückfragen.'),'muted'));self.detail_buttons(dialog,box)
        if dialog.exec():d.prompt.setPlainText(editor.toPlainText())
        dialog.deleteLater();self.refresh()

    def can_discard(self):
        d=self.d
        if d.value is not None or self.snapshot()==self.baseline:return True
        answer=QMessageBox.question(d,tr('Lumen · Entwurf schließen'),tr('Änderungen vor dem Schließen speichern?'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if answer==QMessageBox.Save:d.save();return False
        return answer==QMessageBox.Discard

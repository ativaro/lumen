"""Dedicated native forms for tools, routines and coding project setup."""
import json
from pathlib import Path
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPlainTextEdit,
    QCheckBox,QFileDialog,QButtonGroup,QFrame)
from tools_ui import button,label
from lumen_i18n import tr
from code_condition_ui import combo
from code_tool import INPUTS,OUTPUTS,instructions


def field(box,title,control):
    caption=label(tr(title));caption.setBuddy(control);control.caption=caption;box.addWidget(caption);control.setAccessibleName(tr(title));box.addWidget(control);return control


class ToolForm(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(12)
        self.columns=QHBoxLayout();self.columns.setSpacing(24);box.addLayout(self.columns)
        form=QWidget();box=QVBoxLayout(form);box.setContentsMargins(0,0,0,0);box.setSpacing(12);self.columns.addWidget(form,3)
        test=QFrame();test.setObjectName('codeLogic');self.test_box=QVBoxLayout(test);self.test_box.setContentsMargins(20,20,20,20);self.test_box.setSpacing(12);self.columns.addWidget(test,2)
        pair=QHBoxLayout();box.addLayout(pair)
        left=QVBoxLayout();right=QVBoxLayout();pair.addLayout(left,1);pair.addLayout(right,1)
        self.pair=pair
        self.input=field(left,'Eingabe',combo([(v,v) for v in INPUTS],'Text'))
        self.output=field(right,'Ergebnis',combo([(v,v) for v in OUTPUTS],'Checkliste'))
        self.request=field(box,'Was soll das Werkzeug tun?',QPlainTextEdit());self.request.setFixedHeight(100)
        self.request.setPlaceholderText(tr('Beschreibe einen wiederverwendbaren Auftrag.'))
        box.addWidget(label(tr('Regeln für jedes Ergebnis'),'codeCardTitle'));self.rules=[]
        for text in ('Fehlende Angaben kenntlich machen','Keine Fakten oder Zuständigkeiten erfinden','Möglichst knapp formulieren'):
            c=QCheckBox(tr(text));c.setChecked(len(self.rules)<2);box.addWidget(c);self.rules.append((c,text))
        self.test_box.addWidget(label(tr('Mit einem Beispiel prüfen'),'codeCardTitle'))
        self.test_box.addWidget(label(tr('Deine Beispieleingabe geht nach Bestätigung an die eingerichtete KI. Es werden keine Ergebnisaktionen ausgeführt.'),'codeMuted'))
        self.example=field(self.test_box,'Beispieleingabe für den Test',QPlainTextEdit());self.example.setFixedHeight(120)
        box.addWidget(label(tr('Du verwendest dieses Werkzeug später mit neuen Eingaben. Ergebnisse werden nicht ungefragt in anderen Apps abgelegt.'),'codeMuted'));box.addStretch()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.columns.setDirection(QHBoxLayout.TopToBottom if self.width()<760 else QHBoxLayout.LeftToRight)

    def value(self):
        request=self.request.toPlainText().strip()
        if not request:raise ValueError(tr('Bitte den Auftrag des Werkzeugs beschreiben.'))
        spec={'input':self.input.currentData(),'output':self.output.currentData(),'rules':[request]+[tr(text) for c,text in self.rules if c.isChecked()]}
        return {'tool_spec':json.dumps(spec,ensure_ascii=False),'prompt':instructions(spec)}


from code_sections_editor import SectionsEditor


class RoutineForm(SectionsEditor):
    def __init__(self,parent=None,tools=None,store=None):
        from code_triggers import project_choices
        super().__init__(parent,projects=project_choices(store) if store is not None else {},tools=tools,routine=True)

    def value(self):
        from code_flow import encode,prompt
        from code_block_paths import config
        plan=self.plan();source=config(plan['nodes'][0])
        if source['kind']=='text' and not source.get('text','').strip():raise ValueError(tr('Bitte Eingabetext oder eine Quelle für die Routine wählen.'))
        return {'flow':encode(plan),'prompt':prompt(plan),'editor':'routine'}


class CodeForm(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(12)
        box.addWidget(label(tr('Projektquelle'),'codeCardTitle'))
        self.source=combo([('folder','Ordner öffnen'),('repo','Repository klonen'),('new','Neu beginnen')],'folder');self.source.setParent(self);self.source.hide()
        self.sources=QHBoxLayout();box.addLayout(self.sources);self.source_buttons=[];self.source_group=QButtonGroup(self)
        for index,title in enumerate(('Ordner öffnen','Repository klonen','Neu beginnen')):
            control=button(tr(title),lambda _=False,i=index:self.source.setCurrentIndex(i));control.setCheckable(True);self.source_group.addButton(control);self.sources.addWidget(control,1);self.source_buttons.append(control)
        self.pair=QHBoxLayout();self.pair.setSpacing(24);box.addLayout(self.pair)
        left=QWidget();fields=QVBoxLayout(left);fields.setContentsMargins(0,0,0,0);fields.setSpacing(12);self.pair.addWidget(left,3)
        self.url=field(fields,'Repository-Adresse',QLineEdit());self.url.setPlaceholderText('https://… oder git@host:projekt.git')
        self.branch=field(fields,'Branch · optional',QLineEdit())
        self.directory=field(fields,'Projektordner',QLineEdit());self.directory.setPlaceholderText(tr('Einen lokalen Projektordner auswählen'))
        fields.addWidget(button(tr('Ordner auswählen'),self.choose_directory));self.info=label('','codeMuted');fields.addWidget(self.info);fields.addStretch()
        preview=QFrame();preview.setObjectName('codeLogic');inside=QVBoxLayout(preview);inside.setContentsMargins(16,16,16,16);inside.setSpacing(12);self.pair.addWidget(preview,2)
        inside.addWidget(label(tr('Dein Startpunkt'),'codeMuted'));self.preview_title=label('','codeCardTitle');inside.addWidget(self.preview_title);self.preview_path=label('','codeMuted');inside.addWidget(self.preview_path);inside.addWidget(label(tr('Gespräch, Projektdateien, Änderungen und tatsächliche Prüfergebnisse im nächsten Schritt.'),'codeMuted'));inside.addStretch()
        self.task=field(box,'Erster Auftrag · optional',QPlainTextEdit());self.task.setFixedHeight(100);self.task.setPlaceholderText(tr('Beschreibe, was Lumen in diesem Projekt ändern oder prüfen soll.'))
        self.source.currentIndexChanged.connect(self.refresh);self.directory.textChanged.connect(self.refresh);self.refresh();box.addStretch()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.pair.setDirection(QHBoxLayout.TopToBottom if self.width()<620 else QHBoxLayout.LeftToRight)
        self.sources.setDirection(QHBoxLayout.TopToBottom if sum(b.sizeHint().width() for b in self.source_buttons)+self.sources.spacing()*2>self.width() else QHBoxLayout.LeftToRight)

    def choose_directory(self):
        path=QFileDialog.getExistingDirectory(self,tr('Lumen · Projektordner auswählen'))
        if path:
            if self.source.currentData()!='folder':
                from PySide6.QtWidgets import QInputDialog
                name,ok=QInputDialog.getText(self,tr('Lumen · Neuer Projektordner'),tr('Name des neuen Ordners'))
                if not ok:return
                if not name.strip() or name in ('.','..') or '/' in name or '\\' in name:self.info.setText(tr('Einen einzelnen neuen Ordnernamen eingeben.'));return
                path=str(Path(path)/name.strip())
            self.directory.setText(path)

    def refresh(self,*_):
        repo=self.source.currentData()=='repo';self.url.setVisible(repo);self.branch.setVisible(repo);self.url.caption.setVisible(repo);self.branch.caption.setVisible(repo)
        for i,control in enumerate(self.source_buttons):control.setChecked(i==self.source.currentIndex())
        self.info.setText(tr('Projektordner ist verfügbar. Ein Gespräch öffnet sich nach der Prüfung.' if self.directory.text() and Path(self.directory.text()).is_dir() else 'Vorhandenen Projektordner auswählen.') if self.source.currentData()=='folder' else tr('Ein neuer, bisher nicht vorhandener Zielordner. Erst nach der Prüfung wird er angelegt.'))
        path=self.directory.text();self.preview_title.setText(Path(path).name if path else tr('Noch kein Projektordner'));self.preview_path.setText(path or tr('Wähle zuerst deine Projektquelle.'))

    def setup(self):
        from code_project_setup import validate
        return validate({'source':self.source.currentData(),'directory':self.directory.text(),'url':self.url.text(),'branch':self.branch.text()})

    def value(self):
        setup=self.setup();return {'directory':setup['directory'],'prompt':self.task.toPlainText().strip()}

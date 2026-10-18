"""Dedicated native forms for tools, routines and coding project setup."""
import json
from datetime import date
from pathlib import Path
from PySide6.QtCore import Qt,QDate,QTime
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QPlainTextEdit,
    QComboBox,QCheckBox,QSpinBox,QTimeEdit,QDateEdit,QFileDialog,QListWidget,QStackedWidget,QButtonGroup,QFrame)
from tools_ui import button,label,row
from lumen_i18n import tr
from code_condition_ui import combo
from code_clock import default,validate as validate_clock,describe as describe_clock,starts
from code_tool import INPUTS,OUTPUTS,instructions


def field(box,title,control):
    caption=label(tr(title));caption.setBuddy(control);control.caption=caption;box.addWidget(caption);control.setAccessibleName(tr(title));box.addWidget(control);return control


class ClockEditor(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(8)
        self.kind=field(box,'Start',combo([('weekly','Nach Wochenplan'),('daily','Jeden Tag'),('monthly','Monatlich'),('once','Einmalig'),('manual','Nur manuell')],'weekly'))
        self.time=field(box,'Uhrzeit',QTimeEdit(QTime(8,30)));self.time.setDisplayFormat('HH:mm')
        self.date=field(box,'Datum',QDateEdit(QDate.currentDate().addDays(1)));self.date.setCalendarPopup(True);self.date.setDisplayFormat('dd.MM.yyyy')
        self.month=field(box,'Tag im Monat',QSpinBox());self.month.setRange(1,31)
        self.days=[];self.days_widget=QWidget();days=QHBoxLayout(self.days_widget);days.setContentsMargins(0,0,0,0)
        for i,title in enumerate(('Mo','Di','Mi','Do','Fr','Sa','So')):
            c=QCheckBox(tr(title));c.setChecked(i<5);days.addWidget(c);self.days.append(c)
        box.addWidget(self.days_widget);self.summary=label('','codeMuted');box.addWidget(self.summary)
        self.kind.currentIndexChanged.connect(self.refresh);self.time.timeChanged.connect(self.refresh);self.date.dateChanged.connect(self.refresh);self.month.valueChanged.connect(self.refresh)
        for c in self.days:c.toggled.connect(self.refresh)
        self.refresh()

    def value(self):
        return validate_clock({**default(),'kind':self.kind.currentData(),'time':self.time.time().toString('HH:mm'),'date':self.date.date().toString('yyyy-MM-dd'),'month_day':self.month.value(),'days':[i for i,c in enumerate(self.days) if c.isChecked()]})

    def refresh(self,*_):
        kind=self.kind.currentData();self.time.setVisible(kind!='manual');self.date.setVisible(kind=='once');self.month.setVisible(kind=='monthly');self.days_widget.setVisible(kind=='weekly')
        for control in (self.time,self.date,self.month):control.caption.setVisible(not control.isHidden())
        try:self.summary.setText(describe_clock(self.value())+' · Europe/Zurich')
        except ValueError as error:self.summary.setText(tr(str(error)))


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


class RoutineForm(QWidget):
    def __init__(self,parent=None,tools=None,store=None):
        super().__init__(parent);self.steps=[];self.selected=-1;self.loading=False;self.store=store
        box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(12)
        self.pair=QHBoxLayout();self.pair.setSpacing(24);box.addLayout(self.pair);left=QWidget();right=QWidget();steps_box=QVBoxLayout(left);steps_box.setContentsMargins(0,0,0,0);steps_box.setSpacing(12);schedule_box=QVBoxLayout(right);schedule_box.setContentsMargins(0,0,0,0);schedule_box.setSpacing(12);self.pair.addWidget(left,3);self.pair.addWidget(right,2);box=steps_box
        box.addWidget(label(tr('Schritte der Routine'),'codeCardTitle'));self.list=QListWidget();self.list.setObjectName('codeSteps');self.list.setFixedHeight(64);self.list.setAccessibleName(tr('Schritte der Routine'));box.addWidget(self.list)
        order_widget=row(button(tr('Schritt ergänzen'),self.add),button(tr('Entfernen'),self.remove),button('↑',lambda:self.move(-1)),button('↓',lambda:self.move(1)))
        for i in (2,3):order_widget.layout().itemAt(i).widget().setFixedWidth(42)
        box.addWidget(order_widget)
        order=box.itemAt(box.count()-1).widget().layout();order.itemAt(2).widget().setAccessibleName(tr('Schritt nach oben'));order.itemAt(3).widget().setAccessibleName(tr('Schritt nach unten'))
        self.tools=field(box,'Gespeichertes Werkzeug',combo([('', 'Werkzeug wählen')]+[(t['id'],t['title']) for t in tools or []],''));self.tool_records={t['id']:t for t in tools or []};self.tools.activated.connect(self.use_tool)
        self.title=field(box,'Schritttitel',QLineEdit());self.prompt=field(box,'Auftrag des Schritts',QPlainTextEdit());self.prompt.setMaximumHeight(100)
        self.list.currentRowChanged.connect(self.select);self.title.textEdited.connect(self.edited);self.prompt.textChanged.connect(self.edited)
        source_box=QWidget();source_layout=QVBoxLayout(source_box);source_layout.setContentsMargins(0,0,0,0);self.source=field(source_layout,'Dateien lesen aus · optional',QLineEdit());self.source.setReadOnly(True);source_layout.addWidget(button(tr('Ordner auswählen'),self.choose_source));source_layout.addWidget(label(tr('Ein ausgewählter Ordner wird bei der Aktivierung ausdrücklich freigegeben.'),'codeMuted'));source_box.hide();source_toggle=button(tr('Dateien als Quelle hinzufügen · optional'),lambda:source_box.setVisible(not source_box.isVisible()));source_toggle.setObjectName('codeLink');box.addWidget(source_toggle);box.addWidget(source_box);box.addStretch();box=schedule_box
        box.addWidget(label(tr('Wann startet sie?'),'codeCardTitle'));self.clock=ClockEditor(self);box.addWidget(self.clock)
        self.notify=QCheckBox(tr('Ergebnis in Lumen melden'));self.notify.setChecked(True);box.addWidget(self.notify)
        self.note=QCheckBox(tr('Ergebnis als neue Notes-Notiz speichern'));box.addWidget(self.note)
        self.condition=field(box,'Ergebnis weitergeben',combo([('changed','Nur bei verändertem Ergebnis'),('always','Nach jeder Ausführung')],'changed'));box.addStretch()
        self.add()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.pair.setDirection(QHBoxLayout.TopToBottom if self.width()<660 else QHBoxLayout.LeftToRight)

    def choose_source(self):
        path=QFileDialog.getExistingDirectory(self,tr('Lumen · Routineordner auswählen'))
        if path:self.source.setText(path)

    def select(self,index):
        self.selected=index;self.loading=True;step=self.steps[index] if 0<=index<len(self.steps) else {'title':'','prompt':''};self.title.setText(step['title']);self.prompt.setPlainText(step['prompt']);self.loading=False

    def edited(self):
        if self.loading or self.selected<0:return
        step=self.steps[self.selected];step.update(title=self.title.text(),prompt=self.prompt.toPlainText());step.pop('tool_id',None);step.pop('tool_revision',None);self.list.item(self.selected).setText(str(self.selected+1)+'. '+(self.title.text() or tr('Neuer Schritt')))

    def refresh(self,index):
        self.list.blockSignals(True);self.list.clear();self.list.addItems([str(i+1)+'. '+s['title'] for i,s in enumerate(self.steps)]);self.list.setFixedHeight(min(5,max(1,len(self.steps)))*38+12);self.list.blockSignals(False);self.list.setCurrentRow(index);self.select(index)

    def add(self):
        if len(self.steps)<5:self.steps.append({'title':tr('Neuer Schritt'),'prompt':''});self.refresh(len(self.steps)-1)

    def remove(self):
        if self.selected>=0:self.steps.pop(self.selected);self.refresh(min(self.selected,len(self.steps)-1))

    def move(self,delta):
        target=self.selected+delta
        if 0<=self.selected<len(self.steps) and 0<=target<len(self.steps):self.steps[self.selected],self.steps[target]=self.steps[target],self.steps[self.selected];self.refresh(target)

    def use_tool(self):
        tool=self.tool_records.get(self.tools.currentData())
        if tool and len(self.steps)==1 and not self.steps[0]['prompt'].strip():self.steps=[]
        if tool and len(self.steps)<5:self.steps.append({'title':tool['title'],'prompt':tool['definition']['prompt'],'tool_id':tool['id'],'tool_revision':tool['revision']});self.refresh(len(self.steps)-1);self.tools.setCurrentIndex(0)

    def value(self):
        from code_flow import encode,prompt
        clock=self.clock.value();kind=clock['kind']
        if kind!='manual' and not starts(clock):raise ValueError(tr('Bitte eine zukünftige Startzeit wählen.'))
        directory=self.source.text()
        if directory and not Path(directory).is_dir():raise ValueError(tr('Der ausgewählte Ordner ist nicht verfügbar.'))
        outputs=[k for k,c in [('notify',self.notify),('note',self.note)] if c.isChecked()]
        if not outputs:raise ValueError(tr('Mindestens eine Ergebnisaktion auswählen.'))
        plan=dict(trigger='manual' if kind=='manual' else 'schedule',minutes=clock['minutes'],watch='',cron='',timezone='Europe/Zurich',clock=clock,steps=self.steps,condition=self.condition.currentData(),outputs=outputs,source_ids=[],service_ids=[])
        if self.note.isChecked():
            target=self.store.setting('knowledge/notebook','') if self.store else ''
            if not target:raise ValueError(tr('Für Notizen zuerst in Lumen Notes einen Notizordner wählen.'))
            plan['note_root']=target
        return {'flow':encode(plan),'prompt':prompt(plan),**({'directory':directory} if directory else {})}


class CodeForm(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(12)
        box.addWidget(label(tr('Projektquelle'),'codeCardTitle'))
        self.source=combo([('folder','Ordner öffnen'),('repo','Repository klonen'),('new','Neu beginnen')],'folder');self.source.setParent(self);self.source.hide()
        sources=QHBoxLayout();box.addLayout(sources);self.source_buttons=[];self.source_group=QButtonGroup(self)
        for index,title in enumerate(('Ordner öffnen','Repository klonen','Neu beginnen')):
            control=button(tr(title),lambda _=False,i=index:self.source.setCurrentIndex(i));control.setCheckable(True);self.source_group.addButton(control);sources.addWidget(control,1);self.source_buttons.append(control)
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

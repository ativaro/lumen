"""Wenn–Dann editing against the actual local timer and foreground task engine."""
from pathlib import Path
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSpinBox,QLineEdit,QFileDialog,QListWidget,QPlainTextEdit,QCheckBox,QDialog,QDialogButtonBox,QScrollArea)
from lumen_i18n import tr
from tools_ui import button
from code_flow import encode,parse


class FlowEditor(QWidget):
    def __init__(self,parent=None,plan=None,tools=None):
        super().__init__(parent);self.steps=[];self.selected=-1;self.loading=False
        from code_design import logic
        from tools_ui import label
        box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(8)
        trigger=logic(box,'Wenn','Wodurch soll der Ablauf starten?')
        self.trigger=QComboBox();self.trigger.setAccessibleName(tr('Auslöser'));self.trigger.addItem(tr('Ein Zeitintervall vergangen ist'),'interval');self.trigger.addItem(tr('Sich ein gewählter Ordner ändert'),'directory');trigger_row=QHBoxLayout();trigger_row.addWidget(self.trigger,1);trigger.addLayout(trigger_row)
        self.minutes=QSpinBox();self.minutes.setAccessibleName(tr('Intervall in Minuten'));self.minutes.setRange(15,525600);self.minutes.setSuffix(tr(' Minuten'));self.minutes.setValue(1440);trigger_row.addWidget(self.minutes)
        self.watch_row=QWidget();row=QHBoxLayout(self.watch_row);row.setContentsMargins(0,0,0,0)
        self.watch=QLineEdit();self.watch.setAccessibleName(tr('Beobachteter Ordner'));self.watch.setPlaceholderText(tr('Beobachteten Ordner ausdrücklich auswählen'));row.addWidget(self.watch,1);row.addWidget(button(tr('Ordner wählen'),self.choose));trigger.addWidget(self.watch_row)
        box.addWidget(label('↓','codeJoin'))
        steps=logic(box,'Dann','Arbeitsschritte in dieser Reihenfolge')
        work=QHBoxLayout();work.setSpacing(16);steps.addLayout(work)
        order=QVBoxLayout();order.setSpacing(8);work.addLayout(order,1);instruction=QVBoxLayout();instruction.setSpacing(8);work.addLayout(instruction,2)
        self.list=QListWidget();self.list.setObjectName('codeSteps');self.list.setMinimumHeight(76);self.list.setMaximumHeight(116);self.list.setAccessibleName(tr('Arbeitsschritte'));order.addWidget(self.list)
        row=QHBoxLayout();order.addLayout(row)
        order.addWidget(button(tr('Schritt hinzufügen'),self.add,'list-add'));row.addWidget(button(tr('Entfernen'),self.remove));row.addWidget(button('↑',lambda:self.move(-1)));row.addWidget(button('↓',lambda:self.move(1)))
        row.itemAt(1).widget().setAccessibleName(tr('Nach oben'));row.itemAt(2).widget().setAccessibleName(tr('Nach unten'));order.addStretch()
        self.tools=QComboBox();self.tools.setAccessibleName(tr('Gespeichertes Werkzeug übernehmen'));self.tools.addItem(tr('Gespeichertes Werkzeug als Schritt übernehmen'),None)
        for tool in tools or []:
            if tool['definition'].get('prompt'):self.tools.addItem(tool['title'],tool)
        self.tools.currentIndexChanged.connect(self.use_tool);instruction.addWidget(self.tools)
        instruction.addWidget(label(tr('Schritttitel')));self.title=QLineEdit();self.title.setAccessibleName(tr('Schritttitel'));self.title.setMaxLength(160);instruction.addWidget(self.title)
        instruction.addWidget(label(tr('Auftrag des Schritts')));self.prompt=QPlainTextEdit();self.prompt.setAccessibleName(tr('Auftrag des Schritts'));self.prompt.setMinimumHeight(100);self.prompt.setMaximumHeight(130);instruction.addWidget(self.prompt)
        box.addWidget(label('↓','codeJoin'))
        outputs=logic(box,'Danach','Mit dem tatsächlichen Ergebnis')
        self.condition=QComboBox();self.condition.setAccessibleName(tr('Ergebnis weitergeben'));self.condition.addItem(tr('Bei jedem erfolgreichen Durchlauf'),'always');self.condition.addItem(tr('Nur wenn sich das Ergebnis geändert hat'),'changed');outputs.addWidget(self.condition)
        self.notify=QCheckBox(tr('In Lumen melden'));self.notify.setChecked(True);outputs.addWidget(self.notify);self.draft=QCheckBox(tr('Aufgabenentwurf vorbereiten'));outputs.addWidget(self.draft)
        outputs.addWidget(label(tr('KI-Schritte warten auf Lumen im Vordergrund und behalten ihre Werkzeugfreigaben. Ein Aufgabenentwurf wird nicht automatisch ausgeführt. Übernommene Werkzeuge bleiben in dieser geprüften Fassung.'),'codeMuted'))
        self.list.currentRowChanged.connect(self.select);self.title.textEdited.connect(self.changed);self.prompt.textChanged.connect(self.changed)
        self.trigger.currentIndexChanged.connect(self.update_trigger)
        self.set_plan(plan)

    def update_trigger(self,*_):
        directory=self.trigger.currentData()=='directory';self.watch_row.setVisible(directory);self.minutes.setVisible(not directory)

    def choose(self):
        value=QFileDialog.getExistingDirectory(self,tr('Lumen · Ordner auswählen'))
        if value:self.watch.setText(value)

    def changed(self):
        if self.loading or self.selected<0:return
        self.steps[self.selected]={'title':self.title.text(),'prompt':self.prompt.toPlainText()}
        self.list.item(self.selected).setText(str(self.selected+1)+'   '+(self.title.text() or tr('Neuer Schritt')))

    def select(self,index):
        self.selected=index;self.loading=True
        step=self.steps[index] if index>=0 else {'title':'','prompt':''}
        self.title.setText(step['title']);self.prompt.setPlainText(step['prompt']);self.loading=False

    def refresh(self,index):
        self.selected=-1;self.list.blockSignals(True);self.list.clear();self.list.addItems([str(i+1)+'   '+(s['title'] or tr('Neuer Schritt')) for i,s in enumerate(self.steps)]);self.list.blockSignals(False);self.list.setCurrentRow(index)

    def add(self):
        if len(self.steps)>=5:return
        self.steps.append({'title':tr('Neuer Schritt'),'prompt':''});self.refresh(len(self.steps)-1)

    def remove(self):
        if self.selected<0:return
        index=self.selected;self.steps.pop(index);self.refresh(min(index,len(self.steps)-1))

    def move(self,offset):
        index=self.selected;target=index+offset
        if index<0 or not 0<=target<len(self.steps):return
        self.steps[index],self.steps[target]=self.steps[target],self.steps[index];self.refresh(target)

    def use_tool(self,index):
        tool=self.tools.itemData(index)
        if not tool or len(self.steps)>=5:return
        self.steps.append({'title':tool['title'],'prompt':tool['definition']['prompt'],'tool_id':tool['id'],'tool_revision':tool['revision']});self.refresh(len(self.steps)-1);self.tools.setCurrentIndex(0)

    def set_plan(self,plan=None):
        plan=plan or {};self.steps=[dict(s) for s in plan.get('steps',[{'title':tr('Prüfen'),'prompt':''}])]
        self.trigger.setCurrentIndex(max(0,self.trigger.findData(plan.get('trigger','interval'))));self.minutes.setValue(plan.get('minutes',1440));self.watch.setText(plan.get('watch',''))
        self.condition.setCurrentIndex(max(0,self.condition.findData(plan.get('condition','always'))));self.notify.setChecked('notify' in plan.get('outputs',['notify']));self.draft.setChecked('task_draft' in plan.get('outputs',[]));self.refresh(0 if self.steps else -1);self.update_trigger()

    def plan(self,validate=True):
        value=dict(trigger=self.trigger.currentData(),minutes=self.minutes.value(),watch=self.watch.text() if self.trigger.currentData()=='directory' else '',cron='0 9 * * *',timezone='Europe/Zurich',steps=self.steps,condition=self.condition.currentData(),outputs=[key for key,control in [('notify',self.notify),('task_draft',self.draft)] if control.isChecked()],source_ids=[],service_ids=[])
        if validate:
            parse(encode(value))
            if value['trigger']=='directory' and not Path(value['watch']).expanduser().is_dir():raise ValueError(tr('Bitte einen verfügbaren Ordner auswählen.'))
        return value


class FlowDialog(QDialog):
    def __init__(self,parent,item,tools):
        super().__init__(parent);self.setWindowTitle(tr('Lumen · Automation prüfen'));self.resize(820,820);self.setObjectName('codeShell')
        from code_design import STYLE
        self.setStyleSheet(STYLE);box=QVBoxLayout(self);box.setContentsMargins(24,20,24,20);box.setSpacing(16)
        self.editor=FlowEditor(self,parse(item['definition']['flow']),tools);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.editor);box.addWidget(scroll)
        self.approve=QCheckBox(tr('Diese Schritte, Quellen und Ergebnisaktionen freigeben'));box.addWidget(self.approve)
        self.error=QLabel();self.error.setWordWrap(True);box.addWidget(self.error)
        row=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);row.accepted.connect(self.save);row.rejected.connect(self.reject);box.addWidget(row)

    def save(self):
        try:
            if not self.approve.isChecked():raise ValueError(tr('Bitte den Ablauf zuerst prüfen und ausdrücklich freigeben.'))
            self.value=encode(self.editor.plan());self.accept()
        except ValueError as error:self.error.setText(str(error))

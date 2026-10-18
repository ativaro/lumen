"""Linked native blocks and one inspector, shared by creation and execution."""
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QSize
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QLineEdit,QPlainTextEdit,QTabWidget,QSplitter,QMenu,QFileDialog,QMessageBox,QStyledItemDelegate,QScrollArea)
from tools_ui import button,label
from lumen_i18n import tr
from code_blocks import LEGACY_KINDS,CATALOG,LATER,starter,node,parse,generated

STATES={'pending':'Bereit','running':'Läuft','completed':'Erledigt','waiting':'Braucht dich','error':'Fehler','skipped':'Übersprungen','paused':'Pausiert','cancelled':'Abgebrochen'}
STYLE='''
QListWidget#blockList { background: transparent; border: none; outline: none; }
QListWidget#blockList::item { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; margin: 0 6px 12px 0; padding: 13px 16px; }
QListWidget#blockList::item:selected { background: palette(alternate-base); border: 2px solid palette(highlight); color: palette(text); }
QWidget#blockInspector { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
QWidget#blockInspector QLabel { background: transparent; border: none; }
QLabel#blockHeading { font-size: 17px; font-weight: 600; }
QWidget#blockInspector QTabBar::tab { padding: 8px; margin-right: 0; min-width: 0; }
QPlainTextEdit#blockIO { font-family: monospace; font-size: 11px; }
'''


class Connections(QStyledItemDelegate):
    def paint(self,painter,option,index):
        super().paint(painter,option,index)
        if index.row()<index.model().rowCount()-1:
            painter.save();painter.setPen(option.palette.link().color())
            painter.drawText(option.rect.adjusted(0,option.rect.height()-14,-6,0),Qt.AlignCenter,'↓');painter.restore()


class BlockEditor(QWidget):
    changed=Signal()
    def __init__(self,parent=None,plan=None):
        super().__init__(parent);self.nodes=[];self.selected=-1;self.loading=False;self.run=None;self.engine=None;self.locked=False
        self.setStyleSheet(STYLE)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(12)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        canvas=QWidget();layout=QVBoxLayout(canvas);layout.setContentsMargins(0,14,0,0);layout.setSpacing(12)
        head=QHBoxLayout();head.addWidget(label(tr('DEIN ABLAUF'),'codeEyebrow'));head.addStretch();self.add_button=button(tr('+ Baustein'),self.catalog);head.addWidget(self.add_button);layout.addLayout(head)
        self.splitter=QSplitter();layout.addWidget(self.splitter,1)
        left=QWidget();box=QVBoxLayout(left);box.setContentsMargins(0,0,0,0);box.setSpacing(8)
        self.list=QListWidget();self.list.setObjectName('blockList');self.list.setAccessibleName(tr('Ablaufbausteine'));self.list.setMinimumWidth(240);self.list.setItemDelegate(Connections(self.list));box.addWidget(self.list,1)
        row=QHBoxLayout();self.up=button('↑',lambda:self.move(-1));self.up.setAccessibleName(tr('Baustein nach oben'));row.addWidget(self.up)
        self.down=button('↓',lambda:self.move(1));self.down.setAccessibleName(tr('Baustein nach unten'));row.addWidget(self.down)
        self.remove_button=button(tr('Entfernen'),self.remove);row.addWidget(self.remove_button);row.addStretch();box.addLayout(row);self.splitter.addWidget(left)
        self.inspector=QWidget();self.inspector.setObjectName('blockInspector');self.inspector.setMinimumWidth(260)
        box=QVBoxLayout(self.inspector);box.setContentsMargins(18,18,18,18);box.setSpacing(10)
        self.group=label('','codeEyebrow');box.addWidget(self.group);self.heading=label('','blockHeading');box.addWidget(self.heading)
        self.help=label('','codeMuted');box.addWidget(self.help)
        settings=QWidget();fields=QVBoxLayout(settings);fields.setContentsMargins(0,10,0,0);fields.setSpacing(10)
        fields.addWidget(label(tr('Name')));self.title=QLineEdit();self.title.setMaxLength(160);self.title.setAccessibleName(tr('Bausteinname'));fields.addWidget(self.title)
        self.config_label=label(tr('Einstellung'));fields.addWidget(self.config_label)
        self.config=QPlainTextEdit();self.config.setAccessibleName(tr('Bausteineinstellung'));self.config.setMinimumHeight(90);fields.addWidget(self.config)
        self.choose=button(tr('Auswählen …'),self.choose_path,'document-open');fields.addWidget(self.choose);fields.addStretch()
        self.io=QTabWidget();self.input=QPlainTextEdit();self.output=QPlainTextEdit()
        for view in (self.input,self.output):view.setReadOnly(True);view.setObjectName('blockIO');view.setMinimumHeight(90)
        self.input.setAccessibleName(tr('Tatsächliche Eingabe'));self.output.setAccessibleName(tr('Tatsächliches Ergebnis'))
        settings_scroll=QScrollArea();settings_scroll.setWidgetResizable(True);settings_scroll.setWidget(settings)
        self.io.addTab(settings_scroll,tr('Einstellung'));self.io.addTab(self.input,tr('Eingabe'));self.io.addTab(self.output,tr('Ergebnis'));box.addWidget(self.io,1)
        self.node_status=label('','codeMuted');box.addWidget(self.node_status);self.splitter.addWidget(self.inspector);self.splitter.setSizes([480,310])
        self.tabs.addTab(canvas,tr('Bausteine'))
        describe=QWidget();box=QVBoxLayout(describe);box.setContentsMargins(18,18,18,18);box.setSpacing(14)
        box.addWidget(label(tr('Beschreibe deinen Ablauf'),'blockHeading'));box.addWidget(label(tr('Lumen erstellt dieselben bearbeitbaren Bausteine. Quellen und Ziele wählst du anschließend selbst.'),'codeMuted'))
        self.description=QPlainTextEdit();self.description.setAccessibleName(tr('Ablaufbeschreibung'));self.description.setPlaceholderText(tr('Lies eine Datei, fasse sie zusammen und speichere nach meiner Bestätigung eine Notiz.'));box.addWidget(self.description,1)
        self.describe_button=button(tr('Bausteine mit KI entwerfen'),self.describe,primary=True);box.addWidget(self.describe_button,0,Qt.AlignLeft)
        self.description_status=label('','codeMuted');box.addWidget(self.description_status)
        box.addWidget(label(tr('Noch nicht verfügbar: Drive-Ereignisse, Zeitpläne, weitere App-Auslöser, Schleifen und Serverausführung. Bestehende Zeitabläufe bleiben separat erhalten.'),'codeMuted'))
        self.tabs.addTab(describe,tr('Beschreiben'))
        self.list.currentRowChanged.connect(self.select);self.title.textEdited.connect(self.edited);self.config.textChanged.connect(self.edited)
        self.set_plan(plan)

    def set_plan(self,plan=None):
        self.nodes=parse(plan or starter())['nodes'];self.refresh(0)

    def plan(self,validate=True):
        value=dict(version=2,nodes=self.nodes)
        return parse(value) if validate else json.loads(json.dumps(value))

    def refresh(self,index=None):
        if index is None:index=self.selected
        self.loading=True;self.list.clear()
        states={n['id']:s for n,s in zip(self.run['plan']['nodes'],self.run['data']['steps'])} if self.run else {}
        for i,n in enumerate(self.nodes):
            group,title,help=CATALOG[n['kind']];step=states.get(n['id'],{});status=tr(STATES.get(step.get('status','pending'),'Bereit'))
            subtitle=n['config'].replace('\n',' ') or tr(help)
            if len(subtitle)>62:subtitle=subtitle[:59]+'…'
            item=QListWidgetItem(f"{i+1:02d}   {tr(n['title'])}\n{tr(group)} · {status}"+(' · '+tr('KI') if n['kind']=='ai' else ' · '+tr('Direkt'))+'\n'+subtitle)
            from studio_design import icon
            item.setIcon(icon({'manual':'media-playback-start','read_file':'document-open','ai':'tools-wizard','approval':'dialog-question','save_file':'document-save','save_note':'document-new','create_task':'view-task','notify':'notifications','if_pdf':'view-filter'}[n['kind']]))
            item.setSizeHint(QSize(250,96));item.setToolTip(tr(help));self.list.addItem(item)
        self.loading=False;self.list.setCurrentRow(min(max(0,index),len(self.nodes)-1));self.select(self.list.currentRow())

    def select(self,index):
        if self.loading or not 0<=index<len(self.nodes):return
        self.selected=index;n=self.nodes[index];group,title,help=CATALOG[n['kind']];self.loading=True
        self.group.setText(tr(group).upper());self.heading.setText(tr(title));self.help.setText(tr(help));self.title.setText(tr(n['title']));self.config.setPlainText(n['config'])
        kind=n['kind'];editable=kind in ('read_file','save_file','ai','save_note','create_task')
        self.config.setVisible(editable);self.config_label.setVisible(editable);self.choose.setVisible(kind in ('read_file','save_file'))
        self.config.setReadOnly(kind in ('read_file','save_file'))
        self.config_label.setText(tr('Ausgewählte Datei') if kind=='read_file' else tr('Zielordner') if kind=='save_file' else tr('Auftrag') if kind=='ai' else tr('Titel für das Ergebnis'))
        self.up.setEnabled(not self.locked and index>1);self.down.setEnabled(not self.locked and index>0 and index<len(self.nodes)-1);self.remove_button.setEnabled(not self.locked and index>0 and len(self.nodes)>2)
        step=next((s for node,s in zip(self.run['plan']['nodes'],self.run['data']['steps']) if node['id']==n['id']),None) if self.run else None
        for field,key in [(self.input,'input'),(self.output,'output')]:field.setPlainText(json.dumps(step[key],ensure_ascii=False,indent=2) if step and step[key] else tr('Noch kein Durchlauf. Hier erscheinen die tatsächlichen Daten.'))
        self.node_status.setText((tr(STATES[step['status']])+' · '+tr('Versuche: {0}',step['attempts'])+('\n'+step['error'] if step['error'] else '')) if step else tr('Wird erst beim Start ausgeführt.'))
        self.loading=False

    def edited(self):
        if self.loading or self.locked or self.selected<0:return
        n=self.nodes[self.selected];n['title']=self.title.text();n['config']=self.config.toPlainText()
        self.changed.emit()
        # Keep focus and clicks intact while editing the inspector.
        item=self.list.item(self.selected)
        if item:item.setText(f"{self.selected+1:02d}   {n['title']}\n{tr(CATALOG[n['kind']][0])} · {tr('Geändert')}\n{n['config'][:62]}")

    def catalog(self):
        menu=QMenu(self)
        for group in ('Start','Verarbeiten','Handeln','Steuern'):
            submenu=menu.addMenu(tr(group))
            for kind,(category,title,help) in CATALOG.items():
                if category!=group or kind not in LEGACY_KINDS:continue
                action=submenu.addAction(tr(title));action.setToolTip(tr(help));action.setEnabled(kind!='manual' and len(self.nodes)<14)
                action.triggered.connect(lambda _=False,k=kind:self.add(k))
            for title in LATER.get(group,[]):
                action=submenu.addAction(tr(title)+' · '+tr('Später'));action.setEnabled(False)
        menu.exec(self.add_button.mapToGlobal(self.add_button.rect().bottomLeft()))

    def add(self,kind):
        if self.locked or len(self.nodes)>=14:return
        index=self.selected+1;self.nodes.insert(index,node(kind));self.refresh(index);self.changed.emit()

    def remove(self):
        if self.locked or self.selected<=0 or len(self.nodes)<=2:return
        index=self.selected;self.nodes.pop(index);self.refresh(index-1);self.changed.emit()

    def move(self,delta):
        target=self.selected+delta
        if self.locked or self.selected<=0 or not 0<target<len(self.nodes):return
        self.nodes[self.selected],self.nodes[target]=self.nodes[target],self.nodes[self.selected];self.refresh(target);self.changed.emit()

    def choose_path(self):
        kind=self.nodes[self.selected]['kind']
        path=QFileDialog.getExistingDirectory(self,tr('Lumen · Ergebnisordner auswählen')) if kind=='save_file' else QFileDialog.getOpenFileName(self,tr('Lumen · Quelldatei auswählen'),'',tr('Dokumente (*.pdf *.txt *.md *.csv *.png *.jpg *.jpeg *.webp *.tif *.tiff)'))[0]
        if path:self.config.setPlainText(path)

    def set_locked(self,locked):
        self.locked=locked
        for widget in (self.title,self.config,self.choose,self.add_button,self.description,self.describe_button):widget.setEnabled(not locked)
        self.select(self.selected)

    def describe(self):
        text=self.description.toPlainText().strip()
        if not text or len(text)>8000:self.description_status.setText(tr('Bitte den Ablauf in höchstens 8.000 Zeichen beschreiben.'));return
        if QMessageBox.question(self,tr('Lumen · Ablauf entwerfen'),tr('Beschreibung an den eingerichteten KI-Anbieter senden und die bisherigen Bausteine durch den Vorschlag ersetzen?'))!=QMessageBox.Yes:return
        if self.engine is None:
            from assistant_backend import OpenCodeBackend
            self.temporary=tempfile.TemporaryDirectory(prefix='lumen-block-design-')
            self.engine=OpenCodeBackend(self.temporary.name,self,project_config=False);self.engine.completed.connect(self.described)
        self.set_locked(True);self.description_status.setText(tr('Bausteine werden entworfen …'))
        prompt='Erstelle ausschließlich JSON {"nodes":[{"kind":"manual","title":"Start","config":""}, ...]}. Erster und einziger Start manual, 2 bis 14 Bausteine. Verfügbare Typen: '+json.dumps({k:v for k,v in CATALOG.items() if k in LEGACY_KINDS},ensure_ascii=False)+'. config nur für ai als Auftrag füllen; alle Pfade und Ziele leer lassen. Kein Baustein außerhalb dieses Katalogs. Wenn die Anforderung nicht unterstützt ist: {"error":"Grund"}. Beschreibung:\n'+text
        self.engine.send(prompt,proposal=True,title='Lumen Automation')

    def described(self,success,result):
        self.set_locked(False)
        try:
            if not success:raise ValueError(result)
            self.set_plan(generated(result));self.changed.emit();self.tabs.setCurrentIndex(0);self.description_status.setText(tr('Entwurf erstellt. Quellen und Ziele bitte auswählen.'))
        except Exception as error:self.description_status.setText(str(error))

    def shutdown(self):
        if self.engine:self.engine.shutdown()
        if hasattr(self,'temporary'):self.temporary.cleanup()

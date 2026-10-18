"""Panorama automation editor: When, optional conditions, collapsed action blocks."""
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QScrollArea,QTabWidget,
    QLineEdit,QPlainTextEdit,QComboBox,QCheckBox,QFileDialog,QMessageBox,QPushButton,QDoubleSpinBox,QSpinBox,QTimeEdit,QDateEdit)
from tools_ui import button,label,row
from lumen_i18n import tr
from code_blocks import node,CATALOG,parse
from code_block_paths import starter,tree,flatten,available,config,SOURCE_FIELDS,BASE_FIELDS
from code_condition_ui import ConditionEditor,combo
from code_blocks_editor import STATES


class SectionsEditor(QWidget):
    changed=Signal()
    def __init__(self,parent=None,plan=None,projects=None,tools=None,routine=False):
        super().__init__(parent);self.routine=routine;self.run=None;self.engine=None;self.locked=False;self.open_ids=set();self.getters=[];self.projects=projects or {};self.tools=tools or []
        self.temporary=None;self.proposal_condition=None;self.closed=False;self.full_engine=None;self.full_directory=None;self.full_candidate=None
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(12)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();self.tabs.setAccessibleName(tr('Ablauf und Formulierungshilfe'));root.addWidget(self.tabs)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.tabs.addTab(self.scroll,tr('Bausteine'))
        describe=QWidget();box=QVBoxLayout(describe);box.setSpacing(12)
        box.addWidget(button(tr('‹ Zurück zum Ablauf'),lambda:self.tabs.setCurrentIndex(0)),0,Qt.AlignLeft)
        box.addWidget(label(tr('Bedingung beschreiben'),'codeCardTitle'));box.addWidget(label(tr('Lumen übersetzt deinen Text in sichtbare Bedingungen. Erst nach Prüfung übernehmen.'),'codeMuted'))
        self.description=QPlainTextEdit();self.description.setAccessibleName(tr('Bedingung als Text'));box.addWidget(self.description)
        self.describe_button=button(tr('Bedingung vorschlagen'),self.describe,primary=True);box.addWidget(self.describe_button)
        self.description_status=label('','codeMuted');box.addWidget(self.description_status)
        self.proposal_box=QWidget();self.proposal_layout=QVBoxLayout(self.proposal_box);box.addWidget(self.proposal_box)
        self.accept_proposal=button(tr('Als Startbedingung übernehmen'),self.accept_condition);self.accept_proposal.hide();box.addWidget(self.accept_proposal);box.addStretch()
        self.tabs.addTab(describe,tr('Bedingung beschreiben'))
        whole=QWidget();full=QVBoxLayout(whole);full.setSpacing(12)
        full.addWidget(button(tr('‹ Zurück zum Ablauf'),lambda:self.tabs.setCurrentIndex(0)),0,Qt.AlignLeft)
        full.addWidget(label(tr('Den ganzen Ablauf beschreiben'),'codeCardTitle'))
        self.full_description=QPlainTextEdit();self.full_description.setAccessibleName(tr('Ablaufbeschreibung'));full.addWidget(self.full_description)
        self.full_button=button(tr('Bausteine vorschlagen'),self.describe_flow,primary=True);full.addWidget(self.full_button)
        self.full_status=label('','codeMuted');full.addWidget(self.full_status);self.full_preview=QPlainTextEdit();self.full_preview.setReadOnly(True);self.full_preview.setMaximumHeight(220);self.full_preview.setAccessibleName(tr('Vorgeschlagene Bausteine'));full.addWidget(self.full_preview);self.full_accept=button(tr('Bausteinentwurf übernehmen'),self.accept_flow);self.full_accept.hide();full.addWidget(self.full_accept);full.addStretch();self.tabs.addTab(whole,tr('Ablauf beschreiben'));self.set_plan(plan)

    def set_plan(self,plan=None):
        if plan is None and self.routine:
            from code_clock import default
            plan=starter();plan['nodes']=[n for n in plan['nodes'] if n['kind']!='approval'];plan['nodes'][0]['config']=json.dumps({'kind':'text','text':'','trigger':{'kind':'clock','clock':default()}})
        value=parse(plan or starter());self.items=tree(value);self.gate=None
        if len(self.items)>1 and self.items[1]['kind']=='condition':self.gate=self.items.pop(1)
        self.gate_enabled=self.gate is not None;self.refresh()

    @property
    def nodes(self):return self.plan(False)['nodes']

    def sync(self):
        for getter in self.getters:getter()

    def plan(self,validate=True):
        self.sync();items=list(self.items)
        if self.gate_enabled and self.gate:items.insert(1,self.gate)
        result=flatten(items)
        return parse(result) if validate else result

    def emit_change(self,*_):self.changed.emit()

    def mutate(self,fn):
        if self.locked:return
        try:self.sync();fn();self.refresh();self.changed.emit()
        except ValueError as error:self.state.setText(tr(str(error)))

    def fold(self,box,title,key,subtitle=''):
        wrapper=QWidget();layout=QVBoxLayout(wrapper);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        toggle=button(('▾ ' if key in self.open_ids else '▸ ')+title,lambda:None);toggle.setCheckable(True);toggle.setChecked(key in self.open_ids);toggle.setObjectName('codeFold');toggle.setAccessibleName(title)
        if subtitle:toggle.setToolTip(subtitle)
        layout.addWidget(toggle);preview=label(subtitle,'codeMuted');preview.setVisible(bool(subtitle) and not toggle.isChecked());layout.addWidget(preview)
        body=QWidget();body_box=QVBoxLayout(body);body_box.setContentsMargins(16,0,0,8);body_box.setSpacing(12);layout.addWidget(body);body.setVisible(toggle.isChecked())
        def opened(checked):
            if checked:self.open_ids.add(key)
            else:self.open_ids.discard(key)
            toggle.setText(('▾ ' if checked else '▸ ')+title);body.setVisible(checked)
            preview.setVisible(bool(subtitle) and not checked)
        toggle.toggled.connect(opened);box.addWidget(wrapper)
        return body_box

    def fields_at(self,n):
        value=flatten(self.items);index=next(i for i,x in enumerate(value['nodes']) if x['id']==n['id'])
        return available(value['nodes'],index)

    def refresh(self,*_):
        self.getters=[];body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(0,8,0,8);box.setSpacing(16)
        if self.routine:
            columns=QHBoxLayout();columns.setSpacing(24);box.addLayout(columns)
            steps_widget=QWidget();steps_box=QVBoxLayout(steps_widget);steps_box.setContentsMargins(0,0,0,0);steps_box.setSpacing(16);columns.addWidget(steps_widget,3)
            settings_widget=QWidget();settings_box=QVBoxLayout(settings_widget);settings_box.setContentsMargins(0,0,0,0);settings_box.setSpacing(16);columns.addWidget(settings_widget,2)
            columns.setDirection(QHBoxLayout.TopToBottom if self.width()<800 else QHBoxLayout.LeftToRight);self.routine_columns=columns;box=settings_box
        box.addWidget(label(tr('Start' if self.routine else 'Wenn'),'codeCardTitle'))
        start=self.items[0];source=config(start)
        trigger=source.get('trigger',{});kind=trigger.get('kind','manual')
        trigger_choice=combo([('manual','Ich den Ablauf starte'),('clock','Ein Zeitpunkt erreicht ist'),('directory','Eine Datei im Ordner neu ist oder sich ändert'),('project','Sich mein Lumen-Projekt ändert')],kind);trigger_choice.setAccessibleName(tr('Auslöser'));box.addWidget(trigger_choice)
        def trigger_changed():
            def update():
                chosen=trigger_choice.currentData();value=config(start)
                if chosen=='manual':value.pop('trigger',None)
                elif chosen=='clock':
                    from code_clock import default
                    value['trigger']={'kind':'clock','clock':default()}
                else:
                    value['kind']='file' if chosen=='directory' else 'project';value['trigger']={'kind':chosen,**({'path':''} if chosen=='directory' else {})}
                start['config']=json.dumps(value);self.open_ids.add('input')
            self.mutate(update)
        trigger_choice.activated.connect(trigger_changed)
        if kind=='clock':
            from code_clock_editor import ClockEditor
            clock=ClockEditor(self);clock.kind.removeItem(clock.kind.findData('manual'));clock.set_value(trigger['clock']);box.addWidget(clock)
            clock.changed.connect(lambda:self.update_source(start,source,'trigger',{'kind':'clock','clock':clock.value(checked=False)}))
        source_title=tr({'text':'Text eingeben','file':'Ordner auswählen' if kind=='directory' else 'Datei auswählen','project':'Lumen-Projekt auswählen','message':'Nachricht einfügen','calendar':'Termindaten einfügen'}[source['kind']]);source_box=self.fold(box,tr('Mit diesen Daten')+' · '+source_title,'input',trigger.get('path') or source.get('path') or self.projects.get(source.get('project_id')) or source.get('text','')[:180] or tr('Quelle auswählen und ihren Inhalt prüfen.'))
        source_choice=combo([('text','Text eingeben'),('file','Datei auswählen'),('project','Lumen-Projekt auswählen'),('message','Nachricht einfügen'),('calendar','Termindaten einfügen')],source['kind']);source_choice.setAccessibleName(tr('Eingabequelle'))
        source_box.addWidget(source_choice);source_choice.setVisible(kind not in ('directory','project'))
        def source_changed():
            selected=source_choice.currentData();self.mutate(lambda:start.update(config=json.dumps({'kind':selected,'text':'',**({'trigger':config(start)['trigger']} if kind=='clock' else {})})))
        source_choice.activated.connect(source_changed)
        if kind=='directory':
            path=QLineEdit(trigger.get('path',''));path.setReadOnly(True);path.setAccessibleName(tr('Beobachteter Ordner'))
            def choose_folder():
                chosen=QFileDialog.getExistingDirectory(self,tr('Lumen · Beobachteten Ordner auswählen'))
                if chosen:path.setText(chosen);self.update_source(start,source,'trigger',{'kind':'directory','path':chosen})
            source_box.addWidget(row(path,button(tr('Ordner wählen'),choose_folder)))
            source_box.addWidget(label(tr('Neue und geänderte Dateien direkt in diesem Ordner, bis 20 MiB. Vorhandene Dateien bleiben beim Aktivieren unberührt. Start nach zwei unveränderten Hintergrundprüfungen; keine Unterordner oder Verknüpfungen.'),'codeMuted'))
        elif source['kind']=='file':
            path=QLineEdit(source.get('path',''));path.setReadOnly(True);path.setAccessibleName(tr('Quelldatei'))
            def choose_file():
                chosen=QFileDialog.getOpenFileName(self,tr('Lumen · Quelldatei auswählen'))[0]
                if chosen:path.setText(chosen);source['path']=chosen;start['config']=json.dumps(source);self.changed.emit()
            source_box.addWidget(row(path,button(tr('Datei wählen'),choose_file)))
        elif source['kind']=='project':
            choices=combo([('', 'Projekt wählen')]+list(self.projects.items()),source.get('project_id',''));choices.setAccessibleName(tr('Lumen-Projekt'));source_box.addWidget(choices)
            choices.currentIndexChanged.connect(lambda:self.update_source(start,source,'project_id',choices.currentData()))
            source_box.addWidget(label(tr('Liest Projektübersicht, Vorhaben und Aufgaben. Angeheftete Dokumente und Weblinks werden nicht automatisch geöffnet.'),'codeMuted'))
        else:
            text=QPlainTextEdit(source.get('text',''));text.setMaximumHeight(120);text.setAccessibleName(tr('Eingabetext'));source_box.addWidget(text)
            text.textChanged.connect(lambda:self.update_source(start,source,'text',text.toPlainText()))
            if source['kind'] in ('message','calendar'):
                source_box.addWidget(label(tr('Eingefügte Daten · kein automatischer Nachrichten- oder Kalenderauslöser.'),'codeMuted'))
                for key,title in ([('sender','Absender'),('subject','Betreff')] if source['kind']=='message' else [('subject','Termintitel')]):
                    source_box.addWidget(label(tr(title)));edit=QLineEdit(source.get(key,''));edit.setAccessibleName(tr(title));source_box.addWidget(edit)
                    edit.textChanged.connect(lambda text,k=key:self.update_source(start,source,k,text))
                if source['kind']=='message':
                    attach=QCheckBox(tr('Anhang vorhanden'));attach.setChecked(source.get('has_attachment',False));source_box.addWidget(attach);attach.toggled.connect(lambda checked:self.update_source(start,source,'has_attachment',checked))
        if not self.routine:
            condition_heading=QHBoxLayout();condition_heading.addWidget(label(tr('Und wenn'),'codeCardTitle'));condition_heading.addStretch()
            condition_help=button(tr('Bedingung in Worten beschreiben'),lambda:self.tabs.setCurrentIndex(1));condition_help.setObjectName('codeLink');condition_heading.addWidget(condition_help);box.addLayout(condition_heading)
            enable=QCheckBox(tr('Nur starten, wenn diese Bedingungen stimmen'));enable.setChecked(self.gate_enabled);box.addWidget(enable)
            if self.gate_enabled:
                from code_conditions import describe
                description=describe(config(self.gate));condition_box=self.fold(box,description[:100]+('…' if len(description)>100 else ''),'gate',description);editor=ConditionEditor(BASE_FIELDS|SOURCE_FIELDS[source['kind']],config(self.gate),self);editor.changed.connect(self.emit_change);condition_box.addWidget(editor)
                self.getters.append(lambda:self.gate.update(config=json.dumps(editor.value(),ensure_ascii=False)))
            def toggle_gate(checked):
                def change():
                    self.gate_enabled=checked
                    if checked:self.open_ids.add('gate')
                    if self.gate is None:self.gate=node('condition',json.dumps({'field':'text','op':'exists','value':True}))
                self.mutate(change)
            enable.toggled.connect(toggle_gate)
        if self.routine:box.addStretch();box=steps_box
        actions_heading=QHBoxLayout();actions_heading.addWidget(label(tr('Schritte' if self.routine else 'Dann'),'codeCardTitle'));actions_heading.addStretch()
        flow_help=button(tr('Ablauf in Worten beschreiben'),lambda:self.tabs.setCurrentIndex(2));flow_help.setObjectName('codeLink');actions_heading.addWidget(flow_help);box.addLayout(actions_heading)
        box.addWidget(label(tr('Von oben nach unten · nur geöffnete Bausteine zeigen ihre Einstellungen.'),'codeMuted'))
        self.render_steps(self.items,box,0,start=1)
        self.state=label('','codeMuted');box.addWidget(self.state);box.addStretch();self.scroll.setWidget(body);self.apply_lock()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.routine and hasattr(self,'routine_columns'):self.routine_columns.setDirection(QHBoxLayout.TopToBottom if self.width()<800 else QHBoxLayout.LeftToRight)

    def update_source(self,n,source,key,value):
        source[key]=value;n['config']=json.dumps(source,ensure_ascii=False);self.changed.emit()

    def render_steps(self,steps,box,depth,start=0):
        statuses={n['id']:s for n,s in zip(self.run['plan']['nodes'],self.run['data']['steps'])} if self.run else {}
        for index in range(start,len(steps)):
            n=steps[index];status=statuses.get(n['id'],{});state=tr(STATES.get(status.get('status','pending'),'Bereit'))
            summary=n['config'][:180] if n['kind'] in ('ai','ai_check','filter_text','save_file','read_file','save_note','create_task') else self.projects.get(n['config'],'') if n['kind']=='project_note' else tr(CATALOG[n['kind']][2])
            if status.get('error'):summary=status['error']
            inner=self.fold(box,n['title']+' · '+state,n['id'],summary)
            inner.addWidget(label(tr(CATALOG[n['kind']][2]),'codeMuted'))
            title=QLineEdit(n['title']);title.setAccessibleName(tr('Bausteinname'));title.setMaxLength(160);inner.addWidget(title);title.textEdited.connect(lambda text,item=n:self.update_node(item,'title',text))
            if n['kind']=='for_each':
                inner.addWidget(label(tr('Jede nicht leere Textzeile einzeln. Bis zu 20 Elemente; höchstens 1.000 Bausteinschritte pro Durchlauf.'),'codeMuted'))
                self.render_steps(n['steps'],inner,depth+1)
            elif n['kind']=='choose':
                inner.addWidget(label(tr('Der erste passende Weg läuft. Danach geht es im Hauptablauf weiter.'),'codeMuted'))
                for i,case in enumerate(n['cases']):
                    branch_box=self.fold(inner,tr('Möglichkeit {0}',i+1),n['id']+':'+str(i))
                    condition=ConditionEditor(self.fields_at(n),case['when'],self);condition.changed.connect(self.emit_change);branch_box.addWidget(condition)
                    self.getters.append(lambda item=case,control=condition:item.update(when=control.value()))
                    self.render_steps(case['steps'],branch_box,depth+1)
                    actions=QHBoxLayout();branch_box.addLayout(actions)
                    up=button('↑',lambda _=False,idx=i,c=n:self.mutate(lambda:c['cases'].insert(idx-1,c['cases'].pop(idx))));up.setEnabled(i>0);up.setAccessibleName(tr('Weg nach oben'));actions.addWidget(up)
                    down=button('↓',lambda _=False,idx=i,c=n:self.mutate(lambda:c['cases'].insert(idx+1,c['cases'].pop(idx))));down.setEnabled(i<len(n['cases'])-1);down.setAccessibleName(tr('Weg nach unten'));actions.addWidget(down)
                    remove=button(tr('Weg entfernen'),lambda _=False,c=case,item=n:self.mutate(lambda:item['cases'].remove(c)));remove.setEnabled(len(n['cases'])>1);actions.addWidget(remove);actions.addStretch()
                inner.addWidget(button(tr('+ Weiterer Weg'),lambda _=False,item=n:self.add_case(item)))
                fallback=self.fold(inner,tr('Sonst'),n['id']+':else');self.render_steps(n['otherwise'],fallback,depth+1)
            else:
                if n['kind'] in ('read_file','save_file'):
                    edit=QLineEdit(n['config']);edit.setReadOnly(True);edit.setAccessibleName(tr('Ausgewählter Pfad'));inner.addWidget(edit)
                    inner.addWidget(button(tr('Auswählen …'),lambda _=False,item=n:self.choose_path(item)))
                elif n['kind']=='project_note':
                    project_choice=combo([('', 'Lumen-Projekt wählen')]+list(self.projects.items()),n['config']);project_choice.setAccessibleName(tr('Zielprojekt'));inner.addWidget(project_choice);project_choice.activated.connect(lambda _=0,item=n,control=project_choice:self.update_node(item,'config',control.currentData()))
                elif n['kind'] in ('ai','ai_check','save_note','create_task','filter_text','delay'):
                    inner.addWidget(label(tr('Prüffrage' if n['kind']=='ai_check' else 'Wartezeit in Sekunden · 0 bis 3.600' if n['kind']=='delay' else 'Text in den gesuchten Zeilen' if n['kind']=='filter_text' else 'Auftrag oder Ergebnistitel')))
                    edit=QPlainTextEdit(n['config']);edit.setMaximumHeight(110);edit.setAccessibleName(tr('Bausteineinstellung'));inner.addWidget(edit);edit.textChanged.connect(lambda item=n,control=edit:self.update_node(item,'config',control.toPlainText()))
                if status:
                    for key,caption in [('input','Tatsächliche Eingabe'),('output','Tatsächliches Ergebnis')]:
                        inner.addWidget(label(tr(caption)));view=QPlainTextEdit(json.dumps(status.get(key,{}),ensure_ascii=False,indent=2));view.setReadOnly(True);view.setMaximumHeight(120);view.setAccessibleName(tr(caption));inner.addWidget(view)
                    if status.get('error'):inner.addWidget(label(status['error'],'codeError'))
            actions=QHBoxLayout();inner.addLayout(actions)
            up=button('↑',lambda _=False,i=index,s=steps:self.mutate(lambda:s.insert(i-1,s.pop(i))));up.setEnabled(index>start);up.setAccessibleName(tr('Baustein nach oben'));actions.addWidget(up)
            down=button('↓',lambda _=False,i=index,s=steps:self.mutate(lambda:s.insert(i+1,s.pop(i))));down.setEnabled(index<len(steps)-1);down.setAccessibleName(tr('Baustein nach unten'));actions.addWidget(down)
            actions.addWidget(button(tr('Entfernen'),lambda _=False,item=n,s=steps:self.mutate(lambda:s.remove(item))));actions.addStretch()
        add=QComboBox();add.setAccessibleName(tr('Aktion oder Baustein ergänzen'));add.addItem(tr('+ Aktion oder Baustein ergänzen'),'')
        for kind in ('read_file','filter_text','ai','ai_check','choose','for_each','delay','approval','save_file','save_note','create_task','project_note','notify'):
            if self.routine and kind in ('choose','for_each','ai_check'):continue
            if kind not in ('choose','for_each') or depth<3:add.addItem(tr(CATALOG[kind][1]),kind)
        for tool in self.tools:add.addItem(tr('Werkzeug: {0}',tool['title']),tool)
        box.addWidget(add)
        def selected():
            value=add.currentData()
            if not value:return
            def append():
                if len(self.plan(False)['nodes'])>=52:raise ValueError(tr('Der Ablauf hat zu viele Bausteine.'))
                n=node('ai' if isinstance(value,dict) else value,value['definition'].get('prompt','') if isinstance(value,dict) else '')
                if isinstance(value,dict):n['title']=value['title']+' · '+tr('Version {0}',value['revision'])
                if n['kind']=='delay':n['config']='5'
                if n['kind']=='for_each':n.update(steps=[],end=node('end_each',n['id'],title=tr('Ergebnisse sammeln')))
                if n['kind']=='choose':n.update(cases=[{'when':{'field':'text','op':'contains','value':'Rechnung'},'steps':[]}],otherwise=[])
                steps.append(n);self.open_ids.add(n['id'])
            self.mutate(append)
        add.activated.connect(selected)

    def update_node(self,n,key,value):n[key]=value;self.changed.emit()

    def add_case(self,n):
        def append():
            if len(n['cases'])>=12:raise ValueError(tr('Bis zu zwölf Möglichkeiten je Entscheidung.'))
            n['cases'].append({'when':{'field':'text','op':'exists','value':True},'steps':[]})
        self.mutate(append)

    def choose_path(self,n):
        path=QFileDialog.getExistingDirectory(self,tr('Lumen · Ergebnisordner auswählen')) if n['kind']=='save_file' else QFileDialog.getOpenFileName(self,tr('Lumen · Quelldatei auswählen'))[0]
        if path:self.mutate(lambda:n.update(config=path))

    def set_locked(self,locked):
        self.locked=locked;self.apply_lock();self.description.setEnabled(not locked);self.describe_button.setEnabled(not locked);self.full_button.setEnabled(not locked);self.full_description.setEnabled(not locked)

    def apply_lock(self):
        body=self.scroll.widget()
        if not body:return
        for control in body.findChildren(QWidget):
            if isinstance(control,(QLineEdit,QPlainTextEdit,QDoubleSpinBox,QSpinBox,QTimeEdit,QDateEdit)):
                if self.locked and control.property('codeReadOnly') is None:control.setProperty('codeReadOnly',control.isReadOnly())
                if self.locked:control.setReadOnly(True)
                elif control.property('codeReadOnly') is not None:control.setReadOnly(bool(control.property('codeReadOnly')))
            elif isinstance(control,(QComboBox,QCheckBox,QPushButton)) and control.objectName()!='codeFold':
                if self.locked and control.property('codeEnabled') is None:control.setProperty('codeEnabled',control.isEnabled())
                if self.locked:control.setEnabled(False)
                elif control.property('codeEnabled') is not None:control.setEnabled(bool(control.property('codeEnabled')))

    def focus_step(self,index):
        if not self.run or not 0<=index<len(self.run['plan']['nodes']):return
        target=self.run['plan']['nodes'][index]['id']
        def visit(items,parents):
            for n in items:
                if n['id']==target:self.open_ids.update(parents+[n['id']])
                if n['kind']=='for_each':visit(n['steps'],parents+[n['id']])
                if n['kind']=='choose':
                    for i,c in enumerate(n['cases']):visit(c['steps'],parents+[n['id'],n['id']+':'+str(i)])
                    visit(n['otherwise'],parents+[n['id'],n['id']+':else'])
        visit(self.items,[]);self.refresh()

    def describe(self):
        from code_conditions import proposal
        try:
            fields=BASE_FIELDS|SOURCE_FIELDS[config(self.items[0])['kind']]
            prompt=proposal(self.description.toPlainText(),fields)
            if QMessageBox.question(self,tr('Lumen · Bedingung vorschlagen'),tr('Beschreibung an die eingerichtete KI senden? Es werden keine Aktionen ausgeführt.'))!=QMessageBox.Yes:return
            if self.engine is None:
                from assistant_backend import OpenCodeBackend
                self.temporary=tempfile.TemporaryDirectory(prefix='lumen-conditions-');self.engine=OpenCodeBackend(Path(self.temporary.name),self,project_config=False);self.engine.completed.connect(self.described)
            self.proposal_fields=fields;self.proposal_source=config(self.items[0])['kind'];self.proposal_text=self.description.toPlainText();self.proposal_condition=None;self.accept_proposal.hide();self.describe_button.setEnabled(False);self.engine.send(prompt,proposal=True,title='Lumen Automation')
        except (ValueError,OSError,RuntimeError) as error:self.description_status.setText(tr(str(error)))

    def described(self,success,result):
        if self.closed:return
        from code_conditions import generated
        self.describe_button.setEnabled(True)
        try:
            if not success:raise ValueError(result)
            value=generated(result,self.proposal_fields);self.proposal_condition=value['condition']
            while self.proposal_layout.count():self.proposal_layout.takeAt(0).widget().deleteLater()
            self.preview=ConditionEditor(self.proposal_fields,self.proposal_condition,self);self.proposal_layout.addWidget(self.preview);self.description_status.setText(value['explanation']);self.accept_proposal.show()
        except ValueError as error:self.description_status.setText(tr(str(error)))

    def accept_condition(self):
        try:
            if self.description.toPlainText()!=self.proposal_text or config(self.items[0])['kind']!=self.proposal_source:raise ValueError(tr('Beschreibung oder Quelle geändert. Bitte erneut vorschlagen lassen.'))
            condition=self.preview.value()
            def apply():self.gate=node('condition',json.dumps(condition,ensure_ascii=False));self.gate_enabled=True
            self.mutate(apply);self.tabs.setCurrentIndex(0)
        except ValueError as error:self.description_status.setText(tr(str(error)))

    def describe_flow(self):
        from code_block_paths import proposal
        from code_blocks_run import digest
        try:
            prompt=proposal(self.full_description.toPlainText())
            self.full_signature=digest(self.plan());self.full_text=self.full_description.toPlainText()
            if QMessageBox.question(self,tr('Lumen · Ablauf vorschlagen'),tr('Beschreibung an die eingerichtete KI senden? Quellen und Ziele werden nicht übertragen. Übernahme erst nach deiner Prüfung.'))!=QMessageBox.Yes:return
            if self.full_engine is None:
                from assistant_backend import OpenCodeBackend
                self.full_directory=tempfile.TemporaryDirectory(prefix='lumen-flow-design-');self.full_engine=OpenCodeBackend(Path(self.full_directory.name),self,project_config=False);self.full_engine.completed.connect(self.flow_described)
            self.full_candidate=None;self.full_accept.hide();self.set_locked(True);self.full_engine.send(prompt,proposal=True,title='Lumen Automation')
        except (ValueError,OSError,RuntimeError) as error:self.set_locked(False);self.full_status.setText(tr(str(error)))

    def flow_described(self,success,result):
        if self.closed:return
        from code_block_paths import generated
        from code_block_paths import preview
        self.set_locked(False)
        try:
            if not success:raise ValueError(result)
            self.full_candidate=generated(result,self.items[0]);self.full_status.setText(tr('Vorschlag prüfen. Noch nicht übernommen.'));self.full_preview.setPlainText(preview(self.full_candidate));self.full_accept.show()
        except ValueError as error:self.full_status.setText(tr(str(error)))

    def accept_flow(self):
        from code_blocks_run import digest
        try:
            if not self.full_candidate:return
            if digest(self.plan())!=self.full_signature or self.full_description.toPlainText()!=self.full_text:raise ValueError(tr('Ablauf oder Beschreibung inzwischen geändert. Bitte erneut vorschlagen lassen.'))
            if self.routine and any(n['kind'] in ('choose','condition','for_each') for n in self.full_candidate['nodes']):raise ValueError(tr('Für Verzweigungen Automation wählen; eine Routine verwendet feste Schritte.'))
            self.set_plan(self.full_candidate);self.changed.emit();self.tabs.setCurrentIndex(0);self.full_candidate=None;self.full_accept.hide()
        except ValueError as error:self.full_status.setText(tr(str(error)))

    def shutdown(self):
        self.closed=True
        if self.engine:self.engine.shutdown()
        if self.full_engine:self.full_engine.shutdown()
        if self.full_directory:self.full_directory.cleanup()
        if self.temporary:self.temporary.cleanup()

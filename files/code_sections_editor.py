"""Panorama automation editor: When, optional conditions, one selected action inspector."""
import json
import tempfile
from html import escape
from pathlib import Path
from PySide6.QtCore import Signal,Qt,QSize,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QScrollArea,QTabWidget,
    QLineEdit,QPlainTextEdit,QComboBox,QCheckBox,QFileDialog,QMessageBox,QPushButton,QDoubleSpinBox,QSpinBox,QTimeEdit,QDateEdit,QSizePolicy)
from tools_ui import button,label,row
from lumen_i18n import tr
from code_blocks import node,CATALOG,parse,LEGACY_KINDS,STATES
from code_block_paths import starter,tree,flatten,available,config,SOURCE_FIELDS,BASE_FIELDS
from code_condition_ui import ConditionEditor,combo


class ActionRow(QPushButton):
    """Native button geometry includes its wrapped summary labels."""
    def __init__(self):
        super().__init__();policy=self.sizePolicy();policy.setHeightForWidth(True);policy.setVerticalPolicy(QSizePolicy.Preferred);self.setSizePolicy(policy)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):
        layout=self.layout()
        return max(72,layout.totalHeightForWidth(max(120,width))) if layout else 72
    def sizeHint(self):return QSize(320,self.heightForWidth(320))
    def minimumSizeHint(self):return QSize(0,72)


class SectionsEditor(QWidget):
    changed=Signal()
    def __init__(self,parent=None,plan=None,projects=None,tools=None,routine=False):
        super().__init__(parent);self.routine=routine;self.run=None;self.engine=None;self.locked=False;self.selected="input";self.summaries={};self.getters=[];self.projects=projects or {};self.tools=tools or []
        self.temporary=None;self.proposal_condition=None;self.closed=False;self.full_engine=None;self.full_directory=None;self.full_candidate=None
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(12)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();self.tabs.setAccessibleName(tr('Ablauf und Formulierungshilfe'));root.addWidget(self.tabs)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.tabs.addTab(self.scroll,tr('Ablauf'))
        describe=QWidget();box=QVBoxLayout(describe);box.setSpacing(12)
        box.addWidget(button(tr('‹ Zurück zum Ablauf'),lambda:self.tabs.setCurrentIndex(0)),0,Qt.AlignLeft)
        box.addWidget(label(tr('Bedingung beschreiben'),'codeCardTitle'));box.addWidget(label(tr('Lumen übersetzt deinen Text in sichtbare Bedingungen. Erst nach Prüfung übernehmen.'),'codeMuted'))
        self.description=QPlainTextEdit();self.description.setAccessibleName(tr('Bedingung als Text'));box.addWidget(self.description)
        self.describe_button=button(tr('Bedingung vorschlagen'),self.describe,primary=True);box.addWidget(self.describe_button)
        self.description_status=label('','codeMuted');box.addWidget(self.description_status)
        self.proposal_box=QWidget();self.proposal_layout=QVBoxLayout(self.proposal_box);box.addWidget(self.proposal_box)
        self.accept_proposal=button(tr('Als Startbedingung übernehmen'),self.accept_condition);self.accept_proposal.hide();box.addWidget(self.accept_proposal);box.addStretch()
        # Hidden formulation pages must not set the flow's minimum window height.
        describe_scroll=QScrollArea();describe_scroll.setWidgetResizable(True);describe_scroll.setWidget(describe);self.tabs.addTab(describe_scroll,tr('Bedingung beschreiben'))
        whole=QWidget();full=QVBoxLayout(whole);full.setSpacing(12)
        full.addWidget(button(tr('‹ Zurück zum Ablauf'),lambda:self.tabs.setCurrentIndex(0)),0,Qt.AlignLeft)
        full.addWidget(label(tr('Den ganzen Ablauf beschreiben'),'codeCardTitle'))
        self.full_description=QPlainTextEdit();self.full_description.setAccessibleName(tr('Ablaufbeschreibung'));full.addWidget(self.full_description)
        self.full_button=button(tr('Ablauf vorschlagen'),self.describe_flow,primary=True);full.addWidget(self.full_button)
        self.full_status=label('','codeMuted');full.addWidget(self.full_status);self.full_preview=QPlainTextEdit();self.full_preview.setReadOnly(True);self.full_preview.setMaximumHeight(220);self.full_preview.setAccessibleName(tr('Vorgeschlagener Ablauf'));full.addWidget(self.full_preview);self.full_accept=button(tr('Vorschlag übernehmen'),self.accept_flow);self.full_accept.hide();full.addWidget(self.full_accept);full.addStretch()
        whole_scroll=QScrollArea();whole_scroll.setWidgetResizable(True);whole_scroll.setWidget(whole);self.tabs.addTab(whole_scroll,tr('Ablauf beschreiben'));self.set_plan(plan)

    def set_plan(self,plan=None):
        if plan is None and self.routine:
            from code_clock import default
            plan=starter();plan['nodes']=[n for n in plan['nodes'] if n['kind']!='approval'];plan['nodes'][0]['config']=json.dumps({'kind':'text','text':'','trigger':{'kind':'clock','clock':default()}})
        value=parse(plan or starter());self.version=value['version'];self.items=tree(value) if self.version==3 else value['nodes'];self.gate=None
        if self.version==3 and len(self.items)>1 and self.items[1]['kind']=='condition':self.gate=self.items.pop(1)
        self.gate_enabled=self.gate is not None;self.refresh()

    @property
    def nodes(self):return self.plan(False)['nodes']

    def sync(self):
        for getter in self.getters:getter()

    def plan(self,validate=True):
        self.sync();items=list(self.items)
        if self.gate_enabled and self.gate:items.insert(1,self.gate)
        result=flatten(items) if self.version==3 else json.loads(json.dumps(dict(version=2,nodes=items)))
        return parse(result) if validate else result

    def emit_change(self,*_):self.changed.emit()

    def mutate(self,fn):
        if self.locked:return
        try:self.sync();fn();self.refresh();self.changed.emit()
        except ValueError as error:self.state.setText(tr(str(error)))

    def select_entry(self,key):
        self.sync();self.selected=key;self.refresh()
        if self.width()<740:QTimer.singleShot(0,self,lambda:self.scroll.ensureWidgetVisible(self.inspector))

    def summary(self,box,title,detail,key,depth=0):
        control=ActionRow();control.setObjectName('codeFlowRow');control.setCheckable(True);control.setChecked(self.selected==key);control.setAccessibleName(title);control.setAccessibleDescription(detail)
        layout=QVBoxLayout(control);layout.setContentsMargins(16+depth*12,12,16,12);layout.setSpacing(4)
        caption=label(title);preview=label(detail,'codeMuted');layout.addWidget(caption)
        if detail:layout.addWidget(preview)
        for child in (caption,preview):child.setAttribute(Qt.WA_TransparentForMouseEvents)
        control.clicked.connect(lambda:self.select_entry(key));box.addWidget(control);self.summaries[key]=(control,caption,preview)

    def find_step(self,key,steps=None,depth=0,start=1):
        steps=self.items if steps is None else steps
        for i in range(start,len(steps)):
            n=steps[i]
            if n['id']==key:return n,steps,i,depth,start
            children=([n['steps']] if n['kind']=='for_each' else [c['steps'] for c in n['cases']]+[n['otherwise']] if n['kind']=='choose' else [])
            for child in children:
                found=self.find_step(key,child,depth+1,0)
                if found:return found

    def action_summaries(self,steps,box,depth=0,start=1):
        states={n['id']:v for n,v in zip(self.run['plan']['nodes'],self.run['data']['steps'])} if self.run else {}
        for i,n in enumerate(steps[start:],start):
            detail=n['config'] if n['kind'] in ('ai','ai_check','filter_text','read_file','save_file','save_note','create_task') else tr(CATALOG[n['kind']][2])
            step=states.get(n['id'])
            if step:detail=tr(STATES.get(step['status'],'Bereit'))+' · '+(step.get('error') or detail)
            self.summary(box,str(i-start+1)+'. '+n['title'],detail[:240],n['id'],depth)
            if n['kind']=='for_each':self.action_summaries(n['steps'],box,depth+1,0)
            elif n['kind']=='choose':
                from code_conditions import describe
                for case in n['cases']:
                    box.addWidget(label(tr('Wenn')+' · '+describe(case['when']),'codeMuted'));self.action_summaries(case['steps'],box,depth+1,0)
                box.addWidget(label(tr('Sonst'),'codeMuted'));self.action_summaries(n['otherwise'],box,depth+1,0)

    def fields_at(self,n):
        value=flatten(self.items);index=next(i for i,x in enumerate(value['nodes']) if x['id']==n['id'])
        source=config(value['nodes'][0]);source.pop('trigger',None);value['nodes'][0]['config']=json.dumps(source)
        return available(value['nodes'],index)

    def refresh(self,*_):
        if self.selected not in ('input','gate') and not self.find_step(self.selected):self.selected='input'
        self.getters=[];self.summaries={};body=QWidget();self.columns=QHBoxLayout(body);self.columns.setContentsMargins(0,16,8,16);self.columns.setSpacing(32)
        left=QWidget();box=QVBoxLayout(left);box.setContentsMargins(0,0,0,0);box.setSpacing(12);self.columns.addWidget(left,3)
        self.inspector=QWidget();self.inspector.setObjectName('codeFlowInspector');right=QVBoxLayout(self.inspector);right.setContentsMargins(24,0,0,0);right.setSpacing(12);self.columns.addWidget(self.inspector,2)
        box.addWidget(label(tr('Start' if self.routine else 'Wenn'),'codeCardTitle'))
        from code_triggers import describe
        detail=describe(config(self.items[0])) if self.version==3 else tr('Ich den Ablauf starte')
        self.summary(box,tr('Auslöser festlegen'),detail,'input');box.addSpacing(12)
        if not self.routine and self.version==3:
            box.addWidget(label(tr('Und wenn · optional'),'codeCardTitle'))
            if self.gate_enabled:
                from code_conditions import describe as condition_description
                self.summary(box,condition_description(config(self.gate)),tr('Vor den Aktionen prüfen.'),'gate')
            else:box.addWidget(button(tr('+ Startbedingung hinzufügen'),self.add_gate))
            box.addSpacing(12)
        box.addWidget(label(tr('Schritte' if self.routine else 'Dann'),'codeCardTitle'));self.action_summaries(self.items,box);self.add_actions(self.items,box,0);box.addStretch()
        if self.selected=='gate' and self.gate_enabled:
            right.addWidget(label(tr('Startbedingung'),'codeCardTitle'));right.addWidget(label(tr('Nur bei erfüllter Bedingung beginnen die Aktionen.'),'codeMuted'))
            fields=BASE_FIELDS|SOURCE_FIELDS[config(self.items[0])['kind']];editor=ConditionEditor(fields,config(self.gate),self);right.addWidget(editor);editor.changed.connect(self.emit_change)
            self.getters.append(lambda:self.gate.update(config=json.dumps(editor.value(),ensure_ascii=False)))
            right.addWidget(button(tr('Bedingung in Worten beschreiben'),lambda:self.tabs.setCurrentIndex(1)));right.addWidget(button(tr('Bedingung entfernen'),self.remove_gate))
        elif self.selected=='input' or not self.find_step(self.selected):
            self.selected='input';right.addWidget(label(tr('Auslöser festlegen'),'codeCardTitle'))
            if self.version==3:self.render_source(right)
            else:right.addWidget(label(tr('Dieser vorhandene Ablauf startet manuell. Seine Quellen und Aktionen werden unverändert ausgeführt.'),'codeMuted'))
            if self.version==3:right.addWidget(button(tr('Ablauf in Worten beschreiben'),lambda:self.tabs.setCurrentIndex(2)))
        else:self.render_action(*self.find_step(self.selected),right)
        right.addStretch();self.state=label('','codeMuted');right.addWidget(self.state);self.scroll.setWidget(body);self.reflow();self.apply_lock()

    def add_gate(self):
        def add():
            if self.gate is None:self.gate=node('condition',json.dumps({'field':'text','op':'exists','value':True}))
            self.gate_enabled=True;self.selected='gate'
        self.mutate(add)

    def remove_gate(self):
        def remove():self.gate_enabled=False;self.selected='input'
        self.mutate(remove)

    def reflow(self):
        narrow=self.width()<740;self.columns.setDirection(QHBoxLayout.TopToBottom if narrow else QHBoxLayout.LeftToRight)
        self.inspector.layout().setContentsMargins(0 if narrow else 24,16 if narrow else 0,0,0);self.inspector.setProperty('narrow',narrow);self.inspector.style().unpolish(self.inspector);self.inspector.style().polish(self.inspector)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'columns'):self.reflow()

    def render_source(self,box):
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
                start['config']=json.dumps(value)
            self.mutate(update)
        trigger_choice.activated.connect(trigger_changed)
        if kind=='clock':
            from code_clock_editor import ClockEditor
            clock=ClockEditor(self);clock.kind.removeItem(clock.kind.findData('manual'));clock.set_value(trigger['clock']);box.addWidget(clock)
            clock.changed.connect(lambda:self.update_source(start,source,'trigger',{'kind':'clock','clock':clock.value(checked=False)}))
        source_box=box
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

    def update_source(self,n,source,key,value):
        if self.locked:return
        source[key]=value;n['config']=json.dumps(source,ensure_ascii=False);self.changed.emit()
        if 'input' in self.summaries:
            from code_triggers import describe
            self.summaries['input'][2].setText(describe(source))

    def render_action(self,n,steps,index,depth,start,box):
        box.addWidget(label(n['title'],'codeCardTitle'));box.addWidget(label(tr(CATALOG[n['kind']][2]),'codeMuted'))
        title=QLineEdit(n['title']);title.setMaxLength(160);title.setAccessibleName(tr('Bezeichnung'));box.addWidget(label(tr('Bezeichnung')));box.addWidget(title);title.textEdited.connect(lambda text:self.update_node(n,'title',text))
        if n['kind']=='choose':
            for i,case in enumerate(n['cases']):
                box.addWidget(label(tr('Möglichkeit {0}',i+1),'codeCardTitle'));condition=ConditionEditor(self.fields_at(n),case['when'],self);box.addWidget(condition);condition.changed.connect(self.emit_change)
                self.getters.append(lambda c=case,e=condition:c.update(when=e.value()));self.add_actions(case['steps'],box,depth+1)
                actions=QHBoxLayout();box.addLayout(actions)
                up=button(tr('Nach oben'),lambda _=False,i=i:self.mutate(lambda:n['cases'].insert(i-1,n['cases'].pop(i))));up.setEnabled(i>0);actions.addWidget(up)
                down=button(tr('Nach unten'),lambda _=False,i=i:self.mutate(lambda:n['cases'].insert(i+1,n['cases'].pop(i))));down.setEnabled(i<len(n['cases'])-1);actions.addWidget(down)
                remove=button(tr('Weg entfernen'),lambda _=False,c=case:self.mutate(lambda:n['cases'].remove(c)));remove.setEnabled(len(n['cases'])>1);box.addWidget(remove)
            box.addWidget(button(tr('+ Weiterer Weg'),lambda:self.add_case(n)));box.addWidget(label(tr('Sonst'),'codeCardTitle'));self.add_actions(n['otherwise'],box,depth+1)
        elif n['kind']=='for_each':self.add_actions(n['steps'],box,depth+1)
        elif n['kind'] in ('read_file','save_file'):
            edit=QLineEdit(n['config']);edit.setReadOnly(True);edit.setAccessibleName(tr('Ausgewählter Pfad'));box.addWidget(edit);box.addWidget(button(tr('Ordner wählen' if n['kind']=='save_file' else 'Datei wählen'),lambda:self.choose_path(n)))
        elif n['kind']=='project_note':
            choice=combo([('', 'Lumen-Projekt wählen')]+list(self.projects.items()),n['config']);choice.setAccessibleName(tr('Zielprojekt'));box.addWidget(choice);choice.activated.connect(lambda:self.update_node(n,'config',choice.currentData()))
        elif n['kind']=='condition':
            condition=ConditionEditor(self.fields_at(n),config(n),self);box.addWidget(condition);condition.changed.connect(self.emit_change)
            self.getters.append(lambda:n.update(config=json.dumps(condition.value(),ensure_ascii=False)))
        elif n['kind'] in ('ai','ai_check','filter_text','save_note','create_task','delay'):
            caption=tr({'ai':'Was soll Lumen tun?','ai_check':'Prüffrage','filter_text':'Text in den gesuchten Zeilen','save_note':'Titel der neuen Notiz','create_task':'Titel der Aufgabe','delay':'Wartezeit in Sekunden · 0 bis 3.600'}[n['kind']]);box.addWidget(label(caption))
            edit=QPlainTextEdit(n['config']);edit.setMaximumHeight(160);edit.setAccessibleName(caption);box.addWidget(edit);edit.textChanged.connect(lambda:self.update_node(n,'config',edit.toPlainText()))
        status=next((s for item,s in zip(self.run['plan']['nodes'],self.run['data']['steps']) if item['id']==n['id']),None) if self.run else None
        if status:
            for key,caption in [('input','Tatsächliche Eingabe'),('output','Tatsächliches Ergebnis')]:
                box.addWidget(label(tr(caption)));view=QPlainTextEdit(json.dumps(status.get(key,{}),ensure_ascii=False,indent=2));view.setReadOnly(True);view.setMaximumHeight(140);view.setAccessibleName(tr(caption));box.addWidget(view)
            if status.get('error'):box.addWidget(label(status['error'],'codeError'))
        actions=QHBoxLayout();box.addLayout(actions)
        up=button(tr('Nach oben'),lambda:self.mutate(lambda:steps.insert(index-1,steps.pop(index))));up.setEnabled(index>start);actions.addWidget(up)
        down=button(tr('Nach unten'),lambda:self.mutate(lambda:steps.insert(index+1,steps.pop(index))));down.setEnabled(index<len(steps)-1);actions.addWidget(down)
        remove=button(tr('Entfernen'),lambda:self.mutate(lambda:steps.remove(n)));remove.setEnabled(len(self.plan(False)['nodes'])>2);box.addWidget(remove)

    def add_actions(self,steps,box,depth):
        add=QComboBox();add.setAccessibleName(tr('Aktion hinzufügen'));add.addItem(tr('+ Aktion hinzufügen'),'')
        # A saved tool's long name must not widen the entire flow.
        add.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);add.setMinimumContentsLength(20)
        add.view().setTextElideMode(Qt.ElideRight)
        kinds=('read_file','filter_text','ai','ai_check','choose','for_each','delay','approval','save_file','save_note','create_task','project_note','notify') if self.version==3 else tuple(k for k in CATALOG if k in LEGACY_KINDS and k!='manual')
        for kind in kinds:
            if self.routine and kind in ('choose','for_each','ai_check'):continue
            if kind not in ('choose','for_each') or depth<3:add.addItem(tr(CATALOG[kind][1]),kind)
        for tool in self.tools:
            text=tr('Werkzeug: {0}',tool['title']);add.addItem(text,tool);add.setItemData(add.count()-1,'<qt>'+escape(text)+'</qt>',Qt.ToolTipRole)
        box.addWidget(add)
        def selected():
            value=add.currentData()
            if not value:return
            def append():
                if len(self.plan(False)['nodes'])>=(52 if self.version==3 else 14):raise ValueError(tr('Der Ablauf hat zu viele Aktionen.'))
                n=node('ai' if isinstance(value,dict) else value,value['definition'].get('prompt','') if isinstance(value,dict) else '')
                if isinstance(value,dict):n['title']=value['title']+' · '+tr('Version {0}',value['revision'])
                if n['kind']=='delay':n['config']='5'
                if n['kind']=='for_each':n.update(steps=[],end=node('end_each',n['id'],title=tr('Ergebnisse sammeln')))
                if n['kind']=='choose':n.update(cases=[{'when':{'field':'text','op':'contains','value':'Rechnung'},'steps':[]}],otherwise=[])
                steps.append(n);self.selected=n['id']
            self.mutate(append)
        add.activated.connect(selected)

    def update_node(self,n,key,value):
        if self.locked:return
        n[key]=value
        if n['id'] in self.summaries:
            control,caption,preview=self.summaries[n['id']]
            if key=='title':caption.setText(value);control.setAccessibleName(value)
            else:preview.setText(self.projects.get(value,value)[:240])
        self.changed.emit()

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
            elif isinstance(control,(QComboBox,QCheckBox,QPushButton)) and control.objectName()!='codeFlowRow':
                if self.locked and control.property('codeEnabled') is None:control.setProperty('codeEnabled',control.isEnabled())
                if self.locked:control.setEnabled(False)
                elif control.property('codeEnabled') is not None:control.setEnabled(bool(control.property('codeEnabled')))

    def focus_step(self,index):
        if not self.run or not 0<=index<len(self.run['plan']['nodes']):return
        self.select_entry('input' if index==0 else self.run['plan']['nodes'][index]['id'])

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
            if not self.full_description.toPlainText().strip() or len(self.full_description.toPlainText())>8000:raise ValueError(tr('Bitte den Ablauf in höchstens 8.000 Zeichen beschreiben.'))
            prompt=proposal(self.full_description.toPlainText()) if self.version==3 else 'Antworte nur mit JSON {"nodes":[{"kind":"manual","title":"Start","config":""}, ...]}. Zwei bis vierzehn Schritte. Typen: '+', '.join(sorted(LEGACY_KINDS))+'. config nur für ai als Auftrag, alle Pfade leer. Keine Aktionen ausführen. Beschreibung: '+self.full_description.toPlainText()
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

            if self.version==3:self.full_candidate=generated(result,self.items[0])
            else:
                from code_blocks import generated as legacy_generated
                self.full_candidate=legacy_generated(result);self.full_candidate['nodes'][0]=dict(self.items[0])
            self.full_status.setText(tr('Vorschlag prüfen. Noch nicht übernommen.'));self.full_preview.setPlainText(preview(self.full_candidate) if self.version==3 else '\n'.join(n['title']+': '+n['config'] for n in self.full_candidate['nodes']));self.full_accept.show()
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

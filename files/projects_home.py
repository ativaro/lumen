"""One room surface over the existing project, material and conversation owners."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QComboBox, QLineEdit, QMenu, QInputDialog)
from lumen_i18n import tr
from tools_ui import button, label, row, open_path
from workplace_rooms import clear
from projects_rooms import ProjectRooms, source_chain


class ProjectHome(QWidget):
    def __init__(self, window):
        super().__init__(); self.window=window; self.project_id=''; self.room_id=''; self.scope=''; self.chat_limit=5
        self.links=ProjectRooms(window.library,window.workplace.store); self.values=[]; self.signature=None
        self.setObjectName('projectHome')
        self.setAttribute(Qt.WA_StyledBackground,True)
        outer=QVBoxLayout(self); outer.setContentsMargins(24,20,24,16); outer.setSpacing(18)
        header=QHBoxLayout();header.addWidget(label(tr('Lumen Projekte'),'workplaceHeading'),1);header.addWidget(button(tr('Projekt anlegen'),lambda:window.safe(self.create),'list-add',True));outer.addLayout(header)
        self.room_strip=QWidget(); self.strip=QGridLayout(self.room_strip); self.strip.setContentsMargins(0,0,0,0); outer.addWidget(self.room_strip)
        self.all_rooms=QComboBox(); self.all_rooms.setAccessibleName(tr('Alle Projekte')); self.all_rooms.activated.connect(lambda i:window.safe(self.choose,self.all_rooms.itemData(i))); outer.addWidget(self.all_rooms)
        self.editor_layout=QHBoxLayout();self.editor_layout.setSpacing(16);outer.addLayout(self.editor_layout,1)
        body=QWidget();left=QVBoxLayout(body);left.setContentsMargins(0,0,0,0);left.setSpacing(16);self.editor_layout.addWidget(body,1)
        head=QGridLayout();self.title_grid=head;self.heading=label('','workplaceHeading');head.addWidget(self.heading,0,0)
        self.resume=button(tr('Arbeitsstand laden'),lambda:window.safe(self.room_action,'resume'))
        head.addWidget(self.resume,0,1)
        self.options=button(tr('Mehr'),lambda:None,'view-more-symbolic');head.addWidget(self.options,0,2);left.addLayout(head)
        menu=QMenu(self.options);self.options.setMenu(menu)
        for title,fn in [(tr('Arbeitsstand merken'),lambda:self.room_action('capture')),
                         (tr('Projektumgebung'),self.environment),
                         (tr('Ausführungen und Diagnose'),self.diagnostics),
                         (tr('Archiv und Serverabgleich'),self.management),
                         (tr('Projektübersicht exportieren'),lambda:self.project_action(window.export))]:
            menu.addAction(title,lambda _=False,f=fn:window.safe(f))
        self.scope_picker=QComboBox();self.scope_picker.setAccessibleName(tr('Vorhaben'));self.scope_picker.activated.connect(self.change_scope)
        self.plan_button=button(tr('Bearbeiten'),lambda:window.safe(self.plan),'document-edit')
        scope_row=QHBoxLayout();scope_row.addWidget(self.scope_picker,1);scope_row.addStretch();scope_row.addWidget(self.plan_button);left.addLayout(scope_row)
        self.scroller=QScrollArea();self.scroller.setWidgetResizable(True);self.scroller.setFrameShape(QScrollArea.NoFrame)
        left.addWidget(self.scroller,1)
        self.board=QWidget();self.grid=QGridLayout(self.board);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(20);self.scroller.setWidget(self.board)
        self.columns=[]
        for title in ('Material','Vorhaben & nächste Schritte','Gespräche'):
            pane=QWidget();layout=QVBoxLayout(pane);layout.setContentsMargins(16,16,16,16);layout.setSpacing(9)
            pane.setObjectName('projectColumn');self.columns.append((pane,layout))
        self.prompt=QLineEdit();self.prompt.setPlaceholderText(tr('Mit Lumen in diesem Projekt weiterarbeiten …'));self.prompt.setAccessibleName(tr('Frage zum Projekt'))
        send=button(tr('Besprechen →'),lambda:window.safe(self.discuss),'go-next',True);self.prompt.returnPressed.connect(send.click)
        left.addWidget(row(self.prompt,send))
        self.feedback=label('','muted');left.addWidget(self.feedback)
        self.setStyleSheet('''QWidget#projectHome { background: palette(window); }
            QWidget#projectColumn { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
            QWidget#projectColumn QLabel { border: none; background: transparent; }
            QPushButton#roomChoice { text-align: left; padding: 14px; }
            QPushButton#roomChoice:checked { color: palette(text); background: palette(alternate-base); border: 1px solid palette(highlight); }
            QPushButton#roomItem { color: palette(text); background: transparent; text-align: left; padding: 10px 6px; border: none; border-bottom: 1px solid palette(mid); border-radius: 0; }
            QPushButton#roomItem:hover { background: palette(alternate-base); }
            QPushButton#roomItem:focus { border: 1px solid palette(highlight); }
        ''')
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(lambda:window.safe(self.poll));self.timer.start()
        self.refresh()

    def entries(self):
        records=self.window.library.all(); links=self.links.links()
        if self.project_id and self.project_id not in {p['id'] for p in records}:
            records += [p for p in self.window.library.all(True) if p['id']==self.project_id]
        from lumen_projects import projects
        rooms={r['id']:r for r in projects(self.window.workplace.store)}
        values=[dict(id='project:'+p['id'],project=p['id'],room=rooms.get(links.get(p['id'])),title=p['title']) for p in records]
        # Archived projects retain their link, so their rooms do not reappear as new projects.
        values += [dict(id='room:'+r['id'],project='',room=r,title=r['name']) for r in rooms.values() if r['id'] not in links.values()]
        return values

    def refresh(self):
        self.values=self.entries();clear(self.strip)
        selected=('project:'+self.project_id) if self.project_id else ('room:'+self.room_id)
        value=next((v for v in self.values if v['id']==selected),self.values[0] if self.values else None)
        self.project_id=value['project'] if value else '';self.room_id=(value.get('room') or {}).get('id','') if value else ''
        visible=self.values[:3]
        if value and value not in visible:visible[-1]=value
        for i,item in enumerate(visible):
            b=button(item['title'].replace('&','&&'),lambda _=False,v=item['id']:self.window.safe(self.choose,v));b.setAccessibleName(item['title']);b.setObjectName('roomChoice');b.setCheckable(True);b.setChecked(item==value);b.setToolTip(item['title']);self.strip.addWidget(b,0,i)
        self.all_rooms.blockSignals(True);self.all_rooms.clear()
        for item in self.values:self.all_rooms.addItem(item['title'],item['id'])
        if value:self.all_rooms.setCurrentIndex(self.all_rooms.findData(value['id']))
        self.all_rooms.blockSignals(False);self.all_rooms.setVisible(len(self.values)>3)
        self.heading.setText(value['title'] if value else tr('Dein erstes Projekt'))
        self.resume.setEnabled(bool(value and value.get('room')))
        self.scope_picker.blockSignals(True);self.scope_picker.clear();self.scope_picker.addItem(tr('Alle Vorhaben'), '')
        if self.project_id:
            for item in self.window.projects.items(self.project_id,''):self.scope_picker.addItem(item['title'],item['id'])
        index=self.scope_picker.findData(self.scope);self.scope_picker.setCurrentIndex(max(0,index));self.scope=self.scope_picker.currentData() or '';self.scope_picker.blockSignals(False)
        self.scope_picker.setEnabled(bool(self.project_id));self.plan_button.setEnabled(bool(value));self.options.setEnabled(bool(value))
        self.render()

    def choose(self, identity):
        if not self.window.editor.allow_leave():return
        self.window.editor.hide()
        if self.prompt.text().strip() and identity not in ('project:'+self.project_id,'room:'+self.room_id):
            self.all_rooms.setCurrentIndex(self.all_rooms.findData('project:'+self.project_id if self.project_id else 'room:'+self.room_id))
            raise ValueError(tr('Bitte den Gesprächsentwurf zuerst besprechen oder leeren.'))
        value=next((v for v in self.entries() if v['id']==identity),None)
        if not value:raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        self.project_id=value['project'];self.room_id=(value.get('room') or {}).get('id','');self.scope='';self.chat_limit=5;self.refresh()

    def change_scope(self,index):
        if not self.window.editor.allow_leave():
            self.scope_picker.setCurrentIndex(max(0,self.scope_picker.findData(self.scope)));return
        self.window.editor.hide()
        if self.prompt.text().strip():
            self.scope_picker.setCurrentIndex(max(0,self.scope_picker.findData(self.scope)))
            self.feedback.setText(tr('Bitte den Gesprächsentwurf zuerst besprechen oder leeren.'));return
        self.scope=self.scope_picker.itemData(index) or '';self.render()

    def room(self):
        from lumen_projects import projects
        return next((r for r in projects(self.window.workplace.store) if r['id']==self.room_id),None)

    def ensure_project(self):
        if not self.project_id:
            room=self.room()
            if not room:raise ValueError(tr('Bitte zuerst ein Projekt anlegen.'))
            self.project_id=self.links.from_room(room)
        return self.project_id

    def ensure_room(self):
        if not self.room_id:self.room_id=self.links.ensure(self.ensure_project())['id']
        self.window.workplace.select_project(self.room_id)
        if not self.window.workplace.project or self.window.workplace.project['id']!=self.room_id:raise ValueError(tr('Projekt nicht mehr vorhanden.'))
        return self.window.workplace.project

    def plan(self, scope=None, tab=None):
        project=self.ensure_project()
        if not self.window.navigate(project,self.scope if scope is None else scope):return False
        if tab is not None:self.window.editor.show_page(tab)
        return True

    def create(self):self.window.create()
    def add_task(self):self.window.create_task()
    def add_initiative(self):self.window.create_initiative()

    def management(self):
        if not self.window.editor.allow_leave():return
        if self.project_id:self.window.navigate(self.project_id,self.scope)
        self.window.editor.hide();self.window.archived.setChecked(True);self.window.areas.setCurrentIndex(0)

    def project_action(self,callback):
        if not self.window.editor.allow_leave():return
        self.plan();callback()

    def record_chain(self):
        if self.project_id:return source_chain(self.window.projects,self.project_id,self.scope,self.window.workplace.store)
        room=self.room() or {}
        values=[dict(kind='folder',target=s['location'],title=s['label']) for s in room.get('sources',[])]
        values += [dict(kind='url',target=u,title=u) for u in room.get('urls',[])]
        values += [dict(kind='url' if p['kind']=='url' else 'file',target=p['url'],title=p['title']) for p in room.get('pins',[]) if p['kind'] in ('object','url')]
        return [dict(title=room.get('name',''),notes=room.get('note',''),resources=values)]

    def item_button(self, title, detail, callback):
        caption=title+('\n'+detail if detail else '')
        b=button(caption.replace('&','&&'),lambda:self.window.safe(callback));b.setAccessibleName(caption);b.setObjectName('roomItem');b.setToolTip(title);return b

    def render(self):
        for _,layout in self.columns:clear(layout)
        material,work,chats=[x[1] for x in self.columns]
        for box,title in ((material,'Material'),(work,'Vorhaben & nächste Schritte'),(chats,'Gespräche')):box.addWidget(label(tr(title),'heading'))
        chain=self.record_chain();seen=set()
        if self.project_id and self.window.library.get(self.project_id).get('server_bound'):
            material.addWidget(label(tr('Serverprojekt · Lokale Projektquellen werden nicht automatisch hochgeladen.'),'muted'))
        for record in chain:
            for source in record.get('resources',[]):
                if source['target'] in seen:continue
                seen.add(source['target']);kind=source['kind']
                item=self.item_button(source['title'],tr('Ordner · Dateien einzeln anheften') if kind=='folder' or (kind=='file' and Path(source['target']).is_dir()) else tr('Verknüpft · {0}',record['title']),lambda s=source:self.open_material(s))
                item.setContextMenuPolicy(Qt.CustomContextMenu)
                item.customContextMenuRequested.connect(lambda pos,b=item,r=record,s=source:self.material_menu(b,pos,r,s))
                material.addWidget(item)
            if record.get('notes','').strip():
                snippet=label(record['notes'][:300],'muted');snippet.setWordWrap(True);material.addWidget(snippet)
                material.addWidget(button(tr('Notiz bearbeiten'),lambda _=False,r=record:self.window.safe(self.edit_note,r)))
            for ref in record.get('server_attachments',[]):
                material.addWidget(self.item_button(ref.get('title') or tr('Servermaterial'),tr('Lumen Server'),lambda:self.plan(tab=1)))
        if not seen:material.addWidget(label(tr('Dateien, Webseiten und Notizen hier gemeinsam sammeln.'),'muted'))
        material.addWidget(button(tr('Material hinzufügen'),lambda:self.window.safe(self.edit_material),'list-add'))
        if self.project_id:
            from projects_data import STATES,KINDS
            for initiative in self.window.projects.items(self.project_id,''):
                if self.scope and initiative['id']!=self.scope:continue
                work.addWidget(self.item_button(initiative['title'],tr('Vorhaben'),lambda key=initiative['id']:self.plan(key)))
                for task in self.window.projects.items(self.project_id,initiative['id']):
                    state=tr(STATES.get(task.get('status'),'Offen')); repeat=tr(' · Wiederholung aktiv') if task.get('enabled') else ''
                    work.addWidget(self.item_button(task['title'],tr(KINDS.get(task['kind'],'Manuell'))+' · '+state+repeat,lambda key=task['id']:self.plan(key)))
        work.addWidget(button(tr('Aufgabe anlegen'),lambda:self.window.safe(self.add_task),'list-add',True))
        work.addWidget(button(tr('Vorhaben anlegen'),lambda:self.window.safe(self.add_initiative),'list-add'))
        if self.project_id:
            for flow in self.links.flows(self.project_id):
                if self.scope and flow['project_scope'] not in ('',self.scope):continue
                control=self.item_button(flow['name'],tr('Ablauf · {0}',tr('Aktiv') if flow.get('enabled') else tr('Manuell / pausiert')),lambda key=flow['id']:self.open_flow(key))
                control.setContextMenuPolicy(Qt.CustomContextMenu)
                control.customContextMenuRequested.connect(lambda pos,b=control,key=flow['id']:self.flow_menu(b,pos,key))
                work.addWidget(control)
        work.addWidget(button(tr('Bestehenden Ablauf hinzufügen'),lambda:self.window.safe(self.attach_flow)))
        room=self.room() or {}
        pins=list(room.get('pins',[]));saved=room.get('state',{}).get('chat',{})
        known=set();conversations=[]
        for pin in reversed(pins):
            if pin['kind']=='chat' and pin['chat']['session'] not in known:conversations.append(pin);known.add(pin['chat']['session'])
        if saved.get('session') and saved['session'] not in known:conversations.insert(0,dict(kind='chat',title=tr('Letztes gespeichertes Gespräch'),chat=saved))
        for pin in conversations[:self.chat_limit]:chats.addWidget(self.item_button(pin['title'],tr('In Lumen öffnen'),lambda p=pin:self.open_chat(p)))
        if not conversations:chats.addWidget(label(tr('Hefte das aktuelle Lumen-Gespräch an dieses Projekt.'),'muted'))
        if len(conversations)>self.chat_limit:chats.addWidget(button(tr('Mehr laden'),self.more_chats))
        chats.addWidget(button(tr('Aktuelles Gespräch anheften'),lambda:self.window.safe(self.room_action,'pin')))
        legacy=[p for p in pins if p['kind']=='task']
        pinned_ids={p['id'] for p in legacy}
        for key in room.get('state',{}).get('tasks',[]):
            if key in pinned_ids:continue
            task=self.window.workplace.store.task(key)
            if task:legacy.append(dict(kind='task',id=key,title=task['title']))
        if legacy:
            chats.addWidget(label(tr('Angeheftete Ausführungen'),'muted'))
            for pin in legacy:chats.addWidget(self.item_button(pin['title'],tr('Diagnose'),lambda p=pin:self.diagnostics(p['id'])))
        for box in (material,work,chats):box.addStretch()
        self.reflow()

    def select_initiative(self,key):
        self.scope_picker.setCurrentIndex(self.scope_picker.findData(key));self.change_scope(self.scope_picker.currentIndex())

    def more_chats(self):self.chat_limit+=5;self.render()

    def open_chat(self,pin):
        self.ensure_room()
        # A saved conversation may not yet be in the explicit pin list.
        page=self.window.workplace
        if not any(p.get('kind')=='chat' and p['chat']['session']==pin['chat']['session'] for p in page.project.get('pins',[])):
            clean=dict(kind='chat',title=pin['title'],chat={k:pin['chat'][k] for k in ('session','directory')})
            page.rooms.add_pin(clean)
        page.remote_action('chat',pin['chat']['session'])

    def room_action(self,action):
        self.window.save();self.ensure_room();self.window.workplace.remote_action(action);self.refresh()

    def discuss(self):
        if not self.prompt.text().strip():self.prompt.setFocus();return
        self.window.save();self.ensure_room();self.ensure_project()
        import json
        from lumen_detail_routes import room_action
        room_action(self.room_id,'project-discuss',json.dumps(dict(project=self.project_id,scope=self.scope,prompt=self.prompt.text())))
        self.prompt.clear();self.feedback.setText(tr('Gesprächsentwurf in Lumen geöffnet.'))

    def open_material(self,source):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from tools_data import web_url
        target=source['target']
        if target.startswith('lumen:'):
            from interop_open import open_url
            open_url(target,self.window.library.root.parent)
        elif source['kind']=='url':
            if not QDesktopServices.openUrl(QUrl(web_url(target))):raise ValueError(tr('Website konnte nicht geöffnet werden.'))
        else:open_path(target)

    def edit_material(self):self.plan(tab=1)

    def add_files(self):
        if self.plan(tab=1):self.window.open_material_editor('file')
    def add_folder(self):
        if self.plan(tab=1):self.window.open_material_editor('folder')
    def add_link(self):
        if self.plan(tab=1):self.window.open_material_editor('url')

    def edit_note(self,record):
        if record.get('id'):self.plan(record['id'] if record.get('kind')=='initiative' else '',0);return
        # A room's existing note retains its original owner, edited in this same sidebar.
        self.ensure_project()
        if self.plan():self.window.editor.edit_room_note(self.room_id)

    def material_menu(self,widget,pos,record,source):
        menu=QMenu(widget);menu.addAction(tr('Öffnen'),lambda:self.window.safe(self.open_material,source))
        menu.addAction(tr('Verknüpfung entfernen'),lambda:self.window.safe(self.remove_material,record,source))
        menu.exec(widget.mapToGlobal(pos))

    def remove_material(self,record,source):
        self.window.save()
        if record.get('id'):
            key=record['id'];is_item=record.get('kind')=='initiative'
            owner=self.window.projects if is_item else self.window.library
            current=owner.get(key)
            if current.get('resources',[])!=record.get('resources',[]):raise ValueError(tr('Material wurde inzwischen geändert. Bitte erneut öffnen.'))
            owner.update(key,resources=[v for v in current.get('resources',[]) if v!=source])
            if self.window.current==self.project_id:self.window.navigate(self.project_id,self.window.scope)
        else:
            self.ensure_room();page=self.window.workplace;room=page.project;target=source['target']
            page.rooms.save(sources=[s for s in room.get('sources',[]) if s['location']!=target],urls=[u for u in room.get('urls',[]) if u!=target],pins=[p for p in room.get('pins',[]) if p.get('url')!=target])
        self.window.areas.setCurrentIndex(3);self.refresh();self.feedback.setText(tr('Verknüpfung entfernt. Die Datei bleibt erhalten.'))

    def add_note(self):
        if self.plan(tab=1):self.window.open_material_editor('wissen')

    def flow_menu(self,widget,pos,key):
        menu=QMenu(widget)
        def detach():self.links.detach_flow(self.project_id,key);self.refresh()
        menu.addAction(tr('Aus diesem Vorhaben entfernen'),lambda:self.window.safe(detach));menu.exec(widget.mapToGlobal(pos))

    def edit_environment(self):
        if not self.plan(scope=''):return
        self.window.editor.edit_environment(self.ensure_room())

    def environment(self):
        if not self.window.editor.allow_leave():return
        self.ensure_room();self.window.workplace.rooms.open(self.room_id)
        rooms=self.window.workplace.rooms
        for index in (0,2,3):rooms.tabs.setTabVisible(index,False)
        rooms.tabs.setCurrentIndex(1)
        rooms.room_footer.hide()
        from PySide6.QtWidgets import QPushButton
        for control in rooms.detail.findChildren(QPushButton):
            if control.text()==tr('‹ Alle Projekte'):control.hide()
        self.window.areas.setCurrentIndex(1)

    def diagnostics(self,task=None):
        from lumen_detail_routes import open_tasks
        open_tasks(task)

    def attach_flow(self):
        project=self.ensure_project();flows=self.window.workplace.store.workflows()
        if not flows:raise ValueError(tr('Noch kein Ablauf vorhanden. Über „Alle Automationen“ einen Ablauf anlegen.'))
        names=[f['name']+' · '+f['id'][:8] for f in flows]
        name,ok=QInputDialog.getItem(self,tr('Ablauf zuordnen'),tr('Vorhandener Ablauf'),names,0,False)
        if ok:self.links.attach_flow(project,self.scope,flows[names.index(name)]['id']);self.refresh()

    def open_flow(self,key):
        self.window.open_section('automations');listing=self.window.automations.flows
        for i in range(listing.count()):
            if listing.item(i).data(Qt.UserRole)['id']==key:listing.setCurrentRow(i);return
        raise ValueError(tr('Ablauf nicht mehr vorhanden.'))

    def poll(self):
        if not self.isVisible():return
        signature=repr((self.entries(),self.links.links(),self.window.projects.items(self.project_id) if self.project_id else [],self.links.flows(self.project_id)))
        if signature!=self.signature:self.signature=signature;self.refresh()

    def resizeEvent(self,event):super().resizeEvent(event);self.reflow()

    def reflow(self):
        if not hasattr(self,'grid'):return
        for control in (self.heading,self.resume,self.options):self.title_grid.removeWidget(control)
        if self.scroller.width()<560:
            self.title_grid.addWidget(self.heading,0,0,1,3);self.title_grid.addWidget(self.resume,1,0,1,2);self.title_grid.addWidget(self.options,1,2)
        else:
            self.title_grid.addWidget(self.heading,0,0);self.title_grid.addWidget(self.resume,0,1);self.title_grid.addWidget(self.options,0,2)
        self.title_grid.setColumnStretch(0,1)
        columns=3 if self.scroller.width()>=970 else 2 if self.scroller.width()>=530 else 1
        if hasattr(self.window,'editor'):
            width=min(480,max(350,int(self.width()*.43)));self.window.editor.setFixedWidth(width)
        for i,(pane,_) in enumerate(self.columns):self.grid.addWidget(pane,i//columns,i%columns)
        for i in range(3):self.grid.setColumnStretch(i,1 if i<columns else 0)

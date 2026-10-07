"""Native room landing page and project workbench; references never copy content."""
from pathlib import Path
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,QScrollArea,
    QStackedWidget,QTabWidget,QPushButton,QLineEdit,QMenu,QFileDialog,QInputDialog,
    QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QMessageBox,QFormLayout)
from lumen_i18n import tr
from lumen_workplace import text,button,row,table,fill,date
from file_spaces import Catalog
from network import is_network_address
from interop_data import Registry
import lumen_projects as projects
import lumen_history as history


def clear(layout):
    while layout.count():
        item=layout.takeAt(0)
        if item.widget():item.widget().deleteLater()
        elif item.layout():clear(item.layout())


def card(parent=None,hero=False):
    widget=QFrame(parent);widget.setObjectName('roomHero' if hero else 'roomCard')
    box=QVBoxLayout(widget);box.setContentsMargins(22,20,22,20);box.setSpacing(12)
    return widget,box


def scroll():
    area=QScrollArea();area.setWidgetResizable(True);area.setFrameShape(QFrame.NoFrame)
    content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(0,0,8,0);box.setSpacing(22)
    area.setWidget(content);return area,box


def heading(title,subtitle):
    box=QVBoxLayout();box.setSpacing(7);box.addWidget(text(title,'roomHeading'));box.addWidget(text(subtitle,'muted'));return box


class Rooms(QWidget):
    def __init__(self,page):
        super().__init__(page);self.page=page;self.values=[];self.expanded=False;self.preview_cache={};self.preview_labels={}
        self.setObjectName('rooms');root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0)
        self.stack=QStackedWidget();root.addWidget(self.stack)
        home,home_box=scroll();self.home_box=home_box;self.stack.addWidget(home)
        self.detail=QWidget();detail=QVBoxLayout(self.detail);detail.setContentsMargins(0,0,0,0);detail.setSpacing(17)
        top=QHBoxLayout();top.addWidget(button(tr('‹ Alle Arbeitsräume'),self.home));top.addStretch()
        self.resume_button=button(tr('Weiterarbeiten'),page.resume,True);top.addWidget(self.resume_button)
        edit=button(tr('Raum bearbeiten'),page.edit_project);top.addWidget(edit);detail.addLayout(top)
        self.title=text('','roomHeading');detail.addWidget(self.title)
        self.tabs=QTabWidget();detail.addWidget(self.tabs,1)
        board,board_box=scroll();self.board_box=board_box;self.tabs.addTab(board,tr('Werkbank'))
        files=QWidget();box=QVBoxLayout(files);box.setContentsMargins(0,16,0,0)
        box.addWidget(text(tr('DATEIQUELLEN'),'eyebrow'))
        page.sources=table([tr('Herkunft'),tr('Ort'),tr('Verfügbarkeit')]);page.sources.setMaximumHeight(165);box.addWidget(page.sources)
        row(box,[(tr('Quellen prüfen'),page.scan),(tr('Quelle öffnen / verbinden'),page.open_source),(tr('Alle Dateien gemeinsam'),page.combined)])
        page.recent_label=text(tr('ZULETZT GEÄNDERT'),'eyebrow');box.addWidget(page.recent_label)
        page.recent=table([tr('Datei'),tr('Herkunft'),tr('Geändert'),tr('Größe')]);box.addWidget(page.recent,1)
        page.sources.cellDoubleClicked.connect(lambda *_:page.open_source());page.recent.cellDoubleClicked.connect(page.open_recent)
        self.tabs.addTab(files,tr('Dateien'))
        self.tasks=table([tr('Auftrag'),tr('Status')]);self.tasks.cellDoubleClicked.connect(lambda *_:self.open_selected_task());self.tabs.addTab(self.tasks,tr('Aufträge'))
        self.history=table([tr('Änderung'),tr('Wann')]);self.tabs.addTab(self.history,tr('Verlauf'))
        from server_workspace import ServerWorkspace
        self.server_workspace=ServerWorkspace(self);self.tabs.addTab(self.server_workspace,tr('Server'))
        self.tabs.currentChanged.connect(lambda i:page.scan() if i==1 else None)
        composer=QHBoxLayout();self.prompt=QLineEdit();self.prompt.setObjectName('roomComposer');self.prompt.setPlaceholderText(tr('Lumen zu diesem Arbeitsraum fragen …'));self.prompt.setAccessibleName(tr('Frage zum Arbeitsraum'));composer.addWidget(self.prompt,1)
        send=button(tr('Besprechen →'),lambda:self.page.guard(self.discuss));send.setToolTip(tr('Als Entwurf in Lumen öffnen'));self.prompt.returnPressed.connect(send.click);composer.addWidget(send);detail.addLayout(composer)
        row(detail,[(tr('Aktuellen Stand merken'),self.page.capture),(tr('Arbeitsmodi in Lumen System'),self.page.open_modes)])
        self.stack.addWidget(self.detail)
        self.setStyleSheet('''QWidget#rooms { background: transparent; }
            QWidget#rooms QLabel { font-size: 13px; }
            QWidget#rooms QPushButton { font-size: 12px; border-radius: 7px; }
            QWidget#rooms QLabel#eyebrow { font-size: 10px; letter-spacing: 1px; }
            QWidget#rooms QLabel#roomHeading { font-size: 29px; font-weight: 600; }
            QWidget#rooms QLabel#roomTitle { font-size: 23px; font-weight: 600; }
            QWidget#rooms QLabel#roomSection { font-size: 16px; font-weight: 600; }
            QFrame#roomHero { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 13px; }
            QFrame#roomCard { background: palette(base); border: 1px solid palette(mid); border-radius: 11px; }
            QFrame#roomHero QLabel, QFrame#roomCard QLabel { background: transparent; border: none; }
            QPushButton#roomLink { text-align: left; padding: 10px 12px; }
            QPushButton#roomQuiet { color: palette(link); background: transparent; border-color: transparent; }
            QTabWidget::pane { border: none; } QTabBar::tab { border: none; border-bottom: 2px solid transparent; padding: 10px 17px; background: transparent; }
            QTabBar::tab:selected { color: palette(link); border-bottom-color: palette(link); }
            QLineEdit#roomComposer { padding: 14px; font-size: 14px; }
        ''')

    def home(self):
        self.stack.setCurrentIndex(0);self.render_home()

    def open(self,identity):
        if (self.page.project or {}).get('id')!=identity:self.prompt.clear()
        self.page.select_project(identity);self.stack.setCurrentIndex(1);self.tabs.setCurrentIndex(0)
        self.server_workspace.set_room(identity)
        self.page.store.set_setting('workplace/last',identity)
        self.load_previews()

    def render(self,values):
        self.values=values;self.render_home();self.render_board()

    def source_summary(self,project):
        sources=project.get('sources',[])
        return ' · '.join(s['label'] for s in sources[:3]) or tr('Keine Dateiquellen')

    def render_home(self):
        box=self.home_box;clear(box)
        top=QHBoxLayout();top.addLayout(heading(tr('Wo möchtest du weitermachen?'),tr('Ein Raum hält zusammen, was zu einer Sache gehört.')),1)
        top.addWidget(button(tr('+ Neuer Raum'),lambda:self.page.edit_project(new=True)));box.addLayout(top)
        if not self.values:
            item,content=card(hero=True);content.addWidget(text(tr('Dein erster Arbeitsraum'),'roomTitle'))
            content.addWidget(text(tr('Gib ihm einen Namen und wähle einen Ordner. Dateien, Notizen und Gespräche kannst du danach anheften.'),'muted'))
            content.addWidget(button(tr('Arbeitsraum anlegen'),lambda:self.page.edit_project(new=True),True),0,Qt.AlignLeft)
            box.addWidget(item);box.addStretch();return
        last=self.page.store.setting('workplace/last','')
        featured=next((p for p in self.values if p['id']==last),max(self.values,key=lambda p:p.get('updated',0)))
        item,hero=card(hero=True);hero.addWidget(text(tr('HIER GEHT ES WEITER'),'eyebrow'))
        horizontal=QHBoxLayout();left=QVBoxLayout();left.setSpacing(14)
        left.addWidget(text(featured['name'],'roomTitle'));left.addWidget(text(featured.get('note') or tr('Deine Unterlagen und dein letzter Arbeitsstand warten hier.'),'muted'))
        left.addWidget(text(self.source_summary(featured),'muted'))
        actions=QHBoxLayout();actions.addWidget(button(tr('Weiterarbeiten →'),lambda:self.resume(featured),True));actions.addWidget(button(tr('Raum ansehen'),lambda:self.open(featured['id'])));actions.addStretch();left.addLayout(actions)
        horizontal.addLayout(left,3);right=QVBoxLayout();right.setSpacing(9);right.addWidget(text(tr('DEIN ARBEITSSTAND'),'eyebrow'))
        pins=featured.get('pins',[])[:3]
        for pin in pins:self.pin_row(right,pin)
        if not pins:
            for source in featured.get('sources',[])[:3]:
                b=button(source['label'],lambda _=False,s=source:self.page.guard(lambda:self.page.files(True).navigate(s['location'])))
                b.setIcon(QIcon.fromTheme('folder'));b.setToolTip(source['location']);right.addWidget(b)
        if featured.get('state',{}).get('chat',{}).get('session'):right.addWidget(text(tr('Letztes Gespräch beim Weiterarbeiten verfügbar.'),'muted'))
        right.addStretch();horizontal.addLayout(right,2);hero.addLayout(horizontal);box.addWidget(item)
        header=QHBoxLayout();header.addWidget(text(tr('Weitere Arbeitsräume'),'roomSection'));header.addStretch()
        others=[p for p in self.values if p['id']!=featured['id']]
        if len(others)>6:header.addWidget(button(tr('Weniger anzeigen') if self.expanded else tr('Alle Räume'),self.more))
        box.addLayout(header);grid=QGridLayout();grid.setSpacing(15);cols=3 if self.width()>=1000 else 2 if self.width()>=650 else 1
        for i,project in enumerate(others if self.expanded else others[:6]):
            item,content=card();content.addWidget(text(project['name'],'roomSection'));content.addWidget(text((project.get('note') or tr('Noch keinen nächsten Schritt festgehalten.'))[:180],'muted'))
            content.addWidget(text(self.source_summary(project),'muted'));content.addStretch()
            content.addWidget(button(tr('Raum öffnen →'),lambda _=False,p=project:self.open(p['id'])));grid.addWidget(item,i//cols,i%cols)
        box.addLayout(grid)
        foot=QHBoxLayout();foot.addWidget(text(tr('Transfers und Änderungen bleiben unter „Aktivität“ erreichbar.'),'muted'));foot.addStretch();foot.addWidget(button(tr('Aktivität ansehen →'),lambda:self.page.tabs.setCurrentIndex(1)));box.addLayout(foot);box.addStretch()

    def more(self):self.expanded=not self.expanded;self.render_home()

    def resume(self,project):
        self.page.select_project(project['id']);self.page.resume()

    def render_board(self):
        box=self.board_box;clear(box);project=self.page.project
        self.task_labels={};self.preview_labels={}
        if not project:self.title.setText('');self.stack.setCurrentIndex(0);return
        self.title.setText(project['name']);self.task_labels={};self.preview_labels={}
        top=QHBoxLayout();top.addWidget(text(tr('Dateien, Wissen und Gespräche im selben Zusammenhang.'),'muted'),1)
        add=button(tr('+ Hinzufügen'),lambda:None,True);menu=QMenu(add)
        for title,fn in [(tr('Dateien …'),self.add_files),(tr('Wissen-Notiz …'),self.add_note),(tr('Weblink …'),self.add_url),(tr('Aktuelles Gespräch'),self.add_conversation),(tr('Auftrag …'),self.add_task)]:menu.addAction(title,lambda _=False,f=fn:self.page.guard(f))
        add.setMenu(menu);top.addWidget(add);box.addLayout(top)
        lanes=QGridLayout();lanes.setSpacing(18);columns=[]
        for i,title in enumerate([tr('WISSEN & NÄCHSTE SCHRITTE'),tr('DATEIEN & QUELLEN'),tr('LUMEN & AUFTRÄGE')]):
            lane=QWidget();column=QVBoxLayout(lane);column.setContentsMargins(0,0,0,0);column.setSpacing(13);column.addWidget(text(title,'eyebrow'));columns.append(column)
            lanes.addWidget(lane,0,i) if self.width()>=850 else lanes.addWidget(lane,i,0)
        note,note_box=card();note_box.addWidget(text(tr('Dein nächster Schritt'),'roomSection'));note_box.addWidget(text(project.get('note') or tr('Wo möchtest du beim nächsten Mal weitermachen?'),'muted'))
        note_box.addWidget(button(tr('Notiz bearbeiten'),self.edit_note));columns[0].addWidget(note)
        for pin in project.get('pins',[]):
            lane=0 if pin['kind']=='object' and pin.get('app')=='wissen' else 2 if pin['kind'] in ('chat','task') else 1
            self.pin_card(columns[lane],pin)
        if project.get('sources'):
            item,content=card();content.addWidget(text(tr('Dateiquellen'),'roomSection'))
            for source in project['sources']:
                control=button(source['label']+'  ↗',lambda _=False,s=source:self.page.guard(lambda:self.page.files(True).navigate(s['location'])))
                control.setObjectName('roomLink');control.setIcon(QIcon.fromTheme('network-server' if is_network_address(source['location']) else 'folder'));control.setToolTip(source['location']);content.addWidget(control)
                content.addWidget(text(tr('Netzwerk · beim Öffnen verbinden') if is_network_address(source['location']) else tr('Dieser Rechner'),'muted'))
            columns[1].addWidget(item)
        for url in project.get('urls',[]):self.pin_card(columns[1],dict(kind='url',title=url,url=url,legacy=True))
        chat=project.get('state',{}).get('chat',{})
        if chat.get('session') and not any(p['kind']=='chat' for p in project.get('pins',[])):
            self.pin_card(columns[2],dict(kind='chat',title=tr('Letztes gespeichertes Gespräch'),chat=chat,legacy=True))
        tasks=set(project.get('state',{}).get('tasks',[]))-{p.get('id') for p in project.get('pins',[]) if p['kind']=='task'}
        for task in self.page.store.tasks():
            if task['id'] in tasks:self.pin_card(columns[2],dict(kind='task',id=task['id'],title=task['title'],legacy=True))
        if columns[2].count()==1:columns[2].addWidget(text(tr('Hefte ein Gespräch oder einen vorhandenen Auftrag an. Die Ergebnisse erscheinen hier.'),'muted'))
        for column in columns:column.addStretch()
        box.addLayout(lanes)
        self.refresh_tasks()
        box.addStretch()

    def save(self,**changes):
        previous=self.page.project
        # Compare with the rendered snapshot; never overwrite another window's edits.
        value=dict(previous,**changes,updated=time.time())
        Catalog(self.page.store).put('room',value,previous)
        history.record(self.page.store,tr('Arbeitsraum aktualisiert: {0}',value['name']),'store-setting',previous,value,'files/spaces/room/'+value['id'])
        try:
            window=self.page.files()
            if window.spaces.active_room and window.spaces.active_room['id']==value['id']:window.spaces.active_room=value
        except ValueError:pass
        self.page.refresh_projects(value['id'])

    def add_pin(self,pin):
        pin=projects.validate_pin(pin)
        pins=list(self.page.project.get('pins',[]))
        if pin in pins:return
        if len(pins)>=60:raise ValueError(tr('Höchstens 60 Inhalte pro Arbeitsraum anheften.'))
        self.save(pins=pins+[pin])
        if pin.get('app')=='wissen':self.load_previews()

    def edit_note(self):
        note,ok=QInputDialog.getMultiLineText(self,tr('Nächster Schritt'),tr('Wo geht es weiter?'),self.page.project.get('note',''))
        if ok:
            if len(note)>10000:self.page.status.setText(tr('Die Notiz darf höchstens 10.000 Zeichen enthalten.'));return
            self.page.guard(lambda:self.save(note=note))

    def add_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,tr('Dateien anheften'))
        for path in paths:
            from interop_sources import from_paths
            ref=from_paths([path])['source'];url=Registry().register(ref)
            self.add_pin(dict(kind='object',app=ref['app'],title=Path(path).name,url=url))

    def add_url(self):
        url,ok=QInputDialog.getText(self,tr('Weblink anheften'),'HTTP(S):')
        if ok and url.strip():self.add_pin(dict(kind='url',url=url.strip(),title=url.strip()))

    def pick(self,title,items,callback):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(540,430);box=QVBoxLayout(dialog)
        search=QLineEdit();search.setPlaceholderText(tr('Suchen …'));box.addWidget(search)
        listing=QListWidget();box.addWidget(listing)
        for title,value in items:
            item=QListWidgetItem(title);item.setData(Qt.UserRole,value);listing.addItem(item)
        search.textChanged.connect(lambda query:[listing.item(i).setHidden(query.casefold() not in listing.item(i).text().casefold()) for i in range(listing.count())])
        controls=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);controls.accepted.connect(dialog.accept);controls.rejected.connect(dialog.reject);box.addWidget(controls)
        listing.itemDoubleClicked.connect(lambda *_:dialog.accept())
        if not items:box.addWidget(text(tr('Keine passenden Einträge vorhanden.'),'muted'))
        if dialog.exec()==QDialog.Accepted and listing.currentItem() and not listing.currentItem().isHidden():callback(listing.currentItem().data(Qt.UserRole))
        dialog.deleteLater()

    def add_note(self):
        identity=self.page.project['id'];self.page.status.setText(tr('Notizen werden geladen …'))
        def ready(value,error):
            if not self.page.project or self.page.project['id']!=identity:return
            self.page.status.setText(error or '')
            if error:return
            def chosen(ref):self.page.guard(lambda:self.add_pin(dict(kind='object',app='wissen',title=ref['title'],url=Registry().register(ref))))
            self.pick(tr('Wissen-Notiz anheften'),[(r['title']+' · '+r['id'],r) for r in value],chosen)
        self.page.job('notes',{},ready,timeout=12000)

    def add_conversation(self):
        chat=self.page.files().spaces.chat()
        if not chat or not chat.backend.session:raise ValueError(tr('Zuerst ein Gespräch mit Lumen öffnen.'))
        self.add_pin(dict(kind='chat',title=chat.sessions.currentText() or tr('Gespräch'),chat=dict(directory=chat.backend.directory,session=chat.backend.session)))

    def add_task(self):
        self.pick(tr('Auftrag anheften'),[(t['title'],t) for t in self.page.store.tasks(include_dismissed=False)],lambda t:self.add_pin(dict(kind='task',id=t['id'],title=t['title'])))

    def pin_row(self,box,pin):
        b=button(pin['title'][:95],lambda:self.page.guard(lambda:self.open_pin(pin)));b.setObjectName('roomLink');b.setToolTip(pin['title'])
        b.setIcon(QIcon.fromTheme('document-open' if pin['kind']=='object' else 'dialog-messages' if pin['kind']=='chat' else 'view-task' if pin['kind']=='task' else 'internet-web-browser'));box.addWidget(b)

    def pin_card(self,box,pin):
        item,content=card();header=QHBoxLayout();title=text(pin['title'][:160],'roomSection');title.setToolTip(pin['title']);header.addWidget(title,1)
        if not pin.get('legacy'):
            more=button('···',lambda:None);more.setAccessibleName(tr('Verknüpfung verwalten'));menu=QMenu(more)
            pins=self.page.project.get('pins',[]);index=pins.index(pin)
            for title,offset in [(tr('Nach oben'),-1),(tr('Nach unten'),1)]:
                action=menu.addAction(title,lambda _=False,o=offset,p=pin:self.page.guard(lambda:self.move_pin(p,o)));action.setEnabled(0<=index+offset<len(pins))
            if pin['kind'] in ('object','url'):
                auto=menu.addAction(tr('Beim Weiterarbeiten öffnen'));auto.setCheckable(True);auto.setChecked(pin.get('resume',False))
                auto.triggered.connect(lambda checked,p=pin:self.page.guard(lambda:self.save(pins=[dict(v,resume=checked) if v==p else v for v in self.page.project.get('pins',[])])))
            menu.addAction(tr('Aus Arbeitsraum entfernen'),lambda:self.page.guard(lambda:self.save(pins=[p for p in self.page.project.get('pins',[]) if p!=pin])));more.setMenu(menu);header.addWidget(more)
        content.addLayout(header)
        if pin.get('app')=='wissen':
            preview=text(self.preview_cache.get(pin['url'],''),'muted');preview.setMaximumHeight(105);content.addWidget(preview);self.preview_labels[pin['url']]=preview
        hint={'object':tr('Wissen · verknüpfte Notiz') if pin.get('app')=='wissen' else tr('Originaldatei · verknüpft'),'url':tr('Website · verknüpft'),'chat':tr('Lumen · Gespräch'),'task':tr('Lumen · Auftrag')}[pin['kind']]
        hint_label=text(hint,'muted');content.addWidget(hint_label)
        if pin.get('app')=='files':
            try:
                origin=str(Path(Registry().resolve(pin['url'])['path']).parent)
                label=text(origin[-100:],'muted');label.setToolTip(origin);content.addWidget(label)
            except (ValueError,KeyError):pass
        if pin['kind']=='task':
            self.task_labels[pin['id']]=hint_label;self.refresh_tasks()
        content.addWidget(button(tr('Öffnen →'),lambda:self.page.guard(lambda:self.open_pin(pin))));box.addWidget(item)

    def load_previews(self):
        project=self.page.project
        if not project:return
        urls=[p['url'] for p in project.get('pins',[]) if p.get('app')=='wissen'][:8]
        if not urls:return
        identity=project['id']
        def ready(value,error):
            if not self.page.project or self.page.project['id']!=identity:return
            for url in urls:
                snippet=(value or {}).get(url,tr('Vorschau nicht verfügbar'))
                self.preview_cache[url]=snippet
                if url in self.preview_labels:self.preview_labels[url].setText(snippet)
        self.page.job('room-notes',{'urls':urls},ready,timeout=8000)

    def refresh_tasks(self):
        values={t['id']:t for t in self.page.store.tasks()}
        names={'draft':tr('Entwurf'),'pending':tr('Wartet'),'running':tr('Läuft'),'completed':tr('Erledigt'),'failed':tr('Fehlgeschlagen'),'cancelled':tr('Abgebrochen')}
        for key,label in getattr(self,'task_labels',{}).items():
            task=values.get(key);label.setText(names.get(task['status'],task['status']) if task else tr('Nicht mehr vorhanden'))
        project=self.page.project or {};ids=set(project.get('state',{}).get('tasks',[]))|{p['id'] for p in project.get('pins',[]) if p['kind']=='task'}
        fill(self.tasks,[(key,[values[key]['title'],names.get(values[key]['status'],values[key]['status'])]) for key in sorted(ids) if key in values])
        target='files/spaces/room/'+project.get('id','')
        fill(self.history,[(v['id'],[v['title'],date(v['created'])]) for v in history.entries(self.page.store) if v.get('target')==target])

    def open_selected_task(self):
        from lumen_workplace import chosen
        identity=chosen(self.tasks)
        if identity:self.page.guard(lambda:self.page.files().spaces.open_task(self.page.store.task(identity)))


    def move_pin(self,pin,offset):
        pins=list(self.page.project.get('pins',[]));index=pins.index(pin);other=index+offset
        if 0<=other<len(pins):pins[index],pins[other]=pins[other],pins[index];self.save(pins=pins)

    def resume_pins(self,project):
        for pin in project.get('pins',[]):
            if pin.get('resume') and pin['kind'] in ('object','url'):self.page.guard(lambda p=pin:self.open_pin(p))

    def chat_ready(self):
        window=self.page.files();chat=window.spaces.chat()
        if chat:
            if chat.backend.busy or chat.context_tools.process:raise ValueError(tr('Bitte zuerst den laufenden Vorgang abschließen.'))
            if chat.composer.toPlainText().strip() and QMessageBox.question(self,tr('Entwurf behalten?'),tr('Der aktuelle Gesprächsentwurf würde ersetzt. Fortfahren?'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return None
        window.ask_lumen('open',[]);return window.spaces.chat()

    def open_pin(self,pin):
        projects.validate_pin({k:v for k,v in pin.items() if k!='legacy'})
        if pin['kind']=='object':
            from interop_open import open_url
            ref=Registry().resolve(pin['url'])
            if ref['app']=='files':self.page.files(True).open_path(ref['path'])
            else:open_url(pin['url'])
        elif pin['kind']=='url':
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            if not QDesktopServices.openUrl(QUrl(pin['url'])):raise ValueError(tr('Website konnte nicht geöffnet werden.'))
        elif pin['kind']=='task':
            task=self.page.store.task(pin['id'])
            if not task:raise ValueError(tr('Auftrag nicht mehr vorhanden.'))
            self.page.files().spaces.open_task(task)
        else:
            chat=self.chat_ready()
            if chat:
                saved=pin['chat'];chat.backend.new_conversation(saved['directory']);chat.backend.select_session(saved['session'])

    def discuss(self):
        prompt=self.prompt.text().strip()
        if not prompt:return
        chat=self.chat_ready()
        if not chat:return
        project=self.page.project;paths=[];references=[]
        window=self.page.files()
        for source in project.get('sources',[]):
            path=window.spaces.local_reference(source['location'])
            if is_network_address(path):references.append(source['label']+': '+path)
            else:paths.append(path)
        for pin in project.get('pins',[]):
            if pin['kind']=='object':
                ref=Registry().resolve(pin['url'])
                if ref.get('path'):paths.append(ref['path'])
            elif pin['kind']=='url':references.append(pin['url'])
        chat.paths=list(dict.fromkeys(paths));chat.update_context()
        context=tr('Arbeitsraum: {0}\nNächster Schritt: {1}',project['name'],project.get('note',''))
        chat.composer.setPlainText(context+'\n'+'\n'.join(references)+'\n\n'+prompt)
        # Explicit question opens an editable draft in Lumen; no background submission.
        self.prompt.clear()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        width=self.width();columns=3 if width>=1000 else 2 if width>=650 else 1
        signature=(columns,width>=850)
        if getattr(self,'_columns',None)!=signature:
            self._columns=signature
            if self.values:QTimer.singleShot(0,self.reflow)

    def reflow(self):
        if self.values:self.render_home();self.render_board()


class CreateRoom(QDialog):
    def __init__(self,store,parent):
        super().__init__(parent);self.store=store;self.saved=None
        self.setWindowTitle(tr('Lumen · Neuer Arbeitsraum'));self.resize(510,310)
        box=QVBoxLayout(self);box.setContentsMargins(24,24,24,24);box.setSpacing(16)
        box.addWidget(text(tr('Woran möchtest du arbeiten?'),'heading'))
        box.addWidget(text(tr('Ein Name und ein Ordner reichen. Alles Weitere kannst du später hinzufügen.'),'muted'))
        form=QFormLayout();self.name=QLineEdit();self.name.setPlaceholderText(tr('Zum Beispiel: Reiseplanung'));form.addRow(tr('Name'),self.name)
        self.folder=QLineEdit();self.folder.setPlaceholderText(tr('Ordner oder Netzwerkadresse'));form.addRow(tr('Ordner'),self.folder);box.addLayout(form)
        row(box,[(tr('Ordner wählen …'),self.local),(tr('Netzwerk …'),self.remote)])
        self.error=text('','muted');box.addWidget(self.error)
        controls=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);controls.accepted.connect(self.save);controls.rejected.connect(self.reject);box.addWidget(controls)
    def local(self):
        value=QFileDialog.getExistingDirectory(self,tr('Projektordner wählen'))
        if value:self.folder.setText(value)
    def remote(self):
        from network import ConnectDialog
        dialog=ConnectDialog(self)
        if dialog.exec()==QDialog.Accepted:self.folder.setText(dialog.url)
        dialog.deleteLater()
    def save(self):
        try:
            location=self.folder.text().strip()
            from network import server_label
            label=server_label(location) if is_network_address(location) else Path(location).name or tr('Ordner')
            self.saved=projects.save_project(self.store,None,self.name.text(),[dict(label=label,location=location)],[],[],'')
            self.accept()
        except (ValueError,OSError) as error:self.error.setText(str(error))

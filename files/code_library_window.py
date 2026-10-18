"""Native Code & Automation collection and real execution detail."""
import json
import sqlite3
from subprocess import SubprocessError
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QDesktopServices,QShortcut,QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QListWidget, QLineEdit, QComboBox,
    QPlainTextEdit, QFileDialog, QInputDialog, QMessageBox, QGroupBox, QTextBrowser, QScrollArea, QFrame, QHeaderView)
from lumen_i18n import tr
from lumen_store import Store, STATES
from code_library import Collection
from code_library_contract import KINDS, export_template
from tools_ui import button, label, row

HELP = json.loads(Path(__file__).with_name('code_library_help.json').read_text(encoding='utf-8'))

TITLES = {'app':'Kleine Apps', 'tool':'Werkzeuge', 'automation':'Automationen', 'code':'Code-Projekte'}


class CollectionWindow(QMainWindow):
    def __init__(self, store=None):
        super().__init__(); self.store=store or Store(); self.collection=Collection(self.store)
        self.library=SimpleNamespace(root=self.store.directory/'code-window'); self.library.root.mkdir(mode=0o700,exist_ok=True)
        self.current=None;self.loading=False;self.dirty=False;self.category_index=0;self.coding_windows={}
        self.setWindowTitle(tr('Lumen Code & Automation'));self.resize(1240,820)
        from code_design import shell
        container=QWidget();main,nav,self.footer=shell(container);self.setCentralWidget(container)
        outer=QVBoxLayout(main);outer.setContentsMargins(30,26,30,24);outer.setSpacing(14)
        self.status=label('','codeMuted');outer.addWidget(self.status)
        self.categories=QListWidget();self.categories.setObjectName('codeCategories');self.categories.setIconSize(QSize(16,16));self.categories.setAccessibleName(tr('Sammlungsbereiche'))
        self.category_keys=['all','favorites','app','tool','automation','code','attention','archive']
        self.categories.addItems([tr(text) for text in ['Alle Einträge','Favoriten','Kleine Apps','Werkzeuge','Automationen','Code-Projekte','Braucht dich','Archiv']])
        from studio_design import icon
        for index,name in enumerate(['view-list-details','rating','view-grid','tools-wizard','view-process-tree','code-context','dialog-information','archive-extract']):self.categories.item(index).setIcon(icon(name));self.categories.item(index).setSizeHint(QSize(150,44))
        nav.addWidget(self.categories,1);nav.addWidget(label(tr('Deine Idee.\nDein nächster Helfer.'),'codeMuted'))
        self.pages=QStackedWidget();outer.addWidget(self.pages,1)
        self.build_collection();self.build_detail()
        self.categories.currentRowChanged.connect(self.change_category);self.categories.setCurrentRow(0)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh_result);self.timer.start(1500)

    def safe(self, function, *args):
        try:return function(*args)
        except (ValueError,OSError,RuntimeError,sqlite3.Error,SubprocessError) as error:
            self.status.setText(tr(str(error)))

    def build_collection(self):
        from code_collection_view import STYLE,EntryDelegate
        from studio_design import icon
        page=QWidget();page.setStyleSheet(STYLE);box=QVBoxLayout(page);box.setContentsMargins(0,0,0,0);box.setSpacing(18)
        head=QHBoxLayout();titles=QVBoxLayout();titles.setSpacing(8)
        self.collection_heading=label(tr('Meine Sammlung'),'codeTitle');titles.addWidget(self.collection_heading)
        self.collection_intro=label(tr('Deine Apps, Werkzeuge und Abläufe – bereit für den nächsten Einsatz.'),'codeSubtitle');titles.addWidget(self.collection_intro)
        head.addLayout(titles,1);head.addWidget(button(tr('Neu erstellen'),lambda:self.safe(self.create),'list-add',primary=True),0,Qt.AlignTop);box.addLayout(head)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Name oder Aufgabe suchen …'));self.search.setAccessibleName(tr('Sammlung durchsuchen'));self.search.setClearButtonEnabled(True);self.search.addAction(icon('edit-find'),QLineEdit.LeadingPosition)
        self.project_filter=QComboBox();self.project_filter.setAccessibleName(tr('Nach Projekt filtern'));self.project_filter.addItem(tr('Alle Projekte'),None);self.project_filter.addItem(tr('Ohne Projekt'),'')
        from tools_data import Library
        self.project_records={item['id']:item['title'] for item in Library('workbench').all() if item.get('kind')=='project'}
        for key,title in self.project_records.items():self.project_filter.addItem(title,key)
        self.sort=QComboBox();self.sort.setAccessibleName(tr('Sortieren'))
        for text,key in [('Zuletzt verwendet','recent'),('Name A–Z','name'),('Nach Art','kind')]:self.sort.addItem(tr(text),key)
        box.addWidget(row(self.search,self.project_filter,self.sort))
        caption=QHBoxLayout();self.collection_count=label('','codeCollectionCount');caption.addWidget(self.collection_count);caption.addStretch()
        refresh=button(tr('Aktualisieren'),self.refresh,'view-refresh');refresh.setObjectName('codeCollectionQuiet');caption.addWidget(refresh);box.addLayout(caption)
        content=QHBoxLayout();content.setSpacing(20);box.addLayout(content,1)
        self.list_frame=QFrame();self.list_frame.setObjectName('codeCollectionList');list_box=QVBoxLayout(self.list_frame);list_box.setContentsMargins(8,2,8,2)
        self.entries=QTreeWidget();self.entries.setObjectName('codeEntries');self.entries.setRootIsDecorated(False);self.entries.setAccessibleName(tr('Einträge der Sammlung'));self.entries.setMouseTracking(True);self.entries.setUniformRowHeights(True)
        self.entries.setHeaderLabels([tr(text) for text in ['Name','Projekt','Status','Favorit']]);self.entries.setHeaderHidden(True);self.entries.setColumnHidden(1,True)
        self.entries.header().setStretchLastSection(False);self.entries.header().setSectionResizeMode(0,QHeaderView.Stretch)
        self.entries.header().setSectionResizeMode(2,QHeaderView.Fixed);self.entries.setColumnWidth(2,106);self.entries.header().setSectionResizeMode(3,QHeaderView.Fixed);self.entries.setColumnWidth(3,34)
        self.entries.setItemDelegate(EntryDelegate(self.entries));list_box.addWidget(self.entries);content.addWidget(self.list_frame,1)
        self.collection_preview=QFrame();self.collection_preview.setObjectName('codeCollectionPreviewBody');self.collection_preview.setMinimumWidth(0)
        preview=QVBoxLayout(self.collection_preview);preview.setContentsMargins(20,20,20,20);preview.setSpacing(14)
        preview.addWidget(label(tr('AUF EINEN BLICK'),'codeCollectionCount'))
        self.preview_kind=label('','codePreviewKind');preview.addWidget(self.preview_kind)
        self.preview_title=label('','codePreviewTitle');preview.addWidget(self.preview_title)
        self.preview_description=label('','codeSubtitle');preview.addWidget(self.preview_description)
        self.preview_state=label('','codePreviewState');preview.addWidget(self.preview_state,0,Qt.AlignLeft)
        self.preview_project=label('','codeMuted');preview.addWidget(self.preview_project)
        self.preview_used=label('','codeCollectionCount');preview.addWidget(self.preview_used)
        self.preview_open=button(tr('Eintrag öffnen'),lambda:self.safe(self.open_selected),'go-next',primary=True);
        self.preview_favorite=button(tr('Als Favorit'),lambda:self.safe(self.toggle_selected_favorite));self.preview_favorite.setCheckable(True);self.preview_favorite.setObjectName('codeCollectionQuiet');
        preview.addStretch()
        self.preview_shell=QFrame();self.preview_shell.setObjectName('codeCollectionPreview');self.preview_shell.setFixedWidth(256)
        preview_box=QVBoxLayout(self.preview_shell);preview_box.setContentsMargins(0,0,0,0);preview_box.setSpacing(0)
        self.preview_scroll=QScrollArea();self.preview_scroll.setWidgetResizable(True);self.preview_scroll.setWidget(self.collection_preview);preview_box.addWidget(self.preview_scroll,1)
        controls=QVBoxLayout();controls.setContentsMargins(16,12,16,12);controls.setSpacing(4);controls.addWidget(self.preview_open);controls.addWidget(self.preview_favorite);preview_box.addLayout(controls);content.addWidget(self.preview_shell)
        self.empty_frame=QFrame();self.empty_frame.setObjectName('codeCollectionEmpty');empty_box=QVBoxLayout(self.empty_frame);empty_box.setContentsMargins(28,30,28,30);empty_box.setSpacing(14);empty_box.addStretch()
        mark=label('');mark.setPixmap(icon('view-grid').pixmap(36,36));mark.setAlignment(Qt.AlignCenter);empty_box.addWidget(mark)
        self.empty=label('','codePreviewTitle');self.empty.setAlignment(Qt.AlignCenter);empty_box.addWidget(self.empty)
        self.empty_description=label('','codeSubtitle');self.empty_description.setAlignment(Qt.AlignCenter);empty_box.addWidget(self.empty_description)
        self.empty_action=button(tr('Neu erstellen'),lambda:self.safe(self.empty_choice),primary=True);empty_box.addWidget(self.empty_action,0,Qt.AlignCenter);empty_box.addStretch();content.addWidget(self.empty_frame,1)
        self.explanation=QGroupBox();self.explanation.setFlat(True)
        from html import escape
        help_box=QVBoxLayout(self.explanation);self.help_content=QTextBrowser();self.help_content.setMaximumHeight(250)
        self.help_content.setHtml(''.join('<h3>'+escape(tr(item['title']))+'</h3><p>'+escape(tr(item['body']))+'</p><p><b>'+tr('Beispiel:')+'</b> '+escape(tr(item['example']))+'</p>' for item in HELP));help_box.addWidget(self.help_content)
        self.help_content.hide();self.explanation.hide();box.addWidget(self.explanation)
        utilities=QHBoxLayout();self.help_toggle=button(tr('Was kann ich mit Lumen machen?'),lambda:self.help_content.setVisible(self.help_toggle.isChecked()));self.help_toggle.setCheckable(True);self.help_toggle.setObjectName('codeCollectionQuiet');self.help_toggle.toggled.connect(self.explanation.setVisible);utilities.addWidget(self.help_toggle);utilities.addStretch()
        import_button=button(tr('Vorlage importieren'),lambda:self.safe(self.import_file),'document-import');import_button.setObjectName('codeCollectionQuiet');utilities.addWidget(import_button);box.addLayout(utilities)
        self.entries.setAccessibleDescription(tr('Pfeiltasten wählen einen Eintrag, Eingabe öffnet ihn. Strg+D ändert den Favoriten.'))
        favorite_shortcut=QShortcut(QKeySequence('Ctrl+D'),self.entries);favorite_shortcut.setContext(Qt.WidgetWithChildrenShortcut);favorite_shortcut.activated.connect(lambda:self.safe(self.toggle_selected_favorite))
        self.entries.itemActivated.connect(lambda _,column:self.safe(self.open_selected) if column!=3 else None)
        self.entries.currentItemChanged.connect(lambda *_:self.safe(self.update_collection_preview))
        self.entries.itemClicked.connect(lambda item,column:self.safe(self.toggle_selected_favorite) if column==3 else None)
        self.pages.addWidget(page)
        self.search.textChanged.connect(self.refresh);self.project_filter.currentIndexChanged.connect(self.refresh);self.sort.currentIndexChanged.connect(self.refresh)

    def project_title(self,item):
        return self.project_records.get(item['project_id'],tr('Ohne Projekt') if not item['project_id'] else tr('Projekt nicht mehr verfügbar'))

    def update_collection_preview(self):
        from time import strftime,localtime
        selected=self.entries.currentItem()
        self.preview_shell.setVisible(bool(selected) and self.width()>=1080)
        if selected is None:return
        item=self.collection.get(selected.data(0,Qt.UserRole))
        kinds={'app':'Kleine App','tool':'Werkzeug','automation':'Automation','code':'Code im Projekt'}
        self.preview_kind.setText(self.kind_title(item))
        self.preview_title.setText(item['title']);self.preview_description.setText(item['description'] or item['definition'].get('prompt','')[:280] or tr('Öffne den Eintrag, um ihn weiter einzurichten.'))
        self.preview_state.setText(self.entry_status(item));self.preview_project.setText(tr('Projekt: {0}',self.project_title(item)))
        self.preview_used.setText(tr('Zuletzt verwendet: {0}',strftime('%d.%m.%Y · %H:%M',localtime(item['last_used']))) if item['last_used'] else tr('Noch nicht verwendet'))
        self.preview_favorite.setText(tr('★ Favorit' if item['favorite'] else '☆ Als Favorit'));self.preview_favorite.setChecked(item['favorite'])

    def toggle_selected_favorite(self):
        selected=self.entries.currentItem()
        if selected is None:return
        item=self.collection.get(selected.data(0,Qt.UserRole));self.collection.update(item['id'],item['revision'],favorite=not item['favorite']);self.refresh()

    def empty_choice(self):
        if self.search.text().strip() or self.project_filter.currentData() is not None:
            self.search.clear();self.project_filter.setCurrentIndex(0)
        elif self.category_keys[max(0,self.categories.currentRow())] in ('favorites','attention','archive'):self.categories.setCurrentRow(0)
        else:self.create()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'preview_shell'):self.preview_shell.setVisible(self.entries.currentItem() is not None and self.width()>=1080)

    def build_detail(self):
        page=QWidget();box=QVBoxLayout(page);box.setContentsMargins(0,0,0,0);box.setSpacing(16)
        self.favorite=button(tr('Als Favorit'),lambda:self.safe(self.toggle_favorite));self.archive=button(tr('Archivieren'),lambda:self.safe(self.toggle_archive))
        actions=QHBoxLayout();back=button(tr('‹ Zur Sammlung'),self.back);back.setObjectName('codeLink');actions.addWidget(back);actions.addStretch();actions.addWidget(self.favorite);actions.addWidget(self.archive);self.edit_mode=button(tr('Bearbeiten'),lambda:self.safe(self.edit_entry),'document-edit');actions.addWidget(self.edit_mode);box.addLayout(actions)
        self.context=label('','codeSubtitle');box.addWidget(self.context)
        self.title=QLineEdit();self.title.setAccessibleName(tr('Name'));self.title.setMaxLength(160);self.title.setStyleSheet('font-size:25px;font-weight:500;');box.addWidget(self.title)
        content=QHBoxLayout();content.setSpacing(26);box.addLayout(content,1)
        editor=QWidget();fields=QVBoxLayout(editor);fields.setContentsMargins(0,0,4,0);fields.setSpacing(10)
        fields.addWidget(label(tr('Dein Auftrag')))
        self.prompt=QPlainTextEdit();self.prompt.setAccessibleName(tr('Auftrag'));self.prompt.setPlaceholderText(tr('Was soll Lumen für dich erledigen?'));self.prompt.setFixedHeight(110);fields.addWidget(self.prompt)
        fields.addWidget(label(tr('Eingabe für diesen Durchlauf')))
        self.input=QPlainTextEdit();self.input.setAccessibleName(tr('Eingabe für diesen Durchlauf'));self.input.setPlaceholderText(tr('Neue Eingabe für diesen Durchlauf'));self.input.setMinimumHeight(100);fields.addWidget(self.input)
        self.settings_toggle=button(tr('Beschreibung, Projekt und Dateien'),lambda:self.entry_settings.setVisible(self.settings_toggle.isChecked()));self.settings_toggle.setCheckable(True);self.settings_toggle.setObjectName('codeLink');fields.addWidget(self.settings_toggle)
        self.entry_settings=QWidget();settings=QVBoxLayout(self.entry_settings);settings.setContentsMargins(0,0,0,0);settings.setSpacing(8)
        settings.addWidget(label(tr('Beschreibung')));self.description=QPlainTextEdit();self.description.setAccessibleName(tr('Beschreibung'));self.description.setPlaceholderText(tr('Was erledigt dieser Eintrag?'));self.description.setFixedHeight(65);settings.addWidget(self.description)
        settings.addWidget(label(tr('Lumen-Projekt')));self.project=QComboBox();self.project.addItem(tr('Ohne Projekt'),'')
        for key,title in self.project_records.items():self.project.addItem(title,key)
        settings.addWidget(self.project)
        self.directory=QLineEdit();self.directory.setAccessibleName(tr('Ausgewählter Ordner'));self.directory.setPlaceholderText(tr('Optional: ausdrücklich ausgewählter Projekt- oder Eingabeordner'));settings.addWidget(row(self.directory,button(tr('Ordner wählen'),self.choose_directory)))
        self.html=QPlainTextEdit();self.html.setAccessibleName(tr('App-Inhalt (HTML)'));self.html.setPlaceholderText(tr('HTML einer eigenen App oder Inhalt aus einem abgeschlossenen App-Auftrag'));self.html.setMinimumHeight(180);settings.addWidget(self.html);fields.addWidget(self.entry_settings);self.entry_settings.hide();fields.addStretch()
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(editor);content.addWidget(scroll,1)
        aside=QWidget();aside.setFixedWidth(280);run_box=QVBoxLayout(aside);run_box.setContentsMargins(0,0,0,0);run_box.setSpacing(12)
        run_box.addWidget(label(tr('Mit Lumen verwenden'),'codeCardTitle'))
        self.run=button(tr('Mit Lumen ausführen'),lambda:self.safe(self.execute),primary=True);run_box.addWidget(self.run)
        self.preview=button(tr('App öffnen'),lambda:self.safe(self.open_app),'media-playback-start');self.adopt=button(tr('App aus Auftrag übernehmen'),lambda:self.safe(self.adopt_app));run_box.addWidget(self.preview);run_box.addWidget(self.adopt)
        self.schedule=button(tr('Automation einrichten'),lambda:self.safe(self.configure_flow));self.toggle=button(tr('Aktivieren'),lambda:self.safe(self.toggle_flow));run_box.addWidget(self.schedule);run_box.addWidget(self.toggle)
        self.routine_from_tool=button(tr('Als Routine einrichten'),lambda:self.safe(self.new_routine),'view-calendar');run_box.addWidget(self.routine_from_tool)
        run_box.addWidget(label(tr('Tatsächlicher Auftragsstatus und Ergebnis'),'codeMuted'))
        self.result=QPlainTextEdit();self.result.setReadOnly(True);self.result.setAccessibleName(tr('Tatsächlicher Auftragsstatus und Ergebnis'));self.result.setMaximumHeight(220);run_box.addWidget(self.result)
        run_box.addWidget(button(tr('Letzten Auftrag öffnen'),lambda:self.safe(self.open_task)));run_box.addStretch();content.addWidget(aside)
        actions=QHBoxLayout();actions.addWidget(button(tr('Als Vorlage weitergeben'),lambda:self.safe(self.export_file)));actions.addStretch();actions.addWidget(button(tr('Speichern'),lambda:self.safe(self.save)));box.addLayout(actions)
        for control in (self.preview,self.adopt,self.schedule,self.toggle):control.hide()
        self.pages.addWidget(page)
        for control in (self.title,self.description,self.prompt,self.html,self.directory):control.textChanged.connect(self.edited)
        self.project.currentIndexChanged.connect(self.edited)

    def edited(self,*_):
        if not self.loading:self.dirty=True;self.status.setText(tr('Ungespeicherte Änderungen.'))

    def allow_leave(self):
        if not self.dirty:return True
        choice=QMessageBox.question(self,tr('Lumen Code & Automation'),tr('Änderungen vor dem Verlassen speichern?'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        if choice==QMessageBox.Cancel:return False
        if choice==QMessageBox.Save:
            try:self.save()
            except (ValueError,OSError,RuntimeError,sqlite3.Error,SubprocessError) as error:self.status.setText(tr(str(error)));return False
        self.dirty=False;return True

    def change_category(self,index):
        if not self.allow_leave():
            self.categories.blockSignals(True);self.categories.setCurrentRow(self.category_index);self.categories.blockSignals(False);return
        self.category_index=index
        self.footer.setText(tr('Meine Sammlung')+' / '+self.categories.item(index).text())
        self.pages.setCurrentIndex(0);self.refresh()

    def kind_title(self,item):
        if item['kind']=='automation' and item['definition'].get('flow'):
            from code_flow import parse
            if parse(item['definition']['flow']).get('version') not in (2,3):return tr('Routine')
        return tr({'app':'Kleine App','tool':'Werkzeug','automation':'Automation','code':'Code im Projekt'}[item['kind']])

    def entry_status(self,item):
        if item['archived']:return tr('Archiviert')
        if item['last_task']:
            try:
                status=self.store.task(item['last_task'])['status']
                if status=='completed' and self.store.rows("SELECT 1 FROM events WHERE task=? AND kind='code-flow-note'",(item['last_task'],)):return tr('Braucht dich')
                if item['kind']!='automation' or status not in ('completed','cancelled'):return STATES.get(status,status)
            except ValueError:return tr('Auftrag nicht mehr verfügbar')
        if item['kind']=='automation':
            from code_flow import parse
            if item['definition'].get('flow') and parse(item['definition']['flow']).get('version') in (2,3):
                exists=self.store.rows("SELECT 1 FROM sqlite_master WHERE name='code_block_runs'")
                rows=self.store.rows('SELECT status FROM code_block_runs WHERE entry=? ORDER BY updated DESC LIMIT 1',(item['id'],)) if exists else []
                state=rows[0]['status'] if rows else 'draft'
                return tr({'draft':'Entwurf','running':'Läuft','waiting':'Braucht dich','error':'Fehlgeschlagen','completed':'Erledigt','paused':'Pausiert','cancelled':'Abgebrochen'}.get(state,state))
            flow=next((flow for flow in self.store.workflows() if flow['id']==item['definition'].get('workflow_id')),None)
            return tr('Aktiv' if flow and flow['enabled'] else 'Pausiert')
        return tr('Bereit' if item['definition'].get('html' if item['kind']=='app' else 'prompt') else 'Entwurf')

    def refresh(self,*_):
        category=self.category_keys[max(0,self.categories.currentRow())]
        records=self.collection.items(query=self.search.text(),kind=category if category in KINDS else '',project_id=self.project_filter.currentData(),favorite=category=='favorites',archived=category=='archive',sort=self.sort.currentData())
        if category=='attention':records=[item for item in records if self.entry_status(item) in [STATES[key] for key in ('failed','needs_input','interrupted')]]
        heading={'all':'Meine Sammlung','favorites':'Deine Favoriten','attention':'Braucht dich','archive':'Archiv',**TITLES}
        descriptions={'all':'Deine Apps, Werkzeuge und Abläufe – bereit für den nächsten Einsatz.','app':'Kleine Oberflächen für Dinge, die du im Alltag erledigst.','tool':'Deine bewährten Aufträge – bei jedem Mal mit neuen Eingaben.','automation':'Abläufe, die für dich prüfen, vorbereiten und Bescheid geben.','code':'Deine Softwareprojekte mit Gespräch, Dateien und Änderungen.','favorites':'Die Helfer, die du besonders häufig brauchst.','attention':'Offene Rückfragen und Aufträge, die deine Aufmerksamkeit brauchen.','archive':'Aufbewahrt, bis du sie wieder brauchst.'}
        self.collection_intro.setText(tr(descriptions[category]))
        self.collection_heading.setText(tr(heading[category]));self.collection_count.setText(tr('1 Eintrag') if len(records)==1 else tr('{0} Einträge',len(records)))
        selected=self.entries.currentItem();identity=selected.data(0,Qt.UserRole) if selected else None
        self.entries.blockSignals(True);self.entries.clear();chosen=None
        kinds={'app':'Kleine App','tool':'Werkzeug','automation':'Automation','code':'Code im Projekt'}
        for record in records:
            description=record['description'] or record['definition'].get('prompt','').split('\n')[0][:180] or tr('Noch keine Beschreibung')
            context=self.kind_title(record)+' · '+self.project_title(record)
            item=QTreeWidgetItem([record['title']+'\n'+description+'\n'+context,self.project_title(record),self.entry_status(record),'★' if record['favorite'] else '☆'])
            item.setData(0,Qt.UserRole,record['id']);item.setData(0,Qt.UserRole+1,dict(title=record['title'],description=description,context=context,kind=record['kind'],favorite=record['favorite']))
            for column in (0,2,3):item.setToolTip(column,item.text(column))
            self.entries.addTopLevelItem(item)
            if record['id']==identity:chosen=item
        self.entries.setCurrentItem(chosen or self.entries.topLevelItem(0));self.entries.blockSignals(False)
        self.list_frame.setVisible(bool(records));self.empty_frame.setVisible(not records)
        filtered=bool(self.search.text().strip() or self.project_filter.currentData() is not None)
        special=category in ('favorites','attention','archive')
        self.empty.setText(tr('Keine passenden Einträge') if filtered else tr({'favorites':'Deine Favoriten fehlen noch','attention':'Alles im Blick','archive':'Das Archiv ist leer'}.get(category,'Deine Sammlung beginnt mit einer Idee.')))
        self.empty_description.setText(tr('Versuche einen anderen Suchbegriff oder passe die Auswahl an.') if filtered else tr('Markiere häufig verwendete Helfer mit einem Stern.') if category=='favorites' else tr('Hier erscheinen Einträge, die deine Aufmerksamkeit brauchen.') if category=='attention' else tr('Archivierte Helfer bleiben hier erhalten.') if category=='archive' else tr('Eine kleine App, ein wiederverwendbares Werkzeug oder dein erster Ablauf.'))
        self.empty_action.setText(tr('Filter zurücksetzen') if filtered else tr('Alle Einträge anzeigen') if special else tr('Neu erstellen'))
        self.update_collection_preview()

    def create(self):
        if not self.allow_leave():return
        from code_creation import CreationDialog
        dialog=CreationDialog(self,self.project_records,self.collection.items(kind='tool'))
        if not dialog.exec():return
        value=dialog.value
        self.open_entry(self.collection.create(value['kind'],value['title'],value['description'],
                                               value['definition'],value['project_id'])['id'])

    def open_selected(self):
        item=self.entries.currentItem()
        if item is None:raise ValueError(tr('Bitte zuerst einen Eintrag auswählen.'))
        self.open_entry(item.data(0,Qt.UserRole))

    def open_entry(self,identity,blocks=True,apps=True):
        if not self.allow_leave():return
        item=self.collection.get(identity)
        if apps and item['kind']=='app' and not item['archived']:
            from code_app_window import AppWindow
            result=AppWindow(self.collection,identity,self).exec()
            if result==2:self.open_entry(identity,apps=False)
            self.refresh();return
        if item['kind']=='code' and not item['archived']:
            self.open_coding(identity);return
        if item['kind']=='automation' and item['definition'].get('flow'):
            from code_flow import parse
            if blocks and not item['archived'] and parse(item['definition']['flow']).get('version') in (2,3):
                from code_blocks_window import BlockWindow
                BlockWindow(self.collection,identity,self).exec();self.refresh();return
        self.current=item;self.loading=True;self.footer.setText(tr('Meine Sammlung')+' / '+item['title'])
        try:
            self.title.setText(item['title']);self.description.setPlainText(item['description']);self.prompt.setPlainText(item['definition'].get('prompt',''));self.html.setPlainText(item['definition'].get('html',''));self.directory.setText(item['definition'].get('directory',''))
            if item['project_id'] and self.project.findData(item['project_id'])<0:self.project.addItem(tr('Projekt nicht mehr verfügbar'),item['project_id'])
            self.project.setCurrentIndex(max(0,self.project.findData(item['project_id'])));self.input.clear();self.html.setVisible(item['kind']=='app')
            guide=next(row for row in HELP if row['key']==item['kind']);self.context.setText(tr(guide['title'])+' · '+tr(guide['body']))
            self.favorite.setText(tr('★ Favorit' if item['favorite'] else '☆ Als Favorit'));self.archive.setText(tr('Wiederherstellen' if item['archived'] else 'Archivieren'))
            self.preview.setVisible(item['kind']=='app');self.adopt.setVisible(item['kind']=='app');self.schedule.setVisible(item['kind']=='automation');self.toggle.setVisible(item['kind']=='automation');self.run.setEnabled(not item['archived']);self.preview.setEnabled(not item['archived']);self.toggle.setEnabled(not item['archived'])
            from code_flow import parse
            block_flow=item['kind']=='automation' and item['definition'].get('flow') and parse(item['definition']['flow']).get('version') in (2,3)
            self.schedule.setText(tr('Bausteine öffnen' if block_flow else 'Automation einrichten'));self.toggle.setVisible(item['kind']=='automation' and not block_flow)
            self.prompt.setReadOnly(bool(block_flow));self.input.setEnabled(not block_flow)
            self.schedule.setEnabled(not item['archived'])
            self.edit_mode.setVisible(item['kind']=='tool' or (item['kind']=='automation' and bool(item['definition'].get('flow')) and not block_flow));self.edit_mode.setEnabled(not item['archived'])
            self.routine_from_tool.setVisible(item['kind']=='tool');self.routine_from_tool.setEnabled(not item['archived'] and bool(item['definition'].get('prompt')))
            if item['kind']=='automation' and item['definition'].get('flow') and not block_flow:self.schedule.setText(tr('Zeitplan bearbeiten'))
            if item['kind']=='tool' and item['definition'].get('tool_spec'):self.prompt.setReadOnly(True)
            self.pages.setCurrentIndex(1);self.dirty=False;self.status.clear();self.refresh_result()
        finally:self.loading=False

    def open_coding(self,identity):
        from code_session import CodingWindow
        from lumen_activation import present
        window=self.coding_windows.get(identity)
        if window is None:
            window=CodingWindow(self.collection,identity,self);self.coding_windows[identity]=window
            window.destroyed.connect(lambda *_:self.coding_windows.pop(identity,None))
        self.pages.setCurrentIndex(0);self.refresh();present(window)

    def edit_entry(self,schedule=False):
        if not self.allow_leave():return
        from code_edit_window import EditDialog
        identity=self.current['id'];user_input=self.input.toPlainText()
        dialog=EditDialog(self.collection,self.collection.get(identity),self,schedule=schedule)
        dialog.exec();self.open_entry(identity,blocks=False);self.input.setPlainText(user_input);self.refresh()

    def new_routine(self):
        if not self.allow_leave():return
        from code_edit_window import EditDialog
        dialog=EditDialog(self.collection,parent=self,tool=self.collection.get(self.current['id']))
        dialog.exec()
        if dialog.item:self.open_entry(dialog.item['id'],blocks=False)
        self.refresh()

    def save(self):
        value=dict(self.current['definition']);value.update(prompt=self.prompt.toPlainText(),directory=self.directory.text().strip())
        if self.current['kind']=='app':value['html']=self.html.toPlainText()
        item=self.collection.update(self.current['id'],self.current['revision'],title=self.title.text(),description=self.description.toPlainText(),definition=value,project_id=self.project.currentData())
        self.current=item;self.dirty=False;self.status.setText(tr('Gespeichert.'));return item

    def back(self):
        if self.allow_leave():self.pages.setCurrentIndex(0);self.refresh()

    def toggle_favorite(self):
        if self.dirty:self.save()
        item=self.collection.update(self.current['id'],self.current['revision'],favorite=not self.current['favorite']);self.open_entry(item['id'],blocks=False,apps=False)

    def toggle_archive(self):
        if self.dirty:self.save()
        self.collection.update(self.current['id'],self.current['revision'],archived=not self.current['archived']);self.dirty=False;self.back()

    def choose_directory(self):
        path=QFileDialog.getExistingDirectory(self,tr('Lumen · Ordner auswählen'))
        if path:self.directory.setText(path)

    def execute(self):
        if self.open_blocks():return
        from code_library_execution import prepare_run
        from lumen_detail_routes import task_action,open_tasks
        self.save();task=prepare_run(self.collection,self.current['id'],self.input.toPlainText());self.current=self.collection.get(self.current['id']);self.refresh_result();open_tasks(task);task_action(task,'run')

    def open_task(self):
        from lumen_detail_routes import open_tasks
        item=self.collection.get(self.current['id'])
        if not item['last_task']:raise ValueError(tr('Noch kein Auftrag vorhanden.'))
        open_tasks(item['last_task'])

    def refresh_result(self):
        if self.current is None or self.pages.currentIndex()!=1:return
        item=self.collection.get(self.current['id'])
        if not item['last_task']:self.result.setPlainText(tr('Noch kein Auftrag ausgeführt.'));return
        try:task=self.store.task(item['last_task'])
        except ValueError:self.result.setPlainText(tr('Auftrag nicht mehr verfügbar'));return
        pending=tr('Notizablage ausstehend. Prüfe den freigegebenen Notizordner.') if self.store.rows("SELECT 1 FROM events WHERE task=? AND kind='code-flow-note'",(task['id'],)) else ''
        self.result.setPlainText(tr('Status: {0}',STATES.get(task['status'],task['status']))+'\n'+pending+'\n'+(task['error'] or task['result']))

    def open_app(self):
        from code_library_execution import preview_file
        self.save();path=preview_file(self.collection,self.current['id'])
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):raise ValueError(tr('App-Vorschau konnte nicht geöffnet werden.'))

    def adopt_app(self):
        from code_library_execution import generated_html
        source=generated_html(self.collection,self.current['id']);self.html.setPlainText(source);self.save()

    def open_blocks(self):
        from code_flow import parse
        if self.current['kind']!='automation' or not self.current['definition'].get('flow') or parse(self.current['definition']['flow']).get('version') not in (2,3):return False
        if self.dirty:self.save()
        from code_blocks_window import BlockWindow
        BlockWindow(self.collection,self.current['id'],self).exec();self.current=self.collection.get(self.current['id']);return True

    def configure_flow(self):
        if self.open_blocks():return
        if self.current['definition'].get('flow'):
            self.edit_entry(schedule=True);return
        from lumen_workspace import PlanDialog
        from code_library_execution import directory
        self.save()
        if self.current['archived']:raise ValueError(tr('Bitte den Eintrag zuerst wiederherstellen.'))
        value=self.current['definition'];flow=next((row for row in self.store.workflows() if row['id']==value.get('workflow_id')),None)
        dialog=PlanDialog(self,flow or {'title':self.current['title'],'prompt':value.get('prompt',''),'roots':[str(directory(self.collection,self.current))]},workflow=True)
        if not dialog.exec():return
        identity=self.store.save_workflow(**dialog.value,workflow=flow['id'] if flow else None);value={**value,'workflow_id':identity};self.current=self.collection.update(self.current['id'],self.current['revision'],definition=value)
        if dialog.value['enabled']:self.activate_flow(identity)
        self.status.setText(tr('Automation gespeichert.'))

    def toggle_flow(self):
        if self.current['archived']:raise ValueError(tr('Bitte den Eintrag zuerst wiederherstellen.'))
        if self.current['definition'].get('flow'):
            if not self.allow_leave():return
            from code_edit_window import EditDialog
            dialog=EditDialog(self.collection,self.collection.get(self.current['id']),self)
            dialog.activate();dialog.done(0);self.open_entry(self.current['id'],blocks=False);return
        flow=next((row for row in self.store.workflows() if row['id']==self.current['definition'].get('workflow_id')),None)
        if flow is None:raise ValueError(tr('Bitte zuerst die Automation einrichten.'))
        self.store.set_workflow_enabled(flow['id'],not flow['enabled'])
        if not flow['enabled']:self.activate_flow(flow['id'])
        self.status.setText(tr('Pausiert' if flow['enabled'] else 'Aktiv'))

    def activate_flow(self, identity):
        from lumen_actions import command
        try:command(['systemctl','--user','enable','--now','lumen-jobs.timer'])
        except (ValueError,OSError,RuntimeError,SubprocessError):
            self.store.set_workflow_enabled(identity,False)
            raise

    def export_file(self):
        if self.dirty:self.save()
        value=export_template(self.current)
        preview=json.dumps(value,ensure_ascii=False,indent=2)
        review=QMessageBox(self);review.setWindowTitle(tr('Lumen · Vorlage weitergeben'));review.setText(tr('Die Vorlage enthält Auftrag und App-Inhalt. Prüfe diese Inhalte vor dem Weitergeben. Persönliche Quellen, Ordnerfreigaben und Zeitpläne werden nicht übernommen.'));review.setDetailedText(preview);review.setStandardButtons(QMessageBox.Save|QMessageBox.Cancel)
        if review.exec()!=QMessageBox.Save:return
        target,_=QFileDialog.getSaveFileName(self,tr('Lumen · Vorlage speichern'),'werkzeug.lumen.json','Lumen (*.lumen.json)')
        if target:Path(target).write_text(preview,encoding='utf-8')

    def import_file(self):
        if not self.allow_leave():return
        source,_=QFileDialog.getOpenFileName(self,tr('Lumen · Vorlage importieren'),'','Lumen (*.json)')
        if not source:return
        path=Path(source)
        if path.stat().st_size>2000000:raise ValueError(tr('Vorlage ist zu groß.'))
        from code_library_contract import import_template
        value=import_template(path.read_text(encoding='utf-8'))
        if QMessageBox.question(self,tr('Lumen · Vorlage importieren'),tr('„{0}“ als eigenen Entwurf übernehmen? Quellen und Freigaben musst du selbst auswählen.',value['title']))!=QMessageBox.Yes:return
        self.open_entry(self.collection.import_entry(value)['id'])

    def closeEvent(self,event):
        if not self.allow_leave():event.ignore();return
        if any(not window.close() for window in list(self.coding_windows.values())):event.ignore();return
        self.timer.stop()
        super().closeEvent(event)

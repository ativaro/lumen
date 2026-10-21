"""The direct notebook layout; storage and actions live in tools_wissen."""
from lumen_i18n import tr
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPlainTextEdit,
    QTabWidget,QStackedWidget,QListWidget,QCheckBox,QMenu,QScrollArea,QToolBar,QComboBox,QWidgetAction,QProxyStyle,QStyle,QToolButton,QGridLayout)
from tools_ui import button,label,row
from assistant import Transcript
from wissen_views import NotePreview,KnowledgeMap
from notes_editor import NotesEditor


class ToolbarStyle(QProxyStyle):
    def pixelMetric(self,metric,option=None,widget=None):
        if metric==QStyle.PM_ToolBarExtensionExtent:return 32
        return super().pixelMetric(metric,option,widget)


def build(w):
    old=w.takeCentralWidget();shell=QWidget();shell.setObjectName('wissenShell');w.setCentralWidget(shell)
    from notes_design import apply, icon as glyph, NoteListDelegate, reflow
    apply(w,shell)
    shell.setStyleSheet(Path(__file__).with_name('wissen.qss').read_text())
    from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
    outer=QVBoxLayout(shell);outer.setContentsMargins(PAGE_MARGIN,20,PAGE_MARGIN,20);outer.setSpacing(PAGE_SPACING)
    w.app_header=AppHeader(tr('Lumen Notes'),tr('Gedanken festhalten. Quellen verbinden. Zusammenhänge entdecken.'))
    w.brand=w.app_header.title;w.status.setMaximumWidth(600);w.status.setWordWrap(False)
    for control in (w.progress,w.cancel_button):
        policy=control.sizePolicy();policy.setRetainSizeWhenHidden(True);control.setSizePolicy(policy)
        w.app_header.actions.addWidget(control)
    outer.addWidget(w.app_header)
    w.notes_layout=QGridLayout();w.notes_layout.setContentsMargins(0,0,0,0);w.notes_layout.setSpacing(0);outer.addLayout(w.notes_layout,1)
    w.split.setHandleWidth(1);w.split.setChildrenCollapsible(False)
    w.navigation=QWidget();w.navigation.setObjectName('wissenNavigation');w.navigation.setMinimumWidth(0)
    nav=QVBoxLayout(w.navigation);nav.setContentsMargins(0,4,14,16);nav.setSpacing(8)
    w.area_buttons={}
    for title,area in [(tr('Meine Notizen'),'user'),(tr('Gedächtnis'),'lumen')]:
        b=button(title,lambda checked=False,a=area:w.safe(w.switch_area,a),'');b.setCheckable(True);b.setChecked(area=='user');b.setObjectName('wissenArea');b.setAccessibleName(title)
        w.area_buttons[area]=b;b.hide()
    w.area_caption=label(tr('MEINE NOTIZEN'),'wissenCaption');nav.addWidget(w.area_caption)
    w.collection_label=label(tr('SAMMLUNGEN'),'wissenCaption');nav.addWidget(w.collection_label)
    w.collection_button=button(tr('Neue Sammlung'),lambda:w.safe(w.create_collection));w.collection_button.setIcon(glyph('plus'));w.collection_button.setAccessibleName(tr('Neue Sammlung'));nav.addWidget(w.collection_button)
    w.collections=QListWidget();w.collections.setObjectName('wissenCollections');w.collections.setAccessibleName(tr('Sammlungen'));w.collections.currentItemChanged.connect(w.select_collection);nav.addWidget(w.collections,1)
    w.collections.setIconSize(QSize(16,16))
    w.rename_collection_button=button(tr('Sammlung umbenennen / verschieben'),lambda:w.safe(w.rename_collection),'edit-rename');nav.addWidget(w.rename_collection_button)
    from server_memory_view import show_server_memory
    w.server_memory_button=button(tr('Server-Gedächtnis'),lambda:w.safe(show_server_memory,w),'network-server');nav.addWidget(w.server_memory_button)
    w.questions_button=button(tr('Fragen'),lambda:w.tabs.setCurrentIndex(1),'edit-find');nav.addWidget(w.questions_button)
    w.map_button=button(tr('Notizkarte'),lambda:w.tabs.setCurrentIndex(2),'insert-link');nav.addWidget(w.map_button)
    settings=button(tr('Einstellungen'),lambda:None,'configure');settings_menu=QMenu(settings)
    w.notebook_menu=settings_menu
    from notes_capture import open_daily,choose_template
    if not w.memory_only:
        settings_menu.addAction(tr('Tagesnotiz öffnen'),lambda:w.safe(open_daily,w))
        settings_menu.addAction(tr('Notiz aus Vorlage …'),lambda:w.safe(choose_template,w))
        settings_menu.addAction(tr('Gedächtnis'),lambda:w.safe(w.switch_area,'lumen'))
        settings_menu.addAction(tr('Meine Notizen'),lambda:w.safe(w.switch_area,'user'))
    from notes_move import review as review_move,recover as recover_move
    if not w.memory_only:
        settings_menu.addAction(tr('Unterbrochenes Verschieben fortsetzen'),lambda:w.safe(recover_move,w))
        settings_menu.addAction(tr('Letztes Verschieben zurücknehmen'),lambda:w.safe(recover_move,w,True))
        settings_menu.addAction(tr('Neue Sammlung'),lambda:w.safe(w.create_collection))
        settings_menu.addAction(tr('Sammlung umbenennen / verschieben'),lambda:w.safe(w.rename_collection))
        settings_menu.addSeparator()
        settings_menu.addAction(tr('Fragen'),lambda:w.tabs.setCurrentIndex(1))
        settings_menu.addAction(tr('Notizkarte'),lambda:w.tabs.setCurrentIndex(2))
    settings_menu.addAction(tr('Erinnerung öffnen … (Strg+K)') if w.memory_only else tr('Notiz öffnen … (Strg+K)'),lambda:w.safe(w.quick_open))
    from note_tag_actions import review as review_tags
    tags_action=settings_menu.addAction(tr('Tags umbenennen / entfernen …'),lambda:w.safe(review_tags,w))
    settings_menu.aboutToShow.connect(lambda:tags_action.setVisible(w.area=='user'))
    settings_menu.addAction(tr('Lumen einrichten …'),w.setup)
    w.folder_action=settings_menu.addAction(tr('Notizordner wählen …'),lambda:w.safe(w.choose_folder))
    settings_menu.addAction(tr('Aktuellen Ordner öffnen'),lambda:w.safe(w.open_folder))
    w.share_folder_action=settings_menu.addAction(tr('Ordnerfreigaben …'),lambda:w.safe(w.share_folder))
    settings_menu.addAction(tr('Frühere Fassungen …'),lambda:w.safe(w.history))
    settings_menu.addSeparator()
    w.backup_info=settings_menu.addAction(tr('Noch kein Sicherungsplan für dieses Notizbuch.'));w.backup_info.setEnabled(False)
    w.backup_action=settings_menu.addAction(tr('Notizbuch sichern …'),lambda:w.safe(w.backup_notebook))
    settings_menu.aboutToShow.connect(lambda:w.safe(w.backup_status))
    settings_menu.addSeparator()
    settings.setMenu(settings_menu)
    for control in (w.rename_collection_button,w.questions_button,w.map_button): control.hide()
    w.collections.setMinimumHeight(80)
    w.sidebar.setObjectName('wissenList');w.sidebar.setMinimumWidth(260);w.sidebar.setMaximumWidth(320)
    side=w.sidebar.layout()
    while side.count():side.takeAt(0)
    side.setContentsMargins(12,20,12,12);side.setSpacing(10)
    w.search.setPlaceholderText(tr('Text oder #tags suchen …'));w.search.setAccessibleName(tr('Notizen finden'));side.addWidget(w.search)
    hint=label(tr('Mehrere #tags müssen alle passen. Untertags werden mitgefunden.'),'muted');side.addWidget(hint)
    w.add_button.setText(tr('Neu'));w.add_button.setIcon(glyph('plus'));w.add_button.setObjectName('toolButton');w.add_button.setAccessibleName(tr('Neue Notiz'))
    from notes_views import populate as populate_views
    w.views_button=button(tr('Ansichten'),lambda:None,'view-list-details');view_menu=QMenu(w.views_button);w.views_button.setMenu(view_menu);view_menu.aboutToShow.connect(lambda:populate_views(w,view_menu));w.views_button.hide();settings_menu.addMenu(view_menu).setText(tr('Ansichten'))
    w.search.setToolTip(tr('Text und Tags kombinieren, z. B. #projekt [status=offen] oder [due=2026-10-14]'))
    w.list_title=label(tr('Zuletzt bearbeitet'),'muted');list_heading=row(w.list_title,w.add_button);list_heading.layout().setStretch(0,1);side.addWidget(list_heading)
    w.daily_button=button(tr('Tagesnotiz'),lambda:w.safe(open_daily,w));w.daily_button.setToolTip(tr('Tagesnotiz öffnen'))
    w.template_button=button(tr('Aus Vorlage'),lambda:w.safe(choose_template,w));side.addWidget(row(w.daily_button,w.template_button));side.addWidget(w.entries,1);side.addWidget(settings)
    w.entries.setItemDelegate(NoteListDelegate(w.entries));w.entries.setMouseTracking(True)
    w.entries.setWordWrap(True);w.entries.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.archived.hide();w.archive_button.hide()
    w.content.setContentsMargins(0,0,0,0);w.content.setSpacing(0);w.body.setObjectName('wissenPaper')
    w.tabs=QTabWidget();w.tabs.setObjectName('wissenPages');w.tabs.tabBar().hide();w.content.addWidget(w.tabs,1)
    writing=QWidget();writing.setObjectName('wissenWriting');wl=QVBoxLayout(writing);wl.setContentsMargins(28,22,28,18);wl.setSpacing(16)
    w.location=label(tr('Meine Notizen'),'muted');w.location.setAccessibleName(tr('Notizbereich und Sammlung'))
    w.share_note=button(tr('Nur für mich'),lambda:None,'object-locked');w.share_note.setCheckable(True);w.share_note.setEnabled(False)
    w.share_note.setToolTip(tr('Freigeben erlaubt passende Auszüge als Kontext für zukünftige Lumen-Anfragen an deinen eingerichteten Anbieter.'))
    w.share_note.toggled.connect(lambda allow:w.safe(w.set_note_shared,allow))
    w.more_button=button(tr('Mehr'),lambda:None);w.more_button.setIcon(glyph('ellipsis'))
    menu=QMenu(w.more_button)
    for title,callback in [(tr('Notiz verknüpfen …'),w.insert_link),(tr('Bild einfügen …'),w.insert_image),(tr('Tag einfügen …'),w.insert_tag)]:menu.addAction(title,lambda checked=False,cb=callback:w.safe(cb))
    from notes_properties_ui import show as show_properties
    properties_action=menu.addAction(tr('Eigenschaften bearbeiten …'),lambda:w.safe(show_properties,w))
    menu.aboutToShow.connect(lambda:properties_action.setEnabled(w.area=='user' and bool(w.doc)))
    move_action=menu.addAction(tr('Datei umbenennen / verschieben …'),lambda:w.safe(review_move,w))
    menu.aboutToShow.connect(lambda:move_action.setEnabled(w.area=='user' and bool(w.doc)))
    menu.addSeparator();w.preview_action=menu.addAction(tr('Lesevorschau'),w.toggle_view)
    menu.addAction(tr('Fokusmodus'),w.focus_mode);menu.addAction(tr('Jetzt speichern'),lambda:w.safe(w.save_note));menu.addAction(tr('Frühere Fassungen …'),lambda:w.safe(w.history))
    from memory_projects_ui import configure as configure_projects
    project_copy=menu.addAction(tr('Als Projektwissen kopieren …'),lambda:w.safe(configure_projects,w,True))
    menu.aboutToShow.connect(lambda:project_copy.setVisible(w.area=='lumen' and bool(w.doc)))
    menu.addSeparator();w.remove_action=menu.addAction(tr('Notiz entfernen …'),lambda:w.safe(w.archive));w.remove_action.setEnabled(False)
    w.more_button.setMenu(menu)
    top=row(w.location,w.share_note,w.more_button);top.layout().setStretch(0,1);wl.addWidget(top)
    w.title=QLineEdit();w.title.setObjectName('wissenTitle');w.title.setPlaceholderText(tr('Deine erste Notiz'));w.title.setAccessibleName(tr('Notiztitel'));w.title.setMaxLength(300);w.title.setEnabled(False);w.title.textEdited.connect(w.edited);wl.addWidget(w.title)
    w.banner=label('','muted');w.banner.hide();wl.addWidget(w.banner)
    w.recovery=row(button(tr('Externe Fassung laden'),lambda:w.safe(w.reload_external),'view-refresh'),button(tr('Entwurf als Kopie'),lambda:w.safe(w.save_copy),'edit-copy'));w.recovery.hide();wl.addWidget(w.recovery)
    w.timestamp=label('','muted');w.timestamp.setAccessibleDescription(tr('Zeitstempel der Notiz'));w.timestamp.setTextFormat(Qt.PlainText);w.timestamp.hide();wl.addWidget(w.timestamp)
    w.views=QStackedWidget();wl.addWidget(w.views,1)
    w.editor=NotesEditor();w.editor.setObjectName('wissenEditor');w.editor.setAccessibleName(tr('Notiztext'));w.editor.setPlaceholderText(tr('Mit „Neu“ einen Gedanken festhalten.\n\nDeine Notizen bleiben zunächst privat.'));w.editor.setTabStopDistance(32);w.editor.textChanged.connect(w.edited)
    from notes_live_preview import LivePreview
    w.live_preview=LivePreview(w)
    from notes_rich_editor import RichEditor
    w.rich_editor=RichEditor(w);w.authoring=QStackedWidget();w.authoring.addWidget(w.rich_editor);w.authoring.addWidget(w.live_preview);w.views.addWidget(w.authoring)
    def editing():return w.editor if w.source_mode.isChecked() else w.rich_editor
    w.editor.completion.notes=lambda:list((w.notes | ({w.doc['path']:dict(w.doc,text=w.document_text())} if w.doc else {})).values())
    w.editor.completion.origin=lambda:w.doc['path'] if w.doc else ''
    w.editor.linkRequested.connect(lambda target:w.safe(w.follow_editor_link,target))
    w.editor_tools=QToolBar(tr('Text formatieren'));w.editor_tools.setObjectName('notesToolbar')
    w.editor_tools.setIconSize(QSize(18,18))
    toolbar_style=ToolbarStyle();toolbar_style.setParent(w.editor_tools);w.editor_tools.setStyle(toolbar_style)
    overflow=w.editor_tools.findChild(QToolButton,'qt_toolbar_ext_button');overflow.setToolButtonStyle(Qt.ToolButtonTextOnly);overflow.setText('⋮');overflow.setToolTip(tr('Weitere Werkzeuge'));overflow.setAccessibleName(tr('Weitere Werkzeuge'))
    w.editor_tools.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);w.editor_tools.setMovable(False)
    w.paragraph=QComboBox();w.paragraph.setObjectName('notesParagraph');w.paragraph.setAccessibleName(tr('Absatzformat'));w.paragraph.setMinimumWidth(150)
    for title,prefix in [(tr('Normaler Text'),'')]+[(tr('Überschrift')+' '+str(n),'#'*n+' ') for n in range(1,7)]+[(tr('Zitat'),'> ')]: w.paragraph.addItem(title,prefix)
    w.paragraph.activated.connect(lambda index:editing().paragraph_style(w.paragraph.itemData(index)))
    def paragraph_changed():
        if not w.source_mode.isChecked():return
        import re
        match=re.match(r'^(#{1,6} |>)',w.editor.textCursor().block().text())
        prefix=match[0] if match else ''
        w.paragraph.setCurrentIndex(max(0,w.paragraph.findData('> ' if prefix=='>' else prefix)))
    w.editor.cursorPositionChanged.connect(paragraph_changed)
    w.editor_tools.addWidget(w.paragraph)
    w.format_actions={}
    for key,title,callback in [('bold',tr('Fett'),lambda:editing().wrap('**')),('italic',tr('Kursiv'),lambda:editing().wrap('*')),('underline',tr('Unterstrichen'),lambda:editing().wrap('u')),('list',tr('Liste'),lambda:editing().paragraph_style('- ')),('task',tr('Aufgabe'),lambda:editing().toggle_checkbox())]:
        action=w.editor_tools.addAction(title,callback);w.format_actions[key]=action
        if key in ('bold','italic','underline'):action.setCheckable(True)
    numbered=w.editor_tools.addAction(glyph('list-ordered'),tr('Nummerierte Liste'),lambda:editing().paragraph_style('1. '))
    w.editor_tools.insertAction(w.format_actions['task'],numbered)
    if not numbered.icon().isNull():w.editor_tools.widgetForAction(numbered).setToolButtonStyle(Qt.ToolButtonIconOnly)
    w.editor_tools.addSeparator()
    undo_actions=[]
    for title,icon,callback in [(tr('Rückgängig'),'undo-2',lambda:editing().undo()),(tr('Wiederholen'),'redo-2',lambda:editing().redo())]:
        action=w.editor_tools.addAction(glyph(icon),title,callback);undo_actions.append(action)
        if not action.icon().isNull():w.editor_tools.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonIconOnly)
    for key,icon in [('bold','bold'),('italic','italic'),('underline','underline'),('list','list'),('task','list-todo')]:
        action=w.format_actions[key];action.setIcon(glyph(icon))
        if not action.icon().isNull():w.editor_tools.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonIconOnly)
    w.format_actions['bold'].setToolTip(tr('Fett (Strg+B)'));w.format_actions['italic'].setToolTip(tr('Kursiv (Strg+I)'))
    w.format_button=button(tr('Weiteres'),lambda:None)
    formatting=QMenu(w.more_button)
    for title,action in [(tr('Fett (Strg+B)'),lambda:editing().wrap('**')),(tr('Kursiv (Strg+I)'),lambda:editing().wrap('*')),(tr('Code'),lambda:editing().wrap('`')),(tr('Tabelle einfügen'),lambda:editing().insert_table()),(tr('Notiz verknüpfen …'),lambda:w.safe(w.insert_link)),(tr('Bild einfügen …'),lambda:w.safe(w.insert_image))]: formatting.addAction(title,action)
    w.source_mode=QCheckBox(tr('Markdown-Quelltext (erweitert)'))
    def source_mode(enabled):
        w.authoring.setCurrentIndex(1 if enabled else 0);w.editor.set_source_mode(enabled)
        w.table_action.setMenu(None if enabled else w.rich_editor.table_menu)
        w.editor_tools.widgetForAction(w.table_action).setPopupMode(QToolButton.DelayedPopup if enabled else QToolButton.InstantPopup)
        w.format_actions['underline'].setEnabled(not enabled)
        if not enabled:w.live_action.setChecked(False);w.rich_editor.load_source();w.rich_editor.setFocus()
        else:w.editor.setFocus()
        w.rich_editor.cursor_changed()
    w.source_mode.toggled.connect(source_mode)
    source_action=QWidgetAction(formatting);source_action.setDefaultWidget(w.source_mode);formatting.addAction(source_action)
    w.format_button.setMenu(formatting);w.format_button.hide();menu.addMenu(formatting).setText(tr('Weitere Werkzeuge'))
    for title,icon,callback in [(tr('Zitat'),'quote',lambda:editing().paragraph_style('> ')),(tr('Notiz verknüpfen …'),'link',lambda:w.safe(w.insert_link))]:
        action=w.editor_tools.addAction(glyph(icon),title,callback);w.editor_tools.insertAction(undo_actions[0],action)
        w.editor_tools.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonIconOnly)
    w.table_action=w.editor_tools.addAction(glyph('table'),tr('Tabelle'),lambda:editing().insert_table())
    w.editor_tools.insertAction(undo_actions[0],w.table_action)
    w.editor_tools.widgetForAction(w.table_action).setToolButtonStyle(Qt.ToolButtonIconOnly)
    w.table_action.setMenu(w.rich_editor.table_menu)
    w.editor_tools.widgetForAction(w.table_action).setPopupMode(QToolButton.InstantPopup)
    w.live_action=formatting.addAction(tr('Live-Vorschau'));w.live_action.setCheckable(True);w.live_action.setChecked(False);w.live_preview.set_enabled(False);w.live_action.toggled.connect(w.live_preview.set_enabled);w.live_action.toggled.connect(lambda checked:w.source_mode.setChecked(True) if checked else None)
    formatting.addAction(tr('Nur lesen'),w.toggle_view)
    w.outline_button=w.editor_tools.addAction(tr('Gliederung'))
    outline_menu=QMenu(w.editor_tools);w.outline_button.setMenu(outline_menu)
    w.editor_tools.widgetForAction(w.outline_button).setPopupMode(QToolButton.InstantPopup)
    def outline():
        from notes_structure import targets
        outline_menu.clear()
        headings=[value for value in targets(w.document_text()) if value['level']] if w.doc else []
        for value in headings[:200]:
            outline_menu.addAction('  '*(value['level']-1)+value['title'],lambda checked=False,a=value['anchor']:w.safe(w.focus_anchor,a))
        if not headings:outline_menu.addAction(tr('Noch keine Überschriften')).setEnabled(False)
    outline_menu.aboutToShow.connect(outline)
    w.editor_tools.setEnabled(False)
    writing_index=wl.indexOf(w.views);wl.removeWidget(w.views)
    w.editor_frame=QWidget();w.editor_frame.setObjectName('notesDocument');w.editor_frame.setAttribute(Qt.WA_StyledBackground);frame=QVBoxLayout(w.editor_frame);frame.setContentsMargins(1,1,1,1);frame.setSpacing(0)
    frame.addWidget(w.editor_tools)
    w.table_tools=QToolBar(tr('Tabelle bearbeiten'));w.table_tools.setObjectName('notesTableTools');w.table_tools.setMovable(False)
    for key in ('add_row','add_column','remove_row','remove_column','remove_table'):
        action=next(a for a in w.rich_editor.table_menu.actions() if a.data()==key);w.table_tools.addAction(action)
    frame.addWidget(w.table_tools);w.table_tools.hide();frame.addWidget(w.views,1);wl.insertWidget(writing_index,w.editor_frame,1)
    wl.addWidget(label(tr('Direkt schreiben · Text markieren und oben formatieren'),'muted'))
    w.views.currentChanged.connect(lambda index:w.editor_tools.setVisible(index==0))
    w.views.currentChanged.connect(lambda _:w.rich_editor.cursor_changed())
    from notes_tags_ui import NoteTagsBar
    w.note_tags=NoteTagsBar(w);wl.insertWidget(wl.indexOf(w.title)+1,w.note_tags)
    w.preview=NotePreview();w.preview.interop_root=w.library.root.parent;w.preview.setObjectName('wissenPreview');w.preview.noteRequested.connect(lambda p:w.safe(w.open_note,p));w.preview.targetRequested.connect(lambda p,a:w.safe(w.open_note_target,p,a));w.views.addWidget(w.preview)
    w.view_button=button(tr('Bearbeiten'),w.toggle_view,'document-edit');w.view_button.hide();wl.addWidget(w.view_button)
    w.details_button=button(tr('Quelle und zugehörige Notizen'),w.toggle_details,'insert-link');w.details_button.setCheckable(True);wl.addWidget(w.details_button)
    w.rail=QScrollArea();w.rail.setObjectName('wissenDetails');w.rail.setWidgetResizable(True);w.rail.setMaximumHeight(230);w.rail.hide()
    details=QWidget();dl=QVBoxLayout(details);dl.setContentsMargins(12,12,12,12);dl.setSpacing(12);w.rail.setWidget(details);wl.addWidget(w.rail)
    w.source=label(tr('Herkunft und Verbindungen erscheinen hier.'),'muted');w.source.setTextFormat(Qt.RichText);w.source.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.LinksAccessibleByMouse|Qt.LinksAccessibleByKeyboard)
    from interop_open import open_url
    w.source.linkActivated.connect(lambda url:w.safe(open_url,url,w.library.root.parent));dl.addWidget(w.source)
    w.origin=label('','muted');w.origin.setTextFormat(Qt.RichText);w.origin.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.LinksAccessibleByMouse|Qt.LinksAccessibleByKeyboard)
    w.origin.linkActivated.connect(lambda url:w.safe(open_url,url,w.library.root.parent));w.origin.hide();wl.insertWidget(wl.indexOf(w.editor_frame),w.origin)
    w.links=QListWidget();w.links.setAccessibleName(tr('Verknüpfungen und Rückverweise'));w.links.setMaximumHeight(95);w.links.itemActivated.connect(lambda item:w.safe(w.follow_connection,item.data(Qt.UserRole)));dl.addWidget(w.links)
    w.memory_options=QWidget();ol=QVBoxLayout(w.memory_options);ol.setContentsMargins(0,0,0,0)
    w.use_memory=QCheckBox(tr('Gedächtnis verwenden'));w.learn_memory=QCheckBox(tr('Aus Gesprächen lernen'));ol.addWidget(w.use_memory)
    w.memory_cost=label(tr('Lokale Bedeutungssuche: zusätzlich ca. 500 MiB RAM während der Nutzung. Einmalig ca. 128 MB Modelldaten plus Laufzeitpakete. Ohne Modell bleibt die Textsuche verfügbar.'),'muted');ol.addWidget(w.memory_cost)
    w.use_memory.setAccessibleDescription(w.memory_cost.text())
    from setup_dialog import open_setup
    ol.addWidget(button(tr('Bedeutungssuche einrichten …'),lambda:open_setup(w)))
    w.memory_search_status=label('','muted');ol.addWidget(w.memory_search_status);ol.addWidget(w.learn_memory)
    w.reuse_solutions=QCheckBox(tr('Bestätigte Lösungen wiederverwenden'));ol.addWidget(w.reuse_solutions)
    w.auto_memory=QCheckBox(tr('Gelernte Erinnerungen automatisch übernehmen'));ol.addWidget(w.auto_memory)
    from memory_review_ui import review as review_memories
    ol.addWidget(button(tr('Gedächtnisvorschläge prüfen …'),lambda:w.safe(review_memories,w)))
    w.reuse_solutions.toggled.connect(lambda _:w.safe(w.configure_memory));w.auto_memory.toggled.connect(lambda _:w.safe(w.configure_memory))
    ol.addWidget(label(tr('Passende Erinnerungen und freigegebene Notizen gehen an deinen KI-Anbieter. Beim Lernen beurteilt das Modell deine Nachricht und die vorherige Antwort. Gespeichertes bleibt hier einsehbar.'),'muted'))
    from memory_sync_ui import configure as configure_memory_sync
    ol.addWidget(button(tr('Gedächtnis mit Lumen Server abgleichen …'),lambda:w.safe(configure_memory_sync,w),'network-server'))
    ol.addWidget(button(tr('Projektordner zuordnen …'),lambda:w.safe(configure_projects,w),'folder'))
    w.use_memory.toggled.connect(lambda _:w.safe(w.configure_memory));w.learn_memory.toggled.connect(lambda _:w.safe(w.configure_memory));dl.addWidget(w.memory_options);w.memory_options.hide()
    w.save_note_button=button(tr('Speichern'),lambda:w.safe(w.save_note),primary=True);w.save_note_button.setIcon(glyph('save'));w.save_note_button.setEnabled(False);w.save_note_button.setMaximumWidth(150)
    w.status.setMaximumWidth(16777215)
    footer=row(w.status,w.save_note_button);footer.setObjectName('notesSave');footer.layout().setContentsMargins(0,16,0,0);footer.layout().setStretch(0,1);wl.addWidget(footer)
    w.tabs.addTab(writing,tr('Notizen'))
    questions(w);map_page=QWidget();ml=QVBoxLayout(map_page);ml.setContentsMargins(24,22,24,18);ml.addWidget(label(tr('Eine Notiz und ihre direkten Verbindungen · maximal 36 Nachbarn'),'muted'))
    w.map=KnowledgeMap();w.map.noteRequested.connect(lambda p:w.safe(w.open_note,p));w.map.objectRequested.connect(lambda url:w.safe(w.follow_connection,url));ml.addWidget(w.map,1);w.tabs.addTab(map_page,tr('Notizkarte'));w.tabs.currentChanged.connect(w.tab_changed)
    from memory_profile import MemoryProfile
    dl.removeWidget(w.memory_options)
    w.profile=MemoryProfile(w.memory_options);w.profile.noteRequested.connect(lambda path:w.safe(w.open_profile_note,path))
    w.tabs.addTab(w.profile,tr('Über dich'))
    w.split.setStretchFactor(0,0);w.split.setStretchFactor(1,1);reflow(w)
    w.update_collections();old.deleteLater()


def questions(w):
    asking=QWidget();al=QVBoxLayout(asking);al.setContentsMargins(24,22,24,18)
    al.addWidget(label(tr('Deine Notizen befragen'),'heading'));al.addWidget(label(tr('Quellen lokal auswählen. Erst „Lumen fragen“ sendet die gewählten Auszüge an deinen eingerichteten Anbieter.'),'muted'))
    w.question=QLineEdit();w.question.setPlaceholderText(tr('Was habe ich über das Projekt festgehalten?'));w.question.setAccessibleName(tr('Frage an deine Notizen'));w.question.returnPressed.connect(w.find_sources)
    al.addWidget(w.question);al.addWidget(row(button(tr('Quellen finden'),w.find_sources,'edit-find'),button(tr('Lumen fragen'),lambda:w.safe(w.ask),'lumen',True)))
    w.candidates=QListWidget();w.candidates.setAccessibleName(tr('Ausgewählte Quellen für die Antwort'));w.candidates.setMaximumHeight(180);w.candidates.setWordWrap(True);w.candidates.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);al.addWidget(w.candidates)
    w.candidates.itemActivated.connect(lambda item:w.safe(w.open_note,item.data(Qt.UserRole)))
    w.response=Transcript();w.response.setReadOnly(True);w.response.setOpenExternalLinks(False);w.response.setAccessibleName(tr('Antwort mit Quellen'));w.response.anchorClicked.connect(w.answer_link);al.addWidget(w.response,1)
    al.addWidget(button(tr('Antwort als Notiz'),lambda:w.safe(w.save_answer),'document-save'));w.tabs.addTab(asking,tr('Fragen'))

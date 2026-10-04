"""Content actions in existing menus; no additional application chrome."""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QTextEdit
from lumen_i18n import tr


def send(window, action):
    from interop_ui import with_saved, reviewed_send, capture
    with_saved(window, lambda: reviewed_send(window, capture(window), action))


def add_actions(window, menu, payload=None):
    from interop_ui import actions, capture, safe_action, copy_link, browse, show_files
    if getattr(window, 'job', None): return
    try: payload = payload or capture(window)
    except ValueError: return
    source = payload.get('source', {})
    options = actions(payload)
    primary = {'translate.import', 'wissen.import', 'workbench.add', 'vault.sources'}
    extra = None
    for action, title in options:
        if action not in primary and extra is None: extra = menu.addMenu(tr('Weitere Aktionen'))
        target = menu if action in primary else extra
        target.addAction(title, lambda checked=False, a=action: safe_action(window, lambda: send(window, a)))
    menu.addSeparator()
    link_label = tr('Link zu dieser Notiz kopieren') if source.get('app') == 'wissen' else tr('Link zu dieser Stelle kopieren') if source.get('app') == 'reader' else tr('Link zu diesem Eintrag kopieren')
    menu.addAction(link_label, lambda: safe_action(window, lambda: copy_link(window)))
    if source.get('app') != 'files' and (payload.get('paths') or source.get('path')):
        menu.addAction(tr('Speicherort öffnen'), lambda: safe_action(window, lambda: show_files(window)))
    menu.addAction(tr('Verwendet in …'), lambda: safe_action(window, lambda: browse(window, 'related')))
    menu.addAction(tr('Schlagwörter …'), lambda: safe_action(window, lambda: browse(window, 'tags')))
    if getattr(window, 'name', '') in ('workbench', 'household'):
        from interop_live import show_live, show_paths
        menu.addAction(tr('Zugehörige Notizen …'), lambda: safe_action(window, lambda: show_live(window)))
        if window.name == 'household':
            menu.addAction(tr('Zugehörige Dateien …'), lambda: safe_action(window, lambda: show_paths(window)))
    for name in ('_audio_profile_menu','_communications_menu','_workflow_menu'):
        if hasattr(window,name):menu.addMenu(getattr(window,name))


def add_history(window, menu):
    from interop_ui import browse, safe_action
    menu.addAction(tr('Letzte Aktionen …'), lambda: safe_action(window, lambda: browse(window, 'history')))
    menu.addAction(tr('In allen Lumen-Anwendungen suchen …'), lambda: safe_action(window, lambda: browse(window, 'search')))


def install(window):
    def context(widget, point):
        if widget is window.entries or widget is getattr(window,'notes',None) and hasattr(widget,'itemAt'):
            item = widget.itemAt(point)
            if not item: return
            widget.setCurrentItem(item)
        window._interop_focus = widget
        menu = widget.createStandardContextMenu() if isinstance(widget, (QPlainTextEdit, QTextEdit)) else QMenu(window)
        if menu.actions(): menu.addSeparator()
        loading=menu.addAction(tr('Auswahl wird geladen …'));loading.setEnabled(False)
        timer=QTimer(menu);timer.setInterval(50)
        def populate():
            if getattr(window,'job',None):return
            timer.stop();menu.removeAction(loading);loading.deleteLater();window._interop_focus=widget
            add_actions(window,menu);add_history(window,menu)
        from interop_ui import safe_action
        timer.timeout.connect(lambda:safe_action(window,populate));timer.start();populate()
        menu.exec(widget.mapToGlobal(point));timer.stop();menu.deleteLater()
    widgets = [window.entries]
    if window.name == 'translate': widgets += [window.input, window.output]
    if window.name == 'reader': widgets += [getattr(window,name) for name in ('canvas','text','notes','note') if hasattr(window,name)]
    if window.name == 'wissen' and hasattr(window,'editor'): widgets += [window.editor]
    for widget in widgets:
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        from interop_ui import safe_action
        widget.customContextMenuRequested.connect(lambda point, w=widget: safe_action(window,lambda:context(w, point)))
    if window.name == 'wissen' and hasattr(window,'more_button'):
        menu = window.more_button.menu()
        menu.addSeparator()
        dynamic = []
        def update():
            for action in dynamic: menu.removeAction(action); action.deleteLater()
            before = set(menu.actions()); add_actions(window, menu)
            dynamic[:] = [action for action in menu.actions() if action not in before]
        menu.aboutToShow.connect(update)
        add_history(window, window.notebook_menu)
    elif window.name == 'reader' and hasattr(window,'document_menu'):
        add_history(window, window.document_menu)


def receive_drop(window, payload):
    from interop_ui import reviewed_send, actions
    name = getattr(window, 'name', '')
    if name == 'reader' and payload.get('paths'):
        from interop_targets import READER_SUFFIXES
        if all(Path(p).is_file() and Path(p).suffix.lower() in READER_SUFFIXES for p in payload['paths']):
            from interop_ui import controller
            for path in payload['paths']:controller(window).enqueue({'path':path})
            return
    preferred = {'wissen':'wissen.import', 'reader':'reader.import', 'workbench':'workbench.add',
                 'household':'household.add', 'vault':'vault.sources', 'radio':'radio.add', 'meetings':'meetings.import'}
    action = preferred.get(name)
    reviewed_send(window, payload, action if action in dict(actions(payload)) else None)

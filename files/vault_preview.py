"""Non-persistent design prototype. ONLY fixed synthetic fixtures, never a secret API.

Deliberately no create/import/save or free-form secret inputs. Replacing these
fixtures with user data is NOT a backend integration: see SPEC-vault-secrets.md.
"""
from pathlib import Path
import sys
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QSettings, QUrl, QEvent, QStandardPaths, ClassInfo
from PySide6.QtGui import QGuiApplication, QPalette, QIcon, QColor
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBus
from lumen_i18n import tr, install


def fixtures():
    return [dict(id=key, title=tr(title), username=user, website=site, kind=kind, collection=tr(collection),
                 favorite=favorite, secret='DEMO-ONLY-NOT-A-REAL-SECRET', trashed=False, note=tr(note))
        for key,title,user,site,kind,collection,favorite,note in [
            ('mail','Mailkonto','alex@example.invalid','mail.example.invalid','login','Privat',True,'Ein Beispiel für deine täglichen Anmeldungen.'),
            ('git','Git-Server','alex','git.example.invalid','login','Arbeit',True,'Ein Beispiel für einen Zugang im Team.'),
            ('nas','NAS','demo','nas.example.invalid','login','Server',False,'Ein Beispiel für deine Geräte und Dienste.'),
            ('api','Cloud API','Demo-Projekt','api.example.invalid','token','Arbeit',True,'Berechtigungen: nur Lesen · Umgebung: Test'),
            ('note','Sichere Notiz','','','note','Privat',False,'Dies ist eine feste Beispielnotiz. Hier werden keine eigenen Inhalte gespeichert.'),
            ('codes','Wiederherstellungscodes','','','recovery','Privat',False,'Beispielcodes, die zu keinem echten Konto gehören.')]]


class VaultPreview(QObject):
    changed = Signal(); themeChanged = Signal()
    def __init__(self):
        super().__init__()
        self.settings = QSettings('Lumen', 'Assistant'); self._theme = {}; self.reload_theme()
        self.rows = []; self.selected = ''; self.category = 'all'; self.query = ''; self.revealed = False
        self.message = ''; self._locked = True
        self.hide_timer = QTimer(self); self.hide_timer.setSingleShot(True); self.hide_timer.setInterval(10000)
        self.hide_timer.timeout.connect(self.hide_secret)
        self.lock_timer = QTimer(self); self.lock_timer.setSingleShot(True); self.lock_timer.setInterval(300000)
        self.lock_timer.timeout.connect(self.lock)
        self.theme_timer = QTimer(self); self.theme_timer.setInterval(2000); self.theme_timer.timeout.connect(self.reload_theme); self.theme_timer.start()

    theme = Property('QVariantMap', lambda s: s._theme, notify=themeChanged)
    locked = Property(bool, lambda s: s._locked, notify=changed)
    status = Property(str, lambda s: s.message, notify=changed)
    activeCategory = Property(str, lambda s: s.category, notify=changed)
    @Property('QVariantList', notify=changed)
    def entries(self):
        # Synthetic metadata only. Even fake secret values stay out of the list model.
        if self._locked: return []
        return [{k:v for k,v in r.items() if k not in ('secret','note')} for r in self.rows
                if r['trashed'] == (self.category == 'trash')
                and (self.category in ('all','trash') or (self.category == 'favorites' and r['favorite'])
                     or r['kind'] == self.category or r['collection'] == self.category)
                and self.query.casefold() in (r['title']+' '+r['username']+' '+r['website']).casefold()]
    @Property('QVariantMap', notify=changed)
    def detail(self):
        row = next((r for r in self.rows if r['id']==self.selected), None) if not self._locked else None
        if not row: return {}
        value = dict(row); value['secret'] = row['secret'] if self.revealed else '•••• •••• •••• ••••'
        value['revealed'] = self.revealed
        return value

    @Slot(str, result=str)
    def text(self, value): return tr(value)

    def reload_theme(self):
        from appearance_tokens import COLORS, RADII, DEFAULT_DESIGN, normalize_design
        from ui_typography import metrics
        self.settings.sync(); name = normalize_design(self.settings.value('appearance', DEFAULT_DESIGN))
        colors = COLORS.get(name)
        if colors is None:
            colors = tuple(QGuiApplication.palette().color(role).name() for role in
                           (QPalette.Window,QPalette.Base,QPalette.AlternateBase,QPalette.Text,QPalette.Button,QPalette.Mid,QPalette.Dark,QPalette.Highlight,QPalette.HighlightedText))
        theme = dict(zip(('window','base','hover','text','button','border','muted','accent','onAccent'),colors))
        theme.update(metrics(self.settings), radius=RADII[name])
        if theme != self._theme: self._theme = theme; self.themeChanged.emit()

    @Slot()
    def show_demo(self):
        self.rows = fixtures(); self._locked = False; self.selected = 'mail'; self.category = 'all'; self.query = ''
        self.message = tr('Beispieldaten · Änderungen werden nicht gespeichert.'); self.lock_timer.start(); self.changed.emit()

    @Slot(bool)
    def screen_locked(self, active):
        if active: self.lock()

    @Slot()
    def lock(self):
        self.rows.clear(); self.selected = ''; self.query = ''; self.category = 'all'; self.revealed = False
        self._locked = True; self.message = ''; self.hide_timer.stop(); self.lock_timer.stop(); self.changed.emit()

    @Slot(str)
    def filter(self, query):
        if self._locked: return
        self.query = query[:256]; self._match_selection()

    @Slot(str)
    def choose_category(self, category):
        if self._locked: return
        self.category = category; self._match_selection()

    def _match_selection(self):
        self.revealed = False; self.hide_timer.stop()
        if not any(r['id'] == self.selected for r in self.entries): self.selected = self.entries[0]['id'] if self.entries else ''
        self.changed.emit()

    @Slot(str)
    def select(self, identity):
        if any(r['id']==identity for r in self.entries):
            self.selected = identity; self.revealed = False; self.hide_timer.stop(); self.changed.emit()

    @Slot()
    def reveal(self):
        if self._locked or not self.selected: return
        self.revealed = not self.revealed
        if self.revealed: self.hide_timer.start()
        else: self.hide_timer.stop()
        self.changed.emit()

    def hide_secret(self): self.revealed = False; self.changed.emit()

    @Slot()
    def favorite(self):
        for r in self.rows:
            if r['id'] == self.selected: r['favorite'] = not r['favorite']; break
        self._match_selection()

    @Slot()
    def trash(self):
        for r in self.rows:
            if r['id'] == self.selected: r['trashed'] = not r['trashed']; break
        self._match_selection()

    @Slot(str)
    def explain(self, action):
        self.message = tr({'copy':'In der Vorschau wird nichts in die Zwischenablage kopiert.',
            'new':'Eigene Einträge folgen mit der geprüften Speicher-Engine. Diese Vorschau verwendet nur feste Beispieldaten.',
            'edit':'Dies ist ein festes Beispiel. Eigene Zugangsdaten können hier noch nicht eingegeben werden.',
            'access':'App-Zugriffe bleiben gesperrt. Die Vorschau hat keine Verbindung zu Lumen, KI oder MCP.',
            'collection':'Beispielsammlungen: Privat, Arbeit und Server. Eigene Sammlungen folgen mit dem Tresorkern.'}.get(action,'Designvorschau · keine Passwortverwaltung.'))
        self.changed.emit()

    @Slot()
    def backups(self):
        from PySide6.QtCore import QProcess
        from lumen_launch import executable
        ok, _ = QProcess.startDetached(executable('lumen-vault'), [])
        if not ok: self.message = tr('Sicherungen konnten nicht geöffnet werden.'); self.changed.emit()

    def eventFilter(self, watched, event):
        if not self._locked and event.type() in (QEvent.KeyPress,QEvent.MouseButtonPress,QEvent.Wheel,QEvent.TouchBegin): self.lock_timer.start()
        return False


@ClassInfo(**{'D-Bus Interface':'org.lumen.VaultPreview'})
class Activation(QObject):
    def __init__(self, window): super().__init__(); self.window = window
    @Slot()
    def Activate(self): self.window.showNormal(); self.window.raise_(); self.window.requestActivate()


def create_window(controller):
    QIcon.setThemeSearchPaths([str(Path(p)/'icons') for p in QStandardPaths.standardLocations(QStandardPaths.GenericDataLocation)] + QIcon.themeSearchPaths())
    def icons():
        QIcon.setThemeName('breeze-dark' if QColor(controller.theme['window']).lightness() < 128 else 'breeze')
    icons(); controller.themeChanged.connect(icons)
    engine = QQmlApplicationEngine(); engine.setInitialProperties({'controller':controller})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('qml')/'vault'/'Vault.qml')))
    if not engine.rootObjects(): raise RuntimeError('Vault preview failed to load')
    return engine, engine.rootObjects()[0]


def main():
    # No file arguments, input, recovery state, clipboard reader or secret IPC.
    if len(sys.argv) != 1: return 2
    app = QGuiApplication(sys.argv); app.setApplicationName('lumen-vault-preview'); app.setDesktopFileName('lumen-vault')
    app.setApplicationDisplayName(tr('Lumen Vault · Designvorschau')); install(app)
    app.setWindowIcon(QIcon.fromTheme('lumen-vault', QIcon.fromTheme('document-encrypt')))
    bus = QDBusConnection.sessionBus(); service = 'org.lumen.VaultPreview'
    if bus.isConnected() and not bus.registerService(service):
        reply = bus.call(QDBusMessage.createMethodCall(service,'/Preview',service,'Activate'),QDBus.Block,2000)
        return int(reply.type() == QDBusMessage.ErrorMessage)
    controller = VaultPreview(); engine, window = create_window(controller); activation = Activation(window)
    if bus.isConnected():
        bus.registerObject('/Preview',activation,QDBusConnection.ExportAllSlots)
        bus.connect('org.freedesktop.ScreenSaver','/ScreenSaver','org.freedesktop.ScreenSaver','ActiveChanged',controller.screen_locked)
    app.installEventFilter(controller); app.aboutToQuit.connect(controller.lock)
    window.show(); result = app.exec(); engine.deleteLater(); app.sendPostedEvents(None,0); return result


if __name__ == '__main__': sys.exit(main())

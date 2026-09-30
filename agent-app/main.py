#!/usr/bin/python3
"""Native Lumen desktop application; OpenCode runs only behind the scenes."""
import argparse
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'files'))
from PyQt5.QtCore import QObject, Q_CLASSINFO, QProcess, QSettings, Qt, QTimer, QUrl, pyqtSlot
from PyQt5.QtDBus import QDBus, QDBusConnection, QDBusMessage
from PyQt5.QtGui import QIcon, QKeySequence, QTextDocument
from PyQt5.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QMainWindow,
                             QPushButton, QShortcut, QStackedWidget, QVBoxLayout, QWidget)
from app import create_app, button
from assistant import ChatPanel, Transcript
from preview import label


class DesktopActivation(QObject):
    Q_CLASSINFO('D-Bus Interface', 'org.lumen.Desktop')

    def __init__(self):
        super().__init__()
        self.window = None
        self.pending = False
        self.page = 0

    @pyqtSlot(int)
    def ActivatePage(self, page):
        self.page = page
        self.Activate()

    @pyqtSlot()
    def Activate(self):
        self.pending = True
        if self.window is None:
            return
        # Refresh the X11 user timestamp for an explicit launcher/hotkey request.
        try:
            from PyQt5.QtX11Extras import QX11Info
            if QX11Info.isPlatformX11():
                QX11Info.setAppUserTime(QX11Info.getTimestamp())
        except ImportError:
            pass
        window = QApplication.activeModalWidget() or self.window
        self.window.setWindowState(self.window.windowState() & ~Qt.WindowMinimized)
        self.window.show_page(self.page)
        self.window.show()
        window.raise_()
        window.activateWindow()


class LumenWindow(QMainWindow):
    def __init__(self, directory, file_settings=None):
        super().__init__()
        self.setWindowTitle('Lumen')
        icon = ROOT / 'icons/hicolor/scalable/apps/lumen.svg'
        self.setWindowIcon(QIcon(str(icon)) if icon.exists() else QIcon.fromTheme('lumen'))
        self.resize(1380, 860)
        self.setMinimumSize(760, 600)
        self.settings = QSettings('Lumen', 'Assistant')
        self.file_settings = file_settings
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        self.jobs = []
        self.cpu_previous = None
        self.copy_after_answer = False
        central = QWidget()
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        self.navigation = QWidget()
        navigation = QVBoxLayout(self.navigation)
        navigation.setContentsMargins(10, 20, 10, 10)
        navigation.addWidget(label('DEIN ASSISTENT', 'eyebrow'))
        self.pages = QStackedWidget()
        self.chat = ChatPanel(directory, settings=self.settings)
        self.pages.addWidget(self.chat)
        self.chat.backend.busyChanged.connect(self.copy_answer_if_ready)
        self.chat.backend.failed.connect(lambda _: setattr(self, "copy_after_answer", False))
        self.system_page = self.build_system()
        self.pages.addWidget(self.system_page)
        self.pages.addWidget(self.build_actions())
        self.files_page = QWidget()
        self.file_window = None
        self.pages.addWidget(self.files_page)
        from lumen_workspace import Workspace
        self.workspace = Workspace(self)
        for page in (self.workspace.tasks_page, self.workspace.knowledge_page, self.workspace.flows_page, self.workspace.models_page):
            self.pages.addWidget(page)
        self.nav_buttons = []
        for index, title in enumerate(('Gespräche', 'Systemstatus', 'Aktionen', 'Dateien', 'Aufträge', 'Wissen', 'Abläufe', 'Modelle')):
            item = button(title, lambda _=False, i=index: self.show_page(i))
            item.setCheckable(True)
            navigation.addWidget(item)
            self.nav_buttons.append(item)
        navigation.addStretch()
        navigation.addWidget(button('Einstellungen', self.show_settings, 'configure', 'Strg+Komma'))
        QShortcut(QKeySequence('Ctrl+,'), self, activated=self.show_settings)
        navigation.addWidget(button('Ordner wählen', self.choose_directory, 'folder-open'))
        navigation.addWidget(button('Dateien hinzufügen', lambda: self.choose_files(), 'list-add'))
        row.addWidget(self.navigation)
        row.addWidget(self.pages, 1)
        self.show_page(0)
        self.chat.actionChanged.connect(self.present_action)
        self.chat.closeRequested.connect(self.close)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(lambda: self.refresh_system() if self.pages.currentIndex() == 1 else None)
        self.refresh_timer.start(5000)

    def show_settings(self):
        from settings_dialog import SettingsDialog
        dialog = SettingsDialog(self, assistant_settings=self.settings)
        dialog.preferencesChanged.connect(self.chat.reload_settings)
        dialog.exec_()
        dialog.deleteLater()

    def present_action(self, action):
        was_action = self.navigation.isHidden()
        self.navigation.setVisible(not action)
        self.setWindowTitle(self.chat.heading.text() + ' — Lumen' if action else 'Lumen')
        self.setMinimumSize(560, 520) if action else self.setMinimumSize(760, 600)
        if action:
            self.resize(680, 740)
        elif was_action:
            self.resize(1380, 860)

    def show_page(self, index):
        if index == 3 and self.file_window is None:
            from app import Window
            self.file_window = Window(self.chat.backend.directory, settings=self.file_settings)
            self.file_window.lumen_host = self
            for shortcut in self.file_window.findChildren(QShortcut):
                shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            self.file_window.setWindowFlags(Qt.Widget)
            self.file_window.setMinimumSize(0, 0)
            layout = QVBoxLayout(self.files_page); layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.file_window)
            self.file_window.show()
        self.pages.setCurrentIndex(index)
        for i, item in enumerate(self.nav_buttons):
            item.setChecked(i == index)
        if index == 1:
            self.refresh_system()

    def choose_directory(self):
        if self.chat.backend.busy:
            self.show_page(0)
            self.chat.show_error('Bitte den laufenden Vorgang zuerst abschließen oder abbrechen.')
            return
        path = QFileDialog.getExistingDirectory(self, 'Arbeitsordner wählen', self.chat.backend.directory)
        if path:
            self.chat.begin_context(directory=path)
            self.show_page(0)

    def choose_files(self, action='open'):
        if self.chat.backend.busy:
            self.show_page(0)
            self.chat.show_error('Bitte den laufenden Vorgang zuerst abschließen oder abbrechen.')
            return
        paths, _ = QFileDialog.getOpenFileNames(self, 'Dateien zu Lumen hinzufügen', self.chat.backend.directory)
        if paths:
            self.chat.begin_context(action, paths=paths)
            self.show_page(0)

    def build_system(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(label('Systemstatus', 'heading'))
        layout.addWidget(label('Auslastung und der letzte Wächter-Bericht', 'muted'))
        grid = QGridLayout()
        self.metrics = {}
        for i, name in enumerate(('CPU', 'Arbeitsspeicher', 'Laufwerk /', 'Grafikkarte', 'Benutzerdienste', 'Systemdienste')):
            card = QWidget()
            box = QVBoxLayout(card)
            box.addWidget(label(name, 'muted'))
            value = label('…', 'previewTitle')
            value.setWordWrap(True)
            box.addWidget(value)
            self.metrics[name] = value
            grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(grid)
        self.report = Transcript()
        self.report.setAccessibleName('Letzter Systembericht')
        layout.addWidget(self.report, 1)
        self.report_status = label('', 'muted')
        self.report_status.setWordWrap(True)
        layout.addWidget(self.report_status)
        actions = QHBoxLayout()
        actions.addWidget(button('Aktualisieren', self.refresh_system))
        self.watch_button = button('Wächter prüfen', self.run_watch)
        actions.addWidget(self.watch_button)
        actions.addWidget(button('Mit Lumen besprechen', self.discuss_report))
        layout.addLayout(actions)
        return page

    def build_actions(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(label('Direkt loslegen', 'heading'))
        for title, callback in [
            ('Dateien erklären', lambda: self.choose_files('explain')),
            ('Dateifehler beheben', lambda: self.choose_files('fix')),
            ('Zwischenablage besprechen', lambda: self.selection('explain')),
            ('Text korrigieren', lambda: self.selection('fix')),
            ('Text übersetzen', lambda: self.selection('translate')),
            ('Systembericht ansehen', lambda: self.show_page(1)),
            ('Lumen — Dateien öffnen', self.open_files)]:
            layout.addWidget(button(title, callback))
        layout.addStretch()
        return page

    def run_job(self, program, arguments, callback, timeout=10000):
        job = QProcess(self)
        self.jobs.append(job)
        done = False
        timer = QTimer(job)
        timer.setSingleShot(True)
        timer.timeout.connect(job.kill)
        def finish(code):
            nonlocal done
            if done:
                return
            done = True
            timer.stop()
            output = bytes(job.readAllStandardOutput()).decode(errors='replace').strip()
            callback(code, output)
            self.jobs.remove(job)
            job.deleteLater()
        job.finished.connect(lambda code, _status: finish(code))
        job.errorOccurred.connect(lambda error: finish(-1) if error == QProcess.FailedToStart else None)
        job.start(program, arguments)
        timer.start(timeout)

    def refresh_system(self):
        try:
            cpu = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            total, idle = sum(cpu), cpu[3] + cpu[4]
            if self.cpu_previous and total > self.cpu_previous[0]:
                usage = 100 * (1 - (idle - self.cpu_previous[1]) / (total - self.cpu_previous[0]))
                self.metrics['CPU'].setText(f'{usage:.0f} %')
            self.cpu_previous = (total, idle)
            mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
            self.metrics['Arbeitsspeicher'].setText(f"{(mem['MemTotal'] - mem['MemAvailable']) / 1048576:.1f} / {mem['MemTotal'] / 1048576:.1f} GiB")
            disk = shutil.disk_usage('/')
            self.metrics['Laufwerk /'].setText(f'{100 * disk.used / disk.total:.0f} % belegt')
        except (OSError, ValueError, KeyError):
            self.report_status.setText('Einige Systemwerte sind nicht verfügbar.')
        if not self.jobs:
            self.run_job('nvidia-smi', ['--query-gpu=utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'],
                         lambda code, out: self.metrics['Grafikkarte'].setText(out.replace(',', ' % ·') + ' °C' if code == 0 else 'Nicht verfügbar'))
            for user, name in [(True, 'Benutzerdienste'), (False, 'Systemdienste')]:
                self.run_job('systemctl', (['--user'] if user else []) + ['--failed', '--no-legend', '--plain'],
                             lambda code, out, n=name: self.metrics[n].setText(f'{len(out.splitlines())} fehlgeschlagen' if code == 0 else 'Nicht verfügbar'))
        reports = [Path(os.environ.get('LUMEN_STATE', str(Path.home() / '.cache/lumen'))) / 'latest-analysis.md', Path('/var/lib/lumen/findings.md')]
        self.report_text = ''
        for path in reports:
            try:
                self.report_text += f'## {path.name}\n\n' + path.read_text() + '\n\n'
            except OSError:
                pass
        self.report.document().setMarkdown(self.report_text or 'Noch kein Systembericht vorhanden.', QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))

    def run_watch(self):
        self.watch_button.setEnabled(False)
        self.report_status.setText('Wächter-Prüfung wird angefordert …')
        system_install = Path('/usr/share/dbus-1/system-services/org.lumen.Agent.service').exists()
        def finished(code, out):
            self.watch_button.setEnabled(True)
            self.refresh_system()
            okay = code == 0 and (not system_install or out == 'b true')
            self.report_status.setText('Prüfung angefordert. Der Bericht wird automatisch aktualisiert.' if okay
                                       else 'Prüfung konnte nicht gestartet werden. Der Wächter-Dienst ist möglicherweise nicht verfügbar.')
        if system_install:
            self.run_job('busctl', ['--system', '--timeout=10s', 'call', 'org.lumen.Agent',
                                  '/org/lumen/Agent', 'org.lumen.Agent', 'RefreshWatch'], finished)
        else:
            self.run_job(str(Path(os.environ.get('LUMEN_BIN_DIR', '/usr/bin')) / 'lumen-watch'), [], finished, 300000)

    def discuss_report(self):
        self.show_page(0)
        self.chat.begin_context(prompt='Erkläre den folgenden Systembericht und priorisiere sinnvolle nächste Schritte.\n\n' + self.report_text)

    def open_files(self):
        self.show_page(3)

    def copy_answer_if_ready(self, busy):
        if busy or not self.copy_after_answer:
            return
        self.copy_after_answer = False
        answers = [m for m in self.chat.backend.messages if m.get('info', {}).get('role') == 'assistant'
                   and m['info'].get('parentID') == self.chat.backend.message_id]
        if (answers and answers[-1]['info'].get('time', {}).get('completed')
                and not answers[-1]['info'].get('error') and self.chat.last_answer):
            QApplication.clipboard().setText(self.chat.last_answer)

    def selection(self, action):
        clipboard = QApplication.clipboard()
        text = clipboard.text(clipboard.Selection) if clipboard.supportsSelection() else ''
        text = text or clipboard.text()
        self.show_page(0)
        if not text:
            self.chat.show_error('Die Zwischenablage enthält keinen Text.')
            return
        prompts = {'explain': 'Erkläre den folgenden Text verständlich:',
                   'fix': 'Korrigiere Rechtschreibung und Grammatik. Gib nur den korrigierten Text aus:',
                   'summarize': 'Fasse den folgenden Text in höchstens drei Sätzen zusammen:',
                   'translate': 'Übersetze den folgenden Text nach ' + os.environ.get('LUMEN_SEL_LANG', self.settings.value('translationLanguage', 'Deutsch')) + '. Gib nur die Übersetzung aus:'}
        if self.chat.backend.busy:
            self.chat.show_error("Bitte den laufenden Vorgang zuerst abschließen oder abbrechen.")
            return
        self.copy_after_answer = action in ("translate", "fix", "summarize")
        self.chat.begin_context(prompt=prompts.get(action, action) + '\n\n' + text)

    def closeEvent(self, event):
        if not self.workspace.can_close():
            event.ignore(); return
        if not self.chat.can_close():
            event.ignore()
            return
        if self.jobs and not self.watch_button.isEnabled():
            self.report_status.setText('Bitte die laufende Wächter-Prüfung vor dem Schließen abwarten.')
            self.show_page(1)
            event.ignore()
            return
        if self.file_window is not None and not self.file_window.close():
            event.ignore(); return
        self.chat.tracker.interrupt()
        self.chat.context_tools.close()
        self.chat.backend.shutdown()
        for job in self.jobs[:]:
            job.kill()
            job.waitForFinished(1000)
        if not self.chat.action:
            self.settings.setValue('geometry', self.saveGeometry())
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Lumen – dein Desktop-Assistent')
    parser.add_argument('--directory')
    parser.add_argument('--location', help='Datei- oder Netzwerkordner im Dateibereich')
    parser.add_argument('--prompt', default='')
    parser.add_argument('--action', choices=['open', 'ask', 'explain', 'fix', 'review'], default='open')
    parser.add_argument('--context', nargs='*', default=[])
    parser.add_argument('--file', action='append', default=[])
    parser.add_argument('--selection')
    parser.add_argument('--clipboard-image', action='store_true')
    parser.add_argument('--page', choices=['chat', 'system', 'actions', 'files', 'tasks', 'knowledge', 'workflows', 'models', 'settings'], default='chat')
    args = parser.parse_args()
    from lumen_migrate import migrate_user
    migrate_user()
    app = create_app(QSettings('Lumen', 'Assistant').value('appearance', 'lumen'))
    app.setApplicationName('Lumen')
    app.setDesktopFileName('lumen')
    activation = DesktopActivation()
    plain_launch = (args.action == 'open' and args.page != 'settings' and not any(
        (args.directory, args.location, args.prompt, args.context, args.file, args.selection,
         args.clipboard_image, os.environ.get('LUMEN_ASK_PROMPT'))))
    page_index = {'chat': 0, 'system': 1, 'actions': 2, 'files': 3, 'tasks': 4, 'knowledge': 5, 'workflows': 6, 'models': 7}
    activation.page = page_index.get(args.page, 0)
    bus = QDBusConnection.sessionBus()
    if plain_launch and bus.isConnected() and bus.registerObject('/Lumen', activation, QDBusConnection.ExportAllSlots):
        if not bus.registerService('org.lumen.Desktop'):
            request = QDBusMessage.createMethodCall('org.lumen.Desktop', '/Lumen', 'org.lumen.Desktop', 'ActivatePage')
            request.setArguments([page_index[args.page]])
            reply = bus.call(request, QDBus.Block, 3000)
            if reply.type() == QDBusMessage.ErrorMessage:
                print('Lumen: Das vorhandene Fenster antwortet nicht: ' + reply.errorMessage(), file=sys.stderr)
                return 1
            return 0
    directory = Path(args.directory or os.environ.get('LUMEN_WORKDIR') or
                     QSettings('Lumen', 'Assistant').value('workdir', str(Path.home() / 'Documents/work'))).expanduser()
    window = LumenWindow(str(directory if directory.is_dir() else Path.home()))
    activation.window = window
    if args.action in window.chat.action_titles:
        window.chat.set_action(args.action)
    window.show()
    if activation.pending:
        activation.Activate()
    def start():
        if args.page == 'settings':
            window.show_settings()
            return
        paths = [QUrl(p).toLocalFile() if p.startswith('file:') else p for p in args.context + args.file]
        if args.clipboard_image:
            clip = app.clipboard().mimeData()
            paths = [u.toLocalFile() for u in clip.urls() if u.isLocalFile()] if clip.hasUrls() else [app.clipboard().text().strip()]
        invalid = [p for p in paths if not Path(p).exists()]
        if invalid:
            window.chat.show_error('Pfad nicht erreichbar: ' + ', '.join(invalid))
            return
        if args.selection:
            window.selection(args.selection)
        elif args.page == 'chat' or args.prompt or paths or args.action != 'open':
            window.chat.begin_context(args.action, paths, prompt=args.prompt or os.environ.get('LUMEN_ASK_PROMPT', ''))
        window.show_page(page_index[args.page])
        if args.location:
            window.open_files()
            window.file_window.navigate(args.location)
    QTimer.singleShot(0, start)
    app.aboutToQuit.connect(window.chat.backend.shutdown)
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())

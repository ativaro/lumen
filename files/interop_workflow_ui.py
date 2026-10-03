"""Native review surfaces for household and project handoffs."""
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout, QLineEdit,
    QPlainTextEdit, QListWidget, QListWidgetItem, QInputDialog, QFileDialog, QMessageBox, QAbstractItemView)
from lumen_i18n import tr
from tools_ui import button, row, open_path
import interop_workflows as flow


def _ready(window):
    if not window.current: raise ValueError(tr('Zuerst einen Eintrag auswählen.'))
    if window.job: raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
    window.save(); return window.library.get(window.current)


def _files(window, record):
    if window.name == 'household':
        rows = [dict(title=a['name'], path=str(window.library.asset(a['asset']))) for a in record.get('attachments', [])]
    else:
        rows = [dict(title=r.get('title') or Path(r['target']).name, path=r['target']) for r in record.get('resources', []) if r.get('kind') == 'file' and Path(r['target']).is_file()]
    if not rows: return []
    dialog = QDialog(window); dialog.setWindowTitle(tr('Unterlagen auswählen')); dialog.resize(570, 430)
    layout = QVBoxLayout(dialog); listing = QListWidget(); listing.setAccessibleName(tr('Ausgewählte Unterlagen'))
    for value in rows:
        item = QListWidgetItem(value['title']+'\n'+value['path']); item.setData(Qt.UserRole, value['path']); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked); listing.addItem(item)
    layout.addWidget(listing); buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    if dialog.exec_() != QDialog.Accepted: return None
    return [listing.item(i).data(Qt.UserRole) for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked]


def _send(window, payload, action):
    from interop_ui import reviewed_send
    reviewed_send(window, payload, action)


def household(window, workflow):
    record = _ready(window)
    if workflow in ('remind', 'until'):
        _send(window, flow.deadline_payload(window.library, record['id'], workflow), 'inbox.event'); return
    text = ''
    if workflow == 'support':
        text, ok = QInputDialog.getMultiLineText(window, tr('Supportanfrage vorbereiten'), tr('Fehlerbeschreibung / Anliegen'), record.get('notes', ''))
        if not ok: return
    paths = [] if workflow == 'cancel' else _files(window, record)
    if paths is None: return
    payload = flow.household_payload(window.library, record['id'], workflow, text=text, paths=paths)
    if workflow == 'handover': _export(window, payload)
    else: _send(window, payload, 'workbench.add' if workflow == 'repair' else 'inbox.draft')


def invoice(window):
    record = _ready(window); item = window.attachments.currentItem()
    if not item: raise ValueError(tr('Zuerst einen Beleg aus der Liste auswählen.'))
    attachment = item.data(Qt.UserRole); key = record['id']
    def reviewed(text):
        def show():
            candidates = flow.invoice_candidates(text)
            dialog = QDialog(window); dialog.setWindowTitle(tr('Belegdaten prüfen')); dialog.resize(670, 570); form = QFormLayout(dialog)
            fields = {}
            for field, title in [('provider', tr('Hersteller / Anbieter')), ('model', tr('Modell / Vertragsnummer')), ('serial', tr('Seriennummer / Kundennummer')), ('since', tr('Kauf / Beginn'))]:
                control = QLineEdit(candidates.get(field, record.get(field, ''))); control.setAccessibleName(title); form.addRow(title, control); fields[field] = control
            preview = QPlainTextEdit(text); preview.setReadOnly(True); preview.setAccessibleName(tr('Erkannter Belegtext')); form.addRow(preview)
            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
            if dialog.exec_() != QDialog.Accepted: return
            values = {field: control.text().strip() for field, control in fields.items()}
            if values['since']:
                from datetime import date
                date.fromisoformat(values['since'])
            latest = window.library.get(key); attachments = latest.get('attachments', [])
            for value in attachments:
                if value['asset'] == attachment['asset']: value['text'] = text
            window.library.update(key, attachments=attachments, **values); window.focus_record(key)
        QTimer.singleShot(0, lambda: window.safe(show))
    from tools_data import document_text
    window.work(tr('Beleg wird lokal gelesen …'), lambda job: document_text(window.library.asset(attachment['asset']), job), reviewed)


def _export(window, payload):
    folder = QFileDialog.getExistingDirectory(window, tr('Übergabepaket speichern'), str(Path.home()))
    if not folder: return
    from interop_exports import export_payload
    window.work(tr('Übergabepaket wird zusammengestellt …'), lambda job: export_payload(payload, folder, job), lambda path: open_path(path))


def project(window, workflow):
    record = _ready(window); values = {}
    if workflow == 'lessons':
        text, ok = QInputDialog.getMultiLineText(window, tr('Projekterkenntnisse festhalten'), tr('Welche Erkenntnisse möchtest du übernehmen?'), window.notes.textCursor().selectedText().replace('\u2029', '\n') or record.get('notes', ''))
        if not ok: return
        values['text'] = text
    if workflow == 'milestone':
        dialog = QDialog(window); dialog.setWindowTitle(tr('Meilenstein planen')); form = QFormLayout(dialog)
        title = QLineEdit(); due = QLineEdit(); due.setPlaceholderText('JJJJ-MM-TT'); form.addRow(tr('Meilenstein'), title); form.addRow(tr('Datum'), due)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec_() != QDialog.Accepted: return
        values.update(title=title.text(), due=due.text())
    if workflow in ('handover', 'export'):
        paths = _files(window, record)
        if paths is None: return
        values['paths'] = paths
    payload = flow.project_payload(window.library, record['id'], 'handover' if workflow == 'export' else workflow, **values)
    if workflow == 'export': _export(window, payload)
    elif workflow == 'status':
        text, ok = QInputDialog.getMultiLineText(window, tr('Projektstand vorlesen'), tr('Geprüfter Text für die lokale Stimme'), payload['text'])
        if not ok: return
        payload['text'] = text
        def done(ref):
            from interop_open import open_url
            from interop_data import Registry
            url = Registry(window.library.root.parent).register(ref)
            QTimer.singleShot(0, lambda: open_url(url, window.library.root.parent))
        window.work(tr('Projektstand wird lokal vertont …'), lambda job: flow.spoken_status(payload, window.library.root.parent, job), done)
    else: _send(window, payload, {'agenda': 'meetings.agenda', 'lessons': 'wissen.import', 'milestone': 'inbox.event', 'handover': 'inbox.draft'}[workflow])


def reading(window):
    record = _ready(window); values = flow.reading_list(window.library, record['id'])
    if not values: raise ValueError(tr('Zuerst lesbare Dateien zum Projektmaterial hinzufügen.'))
    dialog = QDialog(window); dialog.setWindowTitle(tr('Lumen Leseliste')); dialog.resize(620, 440); layout = QVBoxLayout(dialog)
    listing = QListWidget(); listing.setAccessibleName(tr('Lesereihenfolge')); listing.setDragDropMode(QAbstractItemView.InternalMove)
    for value in values:
        item = QListWidgetItem(value['title']); item.setData(Qt.UserRole, value); listing.addItem(item)
    layout.addWidget(listing)
    def shift(delta):
        index = listing.currentRow(); target = index+delta
        if 0 <= index < listing.count() and 0 <= target < listing.count():
            item = listing.takeItem(index); listing.insertItem(target, item); listing.setCurrentRow(target)
    def save(): flow.save_reading_list(window.library, record['id'], [listing.item(i).data(Qt.UserRole) for i in range(listing.count())])
    def opened():
        item = listing.currentItem()
        if item:
            save(); from interop_open import launch
            launch('reader', [item.data(Qt.UserRole)['path']], window.library.root.parent)
    layout.addWidget(row(button(tr('Nach oben'), lambda: shift(-1)), button(tr('Nach unten'), lambda: shift(1)), button(tr('Mit Lumen Reader öffnen'), lambda: window.safe(opened))))
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    if dialog.exec_() == QDialog.Accepted: save()


def recent(window):
    record = _ready(window)
    def show(values):
        dialog = QDialog(window); dialog.setWindowTitle(tr('Zuletzt geänderte Projektdateien')); dialog.resize(740, 450); layout = QVBoxLayout(dialog); listing = QListWidget()
        for value in values:
            item = QListWidgetItem(datetime.fromtimestamp(value['modified']).strftime('%d.%m.%Y %H:%M')+' · '+value['path']); item.setData(Qt.UserRole, value['path']); listing.addItem(item)
        layout.addWidget(listing); listing.itemDoubleClicked.connect(lambda item: window.safe(open_path, item.data(Qt.UserRole)))
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons); dialog.exec_()
    window.work(tr('Projektdateien werden geprüft …'), lambda job: flow.recent_files(window.library, record['id'], job), lambda values: QTimer.singleShot(0, lambda: window.safe(show, values)))


def repair(window):
    record = _ready(window)
    missing = [r for r in record.get('resources', []) if r.get('kind') == 'file' and not Path(r['target']).exists()]
    if not missing: raise ValueError(tr('Alle verknüpften Projektdateien sind erreichbar.'))
    title, ok = QInputDialog.getItem(window, tr('Dateiverknüpfung reparieren'), tr('Fehlende Datei oder Ordner'), [r['target'] for r in missing], 0, False)
    if not ok: return
    kind, ok = QInputDialog.getItem(window, tr('Ersatz auswählen'), tr('Art des Ersatzes'), [tr('Datei'), tr('Ordner')], 0, False)
    if not ok: return
    target = (QFileDialog.getOpenFileName(window, tr('Ersatzdatei auswählen'), str(Path.home()))[0] if kind == tr('Datei') else QFileDialog.getExistingDirectory(window, tr('Ersatzordner auswählen'), str(Path.home())))
    if not target: return
    if QMessageBox.question(window, tr('Verknüpfungen reparieren'), tr('Alle Projektverweise auf diese fehlende Datei oder diesen Ordner auf das gewählte Ziel umstellen?')) != QMessageBox.Yes: return
    flow.repair_resource(window.library, record['id'], title, target, all_projects=True); window.focus_record(record['id'])


def context(window, reopen=False):
    record = _ready(window)
    if reopen:
        from interop_open import open_url
        urls = record.get('context', [])
        if not urls: raise ValueError(tr('Zuerst einen Arbeitskontext speichern.'))
        for url in urls: open_url(url, window.library.root.parent)
        return
    values = flow.project_context(window.library, record['id'])
    if not values: raise ValueError(tr('Zuerst Notizen, Dokumente oder Aufgaben mit diesem Projekt verknüpfen.'))
    dialog = QDialog(window); dialog.setWindowTitle(tr('Arbeitskontext speichern')); dialog.resize(640, 440); layout = QVBoxLayout(dialog); listing = QListWidget()
    from interop_graph import app_title
    for value in values:
        item = QListWidgetItem(app_title(value['app'])+' · '+value['title']); item.setData(Qt.UserRole, value['url']); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked if value['url'] in record.get('context', []) else Qt.Unchecked); listing.addItem(item)
    layout.addWidget(listing); buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    if dialog.exec_() == QDialog.Accepted:
        flow.save_context(window.library, record['id'], [listing.item(i).data(Qt.UserRole) for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked])


def install_menu(window):
    menu = window.menuBar().addMenu(tr('Lumen Abläufe'))
    def add(title, callback): menu.addAction(title, lambda: window.safe(callback))
    if window.name == 'household':
        add(tr('Belegdaten prüfen'), lambda: invoice(window))
        for value, title in [('remind', tr('Kündigungsfrist im Kalender planen')), ('until', tr('Garantie / Vertragsende im Kalender planen')), ('cancel', tr('Kündigungsentwurf vorbereiten')), ('support', tr('Supportentwurf mit Belegen vorbereiten')), ('repair', tr('Reparaturprojekt anlegen')), ('handover', tr('Übergabepaket exportieren'))]:
            add(title, lambda value=value: household(window, value))
    else:
        for value, title in [('agenda', tr('Agenda aus offenen Fragen')), ('milestone', tr('Meilenstein im Kalender planen')), ('lessons', tr('Erkenntnisse in Lumen Wissen festhalten')), ('handover', tr('Projektübergabe als Mailentwurf')), ('export', tr('Übergabepaket exportieren')), ('status', tr('Projektstand lokal vorlesen'))]:
            add(title, lambda value=value: project(window, value))
        add(tr('Leseliste ordnen und öffnen'), lambda: reading(window)); add(tr('Zuletzt geänderte Dateien'), lambda: recent(window)); add(tr('Fehlende Dateiverknüpfungen reparieren'), lambda: repair(window))
        add(tr('Arbeitskontext speichern'), lambda: context(window)); add(tr('Arbeitskontext öffnen'), lambda: context(window, True))
    return menu

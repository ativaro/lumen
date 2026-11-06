"""Native review surfaces for household and project handoffs."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout, QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem, QInputDialog, QFileDialog
from lumen_i18n import tr
from tools_ui import open_path
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
    if dialog.exec() != QDialog.Accepted: return None
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
            if dialog.exec() != QDialog.Accepted: return
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












def install_menu(window):
    from PySide6.QtWidgets import QMenu
    menu = QMenu(tr('Passende Aktionen'),window)
    window._workflow_menu=menu
    def add(title, callback): menu.addAction(title, lambda: window.safe(callback))
    if window.name == 'household':
        add(tr('Belegdaten prüfen'), lambda: invoice(window))
        for value, title in [('remind', tr('Kündigungsfrist im Kalender planen')), ('until', tr('Garantie / Vertragsende im Kalender planen')), ('cancel', tr('Kündigungsentwurf vorbereiten')), ('support', tr('Supportentwurf mit Belegen vorbereiten')), ('repair', tr('Reparaturprojekt anlegen')), ('handover', tr('Übergabepaket exportieren'))]:
            add(title, lambda value=value: household(window, value))
    return menu

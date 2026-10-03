"""Native actions for conversations, verified meeting results and radio notes."""
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QInputDialog,
    QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QDockWidget,
    QPlainTextEdit, QWidget, QLabel, QPushButton)
from lumen_i18n import tr
from tools_data import Library
from interop_data import Registry
from interop_dialogs import run_job
import interop_communications as comm


def _send(window, payload, action):
    from interop_ui import reviewed_send
    reviewed_send(window, payload, action)


def _choose(window, title, rows):
    if not rows:
        raise ValueError(tr('Keine passenden lokalen Einträge vorhanden.'))
    labels = [row['title'] + ' · ' + str(index + 1) for index, row in enumerate(rows)]
    value, accepted = QInputDialog.getItem(window, title, tr('Eintrag auswählen'), labels, 0, False)
    return rows[labels.index(value)] if accepted else None


def _checked(window, title, rows, checked=False):
    dialog = QDialog(window)
    dialog.setWindowTitle(title)
    dialog.resize(640, 430)
    layout = QVBoxLayout(dialog)
    listing = QListWidget()
    for value in rows:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        listing.addItem(item)
    layout.addWidget(listing)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec_() != QDialog.Accepted:
        return None
    return [index for index in range(listing.count()) if listing.item(index).checkState() == Qt.Checked]


def _message(window):
    if not window.message:
        raise ValueError(tr('Zuerst eine Nachricht auswählen.'))
    return window.message


def _attachment(window):
    from interop_ui import capture
    _message(window)
    if window.attachments.currentIndex() < 0:
        raise ValueError(tr('Zuerst einen Mailanhang auswählen.'))
    window._interop_focus = window.attachments
    return capture(window)


def show_knowledge_note(window, registry, url):
    note = comm.knowledge_note(registry, url)
    dock = getattr(window, '_knowledge_dock', None)
    if dock is None:
        dock = QDockWidget(tr('Lumen Wissen neben der Besprechung'), window)
        dock.setObjectName('meetingKnowledgeDock')
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        pane = QWidget(dock)
        layout = QVBoxLayout(pane)
        title = QLabel(); title.setWordWrap(True); title.setTextFormat(Qt.PlainText)
        text = QPlainTextEdit(); text.setReadOnly(True)
        text.setAccessibleName(tr('Wissensnotiz zur Besprechung'))
        open_button = QPushButton(tr('In Lumen Wissen öffnen'))
        def open_note():
            from interop_open import open_url
            window.safe(open_url, dock.source_url, window.library.root.parent)
        open_button.clicked.connect(open_note)
        layout.addWidget(title); layout.addWidget(text, 1); layout.addWidget(open_button)
        dock.setWidget(pane); dock.note_title = title; dock.note_text = text
        window.addDockWidget(Qt.RightDockWidgetArea, dock)
        window.resizeDocks([dock], [380], Qt.Horizontal)
        window.entries.currentItemChanged.connect(lambda *_: dock.hide())
        window._knowledge_dock = dock
    dock.source_url = url
    dock.note_title.setText(note['title'])
    dock.note_text.setPlainText(note['text'])
    dock.show(); dock.raise_()


def mail(window, action):
    if action in ('workbench.add', 'wissen.import'):
        _send(window, comm.mail_thread(window.library, _message(window)), action)
    elif action == 'vault':
        message = dict(_message(window))
        payload = run_job(window, tr('Unterhaltung wird lokal verpackt …'), lambda job: comm.archive_thread(window.library, message, job))
        if payload:
            _send(window, payload, 'vault.sources')
    elif action == 'newsletter':
        from interop_ui import capture
        window._interop_focus = window.reader
        payload = capture(window)
        payload['items'] = [dict(kind='source', title=payload['title'], text=payload['text'])]
        _send(window, payload, 'radio.add')
    elif action == 'meeting':
        from interop_ui import capture
        if window.tabs.currentIndex() != 1 or not window.events.currentItem():
            raise ValueError(tr('Zuerst einen Kalendertermin auswählen.'))
        _send(window, capture(window), 'meetings.agenda')
    elif action in ('compare', 'save'):
        payload = _attachment(window)
        if action == 'compare':
            path, _ = QFileDialog.getOpenFileName(window, tr('Vorhandene Fassung vergleichen'), str(Path.home()))
            if not path: return
            result = run_job(window, tr('Anhänge werden lokal verglichen …'), lambda job: comm.compare_attachment(payload, path, job, window.library.root.parent))
            if result:
                QMessageBox.information(window, tr('Anhangvergleich'), (tr('Die Dateien sind inhaltlich identisch.') if result['identical'] else tr('Die Dateien unterscheiden sich. Die vorhandene Fassung bleibt erhalten.')) + '\n' + tr('Neuer Anhang: {0} Bytes · Vorhanden: {1} Bytes', result['incoming_size'], result['existing_size']))
        else:
            path, _ = QFileDialog.getSaveFileName(window, tr('Anhang mit Herkunft ablegen'), str(Path.home() / payload['title']))
            if not path: return
            result = run_job(window, tr('Anhang wird mit Herkunft abgelegt …'), lambda job: comm.save_attachment_with_source(payload, path, job, window.library.root.parent))
            if result: window.status.setText(tr('Anhang mit Verweis auf die Ursprungsmail gespeichert.'))
    elif action == 'support':
        library = Library('household', window.library.root.parent)
        record = _choose(window, tr('Gerät oder Vertrag für Supportanfrage'), library.all())
        if not record: return
        selected = _checked(window, tr('Belege für den Mailentwurf auswählen'), [item['name'] for item in record.get('attachments', [])])
        if selected is None: return
        text, accepted = QInputDialog.getMultiLineText(window, tr('Supportanfrage'), tr('Fehlerbeschreibung oder Anliegen'))
        if accepted:
            _send(window, comm.support_payload(library, record['id'], selected, text), 'inbox.draft')


def meeting(window, action):
    if not window.current:
        raise ValueError(tr('Zuerst eine Besprechung auswählen.'))
    record = window.library.get(window.current)
    if action == 'protocol':
        _send(window, comm.meeting_protocol(window.library, window.current), 'wissen.import')
    elif action in ('tasks', 'decisions', 'radio', 'followup'):
        rows = record.get('results', [])
        indices = [i for i, row in enumerate(rows) if action not in ('tasks', 'decisions') or row['kind'] == ('actions' if action == 'tasks' else 'decisions')]
        selected = _checked(window, tr('Geprüfte Meeting-Ergebnisse auswählen'), [rows[index]['text'] + (' · ' + rows[index]['due'] if rows[index].get('due') else '') for index in indices])
        if selected is None or not selected: return
        selected = [indices[index] for index in selected]
        if action == 'tasks':
            for index in selected:
                _send(window, comm.meeting_result_payload(window.library, window.current, index), 'inbox.task')
        else:
            payload = comm.meeting_protocol(window.library, window.current, results=selected, transcript=False)
            _send(window, payload, {'decisions': 'workbench.add', 'radio': 'radio.add', 'followup': 'inbox.draft'}[action])
    elif action == 'question':
        from interop_ui import capture
        payload = capture(window)
        text, accepted = QInputDialog.getMultiLineText(window, tr('Offene Projektfrage'), tr('Welche Frage bleibt offen?'), payload.get('text', ''))
        if accepted and text.strip():
            payload.update(text=text, paths=[], items=[dict(kind='question', text=text, done=False)])
            _send(window, payload, 'workbench.question')
    elif action == 'document':
        index = window.transcript.currentRow()
        if index < 0: raise ValueError(tr('Zuerst eine Transkriptstelle auswählen.'))
        reader = Library('reader', window.library.root.parent)
        document = _choose(window, tr('Erwähntes Dokument in Lumen Reader'), reader.all())
        if not document: return
        page, accepted = QInputDialog.getInt(window, tr('Erwähnte Buchseite'), tr('Seite'), document.get('page', 0) + 1, 1, max(1, document.get('pages', 1)))
        if accepted:
            comm.link_meeting_document(window.library, window.current, index, document['id'], page - 1)
            window.status.setText(tr('Transkriptstelle und Buchseite sind jetzt miteinander verknüpft.'))
    elif action == 'event':
        import inbox_data
        library = inbox_data.store(window.library.root.parent)
        with library.connect() as db:
            rows = [dict(json.loads(row['data']), account=row['account']) for row in db.execute('SELECT account,data FROM calendar_cache LIMIT 2000')]
        labels = [dict(row, title=row['title'] + ' · ' + row.get('start', '')) for row in rows]
        event = _choose(window, tr('Besprechung einem Kalendertermin zuordnen'), labels)
        if event:
            comm.link_meeting_event(window.library, window.current, event['account'], event['uid'], event['start'])
            window.status.setText(tr('Besprechung mit dem Kalendertermin verknüpft.'))
    elif action == 'knowledge':
        query, accepted = QInputDialog.getText(window, tr('Frühere Wissensnotizen finden'), tr('Thema oder Suchwort'), text=record['title'])
        if not accepted or not query.strip(): return
        registry = Registry(window.library.root.parent)
        from interop_catalog import index_local
        result = run_job(window, tr('Lokale Wissensquellen werden durchsucht …'), lambda job: index_local(registry, job=job))
        if result is None: return
        row = _choose(window, tr('Passende Lumen-Wissensnotiz öffnen'), [item for item in registry.search(query, 200) if item['app'] == 'wissen'])
        if row:
            source = registry.register(comm._meeting_ref(record))
            registry.link(source, row['url'], 'background_note')
            show_knowledge_note(window, registry, row['url'])


def radio(window, action):
    if not window.current:
        raise ValueError(tr('Zuerst eine Radioausgabe auswählen.'))
    record = window.library.get(window.current)
    if action in ('draft', 'export', 'event'):
        payload = comm.radio_bundle(window.library, window.current)
        if action == 'export':
            folder = QFileDialog.getExistingDirectory(window, tr('Audio, Hörskript und Quellen exportieren'), str(Path.home()))
            if not folder: return
            from interop_exports import export_payload
            result = run_job(window, tr('Radioausgabe wird vollständig exportiert …'), lambda job: export_payload(payload, folder, job))
            if result: window.status.setText(tr('Audio, Hörskript und Quellen exportiert: ') + result)
        else:
            payload['paths'] = []
            _send(window, payload, 'inbox.draft' if action == 'draft' else 'inbox.event')
    elif action == 'note':
        position = int(window.player.position)
        text, accepted = QInputDialog.getMultiLineText(window, tr('Hörnotiz mit Zeitmarke'), tr('Dein Gedanke zu dieser Stelle'))
        if accepted and text.strip():
            _send(window, comm.radio_note(window.library, window.current, position, text), 'wissen.import')
    elif action == 'source':
        from interop_radio_audio import audio_source
        section = audio_source(record, int(window.player.position), window.script.toPlainText())
        if section is None and window.tabs.currentIndex() == 1:
            section = comm.radio_script_source(record, window.script.textCursor().position(), window.script.toPlainText())
        source = section or _choose(window, tr('Originalquelle der Radioausgabe öffnen'), record.get('edition_sources') or record.get('sources', []))
        if not source: return
        url = source.get('url', '')
        if url.startswith('lumen://'):
            from interop_open import open_url
            open_url(url, window.library.root.parent)
            return
        original = next((item for item in record.get('sources', []) if item.get('url') == url and item.get('title') == source['title']), source)
        payload = comm._payload(window.library, dict(app='radio', kind='record', id=record['id'], title=record['title']), original.get('text', ''), title=source['title'])
        parsed = urlsplit(url)
        if parsed.scheme in ('http', 'https'):
            from tools_data import fetch_article
            article = run_job(window, tr('Originalartikel wird für Lumen Reader geladen …'), lambda job: fetch_article(url, job))
            if article is None: return
            payload.update(url=url, text=article['text'])
        elif parsed.scheme == 'file' and not parsed.netloc: payload['paths'] = [unquote(parsed.path)]
        if not payload['text'] and not payload.get('paths') and not payload.get('url'):
            raise ValueError(tr('Diese Quelle hat keinen erreichbaren Originaltext.'))
        _send(window, payload, 'reader.import')


def install(window):
    name = getattr(window, 'name', '')
    if name not in ('inbox', 'meetings', 'radio') or hasattr(window, '_communications_menu'):
        return
    from PyQt5.QtWidgets import QMenu
    menu = QMenu(tr('Passende Aktionen'),window)
    window._communications_menu = menu
    choices = {
        'inbox': [(tr('Unterhaltung in Lumen Wissen sichern'), 'wissen.import'), (tr('Unterhaltung Lumen Projekt-Werkbank zuordnen'), 'workbench.add'), (tr('Unterhaltung mit Anhängen an Lumen Vault'), 'vault'), (tr('Newsletter als Quelle für Lumen Persönliches Radio'), 'newsletter'), (tr('Kalendertermin als Meeting-Agenda'), 'meeting'), (tr('Mailanhang mit vorhandener Fassung vergleichen'), 'compare'), (tr('Mailanhang mit Herkunft ablegen'), 'save'), (tr('Supportentwurf mit Haushaltsunterlagen'), 'support')],
        'meetings': [(tr('Protokoll mit Zeitlinks in Lumen Wissen'), 'protocol'), (tr('Geprüfte Aufgaben an Lumen Inbox'), 'tasks'), (tr('Geprüfte Entscheidungen an Lumen Projekt-Werkbank'), 'decisions'), (tr('Geprüfte Ergebnisse für Lumen Persönliches Radio'), 'radio'), (tr('Follow-up-Entwurf in Lumen Inbox'), 'followup'), (tr('Offenen Punkt als Projektfrage übernehmen'), 'question'), (tr('Transkriptstelle mit Lumen Reader verknüpfen'), 'document'), (tr('Besprechung einem Kalendertermin zuordnen'), 'event'), (tr('Frühere Lumen-Wissensnotizen zum Thema'), 'knowledge')],
        'radio': [(tr('Originalquelle der Radioausgabe öffnen'), 'source'), (tr('Hörnotiz mit Zeitmarke in Lumen Wissen'), 'note'), (tr('Hörtermin in Lumen Inbox vorbereiten'), 'event'), (tr('Hörskript mit Quellen als Mailentwurf'), 'draft'), (tr('Audio, Hörskript und Quellen gemeinsam exportieren'), 'export')],
    }
    handler = {'inbox': mail, 'meetings': meeting, 'radio': radio}[name]
    from interop_ui import with_saved
    for label, action in choices[name]:
        menu.addAction(label, lambda checked=False, a=action: window.safe(with_saved, window, lambda: handler(window, a)))

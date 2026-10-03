import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from tools_data import Library
import interop_sources as sources


class SourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'lumen'), 'LUMEN_TOOLS_DATA': str(self.root/'tools')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def window(self, cls):
        window = cls(self.root/'tools')
        def close():
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.addCleanup(close)
        return window

    def capture(self, window):
        from interop_data import validate_payload
        return validate_payload(sources.capture(window))

    def select(self, editor, start, end):
        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)

    def test_files_capture_only_explicit_selection_and_bounds(self):
        path = self.root/'notes.md'
        path.write_text('not read by capture')
        hidden = self.root/'nested'
        hidden.mkdir()
        (hidden/'private.txt').write_text('unselected')
        value = sources.from_paths([path, hidden, path])
        self.assertEqual(value['paths'], [str(path), str(hidden)])
        self.assertEqual(value['text'], '')
        self.assertNotIn('private.txt', json.dumps(value))
        with self.assertRaises(ValueError): sources.from_paths([])
        with self.assertRaises(ValueError): sources.from_paths(['relative.md'])
        with self.assertRaises(ValueError): sources.from_paths([self.root/'missing'])

    def test_reader_quote_and_live_margin_note_exclude_document_copy(self):
        from tools_reader import Reader
        with patch.object(Reader, 'render_page'):
            window = self.window(Reader)
            asset = window.library.asset('book.txt')
            asset.write_text('first and second page')
            key = window.library.create('Book', asset=asset.name, name='book.txt', notes=[dict(id='note', page=2, text='saved quote', note='old note')], page=2, pages=3)
            window.current = key
            window.page_index = 2
            window.text.setPlainText('visible selection and other text')
            window.mode.setCurrentIndex(1)
            self.select(window.text, 0, 17)
            value = self.capture(window)
            self.assertEqual(value['text'], 'visible selection')
            self.assertEqual(value['paths'], [])
            self.assertEqual(value['source']['position'], dict(page=2, start=0, end=17))
            self.select(window.text, 0, 0)
            window.note_id = 'note'
            window.note.setPlainText('edited unsaved margin')
            value = self.capture(window)
            self.assertIn('edited unsaved margin', value['text'])
            self.assertEqual(value['source']['position']['note'], 'note')
            self.assertNotIn('first and second page', value['text'])

    def inbox_message(self):
        from email.message import EmailMessage
        from tools_inbox import Inbox
        window = self.window(Inbox)
        account = window.library.create('Private account', kind='imap', host='secret-host', password='must-not-leak')
        mail = EmailMessage()
        mail['From'] = 'Alice <alice@example.test>'
        mail['To'] = 'bob@example.test'
        mail['Subject'] = 'Selected message'
        mail.set_content('Selected body and unselected remainder')
        mail.add_attachment(b'%PDF-fake-test', maintype='application', subtype='pdf', filename='../../manual.pdf')
        mail.add_attachment(b'private-other-attachment', maintype='text', subtype='plain', filename='private.txt')
        raw = mail.as_bytes()
        with window.library.connect() as db:
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)', (account, 'INBOX', '77', '12', 'thread', 'Selected message', 'Alice', '2026-10-03', 'Selected body and unselected remainder', raw, 0))
        window.refresh()
        window.messages.setCurrentItem(window.messages.topLevelItem(0))
        return window, raw

    def test_inbox_selected_text_excludes_raw_and_account_secrets(self):
        window, raw = self.inbox_message()
        self.select(window.reader, 0, 13)
        value = self.capture(window)
        self.assertEqual(value['text'], 'Selected body')
        self.assertEqual(value['source']['kind'], 'message')
        self.assertEqual(value['source']['locator']['uid'], '12')
        serialized = json.dumps(value)
        for private in ('must-not-leak', 'secret-host', 'private-other-attachment', 'unselected remainder', 'Content-Type'):
            self.assertNotIn(private, serialized)

    def test_selected_attachment_materializes_only_on_worker_and_is_replayable(self):
        from tools_ui import Job
        window, raw = self.inbox_message()
        window._interop_focus = window.attachments
        window.attachments.setCurrentIndex(0)
        value = self.capture(window)
        self.assertEqual(value['paths'], [])
        self.assertEqual(list(window.library.assets.iterdir()), [])
        self.assertNotIn('raw', json.dumps(value))
        job = Job(lambda _: None)
        result = sources.materialize(value, job, self.root/'tools')
        path = Path(result['paths'][0])
        self.assertEqual(path.read_bytes(), b'%PDF-fake-test')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result['items'][0]['title'], 'manual.pdf')
        self.assertEqual(sources.materialize(value, job, self.root/'tools'), result)
        self.assertEqual(len(list(window.library.assets.iterdir())), 1)
        with window.library.connect() as db:
            self.assertEqual(db.execute('SELECT raw FROM messages').fetchone()['raw'], raw)

    def test_attachment_cancellation_removes_partial_copy(self):
        from tools_data import Cancelled
        window, _ = self.inbox_message()
        window._interop_focus = window.attachments
        value = self.capture(window)
        class CancelAtWrite:
            checks = 0
            def check(self):
                self.checks += 1
                if self.checks == 3: raise Cancelled('Abgebrochen')
        with self.assertRaises(Cancelled):
            sources.materialize(value, CancelAtWrite(), self.root/'tools')
        self.assertEqual(list(window.library.assets.iterdir()), [])

    def test_inbox_task_and_event_keep_dates_without_private_calendar_url(self):
        from tools_inbox import Inbox
        window = self.window(Inbox)
        account = window.library.create('Calendar', kind='ics', url='https://calendar.test/private-secret')
        event = dict(uid='event', title='Planung', start='2026-10-04T12:00:00+02:00', end='2026-10-04T13:00:00+02:00', location='Room', description='Discuss next steps', url='https://calendar.test/private-secret')
        with window.library.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?)', ('task', 'Call Alice', '2026-10-05', '', 0))
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)', (account, 'event', json.dumps(event)))
        window.reload_other()
        window.tabs.setCurrentIndex(3)
        window.tasks.setCurrentItem(window.tasks.topLevelItem(0))
        value = self.capture(window)
        self.assertEqual(value['items'][0]['due'], '2026-10-05')
        self.assertEqual(value['source']['kind'], 'task')
        window.tabs.setCurrentIndex(1)
        window.events.setCurrentItem(window.events.topLevelItem(0))
        value = self.capture(window)
        self.assertEqual(value['source']['kind'], 'event')
        self.assertEqual(value['items'][0]['start'], event['start'])
        self.assertNotIn('private-secret', json.dumps(value))

    def test_meeting_selected_transcript_and_action_keep_time_and_edits(self):
        from tools_meetings import Meetings
        window = self.window(Meetings)
        window.library.asset('recording.wav').write_bytes(b'fake audio')
        key = window.library.create('Meeting', recording=dict(asset='recording.wav', name='recording.wav'), duration=30000,
            segments=[dict(start=0, end=1000, text='Unselected private segment'), dict(start=1200, end=5000, text='Send notes')],
            summary='Meeting summary', results=[dict(kind='actions', text='Send the notes', segment=1, done=False, due='2026-10-04')])
        window.focus_record(key)
        window.transcript.item(1, 1).setText('Corrected live transcript')
        window.transcript.selectRow(1)
        value = self.capture(window)
        self.assertIn('Corrected live transcript', value['text'])
        self.assertNotIn('Unselected', value['text'])
        self.assertEqual(value['source']['position']['time'], 1200)
        self.assertEqual(value['paths'], [])
        window.tabs.setCurrentIndex(1)
        window.results.selectRow(0)
        value = self.capture(window)
        self.assertEqual(value['items'][0]['kind'], 'task')
        self.assertEqual(value['items'][0]['due'], '2026-10-04')
        self.assertEqual(value['items'][0]['time'], 1200)

    def test_household_selected_document_excludes_other_attachments(self):
        from tools_household import Household
        window = self.window(Household)
        for name in ('receipt.pdf', 'private.pdf'):
            window.library.asset(name).write_bytes(name.encode())
        key = window.library.create('Device', kind='Gerät', attachments=[dict(asset='receipt.pdf', name='Receipt', text='selected OCR'), dict(asset='private.pdf', name='Private receipt', text='unselected')], notes='whole device notes', serial='private serial')
        window.focus_record(key)
        window.attachments.setCurrentRow(0)
        value = self.capture(window)
        self.assertEqual(value['paths'], [str(window.library.asset('receipt.pdf'))])
        self.assertEqual(value['text'], 'selected OCR')
        self.assertNotIn('private serial', json.dumps(value))
        self.assertNotIn('private.pdf', json.dumps(value))
        self.select(window.notes, 0, 5)
        value = self.capture(window)
        self.assertEqual(value['text'], 'whole')
        self.assertEqual(value['paths'], [])

    def test_agenda_without_recording_captures_live_selected_agenda(self):
        from tools_meetings import Meetings
        window = self.window(Meetings)
        key = window.library.create('Agenda', recording=None, agenda='Saved agenda', segments=[], results=[], summary='')
        window.focus_record(key)
        window.tabs.setCurrentIndex(2)
        window.agenda.setPlainText('Current agenda\nOther material')
        self.select(window.agenda, 0, 14)
        value = self.capture(window)
        self.assertEqual(value['text'], 'Current agenda')
        self.assertEqual(value['paths'], [])
        self.assertEqual(value['items'], [dict(kind='agenda', text='Current agenda')])

    def test_workbench_material_question_and_unsaved_notes(self):
        from tools_workbench import Workbench
        window = self.window(Workbench)
        path = self.root/'project.txt'
        path.write_text('material')
        key = window.library.create('Project', notes='Saved notes', questions=[dict(text='What next?', done=False)], resources=[dict(kind='file', title='Material', target=str(path)), dict(kind='url', title='Web', target='https://example.test/article')])
        window.focus_record(key)
        window.tabs.setCurrentIndex(1)
        window.resources.setCurrentRow(0)
        value = self.capture(window)
        self.assertEqual(value['paths'], [str(path)])
        self.assertNotIn('What next?', value['text'])
        window.resources.setCurrentRow(1)
        self.assertEqual(self.capture(window)['url'], 'https://example.test/article')
        window.tabs.setCurrentIndex(0)
        window.questions.setCurrentRow(0)
        value = self.capture(window)
        self.assertEqual(value['items'], [dict(kind='question', text='What next?', done=False)])
        window.notes.setPlainText('Live edited notes')
        self.select(window.notes, 0, 11)
        self.assertEqual(self.capture(window)['text'], 'Live edited')

    def test_radio_source_script_excerpt_and_playback_position(self):
        from tools_radio import Radio
        window = self.window(Radio)
        window.library.asset('edition.wav').write_bytes(b'fake audio')
        key = window.library.create('Edition', sources=[dict(title='Article', text='Article body', url='https://example.test/article', selected=True)], script='First paragraph. Second paragraph.', minutes=5, edition_sources=[dict(title='Article', url='https://example.test/article')], audio='edition.wav', duration=40000)
        window.focus_record(key)
        window.source_text.setPlainText('Edited article body')
        value = self.capture(window)
        self.assertEqual(value['text'], 'Edited article body')
        self.assertEqual(value['url'], 'https://example.test/article')
        from interop_parts import capture_part
        self.assertEqual(value['source']['position']['part'], capture_part(window, 'source', 0))
        window.tabs.setCurrentIndex(1)
        window.player.position = 12500
        self.select(window.script, 0, 16)
        value = self.capture(window)
        self.assertEqual(value['text'], 'First paragraph.')
        self.assertEqual(value['paths'], [])
        self.assertEqual(value['source']['position']['time'], 12500)

    def test_vault_and_sound_capture_only_useful_settings(self):
        from tools_vault import Vault
        from tools_sound import Sound
        vault = self.window(Vault)
        key = vault.library.create('Backup', sources=[str(self.root)], repository='/secret/repository', password='secret-password')
        vault.focus_record(key)
        value = self.capture(vault)
        self.assertEqual(value['paths'], [])
        self.assertNotIn('secret', json.dumps(value))
        vault.sources.setCurrentRow(0)
        vault._interop_focus = vault.sources
        self.assertEqual(self.capture(vault)['paths'], [str(self.root)])
        with patch.object(Sound, 'poll'):
            sound = self.window(Sound)
        sound.timer.stop()
        sound.library.update(sound.current, rules={'reader': dict(title='Lumen Reader', volume=80, mute=False, sink='headphones', role='music')}, arbitrary_private='excluded')
        sound.load_rules()
        sound.rules.setCurrentItem(sound.rules.topLevelItem(0))
        value = self.capture(sound)
        self.assertEqual(value['items'][0]['title'], 'Lumen Reader')
        self.assertNotIn('arbitrary_private', json.dumps(value))

    def test_wissen_live_note_selection_and_collection_keep_notebook_locator(self):
        from tools_wissen import Wissen
        from wissen_data import Notebook
        with patch.object(Wissen, 'initialize'):
            window = self.window(Wissen)
            QCoreApplication.processEvents()
        window.poll_timer.stop()
        window.book = Notebook(window.store, self.root/'notebook', create=True)
        note = window.book.create('Selected note', 'Original notebook content #topic')
        other = window.book.create('Other note', 'Another topic #topic')
        window.notes = {value['path']: value for value in (note, other)}
        window.show_note(note)
        before = (window.book.root/note['path']).read_text()
        window.editor.setPlainText('Live unsaved words\nUnselected remainder')
        self.select(window.editor, 0, 18)
        window.draft_timer.stop()
        window.autosave_timer.stop()
        value = self.capture(window)
        self.assertEqual(value['text'], 'Live unsaved words')
        self.assertEqual(value['paths'], [])
        self.assertEqual(value['source']['locator']['root'], str(window.book.root))
        self.assertEqual((window.book.root/note['path']).read_text(), before)
        window._interop_focus = window.collections
        value = self.capture(window)
        self.assertEqual(value['source']['kind'], 'collection')
        self.assertEqual(set(value['paths']), {str(window.book.root/value['path']) for value in (note, other)})
        window.dirty = False

    def test_every_payload_passes_registry_bounds_and_roundtrips_reference(self):
        from interop_data import Registry, validate_payload
        path = self.root/'selected.txt'
        path.write_text('content')
        value = sources.from_paths([path])
        self.assertEqual(validate_payload(value), value)
        registry = Registry(self.root/'tools')
        ref = dict(app='reader', kind='record', id='book', title='Book', position=dict(page=4, start=5, end=9))
        self.assertEqual(registry.resolve(registry.register(ref)), ref)
        with self.assertRaises(ValueError):
            sources._bounded(dict(value, text='a' * 120001))
        with self.assertRaises(ValueError):
            sources._bounded(dict(value, items=[{}] * 1001))


if __name__ == '__main__':
    unittest.main()

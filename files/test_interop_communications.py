import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from tools_ui import Job
from tools_data import Library, Cancelled
from interop_data import Registry
import interop_communications as comm


class CommunicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.job = Job(lambda _: None)

    def mail(self):
        import inbox_data
        library = inbox_data.store(self.root)
        account = library.create('Mailbox', kind='imap', password='account-secret', host='secret-server')
        other = library.create('Other mailbox', kind='imap')
        with library.connect() as db:
            for owner, uid, body in ((account, '1', 'First text'), (account, '2', 'Second text'), (other, '3', 'Other account secret')):
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)', (owner, 'INBOX', '1', uid, 'thread', 'Conversation', 'Sender '+uid, 'Sat, 03 Oct 2026 1'+uid+':00:00 +0200', body, ('Subject: Original '+uid+'\r\n\r\nAttachment bytes '+uid).encode(), 0))
            message = dict(db.execute('SELECT * FROM messages WHERE account=? AND uid=?', (account, '2')).fetchone())
        return library, message

    def test_conversation_preserves_order_and_per_message_links_without_other_accounts(self):
        library, message = self.mail()
        payload = comm.mail_thread(library, message)
        self.assertLess(payload['text'].index('First text'), payload['text'].index('Second text'))
        self.assertEqual(len(payload['items']), 2)
        registry = Registry(self.root)
        self.assertEqual([registry.resolve(item['url'])['locator']['uid'] for item in payload['items']], ['1', '2'])
        for private in ('Other account secret', 'account-secret', 'secret-server', 'Attachment bytes'):
            self.assertNotIn(private, json.dumps(payload))

    def test_conversation_archive_contains_only_selected_thread_and_cleans_cancel(self):
        library, message = self.mail()
        payload = comm.archive_thread(library, message, self.job)
        path = Path(payload['paths'][0])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), {'001.eml', '002.eml', 'manifest.json'})
            self.assertIn(b'Attachment bytes 1', archive.read('001.eml'))
        self.assertNotIn('Attachment bytes', json.dumps(payload))
        class Cancel:
            count = 0
            def check(self):
                self.count += 1
                if self.count > 2: raise Cancelled('Abgebrochen')
        with self.assertRaises(Cancelled): comm.archive_thread(library, message, Cancel())
        self.assertEqual(list(library.assets.glob('conversation-*')), [path])

    def test_attachment_compare_and_saved_provenance_do_not_overwrite_existing_file(self):
        path = self.root/'incoming.pdf'
        path.write_bytes(b'new attachment')
        existing = self.root/'existing.pdf'
        existing.write_bytes(b'old attachment')
        source = dict(app='inbox', kind='message', id='message', title='Mail')
        payload = dict(title='Attachment', source=source, paths=[str(path)], items=[])
        result = comm.compare_attachment(payload, existing, self.job, self.root)
        self.assertFalse(result['identical'])
        self.assertEqual(existing.read_bytes(), b'old attachment')
        with self.assertRaises(FileExistsError): comm.save_attachment_with_source(payload, existing, self.job, self.root)
        output = self.root/'new.pdf'
        comm.save_attachment_with_source(payload, output, self.job, self.root)
        registry = Registry(self.root)
        url = registry.register(source)
        self.assertEqual(registry.related(url)[0]['path'], str(output))
        self.assertEqual(output.read_bytes(), b'new attachment')

    def meeting(self):
        library = Library('meetings', self.root)
        key = library.create('Planning', recording=None, duration=30000, agenda='Agenda', summary='Unselected summary',
            segments=[dict(start=1000, end=3000, text='Decision evidence'), dict(start=4000, end=6000, text='Task evidence')],
            results=[dict(kind='decisions', text='Agreed decision', segment=0, done=False), dict(kind='actions', text='Send the plan', segment=1, done=False, due='2026-10-05', source_url='preserved-source')])
        return library, key

    def test_protocol_time_links_and_selected_task_are_precise(self):
        library, key = self.meeting()
        registry = Registry(self.root)
        payload = comm.meeting_protocol(library, key)
        self.assertIn('00:00:01', payload['text'])
        self.assertIn('?time=1000', payload['text'])
        task = comm.meeting_result_payload(library, key, 1)
        self.assertEqual(task['items'][0]['due'], '2026-10-05')
        self.assertEqual(registry.resolve(task['source_url'])['position']['time'], 4000)
        selected = comm.meeting_protocol(library, key, results=[0], transcript=False)
        self.assertIn('Agreed decision', selected['text'])
        for excluded in ('Unselected summary', 'Send the plan', 'Task evidence'):
            self.assertNotIn(excluded, selected['text'])

    def test_meeting_document_and_calendar_links_roundtrip_exact_objects(self):
        import inbox_data
        library, key = self.meeting()
        reader = Library('reader', self.root)
        reader.asset('book.pdf').write_bytes(b'pdf')
        document = reader.create('Manual', asset='book.pdf', pages=7)
        url = comm.link_meeting_document(library, key, 1, document, 4)
        self.assertEqual(Registry(self.root).resolve(url)['position']['page'], 4)
        inbox = inbox_data.store(self.root)
        account = inbox.create('Calendar', kind='ics', url='secret-calendar-url')
        event = dict(uid='event', title='Planning event', start='2026-10-05T12:00:00+02:00')
        with inbox.connect() as db:
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)', (account, 'event', json.dumps(event)))
        url = comm.link_meeting_event(library, key, account, event['uid'], event['start'])
        self.assertEqual(library.get(key)['calendar_event'], url)
        self.assertNotIn('secret-calendar-url', json.dumps(Registry(self.root).resolve(url)))

    def test_support_bundle_only_includes_selected_device_documents(self):
        library = Library('household', self.root)
        for asset in ('receipt.pdf', 'private.pdf'): library.asset(asset).write_bytes(asset.encode())
        key = library.create('Printer', serial='serial-1', model='Model', attachments=[dict(name='Receipt', asset='receipt.pdf'), dict(name='Private', asset='private.pdf')])
        payload = comm.support_payload(library, key, [0], 'Paper feed does not work')
        self.assertEqual(payload['paths'], [str(library.asset('receipt.pdf'))])
        self.assertIn('serial-1', payload['text'])
        self.assertNotIn('private.pdf', json.dumps(payload))

    def test_radio_sections_notes_and_portable_bundle_keep_provenance(self):
        from tools_radio import radio_result
        from interop_exports import export_payload
        library = Library('radio', self.root)
        values = radio_result(json.dumps(dict(sections=[dict(source=0, text='First 🐟 section.'), dict(source=1, text='Second section.')])), [dict(title='First', url='https://one.test'), dict(title='Second', url='https://two.test')])
        key = library.create('Edition', **values, audio='audio.wav', duration=20000)
        library.asset('audio.wav').write_bytes(b'fake audio')
        record = library.get(key)
        second = values['edition_sections'][1]
        self.assertEqual(comm.radio_script_source(record, second['start'], values['script'])['url'], 'https://two.test')
        self.assertIsNone(comm.radio_script_source(record, second['start'], 'Edited ' + values['script']))
        note = comm.radio_note(library, key, 12000, 'A thought')
        self.assertEqual(Registry(self.root).resolve(note['source_url'])['position']['time'], 12000)
        bundle = comm.radio_bundle(library, key)
        target = Path(export_payload(bundle, self.root, self.job))
        self.assertTrue((target/'document.md').is_file())
        self.assertIn('https://two.test', (target/'document.md').read_text())
        self.assertEqual(len(list((target/'files').iterdir())), 1)

    def test_native_communications_menu_flushes_edits_and_preserves_result_metadata(self):
        from tools_meetings import Meetings
        from tools_radio import Radio
        from tools_inbox import Inbox
        import interop_ui
        library, key = self.meeting()
        with patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'state')}):
            windows = [Meetings(self.root), Radio(self.root), Inbox(self.root)]
            try:
                meeting = windows[0]
                meeting.focus_record(key)
                meeting.results.item(1, 1).setText('Edited task')
                for window in windows:
                    comm.install_communications_menu(window)
                    self.assertGreater(len(window._communications_menu.actions()), 4)
                with patch.object(interop_ui, 'reviewed_send') as send:
                    meeting._communications_menu.actions()[0].trigger()
                    payload = send.call_args.args[1]
                    self.assertIn('Edited task', payload['text'])
                task = library.get(key)['results'][1]
                self.assertEqual(task['due'], '2026-10-05')
                self.assertEqual(task['source_url'], 'preserved-source')
            finally:
                for window in windows:
                    window.close()
                    window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_meeting_shows_selected_knowledge_note_in_read_only_side_panel(self):
        from tools_meetings import Meetings
        from interop_communication_ui import show_knowledge_note
        library, key = self.meeting()
        notebook = self.root/'notebook'
        notebook.mkdir()
        path = notebook/'context.md'
        path.write_text('# Earlier planning\n\nPrior decision without leaving the meeting.')
        registry = Registry(self.root)
        url = registry.register(dict(app='wissen', kind='note', id='context.md', title='Earlier planning', path=str(path), locator=dict(root=str(notebook))))
        with patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'state')}):
            window = Meetings(self.root)
            try:
                window.focus_record(key)
                window.show()
                show_knowledge_note(window, registry, url)
                self.app.processEvents()
                dock = window._knowledge_dock
                self.assertTrue(dock.isVisible())
                self.assertTrue(dock.note_text.isReadOnly())
                self.assertIn('Prior decision', dock.note_text.toPlainText())
                self.assertEqual(window.current, key)
                path.unlink()
                path.symlink_to(self.root/'other.md')
                (self.root/'other.md').write_text('Unselected secret')
                with self.assertRaises(OSError): comm.knowledge_note(registry, url)
            finally:
                window.close(); window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_radio_playback_source_fetches_exact_article_for_reader(self):
        from tools_radio import Radio, radio_result
        import interop_communication_ui as ui
        import hashlib
        library = Library('radio', self.root)
        values = radio_result(json.dumps(dict(sections=[dict(source=0, text='First.'), dict(source=1, text='Second.')])),
            [dict(title='One', url='https://one.test'), dict(title='Two', url='https://two.test')])
        key = library.create('Edition', **values, audio='audio.wav', duration=20000,
            audio_hash=hashlib.sha256(values['script'].encode()).hexdigest(), audio_source_hash=values['edition_script_hash'], audio_source_asset='audio.wav',
            audio_source_timeline=[dict(start=0, end=7000, title='One', url='https://one.test'), dict(start=7000, end=20000, title='Two', url='https://two.test')])
        with patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'state')}):
            window = Radio(self.root)
            try:
                window.focus_record(key)
                window.player.position = 12000
                with patch.object(ui, '_choose', side_effect=AssertionError('Must use playback time')), patch.object(ui, '_send') as send, patch('tools_data.fetch_article', return_value=dict(text='Original full article')) as fetch, patch.object(ui, 'run_job', side_effect=lambda w, text, fn: fn(self.job)):
                    ui.radio(window, 'source')
                fetch.assert_called_once_with('https://two.test', self.job)
                self.assertEqual(send.call_args.args[1]['text'], 'Original full article')
                self.assertEqual(send.call_args.args[2], 'reader.import')
                note = comm.radio_note(library, key, 12000, 'Listening thought')
                self.assertEqual([item['url'] for item in note['items']], ['https://two.test'])
            finally:
                window.close(); window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__': unittest.main()

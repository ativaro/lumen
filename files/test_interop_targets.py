"""Transfers use only synthetic local state; no provider or personal data."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from lumen_store import Store
from tools_data import Cancelled, Library
from tools_ui import Job
import interop_targets as targets
import wissen_data
import inbox_data


class TargetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.tools = self.root/'tools'
        self.store = Store(self.root/'state'); wissen_data.activate(self.store)
        self.job = Job(lambda _: None)
        self.source = 'lumen://object/'+'a'*32
        self.payload = dict(title='Quelle', text='Ein überprüfbarer Gedanke.', paths=[],
                            source=dict(app='wissen', id='note.md', kind='note', title='Quelle'),
                            source_url=self.source)

    def apply(self, action, payload=None, **choice):
        return targets.apply(action, payload or self.payload,
                             dict(dict(title='Ziel', mode='copy', token='test-token'), **choice),
                             self.job, root=self.tools, store=self.store)

    def test_legacy_wissen_copy_cannot_write_after_server_switch(self):
        source=self.root/'receipt.txt';source.write_text('Ein Beleg')
        book=wissen_data.Notebook(self.store);before=book.scan()['notes']
        with self.assertRaises(ValueError):self.apply('wissen.import',dict(self.payload,paths=[str(source)]))
        self.assertEqual(book.scan()['notes'],before);self.assertEqual(source.read_text(),'Ein Beleg')

    def test_workbench_copy_add_and_link_preserve_original(self):
        source = self.root/'plan.txt'; source.write_text('Version eins')
        payload = dict(self.payload, paths=[str(source)])
        result = self.apply('workbench.add', payload)
        library = Library('workbench', self.tools); project = library.get(result['id'])
        copy = Path(project['resources'][0]['target'])
        self.assertNotEqual(copy, source); self.assertEqual(copy.read_text(), source.read_text())
        source.write_text('Version zwei'); self.assertEqual(copy.read_text(), 'Version eins')
        addition = dict(self.payload, text='Weitere Notiz', paths=[str(source)])
        choice = dict(id=result['id'], title='ignored', mode='link', token='second')
        targets.apply('workbench.add', addition, choice, self.job, self.tools, self.store)
        targets.apply('workbench.add', addition, choice, self.job, self.tools, self.store)
        project = library.get(result['id'])
        self.assertEqual(project['title'], 'Ziel'); self.assertEqual(len(project['resources']), 2)
        self.assertEqual(project['resources'][1]['target'], str(source))
        self.assertEqual(project['interop_sources'], [self.source])

    def test_household_and_radio_store_real_content(self):
        source = self.root/'manual.txt'; source.write_text('Handbuchtext')
        result = self.apply('household.add', dict(self.payload, paths=[str(source)]))
        library = Library('household', self.tools); record = library.get(result['id'])
        self.assertEqual(library.asset(record['attachments'][0]['asset']).read_text(), 'Handbuchtext')
        result = self.apply('radio.add')
        record = Library('radio', self.tools).get(result['id'])
        self.assertEqual(record['sources'][0]['text'], self.payload['text'])
        self.assertEqual(record['sources'][0]['url'], self.source)

    def test_cancel_after_first_copy_leaves_no_partial_files_or_record(self):
        first = self.root/'one.txt'; second = self.root/'two.txt'
        first.write_text('one'); second.write_text('two')
        calls = []
        def cancel():
            calls.append(1)
            if len(calls) == 4: raise Cancelled()
        self.job.check = cancel
        with self.assertRaises(Cancelled): self.apply('household.add', dict(self.payload, paths=[str(first), str(second)]))
        library = Library('household', self.tools)
        self.assertEqual(library.all(), []); self.assertEqual(list(library.assets.iterdir()), [])

    def test_choices_do_not_return_account_credentials(self):
        library = Library('inbox', self.tools)
        key = library.create('Mailbox', kind='imap', password='DO-NOT-EXPORT', username='private')
        library.create('Calendar', kind='caldav', password='DO-NOT-EXPORT')
        self.assertEqual(targets.choices('inbox.draft', self.tools), [dict(id=key, title='Mailbox')])
        self.assertNotIn('DO-NOT-EXPORT', json.dumps(targets.choices('inbox.event', self.tools)))

    def test_invalid_modes_paths_and_reused_token_do_not_mutate(self):
        with self.assertRaises(ValueError): self.apply('household.add', mode='unsupported')
        with self.assertRaises(ValueError): self.apply('workbench.add', dict(self.payload, paths=['relative.txt']))
        self.apply('workbench.add')
        with self.assertRaises(ValueError): self.apply('workbench.add', dict(self.payload, text='different'))
        self.assertEqual(len(Library('workbench', self.tools).all()), 1)

    def test_reader_copies_a_real_document_with_source_and_no_network(self):
        document = self.root/'article.txt'; document.write_text('Eine lesbare Geschichte.')
        result = self.apply('reader.import', dict(self.payload, text='', paths=[str(document)]))
        library = Library('reader', self.tools); record = library.get(result['id'])
        self.assertEqual(record['source'], self.source); self.assertGreater(record['pages'], 0)
        self.assertEqual(record['interop_sources'], [self.source])
        self.assertEqual(self.apply('reader.import', dict(self.payload, text='', paths=[str(document)])), result)
        self.assertEqual(len(library.all()), 1)

    def test_meeting_audio_and_agenda_only_record_are_complete(self):
        import wave
        path = self.root/'sample.wav'
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b'\0\0'*8000)
        result = self.apply('meetings.import', dict(self.payload, paths=[str(path)]))
        record = Library('meetings', self.tools).get(result['id'])
        self.assertEqual(record['duration'], 1000); self.assertEqual(record['segments'], [])
        agenda = self.apply('meetings.agenda', token='agenda')
        record = Library('meetings', self.tools).get(agenda['id'])
        self.assertIn(self.payload['text'], record['agenda']); self.assertFalse(record.get('recording'))

    def test_inbox_draft_task_and_calendar_proposal_stay_local_and_replay(self):
        library = inbox_data.store(self.tools)
        mail = library.create('Mail', kind='imap'); calendar = library.create('Calendar', kind='caldav')
        attachment = self.root/'document.txt'; attachment.write_text('Anhang')
        payload = dict(self.payload, paths=[str(attachment)])
        with patch('inbox_data.send_draft', side_effect=AssertionError('No automatic sending')):
            draft = self.apply('inbox.draft', payload, id=mail)
            self.assertEqual(draft, self.apply('inbox.draft', payload, id=mail))
        with library.connect() as db:
            row = db.execute('SELECT * FROM drafts').fetchone(); values = json.loads(row['data'])
        self.assertEqual(row['status'], 'draft'); self.assertEqual(values['to'], '')
        self.assertTrue(values['formatted'])
        self.assertEqual(library.asset(values['attachments'][0]['asset']).read_text(), 'Anhang')
        inbox_data.save_draft(library, mail, dict(to='reader@example.invalid', subject='edited', body='edited'), draft['id'])
        with library.connect() as db: saved = json.loads(db.execute('SELECT data FROM drafts').fetchone()[0])
        self.assertEqual(saved['attachments'], values['attachments'])
        self.assertTrue(saved['formatted'])
        task = self.apply('inbox.task', due='2026-11-01', token='task')
        with library.connect() as db: record = db.execute('SELECT * FROM tasks WHERE id=?', (task['id'],)).fetchone()
        self.assertEqual(record['due'], '2026-11-01'); self.assertEqual(record['source'], self.source)
        with library.connect() as db:detail=db.execute('SELECT body FROM interop_task_details WHERE task=?',(task['id'],)).fetchone()[0]
        self.assertIn(self.payload['text'],detail);self.assertIn(self.source,detail)
        event = self.apply('inbox.event', id=calendar, due='2026-11-02', token='event')
        proposal = targets.event_proposal(library, event['id'])
        self.assertEqual(proposal['account'], calendar); self.assertIn(self.source, proposal['description'])
        self.assertTrue(proposal['start'].startswith('2026-11-02T'))
        with library.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM calendar_cache').fetchone()[0], 0)

    def test_existing_contract_and_project_structured_questions_are_preserved(self):
        household = Library('household', self.tools); key = household.create('Internet', kind='Vertrag', notes='Vorhanden', attachments=[])
        self.apply('household.add', id=key)
        self.assertEqual(household.get(key)['kind'], 'Vertrag')
        payload = dict(self.payload, items=[dict(kind='question', text='Offene Frage?', done=False), dict(kind='task', text='Prüfen', due='2026-11-03')])
        result = self.apply('workbench.add', payload)
        questions = Library('workbench', self.tools).get(result['id'])['questions']
        self.assertEqual(len(questions), 2); self.assertIn('2026-11-03', questions[1]['text'])

    def test_markdown_note_import_requires_server_capture_instead_of_local_notebook(self):
        path=self.root/'article.md';path.write_text('# Original\n\n## Abschnitt\n\nWichtig.')
        with self.assertRaises(ValueError):self.apply('wissen.import',dict(self.payload,text='',paths=[str(path)]))
        self.assertEqual(path.read_text(),'# Original\n\n## Abschnitt\n\nWichtig.')
        self.assertEqual(wissen_data.Notebook(self.store).scan()['notes'],[])

    def test_agenda_only_meeting_opens_and_preserves_edits(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QCoreApplication, QEvent
        from tools_meetings import Meetings
        app = QApplication.instance() or QApplication([])
        result = self.apply('meetings.agenda')
        window = Meetings(self.tools)
        try:
            window.focus_record(result['id'])
            self.assertIn(self.payload['text'], window.agenda.toPlainText())
            window.agenda.setPlainText('Geprüfte Agenda'); window.save()
            self.assertEqual(window.library.get(result['id'])['agenda'], 'Geprüfte Agenda')
        finally:
            window.close(); window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_concurrent_replay_creates_one_destination(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.apply, 'workbench.add') for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(results[0], results[1]); self.assertEqual(len(Library('workbench', self.tools).all()), 1)

    def test_missing_or_invalid_draft_attachment_never_reaches_mail_transport(self):
        library = inbox_data.store(self.tools)
        account = library.create('Test', kind='imap', host='localhost', port=993, tls='ssl', smtp_host='localhost', smtp_port=465, smtp_tls='ssl', username='local', address='me@example.invalid')
        attachment = self.root/'part.txt'; attachment.write_bytes(b'attachment-bytes')
        result = self.apply('inbox.draft', dict(self.payload, paths=[str(attachment)]), id=account)
        inbox_data.save_draft(library, account, dict(to='recipient@example.invalid', subject='Review', body='Approved locally'), result['id'])
        with patch('inbox_data.smtplib.SMTP_SSL') as smtp, patch('inbox_data.secret', return_value='fake'), patch('inbox_data.verify_peer'):
            smtp.return_value.send_message.return_value = {}
            inbox_data.send_draft(library, result['id'], self.job)
            message = smtp.return_value.send_message.call_args.args[0]
            parts = list(message.iter_attachments())
            self.assertEqual(parts[0].get_filename(), 'part.txt'); self.assertEqual(parts[0].get_payload(decode=True), b'attachment-bytes')
        with self.assertRaises(ValueError): inbox_data.draft_attachments(library, [dict(asset='../private', name='escape')])


if __name__ == '__main__': unittest.main()

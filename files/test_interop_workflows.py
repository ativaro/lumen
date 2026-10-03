import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools_data import Library, Cancelled
from tools_ui import Job
from interop_data import Registry
import inbox_data
import interop_workflows as flow


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.tools = self.root/'tools'; self.job = Job(lambda _: None)
        self.house = Library('household', self.tools)
        self.device = self.house.create('Waschmaschine', kind='Gerät', provider='Hersteller', model='Modell 1', serial='SN-123', since='2026-01-02', remind='2026-12-01', notes='Pumpe prüfen.', attachments=[])
        self.projects = Library('workbench', self.tools)
        self.project = self.projects.create('Reparatur', notes='Pumpentausch prüfen.', questions=[dict(text='Welche Pumpe?', done=False), dict(text='Garantie geklärt', done=True)], resources=[])

    def test_invoice_candidates_are_only_extracted_labeled_fields(self):
        self.assertEqual(flow.invoice_candidates('Händler: Beispiel AG\nRechnungsdatum: 02.01.2026\nModell: Test 4'), dict(provider='Beispiel AG', since='2026-01-02', model='Test 4'))
        self.assertEqual(flow.invoice_candidates('Ohne eindeutige Felder'), {})

    def test_support_cancel_repair_and_deadline_payloads_keep_context(self):
        support = flow.household_payload(self.house, self.device, 'support', text='Motor startet nicht.')
        self.assertIn('SN-123', support['text']); self.assertIn('Motor startet nicht.', support['text']); self.assertEqual(support['paths'], [])
        cancel = flow.household_payload(self.house, self.device, 'cancel')
        self.assertIn('kündige', cancel['text']); self.assertIn('Modell 1', cancel['text'])
        repair = flow.household_payload(self.house, self.device, 'repair')
        self.assertIn('Waschmaschine', repair['title']); self.assertIn('Pumpe prüfen.', repair['text'])
        deadline = flow.deadline_payload(self.house, self.device)
        self.assertTrue(deadline['items'][0]['start'].startswith('2026-12-01T09:00'))
        self.assertIn('[Lumen-Frist:'+self.device+':remind]', deadline['text'])

    def test_deadline_update_matches_only_same_account_and_exact_marker(self):
        inbox = inbox_data.store(self.tools); account = inbox.create('Calendar', kind='caldav')
        other = inbox.create('Other', kind='caldav'); payload = flow.deadline_payload(self.house, self.device)
        marker = '[Lumen-Frist:'+self.device+':remind]'
        event = dict(uid='old', description=marker, url='https://example.invalid/event.ics', etag='"v1"', ics='BEGIN:VCALENDAR')
        with inbox.connect() as db:
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)', (other, 'other', json.dumps(event)))
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)', (account, 'old', json.dumps(event)))
        result = flow.prepare_event_update(inbox, dict(account=account, description=payload['text']), payload['items'][0])
        self.assertEqual(result['uid'], 'old'); self.assertEqual(result['etag'], '"v1"'); self.assertEqual(result['account'], account)
        with inbox.connect() as db: db.execute('INSERT INTO calendar_cache VALUES (?,?,?)', (account, 'duplicate', json.dumps(dict(event, uid='duplicate'))))
        with self.assertRaises(ValueError): flow.prepare_event_update(inbox, dict(account=account, description=payload['text']), payload['items'][0])

    def test_pending_deadline_proposal_is_reused_without_network(self):
        inbox = inbox_data.store(self.tools); payload = flow.deadline_payload(self.house, self.device)
        values = dict(account='calendar', description=payload['text'])
        with inbox.connect() as db:
            db.execute('CREATE TABLE interop_event_proposals(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            db.execute('INSERT INTO interop_event_proposals VALUES (?,?)', ('pending', json.dumps(values)))
        self.assertEqual(flow.prepare_event_update(inbox, values, payload['items'][0])['proposal_id'], 'pending')

    def test_project_agenda_lessons_milestone_handover_and_spoken_status(self):
        agenda = flow.project_payload(self.projects, self.project, 'agenda')
        self.assertIn('Welche Pumpe?', agenda['text']); self.assertNotIn('Garantie geklärt', agenda['text'])
        lessons = flow.project_payload(self.projects, self.project, 'lessons', text='Prüfung vor Bestellung.')
        self.assertEqual(lessons['text'], 'Prüfung vor Bestellung.')
        milestone = flow.project_payload(self.projects, self.project, 'milestone', title='Abnahme', due='2026-12-02')
        self.assertEqual(milestone['items'][0]['title'], 'Abnahme'); self.assertTrue(milestone['items'][0]['start'].startswith('2026-12-02'))
        status = flow.project_payload(self.projects, self.project, 'status')
        self.assertIn('Garantie geklärt', status['text']); self.assertIn('Welche Pumpe?', status['text'])
        self.assertEqual(flow.project_payload(self.projects, self.project, 'handover')['source']['id'], self.project)

    def test_handover_payload_contains_selected_files_and_provenance_for_shared_exporter(self):
        source = self.root/'manual.txt'; source.write_text('Manual')
        payload = flow.household_payload(self.house, self.device, 'handover', paths=[str(source)])
        self.assertEqual(payload['paths'], [str(source)])
        self.assertEqual(payload['items'][0]['title'], 'manual.txt')
        self.assertEqual(Registry(self.tools).resolve(payload['source_url'])['id'], self.device)
        self.assertEqual(source.read_text(), 'Manual')

    def test_recent_files_reading_order_and_link_repair(self):
        folder = self.root/'project'; folder.mkdir(); old = folder/'old.pdf'; old.write_bytes(b'pdf')
        second = folder/'second.txt'; second.write_text('read')
        self.projects.update(self.project, resources=[dict(kind='file', target=str(old), title='Old'), dict(kind='file', target=str(second), title='Second')])
        reading = flow.reading_list(self.projects, self.project)
        self.assertEqual([item['path'] for item in reading], [str(old), str(second)])
        flow.save_reading_list(self.projects, self.project, list(reversed(reading)))
        self.assertEqual(flow.reading_list(self.projects, self.project)[0]['path'], str(second))
        self.assertEqual(len(flow.recent_files(self.projects, self.project, self.job)), 2)
        new = folder/'new.pdf'; old.rename(new)
        registry = Registry(self.tools); url = registry.register(dict(app='files', kind='file', id=str(old), title='Old', path=str(old)))
        flow.repair_resource(self.projects, self.project, str(old), str(new))
        self.assertEqual(self.projects.get(self.project)['resources'][0]['target'], str(new))
        self.assertEqual(registry.resolve(url)['path'], str(new))

    def test_spoken_status_has_real_audio_asset_script_and_source_relation(self):
        payload = flow.project_payload(self.projects, self.project, 'status')
        def voice(text, library, job):
            library.asset('status.wav').write_bytes(b'local-audio')
            return dict(audio='status.wav', duration=1000)
        with patch('tools_data.synthesize', side_effect=voice): result = flow.spoken_status(payload, self.tools, self.job)
        library = Library('radio', self.tools); record = library.get(result['id'])
        self.assertEqual(record['script'], payload['text']); self.assertEqual(library.asset(record['audio']).read_bytes(), b'local-audio')
        self.assertEqual(Registry(self.tools).related(payload['source_url'])[0]['app'], 'radio')

    def test_native_project_and_household_workflow_menus_send_reviewed_payloads(self):
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QCoreApplication, QEvent
        from tools_household import Household
        from tools_workbench import Workbench
        app = QApplication.instance() or QApplication([])
        windows = [Household(self.tools), Workbench(self.tools)]
        try:
            windows[0].focus_record(self.device); windows[1].focus_record(self.project)
            with patch('interop_ui.reviewed_send') as send:
                for window, label, action in [(windows[0], 'Kündigungsfrist im Kalender planen', 'inbox.event'), (windows[1], 'Agenda aus offenen Fragen', 'meetings.agenda')]:
                    menu = window._workflow_menu
                    next(item for item in menu.actions() if item.text() == label).trigger()
                    self.assertEqual(send.call_args.args[2], action)
                    self.assertEqual(send.call_args.args[1]['source']['id'], window.current)
        finally:
            for window in windows: window.close(); window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_project_context_captures_related_note_and_current_reader_page(self):
        path = self.root/'guide.pdf'; path.write_bytes(b'guide')
        self.projects.update(self.project, resources=[dict(kind='file', target=str(path), title='Guide')])
        reader = Library('reader', self.tools); book = reader.create('Guide', source=path.as_uri(), page=3, pages=8, notes=[])
        registry = Registry(self.tools)
        project_url = registry.register(dict(app='workbench', kind='record', id=self.project, title='Reparatur'))
        note_url = registry.register(dict(app='wissen', kind='note', id='repair.md', title='Reparaturnotiz'))
        registry.link(note_url, project_url)
        context = flow.project_context(self.projects, self.project)
        self.assertIn(note_url, [item['url'] for item in context])
        reading = next(item for item in context if item['app'] == 'reader')
        self.assertEqual(registry.resolve(reading['url'])['position']['page'], 3)
        flow.save_context(self.projects, self.project, [note_url, reading['url']])
        self.assertEqual(len(self.projects.get(self.project)['context']), 2)

    def test_cancelled_spoken_status_cleans_audio_and_does_not_create_radio_record(self):
        payload = flow.project_payload(self.projects, self.project, 'status')
        def voice(text, library, job):
            library.asset('cancelled.wav').write_bytes(b'audio'); job.cancelled.set()
            return dict(audio='cancelled.wav', duration=1000)
        with patch('tools_data.synthesize', side_effect=voice), self.assertRaises(Cancelled): flow.spoken_status(payload, self.tools, self.job)
        radio = Library('radio', self.tools); self.assertEqual(radio.all(), []); self.assertEqual(list(radio.assets.iterdir()), [])


if __name__ == '__main__': unittest.main()

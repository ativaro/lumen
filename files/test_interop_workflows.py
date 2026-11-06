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


    def test_handover_payload_contains_selected_files_and_provenance_for_shared_exporter(self):
        source = self.root/'manual.txt'; source.write_text('Manual')
        payload = flow.household_payload(self.house, self.device, 'handover', paths=[str(source)])
        self.assertEqual(payload['paths'], [str(source)])
        self.assertEqual(payload['items'][0]['title'], 'manual.txt')
        self.assertEqual(Registry(self.tools).resolve(payload['source_url'])['id'], self.device)
        self.assertEqual(source.read_text(), 'Manual')







if __name__ == '__main__': unittest.main()

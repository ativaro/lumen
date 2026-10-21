"""Native Qt choices, real Registry/FD/upload adapter, synthetic profile and HTTP.

The lease is a fixture for the still-unimplemented Host series B, not proof of it.
"""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QComboBox,
                              QLineEdit, QListWidget, QMessageBox, QPushButton, QWidget)
import interop_ui
from interop_data import Registry
from server_app_session import Binding
import test_server_file_import as fixture


class ImportUITest(unittest.TestCase):
    wire = fixture.FileImportTest.wire

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        fixture.FileImportTest.setUp(self)
        self.config['device_id'] = self.device
        self.folder_row['parent_id'] = None
        self.revision = 7; self.capabilities = ['drive', 'translate']
        self.window = QWidget(); self.window.name = 'compose'
        self.window.library = SimpleNamespace(root=self.base/'tools'/'compose')
        self.errors = []; self.window.error = self.errors.append
        self.addCleanup(self.window.deleteLater)
        self.generation = 0; self.delivered = []; self.seen = []
        self.context = self.lease()
        self.timer = QTimer(); self.timer.setInterval(5)
        self.addCleanup(self.timer.stop)
        self.cancel_picker = self.cancel_review = False
        self.before_review = lambda:None
        self.before_history = lambda dialog:None
        self.timer.timeout.connect(self.answer_dialog); self.timer.start()

    def profile(self, config, path, body=None):
        self.assertEqual(path, '/bridge/me')
        return dict(id=self.account, device_id=self.device,
                    permissions_revision=self.revision, capabilities=list(self.capabilities))

    def lease(self):
        generation = self.generation
        def check():
            if self.generation != generation:raise ValueError('Fixture host generation changed')
        return SimpleNamespace(window=self.window,
            binding=Binding(self.config['server'], self.account, self.device, 'compose'),
            permissions_revision=self.revision, check=check,
            accept_import=lambda ref,resolved:self.delivered.append(dict(reference=ref,resolved=resolved)))

    def answer_dialog(self):
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QFileDialog):
            if dialog.property('fixtureAnswered'):return
            dialog.setProperty('fixtureAnswered',True)
            if self.cancel_picker:dialog.reject()
            else:
                dialog.setDirectory(str(self.path.parent))
                def choose():
                    dialog.findChild(QLineEdit,'fileNameEdit').setText(str(self.path));dialog.accept()
                QTimer.singleShot(50,choose)
        elif isinstance(dialog, QDialog) and dialog.windowTitle() == 'Lumen Drive · Datei übernehmen':
            self.seen.append(dialog.windowTitle())
            self.before_review()
            if self.cancel_review:dialog.reject(); return
            destination = dialog.findChild(QComboBox)
            destination.setCurrentIndex(destination.findData(self.folder))
            dialog.accept()
        elif isinstance(dialog, QMessageBox) and dialog.windowTitle() == 'Lumen Drive · Übernahme prüfen':
            dialog.done(QMessageBox.StandardButton.Yes)

    def start(self, token=None):
        from server_file_import_ui import start_import
        return start_import(self.window, self.context, token, root=self.base/'tools')

    def only_request(self):
        rows = self.registry.history()
        self.assertEqual(len(rows), 2)  # Original adapter fixture plus the native selection.
        return self.registry.request(next(r['id'] for r in rows if r['id'] != self.token))

    def history_action(self, button):
        self.timer.stop()
        def activate():
            dialog = QApplication.activeModalWidget()
            if not dialog:return
            listing = dialog.findChild(QListWidget); listing.setCurrentRow(0)
            self.before_history(dialog)
            if button:
                control = next(b for b in dialog.findChildren(QPushButton) if 'fortsetzen' in b.text())
                QTest.mouseClick(control, Qt.LeftButton)
            else:
                listing.setFocus(); QTest.keyClick(listing, Qt.Key_Return)
        QTimer.singleShot(0, activate)
        interop_ui.browse(self.window, 'history')

    def test_both_pending_history_entries_fail_closed_without_host_callback(self):
        launches = []
        with patch('interop_open.launch', side_effect=lambda *a:launches.append(a)), patch('interop_ui.launch', side_effect=lambda *a:launches.append(a)):
            for button in (False, True):
                with self.subTest(button=button):self.history_action(button)
        self.assertEqual(launches, [], 'Files has no --handoff route')
        self.assertEqual(len(self.errors), 2)
        self.assertEqual(self.calls, [])

    def test_both_pending_history_entries_use_only_the_explicit_native_callback(self):
        resumed = []; self.window._lumen_file_import = resumed.append
        with patch('interop_open.launch', side_effect=AssertionError('No launcher')), patch('interop_ui.launch', side_effect=AssertionError('No launcher')):
            for button in (False, True):self.history_action(button)
        self.assertEqual(resumed, [self.token, self.token]); self.assertEqual(self.errors, [])

    def test_import_history_has_readable_action_and_no_generic_undo(self):
        def inspect(dialog):
            item=dialog.findChild(QListWidget).currentItem()
            self.assertNotIn('files.drive_import',item.text());self.assertIn('Lumen Drive',item.text())
            buttons=dialog.findChildren(QPushButton)
            self.assertTrue(any('prüfen und fortsetzen' in button.text() for button in buttons))
            undo=next(button for button in buttons if 'rückgängig' in button.text())
            self.assertFalse(undo.isEnabled())
        self.before_history=inspect;self.window._lumen_file_import=lambda token:None
        self.history_action(True)

    def test_existing_review_defaults_and_choice_fields_remain_unchanged(self):
        self.timer.stop()
        from interop_targets import ACTIONS
        before = json.dumps(ACTIONS, sort_keys=True)
        request = dict(self.registry.request(self.token), action='wissen.import')
        def accept():QApplication.activeModalWidget().accept()
        QTimer.singleShot(0, accept)
        with patch('interop_targets.choices', return_value=[dict(id='folder',title='Notes')]):
            choice = interop_ui.review(self.window, request)
        self.assertEqual(choice, dict(id='folder',title=self.path.name,mode='copy',due='',token=self.token))
        self.assertEqual(json.dumps(ACTIONS, sort_keys=True), before)
        self.assertNotIn('files.drive_import', ACTIONS)

    def test_native_selection_review_upload_and_filtered_return(self):
        other=str(uuid4())
        self.cache['folders'][other]=dict(self.folder_row,id=other,name='A different folder')
        result = self.start(); request = self.only_request()
        self.assertEqual(request['state'], 'done'); self.assertEqual(len(self.sessions), 1)
        self.assertEqual(result, self.delivered[0]); self.assertEqual(set(result), {'reference','resolved'})
        self.assertEqual(result['reference']['id'], next(iter(self.cache['files'])))
        self.assertEqual(self.path.read_bytes(), self.original); self.assertEqual(len(self.seen), 1)
        self.assertNotIn(str(self.path), str(result)); self.assertNotIn(self.config['token'], str(result))
        self.assertEqual(sum(method == 'PUT' for _,method,_ in self.calls), 1)
        begin=next(body for path,method,body in self.calls if method=='POST' and path.count('/')==2)
        self.assertEqual(begin['folder'],self.folder)

    def test_picker_and_review_cancellation_never_claim_or_upload(self):
        self.cancel_picker = True; self.assertIsNone(self.start())
        self.assertEqual(len(self.registry.history()), 1)
        self.cancel_picker = False; self.cancel_review = True
        with patch.object(Registry, 'claim', side_effect=AssertionError('No claim')):
            self.assertIsNone(self.start())
        request = self.only_request(); self.assertEqual(request['choice'], {})
        self.assertEqual(request['state'], 'pending'); self.assertEqual(self.calls, [])

    def test_missing_or_foreign_native_lease_never_opens_a_picker(self):
        from server_file_import_ui import start_import
        with patch.object(QFileDialog, 'getOpenFileName', side_effect=AssertionError('No picker')):
            for context in (None, SimpleNamespace(**dict(vars(self.context),window=QWidget()))):
                with self.subTest(context=context),self.assertRaises(ValueError):
                    start_import(self.window,context,root=self.base/'tools')
        self.assertEqual(self.calls, [])

    def test_current_identity_revision_and_explicit_areas_are_required(self):
        changes = [('account','other-account'), ('device','other-device'), ('revision',8),
                   ('capabilities',['translate']), ('capabilities',['drive'])]
        for field,value in changes:
            old = getattr(self,field); setattr(self,field,value)
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.start()
            setattr(self,field,old)
        self.assertEqual(self.calls, []); self.assertEqual(self.delivered, [])
        original=self.config['server'];self.config['server']='https://other.invalid'
        with self.assertRaises(ValueError):self.start()
        self.config['server']=original
        self.context.binding=Binding(original,self.account,self.device,'projects')
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.calls,[])

    def test_generation_change_during_review_prevents_prepare(self):
        self.before_review = lambda:setattr(self,'generation',1)
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(self.only_request()['choice'], {}); self.assertEqual(self.calls, [])

    def test_generation_change_after_begin_keeps_the_same_pending_operation(self):
        self.after_begin = lambda:setattr(self,'generation',1)
        with self.assertRaises(ValueError):self.start()
        request = self.only_request(); plan = request['choice']['drive_import']
        self.assertEqual(request['state'],'pending'); self.assertEqual(len(self.sessions),1)
        self.assertFalse(any(method == 'PUT' for _,method,_ in self.calls))
        self.after_begin = lambda:None; self.context = self.lease(); self.start(request['id'])
        self.assertEqual(self.registry.request(request['id'])['choice']['drive_import'],plan)
        self.assertEqual(len(self.sessions),1); self.assertEqual(len(self.delivered),1)

    def test_uncertain_ack_requires_explicit_same_operation_retry(self):
        self.lost_finish = True
        with self.assertRaises(ValueError):self.start()
        request = self.only_request(); self.assertEqual(request['state'],'pending')
        self.assertEqual(len(self.cache['files']),1); self.assertEqual(self.delivered,[])
        result = self.start(request['id'])
        self.assertEqual(self.registry.request(request['id'])['state'],'done')
        self.assertEqual(len(self.sessions),1); self.assertEqual(len(self.cache['files']),1)
        self.assertEqual(len(self.delivered),1); self.assertEqual(result,self.delivered[0])
        self.assertEqual(sum(method == 'PUT' for _,method,_ in self.calls),1)

    def test_local_finish_failure_retains_receipt_for_same_operation(self):
        with patch.object(Registry,'finish',side_effect=OSError('Local finish interrupted')):
            with self.assertRaises(ValueError):self.start()
        request = self.only_request(); receipt = request['choice']['drive_import_receipt']
        self.start(request['id'])
        self.assertEqual(self.registry.request(request['id'])['choice']['drive_import_receipt'],receipt)
        self.assertEqual(len(self.sessions),1); self.assertEqual(len(self.delivered),1)

    def test_changed_source_after_prepare_sends_no_requests(self):
        import server_file_import
        apply = server_file_import.apply
        def changed(*args,**kwargs):
            self.path.write_bytes(b'Replacement after review'); return apply(*args,**kwargs)
        with patch.object(server_file_import,'apply',side_effect=changed),self.assertRaises(ValueError):self.start()
        self.assertEqual(self.calls,[]); self.assertEqual(self.delivered,[])
        self.assertEqual(self.only_request()['state'],'pending')

    def test_completed_result_resolves_current_family_without_upload_or_old_source(self):
        self.start(); request = self.only_request(); calls = len(self.calls)
        row = next(iter(self.cache['files'].values())); row.update(version=2,revision=2,name='Renamed.pdf')
        self.path.unlink()
        result = self.start(request['id'])
        self.assertEqual(result['reference']['id'],row['family'])
        self.assertEqual(result['reference']['title'],'Renamed.pdf')
        self.assertEqual(result['resolved']['version'],2); self.assertEqual(len(self.calls),calls)

    def test_reentrant_review_does_not_enqueue_a_second_operation(self):
        duplicate=[]
        def enter_again():
            try:self.start()
            except ValueError as error:duplicate.append(str(error))
        self.before_review=enter_again;self.start()
        self.assertEqual(len(duplicate),1);self.only_request()
        self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.delivered),1)

    def test_user_cancel_after_chunk_retains_same_operation_without_callback(self):
        import server_file_import_ui as ui
        run=ui.run_job
        def observed(parent,title,function):
            def perform(job):self.active_job=job;return function(job)
            return run(parent,title,perform)
        self.after_chunk=lambda:self.active_job.cancelled.set()
        with patch.object(ui,'run_job',side_effect=observed):self.assertIsNone(self.start())
        request=self.only_request();self.assertEqual(request['state'],'pending')
        self.assertEqual(self.delivered,[]);self.assertEqual(len(self.sessions),1)
        self.after_chunk=lambda:None;self.start(request['id'])
        self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.delivered),1)
        self.assertEqual(sum(method=='PUT' for _,method,_ in self.calls),1)

    def test_permission_revision_change_after_commit_does_not_deliver_stale_result(self):
        self.after_finish=lambda:setattr(self,'revision',8)
        with self.assertRaises(ValueError):self.start()
        request=self.only_request();self.assertEqual(request['state'],'done')
        self.assertEqual(self.delivered,[]);calls=len(self.calls)
        self.context=self.lease();self.start(request['id'])
        self.assertEqual(len(self.delivered),1);self.assertEqual(len(self.calls),calls)


if __name__ == '__main__':unittest.main()

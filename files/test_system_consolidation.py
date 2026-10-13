"""Real retained pages with isolated settings and synthetic update outcomes."""
from unittest.mock import patch
import json
import sys
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
import unittest
import test_system_integration as integration


class ConsolidationTest(unittest.TestCase):
    setUpClass = classmethod(integration.SystemIntegrationTest.setUpClass.__func__)
    setUp = integration.SystemIntegrationTest.setUp
    tearDown = integration.SystemIntegrationTest.tearDown
    def test_update_page_retains_selection_and_guards_running_install(self):
        self.window.select('updates')
        page = self.window.updates
        page.set_plan(dict(revision='a'*40, notes='Synthetic release', rows=[
            dict(id='lumen', title='Lumen', detail='Apps', pending=True, optional=False),
            dict(id='system', title='Linux', detail='Optional', pending=True, optional=True)]))
        self.window.select('system'); self.window.select('updates')
        self.assertTrue(page.rows['lumen'][0].isChecked())
        self.assertFalse(page.rows['system'][0].isChecked())
        with patch.object(page, 'start') as start:
            page.install_button.click()
            self.assertEqual(start.call_args.args, ('apply', ['--revision', 'a'*40, '--components', 'lumen']))
        page.running = True
        event = QCloseEvent(); self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        page.running = False

    def test_diagnostics_is_explicit_and_aborts_on_close(self):
        self.window.select('diagnostics')
        page = self.window.diagnostics
        self.assertIsNone(page.checks.job)
        with patch('system_diagnostics.QProcess.startDetached', return_value=(True, 42)) as launch:
            page.tasks.click()
            launch.assert_not_called()
            self.assertEqual(page.views.currentIndex(), 1)
        with patch.object(page.checks, 'stop') as stop:
            self.window.close()
            stop.assert_called_once()

    def test_legacy_update_route_and_visible_catalogue(self):
        from lumen_apps import catalogue, launch
        self.assertNotIn('updater', [r[0] for r in catalogue()])
        self.assertNotIn('notification', [r[0] for r in catalogue()])
        self.assertIn('notification', [r[0] for r in catalogue(include_utilities=True)])
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as start:
            launch('updater')
            self.assertEqual(start.call_args.args[1], ['--page', 'updates'])
            launch('system', page='diagnostics')
            self.assertEqual(start.call_args.args[1], ['--page', 'diagnostics'])

    def test_update_worker_failure_and_retry_preserve_checked_revision(self):
        page = self.window.updates
        plan = dict(revision='a'*40, rows=[dict(id='lumen', title='Lumen', detail='Apps', pending=True, optional=False)])
        page.running = True
        page.proc.start(sys.executable, ['-c', 'print(' + repr(json.dumps({'plan': plan})) + ')'])
        self.assertTrue(page.proc.waitForFinished(3000))
        self.assertEqual(page.plan['revision'], 'a'*40)
        page.received_result = False; page.running = True
        page.proc.start('/nonexistent/lumen-test-worker', [])
        self.assertFalse(page.proc.waitForStarted(1000))
        self.assertFalse(page.running)
        self.assertFalse(page.install_button.isEnabled())
        self.assertIsNone(page.plan)
        self.assertTrue(page.check_button.isEnabled())

    def test_diagnostic_cancel_and_failed_task_launch(self):
        page = self.window.diagnostics; self.window.select('diagnostics')
        job = QProcess(page.checks); page.checks.job = job
        job.start(sys.executable, ['-c', 'import time; time.sleep(20)'])
        self.assertTrue(job.waitForStarted(1000))
        page.checks.cancel.show()
        QTest.mouseClick(page.checks.cancel, Qt.LeftButton)
        self.assertIsNone(page.checks.job)
        self.assertEqual(job.state(), QProcess.NotRunning)
        with patch('system_diagnostics.QProcess.startDetached', return_value=(False, 0)):
            page.tasks.click()
        self.assertEqual(page.views.currentIndex(), 1)
        self.assertEqual(page.checks.status.text(), 'Prüfung abgebrochen.')

    def test_notification_button_opens_existing_center(self):
        from lumen_apps import AppCenter
        center = AppCenter(); self.addCleanup(center.close)
        with patch('lumen_notifications.open_center') as open_center:
            center.notifications.click()
            open_center.assert_called_once_with()

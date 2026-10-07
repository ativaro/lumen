import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import troubleshooter as checks


class TroubleshooterChecksTest(unittest.TestCase):
    def test_disabled_services_are_not_failures_but_enabled_failed_units_are(self):
        from desktop_settings import SERVICES
        def response(command, **kwargs):
            scope = 'user' if '--user' in command else 'system'
            rows = [f'Id={unit}\nLoadState=loaded\nActiveState=inactive\nUnitFileState=disabled'
                    for group, unit in SERVICES if group == scope]
            return subprocess.CompletedProcess(command, 0, '\n\n'.join(rows), '')
        with patch('troubleshooter.subprocess.run', side_effect=response):
            self.assertEqual(checks.services({})[0], 'ok')
        failed = subprocess.CompletedProcess([], 0, 'Id=lumen-notify.path\nLoadState=loaded\nActiveState=failed\nUnitFileState=enabled', '')
        with patch('troubleshooter.subprocess.run', return_value=failed):
            self.assertEqual(checks.services({})[0], 'warning')

    def test_partial_failures_stay_local_and_report_excludes_private_values(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LUMEN_DATA=folder):
            report = Path(folder)/'crashes/run-test/report.json'; report.parent.mkdir(parents=True)
            report.write_text(json.dumps(dict(status='crashed', started=checks.time.time(), detail='secret-chat')))
            with patch('lumen_setup.executable', return_value=''), patch('troubleshooter.subprocess.run', side_effect=FileNotFoundError('private-path')):
                result = checks.collect(dict(model='secret-model', speechModel='private-path'))
            states = {row['action']: row['state'] for row in result['checks']}
            self.assertEqual(states['model'], 'warning'); self.assertEqual(states['services'], 'warning')
            self.assertEqual(states['recovery'], 'warning'); self.assertEqual(states['speech'], 'warning')
            self.assertEqual(states['setup'], 'info'); self.assertTrue(result['checked_at'])
            output = json.dumps(result)
            for private in ('secret-model', 'secret-chat', 'private-path', folder): self.assertNotIn(private, output)
            self.assertEqual(list(Path(folder).iterdir()), [Path(folder)/'crashes'])
            report.write_text(json.dumps(dict(status='interrupted', started=checks.time.time())))
            self.assertEqual(checks.crashes({})[0], 'ok')
            report.write_text(json.dumps(dict(status='closed', started=0, hang_detected=checks.time.time())))
            self.assertEqual(checks.crashes({})[0], 'warning')


if __name__ == '__main__': unittest.main()

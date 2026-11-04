import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from topbar_data import snapshot


class TopbarDataTests(unittest.TestCase):
    def test_bar_reads_shared_palette_without_waking_notifications_or_loading_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'plasmarc').write_text('[Theme]\nname=org.lumen.atelier\n')
            with patch.dict(os.environ, XDG_CONFIG_HOME=directory), \
                 patch('lumen_panel.applications', return_value=[dict(id='files')]), \
                 patch('lumen_panel.snapshot', side_effect=AssertionError('Task history is not a bar dependency')), \
                 patch('lumen_controls.snapshot', return_value={}), \
                 patch('topbar_context.snapshot', return_value={}), \
                 patch('lumen_notifications.snapshot', return_value=dict(unread=4)) as notices:
                result = snapshot()
            notices.assert_called_once_with(wake=False)
            self.assertEqual(result['palette']['window'], '#f2efe8')
            self.assertEqual(result['unread'], 4)
            self.assertNotIn('active', result)
            json.dumps(result)

    def test_unavailable_notification_store_does_not_claim_zero_unread(self):
        with patch('lumen_panel.applications', return_value=[]), \
             patch('lumen_controls.snapshot', return_value={}), \
             patch('topbar_context.snapshot', return_value={}), \
             patch('lumen_notifications.snapshot', side_effect=sqlite3.OperationalError('locked')):
            self.assertIsNone(snapshot()['unread'])


if __name__ == '__main__':
    unittest.main()

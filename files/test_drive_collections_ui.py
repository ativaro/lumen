"""All accessible Drive files, folder-derived writes, no global area switch."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from PySide6.QtWidgets import QApplication, QComboBox
from PySide6.QtCore import Qt
from drive_ui import Drive
from lumen_i18n import tr


class DriveBrowseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_accessible_sources_are_combined_and_writes_follow_folder(self):
        def inventory(config):
            return dict(files={source:dict(id=source,name=source+'.txt',folder_id=None,trashed=False,mime='text/plain',size=1,can_write=source!='read') for source in ['mine','shared','read']},
                        folders={source:dict(id=source,name=source,parent_id=None,trashed=False,can_write=source!='read') for source in ['mine','shared','read']})
        with tempfile.TemporaryDirectory() as root, patch('drive_ui.lumen_connect.read_config',return_value={'server':'https://fixture.invalid'}), \
             patch('drive_ui.lumen_connect.request',return_value={'can_create':True}), patch('drive_ui.sync.inventory',side_effect=inventory), \
             patch('drive_ui.sync.read',return_value={'roots':[]}):
            window=Drive()
            def work(fn,done=None):
                value=fn(Mock())
                if done: done(value)
            window.work=work
            try:
                window.reload()
                self.assertEqual(window.list.topLevelItemCount(),6)
                self.assertEqual(window.findChildren(QComboBox),[window.roots])
                self.assertTrue(window.can_write())
                window.folder='shared';window.render()
                self.assertTrue(window.can_write())
                file=Path(root)/'upload.txt';file.write_text('original')
                with patch('drive_ui.QFileDialog.getOpenFileName',return_value=(str(file),'')), patch('drive_ui.transport.upload') as upload:
                    window.upload()
                    self.assertEqual(upload.call_args.args[3],'shared')
                window.folder='read';window.render()
                with patch('drive_ui.QFileDialog.getOpenFileName') as choose:
                    window.upload();choose.assert_not_called()
                window.folder=None;window.render()
                with patch('drive_ui.QMessageBox.question') as confirm:
                    window.configure();confirm.assert_not_called()
                self.assertEqual(window.status.text(),tr('Zum Synchronisieren zuerst einen Drive-Ordner öffnen.'))
            finally:
                # Execute queued refreshes against the same synthetic transport.
                self.app.processEvents();window.close();window.deleteLater();self.app.processEvents()

    def test_failed_refresh_clears_old_inventory_instead_of_showing_revoked_files(self):
        with patch('drive_ui.sync.read',return_value={'roots':[]}):
            window=Drive();window.work=lambda fn,done=None: None
            try:
                window.cache={'files':{'old':{}},'folders':{}}
                window.reload()
                self.assertEqual(window.cache,{'files':{},'folders':{}})
                self.assertEqual(window.profile,{})
            finally:
                self.app.processEvents();window.close();window.deleteLater();self.app.processEvents()

if __name__=='__main__':unittest.main()

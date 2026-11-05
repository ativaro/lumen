"""Files uses its normal model/history for Drive; no popup or local-path fallback."""

import tempfile
import lumen_transfers as transfers
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from PySide6.QtCore import QSettings, Qt, QItemSelectionModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import Window, create_app
import drive_browser as browser


class DriveBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app()

    def start_transfer(self, store, value):
        transfers.execute(store, value['id'])
        transfers.update(store, value['id'], status='completed')

    def wait(self, predicate):
        end = time.monotonic() + 6
        while not predicate() and time.monotonic() < end:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def test_normal_view_history_tabs_search_and_local_clipboard_download(self):
        user, folder, family, version = (str(uuid4()) for _ in range(4))
        config = dict(server="https://example.invalid", token="fixture")
        cache = dict(
            folders={
                folder: dict(
                    id=folder, name="Photos", parent_id=None, trashed=False, revision=1
                )
            },
            files={
                family: dict(
                    id=version,
                    family=family,
                    name="photo.txt",
                    folder_id=folder,
                    trashed=False,
                    revision=1,
                    size=5,
                    mime="text/plain",
                    sha256="unused",
                )
            },
        )

        def request(_config, path, body=None):
            self.assertEqual(path, "/bridge/me")
            return dict(id=user, name="Reader QA", can_create=True)

        def download(_config, root, row, progress):
            Path(root["path"], "stage").write_text("hello")
            return "stage"

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(browser.lumen_connect, "read_config", return_value=config),
            patch.object(transfers, "start", side_effect=self.start_transfer),
            patch.object(browser.lumen_connect, "request", side_effect=request),
            patch.object(browser.sync, "inventory", return_value=cache),
            patch.object(browser.transport, "download", side_effect=download),
        ):
            w = Window(tmp, QSettings(tmp + "/settings.ini", QSettings.IniFormat))
            w.show()
            errors = []
            w.error = lambda *args: errors.append(args)
            try:
                w.navigate(browser.ROOT)
                self.wait(lambda: not w.drive.jobs)
                self.assertIs(w.proxy.sourceModel(), w.drive.model)
                self.assertFalse(hasattr(w, "drive_dialog"))
                w.open_path(browser.location())
                self.wait(lambda: not w.drive.jobs)
                self.assertEqual(w.drive.model.item(0).text(), "Photos")
                w.open_path(browser.location(folder))
                self.wait(lambda: not w.drive.jobs)
                self.assertEqual(w.drive.model.item(0).text(), "photo.txt")
                w.search.setText("missing")
                w.start_search()
                self.assertEqual(w.drive.model.rowCount(), 0)
                w.search.clear()
                w.start_search()
                index = w.proxy.index(0, 0)
                w.view.selectionModel().select(
                    index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                )
                w.copy(False)
                self.assertTrue(
                    browser.is_drive(
                        QApplication.clipboard().mimeData().urls()[0].toString()
                    )
                )
                w.navigate(tmp)
                self.wait(lambda: not w.drive.jobs)
                w.paste()
                self.wait(lambda: not w.drive.jobs)
                self.assertEqual(Path(tmp, "photo.txt").read_text(), "hello")
                w.history(-1)
                self.wait(lambda: not w.drive.jobs)
                self.assertEqual(w.current_location, browser.location(folder))
                w.up()
                self.wait(lambda: not w.drive.jobs)
                self.assertEqual(w.current_location, browser.location())
                w.new_tab(browser.location(folder))
                self.wait(lambda: not w.drive.jobs)
                self.assertEqual(w.tabs.tabText(w.tabs.currentIndex()), "Photos")
                # Leaving while a listing is in flight must never restore the Drive model.
                w.navigate(browser.ROOT)
                w.navigate(tmp)
                self.wait(lambda: not w.drive.jobs)
                self.assertIs(w.proxy.sourceModel(), w.fs)
                self.assertEqual(w.current_path, tmp)
                self.assertEqual(errors, [])
            finally:
                self.wait(lambda: not w.drive.jobs)
                QApplication.clipboard().clear()
                w.close()
                QTest.qWait(30)

    def test_recursive_download_includes_files_directly_in_selected_folder(self):
        folder, family = (str(uuid4()) for _ in range(2))
        row = dict(
            id=str(uuid4()),
            family=family,
            name="inside.txt",
            size=5,
            folder_id=folder,
            trashed=False,
        )
        cache = dict(
            folders={
                folder: dict(id=folder, name="Folder", parent_id=None, trashed=False)
            },
            files={family: row},
        )

        class Job:
            def check(self):
                pass

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(browser.sync, "inventory", return_value=cache),
        ):
            w = Window(tmp, QSettings(tmp + "/settings.ini", QSettings.IniFormat))
            try:

                def download(_config, root, _row, _progress):
                    Path(root["path"], "stage").write_text("hello")
                    return "stage"

                with patch.object(browser.transport, "download", side_effect=download):
                    w.drive.download_into(
                        {}, [browser.location(folder)], tmp, Job()
                    )
                self.assertEqual(Path(tmp, "Folder/inside.txt").read_text(), "hello")
                with self.assertRaises(ValueError):
                    w.drive.download_into(
                        {}, [browser.location(folder)], tmp, Job()
                    )
            finally:
                QApplication.clipboard().clear()
                w.close()
                QTest.qWait(30)


if __name__ == "__main__":
    unittest.main()

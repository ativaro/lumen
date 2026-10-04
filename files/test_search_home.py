import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from search_home import recent_documents, SearchHome


class HomeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
        self.enterContext(patch.dict(os.environ,LUMEN_DATA=self.tmp+'/state',XDG_DATA_HOME=self.tmp+'/data'))

    def test_recent_metadata_is_bounded_and_never_executes_desktop_entries(self):
        folder=self.root/'RecentDocuments';folder.mkdir()
        (folder/'a.desktop').write_text('[Desktop Entry]\nName=Report\nURL=file:///nonexistent/report.pdf\nExec=touch /should-not-exist\nIcon=application-pdf\n')
        (folder/'b.desktop').write_text('[Desktop Entry]\nName=Remote\nURL=https://example.com/secret\n')
        (self.root/'recently-used.xbel').write_text('<xbel><bookmark href="file:///nonexistent/note.txt" modified="2026-10-04T10:00:00Z"><title>Note</title></bookmark></xbel>')
        rows=recent_documents(self.root)
        self.assertEqual({r['title'] for r in rows},{'Report','Note'})
        self.assertNotIn('Exec',str(rows))

    def test_open_routes_are_allowlisted_and_only_finished_tasks_are_dismissed(self):
        from lumen_store import Store
        store=Store();done=store.create_task('Done',directory=self.tmp);live=store.create_task('Live',directory=self.tmp)
        store.update_task(done,status='completed');store.update_task(live,status='running')
        home=SearchHome();home._tasks=[dict(id=done,status='completed'),dict(id=live,status='running')]
        with patch.object(home,'refresh'),patch.object(home,'launch_desktop') as launch:
            home.open_task('unknown');launch.assert_not_called()
            home.open_task(done);launch.assert_called_once_with(['--task',done])
            home.dismiss(live);self.assertIn(live,[t['id'] for t in store.tasks(False)])
            home.dismiss(done);self.assertNotIn(done,[t['id'] for t in store.tasks(False)])
        with patch('search_home.QDesktopServices.openUrl') as opened:
            home.open_recent('/unknown');opened.assert_not_called()
            home._recent=[dict(path='/known')];home.open_recent('/known');self.assertEqual(opened.call_args.args[0].toLocalFile(),'/known')
        home.shutdown()

    def test_snapshot_worker_reads_actual_tasks_without_blocking_the_ui(self):
        from lumen_store import Store
        from PySide6.QtTest import QTest
        store=Store();identity=store.create_task('Native task',directory=self.tmp)
        home=SearchHome();home.refresh()
        try:
            for _ in range(100):
                if home.process is None:break
                QTest.qWait(20)
            self.assertIsNone(home.process)
            self.assertIn(identity,[t['id'] for t in home.tasks])
            self.assertEqual(home.recent,[])
        finally:home.shutdown()


if __name__=='__main__':unittest.main()

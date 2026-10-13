import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from tools_data import Library
from tools_workbench import Workbench
from interop_paths import relocate

class PathMoveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_move_updates_closed_reader_and_unsaved_project_without_losing_edits(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_TOOLS_DATA':tmp,'LUMEN_DATA':tmp+'/state'}):
            old=Path(tmp)/'old';new=Path(tmp)/'new';old.mkdir();file=old/'book.txt';file.write_text('book')
            reader=Library('reader',tmp);book=reader.create('Book',original_path=str(file),source=file.as_uri())
            window=Workbench(tmp);window.error=lambda text:self.fail(text)
            project=window.library.create('Project',notes='saved',questions=[],resources=[dict(kind='file',title='book',target=str(file))])
            window.focus_record(project);window.notes.setPlainText('unsaved')
            old.rename(new);relocate(old,new,tmp);window.save()
            record=window.library.get(project)
            self.assertEqual(record['notes'],'unsaved');self.assertEqual(record['resources'][0]['target'],str(new/'book.txt'))
            self.assertEqual(reader.get(book)['original_path'],str(new/'book.txt'))
            old.mkdir();file.write_text('new different file');window.add_resource('file',str(file),'new book');window.save()
            self.assertEqual(window.library.get(project)['resources'][1]['target'],str(file))
            window.close();window.deleteLater();self.app.processEvents()
if __name__=='__main__':unittest.main()

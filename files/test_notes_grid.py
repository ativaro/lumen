import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QInputDialog
from notes_grid import Model,show
from notes_properties_ui import PropertiesDialog
from wissen_data import parse


class GridTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def wait(self,check):
        for _ in range(600):
            QTest.qWait(10)
            if check():return
        self.fail('Notes table timed out')
    def test_virtual_model_many_rows_and_sparse_properties(self):
        model=Model();notes=[parse(f'{i}.md',f'---\nstatus: open\n---\n# Note {i}'.encode()) for i in range(10000)]
        model.replace(notes);self.assertEqual(model.rowCount(),10000);self.assertEqual(model.columnCount(),4)
        self.assertEqual(model.data(model.index(9999,0)),'Note 9999');self.assertEqual(model.data(model.index(9999,3)),'open')
        self.assertFalse(model.flags(model.index(0,3))&Qt.ItemIsEditable)
        model.replace([parse('empty.md',b'# Empty')]);self.assertEqual(model.columnCount(),3)




if __name__=='__main__':unittest.main()

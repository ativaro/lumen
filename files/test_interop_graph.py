import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from interop_data import Registry
from interop_graph import neighbors
from wissen_views import KnowledgeMap, GraphNode


class GraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_cross_app_backlinks_and_inline_links_are_graph_nodes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); book = SimpleNamespace(root=root/'notes'); registry = Registry(root/'tools')
            note = dict(path='idea.md', title='Idee', text='# Idee', source='', links=[])
            url = registry.register(dict(app='wissen', kind='note', id=note['path'], title=note['title'], path=str(book.root/note['path']), locator=dict(root=str(book.root), area='user')))
            project = registry.register(dict(app='workbench', kind='record', id='project', title='Projekt'))
            device = registry.register(dict(app='household', kind='record', id='device', title='Gerät'))
            registry.link(project, url); note['text'] += '\n'+device
            external = neighbors(book, note, root/'tools')
            self.assertEqual({value['app'] for value in external}, {'workbench', 'household'})
            view = KnowledgeMap(); view.resize(800, 600); view.show()
            try:
                view.display({'idea.md': note}, 'idea.md', external)
                nodes = [item for item in view.scene().items() if isinstance(item, GraphNode)]
                self.assertEqual(len(nodes), 3)
                target = next(node for node in nodes if node.path == project)
                spy = QSignalSpy(view.objectRequested)
                QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(target.scenePos()))
                self.assertEqual(spy.at(0)[0], project)
            finally: view.close()


if __name__ == '__main__': unittest.main()

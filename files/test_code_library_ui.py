import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


class CollectionUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.root.cleanup)
        cls.environment=patch.dict(os.environ,{'QT_QPA_PLATFORM':'offscreen','LUMEN_DATA':cls.root.name+'/state','LUMEN_TOOLS_DATA':cls.root.name+'/tools','XDG_CONFIG_HOME':cls.root.name+'/config','LUMEN_LANGUAGE':'de'})
        cls.environment.start();cls.addClassCleanup(cls.environment.stop)
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def test_collection_detail_back_and_safe_preview(self):
        from code_library_window import CollectionWindow
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as root:
            window=CollectionWindow(Store(root));self.addCleanup(window.close)
            entry=window.collection.create('app','Vergleich',value={'html':'<button>Test</button>'},project_id='preserved-project')
            window.collection.create('tool','Bericht',value={'prompt':'Bericht erstellen'})
            window.search.setText('Vergleich');self.assertEqual(window.entries.topLevelItemCount(),1)
            window.open_entry(entry['id'],apps=False);self.assertEqual(window.title.text(),'Vergleich')
            window.save();self.assertEqual(window.collection.get(entry['id'])['project_id'],'preserved-project')
            window.toggle_favorite();self.assertTrue(window.current['favorite'])
            with patch('code_library_window.QDesktopServices.openUrl',return_value=True) as opened:
                window.open_app();self.assertTrue(opened.called)
                path=Path(opened.call_args.args[0].toLocalFile());self.assertIn('sandbox=',path.read_text())
            window.back();self.assertEqual(window.search.text(),'Vergleich');self.assertEqual(window.entries.topLevelItemCount(),1)
            window.open_entry(entry['id'],apps=False);window.toggle_archive();self.assertEqual(window.entries.topLevelItemCount(),0)
            window.categories.setCurrentRow(window.category_keys.index('archive'));self.assertEqual(window.entries.topLevelItemCount(),1)

    def test_collection_selection_favorites_filters_and_keyboard(self):
        from code_library_window import CollectionWindow
        from lumen_store import Store
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as root:
            window=CollectionWindow(Store(root));self.addCleanup(window.close)
            window.collection.create('app','Packliste','Für die nächste Reise',value={'html':'<h1>Packliste</h1>'})
            tool=window.collection.create('tool','Dokumentenprüfung','Fehlende Angaben erkennen',value={'prompt':'Prüfe die Angaben'},project_id='retained-project')
            window.refresh();window.show();window.activateWindow();QTest.qWait(40)
            self.assertEqual(window.preview_title.text(),tool['title']);self.assertTrue(window.preview_open.isVisible())
            self.assertFalse(window.store.tasks());self.assertEqual(window.collection_count.text(),'2 Einträge')
            window.sort.setCurrentIndex(1);self.assertEqual(window.entries.currentItem().data(0,Qt.UserRole),tool['id'])
            window.entries.setFocus();QTest.keyClick(window.entries,Qt.Key_D,Qt.ControlModifier)
            self.assertTrue(window.collection.get(tool['id'])['favorite'])
            window.categories.setCurrentRow(1);self.assertEqual(window.entries.topLevelItemCount(),1)
            window.preview_favorite.click();self.assertEqual(window.entries.topLevelItemCount(),0);self.assertTrue(window.empty_frame.isVisible());self.assertFalse(window.preview_shell.isVisible())
            window.empty_action.click();self.assertEqual(window.categories.currentRow(),0)
            window.search.setText('Nicht vorhanden');self.assertEqual(window.empty.text(),'Keine passenden Einträge')
            window.empty_action.click();self.assertEqual(window.entries.topLevelItemCount(),2);self.assertEqual(window.search.text(),'')
            window.project_filter.addItem('Erhaltenes Projekt','retained-project');window.project_filter.setCurrentIndex(2)
            self.assertEqual(window.entries.topLevelItemCount(),1)
            with patch.object(window,'open_entry') as opened:
                window.entries.setFocus();QTest.keyClick(window.entries,Qt.Key_Return);opened.assert_called_once_with(tool['id'])
            window.resize(960,720);QTest.qWait(30);self.assertFalse(window.preview_shell.isVisible())
            window.resize(1240,820);QTest.qWait(30);self.assertTrue(window.preview_shell.isVisible())
            self.assertTrue(window.preview_open.isVisible());self.assertFalse(window.store.tasks())
            window.project_filter.setCurrentIndex(0);window.categories.setCurrentRow(window.category_keys.index('archive'));self.assertEqual(window.empty.text(),'Das Archiv ist leer')

    def test_empty_collection_starts_creation_and_long_preview_keeps_actions(self):
        from code_library_window import CollectionWindow
        from lumen_store import Store
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as root:
            window=CollectionWindow(Store(root));self.addCleanup(window.close);window.show();QTest.qWait(20)
            self.assertTrue(window.empty_frame.isVisible());self.assertFalse(window.list_frame.isVisible())
            with patch.object(window,'create') as create:window.empty_action.click();create.assert_called_once()
            window.collection.create('tool','Langer Titel '*10,'Eine ausführliche Beschreibung. '*50,value={'prompt':'Auftrag'})
            window.refresh();QTest.qWait(30)
            self.assertTrue(window.preview_open.isVisible())
            self.assertTrue(window.rect().contains(window.preview_open.mapTo(window,window.preview_open.rect().center())))
            self.assertLessEqual(window.height(),820);self.assertFalse(window.store.tasks())

    def test_creation_preserves_per_kind_drafts_and_requires_review(self):
        from PySide6.QtWidgets import QMessageBox
        from code_creation import CreationDialog,KINDS
        from code_library import Collection
        from lumen_store import Store
        from code_tool import spec
        from code_flow import parse
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            collection=Collection(Store(root));dialog=CreationDialog(projects={'project-a':'Projekt A'})
            self.addCleanup(lambda:dialog.done(0))
            self.assertNotIn('app',KINDS)
            dialog.select_kind('tool');dialog.prompt.setPlainText('Eigene Regeln');dialog.name.setText('Prüfer');dialog.project.setCurrentIndex(1);dialog.back()
            dialog.select_kind('routine');dialog.prompt.setPlainText('Wöchentlicher Überblick');dialog.back()
            dialog.select_kind('tool');self.assertEqual(dialog.prompt.toPlainText(),'Eigene Regeln');self.assertEqual(dialog.name.text(),'Prüfer')
            self.assertEqual(collection.items(),[]);dialog.review();self.assertEqual(dialog.pages.currentIndex(),2)
            value=dialog.value;self.assertEqual(value['project_id'],'project-a');self.assertIn('Eigene Regeln',spec(value['definition']['tool_spec'])['rules'])
            dialog.pages.setCurrentIndex(1)
            with patch('code_creation.QMessageBox.question',return_value=QMessageBox.No):dialog.reject()
            self.assertEqual(dialog.result(),0);self.assertEqual(dialog.prompt.toPlainText(),'Eigene Regeln')
            dialog.select_kind('code');dialog.review();self.assertIsNone(dialog.value);self.assertIn('Projektordner',dialog.error.text())
            dialog.select_kind('routine');dialog.review();self.assertEqual(dialog.value['kind'],'automation');self.assertIn('clock',parse(dialog.value['definition']['flow']))

    def test_creation_cards_navigation_and_reachable_flow_actions(self):
        from code_creation import CreationDialog
        from PySide6.QtWidgets import QPushButton,QLabel
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        dialog=CreationDialog();self.addCleanup(lambda:dialog.done(0));dialog.show();QTest.qWait(40)
        self.assertEqual(dialog.pages.currentIndex(),0)
        cards=[b for b in dialog.findChildren(QPushButton,'codeCard') if b.isVisible()];self.assertEqual(len(cards),4)
        for card in cards:
            self.assertGreaterEqual(card.height(),156)
            for text in card.findChildren(QLabel):self.assertTrue(card.rect().contains(text.mapTo(card,text.rect().center())))
        QTest.mouseClick(cards[2],Qt.LeftButton);QTest.qWait(20);self.assertEqual(dialog.kind,'automation')
        self.assertIn('Automation',dialog.windowTitle())
        self.assertEqual(dialog.flow_editor.plan()['version'],3)
        review=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Weiter zur Prüfung');self.assertTrue(review.isVisible());self.assertTrue(dialog.rect().contains(review.mapTo(dialog,review.rect().center())))
        QTest.mouseClick(review,Qt.LeftButton);self.assertEqual(dialog.pages.currentIndex(),2)
        dialog.back();QTest.mouseClick(cards[0],Qt.LeftButton);self.assertEqual(dialog.kind,'tool');self.assertTrue(dialog.forms['tool'].input.isVisible())
        dialog.back();QTest.mouseClick(cards[3],Qt.LeftButton);self.assertEqual(dialog.kind,'code');self.assertTrue(all(b.isVisible() for b in dialog.forms['code'].source_buttons));dialog.forms['code'].source_buttons[1].click();self.assertTrue(dialog.forms['code'].url.isVisible())

    def test_goal_recommendation_is_reviewed_and_keeps_manual_override(self):
        import json
        from code_creation import CreationDialog
        dialog=CreationDialog();self.addCleanup(lambda:dialog.done(0));dialog.pages.setCurrentIndex(3)
        dialog.goal.setPlainText('請檢查我的文件');dialog.goal_submitted=dialog.goal.toPlainText()
        plan=dict(kind='tool',title='Dokumentenprüfung',prompt='Nenne fehlende Felder',reason='Mit neuen Dokumenten wiederverwenden',checks=['Fundstelle pro Lücke nennen'])
        dialog.goal_generated(True,json.dumps(plan));self.assertEqual(dialog.pages.currentIndex(),3);self.assertIsNone(dialog.value)
        dialog.accept_goal();self.assertEqual(dialog.kind,'tool');self.assertIn('Fundstelle',dialog.prompt.toPlainText())
        dialog.back();dialog.select_kind('routine');self.assertEqual(dialog.prompt.toPlainText(),'請檢查我的文件')
        dialog.back();dialog.select_kind('tool');self.assertIn('Fundstelle',dialog.prompt.toPlainText())

    def test_real_coding_surface_and_unsent_draft(self):
        from code_session import CodingWindow
        from code_library import Collection
        from lumen_store import Store
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as root,patch('assistant_backend.OpenCodeBackend.refresh_sessions'):
            collection=Collection(Store(root+'/state'));folder=Path(root)/'repo';folder.mkdir();(folder/'code.txt').write_text('actual source')
            item=collection.create('code','Projekt',value={'directory':str(folder),'prompt':'Prüfe die Datei'})
            window=CodingWindow(collection,item['id']);window.show();QTest.qWait(180)
            self.assertEqual([window.studio.result_tabs.tabText(i) for i in range(4)],['Arbeitsschritte','Dateien','Änderungen','Prüfung'])
            self.assertEqual(window.studio.result_tabs.currentIndex(),2)
            self.assertTrue(window.chat.isVisible());self.assertTrue(window.back_to_collection.isVisible())
            window.studio.finish_work(True,'Fertig');self.assertEqual(window.studio.result_tabs.currentIndex(),2)
            self.assertFalse(window.studio.stage.isVisible())
            window.resize(960,800);QTest.qWait(40)
            self.assertTrue(window.chat.isVisible());self.assertGreater(window.chat.width(),window.studio.pane.width())
            window.studio.set_result({'paths':[folder/'code.txt'],'title':'Datei'})
            self.assertTrue(window.studio.files_button.isVisible());window.studio.open_files()
            self.assertTrue(window.studio.file_dialog.isVisible());self.assertTrue(window.studio.choice.isVisible())
            window.studio.file_dialog.close();self.assertFalse(window.studio.file_dialog.isVisible())
            self.assertEqual(window.chat.composer.toPlainText(),'Prüfe die Datei')
            window.open_source('code.txt');self.assertEqual(window.source.toPlainText(),'actual source')
            window.chat.backend.session='previous-session';window.persist();window.chat.backend.new_conversation()
            self.assertEqual(collection.get(item['id'])['definition']['session_id'],'')
            window.chat.composer.setPlainText('Ungesendeter Entwurf');self.assertTrue(window.close());QTest.qWait(50)
            item=collection.get(item['id']);self.assertEqual(item['definition']['draft_prompt'],'Ungesendeter Entwurf')
            again=CodingWindow(collection,item['id']);self.assertTrue(again.close());again.inspect();self.assertIsNone(again.job);QTest.qWait(50)

    def test_task_routing_dirty_cancel_and_failed_activation(self):
        from code_library_window import CollectionWindow
        from lumen_store import Store
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as root:
            window=CollectionWindow(Store(root));self.addCleanup(window.close)
            entry=window.collection.create('tool','Bericht',value={'prompt':'Prüfe die Eingabe'})
            window.open_entry(entry['id']);window.input.setPlainText('Neue Daten')
            with patch('lumen_detail_routes.open_tasks') as opened, patch('lumen_detail_routes.task_action') as action:
                window.execute();task=window.collection.get(entry['id'])['last_task']
                opened.assert_called_once_with(task);action.assert_called_once_with(task,'run')
                self.assertIn('Neue Daten',window.store.task(task)['prompt'])
            window.title.setText('Nicht verlieren')
            with patch('code_library_window.QMessageBox.question',return_value=QMessageBox.Cancel):
                window.categories.setCurrentRow(1)
            self.assertEqual(window.categories.currentRow(),0);self.assertEqual(window.title.text(),'Nicht verlieren')
            window.save();automation=window.collection.create('automation','Daily',value={'prompt':'Bericht','directory':root});window.open_entry(automation['id'])
            with patch('lumen_workspace.PlanDialog') as plan,patch('lumen_actions.command',side_effect=RuntimeError('Timer nicht verfügbar')):
                plan.return_value.exec.return_value=1
                plan.return_value.value=dict(name='Daily',steps=[],roots=[root],prompt='Bericht',approved=True,enabled=True)
                window.safe(window.configure_flow)
            self.assertIn('Timer nicht verfügbar',window.status.text());self.assertFalse(window.store.workflows()[0]['enabled'])


if __name__=='__main__':unittest.main()

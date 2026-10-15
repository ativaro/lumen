import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class JournalTest(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
        self.enterContext(patch.dict(os.environ,LUMEN_TOOLS_DATA=self.tmp,LUMEN_DATA=self.tmp+'/state',XDG_CONFIG_HOME=self.tmp+'/config'))
        from PySide6.QtWidgets import QApplication
        from tools_workbench import Workbench
        self.app=QApplication.instance() or QApplication([]);self.window=Workbench(self.root)
        self.window.error=lambda text:self.fail(text)
        self.key=self.window.library.create('Journal',notes='Keep me',resources=[],references=[])
        self.window.focus_record(self.key);self.window.editor.hide()
    def tearDown(self):
        self.window.journal.question.clear();self.window.close();self.window.deleteLater();self.app.processEvents()
    def test_card_overview_search_archive_and_draft_return(self):
        w=self.window;other=w.library.create('Other',notes='Find this source',resources=[])
        archived=w.library.create('Archived',resources=[]);w.library.archive(archived,True)
        w.journal.question.setPlainText('Keep unsent question')
        w.show_home();self.assertIs(w.home.pages.currentWidget(),w.home.overview)
        self.assertEqual(w.journal.question.toPlainText(),'Keep unsent question')
        overview=w.home.overview;overview.search.setText('Find this')
        self.assertEqual([c.accessibleName() for c in overview.cards],['Other'])
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox,'question',return_value=QMessageBox.No):overview.cards[0].click()
        self.assertIs(w.home.pages.currentWidget(),overview);self.assertEqual(w.home.project_id,self.key)
        w.journal.question.clear();overview.cards[0].click()
        self.assertEqual(w.home.project_id,other);self.assertIs(w.home.pages.currentWidget(),w.home.detail)
        w.show_home();overview.search.clear();overview.archive.click()
        self.assertEqual([c.accessibleName() for c in overview.cards],['Archived'])
        overview.cards[0].click();self.assertTrue(all(not c.isEnabled() for c in w.journal.add_controls))
        self.assertEqual(len(w.library.all())+len(w.library.all(True)),3)

    def test_independent_journal_and_local_draft(self):
        w=self.window;self.assertFalse(hasattr(w,'workplace'));self.assertEqual(w.home.project_id,self.key)
        w.journal.question.setPlainText('Which evidence?')
        with patch('projects_journal_ui.QProcess.startDetached',return_value=(True,1)) as launch:w.journal.ask()
        args=launch.call_args.args[1];self.assertIn('--draft',args);self.assertNotIn('--prompt',args)
        self.assertEqual(w.library.get(self.key)['notes'],'Keep me');self.assertEqual(w.projects.items(self.key),[])
    def test_edit_button_opens_project_and_saves(self):
        w=self.window;w.show();self.app.processEvents()
        import sys
        with patch.object(sys,'excepthook') as errors:
            w.journal.edit.click();self.app.processEvents()
        self.assertTrue(w.project_dialog.isVisible())
        errors.assert_not_called()
        w.project_dialog.title.setText('Edited through button');w.project_dialog.save()
        self.assertEqual(w.library.get(self.key)['title'],'Edited through button')

    def test_content_dialog_and_permanent_folder(self):
        from PySide6.QtWidgets import QFileDialog
        w=self.window;w.show();self.app.processEvents();journal=w.journal
        journal.tabs.setCurrentIndex(1);journal.add_source.click();self.app.processEvents()
        dialog=w.project_dialog;self.assertTrue(dialog.isVisible())
        choice=dialog.kind
        self.assertEqual({choice.itemData(i) for i in range(choice.count())},{'file','folder','url','wissen'})
        choice.setCurrentIndex(choice.findData('folder'))
        folder=self.root/'linked';folder.mkdir()
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(folder)):dialog.choose()
        self.assertEqual(w.library.get(self.key)['resources'],[])
        dialog.save();resource=w.library.get(self.key)['resources'][0]
        self.assertEqual(resource,dict(kind='folder',title='linked',target=str(folder)))
        with patch('tools_workbench.open_path') as opened:
            journal.open_material(0);opened.assert_called_once_with(str(folder))
        (folder/'new.txt').write_text('Fresh document')
        self.assertEqual(w.library.get(self.key)['resources'][0],resource)

    def test_server_project_with_local_folder_asks_on_this_device(self):
        w=self.window;folder=self.root/'local';folder.mkdir()
        w.library.update(self.key,server_bound=True,server_role='editor',resources=[dict(kind='folder',target=str(folder),title='Local')])
        w.home.refresh();w.journal.question.setPlainText('What does the folder say?')
        with patch('projects_journal_ui.QProcess.startDetached',return_value=(True,1)) as launch,patch('projects_question_ui.ProjectQuestion') as server_dialog:
            w.journal.ask()
        launch.assert_called_once();server_dialog.assert_not_called()
        self.assertIn('--draft',launch.call_args.args[1])

    def test_assignment_types_follow_the_current_view(self):
        journal=self.window.journal
        expected=[{'file','folder','url','note','chat','task'},{'file','folder','url','note'},{'chat'},{'analysis','research'},{'task'}]
        for index,kinds in enumerate(expected):
            journal.tabs.setCurrentIndex(index)
            self.assertEqual({a.data() for a in journal.source_actions if a.isVisible()},kinds)
        journal.tabs.setCurrentIndex(1)
        with patch.object(self.window.reference_pane,'pick') as pick,self.assertRaises(ValueError):journal.pick_reference('task')
        pick.assert_not_called()
        journal.tabs.setCurrentIndex(2)
        with patch.object(self.window,'add_files') as add,self.assertRaises(ValueError):journal.add_files()
        add.assert_not_called()
        journal.tabs.setCurrentIndex(3)
        with patch.object(self.window,'create_task') as create:
            journal.source_actions[-1].trigger();create.assert_called_once_with('research')
        self.window.library.archive(self.key,True);self.window.home.refresh()
        self.assertTrue(all(not a.isEnabled() for a in journal.source_actions))
    def test_server_style_views_keep_question_and_open_project_material(self):
        w=self.window
        parent=w.projects.add(self.key,'','Milestone','initiative')
        analysis=w.projects.add(self.key,parent,'Compare evidence','analysis')
        w.projects.add(self.key,parent,'Book meeting','manual')
        w.library.update(self.key,resources=[dict(kind='url',title='Source link',target='https://example.org')],references=[dict(kind='chat',title='Planning conversation',chat=dict(directory=str(self.root),session='ses_test'))])
        w.focus_record(self.key);w.editor.hide();journal=w.journal
        journal.question.setPlainText('Keep this question across tabs')
        for index,titles in [(1,['Source link']),(2,['Planning conversation']),(3,['Compare evidence']),(4,['Compare evidence','Book meeting'])]:
            previous=journal.main_box.itemAt(0).widget()
            journal.tabs.setCurrentIndex(index)
            self.assertTrue(previous.isHidden())
            self.assertEqual(set(journal.visible_titles),set(titles))
            self.assertEqual(journal.question.toPlainText(),'Keep this question across tabs')
        w.library.update(self.key,notes='Updated note');w.home.refresh()
        self.assertEqual(journal.view,'tasks')
        w.navigate(self.key,analysis)
        with patch.object(w,'open_resource_value') as opened:
            journal.open_material(0);opened.assert_called_once()
        self.assertEqual(w.scope,analysis)
        journal.tabs.setCurrentIndex(1)
        with patch.object(w.editor,'allow_leave',return_value=False),patch.object(w,'add_files') as add:
            journal.add_files();add.assert_not_called()
        w.library.archive(self.key,True);w.home.refresh()
        self.assertTrue(all(not control.isEnabled() for control in journal.add_controls))
    def test_journal_notes_uses_current_material_picker(self):
        self.window.journal.add_note()
        self.assertEqual(self.window.project_dialog.kind.currentData(),'wissen')
        self.assertFalse(self.window.editor.isVisible())
    def test_real_cli_parser_accepts_draft_and_session_separately(self):
        import ast,argparse,sys
        tree=ast.parse((Path(__file__).resolve().parents[1]/'agent-app/main.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        end=next(i for i,n in enumerate(function.body) if isinstance(n,ast.ImportFrom) and n.module=='lumen_migrate')
        function.body=function.body[:end]+[ast.Return(value=ast.Name(id='args',ctx=ast.Load()))]
        module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]));namespace=dict(argparse=argparse,Path=Path,tr=lambda x:x)
        exec(compile(module,'main.py','exec'),namespace)
        for args in (['--draft','Do not send'],['--directory',str(self.root),'--session','ses_existing']):
            with patch.object(sys,'argv',['lumen',*args]):parsed=namespace['main']()
            self.assertTrue(parsed.draft or parsed.session)
        with patch.object(sys,'argv',['lumen','--draft','Question','--session','ses_existing']),self.assertRaises(SystemExit):namespace['main']()
    def test_native_journal_preserves_editor_and_archived_permissions(self):
        w=self.window;parent=w.projects.add(self.key,'','Milestone','initiative');task=w.projects.add(self.key,parent,'Compare','analysis',goal='Compare evidence')
        w.navigate(self.key,task);self.assertTrue(w.editor.is_task())
        w.navigate(self.key);w.editor.hide();w.library.archive(self.key,True);w.home.refresh()
        self.assertTrue(all(not x.isEnabled() for x in w.journal.add_controls))
    def test_bound_project_uses_explicit_source_dialog(self):
        w=self.window;w.library.update(self.key,server_bound=True,server_role='manager');w.focus_record(self.key);w.journal.question.setPlainText('A server question')
        with patch('projects_question_ui.ProjectQuestion') as dialog,patch('projects_journal_ui.QProcess.startDetached') as launch:
            w.journal.ask();dialog.assert_called_once_with(w.journal,'A server question');dialog.return_value.show.assert_called_once();launch.assert_not_called()
        self.assertEqual(w.journal.question.toPlainText(),'A server question')
    def test_legacy_room_keeps_bound_identity_and_references_once(self):
        from projects_legacy import migrate
        w=self.window
        with w.library.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS project_rooms(project TEXT PRIMARY KEY,room TEXT UNIQUE)');db.execute('INSERT INTO project_rooms VALUES(?,?)',(self.key,'legacy'))
        room=dict(id='legacy',name='Old',note='Room note',state={},sources=[dict(location='/tmp/evidence.txt')],pins=[])
        with patch('projects_legacy.Catalog') as catalog:
            catalog.return_value.rooms.return_value=[room]
            self.assertEqual(migrate(w.library,w.project_store),[self.key]);self.assertEqual(migrate(w.library,w.project_store),[])
        self.assertEqual(len(w.library.all()),1);value=w.library.get(self.key)
        self.assertEqual(value['notes'],'Keep me\n\nRoom note');self.assertEqual(value['resources'][0]['target'],'/tmp/evidence.txt')
if __name__=='__main__':unittest.main()

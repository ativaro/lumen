import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent,QTime
from PySide6.QtWidgets import QComboBox,QDialog,QMessageBox
from code_blocks import node,encode
from code_library import Collection
from code_triggers import Triggers
from lumen_store import Store

class TriggerUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.env=patch.dict(os.environ,{'LUMEN_DATA':cls.tmp.name+'/data','LUMEN_TOOLS_DATA':cls.tmp.name+'/tools','XDG_CONFIG_HOME':cls.tmp.name+'/config','QT_QPA_PLATFORM':'offscreen','LUMEN_LANGUAGE':'de'})
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def dispose(self,w):
        if hasattr(w,'editor'):w.editor.shutdown()
        w.done(0);w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_all_triggers_are_editable_and_clock_survives_source_change(self):
        from code_sections_editor import SectionsEditor
        from code_clock_editor import ClockEditor
        w=SectionsEditor();self.addCleanup(lambda:(w.shutdown(),w.close()))
        def choose(accessible,value):
            c=next(c for c in w.findChildren(QComboBox) if c.accessibleName()==accessible and c.findData(value)>=0)
            index=c.findData(value);c.setCurrentIndex(index);c.activated.emit(index)
        choose('Auslöser','clock');clock=w.findChild(ClockEditor);clock.time.setTime(QTime(9,15))
        choose('Eingabequelle','project')
        source=json.loads(w.plan()['nodes'][0]['config']);self.assertEqual(source['trigger']['clock']['time'],'09:15');self.assertEqual(source['kind'],'project')
        choose('Auslöser','directory');self.assertEqual(json.loads(w.plan()['nodes'][0]['config'])['trigger']['kind'],'directory')
        choose('Auslöser','project');self.assertEqual(json.loads(w.plan()['nodes'][0]['config'])['kind'],'project')

    def test_creation_and_edit_have_same_interval_and_directory_schedule(self):
        from code_creation_forms import RoutineForm
        from code_edit_window import EditDialog
        from code_flow import parse
        with tempfile.TemporaryDirectory() as tmp:
            from code_clock import default
            from code_flow import encode
            for kind in ('interval','directory'):
                plan=dict(trigger=kind,minutes=30,watch=tmp if kind=='directory' else '',cron='',timezone='Europe/Zurich',steps=[dict(title='Prüfen',prompt='Offene Punkte finden')],condition='always',outputs=['notify'],source_ids=[],service_ids=[])
                if kind!='directory':plan['clock']={**default(),'kind':kind,'minutes':30}
                c=Collection(Store(Path(tmp)/kind));e=c.create('automation','Prüfen',value={'flow':encode(plan),'directory':tmp});plan=parse(e['definition']['flow'])
                self.assertEqual(plan['trigger'],kind);self.assertEqual(plan['minutes'],30)
                w=EditDialog(c,e,schedule=True);self.assertEqual(w.clock_kind.currentData(),kind);self.assertEqual(w.interval.value(),30);self.assertEqual(parse(w.validated()['definition']['flow'])['trigger'],kind);self.dispose(w)

    def test_activation_failed_timer_pause_and_save_invalidate(self):
        from code_clock import default
        from code_blocks_window import BlockWindow
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'alpha','trigger':{'kind':'clock','clock':{**default(),'kind':'daily'}}})),node('filter_text','alpha')]}
            e=c.create('automation','Prüfen',value={'flow':encode(plan)});w=BlockWindow(c,e['id']);self.addCleanup(self.dispose,w)
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes),patch('lumen_actions.command',side_effect=RuntimeError('not running')):
                with self.assertRaisesRegex(ValueError,'pausiert'):w.toggle_trigger()
            self.assertFalse(Triggers(c).get(e['id'])['enabled'])
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes),patch('lumen_actions.command'):w.toggle_trigger()
            self.assertTrue(Triggers(c).get(e['id'])['enabled']);w.editor.items[-1]['config']='beta';w.changed();w.save();self.assertFalse(Triggers(c).get(e['id'])['enabled'])

    def test_current_project_append_preserves_data_and_read_only_rights(self):
        from tools_data import Library
        from code_blocks_run import Runs
        from test_code_triggers import Job
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_TOOLS_DATA':tmp+'/tools'}):
            lib=Library('workbench');key=lib.create('Ziel',kind='project',notes='Vorhanden',goal='Erhalten')
            c=Collection(Store(tmp));plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'Neuer Punkt'})),node('project_note','workbench:'+key)]}
            e=c.create('automation','Ergänzen',value={'flow':encode(plan)});r=Runs(c);run=r.create(e['id'],False);r.resume(run['id'])
            r.advance(run['id'],Job());r.advance(run['id'],Job());self.assertEqual(r.get(run['id'])['status'],'completed');self.assertIn('Neuer Punkt',lib.get(key)['notes']);self.assertEqual(lib.get(key)['goal'],'Erhalten')
            lib.update(key,server_bound=True,server_role='reader');run=r.create(e['id'],False);r.resume(run['id']);r.advance(run['id'],Job());r.advance(run['id'],Job());self.assertEqual(r.get(run['id'])['status'],'error')

    def test_folded_steps_show_current_edited_instruction_and_title(self):
        from code_sections_editor import SectionsEditor
        w=SectionsEditor();self.addCleanup(lambda:(w.shutdown(),w.close()))
        step=next(n for n in w.items if n['kind']=='ai');toggle,preview=w.fold_views[step['id']]
        toggle.setChecked(True);w.update_node(step,'config','Prüfe auch den Betrag');w.update_node(step,'title','Beleg prüfen');toggle.setChecked(False)
        self.assertEqual(preview.text(),'Prüfe auch den Betrag');self.assertIn('Beleg prüfen',toggle.text())

    def test_tool_shortcut_uses_same_new_routine_and_preserves_frozen_instruction(self):
        from code_library_window import CollectionWindow
        from code_creation import CreationDialog
        from code_block_paths import config
        with tempfile.TemporaryDirectory() as tmp:
            w=CollectionWindow(Store(tmp));self.addCleanup(w.close);tool=w.collection.create('tool','Prüfen',value={'prompt':'Nenne fehlende Angaben'});w.current=tool
            def accept(dialog):
                form=dialog.forms['routine'];form.items[0]['config']=json.dumps({**config(form.items[0]),'text':'Beispiel'});form.refresh();dialog.review();return QDialog.Accepted
            with patch.object(CreationDialog,'exec',accept),patch.object(w,'open_entry') as opened:w.new_routine()
            saved=w.collection.get(opened.call_args.args[0]);self.assertEqual(saved['definition']['editor'],'routine')
            plan=json.loads(saved['definition']['flow']);self.assertIn('Nenne fehlende Angaben',[n['config'] for n in plan['nodes']])

if __name__=='__main__':unittest.main()

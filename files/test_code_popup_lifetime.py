"""Real popup mouse selection runs in children so a native crash fails the test."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PopupLifetimeTest(unittest.TestCase):
    def check(self,scenario):
        with tempfile.TemporaryDirectory(prefix='lumen-popup-test-') as root:
            env=dict(os.environ,HOME=root,QT_QPA_PLATFORM='offscreen',LUMEN_LANGUAGE='de',LUMEN_OPENCODE_BIN='/nonexistent/test-engine',LUMEN_CRASH_CHILD='1')
            for name,folder in [('LUMEN_DATA','state'),('LUMEN_TOOLS_DATA','tools'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','xdg-state'),('XDG_RUNTIME_DIR','runtime')]:
                env[name]=str(Path(root)/folder);Path(env[name]).mkdir(mode=0o700)
            result=subprocess.run([sys.executable,'-B','-X','faulthandler',str(Path(__file__).resolve()),'--child',scenario],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            self.assertIn('popup-survived',result.stdout)

    def test_creation_time_popup_save_reopen_and_cancel(self):self.check('creation')
    def test_creation_source_popup_preserves_time(self):self.check('source')
    def test_routine_trigger_popup(self):self.check('routine-trigger')
    def test_routine_add_action_popup(self):self.check('routine-action')
    def test_native_start_popup_keeps_controls_alive(self):self.check('native')
    def test_retired_widget_lives_until_deferred_delete(self):self.check('lifetime')


def child(scenario):
    import traceback
    from PySide6.QtCore import Qt,QPoint,QTimer,QTime,QCoreApplication,QEvent
    from PySide6.QtTest import QTest,QSignalSpy
    from PySide6.QtWidgets import QComboBox,QApplication,QDialog,QScrollArea,QWidget
    from app import create_app
    from code_creation import CreationDialog
    from code_clock_editor import ClockEditor
    from code_block_paths import config
    app=create_app();app.setStyle('Fusion');errors=[]

    def choose(control,value):
        import shiboken6
        activated=QSignalSpy(control.activated);alive=[]
        control.activated.connect(lambda *_:alive.append(shiboken6.isValid(control)))
        QTest.mouseClick(control,Qt.LeftButton,pos=QPoint(control.width()-8,control.height()//2));QTest.qWait(150)
        view=control.view();assert view.isVisible()
        index=control.model().index(control.findData(value),0);assert index.isValid();view.scrollTo(index)
        print('popup '+scenario+' '+str(value),flush=True)
        point=view.visualRect(index).center();QTest.mouseMove(view.viewport(),point);QTest.qWait(20)
        QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=point)
        assert activated.count()==1 and alive==[True];assert QApplication.activePopupWidget() is None
        QTest.qWait(10)

    if scenario=='native':
        from lumen_workspace import PlanDialog
        d=PlanDialog(None,{'name':'Synthetic','steps':[{'action':'diagnose'}],'roots':[os.environ['HOME']]},workflow=True)
        def native():
            try:
                modal=QApplication.activeModalWidget();combo=next(c for c in modal.findChildren(QComboBox) if c.findData('interval')>=0)
                choose(combo,'interval');assert combo.currentData()=='interval';modal.reject()
            except BaseException:errors.append(traceback.format_exc());QApplication.activeModalWidget().done(0)
        d.show();QTimer.singleShot(10,native);d.native_sentence.start();d.done(0)
    elif scenario=='lifetime':
        import shiboken6
        import weakref
        from code_sections_editor import SectionsEditor
        e=SectionsEditor();scroll=QScrollArea();old=QWidget();scroll.setWidget(old);reference=weakref.ref(old)
        e.replace_content(scroll,QWidget());assert shiboken6.isValid(old);del old
        assert reference() is not None and shiboken6.isValid(reference())
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        assert reference() is None or not shiboken6.isValid(reference());assert shiboken6.isValid(scroll.widget());e.shutdown();e.close();scroll.close()
    else:
        d=CreationDialog(kind='routine' if scenario.startswith('routine') else 'automation');e=d.forms[d.kind]
        if scenario=='source':
            from code_clock import default
            e.items[0]['config']=json.dumps({'kind':'text','text':'','trigger':{'kind':'clock','clock':default()}});e.refresh()
        def combo(name):return next(c for c in e.findChildren(QComboBox) if c.accessibleName()==name and c.isVisible())
        def exercise():
            try:
                if scenario=='routine-action':
                    before=len(e.items);choose(combo('Aktion hinzufügen'),'notify');assert len(e.items)==before+1
                elif scenario=='routine-trigger':
                    for kind in ('manual','clock','manual','clock'):choose(combo('Auslöser'),kind)
                    assert config(e.items[0])['trigger']['kind']=='clock'
                else:
                    original=e.plan(False);e.open_detail('input');QTest.qWait(10)
                    if scenario!='source':
                        for kind in ('clock','manual','clock'):choose(combo('Auslöser'),kind)
                    clock=e.findChild(ClockEditor);choose(clock.kind,'daily');clock.time.setTime(QTime(9,15))
                    if scenario=='source':
                        choose(combo('Eingabequelle'),'file');assert config(e.items[0])['kind']=='file';assert config(e.items[0])['trigger']['clock']['time']=='09:15'
                        e.dialog.reject();assert e.plan(False)==original
                    else:
                        e.dialog_apply.click();e.choose_action('notify',e.items,0);e.dialog_apply.click();d.review_button.click();assert d.result()==QDialog.Accepted
            except BaseException:errors.append(traceback.format_exc())
            finally:
                if d.isVisible():d.done(0)
        QTimer.singleShot(10,exercise);d.exec()
        if scenario=='creation' and not errors:
            from lumen_store import Store
            from code_library import Collection
            from code_blocks_window import BlockWindow
            c=Collection(Store(os.environ['LUMEN_DATA']));v=d.value;entry=c.create(v['kind'],v['title'],v['description'],v['definition'],v['project_id'])
            reopened=BlockWindow(c,entry['id']);reopened.show();reopened.editor.open_detail('input');QTest.qWait(10)
            clock=reopened.editor.findChild(ClockEditor);assert clock.value()['kind']=='daily' and clock.value()['time']=='09:15'
            choose(clock.kind,'monthly');reopened.editor.dialog.reject();assert c.get(entry['id'])==entry;assert reopened.editor.plan(False)==json.loads(entry['definition']['flow']);assert c.store.workflows()==[];reopened.reject()
        e.shutdown();d.done(0)
    assert not errors,'\n'.join(errors)
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    print('popup-survived '+scenario,flush=True)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--child':
        import resource
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));child(sys.argv[2])
    else:unittest.main()

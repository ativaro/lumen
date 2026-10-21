"""A clicked Notes link needs a current native file confirmation before dispatch."""
import json,os,tempfile,threading,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import unittest

from PySide6.QtCore import QObject,QTimer,QUrl
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox,QWidget
from server_app_session import AppSession,Binding,SessionError
from server_app_window import BoundPage,QWebEnginePage
from interop_data import Registry
import server_notes_links as links


class FileLinksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['LUMEN_IMPORT_FIXTURES']);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'Original.txt';self.path.write_text('Own selected original')
        self.env=patch.dict(os.environ,LUMEN_TOOLS_DATA=str(self.root/'tools'));self.env.start();self.addCleanup(self.env.stop)
        self.registry=Registry();self.config=dict(server='https://synthetic.invalid',device_id=str(uuid4()),token='NEVER_RENDER_TOKEN')
        self.stamp=('original',);self.revision=7;self.caps=['notes','drive'];self.gui_thread=threading.get_ident()
        self.binding=Binding(self.config['server'],str(uuid4()),self.config['device_id'],'notes')
        self.w=QWidget();self.w._binding=self.binding;self.w._generation=0;self.w._disposed=False;self.w._closing=False
        self.w._live=True;self.w._loaded=True;self.w._import_close=False;self.w._import_running=False;self.w._worker=None
        self.w._import_destroyed=threading.Event();self.w.destroyed.connect(self.w._import_destroyed.set)
        self.w.session=AppSession(self.config,self.binding);self.w.session._cookie=b'x'*43
        self.w.session._deadline=self.w.session._clock()+600;self.w.session.state='ready';self.w.session.access='read'
        self.w.page=QWidget(self.w);self.w.profile=QObject(self.w);self.w.view=QWidget(self.w);self.w.view.page=lambda:self.w.page
        self.w._cookie_valid=lambda:True;self.addCleanup(self.w.deleteLater)
        self.ref=dict(app='files',kind='file',id=str(self.path),title=self.path.name,path=str(self.path))
        self.url=self.registry.register(self.ref);self.dispatch=[];self.warnings=[];self.confirmed=[];self.accept=True;self.before_confirm=lambda:None
        self.drive_ref=dict(app='files',kind='drive_file',id=str(uuid4()),title='Drive original.txt',locator=dict(server=self.binding.origin,account=self.binding.account))
        self.row=dict(id=str(uuid4()),family=self.drive_ref['id'],version=1,revision=1,size=5,sha256='a'*64,name='Drive original.txt',folder_id=str(uuid4()),current=True,trashed=False)
        self.folder=dict(id=self.row['folder_id'],revision=1,name='Own folder',parent_id=None,trashed=False)
        self.cache=dict(files={self.drive_ref['id']:self.row},folders={self.folder['id']:self.folder})
        for p in (patch('server_app_window._connection',side_effect=lambda:(dict(self.config),self.stamp)),
                  patch.object(AppSession,'check',return_value=True),
                  patch.object(links.lumen_connect,'read_config',side_effect=lambda:dict(self.config)),
                  patch.object(links.lumen_connect,'request',side_effect=self.profile),
                  patch.object(links.drive.sync,'inventory',side_effect=lambda *a,**k:self.cache),
                  patch.object(links,'open_url',side_effect=lambda url:self.dispatch.append(self.registry.resolve(url))),
                  patch.object(QMessageBox,'warning',side_effect=lambda _w,_title,text:self.warnings.append(text))):
            p.start();self.addCleanup(p.stop)
        self.controller=links.controller(self.w)
        self.timer=QTimer();self.timer.setInterval(5);self.timer.timeout.connect(self.answer);self.timer.start();self.addCleanup(self.timer.stop)

    def profile(self,config,path,body=None,**kwargs):
        self.assertNotEqual(threading.get_ident(),self.gui_thread)
        self.assertEqual(path,'/bridge/me')
        return dict(id=self.binding.account,device_id=self.binding.device,capabilities=self.caps[:],permissions_revision=self.revision)

    def answer(self):
        dialog=QApplication.activeModalWidget()
        if not isinstance(dialog,QMessageBox) or dialog.windowTitle()!='Lumen Files · Verknüpfung öffnen' or dialog.property('answered'):return
        dialog.setProperty('answered',True);self.confirmed.append(dialog.text())
        self.assertEqual(dialog.textFormat(),__import__('PySide6.QtCore',fromlist=['Qt']).Qt.PlainText)
        self.assertEqual(dialog.defaultButton(),dialog.button(QMessageBox.Cancel))
        self.assertNotIn(self.config['token'],dialog.text())
        self.before_confirm();dialog.button(QMessageBox.Yes if self.accept else QMessageBox.Cancel).click()

    def invoke(self,url=None):
        context=links.Context(self.w,self.w.page,self.w.profile,self.w.view,self.w.session,self.binding,
            self.w._generation,self.w.session._generation,self.stamp,self.w._import_destroyed,self.gui_thread)
        self.controller.pending=True
        self.controller.open(context,url or self.url)
        self.assertFalse(self.controller.pending)
        self.assertFalse(self.w._import_running)

    def test_registered_local_original_dispatches_only_after_plain_native_confirmation(self):
        self.invoke();self.assertEqual(self.dispatch,[self.ref]);self.assertEqual(len(self.confirmed),1);self.assertEqual(self.warnings,[])
        self.assertEqual(self.path.read_text(),'Own selected original')

    def test_cancel_keeps_original_and_never_dispatches(self):
        self.accept=False;self.invoke();self.assertEqual(self.dispatch,[]);self.assertEqual(len(self.confirmed),1)

    def test_sameorigin_drive_version_maps_to_current_family_and_files_dispatcher(self):
        self.invoke(self.binding.origin+'/?app=files&file='+self.row['id']);self.assertEqual(self.dispatch,[self.drive_ref])
        self.assertIn('Lumen Drive',self.confirmed[0])

    def test_registered_drive_folder_maps_to_files_without_download(self):
        ref=dict(self.drive_ref,kind='drive_folder',id=self.folder['id'],title=self.folder['name'])
        self.invoke(self.registry.register(ref));self.assertEqual(self.dispatch,[ref])

    def test_registered_directory_uses_existing_file_reference(self):
        ref=dict(self.ref,id=str(self.root),path=str(self.root),title='Own directory')
        self.invoke(self.registry.register(ref));self.assertEqual(self.dispatch,[ref])

    def test_external_schemes_raw_paths_handoff_and_other_apps_never_dispatch(self):
        invalid=['file://'+str(self.path),str(self.path),'ssh://host','javascript:alert(1)',
                 'http://synthetic.invalid/?app=files&file='+self.row['id'],'lumen://handoff/'+uuid4().hex,
                 'https://foreign.invalid/?app=files&file='+self.row['id'],self.binding.origin+'/?app=files&file='+self.row['id']+'&token=x',
                 self.binding.origin+'/?app=files&file='+self.row['id']+'#fragment',self.binding.origin+'/?app=files&file=bad']
        for url in invalid:
            with self.subTest(url=url):self.invoke(url)
        note=dict(app='wissen',kind='note',id='fake.md',title='No native Notes')
        self.invoke(self.registry.register(note));self.assertEqual(self.dispatch,[]);self.assertEqual(self.confirmed,[])

    def test_foreign_account_or_origin_drive_reference_never_dispatches(self):
        for key,value in (('account',str(uuid4())),('server','https://foreign.invalid')):
            ref=dict(self.drive_ref,locator=dict(self.drive_ref['locator'],**{key:value}))
            self.invoke(self.registry.register(ref))
        self.assertEqual(self.dispatch,[]);self.assertEqual(self.confirmed,[])

    def test_drive_permission_is_required_but_not_added_for_original(self):
        self.caps=['notes'];self.invoke(self.registry.register(self.drive_ref));self.assertEqual(self.dispatch,[])
        self.assertEqual(self.caps,['notes']);self.invoke();self.assertEqual(self.dispatch,[self.ref])

    def test_permission_revision_change_during_confirmation_blocks_dispatch(self):
        self.before_confirm=lambda:setattr(self,'revision',8);self.invoke();self.assertEqual(self.dispatch,[]);self.assertEqual(len(self.confirmed),1)

    def test_config_change_during_confirmation_blocks_dispatch(self):
        self.before_confirm=lambda:setattr(self,'stamp',('changed',));self.invoke();self.assertEqual(self.dispatch,[])

    def test_page_or_generation_change_during_confirmation_blocks_dispatch(self):
        for change in (lambda:setattr(self.w,'_generation',1),lambda:setattr(self.w,'page',QWidget(self.w))):
            self.w._generation=0;self.before_confirm=change;self.invoke();self.assertEqual(self.dispatch,[])

    def test_drive_version_changed_during_confirmation_is_not_silently_rebased(self):
        url=self.binding.origin+'/?app=files&file='+self.row['id']
        self.before_confirm=lambda:self.row.update(id=str(uuid4()),version=2,revision=2)
        self.invoke(url);self.assertEqual(self.dispatch,[])

    def test_local_path_replaced_during_confirmation_is_not_opened(self):
        def replace():
            other=self.root/'other.txt';other.write_text('replacement');other.replace(self.path)
        self.before_confirm=replace;self.invoke();self.assertEqual(self.dispatch,[])

    def test_singleflight_keeps_second_native_request_out_of_the_active_review(self):
        self.before_confirm=self.controller.current_sources
        self.invoke();self.assertEqual(len(self.confirmed),1);self.assertEqual(self.dispatch,[self.ref])

    def test_changed_token_before_click_cannot_bind_old_page_to_new_connection(self):
        self.config['token']='REPLACED_TOKEN';self.invoke();self.assertEqual(self.dispatch,[]);self.assertEqual(self.confirmed,[])

    def test_malformed_drive_metadata_fails_before_confirmation(self):
        for key,value in (('size','5'),('sha256',None),('id',None),('name',None)):
            old=self.row[key];self.row[key]=value
            self.invoke(self.registry.register(self.drive_ref));self.row[key]=old
        self.assertEqual(self.dispatch,[]);self.assertEqual(self.confirmed,[])

    def test_worker_guard_never_calls_qt_proof_and_gui_guard_rejects_worker(self):
        context=links.Context(self.w,self.w.page,self.w.profile,self.w.view,self.w.session,self.binding,0,0,self.stamp,self.w._import_destroyed,self.gui_thread)
        outcomes=[]
        def worker():
            with patch.object(self.w,'_cookie_valid',side_effect=AssertionError('Worker accessed Qt cookie proof')):
                context.check();outcomes.append('native guard')
                try:context.gui()
                except SessionError:outcomes.append('gui rejected')
        thread=threading.Thread(target=worker);thread.start();thread.join(timeout=2)
        self.assertEqual(outcomes,['native guard','gui rejected'])

    def receipt(self,note_id,payload=None):
        payload=payload or dict(title='Own import',source=self.ref,source_url=self.url,paths=[],references=[self.drive_ref])
        token=self.registry.enqueue('wissen','wissen.import',payload);self.registry.claim(token,'wissen')
        ref=dict(version=2,app='note',id=note_id,title='Own note',locator=dict(server=self.binding.origin,account=self.binding.account))
        self.registry.finish(token,self.registry.register(ref))

    def known_sources(self,note_id):
        from concurrent.futures import ThreadPoolExecutor
        context=links.Context(self.w,self.w.page,self.w.profile,self.w.view,self.w.session,self.binding,0,0,self.stamp,self.w._import_destroyed,self.gui_thread)
        with ThreadPoolExecutor(max_workers=1) as pool:return pool.submit(links.sources,context,note_id,SimpleNamespace(check=lambda:None)).result(timeout=3)

    def test_sources_use_only_authorized_current_note_and_committed_receipt(self):
        note_id=str(uuid4());self.receipt(note_id)
        with patch.object(self.w.session,'request',return_value=dict(id=note_id,kind='note',deleted=False,title='Own note')) as request:
            title,rows=self.known_sources(note_id)
        self.assertEqual(title,'Own note');self.assertEqual([row['reference'] for row in rows],[self.ref,self.drive_ref])
        request.assert_called_once_with('/api/documents/'+note_id,max_bytes=1024**2)

    def test_sources_do_not_parse_body_links_or_reuse_another_notes_receipt(self):
        self.receipt(str(uuid4()));note_id=str(uuid4())
        with patch.object(self.w.session,'request',return_value=dict(id=note_id,kind='note',deleted=False,title='Server note',body=self.url)):
            self.assertEqual(self.known_sources(note_id),('Server note',[]))

    def test_sources_reject_wrong_note_response_and_revocation(self):
        note_id=str(uuid4());self.receipt(note_id)
        with patch.object(self.w.session,'request',return_value=dict(id=str(uuid4()),kind='note',deleted=False,title='Foreign')):
            with self.assertRaises(ValueError):self.known_sources(note_id)
        def revoked(*a,**k):
            self.caps=[];return dict(id=note_id,kind='note',deleted=False,title='Own')
        with patch.object(self.w.session,'request',side_effect=revoked):
            with self.assertRaises(SessionError):self.known_sources(note_id)

    def test_sources_reject_non_uuid_without_note_request(self):
        with patch.object(self.w.session,'request') as request:
            with self.assertRaises(ValueError):self.known_sources('../../other')
            request.assert_not_called()

    def test_deferred_note_id_reply_does_not_clear_a_newer_import(self):
        callbacks=[];self.w.page.runJavaScript=lambda code,world,callback:callbacks.append(callback)
        self.controller.current_sources();self.assertTrue(self.controller.pending)
        self.w._import_running=True
        with patch.object(links,'sources',side_effect=AssertionError('A different import owns the window')):
            callbacks[0](str(uuid4()))
        self.assertTrue(self.w._import_running);self.assertFalse(self.controller.pending)

    def test_busy_direct_review_does_not_clear_another_import(self):
        context=links.Context(self.w,self.w.page,self.w.profile,self.w.view,self.w.session,self.binding,0,0,self.stamp,self.w._import_destroyed,self.gui_thread)
        self.w._import_running=True;self.controller.open(context,self.url)
        self.assertTrue(self.w._import_running);self.assertEqual(self.confirmed,[])

    def test_navigation_stays_closed_even_for_file_link_clicks(self):
        page=SimpleNamespace(window=self.w);kind=QWebEnginePage.NavigationType
        with patch.object(links.Links,'current_sources') as opened:
            for action in (kind.NavigationTypeOther,kind.NavigationTypeLinkClicked):
                self.assertFalse(BoundPage.acceptNavigationRequest(page,QUrl(self.url),action,True))
            self.assertTrue(BoundPage.acceptNavigationRequest(page,QUrl(self.binding.url),kind.NavigationTypeLinkClicked,True))
            opened.assert_not_called()
        self.assertEqual(self.dispatch,[])

if __name__=='__main__':unittest.main()

class ActualLinkNavigationTest(unittest.TestCase):
    def test_context_menu_and_shift_f10_confirm_original_and_drive_sources(self):
        import test_server_app_window as fixture
        from PySide6.QtCore import QPoint,Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMenu,QListWidget,QDialogButtonBox
        fixture.WindowTest.setUpClass();case=fixture.WindowTest();case.setUp()
        dispatched=[];dialogs=[];menus=[];selections=[0];timer=QTimer()
        try:
            window=case.import_window(app='notes',pilot=True)
            original=case.import_root/'Known.txt';original.write_text('Own original')
            registry=Registry();source=dict(app='files',kind='file',id=str(original),path=str(original),title='Known.txt')
            url=registry.register(source);note_id=str(uuid4());drive_id=str(uuid4())
            row=dict(id=drive_id,family=fixture.FILE,version=1,revision=1,size=5,sha256='a'*64,
                name='Drive source.txt',folder_id=fixture.FOLDER,current=True,trashed=False)
            case.drive_files.append(row)
            dref=dict(app='files',kind='drive_file',id=fixture.FILE,title=row['name'],locator=dict(server=case.origin,account=fixture.USER))
            token=registry.enqueue('wissen','wissen.import',dict(title='Own note',source=source,source_url=url,paths=[],references=[dref]))
            registry.claim(token,'wissen');registry.finish(token,registry.register(dict(version=2,app='note',id=note_id,title='Own note',locator=dict(server=case.origin,account=fixture.USER))))
            window.session.request=lambda *_a,**_k:dict(id=note_id,kind='note',title='Own note',deleted=False)
            case.js(window,"document.querySelector('.knowledge-editor').dataset.documentId="+json.dumps(note_id)+";true")
            def answer():
                menu=QApplication.activePopupWidget()
                if isinstance(menu,QMenu) and not menu.property('clicked'):
                    action=next((a for a in menu.actions() if a.objectName()=='lumen-notes-file-references'),None)
                    if action:
                        menu.setProperty('clicked',True);menus.append(action.text());menu.setActiveAction(action);QTest.keyClick(menu,Qt.Key_Return)
                    return
                dialog=QApplication.activeModalWidget()
                if dialog is None or dialog.property('clicked'):return
                if dialog.windowTitle()=='Lumen Notes · Dateiverweise':
                    dialog.setProperty('clicked',True);listing=dialog.findChild(QListWidget);listing.setCurrentRow(selections[0])
                    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Open).click()
                elif isinstance(dialog,QMessageBox) and dialog.windowTitle()=='Lumen Files · Verknüpfung öffnen':
                    dialog.setProperty('clicked',True);dialogs.append(dialog.text());dialog.button(QMessageBox.Yes).click()
            timer.setInterval(5);timer.timeout.connect(answer);timer.start()
            cookie=window.session._cookie
            with patch('interop_open.launch',side_effect=lambda *args:dispatched.append(args)):
                QTest.mouseClick(window.view.focusProxy() or window.view,Qt.RightButton,pos=QPoint(30,150))
                case.wait(lambda:len(dispatched)==1,timeout=8000)
                selections[0]=1;window.view.setFocus()
                QTest.keyClick(window.view.focusProxy() or window.view,Qt.Key_F10,Qt.ShiftModifier)
                case.wait(lambda:len(dispatched)==2,timeout=8000)
            self.assertEqual(dispatched[0],('files',[str(original),'--select'],None))
            self.assertEqual(dispatched[1][0],'files');self.assertEqual(dispatched[1][1][0],'--ref')
            self.assertEqual(registry.resolve(dispatched[1][1][1]),dref)
            self.assertEqual(len(dialogs),2);self.assertEqual(len(menus),2)
            self.assertEqual(window.session._cookie,cookie);self.assertEqual(original.read_text(),'Own original');self.assertTrue(window._live)
        finally:
            timer.stop();case.tearDown();case.doCleanups();fixture.WindowTest.tearDownClass()

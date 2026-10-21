"""Native, reviewed handoffs and source links shared by Lumen windows."""
from collections import deque
from pathlib import Path
import json
from PySide6.QtCore import Qt,QObject,QTimer,QEvent,QMimeData,QUrl
from lumen_qt import is_deleted
from PySide6.QtWidgets import (QApplication,QDialog,QDialogButtonBox,QVBoxLayout,QFormLayout,
    QLabel,QLineEdit,QPlainTextEdit,QComboBox,QMenu,QListWidget,QListWidgetItem,QInputDialog,QMessageBox,QPushButton,QSizePolicy)
from lumen_i18n import tr
from interop_data import Registry,validate_payload
from interop_open import launch,open_url,focus


def root_for(window):
    return window.library.root.parent if hasattr(window,'library') else None


def capture(window):
    from interop_sources import capture as source_capture
    payload=validate_payload(source_capture(window))
    registry=Registry(root_for(window));payload['source_url']=registry.register(payload['source'])
    return payload


def actions(payload):
    from interop_targets import ACTIONS,available
    source=payload.get('source',{}).get('app')
    result=[(key,tr(ACTIONS[key]['label'])) for key in available(payload)
            if key not in ({'reader.import'} if source=='reader' else {'wissen.import'} if source=='wissen' else set())]
    if payload.get('paths') or payload.get('source',{}).get('app')!='files':
        if source!='vault':result.append(('vault.sources',tr('Sicherung einrichten …')))
    return result


def error(window,message):
    if hasattr(window,'error'):window.error(str(message))
    else:QMessageBox.warning(window,'Lumen',str(message))


def safe_action(window,callback):
    try:return callback()
    except Exception as exc:error(window,exc)


def reviewed_send(window,payload,action=None):
    """Only select a destination here; its live window reviews the actual change."""
    def send(value):
        try:
            options=actions(value)
            if not options:raise ValueError(tr('Für diese Auswahl gibt es noch kein passendes Übergabeziel.'))
            chosen=action
            if not chosen:
                label,ok=QInputDialog.getItem(window,tr('Weitere Aktionen'),tr('Was möchtest du mit der Auswahl tun?'),[v for _,v in options],0,False)
                if not ok:return
                chosen=options[[v for _,v in options].index(label)][0]
            if chosen not in dict(options):raise ValueError(tr('Dieses Ziel unterstützt die Auswahl nicht.'))
            registry=Registry(root_for(window))
            value=validate_payload(value)
            if value.get('source') and not value.get('source_url'):value['source_url']=registry.register(value['source'])
            target=chosen.split('.')[0];token=registry.enqueue(target,chosen,value)
            if getattr(window,'name','')==target:controller(window).enqueue({'handoff':token})
            else:launch(target,['--handoff',token],root_for(window))
            if hasattr(window,'status'):window.status.setText(tr('In {0} fortsetzen.',app_name(target)))
        except Exception as exc:error(window,exc)
    # MIME attachment decoding/file copying is performed in the existing cancellable worker.
    if any(item.get('kind')=='attachment' for item in payload.get('items',[])) and hasattr(window,'work'):
        from interop_sources import materialize
        window.work(tr('Auswahl wird für die Übergabe vorbereitet …'),lambda job:materialize(payload,job,root_for(window)),lambda value:QTimer.singleShot(0,lambda:send(value)))
    else:send(payload)


def send_current(window):
    def proceed():
        try:reviewed_send(window,capture(window))
        except Exception as exc:error(window,exc)
    with_saved(window,proceed)


def with_saved(window,callback):
    if getattr(window,'job',None) or (getattr(window,'engine',None) and window.engine.busy):
        raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
    if getattr(window,'name','')=='wissen':
        if getattr(window,'conflict',False):raise ValueError(tr('Zuerst den Notizkonflikt auflösen oder den Entwurf als Kopie speichern.'))
        window.save_note(callback)
    else:
        if hasattr(window,'save'):window.save()
        callback()


def review(window,request,*,spec=None,rows=None):
    from interop_targets import ACTIONS,choices
    explicit=spec is not None
    action=request['action'];spec=ACTIONS[action] if spec is None else spec;payload=request['payload']
    dialog=QDialog(window);dialog.setWindowTitle(tr(spec['label']));dialog.resize(620,600 if explicit and spec.get('heading') else 520)
    form=QFormLayout(dialog)
    if explicit and spec.get('heading'):
        from desktop_design import AppHeader
        heading=AppHeader(tr(spec['heading']));heading.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed);form.addRow(heading)
    description=QLabel(tr(spec.get('description',spec['label'])));form.addRow(description)
    default_title=payload.get('title','')
    if action=='inbox.task' and payload.get('text','').strip():
        import re
        default_title=re.sub(r'^\s*[-*]\s*\[[ xX]\]\s*','',payload['text'].strip().splitlines()[0])[:300]
    title=QLineEdit(default_title);form.addRow(tr(spec.get('title_label','Titel')),title)
    destination=QComboBox();rows=choices(action,root_for(window),store=getattr(window,'store',None)) if rows is None else rows
    needs_choice=action in ('inbox.draft','inbox.event') or spec.get('requires_choice',False)
    if not needs_choice and action!='wissen.import':destination.addItem(tr('Neues Projekt') if action.startswith('workbench.') else tr('Neuen Eintrag anlegen'),'')
    for row in rows:destination.addItem(row['title'],row['id'])
    if action=='workbench.add' and getattr(window,'name','')=='workbench' and window.current:
        key=window.current+('/'+window.scope if getattr(window,'scope','') else '')
        index=destination.findData(key)
        if index>=0:destination.setCurrentIndex(index)
    if needs_choice and not rows:
        dialog.deleteLater()
        if getattr(window,'name','')=='inbox' and QMessageBox.question(window,tr('Lumen Inbox einrichten'),tr('Für diese Übergabe fehlt ein passendes Konto. Jetzt einrichten und anschließend die Übergabe fortsetzen?'))==QMessageBox.Yes:
            window.account_dialog()
            if choices(action,root_for(window),store=getattr(window,'store',None)):return review(window,request)
        return None
    if rows or needs_choice:
        field={'wissen.import':tr('Notizordner'),'workbench.add':tr('Projekt'),'workbench.question':tr('Projekt'),
               'household.add':tr('Gerät oder Vertrag'),'inbox.draft':tr('Mailkonto'),'inbox.event':tr('Kalender')}.get(action,tr('Speichern in'))
        form.addRow(field,destination)
    mode=QComboBox()
    for key in spec.get('modes',['copy']):
        if payload.get('references') and key!=('link' if action in ('wissen.import','workbench.add') else 'copy'):continue
        if key=='live' and not (payload.get('source',{}).get('app')=='wissen' and payload['source'].get('kind') in ('note','collection')):continue
        mode.addItem({'copy':tr('Eigenständige Kopie speichern'),'link':tr('Link zum Original speichern'),'live':tr('Mit der Originalnotiz aktuell halten')}[key],key)
    if any(Path(p).is_dir() for p in payload.get('paths',[])) and mode.findData('link')>=0:mode.setCurrentIndex(mode.findData('link'))
    if payload.get('references'):
        hint=tr(spec['reference_hint']) if spec.get('reference_hint') else tr('Verknüpfungen zum Drive-Original · keine Dateien werden heruntergeladen.') if action in ('wissen.import','workbench.add') else tr('Lokale Kopie mit Herkunft. Das Drive-Original bleibt unverändert. Änderungen über „Original öffnen“ in Lumen Files mit „Dateien hochladen …“ zurückübertragen.')
        label=QLabel(hint);label.setWordWrap(True);form.addRow(label)
    if mode.count()>1 and (payload.get('paths') or action in ('workbench.add','household.add')):
        form.addRow(tr('Inhalt'),mode)
    task=next((item for item in payload.get('items',[]) if item.get('kind')=='task'),{})
    due=QLineEdit(task.get('due','') if action in ('inbox.task','inbox.event') else '');due.setPlaceholderText('JJJJ-MM-TT')
    if action in ('inbox.task','inbox.event'):form.addRow(tr('Fällig am') if action=='inbox.task' else tr('Datum'),due)
    preview=QPlainTextEdit(payload.get('text',''));preview.setReadOnly(True);preview.setAccessibleName(tr('Inhalt der neuen Notiz') if action=='wissen.import' else tr('Inhalt'))
    if payload.get('text'):form.addRow(preview)
    if explicit and payload.get('paths'):
        source=QPlainTextEdit();source.setReadOnly(True)
        source.setAccessibleName(tr('Gewählte Quelle und Zielordner'));source.setMinimumHeight(112);source.setMaximumHeight(144)
        def details(*_):source.setPlainText(tr('Quelle: {0}\n\n{1}: {2}','\n'.join(payload['paths'][:10]),tr(spec.get('destination_label','Zielordner')),destination.currentText()))
        destination.currentTextChanged.connect(details);details()
        form.addRow(tr('Quelle und Ziel'),source)
    elif payload.get('paths'):
        paths=QLabel('\n'.join(payload['paths'][:10]));paths.setTextFormat(Qt.PlainText);form.addRow(paths)
    from interop_sources import source_title
    if not explicit:
        source=QLabel(tr('Quelle: {0}',source_title(payload.get('source',{}))));source.setTextFormat(Qt.PlainText);form.addRow(source)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
    if action=='wissen.import':buttons.button(QDialogButtonBox.Save).setText(tr('Notiz speichern'))
    if spec.get('save_label'):buttons.button(QDialogButtonBox.Save).setText(tr(spec['save_label']))
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
    if explicit:
        from desktop_design import PAGE_MARGIN,PAGE_SPACING
        form.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN)
        form.setSpacing(PAGE_SPACING);form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.setFormAlignment(Qt.AlignTop)
        destination.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        destination.setMinimumContentsLength(1);destination.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        title.textChanged.connect(title.setToolTip);title.setToolTip(title.text())
        for text in (description,):
            text.setWordWrap(True);text.setTextFormat(Qt.PlainText)
            text.setAlignment(Qt.AlignLeft|Qt.AlignTop)
            text.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Maximum)
    if dialog.exec()!=QDialog.Accepted:return None
    if due.text():
        from datetime import date
        date.fromisoformat(due.text())
    return dict(id=destination.currentData() or '',title=title.text(),mode=mode.currentData(),due=due.text(),token=request['id'])


class Controller(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.queue=deque();self.running=False;self.saving_request=None
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.process)
        if hasattr(window,'name'):
            window.setAcceptDrops(True);window.installEventFilter(self)
            QApplication.instance().focusChanged.connect(self.remember_focus)
        if hasattr(window,'operation_failed'):window.operation_failed.connect(self.save_failed)

    def save_failed(self,message):
        if self.saving_request is None:return
        self.queue.appendleft(self.saving_request);self.saving_request=None;self.running=False
        self.timer.stop()

    def remember_focus(self,old,new):
        from PySide6.QtWidgets import QAbstractButton
        window=getattr(self,'window',None)
        # Qt may emit focus changes while Python is collecting a widget cycle.
        if window is None or is_deleted(window) or new is None or is_deleted(new) or isinstance(new,QAbstractButton):return
        central=window.centralWidget()
        if central and (new is central or central.isAncestorOf(new)):
            window._interop_focus=new

    def enqueue(self,request):
        if not isinstance(request,dict) or set(request)-{'path','ref','handoff','text'}:raise ValueError(tr('Ungültige Übergabe.'))
        if getattr(self.window,'memory_only',False) and set(request)-{'path'}:
            raise ValueError(tr('Dateien und Notizen in der Server-App öffnen. Dieser Editor ist nur für Erinnerungen.'))
        if 'text' in request and getattr(self.window,'name','') != 'translate': raise ValueError(tr('Ungültige Übergabe.'))
        if any(not isinstance(v,str) or len(v)>(12000 if k=='text' else 4096) for k,v in request.items()):raise ValueError(tr('Ungültige Übergabe.'))
        if len(self.queue)>=30:raise ValueError(tr('Zu viele wartende Übergaben.'))
        if request not in self.queue:self.queue.append(request)
        self.timer.start()

    def ready(self):
        w=self.window
        return not (self.running or getattr(w,'job',None) or (getattr(w,'engine',None) and w.engine.busy)
                    or QApplication.activeModalWidget() or (getattr(w,'name','')=='wissen' and (not getattr(w,'book',None) or getattr(w,'conflict',False))))

    def process(self):
        if not self.queue:self.timer.stop();return
        if not self.ready():return
        request=self.queue.popleft();self.running=True;self.saving_request=request
        def proceed():
            self.saving_request=None
            try:self.deliver(request)
            except Exception as exc:
                if request.get('handoff'):Registry(root_for(self.window)).release(request['handoff'],str(exc)[:4000])
                error(self.window,exc)
            finally:self.running=False
        try:with_saved(self.window,proceed)
        except Exception as exc:self.save_failed(str(exc));error(self.window,exc)

    def deliver(self,request):
        if getattr(self.window,'memory_only',False) and set(request)-{'path'}:
            raise ValueError(tr('Dateien und Notizen in der Server-App öffnen. Dieser Editor ist nur für Erinnerungen.'))
        w=self.window;registry=Registry(root_for(w))
        if request.get('ref'):
            focus(w,registry.resolve(request['ref']));return
        if request.get('text'):
            w.open_text(request['text']);return
        if request.get('path'):
            if w.name in ('reader','wissen','translate'):w.open_file(request['path'])
            return
        if not request.get('handoff'):return
        token=request['handoff'];value=registry.request(token)
        if value['target']!=w.name:raise ValueError(tr('Dieser Verweis gehört zu einer anderen Lumen-Anwendung.'))
        if value['state']=='undone':raise ValueError(tr('Diese Übergabe wurde rückgängig gemacht. Für eine neue Übernahme erneut von der Quelle aus starten.'))
        if value['state']=='done':focus(w,registry.resolve(value['result']));return
        if value['action']=='vault.sources':
            from interop_vault import receive_sources
            registry.claim(token,w.name)
            def finished(ref):
                try:
                    if ref:registry.finish(token,registry.register(ref))
                    else:registry.release(token)
                except Exception as exc:
                    registry.release(token,str(exc)[:4000]);error(w,exc)
            try:
                if not receive_sources(w,value['payload'],root=root_for(w),done=finished,token=token):registry.release(token)
            except Exception:
                registry.release(token);raise
            return
        from interop_targets import ACTIONS,apply
        if value['action'] not in ACTIONS or ACTIONS[value['action']]['target']!=w.name:
            raise ValueError(tr('Unbekanntes Übergabeziel.'))
        choice=value.get('choice') or review(w,value)
        if choice is None:return
        registry.save_choice(token,choice)
        registry.claim(token,w.name)
        applied={}
        def done(ref):
            # Reload durable target data even if recording the receipt in the registry fails.
            applied['ref']=ref
            try:url=registry.register(ref);registry.finish(token,url)
            except Exception as exc:
                registry.release(token,str(exc)[:4000]);raise
            w.status.setText(tr('Notiz „{0}“ gespeichert.',ref['title']) if ref['app']=='wissen' else tr('In „{0}“ gespeichert.',ref['title']))
        def failed(message):registry.release(token,str(message)[:4000])
        def finished():
            if applied.get('ref'):focus(w,applied['ref'])
        started=w.work(tr('Auswahl wird übernommen …'),lambda job:apply(value['action'],value['payload'],choice,job,root=root_for(w),store=getattr(w,'store',None)),done,failed=failed,finished=finished)
        if not started:registry.release(token)

    def eventFilter(self,watched,event):
        window=getattr(self,'window',None)
        if window is None or is_deleted(window):return False
        if watched is window and event.type() in (QEvent.DragEnter,QEvent.DragMove,QEvent.Drop):
            mime=event.mimeData()
            if mime.hasUrls() and all(url.isLocalFile() for url in mime.urls()):
                event.acceptProposedAction()
                if event.type()==QEvent.Drop:
                    from interop_sources import from_paths
                    paths=[url.toLocalFile() for url in mime.urls()]
                    timer=QTimer(self);timer.setSingleShot(True)
                    from interop_context import receive_drop
                    timer.timeout.connect(lambda:self.window.safe(lambda:receive_drop(self.window,from_paths(paths))))
                    timer.timeout.connect(timer.deleteLater);timer.start(0)
                return True
        return False


def controller(window):
    if not hasattr(window,'interop_controller'):window.interop_controller=Controller(window)
    return window.interop_controller


def copy_link(window):
    def copy():
        try:QApplication.clipboard().setText(capture(window)['source_url'])
        except Exception as exc:error(window,exc)
    with_saved(window,copy)


def _resume_drive_import(window,row):
    if row['action']!='files.drive_import' or row['state']!='pending':return False
    callback=getattr(window,'_lumen_file_import',None)
    if not callable(callback):raise ValueError(tr('Diese Dateiübernahme benötigt das zugehörige geprüfte Server-App-Fenster.'))
    callback(row['id']);return True


def browse(window,mode='related',payload=None):
    registry=Registry(root_for(window));url=''
    if mode in ('search','related'):
        from interop_catalog import index_local
        from interop_dialogs import run_job
        result=run_job(window,tr('Gespeicherte Lumen-Inhalte werden durchsucht …'),lambda job:index_local(registry,getattr(window,'store',None),job))
        if result is None:return
    if mode in ('related','tags'):
        payload=payload or capture(window);url=payload.get('source_url') or registry.register(payload['source'])
    if mode=='tags':
        text,ok=QInputDialog.getText(window,tr('Gemeinsame Lumen-Tags'),tr('Tags mit Komma trennen'),text=', '.join(registry.tags(url)))
        if ok:registry.set_tags(url,[v.strip() for v in text.split(',') if v.strip()])
        return
    dialog=QDialog(window);dialog.setWindowTitle(tr('Lumen Verbindungen'));dialog.resize(720,520)
    layout=QVBoxLayout(dialog);query=QLineEdit();query.setPlaceholderText(tr('Suchen oder #Tag eingeben'));layout.addWidget(query)
    if mode=='history':
        from desktop_design import PAGE_MARGIN,PAGE_SPACING
        layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
    listing=QListWidget();listing.setAccessibleName(tr('Verknüpfte Lumen-Inhalte'));layout.addWidget(listing)
    def refresh():
        listing.clear()
        if mode=='history':
            rows=registry.history()
            for row in rows:
                from datetime import datetime
                imported=row['action']=='files.drive_import'
                action=tr('Datei nach Lumen Drive übernehmen') if imported else row['action']
                item=QListWidgetItem(datetime.fromtimestamp(row['created']).strftime('%d.%m. %H:%M')+' · '+action+('\n' if imported else ' · ')+{'pending':tr('Wartet auf Übernahme'),'applying':tr('Wird übernommen'),'done':tr('Übernommen'),'undone':tr('Rückgängig gemacht')}[row['state']]);item.setData(Qt.UserRole,row['result'] or 'lumen://handoff/'+row['id']);item.setData(Qt.UserRole+1,row);item.setToolTip(row['error']);listing.addItem(item)
        else:
            rows=registry.related(url) if mode=='related' and not query.text() else registry.search(query.text())
            for ref in rows:
                item=QListWidgetItem(ref['title']+' · '+app_name(ref['app']));item.setData(Qt.UserRole,ref['url']);listing.addItem(item)
    def activate(item):
        def proceed():
            row=item.data(Qt.UserRole+1) if mode=='history' else None
            if row and _resume_drive_import(window,row):return
            open_url(item.data(Qt.UserRole),root_for(window))
        dialog.accept();safe_action(window,proceed)
    listing.itemActivated.connect(activate);query.textChanged.connect(refresh);refresh()
    if mode=='history':
        resume_button=QPushButton(tr('Einrichtung öffnen und Übergabe fortsetzen'));layout.addWidget(resume_button)
        def resume_selected():
            try:
                item=listing.currentItem();row=item.data(Qt.UserRole+1) if item else None
                if not row or row['state']!='pending':return
                dialog.accept()
                if _resume_drive_import(window,row):return
                if row['target']==getattr(window,'name',''):
                    window.setup();controller(window).enqueue(dict(handoff=row['id']))
                else:launch(row['target'],['--handoff',row['id']],root_for(window))
            except Exception as exc:error(window,exc)
        resume_button.clicked.connect(resume_selected)
        undo_button=QPushButton(tr('Übernahme rückgängig machen'));layout.addWidget(undo_button)
        def undo_selected():
            try:
                item=listing.currentItem();row=item.data(Qt.UserRole+1) if item else None
                if not row or row['state']!='done':return
                if row['action']=='files.drive_import':raise ValueError(tr('Dateien bei Bedarf direkt in Lumen Drive in den Papierkorb legen. Die lokale Quelle bleibt erhalten.'))
                if row['target']!=getattr(window,'name',''):
                    QMessageBox.information(dialog,tr('Im Ziel rückgängig machen'),tr('In der Zielanwendung „Letzte Aktionen …“ öffnen und dort rückgängig machen.'));return
                if row['action']=='vault.sources':raise ValueError(tr('Sicherungsquellen im Lumen-Vault-Plan bearbeiten. Vorhandene Sicherungen bleiben erhalten.'))
                if QMessageBox.question(dialog,tr('Übernahme rückgängig machen'),tr('Nur die unveränderte lokale Übernahme zurücknehmen? Neu angelegte Einträge kommen ins Archiv; die Quelle bleibt erhalten. Bereits gespeicherte Kalendertermine bleiben bestehen.'))!=QMessageBox.Yes:return
                from interop_undo import undo
                applied={}
                def done(ref):
                    applied['ref']=ref;registry.mark_undone(row['id'])
                def finished():
                    ref=applied.get('ref')
                    if not ref:return
                    if ref['kind']=='record':focus(window,ref)
                    elif ref['kind']=='note':
                        if window.doc and window.doc['path']==ref['id']:window.clear_note(tr('Übernahme rückgängig gemacht.'))
                        window.poll()
                    elif hasattr(window,'reload_other'):window.reload_other()
                dialog.accept()
                with_saved(window,lambda:window.work(tr('Übernahme wird zurückgenommen …'),lambda job:undo(row['action'],row['id'],job,root_for(window),getattr(window,'store',None)),done,finished=finished))
            except Exception as exc:error(window,exc)
        undo_button.clicked.connect(undo_selected)
        def selected_history(item,previous):
            row=item.data(Qt.UserRole+1) if item else None
            imported=bool(row and row['action']=='files.drive_import')
            resume_button.setText(tr('Übernahme prüfen und fortsetzen') if imported else tr('Einrichtung öffnen und Übergabe fortsetzen'))
            resume_button.setEnabled(not imported or row['state']=='pending');undo_button.setEnabled(not imported)
        listing.currentItemChanged.connect(selected_history)
    buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()


def install(window):
    if getattr(window,'memory_only',False):return
    if getattr(window,'interop_installed',False):return
    window.interop_installed=True;controller(window)
    from interop_audio import install_audio_menu
    install_audio_menu(window)
    from interop_drag import install_drop_filter
    from interop_context import install as install_context, receive_drop
    install_drop_filter(window,lambda payload:with_saved(window,lambda:receive_drop(window,payload)))
    if hasattr(window,'entries'):install_context(window)


def files_menu(window,menu,paths,*,safety=None):
    if safety is None:safety=menu
    from interop_sources import from_paths,from_drive
    from drive_browser import is_drive
    drive=bool(paths) and all(is_drive(path) for path in paths)
    capture=lambda:from_drive(window.drive,paths) if drive else from_paths(paths)
    # Names and cached metadata decide availability; capture the whole selection only on invocation.
    payload=dict(source={'app':'files'},paths=[] if drive else paths)
    if drive:payload['references']=[dict(kind='drive_'+window.drive.entries[p][0],title=window.drive.entries[p][1]['name']) for p in paths]
    targets=menu.addMenu(tr('Verwenden in …'))
    if not drive and all(Path(p).suffix.lower() in ('.pdf','.epub','.txt','.md','.html','.htm') for p in paths):
        def reader():
            from_paths(paths)
            if len(paths)==1 and hasattr(window,'open_reader'):
                window.open_reader(paths[0]);return
            for path in paths:launch('reader',[path],root_for(window))
        targets.addAction(tr('Mit Lumen Reader öffnen'),lambda:safe_action(window,reader))
    for action,label in actions(payload):
        if action=='reader.import' and not drive:continue
        targets.addAction(label,lambda checked=False,a=action:safe_action(window,lambda:reviewed_send(window,capture(),a)))
    targets.addSeparator()
    targets.addAction(tr('Verwendet in …'),lambda:safe_action(window,lambda:browse(window,'related',capture())))
    if not drive:
        safety.addAction(tr('Lesefortschritt und Sicherungen …'),lambda:file_status(window,paths))
        if len(paths)==1:
            from interop_vault import show_file_versions
            safety.addAction(tr('Versionen in Lumen Vault …'),lambda:safe_action(window,lambda:show_file_versions(window,paths[0],root_for(window))))


def app_name(app):
    return {'files':'Lumen Files','wissen':'Lumen Notes','reader':'Lumen Reader','inbox':'Lumen Inbox',
            'meetings':tr('Lumen Audio Studio · Meeting'),'household':tr('Lumen Digitaler Haushalt'),
            'workbench':tr('Lumen Projekte'),'radio':tr('Lumen Audio Studio · Radio'),
            'vault':'Lumen Vault','sound':'Lumen Sound','translate':'Lumen Compose'}.get(app,'Lumen')


def file_status(window,paths):
    from datetime import datetime
    from interop_vault import coverage
    from interop_reader import progress_for_paths
    try:
        reader=progress_for_paths(paths,root_for(window));lines=[]
        for item in coverage(paths,root_for(window)):
            lines.append(item['path'])
            for book in reader.get(item['path'],[]):lines.append(tr('Lumen Reader: Seite {0}/{1}, {2} Markierungen',book['page']+1,book['pages'],book['marks']))
            if not item['plans']:lines.append(tr('Lumen Vault: in keinem Sicherungsplan.'))
            for plan in item['plans']:
                state=tr('Noch kein erfolgreicher Sicherungslauf.') if not plan['last_backup'] else tr('Letzter Sicherungslauf: {0}',datetime.fromtimestamp(plan['last_backup']).strftime('%d.%m.%Y %H:%M'))
                if plan['changed']:state+=' '+tr('Seitdem geändert.')
                lines.append(plan['title']+': '+state)
            lines.append('')
        QMessageBox.information(window,tr('Lesestand und Sicherungsstatus'),'\n'.join(lines)+tr('Der Planstatus bestätigt keine einzelne Dateiversion. Gesicherte Versionen separat in Lumen Vault prüfen.'))
    except Exception as exc:error(window,exc)


def show_files(window):
    payload=capture(window);paths=payload.get('paths') or [payload.get('source',{}).get('path','')]
    if getattr(window,'name','')=='wissen' and window.doc and window.book:
        paths=note_files(window.document_text(),window.book.root/window.doc['path'])
        if len(paths)>1:
            chosen,ok=QInputDialog.getItem(window,tr('Notiz oder Anhang in Lumen Files zeigen'),tr('Datei auswählen'),paths,0,False)
            if not ok:return
            paths=[chosen]
    if not paths[0]:raise ValueError(tr('Diese Auswahl hat keine zugehörige Datei.'))
    launch('files',[paths[0],'--select'],root_for(window))


def note_files(text,path):
    import re
    from urllib.parse import unquote,urlsplit
    paths=[str(path)]
    for target in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)',text):
        url=urlsplit(target.strip().strip('<>'))
        if url.scheme not in ('','file') or url.netloc:continue
        value=Path(unquote(url.path))
        if not value.is_absolute():value=path.parent/value
        value=value.absolute()
        if value.exists() and str(value) not in paths:paths.append(str(value))
    return paths

def attachment_send(window):
    window._interop_focus=window.attachments
    send_current(window)

def source_markup(text,root=None):
    import html,re
    escaped=html.escape(text)
    def link(match):
        try:
            from interop_sources import source_title
            title=source_title(Registry(root).resolve(html.unescape(match[0])))
        except (ValueError,OSError):title=tr('Original öffnen')
        return '<a href="'+match[0]+'">'+html.escape(title)+'</a>'
    return re.sub(r'lumen://object/[a-f0-9]{32}(?:\?[^\s<>]+)?',link,escaped).replace('\n','<br>')

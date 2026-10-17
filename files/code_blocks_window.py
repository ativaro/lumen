"""Foreground block execution; the inspector always reads durable checkpoints."""
import os
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QMessageBox
from tools_ui import button,label
from lumen_i18n import tr
from code_blocks import encode,permissions
from code_blocks_run import Runs,digest
from code_blocks_editor import BlockEditor,STATES


class BlockWindow(QDialog):
    def __init__(self,collection,identity,parent=None):
        super().__init__(parent);self.collection=collection;self.identity=identity;self.item=collection.get(identity)
        self.runs=Runs(collection);self.run=self.runs.latest(identity);self.job=None;self.engine=None;self.ai_wait=False;self.lease_fd=None;self.dirty=False;self.closing=False;self.last_state=None;self.closed=False
        self.setWindowTitle('Lumen · '+self.item['title']);self.resize(1240,860)
        from code_design import shell,navigation
        main,nav,self.footer=shell(self);self.nav=navigation(nav,self.reject,lambda _:self.reject());self.nav['automation'].setChecked(True)
        root=QVBoxLayout(main);root.setContentsMargins(28,20,28,24);root.setSpacing(12)
        row=QHBoxLayout();row.addWidget(button(tr('‹ Zur Sammlung'),self.reject));
        self.manage_button=button(tr('Eintrag verwalten'),self.manage) if parent is not None else None
        if self.manage_button:row.addWidget(self.manage_button)
        row.addStretch();self.save_button=button(tr('Entwurf speichern'),lambda:self.safe(self.save));row.addWidget(self.save_button);root.addLayout(row)
        root.addWidget(label(self.item['title'],'codeTitle'))
        root.addWidget(label(tr('Dateien und Apps Schritt für Schritt verbinden. Jeder Baustein zeigt seine tatsächlichen Daten.'),'codeSubtitle'))
        from code_flow import parse
        self.editor=BlockEditor(self,parse(self.item['definition']['flow']));self.editor.changed.connect(self.changed);root.addWidget(self.editor,1)
        self.status=label('','codeMuted');root.addWidget(self.status)
        row=QHBoxLayout();self.test_button=button(tr('Testlauf'),lambda:self.safe(self.start,True),'media-playback-start',True);row.addWidget(self.test_button)
        self.live_button=button(tr('Jetzt ausführen'),lambda:self.safe(self.start,False));row.addWidget(self.live_button);row.addStretch()
        self.pause_button=button(tr('Pausieren'),lambda:self.safe(self.pause));row.addWidget(self.pause_button)
        self.resume_button=button(tr('Fortsetzen'),lambda:self.safe(self.resume));row.addWidget(self.resume_button)
        self.approve_button=button(tr('Bestätigen und fortsetzen'),lambda:self.safe(self.approve),primary=True);row.addWidget(self.approve_button)
        self.cancel_button=button(tr('Abbrechen'),lambda:self.safe(self.cancel));row.addWidget(self.cancel_button);root.addLayout(row)
        self.repair_button=button(tr('Reparatur vorbereiten'),lambda:self.safe(self.prepare_repair));row.addWidget(self.repair_button)
        self.footer.setText(tr('Lumen Desktop · Manuelle Abläufe · Lumen bleibt während der Ausführung geöffnet.'))
        if self.run and self.run['status']=='running':
            try:orphan=self.collection.store.acquire('block-'+self.run['id'])
            except BlockingIOError:pass
            else:
                try:self.run=self.runs.control(self.run['id'],'pause')
                finally:os.close(orphan)
        self.render()

    def manage(self):
        parent=self.parent();self.reject()
        if self.closed:parent.open_entry(self.identity,blocks=False)

    def safe(self,function,*args):
        try:return function(*args)
        except Exception as error:self.status.setText(str(error))

    def changed(self):
        self.dirty=True;self.save_button.setText(tr('Entwurf speichern · geändert'));self.resume_button.setEnabled(False);self.status.setText(tr('Ungespeicherte Änderungen · Vor einem Durchlauf speichern.'))

    def save(self):
        value={**self.item['definition'],'flow':encode(self.editor.plan())};value.pop('workflow_id',None)
        self.item=self.collection.update(self.identity,self.item['revision'],definition=value)
        self.dirty=False;self.save_button.setText(tr('Entwurf speichern'));self.render();return self.item

    def start(self,testing):
        if self.job or self.ai_wait or (self.editor.engine and self.editor.engine.busy):return
        if self.dirty:self.save()
        plan=self.editor.plan();grants=permissions(plan)
        if not testing:
            notes=self.collection.store.setting('knowledge/notebook','')
            if any(n['kind']=='save_note' for n in plan['nodes']):grants.append(tr('Notizordner: ')+(notes or tr('Noch nicht eingerichtet')))
        text=(tr('Echter Test: Datei lesen und KI aufrufen. Schreibaktionen landen ausschließlich im privaten Testordner; keine App-Einträge oder Benachrichtigungen.') if testing else tr('Diesen Durchlauf mit diesen Quellen und Aktionen ausführen?'))+'\n\n'+'\n\n'.join(grants)
        if QMessageBox.question(self,tr('Lumen · Testlauf prüfen' if testing else 'Lumen · Aktionen freigeben'),text)!=QMessageBox.Yes:return
        self.run=self.runs.create(self.identity,testing);self.collection.used(self.identity);self.resume()

    def acquire(self):
        if self.lease_fd is None:
            try:self.lease_fd=self.collection.store.acquire('block-'+self.run['id'])
            except BlockingIOError:raise ValueError(tr('Dieser Durchlauf läuft bereits in einem anderen Fenster.')) from None

    def release(self):
        if self.lease_fd is not None:os.close(self.lease_fd);self.lease_fd=None

    def resume(self):
        if not self.run or self.job or self.ai_wait or self.dirty:return
        self.acquire()
        try:self.run=self.runs.resume(self.run['id'])
        except Exception:self.release();raise
        self.render();self.drive()

    def drive(self):
        if self.closed or self.job or self.ai_wait or not self.run:return
        self.run=self.runs.get(self.run['id'])
        if self.run['status']!='running':self.idle();return
        from lumen_jobs import Job
        identity=self.run['id'];self.job=Job(lambda job:self.runs.advance(identity,job),self)
        self.job.result.connect(self.advanced);self.job.failed.connect(self.failed);self.job.finished.connect(self.job_finished);self.job.start()

    def advanced(self,value):
        self.render()
        if not value or self.closed or self.run['status']!='running':return
        try:
            with self.collection.store.connect() as db:self.runs.fence(self.runs.get(self.run['id'],db),db)
            if self.engine is None:
                from assistant_backend import OpenCodeBackend
                folder=self.collection.store.directory/'block-engine';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
                self.engine=OpenCodeBackend(folder,self,project_config=False);self.engine.completed.connect(self.ai_done)
            self.ai_wait=True;self.ai_attempt=value['attempt'];self.ai_identity=self.run['id']
            self.engine.send(value['prompt'],proposal=True,title='Lumen Automation')
        except Exception as error:
            self.ai_wait=False;self.failed(str(error))

    def ai_done(self,success,result):
        self.ai_wait=False
        if success:self.runs.ai_done(self.ai_identity,result,self.ai_attempt)
        else:self.runs.fail(self.ai_identity,result,self.ai_attempt)
        self.render();QTimer.singleShot(0,self.drive)

    def failed(self,message):
        self.runs.fail(self.run['id'],message);self.render()

    def job_finished(self):
        job,self.job=self.job,None;job.deleteLater();self.render();QTimer.singleShot(0,self.drive)

    def idle(self):
        self.release();self.render()
        if self.closing:self.reject()

    def pause(self):
        if not self.run:return
        self.run=self.runs.control(self.run['id'],'pause')
        if self.job:self.job.cancelled.set()
        if self.engine and self.ai_wait:self.engine.stop()
        self.render()
        if not self.job and not self.ai_wait:self.idle()

    def cancel(self):
        if not self.run:return
        self.run=self.runs.control(self.run['id'],'cancel')
        if self.job:self.job.cancelled.set()
        if self.engine and self.ai_wait:self.engine.stop()
        self.render()
        if not self.job and not self.ai_wait:self.idle()

    def approve(self):
        if not self.run:return
        self.run=self.runs.control(self.run['id'],'approve')
        if self.run['status']=='completed':self.idle()
        else:self.resume()

    def render(self):
        if self.closed:return
        if self.run:self.run=self.runs.get(self.run['id'])
        same=bool(self.run and self.run['signature']==digest(self.editor.plan(False)))
        state=self.run['status'] if same else 'draft'
        active=state in ('running','waiting') or self.job is not None or self.ai_wait
        self.editor.set_locked(active);self.editor.run=self.run if same else None;self.editor.refresh()
        if state in ('waiting','error') and state!=self.last_state:
            self.editor.list.setCurrentRow(self.run['data']['cursor']);self.editor.io.setCurrentIndex(1)
        self.last_state=state
        self.repair_button.setVisible(state=='error')
        if self.manage_button:self.manage_button.setEnabled(not active)
        self.save_button.setEnabled(not active);self.test_button.setEnabled(not active);self.live_button.setEnabled(not active)
        self.pause_button.setVisible(state=='running');self.resume_button.setVisible(state in ('paused','error'));self.resume_button.setEnabled(not self.dirty and not self.job and not self.ai_wait)
        self.approve_button.setVisible(state=='waiting');self.cancel_button.setVisible(state in ('running','waiting','paused','error'))
        if state=='draft':self.status.setText(tr('Entwurf · Beim Speichern läuft noch nichts.'))
        else:
            completed=sum(s['status'] in ('completed','skipped') for s in self.run['data']['steps'])
            text=tr('Testlauf' if self.run['testing'] else 'Durchlauf')+' · '+tr(STATES.get(state,state))+' · '+f"{completed}/{len(self.run['plan']['nodes'])}"
            if self.run['testing']:text+=' · '+str(self.collection.store.directory/'block-tests'/self.run['id'])
            if state=='error':text+='\n'+self.run['data']['steps'][self.run['data']['cursor']]['error']
            if state=='waiting':text+='\n'+tr('Ergebnis prüfen: Bestätigen setzt den wartenden Baustein fort, auch wenn du einen anderen betrachtest.')
            self.status.setText(text)

    def prepare_repair(self):
        if not self.run or self.run['status']!='error':return
        if QMessageBox.question(self,tr('Lumen · Reparatur vorbereiten'),tr('Den angehaltenen Durchlauf beenden und einen bearbeitbaren Reparaturauftrag vorbereiten? Die bisherigen Ergebnisse bleiben erhalten.'))!=QMessageBox.Yes:return
        from code_repair import request
        text=request(self.run['plan'],self.run['data']['cursor'])
        self.cancel();self.editor.description.setPlainText(text);self.editor.tabs.setCurrentIndex(1)
        self.editor.description_status.setText(tr('Fehlerbeschreibung prüfen und ergänzen. Erst der nächste Klick sendet den Auftrag an die KI.'))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'editor'):
            from PySide6.QtCore import Qt
            self.editor.splitter.setOrientation(Qt.Vertical if self.width()<900 else Qt.Horizontal)

    def reject(self):
        if self.closed:return
        if self.job or self.ai_wait:
            self.closing=True;self.pause();return
        if self.run and self.run['status']=='running':self.pause()
        if self.dirty and QMessageBox.question(self,tr('Lumen · Entwurf speichern'),tr('Änderungen vor dem Schließen speichern?'))==QMessageBox.Yes:
            try:self.save()
            except Exception as error:self.status.setText(str(error));return
        self.closed=True;self.release();self.editor.shutdown()
        if self.engine:self.engine.shutdown()
        super().reject()

"""Foreground block execution; the inspector always reads durable checkpoints."""
import os
import json
from html import escape
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QMessageBox,QTabWidget,QWidget,QTextBrowser,QLineEdit
from tools_ui import button,label
from lumen_i18n import tr
from code_blocks import encode,permissions
from code_blocks_run import Runs,digest
from code_blocks import STATES


class BlockWindow(QDialog):
    def __init__(self,collection,identity,parent=None):
        super().__init__(parent);self.collection=collection;self.identity=identity;self.item=collection.get(identity)
        self.runs=Runs(collection);self.run=self.runs.latest(identity);self.job=None;self.engine=None;self.ai_wait=False;self.lease_fd=None;self.dirty=False;self.closing=False;self.last_state=None;self.closed=False
        self.setWindowTitle('Lumen · '+self.item['title']);self.resize(1240,860)
        from code_design import editor_shell
        main,self.header,self.footer=editor_shell(self,tr('Lumen Routine' if self.item['definition'].get('editor')=='routine' else 'Lumen Automation'),tr('Feste Schritte, Quellen und Zeitplan zusammenstellen.') if self.item['definition'].get('editor')=='routine' else tr('Auslöser, optionale Bedingungen und Aktionen.'))
        root=QVBoxLayout(main);root.setContentsMargins(0,0,0,0);root.setSpacing(16)
        row=QHBoxLayout();row.addWidget(button(tr('‹ Zur Sammlung'),self.reject));
        self.manage_button=button(tr('Eintrag verwalten'),self.manage) if parent is not None else None
        if self.manage_button:row.addWidget(self.manage_button)
        row.addStretch();root.addLayout(row)
        self.title_edit=QLineEdit(self.item['title']);self.title_edit.setObjectName('codeFlowTitle');self.title_edit.setMaxLength(160);self.title_edit.setAccessibleName(tr('Name der Automation'));root.addWidget(self.title_edit)
        self.views=QTabWidget();self.views.setAccessibleName(tr('Automation'));root.addWidget(self.views,1)
        actions=QHBoxLayout();self.save_button=button(tr('Entwurf speichern'),lambda:self.safe(self.save));actions.addWidget(self.save_button)
        from code_flow import parse
        plan=parse(self.item['definition']['flow'])
        from code_sections_editor import SectionsEditor
        from code_triggers import project_choices
        self.editor=SectionsEditor(self,plan,projects=project_choices(self.collection.store),tools=self.collection.items(kind='tool'),routine=self.item['definition'].get('editor')=='routine')
        self.editor.changed.connect(self.changed);self.views.addTab(self.editor,tr('Ablauf'));self.title_edit.textEdited.connect(self.changed)
        from code_triggers import Triggers
        self.triggers=Triggers(collection)
        self.activation_button=button(tr('Prüfen und aktivieren'),lambda:self.safe(self.toggle_trigger),primary=True)
        actions.addStretch()
        self.result_page=QWidget();results=QVBoxLayout(self.result_page);results.setContentsMargins(0,16,0,0);results.setSpacing(12);self.views.addTab(self.result_page,tr('Test && Ergebnis'))
        self.status=label('','codeMuted');results.addWidget(self.status)
        self.result_view=QTextBrowser();self.result_view.setOpenExternalLinks(False);self.result_view.setAccessibleName(tr('Ergebnis des letzten Durchlaufs'));results.addWidget(self.result_view,1)
        row=QHBoxLayout();self.test_button=button(tr('Testlauf'),lambda:self.safe(self.start,True),'media-playback-start');actions.addWidget(self.test_button);actions.addWidget(self.activation_button);root.addLayout(actions)
        self.live_button=button(tr('Jetzt ausführen'),lambda:self.safe(self.start,False),primary=True);actions.addWidget(self.live_button);row.addStretch()
        self.pause_button=button(tr('Pausieren'),lambda:self.safe(self.pause));row.addWidget(self.pause_button)
        self.resume_button=button(tr('Fortsetzen'),lambda:self.safe(self.resume));row.addWidget(self.resume_button)
        self.approve_button=button(tr('Bestätigen und fortsetzen'),lambda:self.safe(self.approve),primary=True);row.addWidget(self.approve_button)
        self.cancel_button=button(tr('Abbrechen'),lambda:self.safe(self.cancel));row.addWidget(self.cancel_button);results.addLayout(row)
        self.repair_button=button(tr('Reparatur vorbereiten'),lambda:self.safe(self.prepare_repair));row.addWidget(self.repair_button)
        self.footer.setText(tr('Lumen Desktop · Auslöser laufen über die Hintergrundprüfung. Testlauf führt keine App-Aktionen aus.'))
        if self.run and self.run['status']=='running':
            try:orphan=self.collection.store.acquire('block-'+self.run['id'])
            except BlockingIOError:pass
            else:
                try:self.run=self.runs.control(self.run['id'],'pause')
                finally:os.close(orphan)
        self.render()
        self.refresh_timer=QTimer(self);self.refresh_timer.setInterval(1500);self.refresh_timer.timeout.connect(self.refresh_run);self.refresh_timer.start()

    def refresh_run(self):
        if self.closed or self.dirty or self.job or self.ai_wait or getattr(self.editor,'dialog',None) is not None:return
        latest=self.runs.latest(self.identity)
        if latest and (not self.run or latest['updated']!=self.run['updated'] or latest['id']!=self.run['id']):
            self.run=latest;self.render()

    def manage(self):
        parent=self.parent();self.reject()
        if self.closed:parent.open_entry(self.identity,blocks=False)

    def safe(self,function,*args):
        try:return function(*args)
        except Exception as error:self.status.setText(str(error));self.footer.setText(str(error))

    def changed(self,*_):
        row=self.triggers.get(self.identity)
        if row and row['enabled']:self.triggers.pause(self.identity);self.footer.setText(tr('Auslöser pausiert · Änderungen speichern und erneut testen.'))
        self.dirty=True;self.save_button.setText(tr('Entwurf speichern · geändert'));self.resume_button.setEnabled(False);self.status.setText(tr('Ungespeicherte Änderungen · Vor einem Durchlauf speichern.'))
        self.save_button.setEnabled(True)
        self.footer.setText(tr('Ungespeicherte Änderungen · Auslöser pausiert. Vor der Aktivierung speichern und testen.'))
        self.activation_button.setText(tr('Prüfen und aktivieren'));self.activation_button.setEnabled(False)

    def save(self):
        value={**self.item['definition'],'flow':encode(self.editor.plan())};value.pop('workflow_id',None)
        self.item=self.collection.update(self.identity,self.item['revision'],title=self.title_edit.text().strip(),definition=value)
        self.setWindowTitle('Lumen · '+self.item['title'])
        self.dirty=False;self.save_button.setText(tr('Entwurf speichern'));self.render();return self.item

    def toggle_trigger(self):
        from code_block_paths import config
        row=self.triggers.get(self.identity)
        if row and row['enabled']:
            self.triggers.pause(self.identity);self.render();return
        if self.dirty:raise ValueError(tr('Änderungen zuerst als Entwurf speichern.'))
        if not self.passed_test():raise ValueError(tr('Den gespeicherten Ablauf zuerst erfolgreich testen.'))
        source=config(self.editor.plan()['nodes'][0]);trigger=source.get('trigger')
        if not trigger:raise ValueError(tr('Unter Wenn zuerst einen automatischen Auslöser wählen.'))
        from code_triggers import describe
        grants=[describe(source),*permissions(self.editor.plan())]
        if any(n['kind']=='save_note' for n in self.editor.plan()['nodes']):grants.append(tr('Notizordner: ')+self.collection.store.setting('knowledge/notebook',''))
        if QMessageBox.question(self,tr('Lumen · Hintergrundablauf freigeben'),tr('Diesen Auslöser mit den folgenden Quellen und Aktionen aktivieren? KI-Schritte senden Inhalte an deinen eingerichteten Anbieter. Bestätigungsschritte warten weiterhin auf dich.')+'\n\n'+'\n\n'.join(grants))!=QMessageBox.Yes:return
        self.triggers.activate(self.identity)
        try:
            from lumen_actions import command
            command(['systemctl','--user','enable','--now','lumen-jobs.timer'])
        except Exception:
            self.triggers.pause(self.identity);raise ValueError(tr('Hintergrundprüfung nicht verfügbar. Der Auslöser bleibt pausiert.')) from None
        self.render()

    def start(self,testing):
        if self.job or self.ai_wait or (self.editor.engine and self.editor.engine.busy) or (getattr(self.editor,'full_engine',None) and self.editor.full_engine.busy):return
        if self.dirty:self.save()
        plan=self.editor.plan();grants=permissions(plan)
        if not testing:
            notes=self.collection.store.setting('knowledge/notebook','')
            if any(n['kind']=='save_note' for n in plan['nodes']):grants.append(tr('Notizordner: ')+(notes or tr('Noch nicht eingerichtet')))
        text=(tr('Echter Test: Datei lesen und KI aufrufen. Schreibaktionen landen ausschließlich im privaten Testordner; keine App-Einträge oder Benachrichtigungen.') if testing else tr('Diesen Durchlauf mit diesen Quellen und Aktionen ausführen?'))+'\n\n'+'\n\n'.join(grants)
        if QMessageBox.question(self,tr('Lumen · Testlauf prüfen' if testing else 'Lumen · Aktionen freigeben'),text)!=QMessageBox.Yes:return
        event=None
        if plan.get('version')==3:
            from code_block_paths import config
            source=config(plan['nodes'][0])
            if source.get('trigger',{}).get('kind')=='directory':
                from PySide6.QtWidgets import QFileDialog
                from code_triggers import file_event
                chosen=QFileDialog.getOpenFileName(self,tr('Lumen · Beispieldatei aus dem beobachteten Ordner wählen'),source['trigger']['path'])[0]
                if not chosen:return
                event=file_event(source,chosen)
        self.views.setCurrentIndex(1);self.run=self.runs.create(self.identity,testing,event=event);self.collection.used(self.identity);self.resume()

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

    def passed_test(self):
        plan=self.editor.plan(False);signature=digest(plan)
        with self.collection.store.connect() as db:
            row=db.execute("SELECT status,data FROM code_block_runs WHERE entry=? AND signature=? AND testing=1 ORDER BY updated DESC LIMIT 1",(self.identity,signature)).fetchone()
        if row is None or row['status']!='completed':return False
        return any(step['status']=='completed' for n,step in zip(plan['nodes'],json.loads(row['data'])['steps']) if n['kind'] not in ('manual','condition','end_each'))

    def render_result(self,same):
        if not self.run:
            self.result_view.setHtml('<h3>'+escape(tr('Noch kein Testlauf'))+'</h3><p>'+escape(tr('Teste den gespeicherten Ablauf. Datei- und KI-Schritte laufen tatsächlich; Ausgaben bleiben im privaten Testordner.'))+'</p>');return
        parts=['<h3>'+escape(tr('Letzter Testlauf' if self.run['testing'] else 'Letzter Durchlauf'))+'</h3>']
        if not same:parts.append('<p>'+escape(tr('Dieser Durchlauf gehört zu einem früheren Entwurf. Die aktuellen Änderungen wurden noch nicht getestet.'))+'</p>')
        elif self.run['testing'] and self.run['status']=='completed' and not self.passed_test():parts.append('<p>'+escape(tr('Keine Aktion ausgeführt. Vor der Aktivierung mit einer passenden Eingabe testen.'))+'</p>')
        for n,step in zip(self.run['plan']['nodes'],self.run['data']['steps']):
            parts.append('<p><b>'+escape(n['title'])+'</b> · '+escape(tr(STATES.get(step['status'],step['status'])))+'</p>')
            result=step.get('error') or step.get('output') or {}
            if isinstance(result,dict):result='\n'.join(str(v) for v in result.values() if v is not None)
            if result:parts.append('<p>'+escape(str(result)).replace('\n','<br>')+'</p>')
        self.result_view.setHtml(''.join(parts))

    def render(self):
        if self.closed:return
        if self.run:self.run=self.runs.get(self.run['id'])
        same=bool(self.run and self.run['signature']==digest(self.editor.plan(False)))
        from code_block_paths import config
        trigger=config(self.editor.plan(False)['nodes'][0]).get('trigger') if self.editor.plan(False).get('version')==3 else None
        row=self.triggers.get(self.identity);enabled=bool(row and row['enabled'])
        self.activation_button.setText(tr('Auslöser pausieren' if enabled else 'Prüfen und aktivieren'))
        self.activation_button.setVisible(bool(trigger));self.activation_button.setToolTip(tr('Vor dem Aktivieren den gespeicherten Ablauf erfolgreich testen.'))
        from code_triggers import describe
        self.footer.setText((tr('Aktiv')+' · '+describe(config(self.editor.plan(False)['nodes'][0]))) if enabled else tr('Auslöser pausiert · Speichern startet keine Ausführung.') if trigger else tr('Manueller Ablauf · Lumen bleibt während der Ausführung geöffnet.'))
        if row and row['error']:self.footer.setText(tr('Auslöser angehalten: ')+row['error'])
        state=self.run['status'] if same else 'draft'
        active=state in ('running','waiting') or self.job is not None or self.ai_wait
        self.activation_button.setEnabled(enabled or (not active and not self.dirty and self.passed_test()))
        self.title_edit.setReadOnly(active);self.editor.set_locked(active);self.editor.run=self.run if same else None;self.editor.refresh()
        if state in ('waiting','error') and state!=self.last_state:
            self.editor.focus_step(self.run['data']['cursor']) if hasattr(self.editor,'focus_step') else self.editor.list.setCurrentRow(self.run['data']['cursor'])
            if hasattr(self.editor,'io'):self.editor.io.setCurrentIndex(1)
        self.render_result(same);self.last_state=state
        self.repair_button.setVisible(state=='error')
        if self.manage_button:self.manage_button.setEnabled(not active)
        self.save_button.setEnabled(not active and self.dirty);self.test_button.setEnabled(not active);self.live_button.setEnabled(not active)
        self.pause_button.setVisible(state=='running');self.resume_button.setVisible(state in ('paused','error'));self.resume_button.setEnabled(not self.dirty and not self.job and not self.ai_wait)
        self.approve_button.setVisible(state=='waiting');self.cancel_button.setVisible(state in ('running','waiting','paused','error'))
        if state in ('waiting','error') and same:self.views.setCurrentIndex(1)
        if state=='draft':self.status.setText(tr('Entwurf · Beim Speichern läuft noch nichts.'))
        else:
            completed=sum(s['status'] in ('completed','skipped') for s in self.run['data']['steps'])
            text=tr('Testlauf' if self.run['testing'] else 'Durchlauf')+' · '+tr(STATES.get(state,state))+' · '+f"{completed}/{len(self.run['plan']['nodes'])}"
            if self.run['testing']:text+=' · '+str(self.collection.store.directory/'block-tests'/self.run['id'])
            if state=='error':text+='\n'+self.run['data']['steps'][self.run['data']['cursor']]['error']
            if state=='waiting':text+='\n'+tr('Ergebnis prüfen: Bestätigen setzt den wartenden Schritt fort, auch wenn du einen anderen betrachtest.')
            self.status.setText(text)

    def prepare_repair(self):
        if not self.run or self.run['status']!='error':return
        if QMessageBox.question(self,tr('Lumen · Reparatur vorbereiten'),tr('Den angehaltenen Durchlauf beenden und einen bearbeitbaren Reparaturauftrag vorbereiten? Die bisherigen Ergebnisse bleiben erhalten.'))!=QMessageBox.Yes:return
        from code_repair import request
        text=request(self.run['plan'],self.run['data']['cursor'])
        self.cancel()
        if hasattr(self.editor,'full_description'):
            self.editor.full_description.setPlainText(text);self.editor.tabs.setCurrentIndex(2);self.editor.full_status.setText(tr('Fehlerbeschreibung prüfen. Erst dein nächster Klick sendet sie an die KI.'));return
        self.editor.description.setPlainText(text);self.editor.tabs.setCurrentIndex(1)
        self.editor.description_status.setText(tr('Fehlerbeschreibung prüfen und ergänzen. Erst der nächste Klick sendet den Auftrag an die KI.'))

    def reject(self):
        if self.closed:return
        if self.job or self.ai_wait:
            self.closing=True;self.pause();return
        if self.run and self.run['status']=='running':self.pause()
        if self.dirty and QMessageBox.question(self,tr('Lumen · Entwurf speichern'),tr('Änderungen vor dem Schließen speichern?'))==QMessageBox.Yes:
            try:self.save()
            except Exception as error:self.status.setText(str(error));return
        self.closed=True;self.refresh_timer.stop();self.release();self.editor.shutdown()
        if self.engine:self.engine.shutdown()
        super().reject()

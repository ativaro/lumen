"""A native backup desk: explicit plans and a recoverable timeline."""
from lumen_i18n import tr
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QCheckBox,
    QComboBox, QFileDialog, QInputDialog, QListWidget, QListWidgetItem, QMessageBox, QTreeWidget, QTreeWidgetItem)
from tools_ui import ToolWindow, button, label, row, open_path
import vault_data as vault


class Vault(ToolWindow):
    def __init__(self,root=None):
        super().__init__('vault',tr('Lumen Vault'),tr('Deine Dateien und Einstellungen. Verschlüsselt gesichert, gezielt zurückholen.'),'document-encrypt',root)
        self.add_button.setText(tr('Sicherung einrichten')); self.search.setPlaceholderText(tr('Sicherungspläne …'))
        self.summary=label(tr('Wähle einen Sicherungsplan oder richte deine erste Sicherung ein.'),'heading'); self.content.addWidget(self.summary)
        self.details=label(''); self.content.addWidget(self.details)
        self.sources=QListWidget(); self.sources.setAccessibleName(tr('Geschützte Quellen')); self.sources.setMaximumHeight(115); self.content.addWidget(self.sources)
        self.content.addWidget(row(button(tr('Quelle hinzufügen'),lambda:self.safe(self.add_source),'list-add'),
                                  button(tr('Lumen-Daten hinzufügen'),lambda:self.safe(self.add_lumen_sources),'lumen'),
                                  button(tr('Quelle entfernen'),lambda:self.safe(self.remove_source),'list-remove')))
        self.content.addWidget(row(button(tr('Sicherungsvorschau'),lambda:self.action('preview'),'document-preview'),
                                  button(tr('Jetzt sichern'),lambda:self.action('backup'),'document-save',True)))
        self.interval=QComboBox(); self.interval.setAccessibleName(tr('Sicherungsrhythmus'))
        for title,value in [(tr('Nur manuell'),0),(tr('Täglich'),86400),(tr('Wöchentlich'),604800)]:self.interval.addItem(title,value)
        self.content.addWidget(row(label(tr('Zeitplan')),self.interval,button(tr('Zeitplan übernehmen'),self.set_schedule)))
        self.snapshots=QTreeWidget(); self.snapshots.setHeaderLabels([tr('Sicherungsstand'),tr('Quellen')]); self.snapshots.setRootIsDecorated(False)
        self.snapshots.setAccessibleName(tr('Gesicherte Versionen')); self.content.addWidget(self.snapshots,1)
        self.content.addWidget(row(button(tr('Stände laden'),lambda:self.action('snapshots'),'view-refresh'),
            button(tr('Inhalt ansehen'),self.show_files,'document-preview'),button(tr('Stand wiederherstellen'),self.restore,'edit-undo')))
        self.content.addWidget(row(button(tr('Struktur prüfen'),lambda:self.action('check'),'dialog-ok-apply'),
            button(tr('Alle Sicherungsdaten prüfen'),lambda:self.action('check',full=True),'security-high'),
            button(tr('Projektquellen prüfen'),lambda:self.safe(self.check_sources),'document-preview')))
        self.content.addWidget(label(tr('Wiederherstellungen landen in einem neuen Ordner. Das Sicherungspasswort zusätzlich außerhalb dieses Rechners aufbewahren.'),'muted'))
        self.body.setEnabled(False);self.refresh()

    def create(self,prefill_sources=None,on_done=None,source_ref=None,handoff=None):
        if self.job:return False
        if not vault.binary():self.status.setText(tr('Bitte zuerst unter Einrichtung „Vault vorbereiten“ wählen.'));self.setup();return False
        prefill_sources=prefill_sources or []
        dialog=QDialog(self);dialog.setWindowTitle(tr('Sicherung einrichten'));dialog.resize(620,440);form=QFormLayout(dialog)
        title=QLineEdit(tr('Meine Sicherung'));repo=QLineEdit();source=QLineEdit();password=QLineEdit();password.setEchoMode(QLineEdit.Password)
        if prefill_sources:source.setText(prefill_sources[0]['path'])
        confirm=QLineEdit();confirm.setEchoMode(QLineEdit.Password)
        def choose(field):
            path=QFileDialog.getExistingDirectory(dialog,tr('Ordner auswählen'),str(Path.home()))
            if path:field.setText(path)
        form.addRow(tr('Name'),title);form.addRow(tr('USB-/NAS-Zielordner'),row(repo,button(tr('Wählen'),lambda:choose(repo))))
        form.addRow(tr('Erster Quellordner'),row(source,button(tr('Wählen'),lambda:choose(source))))
        if len(prefill_sources)>1:form.addRow(tr('Weitere Lumen-Quellen'),label('\n'.join(row['path'] for row in prefill_sources[1:])))
        desktop=QCheckBox(tr('Lumen- und KDE-Einstellungen ebenfalls sichern'));form.addRow(desktop)
        form.addRow(tr('Sicherungspasswort'),password);form.addRow(tr('Wiederholen'),confirm)
        form.addRow(label(tr('Neues Ziel: leerer Ordner. Vorhandenes Restic-Ziel: bisheriges Sicherungspasswort verwenden. Passwörter speichert der System-Schlüsselbund.')))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec_()!=QDialog.Accepted:return False
        if password.text()!=confirm.text():raise ValueError(tr('Die Passwörter stimmen nicht überein.'))
        sources=([source.text()] if source.text().strip() else [])+[row['path'] for row in prefill_sources[1:]]+(vault.config_sources() if desktop.isChecked() else [])
        name,target,key=title.text(),repo.text(),password.text()
        def prepare(job):
            chosen=[row for row in prefill_sources if row['path'] in sources]
            return vault.create(self.library,name,target,sources,key,job,app_sources=chosen,source_ref=source_ref,handoff=handoff)
        def complete(identity):
            self.focus_record(identity)
            if on_done:on_done(identity)
        self.work(tr('Sicherungsziel wird vorbereitet …'),prepare,complete)
        if on_done and self.job:self.job.failed.connect(lambda _:on_done(None))
        return bool(self.job)

    def load(self,plan):
        self.summary.setText(plan['title']);self.sources.clear();self.sources.addItems(plan['sources']);self.snapshots.clear()
        self.interval.setCurrentIndex(self.interval.findData(plan.get('interval',0)))
        last=plan.get('last_backup');when=datetime.fromtimestamp(last).strftime('%d.%m.%Y %H:%M') if last else tr('Noch keine abgeschlossene Sicherung')
        self.details.setText(plan['repository']+'\n'+when+('\n'+plan['last_error'] if plan.get('last_error') else ''))
        if plan.get('app_sources'):
            self.details.setText(self.details.text()+'\n'+tr('Lumen-Daten: gespeicherte Dateien und konsistente Datenbankkopien. Ungespeicherte Fensteränderungen sind nicht enthalten.'))
        if plan.get('backup_flushes'):
            from interop_vault import APP_NAMES
            text=' · '.join(tr(APP_NAMES.get(row['app'],row['app']))+' '+datetime.fromtimestamp(row['flushed_at']).strftime('%H:%M:%S') for row in plan['backup_flushes'])
            self.details.setText(self.details.text()+'\n'+tr('Vor der letzten Sicherung gespeichert bestätigt: {0}',text))
        if any(row.get('kind')=='inbox-local' for row in plan.get('app_sources',[])):
            self.details.setText(self.details.text()+'\n'+tr('Lumen Inbox: nur lokale Aufgaben und ungesendete Entwürfe mit Anhängen sichern'))
        self.status.setText(tr('Sicherungsplan lokal gespeichert · Ziel wird erst bei einer Aktion geöffnet'))

    def add_source(self):
        folder=QFileDialog.getExistingDirectory(self,tr('Quellordner hinzufügen'),str(Path.home()))
        if folder:
            plan=self.library.get(self.current);_,sources=vault.paths(plan['repository'],plan['sources']+[folder])
            self.library.update(self.current,sources=sources);self.focus_record(self.current)

    def remove_source(self):
        item=self.sources.currentItem()
        if not item:return
        plan=self.library.get(self.current);sources=[v for v in plan['sources'] if v!=item.text()]
        if not sources:raise ValueError(tr('Mindestens eine Quelle muss erhalten bleiben.'))
        self.library.update(self.current,sources=sources,app_sources=[r for r in plan.get('app_sources',[]) if r['path'] in sources]);self.focus_record(self.current)

    def add_lumen_sources(self):
        from interop_vault import discover_sources,receive_sources
        rows=discover_sources(self.library.root.parent)
        if not rows:raise ValueError(tr('Noch keine gespeicherten Lumen-Anwendungsdaten gefunden.'))
        receive_sources(self,dict(source=dict(app='vault')),entries=rows)

    def check_sources(self):
        if not self.current:return
        from interop_vault import preflight
        findings=preflight(self.library.get(self.current))
        text='\n'.join((tr('Fehlt: ') if row['reason']=='missing' else tr('Nicht im Plan: '))+row['path'] for row in findings)
        QMessageBox.information(self,tr('Projektquellen im Sicherungsplan'),text or tr('Alle bekannten lokalen Projektquellen sind vorhanden und im Plan enthalten.'))

    def action(self,action,completed=None,**kwargs):
        if not self.current:return
        key=self.current
        if action=='backup':
            from interop_vault import preflight
            try:findings=preflight(self.library.get(key))
            except Exception as error:self.error(str(error));return
            if findings:
                text=tr('Diese Projektquellen fehlen oder sind nicht in diesem Sicherungsplan enthalten:')+'\n\n'
                text+='\n'.join((tr('Fehlt: ') if item['reason']=='missing' else tr('Nicht im Plan: '))+item['path'] for item in findings[:30])
                text+='\n\n'+tr('Nur die bereits ausgewählten Quellen sichern?')
                question=QMessageBox(QMessageBox.Warning,tr('Projektquellen vor der Sicherung prüfen'),text,QMessageBox.Yes|QMessageBox.Cancel,self)
                question.setTextFormat(Qt.PlainText);question.setDefaultButton(QMessageBox.Cancel)
                if question.exec_()!=QMessageBox.Yes:return
        def done(value):
            if action=='snapshots':
                self.snapshots.clear()
                for snapshot in reversed(value):
                    item=QTreeWidgetItem([snapshot['time'][:19].replace('T',' '),' · '.join(snapshot.get('paths',[]))])
                    item.setData(0,Qt.UserRole,snapshot['id']);self.snapshots.addTopLevelItem(item)
                self.status.setText(tr('{0} Sicherungsstände geladen' , len(value)))
            elif action in ('preview','backup'):
                self.status.setText((tr('Vorschau: ') if action=='preview' else tr('Gesichert: '))+tr('{0} Dateien · {1:.1f} MiB' , value.get('total_files_processed',0), value.get('total_bytes_processed',0)/1024**2))
                if action=='backup':self.load(self.library.get(key));self.status.setText(tr('Sicherung erfolgreich abgeschlossen.'))
            else:self.status.setText(str(value))
            if completed:completed()
        self.work({'backup':tr('Sicherung wird erstellt …'),'preview':tr('Sicherung wird vorgeprüft …'),'snapshots':tr('Sicherung wird gelesen …'),'check':tr('Sicherung wird geprüft …')}.get(action,action),
            lambda job:vault.run(self.library,key,action,job,**kwargs),done)

    def selected(self):
        item=self.snapshots.currentItem()
        if not item:raise ValueError(tr('Bitte einen Sicherungsstand auswählen.'))
        return item.data(0,Qt.UserRole)

    def show_files(self):
        self.safe(self._show_files)

    def _show_files(self):
        snapshot=self.selected();key=self.current
        def show(items):
            dialog=QDialog(self);dialog.setWindowTitle(tr('Gesicherte Dateien'));dialog.resize(780,600);form=QFormLayout(dialog)
            listing=QListWidget();listing.setAccessibleName(tr('Dateien dieses Sicherungsstands'));form.addRow(listing)
            for value in items:
                item=QListWidgetItem(value.get('path',''));item.setData(Qt.UserRole,value);listing.addItem(item)
            form.addRow(button(tr('Auswahl wiederherstellen'),lambda:self._restore_from_dialog(dialog,listing,snapshot)))
            # The worker completes after its result signal; defer this modal window.
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0,dialog.exec_)
        self.work(tr('Gesicherte Pfade werden geladen …'),lambda job:vault.run(self.library,key,'files',job,snapshot=snapshot),show)

    def _restore_from_dialog(self,dialog,listing,snapshot):
        item=listing.currentItem()
        if item:dialog.accept();self.safe(self.restore_selected,snapshot,item.data(Qt.UserRole)['path'])

    def restore(self):self.safe(lambda:self.restore_selected(self.selected()))

    def restore_selected(self,snapshot,selected=''):
        folder=QFileDialog.getExistingDirectory(self,tr('Wiederherstellung: übergeordneten Zielordner wählen'),str(Path.home()))
        if not folder:return
        key=self.current
        def done(path):
            self.status.setText(tr('Wiederhergestellt und geprüft: ')+path)
            from interop_vault import show_restored
            show_restored(self,path)
        self.work(tr('Daten werden in einen neuen Ordner wiederhergestellt …'),lambda job:vault.run(self.library,key,'restore',job,snapshot=snapshot,selected=selected,destination=folder),done)

    def set_schedule(self):
        if not self.current:return
        key=self.current;interval=self.interval.currentData()
        self.work(tr('Zeitplan übernehmen …'),lambda job:vault.schedule(self.library,key,interval,job),lambda _:self.status.setText(tr('Zeitplan gespeichert. Bei gesperrtem Schlüsselbund oder fehlendem Medium wird gewartet.')))

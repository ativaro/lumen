"""A native backup desk: explicit plans and a recoverable timeline."""
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QCheckBox,
    QComboBox, QFileDialog, QInputDialog, QListWidget, QListWidgetItem, QMessageBox, QTreeWidget, QTreeWidgetItem)
from tools_ui import ToolWindow, button, label, row, open_path
import vault_data as vault


class Vault(ToolWindow):
    def __init__(self,root=None):
        super().__init__('vault','Lumen Vault','Deine Dateien und Einstellungen. Verschlüsselt gesichert, gezielt zurückholen.','document-encrypt',root)
        self.add_button.setText('Sicherung einrichten'); self.search.setPlaceholderText('Sicherungspläne …')
        self.summary=label('Wähle einen Sicherungsplan oder richte deine erste Sicherung ein.','heading'); self.content.addWidget(self.summary)
        self.details=label(''); self.content.addWidget(self.details)
        self.sources=QListWidget(); self.sources.setAccessibleName('Geschützte Quellen'); self.sources.setMaximumHeight(115); self.content.addWidget(self.sources)
        self.content.addWidget(row(button('Quelle hinzufügen',lambda:self.safe(self.add_source),'list-add'),
                                  button('Quelle entfernen',lambda:self.safe(self.remove_source),'list-remove')))
        self.content.addWidget(row(button('Sicherungsvorschau',lambda:self.action('preview'),'document-preview'),
                                  button('Jetzt sichern',lambda:self.action('backup'),'document-save',True)))
        self.interval=QComboBox(); self.interval.setAccessibleName('Sicherungsrhythmus')
        for title,value in [('Nur manuell',0),('Täglich',86400),('Wöchentlich',604800)]:self.interval.addItem(title,value)
        self.content.addWidget(row(label('Zeitplan'),self.interval,button('Zeitplan übernehmen',self.set_schedule)))
        self.snapshots=QTreeWidget(); self.snapshots.setHeaderLabels(['Sicherungsstand','Quellen']); self.snapshots.setRootIsDecorated(False)
        self.snapshots.setAccessibleName('Gesicherte Versionen'); self.content.addWidget(self.snapshots,1)
        self.content.addWidget(row(button('Stände laden',lambda:self.action('snapshots'),'view-refresh'),
            button('Inhalt ansehen',self.show_files,'document-preview'),button('Stand wiederherstellen',self.restore,'edit-undo')))
        self.content.addWidget(row(button('Struktur prüfen',lambda:self.action('check'),'dialog-ok-apply'),
            button('Alle Sicherungsdaten prüfen',lambda:self.action('check',full=True),'security-high')))
        self.content.addWidget(label('Wiederherstellungen landen in einem neuen Ordner. Das Sicherungspasswort zusätzlich außerhalb dieses Rechners aufbewahren.','muted'))
        self.body.setEnabled(False);self.refresh()

    def create(self):
        if not vault.binary():self.status.setText('Bitte zuerst unter Einrichtung „Vault vorbereiten“ wählen.');self.setup();return
        dialog=QDialog(self);dialog.setWindowTitle('Sicherung einrichten');dialog.resize(620,440);form=QFormLayout(dialog)
        title=QLineEdit('Meine Sicherung');repo=QLineEdit();source=QLineEdit();password=QLineEdit();password.setEchoMode(QLineEdit.Password)
        confirm=QLineEdit();confirm.setEchoMode(QLineEdit.Password)
        def choose(field):
            path=QFileDialog.getExistingDirectory(dialog,'Ordner auswählen',str(Path.home()))
            if path:field.setText(path)
        form.addRow('Name',title);form.addRow('USB-/NAS-Zielordner',row(repo,button('Wählen',lambda:choose(repo))))
        form.addRow('Erster Quellordner',row(source,button('Wählen',lambda:choose(source))))
        desktop=QCheckBox('Lumen- und KDE-Einstellungen ebenfalls sichern');form.addRow(desktop)
        form.addRow('Sicherungspasswort',password);form.addRow('Wiederholen',confirm)
        form.addRow(label('Neues Ziel: leerer Ordner. Vorhandenes Restic-Ziel: bisheriges Sicherungspasswort verwenden. Passwörter speichert der System-Schlüsselbund.'))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec_()!=QDialog.Accepted:return
        if password.text()!=confirm.text():raise ValueError('Die Passwörter stimmen nicht überein.')
        sources=([source.text()] if source.text().strip() else [])+(vault.config_sources() if desktop.isChecked() else [])
        name,target,key=title.text(),repo.text(),password.text()
        self.work('Sicherungsziel wird vorbereitet …',lambda job:vault.create(self.library,name,target,sources,key,job),self.focus_record)

    def load(self,plan):
        self.summary.setText(plan['title']);self.sources.clear();self.sources.addItems(plan['sources']);self.snapshots.clear()
        self.interval.setCurrentIndex(self.interval.findData(plan.get('interval',0)))
        last=plan.get('last_backup');when=datetime.fromtimestamp(last).strftime('%d.%m.%Y %H:%M') if last else 'Noch keine abgeschlossene Sicherung'
        self.details.setText(plan['repository']+'\n'+when+('\n'+plan['last_error'] if plan.get('last_error') else ''))
        self.status.setText('Sicherungsplan lokal gespeichert · Ziel wird erst bei einer Aktion geöffnet')

    def add_source(self):
        folder=QFileDialog.getExistingDirectory(self,'Quellordner hinzufügen',str(Path.home()))
        if folder:
            plan=self.library.get(self.current);_,sources=vault.paths(plan['repository'],plan['sources']+[folder])
            self.library.update(self.current,sources=sources);self.focus_record(self.current)

    def remove_source(self):
        item=self.sources.currentItem()
        if not item:return
        plan=self.library.get(self.current);sources=[v for v in plan['sources'] if v!=item.text()]
        if not sources:raise ValueError('Mindestens eine Quelle muss erhalten bleiben.')
        self.library.update(self.current,sources=sources);self.focus_record(self.current)

    def action(self,action,**kwargs):
        if not self.current:return
        key=self.current
        def done(value):
            if action=='snapshots':
                self.snapshots.clear()
                for snapshot in reversed(value):
                    item=QTreeWidgetItem([snapshot['time'][:19].replace('T',' '),' · '.join(snapshot.get('paths',[]))])
                    item.setData(0,Qt.UserRole,snapshot['id']);self.snapshots.addTopLevelItem(item)
                self.status.setText(f'{len(value)} Sicherungsstände geladen')
            elif action in ('preview','backup'):
                self.status.setText(('Vorschau: ' if action=='preview' else 'Gesichert: ')+f"{value.get('total_files_processed',0)} Dateien · {value.get('total_bytes_processed',0)/1024**2:.1f} MiB")
                if action=='backup':self.load(self.library.get(key));self.status.setText('Sicherung erfolgreich abgeschlossen.')
            else:self.status.setText(str(value))
        self.work('Sicherung wird '+{'backup':'erstellt','preview':'vorgeprüft','snapshots':'gelesen','check':'geprüft'}.get(action,action)+' …',
            lambda job:vault.run(self.library,key,action,job,**kwargs),done)

    def selected(self):
        item=self.snapshots.currentItem()
        if not item:raise ValueError('Bitte einen Sicherungsstand auswählen.')
        return item.data(0,Qt.UserRole)

    def show_files(self):
        self.safe(self._show_files)

    def _show_files(self):
        snapshot=self.selected();key=self.current
        def show(items):
            dialog=QDialog(self);dialog.setWindowTitle('Gesicherte Dateien');dialog.resize(780,600);form=QFormLayout(dialog)
            listing=QListWidget();listing.setAccessibleName('Dateien dieses Sicherungsstands');form.addRow(listing)
            for value in items:
                item=QListWidgetItem(value.get('path',''));item.setData(Qt.UserRole,value);listing.addItem(item)
            form.addRow(button('Auswahl wiederherstellen',lambda:self._restore_from_dialog(dialog,listing,snapshot)))
            # The worker completes after its result signal; defer this modal window.
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0,dialog.exec_)
        self.work('Gesicherte Pfade werden geladen …',lambda job:vault.run(self.library,key,'files',job,snapshot=snapshot),show)

    def _restore_from_dialog(self,dialog,listing,snapshot):
        item=listing.currentItem()
        if item:dialog.accept();self.safe(self.restore_selected,snapshot,item.data(Qt.UserRole)['path'])

    def restore(self):self.safe(lambda:self.restore_selected(self.selected()))

    def restore_selected(self,snapshot,selected=''):
        folder=QFileDialog.getExistingDirectory(self,'Wiederherstellung: übergeordneten Zielordner wählen',str(Path.home()))
        if not folder:return
        key=self.current
        def done(path):self.status.setText('Wiederhergestellt und geprüft: '+path);open_path(path)
        self.work('Daten werden in einen neuen Ordner wiederhergestellt …',lambda job:vault.run(self.library,key,'restore',job,snapshot=snapshot,selected=selected,destination=folder),done)

    def set_schedule(self):
        if not self.current:return
        key=self.current;interval=self.interval.currentData()
        self.work('Zeitplan übernehmen …',lambda job:vault.schedule(self.library,key,interval,job),lambda _:self.status.setText('Zeitplan gespeichert. Bei gesperrtem Schlüsselbund oder fehlendem Medium wird gewartet.'))

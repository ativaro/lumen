"""A native backup desk: explicit plans and a recoverable timeline."""
from lumen_i18n import tr
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QCheckBox,
    QComboBox, QWidget, QLabel, QFrame, QPushButton, QHBoxLayout, QVBoxLayout, QStackedWidget, QScrollArea, QSizePolicy, QFileDialog, QInputDialog, QListWidget, QListWidgetItem, QMessageBox, QTreeWidget, QTreeWidgetItem)
from tools_ui import ToolWindow, button, label, row, open_path
import vault_data as vault


class Vault(ToolWindow):
    def __init__(self,root=None,*,embedded=False):
        self.embedded = embedded
        self.setup_dialog = None
        super().__init__('vault',tr('Lumen Vault'),tr('Deine Dateien und Einstellungen. Verschlüsselt gesichert, gezielt zurückholen.'),'document-encrypt',root)
        # Explicit laboratory installation; never silently enable production secrets.
        from PySide6.QtCore import QStandardPaths
        self.native_lab = (Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)) / 'lumen/vault-lab/bin/lumen-vault-lab').is_file()
        self.build_shell()
        if embedded:
            self.setWindowFlags(Qt.Widget)
            self.setMinimumSize(0, 0)
        self.add_button.setText(tr('Sicherung einrichten')); self.search.setPlaceholderText(tr('Sicherungspläne …'))
        self.summary=label(tr('Wähle einen Sicherungsplan oder richte deine erste Sicherung ein.'),'heading'); self.content.addWidget(self.summary)
        self.details=label(''); self.content.addWidget(self.details)
        self.resume_setup = button(tr('Einrichtung abschließen'), self.finish_setup)
        self.resume_setup.hide(); self.content.addWidget(self.resume_setup)
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
        self.backup_rows = [item.widget().layout() for i in range(self.content.count()) if (item := self.content.itemAt(i)).widget() and isinstance(item.widget().layout(), QHBoxLayout)]

    def build_shell(self):
        """Keep the backup engine/widgets; give them the same Vault navigation."""
        shell = self.centralWidget()
        shell.setObjectName('vaultBackupShell')
        outer = shell.layout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = outer.takeAt(0).layout()
        brand = header.takeAt(0).widget()
        apps = header.takeAt(0).widget()
        settings = header.takeAt(0).widget()
        header.deleteLater()
        titles = brand.findChildren(QLabel)
        titles[0].setObjectName('vaultBrand')
        titles[1].setText(tr('Deine Daten. In deiner Hand.'))
        titles[1].setObjectName('vaultTagline')
        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(48, 48)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 8, 0, 22)
        brand_row.setSpacing(12)
        brand.setVisible(not self.embedded)
        self.brand_icon.setVisible(not self.embedded)
        brand_row.addWidget(self.brand_icon)
        brand_row.addWidget(brand, 1)
        side = self.sidebar.layout()
        side.setContentsMargins(20, 20, 20, 20)
        side.insertLayout(0, brand_row)
        side.addSpacing(12)
        side.addWidget(settings)
        self.sidebar.setObjectName('vaultBackupSidebar')
        self.sidebar.setMinimumWidth(240 if self.embedded else 300)
        self.sidebar.setMaximumWidth(260 if self.embedded else 340)
        self.split.setHandleWidth(1)

        self.sections = QWidget()
        self.sections.setObjectName('vaultSections')
        self.sections.setAccessibleName(tr('Bereich'))
        self.sections.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        segment = QHBoxLayout(self.sections)
        segment.setContentsMargins(0, 0, 0, 0)
        segment.setSpacing(0)
        self.vault_tab = QPushButton(tr('Tresor'))
        self.backups_tab = QPushButton(tr('Sicherungen'))
        self.vault_tab.setObjectName('vaultTabLeft')
        self.backups_tab.setObjectName('vaultTabRight')
        self.backups_tab.setCheckable(True)
        self.backups_tab.setChecked(True)
        self.backups_tab.clicked.connect(lambda: self.backups_tab.setChecked(True))
        self.vault_tab.clicked.connect(self.open_preview)
        for tab in (self.vault_tab, self.backups_tab):
            tab.setCursor(Qt.PointingHandCursor)
            tab.setMinimumHeight(42)
            segment.addWidget(tab)
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(22, 16, 22, 16)
        top.addStretch()
        self.sections.setVisible(not self.embedded)
        if self.embedded:
            top.addWidget(label(tr('Sicherungen'), 'heading'))
        top.addWidget(self.sections)
        top.addStretch()
        apps.setText('Apps')
        apps.setToolTip('Lumen Apps')
        top.addWidget(apps)
        layout.addLayout(top)
        separator = QFrame()
        separator.setObjectName('vaultRule')
        separator.setFixedHeight(1)
        layout.addWidget(separator)
        self.backup_stack = QStackedWidget()
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(44, 44, 44, 44)
        empty_layout.setSpacing(16)
        empty_layout.addStretch()
        empty_layout.addWidget(label(tr('Deine Dateien. Gut gesichert.'), 'vaultEmptyTitle'))
        empty_layout.addWidget(label(tr('Lege einen Sicherungsplan an oder wähle links einen vorhandenen Plan.'), 'muted'))
        create = button(tr('Sicherung einrichten'), lambda: self.safe(self.create), 'list-add', True)
        empty_layout.addWidget(create, 0, Qt.AlignLeft)
        empty_layout.addStretch()
        self.backup_stack.addWidget(empty)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.body)
        self.backup_stack.addWidget(scroll)
        self.content.setContentsMargins(28, 26, 28, 24)
        layout.addWidget(self.backup_stack, 1)
        self.split.addWidget(main)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([260 if self.embedded else 310, 900])
        footer = outer.itemAt(outer.count() - 1).widget()
        footer.layout().setContentsMargins(24, 14, 24, 14)
        self.resize(1440, 900)
        self.setMinimumSize(1080, 720)
        shell.setStyleSheet("""
            QWidget#vaultBackupShell { background: palette(window); }
            QWidget#vaultBackupSidebar { background: palette(base); border-right: 1px solid palette(mid); }
            QLabel#vaultBrand { font-size: 24px; font-weight: 500; }
            QLabel#vaultTagline { font-size: 12px; color: palette(placeholder-text); }
            QLabel#vaultEmptyTitle { font-size: 28px; font-weight: 500; }
            QWidget#vaultBackupShell QLabel#muted { font-size: 14px; color: palette(dark); }
            QWidget#vaultBackupShell QPushButton#toolButton { font-size: 14px;
                min-height: 26px; padding: 7px 12px; border: 1px solid palette(mid);
                border-radius: 8px; background: palette(button); }
            QWidget#vaultBackupSidebar QPushButton#toolButton { font-size: 16px;
                background: transparent; border: 0; text-align: left; }
            QWidget#vaultBackupShell QListWidget, QWidget#vaultBackupShell QTreeWidget {
                border: 1px solid palette(mid); border-radius: 8px; padding: 4px; }
            QWidget#vaultSections QPushButton { min-width: 110px; padding: 9px 20px;
                margin: 0; border: 1px solid palette(mid); border-radius: 0;
                background: palette(base); color: palette(text); }
            QWidget#vaultSections QPushButton#vaultTabLeft { border-top-left-radius: 9px; border-bottom-left-radius: 9px; }
            QWidget#vaultSections QPushButton#vaultTabRight { border-top-right-radius: 9px; border-bottom-right-radius: 9px; border-left: 0; }
            QWidget#vaultSections QPushButton:checked { background: palette(highlight); color: palette(highlighted-text); }
            QWidget#vaultSections QPushButton:hover { border-color: palette(highlight); }
            QWidget#vaultSections QPushButton:focus { border: 2px solid palette(highlight); }
            QFrame#vaultRule { background: palette(mid); }
        """)
        self.update_brand_icon()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.embedded:
            for layout in getattr(self, 'backup_rows', []):
                layout.setDirection(QHBoxLayout.TopToBottom if self.width() < 1100 else QHBoxLayout.LeftToRight)

    def update_brand_icon(self):
        from PySide6.QtGui import QPixmap, QPainter, QPalette
        pixmap = QPixmap(str(Path(__file__).with_name('lumen-vault-mark.svg'))).scaled(
            48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if not pixmap.isNull():
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), self.palette().color(QPalette.WindowText))
            painter.end()
        self.brand_icon.setPixmap(pixmap)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange and hasattr(self, 'brand_icon'):
            self.update_brand_icon()

    def refresh(self):
        super().refresh()
        if hasattr(self, 'backup_stack'):
            self.backup_stack.setCurrentIndex(1 if self.current else 0)

    def focus_record(self, key):
        super().focus_record(key)
        self.backup_stack.setCurrentIndex(1)

    def open_preview(self):
        from PySide6.QtCore import QProcess
        from lumen_launch import executable
        started, _ = QProcess.startDetached(executable('lumen-vault'), ['--lab' if self.native_lab else '--preview'])
        if not started: self.error(tr('Die Tresor-Vorschau konnte nicht geöffnet werden.'))

    def create(self,prefill_sources=None,on_done=None,source_ref=None,handoff=None):
        if self.job:return False
        if not vault.binary():self.status.setText(tr('Bitte zuerst unter Einrichtung „Vault vorbereiten“ wählen.'));self.setup();return False
        if not prefill_sources and not source_ref and not handoff:
            from backup_setup_ui import BackupWizard
            dialog = BackupWizard(self.library, self); self.setup_dialog = dialog
            try:
                result = dialog.exec()
                if result != QDialog.Accepted: dialog.reject()
                if dialog.plan_id: self.focus_record(dialog.plan_id)
                if on_done: on_done(dialog.plan_id or None)
                return bool(dialog.plan_id)
            finally:
                self.setup_dialog = None; dialog.deleteLater()
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
        interval=QComboBox();interval.setAccessibleName(tr('Sicherungsrhythmus'))
        for caption,value in [(tr('Nur manuell'),0),(tr('Täglich'),86400),(tr('Wöchentlich'),604800)]:interval.addItem(caption,value)
        form.addRow(tr('Zeitplan'),interval)
        form.addRow(tr('Sicherungspasswort'),password);form.addRow(tr('Wiederholen'),confirm)
        form.addRow(label(tr('Neues Ziel: leerer Ordner. Vorhandenes Restic-Ziel: bisheriges Sicherungspasswort verwenden. Passwörter speichert der System-Schlüsselbund.')))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec()!=QDialog.Accepted:return False
        if password.text()!=confirm.text():raise ValueError(tr('Die Passwörter stimmen nicht überein.'))
        sources=([source.text()] if source.text().strip() else [])+[row['path'] for row in prefill_sources[1:]]+(vault.config_sources() if desktop.isChecked() else [])
        name,target,key,rhythm=title.text(),repo.text(),password.text(),interval.currentData()
        created=[]
        def prepare(job):
            chosen=[row for row in prefill_sources if row['path'] in sources]
            identity=vault.create(self.library,name,target,sources,key,job,app_sources=chosen,source_ref=source_ref,handoff=handoff,interval=rhythm)
            created.append(identity)
            if rhythm:vault.schedule(self.library,identity,rhythm,job)
            return identity
        def complete(identity):
            self.focus_record(identity)
            if on_done:on_done(identity)
        def failed(message):
            if created:self.focus_record(created[0])
            if on_done:on_done(None)
        self.work(tr('Sicherungsziel wird vorbereitet …'),prepare,complete,failed=failed)
        return bool(self.job)

    def archive(self):
        if not self.current or self.job: return
        from vault_service import execute
        identity, archived = self.current, not self.archived.isChecked()
        if archived and QMessageBox.question(self, tr('Sicherungsplan archivieren'),
                tr('Zeitplan deaktivieren und diesen Plan archivieren? Sicherungsdaten und Schlüssel bleiben erhalten.'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        def done(_):
            self.current=''; self.body.setEnabled(False); self.refresh()
        self.work(tr('Sicherungsplan wird aktualisiert …'),
                  lambda job: execute(self.library, dict(op='archive', id=identity, archived=archived), job), done)

    def load(self,plan):
        self.resume_setup.setVisible(bool(plan.get('setup_pending')))
        self.summary.setText(plan['title']);self.sources.clear();self.sources.addItems(plan['sources']);self.snapshots.clear()
        self.interval.setCurrentIndex(self.interval.findData(plan.get('interval',0)))
        last=plan.get('last_backup');when=datetime.fromtimestamp(last).strftime('%d.%m.%Y %H:%M') if last else tr('Noch keine abgeschlossene Sicherung')
        self.details.setText(plan['repository']+'\n'+when+('\n'+plan['last_error'] if plan.get('last_error') else ''))
        groups = plan.get('groups', {})
        if groups:
            lines=[]
            for key, title in [('files', tr('Meine Dateien')), ('lumen', tr('Mein Lumen')), ('vault', tr('Mein Tresor'))]:
                selected=groups.get(key, [])
                verified=bool(selected) and selected==plan.get('backup_groups', {}).get(key, []) and plan['sources']==plan.get('backup_sources')
                state=tr('Nicht im Plan ausgewählt') if not selected else tr('Gesichert · Wiederherstellungsprobe erfolgreich') if verified else tr('Ausgewählt · nächste Sicherung ausstehend')
                lines.append(title+': '+state)
            self.details.setText(self.details.text()+'\n'+'\n'.join(lines))
        if plan.get('schedule_pending') is not None:
            self.interval.setCurrentIndex(self.interval.findData(plan['schedule_pending']))
            self.details.setText(self.details.text()+'\n'+tr('Zeitplan noch nicht aktiviert. „Zeitplan übernehmen“ erneut wählen.'))
        if plan.get('app_sources'):
            self.details.setText(self.details.text()+'\n'+tr('Lumen-Daten: gespeicherte Dateien und konsistente Datenbankkopien. Ungespeicherte Fensteränderungen sind nicht enthalten.'))
        if plan.get('backup_flushes'):
            from interop_vault import APP_NAMES
            text=' · '.join(tr(APP_NAMES.get(row['app'],row['app']))+' '+datetime.fromtimestamp(row['flushed_at']).strftime('%H:%M:%S') for row in plan['backup_flushes'])
            self.details.setText(self.details.text()+'\n'+tr('Vor der letzten Sicherung gespeichert bestätigt: {0}',text))
        if any(row.get('kind')=='inbox-local' for row in plan.get('app_sources',[])):
            self.details.setText(self.details.text()+'\n'+tr('Lumen Inbox: nur lokale Aufgaben und ungesendete Entwürfe mit Anhängen sichern'))
        self.status.setText(tr('Sicherungsplan lokal gespeichert · Ziel wird erst bei einer Aktion geöffnet'))

    def finish_setup(self):
        from backup_setup import finish_setup
        key = self.current
        if not key: return
        self.work(tr('Erste Sicherung und Wiederherstellungsprobe …'),
                  lambda job: finish_setup(self.library, key, job),
                  lambda _: self.focus_record(key))

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
                if question.exec()!=QMessageBox.Yes:return
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
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,dialog.exec)
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

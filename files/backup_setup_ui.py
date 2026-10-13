"""System backup setup using the native wizard's existing backend operations."""
from pathlib import Path
from urllib.parse import urlsplit
import secrets
from PySide6.QtCore import Qt, QTimer, Signal, QSaveFile, QIODevice, QFileDevice
from PySide6.QtWidgets import (QWidget, QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QLineEdit, QCheckBox, QListWidget,
    QListWidgetItem, QComboBox, QStackedWidget, QFileDialog, QDialog)
from lumen_i18n import tr
from lumen_jobs import Job
from tools_ui import label, button, row
from vault_service import execute


def private_field():
    field = QLineEdit(); field.setEchoMode(QLineEdit.Password); field.setMaxLength(4096)
    field.setInputMethodHints(Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhHiddenText)
    field.setContextMenuPolicy(Qt.NoContextMenu)
    return field


def export_key(path, destination, content):
    chosen = Path(path)
    parent = chosen.parent.resolve(strict=True)
    if chosen.is_symlink(): raise ValueError(tr('Bitte eine eigene Schlüsseldatei wählen.'))
    if not destination.startswith('rest:https://'):
        target = Path(destination).resolve(strict=True)
        if (parent/chosen.name).is_relative_to(target):
            raise ValueError(tr('Bitte den Schlüssel außerhalb des Sicherungsziels speichern.'))
    output = QSaveFile(str(parent/chosen.name)); output.setDirectWriteFallback(False)
    if not output.open(QIODevice.WriteOnly): raise OSError(output.errorString())
    if not output.setPermissions(QFileDevice.ReadOwner | QFileDevice.WriteOwner):
        output.cancelWriting(); raise OSError(output.errorString())
    data = content.encode()
    if output.write(data) != len(data) or not output.commit():
        output.cancelWriting(); raise OSError(tr('Schlüsseldatei konnte nicht gespeichert werden.'))


class NetworkPicker(QWidget):
    selected = Signal(dict)

    def __init__(self, request, writable=True, parent=None):
        super().__init__(parent); self.request = request; self.writable = writable
        self.selection = {}; self.host = ''
        layout = QVBoxLayout(self); self.uri = QLineEdit(); self.uri.setPlaceholderText('smb://server/freigabe')
        self.uri.setAccessibleName(tr('Server oder Freigabe'))
        layout.addWidget(row(self.uri, button(tr('Öffnen'), lambda: self.perform('browse')),
                             button(tr('Netzwerk suchen'), lambda: self.perform('discover'))))
        self.places = QListWidget(); self.places.setAccessibleName(tr('Server und Freigaben')); self.places.setMaximumHeight(160)
        layout.addWidget(self.places); form = QFormLayout(); layout.addLayout(form)
        self.user = QLineEdit(); self.password = private_field(); self.domain = QLineEdit()
        for title, field in ((tr('Benutzername'), self.user), (tr('Passwort'), self.password), (tr('Domäne'), self.domain)):
            form.addRow(title, field); field.textChanged.connect(self.invalidate)
        self.remember = QCheckBox(tr('Zugang im System-Schlüsselbund merken')); layout.addWidget(self.remember)
        self.remember.toggled.connect(self.invalidate); self.uri.textChanged.connect(self.changed_address)
        self.use = button(tr('Verbindung testen und Ziel verwenden') if writable else tr('Ordner verbinden und auswählen'),
                          lambda: self.perform('test' if writable else 'resolve'))
        layout.addWidget(self.use); self.status = label(''); layout.addWidget(self.status)
        self.places.itemClicked.connect(lambda item: self.uri.setText(item.data(Qt.UserRole)))
        self.places.itemDoubleClicked.connect(lambda _: self.perform('browse'))

    def invalidate(self, *_): self.selection = {}

    def changed_address(self, value):
        try: host = urlsplit(value if value.startswith('smb://') else 'smb://'+value).netloc
        except ValueError: host = ''
        if host != self.host:
            self.user.clear(); self.password.clear(); self.domain.clear()
        self.host = host; self.invalidate()

    def perform(self, action):
        self.setEnabled(False)
        args = dict(op='network', action=action, uri='smb://' if action == 'discover' else self.uri.text(),
                    username=self.user.text(), password=self.password.text(), domain=self.domain.text(),
                    remember=self.remember.isChecked(), network_id=self.selection.get('network_id', ''))
        self.selection = {}; self.status.setText(tr('Verbindung wird geprüft …'))
        def done(result):
            self.setEnabled(True)
            if action in ('test', 'resolve'):
                self.password.clear(); self.selection = result
                self.status.setText(tr('Verbunden. Der Ordner ist bereit.')); self.selected.emit(result)
            else:
                self.places.clear()
                for value in result.get('items', []):
                    item = QListWidgetItem(value['label'], self.places); item.setData(Qt.UserRole, value['uri'])
                self.status.setText(tr('Server/Freigabe wählen oder eine Adresse eingeben.'))
        def failed(message):
            self.setEnabled(True); self.status.setText(message)
        self.request(args, done, failed)


class BackupWizard(QWizard):
    def __init__(self, library, parent=None):
        super().__init__(parent); self.library = library; self.job = None
        self.plan_id = ''; self.destination = {}; self.remotes = []; self.closing = False; self.completed = False
        self.setWindowTitle(tr('Lumen Sicherung einrichten')); self.resize(840, 740)
        self.setStyleSheet('QCheckBox::indicator { width: 16px; height: 16px; } QCheckBox::indicator:unchecked { border: 1px solid palette(mid); border-radius: 3px; background: palette(base); }')
        self.setWizardStyle(QWizard.ModernStyle)
        for key, text in ((QWizard.WizardButton.NextButton, tr('Weiter')), (QWizard.WizardButton.BackButton, tr('Zurück')),
                          (QWizard.WizardButton.CancelButton, tr('Abbrechen')), (QWizard.WizardButton.FinishButton, tr('Sicherung starten'))):
            self.setButtonText(key, text)
        def page(title):
            p = QWizardPage(); p.setTitle(title); self.addPage(p)
            return QVBoxLayout(p)
        sources = page(tr('1 · Was möchtest du schützen?'))
        sources.addWidget(label(tr('Gespeicherte Daten auswählen. Offene, ungespeicherte Änderungen sind nicht enthalten.')))
        cards = QHBoxLayout(); sources.addLayout(cards); self.groups_ui = {}
        for key, title in (('files', tr('Meine Dateien')), ('lumen', tr('Mein Lumen')), ('vault', tr('Mein Tresor'))):
            group = QGroupBox(title); group.setCheckable(True); listing = QListWidget()
            listing.setAccessibleName(title); QVBoxLayout(group).addWidget(listing)
            cards.addWidget(group); self.groups_ui[key] = (group, listing)
        sources.addWidget(row(button(tr('Weiteren Ordner hinzufügen'), self.add_folder),
                              button(tr('Ordner vom NAS hinzufügen'), self.add_network)))
        targets = page(tr('2 · Wo soll die Sicherung liegen?'))
        self.kind = QComboBox(); self.kind.setAccessibleName(tr('Art des Sicherungsziels'))
        for title, key in ((tr('Laufwerk / Ordner'), 'local'), (tr('NAS / Netzwerk'), 'network'), ('Lumen Server', 'server')):
            self.kind.addItem(title, key)
        targets.addWidget(self.kind); self.targets = QStackedWidget(); targets.addWidget(self.targets)
        self.target = QLineEdit(); self.target.setAccessibleName(tr('Sicherungsziel'))
        self.targets.addWidget(row(self.target, button(tr('Auswählen …'), self.choose_target)))
        self.network = NetworkPicker(self.work); self.targets.addWidget(self.network)
        server = QWidget(); server_layout = QVBoxLayout(server); self.servers = QComboBox()
        self.servers.setAccessibleName(tr('Gekoppelter Server')); server_layout.addWidget(self.servers)
        server_layout.addWidget(label(tr('Gekoppelten Server auswählen. Dateien werden vor dem Hochladen verschlüsselt. Ohne Verbindung zuerst im Server unter Geräte diesen Desktop verbinden.')))
        self.targets.addWidget(server)
        self.kind.currentIndexChanged.connect(self.targets.setCurrentIndex)
        for signal in (self.kind.currentIndexChanged, self.target.textChanged, self.servers.currentIndexChanged):
            signal.connect(self.invalidate_target)
        protection = page(tr('3 · Schlüssel und Zeitplan'))
        form = QFormLayout(); protection.addLayout(form)
        self.name = QLineEdit(tr('Meine Sicherung')); self.schedule = QComboBox()
        for title, interval in ((tr('Täglich'), 86400), (tr('Wöchentlich'), 604800), (tr('Manuell'), 0)):
            self.schedule.addItem(title, interval)
        self.key = private_field(); self.key.setText(secrets.token_hex(32))
        form.addRow(tr('Name'), self.name); form.addRow(tr('Sichern'), self.schedule); form.addRow(tr('Sicherungsschlüssel'), self.key)
        self.hint = label(''); protection.addWidget(self.hint)
        self.export = button(tr('Wiederherstellungsschlüssel als Datei sichern …'), self.save_key); protection.addWidget(self.export)
        self.saved = QCheckBox(tr('Ich habe den Schlüssel unabhängig aufbewahrt.')); protection.addWidget(self.saved)
        self.key.textChanged.connect(lambda: self.saved.setChecked(False)); protection.addStretch()
        last = page(tr('4 · Prüfen und starten')); self.review = label(''); last.addWidget(self.review); last.addStretch()
        for index in self.pageIds():
            self.page(index).status = label(''); self.page(index).layout().addWidget(self.page(index).status)
        self.currentIdChanged.connect(self.enter_page)
        QTimer.singleShot(0, lambda: self.work(dict(op='setup_inventory'), self.inventory))

    def message(self, text):
        for index in self.pageIds(): self.page(index).status.setText(text)

    def work(self, args, done, failed=None):
        if self.job or self.closing: return
        self.message(tr('Bitte warten …')); self.currentPage().setEnabled(False)
        for key in (QWizard.WizardButton.NextButton, QWizard.WizardButton.BackButton, QWizard.WizardButton.FinishButton): self.button(key).setEnabled(False)
        outcome = {}; op = args['op']; job = Job(lambda worker: execute(self.library, args, worker), self); self.job = job
        job.result.connect(lambda value: outcome.update(value=value))
        job.failed.connect(lambda error: outcome.update(error=error)); job.progress.connect(self.message)
        def finished():
            self.job = None; job.function = None; job.deleteLater(); args.clear()
            value = outcome.get('value')
            if op == 'configure' and value: self.plan_id = value['id']
            self.currentPage().setEnabled(True)
            for key in (QWizard.WizardButton.NextButton, QWizard.WizardButton.FinishButton): self.button(key).setEnabled(True)
            self.button(QWizard.WizardButton.BackButton).setEnabled(not self.plan_id)
            if self.closing: self.reject(); return
            self.message('')
            if 'error' in outcome:
                self.message(outcome['error'])
                if failed: failed(outcome['error'])
            else: done(value)
        job.finished.connect(finished); job.start()

    def inventory(self, values):
        for key, (group, listing) in self.groups_ui.items():
            listing.clear()
            for item in values[key]: self.append_source(key, item['path'], item['label'])
            group.setChecked(bool(listing.count()))
        for item in values['servers']: self.servers.addItem(item['label'], item['server_target'])

    def append_source(self, group, path, title):
        box, listing = self.groups_ui[group]
        if any(listing.item(i).data(Qt.UserRole) == path for i in range(listing.count())): return
        item = QListWidgetItem(title, listing); item.setData(Qt.UserRole, path); item.setToolTip(path)
        item.setCheckState(Qt.Checked); box.setChecked(True)

    def groups(self):
        return {key: [listing.item(i).data(Qt.UserRole) for i in range(listing.count())
                      if group.isChecked() and listing.item(i).checkState() == Qt.Checked]
                for key, (group, listing) in self.groups_ui.items()}

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, tr('Ordner schützen'))
        if path: self.append_source('files', path, path)

    def choose_target(self):
        path = QFileDialog.getExistingDirectory(self, tr('Sicherungsziel'))
        if path: self.target.setText(path)

    def add_network(self):
        wizard = self
        class NetworkDialog(QDialog):
            def reject(self):
                if wizard.job:
                    wizard.job.cancelled.set(); wizard.message(tr('Wird abgebrochen …')); return
                super().reject()
        dialog = NetworkDialog(self); dialog.setWindowTitle(tr('Lumen Netzwerkordner')); dialog.resize(680, 560)
        picker = NetworkPicker(self.work, writable=False); QVBoxLayout(dialog).addWidget(picker)
        def selected(value):
            self.append_source('files', value['path'], value['uri'])
            self.remotes = [r for r in self.remotes if r['path'] != value['path']]
            self.remotes.append({key: value.get(key, '') for key in ('path', 'uri', 'network_id')}); dialog.accept()
        picker.selected.connect(selected); dialog.exec(); picker.password.clear(); dialog.deleteLater()

    def invalidate_target(self, *_):
        self.destination = {}
        if hasattr(self, 'saved'): self.saved.setChecked(False)

    def set_destination(self, value):
        if self.destination != value:
            self.key.setText('' if value.get('existing') else secrets.token_hex(32))
        self.destination = value

    def validateCurrentPage(self):
        if self.job or self.closing: return False
        if self.currentId() == 1:
            kind = self.kind.currentData()
            if kind == 'network':
                if not self.network.selection.get('path'):
                    self.message(tr('Bitte die Freigabe verbinden und testen.')); return False
                self.set_destination(dict(self.network.selection))
            else:
                if kind == 'server':
                    selected = self.servers.currentData()
                    if not selected:
                        self.message(tr('Lumen Server zuerst unter Geräte mit diesem Desktop verbinden.')); return False
                    valid = self.destination.get('server_target') == selected
                    args = dict(op='test_target', server_target=selected)
                else:
                    valid = self.destination.get('path') == self.target.text() and bool(self.target.text())
                    args = dict(op='test_target', path=self.target.text())
                if not valid:
                    def checked(value):
                        if kind == 'local':
                            self.target.blockSignals(True); self.target.setText(value['path']); self.target.blockSignals(False)
                        self.set_destination(value); self.next()
                    self.work(args, checked); return False
        if self.currentId() == 2:
            existing = self.destination.get('existing', False)
            if len(self.key.text()) < (1 if existing else 12) or (not existing and not self.saved.isChecked()):
                self.message(tr('Schlüssel eingeben und seine unabhängige Aufbewahrung bestätigen.')); return False
        return True

    def enter_page(self, index):
        self.message('')
        existing = self.destination.get('existing', False)
        if index == 2:
            self.saved.setVisible(not existing); self.export.setVisible(not existing); self.schedule.setEnabled(not existing)
            self.hint.setText(tr('Bestehende Sicherung erkannt. Gib ihren bisherigen Sicherungsschlüssel ein.') if existing else
                             tr('Bewahre den Schlüssel getrennt vom Sicherungsziel auf. Der Tresor benötigt weiterhin sein eigenes Master-Passwort.'))
        if index == 3:
            counts = '\n'.join(f'{self.groups_ui[key][0].title()}: {len(values)}' for key, values in self.groups().items())
            self.review.setText(self.name.text()+'\n\n'+self.destination.get('uri', self.destination.get('path', ''))+'\n\n'+counts+'\n\n'+
                                (tr('Bestehende Sicherung zum Wiederherstellen verbinden.') if existing else self.schedule.currentText()+'\n'+tr('Erste Sicherung und Wiederherstellungsprobe. Erst danach wird der Zeitplan aktiviert.')))
            self.setButtonText(QWizard.WizardButton.FinishButton, tr('Sicherung verbinden') if existing else tr('Sicherung starten'))

    def save_key(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Unabhängig aufbewahren'), 'Lumen-Wiederherstellung.txt', 'Text (*.txt)')
        if not path: return
        try:
            export_key(path, self.destination['path'], 'Lumen · '+self.name.text()+'\n'+self.destination.get('uri', self.destination['path'])+
                       '\n'+tr('Sicherungsschlüssel')+': '+self.key.text()+'\n\n'+
                       tr('Wiederherstellung: Lumen System → Sicherungen → vorhandenes Ziel verbinden. Für Serverziele auch den zugehörigen Serverzugang aufbewahren; eine neue Gerätekopplung erzeugt ein anderes Ziel.')+'\n')
            self.message(tr('Schlüssel gespeichert. Seine unabhängige Aufbewahrung anschließend bestätigen.'))
        except (OSError, ValueError) as error: self.message(str(error))

    def accept(self):
        if self.job or self.closing: return
        if self.completed: self.clear_secrets(); super().accept(); return
        if self.currentId() != 3 or not self.destination: return
        selected = self.groups(); existing = self.destination.get('existing', False)
        if not existing and not any(selected.values()): self.message(tr('Mindestens eine Quelle auswählen.')); return
        def complete(_):
            self.completed = True; self.clear_secrets(); self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.review.setText(tr('Sicherung eingerichtet. Erste Sicherung und Wiederherstellungsprobe erfolgreich.'))
            self.setButtonText(QWizard.WizardButton.FinishButton, tr('Fertig'))
        def finish(): self.work(dict(op='finish_setup', id=self.plan_id), complete)
        if self.plan_id: finish(); return
        args = dict(op='configure', title=self.name.text(), repository=self.destination['path'],
                    network_uri=self.destination.get('uri', ''), network_id=self.destination.get('network_id', ''),
                    server_target=self.destination.get('server_target'), password=self.key.text(), groups=selected,
                    remote_sources=[r for r in self.remotes if r['path'] in selected['files']],
                    interval=self.schedule.currentData(), recovery_confirmed=self.saved.isChecked(), adopt=existing)
        def configured(result):
            if result.get('restored_connection'):
                self.completed = True; self.accept()
            else: finish()
        self.work(args, configured)

    def clear_secrets(self):
        self.key.clear(); self.network.password.clear()

    def reject(self):
        self.closing = True; self.clear_secrets()
        if self.job:
            self.job.cancelled.set(); self.message(tr('Wird abgebrochen …')); return
        super().reject()

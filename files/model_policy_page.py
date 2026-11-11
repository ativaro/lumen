"""Settings page for the model policy: allowed models, privacy and limits for background work."""
from lumen_i18n import tr
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QLabel, QMessageBox, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget)
from lumen_store import Store
from plan_dialog import buttons


def page(title, description):
    widget = QWidget(); layout = QVBoxLayout(widget)
    heading = QLabel(title); heading.setObjectName('heading'); heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); layout.addWidget(heading)
    info = QLabel(description); info.setWordWrap(True); info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); layout.addWidget(info)
    return widget, layout


class ModelPolicyPage(QObject):
    def __init__(self, window, store=None):
        super().__init__(window); self.window = window
        self.store = store or (window.chat.tracker.store if hasattr(window, 'chat') else Store())
        self.model_backend = None
        widget = self.build_models(); widget.setParent(window); self.models_page = widget

    def guarded(self, fn):
        def call(*_):
            try: fn()
            except Exception as exc: QMessageBox.warning(self.window, 'Lumen', str(exc))
        return call

    def build_models(self):
        widget, box = page(tr('Modelle & Ressourcen'), tr('Wähle, welche Modelle Lumen verwenden darf. „Lokaler Dienst“ erzwingt eine Loopback-Adresse; dessen eigene Weiterleitungen bleiben dessen Verantwortung.'))
        form = QFormLayout(); box.addLayout(form); policy = self.store.setting('modelPolicy', {})
        self.privacy = QComboBox(); self.privacy.addItem(tr('Konfigurierte Anbieter (auch Cloud)'), 'configured'); self.privacy.addItem(tr('Nur lokaler Dienst'), 'local')
        self.privacy.setCurrentIndex(1 if policy.get('privacy') == 'local' else 0); form.addRow(tr('Verarbeitung'), self.privacy)
        self.model_controls = {}
        for key, title in [('model', tr('Standardmodell')), ('background_model', tr('Modell für wiederkehrende KI-Aufträge')), ('local_model', tr('Lokales Modell'))]:
            control = QComboBox(); control.setEditable(True); control.addItem(policy.get(key, '')); control.setAccessibleName(title)
            form.addRow(title, control); self.model_controls[key] = control
        self.timeout = QSpinBox(); self.timeout.setRange(1, 120); self.timeout.setValue(int(policy.get('timeout_seconds', 900))//60); self.timeout.setSuffix(tr(' Minuten')); form.addRow(tr('Zeitlimit pro KI-Auftrag'), self.timeout)
        self.gpu = QSpinBox(); self.gpu.setRange(1,100); self.gpu.setValue(int(policy.get('gpu_limit',90))); self.gpu.setSuffix(' %'); form.addRow(tr('Hintergrundarbeit pausiert ab GPU-Auslastung'), self.gpu)
        self.pause_background = QCheckBox(tr('Alle Hintergrundaufträge pausieren')); self.pause_background.setChecked(policy.get('pause_background',False)); box.addWidget(self.pause_background)
        self.model_status = QLabel(tr('GPU-Prüfung verwendet NVIDIA-SMI, wenn verfügbar. 100 % deaktiviert die GPU-Grenze.')); self.model_status.setWordWrap(True); box.addWidget(self.model_status)
        buttons(box, [(tr('Verfügbare Modelle laden'), self.load_models), (tr('Speichern'), self.guarded(self.save_models))]); box.addStretch(); return widget

    def load_models(self):
        if hasattr(self.window, 'chat'): backend = self.window.chat.backend
        else:
            if self.model_backend is None:
                from desktop_backend import DesktopBackend
                self.model_backend = DesktopBackend(self.directory(), self)
            backend = self.model_backend
        def loaded(data):
            names = [p['id'] + '/' + model for p in data.get('providers', []) for model in p.get('models', {})]
            for control in self.model_controls.values():
                old = control.currentText(); control.clear(); control.addItem(''); control.addItems(names); control.setCurrentText(old)
            self.model_status.setText(tr('{0} Modelle verfügbar. Lokale Anbieter in den Verbindungseinstellungen konfigurieren.', len(names)))
        backend.ensure_server(lambda: backend.request('GET','/config/providers',callback=loaded))

    def save_models(self):
        policy = self.store.setting('modelPolicy', {})
        policy.update({key: c.currentText().strip() for key,c in self.model_controls.items()})
        if self.privacy.currentData() == 'local' and '/' not in policy['local_model']: raise ValueError(tr('Lokales Modell als anbieter/modell auswählen.'))
        policy.update(privacy=self.privacy.currentData(),timeout_seconds=self.timeout.value()*60,gpu_limit=self.gpu.value(),pause_background=self.pause_background.isChecked())
        from PySide6.QtCore import QSettings
        settings = self.window.chat.settings if hasattr(self.window, 'chat') else getattr(self.window, 'assistant', None) or QSettings('Lumen', 'Assistant')
        if hasattr(self.window, 'preferencesChanged'): self.window.save(settings, {'model': policy['model']})
        else: settings.setValue('model', policy['model']); settings.sync()
        self.store.set_setting('modelPolicy',policy)
        self.model_status.setText(tr('Gespeichert. Die Richtlinie gilt ab dem nächsten Auftrag.'))

    def can_close(self):
        return True

    def directory(self):
        if hasattr(self.window, 'chat'): return self.window.chat.backend.directory
        from PySide6.QtCore import QSettings
        return QSettings('Lumen', 'Assistant').value('workdir', str(Path.home()))

    def shutdown(self):
        if self.model_backend is not None: self.model_backend.shutdown()

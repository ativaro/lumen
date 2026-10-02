"""Native sensor view, refreshed only while visible."""
import json
import sys
from pathlib import Path
from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QCheckBox, QLineEdit
from lumen_store import Store


class HardwareView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel('Messwerte werden beim Öffnen geladen.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.values = QTreeWidget(); self.values.setHeaderLabels(['Gerät / Sensor', 'Messwert']); self.values.setMinimumHeight(260)
        self.values.setAccessibleName('Hardware-Messwerte'); layout.addWidget(self.values)
        self.games = QCheckBox('Bei Spielen und geöffneten Aufnahmeprogrammen Hintergrundarbeit pausieren')
        self.games.setChecked(Store().setting('modelPolicy', {}).get('pause_on_activity', True)); layout.addWidget(self.games)
        self.games.toggled.connect(self.save)
        self.apps = QLineEdit(', '.join(Store().setting('modelPolicy', {}).get('activity_apps', [])))
        self.apps.setPlaceholderText('Weitere Prozessnamen, z. B. minecraft, supertuxkart')
        self.apps.setAccessibleName('Weitere Spiele oder Aufnahmeprogramme'); self.apps.setMaxLength(500)
        layout.addWidget(self.apps)
        save_apps = QPushButton('Weitere Programme übernehmen'); save_apps.clicked.connect(self.save_apps); layout.addWidget(save_apps)
        refresh = QPushButton('Messwerte aktualisieren'); refresh.clicked.connect(self.refresh); layout.addWidget(refresh)
        self.proc = QProcess(self); self.proc.finished.connect(self.loaded)
        self.timer = QTimer(self); self.timer.setInterval(10000); self.timer.timeout.connect(self.refresh)
        self.deadline = QTimer(self); self.deadline.setSingleShot(True); self.deadline.timeout.connect(self.proc.kill)

    def save(self, value):
        store = Store(); policy = store.setting('modelPolicy', {}); policy['pause_on_activity'] = value
        store.set_setting('modelPolicy', policy)

    def save_apps(self):
        import re
        names = sorted(set(v.strip().lower() for v in self.apps.text().split(',') if v.strip()))
        if any(not re.fullmatch(r'[a-z0-9_.-]{1,15}', v) for v in names):
            self.status.setText('Prozessnamen: maximal 15 Zeichen, Buchstaben, Zahlen, Punkt, Bindestrich oder Unterstrich.'); return
        store = Store(); policy = store.setting('modelPolicy', {}); policy['activity_apps'] = names
        store.set_setting('modelPolicy', policy); self.status.setText('Zusätzliche Programme gespeichert.')

    def showEvent(self, event):
        super().showEvent(event); self.timer.start(); self.refresh()

    def hideEvent(self, event):
        self.timer.stop(); self.deadline.stop(); self.proc.kill(); self.proc.waitForFinished(1000)
        super().hideEvent(event)

    def refresh(self):
        if self.proc.state() != QProcess.NotRunning: return
        self.status.setText('Hardware wird gelesen …')
        self.proc.start(sys.executable, [str(Path(__file__).with_name('lumen_hardware.py'))]); self.deadline.start(9000)

    def loaded(self, code):
        self.deadline.stop()
        expanded = {self.values.topLevelItem(i).toolTip(0) for i in range(self.values.topLevelItemCount()) if self.values.topLevelItem(i).isExpanded()}
        initial = self.values.topLevelItemCount() == 0; scroll = self.values.verticalScrollBar().value()
        self.values.clear()
        try:
            if code: raise ValueError()
            data = json.loads(bytes(self.proc.readAllStandardOutput()))
            groups = {}
            labels = {'Tctl':'CPU gesamt', 'Tccd1':'CPU-Chiplet 1', 'Tccd2':'CPU-Chiplet 2', 'Composite':'Temperatur',
                      'PPT':'Leistung', 'temp1':'Temperatur', 'edge':'Temperatur', 'CPU_Opt':'CPU-Zusatzlüfter'}
            for row in data['sensors']:
                device = row['device']; low = device.lower()
                category = next((title for prefix,title in [('k10temp','Prozessor'), ('coretemp','Prozessor'),
                    ('amdgpu','AMD-Grafik'), ('nvme','SSD'), ('spd','Arbeitsspeicher'), ('asusec','Mainboard'),
                    ('prom','USB-Controller'), ('r8169','Netzwerk'), ('mt79','WLAN')] if low.startswith(prefix)), device)
                if device not in groups:
                    group = QTreeWidgetItem(self.values, [category, '']); group.setToolTip(0, device)
                    group.setExpanded(device in expanded or (initial and (category == 'Prozessor' or 'grafik' in category.lower() or 'nvidia' in low)))
                    groups[device] = group
                child = QTreeWidgetItem(groups[device], [labels.get(row['name'],row['name']), f"{row['value']:g} {row['unit']}"])
                child.setToolTip(0, device + ' · ' + row['name'])
            self.values.resizeColumnToContents(0)
            self.values.verticalScrollBar().setValue(scroll)
            self.status.setText((' · '.join(data['activity']) or 'Kein Spiel / Aufnahmeprogramm erkannt') +
                ('\nKeine Sensoren verfügbar. lm_sensors kann über die Einrichtung ergänzt werden.' if not data['sensors'] else '\nAktualisierung alle 10 Sekunden.'))
        except (ValueError, KeyError): self.status.setText('Messwerte momentan nicht verfügbar. Erneut aktualisieren.')

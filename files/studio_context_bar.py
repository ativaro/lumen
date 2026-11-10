"""Context of the selected conversation; management lives in the native tools."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton
from lumen_i18n import tr
from studio_design import icon, surface


class StudioContextBar(QFrame):
    def __init__(self, window):
        super().__init__(window); self.window = window
        self.setObjectName('studioContextBar'); surface(self)
        box = QHBoxLayout(self); box.setContentsMargins(24, 12, 24, 12)
        self.compact = QPushButton(tr('Zurück zu Lumen')); self.compact.setIcon(icon('go-previous'))
        self.compact.clicked.connect(window.open_search); box.addWidget(self.compact)
        box.addStretch()
        self.directory = QPushButton(); self.directory.setIcon(icon('folder-open'))
        self.directory.setAccessibleName(tr('Gesprächsordner wählen')); self.directory.clicked.connect(window.choose_directory)
        box.addWidget(self.directory)
        self.project = QPushButton(tr('Lumen Projekte')); self.project.setIcon(icon('folder-development'))
        self.project.clicked.connect(lambda: window.show_page(8)); box.addWidget(self.project)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1500); self.refresh()

    def refresh(self):
        from pathlib import Path
        path = self.window.chat.backend.directory
        self.directory.setText(Path(path).name or '/'); self.directory.setToolTip(path)
        self.directory.setEnabled(not self.window.chat.backend.busy)

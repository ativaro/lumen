"""System entry to the existing maintenance and task troubleshooting flows."""
from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QScrollArea, QFrame, QStackedWidget
from lumen_i18n import tr
from troubleshooter_ui import Troubleshooter, label


class DiagnosticsPage(QWidget):
    def __init__(self, system, store=None):
        super().__init__(system)
        self.system = system
        self.assistant = QSettings('Lumen', 'Assistant')
        outer = QVBoxLayout(self); self.views = QStackedWidget(); outer.addWidget(self.views)
        overview = QWidget(); self.views.addWidget(overview)
        root = QVBoxLayout(overview); root.setContentsMargins(32, 28, 32, 24)
        heading = label(tr('Diagnose')); heading.setObjectName('heading'); root.addWidget(heading)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        self.checks = Troubleshooter(self); self.checks.layout().setAlignment(Qt.AlignTop)
        scroll.setWidget(self.checks); root.addWidget(scroll, 1)
        root.addWidget(label(tr('Wenn ein Auftrag hängen bleibt, findest du hier seinen Verlauf und die verfügbaren Aktionen.')))
        self.tasks = QPushButton(tr('Alle Aufgaben anzeigen')); self.tasks.clicked.connect(self.open_tasks)
        root.addWidget(self.tasks)
        from system_status import SystemStatus
        self.system_status = SystemStatus(self)
        report = QPushButton(tr('Systemstatus & Wächterbericht')); root.addWidget(report)
        report.clicked.connect(lambda: self.views.setCurrentIndex(2))
        from task_controller import TaskController
        self.task_controller = TaskController(self, store=store)
        task_view = QWidget(); layout = QVBoxLayout(task_view)
        back = QPushButton(tr('Zurück zur Diagnose')); back.clicked.connect(lambda: self.views.setCurrentIndex(0)); layout.addWidget(back)
        layout.addWidget(self.task_controller.tasks_page); self.views.addWidget(task_view)
        status_view = QWidget(); status_layout = QVBoxLayout(status_view)
        back = QPushButton(tr('Zurück zur Diagnose')); back.clicked.connect(lambda: self.views.setCurrentIndex(0)); status_layout.addWidget(back)
        status_layout.addWidget(self.system_status); self.views.addWidget(status_view)

    def open_system(self):
        self.system.select('system')

    def open_page(self, index):
        from settings_dialog import SettingsDialog
        dialog = SettingsDialog(self, load_system=False)
        dialog.open_page(index)
        dialog.exec(); dialog.deleteLater()

    def open_setup_wizard(self, index):
        from setup_dialog import open_setup
        open_setup(self, self.assistant, page=index)
        self.assistant.sync()

    def open_tasks(self, identity=None):
        self.task_controller.refresh_tasks()
        if isinstance(identity, str): self.task_controller.select_task(identity)
        self.views.setCurrentIndex(1)

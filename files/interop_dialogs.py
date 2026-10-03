"""Bounded worker dialog that keeps Qt jobs alive through cancellation."""
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QProgressBar,QDialogButtonBox
from tools_ui import Job
from lumen_i18n import tr


def run_job(parent,title,function):
    result={}
    class Progress(QDialog):
        def reject(self):
            job.cancelled.set();status.setText(tr('Abbruch wird abgeschlossen …'))
        def closeEvent(self,event):
            self.reject();event.ignore()
    dialog=Progress(parent);dialog.setWindowTitle(title);dialog.resize(440,140)
    layout=QVBoxLayout(dialog);status=QLabel(title);layout.addWidget(status)
    progress=QProgressBar();progress.setRange(0,0);layout.addWidget(progress)
    buttons=QDialogButtonBox(QDialogButtonBox.Cancel);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    job=Job(function,dialog);job.result.connect(lambda value:result.update(value=value))
    job.failed.connect(lambda message:result.update(error=message));job.progress.connect(status.setText)
    job.finished.connect(dialog.accept);job.start();dialog.exec_();job.wait()
    if job.cancelled.is_set():return None
    if 'error' in result:raise ValueError(result['error'])
    return result.get('value')

"""Bounded worker dialog that keeps Qt jobs alive through cancellation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog,QVBoxLayout,QProgressBar,QDialogButtonBox,QPlainTextEdit,QFrame
from tools_ui import Job
from desktop_design import PAGE_MARGIN,PAGE_SPACING
from lumen_i18n import tr


def run_job(parent,title,function):
    result={}
    class Progress(QDialog):
        def reject(self):
            job.cancelled.set();status.setPlainText(tr('Abbruch wird abgeschlossen …'))
        def closeEvent(self,event):
            self.reject();event.ignore()
    dialog=Progress(parent);dialog.setWindowTitle(title);dialog.resize(440,140)
    layout=QVBoxLayout(dialog);layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
    status=QPlainTextEdit(title,dialog);status.setReadOnly(True);status.setFrameShape(QFrame.NoFrame)
    # The shared input stylesheet otherwise restores its border and 8px padding.
    status.setStyleSheet('QPlainTextEdit { border:0; padding:0; }')
    status.document().setDocumentMargin(0);status.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    status.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);layout.addWidget(status,1)
    progress=QProgressBar();progress.setRange(0,0);layout.addWidget(progress)
    buttons=QDialogButtonBox(QDialogButtonBox.Cancel);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    buttons.button(QDialogButtonBox.Cancel).setText(tr('Abbrechen'))
    job=Job(function,dialog);job.result.connect(lambda value:result.update(value=value))
    job.failed.connect(lambda message:result.update(error=message));job.progress.connect(status.setPlainText)
    job.finished.connect(dialog.accept);job.start();dialog.exec();job.wait()
    if job.cancelled.is_set():return None
    if 'error' in result:raise ValueError(result['error'])
    return result.get('value')

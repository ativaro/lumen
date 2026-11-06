"""Explicitly save one current local conversation instruction as a server tool."""
from uuid import UUID
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QFormLayout,QLineEdit,QPlainTextEdit,QLabel
from interop_dialogs import run_job
from lumen_store import Store
from lumen_i18n import tr
from server_app_session import SessionError


def capture(window, identity):
    if window._binding.app!='code' or not window.session.usable:raise SessionError('identity')
    parsed=UUID(identity)
    if identity not in (str(parsed),parsed.hex):raise ValueError(tr('Ungültiger Auftrag.'))
    task=Store().task(identity)
    prompt=task['prompt'];title=task['title']
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000:
        raise ValueError(tr('Dieser Auftrag benötigt einen Text mit höchstens 20.000 Zeichen.'))
    session=window.session;generation=window._generation
    def current():
        if (window._disposed or window._closing or window.session is not session
                or generation!=window._generation or not session.usable or not window._pilot_current()):
            raise SessionError('identity')
    dialog=QDialog(window);dialog.setWindowTitle(tr('Lumen Code · Als Werkzeug speichern'))
    layout=QFormLayout(dialog);layout.setContentsMargins(24,24,24,24);layout.setSpacing(16)
    target=QLabel(tr('Speichern auf')+': '+window._binding.origin);target.setTextFormat(Qt.PlainText);target.setWordWrap(True)
    layout.addRow(target)
    name=QLineEdit(title[:160]);name.setMaxLength(160);name.setAccessibleName(tr('Name'))
    text=QPlainTextEdit(prompt);text.setReadOnly(True);text.setAccessibleName(tr('Auftragstext'))
    layout.addRow(tr('Name'),name);layout.addRow(tr('Auftragstext'),text)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Save).setText(tr('Als Werkzeug speichern'))
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
    dialog.resize(620,440)
    if dialog.exec()!=QDialog.Accepted:return None
    current()
    if not name.text().strip():raise ValueError(tr('Bitte einen Namen eingeben.'))
    chosen=name.text().strip();binding=window._binding
    def save(job):
        job.check();current()
        saved=session.request('/api/code-library',dict(kind='tool',title=chosen,
            description=tr('Aus einem Lumen-Gespräch übernommen')+' · '+identity,definition=dict(prompt=prompt)),max_bytes=256*1024)
        job.check();current()
        key=saved.get('id');UUID(key)
        return dict(version=2,app='code',id=key,title=saved['title'],
            locator=dict(server=binding.origin,account=binding.account))
    return run_job(window,tr('Lumen Code · Werkzeug wird gespeichert …'),save)

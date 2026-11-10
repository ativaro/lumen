"""Task cards and inspector; actions stay on the existing WorkPages controller."""
from datetime import datetime
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPalette, QPainter, QPen, QFont, QDesktopServices
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QMenu, QCheckBox, QWidgetAction, QSplitter, QListWidget, QStyledItemDelegate,
    QStyle, QScrollArea, QProgressBar, QPlainTextEdit)
from lumen_i18n import tr
from lumen_store import STATES
from studio_design import font, icon, surface
from preview import label


class TaskCards(QStyledItemDelegate):
    def sizeHint(self, option, index):
        task = index.data(Qt.UserRole+1)
        return QSize(280, 98 if task and task['status'] == 'running' else 84 if task else 44)

    def paint(self, painter, option, index):
        painter.save(); painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(0, 0, 0, -8); task = index.data(Qt.UserRole+1)
        colors = option.palette
        if not task:
            painter.setFont(font(11)); painter.setPen(colors.color(QPalette.Text))
            painter.setBrush(colors.color(QPalette.Highlight)); painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect.left(), rect.center().y()-2, 5, 5)
            painter.setPen(colors.color(QPalette.Text)); painter.drawText(rect.adjusted(13, 0, -24, 0), Qt.AlignVCenter, index.data())
            painter.setPen(colors.color(QPalette.PlaceholderText)); painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, str(index.data(Qt.UserRole+2) or ''))
        else:
            selected = bool(option.state & QStyle.State_Selected)
            painter.setPen(QPen(colors.color(QPalette.Highlight if selected else QPalette.Mid), 1))
            painter.setBrush(colors.color(QPalette.Midlight if selected else QPalette.Button if option.state & QStyle.State_MouseOver else QPalette.Base))
            painter.drawRoundedRect(QRectF(rect).adjusted(.5, .5, -.5, -.5), 9, 9)
            if selected:
                painter.setPen(QPen(colors.color(QPalette.Highlight), 3)); painter.drawLine(rect.left()+2, rect.top()+10, rect.left()+2, rect.bottom()-10)
            state = task['status']; name = 'dialog-warning' if state in ('needs_input', 'failed', 'interrupted') else 'folder' if state == 'running' else 'text-x-generic'
            icon(name).paint(painter, rect.left()+19, rect.center().y()-9, 18, 18)
            text = rect.adjusted(56, 15, -35, -12); painter.setFont(font(13, QFont.Medium)); painter.setPen(colors.color(QPalette.Text))
            painter.drawText(text, Qt.AlignTop, painter.fontMetrics().elidedText(task['title'], Qt.ElideRight, text.width()))
            painter.setFont(font(11)); painter.setPen(colors.color(QPalette.PlaceholderText))
            subtitle = task['error'] or (tr('{0} von {1} Schritten', task['cursor'], len(task['steps'])) if task.get('steps') else
                       STATES.get(state, state)+' · '+datetime.fromtimestamp(task['updated']).strftime('%d.%m. · %H:%M'))
            painter.drawText(text.adjusted(0, 24, 0, 0), Qt.AlignTop, painter.fontMetrics().elidedText(subtitle.replace('\n', ' '), Qt.ElideRight, text.width()))
            if state == 'running':
                painter.setFont(font(10)); painter.setPen(colors.color(QPalette.Highlight))
                painter.drawText(text.adjusted(0, 46, 0, 0), Qt.AlignTop, '•  '+STATES[state])
            painter.setPen(colors.color(QPalette.PlaceholderText)); painter.setFont(font(16)); painter.drawText(rect.adjusted(0, 0, -16, 0), Qt.AlignRight | Qt.AlignVCenter, '›')
            if option.state & QStyle.State_HasFocus:
                painter.setPen(QPen(colors.color(QPalette.Highlight), 1, Qt.DotLine)); painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(rect).adjusted(4, 4, -4, -4), 6, 6)
        painter.restore()


def section(name):
    widget = QFrame(); widget.setObjectName(name)
    layout = QVBoxLayout(widget); layout.setContentsMargins(23, 24, 23, 20); layout.setSpacing(12)
    return widget, layout


def build_task_page(w):
    from assistant import Transcript, SafeDocument
    page = QWidget(); page.setObjectName('taskOverview'); surface(page); page.installEventFilter(w)
    root = QVBoxLayout(page); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
    head = QFrame(); head.setObjectName('taskOverviewHead'); head.setMinimumHeight(121)
    header = QHBoxLayout(head); header.setContentsMargins(29, 24, 29, 22); header.setSpacing(18)
    intro = QVBoxLayout(); intro.setSpacing(9)
    w.task_heading = label(tr('Alles im Blick.'), 'taskOverviewTitle'); intro.addWidget(w.task_heading)
    subtitle = label(tr('Deine Gespräche arbeiten weiter. Hier behältst du den Überblick.'), 'taskMuted'); subtitle.setWordWrap(True); intro.addWidget(subtitle)
    header.addLayout(intro, 1)
    w.task_search = QLineEdit(); w.task_search.setObjectName('taskSearch'); w.task_search.setPlaceholderText(tr('Aufträge finden'))
    w.task_search.setAccessibleName(tr('Aufträge suchen')); w.task_search.setClearButtonEnabled(True); w.task_search.setMaximumWidth(210)
    w.task_search.addAction(icon('edit-find'), QLineEdit.LeadingPosition)
    w.task_search.textChanged.connect(w.refresh_tasks); header.addWidget(w.task_search)
    more = QPushButton('···'); more.setObjectName('taskMore'); more.setAccessibleName(tr('Weitere Auftragsaktionen')); more.setFixedSize(30, 32)
    menu = QMenu(more); menu.addAction(tr('Neuer Auftrag'), w.guarded(w.new_task))
    w.show_closed = QCheckBox(tr('Geschlossene Aufgaben anzeigen')); w.show_closed.toggled.connect(w.refresh_tasks)
    action = QWidgetAction(menu); action.setDefaultWidget(w.show_closed); menu.addAction(action); more.setMenu(menu); header.addWidget(more)
    root.addWidget(head)
    w.task_split = QSplitter(); w.task_split.setChildrenCollapsible(False); w.task_split.setHandleWidth(1)
    queue = QWidget(); queue.setObjectName('taskQueue'); box = QVBoxLayout(queue); box.setContentsMargins(25, 10, 25, 18); box.setSpacing(0)
    w.tasks_empty = label(tr('Noch keine Aufträge. Beginne ein Gespräch oder lege einen Auftrag an.'), 'taskMuted'); w.tasks_empty.setWordWrap(True); box.addWidget(w.tasks_empty)
    w.tasks = QListWidget(); w.tasks.setObjectName('taskList'); w.tasks.setMinimumWidth(220)
    w.tasks.setAccessibleName(tr('Aufträge nach Zustand')); w.tasks.setItemDelegate(TaskCards(w.tasks)); w.tasks.setMouseTracking(True)
    w.tasks.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); box.addWidget(w.tasks, 1); w.task_split.addWidget(queue)
    inspector = QWidget(); inspector.setObjectName('taskInspector'); inspector.setMaximumWidth(342)
    details = QVBoxLayout(inspector); details.setContentsMargins(0, 0, 0, 0); details.setSpacing(0)
    top, title = section('taskInspectorHead'); title.addWidget(label(tr('AUSGEWÄHLTER AUFTRAG'), 'taskEyebrow'))
    w.task_title = label('', 'taskInspectorTitle'); w.task_title.setWordWrap(True); w.task_title.setTextFormat(Qt.PlainText); title.addWidget(w.task_title)
    w.task_state = label('', 'taskState'); title.addWidget(w.task_state)
    w.task_meta = label('', 'taskMuted'); w.task_meta.setTextFormat(Qt.PlainText); w.task_meta.setWordWrap(True); title.addWidget(w.task_meta); details.addWidget(top)
    content, body = section('taskInspectorContent')
    w.task_error = label('', 'taskError'); w.task_error.setWordWrap(True); w.task_error.setTextFormat(Qt.PlainText); body.addWidget(w.task_error)
    body.addWidget(label(tr('Fortschritt'), 'taskSection'))
    w.task_progress = QProgressBar(); w.task_progress.setObjectName('taskProgress'); w.task_progress.setTextVisible(False); w.task_progress.setFixedHeight(4)
    w.task_progress.setAccessibleName(tr('Abgeschlossene Schritte')); body.addWidget(w.task_progress)
    w.task_steps = label('', 'taskSteps'); w.task_steps.setWordWrap(True); w.task_steps.setTextFormat(Qt.PlainText); body.addWidget(w.task_steps)
    w.task_result_link = QPushButton(tr('Ergebnis ansehen')); w.task_result_link.setObjectName('taskResultLink')
    w.task_result_link.setIcon(icon('text-x-generic')); w.task_result_link.setCheckable(True); body.addWidget(w.task_result_link)
    w.task_result = Transcript(); w.task_result.setDocument(SafeDocument(w.task_result)); w.task_result.setObjectName('taskResult')
    w.task_result.setFont(font(13)); w.task_result.setMinimumHeight(160); w.task_result.setOpenLinks(False); w.task_result.setAccessibleName(tr('Auftragsergebnis'))
    w.task_result.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url) if url.scheme() in ('http', 'https') else None)
    body.addWidget(w.task_result); w.task_result.hide(); w.task_result_link.toggled.connect(w.task_result.setVisible)
    w.detail = QPlainTextEdit(); w.detail.setReadOnly(True); w.detail.setMinimumHeight(160); w.detail.setObjectName('taskExecution')
    w.detail.setAccessibleName(tr('Auftrag, Ergebnis und Verlauf')); body.addWidget(w.detail); w.detail.hide(); body.addStretch()
    scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidget(content); details.addWidget(scroll, 1)
    footer, controls = section('taskInspectorFooter'); controls.setContentsMargins(22, 16, 22, 16)
    w.task_conversation = QPushButton(tr('←  Zum zugehörigen Gespräch')); w.task_conversation.setObjectName('taskBackChat')
    w.task_conversation.clicked.connect(w.guarded(w.open_task_conversation))
    links = QHBoxLayout(); links.addWidget(w.task_conversation); links.addStretch(); controls.addLayout(links)
    actions = QHBoxLayout(); actions.setSpacing(8); w.task_buttons = {}
    for key, text, callback in [('run', tr('Fortsetzen'), w.run_task), ('pause', tr('Pausieren'), lambda: w.stop_task('paused')), ('cancel', tr('Abbrechen'), lambda: w.stop_task('cancelled'))]:
        control = QPushButton(text); control.setObjectName('taskCancel' if key == 'cancel' else 'taskControl')
        control.setIcon(icon('media-playback-pause' if key == 'pause' else 'process-stop' if key == 'cancel' else 'media-playback-start'))
        control.clicked.connect(w.guarded(callback)); actions.addWidget(control); w.task_buttons[key] = control
    actions.addStretch(); controls.addLayout(actions)
    w.task_outputs = QWidget(); outputs = QHBoxLayout(w.task_outputs); outputs.setContentsMargins(0, 0, 0, 0)
    w.task_save = QPushButton(tr('Speichern')); menu = QMenu(w.task_save)
    menu.addAction(tr('Als Datei speichern …'), w.guarded(w.export_task)); menu.addAction(tr('In Lumen Notes speichern'), w.guarded(w.task_to_knowledge))
    w.task_save.setMenu(menu); outputs.addWidget(w.task_save)
    w.task_reuse = QPushButton(tr('Verwenden')); menu = QMenu(w.task_reuse)
    menu.addAction(tr('Als Dateiaktion'), w.guarded(w.task_to_file_action)); menu.addAction(tr('Als Ablauf speichern'), w.guarded(w.task_to_flow))
    w.task_reuse.setMenu(menu); outputs.addWidget(w.task_reuse)
    extra = QPushButton('···'); extra.setObjectName('taskMore'); extra.setFixedWidth(30); extra.setAccessibleName(tr('Details und weitere Aktionen'))
    menu = QMenu(extra)
    w.task_details = QPushButton(tr('Details zur Ausführung'), inspector); w.task_details.setCheckable(True); w.task_details.hide()
    action = menu.addAction(tr('Details zur Ausführung')); action.setCheckable(True); action.toggled.connect(w.task_details.setChecked)
    w.task_details.toggled.connect(w.detail.setVisible)
    w.close_task = QPushButton(tr('Schließen'), inspector); w.close_task.setEnabled(False); w.close_task.hide()
    w.close_task.setToolTip(tr('Aus der Übersicht entfernen. Ergebnis und Verlauf bleiben erhalten.')); w.close_task.clicked.connect(w.guarded(w.dismiss_task))
    close = menu.addAction(tr('Aus Übersicht entfernen'), w.close_task.click); menu.aboutToShow.connect(lambda: close.setEnabled(w.close_task.isEnabled()))
    w.undo_task = QPushButton(tr('Änderung rückgängig'), inspector); w.undo_task.hide(); w.undo_task.clicked.connect(w.guarded(w.undo_change))
    undo = menu.addAction(tr('Änderung rückgängig'), w.undo_task.click); menu.aboutToShow.connect(lambda: undo.setEnabled(w.undo_task.isEnabled()))
    menu.addSeparator(); menu.addAction(tr('Als Datei speichern …'), w.guarded(w.export_task))
    extra.setMenu(menu); links.addWidget(extra); outputs.addStretch(); controls.addWidget(w.task_outputs); details.addWidget(footer)
    w.task_inspector = inspector; w.task_split.addWidget(inspector); w.task_split.setStretchFactor(0, 1); w.task_split.setStretchFactor(1, 0)
    w.task_split.setSizes([800, 342]); root.addWidget(w.task_split, 1)
    w.tasks.currentItemChanged.connect(w.show_task)
    if hasattr(w.window, 'chat'): w.window.chat.backend.busyChanged.connect(w.show_task)
    return page

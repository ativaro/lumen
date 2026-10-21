"""Actual shared modal/Job behavior and Panorama layout in a private Qt process."""
import hashlib
import json
import os
from pathlib import Path
import threading
import unittest

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt, QPoint, QRect
from PySide6.QtGui import QTextOption
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel, QWidget, QScrollArea, QProgressBar, QPlainTextEdit
from shiboken6 import isValid
from appearance import apply_design
from desktop_design import PAGE_MARGIN, PAGE_SPACING
from lumen_i18n import language, tr
import interop_dialogs


app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class ProgressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_design(app,os.environ.get('LUMEN_PROGRESS_THEME','glass'))
        cls.output = Path(os.environ['LUMEN_PROGRESS_OUTPUT']) if os.environ.get('LUMEN_PROGRESS_OUTPUT') else None
        cls.images = []
        if cls.output:
            cls.output.mkdir(parents=True,exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.output:
            (cls.output/'metrics.json').write_text(json.dumps(cls.images,indent=2)+'\n')

    def setUp(self):
        self.objects = []

    def tearDown(self):
        for obj in self.objects:
            if isValid(obj):
                obj.close()
                obj.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        app.processEvents()

    def invoke(self,*,parent=False,action='',late=False,failure=False,width=440,title='Lumen · Kurzer Status',update=None,scroll=False):
        entered = threading.Event()
        release = threading.Event()
        observed = []
        errors = []
        sentinel = {'owned':'actual job result'}
        parent_widget = QWidget() if parent else None
        if parent_widget:
            self.objects.append(parent_widget)
            parent_widget.show()
        def worker(job):
            observed.append(job)
            if update:
                job.progress.emit(update)
            entered.set()
            if not release.wait(4):
                raise TimeoutError('Owned Qt test did not release the worker')
            if not late:
                job.check()
            if failure:
                raise ValueError('Owned worker failure')
            return sentinel
        metrics = {}
        timer = QTimer()
        def inspect():
            dialog = QApplication.activeModalWidget()
            if not entered.is_set() or dialog is None:
                return
            editor = dialog.findChild(QPlainTextEdit)
            status = editor if editor else dialog.findChild(QLabel)
            text = status.toPlainText() if editor else status.text()
            if update and text!=update:
                return
            timer.stop()
            self.objects.append(dialog)
            try:
                dialog.resize(width,dialog.height())
                app.processEvents()
                buttons = dialog.findChild(QDialogButtonBox)
                cancel = buttons.button(QDialogButtonBox.Cancel)
                layout = dialog.layout()
                margin = layout.contentsMargins()
                job = observed[0]
                event = job.cancelled
                available=dialog.screen().availableGeometry()
                button_rect=QRect(cancel.mapToGlobal(QPoint(0,0)),cancel.size())
                button_local=QRect(cancel.mapTo(dialog,QPoint(0,0)),cancel.size())
                metrics.update(width=dialog.width(),height=dialog.height(),requested_width=width,
                    margin=[margin.left(),margin.top(),margin.right(),margin.bottom()],spacing=layout.spacing(),
                    caption=cancel.text(),role=buttons.standardButton(cancel).name,
                    text=text,format='PlainText' if editor else status.textFormat().name,
                    wrap=editor.wordWrapMode()==QTextOption.WrapAtWordBoundaryOrAnywhere if editor else status.wordWrap(),
                    label_height=status.height(),needed_height=status.heightForWidth(status.width()),
                    language=language(),theme=app.property('lumenDesign'),scale=dialog.devicePixelRatioF(),
                    running_before=job.isRunning(),cancel_before=event.is_set(),parent=parent)
                metrics.update(available=[available.x(),available.y(),available.width(),available.height()],
                    frame_inside_available=available.contains(dialog.frameGeometry()),
                    cancel_global=[button_rect.x(),button_rect.y(),button_rect.width(),button_rect.height()],
                    cancel_dialog=[button_local.x(),button_local.y(),button_local.width(),button_local.height()],
                    cancel_inside_available=available.contains(button_rect))
                area=editor if editor else dialog.findChild(QScrollArea)
                if area:
                    viewport=area.viewport();bar=area.verticalScrollBar()
                    area.setFocus()
                    for _ in range(bar.maximum()//max(1,bar.pageStep())+2):
                        QTest.keyClick(area,Qt.Key_PageDown)
                    app.processEvents()
                    if editor:
                        last=editor.document().lastBlock();layout=last.layout()
                        line=layout.lineAt(layout.lineCount()-1)
                        rect=line.naturalTextRect().translated(editor.blockBoundingGeometry(last).translated(editor.contentOffset()).topLeft())
                        bottom_visible=viewport.rect().contains(rect.toAlignedRect())
                    else:
                        bottom=status.mapTo(viewport,QPoint(0,status.height()-1))
                        bottom_visible=0<=bottom.y()<viewport.height()
                    metrics['content_reachable']=bar.value()==bar.maximum() and bottom_visible
                    for _ in range(bar.maximum()//max(1,bar.pageStep())+2):
                        QTest.keyClick(area,Qt.Key_PageUp)
                    app.processEvents()
                else:
                    metrics['content_reachable']=status.height()>=status.heightForWidth(status.width())
                if scroll:
                    metrics['scroll_present']=area is not None
                    if area:
                        viewport=area.viewport();bar=area.verticalScrollBar()
                        origin=viewport.mapTo(dialog,QPoint(0,0))
                        metrics.update(viewport_origin=[origin.x(),origin.y()],
                            status_width=editor.viewport().width() if editor else status.width(),viewport_width=viewport.width(),
                            horizontal_off=area.horizontalScrollBarPolicy()==Qt.ScrollBarAlwaysOff,
                            controls_outside_scroll=not area.isAncestorOf(cancel) and not area.isAncestorOf(dialog.findChild(QProgressBar)),
                            scroll_maximum=bar.maximum())
                        area.setFocus()
                        for _ in range(bar.maximum()//max(1,bar.pageStep())+2):
                            QTest.keyClick(area,Qt.Key_PageDown)
                        app.processEvents()
                        metrics['keyboard_reaches_end']=bar.value()==bar.maximum() and bar.maximum()>0
                        metrics['status_bottom_visible']=bottom_visible
                        for _ in range(bar.maximum()//max(1,bar.pageStep())+2):
                            QTest.keyClick(area,Qt.Key_PageUp)
                        app.processEvents()
                        QTest.wheelEvent(dialog.windowHandle(),viewport.mapTo(dialog,QPoint(20,20)),QPoint(0,-120))
                        app.processEvents()
                        metrics['wheel_moves']=bar.value()>0
                if self.output:
                    name=f'{self._testMethodName}-{len(self.images)}.png'
                    self.assertTrue(dialog.grab().save(str(self.output/name)))
                    metrics['image']=name
                    metrics['image_sha256']=hashlib.sha256((self.output/name).read_bytes()).hexdigest()
                if action=='button':
                    cancel.click()
                elif action=='escape':
                    QTest.keyClick(dialog,Qt.Key_Escape)
                elif action=='close':
                    dialog.close()
                metrics.update(cancel_after=event.is_set(),same_event=job.cancelled is event,
                    visible_before_release=dialog.isVisible(),running_before_release=job.isRunning(),
                    final_status=status.toPlainText() if editor else status.text())
            except Exception as error:
                errors.append(type(error).__name__)
            finally:
                release.set()
        timer.timeout.connect(inspect)
        timer.start(3)
        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(release.set)
        watchdog.start(3500)
        try:
            if failure:
                with self.assertRaisesRegex(ValueError,'Owned worker failure'):
                    result=interop_dialogs.run_job(parent_widget,title,worker)
                result=None
            else:
                result=interop_dialogs.run_job(parent_widget,title,worker)
        finally:
            timer.stop();watchdog.stop();release.set()
        self.assertEqual(errors,[])
        self.assertTrue(metrics)
        self.assertEqual(len(observed),1)
        self.assertFalse(observed[0].isRunning())
        if parent_widget:
            self.assertTrue(parent_widget.isVisible())
        self.images.append(metrics)
        return result,sentinel,metrics

    def test_panorama_geometry_plain_text_and_caption(self):
        for parent in (False,True):
            for width in (440,320):
                for title in ('Lumen · Kurzer Status','Lumen · <b>Ausführlicher Status</b> · '+('Dieser Vorgang wird sorgfältig abgeschlossen. '*4)):
                    with self.subTest(parent=parent,width=width,long=len(title)>40):
                        result,sentinel,m=self.invoke(parent=parent,width=width,title=title)
                        self.assertIs(result,sentinel)
                        self.assertEqual(m['margin'],[PAGE_MARGIN]*4)
                        self.assertEqual(m['spacing'],PAGE_SPACING)
                        self.assertEqual(m['caption'],'Abbrechen' if language()=='de' else 'Cancel')
                        self.assertEqual(m['role'],'Cancel')
                        self.assertEqual(m['format'],'PlainText')
                        self.assertTrue(m['wrap'])
                        self.assertLessEqual(m['width'],width)
                        self.assertTrue(m['content_reachable'])

    def test_success_preserves_real_job_result_for_both_parents(self):
        for parent in (False,True):
            with self.subTest(parent=parent):
                result,sentinel,m=self.invoke(parent=parent)
                self.assertIs(result,sentinel)
                self.assertTrue(m['same_event'])
                self.assertFalse(m['cancel_after'])

    def test_worker_error_propagates_and_parent_survives(self):
        self.invoke(parent=True,failure=True)

    def cancel(self,action,*,late=False,parent=True):
        result,sentinel,m=self.invoke(action=action,late=late,parent=parent)
        self.assertIsNone(result)
        self.assertTrue(m['running_before'])
        self.assertFalse(m['cancel_before'])
        self.assertTrue(m['cancel_after'])
        self.assertTrue(m['same_event'])
        self.assertTrue(m['visible_before_release'])
        self.assertTrue(m['running_before_release'])
        self.assertEqual(m['final_status'],tr('Abbruch wird abgeschlossen …'))

    def test_cancel_button_waits_for_worker(self): self.cancel('button')
    def test_escape_waits_for_worker(self): self.cancel('escape',parent=False)
    def test_close_waits_for_worker(self): self.cancel('close')
    def test_late_success_after_cancel_returns_none(self): self.cancel('button',late=True,parent=False)

    def test_long_progress_update_remains_visible(self):
        message='Lumen · '+('Lange Fortschrittsmeldung mit einer verständlichen Erklärung. '*4)
        result,sentinel,m=self.invoke(width=320,parent=True,update=message)
        self.assertIs(result,sentinel)
        self.assertEqual(m['text'],message)
        self.assertTrue(m['wrap'])
        self.assertTrue(m['content_reachable'])

    def test_very_long_status_scroll_keeps_cancel_on_available_screen(self):
        for message in ('Lumen · '+('Sehr lange Statusmeldung zur tatsächlichen Bildschirmgrenze. '*40),
                        'Lumen · '+('UnunterbrochenerDateiname'*100)):
            with self.subTest(unbroken=' ' not in message[8:]):
                result,_,m=self.invoke(width=320,parent=True,update=message,scroll=True,action='button')
                self.assertIsNone(result)
                self.assertTrue(m['frame_inside_available'])
                self.assertTrue(m['cancel_inside_available'])
                self.assertTrue(m['scroll_present'])
                self.assertEqual(m['viewport_origin'],[PAGE_MARGIN,PAGE_MARGIN])
                self.assertLessEqual(m['status_width'],m['viewport_width'])
                self.assertTrue(m['horizontal_off'])
                self.assertGreater(m['scroll_maximum'],0)
                self.assertTrue(m['controls_outside_scroll'])
                self.assertTrue(m['keyboard_reaches_end'])
                self.assertTrue(m['status_bottom_visible'])
                self.assertTrue(m['wheel_moves'])
                x,y,w,h=m['cancel_dialog']
                self.assertGreaterEqual(x,PAGE_MARGIN)
                self.assertLessEqual(x+w,m['width']-PAGE_MARGIN)
                self.assertLessEqual(y+h,m['height']-PAGE_MARGIN)


if __name__=='__main__':unittest.main()

"""The real Automation views stay usable with compact windows and long content."""
import json
import tempfile
import unittest
from PySide6.QtCore import QCoreApplication,QEvent,Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication,QPushButton,QComboBox,QStyle,QStyleOptionButton
from PySide6.QtTest import QTest
from code_blocks import node,encode
from code_blocks_window import BlockWindow
from code_creation import CreationDialog
from code_library import Collection
from lumen_store import Store


class AutomationGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.collection=Collection(Store(self.tmp.name))
        self.tool=self.collection.create('tool','Dokumente prüfen und fehlende Angaben für die gemeinsame Projektbesprechung übersichtlich zusammenfassen · <Test & Prüfung>',value={'prompt':'Prüfen'})
        self.plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'Beispiel'})),node('ai','Zusammenfassen',title='Dokumente prüfen und fehlende Angaben für die nächste gemeinsame Besprechung übersichtlich zusammenfassen'),node('approval'),node('notify')]}
        self.entry=self.collection.create('automation','Belege prüfen und ablegen',value={'flow':encode(self.plan)})

    def dispose(self,w):
        if isinstance(w,BlockWindow):w.dirty=False;w.reject()
        else:w.done(0)
        w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def show(self,w,width=960,height=640):
        self.addCleanup(self.dispose,w);w.resize(width,height);w.show();QTest.qWait(30);self.app.processEvents()
        self.assertEqual((w.width(),w.height()),(width,height))
        return w

    def test_compact_editor_and_creation_do_not_inherit_hidden_formulation_minima(self):
        w=self.show(BlockWindow(self.collection,self.entry['id']))
        self.assertEqual(w.editor.scroll.horizontalScrollBar().maximum(),0)
        d=self.show(CreationDialog(kind='automation',tools=[self.tool]))
        self.assertEqual(d.flow_editor.scroll.horizontalScrollBar().maximum(),0)
        for tab in (1,2):
            d.flow_editor.tabs.setCurrentIndex(tab);self.app.processEvents()
            self.assertEqual(d.size().height(),640)

    def test_long_actions_wrap_and_keep_room_before_the_scrollbar(self):
        w=self.show(BlockWindow(self.collection,self.entry['id']),1280,800)
        self.assertGreaterEqual(w.editor.columns.contentsMargins().right(),8)
        for control,caption,detail in w.editor.summaries.values():
            self.assertGreaterEqual(control.height(),control.layout().totalHeightForWidth(control.width()))
            self.assertTrue(control.rect().contains(caption.geometry()))
            if detail.text():self.assertTrue(control.rect().contains(detail.geometry()))
        picker=next(x for x in w.editor.findChildren(QComboBox) if x.accessibleName()=='Aktion hinzufügen')
        tooltip=QTextDocument();tooltip.setHtml(picker.itemData(picker.count()-1,Qt.ToolTipRole))
        self.assertEqual(tooltip.toPlainText(),'Werkzeug: '+self.tool['title'])

    def test_dirty_and_result_footer_actions_keep_complete_labels(self):
        w=self.show(BlockWindow(self.collection,self.entry['id']))
        w.changed();w.views.setCurrentIndex(1)
        # A waiting checkpoint and an error use the same action bar with different controls.
        w.approve_button.show();w.cancel_button.show();self.app.processEvents()
        for b in (w.save_button,w.test_button,w.activation_button,w.live_button,w.approve_button,w.cancel_button):
            option=QStyleOptionButton();b.initStyleOption(option)
            content=b.style().subElementRect(QStyle.SE_PushButtonContents,option,b)
            self.assertGreaterEqual(content.width(),b.fontMetrics().horizontalAdvance(b.text()))
            self.assertTrue(w.rect().contains(b.mapTo(w,b.rect().topLeft())))
            self.assertTrue(w.rect().contains(b.mapTo(w,b.rect().bottomRight())))

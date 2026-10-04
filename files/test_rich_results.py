import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rich_result import present, from_messages


def sample():
    return dict(title='Bilder vorbereiten', submit_label='Auswahl senden', blocks=[
        dict(id='table',type='table',label='Dateien',columns=['Datei','MB'],rows=[['large',10],['small',2],['=FORMULA',3]]),
        dict(id='quality',type='slider',label='Qualität',min=0,max=100,step=5,value=85,unit='%'),
        dict(id='format',type='select',label='Format',options=['WebP','JPEG'],value='WebP'),
        dict(id='keep',type='toggle',label='Originale behalten',value=True),
        dict(id='chart',type='chart',label='Größe',unit='MB',items=[dict(label='Vorher',value=20),dict(label='Nachher',value=3)]),
        dict(id='progress',type='progress',label='Analysiert',value=100)])


def message(payload):
    return [dict(info=dict(role='assistant'),parts=[dict(type='tool',tool='cachyos_lumen_present_view',state=dict(status='completed',output=json.dumps(payload)))])]


class RichResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ,LUMEN_DATA=self.tmp+'/state'))
        from assistant_backend import OpenCodeBackend
        from rich_controller import RichController
        self.backend=OpenCodeBackend(self.tmp);self.view=RichController(self.backend)
        self.addCleanup(self.backend.shutdown)

    def test_contract_rejects_scripts_bad_ranges_and_untrusted_messages(self):
        payload=present(sample());self.assertEqual(from_messages(message(payload)),payload)
        bad=sample();bad['blocks'][1]['max']=-1
        with self.assertRaises(ValueError):present(bad)
        bad=sample();bad['blocks'][0]['rows']=[['x']]
        with self.assertRaises(ValueError):present(bad)
        bad=sample();bad['blocks'][2]['value']='fake'
        with self.assertRaises(ValueError):present(bad)
        bad=sample();bad['blocks'][0]['type']='script'
        with self.assertRaises(ValueError):present(bad)
        forged=message(payload);forged[0]['info']['role']='user';self.assertIsNone(from_messages(forged))
        forged=message(payload);forged[0]['parts'][0]['state']['status']='error';self.assertIsNone(from_messages(forged))

    def test_sort_filter_selection_values_submit_once_and_recovery(self):
        self.view.update_messages(message(present(sample())))
        self.view.sort_table('table',1)
        self.assertEqual([r['cells'][1] for r in self.view.table_rows('table')],[2,3,10])
        self.view.filter_table('table','small');self.assertEqual(len(self.view.table_rows('table')),1)
        self.view.select_row('table',1)
        self.assertTrue(self.view.set_value('quality',42));self.assertEqual(self.view.values['quality'],40)
        self.assertFalse(self.view.set_value('quality',101));self.assertFalse(self.view.set_value('format','Invalid'))
        self.view.set_value('format','JPEG'); self.view.set_value('keep',False)
        old=self.view.payload;self.view.update_messages(message(old));self.assertEqual(self.view.values['format'],'JPEG')
        calls=[];self.view.submitted.connect(lambda text,data:calls.append((text,data)))
        self.backend.busy=True;self.view.submit();self.assertEqual(calls,[])
        self.backend.busy=False
        state=self.view.recovery_state();self.view.set_result(None);self.view.restore(state)
        self.assertEqual(calls,[]);self.assertEqual(self.view.values['quality'],40)
        self.view.submit();self.view.submit();self.assertEqual(len(calls),1)
        self.assertNotIn('view_id',calls[0][0]);data=calls[0][1];self.assertEqual(data['tables']['table'],[['small',2]])
        self.assertEqual(data['values']['format'],'JPEG')
        self.view.update_messages([]);self.assertFalse(self.view.active)

    def test_csv_is_user_selected_and_never_overwrites_or_executes(self):
        from PySide6.QtCore import QUrl
        self.view.set_result(present(sample()))
        self.assertIn("'=FORMULA",self.view.table_text('table',','))
        file=Path(self.tmp)/'table.csv';errors=[];self.view.failed.connect(errors.append)
        self.view.export_table('table',QUrl.fromLocalFile(str(file)).toString());before=file.read_text()
        self.view.export_table('table',QUrl.fromLocalFile(str(file)).toString());self.assertEqual(file.read_text(),before)
        self.assertTrue(errors)

    def test_shared_qml_renders_components_and_resizes_without_warnings(self):
        from PySide6.QtCore import QSettings, qInstallMessageHandler, QObject, QMetaObject, Qt, QCoreApplication, QEvent
        from PySide6.QtTest import QTest
        from rich_widget import RichWidget
        warnings=[];previous=qInstallMessageHandler(lambda kind,context,text:warnings.append(text) if any(x in text for x in ['file:','TypeError','Binding loop','ReferenceError']) else None)
        widget=RichWidget(self.view,QSettings(self.tmp+'/settings.ini',QSettings.IniFormat))
        widget.resize(600,widget.height());widget.show();self.view.set_result(present(sample()));QTest.qWait(50)
        try:
            self.assertIsNotNone(widget.rootObject(),warnings)
            self.assertEqual(round(widget.rootObject().height()),widget.height())
            def find(item,name):
                if item.objectName()==name:return item
                for child in item.childItems():
                    found=find(child,name)
                    if found is not None:return found
            slider=find(widget.rootObject(),'resultSlider_quality');self.assertIsNotNone(slider,warnings)
            slider.setProperty('value',50);QMetaObject.invokeMethod(slider,'moved');QTest.qWait(10)
            self.assertEqual(self.view.values['quality'],50)
            for width in (350,760):widget.resize(width,widget.height());QTest.qWait(20)
            self.assertEqual(warnings,[])
        finally:
            widget.close();widget.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            qInstallMessageHandler(previous)


if __name__=='__main__':unittest.main()

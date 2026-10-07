"""Execute the production Plasma action handler, including its admission checks."""
from pathlib import Path
import unittest
from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


class PanelDispatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.engine = QJSEngine()
        source = (Path(__file__).resolve().parents[1]/'plasmoid/contents/ui/main.qml').read_text()
        handler = 'function control(' + source.split('function control(',1)[1].split('\n    function launch(',1)[0]
        result = self.engine.evaluate('var systemBusy=false; var helper="/usr/bin/lumen-panel"; '
            'var systemCommand=""; var root={expanded:true}; var commands=[]; '
            'var runner={connectSource:function(command){commands.push(command);}}; '+handler)
        self.assertFalse(result.isError(),result.toString())

    def test_hardware_reaches_helper_even_during_status_refresh(self):
        for busy in ('false','true'):
            self.engine.evaluate('commands=[]; systemBusy='+busy+'; root.expanded=true; control("hardware",0);')
            self.assertEqual(self.engine.evaluate('commands.join()').toString(),'/usr/bin/lumen-panel --control hardware')
            self.assertFalse(self.engine.evaluate('root.expanded').toBool())

    def test_unknown_actions_and_invalid_values_still_rejected(self):
        self.engine.evaluate('control("hardware; false",0); control("volume",101); control("brightness",-1);')
        self.assertEqual(self.engine.evaluate('commands.length').toInt(),0)
        self.engine.evaluate('systemBusy=true; control("volume",50);')
        self.assertEqual(self.engine.evaluate('commands.length').toInt(),0)
        self.engine.evaluate('systemBusy=false; control("volume",50);')
        self.assertEqual(self.engine.evaluate('commands.join()').toString(),'/usr/bin/lumen-panel --control volume --value 50')

if __name__=='__main__':unittest.main()

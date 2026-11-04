"""Replace only Lumen's upper panels and keep a single history host."""
from pathlib import Path
import unittest
from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


class TopbarLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_replacement_is_idempotent_and_preserves_dock_and_other_panels(self):
        engine=QJSEngine()
        result=engine.evaluate('''
var all=[{id:98,location:"top",widgets:()=>[{type:"org.lumen.system"}]},
{id:121,location:"bottom",widgets:()=>[{type:"org.kde.plasma.icontasks"}]},
{id:99,location:"top",widgets:()=>[{type:"org.kde.plasma.digitalclock"}]}];
all.forEach(p=>p.remove=()=>all=all.filter(row=>row!==p));
var widgets=[],next=1;
var desktop={screen:0,widgets:()=>widgets,addWidget:type=>{var w={type:type,id:next++};widgets.push(w);return w;}};
var desktops=()=>[desktop],panels=()=>all,knownWidgetTypes=["org.lumen.notificationhost"];
'''+(Path(__file__).parents[1]/'desktop/topbar.js').read_text()+'''
var first=installLumenNotificationHost(),removed=removeLumenTopPanels();
var second=installLumenNotificationHost(),again=removeLumenTopPanels();
JSON.stringify({same:first===second,hosts:widgets.length,removed:removed,again:again,panels:all.map(p=>p.id)});
''')
        self.assertFalse(result.isError(),result.toString())
        import json
        self.assertEqual(json.loads(result.toString()),dict(same=True,hosts=1,removed=[98],again=[],panels=[121,99]))


class TopbarCodeRetirementTest(unittest.TestCase):
    def test_backup_and_restore_preserve_other_packages_and_symlink_targets(self):
        import os,tempfile,json
        from unittest.mock import patch
        from types import SimpleNamespace
        import lumen_desktop_setup as setup
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';art=root/'art';art.mkdir();backup=root/'backup';backup.mkdir()
            plugins=data/'plasma/plasmoids';plugins.mkdir(parents=True)
            legacy=plugins/'org.lumen.islands';legacy.mkdir();(legacy/'metadata.json').write_text('old code')
            other=plugins/'org.kde.example';other.mkdir();(other/'metadata.json').write_text('preserve')
            target=root/'user-material';target.mkdir();(target/'photo').write_text('preserve data')
            (plugins/'org.lumen.agent').symlink_to(target,target_is_directory=True)
            (art/'appmenu.js').write_text('old integration')
            names=['plasma-org.kde.plasma.desktop-appletsrc','plasmarc','kwinrc','Lumen/Assistant.conf']
            (backup/'missing.json').write_text(json.dumps(names))
            with patch.dict(os.environ,XDG_DATA_HOME=str(data),XDG_CONFIG_HOME=str(root/'config')),patch.object(setup,'ARTWORK',art),patch.object(setup.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
                setup.retire_topbar_code(backup)
                self.assertFalse(legacy.exists());self.assertTrue((backup/'retired-code/org.lumen.agent').is_symlink())
                setup.restore(backup)
            self.assertEqual((legacy/'metadata.json').read_text(),'old code')
            self.assertEqual((other/'metadata.json').read_text(),'preserve')
            self.assertEqual((target/'photo').read_text(),'preserve data')
            self.assertTrue((plugins/'org.lumen.agent').is_symlink())


if __name__=='__main__':unittest.main()

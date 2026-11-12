#!/usr/bin/env python3
"""Render each Qt 6 entry surface with a disposable profile and no model request."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT/'artifacts/qt6/windows')
parser.add_argument('--child', choices=('lumen','files','settings','setup','search','meetings','household','workbench','radio','inbox','reader','sound','wissen'))
parser.add_argument('--platform', default='offscreen')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
if not args.child:
    for language in ('de','en'):
        for surface in parser._option_string_actions['--child'].choices:
            with tempfile.TemporaryDirectory(prefix='lumen-qt6-render-') as tmp:
                env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=tmp+'/config', XDG_DATA_HOME=tmp+'/data',
                    XDG_STATE_HOME=tmp+'/state', XDG_CACHE_HOME=tmp+'/cache', LUMEN_DATA=tmp+'/state/lumen',
                    LUMEN_TOOLS_DATA=tmp+'/tools', QT_QPA_PLATFORM=args.platform, LUMEN_LANGUAGE=language,
                    LUMEN_CRASH_CHILD='1', QT_QUICK_BACKEND='software')
                result = subprocess.run([sys.executable, __file__, '--child', surface, '--output', str(args.output)],
                    env=env, capture_output=True, text=True, timeout=20)
                if result.returncode: raise RuntimeError(surface+' '+language+'\n'+result.stderr)
                if 'Traceback' in result.stderr or 'TypeError' in result.stderr: raise RuntimeError(result.stderr)
                print(surface+' '+language+': rendered and closed', flush=True)
    raise SystemExit()

sys.path.insert(0, str(ROOT/'files'))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QColor
from app import create_app
app = create_app()
folder = Path.home()/'Documents'; folder.mkdir()
(folder/'Project notes.txt').write_text('Synthetic notes for the native Qt 6 migration check.')
(folder/'Archive').mkdir()
img = QImage(640,480,QImage.Format_RGB32); img.fill(QColor('#69bcae')); img.save(str(folder/'Example.png'))
if args.child == 'lumen':
    spec = importlib.util.spec_from_file_location('desktop', ROOT/'agent-app/main.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    window = module.LumenWindow(str(folder))
elif args.child == 'files':
    from app import Window
    window = Window(str(folder))
elif args.child == 'settings':
    from settings_dialog import SettingsDialog
    window = SettingsDialog(load_system=False, page=3)
elif args.child == 'setup':
    from setup_dialog import SetupDialog
    window = SetupDialog()
elif args.child == 'search':
    from search_controller import SearchController
    from search_qml import create_window
    controller = SearchController(str(folder), applications=[('Calculator','calculator.desktop')])
    engine, window = create_window(app,controller)
    controller.set_query('Project')
    app.aboutToQuit.connect(controller.shutdown)
else:
    module = importlib.import_module('tools_'+args.child)
    window = getattr(module,args.child.capitalize())()
window.show()
checks=[]
def capture():
    try:
        assert not any(name.startswith('PyQt5') for name in sys.modules)
        frame = window.grabWindow() if args.child=='search' else window.grab()
        assert not frame.isNull()
        assert frame.save(str(args.output/(args.child+'-'+os.environ['LUMEN_LANGUAGE']+'.png')))
        checks.append(True)
    finally:
        window.close(); app.quit()
QTimer.singleShot(600,capture)
app.exec()
assert checks == [True]

#!/usr/bin/python3
"""Cold/warm native launch and Reader file forwarding in a disposable profile."""
import hashlib,os,subprocess,sys,tempfile,time
from pathlib import Path
repo=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(repo/'files'))
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtNetwork import QLocalSocket
from tools_data import Library
app=QCoreApplication([])
binary_dir=Path(sys.argv[1]) if len(sys.argv)>1 else repo/'bin'


def wait(predicate):
    for _ in range(150):
        if predicate():return
        time.sleep(.1)
    raise AssertionError('Native application did not become ready')


with tempfile.TemporaryDirectory(prefix='lumen-reader-sound-launch-') as tmp:
    root=Path(tmp)
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',HOME=tmp,XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),XDG_CONFIG_HOME=str(root/'config'),LUMEN_TOOLS_DATA=str(root/'tools'),LUMEN_DATA=str(root/'state/lumen'))
    first=root/'First.txt';first.write_text('The first document has a reading position.')
    second=root/'Second.txt';second.write_text('The second document arrives in the same window.')
    for tool in ('reader','sound','vault','inbox','radio','meetings','workbench','household'):
        binary=str(binary_dir/('lumen-'+tool));library=Library(tool,root/'tools')
        with tempfile.TemporaryFile() as log:
            proc=subprocess.Popen([binary,*([str(first)] if tool=='reader' else [])],env=env,stdout=log,stderr=log)
            try:
                name='lumen-tool-'+str(os.getuid())+'-'+hashlib.sha256(str(library.root.resolve()).encode()).hexdigest()[:20]
                def ready():
                    assert proc.poll() is None,tool+' failed to start'
                    socket=QLocalSocket();socket.connectToServer(name)
                    result=socket.waitForConnected(50);socket.disconnectFromServer();return result
                wait(ready)
                if tool=='reader':wait(lambda:len(library.all())==1)
                result=subprocess.run([binary,*([str(second)] if tool=='reader' else [])],env=env,stdout=log,stderr=log,timeout=10)
                assert result.returncode==0 and proc.poll() is None,tool
                if tool=='reader':
                    wait(lambda:len(library.all())==2)
                    assert {r['source'] for r in library.all()}=={first.as_uri(),second.as_uri()}
                print(tool+': cold/warm activation'+(' and file forwarding' if tool=='reader' else '')+' passed',flush=True)
            except BaseException:
                log.seek(0);print(log.read().decode(errors='replace')[-5000:],file=sys.stderr);raise
            finally:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()

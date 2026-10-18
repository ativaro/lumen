"""Native collection entry point with private single-window activation."""
import argparse
import json
import sys
from PySide6.QtCore import QCoreApplication, Qt, QLockFile, QTimer
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtGui import QIcon
from app import create_app
from code_library_window import CollectionWindow
from lumen_activation import present
from tools_app import listen_window


def main(arguments=None):
    parser=argparse.ArgumentParser(description='Lumen Code & Automation')
    parser.add_argument('--entry');parser.add_argument('--save-task')
    args=parser.parse_args(arguments)
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app=create_app()
    # Files' global history filter wraps WebEngine's transient Quick objects in
    # PySide. Code has no Files history; keep that filter out of this process.
    app.removeEventFilter(app)
    app.setApplicationName('lumen-code');app.setApplicationDisplayName('Lumen Code & Automation');app.setDesktopFileName('lumen-code');app.setWindowIcon(QIcon.fromTheme('lumen-code'))
    window=CollectionWindow()
    from interop_flush import server_name
    socket=QLocalSocket();socket.connectToServer(server_name(window.library.root))
    request={key:value for key,value in vars(args).items() if value}
    if socket.waitForConnected(500):
        socket.write((json.dumps(request)+'\n').encode());socket.waitForBytesWritten(1000);socket.disconnectFromServer();return 0
    lock=QLockFile(str(window.library.root/'window.lock'))
    if not lock.tryLock(0):
        print('Lumen: Das vorhandene Sammlungsfenster antwortet nicht.',file=sys.stderr);return 1
    def activate(value):
        if not isinstance(value,dict) or set(value)-{'entry','save_task'}:raise ValueError('Ungültige Sammlungsanfrage.')
        if value.get('save_task'):
            task=window.store.task(value['save_task'])
            entry=window.collection.create('tool',task['title'],value={'prompt':task['prompt'],'source_task':task['id']})
            window.open_entry(entry['id'])
        elif value.get('entry'):window.open_entry(value['entry'])
        present(window)
    server=listen_window(window,activate);window.activation_server=server
    QTimer.singleShot(0,lambda:window.safe(activate,request))
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())

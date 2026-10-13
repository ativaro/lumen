"""Routes from native tools to the owning conversation or diagnostics window."""
import json
from PySide6.QtCore import QProcess
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
from lumen_i18n import tr


def launch(name, arguments):
    from lumen_launch import executable
    started, _ = QProcess.startDetached(executable(name), arguments)
    if not started: raise OSError(tr('Die Lumen-Anwendung konnte nicht geöffnet werden.'))


def open_tasks(identity=None):
    launch('lumen-system', ['--task', identity] if identity else ['--page', 'tasks'])


def task_action(identity, action):
    from lumen_panel import valid_task
    identity = valid_task(identity)
    if action not in ('run', 'pause', 'cancel', 'conversation'): raise ValueError('Invalid task action')
    bus = QDBusConnection.sessionBus()
    if bus.isConnected() and bus.interface().isServiceRegistered('org.lumen.Desktop').value():
        message = QDBusMessage.createMethodCall('org.lumen.Desktop', '/Lumen', 'org.lumen.Desktop', 'TaskAction')
        message.setArguments([identity, action])
        reply = bus.call(message, QDBus.Block, 5000)
        if reply.type() == QDBusMessage.ErrorMessage: raise ValueError(tr('Lumen konnte den Auftrag nicht übernehmen.'))
        error = reply.arguments()[0]
        if error: raise ValueError(error)
    elif action in ('run', 'conversation'):
        launch('lumen-agent-app', ['--task', identity, '--task-action', action])
    else:
        raise ValueError(tr('Das ausführende Lumen-Fenster ist nicht erreichbar. Der Auftrag wurde nicht verändert.'))


def room_action(identity, action, value=''):
    """Only identifiers cross the app boundary; room data stays in the shared store."""
    from PySide6.QtCore import QCoreApplication, QElapsedTimer, QThread
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected(): raise ValueError(tr('Die lokale Lumen-Verbindung ist nicht verfügbar.'))
    if not bus.interface().isServiceRegistered('org.lumen.Desktop').value():
        launch('lumen-agent-app', ['--details'])
        timer = QElapsedTimer(); timer.start()
        while not bus.interface().isServiceRegistered('org.lumen.Desktop').value():
            if timer.elapsed() > 10000: raise ValueError(tr('Lumen startet noch. Bitte erneut versuchen.'))
            QCoreApplication.processEvents(); QThread.msleep(25)
    if action == 'project-discuss':
        probe = QDBusMessage.createMethodCall('org.lumen.Desktop', '/Lumen', 'org.lumen.Desktop', 'ProjectContextVersion')
        version = bus.call(probe, QDBus.BlockWithGui, 3000)
        if version.type() == QDBusMessage.ErrorMessage or version.arguments() != [1]:
            raise ValueError(tr('Bitte Lumen einmal regulär schließen und neu öffnen, damit der neue Projektkontext verfügbar ist. Dein Entwurf bleibt hier erhalten.'))
    message = QDBusMessage.createMethodCall('org.lumen.Desktop', '/Lumen', 'org.lumen.Desktop', 'RoomAction')
    message.setArguments([json.dumps(dict(room=identity, action=action, value=value))])
    reply = bus.call(message, QDBus.BlockWithGui, 15000)
    if reply.type() == QDBusMessage.ErrorMessage: raise ValueError(tr('Lumen konnte das Projekt nicht übernehmen.'))
    result = json.loads(reply.arguments()[0])
    if result.get('error'): raise ValueError(result['error'])
    return result


def open_page(index, task=None):
    targets = {
        1: ('lumen-system', ['--page','diagnostics']),
        3: ('lumen-files', []),
        4: ('lumen-system', ['--task',task] if task else ['--page','tasks']),
        5: ('lumen-wissen', []),
        6: ('lumen-workbench', ['--section','automations']),
        7: ('lumen-settings', ['--models']),
        8: ('lumen-workbench', ['--section','rooms']),
        10: ('lumen-wissen', ['--section','results']),
        11: ('lumen-companion', []),
        12: ('lumen-workbench', ['--section','household'])}
    if index not in targets: return False
    name, args = targets[index]; launch(name, args); return True


def task_capabilities(identity):
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected() or not bus.interface().isServiceRegistered('org.lumen.Desktop').value(): return None
    message = QDBusMessage.createMethodCall('org.lumen.Desktop', '/Lumen', 'org.lumen.Desktop', 'TaskCapabilities')
    message.setArguments([identity]); reply = bus.call(message, QDBus.Block, 500)
    if reply.type() == QDBusMessage.ErrorMessage: return None
    try:
        value = json.loads(reply.arguments()[0])
        return value if set(value)=={'run','pause','cancel'} and all(type(v) is bool for v in value.values()) else None
    except (ValueError, TypeError, IndexError): return None

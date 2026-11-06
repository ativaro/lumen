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


def open_page(index, task=None):
    targets = {
        1: ('lumen-system', ['--page','diagnostics']),
        3: ('lumen-files', []),
        4: ('lumen-system', ['--task',task] if task else ['--page','tasks']),
        5: ('lumen-wissen', []),
        6: ('lumen-workbench', ['--section','automations']),
        7: ('lumen-settings', ['--models']),
        8: ('lumen-workbench', ['--section','projects']),
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

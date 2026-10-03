"""Credentials belong to the desktop Secret Service, never Library records."""
from lumen_i18n import tr
import re
import subprocess


def secret(namespace, identity, value=None, remove=False):
    if namespace not in ('vault', 'inbox') or not re.fullmatch(r'[a-f0-9]{32}', identity):
        raise ValueError(tr('Ungültiger Schlüsselbund-Eintrag.'))
    attributes = ['application', 'lumen-' + namespace, 'identity', identity]
    args = ['secret-tool', 'clear' if remove else 'lookup', *attributes]
    if value is not None:
        if not value or any(c in value for c in '\x00\r\n') or len(value) > 8192: raise ValueError(tr('Ungültiges Passwort.'))
        args = ['secret-tool', 'store', '--label=Lumen ' + namespace, *attributes]
    try:
        result = subprocess.run(args, input=value, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise ValueError(tr('System-Schlüsselbund nicht erreichbar. libsecret und die entsperrte KWallet prüfen.')) from None
    if result.returncode or (value is None and not remove and not result.stdout.strip()):
        raise ValueError(tr('Zugangsdaten fehlen oder der System-Schlüsselbund ist gesperrt.'))
    return result.stdout.rstrip('\n') if value is None and not remove else None


def unlocked():
    """Scheduled jobs must not summon an unlock prompt."""
    try:
        import dbus
        bus = dbus.SessionBus()
        if not bus.name_has_owner('org.freedesktop.secrets'): return False
        obj = bus.get_object('org.freedesktop.secrets', '/org/freedesktop/secrets/aliases/default')
        return not bool(obj.Get('org.freedesktop.Secret.Collection', 'Locked', dbus_interface='org.freedesktop.DBus.Properties'))
    except Exception: return False

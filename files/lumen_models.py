"""Model selection is explicit; a local-only task must fail closed."""
from lumen_i18n import tr
import ipaddress
from urllib.parse import urlsplit


def anonymous_opencode(provider):
    """The pinned engine marks its anonymous OpenCode loader with this public key."""
    if not isinstance(provider, dict) or provider.get('id') != 'opencode': return False
    options = provider.get('options')
    return isinstance(options, dict) and options.get('apiKey') == 'public'


def configured_opencode_endpoint(config):
    """Only the user's effective config can prove an explicit endpoint override."""
    try:
        value = config.get('provider', {}).get('opencode', {}).get('options', {}).get('baseURL', '')
        if not isinstance(value, str) or not value or any(character.isspace() for character in value): return False
        parsed = urlsplit(value)
        return parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (AttributeError, ValueError): return False


def loopback(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password: return False
        # Literal addresses avoid DNS rebinding and ambiguous 'local' provider names.
        return ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError: return False


def select_model(policy, providers, selected='', background=False):
    privacy = policy.get('privacy', 'configured')
    model = policy.get('local_model', '') if privacy == 'local' else selected or policy.get('model', '')
    if background and privacy != 'local': model = policy.get('background_model', '') or model
    if privacy not in ('configured', 'local'): raise ValueError(tr('Unbekannte Modellrichtlinie.'))
    if privacy == 'local':
        if '/' not in model: raise ValueError(tr('Für „Nur lokal“ zuerst ein lokales Modell auswählen.'))
        provider_id, model_id = model.split('/', 1)
        provider = next((p for p in providers if p.get('id') == provider_id), {})
        options = provider.get('options', {})
        if not loopback(options.get('baseURL', '')) or model_id not in provider.get('models', {}):
            raise ValueError(tr('Das ausgewählte Modell ist nicht als lokaler Dienst mit Loopback-Adresse bestätigt.'))
    return model

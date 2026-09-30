"""Model selection is explicit; a local-only task must fail closed."""
import ipaddress
from urllib.parse import urlsplit


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
    if privacy not in ('configured', 'local'): raise ValueError('Unbekannte Modellrichtlinie.')
    if privacy == 'local':
        if '/' not in model: raise ValueError('Für „Nur lokal“ zuerst ein lokales Modell auswählen.')
        provider_id, model_id = model.split('/', 1)
        provider = next((p for p in providers if p.get('id') == provider_id), {})
        options = provider.get('options', {})
        if not loopback(options.get('baseURL', '')) or model_id not in provider.get('models', {}):
            raise ValueError('Das ausgewählte Modell ist nicht als lokaler Dienst mit Loopback-Adresse bestätigt.')
    return model

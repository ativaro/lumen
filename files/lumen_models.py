"""Model selection is explicit; a local-only task must fail closed."""
from lumen_i18n import tr
import ipaddress
from urllib.parse import urlsplit


def free_default(inventory):
    """Use the live catalogue, never a name containing 'free' or unknown pricing."""
    if not isinstance(inventory, dict) or not isinstance(inventory.get('all'), list) or not isinstance(inventory.get('connected'), list):
        raise ValueError(tr('Die Engine liefert keine gültige Modellliste.'))
    def zero(value):
        return all(zero(v) for v in value.values()) if isinstance(value, dict) else type(value) in (int, float) and value == 0
    candidates = []
    defaults = inventory.get('default') or {}
    for provider in inventory['all']:
        if not isinstance(provider, dict) or not isinstance(provider.get('id'), str) or provider['id'] not in inventory['connected']: continue
        models = provider.get('models')
        if not isinstance(models, dict): continue
        for identifier, model in models.items():
            if not isinstance(model, dict): continue
            cost = model.get('cost'); capabilities = model.get('capabilities') or {}
            if not isinstance(cost, dict) or cost.get('input') != 0 or cost.get('output') != 0 or not zero(cost): continue
            if model.get('status') == 'deprecated' or not isinstance(capabilities, dict) or capabilities.get('toolcall') is not True: continue
            candidates.append((provider['id'] != 'opencode',
                not isinstance(defaults, dict) or defaults.get(provider['id']) != identifier,
                provider['id'] + '/' + identifier))
    return min(candidates)[2] if candidates else ''


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

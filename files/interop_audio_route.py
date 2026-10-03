"""Read-only preflight for explicit SDL routes and opt-in PipeWire no-fallback."""
import json
import re
from lumen_i18n import tr


def snapshot(job):
    info = json.loads(job.command(['pactl', '-f', 'json', 'info'], timeout=5))
    sinks = json.loads(job.command(['pactl', '-f', 'json', 'list', 'sinks'], timeout=5))
    manager = ''
    if 'PipeWire' in info.get('server_name', ''):
        try:
            graph = json.loads(job.command(['pw-dump'], timeout=5))
            for node in graph:
                props = node.get('info', {}).get('props', {})
                if node.get('type') == 'PipeWire:Interface:Client' and props.get('application.name') in ('WirePlumber', 'WirePlumber (main)', 'WirePlumber (policy)'):
                    manager = props.get('application.version', '')
                    break
        except (ValueError, OSError):
            pass
    return dict(sinks=sinks, server=info.get('server_name', ''), manager=manager)


def strict_reason(state, sink):
    # Restricted to the versions exercised with isolated PipeWire/WirePlumber.
    # Unknown stacks fail closed; a saved opt-in never silently loses protection.
    server = re.search(r'PipeWire (\d+)\.(\d+)\.(\d+)', state.get('server', ''))
    manager = re.match(r'^(\d+)\.(\d+)\.(\d+)', state.get('manager', ''))
    if not server or tuple(map(int, server.groups())) != (1, 6, 9) or not manager or tuple(map(int, manager.groups())) != (0, 5, 18):
        return tr('Feste Gerätesperre ist nur für geprüftes PipeWire 1.6.9 mit WirePlumber 0.5.18 verfügbar.')
    props = sink.get('properties', {}) if sink else {}
    if props.get('device.bus') not in ('usb', 'bluetooth'):
        return tr('Feste Gerätesperre benötigt einen separaten USB- oder Bluetooth-Ausgang.')
    if any('speaker' in str(port.get('name', '')).lower() or port.get('type') == 'speaker' for port in sink.get('ports', [])):
        return tr('Dieser Ausgang kann intern auf Lautsprecher umschalten; eine feste Gerätesperre ist dafür nicht verfügbar.')
    return ''


def route(state, prefs):
    chosen = next((sink for sink in state['sinks'] if sink['name'] == prefs['sink']), None)
    if chosen is None:
        raise ValueError(tr('Der gewählte Audioausgang ist nicht verbunden. Wiedergabe bleibt gestoppt.'))
    description = chosen.get('description', '')
    if not description or sum(sink.get('description') == description for sink in state['sinks']) != 1:
        raise ValueError(tr('Der Audioausgang hat keinen eindeutigen Gerätenamen. Bitte in Lumen Sound einen anderen Ausgang wählen.'))
    if prefs.get('strict_routing'):
        reason = strict_reason(state, chosen)
        if reason: raise ValueError(reason)
    return dict(prefs, sink_description=description)

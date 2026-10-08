"""Shareable setup diagnostics: metadata and counts only, never response contents."""
import hashlib
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path


def version_text(raw):
    value = raw.decode('utf-8', errors='replace').strip() if isinstance(raw, bytes) else str(raw).strip()
    return value if re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,6}(?:[-+][A-Za-z0-9.-]{1,40})?', value) else 'unavailable'


def startup_summary(outcome, raw, elapsed_ms, exit_code=None, process_error=None):
    """Classify known startup failures without retaining paths, config or log excerpts."""
    text = raw.decode('utf-8', errors='replace').lower()
    hint = 'unknown'
    for name, markers in (
        ('invalid_config', ('configuration is invalid', 'is not valid json(c)', 'configinvaliderror', 'configjsonerror')),
        ('permission_denied', ('eacces', 'eperm', 'permission denied')),
        ('disk_full', ('enospc', 'no space left on device')),
        ('database_schema', ('database is not empty and has no session table',)),
        ('database', ('sqlite_', 'sqliteerror', 'database is locked', 'unable to open database')),
        ('address_in_use', ('eaddrinuse', 'address already in use')),
        ('tls', ('certificate_verify_failed', 'unable_to_verify_leaf_signature', 'unable to verify the first certificate')),
    ):
        if any(marker in text for marker in markers):
            hint = name
            break
    result = dict(outcome=outcome, hint=hint, elapsed_ms=elapsed_ms, captured_bytes=len(raw))
    if exit_code is not None: result['exit_code'] = int(exit_code)
    if process_error is not None: result['process_error'] = int(process_error)
    return result


def response_summary(path, code, network_error, content_type, data, size):
    if path.startswith('/auth/'): path = '/auth/<provider>'
    if path not in ('/config', '/provider', '/provider/auth', '/auth/<provider>'): return None
    value = dict(endpoint=path, http=int(code), network_error=int(network_error), bytes=size,
                 format='json' if 'json' in content_type.lower() else 'html' if 'html' in content_type.lower() else 'other',
                 json_type=type(data).__name__)
    if path == '/provider' and isinstance(data, dict):
        value['fields'] = {key:type(data.get(key)).__name__ for key in ('all','connected','default')}
        providers = data.get('all')
        if isinstance(providers,list):
            value['providers'] = len(providers)
            value['invalid_providers'] = sum(not isinstance(p,dict) for p in providers)
            connected = data.get('connected')
            value['connected'] = len(connected) if isinstance(connected,list) else None
            value['models_by_provider'] = [dict(provider='opencode-zen' if p.get('id')=='opencode' else 'other',
                connected=isinstance(connected,list) and p.get('id') in connected,
                models=len(p['models']) if isinstance(p.get('models'),dict) else None,
                invalid_models=sum(not isinstance(m,dict) for m in p['models'].values()) if isinstance(p.get('models'),dict) else None)
                for p in providers[:300] if isinstance(p,dict) and
                (p.get('id')=='opencode' or isinstance(connected,list) and p.get('id') in connected)]
    return value


def build_report(dialog, engine_version):
    from PySide6.QtCore import qVersion
    from assistant_backend import ENGINE_VERSION, managed_opencode, opencode_binary
    root = Path(__file__).resolve().parent.parent
    try: revision = json.loads((root/'install.json').read_text()).get('revision','')
    except (OSError,ValueError,AttributeError): revision = ''
    if not isinstance(revision,str) or not re.fullmatch('[a-f0-9]{40}',revision): revision = 'source-or-unknown'
    digest = hashlib.sha256()
    try:
        for name in ('setup_dialog.py','assistant_backend.py','setup_diagnostics.py'):
            digest.update((Path(__file__).parent/name).read_bytes())
        fingerprint = digest.hexdigest()[:16]
    except OSError: fingerprint = 'unavailable'
    binary = dialog.engine.proc.program() if dialog.engine.proc else opencode_binary()
    try: distribution = platform.freedesktop_os_release()
    except OSError: distribution = {}
    report = dict(report='Lumen setup diagnostic v2', utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        lumen_revision=revision, code_fingerprint=fingerprint,
        python=platform.python_version(), qt=qVersion(), architecture=platform.machine(),
        os=distribution.get('ID','unknown'), os_version=distribution.get('VERSION_ID','rolling-or-unknown'),
        engine_version=version_text(engine_version), compatible_engine=ENGINE_VERSION,
        engine_source='managed' if Path(binary)==managed_opencode() else 'external',
        engine_database=getattr(dialog.engine, 'database_source', 'unknown'),
        engine_reachable=bool(dialog.engine.url), stage=dialog.diagnostic_stage,
        startup=getattr(dialog.engine, 'startup_diagnostic', {'outcome': 'unavailable'}),
        outcome=dialog.diagnostic_outcome, providers=len(dialog.providers),
        selectable_models=sum(bool(dialog.models.itemData(i)) for i in range(dialog.models.count())),
        model_selected=bool(dialog.models.currentData()), saved_model_configured=bool(dialog.settings.value('model','')),
        requests=dialog.diagnostic_events)
    return json.dumps(report,ensure_ascii=False,indent=2)

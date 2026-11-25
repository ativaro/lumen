"""Shareable setup diagnostics: metadata and counts only, never response contents. The engine's startup
and answer summaries come from lumen-service (native/service/src/engine.rs and turn.rs)."""
import hashlib
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path


def version_text(raw):
    value = raw.decode('utf-8', errors='replace').strip() if isinstance(raw, bytes) else str(raw).strip()
    return value if re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,6}(?:[-+][A-Za-z0-9.-]{1,40})?', value) else 'unavailable'


def build_report(dialog, engine_version):
    from PySide6.QtCore import qVersion
    from lumen_i18n import worker_environment
    from lumen_service import engine_info
    info = engine_info(worker_environment())
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
    binary = dialog.engine.program()
    try: distribution = platform.freedesktop_os_release()
    except OSError: distribution = {}
    report = dict(report='Lumen setup diagnostic v2', utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        lumen_revision=revision, code_fingerprint=fingerprint,
        python=platform.python_version(), qt=qVersion(), architecture=platform.machine(),
        os=distribution.get('ID','unknown'), os_version=distribution.get('VERSION_ID','rolling-or-unknown'),
        engine_version=version_text(engine_version), compatible_engine=info['version'],
        engine_source='managed' if Path(binary)==Path(info['managed']) else 'external',
        engine_database=getattr(dialog.engine, 'database_source', 'unknown'),
        engine_reachable=dialog.engine.reachable, stage=dialog.diagnostic_stage,
        startup=getattr(dialog.engine, 'startup_diagnostic', {'outcome': 'unavailable'}),
        outcome=dialog.diagnostic_outcome, providers=len(dialog.providers),
        selectable_models=sum(bool(dialog.models.itemData(i)) for i in range(dialog.models.count())),
        model_selected=bool(dialog.models.currentData()), saved_model_configured=bool(dialog.settings.value('model','')),
        requests=dialog.diagnostic_events)
    return json.dumps(report,ensure_ascii=False,indent=2)

"""State location shared with the crash supervisor, without loading Qt or storage."""
import os
from pathlib import Path


def require_test_profile():
    if os.environ.get('QT_QPA_PLATFORM', '').split(':')[0] in ('offscreen', 'minimal'):
        if not all(os.environ.get(key, '').strip() for key in ('LUMEN_DATA', 'LUMEN_TOOLS_DATA')):
            raise ValueError('Headless test starts require explicit LUMEN_DATA and LUMEN_TOOLS_DATA paths.')


def state_path():
    return Path(os.environ.get('LUMEN_DATA', str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'lumen')))

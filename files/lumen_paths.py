"""State location shared with the crash supervisor, without loading Qt or storage."""
import os
from pathlib import Path


def state_path():
    return Path(os.environ.get('LUMEN_DATA', str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'lumen')))

"""Bring the backup window forward after an explicit Vault navigation click."""
from pathlib import Path


def activate_backup(pid):
    """Use KWin's existing window API, scoped to the locked backup process."""
    from lumen_activation import activate_process
    return activate_process(pid, 'lumen-system') or activate_process(pid, 'lumen-vault')


def activate_existing_backup(root):
    from PySide6.QtCore import QLockFile
    pid, _, _ = QLockFile(str(Path(root) / 'window.lock')).getLockInfo()
    return activate_backup(pid)

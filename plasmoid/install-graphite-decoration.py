#!/usr/bin/env python3
"""Install the shared Graphite Echo decoration; activation stays an explicit action."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'files'))
from lumen_desktop_theme import prepare_decoration

print(prepare_decoration('graphite'))
print('Aktivieren: lumen-desktop-setup --refresh-decoration (bei aktivem Lumen-Theme).')

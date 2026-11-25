"""Explicit, conversation-scoped presentation results from the Lumen MCP tool."""
import json
from pathlib import Path
import uuid

KIND = 'lumen.presentation.v1'
TOOL = 'lumen_present_files'
# The instruction that offers the preview is the service's (native/service/src/turn.rs).


def validate(value):
    if not isinstance(value, dict) or value.get('kind') != KIND:
        raise ValueError('Invalid presentation result.')
    paths, title, identity = value.get('paths'), value.get('title'), value.get('id')
    if (not isinstance(paths, list) or len(paths) > 100
            or not isinstance(title, str) or len(title) > 160
            or not isinstance(identity, str) or not 1 <= len(identity) <= 128):
        raise ValueError('Invalid presentation fields.')
    for path in paths:
        if not isinstance(path, str) or not path.startswith('/') or len(path) > 4096 or '\0' in path:
            raise ValueError('Presentation paths must be absolute local or mounted file paths.')
    return dict(kind=KIND, id=identity, title=title, paths=list(dict.fromkeys(paths)))


def present(paths, title=''):
    result = validate(dict(kind=KIND, id=uuid.uuid4().hex, title=title, paths=paths))
    # Runs in the existing bounded MCP worker, never on the GUI thread.
    for path in result['paths']:
        if not Path(path).is_file():
            raise ValueError('File not available for presentation: ' + path)
    return result


def from_messages(messages):
    """Use only successful explicit tool results, never prose or user attachments."""
    for message in reversed(messages):
        if message.get('info', {}).get('role') != 'assistant': continue
        for part in reversed(message.get('parts', [])):
            tool = part.get('tool', '')
            if part.get('type') != 'tool' or not isinstance(tool, str): continue
            if tool != TOOL and not tool.endswith('_' + TOOL): continue
            state = part.get('state', {})
            if state.get('status') != 'completed': continue
            output = state.get('output')
            if not isinstance(output, str) or len(output) > 512000: continue
            try: return validate(json.loads(output))
            except (ValueError, TypeError): continue
    return None

"""Portable tag identities and narrowly scoped, source-preserving tag edits. The service derives and edits
them (`notes.tags`, `notes.mask`, `notes.identity`, `notes.add_tag`, `notes.rename_tag`;
native/service/src/notebook/text.rs and edit.rs), the one front-matter reader."""
from functools import lru_cache
import re

from wissen_data import _ask

# The front matter's delimiters, for the views that split a text around it.
FRONT = re.compile(r'\A---\r?\n([\s\S]*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)')


@lru_cache(maxsize=1024)
def identity(value):
    """The tag `value` stands for (NFC, case folded); ValueError for no tag."""
    return _ask('identity', value=value)['tag']


def body_mask(text):
    """`text` with front matter, code and link destinations as spaces: offsets stay."""
    return _ask('mask', text=text)['mask']


def tags(text):
    return _ask('tags', text=text)['tags']


def matches_tags(values, selected):
    """Whether a note with the tags `values` (as the service derived them) has every selected tag or a
    subtag of it."""
    return all(any(tag == identity(wanted) or tag.startswith(identity(wanted) + '/') for tag in values) for wanted in selected)


def add_tag(text, tag):
    return _ask('add_tag', text=text, tag=tag)['text']


def rename_tag(text, old, new, *, descendants=True):
    return _ask('rename_tag', text=text, old=old, new=new, descendants=descendants)['text']

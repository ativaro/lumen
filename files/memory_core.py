"""Lumen memory contract. Pure Python; callers supply freshly authorized records.

Canonical source: lumen-server/server/memory_core.py. Desktop ships this exact file.
No storage, UI, network or model dependencies. Index results never grant access.
"""
from collections import Counter
from dataclasses import dataclass
import math
import re
import unicodedata

VERSION = 1
MAX_TEXT = 20000


def normalize(value):
    return unicodedata.normalize('NFKC', str(value)).casefold()


def terms(value):
    words = re.findall(r'[^\W_]+(?:[-./][^\W_]+)*', normalize(value), re.UNICODE)
    result = []
    for word in words:
        result.append(word)
        # Unsegmented scripts need character overlap; no language or intent word list.
        if len(word) > 1 and all(unicodedata.east_asian_width(c) in 'WF' for c in word):
            result.extend(word[i:i + 2] for i in range(len(word) - 1))
    return result


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    text: str
    revision: str
    boundary: str
    kind: str = 'fact'
    project: str = ''
    status: str = 'active'
    allowed: bool = False
    updated: float = 0
    correction: bool = False
    supersedes: str = ''

    def __post_init__(self):
        if not self.id or not self.revision or not self.boundary:
            raise ValueError('Memory identity, revision and boundary are required')
        if len(self.text) > MAX_TEXT or len(self.title) > 500:
            raise ValueError('Memory exceeds text budget')
        if self.kind not in ('fact', 'preference', 'decision', 'solution', 'note'):
            raise ValueError('Unknown memory kind')
        if self.status not in ('active', 'proposed', 'replaced', 'forgotten', 'conflict'):
            raise ValueError('Unknown memory state')


def eligible(entries, boundary, project=''):
    permitted = [e for e in entries if e.boundary == boundary and e.allowed
                 and (not e.project or e.project == project)]
    replaced = {e.supersedes for e in permitted if e.status == 'active' and e.supersedes}
    return [e for e in permitted if e.status == 'active' and e.id not in replaced]


def search(entries, query, *, boundary, project='', limit=6, browse=False,
           preferences=0, semantic=None):
    """Rank only current visible records; empty queries do not dump memory.

    preferences explicitly reserves a bounded number of general style entries for
    prompt context. Tool search leaves it at zero. Ties are deterministic.
    """
    if not 0 <= limit <= 5000 or not 0 <= preferences <= 3:
        raise ValueError('Invalid retrieval budget')
    current = eligible(entries, boundary, project)
    by_id = {}
    for entry in current:
        if entry.id in by_id:
            raise ValueError('Duplicate memory identity in one boundary')
        by_id[entry.id] = entry
    if browse and not query.strip():
        return sorted(current, key=lambda e: (-e.updated, e.id))[:limit]
    needle = set(terms(query[:6000]))
    documents = [(e, Counter(terms(e.title + ' ' + e.text))) for e in current]
    frequencies = Counter(t for _, counts in documents for t in needle if t in counts)
    scores = []
    for entry, counts in documents:
        matches = needle & counts.keys()
        if not matches:
            continue
        title_terms = set(terms(entry.title))
        score = sum(math.log(1 + (len(current) + 1) / (frequencies[t] + 1))
                    * (3 if t in title_terms else 1) * (1 + math.log(counts[t]))
                    for t in matches)
        score *= len(matches) / max(1, len(needle))
        if normalize(query.strip()) in normalize(entry.title) and query.strip():
            score += 4
        scores.append((score, entry))
    scores.sort(key=lambda pair: (-pair[0], not pair[1].correction, -pair[1].updated, pair[1].id))
    if semantic is not None and needle:
        # Reciprocal rank fusion preserves exact retrieval and combines unlike scales.
        # Index scores are keyed by revision; stale vectors never become current facts.
        combined = {entry.id: 1 / (60 + rank) for rank, (_, entry) in enumerate(scores, 1)}
        vectors = []
        for entry in current:
            value = semantic.get((entry.id, entry.revision), -1)
            if isinstance(value, (int, float)) and math.isfinite(value) and .35 <= value <= 1.00001:
                vectors.append((value, entry))
        vectors.sort(key=lambda pair: (-pair[0], pair[1].id))
        for rank, (_, entry) in enumerate(vectors, 1):
            combined[entry.id] = combined.get(entry.id, 0) + 1 / (60 + rank)
        literal = normalize(query.strip())
        scores = [(score, by_id[identity]) for identity, score in combined.items()]
        scores.sort(key=lambda pair: (
            literal not in normalize(pair[1].title + '\n' + pair[1].text),
            -pair[0], not pair[1].correction, -pair[1].updated, pair[1].id))
    pinned = sorted((e for e in current if e.kind == 'preference' and not e.project),
                    key=lambda e: (not e.correction, -e.updated, e.id))[:preferences]
    result = pinned + [e for _, e in scores if e not in pinned]
    seen = set()
    unique = []
    for entry in result:
        key = normalize(entry.text).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
        if len(unique) >= limit:
            break
    return unique if limit else []


def context(entries, *, budget=18000, excerpt=1600):
    """Return bounded excerpts and their exact identities/revisions together."""
    if not 0 <= budget <= 60000 or not 0 < excerpt <= MAX_TEXT:
        raise ValueError('Invalid context budget')
    selected = []
    remaining = budget
    for entry in entries:
        header = f'[{entry.id} @ {entry.revision}] {entry.title}\n'
        text = entry.text[:excerpt]
        available = remaining - len(header) - 2
        if available <= 0:
            break
        block = header + text[:available]
        selected.append({'id': entry.id, 'revision': entry.revision,
                         'title': entry.title, 'text': block})
        remaining -= len(block) + 2
    return {'context': '\n\n'.join(row['text'] for row in selected), 'sources': selected,
            'mode': 'text', 'core_version': VERSION}

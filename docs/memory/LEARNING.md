# Personal learning

## Scope and build order

| Capability | Responsibility | Depends on |
| --- | --- | --- |
| corrections | Recognize explicit lasting corrections, update supported automatic memories | Existing memory consent, evidence and version checks |
| solutions | Extract reusable steps after the user confirms the previous answer worked | corrections learning pipeline |
| profile | Inspect global user knowledge, corrections and solutions in Wissen | Existing notebook editing and memory metadata |

Implement and verify in that order. No dependency, database-schema or permission changes.

## Contract

Use the existing Python/PySide6 shared OpenCode backend, MemoryBridge and local
Markdown memory. Consent remains `memory/options`: both enabled and learn are
required for automatic extraction. Do not enable either setting as part of rollout.

- Let the LLM recognize explicit future-facing corrections in any language.
  Do not use keyword lists, regexes or per-language semantic heuristics. The extractor distinguishes durable preferences from a
  one-off formatting request. Keep evidence, source and update time. Only replace
  candidate memories whose scope, automatic status and expected hash still match.
- A solution is eligible only when the LLM identifies explicit positive user feedback about
  the preceding completed assistant answer. The LLM distinguishes negation, partial success and quotes.
  Failed/unfinished responses and another conversation do not qualify. Extract
  problem, conditions and steps from that answer, with the user's feedback as
  evidence and a matching answer ID. No language-dependent minimum word length. Never treat model self-reported success or a zero exit code as proof.
- Solutions are recallable context, not executable workflows or new permissions.
  Check the current situation before recommending reuse. Store no credentials.
- Wissen offers an overview of global preferences/facts/decisions plus direct
  filters for corrections and solutions. Existing edit, source, history and
  forget controls remain authoritative. Personal notes stay separate.
- Prioritize current correction preferences in bounded recall. New statements
  take precedence over old conversational context. Forgotten content stays blocked.
- All authored UI strings support German and English. No personal data in Git.

## Files and style

`files/lumen_memory.py`: authoritative storage/validation/recall.
`files/memory_bridge.py`: asynchronous bounded extraction; no tool permissions.
`files/memory_learning.py`: pure feedback/context validation and extraction prompt.
`files/tools_wissen.py`, `files/wissen_ui.py`: existing native notebook UI.
`files/test_memory*.py`: unittest storage, backend and native UI checks.
Follow existing small functions and explicit dictionaries; reuse note storage.

## Verification

`QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de python -m unittest test_memory test_memory_learning`
(from `files`, with isolated HOME/XDG/LUMEN_DATA when running UI tests).
Include positive and negative feedback, correction update/reuse, stale/manual
conflicts, consent revocation, forgetting, cross-project isolation, backend prompt
contracts, global profile and existing notebook controls. Render DE/EN native UI.
Build after committing: `./packaging/arch/build-package.sh`.

## Agent capabilities

`lumen_memory_list(directory, limit, offset)` exposes eligible memory summaries
without a keyword query; `lumen_memory_read(directory, path)` reads the entry the
LLM selects. This supports semantic and cross-language recall without adding
language-specific search rewrites or another mandatory model call. Both are
read-only and recheck the same consent, scope and forgetting rules as native recall.

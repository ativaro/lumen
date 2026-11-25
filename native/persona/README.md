# Lumen persona

`lumen-persona` is Lumen's one implementation of the persona: how Lumen talks in a conversation.
Style grants no data, memory or tool permissions. The server uses it for its account persona and
every model run; the desktop's service `lumen-service` (`native/service`, `src/persona.rs`) uses it
for the local persona, the account persona it reads over the server bridge, the settings view and
every turn. The
server keeps a pinned, hash-checked copy in `rust/shared/persona` (`scripts/update_shared_crates.py`).

Storage (QSettings, `lumen.sqlite3`, PostgreSQL), connections, the choice between the local and the
account persona and translation stay with each side.

## Contents

- `catalog()`: the catalogue compiled in from `src/catalog.json`: `default`, the six `presets`
  (`id`, `title`, `description`, `traits`, `example`), the seven `fields` with their `options` and
  the `kate_style` text. Titles, descriptions and examples are the German source texts; the desktop
  translates them with its `tr()` keys in `files/translations/en/persona.json`.
- `profile(raw)`: the profile a stored value stands for. Unknown keys and values are ignored, the
  preset's traits and the default fill the rest; names lose unprintable characters (Python's
  `str.isprintable()` at Unicode 16.0.0, `src/printable.rs`) and repeated spaces and keep at most 60
  characters; an empty persona name is `Lumen`. Never an error.
- `checked(raw)`: the same for a profile a client wants stored; anything `profile` would drop is
  refused (`Invalid`), and so is a name longer than 60 characters.
- `chosen(raw, choice)`: the profile with the preset chosen for one conversation or task: the
  preset's traits replace the profile's, names, presentation and address stay.
- `instruction(value)`: the conversation style appended to a model run's system text; names are
  quoted JSON data, never instructions.
- `preview(value, tr)`: the desktop's illustrative preview (no model request); `tr` translates each
  German sentence (`PREVIEW_MORE` names the two that are not preset examples).
- `account(answer)`: the account persona of a `/bridge/persona` answer as the desktop accepts it.

## Checks

```bash
python3 ../document-core/check-licenses.py .
cargo fmt --check
cargo clippy --locked --offline --release --all-targets -- -D warnings
cargo test --locked --offline --release
```

The dependencies (serde, serde_json; sha2 for a test) are frozen in `../service/vendor`; the build
never reaches the network. `tests/golden.json` holds outputs recorded from the code the crate
replaces, for the same inputs: the server's `rust/src/persona.rs` at 40b2f178 and the desktop's
`files/lumen_persona.py` at af038a0b (German and English preview, account check). Both gave the same
profiles, conversation presets and style texts.

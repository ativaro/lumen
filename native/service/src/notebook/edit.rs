//! The Notes editor's edits of unsaved text, as the earlier `note_tags.add_tag`, `rename_tag` and
//! `notes_properties.change` made them: only the YAML value or `#tag` concerned is replaced, every
//! other character stays. Positions are code points, as Python's are.
use super::python::{self, Py};
use super::text::{self, Front};
use super::{Result, tr};

fn identity(value: &str) -> Result<String> {
    text::identity(value).ok_or_else(|| tr("Ungültiger Tag."))
}

/// `json.dumps(tags, ensure_ascii=False)`.
fn list(tags: &[String]) -> String {
    python::dumps(&Py::List(tags.iter().map(|t| Py::str(t)).collect()), false)
}

fn splice(chars: &[char], start: usize, end: usize, with: &str) -> String {
    let mut result: String = chars[..start].iter().collect();
    result.push_str(with);
    result.extend(&chars[end..]);
    result
}

/// The `tags` value's current texts; a value that is an alias or carries an anchor is refused.
fn current(front: &Front, (key, value): (usize, usize)) -> Result<Vec<String>> {
    let yaml: Vec<char> = front.yaml.chars().collect();
    let (key_end, start) = (front.node(key).end.index, front.node(value).start.index);
    if start < key_end || yaml[key_end.min(yaml.len())..(start + 1).min(yaml.len())].contains(&'&')
    {
        return Err(tr("Verankerte Tags zuerst in unabhängige Werte umwandeln."));
    }
    text::tag_values(front.document.as_ref().expect("a tags value"), value)
        .ok_or_else(|| tr("Tags müssen Text oder eine Liste aus Text sein."))
}

/// The `tags` value replaced by the list `tags`, the value's last newline kept.
fn replace_value(front: &Front, value: usize, tags: &[String]) -> (usize, usize, String) {
    let yaml: Vec<char> = front.yaml.chars().collect();
    let node = front.node(value);
    let (start, end) = (node.start.index, node.end.index);
    let suffix = if yaml.get(start..end).and_then(<[char]>::last) == Some(&'\n') {
        "\n"
    } else {
        ""
    };
    (
        front.start + start,
        front.start + end,
        format!("{}{suffix}", list(tags)),
    )
}

/// `note_tags.add_tag`.
pub fn add_tag(text: &str, tag: &str) -> Result<String> {
    let tag = identity(tag)?;
    let tags = text::tags(text);
    if tags.contains(&tag) {
        return Ok(text.to_owned());
    }
    if tags.len() >= 100 {
        return Err(tr("Maximal 100 Tags pro Notiz."));
    }
    let found = text::tag_front(text)?;
    if text.starts_with("---\n") && found.is_none() {
        return Err(tr("Ungültige Notizeigenschaften."));
    }
    let Some((front, pair)) = found else {
        return Ok(format!("---\ntags: {}\n---\n{text}", list(&[tag])));
    };
    let chars: Vec<char> = text.chars().collect();
    let Some(pair) = pair else {
        if front.root().is_some_and(|root| root.flow) {
            return Err(tr(
                "Tags in kompakten Notizeigenschaften zuerst im Quelltext anlegen.",
            ));
        }
        let line = format!("tags: {}\n", list(&[tag]));
        return Ok(splice(&chars, front.start, front.start, &line));
    };
    let mut changed = current(&front, pair)?
        .iter()
        .map(|t| identity(t))
        .collect::<Result<Vec<_>>>()?;
    changed.push(tag);
    changed.sort();
    changed.dedup();
    let (start, end, value) = replace_value(&front, pair.1, &changed);
    let padding = if chars.get(start.wrapping_sub(1)) == Some(&':') {
        " "
    } else {
        ""
    };
    Ok(splice(&chars, start, end, &format!("{padding}{value}")))
}

/// `note_tags.rename_tag`: `old` (and with `descendants` its subtags) becomes `new`, or goes when
/// `new` is empty, in the front matter's `tags` and as `#tags` of the visible body.
pub fn rename_tag(text: &str, old: &str, new: &str, descendants: bool) -> Result<String> {
    let old = identity(old)?;
    let new = if new.is_empty() {
        String::new()
    } else {
        identity(new)?
    };
    let replacement = |value: &str| -> Result<String> {
        let value = identity(value)?;
        let below = descendants && value.starts_with(&format!("{old}/"));
        Ok(match (value == old || below, new.is_empty()) {
            (false, _) => value,
            (true, true) => String::new(),
            (true, false) => format!("{new}{}", &value[old.len()..]),
        })
    };
    let found = text::tag_front(text)?;
    let mut edits = Vec::new();
    if let Some((front, Some(pair))) = &found {
        let current = current(front, *pair)?;
        let mut changed = Vec::new();
        for tag in &current {
            let tag = replacement(tag)?;
            if !tag.is_empty() {
                changed.push(tag);
            }
        }
        changed.sort();
        changed.dedup();
        let mut before = current
            .iter()
            .map(|t| identity(t))
            .collect::<Result<Vec<_>>>()?;
        before.sort();
        before.dedup();
        if changed != before {
            edits.push(replace_value(front, pair.1, &changed));
        }
    }
    let masked = text::body_mask(text);
    for (start, end) in text::hashtags(&masked) {
        let token: String = masked[start + 1..end].iter().collect();
        let Ok(result) = replacement(&token) else {
            continue;
        };
        if result != identity(&token)? {
            let value = if result.is_empty() {
                result
            } else {
                format!("#{result}")
            };
            edits.push((start, end, value));
        }
    }
    edits.sort();
    let mut chars: Vec<char> = text.chars().collect();
    for (start, end, value) in edits.into_iter().rev() {
        chars.splice(start..end, value.chars());
    }
    Ok(chars.into_iter().collect())
}

/// `notes_properties.change`: sets (or with `remove` deletes) the simple property `name` of `kind`
/// `text` or `date` (`YYYY-MM-DD`).
pub fn set_property(
    text: &str,
    name: &str,
    kind: &str,
    value: &str,
    remove: bool,
) -> Result<String> {
    if !text::property_name(name) || name == "tags" {
        return Err(tr(
            "Einen Eigenschaftsnamen ohne Sonderzeichen wählen; Tags haben eine eigene Bedienung.",
        ));
    }
    if !matches!(kind, "text" | "date") || value.chars().count() > 2000 {
        return Err(tr("Ungültiger Eigenschaftswert."));
    }
    if kind == "date" && !remove && !text::iso_date(value) {
        return Err(tr("Datum als JJJJ-MM-TT eingeben."));
    }
    let front = text::property_document(text)?;
    let mut encoded = if kind == "date" {
        value.to_owned()
    } else {
        python::dumps(&Py::str(value), false)
    };
    let existing = front.as_ref().and_then(|front| {
        front
            .pairs()
            .iter()
            .find(|(key, _)| front.scalar(*key) == Some(name))
            .map(|(key, value)| (front.node(*key).start.index, front.node(*value)))
    });
    let chars: Vec<char> = text.chars().collect();
    if let (Some(front), Some((key, node))) = (&front, existing) {
        if !text::property_values(text)?.iter().any(|(n, _)| n == name) {
            return Err(tr(
                "Diese komplexe oder verankerte Eigenschaft bleibt unverändert.",
            ));
        }
        let (start, end) = (front.start + node.start.index, front.start + node.end.index);
        let newline = chars.get(start..end).and_then(<[char]>::last) == Some(&'\n');
        if remove {
            let line = chars[..front.start + key]
                .iter()
                .rposition(|c| *c == '\n')
                .map_or(0, |at| at + 1);
            let end = if newline {
                end
            } else {
                chars[end..]
                    .iter()
                    .position(|c| *c == '\n')
                    .map_or(front.end, |at| end + at + 1)
            };
            return Ok(splice(&chars, line, end, ""));
        }
        // Block scalars consume their final newline; it keeps the next key on a line of its own.
        if newline {
            encoded.push('\n');
        }
        return Ok(splice(&chars, start, end, &encoded));
    }
    if remove {
        return Ok(text.to_owned());
    }
    let line = format!("{}: {encoded}\n", python::dumps(&Py::str(name), false));
    Ok(match &front {
        None => format!("---\n{line}---\n{text}"),
        Some(front) => splice(&chars, front.start, front.start, &line),
    })
}

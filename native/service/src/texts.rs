//! The Qt side's one translation catalogue, applied by the service: the German source text is the
//! key, `files/translations/en/*.json` hold the English values. The binding names the catalogue
//! folder and the window's language (`lumen_i18n.language()`) with each request.
use serde_json::Value;
use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::rc::Rc;

type Catalogue = Rc<HashMap<String, String>>;
/// A catalogue file's name, modification time and size.
type File = (String, Option<std::time::SystemTime>, u64);

thread_local! {
    /// Catalogues by folder, reloaded when a file in it changes (an update may replace only them).
    static LOADED: RefCell<HashMap<PathBuf, (Vec<File>, Catalogue)>> =
        RefCell::default();
}

/// How the files of a catalogue folder look now, so a changed one is read again.
fn signature(folder: &Path) -> Vec<File> {
    let mut files: Vec<_> = std::fs::read_dir(folder)
        .into_iter()
        .flatten()
        .flatten()
        .filter_map(|entry| {
            let name = entry.file_name().into_string().ok()?;
            let meta = entry.metadata().ok()?;
            (name.ends_with(".json") && meta.is_file())
                .then(|| (name, meta.modified().ok(), meta.len()))
        })
        .collect();
    files.sort();
    files
}

fn load(folder: &Path, files: &[File]) -> Catalogue {
    let mut values = HashMap::new();
    for (name, _, _) in files {
        // An incomplete installation still shows the original readable text.
        let Ok(Value::Object(entries)) = std::fs::read(folder.join(name))
            .map_err(|_| ())
            .and_then(|data| serde_json::from_slice(&data).map_err(|_| ()))
        else {
            continue;
        };
        for (key, value) in entries {
            if let Value::String(value) = value
                && !value.is_empty()
            {
                values.insert(key, value);
            }
        }
    }
    Rc::new(values)
}

/// The language and catalogue of one request.
#[derive(Clone, Default)]
pub struct Texts {
    english: Option<Catalogue>,
}

impl Texts {
    /// `{"language": "de"|"en", "catalogue": "/…/translations/en"}`; German without them.
    pub fn of(request: &Value) -> Self {
        let texts = &request["texts"];
        let Some(folder) = texts["catalogue"].as_str().map(PathBuf::from) else {
            return Self::default();
        };
        if texts["language"] != "en" || !folder.is_absolute() {
            return Self::default();
        }
        let files = signature(&folder);
        let english = LOADED.with_borrow_mut(|loaded| match loaded.get(&folder) {
            Some((seen, catalogue)) if *seen == files => catalogue.clone(),
            _ => {
                let catalogue = load(&folder, &files);
                loaded.insert(folder, (files, catalogue.clone()));
                catalogue
            }
        });
        Self {
            english: Some(english),
        }
    }

    /// The text in the request's language.
    pub fn tr(&self, source: &str) -> String {
        self.english
            .as_ref()
            .and_then(|values| values.get(source))
            .cloned()
            .unwrap_or_else(|| source.to_owned())
    }

    /// The translated template with `{0}`, `{1}` … filled in; a template that does not fit its
    /// values falls back to the source text.
    pub fn tr_args(&self, source: &str, values: &[&str]) -> String {
        format(&self.tr(source), values)
            .or_else(|| format(source, values))
            .unwrap_or_else(|| source.to_owned())
    }
}

/// Python's `str.format` for positional fields only: `{0}`, `{{` and `}}`.
fn format(template: &str, values: &[&str]) -> Option<String> {
    let mut result = String::new();
    let mut rest = template;
    while let Some(at) = rest.find(['{', '}']) {
        result.push_str(&rest[..at]);
        let tail = &rest[at..];
        if let Some(after) = tail.strip_prefix("{{").or_else(|| tail.strip_prefix("}}")) {
            result.push_str(&tail[..1]);
            rest = after;
            continue;
        }
        let inner = tail.strip_prefix('{')?;
        let end = inner.find('}')?;
        result.push_str(values.get(inner[..end].parse::<usize>().ok()?)?);
        rest = &inner[end + 1..];
    }
    result.push_str(rest);
    Some(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn english_values_apply_only_in_english_and_templates_fall_back_safely() {
        let folder =
            std::env::temp_dir().join(format!("lumen-service-texts-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&folder);
        std::fs::create_dir(&folder).unwrap();
        std::fs::write(
            folder.join("a.json"),
            r#"{"Öffne {0}": "Open {0}", "Fehler {0}": "Error {missing}", "Leer": ""}"#,
        )
        .unwrap();
        std::fs::write(folder.join("b.json"), "{broken").unwrap();
        let request = |language| json!({"texts": {"language": language, "catalogue": folder}});
        let english = Texts::of(&request("en"));
        assert_eq!(
            english.tr_args("Öffne {0}", &["Notiz {x}.md"]),
            "Open Notiz {x}.md"
        );
        assert_eq!(
            english.tr_args("Fehler {0}", &["Original"]),
            "Fehler Original"
        );
        assert_eq!(english.tr("Leer"), "Leer");
        assert_eq!(english.tr("Noch nicht übersetzt"), "Noch nicht übersetzt");
        assert_eq!(english.tr_args("{{a}} {1} {0}", &["x", "y"]), "{a} y x");
        let german = Texts::of(&request("de"));
        assert_eq!(german.tr_args("Öffne {0}", &["Datei"]), "Öffne Datei");
        std::fs::write(
            folder.join("a.json"),
            r#"{"Leer": "Empty", "Long one": "x"}"#,
        )
        .unwrap();
        assert_eq!(Texts::of(&request("en")).tr("Leer"), "Empty");
        std::fs::remove_dir_all(&folder).unwrap();
    }
}

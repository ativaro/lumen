//! The persona of the desktop's conversations, with the shared crate `native/persona`: the profile a
//! turn uses (the view's local profile, or the account persona the paired server answers on
//! `/bridge/persona`), the preset chosen for one conversation, the style text, and the persona rows
//! of each conversation in the Store (`lumen.sqlite3`, table `settings`), which only the service
//! writes. The settings view shows the catalogue and its preview through `persona.catalog` and
//! `persona.preview`; QSettings stay with the view, which sends their values.
use crate::bridge;
use crate::engine::{self, Failure};
use crate::store::{store, write};
use crate::texts::Texts;
use lumen_engine::python;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::time::Duration;

/// What a conversation's persona was made of (`persona/context/<session>`): the server binding (the
/// pairing's `connection` scope, the local deviation `override` and the fingerprint of the local
/// profile it used), the account persona's revision (0 for the local profile, -1 for the default
/// style while the account persona was unreachable) and the conversation's preset. A conversation
/// continues only while it stays the same.
#[derive(Debug, PartialEq)]
pub struct Context {
    connection: String,
    deviation: bool,
    local: String,
    revision: i64,
    choice: String,
}

impl Context {
    fn value(&self) -> Value {
        json!({"binding": {"connection": self.connection, "override": self.deviation,
            "local": self.local}, "revision": self.revision, "choice": self.choice})
    }

    /// The row as the earlier Python view wrote it (`json.dumps`, keys in this order).
    fn text(&self) -> String {
        format!(
            r#"{{"binding": {{"connection": {}, "override": {}, "local": {}}}, "revision": {}, "choice": {}}}"#,
            json!(self.connection),
            self.deviation,
            json!(self.local),
            self.revision,
            json!(self.choice)
        )
    }
}

/// The persona part of one turn.
pub struct Persona {
    /// The style text after the mode's system text.
    pub instruction: String,
    context: Context,
    /// The Store the conversation's rows are in.
    store: String,
    /// The account persona could not be read; the turn uses the default style.
    pub unreachable: bool,
}

/// `sha256(json.dumps(value))` with Python's ASCII escapes. Maps are ordered by key, as `sort_keys`
/// orders them, so a profile's fingerprint is the one the earlier view computed.
fn fingerprint(value: &Value) -> String {
    let text = python::python_ascii(&python::python_json(value));
    engine::hex(&Sha256::digest(text.as_bytes()))
}

/// `lumen_connect.connection_scope`: the server, device and token a persona was read with.
pub fn scope(pairing: &Map<String, Value>) -> String {
    let field = |key| pairing.get(key).cloned().unwrap_or_default();
    fingerprint(&json!([
        field("server"),
        field("device_id"),
        field("token")
    ]))
}

fn preset(choice: &str) -> bool {
    lumen_persona::catalog()["presets"]
        .as_array()
        .is_some_and(|presets| presets.iter().any(|p| p["id"] == choice))
}

/// A stored `personaProfile` (JSON text, keys in any order); anything else stands for no settings.
fn stored(raw: &str) -> Value {
    lumen_persona::profile(&serde_json::from_str(raw).unwrap_or_default())
}

/// The account persona of the paired server, as the earlier worker read it: every step within 3 s,
/// all within 5 s. `None` when it cannot be read or the answer is not an account persona.
async fn account(pairing: &Map<String, Value>) -> Option<(Value, i64)> {
    let text = |key| {
        pairing
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned()
    };
    let connection = bridge::Connection {
        server: text("server"),
        token: text("token"),
        ca_file: text("ca_file"),
        home: std::env::var_os("HOME").map(Into::into),
    };
    let request = bridge::request(&connection, "/bridge/persona", None, Duration::from_secs(3));
    let reply = tokio::time::timeout(Duration::from_secs(5), request)
        .await
        .ok()?
        .ok()?;
    if !(200..300).contains(&reply.status) {
        return None;
    }
    let (profile, revision) =
        lumen_persona::account(&serde_json::from_slice(&reply.body).ok()?).ok()?;
    Some((profile, i64::try_from(revision).ok()?))
}

/// The persona of a turn in Lumen's style. The request carries the view's settings, `"persona":
/// {"profile": "<personaProfile>", "override": <personaLocalOverride>, "choice": "<the
/// conversation's preset or empty>"}`, the Store (`store`) and the view's environment
/// (`engine.env`), whose configuration folder holds the pairing. Without a pairing, or with the
/// local deviation, the local profile applies; else the account persona, or the default style while
/// it cannot be read. A pairing that changes meanwhile fails the turn.
pub async fn prepare(request: &Value, t: &Texts) -> Result<Persona, Failure> {
    let inputs = &request["persona"];
    let (Some(raw), Some(deviation), Some(choice), Some(store)) = (
        inputs["profile"].as_str(),
        inputs["override"].as_bool(),
        inputs["choice"].as_str(),
        request["store"].as_str().filter(|s| s.starts_with('/')),
    ) else {
        return Err(Failure::invalid());
    };
    let env = engine::strings(&request["engine"]["env"]).ok_or_else(Failure::invalid)?;
    let choice = if preset(choice) { choice } else { "" };
    let local = stored(raw);
    let binding = |pairing: &Option<Map<String, Value>>| {
        let own = pairing.is_none() || deviation;
        (
            pairing.as_ref().map(scope).unwrap_or_default(),
            if own {
                fingerprint(&local)
            } else {
                String::new()
            },
        )
    };
    let pairing = engine::pairing(&env).map_err(|()| {
        Failure::new(t.tr("Persona- oder Serverbindung nicht lesbar. Bitte Einstellungen prüfen."))
    })?;
    let (connection, fingerprint) = binding(&pairing);
    let (profile, revision) = match &pairing {
        Some(paired) if !deviation => {
            let answer = account(paired).await;
            let changed =
                || Failure::new(t.tr("Persona- oder Serverbindung geändert. Bitte erneut senden."));
            let now = engine::pairing(&env).map_err(|()| changed())?;
            if binding(&now) != (connection.clone(), fingerprint.clone()) {
                return Err(changed());
            }
            // Read with another pairing of the same scope: not this account's persona.
            match answer.filter(|_| now.as_ref() == Some(paired)) {
                Some(account) => account,
                None => (lumen_persona::catalog()["default"].clone(), -1),
            }
        }
        _ => (local, 0),
    };
    Ok(Persona {
        instruction: lumen_persona::instruction(&lumen_persona::chosen(&profile, choice)),
        context: Context {
            connection,
            deviation,
            local: fingerprint,
            revision,
            choice: choice.into(),
        },
        store: store.into(),
        unreachable: revision == -1,
    })
}

/// Whether the conversation `session` was held with this persona; one without its row was not.
pub async fn continues(session: &str, persona: &Persona, t: &Texts) -> Result<bool, Failure> {
    let key = format!("persona/context/{session}");
    let row = store(&persona.store, t, move |db| crate::store::read(db, &key)).await?;
    Ok(row
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .is_some_and(|value| value == persona.context.value()))
}

/// The rows of a conversation that just began: its preset, when one was chosen, and its persona.
pub async fn begun(session: &str, persona: &Persona, t: &Texts) -> Result<(), Failure> {
    let mut rows = vec![(format!("persona/context/{session}"), persona.context.text())];
    if !persona.context.choice.is_empty() {
        rows.push((
            format!("persona/session/{session}"),
            json!(persona.context.choice).to_string(),
        ));
    }
    store(&persona.store, t, move |db| write(db, &rows)).await
}

/// The catalogue in the request's language: `presets` (`id`, `title`, `description`) and `fields`
/// (`id`, `title`, `options` with `id` and `title`), in the order the settings view shows them.
fn catalogue(t: &Texts) -> Value {
    let catalog = lumen_persona::catalog();
    let tr = |text: &Value| json!(t.tr(text.as_str().unwrap_or_default()));
    let rows = |key: &str| catalog[key].as_array().cloned().unwrap_or_default();
    let presets: Vec<_> = rows("presets")
        .iter()
        .map(|p| json!({"id": p["id"], "title": tr(&p["title"]), "description": tr(&p["description"])}))
        .collect();
    let fields: Vec<_> = rows("fields")
        .iter()
        .map(|field| {
            let options: Vec<_> = field["options"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|o| json!({"id": o["id"], "title": tr(&o["title"])}))
                .collect();
            json!({"id": field["id"], "title": tr(&field["title"]), "options": options})
        })
        .collect();
    json!({"presets": presets, "fields": fields})
}

/// `persona.catalog`; `persona.preview` with `profile` (JSON text) and an optional preset `choice`
/// whose traits replace the profile's: the profile it stands for and its illustrative preview;
/// `persona.choose` with `store`, `session` and `choice` (a preset or empty): the conversation's
/// preset.
pub async fn once(op: &str, request: &Value, t: &Texts) -> Value {
    let choice = request["choice"].as_str().unwrap_or_default();
    match op {
        "persona.catalog" => catalogue(t),
        "persona.preview" => {
            let Some(raw) = request["profile"].as_str() else {
                return Failure::invalid().answer();
            };
            let value = lumen_persona::chosen(&stored(raw), choice);
            let preview = lumen_persona::preview(&value, |text| t.tr(text));
            json!({"profile": value, "preview": preview})
        }
        "persona.choose" => {
            let (Some(store_path), Some(session)) = (
                request["store"].as_str().filter(|s| s.starts_with('/')),
                request["session"].as_str().filter(|s| {
                    (1..=200).contains(&s.len())
                        && s.bytes()
                            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
                }),
            ) else {
                return Failure::invalid().answer();
            };
            if !choice.is_empty() && !preset(choice) {
                return Failure::invalid().answer();
            }
            let rows = vec![(
                format!("persona/session/{session}"),
                json!(choice).to_string(),
            )];
            match store(store_path, t, move |db| write(db, &rows)).await {
                Ok(()) => json!({}),
                Err(failure) => failure.answer(),
            }
        }
        _ => json!({"error": "unknown_op"}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fingerprints_and_rows_are_the_ones_the_python_view_wrote() {
        // Recorded with files/lumen_persona.py at ee2046ca: the default profile, and the profile of
        // `{"user_name": "Änne 😀", "preset": "companion", "name": "Nova\u0007 x  y", "closeness":
        // "personal"}`, in any key order.
        assert_eq!(
            fingerprint(&stored("")),
            "143bbc084658bf3a903e556fe4874825aabaa517f48d7d6803e5fcc266c384ac"
        );
        let profile = r#"{"user_name": "Änne 😀", "preset": "companion", "name": "Nova\u0007 x  y", "closeness": "personal"}"#;
        let sorted = serde_json::to_string(&stored(profile)).unwrap();
        assert_eq!(fingerprint(&stored(profile)), fingerprint(&stored(&sorted)));
        assert_eq!(fingerprint(&stored(profile)), GOLDEN_LOCAL);
        // `lumen_connect.connection_scope` of these pairings.
        for (server, expected) in [
            ("https://127.0.0.1:4433", GOLDEN_SCOPE),
            (
                "https://bücher.invalid",
                "5c8e7c6ab4e65936aec97665b8718e90addca9950ecae023c963c52292fd1131",
            ),
        ] {
            let pairing = json!({"server": server, "device_id": "a5c704e4-c826-479b-bcde-41b2c8dc8efb",
                "token": "golden-device-token", "account": "Änne"});
            assert_eq!(scope(pairing.as_object().unwrap()), expected);
        }
        let context = Context {
            connection: GOLDEN_SCOPE.into(),
            deviation: true,
            local: GOLDEN_LOCAL.into(),
            revision: -1,
            choice: "kate".into(),
        };
        assert_eq!(
            context.text(),
            format!(
                r#"{{"binding": {{"connection": "{GOLDEN_SCOPE}", "override": true, "local": "{GOLDEN_LOCAL}"}}, "revision": -1, "choice": "kate"}}"#
            )
        );
        assert_eq!(
            serde_json::from_str::<Value>(&context.text()).unwrap(),
            context.value()
        );
    }

    const GOLDEN_LOCAL: &str = "a231df3716ee1fc44131912bdf0565860d0a08b1e911d321adab3202bf7fc8ec";
    const GOLDEN_SCOPE: &str = "a05b4e23f2021624e1dd186c2f8914b80e7b4aa286c4796490f28867af9f31e8";

    #[test]
    fn the_settings_view_gets_the_catalogue_and_preview_in_its_language() {
        let english = Texts::of(&json!({"texts": {"language": "en",
            "catalogue": concat!(env!("CARGO_MANIFEST_DIR"), "/../../files/translations/en")}}));
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let ask = |request: Value, t: &Texts| {
            runtime.block_on(once(request["op"].as_str().unwrap(), &request, t))
        };
        let catalog = ask(json!({"op": "persona.catalog"}), &english);
        assert_eq!(
            catalog["presets"][0],
            json!({"id": "guide", "title": "Guide",
            "description": "Calm, clear and friendly."})
        );
        assert_eq!(
            catalog["fields"][0]["options"][1],
            json!({"id": "female", "title": "Female"})
        );
        let german = ask(json!({"op": "persona.catalog"}), &Texts::default());
        assert_eq!(german["presets"][0]["title"], "Lotse");
        let preview = ask(
            json!({"op": "persona.preview", "profile": r#"{"name": "Nova", "user_name": "Alex", "preset": "kate", "length": "detailed"}"#,
                "choice": "companion"}),
            &Texts::default(),
        );
        assert_eq!(
            (
                &preview["profile"]["preset"],
                &preview["profile"]["name"],
                &preview["profile"]["length"]
            ),
            (&json!("companion"), &json!("Nova"), &json!("balanced"))
        );
        assert_eq!(
            preview["preview"],
            "Alex, Schauen wir gemeinsam nach. Ich prüfe zuerst die Verbindung zum NAS. Danach sehen wir, ob die Anmeldung oder die Freigabe betroffen ist."
        );
        assert_eq!(
            ask(
                json!({"op": "persona.preview", "profile": "broken"}),
                &english
            )["profile"],
            lumen_persona::catalog()["default"]
        );
        assert_eq!(
            ask(json!({"op": "persona.preview"}), &english)["error"],
            "invalid_request"
        );
    }

    #[test]
    fn only_the_settings_rows_of_a_current_store_are_written() {
        let folder =
            std::env::temp_dir().join(format!("lumen-service-persona-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&folder);
        std::fs::create_dir_all(&folder).unwrap();
        let path = folder.join("lumen.sqlite3");
        let db = rusqlite::Connection::open(&path).unwrap();
        db.execute_batch(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); PRAGMA user_version=3;",
        )
        .unwrap();
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let t = Texts::default();
        let store = path.display().to_string();
        let choose = |choice: &str, session: &str| {
            runtime.block_on(once(
                "persona.choose",
                &json!({"store": store, "session": session, "choice": choice}),
                &t,
            ))
        };
        assert_eq!(choose("kate", "ses_a"), json!({}));
        assert_eq!(choose("", "ses_b"), json!({}));
        assert_eq!(choose("nobody", "ses_c")["error"], "invalid_request");
        assert_eq!(choose("kate", "../x")["error"], "invalid_request");
        let rows: Vec<(String, String)> = db
            .prepare("SELECT key, value FROM settings ORDER BY key")
            .unwrap()
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
            .unwrap()
            .collect::<Result<_, _>>()
            .unwrap();
        assert_eq!(
            rows,
            [
                ("persona/session/ses_a".to_owned(), r#""kate""#.to_owned()),
                ("persona/session/ses_b".to_owned(), r#""""#.to_owned())
            ]
        );
        let persona = Persona {
            instruction: String::new(),
            context: Context {
                connection: String::new(),
                deviation: false,
                local: GOLDEN_LOCAL.into(),
                revision: 0,
                choice: "maker".into(),
            },
            store: store.clone(),
            unreachable: false,
        };
        runtime.block_on(async {
            assert!(!continues("ses_new", &persona, &t).await.unwrap());
            begun("ses_new", &persona, &t).await.unwrap();
            assert!(continues("ses_new", &persona, &t).await.unwrap());
        });
        let stored: String = db
            .query_row(
                "SELECT value FROM settings WHERE key='persona/session/ses_new'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(stored, r#""maker""#);
        // A newer Store and a missing one are refused; nothing is created.
        db.execute_batch("PRAGMA user_version=4").unwrap();
        assert_eq!(
            choose("kate", "ses_a")["failed"],
            "Diese Lumen-Datenbank benötigt eine neuere Version."
        );
        let missing = folder.join("missing.sqlite3").display().to_string();
        let answer = runtime.block_on(once(
            "persona.choose",
            &json!({"store": missing, "session": "ses_a", "choice": ""}),
            &t,
        ));
        assert_eq!(
            answer["failed"],
            "Einstellungen konnten nicht gespeichert werden."
        );
        assert!(!folder.join("missing.sqlite3").exists());
        std::fs::remove_dir_all(&folder).unwrap();
    }
}

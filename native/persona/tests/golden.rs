//! The crate against outputs recorded from the code it replaces, for the same inputs: the server's
//! `rust/src/persona.rs` (40b2f178) and the desktop's `files/lumen_persona.py` (af038a0b).
use lumen_persona::{
    PREVIEW_MORE, account, catalog, checked, chosen, instruction, preview, profile,
};
use serde_json::{Map, Value, json};
use std::path::Path;

fn golden() -> Value {
    serde_json::from_str(include_str!("golden.json")).unwrap()
}

/// The desktop's English product texts (`files/translations/en/*.json`).
fn english() -> Map<String, Value> {
    let folder = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../files/translations/en");
    let mut texts = Map::new();
    for entry in std::fs::read_dir(folder).unwrap() {
        let file: Map<String, Value> =
            serde_json::from_str(&std::fs::read_to_string(entry.unwrap().path()).unwrap()).unwrap();
        texts.extend(file);
    }
    texts
}

#[test]
fn profiles_presets_and_style_text_match_server_and_desktop() {
    let golden = golden();
    let choices = golden["choices"].as_array().unwrap();
    for (i, raw) in golden["inputs"].as_array().unwrap().iter().enumerate() {
        assert_eq!(profile(raw), golden["profile"][i], "profile {raw}");
        // Refused profiles are recorded as null.
        let strict = checked(raw).unwrap_or(Value::Null);
        assert_eq!(strict, golden["strict"][i], "strict {raw}");
        for (j, choice) in choices.iter().enumerate() {
            assert_eq!(
                chosen(raw, choice.as_str().unwrap()),
                golden["chosen"][i][j],
                "chosen {raw} {choice}"
            );
        }
        assert_eq!(
            instruction(raw),
            golden["instruction"][i],
            "instruction {raw}"
        );
        // The server's API answers carry the same JSON text.
        assert_eq!(
            serde_json::to_string(&profile(raw)).unwrap(),
            golden["api"]["profile"][i],
            "api {raw}"
        );
    }
    let api = json!({"presets": catalog()["presets"], "fields": catalog()["fields"]});
    assert_eq!(
        serde_json::to_string(&api).unwrap(),
        golden["api"]["catalogue"]
    );
}

#[test]
fn desktop_preview_and_account_check_match_the_desktop() {
    let golden = golden();
    let english = english();
    let translate = |text: &str| {
        english
            .get(text)
            .and_then(Value::as_str)
            .unwrap_or(text)
            .to_owned()
    };
    for (i, raw) in golden["inputs"].as_array().unwrap().iter().enumerate() {
        assert_eq!(
            preview(raw, str::to_owned),
            golden["preview"]["de"][i],
            "{raw}"
        );
        assert_eq!(preview(raw, translate), golden["preview"]["en"][i], "{raw}");
    }
    for (answer, expected) in golden["answers"]
        .as_array()
        .unwrap()
        .iter()
        .zip(golden["account"].as_array().unwrap())
    {
        let accepted = account(answer)
            .ok()
            .map(|(profile, revision)| json!([profile, revision]));
        assert_eq!(
            accepted.as_ref().unwrap_or(&Value::Null),
            expected,
            "{answer}"
        );
    }
}

#[test]
fn every_german_text_the_desktop_shows_has_its_english_key() {
    let english = english();
    let catalog = catalog();
    let mut texts: Vec<&str> = PREVIEW_MORE.to_vec();
    for preset in catalog["presets"].as_array().unwrap() {
        texts.extend(["title", "description", "example"].map(|key| preset[key].as_str().unwrap()));
    }
    for field in catalog["fields"].as_array().unwrap() {
        texts.push(field["title"].as_str().unwrap());
        texts.extend(
            field["options"]
                .as_array()
                .unwrap()
                .iter()
                .map(|o| o["title"].as_str().unwrap()),
        );
    }
    let missing: Vec<_> = texts
        .into_iter()
        .filter(|text| !english.contains_key(*text))
        .collect();
    assert!(missing.is_empty(), "{missing:?}");
}

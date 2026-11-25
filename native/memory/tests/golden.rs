//! The crate against outputs recorded from the code it replaces, for the same inputs: the server's
//! `rust/src/memory_rank.rs`, `note_unicode.rs`, the forgetting fingerprint and the entries of
//! `worker/encoder.rs` (50d57c35) and the desktop's `files/memory_core.py` and
//! `lumen_memory.fingerprint` (61ff3bff).
use lumen_memory::{Entry, Ranking, eligible, fingerprint, mentions, terms, unicode::search_fold};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::HashMap;

fn golden() -> Value {
    serde_json::from_str(include_str!("golden.json")).unwrap()
}

#[test]
fn entries_and_eligibility_match_server_and_desktop() {
    let golden = golden();
    let mut entries = Vec::new();
    for (i, raw) in golden["entries"].as_array().unwrap().iter().enumerate() {
        let entry = Entry::deserialize(raw).ok().filter(Entry::valid);
        assert_eq!(json!(entry.is_some()), golden["valid"][i], "valid {raw}");
        entries.extend(entry);
    }
    for query in golden["eligible"].as_array().unwrap() {
        let (boundary, project) = (
            query["boundary"].as_str().unwrap(),
            query["project"].as_str().unwrap(),
        );
        let ids: Vec<_> = eligible(entries.clone(), boundary, project)
            .into_iter()
            .map(|e| e.id)
            .collect();
        assert_eq!(json!(ids), query["ids"], "eligible {query}");
    }
}

#[test]
fn terms_folding_fingerprints_and_mentions_match_server_and_desktop() {
    let golden = golden();
    let texts: Vec<_> = golden["texts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();
    for (i, text) in texts.iter().enumerate() {
        assert_eq!(json!(terms(text)), golden["terms"][i], "terms {text:?}");
        assert_eq!(
            json!(search_fold(text)),
            golden["normalize"][i],
            "fold {text:?}"
        );
        assert_eq!(
            json!(fingerprint(text)),
            golden["fingerprint"][i],
            "fingerprint {text:?}"
        );
    }
    let pairs = texts[..20]
        .iter()
        .flat_map(|query| texts[..20].iter().map(|text| mentions(text, query)));
    assert_eq!(json!(pairs.collect::<Vec<_>>()), golden["mentions"]);
}

#[test]
fn rankings_match_server_and_desktop() {
    let golden = golden();
    for case in golden["cases"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let rows = case["rows"].as_array().unwrap();
        let key = |r: &Value| {
            (
                r["id"].as_str().unwrap().to_owned(),
                r["revision"].to_string(),
            )
        };
        let mut ranking = Ranking::new(case["query"].as_str().unwrap());
        for r in rows {
            let text = |field: &str| r[field].as_str().unwrap();
            ranking.push(
                key(r),
                text("title"),
                text("text"),
                r["updated"].as_f64().unwrap(),
                r["correction"] == true,
            );
        }
        let semantic: Option<HashMap<_, _>> = case["semantic"].as_object().map(|map| {
            map.iter()
                .map(|(k, v)| {
                    let (id, revision) = k.split_once('/').unwrap();
                    ((id.to_owned(), revision.to_owned()), v.as_f64().unwrap())
                })
                .collect()
        });
        let ids = |order: Vec<usize>| {
            json!(
                order
                    .iter()
                    .map(|i| &ranking.rows[*i].key.0)
                    .collect::<Vec<_>>()
            )
        };
        // The server: no scores means no fusion; no reserved rows; an empty query browses.
        let scores = semantic.as_ref().filter(|s| !s.is_empty());
        assert_eq!(
            ids(ranking.ordered(scores, &[], true)),
            case["server"]["ordered"],
            "server {name}"
        );
        let literal: Vec<_> = ranking.rows.iter().map(|r| r.literal_body).collect();
        assert_eq!(
            json!(literal),
            case["server"]["literal_body"],
            "literal {name}"
        );
        // The desktop: `preferences` reserves its newest general preferences, corrections first.
        let mut preferences: Vec<_> = (0..rows.len())
            .filter(|i| rows[*i]["kind"] == "preference" && rows[*i]["project"] == "")
            .collect();
        preferences.sort_by(|a, b| {
            let (a, b) = (&rows[*a], &rows[*b]);
            (b["correction"] == true)
                .cmp(&(a["correction"] == true))
                .then(
                    b["updated"]
                        .as_f64()
                        .unwrap()
                        .total_cmp(&a["updated"].as_f64().unwrap()),
                )
                .then(key(a).cmp(&key(b)))
        });
        for (mode, expected) in case["desktop"].as_object().unwrap() {
            let (browse, reserved) = mode.split_once(',').unwrap();
            let reserved: usize = reserved["preferences=".len()..].parse().unwrap();
            let first = &preferences[..reserved.min(preferences.len())];
            let order = ranking.ordered(semantic.as_ref(), first, browse == "browse=True");
            assert_eq!(&ids(order), expected, "desktop {name} {mode}");
        }
    }
}

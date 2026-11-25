//! The learning MCP against the recorded Python server (`tests/learning-mcp-golden.json`, made by
//! `measure/memory/make_mcp_golden.py` from `memory_agent_stdio.py` and `bin/lumen_mcp.py` at
//! ee2046ca): the same answer lines, `result.json` and its mode, under the event's consent and after
//! learning was switched off.
use super::*;
use std::os::unix::fs::PermissionsExt;

#[test]
fn the_learning_tools_answer_as_the_python_server() {
    let golden = python::loads(include_str!("../../tests/learning-mcp-golden.json")).unwrap();
    let base = std::env::temp_dir().join(format!("lumen-learning-mcp-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    for folder in ["state", "home", "config", "data", "tools"] {
        std::fs::create_dir_all(base.join(folder)).unwrap();
    }
    rusqlite::Connection::open(base.join("state/lumen.sqlite3"))
        .unwrap()
        .execute_batch("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); PRAGMA user_version=3;")
        .unwrap();
    let store = Store {
        directory: base.join("state"),
    };
    let mut vars = crate::engine::Env::new();
    for (key, value) in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("LUMEN_TOOLS_DATA", "tools"),
    ] {
        vars.insert(key.into(), base.join(value).to_string_lossy().into_owned());
    }
    let mut event = get(&golden, "event").unwrap().clone();
    event.set(
        "store",
        Py::Str(store.directory.to_string_lossy().into_owned()),
    );
    for run in python_items(get(&golden, "runs").unwrap()) {
        let consent = get(run, "consent").is_some_and(Py::truthy);
        let options = dict(vec![
            ("enabled", Py::Bool(true)),
            ("learn", Py::Bool(consent)),
            ("solutions", Py::Bool(true)),
            ("automatic", Py::Bool(true)),
        ]);
        store.set_setting("memory/options", &options).unwrap();
        // The event's stamp: memory on, its privacy revision, no server, no project folders.
        let stamp = python_items(get(&event, "stamp").unwrap()).to_vec();
        store
            .set_setting("memory/privacy_revision", &stamp[1])
            .unwrap();
        let folder = base.join(format!("run-{consent}"));
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::write(folder.join("event.json"), python::dumps(&event, false)).unwrap();
        let mut answered = Vec::new();
        let sent = s(run, "sent").as_bytes().to_vec();
        serve(
            &folder.join("event.json"),
            std::io::Cursor::new(sent),
            &mut answered,
            &vars,
        )
        .unwrap();
        assert_eq!(
            String::from_utf8(answered).unwrap(),
            s(run, "answered"),
            "consent {consent}"
        );
        let result = folder.join("result.json");
        match get(run, "result") {
            Some(Py::Str(expected)) => {
                assert_eq!(&std::fs::read_to_string(&result).unwrap(), expected);
                assert_eq!(
                    result.metadata().unwrap().permissions().mode() & 0o777,
                    0o600
                );
            }
            _ => assert!(!result.exists()),
        }
    }
    let _ = std::fs::remove_dir_all(&base);
}

#[test]
fn the_profile_holds_only_the_learning_tools_and_the_models_credentials() {
    let base = std::env::temp_dir().join(format!("lumen-learning-profile-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    std::fs::create_dir_all(base.join("data/opencode")).unwrap();
    std::fs::create_dir_all(base.join("profile")).unwrap();
    std::fs::write(
        base.join("data/opencode/auth.json"),
        r#"{"fake": {"key": "k"}, "other": {"key": "secret"}}"#,
    )
    .unwrap();
    let mut vars = crate::engine::Env::new();
    vars.insert("HOME".into(), base.to_string_lossy().into_owned());
    vars.insert(
        "XDG_DATA_HOME".into(),
        base.join("data").to_string_lossy().into_owned(),
    );
    let event = dict(vec![("store", Py::str("/state"))]);
    let environment = profile(
        &base.join("profile"),
        &json!({"provider": {"fake": {"options": {"baseURL": "http://127.0.0.1:1/v1"}}}}),
        "fake/one",
        &event,
        &vars,
        Path::new("/usr/lib/lumen/lumen-service"),
    )
    .unwrap();
    assert_eq!(
        std::fs::read_to_string(base.join("profile/data/opencode/auth.json")).unwrap(),
        r#"{"fake": {"key": "k"}}"#
    );
    let engine: Value = serde_json::from_str(&environment["OPENCODE_CONFIG_CONTENT"]).unwrap();
    assert_eq!(
        engine["mcp"]["lumen_learning"]["command"][0],
        "/usr/lib/lumen/lumen-service"
    );
    assert_eq!(
        engine["mcp"]["lumen_learning"]["command"][1],
        "learning-mcp"
    );
    assert_eq!(engine["permission"]["*"], "deny");
    assert!(
        profile(
            &base.join("other"),
            &json!({}),
            "no-provider",
            &event,
            &vars,
            Path::new("x")
        )
        .is_err()
    );
    assert!(!base.join("other").exists());
    let _ = std::fs::remove_dir_all(&base);
}

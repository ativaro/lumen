use std::process::Command;

#[test]
fn standalone_probe_completes_without_exposing_fixture_values() {
    let output = Command::new(env!("CARGO_BIN_EXE_lumen-vault-core"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "probe failure: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(text.contains("PASS KeePassXC"));
    assert!(text.contains("PRODUCTION_READY=false"));
    for secret in [
        "SYNTHETIC-PROBE-MASTER",
        "SYNTHETIC-NEW-SECRET",
        "SYNTHETIC-XC-CHANGED",
        "demo@example.invalid",
    ] {
        assert!(!text.contains(secret));
        assert!(!String::from_utf8_lossy(&output.stderr).contains(secret));
    }
}
#[test]
fn executable_rejects_all_user_input_arguments() {
    let output = Command::new(env!("CARGO_BIN_EXE_lumen-vault-core"))
        .args(["--open", "/does/not/exist"])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
}

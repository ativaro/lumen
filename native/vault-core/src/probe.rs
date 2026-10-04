//! The only executable path: self-contained synthetic fixtures, no user inputs.
use crate::{Error, Result, header, store::Session};
use std::{
    fs,
    io::Write,
    os::unix::fs::PermissionsExt,
    path::Path,
    process::{Command, Stdio},
    time::Instant,
};
use zeroize::Zeroizing;
const PASSWORD: &str = "SYNTHETIC-PROBE-MASTER-NOT-PRIVATE";
const OLD: &str = "SYNTHETIC-OLD-SECRET-NOT-PRIVATE";
const NEW: &str = "SYNTHETIC-NEW-SECRET-NOT-PRIVATE";
fn key() -> Zeroizing<String> {
    Zeroizing::new(PASSWORD.to_owned())
}
fn directory() -> Result<tempfile::TempDir> {
    let d = tempfile::tempdir()?;
    fs::set_permissions(d.path(), fs::Permissions::from_mode(0o700))?;
    Ok(d)
}
fn require(condition: bool) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(Error::InvalidFile)
    }
}
fn xc(arguments: &[&str], input: &str) -> Result<Vec<u8>> {
    let mut child = Command::new("/usr/bin/keepassxc-cli")
        .args(arguments)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    child
        .stdin
        .take()
        .ok_or(Error::Io)?
        .write_all(input.as_bytes())?;
    let result = child.wait_with_output()?;
    if !result.status.success() {
        return Err(Error::Compatibility);
    }
    if result.stdout.len() > header::MAX_FILE {
        return Err(Error::Limit);
    }
    Ok(result.stdout)
}
fn no_canaries(root: &Path) -> Result<()> {
    for entry in fs::read_dir(root)? {
        let p = entry?.path();
        let data = fs::read(p)?;
        for value in [
            PASSWORD,
            OLD,
            NEW,
            "SYNTHETIC-XC-CHANGED",
            "demo@example.invalid",
            "SYNTHETIC-MAIL-ENTRY",
            "秘密 • مرحبا • Zürich",
        ] {
            require(!data.windows(value.len()).any(|w| w == value.as_bytes()))?;
        }
    }
    Ok(())
}
/// Runs entirely on fixed public examples in newly created private directories.
/// Returned strings are fixed checkpoint labels and timings, never vault fields.
pub fn qualify() -> Result<Vec<String>> {
    let started = Instant::now();
    let root = directory()?;
    let mut session = Session::create(root.path(), key())?;
    let generated = crate::generate_password()?;
    require(generated.len() == 24)?;
    drop(generated);
    let id = session.add("SYNTHETIC-MAIL-ENTRY", Zeroizing::new(OLD.into()))?;
    session.set(
        id,
        "UserName",
        Zeroizing::new("demo@example.invalid".into()),
    )?;
    session.set(id, "URL", Zeroizing::new("https://example.invalid".into()))?;
    session.set(
        id,
        "Lumen:Token",
        Zeroizing::new("秘密 • مرحبا • Zürich".into()),
    )?;
    session.set(
        id,
        "Notes",
        Zeroizing::new("line one\nline two\tUnicode ✓".into()),
    )?;
    session.set(id, "Password", Zeroizing::new(NEW.into()))?;
    session.save()?;
    let history = session.history_len(id)?;
    require(history >= 5)?;
    let file = root.path().join("vault.kdbx");
    let bytes = fs::read(&file)?;
    let profile = header::inspect(&bytes)?;
    require(profile.memory == 64 * 1024 * 1024 && profile.iterations == 3)?;
    session.lock();
    require(matches!(session.field(id, "Password"), Err(Error::Locked)))?;
    drop(session);
    let mut session = Session::open(root.path(), key())?;
    require(&**session.field(id, "Password")? == NEW)?;
    require(session.history_len(id)? == history)?;
    session.save()?;
    let resaved = fs::read(&file)?;
    require(bytes != resaved)?;
    drop(session);
    let mut checks = vec![
        "PASS create/save/reopen: KDBX 4.1 / AES-256 / Argon2id (64 MiB, 3 iterations, 2 lanes)"
            .into(),
        "PASS fresh encryption randomness; Unicode, custom protected fields and encrypted history"
            .into(),
    ];
    let path = file.to_str().ok_or(Error::InvalidInput)?;
    // Only public synthetic constants are passed to this reference application's CLI.
    // Production code never uses this CLI adapter or exposes a CLI secret interface.
    let xml = Zeroizing::new(xc(&["export", "-q", path], &format!("{PASSWORD}\n"))?);
    for v in [NEW, OLD, "秘密 • مرحبا • Zürich", "demo@example.invalid"] {
        require(xml.windows(v.len()).any(|w| w == v.as_bytes()))?;
    }
    drop(xml);
    xc(
        &["edit", "-q", "-p", path, "SYNTHETIC-MAIL-ENTRY"],
        &format!("{PASSWORD}\nSYNTHETIC-XC-CHANGED\n"),
    )?;
    // KeePassXC 2.7 writes format 4.0 for this fixture; crypto parameters must remain identical.
    require(header::inspect(&fs::read(&file)?)? == profile)?;
    let session = Session::open(root.path(), key())?;
    require(&**session.field(id, "Password")? == "SYNTHETIC-XC-CHANGED")?;
    require(&**session.field(id, "Lumen:Token")? == "秘密 • مرحبا • Zürich")?;
    require(session.history_len(id)? >= history)?;
    checks.push("PASS KeePassXC reads all fixture fields/history, edits password, Rust reopens without field loss".into());
    let restored = directory()?;
    session.encrypted_backup(restored.path())?;
    drop(session);
    let restored_session = Session::open(restored.path(), key())?;
    require(&**restored_session.field(id, "Password")? == "SYNTHETIC-XC-CHANGED")?;
    drop(restored_session);
    require(matches!(
        Session::open(root.path(), Zeroizing::new("WRONG-SYNTHETIC-KEY".into())),
        Err(Error::UnlockFailed)
    ))?;
    no_canaries(root.path())?;
    no_canaries(restored.path())?;
    checks.push("PASS encrypted backup restored in fresh directory; wrong key rejected; no fixture canaries in on-disk store files".into());
    checks.push(format!(
        "Completed synthetic qualification in {} ms; PRODUCTION_READY=false",
        started.elapsed().as_millis()
    ));
    Ok(checks)
}

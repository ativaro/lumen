//! Private KDBX storage; exposed only through the bounded native laboratory broker.
use crate::{Error, Result, header};
use keepass::{
    Database, DatabaseKey,
    config::{CompressionConfig, DatabaseVersion, KdfConfig, OuterCipherConfig},
    db::{EntryId, History},
};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::{
        fd::AsRawFd,
        unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    },
    path::{Path, PathBuf},
};
use tempfile::NamedTempFile;
use zeroize::Zeroizing;

pub(crate) struct Session {
    db: Option<Database>,
    key: Option<DatabaseKey>,
    root: PathBuf,
    revision: Option<[u8; 32]>,
    _writer: File,
    _directory: File,
}

fn private_root(root: &Path) -> Result<()> {
    let meta = fs::symlink_metadata(root)?;
    // The store directory is dedicated, local, and owned by this process's uid.
    // SAFETY: geteuid has no pointer arguments and no side effects.
    if !meta.is_dir() || meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o077 != 0 {
        return Err(Error::InvalidInput);
    }
    Ok(())
}
// Pin the directory inode so ancestor replacement cannot redirect later writes.
fn anchor(root: &Path) -> Result<(File, PathBuf)> {
    let directory = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open(root)?;
    let anchored = PathBuf::from(format!("/proc/self/fd/{}/.", directory.as_raw_fd()));
    private_root(&anchored)?;
    Ok((directory, anchored))
}
pub(crate) const MAX_ENTRIES: usize = 10_000;
const MAX_HISTORY: usize = 1000;
fn all_entries(db: &Database) -> Result<Vec<EntryId>> {
    let mut groups = vec![db.root().id()];
    let mut entries = Vec::new();
    let mut visited = 0;
    while let Some(id) = groups.pop() {
        visited += 1;
        if visited > MAX_ENTRIES {
            return Err(Error::Limit);
        }
        let group = db.group(id).ok_or(Error::InvalidFile)?;
        if group.name.len() > 1024 {
            return Err(Error::Limit);
        }
        entries.extend(group.entries().map(|e| e.id()));
        if entries.len() > MAX_ENTRIES {
            return Err(Error::Limit);
        }
        groups.extend(group.groups().map(|g| g.id()));
    }
    entries.sort_by_key(|id| id.uuid().to_string());
    Ok(entries)
}
fn normalize_history(db: &mut Database) -> Result<()> {
    for id in all_entries(db)? {
        let mut entry = db.entry_mut(id).ok_or(Error::InvalidFile)?;
        if let Some(old) = entry.history.take() {
            let mut versions = old.get_entries().clone();
            versions.sort_by(|a, b| b.times.last_modification.cmp(&a.times.last_modification));
            let mut history = History::default();
            for e in versions.into_iter().rev() {
                history.add_entry(e);
            }
            entry.history = Some(history);
        }
    }
    Ok(())
}
fn supported(db: &Database) -> Result<()> {
    let mut total = 0usize;
    for id in all_entries(db)? {
        let entry = db.entry(id).ok_or(Error::InvalidFile)?;
        if entry.attachments().next().is_some() {
            return Err(Error::Unsupported);
        }
        let history = entry
            .history
            .as_ref()
            .map(|h| h.get_entries().as_slice())
            .unwrap_or(&[]);
        if history.len() > MAX_HISTORY {
            return Err(Error::Limit);
        }
        for fields in std::iter::once(&entry.fields).chain(history.iter().map(|e| &e.fields)) {
            if fields.len() > 64
                || fields.iter().any(|(k, v)| {
                    k.is_empty()
                        || k.len() > 128
                        || v.get().len() > 16384
                        || (["Title", "LumenCollection"].contains(&k.as_str())
                            && v.get().len() > 1024)
                })
            {
                return Err(Error::Limit);
            }
            total += fields
                .iter()
                .map(|(k, v)| k.len() + v.get().len())
                .sum::<usize>();
            if total > 16 * 1024 * 1024 {
                return Err(Error::Limit);
            }
        }
    }
    Ok(())
}
fn read_file(path: &Path) -> Result<Vec<u8>> {
    read_source(path, true)
}
fn read_source(path: &Path, private: bool) -> Result<Vec<u8>> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let meta = file.metadata()?;
    // SAFETY: geteuid has no pointer arguments.
    if !meta.is_file()
        || meta.nlink() != 1
        || meta.uid() != unsafe { libc::geteuid() }
        || (private && meta.mode() & 0o077 != 0)
    {
        return Err(Error::InvalidInput);
    }
    if meta.len() > header::MAX_FILE as u64 {
        return Err(Error::Limit);
    }
    let mut data = Vec::new();
    file.take(header::MAX_FILE as u64 + 1)
        .read_to_end(&mut data)?;
    if data.len() > header::MAX_FILE {
        return Err(Error::Limit);
    }
    Ok(data)
}
fn digest(data: &[u8]) -> [u8; 32] {
    Sha256::digest(data).into()
}
fn writer(root: &Path) -> Result<File> {
    private_root(root)?;
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(root.join("writer.lock"))?;
    let m = file.metadata()?;
    // SAFETY: geteuid has no pointer arguments.
    if !m.is_file()
        || m.nlink() != 1
        || m.mode() & 0o077 != 0
        || m.uid() != unsafe { libc::geteuid() }
    {
        return Err(Error::InvalidInput);
    }
    file.try_lock().map_err(|_| Error::Busy)?;
    Ok(file)
}
fn encode(db: &Database, key: &DatabaseKey) -> Result<Vec<u8>> {
    let mut encrypted = Vec::new();
    db.save(&mut encrypted, key.clone())
        .map_err(|_| Error::InvalidFile)?;
    header::inspect(&encrypted)?;
    Ok(encrypted)
}
fn atomic(root: &Path, name: &str, data: &[u8], new: bool) -> Result<()> {
    atomic_checked(root, name, data, new, |_| Ok(()))
}
fn atomic_checked(
    root: &Path,
    name: &str,
    data: &[u8],
    new: bool,
    mut stage: impl FnMut(u8) -> Result<()>,
) -> Result<()> {
    let mut file = NamedTempFile::new_in(root)?;
    file.as_file()
        .set_permissions(fs::Permissions::from_mode(0o600))?;
    stage(0)?;
    let split = data.len() / 2;
    file.write_all(&data[..split])?;
    stage(1)?;
    file.write_all(&data[split..])?;
    stage(2)?;
    file.as_file().sync_all()?;
    stage(3)?;
    if new {
        file.persist_noclobber(root.join(name))
            .map_err(|_| Error::Conflict)?;
    } else {
        file.persist(root.join(name)).map_err(|_| Error::Io)?;
    }
    // After rename, uncertainty must never be described as an unchanged file.
    stage(4).map_err(|_| Error::CommitUncertain)?;
    File::open(root)
        .and_then(|f| f.sync_all())
        .map_err(|_| Error::CommitUncertain)?;
    stage(5).map_err(|_| Error::CommitUncertain)?;
    Ok(())
}

/// Calibrate new laboratory files only. Existing/imported KDF settings are preserved.
fn calibrated_kdf() -> Result<KdfConfig> {
    let config = argon2::Config {
        mem_cost: 128 * 1024,
        time_cost: 3,
        lanes: 2,
        ..Default::default()
    };
    let started = std::time::Instant::now();
    let _probe = Zeroizing::new(
        argon2::hash_raw(
            b"public calibration input",
            b"public calibration salt",
            &config,
        )
        .map_err(|_| Error::Io)?,
    );
    let milliseconds = started.elapsed().as_millis().max(1);
    let iterations = (3 * 800 / milliseconds).clamp(3, 16) as u64;
    Ok(KdfConfig::Argon2id {
        iterations,
        memory: 128 * 1024 * 1024,
        parallelism: 2,
        version: argon2::Version::Version13,
    })
}
impl Session {
    pub(crate) fn create(root: &Path, password: Zeroizing<String>) -> Result<Self> {
        Self::create_with_kdf(root, password, None)
    }
    fn create_with_kdf(
        root: &Path,
        password: Zeroizing<String>,
        kdf: Option<KdfConfig>,
    ) -> Result<Self> {
        if password.len() < 14 || password.len() > 4096 {
            return Err(Error::InvalidInput);
        }
        let (directory, root) = anchor(root)?;
        let lock = writer(&root)?;
        if root.join("vault.kdbx").try_exists()? {
            return Err(Error::Conflict);
        }
        let mut db = Database::new();
        db.config.version = DatabaseVersion::KDB4(1);
        db.config.outer_cipher_config = OuterCipherConfig::AES256;
        db.config.compression_config = CompressionConfig::None;
        db.config.kdf_config = KdfConfig::Argon2id {
            iterations: 3,
            memory: 64 * 1024 * 1024,
            parallelism: 2,
            version: argon2::Version::Version13,
        };
        if let Some(config) = kdf {
            db.config.kdf_config = config;
        }
        db.root_mut().name = "Vault".into();
        let mut session = Self {
            db: Some(db),
            key: Some(DatabaseKey::new().with_password(&password)),
            root: root.to_owned(),
            revision: None,
            _writer: lock,
            _directory: directory,
        };
        session.save()?;
        Ok(session)
    }
    pub(crate) fn create_calibrated(root: &Path, password: Zeroizing<String>) -> Result<Self> {
        Self::create_with_kdf(root, password, Some(calibrated_kdf()?))
    }
    pub(crate) fn open(root: &Path, password: Zeroizing<String>) -> Result<Self> {
        if password.len() > 4096 {
            return Err(Error::InvalidInput);
        }
        let (directory, root) = anchor(root)?;
        let lock = writer(&root)?;
        let data = read_file(&root.join("vault.kdbx"))?;
        header::inspect(&data)?;
        let key = DatabaseKey::new().with_password(&password);
        let mut db = Database::parse(&data, key.clone()).map_err(|_| Error::UnlockFailed)?;
        supported(&db)?;
        normalize_history(&mut db)?;
        db.config.version = DatabaseVersion::KDB4(1);
        Ok(Self {
            db: Some(db),
            key: Some(key),
            root: root.to_owned(),
            revision: Some(digest(&data)),
            _writer: lock,
            _directory: directory,
        })
    }
    pub(crate) fn lock(&mut self) {
        self.db = None;
        self.key = None;
    }
    fn database(&self) -> Result<&Database> {
        self.db.as_ref().ok_or(Error::Locked)
    }
    pub(crate) fn add(&mut self, title: &str, secret: Zeroizing<String>) -> Result<EntryId> {
        if title.is_empty() || title.len() > 1024 || secret.len() > 16384 {
            return Err(Error::InvalidInput);
        }
        let db = self.db.as_mut().ok_or(Error::Locked)?;
        if all_entries(db)?.len() >= MAX_ENTRIES {
            return Err(Error::Limit);
        }
        let mut root = db.root_mut();
        let mut entry = root.add_entry();
        entry.set_protected("Title", title);
        entry.set_protected("Password", secret.to_string());
        Ok(entry.id())
    }
    pub(crate) fn set(&mut self, id: EntryId, field: &str, value: Zeroizing<String>) -> Result<()> {
        if field.is_empty()
            || field.len() > 128
            || value.len() > 16384
            || (["Title", "LumenCollection"].contains(&field) && value.len() > 1024)
        {
            return Err(Error::InvalidInput);
        }
        let db = self.db.as_mut().ok_or(Error::Locked)?;
        let mut entry = db.entry_mut(id).ok_or(Error::InvalidInput)?;
        if entry.fields.len() >= 64 && !entry.fields.contains_key(field) {
            return Err(Error::Limit);
        }
        if entry
            .history
            .as_ref()
            .is_some_and(|h| h.get_entries().len() >= MAX_HISTORY)
        {
            return Err(Error::Limit);
        }
        entry.edit_tracking(|e| e.set_protected(field, value.to_string()));
        Ok(())
    }
    pub(crate) fn field(&self, id: EntryId, key: &str) -> Result<Zeroizing<String>> {
        let db = self.database()?;
        let entry = db.entry(id).ok_or(Error::InvalidInput)?;
        if key == "LumenCollection"
            && entry.get(key).is_none()
            && entry.parent().id() != db.root().id()
        {
            return Ok(Zeroizing::new(entry.parent().name.clone()));
        }
        Ok(Zeroizing::new(
            entry.get(key).ok_or(Error::InvalidInput)?.to_owned(),
        ))
    }
    pub(crate) fn history_len(&self, id: EntryId) -> Result<usize> {
        Ok(self
            .database()?
            .entry(id)
            .ok_or(Error::InvalidInput)?
            .history
            .as_ref()
            .map_or(0, |h| h.get_entries().len()))
    }
    pub(crate) fn entries(&self) -> Result<Vec<EntryId>> {
        all_entries(self.database()?)
    }
    pub(crate) fn history(&self, id: EntryId) -> Result<Vec<String>> {
        let entry = self.database()?.entry(id).ok_or(Error::InvalidInput)?;
        Ok(entry
            .history
            .as_ref()
            .map(|h| {
                h.get_entries()
                    .iter()
                    .map(|e| {
                        e.times
                            .last_modification
                            .map(|t| t.to_string())
                            .unwrap_or_default()
                    })
                    .collect()
            })
            .unwrap_or_default())
    }
    pub(crate) fn history_fields(
        &self,
        id: EntryId,
        index: usize,
    ) -> Result<Vec<(String, Zeroizing<String>)>> {
        let entry = self.database()?.entry(id).ok_or(Error::InvalidInput)?;
        let version = entry
            .history
            .as_ref()
            .and_then(|h| h.get_entries().get(index))
            .ok_or(Error::InvalidInput)?;
        Ok(version
            .fields
            .iter()
            .map(|(k, v)| (k.clone(), Zeroizing::new(v.get().clone())))
            .collect())
    }
    pub(crate) fn prune_history(&mut self, id: EntryId, keep: usize) -> Result<()> {
        if keep > MAX_HISTORY {
            return Err(Error::Limit);
        }
        let mut entry = self
            .db
            .as_mut()
            .ok_or(Error::Locked)?
            .entry_mut(id)
            .ok_or(Error::InvalidInput)?;
        if let Some(old) = entry.history.take() {
            let mut versions = old.get_entries().clone();
            versions.sort_by(|a, b| b.times.last_modification.cmp(&a.times.last_modification));
            let mut history = History::default();
            for version in versions.iter().take(keep).rev() {
                history.add_entry(version.clone());
            }
            entry.history = Some(history);
        }
        Ok(())
    }
    pub(crate) fn restore_fields(&mut self, id: EntryId, index: usize) -> Result<()> {
        let mut entry = self
            .db
            .as_mut()
            .ok_or(Error::Locked)?
            .entry_mut(id)
            .ok_or(Error::InvalidInput)?;
        let history = entry.history.as_ref().ok_or(Error::InvalidInput)?;
        if history.get_entries().len() >= MAX_HISTORY {
            return Err(Error::Limit);
        }
        let fields = history
            .get_entries()
            .get(index)
            .ok_or(Error::InvalidInput)?
            .fields
            .clone();
        entry.edit_tracking(|e| {
            e.fields = fields;
            e.times.last_modification = Some(keepass::db::Times::now());
        });
        Ok(())
    }

    pub(crate) fn fields(&self, id: EntryId) -> Result<Vec<(String, Zeroizing<String>)>> {
        let entry = self.database()?.entry(id).ok_or(Error::InvalidInput)?;
        Ok(entry
            .fields
            .keys()
            .map(|key| {
                (
                    key.clone(),
                    Zeroizing::new(entry.get(key).unwrap_or("").to_owned()),
                )
            })
            .collect())
    }
    pub(crate) fn update(
        &mut self,
        id: EntryId,
        fields: &[(String, Zeroizing<String>)],
    ) -> Result<()> {
        if fields.len() > 32
            || fields.iter().any(|(k, v)| {
                k.is_empty()
                    || k.len() > 128
                    || v.len() > 16384
                    || (["Title", "LumenCollection"].contains(&k.as_str()) && v.len() > 1024)
            })
        {
            return Err(Error::Limit);
        }
        // Bound history and aggregate working data before serializer allocations.
        let db = self.db.as_mut().ok_or(Error::Locked)?;
        let mut entry = db.entry_mut(id).ok_or(Error::InvalidInput)?;
        let incoming: std::collections::HashSet<_> =
            fields.iter().map(|(k, _)| k.as_str()).collect();
        if incoming.len() != fields.len()
            || entry
                .fields
                .keys()
                .filter(|k| !incoming.contains(k.as_str()))
                .count()
                + fields.len()
                > 64
        {
            return Err(Error::Limit);
        }
        if entry
            .history
            .as_ref()
            .is_some_and(|h| h.get_entries().len() >= MAX_HISTORY)
        {
            return Err(Error::Limit);
        }
        if fields.iter().map(|(k, v)| k.len() + v.len()).sum::<usize>() > 32768 {
            return Err(Error::Limit);
        }
        entry.edit_tracking(|e| {
            for (key, value) in fields {
                e.set_protected(key, value.as_str());
            }
        });
        Ok(())
    }
    pub(crate) fn restore_file(
        root: &Path,
        source: &Path,
        password: Zeroizing<String>,
    ) -> Result<Self> {
        if password.is_empty() || password.len() > 4096 {
            return Err(Error::InvalidInput);
        }
        let (directory, root) = anchor(root)?;
        let lock = writer(&root)?;
        if root.join("vault.kdbx").try_exists()? {
            return Err(Error::Conflict);
        }
        let data = read_source(source, false)?;
        header::inspect(&data)?;
        let key = DatabaseKey::new().with_password(&password);
        let mut db = Database::parse(&data, key.clone()).map_err(|_| Error::UnlockFailed)?;
        supported(&db)?;
        normalize_history(&mut db)?;
        db.config.version = DatabaseVersion::KDB4(1);
        let mut session = Self {
            db: Some(db),
            key: Some(key),
            root: root.to_owned(),
            revision: None,
            _writer: lock,
            _directory: directory,
        };
        session.save()?;
        Ok(session)
    }
    pub(crate) fn save(&mut self) -> Result<()> {
        self.save_checked(|| Ok(()))
    }
    fn save_checked(&mut self, before_commit: impl FnOnce() -> Result<()>) -> Result<()> {
        supported(self.database()?)?;
        let data = encode(self.database()?, self.key.as_ref().ok_or(Error::Locked)?)?;
        // Tests inject a write failure / conflicting external write at this boundary.
        before_commit()?;
        if let Some(expected) = self.revision {
            let old = read_file(&self.root.join("vault.kdbx"))?;
            if digest(&old) != expected {
                return Err(Error::Conflict);
            }
            atomic(&self.root, "previous.kdbx", &old, false)?;
            // Recheck after making backup; lock coordinates Lumen writers, not other apps.
            if digest(&read_file(&self.root.join("vault.kdbx"))?) != expected {
                return Err(Error::Conflict);
            }
        }
        atomic(&self.root, "vault.kdbx", &data, self.revision.is_none())?;
        self.revision = Some(digest(&data));
        Ok(())
    }
    pub(crate) fn encrypted_backup(&self, destination: &Path) -> Result<()> {
        self.database()?;
        let (_directory, destination) = anchor(destination)?;
        let data = read_file(&self.root.join("vault.kdbx"))?;
        if Some(digest(&data)) != self.revision {
            return Err(Error::Conflict);
        }
        atomic(&destination, "vault.kdbx", &data, true)
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn exact_hmac_terminator_truncation_and_trailing_bytes_are_rejected() {
        use super::*;
        let root = tempfile::tempdir().unwrap();
        fs::set_permissions(root.path(), fs::Permissions::from_mode(0o700)).unwrap();
        let password = || Zeroizing::new("SYNTHETIC MASTER PASSWORD".into());
        drop(Session::create(root.path(), password()).unwrap());
        let path = root.path().join("vault.kdbx");
        let original = fs::read(&path).unwrap();
        fs::write(&path, &original[..original.len() - 36]).unwrap();
        assert!(
            Session::open(root.path(), password()).is_err(),
            "missing authenticated end block accepted"
        );
        let mut trailing = original;
        trailing.push(0);
        fs::write(&path, trailing).unwrap();
        assert!(
            Session::open(root.path(), password()).is_err(),
            "trailing bytes accepted"
        );
    }

    #[test]
    fn directory_replacement_cannot_redirect_writes() {
        use super::*;
        let parent = tempfile::tempdir().unwrap();
        let root = parent.path().join("active");
        std::fs::create_dir(&root).unwrap();
        std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700)).unwrap();
        let mut session =
            Session::create(&root, Zeroizing::new("synthetic master password".into())).unwrap();
        let pinned = parent.path().join("pinned");
        std::fs::rename(&root, &pinned).unwrap();
        std::fs::create_dir(&root).unwrap();
        session
            .add("synthetic", Zeroizing::new("synthetic".into()))
            .unwrap();
        session.save().unwrap();
        assert!(!root.join("vault.kdbx").exists());
        assert!(pinned.join("vault.kdbx").exists());
    }
    #[test]
    fn restore_validates_before_creating_and_preserves_original() {
        use super::*;
        let source = tempfile::tempdir().unwrap();
        let dest = tempfile::tempdir().unwrap();
        for dir in [source.path(), dest.path()] {
            std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700)).unwrap();
        }
        let password = || Zeroizing::new("synthetic master password".into());
        let mut session = Session::create(source.path(), password()).unwrap();
        let id = session
            .add("synthetic title", Zeroizing::new("synthetic secret".into()))
            .unwrap();
        session.save().unwrap();
        let file = source.path().join("vault.kdbx");
        assert!(Session::restore_file(dest.path(), &file, Zeroizing::new("wrong".into())).is_err());
        assert!(!dest.path().join("vault.kdbx").exists());
        let restored = Session::restore_file(dest.path(), &file, password()).unwrap();
        assert_eq!(
            restored.field(id, "Password").unwrap().as_str(),
            "synthetic secret"
        );
        drop(restored);
        assert!(Session::restore_file(dest.path(), &file, password()).is_err());
    }

    use super::*;
    fn directory() -> tempfile::TempDir {
        let d = tempfile::tempdir().unwrap();
        fs::set_permissions(d.path(), fs::Permissions::from_mode(0o700)).unwrap();
        d
    }
    fn password() -> Zeroizing<String> {
        Zeroizing::new("SYNTHETIC-TEST-PASSWORD".into())
    }
    #[test]
    fn save_unlock_history_restore_and_wrong_key() {
        let root = directory();
        let mut s = Session::create(root.path(), password()).unwrap();
        let id = s
            .add("Synthetic title", Zeroizing::new("SYNTHETIC-OLD".into()))
            .unwrap();
        s.set(id, "Password", Zeroizing::new("SYNTHETIC-NEW".into()))
            .unwrap();
        s.save().unwrap();
        assert_eq!(s.history_len(id).unwrap(), 1);
        s.lock();
        assert_eq!(s.save(), Err(Error::Locked));
        assert!(matches!(s.field(id, "Password"), Err(Error::Locked)));
        drop(s);
        assert!(matches!(
            Session::open(root.path(), Zeroizing::new("WRONG-PASSWORD".into())),
            Err(Error::UnlockFailed)
        ));
        let s = Session::open(root.path(), password()).unwrap();
        assert_eq!(&**s.field(id, "Password").unwrap(), "SYNTHETIC-NEW");
        let fresh = directory();
        s.encrypted_backup(fresh.path()).unwrap();
        drop(s);
        let restored = Session::open(fresh.path(), password()).unwrap();
        assert_eq!(restored.history_len(id).unwrap(), 1);
        assert_eq!(&**restored.field(id, "Password").unwrap(), "SYNTHETIC-NEW");
    }
    #[test]
    fn concurrent_writer_failed_save_and_conflict_preserve_original() {
        let root = directory();
        let mut s = Session::create(root.path(), password()).unwrap();
        assert!(matches!(
            Session::open(root.path(), password()),
            Err(Error::Busy)
        ));
        let original = fs::read(root.path().join("vault.kdbx")).unwrap();
        s.add("Not committed", Zeroizing::new("DEMO".into()))
            .unwrap();
        // Real rename failure: the backup destination is an existing directory.
        fs::create_dir(root.path().join("previous.kdbx")).unwrap();
        assert_eq!(s.save(), Err(Error::Io));
        fs::remove_dir(root.path().join("previous.kdbx")).unwrap();
        assert_eq!(fs::read(root.path().join("vault.kdbx")).unwrap(), original);
        assert_eq!(
            s.save_checked(|| {
                fs::write(root.path().join("vault.kdbx"), b"external writer")?;
                Ok(())
            }),
            Err(Error::Conflict)
        );
        assert_eq!(
            fs::read(root.path().join("vault.kdbx")).unwrap(),
            b"external writer"
        );
    }
    #[test]
    fn corruption_and_truncation_are_rejected() {
        let root = directory();
        let s = Session::create(root.path(), password()).unwrap();
        drop(s);
        let path = root.path().join("vault.kdbx");
        let original = fs::read(&path).unwrap();
        for index in [original.len() - 1, original.len() - 20] {
            let mut bad = original.clone();
            bad[index] ^= 0x40;
            fs::write(&path, bad).unwrap();
            assert!(matches!(
                Session::open(root.path(), password()),
                Err(Error::UnlockFailed)
            ));
        }
        for length in [0, 8, 12, 70, original.len() - 1] {
            fs::write(&path, &original[..length]).unwrap();
            assert!(Session::open(root.path(), password()).is_err());
        }
    }
    #[test]
    fn untrusted_kdf_headers_are_bounded_before_authentication() {
        let root = directory();
        drop(Session::create(root.path(), password()).unwrap());
        let data = fs::read(root.path().join("vault.kdbx")).unwrap();
        fn variant_value(data: &[u8], key: u8) -> usize {
            let marker = [5, 1, 0, 0, 0, key, 8, 0, 0, 0];
            data.windows(marker.len())
                .position(|w| w == marker)
                .unwrap()
                + marker.len()
        }
        for field in [b'M', b'I'] {
            let mut expensive = data.clone();
            let pos = variant_value(&data, field);
            expensive[pos..pos + 8].copy_from_slice(&u64::MAX.to_le_bytes());
            assert_eq!(header::inspect(&expensive), Err(Error::Limit));
        }
        let mut future = data.clone();
        future[8] = 2;
        assert_eq!(header::inspect(&future), Err(Error::Unsupported));
        let mut excessive = vec![0; header::MAX_FILE + 1];
        excessive[..12].copy_from_slice(&data[..12]);
        assert_eq!(header::inspect(&excessive), Err(Error::Limit));
        let mut unknown = data.clone();
        unknown[12] = 99;
        assert_eq!(header::inspect(&unknown), Err(Error::Unsupported));
    }
    #[test]
    fn symlinks_permissions_and_backup_overwrite_are_rejected() {
        use std::os::unix::fs::symlink;
        let root = directory();
        let outside = directory();
        let target = outside.path().join("unrelated");
        fs::write(&target, b"keep").unwrap();
        symlink(&target, root.path().join("vault.kdbx")).unwrap();
        assert!(Session::open(root.path(), password()).is_err());
        assert!(Session::create(root.path(), password()).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"keep");
        fs::remove_file(root.path().join("vault.kdbx")).unwrap();
        let mut s = Session::create(root.path(), password()).unwrap();
        let id = s.add("Title", Zeroizing::new("CANARY".into())).unwrap();
        s.save().unwrap();
        s.encrypted_backup(outside.path()).unwrap();
        assert_eq!(s.encrypted_backup(outside.path()), Err(Error::Conflict));
        assert_eq!(
            fs::metadata(root.path().join("vault.kdbx")).unwrap().mode() & 0o777,
            0o600
        );
        assert_eq!(
            fs::metadata(root.path().join("previous.kdbx"))
                .unwrap()
                .mode()
                & 0o777,
            0o600
        );
        s.lock();
        assert!(matches!(s.field(id, "Password"), Err(Error::Locked)));
        drop(s);
        fs::set_permissions(root.path(), fs::Permissions::from_mode(0o755)).unwrap();
        assert!(matches!(
            Session::open(root.path(), password()),
            Err(Error::InvalidInput)
        ));
    }

    #[test]
    fn more_than_100_entries_and_20_versions_remain_editable() {
        let root = directory();
        let mut s = Session::create(root.path(), password()).unwrap();
        let id = s.add("history", Zeroizing::new("old".into())).unwrap();
        for n in 0..30 {
            s.set(id, "Password", Zeroizing::new(format!("value-{n}")))
                .unwrap();
        }
        for n in 0..150 {
            s.add(&format!("entry-{n}"), Zeroizing::new("synthetic".into()))
                .unwrap();
        }
        s.save().unwrap();
        drop(s);
        let mut s = Session::open(root.path(), password()).unwrap();
        assert_eq!(s.entries().unwrap().len(), 151);
        assert_eq!(s.history_len(id).unwrap(), 30);
        s.restore_fields(id, 0).unwrap();
        assert_eq!(s.field(id, "Password").unwrap().as_str(), "value-28");
        s.prune_history(id, 5).unwrap();
        assert_eq!(s.history_len(id).unwrap(), 5);
        s.save().unwrap();
        drop(s);
        assert_eq!(
            Session::open(root.path(), password())
                .unwrap()
                .history_len(id)
                .unwrap(),
            5
        );
    }
    #[test]
    fn gzip_groups_custom_fields_and_history_roundtrip_without_pruning() {
        let source = directory();
        let dest = directory();
        let mut s = Session::create(source.path(), password()).unwrap();
        let db = s.db.as_mut().unwrap();
        db.config.compression_config = CompressionConfig::GZip;
        let mut root = db.root_mut();
        let mut group = root.add_group();
        group.name = "Servers & work".into();
        let mut e = group.add_entry();
        e.set_protected("Title", "nested");
        e.set_protected("Custom & field", "value");
        let id = e.id();
        for n in 0..25 {
            s.set(id, "Password", Zeroizing::new(format!("old-{n}")))
                .unwrap();
        }
        s.save().unwrap();
        drop(s);
        let path = source.path().join("vault.kdbx");
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        let imported = Session::restore_file(dest.path(), &path, password()).unwrap();
        assert_eq!(imported.entries().unwrap().len(), 1);
        assert_eq!(imported.history_len(id).unwrap(), 25);
        assert_eq!(
            imported.field(id, "Custom & field").unwrap().as_str(),
            "value"
        );
        assert_eq!(
            imported
                .database()
                .unwrap()
                .entry(id)
                .unwrap()
                .parent()
                .name,
            "Servers & work"
        );
    }
    #[test]
    fn every_atomic_failure_boundary_preserves_a_complete_authenticated_file() {
        let root = directory();
        let mut s = Session::create(root.path(), password()).unwrap();
        let old = fs::read(root.path().join("vault.kdbx")).unwrap();
        s.add("new", Zeroizing::new("synthetic".into())).unwrap();
        let new = encode(s.database().unwrap(), s.key.as_ref().unwrap()).unwrap();
        for name in ["vault.kdbx", "previous.kdbx"] {
            for failure in 0..6 {
                fs::write(root.path().join(name), &old).unwrap();
                let result = atomic_checked(root.path(), name, &new, false, |stage| {
                    if stage == failure {
                        Err(Error::Io)
                    } else {
                        Ok(())
                    }
                });
                assert_eq!(
                    result,
                    Err(if failure < 4 {
                        Error::Io
                    } else {
                        Error::CommitUncertain
                    })
                );
                let data = fs::read(root.path().join(name)).unwrap();
                assert_eq!(
                    data,
                    if failure < 4 {
                        old.clone()
                    } else {
                        new.clone()
                    }
                );
                Database::parse(&data, DatabaseKey::new().with_password(&password())).unwrap();
            }
        }
    }

    #[test]
    fn imported_oldest_first_history_keeps_newest_on_prune() {
        let root = directory();
        let mut s = Session::create(root.path(), password()).unwrap();
        let id = s.add("history", Zeroizing::new("current".into())).unwrap();
        let entry = s.database().unwrap().entry(id).unwrap();
        let mut old = (*entry).clone();
        let mut new = old.clone();
        old.times.last_modification = Some("2000-01-01T00:00:00".parse().unwrap());
        old.set_protected("Password", "oldest");
        new.times.last_modification = Some("2020-01-01T00:00:00".parse().unwrap());
        new.set_protected("Password", "newest");
        let mut history = History::default();
        history.add_entry(new);
        history.add_entry(old);
        s.db.as_mut().unwrap().entry_mut(id).unwrap().history = Some(history);
        s.save().unwrap();
        drop(s);
        let mut s = Session::open(root.path(), password()).unwrap();
        s.prune_history(id, 1).unwrap();
        let fields = s.history_fields(id, 0).unwrap();
        assert_eq!(
            fields
                .iter()
                .find(|(k, _)| k == "Password")
                .unwrap()
                .1
                .as_str(),
            "newest"
        );
    }

    #[test]
    #[ignore = "subprocess-only write crash worker"]
    fn atomic_crash_worker() {
        let root = std::env::var("LUMEN_TEST_CRASH_ROOT").unwrap();
        let root = Path::new(&root);
        let stage: u8 = std::env::var("LUMEN_TEST_CRASH_STAGE")
            .unwrap()
            .parse()
            .unwrap();
        let name = std::env::var("LUMEN_TEST_CRASH_FILE").unwrap();
        let mut s = Session::open(root, password()).unwrap();
        s.add("new after crash", Zeroizing::new("SYNTHETIC".into()))
            .unwrap();
        let data = encode(s.database().unwrap(), s.key.as_ref().unwrap()).unwrap();
        atomic_checked(root, &name, &data, false, |at| {
            if at == stage {
                unsafe {
                    libc::raise(libc::SIGKILL);
                }
            }
            Ok(())
        })
        .unwrap();
        panic!("crash stage was not reached");
    }
    #[test]
    fn killed_writer_never_exposes_partial_active_or_backup_file() {
        use std::process::{Command, Stdio};
        for name in ["vault.kdbx", "previous.kdbx"] {
            for stage in 0..6 {
                let root = directory();
                drop(Session::create(root.path(), password()).unwrap());
                let old = fs::read(root.path().join("vault.kdbx")).unwrap();
                fs::write(root.path().join("previous.kdbx"), &old).unwrap();
                fs::set_permissions(
                    root.path().join("previous.kdbx"),
                    fs::Permissions::from_mode(0o600),
                )
                .unwrap();
                let status = Command::new(std::env::current_exe().unwrap())
                    .args(["--ignored", "--exact", "store::tests::atomic_crash_worker"])
                    .env("LUMEN_TEST_CRASH_ROOT", root.path())
                    .env("LUMEN_TEST_CRASH_STAGE", stage.to_string())
                    .env("LUMEN_TEST_CRASH_FILE", name)
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status()
                    .unwrap();
                use std::os::unix::process::ExitStatusExt;
                assert_eq!(status.signal(), Some(libc::SIGKILL));
                let active = Session::open(root.path(), password()).unwrap();
                assert_eq!(
                    active.entries().unwrap().len(),
                    usize::from(name == "vault.kdbx" && stage >= 4)
                );
                drop(active);
                let backup = fs::read(root.path().join("previous.kdbx")).unwrap();
                Database::parse(&backup, DatabaseKey::new().with_password(&password())).unwrap();
                for path in fs::read_dir(root.path()).unwrap() {
                    let bytes = fs::read(path.unwrap().path()).unwrap();
                    assert!(!bytes.windows(9).any(|w| w == b"SYNTHETIC"));
                }
            }
        }
    }
}

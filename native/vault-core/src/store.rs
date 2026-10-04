//! Private implementation, deliberately not an IPC or user-facing secret API.
use crate::{Error, Result, header};
use keepass::{
    Database, DatabaseKey,
    config::{CompressionConfig, DatabaseVersion, KdfConfig, OuterCipherConfig},
    db::EntryId,
};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
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
fn read_file(path: &Path) -> Result<Vec<u8>> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let meta = file.metadata()?;
    // SAFETY: geteuid has no pointer arguments.
    if !meta.is_file()
        || meta.nlink() != 1
        || meta.uid() != unsafe { libc::geteuid() }
        || meta.mode() & 0o077 != 0
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
    if !m.is_file() || m.nlink() != 1 || m.mode() & 0o077 != 0 {
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
    let mut file = NamedTempFile::new_in(root)?;
    file.as_file()
        .set_permissions(fs::Permissions::from_mode(0o600))?;
    file.write_all(data)?;
    file.as_file().sync_all()?;
    if new {
        file.persist_noclobber(root.join(name))
            .map_err(|_| Error::Conflict)?;
    } else {
        file.persist(root.join(name)).map_err(|_| Error::Io)?;
    }
    File::open(root)?.sync_all()?;
    Ok(())
}

impl Session {
    pub(crate) fn create(root: &Path, password: Zeroizing<String>) -> Result<Self> {
        if password.len() < 14 || password.len() > 4096 {
            return Err(Error::InvalidInput);
        }
        let lock = writer(root)?;
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
        db.root_mut().name = "Vault".into();
        let mut session = Self {
            db: Some(db),
            key: Some(DatabaseKey::new().with_password(&password)),
            root: root.to_owned(),
            revision: None,
            _writer: lock,
        };
        session.save()?;
        Ok(session)
    }
    pub(crate) fn open(root: &Path, password: Zeroizing<String>) -> Result<Self> {
        if password.len() > 4096 {
            return Err(Error::InvalidInput);
        }
        let lock = writer(root)?;
        let data = read_file(&root.join("vault.kdbx"))?;
        header::inspect(&data)?;
        let key = DatabaseKey::new().with_password(&password);
        let db = Database::parse(&data, key.clone()).map_err(|_| Error::UnlockFailed)?;
        Ok(Self {
            db: Some(db),
            key: Some(key),
            root: root.to_owned(),
            revision: Some(digest(&data)),
            _writer: lock,
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
        if db.root().entries().count() >= 1000 {
            return Err(Error::Limit);
        }
        let mut root = db.root_mut();
        let mut entry = root.add_entry();
        entry.set_protected("Title", title);
        entry.set_protected("Password", secret.to_string());
        Ok(entry.id())
    }
    pub(crate) fn set(&mut self, id: EntryId, field: &str, value: Zeroizing<String>) -> Result<()> {
        if field.is_empty() || field.len() > 128 || value.len() > 16384 {
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
            .is_some_and(|h| h.get_entries().len() >= 20)
        {
            return Err(Error::Limit);
        }
        entry.edit_tracking(|e| e.set_protected(field, value.to_string()));
        Ok(())
    }
    pub(crate) fn field(&self, id: EntryId, key: &str) -> Result<Zeroizing<String>> {
        let entry = self.database()?.entry(id).ok_or(Error::InvalidInput)?;
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
    pub(crate) fn save(&mut self) -> Result<()> {
        self.save_checked(|| Ok(()))
    }
    fn save_checked(&mut self, before_commit: impl FnOnce() -> Result<()>) -> Result<()> {
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
        private_root(destination)?;
        let data = read_file(&self.root.join("vault.kdbx"))?;
        if Some(digest(&data)) != self.revision {
            return Err(Error::Conflict);
        }
        atomic(destination, "vault.kdbx", &data, true)
    }
}

#[cfg(test)]
mod tests {
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
}

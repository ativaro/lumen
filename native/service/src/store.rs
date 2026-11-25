//! The view's Store (`lumen.sqlite3`, table `settings`) as the turns use it: the service writes only
//! the conversations' rows (`persona/…`, `memory/session/…`), opens an existing Store and creates or
//! migrates nothing. A newer database version is refused, and a lock is waited for up to 15 s.
use crate::engine::Failure;
use crate::texts::Texts;
use rusqlite::OpenFlags;
use std::path::Path;
use std::time::Duration;

/// Why the Store was not used.
enum Refusal {
    Newer,
    Failed,
}

fn settings<T>(
    path: &Path,
    work: impl FnOnce(&rusqlite::Connection) -> rusqlite::Result<T>,
) -> Result<T, Refusal> {
    let failed = |_| Refusal::Failed;
    let db = rusqlite::Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_WRITE)
        .map_err(failed)?;
    db.busy_timeout(Duration::from_secs(15)).map_err(failed)?;
    let version: i64 = db
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(failed)?;
    if version > 3 {
        return Err(Refusal::Newer);
    }
    work(&db).map_err(failed)
}

/// [`settings`] off the engines' thread, so a locked Store holds up no other turn.
pub async fn store<T: Send + 'static>(
    path: &str,
    t: &Texts,
    work: impl FnOnce(&rusqlite::Connection) -> rusqlite::Result<T> + Send + 'static,
) -> Result<T, Failure> {
    let path = path.to_owned();
    match tokio::task::spawn_blocking(move || settings(Path::new(&path), work)).await {
        Ok(Ok(value)) => Ok(value),
        Ok(Err(Refusal::Newer)) => Err(Failure::new(
            t.tr("Diese Lumen-Datenbank benötigt eine neuere Version."),
        )),
        _ => Err(Failure::new(
            t.tr("Einstellungen konnten nicht gespeichert werden."),
        )),
    }
}

/// The rows in one transaction, each a key and the JSON text `json.dumps` wrote.
pub fn write(db: &rusqlite::Connection, rows: &[(String, String)]) -> rusqlite::Result<()> {
    let transaction = db.unchecked_transaction()?;
    for (key, value) in rows {
        transaction.execute(
            "INSERT OR REPLACE INTO settings VALUES (?1, ?2)",
            [key, value],
        )?;
    }
    transaction.commit()
}

/// The JSON text of one row, or `None` without it.
pub fn read(db: &rusqlite::Connection, key: &str) -> rusqlite::Result<Option<String>> {
    use rusqlite::OptionalExtension;
    db.query_row("SELECT value FROM settings WHERE key=?1", [key], |row| {
        row.get(0)
    })
    .optional()
}

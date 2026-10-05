//! Experimental, native-only IPC. The inherited pipe descriptors are the capability:
//! no socket name, service discovery, reconnect, MCP or agent endpoint exists.
use crate::{Error, Result, generate_password, store::Session};
use keepass::db::EntryId;
use std::{
    io::{Read, Write},
    path::Path,
    time::{Duration, Instant},
};
use zeroize::Zeroizing;
const MAX_FRAME: usize = 4 * 1024 * 1024;
const MAX_FIELDS: usize = 4096;
const IDLE: Duration = Duration::from_secs(300);
type Fields = Vec<Zeroizing<String>>;

fn read_exact_deadline(
    input: &mut impl Read,
    mut buffer: &mut [u8],
    deadline: Instant,
) -> Result<()> {
    while !buffer.is_empty() {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(Error::Locked);
        }
        let mut fd = libc::pollfd {
            fd: 0,
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: fd points to one initialized poll descriptor.
        if unsafe {
            libc::poll(
                &mut fd,
                1,
                remaining.as_millis().min(i32::MAX as u128) as i32,
            )
        } <= 0
        {
            return Err(Error::Locked);
        }
        let n = input.read(buffer)?;
        if n == 0 {
            return Err(Error::Io);
        }
        buffer = &mut buffer[n..];
    }
    Ok(())
}
fn decode(data: &[u8]) -> Result<Fields> {
    let mut cursor = 0;
    fn size(data: &[u8], cursor: &mut usize) -> Result<usize> {
        let bytes = data.get(*cursor..*cursor + 4).ok_or(Error::InvalidInput)?;
        *cursor += 4;
        Ok(u32::from_be_bytes(bytes.try_into().map_err(|_| Error::InvalidInput)?) as usize)
    }
    let count = size(data, &mut cursor)?;
    if count > MAX_FIELDS {
        return Err(Error::Limit);
    }
    let mut fields = Vec::with_capacity(count);
    for _ in 0..count {
        let length = size(data, &mut cursor)?;
        if length > 16384 {
            return Err(Error::Limit);
        }
        let bytes = data
            .get(cursor..cursor + length)
            .ok_or(Error::InvalidInput)?;
        fields.push(Zeroizing::new(
            std::str::from_utf8(bytes)
                .map_err(|_| Error::InvalidInput)?
                .to_owned(),
        ));
        cursor += length;
    }
    if cursor != data.len() {
        return Err(Error::InvalidInput);
    }
    Ok(fields)
}
fn encode(fields: &[Zeroizing<String>]) -> Result<Zeroizing<Vec<u8>>> {
    if fields.len() > MAX_FIELDS || fields.iter().any(|f| f.len() > 16384) {
        return Err(Error::Limit);
    }
    let size = 4 + fields.iter().map(|f| 4 + f.len()).sum::<usize>();
    if size > MAX_FRAME {
        return Err(Error::Limit);
    }
    let mut bytes = Zeroizing::new(Vec::with_capacity(size));
    bytes.extend_from_slice(&(fields.len() as u32).to_be_bytes());
    for field in fields {
        bytes.extend_from_slice(&(field.len() as u32).to_be_bytes());
        bytes.extend_from_slice(field.as_bytes());
    }
    if bytes.len() > MAX_FRAME {
        return Err(Error::Limit);
    }
    Ok(bytes)
}
fn text(value: &str) -> Zeroizing<String> {
    Zeroizing::new(value.to_owned())
}
fn entry(session: &Session, key: &str) -> Result<EntryId> {
    session
        .entries()?
        .into_iter()
        .find(|id| id.uuid().to_string() == key)
        .ok_or(Error::InvalidInput)
}
fn dispatch(session: &mut Option<Session>, root: &Path, request: Fields) -> Result<Fields> {
    let op = request.first().ok_or(Error::InvalidInput)?.as_str();
    let arg = |index: usize| {
        request
            .get(index)
            .map(|v| v.as_str())
            .ok_or(Error::InvalidInput)
    };
    match op {
        "create" | "open" if request.len() == 2 => {
            *session = None;
            *session = Some(if op == "create" {
                Session::create_calibrated(root, text(arg(1)?))?
            } else {
                Session::open(root, text(arg(1)?))?
            });
            Ok(vec![])
        }
        "restore" if request.len() == 3 => {
            *session = None;
            *session = Some(Session::restore_file(
                root,
                Path::new(arg(1)?),
                text(arg(2)?),
            )?);
            Ok(vec![])
        }
        "lock" if request.len() == 1 => {
            *session = None;
            Ok(vec![])
        }
        _ => {
            let session = session.as_mut().ok_or(Error::Locked)?;
            match op {
                "list" | "page" if request.len() == 1 || (op == "page" && request.len() == 2) => {
                    let ids = session.entries()?;
                    if op == "list" && ids.len() > 100 {
                        return Err(Error::Limit);
                    }
                    let start = if op == "page" {
                        arg(1)?.parse::<usize>().map_err(|_| Error::InvalidInput)?
                    } else {
                        0
                    };
                    if start > ids.len() {
                        return Err(Error::InvalidInput);
                    }
                    let end = if op == "page" {
                        (start + 64).min(ids.len())
                    } else {
                        ids.len().min(100)
                    };
                    let mut result = if op == "page" {
                        vec![text(&if end < ids.len() {
                            end.to_string()
                        } else {
                            String::new()
                        })]
                    } else {
                        vec![]
                    };
                    for id in ids[start..end].iter().copied() {
                        result.push(text(&id.uuid().to_string()));
                        for key in [
                            "Title",
                            "LumenType",
                            "LumenCollection",
                            "LumenFavorite",
                            "LumenTrash",
                        ] {
                            result.push(session.field(id, key).unwrap_or_else(|_| {
                                text(if key == "LumenType" { "login" } else { "" })
                            }));
                        }
                    }
                    Ok(result)
                }
                "connections" if request.len() == 2 => {
                    let ids = session.entries()?;
                    let start = arg(1)?.parse::<usize>().map_err(|_| Error::InvalidInput)?;
                    if start > ids.len() {
                        return Err(Error::InvalidInput);
                    }
                    let end = start.saturating_add(64).min(ids.len());
                    let mut result = vec![text(&if end < ids.len() {
                        end.to_string()
                    } else {
                        String::new()
                    })];
                    for id in ids[start..end].iter().copied() {
                        if session
                            .field(id, "LumenApiEnabled")
                            .is_ok_and(|v| v.as_str() == "1")
                            && session
                                .field(id, "LumenType")
                                .is_ok_and(|v| v.as_str() == "token")
                            && !session
                                .field(id, "LumenTrash")
                                .is_ok_and(|v| v.as_str() == "1")
                        {
                            result.push(text(&id.uuid().to_string()));
                        }
                    }
                    Ok(result)
                }
                "enable-api" if request.len() == 3 && ["0", "1"].contains(&arg(2)?) => {
                    let id = entry(session, arg(1)?)?;
                    if arg(2)? == "1"
                        && (!session
                            .field(id, "LumenType")
                            .is_ok_and(|v| v.as_str() == "token")
                            || session
                                .field(id, "LumenTrash")
                                .is_ok_and(|v| v.as_str() == "1"))
                    {
                        return Err(Error::InvalidInput);
                    }
                    session.set(id, "LumenApiEnabled", text(arg(2)?))?;
                    session.save()?;
                    Ok(vec![])
                }
                "summary" if request.len() == 2 => {
                    let id = entry(session, arg(1)?)?;
                    Ok(vec![
                        session.field(id, "URL").unwrap_or_else(|_| text("")),
                        session.field(id, "UserName").unwrap_or_else(|_| text("")),
                    ])
                }
                "get" if request.len() == 3 => {
                    let id = entry(session, arg(1)?)?;
                    Ok(vec![
                        session.field(id, arg(2)?).unwrap_or_else(|_| text("")),
                    ])
                }
                "edit" if request.len() == 2 => {
                    let mut result = vec![];
                    for (key, value) in session.fields(entry(session, arg(1)?)?)? {
                        result.push(text(&key));
                        result.push(value);
                    }
                    Ok(result)
                }
                "put" if request.len() >= 4 && request.len() % 2 == 0 => {
                    let fields: Vec<_> = request[2..]
                        .chunks_exact(2)
                        .map(|p| (p[0].to_string(), text(&p[1])))
                        .collect();
                    // Only the dedicated native availability action may change this flag.
                    if fields.iter().any(|(k, _)| k == "LumenApiEnabled") {
                        return Err(Error::InvalidInput);
                    }
                    if !fields
                        .iter()
                        .any(|(k, v)| k == "Title" && !v.trim().is_empty())
                    {
                        return Err(Error::InvalidInput);
                    }
                    let id = if arg(1)?.is_empty() {
                        if session.entries()?.len() >= crate::store::MAX_ENTRIES {
                            return Err(Error::Limit);
                        }
                        session.add("New", text(""))?
                    } else {
                        entry(session, arg(1)?)?
                    };
                    session.update(id, &fields)?;
                    session.save()?;
                    Ok(vec![text(&id.uuid().to_string())])
                }
                "trash" | "favorite" if request.len() == 3 && ["0", "1"].contains(&arg(2)?) => {
                    let id = entry(session, arg(1)?)?;
                    session.set(
                        id,
                        if op == "trash" {
                            "LumenTrash"
                        } else {
                            "LumenFavorite"
                        },
                        text(arg(2)?),
                    )?;
                    if op == "trash" && arg(2)? == "1" {
                        session.set(id, "LumenApiEnabled", text("0"))?;
                    }
                    session.save()?;
                    Ok(vec![])
                }
                "history-fields" if request.len() == 3 => {
                    let index = arg(2)?.parse::<usize>().map_err(|_| Error::InvalidInput)?;
                    let mut result = vec![];
                    for (k, v) in session.history_fields(entry(session, arg(1)?)?, index)? {
                        result.push(text(&k));
                        result.push(v);
                    }
                    Ok(result)
                }
                "history" if request.len() == 2 => Ok(session
                    .history(entry(session, arg(1)?)?)?
                    .iter()
                    .map(|v| text(v))
                    .collect()),
                "prune" | "restore-fields" if request.len() == 3 => {
                    let id = entry(session, arg(1)?)?;
                    let n = arg(2)?.parse::<usize>().map_err(|_| Error::InvalidInput)?;
                    if op == "prune" {
                        session.prune_history(id, n)?;
                    } else {
                        session.restore_fields(id, n)?;
                        session.set(id, "LumenApiEnabled", text("0"))?;
                    }
                    session.save()?;
                    Ok(vec![])
                }
                "generate" if request.len() == 1 => Ok(vec![generate_password()?]),
                "backup" if request.len() == 2 => {
                    session.encrypted_backup(Path::new(arg(1)?))?;
                    Ok(vec![])
                }
                _ => Err(Error::InvalidInput),
            }
        }
    }
}
/// Laboratory entry point, intentionally excluded from normal launchers and MCP.
pub fn serve(root: &Path) -> Result<()> {
    // Use unbuffered reads: a buffered stdin could retain bytes after poll
    // reports an empty descriptor, blocking the rest of an already received frame.
    use std::os::fd::FromRawFd;
    // SAFETY: dup returns a new owned descriptor; File closes only this duplicate.
    let fd = unsafe { libc::dup(0) };
    if fd < 0 {
        return Err(Error::Io);
    }
    let mut input = unsafe { std::fs::File::from_raw_fd(fd) };
    let mut output = std::io::stdout();
    let mut session = None;
    loop {
        let deadline = Instant::now() + IDLE;
        let mut length = [0; 4];
        read_exact_deadline(&mut input, &mut length, deadline)?;
        let length = u32::from_be_bytes(length) as usize;
        if !(4..=MAX_FRAME).contains(&length) {
            return Err(Error::Limit);
        }
        let mut data = crate::memory::LockedBytes::new(length)?;
        read_exact_deadline(&mut input, data.bytes_mut(), deadline)?;
        let request = decode(data.bytes())?;
        drop(data);
        let shutdown = request.len() == 1 && request[0].as_str() == "shutdown";
        if shutdown {
            drop(session);
            output.write_all(&[0, 0, 0, 10, 0, 0, 0, 1, 0, 0, 0, 2, b'o', b'k'])?;
            output.flush()?;
            return Ok(());
        }
        let response = match dispatch(&mut session, root, request) {
            Ok(mut fields) => {
                fields.insert(0, text("ok"));
                fields
            }
            Err(error) => {
                session = None;
                vec![text("error"), text(&format!("{error:?}"))]
            }
        };
        let bytes = encode(&response)?;
        output.write_all(&(bytes.len() as u32).to_be_bytes())?;
        output.write_all(&bytes)?;
        output.flush()?;
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn framing_is_bounded_and_exact() {
        for input in [vec![], vec![0, 0, 0, 0, 0], vec![0, 0, 16, 1]] {
            assert!(decode(&input).is_err());
        }
        let values = vec![text("مرحبا"), text("line\nsecond"), text("")];
        assert_eq!(decode(&encode(&values).unwrap()).unwrap(), values);
    }
    #[test]
    fn connection_permission_is_explicit_persistent_and_revocable() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
        let mut session = None;
        let mut call = |fields: &[&str]| {
            dispatch(
                &mut session,
                dir.path(),
                fields.iter().map(|v| text(v)).collect(),
            )
        };
        call(&["create", "SYNTHETIC MASTER LONG"]).unwrap();
        let id = call(&[
            "put",
            "",
            "Title",
            "Synthetic",
            "LumenType",
            "token",
            "Password",
            "SYNTHETIC SECRET",
        ])
        .unwrap()
        .remove(0);
        assert_eq!(call(&["connections", "0"]).unwrap().len(), 1);
        assert!(call(&["put", &id, "Title", "Synthetic", "LumenApiEnabled", "1"]).is_err());
        call(&["enable-api", &id, "1"]).unwrap();
        call(&["put", &id, "Title", "Renamed"]).unwrap();
        call(&["lock"]).unwrap();
        assert!(call(&["connections", "0"]).is_err());
        call(&["open", "SYNTHETIC MASTER LONG"]).unwrap();
        assert_eq!(
            call(&["connections", "0"]).unwrap(),
            vec![text(""), text(&id)]
        );
        call(&["enable-api", &id, "0"]).unwrap();
        assert_eq!(call(&["connections", "0"]).unwrap(), vec![text("")]);
        call(&["enable-api", &id, "1"]).unwrap();
        call(&["trash", &id, "1"]).unwrap();
        assert!(call(&["enable-api", &id, "1"]).is_err());
        call(&["trash", &id, "0"]).unwrap();
        assert_eq!(
            call(&["get", &id, "LumenApiEnabled"]).unwrap(),
            vec![text("0")]
        );
        call(&["enable-api", &id, "1"]).unwrap();
        call(&["restore-fields", &id, "0"]).unwrap();
        assert_eq!(
            call(&["get", &id, "LumenApiEnabled"]).unwrap(),
            vec![text("0")]
        );
        for file in std::fs::read_dir(dir.path()).unwrap() {
            let bytes = std::fs::read(file.unwrap().path()).unwrap();
            assert!(!bytes.windows(15).any(|w| w == b"LumenApiEnabled"));
        }
    }
    #[test]
    fn crud_lock_trash_restore_and_no_plaintext() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
        let mut session = None;
        let mut call = |fields: &[&str]| {
            dispatch(
                &mut session,
                dir.path(),
                fields.iter().map(|v| text(v)).collect(),
            )
        };
        assert!(call(&["generate"]).is_err());
        call(&["create", "SYNTHETIC TEST MASTER"]).unwrap();
        let id = call(&[
            "put",
            "",
            "Title",
            "SYNTHETIC TITLE",
            "Password",
            "SYNTHETIC SECRET",
            "LumenType",
            "login",
        ])
        .unwrap()
        .remove(0);
        call(&["favorite", &id, "1"]).unwrap();
        call(&["trash", &id, "1"]).unwrap();
        assert_eq!(call(&["list"]).unwrap()[5].as_str(), "1");
        call(&["trash", &id, "0"]).unwrap();
        call(&["lock"]).unwrap();
        assert!(call(&["get", &id, "Password"]).is_err());
        call(&["open", "SYNTHETIC TEST MASTER"]).unwrap();
        assert_eq!(
            call(&["get", &id, "Password"]).unwrap()[0].as_str(),
            "SYNTHETIC SECRET"
        );
        for path in std::fs::read_dir(dir.path()).unwrap() {
            let bytes = std::fs::read(path.unwrap().path()).unwrap();
            assert!(!bytes.windows(9).any(|w| w == b"SYNTHETIC"));
        }
    }
}

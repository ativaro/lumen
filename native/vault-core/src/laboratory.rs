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
    let mut bytes = Zeroizing::new(Vec::new());
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
                "list" if request.len() == 1 => {
                    let mut result = vec![];
                    for id in session.entries()? {
                        result.push(text(&id.uuid().to_string()));
                        for key in [
                            "Title",
                            "LumenType",
                            "LumenCollection",
                            "LumenFavorite",
                            "LumenTrash",
                        ] {
                            result.push(session.field(id, key).unwrap_or_else(|_| text("")));
                        }
                    }
                    Ok(result)
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
                    if !fields
                        .iter()
                        .any(|(k, v)| k == "Title" && !v.trim().is_empty())
                    {
                        return Err(Error::InvalidInput);
                    }
                    let id = if arg(1)?.is_empty() {
                        if session.entries()?.len() >= 100 {
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
        let mut data = Zeroizing::new(vec![0; length]);
        read_exact_deadline(&mut input, &mut data, deadline)?;
        let request = decode(&data)?;
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

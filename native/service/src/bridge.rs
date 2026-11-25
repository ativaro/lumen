//! The connection to the user's Lumen Server, the bridge: the desktop's one HTTPS client.
//!
//! `bridge.request` sends one request and answers with the server's status, headers and body;
//! `bridge.receive` streams one download into a new file; `bridge.trust` names the certificates a
//! connection trusts, for the TLS connections the Qt side still makes itself. The rules are those of
//! the earlier Python client: HTTPS only, the device token as bearer, no redirects (a 3xx is answered
//! like any other status), 4 MiB per answer, and every step (connect, TLS, answer, each read) within
//! the caller's timeout. A connection trusts its `ca_file` alone, or else the system's certificates
//! and the Lumen Server CAs the user trusted in the NSS store (`certutil`). As with OpenSSL, a server
//! certificate that is itself one of those certificates (a self-signed one named as `ca_file`) is
//! trusted as it is, after the checks OpenSSL made of it (`pinned`).

use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use base64::Engine as _;
use http_body_util::{BodyExt, Full};
use hyper::body::{Bytes, Incoming};
use rustls::pki_types::pem::PemObject;
use rustls::pki_types::{CertificateDer, ServerName};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncWriteExt};

/// The largest answer `bridge.request` reads, and the most of a refusal's body it keeps.
const LIMIT: usize = 4 * 1024 * 1024;
const BASE64: base64::engine::GeneralPurpose = base64::engine::general_purpose::STANDARD;

/// Why a request failed. The binding raises for each the exception the earlier client raised.
#[derive(Debug, PartialEq)]
pub enum Failure {
    /// No HTTPS address (a `ValueError`).
    Url(String),
    /// The CA file cannot be read or holds no certificate.
    Ca(String),
    /// No connection (name, refusal, network, connect or TLS timeout), with the system's error
    /// number where there is one.
    Connect(String, Option<i32>),
    /// The server's certificate is not trusted.
    Certificate(String),
    /// Another TLS failure.
    Tls(String),
    /// No answer, or no further part of it, within the timeout.
    Timeout,
    /// The server closed the connection before it answered.
    Closed,
    /// The server closed the connection in the middle of the answer.
    Incomplete,
    /// The answer is larger than allowed.
    TooLarge,
    /// The download file cannot be created or written.
    File(String, Option<i32>),
}

impl Failure {
    fn io(error: &std::io::Error) -> Failure {
        Failure::Connect(error.to_string(), error.raw_os_error())
    }

    fn file(error: &std::io::Error) -> Failure {
        Failure::File(error.to_string(), error.raw_os_error())
    }

    pub fn answer(&self) -> Value {
        let (kind, reason, errno) = match self {
            Failure::Url(r) => ("url", r.as_str(), None),
            Failure::Ca(r) => ("ca", r.as_str(), None),
            Failure::Connect(r, e) => ("connect", r.as_str(), *e),
            Failure::Certificate(r) => ("certificate", r.as_str(), None),
            Failure::Tls(r) => ("tls", r.as_str(), None),
            Failure::Timeout => ("timeout", "timed out", None),
            Failure::Closed => (
                "closed",
                "Remote end closed connection without response",
                None,
            ),
            Failure::Incomplete => ("incomplete", "connection closed during the answer", None),
            Failure::TooLarge => ("too_large", "answer too large", None),
            Failure::File(r, e) => ("file", r.as_str(), *e),
        };
        json!({"failure": kind, "reason": reason, "errno": errno})
    }
}

/// The paired server's address, the device token, the CA file the connection trusts, and the home
/// folder whose NSS store is asked without one.
pub struct Connection {
    pub server: String,
    pub token: String,
    pub ca_file: String,
    pub home: Option<std::path::PathBuf>,
}

impl Connection {
    fn of(request: &Value) -> Connection {
        let text = |key: &str| request[key].as_str().unwrap_or_default().to_owned();
        Connection {
            server: text("server"),
            token: text("token"),
            ca_file: text("ca_file"),
            home: std::env::var_os("HOME").map(Into::into),
        }
    }
}

/// The status line, headers and body of an answer.
pub struct Reply {
    pub status: u16,
    pub reason: String,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Reply {
    fn answer(&self) -> Value {
        json!({"status": self.status, "reason": self.reason, "headers": self.headers,
            "body": BASE64.encode(&self.body)})
    }
}

/// `certutil` (from NSS), `None` when it is missing, fails or takes longer than five seconds.
async fn certutil(arguments: &[&str]) -> Option<std::process::Output> {
    let mut command = tokio::process::Command::new("certutil");
    command
        .args(arguments)
        .stdin(std::process::Stdio::null())
        .kill_on_drop(true);
    tokio::time::timeout(Duration::from_secs(5), command.output())
        .await
        .ok()?
        .ok()
}

/// The nicknames of the trusted Lumen Server CAs in `certutil -L` output: `Lumen Server Local CA`,
/// twelve hex digits, then the trust flags `C,,`.
fn lumen_names(list: &str) -> Vec<&str> {
    list.lines()
        .filter_map(|line| {
            let rest = line.trim_end().strip_suffix("C,,")?;
            let name = rest.trim_end();
            let digits = name.strip_prefix("Lumen Server Local CA ")?;
            (name.len() < rest.len()
                && digits.len() == 12
                && digits
                    .bytes()
                    .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')))
            .then_some(name)
        })
        .collect()
}

/// The Lumen Server CAs the user trusted in the NSS store of `home`, also on this host.
async fn lumen_cas(home: &Path) -> Vec<CertificateDer<'static>> {
    let legacy = home.join(".pki/nssdb");
    let database = if legacy.exists() {
        legacy
    } else {
        home.join(".local/share/pki/nssdb")
    };
    if !database.join("cert9.db").exists() {
        return Vec::new();
    }
    let database = format!("sql:{}", database.display());
    let Some(list) = certutil(&["-d", &database, "-L"]).await else {
        return Vec::new();
    };
    let list = String::from_utf8_lossy(&list.stdout);
    let mut certificates = Vec::new();
    for name in lumen_names(&list) {
        if let Some(pem) = certutil(&["-d", &database, "-L", "-n", name, "-a"]).await
            && pem.status.success()
        {
            certificates.extend(CertificateDer::pem_slice_iter(&pem.stdout).flatten());
        }
    }
    certificates
}

/// What a connection trusts: the certificates of its CA file and `true` (only those), or the Lumen
/// Server CAs of the NSS store in `home` and `false` (besides the system's).
pub async fn trusted(
    ca_file: &str,
    home: Option<&Path>,
) -> Result<(Vec<CertificateDer<'static>>, bool), Failure> {
    if ca_file.is_empty() {
        return Ok((
            match home {
                Some(home) => lumen_cas(home).await,
                None => Vec::new(),
            },
            false,
        ));
    }
    let certificates = CertificateDer::pem_file_iter(ca_file)
        .and_then(Iterator::collect::<Result<Vec<_>, _>>)
        .map_err(|e| Failure::Ca(format!("{ca_file}: {e}")))?;
    if certificates.is_empty() {
        return Err(Failure::Ca(format!("{ca_file}: no certificate")));
    }
    Ok((certificates, true))
}

fn pem(certificates: &[CertificateDer<'_>]) -> String {
    let mut text = String::new();
    for certificate in certificates {
        text.push_str("-----BEGIN CERTIFICATE-----\n");
        let encoded = BASE64.encode(certificate.as_ref());
        for line in encoded.as_bytes().chunks(64) {
            text.push_str(&String::from_utf8_lossy(line));
            text.push('\n');
        }
        text.push_str("-----END CERTIFICATE-----\n");
    }
    text
}

async fn tls(connection: &Connection) -> Result<tokio_rustls::TlsConnector, Failure> {
    let (extra, only) = trusted(&connection.ca_file, connection.home.as_deref()).await?;
    let mut roots = rustls::RootCertStore::empty();
    if !only {
        // ponytail: the system's certificates and certutil are read for every request, as the
        // Python client did; cache them by file times if the latency shows.
        roots.add_parsable_certificates(rustls_native_certs::load_native_certs().certs);
    }
    roots.add_parsable_certificates(extra.iter().cloned());
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let verifier = Verifier {
        // No root at all: only a pinned certificate can pass.
        webpki: rustls::client::WebPkiServerVerifier::builder_with_provider(
            Arc::new(roots),
            provider.clone(),
        )
        .build()
        .ok(),
        pinned: extra,
        algorithms: provider.signature_verification_algorithms,
    };
    let mut config = rustls::ClientConfig::builder_with_provider(provider)
        .with_safe_default_protocol_versions()
        .map_err(|e| Failure::Tls(e.to_string()))?
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(verifier))
        .with_no_client_auth();
    config.alpn_protocols = vec![b"http/1.1".to_vec()];
    Ok(tokio_rustls::TlsConnector::from(Arc::new(config)))
}

/// What webpki trusts with the roots, and also a server whose own certificate is one of `pinned`
/// byte for byte: OpenSSL (Python's ssl before) trusted a certificate named in the CA file itself,
/// a self-signed one included, also when it is marked as a CA.
#[derive(Debug)]
struct Verifier {
    webpki: Option<Arc<rustls::client::WebPkiServerVerifier>>,
    pinned: Vec<CertificateDer<'static>>,
    algorithms: rustls::crypto::WebPkiSupportedAlgorithms,
}

impl rustls::client::danger::ServerCertVerifier for Verifier {
    fn verify_server_cert(
        &self,
        end_entity: &CertificateDer<'_>,
        intermediates: &[CertificateDer<'_>],
        server_name: &ServerName<'_>,
        ocsp_response: &[u8],
        now: rustls::pki_types::UnixTime,
    ) -> Result<rustls::client::danger::ServerCertVerified, rustls::Error> {
        if self.pinned.iter().any(|p| p == end_entity) {
            pinned(end_entity, server_name, now.as_secs())?;
            return Ok(rustls::client::danger::ServerCertVerified::assertion());
        }
        match &self.webpki {
            Some(webpki) => webpki.verify_server_cert(
                end_entity,
                intermediates,
                server_name,
                ocsp_response,
                now,
            ),
            None => Err(rustls::CertificateError::UnknownIssuer.into()),
        }
    }

    fn verify_tls12_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &rustls::DigitallySignedStruct,
    ) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        rustls::crypto::verify_tls12_signature(message, cert, dss, &self.algorithms)
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &rustls::DigitallySignedStruct,
    ) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        rustls::crypto::verify_tls13_signature(message, cert, dss, &self.algorithms)
    }

    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> {
        self.algorithms.supported_schemes()
    }
}

/// What OpenSSL checked of a server certificate it trusted as it is: the validity period, the name
/// (an alternative name, or for a host name without alternative host names the common name) and,
/// where the certificate limits them, a server's key usage and extended key usage. The handshake
/// itself proves the server holds the certificate's key.
fn pinned(
    certificate: &CertificateDer<'_>,
    name: &ServerName<'_>,
    now: u64,
) -> Result<(), rustls::Error> {
    use rustls::CertificateError;
    let parsed = rustls::server::ParsedCertificate::try_from(certificate)?;
    let facts = x509::facts(certificate).ok_or(CertificateError::BadEncoding)?;
    let now = i64::try_from(now).unwrap_or(i64::MAX);
    if now < facts.not_before {
        return Err(CertificateError::NotValidYet.into());
    }
    if now > facts.not_after {
        return Err(CertificateError::Expired.into());
    }
    if !facts.server_usage {
        return Err(CertificateError::InvalidPurpose.into());
    }
    if rustls::client::verify_server_name(&parsed, name).is_ok() {
        return Ok(());
    }
    match name {
        ServerName::DnsName(host) if !facts.host_names => {
            let host = host.as_ref().as_bytes();
            if facts
                .common_names
                .iter()
                .any(|cn| x509::host_matches(cn, host))
            {
                return Ok(());
            }
            Err(CertificateError::NotValidForName.into())
        }
        _ => Err(CertificateError::NotValidForName.into()),
    }
}

/// The few fields of an X.509 certificate (DER) `pinned` checks.
mod x509 {
    pub struct Facts<'a> {
        pub not_before: i64,
        pub not_after: i64,
        /// Whether an alternative name is a host name (only then the common name is not used).
        pub host_names: bool,
        pub common_names: Vec<&'a [u8]>,
        /// Key usage (if any) allows a TLS server key, extended key usage (if any) a TLS server.
        pub server_usage: bool,
    }

    /// One DER element: its tag, its contents and what follows it.
    fn element(input: &[u8]) -> Option<(u8, &[u8], &[u8])> {
        let (&tag, rest) = input.split_first()?;
        let (&first, rest) = rest.split_first()?;
        let (length, rest) = if first < 0x80 {
            (usize::from(first), rest)
        } else {
            let n = usize::from(first & 0x7f);
            if n == 0 || n > 4 || rest.len() < n {
                return None;
            }
            let length = rest[..n].iter().fold(0, |l, b| l << 8 | usize::from(*b));
            (length, &rest[n..])
        };
        (rest.len() >= length).then(|| (tag, &rest[..length], &rest[length..]))
    }

    /// The elements of a SEQUENCE or SET's contents.
    fn elements(mut input: &[u8]) -> impl Iterator<Item = (u8, &[u8])> {
        std::iter::from_fn(move || {
            let (tag, content, rest) = element(input)?;
            input = rest;
            Some((tag, content))
        })
    }

    /// UTCTime or GeneralizedTime (`Z`, whole seconds, as DER requires) in seconds since 1970.
    pub fn time(tag: u8, text: &[u8]) -> Option<i64> {
        let digits = |range: std::ops::Range<usize>| -> Option<i64> {
            let part = text.get(range)?;
            part.iter()
                .all(u8::is_ascii_digit)
                .then(|| part.iter().fold(0, |n, d| n * 10 + i64::from(d - b'0')))
        };
        let (year, at) = match (tag, text.len()) {
            (0x17, 13) => (
                digits(0..2).map(|y| if y < 50 { 2000 + y } else { 1900 + y })?,
                2,
            ),
            (0x18, 15) => (digits(0..4)?, 4),
            _ => return None,
        };
        if text.last() != Some(&b'Z') {
            return None;
        }
        let (month, day) = (digits(at..at + 2)?, digits(at + 2..at + 4)?);
        let (hour, minute, second) = (
            digits(at + 4..at + 6)?,
            digits(at + 6..at + 8)?,
            digits(at + 8..at + 10)?,
        );
        if !(1..=12).contains(&month)
            || !(1..=31).contains(&day)
            || hour > 23
            || minute > 59
            || second > 60
        {
            return None;
        }
        // Days from the civil date (Howard Hinnant's algorithm).
        let y = if month <= 2 { year - 1 } else { year };
        let era = y.div_euclid(400);
        let yoe = y - era * 400;
        let doy = (153 * (month + if month > 2 { -3 } else { 9 }) + 2) / 5 + day - 1;
        let days = era * 146_097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719_468;
        Some(days * 86_400 + hour * 3_600 + minute * 60 + second)
    }

    const COMMON_NAME: &[u8] = &[0x55, 0x04, 0x03];
    const ALTERNATIVE_NAME: &[u8] = &[0x55, 0x1d, 0x11];
    const KEY_USAGE: &[u8] = &[0x55, 0x1d, 0x0f];
    const EXTENDED_KEY_USAGE: &[u8] = &[0x55, 0x1d, 0x25];
    /// serverAuth and the two server-gated-crypto purposes OpenSSL also counts for a TLS server.
    const SERVER_PURPOSES: [&[u8]; 3] = [
        &[0x2b, 0x06, 0x01, 0x05, 0x05, 0x07, 0x03, 0x01],
        &[0x60, 0x86, 0x48, 0x01, 0x86, 0xf8, 0x42, 0x04, 0x01],
        &[0x2b, 0x06, 0x01, 0x04, 0x01, 0x82, 0x37, 0x0a, 0x03, 0x03],
    ];

    pub fn facts(der: &[u8]) -> Option<Facts<'_>> {
        let (_, certificate, _) = element(der)?;
        let (_, tbs, _) = element(certificate)?;
        let mut fields = elements(tbs).peekable();
        fields.next_if(|(tag, _)| *tag == 0xa0); // version
        let _serial = fields.next()?;
        let _signature = fields.next()?;
        let _issuer = fields.next()?;
        let (_, validity) = fields.next()?;
        let mut times = elements(validity);
        let (not_before, not_after) = (times.next()?, times.next()?);
        let (_, subject) = fields.next()?;
        let mut facts = Facts {
            not_before: time(not_before.0, not_before.1)?,
            not_after: time(not_after.0, not_after.1)?,
            host_names: false,
            common_names: Vec::new(),
            server_usage: true,
        };
        for (_, set) in elements(subject) {
            for (_, pair) in elements(set) {
                let mut pair = elements(pair);
                if let (Some((0x06, COMMON_NAME)), Some((_, text))) = (pair.next(), pair.next()) {
                    facts.common_names.push(text);
                }
            }
        }
        let Some((_, extensions)) = fields.find(|(tag, _)| *tag == 0xa3) else {
            return Some(facts);
        };
        let (_, extensions, _) = element(extensions)?;
        for (_, extension) in elements(extensions) {
            let mut parts = elements(extension);
            let (_, oid) = parts.next()?;
            let (_, value) = parts.find(|(tag, _)| *tag == 0x04)?;
            let (_, value, _) = element(value)?;
            match oid {
                ALTERNATIVE_NAME => facts.host_names = elements(value).any(|(tag, _)| tag == 0x82),
                // digitalSignature, keyEncipherment or keyAgreement.
                KEY_USAGE => facts.server_usage &= value.get(1).is_some_and(|b| b & 0xa8 != 0),
                EXTENDED_KEY_USAGE => {
                    facts.server_usage &= elements(value).any(|(_, p)| SERVER_PURPOSES.contains(&p))
                }
                _ => {}
            }
        }
        Some(facts)
    }

    /// OpenSSL's rule for a common name: equal ignoring ASCII case, or `*.` and a rest with a dot
    /// that matches all but the host's first label.
    pub fn host_matches(pattern: &[u8], host: &[u8]) -> bool {
        if pattern.eq_ignore_ascii_case(host) {
            return true;
        }
        let Some(rest) = pattern.strip_prefix(b"*.") else {
            return false;
        };
        let Some(dot) = host.iter().position(|b| *b == b'.') else {
            return false;
        };
        dot > 0 && rest.contains(&b'.') && rest.eq_ignore_ascii_case(&host[dot + 1..])
    }
}

/// Ends the connection task with the answer it served.
struct Task(tokio::task::JoinHandle<()>);

impl Drop for Task {
    fn drop(&mut self) {
        self.0.abort();
    }
}

async fn within<T>(t: Duration, step: impl Future<Output = T>) -> Result<T, Failure> {
    tokio::time::timeout(t, step)
        .await
        .map_err(|_| Failure::Timeout)
}

/// Sends `body` (POST, JSON) or nothing (GET) to `server` + `path` and returns the answer's head
/// with its body still to read.
async fn open(
    connection: &Connection,
    path: &str,
    body: Option<Vec<u8>>,
    t: Duration,
) -> Result<(hyper::Response<Incoming>, Task), Failure> {
    let address = format!("{}{path}", connection.server);
    let invalid = || Failure::Url(format!("invalid HTTPS address: {address}"));
    let uri: hyper::Uri = address.parse().map_err(|_| invalid())?;
    let authority = uri.authority().filter(|a| {
        uri.scheme_str() == Some("https") && !a.as_str().contains('@') && !a.host().is_empty()
    });
    let authority = authority.ok_or_else(invalid)?.clone();
    let host = authority
        .host()
        .trim_start_matches('[')
        .trim_end_matches(']');
    let name = ServerName::try_from(host.to_owned()).map_err(|_| invalid())?;
    let connector = tls(connection).await?;
    let tcp = tokio::net::TcpStream::connect((host, authority.port_u16().unwrap_or(443)));
    let tcp = within(t, tcp)
        .await
        .map_err(|_| Failure::Connect("timed out".into(), Some(libc::ETIMEDOUT)))?
        .map_err(|e| Failure::io(&e))?;
    let stream = within(t, connector.connect(name, tcp))
        .await
        .map_err(|_| Failure::Connect("timed out".into(), Some(libc::ETIMEDOUT)))?
        .map_err(
            |e| match e.get_ref().and_then(|e| e.downcast_ref::<rustls::Error>()) {
                Some(rustls::Error::InvalidCertificate(reason)) => {
                    Failure::Certificate(format!("certificate verify failed: {reason:?}"))
                }
                Some(other) => Failure::Tls(other.to_string()),
                None => Failure::io(&e),
            },
        )?;
    let (mut sender, conn) =
        hyper::client::conn::http1::handshake(hyper_util::rt::TokioIo::new(stream))
            .await
            .map_err(|_| Failure::Closed)?;
    let task = Task(tokio::spawn(async move {
        let _ = conn.await;
    }));
    let target = uri.path_and_query().map_or("/", |p| p.as_str());
    let mut request = hyper::Request::builder()
        .method(if body.is_some() { "POST" } else { "GET" })
        .uri(target)
        .header("host", authority.as_str())
        .header("user-agent", "Lumen-Desktop")
        .header("connection", "close");
    if !connection.token.is_empty() {
        request = request.header("authorization", format!("Bearer {}", connection.token));
    }
    if body.is_some() {
        request = request.header("content-type", "application/json");
    }
    let request = request
        .body(Full::new(Bytes::from(body.unwrap_or_default())))
        .map_err(|_| invalid())?;
    let response = within(t, sender.send_request(request))
        .await?
        .map_err(|_| Failure::Closed)?;
    Ok((response, task))
}

/// The next part of a body, within the timeout; `None` at its end.
async fn chunk(body: &mut Incoming, t: Duration) -> Result<Option<Bytes>, Failure> {
    loop {
        match within(t, body.frame()).await? {
            None => return Ok(None),
            Some(Err(_)) => return Err(Failure::Incomplete),
            Some(Ok(frame)) => {
                if let Ok(data) = frame.into_data() {
                    return Ok(Some(data));
                }
            }
        }
    }
}

fn head(response: &hyper::Response<Incoming>) -> Reply {
    let status = response.status();
    Reply {
        status: status.as_u16(),
        reason: status.canonical_reason().unwrap_or_default().to_owned(),
        headers: response
            .headers()
            .iter()
            .map(|(k, v)| {
                let value = String::from_utf8_lossy(v.as_bytes()).into_owned();
                (k.as_str().to_owned(), value)
            })
            .collect(),
        body: Vec::new(),
    }
}

/// Reads up to `limit` bytes: more is `TooLarge`, or, with `cut`, ends the body there.
async fn collect(
    response: hyper::Response<Incoming>,
    limit: usize,
    cut: bool,
    t: Duration,
) -> Result<Reply, Failure> {
    let mut reply = head(&response);
    let mut body = response.into_body();
    while let Some(data) = chunk(&mut body, t).await? {
        if reply.body.len() + data.len() > limit {
            if !cut {
                return Err(Failure::TooLarge);
            }
            let remaining = limit - reply.body.len();
            reply.body.extend_from_slice(&data[..remaining]);
            break;
        }
        reply.body.extend_from_slice(&data);
    }
    Ok(reply)
}

/// One request: its answer up to 4 MiB, every step within `t` and the whole within four times `t`.
pub async fn request(
    connection: &Connection,
    path: &str,
    body: Option<Vec<u8>>,
    t: Duration,
) -> Result<Reply, Failure> {
    within(t * 4, async {
        let (response, _task) = open(connection, path, body, t).await?;
        let success = response.status().is_success();
        collect(response, LIMIT, !success, t).await
    })
    .await?
}

/// A file this download created, removed unless it is complete.
struct Partial<'a> {
    path: &'a Path,
    kept: bool,
}

impl Drop for Partial<'_> {
    fn drop(&mut self) {
        if !self.kept {
            let _ = std::fs::remove_file(self.path);
        }
    }
}

async fn line(write: &mut tokio::net::unix::OwnedWriteHalf, mut value: Value) -> bool {
    value["v"] = json!(crate::VERSION);
    let mut text = value.to_string();
    text.push('\n');
    write.write_all(text.as_bytes()).await.is_ok()
}

/// Downloads `path` into the new file `file` (0600) up to `limit` bytes, sending `{"received": n}`
/// after every part. Answers the status, size and SHA-256 of a complete download (synced to disk);
/// a refusal, a failure or a client that leaves removes the file. `None` when the client has left.
async fn download(
    connection: &Connection,
    path: &str,
    file: &Path,
    limit: u64,
    t: Duration,
    write: &mut tokio::net::unix::OwnedWriteHalf,
) -> Option<Value> {
    let (response, _task) = match open(connection, path, None, t).await {
        Ok(opened) => opened,
        Err(failure) => return Some(failure.answer()),
    };
    if !response.status().is_success() {
        return Some(match collect(response, LIMIT, true, t).await {
            Ok(reply) => reply.answer(),
            Err(failure) => failure.answer(),
        });
    }
    let mut answer = head(&response).answer();
    let mut body = response.into_body();
    let created = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(file);
    let mut out = match created {
        Ok(out) => tokio::fs::File::from_std(out),
        Err(error) => return Some(Failure::file(&error).answer()),
    };
    let mut partial = Partial {
        path: file,
        kept: false,
    };
    let (mut count, mut digest) = (0u64, Sha256::new());
    loop {
        let data = match chunk(&mut body, t).await {
            Ok(Some(data)) => data,
            Ok(None) => break,
            Err(failure) => return Some(failure.answer()),
        };
        count += data.len() as u64;
        if count > limit {
            return Some(Failure::TooLarge.answer());
        }
        digest.update(&data);
        if let Err(error) = out.write_all(&data).await {
            return Some(Failure::file(&error).answer());
        }
        if !line(write, json!({"received": count})).await {
            return None;
        }
    }
    if let Err(error) = async {
        out.flush().await?;
        out.sync_all().await
    }
    .await
    {
        return Some(Failure::file(&error).answer());
    }
    partial.kept = true;
    answer["size"] = json!(count);
    answer["sha256"] = json!(
        digest
            .finalize()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>()
    );
    Some(answer)
}

fn seconds(request: &Value) -> Duration {
    Duration::from_secs_f64(
        request["timeout"]
            .as_f64()
            .unwrap_or(15.0)
            .clamp(0.01, 600.0),
    )
}

/// Answers one `bridge.*` request on its connection.
pub async fn serve(stream: tokio::net::UnixStream, request: Value) {
    let connection = Connection::of(&request);
    let (mut read, mut write) = stream.into_split();
    let answer = match request["op"].as_str().unwrap_or_default() {
        "bridge.request" => {
            let body = request["body"].as_str().map(|b| b.as_bytes().to_vec());
            let path = request["path"].as_str().unwrap_or_default();
            match self::request(&connection, path, body, seconds(&request)).await {
                Ok(reply) => reply.answer(),
                Err(failure) => failure.answer(),
            }
        }
        "bridge.trust" => match trusted(&connection.ca_file, connection.home.as_deref()).await {
            Ok((certificates, only)) => json!({"pem": pem(&certificates), "only": only}),
            Err(failure) => failure.answer(),
        },
        "bridge.receive" => {
            let (Some(path), Some(file), Some(limit)) = (
                request["path"].as_str(),
                request["file"].as_str().filter(|f| f.starts_with('/')),
                request["limit"].as_u64(),
            ) else {
                let _ = line(&mut write, json!({"error": "invalid_request"})).await;
                return;
            };
            let file = Path::new(file);
            let t = seconds(&request);
            // The client keeps its side open; closing it cancels the download.
            let mut buffer = [0u8; 64];
            let left = async { while matches!(read.read(&mut buffer).await, Ok(n) if n > 0) {} };
            tokio::select! {
                answer = download(&connection, path, file, limit, t, &mut write) => match answer {
                    Some(answer) => answer,
                    None => return,
                },
                () = left => return,
            }
        }
        _ => json!({"error": "unknown_op"}),
    };
    let _ = line(&mut write, answer).await;
    let _ = write.shutdown().await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::process::Command;
    use tokio::io::AsyncBufReadExt;

    #[test]
    fn only_trusted_lumen_cas_are_named() {
        let list = "\nCertificate Nickname                                         Trust Attributes\n\
                    \n\
                    Lumen Server Local CA 0123456789ab                           C,,  \n\
                    Lumen Server Local CA 0123456789AB                           C,,\n\
                    Lumen Server Local CA 0123456789abc                          C,,\n\
                    Lumen Server Local CA fedcba987654                           CT,C,C\n\
                    Other CA 0123456789ab                                        C,,\n\
                    Lumen Server Local CA 00000000000aC,,\n";
        assert_eq!(lumen_names(list), ["Lumen Server Local CA 0123456789ab"]);
    }

    /// A throwaway CA, a certificate for 127.0.0.1 it signed, a second CA that signed nothing, and
    /// self-signed server certificates: `self` and `stranger` (marked as CAs, as `openssl req -x509`
    /// makes them, for 127.0.0.1), `named` (only the common name `localhost`) and `client` (for
    /// clients only).
    struct Certificates {
        folder: PathBuf,
    }

    impl Certificates {
        fn new(name: &str) -> Certificates {
            let folder = std::env::temp_dir().join(format!(
                "lumen-bridge-{name}-{}-{:?}",
                std::process::id(),
                std::thread::current().id()
            ));
            let _ = std::fs::remove_dir_all(&folder);
            std::fs::create_dir(&folder).unwrap();
            std::fs::write(
                folder.join("ca.cnf"),
                "[req]\ndistinguished_name=dn\n[dn]\n[ca]\nbasicConstraints=critical,CA:TRUE\n\
                 keyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n",
            )
            .unwrap();
            std::fs::write(
                folder.join("leaf.ext"),
                "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n\
                 extendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\n",
            )
            .unwrap();
            let openssl = |arguments: &str| {
                let done = Command::new("openssl")
                    .args(arguments.split(' '))
                    .current_dir(&folder)
                    .output()
                    .unwrap();
                assert!(
                    done.status.success(),
                    "{}",
                    String::from_utf8_lossy(&done.stderr)
                );
            };
            let key = "-newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -config ca.cnf";
            for (name, subject) in [("ca", "Test"), ("other", "Other")] {
                openssl(&format!(
                    "req -x509 {key} -days 1 -subj /CN={subject} -extensions ca -keyout {name}.key -out {name}.pem"
                ));
            }
            openssl(&format!(
                "req -new {key} -subj /CN=127.0.0.1 -keyout leaf.key -out leaf.csr"
            ));
            openssl(
                "x509 -req -days 1 -in leaf.csr -CA ca.pem -CAkey ca.key -set_serial 2 -extfile leaf.ext -out leaf.pem",
            );
            let ip = "-addext subjectAltName=IP:127.0.0.1";
            for (name, extensions) in [
                (
                    "self",
                    format!("-addext basicConstraints=critical,CA:TRUE {ip}"),
                ),
                (
                    "stranger",
                    format!("-addext basicConstraints=critical,CA:TRUE {ip}"),
                ),
                ("named", String::new()),
                (
                    "client",
                    format!("{ip} -addext extendedKeyUsage=clientAuth"),
                ),
            ] {
                let subject = if name == "named" { "localhost" } else { name };
                openssl(
                    format!("req -x509 {key} -days 1 -subj /CN={subject} {extensions} -keyout {name}.key -out {name}.pem")
                        .split_whitespace()
                        .collect::<Vec<_>>()
                        .join(" ")
                        .as_str(),
                );
            }
            Certificates { folder }
        }

        fn path(&self, name: &str) -> String {
            self.folder.join(name).display().to_string()
        }
    }

    impl Drop for Certificates {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.folder);
        }
    }

    /// What the fake server does with one request: the raw bytes it answers with, and whether it
    /// waits before closing.
    #[derive(Clone)]
    struct Script {
        answer: Vec<u8>,
        hold: bool,
    }

    fn reply(status: &str, headers: &str, body: &[u8]) -> Vec<u8> {
        let mut raw = format!(
            "HTTP/1.1 {status}\r\ncontent-length: {}\r\n{headers}\r\n",
            body.len()
        )
        .into_bytes();
        raw.extend_from_slice(body);
        raw
    }

    /// A local HTTPS server with the leaf certificate; returns its address and the request heads
    /// (and bodies) it received.
    async fn fake(
        certificates: &Certificates,
        script: Script,
    ) -> (String, tokio::sync::mpsc::UnboundedReceiver<String>) {
        presenting(certificates, "leaf", script).await
    }

    /// The fake server with the certificate `name`.
    async fn presenting(
        certificates: &Certificates,
        name: &str,
        script: Script,
    ) -> (String, tokio::sync::mpsc::UnboundedReceiver<String>) {
        let chain = CertificateDer::pem_file_iter(certificates.path(&format!("{name}.pem")))
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        let key = rustls::pki_types::PrivateKeyDer::from_pem_file(
            certificates.path(&format!("{name}.key")),
        )
        .unwrap();
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        let config = rustls::ServerConfig::builder_with_provider(provider)
            .with_safe_default_protocol_versions()
            .unwrap()
            .with_no_client_auth()
            .with_single_cert(chain, key)
            .unwrap();
        let acceptor = tokio_rustls::TlsAcceptor::from(Arc::new(config));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = format!("https://{}", listener.local_addr().unwrap());
        let (seen, heads) = tokio::sync::mpsc::unbounded_channel();
        tokio::spawn(async move {
            while let Ok((tcp, _)) = listener.accept().await {
                let (acceptor, script, seen) = (acceptor.clone(), script.clone(), seen.clone());
                tokio::spawn(async move {
                    let Ok(stream) = acceptor.accept(tcp).await else {
                        let _ = seen.send("handshake failed".into());
                        return;
                    };
                    let mut stream = tokio::io::BufReader::new(stream);
                    let mut head = String::new();
                    loop {
                        let mut text = String::new();
                        if stream.read_line(&mut text).await.unwrap_or(0) == 0 || text == "\r\n" {
                            break;
                        }
                        head.push_str(&text);
                    }
                    let length = head
                        .lines()
                        .find_map(|l| l.strip_prefix("content-length: "))
                        .map_or(0, |n| n.trim().parse().unwrap());
                    let mut body = vec![0; length];
                    stream.read_exact(&mut body).await.unwrap();
                    head.push_str(&String::from_utf8_lossy(&body));
                    let _ = seen.send(head);
                    let _ = stream.get_mut().write_all(&script.answer).await;
                    let _ = stream.get_mut().flush().await;
                    if script.hold {
                        tokio::time::sleep(Duration::from_secs(5)).await;
                    }
                    let _ = stream.get_mut().shutdown().await;
                });
            }
        });
        (address, heads)
    }

    /// A connection whose NSS store lookup finds nothing: the home folder is the certificates'.
    fn connection(server: &str, ca_file: String) -> Connection {
        Connection {
            server: server.to_owned(),
            token: "fixture-token".into(),
            home: Some(std::env::temp_dir().join("lumen-bridge-no-home")),
            ca_file,
        }
    }

    const T: Duration = Duration::from_secs(3);

    #[tokio::test]
    async fn a_request_carries_the_device_token_and_returns_the_answer() {
        let certificates = Certificates::new("success");
        let script = Script {
            answer: reply(
                "200 OK",
                "content-type: application/json\r\n",
                b"{\"ok\":true}",
            ),
            hold: false,
        };
        let (server, mut heads) = fake(&certificates, script).await;
        let c = connection(&server, certificates.path("ca.pem"));
        let reply = request(&c, "/bridge/me?x=1", Some(b"{\"a\": 1}".to_vec()), T)
            .await
            .unwrap();
        assert_eq!((reply.status, reply.body), (200, b"{\"ok\":true}".to_vec()));
        assert!(
            reply
                .headers
                .contains(&("content-type".into(), "application/json".into()))
        );
        let head = heads.recv().await.unwrap();
        assert!(
            head.starts_with("POST /bridge/me?x=1 HTTP/1.1\r\n"),
            "{head}"
        );
        for expected in [
            "authorization: Bearer fixture-token\r\n",
            "content-type: application/json\r\n",
            "content-length: 8\r\n",
            &format!("host: {}\r\n", server.trim_start_matches("https://")),
        ] {
            assert!(head.contains(expected), "{expected} missing in {head}");
        }
        assert!(head.ends_with("\r\n{\"a\": 1}"));
        // A GET without a body has neither a type nor a length, and no token means no bearer.
        let anonymous = Connection {
            token: String::new(),
            ..connection(&server, certificates.path("ca.pem"))
        };
        request(&anonymous, "/bridge/pairings/preview", None, T)
            .await
            .unwrap();
        let head = heads.recv().await.unwrap();
        assert!(head.starts_with("GET /bridge/pairings/preview HTTP/1.1\r\n"));
        for absent in ["authorization", "content-type", "content-length"] {
            assert!(!head.contains(absent), "{absent} in {head}");
        }
    }

    #[tokio::test]
    async fn refusals_and_redirects_are_answered_as_they_are() {
        let certificates = Certificates::new("refusal");
        for (status, headers) in [
            ("403 Forbidden", "x-detail: no\r\n"),
            ("302 Found", "location: https://127.0.0.1:1/elsewhere\r\n"),
        ] {
            let script = Script {
                answer: reply(status, headers, b"{\"detail\":\"refused\"}"),
                hold: false,
            };
            let (server, mut heads) = fake(&certificates, script).await;
            let c = connection(&server, certificates.path("ca.pem"));
            let reply = request(&c, "/bridge/me", None, T).await.unwrap();
            assert_eq!(reply.status.to_string(), status[..3]);
            assert_eq!(reply.body, b"{\"detail\":\"refused\"}");
            let (name, value) = headers.trim_end().split_once(": ").unwrap();
            assert!(reply.headers.contains(&(name.into(), value.into())));
            heads.recv().await.unwrap();
            // A redirect is not followed: the server saw one request only.
            assert!(heads.try_recv().is_err());
        }
    }

    #[tokio::test]
    async fn an_answer_above_four_mib_and_a_silent_server_fail() {
        let certificates = Certificates::new("limits");
        let large = vec![b' '; LIMIT + 1];
        let script = Script {
            answer: reply("200 OK", "", &large),
            hold: false,
        };
        let (server, _heads) = fake(&certificates, script).await;
        let c = connection(&server, certificates.path("ca.pem"));
        assert_eq!(
            request(&c, "/x", None, T).await.err(),
            Some(Failure::TooLarge)
        );
        // Exactly 4 MiB pass.
        let script = Script {
            answer: reply("200 OK", "", &large[1..]),
            hold: false,
        };
        let (server, _heads) = fake(&certificates, script).await;
        let c = connection(&server, certificates.path("ca.pem"));
        assert_eq!(request(&c, "/x", None, T).await.unwrap().body.len(), LIMIT);
        // A server that never answers runs into the timeout.
        let script = Script {
            answer: Vec::new(),
            hold: true,
        };
        let (server, _heads) = fake(&certificates, script).await;
        let c = connection(&server, certificates.path("ca.pem"));
        let started = std::time::Instant::now();
        let short = Duration::from_millis(300);
        assert_eq!(
            request(&c, "/x", None, short).await.err(),
            Some(Failure::Timeout)
        );
        assert!(started.elapsed() < Duration::from_secs(2));
        // A server that closes before answering.
        let script = Script {
            answer: Vec::new(),
            hold: false,
        };
        let (server, _heads) = fake(&certificates, script).await;
        let c = connection(&server, certificates.path("ca.pem"));
        assert_eq!(
            request(&c, "/x", None, T).await.err(),
            Some(Failure::Closed)
        );
    }

    #[tokio::test]
    async fn only_the_named_ca_is_trusted() {
        let certificates = Certificates::new("trust");
        let script = Script {
            answer: reply("200 OK", "", b"{}"),
            hold: false,
        };
        let (server, _heads) = fake(&certificates, script).await;
        let other = connection(&server, certificates.path("other.pem"));
        assert!(matches!(
            request(&other, "/x", None, T).await,
            Err(Failure::Certificate(_))
        ));
        // Without a CA file the system's certificates do not know the throwaway CA either.
        let system = connection(&server, String::new());
        assert!(matches!(
            request(&system, "/x", None, T).await,
            Err(Failure::Certificate(_))
        ));
        let missing = connection(&server, certificates.path("missing.pem"));
        assert!(matches!(
            request(&missing, "/x", None, T).await,
            Err(Failure::Ca(_))
        ));
        let (pem_text, only) = trusted(&certificates.path("ca.pem"), None).await.unwrap();
        assert!(only);
        assert_eq!(
            pem(&pem_text),
            pem(&CertificateDer::pem_file_iter(certificates.path("ca.pem"))
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap())
        );
        for address in ["http://127.0.0.1:1", "https://", "https://user@127.0.0.1"] {
            assert!(matches!(
                request(&connection(address, String::new()), "/x", None, T).await,
                Err(Failure::Url(_))
            ));
        }
        let refused = connection("https://127.0.0.1:1", certificates.path("ca.pem"));
        assert_eq!(
            request(&refused, "/x", None, T).await.err(),
            Some(Failure::Connect(
                std::io::Error::from_raw_os_error(libc::ECONNREFUSED).to_string(),
                Some(libc::ECONNREFUSED)
            ))
        );
    }

    fn certificate(certificates: &Certificates, name: &str) -> CertificateDer<'static> {
        CertificateDer::from_pem_file(certificates.path(&format!("{name}.pem"))).unwrap()
    }

    #[tokio::test]
    async fn a_self_signed_server_certificate_named_as_ca_file_is_trusted_as_it_is() {
        let certificates = Certificates::new("pinned");
        let answer = || Script {
            answer: reply("200 OK", "", b"{}"),
            hold: false,
        };
        let (server, _heads) = presenting(&certificates, "self", answer()).await;
        let pinned = connection(&server, certificates.path("self.pem"));
        assert_eq!(request(&pinned, "/x", None, T).await.unwrap().status, 200);
        // Another self-signed certificate, the CA of a signed one or no CA file: refused.
        for ca_file in ["stranger.pem", "ca.pem", ""] {
            let path = if ca_file.is_empty() {
                String::new()
            } else {
                certificates.path(ca_file)
            };
            assert!(
                matches!(
                    request(&connection(&server, path), "/x", None, T).await,
                    Err(Failure::Certificate(_))
                ),
                "{ca_file}"
            );
        }
        // A file with several certificates pins each of them; CA and signed certificate still pass.
        let both = certificates.folder.join("both.pem");
        let text = std::fs::read_to_string(certificates.path("ca.pem")).unwrap()
            + &std::fs::read_to_string(certificates.path("self.pem")).unwrap();
        std::fs::write(&both, text).unwrap();
        let both = connection(&server, both.display().to_string());
        assert_eq!(request(&both, "/x", None, T).await.unwrap().status, 200);
        let (signed, _heads) = fake(&certificates, answer()).await;
        let signed = connection(&signed, certificates.path("ca.pem"));
        assert_eq!(request(&signed, "/x", None, T).await.unwrap().status, 200);
        // The name still counts: the certificate is for 127.0.0.1, not for localhost.
        let port = server.rsplit(':').next().unwrap();
        let other_name = connection(
            &format!("https://localhost:{port}"),
            certificates.path("self.pem"),
        );
        assert!(matches!(
            request(&other_name, "/x", None, T).await,
            Err(Failure::Certificate(reason)) if reason.contains("NotValidForName")
        ));
        // Without alternative host names the common name counts for a host name, never for an address.
        let (named, _heads) = presenting(&certificates, "named", answer()).await;
        let port = named.rsplit(':').next().unwrap();
        let host = connection(
            &format!("https://localhost:{port}"),
            certificates.path("named.pem"),
        );
        assert_eq!(request(&host, "/x", None, T).await.unwrap().status, 200);
        let address = connection(&named, certificates.path("named.pem"));
        assert!(matches!(
            request(&address, "/x", None, T).await,
            Err(Failure::Certificate(_))
        ));
        let (client, _heads) = presenting(&certificates, "client", answer()).await;
        let purpose = connection(&client, certificates.path("client.pem"));
        assert!(matches!(
            request(&purpose, "/x", None, T).await,
            Err(Failure::Certificate(reason)) if reason.contains("InvalidPurpose")
        ));
    }

    #[test]
    fn a_pinned_certificate_is_checked_as_openssl_checked_it() {
        use rustls::CertificateError::{Expired, InvalidPurpose, NotValidForName, NotValidYet};
        let certificates = Certificates::new("checks");
        let ip = ServerName::try_from("127.0.0.1").unwrap();
        let host = |name: &'static str| ServerName::try_from(name).unwrap();
        let own = certificate(&certificates, "self");
        let facts = x509::facts(&own).unwrap();
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        assert!(facts.not_before <= now as i64 && now as i64 <= facts.not_after);
        assert!(facts.not_after - facts.not_before >= 86_399);
        assert!(!facts.host_names && facts.common_names == [b"self".as_slice()]);
        assert_eq!(pinned(&own, &ip, now), Ok(()));
        let invalid = |e| Err(rustls::Error::InvalidCertificate(e));
        assert_eq!(
            pinned(&own, &ip, facts.not_after as u64 + 1),
            invalid(Expired)
        );
        assert_eq!(
            pinned(&own, &ip, facts.not_before as u64 - 1),
            invalid(NotValidYet)
        );
        assert_eq!(pinned(&own, &host("self"), now), Ok(()));
        assert_eq!(pinned(&own, &host("other"), now), invalid(NotValidForName));
        let named = certificate(&certificates, "named");
        assert_eq!(pinned(&named, &host("LOCALHOST"), now), Ok(()));
        assert_eq!(pinned(&named, &ip, now), invalid(NotValidForName));
        let client = certificate(&certificates, "client");
        assert_eq!(pinned(&client, &ip, now), invalid(InvalidPurpose));
        // The CA's key usage (certificates only) is not a server's.
        let ca = certificate(&certificates, "ca");
        assert_eq!(pinned(&ca, &host("Test"), now), invalid(InvalidPurpose));
        for (pattern, name, matches) in [
            ("*.example.com", "a.example.com", true),
            ("*.EXAMPLE.com", "a.example.COM", true),
            ("*.example.com", "a.b.example.com", false),
            ("*.example.com", "example.com", false),
            ("*.localhost", "a.localhost", false),
            ("a*.example.com", "ab.example.com", false),
        ] {
            assert_eq!(
                x509::host_matches(pattern.as_bytes(), name.as_bytes()),
                matches,
                "{pattern} {name}"
            );
        }
        // UTCTime before 2050, GeneralizedTime after; anything else is no time.
        assert_eq!(x509::time(0x17, b"700101000000Z"), Some(0));
        assert_eq!(x509::time(0x17, b"491231235959Z"), Some(2_524_607_999));
        assert_eq!(x509::time(0x18, b"20500101000000Z"), Some(2_524_608_000));
        assert_eq!(x509::time(0x17, b"700101000000+0100"), None);
        assert_eq!(x509::time(0x18, b"2050010100000Z"), None);
    }

    /// Runs `bridge.receive` over a socket pair; returns the lines the client read.
    async fn receive(request: Value, leave_after: Option<usize>) -> Vec<Value> {
        let (client, service) = tokio::net::UnixStream::pair().unwrap();
        let work = tokio::spawn(serve(service, request));
        let mut lines = tokio::io::BufReader::new(client).lines();
        let mut seen = Vec::new();
        while let Ok(Some(text)) = lines.next_line().await {
            seen.push(serde_json::from_str(&text).unwrap());
            if Some(seen.len()) == leave_after {
                break;
            }
        }
        drop(lines);
        work.await.unwrap();
        seen
    }

    #[tokio::test]
    async fn a_download_streams_into_a_new_file_and_leaves_nothing_on_failure() {
        let certificates = Certificates::new("download");
        let payload: Vec<u8> = (0..300_000u32).map(|i| (i % 251) as u8).collect();
        let script = Script {
            answer: reply("200 OK", "", &payload),
            hold: false,
        };
        let (server, mut heads) = fake(&certificates, script).await;
        let file = certificates.folder.join(".receive-1");
        let request = json!({"op": "bridge.receive", "server": server, "token": "fixture-token",
            "ca_file": certificates.path("ca.pem"), "path": "/bridge/artifacts/f",
            "file": file.display().to_string(), "limit": payload.len(), "timeout": 3});
        let lines = receive(request.clone(), None).await;
        let end = lines.last().unwrap();
        assert_eq!(end["status"], 200);
        assert_eq!(end["size"], payload.len());
        assert_eq!(
            end["sha256"],
            Sha256::digest(&payload)
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect::<String>()
        );
        assert!(
            lines[..lines.len() - 1]
                .iter()
                .all(|l| l["received"].is_u64())
        );
        assert_eq!(std::fs::read(&file).unwrap(), payload);
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            std::fs::metadata(&file).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert!(
            heads
                .recv()
                .await
                .unwrap()
                .contains("authorization: Bearer fixture-token")
        );
        // An existing file is never written over.
        let lines = receive(request.clone(), None).await;
        assert_eq!(lines.last().unwrap()["failure"], "file");
        assert_eq!(std::fs::read(&file).unwrap(), payload);
        std::fs::remove_file(&file).unwrap();
        // More than allowed, a cut answer, a refusal or a client that leaves: no file remains.
        let mut over = request.clone();
        over["limit"] = json!(payload.len() - 1);
        assert_eq!(
            receive(over, None).await.last().unwrap()["failure"],
            "too_large"
        );
        assert!(!file.exists());
        let mut cut = reply("200 OK", "", &payload);
        cut.truncate(cut.len() - 1000);
        let (cut_server, _h) = fake(
            &certificates,
            Script {
                answer: cut,
                hold: false,
            },
        )
        .await;
        let mut incomplete = request.clone();
        incomplete["server"] = json!(cut_server);
        assert_eq!(
            receive(incomplete, None).await.last().unwrap()["failure"],
            "incomplete"
        );
        assert!(!file.exists());
        let refusal = reply("404 Not Found", "", b"{\"detail\":\"gone\"}");
        let (gone, _h) = fake(
            &certificates,
            Script {
                answer: refusal,
                hold: false,
            },
        )
        .await;
        let mut missing = request.clone();
        missing["server"] = json!(gone);
        let end = receive(missing, None).await;
        assert_eq!(end.last().unwrap()["status"], 404);
        assert!(!file.exists());
        let mut held = reply("200 OK", "", &payload);
        held.truncate(held.len() - 1000);
        let (slow, _h) = fake(
            &certificates,
            Script {
                answer: held,
                hold: true,
            },
        )
        .await;
        let mut left = request.clone();
        left["server"] = json!(slow);
        let lines = receive(left, Some(1)).await;
        assert!(lines[0]["received"].is_u64());
        assert!(!file.exists());
    }
}

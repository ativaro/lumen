//! Lumen's control of the OpenCode engine (`opencode serve`): the loopback client, the reaping of
//! an engine process and the reply loop of one prompt. One implementation for the desktop's
//! `lumen-service` and the server, which keeps a pinned copy in `rust/shared/engine`.
//!
//! Profiles, sandboxing, session policy and tenancy stay with each side; this crate only speaks to
//! an engine that is already running.
use percent_encoding::{NON_ALPHANUMERIC, utf8_percent_encode};
pub use reqwest::{Method, StatusCode};
use serde_json::Value;
use std::time::Duration;
use tokio::process::Child;

pub mod frames;
pub mod python;
mod response;
pub use response::{Observer, provider_error, response};

/// The OpenCode release this code is written against.
pub const VERSION: &str = "1.18.34";
/// The compaction plugin both sides load into every engine.
pub const PLUGIN: &str = include_str!("lumen-continuity.mjs");

/// A failure with its HTTP status and a fixed user-facing text; never an engine or provider body.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Error(pub StatusCode, pub &'static str);

pub const FAILED: Error = Error(
    StatusCode::BAD_GATEWAY,
    "Modelle nicht verfügbar. Engine und Anbindung in Einstellungen prüfen.",
);
pub const TIMEOUT: Error = Error(
    StatusCode::GATEWAY_TIMEOUT,
    "Zeitlimit für die Modellantwort erreicht.",
);

/// The connection to one running engine: loopback only, Basic authentication, no proxy, no
/// redirects and no automatic retries, so no request is ever sent twice.
pub struct Client {
    url: String,
    password: String,
    client: reqwest::Client,
    directory: Option<String>,
    limit: usize,
    page: Option<u32>,
}

impl Client {
    /// An engine at `http://127.0.0.1:<port>`; anything else is refused before a request is made.
    pub fn attached(url: &str, password: &str) -> Result<Self, Error> {
        let parsed = reqwest::Url::parse(url).map_err(|_| FAILED)?;
        if parsed.scheme() != "http"
            || parsed.host_str() != Some("127.0.0.1")
            || parsed.port().is_none()
            || !parsed.username().is_empty()
            || parsed.password().is_some()
            || parsed.query().is_some()
            || parsed.fragment().is_some()
            || parsed.path() != "/"
            || password.is_empty()
            || password.len() > 256
        {
            return Err(FAILED);
        }
        Ok(Self {
            url: url.trim_end_matches('/').into(),
            password: password.into(),
            client: reqwest::Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .retry(reqwest::retry::never())
                .connect_timeout(Duration::from_secs(2))
                .build()
                .map_err(|_| FAILED)?,
            directory: None,
            limit: 2 * 1024 * 1024,
            page: None,
        })
    }

    /// Every request names this project directory (`?directory=`), as one engine may serve several.
    pub fn directory(mut self, path: &str) -> Self {
        self.directory = Some(path.into());
        self
    }

    /// The largest response body accepted; 2 MiB unless set.
    pub fn limit(mut self, bytes: usize) -> Self {
        self.limit = bytes;
        self
    }

    /// Message polls of the reply loop read only the newest `messages` of a session.
    pub fn page(mut self, messages: u32) -> Self {
        self.page = Some(messages);
        self
    }

    pub fn url(&self) -> &str {
        &self.url
    }

    pub fn password(&self) -> &str {
        &self.password
    }

    fn address(&self, path: &str) -> String {
        let mut address = format!("{}{path}", self.url);
        if let Some(directory) = &self.directory {
            address.push(if path.contains('?') { '&' } else { '?' });
            address.push_str("directory=");
            address.extend(utf8_percent_encode(directory, NON_ALPHANUMERIC));
        }
        address
    }

    pub(crate) fn messages(&self, session: &str) -> String {
        match self.page {
            Some(page) => format!("{session}/message?limit={page}"),
            None => format!("{session}/message"),
        }
    }

    async fn send(
        &self,
        method: Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<reqwest::Response, Error> {
        let mut request = self
            .client
            .request(method.clone(), self.address(path))
            .basic_auth("opencode", Some(&self.password))
            .timeout(Duration::from_secs(
                if method == Method::POST && path.ends_with("/message") {
                    190
                } else {
                    20
                },
            ));
        if let Some(body) = body {
            request = request
                .header("Content-Type", "application/json")
                .body(serde_json::to_vec(&body).map_err(|_| FAILED)?);
        }
        request.send().await.map_err(|_| FAILED)
    }

    async fn body(&self, mut response: reqwest::Response) -> Result<Vec<u8>, Error> {
        let mut data = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| FAILED)? {
            if data.len() + chunk.len() > self.limit {
                return Err(FAILED);
            }
            data.extend_from_slice(&chunk);
        }
        Ok(data)
    }

    /// The JSON answer of a successful request; any other status is a failure.
    pub async fn request(
        &self,
        method: Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, Error> {
        let response = self.send(method, path, body).await?;
        if !response.status().is_success() {
            return Err(FAILED);
        }
        let data = self.body(response).await?;
        if data.is_empty() {
            Ok(Value::Null)
        } else {
            serde_json::from_slice(&data).map_err(|_| FAILED)
        }
    }

    /// The status and JSON body of any answer, for callers that show the engine's own refusal. A
    /// successful answer must be JSON; a refusal that is not JSON comes back as `null`.
    pub async fn call(
        &self,
        method: Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<(StatusCode, Value), Error> {
        let response = self.send(method, path, body).await?;
        let status = response.status();
        let data = self.body(response).await?;
        let value = if data.is_empty() {
            Value::Null
        } else if status.is_success() {
            serde_json::from_slice(&data).map_err(|_| FAILED)?
        } else {
            serde_json::from_slice(&data).unwrap_or(Value::Null)
        };
        Ok((status, value))
    }

    /// The status, content type and body of any answer, for callers that judge it themselves: the
    /// desktop's setup diagnosis counts sizes and tells API data from a web page.
    pub async fn raw(
        &self,
        method: Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<(StatusCode, String, Vec<u8>), Error> {
        let response = self.send(method, path, body).await?;
        let status = response.status();
        let kind = response
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or_default()
            .to_owned();
        Ok((status, kind, self.body(response).await?))
    }

    /// Whether the engine answers its health check within `limit`.
    pub async fn health(&self, limit: Duration) -> bool {
        self.client
            .get(self.address("/global/health"))
            .basic_auth("opencode", Some(&self.password))
            .timeout(limit)
            .send()
            .await
            .is_ok_and(|r| r.status().is_success())
    }

    /// The engine's event stream, or `None` for an engine without one.
    pub async fn events(&self) -> Result<Option<reqwest::Response>, Error> {
        let response = self
            .client
            .get(self.address("/event"))
            .basic_auth("opencode", Some(&self.password))
            .timeout(Duration::from_secs(190))
            .send()
            .await
            .map_err(|_| FAILED)?;
        if response.status() == StatusCode::NOT_FOUND {
            return Ok(None);
        }
        if !response.status().is_success()
            || !response
                .headers()
                .get("content-type")
                .and_then(|v| v.to_str().ok())
                .is_some_and(|v| v.split(';').next() == Some("text/event-stream"))
        {
            return Err(FAILED);
        }
        Ok(Some(response))
    }
}

/// Ends an engine process: TERM, five seconds to exit, then KILL. With `group` the signals go to
/// the process group the engine leads, so the tools and servers it started end with it.
pub async fn reap(child: &mut Child, group: bool) {
    let id = child
        .id()
        .and_then(|id| i32::try_from(id).ok())
        .and_then(rustix::process::Pid::from_raw);
    let signal = |signal| {
        if let Some(id) = id {
            let _ = if group {
                rustix::process::kill_process_group(id, signal)
            } else {
                rustix::process::kill_process(id, signal)
            };
        }
    };
    signal(rustix::process::Signal::TERM);
    let exited = matches!(
        tokio::time::timeout(Duration::from_secs(5), child.wait()).await,
        Ok(Ok(_))
    );
    // ponytail: the group is signalled once more after its leader was reaped; a reused group ID
    // within that instant would be hit too. Waiting without reaping would close that gap.
    if group {
        signal(rustix::process::Signal::KILL);
    }
    if !exited {
        let _ = child.kill().await;
    }
}

//! OpenCode response reconciliation. Events improve latency; message state decides completion.
use crate::{Client, Error, FAILED, Method, StatusCode, TIMEOUT};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    future::Future,
    time::Duration,
};
use tokio::time::Instant;

/// What the caller sees of one reply, and how it stops it: every hook may end the loop with an
/// error. All hooks run in the caller's task, so no `Send` bound is needed.
#[allow(async_fn_in_trait)]
pub trait Observer {
    type Error: From<Error>;
    async fn check(&self) -> Result<(), Self::Error>;
    async fn text(&self, text: &str) -> Result<(), Self::Error>;
    async fn messages(&self, _messages: &Value) -> Result<(), Self::Error> {
        Ok(())
    }
    async fn phase(&self, _name: &str) -> Result<(), Self::Error> {
        Ok(())
    }
    async fn session(&self, _id: &str) -> Result<(), Self::Error> {
        Ok(())
    }
    async fn usage(&self, _session: &str, _usage: Option<Value>) -> Result<(), Self::Error> {
        Ok(())
    }
    /// Asked after every message poll: `true` holds completion, for a reply that waits for the
    /// user (an open permission or question).
    async fn waiting(&self) -> Result<bool, Self::Error> {
        Ok(false)
    }
}

async fn guarded<T, O: Observer>(
    observer: &O,
    deadline: Instant,
    future: impl Future<Output = Result<T, Error>>,
) -> Result<T, O::Error> {
    tokio::pin!(future);
    loop {
        if Instant::now() >= deadline {
            return Err(TIMEOUT.into());
        }
        observer.check().await?;
        tokio::select! {
            result=&mut future=>{observer.check().await?;return result.map_err(Into::into);}
            _=tokio::time::sleep(Duration::from_millis(250))=>{}
            _=tokio::time::sleep_until(deadline)=>return Err(TIMEOUT.into()),
        }
    }
}

#[derive(Default)]
struct Text {
    /// The user message the reply answers; without it every assistant message of the session counts.
    parent: Option<String>,
    assistant: HashSet<String>,
    parts: HashMap<String, (String, String)>,
    order: Vec<String>,
    latest: Option<String>,
    seen: HashSet<String>,
}
/// Whether an assistant message answers the named prompt; without one every message does.
fn answers(parent: Option<&str>, info: &Value) -> bool {
    parent.is_none_or(|parent| info["parentID"] == parent)
}

impl Text {
    fn info(&mut self, info: &Value, session: &str) {
        if info["sessionID"] == session
            && info["role"] == "assistant"
            && answers(self.parent.as_deref(), info)
            && let Some(id) = info["id"].as_str()
        {
            self.assistant.insert(id.to_owned());
            self.latest = Some(id.to_owned());
        }
    }
    fn part(&mut self, part: &Value, session: &str) -> Result<(), Error> {
        if part["sessionID"] != session || part["type"] != "text" {
            return Ok(());
        }
        let (Some(id), Some(message), Some(text)) = (
            part["id"].as_str(),
            part["messageID"].as_str(),
            part["text"].as_str(),
        ) else {
            return Err(FAILED);
        };
        if !self.assistant.contains(message) {
            return Ok(());
        }
        if !self.parts.contains_key(id) {
            self.order.push(id.to_owned());
        }
        self.parts.insert(id.into(), (message.into(), text.into()));
        self.limit()
    }
    fn limit(&self) -> Result<(), Error> {
        if self.assistant.len() > 10000
            || self.parts.len() > 10000
            || self.seen.len() > 20000
            || self.parts.values().map(|(_, t)| t.len()).sum::<usize>() > 2 * 1024 * 1024
        {
            return Err(FAILED);
        }
        Ok(())
    }
    fn event(&mut self, value: &Value, session: &str) -> Result<(), Error> {
        let event = value.get("payload").unwrap_or(value);
        if let Some(id) = event["id"].as_str()
            && !self.seen.insert(id.into())
        {
            return Ok(());
        }
        let data = event
            .get("properties")
            .or_else(|| event.get("data"))
            .unwrap_or(&Value::Null);
        match event["type"].as_str() {
            Some("message.updated") => self.info(&data["info"], session),
            Some("message.part.updated") => self.part(&data["part"], session)?,
            Some("message.part.delta")
                if data["sessionID"] == session && data["field"] == "text" =>
            {
                if let (Some(id), Some(message), Some(delta)) = (
                    data["partID"].as_str(),
                    data["messageID"].as_str(),
                    data["delta"].as_str(),
                ) && self.assistant.contains(message)
                    && let Some((saved, text)) = self.parts.get_mut(id)
                    && saved == message
                {
                    text.push_str(delta);
                }
            }
            _ => {}
        }
        self.limit()
    }
    fn text(&self) -> String {
        self.order
            .iter()
            .filter_map(|id| self.parts.get(id))
            .filter(|(message, _)| self.latest.as_ref() == Some(message))
            .map(|(_, t)| t.as_str())
            .collect::<Vec<_>>()
            .join("\n")
    }
}

/// The refusal of a message the provider rejected; the provider's own text never passes.
pub fn provider_error(info: &Value) -> Option<Error> {
    let error = info.get("error")?;
    if error.is_null() || error == &json!({}) || error == &json!(false) {
        return None;
    }
    Some(Error(
        StatusCode::BAD_GATEWAY,
        "Der Modellanbieter hat die Anfrage abgelehnt. Bitte Anbindung und Kontingent prüfen.",
    ))
}

fn provider_message(info: &Value) -> Value {
    let name = match info["error"]["name"].as_str() {
        Some("ProviderAuthError") => "ProviderAuthError",
        Some("APIError") => "APIError",
        Some("UnknownError") => "UnknownError",
        Some("MessageAbortedError") => "MessageAbortedError",
        Some("ContextOverflowError") => "ContextOverflowError",
        Some("StructuredOutputError") => "StructuredOutputError",
        _ => "ProviderError",
    };
    let mut data = json!({});
    if let Some(status) = info["error"]["data"]["statusCode"]
        .as_u64()
        .filter(|v| *v <= 999)
    {
        data["statusCode"] = json!(status);
    }
    json!({"info":{"role":"assistant","error":{"name":name,"data":data}},"parts":[]})
}

/// One prompt to the session at `path` (`/session/<encoded id>`) and its final assistant message.
/// The prompt is sent exactly once; a lost event stream is reopened, never the prompt repeated.
///
/// A payload that names its `messageID` follows that prompt in a session that continues: only
/// replies to it count, and a finished reply completes even without text. Without one, the session
/// is the run's own and its last assistant message with text is the answer.
pub async fn response<O: Observer>(
    engine: &Client,
    path: &str,
    payload: Value,
    deadline: Instant,
    streaming: bool,
    observer: &O,
) -> Result<Value, O::Error> {
    let session =
        percent_encoding::percent_decode_str(path.strip_prefix("/session/").ok_or(FAILED)?)
            .decode_utf8()
            .map_err(|_| FAILED)?;
    let structured = payload.get("format").is_some();
    let parent = payload["messageID"].as_str().map(str::to_owned);
    let mut stream = if streaming {
        guarded(observer, deadline, engine.events()).await?
    } else {
        None
    };
    let mut parser = crate::frames::Events::default();
    let mut state = Text {
        parent: parent.clone(),
        ..Text::default()
    };
    let mut previous = String::new();
    let mut last_text = Instant::now() - Duration::from_millis(75);
    let mut next_poll = Instant::now();
    let mut reconnect = Instant::now() + Duration::from_secs(1);
    if structured {
        let value = guarded(
            observer,
            deadline,
            engine.request(Method::POST, &format!("{path}/message"), Some(payload)),
        )
        .await?;
        if provider_error(&value["info"]).is_some() {
            return Ok(provider_message(&value["info"]));
        }
        if !value["info"]["structured"].is_object()
            || value["info"]["role"] != "assistant"
            || !value["info"]["time"]["completed"]
                .as_f64()
                .is_some_and(|v| v > 0.)
        {
            return Err(Error(
                StatusCode::UNPROCESSABLE_ENTITY,
                "Das Modell hat kein gültiges strukturiertes Ergebnis geliefert.",
            )
            .into());
        }
        if streaming {
            loop {
                let status = guarded(
                    observer,
                    deadline,
                    engine.request(Method::GET, "/session/status", None),
                )
                .await?;
                if status[session.as_ref()]["type"].as_str().unwrap_or("idle") == "idle" {
                    break;
                }
                guarded(observer, deadline, async {
                    tokio::time::sleep(Duration::from_millis(100)).await;
                    Ok(())
                })
                .await?;
            }
        }
        observer.messages(&json!([value.clone()])).await?;
        return Ok(value);
    }
    guarded(
        observer,
        deadline,
        engine.request(Method::POST, &format!("{path}/prompt_async"), Some(payload)),
    )
    .await?;
    loop {
        observer.check().await?;
        if Instant::now() >= deadline {
            return Err(TIMEOUT.into());
        }
        let text = state.text();
        if !text.is_empty() && text != previous && last_text.elapsed() >= Duration::from_millis(75)
        {
            observer.check().await?;
            observer.text(&text).await?;
            previous = text;
            last_text = Instant::now();
        }
        if Instant::now() >= next_poll {
            let value = guarded(
                observer,
                deadline,
                engine.request(Method::GET, &engine.messages(path), None),
            )
            .await?;
            let messages = value.as_array().ok_or(FAILED)?;
            observer.messages(&value).await?;
            let mut replies = messages.iter().filter(|m| {
                m["info"]["role"] == "assistant" && answers(parent.as_deref(), &m["info"])
            });
            for message in replies.clone() {
                state.info(&message["info"], &session);
                if let Some(parts) = message["parts"].as_array() {
                    for part in parts {
                        state.part(part, &session)?;
                    }
                }
            }
            let waiting = observer.waiting().await?;
            if let Some(message) = replies.next_back() {
                if provider_error(&message["info"]).is_some() {
                    return Ok(provider_message(&message["info"]));
                }
                let text = message["parts"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter(|p| p["type"] == "text")
                    .filter_map(|p| p["text"].as_str())
                    .collect::<Vec<_>>()
                    .join("\n");
                if !text.is_empty() && text != previous {
                    observer.text(&text).await?;
                    previous = text.clone();
                    last_text = Instant::now();
                }
                if message["info"]["time"]["completed"]
                    .as_f64()
                    .is_some_and(|v| v > 0.)
                    && (!text.trim().is_empty() || parent.is_some())
                    && !waiting
                {
                    let finish_known = !streaming
                        || !matches!(
                            message["info"]["finish"].as_str(),
                            None | Some("tool-calls" | "unknown")
                        );
                    let idle = if streaming && finish_known {
                        let status = guarded(
                            observer,
                            deadline,
                            engine.request(Method::GET, "/session/status", None),
                        )
                        .await?;
                        status[session.as_ref()]["type"].as_str().unwrap_or("idle") == "idle"
                    } else {
                        !streaming
                    };
                    if finish_known && idle {
                        return Ok(message.clone());
                    }
                }
            }
            next_poll = Instant::now() + Duration::from_secs(1);
        }
        if streaming && stream.is_none() && Instant::now() >= reconnect {
            stream = guarded(observer, deadline, engine.events()).await?;
            parser = crate::frames::Events::default();
            reconnect = Instant::now() + Duration::from_secs(1);
        }
        tokio::select! {
            chunk=async {match &mut stream {Some(s)=>s.chunk().await.map_err(|_|FAILED),None=>std::future::pending().await}}=>{
                match chunk {
                    Ok(Some(bytes))=>{
                        for frame in parser.push(&bytes,false).map_err(|_|FAILED)? {
                            if let Some(value)=crate::frames::event(frame,&[],|s|Ok::<_,Error>(s.to_owned())).map_err(|_|FAILED)?.1 {state.event(&value,&session)?;}
                        }

                    }
                    _=>{stream=None;next_poll=Instant::now();reconnect=Instant::now()+Duration::from_millis(500);}
                }
            }
            _=tokio::time::sleep(Duration::from_millis(100))=>{}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn provider_error_contains_no_upstream_secret() {
        let error =
            provider_error(&json!({"error":{"name":"APIError","data":{"message":"SECRET_TOKEN"}}}))
                .unwrap();
        assert!(!error.1.contains("SECRET_TOKEN"));
    }

    #[test]
    fn events_of_an_earlier_reply_do_not_count_for_a_named_prompt() {
        let mut state = Text {
            parent: Some("msg_new".into()),
            ..Text::default()
        };
        for (id, parent) in [("old", "msg_old"), ("new", "msg_new")] {
            state.event(&json!({"type":"message.updated","properties":{"info":{"id":id,"sessionID":"s","role":"assistant","parentID":parent}}}), "s").unwrap();
            state.event(&json!({"type":"message.part.updated","properties":{"part":{"id":format!("{id}-p"),"messageID":id,"sessionID":"s","type":"text","text":id}}}), "s").unwrap();
        }
        assert_eq!(state.text(), "new");
        assert!(!state.assistant.contains("old"));
    }
}

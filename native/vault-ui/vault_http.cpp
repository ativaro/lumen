// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "vault_http.h"
#include "vault.h"
#include "web_login.h"

namespace {
QJsonObject fail(const char *code) { return {{"error", code}}; }
QByteArray json(const QJsonValue &v) {
  return v.isObject() ? QJsonDocument(v.toObject()).toJson(QJsonDocument::Compact)
                     : QJsonDocument(v.toArray()).toJson(QJsonDocument::Compact);
}
bool inject(QJsonValue &value, const QString &user, const QString &password,
            bool &used, int depth = 0) {
  if (depth > 24) return false;
  if (value.isObject()) {
    auto o = value.toObject();
    if (o.contains("$vault")) {
      if (o.size() != 1 || (o["$vault"] != "username" && o["$vault"] != "password")) return false;
      value = o["$vault"] == "username" ? user : password;
      used = true;
    } else {
      for (auto it = o.begin(); it != o.end(); ++it) {
        QJsonValue child = it.value();
        if (!inject(child, user, password, used, depth + 1)) return false;
        it.value() = child;
      }
      value = o;
    }
  } else if (value.isArray()) {
    auto a = value.toArray();
    for (int i = 0; i < a.size(); ++i) {
      QJsonValue child = a[i];
      if (!inject(child, user, password, used, depth + 1)) return false;
      a[i] = child;
    }
    value = a;
  }
  return true;
}
QJsonValue pointer(QJsonValue v, const QString &path) {
  for (auto part : path.mid(1).split('/')) {
    part.replace("~1", "/"); part.replace("~0", "~");
    if (v.isObject()) v = v.toObject().value(part);
    else if (v.isArray()) {
      bool ok = false; const int i = part.toInt(&ok);
      const auto a = v.toArray();
      if (!ok || i < 0 || i >= a.size()) return {};
      v = a[i];
    } else return {};
  }
  return v;
}
class Cookies : public QNetworkCookieJar {
public:
  QStringList values() const {
    QStringList result;
    for (const auto &c : allCookies()) result << QString::fromUtf8(c.value());
    return result;
  }
};
}
QUrl VaultHttp::origin(const QUrl &url) {
  if (!url.isValid() || url.isRelative() || !QStringList{"http", "https"}.contains(url.scheme()) ||
      url.host().isEmpty() || url.authority().contains('@') || url.port() == 0)
    return {};
  QUrl out; out.setScheme(url.scheme()); out.setHost(url.host()); out.setPort(url.port()); out.setPath("/"); return out;
}
QUrl VaultHttp::route(const QUrl &base, const QString &path) {
  if (origin(base).isEmpty() || !path.startsWith('/') || path.startsWith("//") ||
      path.contains('\\') || path.size() > 2048) return {};
  for (auto c : path) if (c.category() == QChar::Other_Control || c.category() == QChar::Other_Format) return {};
  const QUrl relative(path, QUrl::StrictMode);
  if (!relative.isValid() || !relative.isRelative() || !relative.authority().isEmpty() || relative.hasFragment()) return {};
  const auto target = origin(base).resolved(relative);
  return origin(base) == origin(target) ? target : QUrl();
}
bool VaultHttp::validRequest(const QJsonObject &a) {
  const auto op = a.value("operation").toString();
  const auto field = op == "http_open" ? "reference" : "session";
  if (!a.value(field).isString() || a.value(field).toString().isEmpty() || a.value(field).toString().size() > 128) return false;
  if (op == "http_open") {
    if (!a[field].toString().startsWith("vault:")) return false;
    if (!a.contains("requests")) return a.size() == 2;
    if (a.size() != 3 || !a["requests"].isArray()) return false;
    const auto plan = a["requests"].toArray();
    if (plan.isEmpty() || plan.size() > 12 || json(plan).size() > 32768) return false;
    for (const auto &step : plan) {
      if (!step.isObject()) return false;
      auto request = step.toObject();
      if (request.contains("operation") || request.contains("session")) return false;
      request["operation"] = "http_request"; request["session"] = "plan";
      if (!validRequest(request)) return false;
    }
    return true;
  }
  if (op == "http_close") return a.size() == 2;
  if (op != "http_request") return false;
  for (auto it = a.begin(); it != a.end(); ++it)
    if (!QStringList{"operation", "session", "method", "path", "body", "capture_token"}.contains(it.key())) return false;
  if (!QStringList{"GET", "POST", "PUT", "PATCH", "DELETE"}.contains(a["method"].toString()) ||
      !a["path"].isString() || route(QUrl("https://example.test"), a["path"].toString()).isEmpty()) return false;
  if (a.contains("body")) {
    if (a["method"] == "GET" || (!a["body"].isObject() && !a["body"].isArray()) || json(a["body"]).size() > 32768) return false;
    auto body = a["body"]; bool used = false;
    if (!inject(body, "username", "password", used)) return false;
  }
  if (a.contains("capture_token")) {
    if (!a["capture_token"].isString() || !a["capture_token"].toString().startsWith('/') || a["capture_token"].toString().size() > 512) return false;
  }
  return true;
}
VaultHttp::VaultHttp(QUrl url, QString user, QString secret, QObject *parent)
    : QObject(parent), stored(url), username(user), password(secret),
      handle(QUuid::createUuid().toString(QUuid::WithoutBraces)), knownSecrets{user, secret} {
  manager.setCookieJar(new Cookies);
  manager.setRedirectPolicy(QNetworkRequest::ManualRedirectPolicy);
  manager.setTransferTimeout(30000);
}
VaultHttp::~VaultHttp() {
  if (pending) { pending->disconnect(this); pending->abort(); }
  wipe(username); wipe(password); wipe(bearer);
  for (auto &s : knownSecrets) wipe(s);
}
bool VaultHttp::matches(const QUrl &url, const QString &user, const QString &secret) const {
  return stored == url && username == user && password == secret;
}
void VaultHttp::request(const QJsonObject &args, Reply done) {
  const auto url = route(stored, args["path"].toString());
  if (!validRequest(args) || pending || url.isEmpty()) { done(fail("invalid_request")); return; }
  if (VaultWeb::containsSecret(url.toEncoded(), knownSecrets) ||
      VaultWeb::containsSecret(QUrl::fromPercentEncoding(url.toEncoded()).toUtf8(), knownSecrets)) {
    done(fail("unsafe_request")); return;
  }
  auto body = args.value("body"); bool injected = false;
  if (!inject(body, username, password, injected)) { done(fail("invalid_request")); return; }
  auto bytes = body.isUndefined() ? QByteArray() : json(body);
  if (bytes.size() > 32768) { wipe(bytes); done(fail("invalid_request")); return; }
  QNetworkRequest request(url);
  request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
  request.setAttribute(QNetworkRequest::CacheLoadControlAttribute, QNetworkRequest::AlwaysNetwork);
  request.setAttribute(QNetworkRequest::AuthenticationReuseAttribute, QNetworkRequest::Manual);
  request.setRawHeader("Accept", "application/json");
  if (!bytes.isEmpty()) request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
  if (!bearer.isEmpty()) request.setRawHeader("Authorization", "Bearer " + bearer.toUtf8());
  auto *reply = manager.sendCustomRequest(request, args["method"].toString().toLatin1(), bytes);
  wipe(bytes); pending = reply;
  reply->setReadBufferSize(1024 * 1024 + 1);
  auto data = std::shared_ptr<QByteArray>(new QByteArray, [](QByteArray *p) { wipe(*p); delete p; });
  auto oversized = std::make_shared<bool>(false);
  connect(reply, &QNetworkReply::readyRead, this, [reply, data, oversized] {
    data->append(reply->read(1024 * 1024 + 1 - data->size()));
    if (data->size() > 1024 * 1024) { *oversized = true; reply->abort(); }
  });
  QTimer::singleShot(30000, reply, [reply] { if (!reply->isFinished()) reply->abort(); });
  connect(reply, &QNetworkReply::finished, this, [this, reply, data, oversized, injected, args, done] {
    pending.clear(); reply->deleteLater();
    auto clear = qScopeGuard([&] { wipe(*data); });
    const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (*oversized) { done(fail("response_too_large")); return; }
    if (status >= 300 && status < 400) { done(fail("cross_origin_blocked")); return; }
    if (!status || reply->error() == QNetworkReply::SslHandshakeFailedError || reply->error() == QNetworkReply::OperationCanceledError || reply->error() == QNetworkReply::RemoteHostClosedError) { done(fail("https_request_failed")); return; }
    data->append(reply->readAll());
    if (data->size() > 1024 * 1024) { done(fail("response_too_large")); return; }
    knownSecrets.append(static_cast<Cookies *>(manager.cookieJar())->values());
    knownSecrets.removeDuplicates();
    if (knownSecrets.size() > 256) { done(fail("http_session_limit")); return; }
    QJsonParseError error; const auto document = QJsonDocument::fromJson(*data, &error);
    QJsonObject result{{"http_status", status}, {"untrusted", true}};
    if (args.contains("capture_token")) {
      const auto token = pointer(document.isObject() ? QJsonValue(document.object()) : QJsonValue(document.array()), args["capture_token"].toString());
      const auto value = token.toString();
      bool visible = !value.isEmpty() && value.size() <= 4096;
      for (auto ch : value) visible = visible && ch.unicode() >= 0x21 && ch.unicode() <= 0x7e;
      if (status < 200 || status >= 300 || !token.isString() || !visible) { done(fail("http_token_not_found")); return; }
      wipe(bearer); bearer = value; knownSecrets << bearer;
      result["token_stored"] = true;
    }
    if (injected || args.contains("capture_token")) {
      result["response_withheld"] = true;
      result["authentication_verified"] = false;
      result["credentials_submitted"] = injected;
    } else if (VaultWeb::containsSecret(*data, knownSecrets)) {
      result["response_withheld"] = true;
    } else if (data->trimmed().isEmpty()) result["body"] = QJsonValue();
    else if (error.error != QJsonParseError::NoError) { done(fail("invalid_response")); return; }
    else result["body"] = document.isObject() ? QJsonValue(document.object()) : QJsonValue(document.array());
    done(result);
  });
}

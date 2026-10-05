// SPDX-License-Identifier: MIT
#include "bookstack.h"
#include "connection.h"
#include "vault.h"
#include <QStringDecoder>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <sys/stat.h>
#include <unistd.h>

namespace {
// Qt may rewind buffered uploads on connection errors. Refuse every rewind,
// including zero-length requests, so a confirmed write cannot be sent again.
class OneShotUpload final : public QIODevice {
public:
  OneShotUpload(QByteArray data, QObject *parent)
      : QIODevice(parent), data(std::move(data)) {
    open(QIODevice::ReadOnly | QIODevice::Unbuffered);
  }
  ~OneShotUpload() override { wipe(data); }
  bool isSequential() const override { return true; }
  bool reset() override { return false; }
  bool seek(qint64) override { return false; }
  bool atEnd() const override { return offset >= data.size(); }
  qint64 bytesAvailable() const override {
    return data.size() - offset + QIODevice::bytesAvailable();
  }

protected:
  qint64 readData(char *out, qint64 maxSize) override {
    const auto count = qMin(maxSize, qint64(data.size()) - offset);
    if (count <= 0)
      return -1;
    std::memcpy(out, data.constData() + offset, size_t(count));
    offset += count;
    return count;
  }
  qint64 writeData(const char *, qint64) override { return -1; }

private:
  QByteArray data;
  qint64 offset = 0;
};
QNetworkReply *sendOnce(QNetworkAccessManager *network, QNetworkRequest request,
                        const QByteArray &method, QByteArray data) {
  request.setAttribute(QNetworkRequest::Http2AllowedAttribute, false);
  request.setAttribute(QNetworkRequest::HttpPipeliningAllowedAttribute, false);
  request.setAttribute(QNetworkRequest::DoNotBufferUploadDataAttribute, true);
  request.setHeader(QNetworkRequest::ContentLengthHeader, data.size());
  auto *upload = new OneShotUpload(std::move(data), network);
  auto *reply = network->sendCustomRequest(request, method, upload);
  upload->setParent(reply);
  return reply;
}
bool integer(const QJsonValue &value, int low, int high) {
  const double n = value.toDouble(-1);
  return value.isDouble() && std::isfinite(n) && n == std::floor(n) &&
         n >= low && n <= high;
}
bool reflected(const QByteArray &data, const QStringList &secrets) {
  for (const auto &secret : secrets) {
    const auto bytes = secret.toUtf8();
    const auto quoted =
        QJsonDocument(QJsonArray{secret}).toJson(QJsonDocument::Compact);
    if (quoted.size() > 4 && data.contains(quoted.mid(2, quoted.size() - 4)))
      return true;
    if (bytes.isEmpty())
      continue;
    if (data.contains(bytes) || data.contains(bytes.toBase64()) ||
        data.contains(bytes.toHex()) ||
        data.contains(bytes.toPercentEncoding()))
      return true;
  }
  return false;
}
QString plain(const QString &text, int max) {
  class TextOnly : public QTextDocument {
    QVariant loadResource(int, const QUrl &) override { return {}; }
  } document;
  document.setHtml(text.left(BookStack::MaxBody));
  return document.toPlainText().left(max);
}
QJsonObject failure(const char *code) {
  return {{"error", QString::fromLatin1(code)}};
}
} // namespace
QUrl BookStack::origin(const QString &text) {
  const QUrl url(text, QUrl::StrictMode);
  if (!url.isValid() || url.scheme() != "https" || url.host().isEmpty() ||
      url.authority().contains('@') || url.hasQuery() || url.hasFragment() ||
      (!url.path().isEmpty() && url.path() != "/") || url.port() == 0)
    return {};
  QUrl result = url;
  result.setPath("");
  return result;
}
bool BookStack::credential(const QString &value) {
  static const QRegularExpression syntax("^[A-Za-z0-9_-]{8,256}$");
  return syntax.match(value).hasMatch();
}
QUrl BookStack::route(const QUrl &base, const QJsonObject &args) {
  if (origin(base.toString()).isEmpty())
    return {};
  const QString op = args.value("operation").toString();
  QSet<QString> allowed{"operation"};
  QUrl result(base);
  QUrlQuery query;
  if (op == "check") {
    result.setPath("/api/books");
    query.addQueryItem("count", "1");
  } else if (op == "list_books" || op == "search") {
    allowed.unite({"limit", "offset"});
    const auto count = args.value("limit");
    const auto offset = args.value("offset");
    if ((!count.isUndefined() && !integer(count, 1, 20)) ||
        (!offset.isUndefined() && !integer(offset, 0, 100000)))
      return {};
    query.addQueryItem("count", QString::number(count.toInt(10)));
    query.addQueryItem("offset", QString::number(offset.toInt(0)));
    result.setPath(op == "search" ? "/api/search" : "/api/books");
    if (op == "search") {
      allowed.insert("query");
      const auto text = args.value("query");
      if (!text.isString() || text.toString().trimmed().isEmpty() ||
          text.toString().size() > 500)
        return {};
      query.addQueryItem("query", QString::fromLatin1(QUrl::toPercentEncoding(
                                      text.toString())));
    }
  } else if (op == "read_page") {
    allowed.insert("page_id");
    if (!integer(args.value("page_id"), 1, 2147483647))
      return {};
    result.setPath("/api/pages/" +
                   QString::number(args.value("page_id").toInt()));
  } else
    return {};
  for (auto it = args.begin(); it != args.end(); ++it)
    if (!allowed.contains(it.key()))
      return {};
  result.setQuery(query);
  return result;
}
QJsonObject BookStack::project(const QJsonObject &args, const QByteArray &body,
                               const QStringList &secrets) {
  if (body.size() > MaxBody || reflected(body, secrets))
    return failure("unsafe_response");
  QJsonParseError error;
  const auto document = QJsonDocument::fromJson(body, &error);
  if (error.error != QJsonParseError::NoError || !document.isObject())
    return failure("invalid_response");
  const auto source = document.object();
  auto item = [](const QJsonObject &value) {
    QJsonObject out;
    for (const auto *key : {"id", "book_id", "chapter_id"})
      if (integer(value.value(key), 0, 2147483647))
        out[key] = value.value(key);
    for (const auto *key : {"name", "slug", "type"})
      if (value.value(key).isString())
        out[key] = plain(value.value(key).toString(), 512);
    return out;
  };
  QJsonObject out{{"untrusted_content", true}};
  if (args.value("operation") == "read_page") {
    if (!integer(source.value("id"), 1, 2147483647))
      return failure("invalid_response");
    out["page"] = item(source);
    out["text"] = plain(source.value("html").toString(), 100000);
    out["truncated"] =
        plain(source.value("html").toString(), 100001).size() > 100000;
  } else {
    if (!source.value("data").isArray())
      return failure("invalid_response");
    if (args.value("operation") == "check")
      return {{"connected", true}};
    QJsonArray items;
    for (const auto &value : source.value("data").toArray()) {
      if (items.size() >= args.value("limit").toInt(10))
        break;
      if (value.isObject())
        items.append(item(value.toObject()));
    }
    out["items"] = items;
    if (integer(source.value("total"), 0, 2147483647))
      out["total"] = source.value("total");
  }
  if (reflected(QJsonDocument(out).toJson(QJsonDocument::Compact), secrets))
    return failure("unsafe_response");
  return out;
}

VaultAccess::VaultAccess(QWidget *window, Reader reader, bool english)
    : QObject(window), window(window), reader(std::move(reader)),
      english(english) {
  for (auto *timer : {&deadline, &framing})
    timer->setSingleShot(true);
  connect(&deadline, &QTimer::timeout, this,
          [this] { finish(failure("request_timeout")); });
  connect(&framing, &QTimer::timeout, this,
          [this] { finish(failure("invalid_request")); });
  server.setMaxPendingConnections(1);
  server.setSocketOptions(QLocalServer::UserAccessOption);
  connect(&server, &QLocalServer::newConnection, this, &VaultAccess::accept);
}
VaultAccess::~VaultAccess() { revoke(); }
QString VaultAccess::tx(const char *de, const char *en) const {
  return QString::fromUtf8(english ? en : de);
}
bool VaultAccess::listen(const QString &runtime) {
  struct stat s{};
  const auto path = runtime.toUtf8();
  if (!runtime.startsWith('/') || lstat(path.constData(), &s) ||
      !S_ISDIR(s.st_mode) || s.st_uid != geteuid() || (s.st_mode & 0077))
    return false;
  const auto endpoint = runtime + "/lumen-vault-access";
  // Called only by the native GUI singleton that owns the window lock.
  QLocalServer::removeServer(endpoint);
  return server.listen(endpoint);
}
bool VaultAccess::armed() const { return !profiles.isEmpty(); }
bool VaultAccess::arm(const QString &id, const QUrl &url) {
  return arm(id, QJsonObject{{"title", ""},
                             {"endpoint", url.toString()},
                             {"connector", "api"},
                             {"auth", "token_pair"},
                             {"id_header", ""},
                             {"secret_header", "X-API-Key"}});
}
bool VaultAccess::arm(const QString &id, const QJsonObject &value) {
  finish(failure("access_revoked"));
  if (id.isEmpty() || value["endpoint"].toString().isEmpty())
    return false;
  entryId = id;
  profile = value;
  base = QUrl(profile["endpoint"].toString());
  profiles.insert(id, value);
  emit changed();
  return true;
}
void VaultAccess::setConnections(const QMap<QString, QJsonObject> &values) {
  revoke();
  profiles = values;
  emit changed();
}
QJsonObject VaultAccess::connection(int offset) const {
  QJsonArray connections;
  int index = 0;
  for (auto it = profiles.begin(); it != profiles.end(); ++it) {
    if (index++ < offset || connections.size() >= 20)
      continue;
    connections.append(
        QJsonObject{{"reference", "vault:" + it.key()},
                    {"connector", it.value()["connector"]},
                    {"endpoint", QUrl(it.value()["endpoint"].toString())
                                     .toString(QUrl::FullyEncoded)}});
  }
  QJsonObject result{{"connected", armed()},
                     {"connections", connections},
                     {"requires_confirmation", true}};
  // Preserve single-connection clients without choosing an arbitrary service.
  result.insert("next_offset", offset + connections.size() < profiles.size()
                                   ? QJsonValue(offset + connections.size())
                                   : QJsonValue(QJsonValue::Null));
  if (profiles.size() == 1 && connections.size() == 1) {
    const auto single = connections[0].toObject();
    for (auto it = single.begin(); it != single.end(); ++it)
      result.insert(it.key(), it.value());
  }
  return result;
}
void VaultAccess::revoke() {
  ++epoch;
  entryId.clear();
  base.clear();
  profile = {};
  profiles.clear();
  finish(failure("access_revoked"));
  emit changed();
}
void VaultAccess::cancel() {
  ++epoch;
  deadline.stop();
  framing.stop();
  auto dialog = prompt;
  prompt.clear();
  if (dialog) {
    dialog->disconnect(this);
    // A user-confirmed write already dispatched to Rust cannot be undone by
    // losing the IPC client. Let its native dialog finish; lock still closes
    // it.
    if (!dialog->property("saving").toBool()) {
      dialog->reject();
      dialog->deleteLater();
    }
  }
  if (reply) {
    reply->disconnect(this);
    reply->abort();
    reply->deleteLater();
    reply.clear();
  }
  if (network) {
    network->deleteLater();
    network.clear();
  }
  for (auto &secret : credentials)
    wipe(secret);
  credentials.clear();
  for (auto &header : authHeaders)
    wipe(header.second);
  authHeaders.clear();
  wipe(sessionId);
  wipe(protocol);
  totalBytes = 0;
  actionDispatched = false;
  wipe(frame);
  wipe(response);
  requested = false;
}
void VaultAccess::finish(const QJsonObject &result) {
  QJsonObject delivered = result;
  if (result.contains("error") && actionDispatched)
    delivered = failure("operation_outcome_unknown");
  if (result.contains("error") && prompt && prompt->property("saving").toBool())
    delivered = failure("save_outcome_unknown");
  auto socket = peer;
  peer.clear();
  cancel();
  if (socket) {
    socket->disconnect(this);
    socket->write(QJsonDocument(delivered).toJson(QJsonDocument::Compact) +
                  '\n');
    connect(socket, &QLocalSocket::disconnected, socket, &QObject::deleteLater);
    socket->disconnectFromServer();
    QTimer::singleShot(2000, socket, [socket] {
      socket->abort();
      socket->deleteLater();
    });
  }
}
void VaultAccess::accept() {
  while (server.hasPendingConnections()) {
    auto *socket = server.nextPendingConnection();
    if (peer) {
      socket->abort();
      socket->deleteLater();
      continue;
    }
    peer = socket;
    socket->setReadBufferSize(BookStack::MaxFrame + 1);
    framing.start(3000);
    deadline.start(90000);
    connect(socket, &QLocalSocket::readyRead, this, &VaultAccess::receive);
    connect(socket, &QLocalSocket::disconnected, this, [this, socket] {
      if (peer == socket) {
        peer.clear();
        cancel();
      }
      socket->deleteLater();
    });
    receive();
  }
}
void VaultAccess::receive() {
  if (!peer)
    return;
  if (requested && peer->bytesAvailable()) {
    finish(failure("invalid_request"));
    return;
  }
  frame += peer->read(BookStack::MaxFrame + 1 - frame.size());
  if (frame.size() > BookStack::MaxFrame) {
    finish(failure("invalid_request"));
    return;
  }
  if (!frame.contains('\n'))
    return;
  if (!frame.endsWith('\n') || frame.count('\n') != 1) {
    finish(failure("invalid_request"));
    return;
  }
  QStringDecoder utf8(QStringDecoder::Utf8);
  const auto text = utf8.decode(frame);
  Q_UNUSED(text);
  QJsonParseError error;
  const auto document = QJsonDocument::fromJson(frame, &error);
  if (utf8.hasError() || error.error != QJsonParseError::NoError ||
      !document.isObject()) {
    finish(failure("invalid_request"));
    return;
  }
  if (document.object().value("operation") == "connection") {
    const auto args = document.object();
    const auto offset = args.value("offset");
    if ((args.size() != 1 && (args.size() != 2 || !args.contains("offset"))) ||
        (!offset.isUndefined() &&
         (!offset.isDouble() || offset.toDouble() != offset.toInt(-1) ||
          offset.toInt(-1) < 0 || offset.toInt() > 10000))) {
      finish(failure("invalid_request"));
      return;
    }
    finish(connection(offset.toInt()));
    return;
  }
  if (document.object().value("operation") == "store") {
    const auto args = document.object();
    for (auto it = args.begin(); it != args.end(); ++it)
      if (it.key() != "operation" && it.key() != "title" &&
          it.key() != "kind" && it.key() != "prefill") {
        finish(failure("invalid_request"));
        return;
      }
    if (!args.value("title").isString() ||
        args.value("title").toString().trimmed().isEmpty() ||
        args.value("title").toString().size() > 120 ||
        (args.value("kind") != "login" && args.value("kind") != "token")) {
      finish(failure("invalid_request"));
      return;
    }
    if (args.contains("prefill")) {
      const auto value = args.value("prefill");
      const auto fields = value.toObject();
      if (!value.isObject() || !fields.contains("Password")) {
        finish(failure("invalid_request"));
        return;
      }
      for (auto it = fields.begin(); it != fields.end(); ++it) {
        const auto name = it.key();
        const auto text = it.value().toString();
        const int limit = name == "Password" || (name == "UserName" && args["kind"] == "token") ? 4096 : 1024;
        if ((name != "UserName" && name != "Password" && name != "URL") ||
            !it.value().isString() || text.isEmpty() || text.size() > limit ||
            std::any_of(text.begin(), text.end(), [](QChar c) { return c.unicode() < 32 || c.unicode() == 127; })) {
          finish(failure("invalid_request"));
          return;
        }
      }
    }
    wipe(frame);
    requested = true;
    framing.stop();
    if (QApplication::activeModalWidget() || !store) {
      finish(failure("vault_busy"));
      return;
    }
    auto *dialog = store(args);
    if (!dialog) {
      finish(failure("unlock_vault_then_retry"));
      return;
    }
    prompt = dialog;
    const auto requestEpoch = epoch;
    connect(dialog, &QDialog::finished, this,
            [this, dialog, requestEpoch](int result) {
              if (requestEpoch != epoch)
                return;
              prompt.clear();
              const QString id = dialog->property("savedEntryId").toString();
              finish(result == QDialog::Accepted && !id.isEmpty()
                         ? QJsonObject{{"saved", true},
                                       {"reference", "vault:" + id}}
                         : failure(dialog->property("saving").toBool()
                                       ? "save_outcome_unknown"
                                       : "entry_not_saved"));
            });
    return;
  }
  if (!armed()) {
    finish(failure("open_vault_and_enable_connection"));
    return;
  }
  auto args = document.object();
  const auto reference = args.take("reference");
  QString id;
  if (reference.isUndefined() && profiles.size() == 1)
    id = profiles.firstKey();
  else if (reference.isString() && reference.toString().startsWith("vault:"))
    id = reference.toString().mid(6);
  if (!profiles.contains(id)) {
    finish(failure(reference.isUndefined() ? "connection_reference_required"
                                           : "connection_not_enabled"));
    return;
  }
  entryId = id;
  profile = profiles.value(id);
  base = QUrl(profile["endpoint"].toString());
  if (VaultConnection::route(profile, args).isEmpty()) {
    finish(failure("invalid_request"));
    return;
  }
  requested = true;
  framing.stop();
  confirm(args);
}
void VaultAccess::confirm(const QJsonObject &args) {
  if (QApplication::activeModalWidget()) {
    finish(failure("vault_busy"));
    return;
  }
  auto *dialog = new QDialog(window);
  prompt = dialog;
  dialog->setWindowTitle(
      tx("Dienstzugriff bestätigen", "Confirm service access"));
  auto *layout = new QVBoxLayout(dialog);
  auto *text = new QLabel(
      tx("Ein lokales Programm möchte den verbundenen Dienst verwenden. Der "
         "Aufrufer ist nicht "
         "als Lumen verifiziert.\n\n",
         "A local program wants to use the connected service. The caller is "
         "not verified "
         "as Lumen.\n\n") +
      tx("Eintrag: ", "Entry: ") + profile["title"].toString() + "\n" +
      "vault:" + entryId + "\n\n" +
      (args["operation"] == "api_request" ? args["method"].toString() + " "
                                          : QString()) +
      VaultConnection::route(profile, args).toString(QUrl::FullyEncoded) +
      "\n" +
      QString::fromUtf8(QJsonDocument(args).toJson(QJsonDocument::Indented)) +
      tx("\nDie Anfrage kann beim Dienst Änderungen auslösen.\nDie Antwort "
         "wird an das anfragende Programm zurückgegeben und kann "
         "an dein Cloud-Modell gelangen. Der Token wird nur zur Anmeldung bei "
         "diesem Dienst verwendet.",
         "\nThe request may change data at the service.\nThe response is "
         "returned to the requesting program and may reach "
         "your cloud model. The token is used only to authenticate to this "
         "service."));
  text->setTextFormat(Qt::PlainText);
  text->setWordWrap(true);
  text->setMinimumWidth(500);
  auto *scroll = new QScrollArea;
  scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame);
  scroll->setWidget(text);
  scroll->setMinimumSize(580, 320);
  layout->addWidget(scroll, 1);
  dialog->resize(680, 540);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel);
  auto *allow =
      buttons->addButton(tx("Diese Anfrage erlauben", "Allow this request"),
                         QDialogButtonBox::AcceptRole);
  allow->setAutoDefault(false);
  allow->setDefault(false);
  buttons->button(QDialogButtonBox::Cancel)->setDefault(true);
  layout->addWidget(buttons);
  connect(buttons, &QDialogButtonBox::accepted, dialog, &QDialog::accept);
  connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);
  const auto requestEpoch = epoch;
  connect(dialog, &QDialog::finished, this,
          [this, args, requestEpoch, dialog](int result) {
            if (prompt == dialog)
              prompt.clear();
            dialog->deleteLater();
            if (requestEpoch != epoch)
              return;
            if (result != QDialog::Accepted || !armed()) {
              finish(failure("access_denied"));
              return;
            }
            reader(entryId, [this, args, requestEpoch](QStringList fields) {
              dispatch(args, requestEpoch, std::move(fields));
            });
          });
  window->show();
  window->raise();
  dialog->open();
  buttons->button(QDialogButtonBox::Cancel)->setFocus();
}
void VaultAccess::dispatch(const QJsonObject &args, quint64 requestEpoch,
                           QStringList fields) {
  const bool valid = VaultConnection::value(fields, "LumenApiEnabled") == "1" &&
                     VaultConnection::problem(fields).isEmpty() &&
                     VaultConnection::settings(fields) == profile;
  if (requestEpoch != epoch || !peer || !armed() || !valid) {
    for (auto &value : fields)
      wipe(value);
    if (requestEpoch == epoch)
      finish(failure("access_revoked_or_invalid_profile"));
    return;
  }
  auto id = VaultConnection::value(fields, "LumenApiTokenId");
  if (id.isEmpty())
    id = VaultConnection::value(fields, "UserName");
  auto secret = VaultConnection::value(fields, "Password");
  credentials = {secret};
  if (!id.isEmpty() &&
      (profile["auth"] == "token_pair" || profile["auth"] == "headers"))
    credentials << id << id + ":" + secret;
  authHeaders = VaultConnection::headers(fields);
  wipe(id);
  wipe(secret);
  for (auto &value : fields)
    wipe(value);
  network = new QNetworkAccessManager(this);
  network->setProxy(QNetworkProxy::NoProxy);
  network->setCache(nullptr);
  sendRequest(args, requestEpoch, profile["connector"] == "mcp" ? 0 : 2);
}
void VaultAccess::sendRequest(const QJsonObject &args, quint64 requestEpoch,
                              int stage) {
  if (requestEpoch != epoch || !peer || !armed()) {
    if (requestEpoch == epoch)
      finish(failure("access_revoked"));
    return;
  }
  if (reply) {
    reply->disconnect(this);
    reply->abort();
    reply->deleteLater();
    reply.clear();
  }
  wipe(response);
  QNetworkRequest request(VaultConnection::route(profile, args));
  request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                       QNetworkRequest::ManualRedirectPolicy);
  request.setAttribute(QNetworkRequest::CookieLoadControlAttribute,
                       QNetworkRequest::Manual);
  request.setAttribute(QNetworkRequest::CookieSaveControlAttribute,
                       QNetworkRequest::Manual);
  request.setAttribute(QNetworkRequest::AuthenticationReuseAttribute,
                       QNetworkRequest::Manual);
  request.setAttribute(QNetworkRequest::CacheLoadControlAttribute,
                       QNetworkRequest::AlwaysNetwork);
  request.setAttribute(QNetworkRequest::CacheSaveControlAttribute, false);
  request.setTransferTimeout(20000);
  request.setRawHeader("Accept-Encoding", "identity");
  const bool mcp = profile["connector"] == "mcp";
  request.setRawHeader("Accept", mcp ? "application/json, text/event-stream"
                                     : "application/json");
  for (const auto &header : authHeaders)
    request.setRawHeader(header.first, header.second);
  if (mcp) {
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    if (!sessionId.isEmpty())
      request.setRawHeader("Mcp-Session-Id", sessionId);
    if (!protocol.isEmpty())
      request.setRawHeader("MCP-Protocol-Version", protocol);
    if (stage == 2 && args["operation"] == "mcp_call")
      actionDispatched = true;
    const auto payload = QJsonDocument(VaultConnection::rpc(args, stage))
                             .toJson(QJsonDocument::Compact);
    reply = stage == 2 && args["operation"] == "mcp_call"
                ? sendOnce(network, request, "POST", payload)
                : network->post(request, payload);
  } else if (args["operation"] == "api_request" && args["method"] != "GET") {
    auto payload = VaultConnection::body(args);
    if (args.contains("body"))
      request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    // From this point onward a lost/unsafe response cannot establish
    // non-execution.
    actionDispatched = true;
    reply = sendOnce(network, request, args["method"].toString().toLatin1(),
                     std::move(payload));
    wipe(payload);
  } else
    reply = network->get(request);
  reply->setReadBufferSize(65536);
  QTimer::singleShot(20000, reply, [this, requestEpoch] {
    if (epoch == requestEpoch)
      finish(failure("network_timeout"));
  });
  connect(reply, &QNetworkReply::readyRead, this,
          [this, args, requestEpoch, stage] {
            received(args, requestEpoch, stage, false);
          });
  connect(reply, &QNetworkReply::finished, this,
          [this, args, requestEpoch, stage] {
            received(args, requestEpoch, stage, true);
          });
}
void VaultAccess::received(const QJsonObject &args, quint64 requestEpoch,
                           int stage, bool final) {
  if (requestEpoch != epoch || !reply)
    return;
  if (!armed()) {
    finish(failure("access_revoked"));
    return;
  }
  auto chunk = reply->read(BookStack::MaxBody + 1 - totalBytes);
  totalBytes += chunk.size();
  response += chunk;
  wipe(chunk);
  if (totalBytes > BookStack::MaxBody) {
    finish(failure("response_too_large"));
    return;
  }
  const int status =
      reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
  const bool apiRequest = args["operation"] == "api_request";
  if (!(apiRequest ? status >= 200 && status < 300 : status == 200) &&
      !(profile["connector"] == "mcp" && stage == 1 && status == 202)) {
    if (final || status)
      finish(failure(status == 401 || status == 403 ? "service_denied"
                                                    : "https_request_failed"));
    return;
  }
  if (final && reply->error() != QNetworkReply::NoError) {
    finish(failure("https_request_failed"));
    return;
  }
  if (!reply->rawHeader("Content-Encoding").isEmpty() &&
      reply->rawHeader("Content-Encoding") != "identity") {
    finish(failure("invalid_response"));
    return;
  }
  if (reflected(response, credentials)) {
    finish(failure("unsafe_response"));
    return;
  }
  if (profile["connector"] == "mcp" && stage == 1) {
    if (final) {
      if (status != 202 || !response.isEmpty())
        finish(failure("invalid_response"));
      else
        sendRequest(args, requestEpoch, 2);
    }
    return;
  }
  if (apiRequest && final && response.isEmpty()) {
    finish({{"untrusted_content", true},
            {"http_status", status},
            {"result", QJsonValue(QJsonValue::Null)}});
    return;
  }
  if (apiRequest && !final && response.isEmpty())
    return;
  const auto contentType =
      reply->header(QNetworkRequest::ContentTypeHeader).toString();
  const bool sse = contentType.startsWith("text/event-stream");
  if (!contentType.startsWith("application/json") &&
      !(sse && profile["connector"] == "mcp")) {
    finish(failure("invalid_response"));
    return;
  }
  if (profile["connector"] == "mcp") {
    if (!final && !sse)
      return;
    const auto result =
        VaultConnection::rpcResponse(response, sse, stage == 0 ? 1 : 2);
    if (result.isEmpty()) {
      if (final)
        finish(failure("invalid_response"));
      return;
    }
    if (result.contains("error")) {
      finish(failure("invalid_mcp_response"));
      return;
    }
    const auto payload = result["result"].toObject();
    if (reflected(QJsonDocument(payload).toJson(QJsonDocument::Compact),
                  credentials)) {
      finish(failure("unsafe_response"));
      return;
    }
    if (stage == 0) {
      protocol = payload["protocolVersion"].toString().toLatin1();
      if (protocol != "2025-06-18" && protocol != "2025-03-26") {
        finish(failure("unsupported_mcp_version"));
        return;
      }
      sessionId = reply->rawHeader("Mcp-Session-Id");
      if (sessionId.size() > 256) {
        finish(failure("invalid_mcp_response"));
        return;
      }
      for (auto c : sessionId)
        if (c < 0x21 || c > 0x7e) {
          finish(failure("invalid_mcp_response"));
          return;
        }
      if (!sessionId.isEmpty())
        credentials << QString::fromLatin1(sessionId);
      sendRequest(args, requestEpoch, 1);
      return;
    }
    finish({{"untrusted_content", true}, {"result", payload}});
    return;
  }
  if (!final)
    return;
  if (args["operation"] != "api_get" && !apiRequest) {
    finish(BookStack::project(args, response, credentials));
    return;
  }
  QJsonParseError error;
  const auto result = QJsonDocument::fromJson(response, &error);
  if (error.error != QJsonParseError::NoError ||
      (!result.isObject() && !result.isArray())) {
    finish(failure("invalid_response"));
    return;
  }
  const auto canonical = result.toJson(QJsonDocument::Compact);
  if (reflected(canonical, credentials)) {
    finish(failure("unsafe_response"));
    return;
  }
  QJsonObject output{{"untrusted_content", true},
                     {"result", result.isObject()
                                    ? QJsonValue(result.object())
                                    : QJsonValue(result.array())}};
  if (apiRequest)
    output.insert("http_status", status);
  finish(output);
}

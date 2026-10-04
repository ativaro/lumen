// SPDX-License-Identifier: MIT
#include "bookstack.h"
#include "vault.h"
#include <QStringDecoder>
#include <cmath>
#include <sys/stat.h>
#include <unistd.h>

namespace {
bool integer(const QJsonValue &value, int low, int high) {
  const double n = value.toDouble(-1);
  return value.isDouble() && std::isfinite(n) && n == std::floor(n) &&
         n >= low && n <= high;
}
bool reflected(const QByteArray &data, const QStringList &secrets) {
  for (const auto &secret : secrets) {
    const auto bytes = secret.toUtf8();
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
  for (auto *timer : {&expiry, &deadline, &framing})
    timer->setSingleShot(true);
  connect(&expiry, &QTimer::timeout, this, &VaultAccess::revoke);
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
bool VaultAccess::armed() const {
  return !entryId.isEmpty() && elapsed.isValid() && elapsed.elapsed() < 300000;
}
bool VaultAccess::arm(const QString &id, const QUrl &url) {
  revoke();
  if (id.isEmpty() || BookStack::origin(url.toString()).isEmpty())
    return false;
  entryId = id;
  base = BookStack::origin(url.toString());
  elapsed.start();
  expiry.start(300000);
  emit changed();
  return true;
}
void VaultAccess::revoke() {
  ++epoch;
  entryId.clear();
  base.clear();
  expiry.stop();
  elapsed.invalidate();
  finish(failure("access_revoked"));
  emit changed();
}
void VaultAccess::cancel() {
  ++epoch;
  deadline.stop();
  framing.stop();
  if (prompt) {
    prompt->disconnect(this);
    // A user-confirmed write already dispatched to Rust cannot be undone by
    // losing the IPC client. Let its native dialog finish; lock still closes
    // it.
    if (!prompt->property("saving").toBool()) {
      prompt->reject();
      prompt->deleteLater();
    }
    prompt.clear();
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
  wipe(frame);
  wipe(response);
  requested = false;
}
void VaultAccess::finish(const QJsonObject &result) {
  QJsonObject delivered = result;
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
  if (document.object().value("operation") == "store") {
    const auto args = document.object();
    for (auto it = args.begin(); it != args.end(); ++it)
      if (it.key() != "operation" && it.key() != "title" &&
          it.key() != "kind") {
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
    requested = true;
    framing.stop();
    if (QApplication::activeModalWidget() || !store) {
      finish(failure("vault_busy"));
      return;
    }
    entryId.clear();
    base.clear();
    expiry.stop();
    elapsed.invalidate();
    emit changed();
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
    finish(failure("open_vault_and_enable_bookstack"));
    return;
  }
  if (BookStack::route(base, document.object()).isEmpty()) {
    finish(failure("invalid_request"));
    return;
  }
  requested = true;
  framing.stop();
  confirm(document.object());
}
void VaultAccess::confirm(const QJsonObject &args) {
  if (QApplication::activeModalWidget()) {
    finish(failure("vault_busy"));
    return;
  }
  auto *dialog = new QDialog(window);
  prompt = dialog;
  dialog->setWindowTitle(
      tx("BookStack-Zugriff bestätigen", "Confirm BookStack access"));
  auto *layout = new QVBoxLayout(dialog);
  auto *text = new QLabel(
      tx("Ein lokales Programm möchte BookStack lesen. Der Aufrufer ist nicht "
         "als Lumen verifiziert.\n\n",
         "A local program wants to read BookStack. The caller is not verified "
         "as Lumen.\n\n") +
      base.toString(QUrl::FullyEncoded) + "\n" +
      QString::fromUtf8(QJsonDocument(args).toJson(QJsonDocument::Indented)) +
      tx("\nDie Antwort wird an das anfragende Programm zurückgegeben und kann "
         "an dein Cloud-Modell gelangen. Der Token wird nur zur Anmeldung bei "
         "diesem Dienst verwendet.",
         "\nThe response is returned to the requesting program and may reach "
         "your cloud model. The token is used only to authenticate to this "
         "service."));
  text->setTextFormat(Qt::PlainText);
  text->setWordWrap(true);
  text->setMinimumWidth(500);
  layout->addWidget(text);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel);
  auto *allow =
      buttons->addButton(tx("Einmal lesen erlauben", "Allow one read"),
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
  auto field = [&fields](const QString &key) {
    const int i = fields.indexOf(key);
    return i >= 0 && i % 2 == 0 ? fields.value(i + 1) : QString();
  };
  const auto configured = BookStack::origin(field("LumenApiBase"));
  QString id = field("LumenApiTokenId"), secret = field("Password");
  const bool valid = configured == base && field("LumenType") == "token" &&
                     field("LumenTrash") != "1" && BookStack::credential(id) &&
                     BookStack::credential(secret);
  for (auto &value : fields)
    wipe(value);
  if (requestEpoch != epoch || !peer || !armed() || !valid) {
    wipe(id);
    wipe(secret);
    if (requestEpoch == epoch)
      finish(failure("access_revoked_or_invalid_profile"));
    return;
  }
  credentials = {id, secret, id + ":" + secret};
  network = new QNetworkAccessManager(this);
  network->setProxy(QNetworkProxy::NoProxy);
  network->setCache(nullptr);
  QNetworkRequest request(BookStack::route(base, args));
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
  request.setRawHeader("Accept", "application/json");
  request.setRawHeader("Accept-Encoding", "identity");
  QByteArray auth = "Token " + id.toUtf8() + ":" + secret.toUtf8();
  request.setRawHeader("Authorization", auth);
  reply = network->get(request);
  wipe(auth);
  wipe(id);
  wipe(secret);
  reply->setReadBufferSize(65536);
  QTimer::singleShot(20000, reply, [this, requestEpoch] {
    if (epoch == requestEpoch)
      finish(failure("network_timeout"));
  });
  connect(reply, &QNetworkReply::readyRead, this, [this, requestEpoch] {
    if (epoch != requestEpoch || !reply)
      return;
    response += reply->read(BookStack::MaxBody + 1 - response.size());
    if (response.size() > BookStack::MaxBody)
      finish(failure("response_too_large"));
  });
  connect(reply, &QNetworkReply::finished, this, [this, requestEpoch, args] {
    if (epoch != requestEpoch || !reply)
      return;
    if (!armed()) {
      finish(failure("access_revoked"));
      return;
    }
    const int status =
        reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (reply->error() != QNetworkReply::NoError || status != 200) {
      finish(failure(status == 401 || status == 403 ? "service_denied"
                                                    : "https_request_failed"));
      return;
    }
    if (!reply->header(QNetworkRequest::ContentTypeHeader)
             .toString()
             .startsWith("application/json") ||
        (!reply->rawHeader("Content-Encoding").isEmpty() &&
         reply->rawHeader("Content-Encoding") != "identity")) {
      finish(failure("invalid_response"));
      return;
    }
    response += reply->read(BookStack::MaxBody + 1 - response.size());
    finish(BookStack::project(args, response, credentials));
  });
}

// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "passkey.h"
#include "vault.h"

static QString randomValue() {
  QByteArray data(32, Qt::Uninitialized);
  for (int i = 0; i < data.size(); i += 4) {
    auto v = QRandomGenerator::system()->generate();
    memcpy(data.data() + i, &v, 4);
  }
  return QString::fromLatin1(data.toBase64(QByteArray::Base64UrlEncoding | QByteArray::OmitTrailingEquals));
}
PasskeyBridge::PasskeyBridge(QJsonObject metadata, bool enroll, QObject *parent)
    : QObject(parent), config(std::move(metadata)) {
  token = randomValue().toLatin1();
  if (enroll) {
    config = {{"salt", randomValue()}, {"binding", randomValue()}, {"language", config["language"]}};
  }
  config["enroll"] = enroll;
  config["challenge"] = randomValue();
  server.setMaxPendingConnections(4);
  if (!server.listen(QHostAddress::LocalHost, 0)) return;
  host = "localhost:" + QByteArray::number(server.serverPort());
  origin = "http://" + host;
  connect(&server, &QTcpServer::newConnection, this, [this] {
    while (server.hasPendingConnections()) {
      auto *socket = server.nextPendingConnection();
      if (findChildren<QTcpSocket *>().size() >= 8) { socket->abort(); socket->deleteLater(); continue; }
      socket->setParent(this);
      socket->setReadBufferSize(24577);
      QTimer::singleShot(5000, socket, &QTcpSocket::abort);
      connect(socket, &QTcpSocket::readyRead, this, [this, socket] { read(socket); });
      connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
    }
  });
  lifetime.setSingleShot(true);
  connect(&lifetime, &QTimer::timeout, this, [this] { stop(); emit failed(); });
  lifetime.start(120000);
}
PasskeyBridge::~PasskeyBridge() { stop(); }
QUrl PasskeyBridge::url() const {
  return server.isListening() ? QUrl(QString::fromLatin1(origin + "/#" + token)) : QUrl();
}
void PasskeyBridge::stop() {
  finished = true;
  lifetime.stop(); server.close(); wipe(token);
  for (auto *socket : findChildren<QTcpSocket *>()) socket->abort();
}
void PasskeyBridge::reply(QTcpSocket *socket, int status, const QByteArray &body, const QByteArray &type) {
  socket->write("HTTP/1.1 " + QByteArray::number(status) + " Result\r\nContent-Type: " + type +
                "\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nX-Content-Type-Options: nosniff\r\n"
                "Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'\r\n"
                "Connection: close\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
  socket->disconnectFromHost();
}
void PasskeyBridge::read(QTcpSocket *socket) {
  if (finished) { socket->abort(); return; }
  auto data = socket->peek(24577);
  if (data.size() > 24576) { socket->abort(); return; }
  const auto end = data.indexOf("\r\n\r\n");
  if (end < 0) return;
  const auto lines = data.left(end).split('\n');
  const auto first = lines.value(0).trimmed().split(' ');
  QMap<QByteArray, QByteArray> headers;
  for (int i = 1; i < lines.size(); ++i) {
    const auto line = lines[i].trimmed();
    const auto colon = line.indexOf(':');
    const auto name = line.left(colon).toLower();
    if (colon <= 0 || headers.contains(name)) { socket->abort(); return; }
    headers[name] = line.mid(colon + 1).trimmed();
  }
  if (first.size() != 3 || first[2] != "HTTP/1.1" || headers.value("host") != host ||
      headers.contains("transfer-encoding")) { reply(socket, 403, "{}"); return; }
  bool ok = true;
  const auto length = headers.contains("content-length") ? headers["content-length"].toInt(&ok) : 0;
  if (!ok || length < 0 || length > 16384) { reply(socket, 400, "{}"); return; }
  if (data.size() < end + 4 + length) return;
  if (data.size() != end + 4 + length) { reply(socket, 400, "{}"); return; }
  data = socket->readAll();
  if (first[0] == "GET" && length == 0 && (first[1] == "/" || first[1] == "/bridge.js" || first[1] == "/bridge.css")) {
    QFile file(":/passkey/" + (first[1] == "/" ? QString("index.html") : QString::fromLatin1(first[1].mid(1))));
    if (!file.open(QIODevice::ReadOnly)) { reply(socket, 500, "{}"); return; }
    reply(socket, 200, file.readAll(), first[1] == "/" ? "text/html; charset=utf-8" : first[1].endsWith(".js") ? "text/javascript" : "text/css");
    return;
  }
  if (headers.value("x-lumen-token") != token ||
      (headers.contains("origin") && headers["origin"] != origin)) { reply(socket, 403, "{}"); wipe(data); return; }
  if (first[0] == "GET" && first[1] == "/config" && length == 0) {
    reply(socket, 200, QJsonDocument(config).toJson(QJsonDocument::Compact)); return;
  }
  if (first[0] != "POST" || first[1] != "/complete" || headers.value("origin") != origin ||
      headers.value("content-type") != "application/json") { reply(socket, 403, "{}"); wipe(data); return; }
  auto payload = data.mid(end + 4); wipe(data);
  auto value = QJsonDocument::fromJson(payload).object(); wipe(payload);
  auto key = value.take("key").toString();
  const auto credential = value["credential"].toString();
  const auto auth = QByteArray::fromBase64(value["authData"].toString().toLatin1(), QByteArray::Base64UrlEncoding);
  const auto client = QJsonDocument::fromJson(QByteArray::fromBase64(value["clientData"].toString().toLatin1(), QByteArray::Base64UrlEncoding)).object();
  const auto rpHash = QCryptographicHash::hash("localhost", QCryptographicHash::Sha256);
  static const QRegularExpression keyPattern("^[0-9a-f]{64}$"), idPattern("^[A-Za-z0-9_-]{1,2048}$");
  const bool valid = keyPattern.match(key).hasMatch() && idPattern.match(credential).hasMatch() &&
      (config["enroll"].toBool() || credential == config["credential"].toString()) &&
      auth.size() >= 37 && auth.left(32) == rpHash && (quint8(auth[32]) & 5) == 5 &&
      client["type"] == "webauthn.get" && client["challenge"] == config["challenge"] &&
      client["origin"].toString().toLatin1() == origin && !client["crossOrigin"].toBool();
  if (!valid) { wipe(key); reply(socket, 400, "{}"); return; }
  finished = true; server.close(); lifetime.stop(); wipe(token);
  reply(socket, 200, "{}");
  emit completed(key, credential); wipe(key);
}

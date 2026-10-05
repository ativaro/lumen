// SPDX-License-Identifier: MIT
#include "bookstack.h"
#include "connection.h"
#include "vault.h"
#include <QtTest>

class LocalHttps : public QTcpServer {
public:
  QSslCertificate certificate;
  QSslKey key;
  QByteArray body = R"({"data":[{"id":1,"name":"Public guide"}],"total":1})";
  QByteArray status = "200 OK";
  QByteArray extra;
  QByteArray received;
  int requests = 0;
  bool mcpMode = false, stream = false, wrongId = false, holdCall = false;
  QList<QByteArray> history;
  QStringList methods;
  void incomingConnection(qintptr descriptor) override {
    auto *socket = new QSslSocket(this);
    socket->setSocketDescriptor(descriptor);
    socket->setLocalCertificate(certificate);
    socket->setPrivateKey(key);
    socket->setPeerVerifyMode(QSslSocket::VerifyNone);
    connect(socket, &QSslSocket::readyRead, socket, [this, socket] {
      auto buffer =
          socket->property("buffer").toByteArray() + socket->readAll();
      socket->setProperty("buffer", buffer);
      if (!buffer.contains("\r\n\r\n") || socket->property("answered").toBool())
        return;
      const int headEnd = buffer.indexOf("\r\n\r\n");
      const auto head = buffer.left(headEnd);
      int length = 0;
      for (const auto &line : head.split('\n'))
        if (line.toLower().startsWith("content-length:"))
          length = line.mid(15).trimmed().toInt();
      if (buffer.size() < headEnd + 4 + length)
        return;
      socket->setProperty("answered", true);
      received = buffer;
      history.append(buffer);
      ++requests;
      if (mcpMode) {
        const auto rpc =
            QJsonDocument::fromJson(buffer.mid(headEnd + 4, length)).object();
        const auto method = rpc["method"].toString();
        methods.append(method);
        if (method == "notifications/initialized") {
          socket->write("HTTP/1.1 202 Accepted\r\nContent-Length: "
                        "0\r\nConnection: close\r\n\r\n");
          socket->disconnectFromHost();
          return;
        }
        if (method == "tools/call" && holdCall)
          return;
        const QJsonObject value =
            method == "initialize"
                ? QJsonObject{{"protocolVersion", "2025-06-18"},
                              {"capabilities",
                               QJsonObject{{"tools", QJsonObject{}}}},
                              {"serverInfo", QJsonObject{{"name", "synthetic"},
                                                         {"version", "1"}}}}
                : QJsonObject{
                      {"tools",
                       QJsonArray{QJsonObject{
                           {"name", "example"},
                           {"inputSchema", QJsonObject{{"type", "object"}}}}}}};
        auto data =
            QJsonDocument(QJsonObject{{"jsonrpc", "2.0"},
                                      {"id", wrongId ? 99 : rpc["id"].toInt()},
                                      {"result", value}})
                .toJson(QJsonDocument::Compact);
        if (stream)
          data = "event: message\r\ndata: " + data + "\r\n\r\n";
        socket->write(
            "HTTP/1.1 200 OK\r\nContent-Type: " +
            QByteArray(stream ? "text/event-stream" : "application/json") +
            "\r\nConnection: close\r\nMcp-Session-Id: "
            "synthetic-session\r\nContent-Length: " +
            QByteArray::number(data.size()) + "\r\n\r\n" + data);
        socket->disconnectFromHost();
        return;
      }
      socket->write("HTTP/1.1 " + status +
                    "\r\nContent-Type: application/json\r\nConnection: "
                    "close\r\nContent-Length: " +
                    QByteArray::number(body.size()) + "\r\n" + extra + "\r\n" +
                    body);
      socket->disconnectFromHost();
    });
    connect(socket, &QSslSocket::disconnected, socket, &QObject::deleteLater);
    socket->startServerEncryption();
  }
};
class AccessTest : public QObject {
  Q_OBJECT
  QTemporaryDir config;
  static QJsonObject result(QLocalSocket &client) {
    return QJsonDocument::fromJson(client.readAll()).object();
  }
  static void send(QLocalSocket &client, const QString &runtime,
                   const QByteArray &request) {
    client.connectToServer(runtime + "/lumen-vault-access");
    QVERIFY(client.waitForConnected(1000));
    client.write(request + '\n');
    client.flush();
  }
private slots:
  void initTestCase() {
    QSettings::setPath(QSettings::NativeFormat, QSettings::UserScope,
                       config.path());
  }
  void fixedRoutesAndInputs() {
    const auto base = BookStack::origin("https://docs.example:8443/");
    QVERIFY(!base.isEmpty());
    for (const auto *bad : {"http://example", "https://user:pw@example",
                            "https://example/a", "https://example/?q=x",
                            "https://example/#fragment", "https://example:0"})
      QVERIFY(BookStack::origin(bad).isEmpty());
    QCOMPARE(
        BookStack::route(base, {{"operation", "read_page"}, {"page_id", 27}})
            .toString(),
        QString("https://docs.example:8443/api/pages/27"));
    QVERIFY(BookStack::route(base, {{"operation", "delete"}}).isEmpty());
    QVERIFY(
        BookStack::route(base, {{"operation", "check"}, {"token", "SYNTHETIC"}})
            .isEmpty());
    QVERIFY(
        BookStack::route(base, {{"operation", "read_page"}, {"page_id", 1.2}})
            .isEmpty());
    QVERIFY(BookStack::route(base, {{"operation", "search"}, {"query", ""}})
                .isEmpty());
    QVERIFY(BookStack::route(base, {{"operation", "list_books"}, {"limit", 21}})
                .isEmpty());
    const auto url = BookStack::route(
        base, {{"operation", "search"}, {"query", "日本語 & count=100"}});
    QCOMPARE(QUrlQuery(url).queryItemValue("query", QUrl::FullyDecoded),
             QString("日本語 & count=100"));
    QCOMPARE(QUrlQuery(url).queryItemValue("count"), QString("10"));
    QVERIFY(!BookStack::credential("SYNTHETIC\r\nHeader"));
  }
  void genericProfilesAndConfinement() {
    QStringList fields{"LumenType",    "token",
                       "URL",          "https://api.example/api",
                       "UserName",     "example-id",
                       "Password",     "eyJhbGc.eyJpc3M.signature_123",
                       "LumenApiAuth", "bearer"};
    QVERIFY(VaultConnection::problem(fields).isEmpty());
    auto profile = VaultConnection::settings(fields);
    QCOMPARE(profile["connector"].toString(), QString("api"));
    QCOMPARE(profile["endpoint"].toString(),
             QString("https://api.example/api"));
    QCOMPARE(VaultConnection::headers(fields).first().second,
             QByteArray("Bearer eyJhbGc.eyJpc3M.signature_123"));
    QCOMPARE(VaultConnection::route(
                 profile, {{"operation", "api_get"}, {"path", "/status"}})
                 .path(),
             QString("/api/status"));
    for (const auto *path :
         {"//evil.test/", "https://evil.test", "/../out", "/%2e%2e/out",
          "/a/../../out", "/ok\n", "/a%2fb", "/a\\b"})
      QVERIFY2(VaultConnection::route(
                   profile, {{"operation", "api_get"}, {"path", path}})
                   .isEmpty(),
               path);
    fields << "LumenApiBase" << "http://bad.example";
    QCOMPARE(VaultConnection::problem(fields),
             QString("endpoint")); // Do not silently fall back from populated
                                   // invalid address.
    fields.removeLast();
    fields.removeLast();
    fields[fields.indexOf("LumenApiAuth") + 1] = "headers";
    fields << "LumenApiIdHeader" << "X-Token-ID" << "LumenApiSecretHeader"
           << "X-Token-Secret";
    QVERIFY(VaultConnection::problem(fields).isEmpty());
    QCOMPARE(VaultConnection::headers(fields).size(), 2);
    fields[fields.indexOf("LumenApiSecretHeader") + 1] = "hOsT";
    QCOMPARE(VaultConnection::problem(fields), QString("secret_header"));
    fields[fields.indexOf("LumenApiSecretHeader") + 1] = "Host\n";
    QCOMPARE(VaultConnection::problem(fields), QString("secret_header"));
    fields[fields.indexOf("LumenApiSecretHeader") + 1] = "x-token-id";
    QCOMPARE(VaultConnection::problem(fields), QString("id_header"));
    fields[fields.indexOf("LumenApiSecretHeader") + 1] = "X-Token-Secret";
    fields[fields.indexOf("Password") + 1] = "bad\r\nHeader: injection";
    QCOMPARE(VaultConnection::problem(fields), QString("secret"));
    QCOMPARE(VaultConnection::rpcResponse(
                 R"({"jsonrpc":"2.0","id":9,"result":{}})", false, 1)["error"]
                 .toString(),
             QString("invalid_rpc"));
    QCOMPARE(
        VaultConnection::rpcResponse(
            R"({"jsonrpc":"2.0","id":1,"method":"sampling/createMessage"})",
            false, 1)["error"]
            .toString(),
        QString("unsupported_server_request"));
    QCOMPARE(VaultConnection::rpcResponse(
                 "data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n", true,
                 1)["result"]
                 .toObject(),
             QJsonObject{});
  }
  void sseFramingAndLimits() {
    const QByteArray event =
        "data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}";
    QVERIFY(VaultConnection::rpcResponse(event + "\r\r", true, 1)
                .contains("result"));
    QVERIFY(VaultConnection::rpcResponse(event + "\r", true, 1).isEmpty());
    QVERIFY(VaultConnection::rpcResponse(
                QByteArray::fromHex("efbbbf") + event + "\r\n\r\n", true, 1)
                .contains("result"));
    QVERIFY(VaultConnection::rpcResponse(QByteArray(130, '\n') + event + "\n\n",
                                         true, 1)
                .contains("error"));
  }
  void responseProjectionAndReflection() {
    const QString canary = "SYNTHETIC_SECRET_123";
    const QJsonObject args{{"operation", "read_page"}, {"page_id", 5}};
    auto body = [](QString html) {
      return QJsonDocument(QJsonObject{{"id", 5},
                                       {"name", "Guide"},
                                       {"html", html},
                                       {"unapproved", "omitted"}})
          .toJson();
    };
    const auto ok = BookStack::project(
        args, body("<h1>Heading</h1><p>Public content</p>"), {canary});
    QVERIFY(!ok.contains("error"));
    QVERIFY(ok.value("untrusted_content").toBool());
    QVERIFY(ok.value("text").toString().contains("Public content"));
    QVERIFY(!QJsonDocument(ok).toJson().contains("unapproved"));
    QCOMPARE(BookStack::project(args, body(canary), {canary})
                 .value("error")
                 .toString(),
             QString("unsafe_response"));
    QCOMPARE(BookStack::project(
                 args, body(QString::fromLatin1(canary.toUtf8().toBase64())),
                 {canary})
                 .value("error")
                 .toString(),
             QString("unsafe_response"));
    QString escaped;
    for (QChar c : canary)
      escaped += "&#" + QString::number(c.unicode()) + ";";
    QCOMPARE(BookStack::project(args, body(escaped), {canary})
                 .value("error")
                 .toString(),
             QString("unsafe_response"));
    QCOMPARE(BookStack::project(args, QByteArray(BookStack::MaxBody + 1, 'x'),
                                {canary})
                 .value("error")
                 .toString(),
             QString("unsafe_response"));
  }
  void invalidIPCAndRevokedApproval() {
    QWidget window;
    QTemporaryDir runtime;
    int reads = 0;
    VaultAccess access(
        &window,
        [&](QString, auto callback) {
          ++reads;
          callback({});
        },
        true);
    QVERIFY(access.listen(runtime.path()));
    QLocalSocket absent;
    send(absent, runtime.path(), R"({"operation":"check"})");
    QTRY_VERIFY(absent.bytesAvailable());
    QCOMPARE(result(absent).value("error").toString(),
             QString("open_vault_and_enable_connection"));
    QVERIFY(access.arm("synthetic-id",
                       BookStack::origin("https://example.invalid")));
    QLocalSocket extra;
    send(extra, runtime.path(), R"({"operation":"check","method":"DELETE"})");
    QTRY_VERIFY(extra.bytesAvailable());
    QCOMPARE(result(extra).value("error").toString(),
             QString("invalid_request"));
    QLocalSocket large;
    send(large, runtime.path(), QByteArray(5000, 'x'));
    QTRY_VERIFY(large.bytesAvailable());
    QCOMPARE(result(large).value("error").toString(),
             QString("invalid_request"));
    QLocalSocket request;
    send(request, runtime.path(), R"({"operation":"check"})");
    QTRY_VERIFY(QApplication::activeModalWidget());
    QCOMPARE(reads, 0);
    access.revoke();
    QTRY_VERIFY(request.bytesAvailable());
    QCOMPARE(result(request).value("error").toString(),
             QString("access_revoked"));
    QCOMPARE(reads, 0);
    QVERIFY(!access.armed());
  }
  void savingCancellationIsNotReportedAsUnsaved() {
    QWidget window;
    QTemporaryDir runtime;
    VaultAccess access(
        &window, [](QString, auto callback) { callback({}); }, true);
    access.setStore([&](const QJsonObject &) {
      auto *dialog = new QDialog(&window);
      dialog->setAttribute(Qt::WA_DeleteOnClose);
      dialog->setProperty("saving", true);
      dialog->open();
      return dialog;
    });
    QVERIFY(access.listen(runtime.path()));
    QLocalSocket client;
    send(client, runtime.path(),
         R"({"operation":"store","title":"Example","kind":"token"})");
    QTRY_VERIFY(QApplication::activeModalWidget());
    auto dialog = QPointer<QDialog>(
        qobject_cast<QDialog *>(QApplication::activeModalWidget()));
    access.revoke();
    QTRY_VERIFY(client.bytesAvailable());
    QCOMPARE(result(client).value("error").toString(),
             QString("save_outcome_unknown"));
    QVERIFY(dialog); // A dispatched save is allowed to complete locally.
    dialog->accept();
    QTRY_VERIFY(!dialog);
  }
  void staleSecretReplyAfterRevoke() {
    QWidget window;
    QTemporaryDir runtime;
    std::function<void(QStringList)> pending;
    VaultAccess access(
        &window, [&](QString, auto callback) { pending = callback; }, true);
    QVERIFY(access.listen(runtime.path()));
    QVERIFY(access.arm("synthetic-id",
                       BookStack::origin("https://example.invalid")));
    QLocalSocket client;
    send(client, runtime.path(), R"({"operation":"check"})");
    QTRY_VERIFY(QApplication::activeModalWidget());
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QVERIFY(bool(pending));
    access.revoke();
    QVERIFY(access.arm("new-id", BookStack::origin("https://other.invalid")));
    pending({"Password", "SYNTHETIC_SECRET_123", "LumenApiTokenId",
             "SYNTHETIC_ID_123", "LumenApiBase", "https://example.invalid",
             "LumenType", "token"});
    QTRY_VERIFY(client.bytesAvailable());
    QVERIFY(!client.readAll().contains("SYNTHETIC"));
    QVERIFY(!access.findChild<QNetworkAccessManager *>());
  }
  void multipleConnectionsRequireReferenceAndRevalidatePermission() {
    QWidget window;
    QTemporaryDir runtime;
    QString readId;
    std::function<void(QStringList)> pending;
    VaultAccess access(
        &window,
        [&](QString id, auto callback) {
          readId = id;
          pending = callback;
        },
        true);
    QVERIFY(access.listen(runtime.path()));
    const QStringList fields{
        "LumenType",           "token",    "LumenApiEnabled", "1", "URL",
        "https://api.example", "Password", "SYNTHETIC_SECRET"};
    const auto profile = VaultConnection::settings(fields);
    access.setConnections({{"a", profile}, {"b", profile}});
    QLocalSocket ambiguous;
    send(ambiguous, runtime.path(),
         R"({"operation":"api_get","path":"/status"})");
    QTRY_VERIFY(ambiguous.bytesAvailable());
    QCOMPARE(result(ambiguous)["error"].toString(),
             QString("connection_reference_required"));
    QVERIFY(readId.isEmpty());
    QLocalSocket wrong;
    send(wrong, runtime.path(),
         R"({"operation":"api_get","reference":"vault:not-enabled"})");
    QTRY_VERIFY(wrong.bytesAvailable());
    QCOMPARE(result(wrong)["error"].toString(),
             QString("connection_not_enabled"));
    QVERIFY(!QApplication::activeModalWidget());
    QLocalSocket selected;
    send(selected, runtime.path(),
         R"({"operation":"api_get","reference":"vault:b","path":"/status"})");
    QTRY_VERIFY(QApplication::activeModalWidget());
    QVERIFY(
        readId.isEmpty()); // Merely selecting a reference never reads a secret.
    QString approval;
    for (auto *label :
         QApplication::activeModalWidget()->findChildren<QLabel *>())
      approval += label->text();
    QVERIFY(approval.contains("vault:b"));
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QCOMPARE(readId, QString("b"));
    auto revoked = fields;
    revoked[revoked.indexOf("LumenApiEnabled") + 1] = "0";
    pending(revoked);
    QTRY_VERIFY(selected.bytesAvailable());
    QCOMPARE(result(selected)["error"].toString(),
             QString("access_revoked_or_invalid_profile"));
    QVERIFY(!access.findChild<QNetworkAccessManager *>());
    QMap<QString, QJsonObject> many;
    for (int i = 0; i < 43; ++i)
      many.insert(QString::number(i).rightJustified(3, '0'), profile);
    access.setConnections(many);
    QCOMPARE(access.connection()["connections"].toArray().size(), 20);
    QCOMPARE(access.connection()["next_offset"].toInt(), 20);
    QCOMPARE(access.connection(20)["next_offset"].toInt(), 40);
    QCOMPARE(access.connection(40)["connections"].toArray().size(), 3);
    QVERIFY(access.connection(40)["next_offset"].isNull());
    QVERIFY(!access.connection().contains("expires_in_seconds"));
    access.revoke();
    QVERIFY(access.connection()["connections"].toArray().isEmpty());
  }
  void httpsOnlyApprovalAndBoundedResults() {
    QTemporaryDir runtime, certFiles;
    const QString keyPath = certFiles.path() + "/key.pem",
                  certPath = certFiles.path() + "/cert.pem";
    QProcess openssl;
    openssl.start("openssl",
                  {"req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout",
                   keyPath, "-out", certPath, "-days", "1", "-subj",
                   "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"});
    QVERIFY(openssl.waitForFinished(10000));
    QCOMPARE(openssl.exitCode(), 0);
    QFile certFile(certPath), keyFile(keyPath);
    QVERIFY(certFile.open(QIODevice::ReadOnly));
    QVERIFY(keyFile.open(QIODevice::ReadOnly));
    LocalHttps service;
    service.certificate = QSslCertificate(certFile.readAll());
    service.key = QSslKey(keyFile.readAll(), QSsl::Rsa);
    QVERIFY(service.listen(QHostAddress::LocalHost));
    const auto original = QSslConfiguration::defaultConfiguration();
    auto restore = qScopeGuard(
        [&] { QSslConfiguration::setDefaultConfiguration(original); });
    auto trusted = original;
    auto ca = trusted.caCertificates();
    ca.append(service.certificate);
    trusted.setCaCertificates(ca);
    const auto base = BookStack::origin("https://127.0.0.1:" +
                                        QString::number(service.serverPort()));
    QWidget window;
    int secretReads = 0;
    VaultAccess access(
        &window,
        [&](QString, auto callback) {
          ++secretReads;
          callback({"LumenApiEnabled", "1", "LumenType", "token",
                    "LumenApiBase", base.toString(), "LumenApiTokenId",
                    "SYNTHETIC_ID_123", "Password", "SYNTHETIC_SECRET_123"});
        },
        true);
    QVERIFY(access.listen(runtime.path()));
    QVERIFY(access.arm("synthetic", base));
    auto perform = [&](const QByteArray &request) -> QJsonObject {
      QLocalSocket client;
      send(client, runtime.path(), request);
      for (int i = 0; i < 100 && !QApplication::activeModalWidget(); ++i)
        QTest::qWait(10);
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      if (!dialog)
        return {{"test_error", "missing_dialog"}};
      dialog->accept();
      for (int i = 0; i < 500 && !client.bytesAvailable(); ++i)
        QTest::qWait(10);
      return result(client);
    };
    // Untrusted certificate: no HTTP request and no credentials transmitted.
    QCOMPARE(perform(R"({"operation":"check"})").value("error").toString(),
             QString("https_request_failed"));
    QCOMPARE(service.requests, 0);
    QSslConfiguration::setDefaultConfiguration(trusted);
    auto output = perform(R"({"operation":"list_books","limit":2})");
    QVERIFY2(output.contains("items"),
             qPrintable(QString::fromUtf8(QJsonDocument(output).toJson())));
    QCOMPARE(service.requests, 1);
    QVERIFY(service.received.startsWith(
        "GET /api/books?count=2&offset=0 HTTP/1.1"));
    QVERIFY(service.received.contains(
        "Authorization: Token SYNTHETIC_ID_123:SYNTHETIC_SECRET_123"));
    QVERIFY(!QJsonDocument(output).toJson().contains("SYNTHETIC"));
    output = perform(R"({"operation":"search","query":"C++ %41 & stuff"})");
    QVERIFY(output.contains("items"));
    QVERIFY(service.received.contains("query=C%2B%2B%20%2541%20%26%20stuff"));
    service.status = "302 Found";
    service.extra = "Location: http://127.0.0.1:9/stolen\r\n";
    QCOMPARE(perform(R"({"operation":"check"})").value("error").toString(),
             QString("https_request_failed"));
    QCOMPARE(service.requests, 3);
    service.status = "200 OK";
    service.extra.clear();
    service.body = R"({"data":[{"id":1,"name":"SYNTHETIC_SECRET_123"}]})";
    QCOMPARE(perform(R"({"operation":"list_books"})").value("error").toString(),
             QString("unsafe_response"));
    service.body = QByteArray(BookStack::MaxBody + 100, 'x');
    QCOMPARE(perform(R"({"operation":"check"})").value("error").toString(),
             QString("response_too_large"));
    // Generic API uses the same encrypted credential boundary, with a different
    // auth scheme.
    QStringList generic{"LumenApiEnabled",
                        "1",
                        "LumenType",
                        "token",
                        "URL",
                        base.toString() + "/service",
                        "Password",
                        "SYNTHETIC.JWT.SECRET",
                        "LumenApiAuth",
                        "bearer",
                        "LumenApiConnector",
                        "api"};
    QWidget genericWindow;
    VaultAccess genericAccess(
        &genericWindow, [&](QString, auto callback) { callback(generic); },
        true);
    QTemporaryDir genericRuntime;
    QVERIFY(genericAccess.listen(genericRuntime.path()));
    QVERIFY(genericAccess.arm("generic", VaultConnection::settings(generic)));
    auto genericPerform = [&](const QByteArray &request) -> QJsonObject {
      QLocalSocket client;
      send(client, genericRuntime.path(), request);
      for (int i = 0; i < 100 && !QApplication::activeModalWidget(); ++i)
        QTest::qWait(10);
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      if (!dialog)
        return {{"test_error", "no_prompt"}};
      dialog->accept();
      for (int i = 0; i < 500 && !client.bytesAvailable(); ++i)
        QTest::qWait(10);
      return result(client);
    };
    service.body = R"({"status":"ok","id":1})";
    generic << "UserName" << "id";
    QVERIFY(genericAccess.arm("generic", VaultConnection::settings(generic)));
    QCOMPARE(
        genericPerform(R"({"operation":"api_get","path":"/status"})")["result"]
            .toObject()["status"]
            .toString(),
        QString("ok"));
    QVERIFY(service.received.startsWith("GET /service/status HTTP/1.1"));
    QVERIFY(service.received.contains(
        "Authorization: Bearer SYNTHETIC.JWT.SECRET"));
    generic[generic.indexOf("LumenApiConnector") + 1] = "mcp";
    service.mcpMode = true;
    for (bool sse : {false, true}) {
      service.stream = sse;
      service.methods.clear();
      service.history.clear();
      QVERIFY(genericAccess.arm("generic", VaultConnection::settings(generic)));
      const auto response = genericPerform(R"({"operation":"mcp_tools"})");
      QVERIFY2(response.contains("result"),
               qPrintable(QString::fromUtf8(QJsonDocument(response).toJson())));
      QCOMPARE(service.methods,
               QStringList(
                   {"initialize", "notifications/initialized", "tools/list"}));
      QVERIFY(service.history[1].contains("Mcp-Session-Id: synthetic-session"));
      QVERIFY(service.history[2].toLower().contains(
          "mcp-protocol-version: 2025-06-18"));
      QVERIFY(!QJsonDocument(response).toJson().contains("synthetic-session"));
    }
    service.wrongId = true;
    QCOMPARE(genericPerform(R"({"operation":"mcp_tools"})")["error"].toString(),
             QString("invalid_mcp_response"));
    service.wrongId = false;
    service.holdCall = true;
    QLocalSocket mutation;
    send(mutation, genericRuntime.path(),
         R"({"operation":"mcp_call","name":"example","arguments":{}})");
    QTRY_VERIFY(QApplication::activeModalWidget());
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QTRY_COMPARE(service.methods.last(), QString("tools/call"));
    const int dispatched = service.methods.count("tools/call");
    genericAccess.revoke();
    QTRY_VERIFY(mutation.bytesAvailable());
    QCOMPARE(result(mutation)["error"].toString(),
             QString("operation_outcome_unknown"));
    QTest::qWait(50);
    QCOMPARE(service.methods.count("tools/call"), dispatched);
    service.mcpMode = false;
    const int prior = secretReads;
    QLocalSocket denied;
    send(denied, runtime.path(), R"({"operation":"check"})");
    QTRY_VERIFY(QApplication::activeModalWidget());
    QTest::keyClick(QApplication::activeModalWidget(), Qt::Key_Return);
    QTRY_VERIFY(denied.bytesAvailable());
    QCOMPARE(result(denied).value("error").toString(),
             QString("access_denied"));
    QCOMPARE(secretReads, prior);
  }
  void existingEntriesConnectWithoutWizardAndSelectionIsScoped() {
    QTemporaryDir root;
    Channel seed(root.path());
    bool created = false;
    seed.call({"create", "SYNTHETIC GENERIC MASTER"},
              [&](QStringList) { created = true; });
    QTRY_VERIFY_WITH_TIMEOUT(created, 10000);
    QString a, b;
    seed.call({"put", "", "Title", "A API", "LumenType", "token", "URL",
               "https://api.example", "UserName", "SYNTHETIC_ID", "Password",
               "SYNTHETIC_SECRET"},
              [&](QStringList result) { a = result.value(0); });
    QTRY_VERIFY_WITH_TIMEOUT(!a.isEmpty(), 10000);
    seed.call({"put", "", "Title", "B MCP", "LumenType", "token",
               "LumenApiConnector", "mcp", "URL", "https://mcp.example/mcp",
               "LumenApiAuth", "bearer", "Password", "SYNTHETIC.JWT.SECRET"},
              [&](QStringList result) { b = result.value(0); });
    QTRY_VERIFY_WITH_TIMEOUT(!b.isEmpty(), 10000);
    seed.stop();
    VaultWindow window(root.path());
    window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC GENERIC MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_COMPARE(window.findChild<QListWidget *>("entries")->count(), 2);
    auto *entries = window.findChild<QListWidget *>("entries");
    auto select = [&](const QString &id) {
      for (int i = 0; i < entries->count(); ++i)
        if (entries->item(i)->data(Qt::UserRole).toString() == id)
          entries->setCurrentRow(i);
    };
    auto *access = window.findChild<VaultAccess *>();
    auto *button = window.findChild<QPushButton *>("apiAccess");
    select(a);
    QTRY_VERIFY(button->isEnabled());
    QTest::mouseClick(button, Qt::LeftButton);
    QTRY_VERIFY(access->enabled(a));
    QVERIFY(!QApplication::activeModalWidget());
    const auto activeText = button->text();
    select(b);
    QVERIFY(button->text() != activeText);
    QVERIFY(access->enabled(a));
    QTest::mouseClick(button, Qt::LeftButton);
    QTRY_VERIFY(access->enabled(b));
    QCOMPARE(access->connection()["connections"].toArray().size(), 2);
    QVERIFY(!access->connection().contains("reference"));
    // A stale history reply must restore availability without opening a dialog.
    select(a);
    QPushButton *historyButton = nullptr;
    for (auto *candidate : window.findChildren<QPushButton *>())
      if (candidate->accessibleName() == "Versionsverlauf" ||
          candidate->accessibleName() == "Version history")
        historyButton = candidate;
    QVERIFY(historyButton);
    historyButton->click();
    select(b);
    QTRY_VERIFY(access->enabled(a) && access->enabled(b));
    QVERIFY(!QApplication::activeModalWidget());
    // Persist across a complete broker/window lock-unlock cycle.
    window.lock();
    QVERIFY(!access->armed());
    master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC GENERIC MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(access->enabled(a) && access->enabled(b), 10000);
    entries = window.findChild<QListWidget *>("entries");
    button = window.findChild<QPushButton *>("apiAccess");
    select(a);
    QTest::mouseClick(button, Qt::LeftButton);
    QTRY_VERIFY(!access->enabled(a) && access->enabled(b));
    auto *channel = window.findChild<Channel *>();
    bool changed = false;
    channel->call({"put", a, "Title", "A API", "URL", "http://api.example"},
                  [&](QStringList) { changed = true; });
    QTRY_VERIFY(changed);
    select(a);
    QTest::mouseClick(button, Qt::LeftButton);
    QTRY_VERIFY(
        window.findChild<QLabel *>("accessStatus")->text().contains("HTTPS"));
    QVERIFY(!QApplication::activeModalWidget());
    QVERIFY(access->enabled(b));
    // Disabled stays disabled after another unlock; invalid profile did not
    // enable it.
    window.lock();
    master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC GENERIC MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(access->enabled(b), 10000);
    QVERIFY(!access->enabled(a));
    // Persisted availability remains revocable even after the profile becomes
    // invalid.
    changed = false;
    channel->call({"put", b, "Title", "B MCP", "URL", "http://mcp.example"},
                  [&](QStringList) { changed = true; });
    QTRY_VERIFY(changed);
    window.lock();
    master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC GENERIC MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    entries = window.findChild<QListWidget *>("entries");
    QTRY_COMPARE(entries->count(), 2);
    button = window.findChild<QPushButton *>("apiAccess");
    select(b);
    QTRY_VERIFY(button->isEnabled());
    QVERIFY(!access->enabled(b));
    QCOMPARE(button->text(), activeText);
    button->click();
    QTRY_VERIFY(button->isEnabled());
    QVERIFY(button->text() != activeText);
    window.lock();
  }
  void nativeIntakeSavesOnlyReferenceAndLocks() {
    QTemporaryDir root, runtime;
    VaultWindow window(root.path());
    QVERIFY(window.startAccessServer(runtime.path()));
    window.show();
    auto *master = window.findChild<QLineEdit *>("master");
    master->setText("SYNTHETIC ACCESS MASTER");
    window.findChild<QLineEdit *>("confirm")->setText(
        "SYNTHETIC ACCESS MASTER");
    QTest::keyClick(master, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(window.unlocked(), 10000);
    QLocalSocket client;
    send(
        client, runtime.path(),
        R"({"operation":"store","title":"Test documentation","kind":"token"})");
    QTRY_VERIFY(window.findChild<QLineEdit *>("editPassword"));
    window.findChild<QLineEdit *>("editPassword")
        ->setText("SYNTHETIC_SECRET_123");
    window.findChild<QLineEdit *>("editURL")->setText(
        "https://example.invalid");
    auto *id = window.findChild<QLineEdit *>("editUserName");
    QCOMPARE(id->echoMode(), QLineEdit::Password);
    id->setText("SYNTHETIC_ID_123");
    QTest::mouseClick(window.findChild<QPushButton *>("save"), Qt::LeftButton);
    QTRY_VERIFY_WITH_TIMEOUT(client.bytesAvailable(), 10000);
    const auto saved = result(client);
    QCOMPARE(saved.keys(), QStringList({"reference", "saved"}));
    QVERIFY(saved.value("saved").toBool());
    QVERIFY(saved.value("reference").toString().startsWith("vault:"));
    QTRY_VERIFY(!window.findChild<QLineEdit *>("editPassword"));
    QTRY_COMPARE(window.findChild<QListWidget *>("entries")->count(), 1);
    window.findChild<QListWidget *>("entries")->setCurrentRow(0);
    QTest::mouseClick(window.findChild<QPushButton *>("apiAccess"),
                      Qt::LeftButton);
    QTRY_VERIFY(window.findChild<VaultAccess *>()->armed());
    QVERIFY(!QApplication::activeModalWidget());
    // An invalid endpoint is shown inline, never as a setup wizard.
    QLocalSocket second;
    send(second, runtime.path(),
         R"({"operation":"store","title":"Cancelled","kind":"login"})");
    QTRY_VERIFY(window.findChild<QLineEdit *>("editPassword"));
    window.findChild<QLineEdit *>("editPassword")->setText("SYNTHETIC_UNSAVED");
    window.lock();
    QTRY_VERIFY(second.bytesAvailable());
    QVERIFY(!result(second).value("saved").toBool());
    for (const auto &file : QDir(root.path()).entryList(QDir::Files)) {
      QFile f(root.path() + '/' + file);
      QVERIFY(f.open(QIODevice::ReadOnly));
      QVERIFY(!f.readAll().contains("SYNTHETIC"));
    }
    Channel reader(root.path());
    bool opened = false;
    reader.call({"open", "SYNTHETIC ACCESS MASTER"},
                [&](QStringList) { opened = true; });
    QTRY_VERIFY_WITH_TIMEOUT(opened, 10000);
    QStringList fields;
    reader.call({"edit", saved.value("reference").toString().mid(6)},
                [&](QStringList value) { fields = value; });
    QTRY_VERIFY_WITH_TIMEOUT(!fields.isEmpty(), 10000);
    QVERIFY(fields.contains("SYNTHETIC_SECRET_123"));
    QVERIFY(fields.contains("SYNTHETIC_ID_123"));
    QVERIFY(!fields.contains("SYNTHETIC_UNSAVED"));
    for (auto &field : fields)
      wipe(field);
  }
};
QTEST_MAIN(AccessTest)
#include "bookstack_test.moc"

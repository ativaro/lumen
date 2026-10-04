// SPDX-License-Identifier: MIT
#include "bookstack.h"
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
      socket->setProperty("answered", true);
      received = buffer;
      ++requests;
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
             QString("open_vault_and_enable_bookstack"));
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
          callback({"LumenType", "token", "LumenApiBase", base.toString(),
                    "LumenApiTokenId", "SYNTHETIC_ID_123", "Password",
                    "SYNTHETIC_SECRET_123"});
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
    window.findChild<QLineEdit *>("editLumenApiBase")
        ->setText("https://example.invalid");
    auto *id = window.findChild<QLineEdit *>("editLumenApiTokenId");
    QCOMPARE(id->echoMode(), QLineEdit::Password);
    id->setText("SYNTHETIC_ID_123");
    QTest::mouseClick(window.findChild<QPushButton *>("save"), Qt::LeftButton);
    QTRY_VERIFY_WITH_TIMEOUT(client.bytesAvailable(), 10000);
    const auto saved = result(client);
    QCOMPARE(saved.keys(), QStringList({"reference", "saved"}));
    QVERIFY(saved.value("saved").toBool());
    QVERIFY(saved.value("reference").toString().startsWith("vault:"));
    QTRY_VERIFY(!window.findChild<QLineEdit *>("editPassword"));
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

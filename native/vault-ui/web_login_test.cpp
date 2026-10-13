// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "web_login.h"
#include <QWebEngineCertificateError>
#include <QWebEngineProfile>
#include <QtNetwork>
#include <QtTest>
#include <sys/prctl.h>
#include <sys/resource.h>

class WebSite final : public QTcpServer {
public:
  QSslCertificate certificate;
  QSslKey key;
  int logins = 0, requests = 0;
  bool correctLogin = false;
  QByteArray content;
  QUrl url() const {
    return QUrl("https://127.0.0.1:" + QString::number(serverPort()) + "/");
  }
  void incomingConnection(qintptr fd) override {
    auto *s = new QSslSocket(this);
    s->setSocketDescriptor(fd);
    s->setLocalCertificate(certificate);
    s->setPrivateKey(key);
    s->setPeerVerifyMode(QSslSocket::VerifyNone);
    connect(s, &QSslSocket::readyRead, s, [this, s] {
      auto data = s->property("buffer").toByteArray() + s->readAll();
      s->setProperty("buffer", data);
      const auto end = data.indexOf("\r\n\r\n");
      if (end < 0 || s->property("done").toBool())
        return;
      int length = 0;
      for (const auto &line : data.left(end).split('\n'))
        if (line.toLower().startsWith("content-length:"))
          length = line.mid(15).trimmed().toInt();
      if (data.size() < end + 4 + length)
        return;
      s->setProperty("done", true);
      ++requests;
      QByteArray body = content;
      if (data.startsWith("POST /signed ")) {
        ++logins;
        correctLogin =
            data.mid(end + 4).contains("user=tester_X42") &&
            data.mid(end + 4).contains("password=synthetic-PASS-only_99");
        body = "<h1>Signed in</h1><label>Search<input id=q type=search "
               "value=DO_NOT_RETURN_INPUT></label><button "
               "onclick=\"document.querySelector('h1').textContent='Saved'\">"
               "Save</button>";
      }
      s->write("HTTP/1.1 200 OK\r\nContent-Type: text/html; "
               "charset=utf-8\r\nConnection: close\r\nContent-Length: " +
               QByteArray::number(body.size()) + "\r\n\r\n" + body);
      s->disconnectFromHost();
    });
    connect(s, &QSslSocket::disconnected, s, &QObject::deleteLater);
    s->startServerEncryption();
  }
};
class WebTest : public QObject {
  Q_OBJECT
  QTemporaryDir certs;
  QSslCertificate cert;
  QSslKey key;
  void configure(WebSite &site) {
    site.certificate = cert;
    site.key = key;
    QVERIFY(site.listen(QHostAddress::LocalHost));
    site.content =
        "<h1>Account</h1><form method=post "
        "action=/signed><label>Username<input name=user autocomplete=username "
        "value=HIDDEN_VALUE></label><label>Password<input name=password "
        "type=password autocomplete=current-password></label><button "
        "type=submit>Sign in</button></form>";
  }
  void trustFixture(VaultWeb &web) {
    connect(web.page(), &QWebEnginePage::certificateError, &web,
            [this](QWebEngineCertificateError e) {
              // Test-only trust of exactly this generated certificate.
              // Production never accepts TLS errors.
              if (e.certificateChain().contains(cert))
                e.acceptCertificate();
              else
                e.rejectCertificate();
            });
  }
  QJsonObject snapshot(VaultWeb &web) {
    QJsonObject out;
    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    connect(&timer, &QTimer::timeout, &loop, &QEventLoop::quit);
    timer.start(10000);
    web.inspect([&](QJsonObject value) {
      out = value;
      loop.quit();
    });
    if (out.isEmpty())
      loop.exec();
    return out;
  }
  QJsonObject act(VaultWeb &web, QJsonObject args) {
    QJsonObject out;
    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    connect(&timer, &QTimer::timeout, &loop, &QEventLoop::quit);
    timer.start(10000);
    web.act(args, [&](QJsonObject value) {
      out = value;
      loop.quit();
    });
    if (out.isEmpty())
      loop.exec();
    return out;
  }
  QJsonObject login(const QJsonObject &s) {
    QJsonObject a{{"operation", "web_login"}, {"snapshot", s["snapshot"]}};
    for (const auto &value : s["nodes"].toArray()) {
      auto n = value.toObject();
      if (n["type"] == "text")
        a["username_node"] = n["node"];
      if (n["type"] == "password")
        a["password_node"] = n["node"];
      if (n["type"] == "submit")
        a["submit_node"] = n["node"];
    }
    return a;
  }
private slots:
  void initTestCase() {
    QProcess openssl;
    openssl.start("openssl",
                  {"req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout",
                   certs.path() + "/key", "-out", certs.path() + "/cert",
                   "-days", "1", "-subj", "/CN=127.0.0.1", "-addext",
                   "subjectAltName=IP:127.0.0.1"});
    QVERIFY(openssl.waitForFinished(10000));
    QCOMPARE(openssl.exitCode(), 0);
    QFile c(certs.path() + "/cert"), k(certs.path() + "/key");
    QVERIFY(c.open(QIODevice::ReadOnly));
    QVERIFY(k.open(QIODevice::ReadOnly));
    cert = QSslCertificate(c.readAll());
    key = QSslKey(k.readAll(), QSsl::Rsa);
  }
  void boundaries() {
    QVERIFY(VaultWeb::validUrl(QUrl("https://example.test/login")));
    for (const auto &url :
         {"http://example.test/", "https://u:p@example.test/", "file:///tmp/a",
          "https://example.test/?token=a", "https://example.test/#token"})
      QVERIFY(!VaultWeb::validUrl(QUrl(url)));
    QVERIFY(!VaultWeb::sameOrigin(QUrl("https://example.test/"),
                                  QUrl("https://example.test:444/")));
    QVERIFY(!VaultWeb::sameOrigin(QUrl("https://example.test/"),
                                  QUrl("https://other.test/")));
    QVERIFY(VaultWeb::validRequest(
        {{"operation", "web_open"}, {"reference", "vault:x"}}));
    QVERIFY(!VaultWeb::validRequest({{"operation", "web_open"},
                                     {"reference", "vault:x"},
                                     {"password", "bad"}}));
    QVERIFY(
        !VaultWeb::validRequest({{"operation", "web_eval"}, {"session", "x"}}));
    for (auto value : {QByteArray("synthetic-secret"),
                       QByteArray("synthetic-secret").toBase64(),
                       QByteArray("synthetic-secret").toHex()})
      QVERIFY(VaultWeb::containsSecret(value, {"synthetic-secret"}));
  }
  void loginAndInteractWithoutCredentialExport() {
    WebSite site;
    configure(site);
    auto initialUrl = site.url();
    initialUrl.setPath("/tester_X42/account");
    VaultWeb web(nullptr, initialUrl, "tester_X42", "synthetic-PASS-only_99",
                 true);
    trustFixture(web);
    QVERIFY(web.page()->profile()->isOffTheRecord());
    QSignalSpy loaded(web.page(), &QWebEnginePage::loadFinished);
    web.start();
    QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
    QVERIFY(loaded.last()[0].toBool());
    auto s = snapshot(web);
    QCOMPARE(s["state"], "page_ready");
    const auto output = QJsonDocument(s).toJson();
    QVERIFY(!output.contains("HIDDEN_VALUE"));
    QVERIFY(!output.contains("synthetic-PASS"));
    auto args = login(s);
    auto replacement = snapshot(web);
    Q_UNUSED(replacement);
    QCOMPARE(act(web, args)["error"], "stale_snapshot");
    s = snapshot(web);
    args = login(s);
    loaded.clear();
    QCOMPARE(act(web, args)["state"], "login_submitted");
    QTRY_COMPARE_WITH_TIMEOUT(site.logins, 1, 15000);
    QVERIFY(site.correctLogin);
    QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
    s = snapshot(web);
    QVERIFY(s["text"].toString().contains("Signed in"));
    QVERIFY(!QJsonDocument(s).toJson().contains("DO_NOT_RETURN_INPUT"));
    QString field, button;
    for (const auto &v : s["nodes"].toArray()) {
      auto n = v.toObject();
      if (n["type"] == "search")
        field = n["node"].toString();
      if (n["tag"] == "button")
        button = n["node"].toString();
    }
    QCOMPARE(act(web, {{"operation", "web_fill"},
                       {"snapshot", s["snapshot"]},
                       {"node", field},
                       {"text", "ordinary search"}})["state"],
             "text_entered");
    s = snapshot(web);
    QVERIFY(!s["text"].toString().contains("ordinary search"));
    QCOMPARE(act(web, {{"operation", "web_click"},
                       {"snapshot", s["snapshot"]},
                       {"node", button}})["state"],
             "clicked");
    s = snapshot(web);
    QVERIFY(s["text"].toString().contains("Saved"));
    QCOMPARE(site.logins, 1);
  }
  void invalidTlsAndCrossOrigin() {
    WebSite site, other;
    configure(site);
    configure(other);
    {
      VaultWeb web(nullptr, site.url(), "tester_X42", "synthetic-PASS-only_99",
                   true);
      QSignalSpy loaded(web.page(), &QWebEnginePage::loadFinished);
      web.start();
      QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
      QVERIFY(!loaded.last()[0].toBool());
      QCOMPARE(snapshot(web)["error"], "web_page_unavailable");
      QCOMPARE(site.requests, 0);
    }
    site.content += "<img src='" + other.url().toEncoded() + "'><a href='" +
                    other.url().toEncoded() + "'>Other host</a>";
    VaultWeb web(nullptr, site.url(), "tester_X42", "synthetic-PASS-only_99",
                 true);
    trustFixture(web);
    QSignalSpy loaded(web.page(), &QWebEnginePage::loadFinished);
    web.start();
    QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
    auto s = snapshot(web);
    QString node;
    for (const auto &v : s["nodes"].toArray())
      if (v.toObject()["tag"] == "a")
        node = v.toObject()["node"].toString();
    QCOMPARE(act(web, {{"operation", "web_click"},
                       {"snapshot", s["snapshot"]},
                       {"node", node}})["error"],
             "cross_origin_blocked");
    QCOMPARE(other.requests, 0);
  }
  void unsafeFormsAndChangedControls() {
    WebSite site;
    configure(site);
    site.content.replace("method=post", "method=get");
    VaultWeb web(nullptr, site.url(), "tester_X42", "synthetic-PASS-only_99",
                 true);
    trustFixture(web);
    QSignalSpy loaded(web.page(), &QWebEnginePage::loadFinished);
    web.start();
    QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
    auto s = snapshot(web);
    QCOMPARE(act(web, login(s))["error"], "unsafe_login_form");
    QCOMPARE(site.logins, 0);
    s = snapshot(web);
    auto a = login(s);
    bool changed = false;
    web.page()->runJavaScript(
        "document.querySelector('button').textContent='Delete everything'",
        [&](const QVariant &) { changed = true; });
    QTRY_VERIFY(changed);
    QCOMPARE(act(web, a)["error"], "stale_snapshot");
    s = snapshot(web);
    a = login(s);
    QCOMPARE(act(web, {{"operation", "web_fill"},
                       {"snapshot", s["snapshot"]},
                       {"node", a["username_node"]},
                       {"text", "no"}})["error"],
             "credential_field_requires_local_input");
  }
  void reflectedCredentialsRedacted() {
    WebSite site;
    configure(site);
    site.content += "<p>synthetic-PASS-only_99</p>";
    VaultWeb web(nullptr, site.url(), "tester_X42", "synthetic-PASS-only_99",
                 true);
    trustFixture(web);
    QSignalSpy loaded(web.page(), &QWebEnginePage::loadFinished);
    web.start();
    QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
    const auto result = snapshot(web);
    QCOMPARE(result["state"], "page_ready");
    QVERIFY(!QJsonDocument(result).toJson().contains("synthetic-PASS-only_99"));
    QVERIFY(result["text"].toString().contains(QString::fromUtf8("[•••]")));
  }
  void ipcApprovalRevalidationAndRevocation() {
    QWidget window;
    QTemporaryDir runtime;
    WebSite site;
    configure(site);
    QStringList fields{"LumenType",
                       "login",
                       "LumenHidden",
                       "0",
                       "URL",
                       site.url().toString(),
                       "UserName",
                       "tester_X42",
                       "Password",
                       "synthetic-PASS-only_99"};
    VaultAccess access(
        &window,
        [&](QString, std::function<void(QStringList)> done) { done(fields); },
        true);
    access.setConnections(
        {}, {{"example", {{"title", "Synthetic website"}, {"kind", "login"}}}});
    QVERIFY(access.listen(runtime.path()));
    auto send = [&](QLocalSocket &c, QJsonObject a) {
      c.connectToServer(runtime.path() + "/lumen-vault-access");
      QVERIFY(c.waitForConnected());
      c.write(QJsonDocument(a).toJson(QJsonDocument::Compact) + '\n');
      c.flush();
    };
    const QJsonObject open{{"operation", "web_open"},
                           {"reference", "vault:example"}};
    QLocalSocket denied;
    send(denied, open);
    QTRY_VERIFY(QApplication::activeModalWidget());
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->reject();
    QTRY_VERIFY(denied.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(denied.readAll()).object()["error"],
             "access_denied");
    QVERIFY(!window.findChild<VaultWeb *>());
    QLocalSocket changed;
    send(changed, open);
    QTRY_VERIFY(QApplication::activeModalWidget());
    fields[5] = "https://changed.invalid/";
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QTRY_VERIFY(changed.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(changed.readAll()).object()["error"],
             "access_revoked_or_invalid_profile");
    QVERIFY(!window.findChild<VaultWeb *>());
    fields[5] = site.url().toString();
    QLocalSocket opened;
    send(opened, open);
    QTRY_VERIFY(QApplication::activeModalWidget());
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QTRY_VERIFY(opened.bytesAvailable());
    auto response = QJsonDocument::fromJson(opened.readAll()).object();
    QVERIFY(response["session"].isString());
    QCOMPARE(response["authentication_verified"], false);
    QPointer<VaultWeb> browser = window.findChild<VaultWeb *>();
    QVERIFY(browser);
    trustFixture(*browser);
    QSignalSpy loaded(browser->page(), &QWebEnginePage::loadFinished);
    browser->page()->load(site.url());
    QTRY_VERIFY_WITH_TIMEOUT(!loaded.isEmpty(), 15000);
    QLocalSocket inspected;
    send(inspected,
         {{"operation", "web_inspect"}, {"session", response["session"]}});
    QTRY_VERIFY(inspected.bytesAvailable());
    const auto inspectedResult =
        QJsonDocument::fromJson(inspected.readAll()).object();
    QVERIFY(!inspectedResult.contains("error"));
    QCOMPARE(inspectedResult["state"], "page_ready");
    auto action = login(inspectedResult);
    action["session"] = response["session"];
    QLocalSocket denyLogin;
    send(denyLogin, action);
    QTRY_VERIFY(QApplication::activeModalWidget());
    QCOMPARE(site.logins, 0);
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->reject();
    QTRY_VERIFY(denyLogin.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(denyLogin.readAll()).object()["error"],
             "access_denied");
    QCOMPARE(site.logins, 0);
    QLocalSocket doLogin;
    send(doLogin, action);
    QTRY_VERIFY(QApplication::activeModalWidget());
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QTRY_VERIFY(doLogin.bytesAvailable());
    const auto loginResult = doLogin.readAll();
    QCOMPARE(QJsonDocument::fromJson(loginResult).object()["state"],
             "login_submitted");
    QVERIFY(!loginResult.contains("synthetic-PASS"));
    QVERIFY(!loginResult.contains("tester_X42"));
    QTRY_COMPARE_WITH_TIMEOUT(site.logins, 1, 15000);
    QVERIFY(site.correctLogin);
    fields[3] = "1";
    QLocalSocket revoked;
    send(revoked,
         {{"operation", "web_inspect"}, {"session", response["session"]}});
    QTRY_VERIFY(revoked.bytesAvailable());
    QCOMPARE(QJsonDocument::fromJson(revoked.readAll()).object()["error"],
             "access_revoked_or_invalid_profile");
    QVERIFY(!browser);
    fields[3] = "0";
    QLocalSocket reopened;
    send(reopened, open);
    QTRY_VERIFY(QApplication::activeModalWidget());
    qobject_cast<QDialog *>(QApplication::activeModalWidget())->accept();
    QTRY_VERIFY(reopened.bytesAvailable());
    browser = window.findChild<VaultWeb *>();
    QVERIFY(browser);
    access.revoke();
    QVERIFY(!browser);
  }
};
int main(int argc, char **argv) {
  struct rlimit core{0, 0};
  if (setrlimit(RLIMIT_CORE, &core) || prctl(PR_SET_DUMPABLE, 0) ||
      prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0))
    return 1;
  qunsetenv("QTWEBENGINE_REMOTE_DEBUGGING");
  qunsetenv("QTWEBENGINE_CHROMIUM_FLAGS");
  qunsetenv("QTWEBENGINE_DISABLE_SANDBOX");
  QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
  QApplication app(argc, argv);
  WebTest test;
  return QTest::qExec(&test, argc, argv);
}
#include "web_login_test.moc"

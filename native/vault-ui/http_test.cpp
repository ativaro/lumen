// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "vault_http.h"
#include <QtTest>

class HttpSite : public QTcpServer {
public:
  QSslCertificate cert; QSslKey key;
  bool tls = true;
  int requests = 0; bool credentials = false, cookie = false, token = false;
  QUrl url() const { return QUrl(QString(tls ? "https://127.0.0.1:" : "http://127.0.0.1:") + QString::number(serverPort()) + "/login"); }
  void incomingConnection(qintptr fd) override {
    auto *s = new QSslSocket(this); s->setSocketDescriptor(fd); s->setLocalCertificate(cert); s->setPrivateKey(key); s->setPeerVerifyMode(QSslSocket::VerifyNone);
    connect(s, &QSslSocket::readyRead, s, [this, s] {
      auto data = s->property("data").toByteArray() + s->readAll(); s->setProperty("data", data);
      const auto end = data.indexOf("\r\n\r\n"); if (end < 0 || s->property("done").toBool()) return;
      int length = 0;
      for (auto line : data.left(end).split('\n')) if (line.toLower().startsWith("content-length:")) length = line.mid(15).trimmed().toInt();
      if (data.size() < end + 4 + length) return;
      s->setProperty("done", true); ++requests;
      const auto path = data.split(' ').value(1);
      const auto body = QJsonDocument::fromJson(data.mid(end+4)).object();
      QByteArray out = "{\"ok\":true}", headers, status = "200 OK";
      if (path == "/rpc") {
        auto params = body["params"].toObject();
        credentials = body["service"] == "Session" && body["method"] == "login" && params["username"] == "fixture_user_42" && params["password"] == "fixture_password_99";
        if (!credentials) status = "401 Unauthorized";
        else headers = "Set-Cookie: session=fixture_cookie_87; " + QByteArray(tls ? "Secure; " : "") + "HttpOnly; Path=/\r\n";
        out = "{\"response\":true,\"error\":null,\"password\":\"fixture_password_99\"}";
      } else if (path == "/token") out = "{\"auth\":{\"value\":\"fixture_bearer_86\"}}";
      else if (path == "/status") {
        cookie = data.contains("session=fixture_cookie_87"); token = data.contains("Authorization: Bearer fixture_bearer_86");
        out = (cookie || token) ? "{\"system\":\"fixture\",\"authenticated\":true}" : "{\"error\":\"not authenticated\"}";
      } else if (path == "/reflect") out = "{\"value\":\"fixture_cookie_87 fixture_bearer_86 fixture_password_99\"}";
      else if (path == "/redirect") { status = "302 Found"; headers = "Location: https://127.0.0.1:1/stolen\r\n"; }
      else if (path == "/large") out = QByteArray(1024*1024+1, 'x');
      else if (path == "/disconnect") { s->disconnectFromHost(); return; }
      s->write("HTTP/1.1 " + status + "\r\nContent-Type: application/json\r\nConnection: close\r\n" + headers + "Content-Length: " + QByteArray::number(out.size()) + "\r\n\r\n" + out); s->disconnectFromHost();
    });
    connect(s, &QSslSocket::disconnected, s, &QObject::deleteLater); if (tls) s->startServerEncryption();
  }
};
class HttpTest : public QObject {
  Q_OBJECT
  QTemporaryDir root; QSslCertificate cert; QSslKey key; QSslConfiguration original;
  void configure(HttpSite &site) { site.cert = cert; site.key = key; QVERIFY(site.listen(QHostAddress::LocalHost)); }
  QJsonObject call(VaultHttp &http, QString method, QString path, QJsonValue body = QJsonValue(QJsonValue::Undefined), QString capture = {}) {
    QJsonObject args{{"operation", "http_request"}, {"session", http.session()}, {"method", method}, {"path", path}};
    if (!body.isUndefined()) args["body"] = body;
    if (!capture.isEmpty()) args["capture_token"] = capture;
    QJsonObject result; QEventLoop loop; QTimer timeout; timeout.setSingleShot(true);
    connect(&timeout, &QTimer::timeout, &loop, &QEventLoop::quit); timeout.start(5000);
    http.request(args, [&](QJsonObject r) { result=r; loop.quit(); });
    if (result.isEmpty()) loop.exec();
    return result;
  }
  QJsonObject login() { return {{"service","Session"},{"method","login"},{"params",QJsonObject{{"username",QJsonObject{{"$vault","username"}}},{"password",QJsonObject{{"$vault","password"}}}}}}; }
private slots:
  void initTestCase() {
    QProcess p; p.start("openssl", {"req","-x509","-newkey","rsa:2048","-nodes","-keyout",root.path()+"/key","-out",root.path()+"/cert","-days","1","-subj","/CN=127.0.0.1","-addext","subjectAltName=IP:127.0.0.1"});
    QVERIFY(p.waitForFinished(10000)); QCOMPARE(p.exitCode(),0);
    QFile c(root.path()+"/cert"), k(root.path()+"/key"); QVERIFY(c.open(QIODevice::ReadOnly)); QVERIFY(k.open(QIODevice::ReadOnly)); cert=QSslCertificate(c.readAll()); key=QSslKey(k.readAll(),QSsl::Rsa);
    original=QSslConfiguration::defaultConfiguration(); auto trusted=original; auto ca=trusted.caCertificates(); ca<<cert; trusted.setCaCertificates(ca); QSslConfiguration::setDefaultConfiguration(trusted);
  }
  void cleanupTestCase() { QSslConfiguration::setDefaultConfiguration(original); }
  void validation() {
    const QUrl origin("https://example.test/login");
    QCOMPARE(VaultHttp::route(origin,"/rpc?x=1"),QUrl("https://example.test/rpc?x=1"));
    for (auto path : {"https://evil.test", "//evil.test/a", "/a#fragment", "/\\evil", "/a\nb"}) QVERIFY(VaultHttp::route(origin,path).isEmpty());
    QCOMPARE(VaultHttp::origin(QUrl("http://example.test/login")),QUrl("http://example.test/"));
    QVERIFY(VaultHttp::origin(QUrl("https://u:p@example.test")).isEmpty());
    QJsonObject args{{"operation","http_request"},{"session","s"},{"method","POST"},{"path","/rpc"},{"body",login()}};
    QVERIFY(VaultHttp::validRequest(args));
    args["body"]=QJsonObject{{"$vault","other"}}; QVERIFY(!VaultHttp::validRequest(args));
    args["body"]=login(); args["method"]="GET"; QVERIFY(!VaultHttp::validRequest(args));
    args["method"]="POST"; args["host"]="evil"; QVERIFY(!VaultHttp::validRequest(args));
  }
  void planValidation() {
    const QJsonObject step{{"method","POST"},{"path","/rpc"},{"body",login()}};
    QJsonObject open{{"operation","http_open"},{"reference","vault:fixture"},{"requests",QJsonArray{step}}};
    QVERIFY(VaultHttp::validRequest(open));
    for (auto invalid : {QJsonValue(), QJsonValue(QJsonArray{}), QJsonValue(QJsonArray{"bad"})}) {
      auto a=open; a["requests"]=invalid; QVERIFY(!VaultHttp::validRequest(a));
    }
    for (auto key : {"operation","session","headers","url","extra"}) {
      auto item=step; item[key]="bad"; open["requests"]=QJsonArray{item}; QVERIFY(!VaultHttp::validRequest(open));
    }
    auto bad=step; bad["body"]=QJsonObject{{"$vault","unknown"}};
    open["requests"]=QJsonArray{bad}; QVERIFY(!VaultHttp::validRequest(open));
    bad=step; bad["path"]="//other.test/";
    open["requests"]=QJsonArray{bad}; QVERIFY(!VaultHttp::validRequest(open));
    QJsonArray many; for (int i=0;i<13;++i) many.append(step);
    open["requests"]=many; QVERIFY(!VaultHttp::validRequest(open));
    bad=step; bad["body"]=QJsonObject{{"large",QString(18000,'a')}};
    open["requests"]=QJsonArray{bad,bad}; QVERIFY(!VaultHttp::validRequest(open));
  }
  void oneApprovalPlan_data() {
    QTest::addColumn<bool>("tls");
    QTest::newRow("TLS") << true;
    QTest::newRow("one plaintext consent") << false;
  }
  void oneApprovalPlan() {
    QFETCH(bool,tls);
    HttpSite site; site.tls=tls; configure(site); QWidget window; QTemporaryDir runtime;
    QStringList fields{"LumenType","login","LumenHidden","0","UserName","fixture_user_42","Password","fixture_password_99","URL",site.url().toString()};
    VaultAccess access(&window,[&](QString,std::function<void(QStringList)> done){done(fields);},true);
    const QMap<QString,QJsonObject> catalog{{"fixture",{{"kind","login"},{"title","Fixture"},{"login_scheme",tls ? "https" : "http"}}}};
    access.setConnections({},catalog); QVERIFY(access.listen(runtime.path()));
    QJsonObject result; int approvals=0;
    auto invoke=[&](QJsonObject args,bool prompt,bool allow=true) {
      QLocalSocket client; client.connectToServer(runtime.path()+"/lumen-vault-access"); QVERIFY(client.waitForConnected());
      client.write(QJsonDocument(args).toJson(QJsonDocument::Compact)+'\n'); client.flush();
      QTRY_VERIFY(client.bytesAvailable() || QApplication::activeModalWidget());
      auto *dialog=qobject_cast<QDialog*>(QApplication::activeModalWidget());
      QCOMPARE(bool(dialog),prompt);
      if (dialog) {
        const auto details=dialog->findChild<QLabel*>("httpApprovalDetails")->text();
        QVERIFY(!details.contains("fixture_password_99"));
        if (args.contains("requests")) {
          QVERIFY(details.contains("1. POST /rpc"));
          QVERIFY(details.contains("2. GET /status"));
        }
        if (allow) {
          if (!tls) { QVERIFY(!dialog->findChild<QPushButton*>("httpAllow")->isEnabled()); dialog->findChild<QCheckBox*>("httpAllowPlaintext")->setChecked(true); }
          ++approvals; dialog->accept();
        } else dialog->reject();
      }
      QTRY_VERIFY(client.bytesAvailable()); result=QJsonDocument::fromJson(client.readAll()).object();
      QTRY_VERIFY(!QApplication::activeModalWidget());
    };
    const QJsonObject loginStep{{"method","POST"},{"path","/rpc"},{"body",login()}};
    const QJsonObject readStep{{"method","GET"},{"path","/status"}};
    QJsonArray plan{loginStep,readStep,readStep,readStep,readStep};
    QJsonObject open{{"operation","http_open"},{"reference","vault:fixture"},{"requests",plan}};
    invoke(open,true,false); QCOMPARE(result["error"],"access_denied"); QCOMPARE(site.requests,0);
    invoke(open,true); QCOMPARE(result["approved_requests"].toInt(),5); QJsonValue session=result.value("session");
    auto run=[&](QJsonObject step,bool prompt=false,bool allow=true) { step["operation"]="http_request"; step["session"]=session; invoke(step,prompt,allow); };
    for (const auto &step : plan) run(step.toObject());
    QCOMPARE(approvals,1); QCOMPARE(site.requests,5); QVERIFY(result["body"].toObject()["authenticated"].toBool());
    run(readStep,true,false); QCOMPARE(result["error"],"access_denied"); QCOMPARE(site.requests,5);
    auto close=[&] { invoke({{"operation","http_close"},{"session",session}},false); };
    close();
    // Out of order, changed payload, and added capture instructions discard grants.
    for (const auto &change : {readStep, QJsonObject{{"method","POST"},{"path","/rpc"},{"body",QJsonObject{{"method","delete"}}}}, QJsonObject{{"method","POST"},{"path","/rpc"},{"body",login()},{"capture_token","/token"}}}) {
      invoke(open,true); session=result["session"];
      run(change,true,false); QCOMPARE(result["error"],"access_denied");
      run(loginStep,true,false); QCOMPARE(result["error"],"access_denied"); close();
    }
    QCOMPARE(site.requests,5);
    invoke(open,true); session=result["session"]; fields[7]="changed_fixture_password";
    run(loginStep); QCOMPARE(result["error"],"access_revoked_or_invalid_profile"); QCOMPARE(site.requests,5); fields[7]="fixture_password_99";
    invoke(open,true); session=result["session"]; fields[3]="1";
    run(loginStep); QCOMPARE(result["error"],"access_revoked_or_invalid_profile"); QCOMPARE(site.requests,5); fields[3]="0";
    invoke(open,true); session=result["session"]; access.revoke();
    run(loginStep); QCOMPARE(result["error"],"http_session_closed"); access.setConnections({},catalog);
    // A dispatched request with a lost response cannot leave reusable approval.
    const QJsonObject disconnect{{"method","GET"},{"path","/disconnect"}};
    open["requests"]=QJsonArray{loginStep,readStep,disconnect,readStep};
    invoke(open,true); session=result["session"]; run(loginStep); run(readStep); run(disconnect);
    QCOMPARE(result["error"],"operation_outcome_unknown");
    run(readStep,true,false); QCOMPARE(result["error"],"access_denied"); close();
    // Authentication failure (HTTP 401) also stops the remainder.
    const QJsonObject failed{{"method","POST"},{"path","/rpc"},{"body",QJsonObject{}}};
    open["requests"]=QJsonArray{loginStep,readStep,failed,readStep};
    invoke(open,true); session=result["session"]; run(loginStep); run(readStep); run(failed);
    QCOMPARE(result["http_status"].toInt(),401); run(readStep,true,false); close();
  }
  void genericRpcCookiesAndBearer() {
    HttpSite site; configure(site);
    VaultHttp h(site.url(),"fixture_user_42","fixture_password_99",this);
    auto r=call(h,"POST","/rpc",login()); QVERIFY2(r.value("credentials_submitted").toBool(),qPrintable(QString::fromUtf8(QJsonDocument(r).toJson())));
    QVERIFY(site.credentials); QVERIFY(r.value("response_withheld").toBool()); QVERIFY(!r.value("authentication_verified").toBool());
    r=call(h,"GET","/status"); QVERIFY(site.cookie); QVERIFY(r["body"].toObject()["authenticated"].toBool());
    r=call(h,"POST","/token",QJsonObject{},"/auth/value"); QVERIFY(r["token_stored"].toBool()); QVERIFY(!QJsonDocument(r).toJson().contains("fixture_bearer"));
    r=call(h,"GET","/status"); QVERIFY(site.token); QVERIFY(r["body"].toObject()["authenticated"].toBool());
    r=call(h,"GET","/reflect"); QVERIFY(r["response_withheld"].toBool());
    const auto count=site.requests; r=call(h,"GET","/rpc?secret=fixture_password_99"); QCOMPARE(r.value("error"),"unsafe_request"); QCOMPARE(site.requests,count);
    r=call(h,"GET","/redirect"); QCOMPARE(r.value("error"),"cross_origin_blocked");
    r=call(h,"GET","/large"); QCOMPARE(r.value("error"),"response_too_large");
  }
  void tlsNotBypassed() {
    HttpSite site; configure(site);
    auto trusted=QSslConfiguration::defaultConfiguration(); QSslConfiguration::setDefaultConfiguration(original);
    VaultHttp h(site.url(),"fixture_user_42","fixture_password_99",this);
    const auto r=call(h,"POST","/rpc",login());
    QSslConfiguration::setDefaultConfiguration(trusted);
    QCOMPARE(r.value("error"),"https_request_failed"); QCOMPARE(site.requests,0);
  }
  void nativeApprovalAndRevocation_data() {
    QTest::addColumn<bool>("tls");
    QTest::newRow("verified TLS") << true;
    QTest::newRow("explicit plaintext consent") << false;
  }
  void nativeApprovalAndRevocation() {
    QFETCH(bool, tls);
    HttpSite site; site.tls=tls; configure(site); QWidget window; QTemporaryDir runtime;
    QStringList fields{"LumenType","login","LumenHidden","0","UserName","fixture_user_42","Password","fixture_password_99","URL",site.url().toString()};
    VaultAccess access(&window,[&](QString,std::function<void(QStringList)> done){done(fields);},true);
    access.setConnections({},{{"fixture",{{"kind","login"},{"title","Fixture"},{"login_scheme","https"}}}}); QVERIFY(access.listen(runtime.path()));
    auto send=[&](QLocalSocket &s,QJsonObject args){s.connectToServer(runtime.path()+"/lumen-vault-access");QVERIFY(s.waitForConnected());s.write(QJsonDocument(args).toJson(QJsonDocument::Compact)+'\n');s.flush();};
    auto approve=[&] {
      auto *d=qobject_cast<QDialog*>(QApplication::activeModalWidget());
      if (!tls) { QVERIFY(!d->findChild<QPushButton*>("httpAllow")->isEnabled()); d->findChild<QCheckBox*>("httpAllowPlaintext")->setChecked(true); }
      d->accept();
    };
    QJsonObject open{{"operation","http_open"},{"reference","vault:fixture"}};
    QLocalSocket denied;send(denied,open);QTRY_VERIFY(QApplication::activeModalWidget());qobject_cast<QDialog*>(QApplication::activeModalWidget())->reject();QTRY_VERIFY(denied.bytesAvailable());QCOMPARE(QJsonDocument::fromJson(denied.readAll()).object().value("error"),"access_denied");QCOMPARE(site.requests,0);
    if (!tls) {
      QLocalSocket unsafe;send(unsafe,open);QTRY_VERIFY(QApplication::activeModalWidget());
      qobject_cast<QDialog*>(QApplication::activeModalWidget())->accept();
      QTRY_VERIFY(unsafe.bytesAvailable());QCOMPARE(QJsonDocument::fromJson(unsafe.readAll()).object().value("error"),"access_denied");QCOMPARE(site.requests,0);
    }
    QLocalSocket opened;send(opened,open);QTRY_VERIFY(QApplication::activeModalWidget());approve();QTRY_VERIFY(opened.bytesAvailable());auto r=QJsonDocument::fromJson(opened.readAll()).object();QVERIFY(r["session"].isString());
    QJsonObject post{{"operation","http_request"},{"session",r["session"]},{"method","POST"},{"path","/rpc"},{"body",login()}};
    QLocalSocket auth;send(auth,post);QTRY_VERIFY(QApplication::activeModalWidget());approve();QTRY_VERIFY(auth.bytesAvailable());r=QJsonDocument::fromJson(auth.readAll()).object();QVERIFY(r["credentials_submitted"].toBool());QVERIFY(site.credentials);
    auto disconnected = post; disconnected["path"] = "/disconnect";
    QLocalSocket lost; send(lost,disconnected); QTRY_VERIFY(QApplication::activeModalWidget()); approve(); QTRY_VERIFY(lost.bytesAvailable()); QCOMPARE(QJsonDocument::fromJson(lost.readAll()).object().value("error"),"operation_outcome_unknown"); QCOMPARE(site.requests,2);
    QLocalSocket changed;send(changed,post);QTRY_VERIFY(QApplication::activeModalWidget());fields[3]="1";approve();QTRY_VERIFY(changed.bytesAvailable());QCOMPARE(QJsonDocument::fromJson(changed.readAll()).object().value("error"),"access_revoked_or_invalid_profile");QCOMPARE(site.requests,2);
    QLocalSocket gone;send(gone,post);QTRY_VERIFY(gone.bytesAvailable());QCOMPARE(QJsonDocument::fromJson(gone.readAll()).object().value("error"),"http_session_closed");
    fields[3]="0";QLocalSocket pending;send(pending,open);QTRY_VERIFY(QApplication::activeModalWidget());access.revoke();QTRY_VERIFY(pending.bytesAvailable());QCOMPARE(QJsonDocument::fromJson(pending.readAll()).object().value("error"),"access_revoked");
  }
};
QTEST_MAIN(HttpTest)
#include "http_test.moc"

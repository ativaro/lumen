#include "passkey.h"
#include <QtTest>
#include <cstring>
void wipe(QString &s) { s.detach(); explicit_bzero(s.data(),size_t(s.size())*sizeof(QChar));s.clear(); }
void wipe(QByteArray &s) { s.detach();explicit_bzero(s.data(),size_t(s.size()));s.clear(); }
class PasskeyTest : public QObject {
  Q_OBJECT
  QNetworkAccessManager network;
  static QString enc(const QByteArray &v) { return QString::fromLatin1(v.toBase64(QByteArray::Base64UrlEncoding | QByteArray::OmitTrailingEquals)); }
  QPair<int,QByteArray> request(const QUrl &url, const QByteArray &token = {}, const QByteArray &origin = {}, const QByteArray &body = {}) {
    QNetworkRequest r(url);
    if (!token.isEmpty()) r.setRawHeader("X-Lumen-Token", token);
    if (!origin.isEmpty()) r.setRawHeader("Origin", origin);
    QNetworkReply *reply;
    if (body.isNull()) reply = network.get(r);
    else { r.setHeader(QNetworkRequest::ContentTypeHeader, "application/json"); reply = network.post(r,body); }
    QEventLoop loop;
    connect(reply,&QNetworkReply::finished,&loop,&QEventLoop::quit);
    QTimer::singleShot(3000,&loop,&QEventLoop::quit);
    loop.exec();
    const QPair<int,QByteArray> result(reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(),reply->readAll());
    delete reply; return result;
  }
private slots:
  void originNonceChallengeAndOneShot() {
    PasskeyBridge bridge({},true);
    auto url=bridge.url(); QVERIFY(!url.isEmpty());
    auto token=url.fragment().toLatin1(); url.setFragment({});
    auto origin=url.adjusted(QUrl::RemovePath).toString().toLatin1();
    QCOMPARE(request(url).first,200);
    url.setPath("/config");
    QCOMPARE(request(url).first,403);
    QCOMPARE(request(url,token,"https://evil.example").first,403);
    auto response=request(url,token); QCOMPARE(response.first,200);
    auto config=QJsonDocument::fromJson(response.second).object();
    QVERIFY(!config.contains("password"));
    QByteArray auth=QCryptographicHash::hash("localhost",QCryptographicHash::Sha256); auth.append(char(5)); auth.append(QByteArray(4,0));
    auto client=QJsonObject{{"type","webauthn.get"},{"challenge",config["challenge"]},{"origin",QString::fromLatin1(origin)},{"crossOrigin",false}};
    QJsonObject result{{"key",QString(64,'a')},{"credential","synthetic"},{"clientData",enc(QJsonDocument(client).toJson(QJsonDocument::Compact))},{"authData",enc(auth)}};
    url.setPath("/complete");
    auto body=QJsonDocument(result).toJson(QJsonDocument::Compact);
    QSignalSpy done(&bridge,&PasskeyBridge::completed);
    QCOMPARE(request(url,token,"https://evil.example",body).first,403);
    QCOMPARE(done.count(),0);
    client["challenge"]="wrong";result["clientData"]=enc(QJsonDocument(client).toJson());
    QCOMPARE(request(url,token,origin,QJsonDocument(result).toJson()).first,400);
    client["challenge"]=config["challenge"];result["clientData"]=enc(QJsonDocument(client).toJson());
    auth[32]=1;result["authData"]=enc(auth);
    QCOMPARE(request(url,token,origin,QJsonDocument(result).toJson()).first,400);
    auth[32]=5;result["authData"]=enc(auth);
    QCOMPARE(request(url,token,origin,QJsonDocument(result).toJson()).first,200);
    QCOMPARE(done.count(),1); QCOMPARE(done[0][0].toString(),QString(64,'a'));
    QVERIFY(bridge.url().isEmpty());
  }
  void unlockCannotSubstituteCredentialAndStopClosesListener() {
    PasskeyBridge bridge({{"credential","expected"},{"salt","salt"},{"binding","binding"}},false);
    auto url=bridge.url();auto token=url.fragment().toLatin1();url.setFragment({});
    const auto origin=url.adjusted(QUrl::RemovePath).toString().toLatin1();
    url.setPath("/config"); const auto c=QJsonDocument::fromJson(request(url,token).second).object();
    auto auth=QCryptographicHash::hash("localhost",QCryptographicHash::Sha256)+QByteArray(1,char(5))+QByteArray(4,0);
    QJsonObject client{{"type","webauthn.get"},{"origin",QString::fromLatin1(origin)},{"challenge",c["challenge"]}};
    QJsonObject result{{"key",QString(64,'a')},{"credential","other"},{"clientData",enc(QJsonDocument(client).toJson())},{"authData",enc(auth)}};
    url.setPath("/complete");QCOMPARE(request(url,token,origin,QJsonDocument(result).toJson()).first,400);
    bridge.stop();QVERIFY(bridge.url().isEmpty());
  }
};
QTEST_GUILESS_MAIN(PasskeyTest)
#include "passkey_test.moc"

// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QtNetwork>
#include <QtWidgets>
#include <functional>

class VaultHttp;
class VaultWeb;
class VaultSsh;

namespace BookStack {
constexpr int MaxFrame = 64 * 1024;
constexpr int MaxBody = 1024 * 1024;
QUrl origin(const QString &text);
QUrl route(const QUrl &base, const QJsonObject &args);
bool credential(const QString &value);
QJsonObject project(const QJsonObject &args, const QByteArray &body,
                    const QStringList &secrets);
} // namespace BookStack

// No credential-export IPC. Same-user clients are NOT authenticated as Lumen.
class VaultAccess : public QObject {
  Q_OBJECT
public:
  using Reader = std::function<void(QString, std::function<void(QStringList)>)>;
  VaultAccess(QWidget *window, Reader reader, bool english, const QString &knownHosts = {});
  ~VaultAccess() override;
  using Store = std::function<QDialog *(const QJsonObject &)>;
  void setStore(Store callback) { store = std::move(callback); }
  bool listen(const QString &runtime);
  bool arm(const QString &id, const QUrl &base);
  bool arm(const QString &id, const QJsonObject &profile);
  QJsonObject connection(int offset = 0) const;
  void setConnections(const QMap<QString, QJsonObject> &values,
                      const QMap<QString, QJsonObject> &entries = {});
  void revoke(bool preserveUnlock = false);
  void setUnlock(std::function<bool()> ready, std::function<QDialog *()> ask) {
    unlockReady = std::move(ready); unlockPrompt = std::move(ask);
  }
  void close() {
    revoke();
    server.close();
  }
  bool armed() const;
  bool waitingForUnlock() const { return unlocking; }
  QString entry() const { return entryId; }
  bool enabled(const QString &id) const { return profiles.contains(id); }
signals:
  void changed();

private:
  void httpRequest(const QJsonObject &args);
  void httpRead(const QJsonObject &args, bool confirmed, const QUrl &approved = {});
  void closeHttp();
  QPointer<VaultHttp> http;
  QString httpEntry;
  QJsonArray httpPlan;
  void sshRequest(const QJsonObject &args);
  void sshRevalidate(const QString &id, quint64 generation, int stage);
  QPointer<VaultSsh> ssh;
  QString sshKnownHosts;
  void webRequest(const QJsonObject &args);
  void webRead(const QJsonObject &args, bool confirmed, const QUrl &approvedUrl = {});
  void webConfirm(const QJsonObject &args, const QString &id, const QUrl &url);
  void closeWeb();
  QPointer<VaultWeb> web;
  QString webEntry;
  void accept();
  void receive();
  void confirm(const QJsonObject &args);
  void dispatch(const QJsonObject &args, quint64 epoch, QStringList fields);
  void sendRequest(const QJsonObject &args, quint64 epoch, int stage);
  void received(const QJsonObject &args, quint64 epoch, int stage, bool final);
  void finish(const QJsonObject &result);
  void cancel();
  QString tx(const char *de, const char *en) const;
  QWidget *window;
  Reader reader;
  Store store;
  std::function<bool()> unlockReady;
  std::function<QDialog *()> unlockPrompt;
  bool unlocking = false;
  bool english;
  QLocalServer server;
  QPointer<QLocalSocket> peer;
  QPointer<QDialog> prompt;
  QPointer<QNetworkReply> reply;
  QPointer<QNetworkAccessManager> network;
  QTimer deadline, framing;
  QMap<QString, QJsonObject> profiles, catalog;
  QString entryId;
  QUrl base;
  QJsonObject profile;
  QList<QPair<QByteArray, QByteArray>> authHeaders;
  QByteArray sessionId, protocol;
  int totalBytes = 0;
  bool actionDispatched = false;
  QByteArray frame, response;
  QStringList credentials;
  quint64 epoch = 0;
  bool requested = false;
};

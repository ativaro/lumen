// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QtNetwork>
#include <functional>

class VaultHttp final : public QObject {
public:
  using Reply = std::function<void(QJsonObject)>;
  VaultHttp(QUrl url, QString user, QString password, QObject *parent);
  ~VaultHttp() override;
  static bool validRequest(const QJsonObject &args);
  static QUrl origin(const QUrl &url);
  static QUrl route(const QUrl &base, const QString &path);
  bool matches(const QUrl &url, const QString &user, const QString &password) const;
  QString session() const { return handle; }
  QUrl base() const { return origin(stored); }
  bool busy() const { return !pending.isNull(); }
  void request(const QJsonObject &args, Reply done);
private:
  QUrl stored;
  QString username, password, handle, bearer;
  QStringList knownSecrets;
  QNetworkAccessManager manager;
  QPointer<QNetworkReply> pending;
};

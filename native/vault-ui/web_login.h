// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QWebEnginePage>
#include <QtWidgets>
#include <functional>

class QWebEngineProfile;
class QWebEngineView;
class VaultWeb final : public QDialog {
  Q_OBJECT
public:
  using Reply = std::function<void(QJsonObject)>;
  VaultWeb(QWidget *parent, const QUrl &url, QString user, QString password,
           bool english);
  ~VaultWeb() override;
  static bool validUrl(const QUrl &url);
  static bool sameOrigin(const QUrl &a, const QUrl &b);
  static bool containsSecret(const QByteArray &data,
                             const QStringList &secrets);
  static bool validRequest(const QJsonObject &args);
  void start();
  void inspect(Reply reply);
  void act(const QJsonObject &args, Reply reply);
  bool matches(const QUrl &url, const QString &user,
               const QString &password) const;
  bool current(const QJsonObject &args) const;
  QString describe(const QJsonObject &args) const;
  QString session() const { return token; }
  QWebEnginePage *page() const;

private:
  void safeReply(QJsonObject result, Reply reply) const;
  QUrl target;
  QString username, password, token, snapshot;
  QJsonArray nodes;
  quint64 revision = 0;
  bool loading = true, failed = false, closing = false;
  QWebEngineProfile *profile;
  QWebEngineView *view;
  QLabel *status;
};

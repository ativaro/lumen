// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QtCore>
#include <atomic>

class VaultSsh final : public QThread {
  Q_OBJECT
public:
  VaultSsh(QUrl target, QString user, QString password, QString command,
           QString knownHosts, int port = 0);
  ~VaultSsh() override;
  static QUrl loginTarget(const QUrl &stored, int port = 0);
  static bool validUrl(const QUrl &url);
  static bool validCommand(const QString &command);
  static bool privateHostFile(const QString &path);
  bool matches(const QUrl &url, const QString &user,
               const QString &password) const;
  void cancel();
  void approve(int stage);
  bool dispatched() const { return sent.load(); }
signals:
  void approvalNeeded(QString fingerprint, bool known);
  void executionReady();
  void resultReady(QJsonObject result);

protected:
  void run() override;

private:
  QJsonObject execute();
  bool waitForApproval(int stage);
  QUrl target, storedTarget;
  QString user, password, command, knownHosts;
  std::atomic_bool cancelled{false}, sent{false};
  QMutex mutex;
  QWaitCondition wake;
  int approved = 0;
};

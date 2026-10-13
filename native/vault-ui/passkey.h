// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QtNetwork>
#include <functional>

// Only the native window creates a bridge; there is no agent/MCP unlock endpoint.
class PasskeyBridge : public QObject {
  Q_OBJECT
public:
  explicit PasskeyBridge(QJsonObject metadata, bool enroll, QObject *parent = nullptr);
  ~PasskeyBridge() override;
  QUrl url() const;
  QJsonObject metadata() const { return config; }
  void stop();
signals:
  void completed(QString key, QString credential);
  void failed();
private:
  void read(QTcpSocket *socket);
  void reply(QTcpSocket *socket, int status, const QByteArray &body, const QByteArray &type = "application/json");
  QTcpServer server;
  QTimer lifetime;
  QJsonObject config;
  QByteArray token, host, origin;
  bool finished = false;
};

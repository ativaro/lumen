// SPDX-License-Identifier: MIT
#pragma once
#include <QtNetwork>
namespace VaultConnection {
QString value(const QStringList &fields, const QString &key);
QJsonObject settings(const QStringList &fields);
QString
problem(const QStringList &fields); // Fixed field identifier, never a secret.
QByteArray body(const QJsonObject &args);
QUrl route(const QJsonObject &profile, const QJsonObject &args);
QList<QPair<QByteArray, QByteArray>> headers(const QStringList &fields);
QJsonObject rpc(const QJsonObject &args, int stage);
QJsonObject rpcResponse(const QByteArray &data, bool sse, int id);
} // namespace VaultConnection

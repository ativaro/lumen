// SPDX-License-Identifier: MIT
#include "connection.h"
#include "bookstack.h"
namespace {
bool visible(const QString &s) {
  if (s.isEmpty() || s.size() > 16384)
    return false;
  for (auto ch : s)
    if (ch.unicode() < 0x21 || ch.unicode() > 0x7e)
      return false;
  return true;
}
bool header(const QString &s) {
  static const QRegularExpression name(
      QRegularExpression::anchoredPattern("[A-Za-z][A-Za-z0-9-]{0,63}"));
  static const QSet<QString> denied{"host",
                                    "authorization",
                                    "proxy-authorization",
                                    "cookie",
                                    "connection",
                                    "content-length",
                                    "content-type",
                                    "transfer-encoding",
                                    "accept",
                                    "accept-encoding",
                                    "origin",
                                    "referer",
                                    "upgrade",
                                    "te",
                                    "trailer",
                                    "mcp-session-id",
                                    "mcp-protocol-version"};
  return name.match(s).hasMatch() && !denied.contains(s.toLower()) &&
         !s.startsWith("Sec-", Qt::CaseInsensitive);
}
QUrl endpoint(const QString &s) {
  QUrl url(s, QUrl::StrictMode);
  if (!url.isValid() || url.scheme() != "https" || url.host().isEmpty() ||
      url.authority().contains('@') || url.hasQuery() || url.hasFragment() ||
      url.port() == 0)
    return {};
  return url;
}
} // namespace
QString VaultConnection::value(const QStringList &fields, const QString &key) {
  for (int i = 0; i + 1 < fields.size(); i += 2)
    if (fields[i] == key)
      return fields[i + 1];
  return {};
}
QJsonObject VaultConnection::settings(const QStringList &fields) {
  const auto val = [&](const QString &key) { return value(fields, key); };
  auto connector = val("LumenApiConnector");
  if (connector.isEmpty())
    connector = "api";
  auto auth = val("LumenApiAuth");
  if (auth.isEmpty())
    auth = (!val("LumenApiTokenId").isEmpty() || !val("UserName").isEmpty())
               ? "token_pair"
               : "bearer";
  const auto address =
      val("LumenApiBase").isEmpty() ? val("URL") : val("LumenApiBase");
  return {{"connector", connector},
          {"auth", auth},
          {"endpoint", address},
          {"id_header", val("LumenApiIdHeader")},
          {"secret_header", val("LumenApiSecretHeader").isEmpty()
                                ? "X-API-Key"
                                : val("LumenApiSecretHeader")}};
}
QString VaultConnection::problem(const QStringList &fields) {
  const auto p = settings(fields);
  if (value(fields, "LumenType") != "token" ||
      value(fields, "LumenTrash") == "1")
    return "type";
  if (!QStringList{"api", "mcp", "bookstack"}.contains(
          p["connector"].toString()))
    return "connector";
  const auto url = endpoint(p["endpoint"].toString());
  if (url.isEmpty())
    return "endpoint";
  if (p["connector"] == "bookstack" &&
      BookStack::origin(url.toString()).isEmpty())
    return "bookstack_origin";
  auto secret = value(fields, "Password");
  auto id = value(fields, "LumenApiTokenId");
  if (id.isEmpty())
    id = value(fields, "UserName");
  if (!visible(secret))
    return "secret";
  const auto auth = p["auth"].toString();
  if ((auth == "token_pair" || auth == "headers") && !visible(id))
    return "token_id";
  if (auth == "token_pair" && (id.contains(':') || secret.contains(':')))
    return "pair";
  if ((auth == "api_key" || auth == "headers") &&
      !header(p["secret_header"].toString()))
    return "secret_header";
  if (auth == "headers" &&
      (!header(p["id_header"].toString()) ||
       p["id_header"].toString().compare(p["secret_header"].toString(),
                                         Qt::CaseInsensitive) == 0))
    return "id_header";
  if (!QStringList{"bearer", "token_pair", "api_key", "headers"}.contains(auth))
    return "auth";
  if (p["connector"] == "bookstack" && auth != "token_pair")
    return "auth";
  return {};
}
QList<QPair<QByteArray, QByteArray>>
VaultConnection::headers(const QStringList &fields) {
  if (!problem(fields).isEmpty())
    return {};
  const auto p = settings(fields);
  const auto secret = value(fields, "Password").toUtf8();
  auto id = value(fields, "LumenApiTokenId").toUtf8();
  if (id.isEmpty())
    id = value(fields, "UserName").toUtf8();
  if (p["auth"] == "bearer")
    return {{"Authorization", "Bearer " + secret}};
  if (p["auth"] == "token_pair")
    return {{"Authorization", "Token " + id + ":" + secret}};
  QList<QPair<QByteArray, QByteArray>> out{
      {p["secret_header"].toString().toLatin1(), secret}};
  if (p["auth"] == "headers")
    out.append({p["id_header"].toString().toLatin1(), id});
  return out;
}
QUrl VaultConnection::route(const QJsonObject &p, const QJsonObject &args) {
  const auto url = endpoint(p["endpoint"].toString());
  if (url.isEmpty())
    return {};
  if (p["connector"] == "bookstack" ||
      (p["connector"] == "api" &&
       QStringList{"check", "list_books", "search", "read_page"}.contains(
           args["operation"].toString())))
    return BookStack::route(url, args);
  QSet<QString> keys{"operation"};
  const auto op = args["operation"].toString();
  QUrl target = url;
  if (p["connector"] == "api" && op == "api_get") {
    keys.unite({"path", "query"});
    const auto path = args.value("path");
    static const QRegularExpression safePath(
        QRegularExpression::anchoredPattern("(/[A-Za-z0-9_.~-]+)*/*"));
    if (!path.isUndefined() &&
        (!path.isString() || path.toString().size() > 512 ||
         !safePath.match(path.toString()).hasMatch() ||
         path.toString().split('/').contains("..") ||
         path.toString().split('/').contains(".")))
      return {};
    QString prefix = url.path();
    while (prefix.endsWith('/'))
      prefix.chop(1);
    target.setPath(prefix + path.toString());
    const auto params = args.value("query");
    if (!params.isUndefined() && !params.isObject())
      return {};
    QUrlQuery query;
    const auto values = params.toObject();
    if (values.size() > 20)
      return {};
    for (auto it = values.begin(); it != values.end(); ++it) {
      if (it.key().size() > 100 || !it.value().isString() ||
          it.value().toString().size() > 500)
        return {};
      query.addQueryItem(
          QString::fromLatin1(QUrl::toPercentEncoding(it.key())),
          QString::fromLatin1(QUrl::toPercentEncoding(it.value().toString())));
    }
    target.setQuery(query);
  } else if (p["connector"] == "mcp" &&
             (op == "mcp_tools" || op == "mcp_call")) {
    if (op == "mcp_tools") {
      keys.insert("cursor");
      if (args.contains("cursor") && (!args["cursor"].isString() ||
                                      args["cursor"].toString().size() > 512))
        return {};
    } else {
      keys.unite({"name", "arguments"});
      if (!args["name"].isString() || args["name"].toString().isEmpty() ||
          args["name"].toString().size() > 128 || !args["arguments"].isObject())
        return {};
    }
  } else
    return {};
  for (auto it = args.begin(); it != args.end(); ++it)
    if (!keys.contains(it.key()))
      return {};
  return target;
}
QJsonObject VaultConnection::rpc(const QJsonObject &args, int stage) {
  if (stage == 0)
    return {{"jsonrpc", "2.0"},
            {"id", 1},
            {"method", "initialize"},
            {"params",
             QJsonObject{{"protocolVersion", "2025-06-18"},
                         {"capabilities", QJsonObject{}},
                         {"clientInfo", QJsonObject{{"name", "Lumen Vault"},
                                                    {"version", "1.0"}}}}}};
  if (stage == 1)
    return {{"jsonrpc", "2.0"}, {"method", "notifications/initialized"}};
  const bool listing = args["operation"] == "mcp_tools";
  QJsonObject params;
  if (listing) {
    if (args.contains("cursor"))
      params["cursor"] = args["cursor"];
  } else {
    params["name"] = args["name"];
    params["arguments"] = args["arguments"];
  }
  return {{"jsonrpc", "2.0"},
          {"id", 2},
          {"method", listing ? "tools/list" : "tools/call"},
          {"params", params}};
}
QJsonObject VaultConnection::rpcResponse(const QByteArray &data, bool sse,
                                         int id) {
  QList<QByteArray> messages;
  if (!sse)
    messages.append(data);
  else {
    QByteArray normalized = data;
    if (normalized.startsWith(QByteArray::fromHex("efbbbf")))
      normalized.remove(0, 3);
    normalized.replace("\r\n", "\n");
    normalized.replace('\r', '\n');
    int start = 0, end, events = 0;
    while ((end = normalized.indexOf("\n\n", start)) >= 0) {
      if (++events > 64)
        return {{"error", "too_many_events"}};
      QByteArray json;
      for (const auto &line : normalized.mid(start, end - start).split('\n'))
        if (line.startsWith("data:")) {
          auto value = line.mid(5);
          if (value.startsWith(' '))
            value.remove(0, 1);
          json += value + '\n';
        }
      if (!json.isEmpty())
        messages.append(json);
      if (messages.size() > 64)
        return {{"error", "too_many_events"}};
      start = end + 2;
    }
  }
  for (const auto &message : messages) {
    QJsonParseError error;
    const auto doc = QJsonDocument::fromJson(message, &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject())
      return {{"error", "invalid_rpc"}};
    const auto obj = doc.object();
    if (obj["jsonrpc"] != "2.0")
      return {{"error", "invalid_rpc"}};
    if (obj.contains("method")) {
      if (obj.contains("id"))
        return {{"error", "unsupported_server_request"}};
      continue; // Notifications are never instructions.
    }
    if (obj["id"] != id)
      return {{"error", "invalid_rpc"}};
    if (obj.contains("error") || !obj["result"].isObject())
      return {{"error", "service_rpc_error"}};
    return {{"result", obj["result"]}};
  }
  return {};
}

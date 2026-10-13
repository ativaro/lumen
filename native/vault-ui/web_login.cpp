// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "web_login.h"
#include "vault.h"
#include <QWebEngineDownloadRequest>
#include <QWebEnginePermission>
#include <QWebEngineProfile>
#include <QWebEngineScript>
#include <QWebEngineSettings>
#include <QWebEngineUrlRequestInterceptor>
#include <QWebEngineView>

namespace {
QJsonObject error(const char *code) { return {{"error", code}}; }
QString script(const char *name) {
  QFile f(QString(":/vault-web/") + name);
  if (!f.open(QIODevice::ReadOnly))
    return {};
  return QString::fromUtf8(f.readAll());
}
QString jsonString(const QString &value) {
  auto bytes = QJsonDocument(QJsonArray{value}).toJson(QJsonDocument::Compact);
  return QString::fromUtf8(bytes.mid(1, bytes.size() - 2));
}
class Guard final : public QWebEngineUrlRequestInterceptor {
public:
  Guard(const QUrl &url, const QString &password, QObject *parent)
      : QWebEngineUrlRequestInterceptor(parent), url(url), secrets{password} {}
  ~Guard() override {
    for (auto &s : secrets)
      wipe(s);
  }
  void interceptRequest(QWebEngineUrlRequestInfo &info) override {
    const auto requested = info.requestUrl();
    const auto decoded =
        QUrl::fromPercentEncoding(requested.toEncoded()).toUtf8();
    if (!VaultWeb::sameOrigin(url, requested) ||
        VaultWeb::containsSecret(requested.toEncoded(), secrets) ||
        VaultWeb::containsSecret(decoded, secrets))
      info.block(true);
  }

private:
  QUrl url;
  QStringList secrets;
};
class Page final : public QWebEnginePage {
public:
  Page(QWebEngineProfile *profile, QUrl origin, QObject *parent)
      : QWebEnginePage(profile, parent), origin(std::move(origin)) {}

protected:
  bool acceptNavigationRequest(const QUrl &url, NavigationType, bool) override {
    return VaultWeb::sameOrigin(origin, url);
  }
  QWebEnginePage *createWindow(WebWindowType) override { return nullptr; }
  QStringList chooseFiles(FileSelectionMode, const QStringList &,
                          const QStringList &) override {
    return {};
  }
  void javaScriptAlert(const QUrl &, const QString &) override {}
  bool javaScriptConfirm(const QUrl &, const QString &) override {
    return false;
  }
  bool javaScriptPrompt(const QUrl &, const QString &, const QString &,
                        QString *) override {
    return false;
  }
  void javaScriptConsoleMessage(JavaScriptConsoleMessageLevel, const QString &,
                                int, const QString &) override {}

private:
  QUrl origin;
};
} // namespace

bool VaultWeb::validUrl(const QUrl &url) {
  return url.isValid() && !url.isRelative() && url.scheme() == "https" &&
         !url.host().isEmpty() && url.userInfo().isEmpty() && !url.hasQuery() &&
         !url.hasFragment();
}
bool VaultWeb::sameOrigin(const QUrl &a, const QUrl &b) {
  return b.isValid() && !b.isRelative() && b.scheme() == "https" &&
         b.userInfo().isEmpty() && a.host() == b.host() &&
         a.port(443) == b.port(443);
}
bool VaultWeb::containsSecret(const QByteArray &data,
                              const QStringList &secrets) {
  for (const auto &secret : secrets) {
    if (secret.isEmpty())
      continue;
    auto bytes = secret.toUtf8();
    auto escaped =
        QJsonDocument(QJsonArray{secret}).toJson(QJsonDocument::Compact);
    escaped = escaped.mid(2, escaped.size() - 4);
    const bool found =
        data.contains(bytes) || data.contains(bytes.toBase64()) ||
        data.toLower().contains(bytes.toHex()) ||
        data.contains(bytes.toPercentEncoding()) || data.contains(escaped);
    wipe(bytes);
    wipe(escaped);
    if (found)
      return true;
  }
  return false;
}
bool VaultWeb::validRequest(const QJsonObject &a) {
  const auto op = a["operation"].toString();
  QSet<QString> keys{"operation"};
  if (op == "web_open")
    keys.insert("reference");
  else {
    keys.insert("session");
    if (op == "web_login")
      keys.unite({"snapshot", "username_node", "password_node", "submit_node"});
    else if (op == "web_click")
      keys.unite({"snapshot", "node"});
    else if (op == "web_fill")
      keys.unite({"snapshot", "node", "text"});
    else if (op != "web_inspect" && op != "web_close")
      return false;
  }
  if (a.size() != keys.size())
    return false;
  for (const auto &k : keys) {
    const auto v = a[k];
    if (!v.isString() || (v.toString().isEmpty() && k != "text") ||
        v.toString().size() > (k == "text" ? 2000 : 128))
      return false;
  }
  return true;
}
VaultWeb::VaultWeb(QWidget *parent, const QUrl &url, QString user, QString pass,
                   bool english)
    : QDialog(parent), target(url), username(std::move(user)),
      password(std::move(pass)),
      token(QUuid::createUuid().toString(QUuid::WithoutBraces)),
      profile(new QWebEngineProfile(this)), view(new QWebEngineView(this)),
      status(new QLabel(this)) {
  setAttribute(Qt::WA_DeleteOnClose);
  setWindowTitle(english ? "Lumen · Vault web access"
                         : "Lumen · Vault-Webzugriff");
  resize(1040, 760);
  auto *layout = new QVBoxLayout(this);
  auto *heading = new QLabel(
      url.adjusted(QUrl::RemovePath | QUrl::RemoveQuery | QUrl::RemoveFragment)
          .toDisplayString(),
      this);
  heading->setTextFormat(Qt::PlainText);
  status->setTextFormat(Qt::PlainText);
  layout->addWidget(heading);
  layout->addWidget(status);
  layout->addWidget(view);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close, this);
  connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::close);
  layout->addWidget(buttons);
  profile->setUrlRequestInterceptor(new Guard(url, password, profile));
  profile->setHttpCacheType(QWebEngineProfile::MemoryHttpCache);
  profile->setHttpCacheMaximumSize(16 * 1024 * 1024);
  profile->setPersistentCookiesPolicy(QWebEngineProfile::NoPersistentCookies);
  connect(profile, &QWebEngineProfile::downloadRequested, this,
          [](QWebEngineDownloadRequest *request) { request->cancel(); });
  auto *p = new Page(profile, url, view);
  view->setPage(p);
  view->setContextMenuPolicy(Qt::NoContextMenu);
  auto *settings = p->settings();
  for (auto setting : {QWebEngineSettings::JavascriptCanOpenWindows,
                       QWebEngineSettings::JavascriptCanAccessClipboard,
                       QWebEngineSettings::JavascriptCanPaste,
                       QWebEngineSettings::LocalContentCanAccessFileUrls,
                       QWebEngineSettings::LocalContentCanAccessRemoteUrls,
                       QWebEngineSettings::PluginsEnabled,
                       QWebEngineSettings::FullScreenSupportEnabled,
                       QWebEngineSettings::ScreenCaptureEnabled,
                       QWebEngineSettings::HyperlinkAuditingEnabled,
                       QWebEngineSettings::PdfViewerEnabled})
    settings->setAttribute(setting, false);
  settings->setUnknownUrlSchemePolicy(
      QWebEngineSettings::DisallowUnknownUrlSchemes);
  connect(p, &QWebEnginePage::permissionRequested, this,
          [](QWebEnginePermission permission) { permission.deny(); });
  connect(p, &QWebEnginePage::loadStarted, this, [this] {
    ++revision;
    snapshot.clear();
    nodes = {};
    loading = true;
    failed = false;
    status->setText("Lumen · …");
  });
  connect(p, &QWebEnginePage::urlChanged, this, [this] {
    ++revision;
    snapshot.clear();
    nodes = {};
  });
  connect(p, &QWebEnginePage::loadFinished, this, [this, english](bool ok) {
    loading = false;
    failed = !ok;
    status->setText(
        ok ? (english
                  ? "Lumen · Temporary session. MFA can be entered here."
                  : "Lumen · Temporäre Sitzung. MFA kannst du hier eingeben.")
           : (english ? "Lumen · Page could not load. Check HTTPS/certificate "
                        "and same-origin resources."
                      : "Lumen · Seite nicht geladen. HTTPS, Zertifikat und "
                        "Ressourcen derselben Adresse prüfen."));
  });
  connect(p, &QWebEnginePage::renderProcessTerminated, this,
          [this] { close(); });
  QTimer::singleShot(10 * 60 * 1000, this, &QDialog::close);
}
VaultWeb::~VaultWeb() {
  closing = true;
  // Page must be destroyed before its off-the-record profile.
  delete view;
  delete profile;
  wipe(username);
  wipe(password);
}
void VaultWeb::start() {
  show();
  view->load(target);
}
QWebEnginePage *VaultWeb::page() const { return view->page(); }
bool VaultWeb::matches(const QUrl &url, const QString &user,
                       const QString &pass) const {
  return target == url && username == user && password == pass;
}
bool VaultWeb::current(const QJsonObject &args) const {
  if (loading || failed || !sameOrigin(target, page()->url()) ||
      snapshot.isEmpty() || args["snapshot"] != snapshot)
    return false;
  const QStringList keys =
      args["operation"] == "web_login"
          ? QStringList{"username_node", "password_node", "submit_node"}
          : QStringList{"node"};
  for (const auto &key : keys) {
    bool found = false;
    for (const auto &n : nodes)
      if (n.toObject()["node"] == args[key])
        found = true;
    if (!found)
      return false;
  }
  return true;
}
QString VaultWeb::describe(const QJsonObject &args) const {
  QStringList labels;
  const auto id =
      args[args["operation"] == "web_login" ? "submit_node" : "node"];
  for (const auto &n : nodes)
    if (n.toObject()["node"] == id)
      labels << n.toObject()["label"].toString().left(160);
  return labels.join(" · ");
}
void VaultWeb::safeReply(QJsonObject result, Reply reply) const {
  const auto redact = [this](QString value) {
    for (const auto &secret : {username, password}) {
      if (secret.isEmpty())
        continue;
      const auto bytes = secret.toUtf8();
      value.replace(secret, QString::fromUtf8("[•••]"));
      value.replace(QString::fromLatin1(bytes.toBase64()),
                    QString::fromUtf8("[•••]"));
      value.replace(QString::fromLatin1(bytes.toHex()),
                    QString::fromUtf8("[•••]"), Qt::CaseInsensitive);
      value.replace(QString::fromLatin1(bytes.toPercentEncoding()),
                    QString::fromUtf8("[•••]"), Qt::CaseInsensitive);
    }
    return value;
  };
  result["text"] = redact(result["text"].toString());
  auto safeNodes = result["nodes"].toArray();
  for (int i = 0; i < safeNodes.size(); ++i) {
    auto node = safeNodes[i].toObject();
    for (const auto &key : {"label", "role", "type", "autocomplete"})
      node[key] = redact(node[key].toString());
    safeNodes[i] = node;
  }
  result["nodes"] = safeNodes;
  auto encoded = QJsonDocument(result).toJson(QJsonDocument::Compact);
  const bool unsafe = containsSecret(encoded, {username, password});
  wipe(encoded);
  reply(unsafe ? error("unsafe_response") : result);
}
void VaultWeb::inspect(Reply reply) {
  if (loading) {
    reply({{"state", "loading"}});
    return;
  }
  if (failed || !sameOrigin(target, page()->url())) {
    reply(error("web_page_unavailable"));
    return;
  }
  snapshot = QUuid::createUuid().toString(QUuid::WithoutBraces);
  auto code = script("web_dom.js");
  code.replace("SNAPSHOT", jsonString(snapshot));
  const auto generation = revision;
  const auto expected = snapshot;
  QPointer<VaultWeb> guard(this);
  page()->runJavaScript(
      code, QWebEngineScript::ApplicationWorld,
      [guard, generation, expected, reply](const QVariant &value) {
        if (!guard || guard->closing)
          return;
        if (guard->revision != generation || guard->snapshot != expected) {
          reply(error("stale_snapshot"));
          return;
        }
        const auto result =
            QJsonDocument::fromJson(value.toString().toUtf8()).object();
        if (result["snapshot"] != expected || !result["nodes"].isArray()) {
          reply(error("web_page_unavailable"));
          return;
        }
        guard->nodes = result["nodes"].toArray();
        auto out = result;
        out["state"] = "page_ready";
        out["untrusted"] = true;
        guard->safeReply(out, reply);
      });
}
void VaultWeb::act(const QJsonObject &args, Reply reply) {
  if (!current(args)) {
    reply(error("stale_snapshot"));
    return;
  }
  if (args["operation"] == "web_fill" &&
      containsSecret(args["text"].toString().toUtf8(), {username, password})) {
    reply(error("credential_field_requires_local_input"));
    return;
  }
  auto values = args;
  if (args["operation"] == "web_login") {
    values["username"] = username;
    values["password"] = password;
  }
  auto encoded = QJsonDocument(values).toJson(QJsonDocument::Compact);
  auto code = script("web_action.js");
  code.replace("ARGUMENTS", QString::fromUtf8(encoded));
  wipe(encoded);
  values = {};
  snapshot.clear();
  nodes = {};
  QPointer<VaultWeb> guard(this);
  page()->runJavaScript(
      code, QWebEngineScript::ApplicationWorld,
      [guard, reply](const QVariant &value) {
        if (!guard || guard->closing)
          return;
        const auto state = value.toString();
        if (state == "login_submitted" || state == "clicked" ||
            state == "text_entered")
          reply({{"state", state}, {"authentication_verified", false}});
        else {
          static const QSet<QString> errors{
              "stale_snapshot",       "invalid_login_controls",
              "unsafe_login_form",    "credential_field_requires_local_input",
              "cross_origin_blocked", "unsupported_control",
              "use_web_login"};
          reply(
              {{"error",
                errors.contains(state) ? state : "operation_outcome_unknown"}});
        }
      });
  wipe(code);
}

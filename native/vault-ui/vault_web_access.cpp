// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "connection.h"
#include "vault.h"
#include "web_login.h"

void VaultAccess::closeWeb() {
  auto previous = web;
  web.clear();
  webEntry.clear();
  if (previous)
    delete previous;
}
void VaultAccess::webRequest(const QJsonObject &args) {
  if (!VaultWeb::validRequest(args)) {
    finish({{"error", "invalid_request"}});
    return;
  }
  const auto op = args["operation"].toString();
  if (op != "web_open" && (!web || args["session"] != web->session())) {
    finish({{"error", "web_session_closed"}});
    return;
  }
  if (op == "web_close") {
    closeWeb();
    finish({{"closed", true}});
    return;
  }
  if (QApplication::activeModalWidget()) {
    finish({{"error", "vault_busy"}});
    return;
  }
  if (op == "web_open" && web) {
    finish({{"error", "web_session_already_open"}});
    return;
  }
  webRead(args, false);
}
void VaultAccess::webRead(const QJsonObject &args, bool confirmed,
                          const QUrl &approvedUrl) {
  const auto op = args["operation"].toString();
  const auto ref = args["reference"].toString();
  const auto id = op == "web_open"
                      ? (ref.startsWith("vault:") ? ref.mid(6) : QString())
                      : webEntry;
  if (!catalog.contains(id) || catalog[id]["kind"] != "login") {
    closeWeb();
    finish({{"error", "connection_not_enabled"}});
    return;
  }
  const auto requestEpoch = epoch;
  reader(id, [this, args, confirmed, id, requestEpoch, op,
              approvedUrl](QStringList fields) {
    auto user = VaultConnection::value(fields, "UserName");
    auto password = VaultConnection::value(fields, "Password");
    const QUrl url(VaultConnection::value(fields, "URL"), QUrl::StrictMode);
    const bool enabled =
        VaultConnection::value(fields, "LumenHidden") != "1" &&
        VaultConnection::value(fields, "LumenType") == "login";
    for (auto &f : fields)
      wipe(f);
    if (requestEpoch != epoch || !peer) {
      wipe(user);
      wipe(password);
      return;
    }
    const bool isOpen = op == "web_open";
    const bool current = isOpen || (web && args["session"] == web->session() &&
                                    web->matches(url, user, password));
    if (!enabled || !catalog.contains(id) || !current ||
        (confirmed && approvedUrl != url) || user.isEmpty() ||
        password.isEmpty() || user.size() > 4096 || password.size() > 4096 ||
        !VaultWeb::validUrl(url)) {
      wipe(user);
      wipe(password);
      closeWeb();
      finish({{"error", !VaultWeb::validUrl(url)
                            ? "web_https_url_required"
                            : "access_revoked_or_invalid_profile"}});
      return;
    }
    if (isOpen && confirmed) {
      web = new VaultWeb(window, url, user, password, english);
      wipe(user);
      wipe(password);
      webEntry = id;
      auto *browser = web.data();
      connect(browser, &QDialog::finished, this, [this, browser] {
        if (web == browser) {
          web.clear();
          webEntry.clear();
          if (peer)
            finish({{"error", "web_session_closed"}});
        }
      });
      browser->start();
      finish({{"session", browser->session()},
              {"state", "opening"},
              {"authentication_verified", false}});
      return;
    }
    wipe(user);
    wipe(password);
    if (isOpen) {
      webConfirm(args, id, url);
      return;
    }
    auto done = [this, requestEpoch](QJsonObject result) {
      if (requestEpoch == epoch && peer) {
        static const QSet<QString> deniedBeforeAction{
            "invalid_login_controls",
            "unsafe_login_form",
            "credential_field_requires_local_input",
            "cross_origin_blocked",
            "unsupported_control",
            "use_web_login"};
        if (deniedBeforeAction.contains(result.value("error").toString()))
          actionDispatched = false;
        finish(result);
      }
    };
    if (op == "web_inspect") {
      web->inspect(done);
      return;
    }
    if (!web->current(args)) {
      finish({{"error", "stale_snapshot"}});
      return;
    }
    if (!confirmed) {
      webConfirm(args, id, url);
      return;
    }
    actionDispatched = true;
    web->act(args, done);
  });
}
void VaultAccess::webConfirm(const QJsonObject &args, const QString &id,
                             const QUrl &url) {
  if (QApplication::activeModalWidget()) {
    finish({{"error", "vault_busy"}});
    return;
  }
  auto *dialog = new QDialog(window);
  prompt = dialog;
  dialog->setWindowTitle(
      tx("Lumen · Webzugriff bestätigen", "Lumen · Confirm web access"));
  auto *layout = new QVBoxLayout(dialog);
  const auto op = args["operation"].toString();
  const auto action =
      op == "web_open"    ? tx("Webseite öffnen und für Lumen lesbar machen",
                               "Open website and let Lumen read it")
      : op == "web_login" ? tx("Mit diesem Vault-Login anmelden",
                               "Sign in with this Vault login")
      : op == "web_fill"  ? tx("Text eintragen", "Enter text")
                          : tx("Bedienelement anklicken", "Click control");
  QString detail = action + "\n\n" + catalog[id]["title"].toString() + "\n" +
                   url.toString(QUrl::FullyEncoded) + "\n" +
                   (web ? web->describe(args) : QString());
  if (op == "web_fill")
    detail += "\n\n" + args["text"].toString();
  detail +=
      tx("\n\nEin lokales Programm fragt an; es ist nicht als Lumen "
         "verifiziert. Sichtbare Seiteninhalte können während dieser Sitzung "
         "an dein KI-Modell gelangen. Aktionen können Daten beim Dienst "
         "ändern. Zugangsdaten werden nur lokal zur Anmeldung eingesetzt.",
         "\n\nA local program is requesting access; it is not verified as "
         "Lumen. Visible page content may reach your AI model during this "
         "session. Actions may change service data. Credentials are used "
         "locally to sign in.");
  auto *text = new QLabel(detail, dialog);
  text->setTextFormat(Qt::PlainText);
  text->setWordWrap(true);
  auto *scroll = new QScrollArea(dialog);
  scroll->setWidgetResizable(true);
  scroll->setWidget(text);
  layout->addWidget(scroll);
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel, dialog);
  auto *allow =
      buttons->addButton(tx("Erlauben", "Allow"), QDialogButtonBox::AcceptRole);
  allow->setAutoDefault(false);
  allow->setDefault(false);
  buttons->button(QDialogButtonBox::Cancel)->setDefault(true);
  layout->addWidget(buttons);
  dialog->resize(600, 420);
  connect(buttons, &QDialogButtonBox::accepted, dialog, &QDialog::accept);
  connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);
  const auto requestEpoch = epoch;
  connect(dialog, &QDialog::finished, this,
          [this, args, requestEpoch, dialog, url](int result) {
            if (prompt == dialog)
              prompt.clear();
            dialog->deleteLater();
            if (requestEpoch != epoch || !peer)
              return;
            if (result != QDialog::Accepted) {
              finish({{"error", "access_denied"}});
              return;
            }
            webRead(args, true, url);
          });
  dialog->open();
  buttons->button(QDialogButtonBox::Cancel)->setFocus();
}

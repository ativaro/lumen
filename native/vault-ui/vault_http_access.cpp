// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "connection.h"
#include "vault.h"
#include "vault_http.h"

void VaultAccess::closeHttp() {
  auto previous = http;
  http.clear(); httpEntry.clear(); httpPlan = {};
  if (previous) delete previous;
}
void VaultAccess::httpRequest(const QJsonObject &args) {
  if (!VaultHttp::validRequest(args)) { finish({{"error", "invalid_request"}}); return; }
  const auto op = args["operation"].toString();
  if (op != "http_open" && (!http || args["session"] != http->session())) { finish({{"error", "http_session_closed"}}); return; }
  if (op == "http_close") { closeHttp(); finish({{"closed", true}}); return; }
  if (QApplication::activeModalWidget()) { finish({{"error", "vault_busy"}}); return; }
  if (op == "http_open" && http) { finish({{"error", "http_session_already_open"}}); return; }
  httpRead(args, false);
}
void VaultAccess::httpRead(const QJsonObject &args, bool confirmed, const QUrl &approved) {
  const bool opening = args["operation"] == "http_open";
  const auto id = opening ? args["reference"].toString().mid(6) : httpEntry;
  if (!catalog.contains(id)) { closeHttp(); finish({{"error", "connection_not_enabled"}}); return; }
  const auto generation = epoch;
  reader(id, [this, args, confirmed, approved, opening, id, generation](QStringList fields) {
    auto user = VaultConnection::value(fields, "UserName"), password = VaultConnection::value(fields, "Password");
    const auto savedUrl = VaultConnection::value(fields, "URL");
    const auto apiBase = VaultConnection::value(fields, "LumenApiBase");
    const QUrl stored(VaultConnection::value(fields, "LumenType") == "token" && !apiBase.isEmpty() ? apiBase : savedUrl, QUrl::StrictMode);
    const bool enabled = VaultConnection::value(fields, "LumenHidden") != "1" &&
        QStringList{"login", "token"}.contains(VaultConnection::value(fields, "LumenType")) &&
        VaultConnection::value(fields, "LumenTrash") != "1";
    for (auto &f : fields) wipe(f);
    auto clear = qScopeGuard([&] { wipe(user); wipe(password); });
    if (generation != epoch || !peer) return;
    if (!enabled || !catalog.contains(id) || password.isEmpty() || password.size() > 4096 || user.size() > 4096 ||
        (confirmed && approved != stored) || (!opening && (!http || args["session"] != http->session() || !http->matches(stored, user, password)))) {
      closeHttp(); finish({{"error", "access_revoked_or_invalid_profile"}}); return;
    }
    const auto origin = VaultHttp::origin(stored);
    if (origin.isEmpty()) { closeHttp(); finish({{"error", "http_url_required"}}); return; }
    auto step = args; step.remove("operation"); step.remove("session");
    const bool planned = !opening && !httpPlan.isEmpty() && httpPlan.first().toObject() == step;
    if (!opening && !planned) httpPlan = {};
    if (!confirmed && !planned) {
      auto *dialog = new QDialog(window); prompt = dialog;
      dialog->setWindowTitle(tx("Lumen · Dienstzugriff bestätigen", "Lumen · Confirm service access"));
      auto *layout = new QVBoxLayout(dialog);
      const auto plan = args["requests"].toArray();
      QString details;
      if (opening && !plan.isEmpty()) {
        details = tx("Diesen Ablauf einmal erlauben. Jeder Schritt gilt genau einmal in dieser Reihenfolge, maximal 10 Minuten. Zusätzliche oder geänderte Anfragen benötigen eine neue Freigabe.\n",
                     "Allow this workflow once. Each step is valid once in this order, for up to 10 minutes. Additional or changed requests need new approval.\n");
        for (int i = 0; i < plan.size(); ++i) {
          const auto item = plan[i].toObject();
          details += "\n" + QString::number(i + 1) + ". " + item["method"].toString() + " " + item["path"].toString() + "\n" + QString::fromUtf8(QJsonDocument(item).toJson(QJsonDocument::Indented));
        }
      } else details = opening ? tx("Temporäre HTTP-Sitzung öffnen. Dies meldet dich noch nicht an.", "Open a temporary HTTP session. This does not log you in yet.")
                               : QString::fromUtf8(QJsonDocument(step).toJson(QJsonDocument::Indented));
      const auto message = catalog.value(id)["title"].toString() + "\n" + origin.toString() + "\n\n" + details +
          tx("\n\nEin lokales Programm fragt an; es ist nicht als Lumen verifiziert. Zugangsdaten-Platzhalter werden erst nativ eingesetzt. Cookies und Sitzungstokens bleiben lokal. Anfragen können Daten ändern; Antworten können an dein KI-Modell gelangen. Ein Abbruch macht gesendete Änderungen nicht rückgängig.",
             "\n\nA local program is requesting access; it is not verified as Lumen. Credential placeholders are filled only in native code. Cookies and session tokens stay local. Requests may change data; responses may reach your AI model. Cancellation does not undo changes already sent.");
      auto *text = new QLabel(message); text->setObjectName("httpApprovalDetails"); text->setTextFormat(Qt::PlainText); text->setWordWrap(true);
      auto *scroll = new QScrollArea; scroll->setWidgetResizable(true); scroll->setWidget(text); layout->addWidget(scroll);
      const bool plaintext = origin.scheme() == "http";
      auto *plain = new QCheckBox(tx("HTTP ist unverschlüsselt: Zugangsdaten und Sitzung können im Netzwerk mitgelesen werden. Für den angezeigten Ablauf trotzdem erlauben.", "HTTP is unencrypted: credentials and session data can be read on the network. Allow the displayed workflow anyway."));
      plain->setObjectName("httpAllowPlaintext"); plain->setVisible(plaintext); layout->addWidget(plain);
      auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel);
      auto *allow = buttons->addButton(plan.isEmpty() ? tx("Erlauben", "Allow") : tx("Ablauf erlauben", "Allow workflow"), QDialogButtonBox::AcceptRole);
      allow->setObjectName("httpAllow"); allow->setEnabled(!plaintext);
      connect(plain, &QCheckBox::toggled, allow, &QPushButton::setEnabled);
      allow->setAutoDefault(false); allow->setDefault(false); buttons->button(QDialogButtonBox::Cancel)->setDefault(true);
      layout->addWidget(buttons);
      connect(buttons, &QDialogButtonBox::accepted, dialog, &QDialog::accept);
      connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);
      connect(dialog, &QDialog::finished, this, [this, dialog, args, stored, generation, plain, plaintext](int result) {
        if (prompt == dialog) prompt.clear();
        dialog->deleteLater();
        if (generation != epoch || !peer) return;
        if (result != QDialog::Accepted || (plaintext && !plain->isChecked())) { finish({{"error", "access_denied"}}); return; }
        httpRead(args, true, stored);
      });
      dialog->resize(660, 480); dialog->open(); buttons->button(QDialogButtonBox::Cancel)->setFocus(); return;
    }
    if (opening) {
      http = new VaultHttp(stored, user, password, this); httpEntry = id; httpPlan = args["requests"].toArray();
      const auto session = http->session();
      QTimer::singleShot(600000, this, [this, session] {
        if (http && http->session() == session) { closeHttp(); if (peer) finish({{"error", "http_session_closed"}}); }
      });
      finish({{"session", session}, {"origin", origin.toString()}, {"authentication_verified", false}, {"approved_requests", httpPlan.size()}}); return;
    }
    // Consume before dispatch: an uncertain outcome must never replay a grant.
    if (planned) httpPlan.removeFirst();
    actionDispatched = true;
    http->request(args, [this, generation](QJsonObject result) {
      if (generation != epoch || !peer) return;
      const int status = result["http_status"].toInt();
      if (result.contains("error") || status < 200 || status >= 300) httpPlan = {};
      finish(result);
    });
  });
}

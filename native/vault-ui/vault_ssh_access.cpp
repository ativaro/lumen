// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "connection.h"
#include "vault.h"
#include "vault_ssh.h"

void VaultAccess::sshRequest(const QJsonObject &args) {
  const bool execute = args["operation"] == "ssh_exec";
  const bool hasPort = args.contains("port");
  const int port = args.value("port").toInt(-1);
  if ((hasPort && (!args["port"].isDouble() || port < 1 || port > 65535 ||
                   args["port"].toDouble() != port)) || (args["operation"] != "ssh_check" && !execute) ||
      args.size() != (execute ? 3 : 2) + (hasPort ? 1 : 0) || !args["reference"].isString() ||
      !args["reference"].toString().startsWith("vault:") ||
      (execute && (!args["command"].isString() ||
                   !VaultSsh::validCommand(args["command"].toString())))) {
    finish({{"error", "invalid_request"}});
    return;
  }
  const auto id = args["reference"].toString().mid(6);
  if (!catalog.contains(id) || catalog.value(id)["kind"] != "login") {
    finish({{"error", "connection_not_enabled"}});
    return;
  }
  if (QApplication::activeModalWidget()) {
    finish({{"error", "vault_busy"}});
    return;
  }
  const auto generation = epoch;
  reader(id, [this, args, id, generation, hasPort, port](QStringList fields) {
    auto user = VaultConnection::value(fields, "UserName"),
         password = VaultConnection::value(fields, "Password");
    const QUrl stored(VaultConnection::value(fields, "URL"), QUrl::StrictMode);
    const QUrl url = VaultSsh::loginTarget(stored, hasPort ? port : 0);
    const bool enabled =
        VaultConnection::value(fields, "LumenType") == "login" &&
        VaultConnection::value(fields, "LumenHidden") != "1";
    for (auto &field : fields)
      wipe(field);
    if (generation != epoch || !peer) {
      wipe(user);
      wipe(password);
      return;
    }
    if (!enabled || !VaultSsh::validUrl(url) || user.isEmpty() ||
        password.isEmpty()) {
      wipe(user);
      wipe(password);
      finish({{"error", !VaultSsh::validUrl(url)
                            ? "ssh_url_required"
                            : "access_revoked_or_invalid_profile"}});
      return;
    }
    auto *worker = new VaultSsh(stored, user, password, args["command"].toString(),
                                sshKnownHosts, hasPort ? port : 0);
    wipe(user);
    wipe(password);
    ssh = worker;
    connect(worker, &QThread::finished, worker, &QObject::deleteLater);
    connect(worker, &VaultSsh::resultReady, this,
            [this, worker, generation](QJsonObject result) {
              if (generation == epoch && peer && ssh == worker)
                finish(result);
            });
    connect(worker, &VaultSsh::executionReady, this,
            [this, worker, id, generation] {
              if (generation == epoch && peer && ssh == worker)
                sshRevalidate(id, generation, 2);
              else
                worker->cancel();
            });
    connect(
        worker, &VaultSsh::approvalNeeded, this,
        [this, worker, args, id, url, stored, generation](const QString &fingerprint,
                                                  bool known) {
          if (generation != epoch || !peer || ssh != worker) {
            worker->cancel();
            return;
          }
          if (QApplication::activeModalWidget()) {
            finish({{"error", "vault_busy"}});
            return;
          }
          auto *dialog = new QDialog(window);
          prompt = dialog;
          dialog->setWindowTitle(tx("Lumen · SSH-Zugriff bestätigen",
                                    "Lumen · Confirm SSH access"));
          auto *layout = new QVBoxLayout(dialog);
          const auto text =
              tx("Eintrag: ", "Entry: ") +
              catalog.value(id)["title"].toString() + "\n" + url.toString() +
              "\n\nSHA256 · " + fingerprint + "\n\n" +
              (known ? tx("Bekannter Server-Schlüssel.", "Known server key.")
                     : tx("Neuer Server: Fingerabdruck unabhängig beim "
                          "Serverbetreiber prüfen.",
                          "New server: verify this fingerprint independently "
                          "with the server operator.")) +
              "\n\n" +
              (args["operation"] == "ssh_exec"
                   ? tx("Remote-Shell-Befehl (kann Daten ändern):\n",
                        "Remote shell command (may change data):\n") +
                         args["command"].toString()
                   : tx("Nur Anmeldung prüfen; keinen Befehl ausführen.",
                        "Check authentication only; run no command.")) +
              tx("\n\nEin lokales Programm fragt an; es ist nicht als Lumen "
                 "verifiziert. Ausgaben können an dein KI-Modell gelangen. Das "
                 "Passwort bleibt in der nativen Anmeldung. Bereits gesendete "
                 "Befehle können nach einem Abbruch auf dem Server "
                 "weiterlaufen.",
                 "\n\nA local program is requesting access; it is not verified "
                 "as Lumen. Output may reach your AI model. The password stays "
                 "in native authentication. Commands already sent may keep "
                 "running remotely after cancellation.");
          auto *label = new QLabel(text, dialog);
          label->setTextFormat(Qt::PlainText);
          label->setWordWrap(true);
          auto *scroll = new QScrollArea(dialog);
          scroll->setWidgetResizable(true);
          scroll->setWidget(label);
          layout->addWidget(scroll);
          auto *trust = new QCheckBox(
              tx("Fingerabdruck geprüft – diesem Server vertrauen",
                 "Fingerprint verified – trust this server"),
              dialog);
          trust->setObjectName("sshTrustHost");
          trust->setVisible(!known);
          layout->addWidget(trust);
          auto *useLogin = new QCheckBox(
              tx("Diesen Website-Login für das angezeigte SSH-Ziel verwenden",
                 "Use this website login for the displayed SSH target"), dialog);
          useLogin->setObjectName("sshUseWebLogin");
          const bool fromWeb = stored.scheme() != "ssh";
          useLogin->setVisible(fromWeb);
          layout->addWidget(useLogin);
          auto *buttons =
              new QDialogButtonBox(QDialogButtonBox::Cancel, dialog);
          auto *allow = buttons->addButton(tx("Erlauben", "Allow"),
                                           QDialogButtonBox::AcceptRole);
          allow->setObjectName("sshAllow");
          allow->setAutoDefault(false);
          allow->setDefault(false);
          const auto updateAllow = [allow, trust, useLogin, known, fromWeb] {
            allow->setEnabled((known || trust->isChecked()) &&
                              (!fromWeb || useLogin->isChecked()));
          };
          updateAllow();
          connect(trust, &QCheckBox::toggled, allow, updateAllow);
          connect(useLogin, &QCheckBox::toggled, allow, updateAllow);
          buttons->button(QDialogButtonBox::Cancel)->setDefault(true);
          layout->addWidget(buttons);
          connect(buttons, &QDialogButtonBox::accepted, dialog,
                  &QDialog::accept);
          connect(buttons, &QDialogButtonBox::rejected, dialog,
                  &QDialog::reject);
          connect(dialog, &QDialog::finished, this,
                  [this, id, generation, dialog, trust, known, useLogin, fromWeb](int result) {
                    const bool permitted = result == QDialog::Accepted &&
                                           (known || trust->isChecked()) &&
                                           (!fromWeb || useLogin->isChecked());
                    if (prompt == dialog)
                      prompt.clear();
                    dialog->deleteLater();
                    if (generation != epoch || !peer)
                      return;
                    if (!permitted) {
                      finish({{"error", "access_denied"}});
                      return;
                    }
                    sshRevalidate(id, generation, 1);
                  });
          dialog->resize(660, 500);
          dialog->open();
          buttons->button(QDialogButtonBox::Cancel)->setFocus();
        });
    worker->start();
  });
}
void VaultAccess::sshRevalidate(const QString &id, quint64 generation,
                                int stage) {
  const QPointer<VaultSsh> worker = ssh;
  reader(id, [this, id, generation, stage, worker](QStringList fields) {
    auto user = VaultConnection::value(fields, "UserName"),
         password = VaultConnection::value(fields, "Password");
    const QUrl url(VaultConnection::value(fields, "URL"), QUrl::StrictMode);
    const bool valid =
        worker && VaultConnection::value(fields, "LumenType") == "login" &&
        VaultConnection::value(fields, "LumenHidden") != "1" &&
        worker->matches(url, user, password);
    wipe(user);
    wipe(password);
    for (auto &field : fields)
      wipe(field);
    if (generation != epoch || !peer || worker != ssh || !worker)
      return;
    if (!valid || !catalog.contains(id)) {
      finish({{"error", "access_revoked_or_invalid_profile"}});
      return;
    }
    worker->approve(stage);
  });
}

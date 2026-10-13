// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "vault.h"
#include "passkey.h"
#include <sys/stat.h>
#include <unistd.h>
#include <memory>

static bool privateFile(const QString &path, bool directory = false) {
  struct stat st{};
  const auto name = QFile::encodeName(path);
  return lstat(name.constData(), &st) == 0 && st.st_uid == geteuid() && !(st.st_mode & 0077) &&
         (directory ? S_ISDIR(st.st_mode) : S_ISREG(st.st_mode) && st.st_nlink == 1);
}
QJsonObject VaultWindow::passkeyMetadata() const {
  if (!privateFile(root + "/passkey", true) || !privateFile(root + "/passkey/browser.json")) return {};
  QFile file(root + "/passkey/browser.json");
  if (!file.open(QIODevice::ReadOnly) || file.size() > 4096) return {};
  const auto result = QJsonDocument::fromJson(file.readAll()).object();
  static const QRegularExpression random("^[A-Za-z0-9_-]{43}$"), credential("^[A-Za-z0-9_-]{1,2048}$");
  if (result["version"].toInt() != 1 || !random.match(result["salt"].toString()).hasMatch() ||
      !random.match(result["binding"].toString()).hasMatch() || !credential.match(result["credential"].toString()).hasMatch()) return {};
  return result;
}
void VaultWindow::removePasskey() {
  if (!isOpen || editor || !privateFile(root + "/passkey", true)) return;
  if (QMessageBox::question(this, "Lumen Vault", tx("Schnellentsperrung auf diesem Rechner entfernen? Dein Hauptpasswort bleibt gültig. Den Passkey kannst du danach in Proton Pass löschen.",
      "Remove quick unlock on this computer? Your master password stays valid. You can then delete the passkey in Proton Pass."), QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel) != QMessageBox::Yes) return;
  if (!isOpen || !privateFile(root + "/passkey", true)) return;
  bool ok = true;
  for (const auto &name : {"browser.json", "vault.kdbx", "writer.lock"}) {
    const auto path = root + "/passkey/" + name;
    if (QFileInfo::exists(path)) ok = privateFile(path) && QFile::remove(path) && ok;
  }
  ok = QDir().rmdir(root + "/passkey") && ok;
  status->setText(ok ? tx("Passkey-Verknüpfung entfernt.", "Passkey link removed.") : tx("Nicht vollständig entfernt. Bitte den Zustand prüfen.", "Not fully removed. Please check the state."));
}
void VaultWindow::passkey(bool enroll) {
  if (editor || passkeyBridge || (enroll != isOpen)) return;
  if (enroll && QFileInfo::exists(root + "/passkey")) {
    QMessageBox::information(this, "Lumen Vault", tx("Entferne zuerst die vorhandene Passkey-Verknüpfung in den Einstellungen.", "First remove the existing passkey link in Settings.")); return;
  }
  auto metadata = passkeyMetadata();
  if (!enroll && metadata.isEmpty()) return;
  metadata["language"] = english ? "en" : "de";
  auto *dialog = new QDialog(this);
  editor = dialog;
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->setWindowTitle(tx("Lumen Vault · Passkey", "Lumen Vault · Passkey"));
  dialog->setWindowModality(Qt::WindowModal);
  dialog->setMinimumWidth(480);
  auto *layout = new QVBoxLayout(dialog);
  auto *notice = new QLabel(enroll ? tx("Richte Proton Pass oder einen anderen PRF-fähigen Passkey ein. Bestätige dafür einmal dein Hauptpasswort. Es verlässt den nativen Tresorprozess nicht in Richtung Browser.",
      "Set up Proton Pass or another PRF-capable passkey. Confirm your master password once. It is not sent from the native vault to the browser.") : tx("Bestätige deinen Passkey im Browser. Dein Hauptpasswort bleibt jederzeit als Alternative verfügbar.", "Confirm your passkey in the browser. Your master password remains available as an alternative."));
  notice->setWordWrap(true); layout->addWidget(notice);
  auto *password = vaultInput("passkeyMaster", true);
  password->setVisible(enroll); layout->addWidget(password);
  auto *message = new QLabel; message->setWordWrap(true); layout->addWidget(message);
  auto *start = new QPushButton(tx("Im Browser fortfahren", "Continue in browser"));
  start->setObjectName("passkeyStart"); layout->addWidget(start);
  connect(password, &QLineEdit::returnPressed, start, &QPushButton::click);
  auto *cancel = new QPushButton(tx("Abbrechen", "Cancel")); layout->addWidget(cancel);
  connect(cancel, &QPushButton::clicked, dialog, &QDialog::reject);
  connect(dialog, &QDialog::finished, this, [this, dialog](int result) {
    if (result == QDialog::Rejected) {
      ++generation;
      if (!isOpen) channel.stop();
      else if (dialog->property("passkeySubmitted").toBool()) {
        QTimer::singleShot(0, this, &VaultWindow::lock);
      }
    }
    if (passkeyBridge) { delete passkeyBridge; passkeyBridge.clear(); }
  });
  connect(start, &QPushButton::clicked, dialog, [this, dialog, password, message, start, metadata, enroll] {
    if ((enroll && password->text().isEmpty()) || enroll != isOpen || passkeyBridge) return;
    auto saved = std::shared_ptr<QString>(new QString(password->text()), [](QString *s) { wipe(*s); delete s; });
    password->clear(); password->setEnabled(false); start->setEnabled(false);
    auto *bridge = new PasskeyBridge(metadata, enroll, dialog);
    passkeyBridge = bridge;
    const auto epoch = generation;
    connect(bridge, &PasskeyBridge::failed, dialog, [this, message, saved] { wipe(*saved); message->setText(tx("Passkey-Verbindung abgelaufen. Bitte abbrechen und erneut starten.", "Passkey connection expired. Cancel and start again.")); });
    connect(bridge, &PasskeyBridge::completed, this, [this, bridge, epoch, enroll, saved, dialog = QPointer<QDialog>(dialog)](QString key, QString credential) {
      if (!dialog || generation != epoch || enroll != isOpen) { wipe(key); return; }
      auto metadata = bridge->metadata();
      metadata.remove("enroll"); metadata.remove("challenge"); metadata["credential"] = credential; metadata["version"] = 1;
      QStringList args = enroll ? QStringList{"enroll-passkey", *saved, key} : QStringList{"open-passkey", key};
      wipe(*saved); wipe(key);
      dialog->setProperty("passkeySubmitted", true);
      channel.call(std::move(args), [this, epoch, enroll, dialog, metadata](QStringList) {
        if (!dialog || generation != epoch) return;
        if (enroll) {
          bool ok = privateFile(root + "/passkey", true);
          QSaveFile file(root + "/passkey/browser.json");
          file.setDirectWriteFallback(false);
          const auto json = QJsonDocument(metadata).toJson(QJsonDocument::Compact);
          ok = ok && file.open(QIODevice::WriteOnly);
          ok = ok && file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
          ok = ok && file.write(json) == json.size() && file.commit();
          dialog->accept();
          if (status) status->setText(ok ? tx("Passkey eingerichtet. Das Hauptpasswort bleibt dein Wiederherstellungsweg.", "Passkey set up. Your master password remains your recovery method.") : tx("Passkey-Einrichtung nicht abgeschlossen. Verknüpfung entfernen und erneut versuchen.", "Passkey setup incomplete. Remove the link and try again."));
        } else {
          dialog->accept(); isOpen = true; sessionActivity(); keepalive.start(); replacePage(openPage()); refresh();
        }
      });
    });
    if (bridge->url().isEmpty() || !QDesktopServices::openUrl(bridge->url())) {
      bridge->stop(); message->setText(tx("Browser konnte nicht geöffnet werden. Bitte abbrechen und erneut versuchen.", "Could not open browser. Cancel and try again."));
    } else message->setText(tx("Warte auf deine Bestätigung im Browser …", "Waiting for your confirmation in the browser …"));
  });
  dialog->open();
}

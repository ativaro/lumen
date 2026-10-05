// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "backup_wizard.h"
#include "vault.h"
#include <QSaveFile>

bool backupKeyDestinationAllowed(const QString &file,
                                 const QString &destination) {
  const QFileInfo info(file);
  const auto parent = info.dir().canonicalPath();
  const auto target = QFileInfo(destination).canonicalFilePath();
  if (info.isSymLink() || parent.isEmpty() || target.isEmpty())
    return false;
  const auto chosen = QDir(parent).filePath(info.fileName());
  return chosen != target && !chosen.startsWith(target + '/');
}

static QLabel *copyLabel(const QString &text) {
  auto *label = new QLabel(text);
  label->setTextFormat(Qt::PlainText);
  label->setWordWrap(true);
  return label;
}
NetworkPicker::NetworkPicker(bool english, bool writable, BackupRequest request,
                             QWidget *parent)
    : QWidget(parent), english(english), writable(writable),
      request(std::move(request)) {
  auto tx = [english](const char *de, const char *en) {
    return QString::fromUtf8(english ? en : de);
  };
  auto *layout = new QVBoxLayout(this);
  layout->setContentsMargins(0, 0, 0, 0);
  auto *address = new QHBoxLayout;
  uri = new QLineEdit;
  uri->setObjectName("networkAddress");
  uri->setPlaceholderText(
      tx("Server oder Freigabe · automatisch suchen oder eingeben",
         "Server or share · discover or enter an address"));
  auto *browse = new QPushButton(tx("Öffnen", "Browse"));
  auto *refresh = new QPushButton(tx("Netzwerk suchen", "Discover network"));
  address->addWidget(uri, 1);
  address->addWidget(browse);
  address->addWidget(refresh);
  layout->addLayout(address);
  places = new QListWidget;
  places->setMinimumHeight(110);
  places->setMaximumHeight(170);
  places->setAccessibleName(tx("Server und Freigaben", "Servers and shares"));
  layout->addWidget(places);
  auto *form = new QFormLayout;
  user = new QLineEdit;
  password = new QLineEdit;
  domain = new QLineEdit;
  password->setEchoMode(QLineEdit::Password);
  password->setMaxLength(4096);
  password->setInputMethodHints(Qt::ImhSensitiveData | Qt::ImhNoPredictiveText |
                                Qt::ImhHiddenText);
  password->setContextMenuPolicy(Qt::NoContextMenu);
  user->setPlaceholderText(tx("Bei bestehender Anmeldung optional",
                              "Optional when already signed in"));
  domain->setPlaceholderText(tx("Optional", "Optional"));
  form->addRow(tx("Benutzername", "Username"), user);
  form->addRow(tx("Passwort", "Password"), password);
  form->addRow(tx("Domäne", "Domain"), domain);
  layout->addLayout(form);
  remember = new QCheckBox(tx("Zugang im System-Schlüsselbund merken",
                              "Remember credentials in the system keyring"));
  remember->setChecked(false);
  layout->addWidget(remember);
  auto *test =
      new QPushButton(writable ? tx("Verbindung testen und Ziel verwenden",
                                    "Test connection and use destination")
                               : tx("Ordner verbinden und auswählen",
                                    "Connect and select folder"));
  layout->addWidget(test);
  status = copyLabel(tx("Vorhandene Verbindungen werden mit angezeigt.",
                        "Existing connections are included."));
  status->setObjectName("muted");
  layout->addWidget(status);
  connect(browse, &QPushButton::clicked, this, [this] { perform("browse"); });
  connect(refresh, &QPushButton::clicked, this, &NetworkPicker::discover);
  connect(uri, &QLineEdit::textChanged, this,
          [this, lastHost = QString()](const QString &text) mutable {
            const auto host =
                QUrl(text.startsWith("smb://") ? text : "smb://" + text).host();
            if (host != lastHost) {
              password->clear();
              user->clear();
              domain->clear();
            }
            lastHost = host;
            selection = {};
          });
  for (auto *field : {user, password, domain})
    connect(field, &QLineEdit::textEdited, this, [this] { selection = {}; });
  connect(remember, &QCheckBox::toggled, this, [this] { selection = {}; });
  connect(places, &QListWidget::itemClicked, this,
          [this](QListWidgetItem *item) {
            uri->setText(item->data(Qt::UserRole).toString());
            selection = {};
          });
  connect(places, &QListWidget::itemDoubleClicked, this,
          [this](QListWidgetItem *) { perform("browse"); });
  connect(test, &QPushButton::clicked, this,
          [this] { perform(this->writable ? "test" : "resolve"); });
}
void NetworkPicker::discover() {
  uri->setText("smb://");
  perform("discover");
}
void NetworkPicker::perform(QString action) {
  setEnabled(false);
  status->setText(english ? "Connecting …" : "Verbindung wird geprüft …");
  QJsonObject args{{"op", "network"},
                   {"action", action},
                   {"uri", uri->text()},
                   {"username", user->text()},
                   {"password", password->text()},
                   {"domain", domain->text()},
                   {"remember", remember->isChecked()}};
  if (!selection["network_id"].toString().isEmpty())
    args["network_id"] = selection["network_id"];
  selection = {};
  const auto guard = QPointer<NetworkPicker>(this);
  request(
      args,
      [guard, action](QJsonValue reply) {
        if (!guard)
          return;
        auto *self = guard.data();
        self->setEnabled(true);
        const auto result = reply.toObject();
        if (action == "test" || action == "resolve") {
          self->selection = result;
          self->password->clear();
          self->status->setText(self->english
                                    ? "Connected. The folder is ready."
                                    : "Verbunden. Der Ordner ist bereit.");
          emit self->selected(result);
        } else {
          self->places->clear();
          for (auto item : result["items"].toArray()) {
            const auto row = item.toObject();
            auto *entry =
                new QListWidgetItem(QIcon::fromTheme("folder-network"),
                                    row["label"].toString(), self->places);
            entry->setData(Qt::UserRole, row["uri"].toString());
          }
          self->status->setText(
              self->places->count()
                  ? (self->english
                         ? "Choose a server/share. Double-click to browse."
                         : "Server/Freigabe wählen. Doppelklick öffnet den "
                           "Inhalt.")
                  : (self->english ? "No advertised shares found. Enter a "
                                     "server address above."
                                   : "Keine Freigaben gefunden. Oben eine "
                                     "Serveradresse eingeben."));
        }
      },
      [guard](QString message) {
        if (guard) {
          guard->setEnabled(true);
          guard->status->setText(message);
        }
      });
}

QString BackupWizard::tx(const char *de, const char *en) const {
  return QString::fromUtf8(english ? en : de);
}
BackupWizard::BackupWizard(bool english, BackupRequest request, QWidget *parent)
    : QWizard(parent), english(english), request(std::move(request)) {
  setWindowTitle(tx("Deine Sicherung einrichten", "Set up your backup"));
  setObjectName("backupWizard");
  setWizardStyle(QWizard::ModernStyle);
  setOption(QWizard::NoBackButtonOnStartPage);
  setOption(QWizard::NoBackButtonOnLastPage, false);
  resize(840, 760);
  setMinimumSize(700, 640);
  setButtonText(QWizard::NextButton, tx("Weiter", "Continue"));
  setButtonText(QWizard::BackButton, tx("Zurück", "Back"));
  setButtonText(QWizard::CancelButton, tx("Abbrechen", "Cancel"));
  setButtonText(QWizard::FinishButton, tx("Sicherung starten", "Start backup"));
  setStyleSheet("QWizard#backupWizard QGroupBox { margin-top: 12px; padding: "
                "14px; border: 1px solid palette(mid); border-radius: 12px; } "
                "QWizard#backupWizard QGroupBox::title { padding: 0 8px; } ");
  auto page = [this](const QString &title, const QString &subtitle) {
    auto *p = new QWizardPage;
    p->setTitle(title);
    p->setSubTitle(subtitle);
    addPage(p);
    return p;
  };
  auto *sources = page(
      tx("1 · Was möchtest du schützen?",
         "1 · What would you like to protect?"),
      tx("Alles Wichtige ist vorausgewählt. Du kannst jeden Bereich anpassen.",
         "Important data is selected. You can customize each area."));
  auto *sourceLayout = new QVBoxLayout(sources);
  auto *cards = new QHBoxLayout;
  for (const QString group : {"files", "lumen", "vault"}) {
    auto *box =
        new QGroupBox(group == "files"   ? tx("Meine Dateien", "My files")
                      : group == "lumen" ? "Mein Lumen"
                                         : tx("Mein Tresor", "My vault"));
    if (english && group == "lumen")
      box->setTitle("My Lumen");
    box->setCheckable(true);
    box->setChecked(true);
    auto *column = new QVBoxLayout(box);
    auto *list = new QListWidget;
    list->setMinimumWidth(175);
    list->setMinimumHeight(210);
    list->setAccessibleName(box->title());
    column->addWidget(list);
    sourceLists[group] = list;
    sourceGroups[group] = box;
    cards->addWidget(box);
  }
  sourceLayout->addLayout(cards);
  auto *extras = new QHBoxLayout;
  auto *addFolder =
      new QPushButton(tx("Weiteren Ordner hinzufügen", "Add another folder"));
  auto *addNetwork =
      new QPushButton(tx("Ordner vom NAS hinzufügen", "Add a NAS folder"));
  extras->addWidget(addFolder);
  extras->addWidget(addNetwork);
  sourceLayout->addLayout(extras);
  auto append = [this](QString path, QString label) {
    if (path.isEmpty())
      return;
    auto *item = new QListWidgetItem(label, sourceLists["files"]);
    item->setData(Qt::UserRole, path);
    item->setToolTip(path);
    item->setCheckState(Qt::Checked);
    sourceGroups["files"]->setChecked(true);
  };
  connect(addFolder, &QPushButton::clicked, this, [this, append] {
    const auto path = QFileDialog::getExistingDirectory(
        this, tx("Ordner schützen", "Protect folder"));
    append(path, path);
  });
  connect(addNetwork, &QPushButton::clicked, this, [this, append] {
    QDialog dialog(this);
    dialog.setWindowTitle(
        tx("Netzwerkordner hinzufügen", "Add network folder"));
    dialog.resize(720, 600);
    auto *layout = new QVBoxLayout(&dialog);
    auto *picker =
        new NetworkPicker(this->english, false, this->request, &dialog);
    layout->addWidget(picker);
    connect(picker, &NetworkPicker::selected, &dialog,
            [this, append, &dialog](QJsonObject value) {
              append(value["path"].toString(), value["uri"].toString());
              remoteSources.append(
                  QJsonObject{{"path", value["path"]},
                              {"uri", value["uri"]},
                              {"network_id", value["network_id"]}});
              dialog.accept();
            });
    picker->discover();
    dialog.exec();
  });
  sourceLayout->addWidget(
      copyLabel(tx("Gespeicherte Lumen-Daten und verschlüsselte Tresordateien. "
                   "Offene, ungespeicherte Änderungen sind nicht enthalten.",
                   "Saved Lumen data and encrypted vault files. Unsaved edits "
                   "are not included.")));

  auto *targetPage = page(tx("2 · Wo soll deine Sicherung liegen?",
                             "2 · Where should your backup live?"),
                          tx("USB, NAS oder ein anderer Ordner. Wir prüfen das "
                             "Ziel vor dem ersten Lauf.",
                             "USB, NAS or another folder. We test the "
                             "destination before the first run."));
  auto *targets = new QVBoxLayout(targetPage);
  targetKind = new QComboBox;
  targetKind->addItem(tx("USB-Laufwerk / Ordner", "USB drive / folder"),
                      "local");
  targetKind->addItem(tx("NAS / Netzwerk", "NAS / network"), "network");
  targets->addWidget(targetKind);
  auto *local = new QWidget;
  auto *localLayout = new QHBoxLayout(local);
  target = new QLineEdit;
  target->setObjectName("backupDestination");
  target->setPlaceholderText(tx("Ziellaufwerk oder Ordner auswählen",
                                "Select a destination drive or folder"));
  auto *choose = new QPushButton(tx("Auswählen …", "Choose …"));
  localLayout->addWidget(target, 1);
  localLayout->addWidget(choose);
  targets->addWidget(local);
  connect(choose, &QPushButton::clicked, this, [this] {
    const auto path = QFileDialog::getExistingDirectory(
        this, tx("Sicherungsziel", "Backup destination"));
    if (!path.isEmpty())
      target->setText(path);
  });
  connect(target, &QLineEdit::textChanged, this, [this] { destination = {}; });
  network = new NetworkPicker(english, true, this->request);
  targets->addWidget(network);
  network->hide();
  connect(network, &NetworkPicker::selected, this, [this](QJsonObject result) {
    destination = result;
    state->setText(tx("Netzwerkziel geprüft.", "Network destination checked."));
  });
  connect(targetKind, &QComboBox::currentIndexChanged, this,
          [this, local](int index) {
            destination = {};
            local->setVisible(index == 0);
            network->setVisible(index == 1);
            if (index == 1)
              network->discover();
          });
  auto *prepare = new QPushButton(
      tx("Netzwerk-Unterstützung einrichten …", "Set up network support …"));
  targets->addWidget(prepare);
  connect(prepare, &QPushButton::clicked, this,
          [] { QProcess::startDetached("lumen-setup-wizard", {}); });
  targets->addStretch();

  auto *automatic = page(
      tx("3 · Automatisch und verschlüsselt", "3 · Automatic and encrypted"),
      tx("Deine Sicherung erhält einen eigenen Wiederherstellungsschlüssel.",
         "Your backup gets its own recovery key."));
  auto *protection = new QVBoxLayout(automatic);
  auto *form = new QFormLayout;
  name = new QLineEdit(tx("Meine Sicherung", "My backup"));
  form->addRow(tx("Name", "Name"), name);
  schedule = new QComboBox;
  schedule->addItem(tx("Täglich · nachholen, sobald erreichbar",
                       "Daily · catch up when available"),
                    86400);
  schedule->addItem(tx("Wöchentlich", "Weekly"), 604800);
  schedule->addItem(tx("Manuell", "Manual"), 0);
  form->addRow(tx("Sichern", "Back up"), schedule);
  key = new QLineEdit;
  key->setObjectName("backupRecoveryKey");
  key->setEchoMode(QLineEdit::Password);
  key->setContextMenuPolicy(Qt::NoContextMenu);
  key->setInputMethodHints(Qt::ImhSensitiveData | Qt::ImhNoPredictiveText |
                           Qt::ImhHiddenText);
  QString generated;
  for (int i = 0; i < 8; ++i)
    generated += QString("%1").arg(QRandomGenerator::system()->generate(), 8,
                                   16, QLatin1Char('0'));
  key->setText(generated);
  wipe(generated);
  form->addRow(tx("Sicherungsschlüssel", "Backup key"), key);
  protection->addLayout(form);
  keyHint = copyLabel(
      tx("Für automatische Sicherungen wird der Schlüssel im "
         "System-Schlüsselbund gespeichert. Bewahre eine Kopie getrennt von "
         "diesem Rechner und vom gesicherten Tresor auf.",
         "For automatic backups, the key is stored in the system keyring. Keep "
         "a copy separately from this computer and the backed-up vault."));
  protection->addWidget(keyHint);
  exportButton =
      new QPushButton(tx("Wiederherstellungsschlüssel als Datei sichern …",
                         "Save recovery key as a file …"));
  protection->addWidget(exportButton);
  connect(exportButton, &QPushButton::clicked, this, &BackupWizard::exportKey);
  keySaved = new QCheckBox(tx("Ich habe den Schlüssel unabhängig aufbewahrt.",
                              "I have kept the key independently."));
  protection->addWidget(keySaved);
  connect(key, &QLineEdit::textChanged, this,
          [this] { keySaved->setChecked(false); });
  protection->addWidget(copyLabel(
      tx("Der Sicherungsschlüssel stellt die Tresordatei wieder her. Zum "
         "Öffnen deines Tresors brauchst du weiterhin dessen Master-Passwort.",
         "The backup key restores the vault file. Opening that vault still "
         "requires its master password.")));
  protection->addStretch();

  auto *last =
      page(tx("4 · Prüfen und starten", "4 · Review and start"),
           tx("Die erste Sicherung wird anschließend mit einer "
              "Wiederherstellungsprobe geprüft.",
              "The first backup is followed by a small restore test."));
  auto *lastLayout = new QVBoxLayout(last);
  review = copyLabel("");
  review->setObjectName("backupReview");
  lastLayout->addWidget(review);
  lastLayout->addStretch();
  state = copyLabel("");
  setSideWidget(nullptr);
  lastLayout->addWidget(state);
  connect(this, &QWizard::currentIdChanged, this, [this](int id) {
    if (id == 2) {
      const bool existing = destination["existing"].toBool();
      const bool wasExisting = key->property("existingBackup").toBool();
      if (existing != wasExisting) {
        key->clear();
        if (!existing) {
          QString generated;
          for (int i = 0; i < 8; ++i)
            generated +=
                QString("%1").arg(QRandomGenerator::system()->generate(), 8, 16,
                                  QLatin1Char('0'));
          key->setText(generated);
          wipe(generated);
        }
      }
      key->setProperty("existingBackup", existing);
      keySaved->setVisible(!existing);
      exportButton->setVisible(!existing);
      schedule->setEnabled(!existing);
      if (!existing)
        keyHint->setText(tx("Bewahre den Sicherungsschlüssel getrennt von "
                            "diesem Rechner und vom gesicherten Tresor auf.",
                            "Keep the backup key separately from this computer "
                            "and the backed-up vault."));
    }
    if (id == 2 && destination["existing"].toBool()) {
      keyHint->setText(tx("Bestehende Sicherung erkannt. Gib ihren bisherigen "
                          "Sicherungsschlüssel ein. Es wird nichts am "
                          "Sicherungsbestand geändert.",
                          "Existing backup found. Enter its original backup "
                          "key. Its contents will remain unchanged."));
      keySaved->hide();
      exportButton->hide();
      schedule->setEnabled(false);
    }
    if (id == 3)
      summary();
  });
  QTimer::singleShot(0, this, [this] {
    work({{"op", "setup_inventory"}}, [this](QJsonValue data) {
      const auto inventory = data.toObject();
      for (auto it = sourceLists.begin(); it != sourceLists.end(); ++it) {
        for (auto value : inventory[it.key()].toArray()) {
          const auto row = value.toObject();
          auto *item = new QListWidgetItem(row["label"].toString(), it.value());
          item->setData(Qt::UserRole, row["path"].toString());
          item->setToolTip(row["path"].toString());
          item->setCheckState(Qt::Checked);
        }
        if (!it.value()->count())
          sourceGroups[it.key()]->setChecked(false);
      }
    });
  });
}
void BackupWizard::work(QJsonObject args,
                        std::function<void(QJsonValue)> done) {
  if (working)
    return;
  working = true;
  if (currentPage())
    currentPage()->setEnabled(false);
  for (auto id :
       {QWizard::NextButton, QWizard::BackButton, QWizard::FinishButton})
    button(id)->setEnabled(false);
  state->setText(
      args["op"] == "finish_setup"
          ? tx("Erste Sicherung läuft … Anschließend prüfen wir die "
               "Wiederherstellung. Bei vielen Dateien kann das länger dauern.",
               "Creating the first backup … Then we verify recovery. A large "
               "collection can take some time.")
          : tx("Bitte warten …", "Please wait …"));
  const auto guard = QPointer<BackupWizard>(this);
  request(
      args,
      [guard, done](QJsonValue value) {
        if (!guard)
          return;
        guard->working = false;
        if (guard->currentPage())
          guard->currentPage()->setEnabled(true);
        guard->button(QWizard::NextButton)->setEnabled(true);
        guard->button(QWizard::BackButton)->setEnabled(guard->planId.isEmpty());
        guard->button(QWizard::FinishButton)->setEnabled(true);
        guard->state->clear();
        done(value);
      },
      [guard](QString message) {
        if (!guard)
          return;
        guard->working = false;
        if (guard->currentPage())
          guard->currentPage()->setEnabled(true);
        guard->button(QWizard::NextButton)->setEnabled(true);
        guard->button(QWizard::BackButton)->setEnabled(guard->planId.isEmpty());
        guard->button(QWizard::FinishButton)->setEnabled(true);
        guard->state->setText(message);
        QMessageBox::warning(guard, "Lumen Vault", message);
      });
}
QJsonObject BackupWizard::groups() const {
  QJsonObject groups;
  for (auto it = sourceLists.begin(); it != sourceLists.end(); ++it) {
    QJsonArray values;
    if (sourceGroups[it.key()]->isChecked())
      for (int i = 0; i < it.value()->count(); ++i)
        if (it.value()->item(i)->checkState() == Qt::Checked)
          values.append(it.value()->item(i)->data(Qt::UserRole).toString());
    groups[it.key()] = values;
  }
  return groups;
}
bool BackupWizard::validateCurrentPage() {
  if (working)
    return false;
  if (currentId() == 1) {
    if (targetKind->currentData() == "network") {
      destination = network->selection;
      if (destination["path"].toString().isEmpty()) {
        QMessageBox::information(this, "Lumen Vault",
                                 tx("Bitte die Freigabe verbinden und testen.",
                                    "Connect and test the share first."));
        return false;
      }
    } else if (destination["path"].toString() != target->text()) {
      work({{"op", "test_target"}, {"path", target->text()}},
           [this](QJsonValue value) {
             destination = value.toObject();
             target->blockSignals(true);
             target->setText(destination["path"].toString());
             target->blockSignals(false);
             next();
           });
      return false;
    }
  }
  if (currentId() == 2 &&
      (key->text().size() < (destination["existing"].toBool() ? 1 : 12) ||
       (!destination["existing"].toBool() && !keySaved->isChecked()))) {
    QMessageBox::information(
        this, "Lumen Vault",
        tx("Schlüssel eingeben und seine unabhängige Aufbewahrung bestätigen.",
           "Enter the key and confirm its independent storage."));
    return false;
  }
  return true;
}
void BackupWizard::summary() {
  const auto values = groups();
  review->setText(
      tx("Ziel: ", "Destination: ") +
      destination["uri"].toString(destination["path"].toString()) + "\n\n" +
      tx("Dateien: ", "Files: ") +
      QString::number(values["files"].toArray().size()) +
      tx(" Quellen", " sources") + "\n" + tx("Lumen: ", "Lumen: ") +
      QString::number(values["lumen"].toArray().size()) +
      tx(" Quellen", " sources") + "\n" + tx("Tresor: ", "Vault: ") +
      (values["vault"].toArray().isEmpty()
           ? tx("nicht ausgewählt", "not selected")
           : tx("verschlüsselte Kopie", "encrypted copy")) +
      "\n\n" +
      (destination["existing"].toBool()
           ? tx("Bestehende Sicherung zum Wiederherstellen verbinden.",
                "Connect an existing backup for recovery.")
           : schedule->currentText() + "\n" +
                 tx("Verschlüsseln → erste Sicherung → kleine "
                    "Wiederherstellungsprobe. Danach wird der Zeitplan "
                    "aktiviert.",
                    "Encrypt → first backup → small restore test. Then the "
                    "schedule is enabled.")));
  if (destination.contains("free"))
    review->setText(review->text() + "\n\n" +
                    tx("Am Ziel verfügbar: ", "Available at destination: ") +
                    QLocale(english ? QLocale::English : QLocale::German)
                        .formattedDataSize(destination["free"].toInteger()));
  if (!destination["uri"].toString().isEmpty() &&
      destination["network_id"].toString().isEmpty())
    review->setText(review->text() + "\n" +
                    tx("NAS-Zugang nicht gespeichert: Nach einer Abmeldung "
                       "kann eine erneute Anmeldung nötig sein.",
                       "NAS credentials are not saved: you may need to sign in "
                       "again after logging out."));
  setButtonText(QWizard::FinishButton,
                destination["existing"].toBool()
                    ? tx("Sicherung verbinden", "Connect backup")
                    : tx("Sicherung starten", "Start backup"));
}
void BackupWizard::exportKey() {
  const auto file = QFileDialog::getSaveFileName(
      this, tx("Unabhängig aufbewahren", "Keep independently"),
      "Lumen-Wiederherstellung.txt", "Text (*.txt)");
  if (file.isEmpty())
    return;
  if (!backupKeyDestinationAllowed(file, destination["path"].toString())) {
    QMessageBox::warning(
        this, "Lumen Vault",
        tx("Bitte den Schlüssel außerhalb des Sicherungsziels speichern.",
           "Save the key outside the backup destination."));
    return;
  }
  QSaveFile output(file);
  output.setDirectWriteFallback(false);
  if (!output.open(QIODevice::WriteOnly))
    return;
  output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
  auto text =
      (QString("Lumen · ") + name->text() + "\n" +
       destination["uri"].toString(destination["path"].toString()) + "\n" +
       tx("Sicherungsschlüssel: ", "Backup key: ") + key->text() + "\n\n" +
       tx("Lumen installieren → Vault → Sicherungen → Ziel auswählen und "
          "bestehende Sicherung verbinden. Die Sicherung liegt im Unterordner "
          "Lumen-Sicherung-… .\nZum Öffnen des wiederhergestellten Tresors "
          "wird weiterhin dessen Master-Passwort benötigt. NAS-Zugang separat "
          "aufbewahren.\n",
          "Install Lumen → Vault → Backups → choose the existing repository. "
          "The backup lives in a Lumen-Sicherung-… subfolder.\nOpening the "
          "restored vault still requires its master password. Keep NAS access "
          "independently too.\n"))
          .toUtf8();
  const bool written = output.write(text) == text.size() && output.commit();
  wipe(text);
  if (written)
    QMessageBox::information(
        this, "Lumen Vault",
        tx("Schlüssel gespeichert. Bestätige anschließend, dass du ihn "
           "unabhängig aufbewahrt hast.",
           "Key saved. Then confirm that you have kept it independently."));
  else
    QMessageBox::warning(this, "Lumen Vault",
                         tx("Schlüsseldatei konnte nicht gespeichert werden.",
                            "Could not save the recovery key file."));
}
void BackupWizard::accept() {
  if (working)
    return;
  if (completed) {
    key->clear();
    QWizard::accept();
    return;
  }
  if (!validateCurrentPage())
    return;
  if (!destination["existing"].toBool()) {
    bool any = false;
    for (const auto value : groups())
      any |= !value.toArray().isEmpty();
    if (!any) {
      QMessageBox::information(this, "Lumen Vault",
                               tx("Mindestens eine Quelle auswählen.",
                                  "Select at least one source."));
      return;
    }
  }
  auto finish = [this] {
    work({{"op", "finish_setup"}, {"id", planId}}, [this](QJsonValue) {
      completed = true;
      key->clear();
      review->setText(
          tx("Deine Sicherung ist eingerichtet.\n\nDie erste Sicherung und die "
             "kleine Wiederherstellungsprobe waren erfolgreich. Deine "
             "Einstellung zur automatischen Sicherung wurde übernommen.",
             "Your backup is ready.\n\nThe first backup and small restore test "
             "succeeded. Your automatic backup preference has been applied."));
      button(QWizard::BackButton)->setEnabled(false);
      setButtonText(QWizard::FinishButton, tx("Fertig", "Done"));
    });
  };
  if (!planId.isEmpty()) {
    finish();
    return;
  }
  QJsonArray selectedRemotes;
  const auto selectedFiles = groups()["files"].toArray();
  for (const auto source : remoteSources)
    if (selectedFiles.contains(source.toObject()["path"]))
      selectedRemotes.append(source);
  work({{"op", "configure"},
        {"title", name->text()},
        {"repository", destination["path"]},
        {"network_uri", destination["uri"]},
        {"network_id", destination["network_id"]},
        {"password", key->text()},
        {"groups", groups()},
        {"remote_sources", selectedRemotes},
        {"interval", schedule->currentData().toInt()},
        {"recovery_confirmed", keySaved->isChecked()},
        {"adopt", destination["existing"].toBool()}},
       [this, finish](QJsonValue result) {
         planId = result.toObject()["id"].toString();
         if (result.toObject()["restored_connection"].toBool()) {
           completed = true;
           accept();
         } else
           finish();
       });
}
void BackupWizard::reject() {
  if (working) {
    QMessageBox::information(this, "Lumen Vault",
                             tx("Der Vorgang läuft noch. Du kannst ihn nach "
                                "dem Schließen im Sicherungsbereich abbrechen.",
                                "The operation is still running. You can "
                                "cancel it from Backups after closing."));
  }
  key->clear();
  QWizard::reject();
}

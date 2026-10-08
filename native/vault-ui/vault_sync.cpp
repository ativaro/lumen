// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "bookstack.h"
#include "vault.h"

namespace {
using SyncReply = std::function<void(QJsonObject, QString)>;
QProcess *syncRequest(QObject *owner, const QString &root, QJsonObject request,
                      SyncReply done) {
  request["root"] = root;
  auto directory = QDir(QCoreApplication::applicationDirPath())
                       .absoluteFilePath("../../files");
  if (!QFileInfo::exists(directory + "/vault_sync.py"))
    directory =
        QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) +
        "/lumen/files";
  const auto python = QDir(directory).absoluteFilePath("../bin/lumen-python");
  auto *child = new QProcess(owner);
  auto *deadline = new QTimer(child);
  deadline->setSingleShot(true);
  QObject::connect(deadline, &QTimer::timeout, child, &QProcess::kill);
  deadline->start(45000);
  QObject::connect(child, &QProcess::errorOccurred, owner,
                   [child, done](QProcess::ProcessError error) {
                     if (error == QProcess::FailedToStart) {
                       child->deleteLater();
                       done({}, "runtime");
                     }
                   });
  QObject::connect(
      child, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), owner,
      [child, done](int code, QProcess::ExitStatus) {
        const auto output = child->readAllStandardOutput();
        const auto error = child->readAllStandardError();
        child->deleteLater();
        if (code != 0) {
          done({}, error.isEmpty() ? "transport"
                                   : QString::fromUtf8(error.left(1000)));
          return;
        }
        QJsonParseError parse;
        const auto result = QJsonDocument::fromJson(output, &parse);
        if (parse.error != QJsonParseError::NoError || !result.isObject()) {
          done({}, "invalid_response");
          return;
        }
        done(result.object(), {});
      });
  child->start(python, {directory + "/vault_sync.py"});
  child->write(QJsonDocument(request).toJson(QJsonDocument::Compact));
  child->closeWriteChannel();
  return child;
}
} // namespace

class SyncDialog final : public QDialog {
public:
  using Adopt = std::function<void(QString, QString, QString, QString, bool)>;
  SyncDialog(VaultWindow *owner, Channel *broker, QString directory, bool empty, Adopt adopt)
      : QDialog(owner), owner(owner), root(std::move(directory)) {
    setAttribute(Qt::WA_DeleteOnClose);
    setWindowModality(Qt::WindowModal);
    setWindowTitle(
        tx("Lumen Vault · Serverabgleich", "Lumen Vault · Server sync"));
    resize(780, 640);
    auto *box = new QVBoxLayout(this);
    box->setContentsMargins(24, 24, 24, 24);
    box->setSpacing(14);
    summary = new QLabel(tx("Dein Tresor auf deinen Geräten", "Your vault across your devices"));
    summary->setObjectName("syncSummary");
    summary->setWordWrap(true);
    auto font = summary->font(); font.setPointSize(18); font.setBold(true);
    summary->setFont(font);
    box->addWidget(summary);
    details = new QLabel;
    details->setTextFormat(Qt::PlainText);
    details->setWordWrap(true);
    box->addWidget(details);
    auto *help = new QLabel(
        tx("Nur verschlüsselte KDBX-Fassungen. Dein Hauptpasswort bleibt auf "
           "diesem Gerät. Ergänze Einträge oder übernimm eine vollständige "
           "Fassung. Unterschiedliche Einträge bleiben als Konfliktkopien "
           "erhalten.",
           "Encrypted KDBX versions only. Your master password stays on this "
           "device. Add entries or adopt a complete version. Different entries "
           "are preserved as conflict copies."));
    help->setWordWrap(true);
    box->addWidget(help);
    versions = new QListWidget;
    versions->setObjectName("syncVersions");
    versions->setAccessibleName(
        tx("Verschlüsselte Tresorfassungen", "Encrypted vault versions"));
    box->addWidget(versions, 1);
    password = vaultInput("syncMaster", true);
    password->setPlaceholderText(
        tx("Ursprüngliches Hauptpasswort · bleibt lokal",
           "Original master password · stays local"));
    password->setVisible(empty);
    box->addWidget(password);
    status = new QLabel;
    status->setTextFormat(Qt::PlainText);
    status->setWordWrap(true);
    box->addWidget(status);
    auto *row = new QHBoxLayout;
    box->addLayout(row);
    refresh = add(row, tx("Aktualisieren", "Refresh"), [this] { load(); });
    publish =
        add(row, tx("Lokale Fassung veröffentlichen", "Publish local version"),
            [this] {
              if (!confirmed(tx(
                      "Diese lokale, verschlüsselte Fassung zum aktuellen "
                      "Serverstand machen? Frühere Fassungen bleiben erhalten.",
                      "Make this local encrypted version the current server "
                      "version? Earlier versions are preserved.")))
                return;
              QString expected;
              for (const auto &value : info["versions"].toArray())
                if (value.toObject()["current"].toBool())
                  expected = value.toObject()["id"].toString();
              call({{"op", "upload"},
                    {"id", QUuid::createUuid().toString(QUuid::WithoutBraces)},
                    {"scope", info["scope"]},
                    {"expected", expected},
                    {"local_hash", info["local_hash"]}},
                   [this](QJsonObject result) {
                     load(result["applied"].toBool()
                              ? tx("Verschlüsselte Fassung veröffentlicht.",
                                   "Encrypted version published.")
                              : tx("Konflikt: Beide verschlüsselten Fassungen "
                                   "sind erhalten. Der aktuelle Serverstand "
                                   "wurde nicht ersetzt.",
                                   "Conflict: both encrypted versions were "
                                   "preserved. The current server version was "
                                   "not replaced."));
                   });
            });
    auto receive = [this, adopt, empty](bool merge) {
      const auto selected = selection();
      if (selected.isEmpty())
        return;
      const auto message =
          merge
              ? tx("Einträge und neue Ordner lokal zusammenführen? Abweichende "
                   "Einträge bleiben als ‚Sync conflict‘ erhalten. Es wird "
                   "nichts gelöscht. Bestehende Ordner und Tresoreinstellungen "
                   "bleiben lokal. API-/MCP-Freigaben müssen neu erlaubt "
                   "werden. "
                   "Lokal gelöschte Ordner benötigen eine manuelle Prüfung. "
                   "Anhänge und eigene Symbole werden noch nicht unterstützt.",
                   "Merge entries and new folders locally? Differing entries "
                   "are kept as 'Sync conflict' copies. Nothing is deleted. "
                   "Existing folders and vault settings stay local. API/MCP "
                   "access must be allowed again. Locally deleted folders "
                   "require manual review. Attachments and custom icons are "
                   "not yet supported.")
              : tx("Diese vollständige Fassung lokal übernehmen? Dein "
                   "bisheriger "
                   "Tresor bleibt als verschlüsselte Kopie erhalten. "
                   "API-/MCP-Freigaben "
                   "müssen danach neu erlaubt werden.",
                   "Use this complete version locally? Your previous vault "
                   "is retained "
                   "as an encrypted copy. API/MCP access must be allowed "
                   "again.");
      if (!confirmed(message))
        return;
      if (empty && password->text().isEmpty()) {
        status->setText(tx("Das ursprüngliche Hauptpasswort eingeben.",
                           "Enter the original master password."));
        return;
      }
      call({{"op", "download"},
            {"id", selected["id"]},
            {"scope", info["scope"]},
            {"sha256", selected["sha256"]}},
           [this, adopt, merge](QJsonObject value) {
             auto key = password->text();
             password->clear();
             adopt(value["path"].toString(), value["sha256"].toString(),
                   info["local_hash"].toString(), key, merge);
             wipe(key);
           });
    };
    auto *actions = new QHBoxLayout;
    box->addLayout(actions);
    preview = add(actions, tx("Änderungen prüfen", "Review changes"), [this, broker] {
      const auto selected = selection();
      if (selected.isEmpty()) return;
      call({{"op", "download"}, {"id", selected["id"]},
            {"scope", info["scope"]}, {"sha256", selected["sha256"]}},
           [this, broker](QJsonObject value) {
        checking = true; controls();
        status->setText(tx("Fassung wird lokal entschlüsselt und verglichen…", "Decrypting and comparing locally…"));
        broker->call({"preview-sync", value["path"].toString(), value["sha256"].toString(),
                      info["local_hash"].toString()}, [guard = QPointer<SyncDialog>(this)](QStringList counts) {
          if (!guard) return;
          guard->checking = false; guard->controls();
          guard->status->setText(guard->tx(
            "%1 neue Einträge · %2 abweichende Einträge. Beim Zusammenführen bleiben beide Fassungen erhalten. Dein Tresor ist unverändert.",
            "%1 new entries · %2 differing entries. Merging preserves both versions. Your vault is unchanged.").arg(counts.value(0), counts.value(1)));
        });
      });
    });
    preview->setObjectName("syncPreview");
    preview->setVisible(!empty);
    connect(broker, &Channel::failed, this, [this](const QString &) {
      checking = false; controls();
      status->setText(tx("Diese Fassung konnte nicht verglichen werden. Dein Tresor bleibt unverändert.",
                        "This version could not be compared. Your vault is unchanged."));
    });
    combine = add(actions, tx("Zusammenführen", "Merge entries"),
                  [receive] { receive(true); });
    combine->setObjectName("syncMerge");
    combine->setVisible(!empty);
    take = add(actions, tx("Fassung übernehmen", "Use selected version"),
               [receive] { receive(false); });
    auto *automatic = new QHBoxLayout;
    box->addLayout(automatic);
    autoEnable = add(
        automatic, tx("Automatik aktivieren", "Enable automatic sync"), [this] {
          if (!confirmed(
                  tx("Künftige lokale Änderungen im Hintergrund verschlüsselt "
                     "veröffentlichen und neue Serverfassungen empfangen – "
                     "auch bei geschlossenem oder gesperrtem Vault? Bei "
                     "Konflikten pausiert die Veröffentlichung. Empfangene "
                     "Fassungen werden im Tresor geprüft und übernommen.",
                     "Publish encrypted local changes and receive new server "
                     "versions in the background, even with Vault closed or "
                     "locked? Conflicts pause publishing. Incoming versions "
                     "are verified and adopted in the native vault.")))
            return;
          call({{"op", "auto-enable"}, {"scope", info["scope"]}},
               [this](QJsonObject) {
                 auto *service = new QProcess(this);
                 connect(
                     service,
                     qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
                     this, [this, service](int code, QProcess::ExitStatus) {
                       service->deleteLater();
                       if (code == 0)
                         load();
                       else
                         status->setText(
                             tx("Automatik gespeichert. "
                                "Lumen-Server-Verbindungsdienst konnte nicht "
                                "gestartet werden.",
                                "Automatic sync saved. Could not start the "
                                "Lumen Server connection service."));
                     });
                 connect(
                     service, &QProcess::errorOccurred, this,
                     [this, service](QProcess::ProcessError error) {
                       if (error == QProcess::FailedToStart) {
                         status->setText(tx(
                             "Verbindungsdienst konnte nicht gestartet werden.",
                             "Could not start the connection service."));
                         service->deleteLater();
                       }
                     });
                 QTimer::singleShot(15000, service, &QProcess::kill);
                 service->start(
                     "systemctl",
                     {"--user", "start", "lumen-server-connector.service"});
               });
        });
    autoDisable =
        add(automatic, tx("Automatik ausschalten", "Disable automatic sync"),
            [this] {
              call({{"op", "auto-disable"}}, [this](QJsonObject) {
                info["automatic"] =
                    QJsonObject{{"enabled", false}, {"reason", "disabled"}};
                autoEnable->show(); autoDisable->hide();
                status->setText(tx(
                    "Automatik ausgeschaltet. Bereits gesendete Übertragungen "
                    "können noch abgeschlossen werden.",
                    "Automatic publishing disabled. Transfers already sent may "
                    "still complete."));
              });
            });
    auto *lower = new QHBoxLayout;
    box->addLayout(lower);
    remove =
        add(lower, tx("Frühere Fassung entfernen…", "Remove earlier version…"),
            [this] {
              auto selected = selection();
              if (selected.isEmpty() || selected["current"].toBool())
                return;
              if (!confirmed(tx(
                      "Diese frühere Serverfassung endgültig entfernen? Lokale "
                      "Tresore und Restic-Sicherungen bleiben erhalten.",
                      "Permanently remove this earlier server version? Local "
                      "vaults and Restic backups remain.")))
                return;
              call({{"op", "remove"},
                    {"scope", info["scope"]},
                    {"id", selected["id"]}},
                   [this](QJsonObject) { load(); });
            });
    options = add(lower, tx("Weitere Optionen", "More options"), [] {});
    options->setCheckable(true);
    connect(options, &QPushButton::toggled, this, [this] { controls(); });
    lower->addStretch();
    add(lower, tx("Schließen", "Close"), [this] { close(); });
    connect(versions, &QListWidget::currentRowChanged, this,
            [this] { controls(); });
    controls();
    QTimer::singleShot(0, this, [this] { load(); });
  }
  ~SyncDialog() override {
    if (process) {
      process->disconnect(this);
      process->kill();
      process->waitForFinished(1000);
    }
    auto value = password->text();
    password->clear();
    wipe(value);
  }

private:
  bool confirmed(const QString &message) {
    QPointer<SyncDialog> guard(this);
    const auto answer = QMessageBox::question(
        this, windowTitle(), message, QMessageBox::Yes | QMessageBox::Cancel,
        QMessageBox::Cancel);
    return guard && answer == QMessageBox::Yes;
  }
  QString tx(const char *de, const char *en) const { return owner->tx(de, en); }
  QPushButton *add(QHBoxLayout *row, const QString &title,
                   std::function<void()> fn) {
    auto *b = new QPushButton(title);
    b->setMinimumHeight(36);
    row->addWidget(b);
    connect(b, &QPushButton::clicked, this, std::move(fn));
    return b;
  }
  QJsonObject selection() const {
    return versions->currentItem()
               ? versions->currentItem()->data(Qt::UserRole).toJsonObject()
               : QJsonObject{};
  }
  void controls() {
    const bool busy = bool(process) || checking;
    const bool local = !info["local_hash"].toString().isEmpty();
    const bool first = local && info["versions"].toArray().isEmpty();
    refresh->setEnabled(!busy);
    publish->setVisible(first || options->isChecked());
    publish->setText(first
        ? tx("Erste Serverfassung erstellen", "Create first server version")
        : tx("Lokale Fassung veröffentlichen", "Publish local version"));
    publish->setEnabled(!busy && local);
    take->setEnabled(!busy && !selection().isEmpty());
    combine->setEnabled(!busy && !selection().isEmpty() && local);
    preview->setEnabled(combine->isEnabled());
    autoEnable->setEnabled(!busy && local && matches);
    autoDisable->setEnabled(!busy);
    remove->setVisible(options->isChecked());
    remove->setEnabled(!busy && !selection().isEmpty() &&
                       !selection()["current"].toBool());
    versions->setEnabled(!busy);
  }
  void load(QString message = {}) {
    call({{"op", "info"}}, [this, message](QJsonObject result) {
      info = result;
      details->setText(info["server"].toString() + "\n" +
                       info["user"].toString());
      versions->clear();
      matches = false;
      for (const auto &value : info["versions"].toArray()) {
        auto v = value.toObject();
        auto text = (v["current"].toBool() ? tx("Aktuell · ", "Current · ")
                                           : tx("Erhalten · ", "Retained · ")) +
                    v["created"].toString().left(19).replace('T', ' ') + " · " +
                    QString::number(v["size"].toDouble() / 1024, 'f', 1) +
                    " KiB";
        const bool same = v["sha256"].toString() == info["local_hash"].toString();
        text += same ? tx("\nEntspricht diesem Gerät", "\nMatches this device")
                     : tx("\nAndere Fassung · lokal prüfbar", "\nDifferent version · review locally");
        if (v["current"].toBool() && same) matches = true;
        auto *item = new QListWidgetItem(text, versions);
        item->setSizeHint(QSize(0, 68));
        item->setToolTip(v["sha256"].toString());
        item->setData(Qt::UserRole, v);
        if (v["current"].toBool())
          versions->setCurrentItem(item);
      }
      const auto automatic = info["automatic"].toObject();
      autoEnable->setVisible(!automatic["enabled"].toBool());
      autoDisable->setVisible(automatic["enabled"].toBool());
      summary->setText(versions->count() == 0
          ? tx("Noch keine Serverfassung", "No server version yet")
          : matches ? tx("Dein Tresor ist auf diesem Stand", "Your vault matches the server")
                    : tx("Eine andere Fassung liegt bereit", "Another version is ready"));
      const auto reason = automatic["reason"].toString();
      status->setText(
          !message.isEmpty() ? message
          : reason == "incoming" || reason == "conflict"
              ? tx("Serverfassung empfangen. Bitte prüfen und übernehmen oder "
                   "zusammenführen; Veröffentlichung bleibt bis zum Abgleich "
                   "pausiert.",
                   "Server version received. Review and adopt or merge it; "
                   "publishing stays paused until reconciled.")
          : automatic["enabled"].toBool()
              ? tx("Hintergrundabgleich aktiv – auch bei geschlossenem oder "
                   "gesperrtem Vault. Empfangene Fassungen hier prüfen und "
                   "übernehmen.",
                   "Background sync enabled, even with Vault closed or locked. "
                   "Review and adopt incoming versions here.")
          : versions->count() == 0
              ? (!info["local_hash"].toString().isEmpty()
                  ? tx("Erstelle zuerst eine verschlüsselte Serverfassung. "
                       "Danach kannst du die Automatik aktivieren.",
                       "Create the first encrypted server version. "
                       "Then you can enable automatic sync.")
                  : tx("Erstelle zuerst einen Tresor oder veröffentliche ihn "
                       "von einem anderen Gerät aus.",
                       "Create a vault first or publish it from another device."))
              : tx("Automatik aus oder pausiert. Zum Aktivieren müssen lokale "
                   "und aktuelle Serverfassung übereinstimmen.",
                   "Automatic sync off or paused. To enable it, local and "
                   "current server versions must match."));
      controls();
    });
  }
  void call(QJsonObject request, std::function<void(QJsonObject)> done) {
    if (process)
      return;
    process = syncRequest(
        this, root, request, [this, done](QJsonObject result, QString error) {
          process = nullptr;
          controls();
          if (!error.isEmpty()) {
            status->setText(tx("Abgleich nicht abgeschlossen: ",
                               "Sync did not complete: ") +
                            error);
            return;
          }
          done(result);
        });
    controls();
    status->setText(tx("Server wird geprüft…", "Checking server…"));
  }
  VaultWindow *owner;
  QString root;
  QJsonObject info;
  QPointer<QProcess> process;
  QLabel *details, *status, *summary;
  bool checking = false, matches = false;
  QListWidget *versions;
  QLineEdit *password;
  QPushButton *refresh, *publish, *take, *combine, *preview, *remove, *autoEnable,
      *autoDisable, *options;
};

void VaultWindow::serverSync() {
  if (channel.busy() || editor)
    return;
  const bool empty = !QFileInfo::exists(root + "/vault.kdbx");
  if (!isOpen && !empty)
    return;
  auto epoch = generation;
  auto *dialog = new SyncDialog(
      this, &channel, root, empty,
      [this, epoch, empty](QString path, QString hash, QString previous,
                           QString password, bool merge) {
        if (generation != epoch) {
          wipe(password);
          return;
        }
        hideSecret();
        clearOwnClipboard();
        ++accessRevision;
        enabledEntries.clear();
        pendingProfiles.clear();
        if (access)
          access->revoke();
        if (editor)
          editor->setEnabled(false);
        // Keep all credential operations inside the inherited broker pipe.
        QStringList args =
            empty ? QStringList{"restore-sync", path, password, hash}
                  : QStringList{merge ? "merge-sync" : "adopt-sync", path, hash,
                                previous};
        wipe(password);
        channel.call(std::move(args), [this, epoch, merge](QStringList result) {
          if (generation != epoch)
            return;
          ++generation;
          if (editor)
            editor->close();
          isOpen = true;
          idle.start();
          replacePage(openPage());
          refresh();
          if (status)
            status->setText(
                merge ? tx("Lokal zusammengeführt: %1 ergänzt, %2 "
                           "Konfliktkopien. Noch nicht veröffentlicht.",
                           "Merged locally: %1 added, %2 conflict copies. Not "
                           "published yet.")
                            .arg(result.value(0), result.value(1))
                      : tx("Serverfassung lokal geprüft und übernommen.",
                           "Server version verified and adopted locally."));
        });
      });
  editor = dialog;
  dialog->show();
}

void VaultWindow::pollServerSync() {
  if (editor || autoSyncProcess || !QFileInfo::exists(root + "/sync-auto.json"))
    return;
  const auto epoch = generation;
  autoSyncProcess = syncRequest(
      this, root, {{"op", "auto-status"}},
      [this, epoch](QJsonObject result, QString error) {
        autoSyncProcess = nullptr;
        if (epoch != generation || !status)
          return;
        if (!error.isEmpty()) {
          status->setText(tx("Automatischer Serverabgleich nicht "
                             "abgeschlossen. Im Serverabgleich prüfen: ",
                             "Automatic server sync did not complete. Check "
                             "Server sync: ") +
                          error);
          return;
        }
        const auto reason = result["reason"].toString();
        if (reason == "published")
          status->setText(
              tx("Lokale Tresoränderungen automatisch veröffentlicht.",
                 "Local vault changes published automatically."));
        else if (reason == "incoming" || reason == "conflict")
          status->setText(tx("Neue Serverfassung empfangen. Im Serverabgleich "
                             "prüfen und übernehmen oder zusammenführen.",
                             "New server version received. Review and adopt or "
                             "merge it in Server sync."));
        else if (reason != "disabled" && reason != "ready" &&
                 reason != "checking")
          status->setText(tx("Automatik pausiert. Serverabgleich öffnen, "
                             "Fassungen prüfen und danach erneut aktivieren.",
                             "Automatic publishing paused. Open Server sync, "
                             "review versions, then enable it again."));
      });
}

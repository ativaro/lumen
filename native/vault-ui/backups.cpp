// SPDX-License-Identifier: MIT
#include "backups.h"
#include "vault.h"
#include <QScopeGuard>

static bool startBackupService() {
  const auto data =
      QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
  const QStringList directories{
      QCoreApplication::applicationDirPath() + "/../../files",
      data + "/lumen/files", "/usr/share/lumen/files",
      QCoreApplication::applicationDirPath() + "/../../../files"};
  for (const auto &directory : directories) {
    const auto script = QDir(directory).absoluteFilePath("vault_service.py");
    const auto python =
        directory == "/usr/share/lumen/files"
            ? QString("/usr/bin/lumen-python")
            : QDir(directory).absoluteFilePath("../bin/lumen-python");
    if (QFileInfo::exists(script) && QFileInfo(python).isExecutable())
      return QProcess::startDetached(python, {script});
  }
  return false;
}

QString BackupPage::tx(const char *de, const char *en) const {
  return QString::fromUtf8(english ? en : de);
}
QPushButton *BackupPage::button(const QString &text,
                                std::function<void()> action) {
  auto *b = new QPushButton(text);
  b->setMinimumHeight(40);
  b->setCursor(Qt::PointingHandCursor);
  connect(b, &QPushButton::clicked, this, std::move(action));
  return b;
}
BackupPage::BackupPage(QWidget *tabs, bool english, QWidget *parent)
    : QWidget(parent), english(english) {
  setObjectName("backupPage");
  auto root = qEnvironmentVariable("LUMEN_TOOLS_DATA");
  if (root.isEmpty())
    root =
        QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) +
        "/lumen-tools";
  root = QDir(root).absolutePath();
  socketPath =
      qEnvironmentVariable("XDG_RUNTIME_DIR") + "/lumen-backups-" +
      QCryptographicHash::hash(root.toUtf8(), QCryptographicHash::Sha256)
          .toHex()
          .left(16);
  auto *outer = new QVBoxLayout(this);
  outer->setContentsMargins(0, 0, 0, 0);
  outer->setSpacing(0);
  auto *columns = new QHBoxLayout;
  columns->setSpacing(0);
  auto *sidebar = new QFrame;
  sidebar->setObjectName("sidebar");
  sidebar->setFixedWidth(296);
  auto *side = new QVBoxLayout(sidebar);
  side->setContentsMargins(20, 28, 20, 22);
  side->setSpacing(16);
  auto *brandRow = new QHBoxLayout;
  auto *mark = new QLabel;
  mark->setFixedSize(42, 42);
  mark->setProperty("glyph", "lumen-mark");
  mark->setProperty("glyphSize", 42);
  auto brandPixmap = QIcon(":/vault/lumen-mark.svg").pixmap(42, 42);
  {
    QPainter painter(&brandPixmap);
    painter.setCompositionMode(QPainter::CompositionMode_SourceIn);
    painter.fillRect(brandPixmap.rect(), palette().color(QPalette::WindowText));
  }
  mark->setPixmap(brandPixmap);
  brandRow->addWidget(mark);
  auto *brand = new QLabel("Lumen Vault");
  brand->setObjectName("brand");
  brandRow->addWidget(brand);
  side->addLayout(brandRow);
  auto *tag = new QLabel(
      tx("Deine Daten. In deiner Hand.", "Your data. In your hands."));
  tag->setObjectName("tagline");
  side->addWidget(tag);
  side->addSpacing(24);
  search = new QLineEdit;
  search->setPlaceholderText(
      tx("Sicherungspläne suchen …", "Search backup plans …"));
  search->setAccessibleName(search->placeholderText());
  side->addWidget(search);
  listing = new QListWidget;
  listing->setObjectName("backupPlans");
  side->addWidget(listing, 1);
  side->addWidget(button(tx("＋ Sicherung einrichten", "＋ Set up backup"),
                         [this] { create(); }));
  side->addWidget(button(tx("Weitere Optionen", "More options"), [this] {
    QMenu menu(this);
    menu.addAction(tx("Aktualisieren", "Refresh"), this, [this] { reload(); });
    menu.addAction(archived ? tx("Aktive Pläne", "Active plans")
                            : tx("Archivierte Pläne", "Archived plans"),
                   this, [this] {
                     if (!busy) {
                       archived = !archived;
                       identity.clear();
                       reload();
                     }
                   });
    if (!identity.isEmpty())
      menu.addAction(archived ? tx("Plan zurückholen", "Restore plan")
                              : tx("Plan archivieren", "Archive plan"),
                     this, [this] {
                       if (QMessageBox::question(
                               this, "Lumen Vault",
                               tx("Zeitplan deaktivieren und Plan verschieben? "
                                  "Sicherungsdaten bleiben erhalten.",
                                  "Disable schedule and move this plan? Backup "
                                  "data will be kept.")) != QMessageBox::Yes)
                         return;
                       start({{"op", "archive"},
                              {"id", identity},
                              {"archived", !archived}},
                             [this](QJsonValue) {
                               identity.clear();
                               reload();
                             });
                     });
    menu.exec(QCursor::pos());
  }));
  columns->addWidget(sidebar);
  auto *main = new QVBoxLayout;
  main->setContentsMargins(0, 0, 0, 0);
  main->setSpacing(0);
  auto *top = new QHBoxLayout;
  top->setContentsMargins(24, 16, 24, 16);
  top->addStretch();
  top->addWidget(tabs);
  top->addStretch();
  main->addLayout(top);
  auto *rule = new QFrame;
  rule->setObjectName("rule");
  rule->setFixedHeight(1);
  main->addWidget(rule);
  pages = new QStackedWidget;
  auto *empty = new QWidget;
  auto *emptyLayout = new QVBoxLayout(empty);
  emptyLayout->setContentsMargins(44, 44, 44, 44);
  emptyLayout->addStretch();
  auto *welcome = new QLabel(
      tx("Deine Dateien. Gut gesichert.", "Your files. Safely backed up."));
  welcome->setObjectName("title");
  emptyLayout->addWidget(welcome);
  auto *hint = new QLabel(
      tx("Wähle links einen Plan oder richte deine erste Sicherung ein.",
         "Choose a plan or set up your first backup."));
  hint->setWordWrap(true);
  emptyLayout->addWidget(hint);
  emptyLayout->addWidget(
      button(tx("Sicherung einrichten", "Set up backup"), [this] { create(); }),
      0, Qt::AlignLeft);
  emptyLayout->addStretch();
  pages->addWidget(empty);
  auto *scroll = new QScrollArea;
  scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame);
  controls = new QWidget;
  auto *content = new QVBoxLayout(controls);
  content->setContentsMargins(28, 24, 28, 24);
  content->setSpacing(12);
  title = new QLabel;
  title->setObjectName("title");
  title->setTextFormat(Qt::PlainText);
  content->addWidget(title);
  details = new QLabel;
  details->setTextFormat(Qt::PlainText);
  details->setWordWrap(true);
  details->setObjectName("muted");
  content->addWidget(details);
  sources = new QListWidget;
  sources->setAccessibleName(tx("Geschützte Quellen", "Protected sources"));
  sources->setFixedHeight(100);
  content->addWidget(sources);
  auto *sourceActions = new QHBoxLayout;
  sourceActions->addWidget(
      button(tx("Quelle hinzufügen", "Add source"), [this] {
        dialogOpen = true;
        auto guard = qScopeGuard([this] { dialogOpen = false; });
        auto path = QFileDialog::getExistingDirectory(
            this, tx("Quellordner auswählen", "Choose source folder"));
        if (!path.isEmpty())
          start({{"op", "add_source"}, {"id", identity}, {"path", path}},
                [this](QJsonValue) { reload(); });
      }));
  sourceActions->addWidget(
      button(tx("Lumen-Daten hinzufügen", "Add Lumen data"),
             [this] { lumenSources(); }));
  sourceActions->addWidget(
      button(tx("Quelle entfernen", "Remove source"), [this] {
        if (sources->currentItem())
          start({{"op", "remove_source"},
                 {"id", identity},
                 {"path", sources->currentItem()->text()}},
                [this](QJsonValue) { reload(); });
      }));
  content->addLayout(sourceActions);
  auto *actions = new QHBoxLayout;
  actions->addWidget(button(tx("Sicherungsvorschau", "Preview backup"),
                            [this] { run("preview"); }));
  auto *save = button(tx("Jetzt sichern", "Back up now"), [this] {
    const auto selected = identity;
    start({{"op", "preflight"}, {"id", selected}}, [this, selected](
                                                       QJsonValue value) {
      if (!value.toArray().isEmpty()) {
        QString text = tx(
            "Einige Projektquellen fehlen oder sind nicht im Plan enthalten:\n",
            "Some project sources are missing or not included:\n");
        for (auto row : value.toArray())
          text += row.toObject()["path"].toString() + '\n';
        text += tx("\nNur die ausgewählten Quellen sichern?",
                   "\nBack up only the selected sources?");
        if (QMessageBox::warning(this, "Lumen Vault", text,
                                 QMessageBox::Yes | QMessageBox::Cancel,
                                 QMessageBox::Cancel) != QMessageBox::Yes)
          return;
      }
      identity = selected;
      run("backup");
    });
  });
  save->setObjectName("primary");
  actions->addWidget(save);
  actions->addStretch();
  content->addLayout(actions);
  interval = new QComboBox;
  interval->addItem(tx("Nur manuell", "Manual only"), 0);
  interval->addItem(tx("Täglich", "Daily"), 86400);
  interval->addItem(tx("Wöchentlich", "Weekly"), 604800);
  interval->setAccessibleName(tx("Sicherungsrhythmus", "Backup schedule"));
  auto *schedule = new QHBoxLayout;
  schedule->addWidget(interval);
  schedule->addWidget(
      button(tx("Zeitplan übernehmen", "Apply schedule"), [this] {
        start({{"op", "schedule"},
               {"id", identity},
               {"interval", interval->currentData().toInt()}},
              [this](QJsonValue) { reload(); });
      }));
  schedule->addStretch();
  content->addLayout(schedule);
  snapshots = new QTreeWidget;
  snapshots->setHeaderLabels(
      {tx("Sicherungsstand", "Snapshot"), tx("Quellen", "Sources")});
  snapshots->setRootIsDecorated(false);
  snapshots->setMinimumHeight(150);
  snapshots->setColumnWidth(0, 250);
  content->addWidget(snapshots, 1);
  auto *versions = new QHBoxLayout;
  versions->addWidget(button(tx("Stände laden", "Load snapshots"),
                             [this] { run("snapshots"); }));
  versions->addWidget(button(tx("Inhalt ansehen", "Browse files"), [this] {
    auto id = snapshot();
    if (!id.isEmpty())
      run("files", {{"snapshot", id}});
  }));
  versions->addWidget(button(tx("Wiederherstellen", "Restore"), [this] {
    auto id = snapshot();
    if (!id.isEmpty())
      restore(id);
  }));
  content->addLayout(versions);
  auto *checks = new QHBoxLayout;
  checks->addWidget(button(tx("Sicherung prüfen", "Check backup"), [this] {
    QMenu menu(this);
    menu.addAction(tx("Struktur prüfen", "Check structure"), this,
                   [this] { run("check"); });
    menu.addAction(tx("Alle Daten prüfen", "Verify all data"), this,
                   [this] { run("check", {{"full", true}}); });
    menu.addAction(
        tx("Projektquellen prüfen", "Check project sources"), this, [this] {
          start({{"op", "preflight"}, {"id", identity}}, [this](QJsonValue
                                                                    result) {
            QString text;
            for (auto item : result.toArray())
              text += item.toObject()["path"].toString() + '\n';
            QMessageBox::information(
                this, "Lumen Vault",
                text.isEmpty()
                    ? tx("Alle bekannten Quellen sind vorhanden und enthalten.",
                         "All known sources are available and included.")
                    : text);
          });
        });
    menu.exec(QCursor::pos());
  }));
  checks->addStretch();
  content->addLayout(checks);
  auto *notice = new QLabel(
      tx("Wiederherstellungen landen in einem neuen Ordner. Bewahre das "
         "Sicherungspasswort auch außerhalb dieses Rechners auf.",
         "Restores go into a new folder. Keep your backup password somewhere "
         "outside this computer too."));
  notice->setWordWrap(true);
  notice->setObjectName("muted");
  content->addWidget(notice);
  scroll->setWidget(controls);
  pages->addWidget(scroll);
  main->addWidget(pages, 1);
  columns->addLayout(main, 1);
  outer->addLayout(columns, 1);
  auto *footer = new QHBoxLayout;
  footer->setContentsMargins(24, 12, 24, 12);
  status = new QLabel(tx("Lokale Sicherungspläne", "Local backup plans"));
  status->setObjectName("backupStatus");
  status->setTextFormat(Qt::PlainText);
  status->setWordWrap(true);
  footer->addWidget(status, 1);
  cancel = button(tx("Abbrechen", "Cancel"), [this] {
    rpc({{"command", "cancel"}, {"token", token}}, [](QJsonObject) {});
  });
  cancel->hide();
  footer->addWidget(cancel);
  outer->addLayout(footer);
  connect(listing, &QListWidget::currentRowChanged, this, [this] { select(); });
  connect(search, &QLineEdit::textChanged, this, [this](const QString &text) {
    for (int i = 0; i < listing->count(); ++i)
      listing->item(i)->setHidden(
          !listing->item(i)->text().contains(text, Qt::CaseInsensitive));
  });
  timer.setInterval(500);
  connect(&timer, &QTimer::timeout, this, &BackupPage::poll);
}
void BackupPage::error(const QString &message) { status->setText(message); }
void BackupPage::rpc(QJsonObject request, std::function<void(QJsonObject)> done,
                     int retries) {
  auto *socket = new QLocalSocket(this);
  socket->setReadBufferSize(36 * 1024 * 1024 + 1);
  auto *deadline = new QTimer(socket);
  deadline->setSingleShot(true);
  deadline->start(5000);
  auto buffer = std::make_shared<QByteArray>();
  auto completed = std::make_shared<bool>(false);
  auto finish = [socket, deadline, done, completed](QJsonObject value) {
    if (*completed)
      return;
    *completed = true;
    deadline->stop();
    socket->abort();
    socket->deleteLater();
    done(value);
  };
  connect(deadline, &QTimer::timeout, this, [finish] {
    finish(
        {{"error", "Backup service timed out; operation was not replayed."}});
  });
  connect(socket, &QLocalSocket::connected, this, [socket, request] {
    auto payload = QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n';
    socket->write(payload);
    wipe(payload);
  });
  connect(socket, &QLocalSocket::readyRead, this, [socket, buffer, finish] {
    buffer->append(socket->readAll());
    if (buffer->size() > 36 * 1024 * 1024) {
      finish({{"error", "Backup result exceeds limit"}});
      return;
    }
    if (!buffer->endsWith('\n'))
      return;
    QJsonParseError error;
    auto doc = QJsonDocument::fromJson(*buffer, &error);
    finish(error.error == QJsonParseError::NoError && doc.isObject()
               ? doc.object()
               : QJsonObject{{"error", "Invalid backup response"}});
  });
  connect(socket, &QLocalSocket::errorOccurred, this,
          [this, socket, request, done, retries, completed, deadline,
           finish](QLocalSocket::LocalSocketError code) {
            if (*completed)
              return;
            if (retries > 0 && (code == QLocalSocket::ServerNotFoundError ||
                                code == QLocalSocket::ConnectionRefusedError)) {
              *completed = true;
              deadline->stop();
              socket->deleteLater();
              if (retries == 20 && !startBackupService()) {
                done({{"error",
                       tx("Sicherungsdienst fehlt. Lumen-Installation prüfen.",
                          "Backup service missing. Check your Lumen "
                          "installation.")}});
                return;
              }
              QTimer::singleShot(250, this, [this, request, done, retries] {
                rpc(request, done, retries - 1);
              });
            } else
              finish({{"error", tx("Verbindung unterbrochen. Der Auftrag wird "
                                   "nicht automatisch wiederholt.",
                                   "Connection interrupted. The operation will "
                                   "not be retried automatically.")}});
          });
  socket->connectToServer(socketPath);
}
void BackupPage::activate() {
  if (busy || polling || loaded)
    return;
  polling = true;
  rpc({{"command", "status"}}, [this](QJsonObject value) {
    polling = false;
    if (value.contains("error") && !value.contains("state")) {
      error(value["error"].toString());
      return;
    }
    if (value["state"] == "running") {
      state(value);
      timer.start();
    } else if (value["state"] == "done" || value["state"] == "error") {
      lastOutcome = value.contains("error") ? value["error"].toString()
                    : value["op"] == "restore"
                        ? tx("Wiederhergestellt: ", "Restored: ") +
                              value["result"].toString()
                    : value["op"] == "list"
                        ? QString()
                        : tx("Letzter Sicherungsvorgang abgeschlossen.",
                             "Last backup operation completed.");
      reload(value["op"] == "create" ? value["result"].toString()
                                     : value["id"].toString());
    } else
      reload();
  });
}
void BackupPage::start(QJsonObject request, Done done) {
  if (busy) {
    error(tx("Ein Sicherungsvorgang läuft bereits.",
             "A backup operation is already running."));
    return;
  }
  busy = true;
  if (request["op"] != "list")
    lastOutcome.clear();
  controls->setEnabled(false);
  listing->setEnabled(false);
  completion = std::move(done);
  request["command"] = "start";
  request["token"] = QUuid::createUuid().toString(QUuid::WithoutBraces);
  rpc(request, [this](QJsonObject value) {
    state(value);
    if (busy)
      timer.start();
  });
}
void BackupPage::poll() {
  if (polling)
    return;
  polling = true;
  rpc({{"command", "status"}}, [this](QJsonObject value) {
    polling = false;
    state(value);
  });
}
void BackupPage::state(QJsonObject value) {
  if (busy && value["state"] == "idle")
    value = {{"error",
              tx("Der Sicherungsdienst wurde neu gestartet. Prüfe den letzten "
                 "Sicherungsstand; der Auftrag wurde nicht wiederholt.",
                 "The backup service restarted. Check the latest snapshot; the "
                 "operation was not replayed.")}};
  if (value["state"] == "running") {
    token = value["token"].toString();
    busy = true;
    controls->setEnabled(false);
    listing->setEnabled(false);
    cancel->show();
    status->setText(
        tx("Sicherungsvorgang läuft … Du kannst zwischen den Reitern wechseln.",
           "Backup operation running … You can switch between tabs."));
    return;
  }
  timer.stop();
  busy = false;
  cancel->hide();
  controls->setEnabled(true);
  listing->setEnabled(true);
  auto done = std::move(completion);
  completion = {};
  if (value.contains("error")) {
    lastOutcome = value["error"].toString();
    error(lastOutcome);
    if (!done && value.contains("state"))
      reload(value["id"].toString());
    return;
  }
  status->setText(tx("Vorgang abgeschlossen.", "Operation completed."));
  if (done)
    done(value["result"]);
  else if (value["op"] != "list") {
    const auto message = value["op"] == "restore" ? value["result"].toString()
                                                  : tx("Vorgang abgeschlossen.",
                                                       "Operation completed.");
    lastOutcome = message;
    reload(value["op"] == "create" ? value["result"].toString()
                                   : value["id"].toString());
  }
}
void BackupPage::reload(QString selected) {
  if (selected.isEmpty())
    selected = identity;
  start({{"op", "list"}, {"archived", archived}},
        [this, selected](QJsonValue value) {
          loaded = true;
          plans = value.toArray();
          QSignalBlocker block(listing);
          listing->clear();
          int row = -1;
          for (auto value : plans) {
            const auto plan = value.toObject();
            auto *item = new QListWidgetItem(plan["title"].toString(), listing);
            item->setData(Qt::UserRole, plan["id"].toString());
            item->setSizeHint(QSize(230, 54));
            if (plan["id"].toString() == selected)
              row = listing->count() - 1;
          }
          listing->setCurrentRow(row);
          select();
          if (!lastOutcome.isEmpty())
            status->setText(lastOutcome);
        });
}
void BackupPage::select() {
  identity = listing->currentItem()
                 ? listing->currentItem()->data(Qt::UserRole).toString()
                 : QString();
  pages->setCurrentIndex(identity.isEmpty() ? 0 : 1);
  snapshots->clear();
  sources->clear();
  for (auto value : plans) {
    auto plan = value.toObject();
    if (plan["id"].toString() != identity)
      continue;
    title->setText(plan["title"].toString());
    QString text = plan["repository"].toString() + '\n';
    text += plan["last_backup"].toDouble() > 0
                ? QDateTime::fromSecsSinceEpoch(
                      qint64(plan["last_backup"].toDouble()))
                      .toString("dd.MM.yyyy HH:mm")
                : tx("Noch keine abgeschlossene Sicherung",
                     "No completed backup yet");
    if (plan.contains("schedule_pending"))
      text += '\n' + tx("Zeitplan noch nicht aktiviert. Erneut übernehmen.",
                        "Schedule not yet active. Apply it again.");
    if (!plan["app_sources"].toArray().isEmpty())
      text += '\n' + tx("Lumen-Daten werden als konsistente Kopien gesichert. "
                        "Ungespeicherte Änderungen sind nicht enthalten.",
                        "Lumen data is backed up as consistent copies. Unsaved "
                        "edits are not included.");
    text += '\n' + plan["last_error"].toString();
    details->setText(text);
    for (auto source : plan["sources"].toArray())
      sources->addItem(source.toString());
    interval->setCurrentIndex(interval->findData(
        plan["schedule_pending"].toInt(plan["interval"].toInt())));
    break;
  }
}
void BackupPage::create() {
  if (busy)
    return;
  dialogOpen = true;
  auto guard = qScopeGuard([this] { dialogOpen = false; });
  QDialog dialog(this);
  dialog.setWindowTitle(tx("Sicherung einrichten", "Set up backup"));
  dialog.resize(620, 460);
  auto *form = new QFormLayout(&dialog);
  QLineEdit name(tx("Meine Sicherung", "My backup")), target, source, password,
      confirm;
  password.setEchoMode(QLineEdit::Password);
  confirm.setEchoMode(QLineEdit::Password);
  form->addRow(tx("Name", "Name"), &name);
  auto choose = [&](QLineEdit *field) {
    auto *row = new QHBoxLayout;
    row->addWidget(field);
    row->addWidget(button(tx("Wählen", "Choose"), [&, field] {
      auto path = QFileDialog::getExistingDirectory(&dialog);
      if (!path.isEmpty())
        field->setText(path);
    }));
    return row;
  };
  form->addRow(tx("USB-/NAS-Zielordner", "USB/NAS destination"),
               choose(&target));
  form->addRow(tx("Erster Quellordner", "First source folder"),
               choose(&source));
  QCheckBox desktop(tx("Lumen- und KDE-Einstellungen ebenfalls sichern",
                       "Include Lumen and KDE settings"));
  form->addRow(&desktop);
  form->addRow(tx("Sicherungspasswort", "Backup password"), &password);
  form->addRow(tx("Wiederholen", "Repeat"), &confirm);
  auto *hint = new QLabel(tx(
      "Neues Ziel: leerer Ordner, mindestens 12 Zeichen. Vorhandenes "
      "Restic-Ziel: bisheriges Passwort. Speicherung im System-Schlüsselbund.",
      "New destination: empty folder, at least 12 characters. Existing Restic "
      "destination: current password. Stored in the system keyring."));
  hint->setWordWrap(true);
  form->addRow(hint);
  QDialogButtonBox buttons(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
  form->addRow(&buttons);
  connect(&buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
  connect(&buttons, &QDialogButtonBox::accepted, &dialog, [&] {
    if (password.text() != confirm.text()) {
      QMessageBox::warning(&dialog, "Lumen Vault",
                           tx("Die Passwörter stimmen nicht überein.",
                              "Passwords do not match."));
      return;
    }
    dialog.accept();
  });
  if (dialog.exec() == QDialog::Accepted) {
    QJsonArray paths;
    if (!source.text().trimmed().isEmpty())
      paths.append(source.text());
    start({{"op", "create"},
           {"title", name.text()},
           {"repository", target.text()},
           {"sources", paths},
           {"password", password.text()},
           {"desktop", desktop.isChecked()}},
          [this](QJsonValue id) {
            archived = false;
            reload(id.toString());
          });
  }
  password.clear();
  confirm.clear();
}
QString BackupPage::snapshot() {
  if (snapshots->currentItem())
    return snapshots->currentItem()->data(0, Qt::UserRole).toString();
  error(
      tx("Bitte einen Sicherungsstand auswählen.", "Select a snapshot first."));
  return {};
}
void BackupPage::run(QString op, QJsonObject extra) {
  if (identity.isEmpty())
    return;
  extra["op"] = op;
  extra["id"] = identity;
  start(extra, [this, op, extra](QJsonValue result) {
    if (op == "snapshots") {
      snapshots->clear();
      for (auto value : result.toArray()) {
        auto record = value.toObject();
        QStringList paths;
        for (auto p : record["paths"].toArray())
          paths << p.toString();
        auto *item = new QTreeWidgetItem(
            snapshots, {record["time"].toString().left(19).replace('T', ' '),
                        paths.join(" · ")});
        item->setData(0, Qt::UserRole, record["id"].toString());
      }
      snapshots->resizeColumnToContents(0);
    } else if (op == "files") {
      dialogOpen = true;
      auto guard = qScopeGuard([this] { dialogOpen = false; });
      QDialog dialog(this);
      dialog.setWindowTitle(tx("Gesicherte Dateien", "Backed up files"));
      dialog.resize(780, 600);
      QVBoxLayout layout(&dialog);
      QListWidget files;
      layout.addWidget(&files);
      for (auto value : result.toArray())
        files.addItem(value.toObject()["path"].toString());
      layout.addWidget(
          button(tx("Auswahl wiederherstellen", "Restore selection"), [&] {
            if (files.currentItem())
              dialog.accept();
          }));
      if (dialog.exec() == QDialog::Accepted && files.currentItem())
        restore(extra["snapshot"].toString(), files.currentItem()->text());
    } else if (op == "backup")
      reload();
    else if (op == "preview") {
      auto summary = result.toObject();
      status->setText(
          tx("Vorschau: ", "Preview: ") +
          QString::number(summary["total_files_processed"].toInteger()) +
          tx(" Dateien · ", " files · ") +
          QString::number(summary["total_bytes_processed"].toDouble() / 1024 /
                              1024,
                          'f', 1) +
          " MiB");
    } else
      status->setText(result.toString(
          tx("Vorgang abgeschlossen.", "Operation completed.")));
  });
}
void BackupPage::restore(QString snapshot, QString selected) {
  dialogOpen = true;
  auto guard = qScopeGuard([this] { dialogOpen = false; });
  const auto destination = QFileDialog::getExistingDirectory(
      this, tx("Übergeordneten Zielordner auswählen",
               "Choose parent destination folder"));
  if (destination.isEmpty())
    return;
  start({{"op", "restore"},
         {"id", identity},
         {"snapshot", snapshot},
         {"selected", selected},
         {"destination", destination}},
        [this](QJsonValue value) {
          const auto path = value.toString();
          status->setText(
              tx("Wiederhergestellt und geprüft: ", "Restored and verified: ") +
              path);
          if (QMessageBox::question(this, "Lumen Vault",
                                    tx("Wiederhergestellten Ordner öffnen?",
                                       "Open restored folder?")) ==
              QMessageBox::Yes)
            QDesktopServices::openUrl(QUrl::fromLocalFile(path));
        });
}
void BackupPage::lumenSources() {
  start({{"op", "discover"}}, [this](QJsonValue value) {
    dialogOpen = true;
    auto guard = qScopeGuard([this] { dialogOpen = false; });
    QDialog dialog(this);
    dialog.setWindowTitle(tx("Lumen-Daten auswählen", "Choose Lumen data"));
    dialog.resize(700, 460);
    QVBoxLayout layout(&dialog);
    QListWidget files;
    layout.addWidget(&files);
    for (auto entry : value.toArray()) {
      auto row = entry.toObject();
      auto *item = new QListWidgetItem(
          row["title"].toString() + '\n' + row["path"].toString(), &files);
      item->setData(Qt::UserRole, row["path"].toString());
      item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
      item->setCheckState(Qt::Checked);
    }
    QCheckBox local(tx("Inbox: nur lokale Aufgaben und ungesendete Entwürfe",
                       "Inbox: local tasks and unsent drafts only"));
    layout.addWidget(&local);
    QDialogButtonBox buttons(QDialogButtonBox::Save | QDialogButtonBox::Cancel);
    layout.addWidget(&buttons);
    connect(&buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(&buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    if (dialog.exec() != QDialog::Accepted)
      return;
    QJsonArray paths;
    for (int i = 0; i < files.count(); ++i)
      if (files.item(i)->checkState() == Qt::Checked)
        paths.append(files.item(i)->data(Qt::UserRole).toString());
    if (!paths.isEmpty())
      start({{"op", "merge_sources"},
             {"id", identity},
             {"paths", paths},
             {"inbox_local", local.isChecked()}},
            [this](QJsonValue) { reload(); });
  });
}

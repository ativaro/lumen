// SPDX-License-Identifier: MIT
#include "vault.h"
#include <QtEndian>
#include <cstring>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>

void wipe(QString &text) {
  text.detach();
  ::explicit_bzero(text.data(), size_t(text.size()) * sizeof(QChar));
  text.clear();
}
void wipe(QByteArray &text) {
  text.detach();
  ::explicit_bzero(text.data(), size_t(text.size()));
  text.clear();
}
static void number(QByteArray &data, quint32 n) {
  char b[4];
  qToBigEndian(n, b);
  data.append(b, 4);
}
static QLineEdit *input(const QString &name, bool hidden = false) {
  auto *edit = new QLineEdit;
  edit->setObjectName(name);
  edit->setMinimumHeight(42);
  edit->setMaxLength(hidden ? 4096 : 1024);
  edit->setClearButtonEnabled(!hidden);
  if (hidden) {
    edit->setEchoMode(QLineEdit::Password);
    edit->setContextMenuPolicy(Qt::NoContextMenu);
    edit->setInputMethodHints(Qt::ImhSensitiveData | Qt::ImhNoPredictiveText |
                              Qt::ImhHiddenText);
  }
  return edit;
}
Channel::Channel(QString root, QObject *parent)
    : QObject(parent), root(std::move(root)) {
  deadline.setSingleShot(true);
  deadline.setInterval(15000);
  child.setProcessChannelMode(QProcess::SeparateChannels);
  child.setStandardErrorFile(QProcess::nullDevice());
  child.setChildProcessModifier([] {
    struct rlimit core{0, 0};
    if (setrlimit(RLIMIT_CORE, &core) != 0 || prctl(PR_SET_DUMPABLE, 0) != 0 ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0)
      _exit(126);
  });
  connect(&child, &QProcess::readyReadStandardOutput, this, &Channel::read);
  connect(&child, &QProcess::finished, this, [this] {
    if (!stopping) {
      stop();
      emit failed("Disconnected");
    }
  });
  connect(&child, &QProcess::errorOccurred, this, [this] {
    if (!stopping) {
      stop();
      emit failed("Disconnected");
    }
  });
  connect(&deadline, &QTimer::timeout, this, [this] {
    stop();
    emit failed("Timeout");
  });
}
void Channel::stop() {
  stopping = true;
  deadline.stop();
  pending = {};
  wipe(buffer);
  if (child.state() != QProcess::NotRunning) {
    child.kill();
    child.waitForFinished(1000);
  }
  stopping = false;
}
void Channel::call(QStringList fields, Reply callback) {
  if (pending) {
    for (auto &field : fields)
      wipe(field);
    return;
  }
  if (child.state() == QProcess::NotRunning) {
    auto environment = QProcessEnvironment::systemEnvironment();
    for (const auto &key : environment.keys())
      if (key.startsWith("LD_") || key.startsWith("RUST_"))
        environment.remove(key);
    child.setProcessEnvironment(environment);
    child.start(QCoreApplication::applicationDirPath() +
                    "/lumen-vault-lab-broker",
                {"--laboratory-only", root});
    if (!child.waitForStarted(3000)) {
      for (auto &field : fields)
        wipe(field);
      emit failed("Unavailable");
      return;
    }
  }
  QByteArray payload;
  number(payload, fields.size());
  for (auto &field : fields) {
    auto bytes = field.toUtf8();
    number(payload, bytes.size());
    payload += bytes;
    wipe(bytes);
    wipe(field);
  }
  QByteArray message;
  number(message, payload.size());
  message += payload;
  wipe(payload);
  pending = std::move(callback);
  deadline.start();
  child.write(message);
  wipe(message);
}
void Channel::read() {
  buffer += child.readAllStandardOutput();
  if (buffer.size() > 4 * 1024 * 1024 + 4) {
    stop();
    emit failed("InvalidReply");
    return;
  }
  if (buffer.size() < 4)
    return;
  const quint32 length = qFromBigEndian<quint32>(buffer.constData());
  if (length < 4 || length > 4 * 1024 * 1024) {
    stop();
    emit failed("InvalidReply");
    return;
  }
  if (buffer.size() < length + 4)
    return;
  if (buffer.size() != length + 4 || !pending) {
    stop();
    emit failed("InvalidReply");
    return;
  }
  qsizetype offset = 8;
  auto count = qFromBigEndian<quint32>(buffer.constData() + 4);
  QStringList fields;
  bool valid = count <= 4096;
  for (quint32 i = 0; valid && i < count; ++i) {
    if (offset + 4 > buffer.size()) {
      valid = false;
      break;
    }
    auto size = qFromBigEndian<quint32>(buffer.constData() + offset);
    offset += 4;
    if (size > 16384 || offset + size > buffer.size()) {
      valid = false;
      break;
    }
    fields << QString::fromUtf8(buffer.constData() + offset, size);
    offset += size;
  }
  valid = valid && offset == buffer.size() && !fields.isEmpty();
  wipe(buffer);
  deadline.stop();
  auto callback = std::move(pending);
  pending = {};
  if (!valid || fields.first() != "ok") {
    QString code = valid && fields.size() == 2 ? fields[1] : "InvalidReply";
    for (auto &field : fields)
      wipe(field);
    stop();
    emit failed(code);
    return;
  }
  fields.removeFirst();
  callback(std::move(fields));
}
VaultWindow::VaultWindow(const QString &root)
    : root(root), channel(root, this) {
  QSettings settings("Lumen", "Assistant");
  const auto language = settings.value("uiLanguage", "system").toString();
  english =
      language == "en" ||
      (language == "system" && QLocale::system().language() != QLocale::German);
  setWindowTitle("Lumen Vault · " + tx("Testversion", "Laboratory"));
  resize(1250, 800);
  setMinimumSize(980, 680);
  idle.setSingleShot(true);
  idle.setInterval(300000);
  revealTimer.setSingleShot(true);
  revealTimer.setInterval(10000);
  clipboardTimer.setSingleShot(true);
  clipboardTimer.setInterval(20000);
  connect(&idle, &QTimer::timeout, this, &VaultWindow::lock);
  connect(&revealTimer, &QTimer::timeout, this, &VaultWindow::hideSecret);
  connect(&clipboardTimer, &QTimer::timeout, this,
          &VaultWindow::clearOwnClipboard);
  connect(&channel, &Channel::failed, this, [this](const QString &code) {
    lock();
    if (status)
      status->setText(tx("Vorgang nicht abgeschlossen. Tresor gesperrt: ",
                         "Operation did not complete. Vault locked: ") +
                      code);
  });
  QDBusConnection::sessionBus().connect(
      "org.freedesktop.ScreenSaver", "/ScreenSaver",
      "org.freedesktop.ScreenSaver", "ActiveChanged", this,
      SLOT(screenLock(bool)));
  QDBusConnection::systemBus().connect(
      "org.freedesktop.login1", "/org/freedesktop/login1",
      "org.freedesktop.login1.Manager", "PrepareForSleep", this,
      SLOT(suspend(bool)));
  qApp->installEventFilter(this);
  replacePage(lockedPage());
  theme();
  themeTimer.setInterval(2000);
  connect(&themeTimer, &QTimer::timeout, this, &VaultWindow::theme);
  themeTimer.start();
}
VaultWindow::~VaultWindow() {
  qApp->removeEventFilter(this);
  clearOwnClipboard();
  channel.stop();
}
QString VaultWindow::tx(const char *de, const char *en) const {
  return QString::fromUtf8(english ? en : de);
}
QPushButton *VaultWindow::button(const QString &text,
                                 std::function<void()> action,
                                 QWidget *parent) {
  auto *b = new QPushButton(text, parent);
  b->setMinimumHeight(40);
  b->setCursor(Qt::PointingHandCursor);
  connect(b, &QPushButton::clicked, this, std::move(action));
  return b;
}
void VaultWindow::replacePage(QWidget *page) {
  if (auto *old = takeCentralWidget())
    delete old;
  setCentralWidget(page);
}
QWidget *VaultWindow::lockedPage() {
  auto *page = new QWidget;
  auto *outer = new QVBoxLayout(page);
  outer->setContentsMargins(36, 28, 36, 28);
  auto *brand = new QLabel("◈  Lumen Vault");
  brand->setObjectName("brand");
  outer->addWidget(brand);
  outer->addStretch();
  auto *card = new QFrame;
  card->setObjectName("card");
  card->setMaximumWidth(510);
  auto *layout = new QVBoxLayout(card);
  layout->setContentsMargins(36, 30, 36, 30);
  layout->setSpacing(14);
  auto *title = new QLabel(
      tx("Dein Tresor. Lokal bei dir.", "Your vault. Stored locally."));
  title->setObjectName("title");
  layout->addWidget(title);
  auto *notice =
      new QLabel(tx("Testversion · nur erfundene Zugangsdaten verwenden.\nDie "
                    "unabhängige Sicherheitsprüfung steht noch aus.",
                    "Laboratory · use synthetic credentials only.\nIndependent "
                    "security review is still pending."));
  notice->setWordWrap(true);
  notice->setObjectName("muted");
  layout->addWidget(notice);
  const bool exists = QFileInfo::exists(root + "/vault.kdbx");
  layout->addSpacing(12);
  master = input("master", true);
  master->setPlaceholderText(tx("Hauptpasswort", "Master password"));
  layout->addWidget(master);
  if (!exists) {
    confirm = input("confirm", true);
    confirm->setPlaceholderText(
        tx("Hauptpasswort wiederholen", "Repeat master password"));
    layout->addWidget(confirm);
  }
  auto *submit =
      button(exists ? tx("Entsperren", "Unlock")
                    : tx("Test-Tresor erstellen", "Create test vault"),
             [this, exists] { authorize(!exists); });
  submit->setObjectName("primary");
  layout->addWidget(submit);
  connect(master, &QLineEdit::returnPressed, submit, &QPushButton::click);
  if (confirm)
    connect(confirm, &QLineEdit::returnPressed, submit, &QPushButton::click);
  if (!exists) {
    auto *help = new QLabel(
        tx("Mindestens 14 Zeichen. Ohne Hauptpasswort gibt es keine "
           "Wiederherstellung. Sichere die verschlüsselte Datei separat.",
           "At least 14 characters. The master password cannot be reset. Back "
           "up the encrypted file separately."));
    help->setWordWrap(true);
    help->setObjectName("muted");
    layout->addWidget(help);
    layout->addWidget(button(tx("Verschlüsselte Sicherung wiederherstellen…",
                                "Restore encrypted backup…"),
                             [this] { authorize(false, true); }));
  }
  status = new QLabel;
  status->setWordWrap(true);
  status->setObjectName("status");
  layout->addWidget(status);
  outer->addWidget(card, 0, Qt::AlignHCenter);
  outer->addStretch();
  auto *footer =
      new QLabel(tx("KDBX · private Prozessverbindung · keine KI-Anbindung",
                    "KDBX · private process channel · no AI integration"));
  footer->setObjectName("muted");
  outer->addWidget(footer, 0, Qt::AlignHCenter);
  master->setFocus();
  return page;
}
void VaultWindow::authorize(bool create, bool restore) {
  if (channel.busy())
    return;
  auto value = master->text();
  if (create && (value.size() < 14 || !confirm || value != confirm->text())) {
    status->setText(
        tx("Mindestens 14 Zeichen; beide Eingaben müssen übereinstimmen.",
           "Use at least 14 characters; both passwords must match."));
    wipe(value);
    return;
  }
  QStringList args{create ? "create" : "open", value};
  if (restore) {
    auto file = QFileDialog::getOpenFileName(
        this, tx("Sicherung auswählen", "Choose backup"), {}, "KDBX (*.kdbx)");
    if (file.isEmpty()) {
      wipe(value);
      return;
    }
    args = {"restore", file, value};
  }
  master->clear();
  if (confirm)
    confirm->clear();
  wipe(value);
  status->setText(tx("Tresor wird geöffnet…", "Opening vault…"));
  channel.call(std::move(args), [this](QStringList) {
    isOpen = true;
    idle.start();
    replacePage(openPage());
    refresh();
  });
}
QWidget *VaultWindow::openPage() {
  auto *page = new QWidget;
  auto *layout = new QVBoxLayout(page);
  layout->setContentsMargins(28, 24, 28, 20);
  layout->setSpacing(20);
  auto *top = new QHBoxLayout;
  auto *brand = new QLabel("◈  Lumen Vault");
  brand->setObjectName("brand");
  top->addWidget(brand);
  top->addStretch();
  auto *pill = new QLabel(tx("Tresor  ·  Testversion", "Vault  ·  Laboratory"));
  pill->setObjectName("muted");
  top->addWidget(pill);
  top->addStretch();
  top->addWidget(button(tx("Lizenzen", "Licenses"), [this] {
    QMessageBox box(this);
    box.setWindowTitle(tx("Über Lumen Vault", "About Lumen Vault"));
    box.setTextFormat(Qt::PlainText);
    box.setText(tx(
        "Lumen Vault verwendet Qt 6 Core, Gui, Widgets und D-Bus unter LGPLv3. "
        "Qt wird dynamisch eingebunden. Austausch und Debugging der "
        "Bibliotheken sind erlaubt.\n\nTresorkern: keepass-rs (MIT) und "
        "weitere Bibliotheken gemäß beiliegendem Lizenzverzeichnis. Kein "
        "KeePassXC-Code eingebunden.\n\nDie Testversion ist nicht für echte "
        "Zugangsdaten freigegeben.",
        "Lumen Vault uses Qt 6 Core, Gui, Widgets and D-Bus under LGPLv3, "
        "linked dynamically. Replacing and debugging the libraries is "
        "permitted.\n\nVault core: keepass-rs (MIT) and other libraries listed "
        "in the included notices. No KeePassXC code is linked.\n\nThis "
        "laboratory build is not approved for real credentials."));
    box.exec();
  }));
  top->addWidget(button(tx("Sicherungen", "Backups"), [] {
    auto app = QStandardPaths::findExecutable("lumen-vault");
    if (!app.isEmpty())
      QProcess::startDetached(app, {});
  }));
  auto *lockButton = button(tx("Sperren", "Lock"), [this] { lock(); });
  lockButton->setObjectName("lock");
  top->addWidget(lockButton);
  layout->addLayout(top);
  auto *columns = new QHBoxLayout;
  columns->setSpacing(20);
  navigation = new QListWidget;
  navigation->setObjectName("navigation");
  navigation->setFixedWidth(185);
  navigation->setSpacing(4);
  const QStringList labels{tx("Alle Einträge", "All entries"),
                           tx("Favoriten", "Favorites"),
                           tx("Passwörter", "Passwords"),
                           tx("API-Tokens", "API tokens"),
                           tx("Sichere Notizen", "Secure notes"),
                           tx("Wiederherstellung", "Recovery codes"),
                           tx("Papierkorb", "Trash")};
  const QStringList keys{"all",  "favorite", "login", "token",
                         "note", "recovery", "trash"};
  for (int i = 0; i < labels.size(); ++i) {
    auto *item = new QListWidgetItem(labels[i], navigation);
    item->setData(Qt::UserRole, keys[i]);
    item->setSizeHint(QSize(170, 46));
  }
  navigation->setCurrentRow(0);
  connect(navigation, &QListWidget::currentRowChanged, this, [this] {
    category = (navigation->currentItem()
                    ? navigation->currentItem()->data(Qt::UserRole).toString()
                    : QString("all"));
    filter();
  });
  columns->addWidget(navigation);
  auto *middle = new QWidget;
  middle->setMinimumWidth(275);
  middle->setMaximumWidth(390);
  auto *ml = new QVBoxLayout(middle);
  ml->setContentsMargins(0, 0, 0, 0);
  ml->setSpacing(14);
  auto *newButton =
      button(tx("＋ Neuer Eintrag", "＋ New entry"), [this] { edit(); });
  newButton->setObjectName("new");
  ml->addWidget(newButton);
  search = input("search");
  search->setPlaceholderText(tx("Im Tresor suchen…", "Search this vault…"));
  ml->addWidget(search);
  connect(search, &QLineEdit::textChanged, this, [this] { filter(); });
  entries = new QListWidget;
  entries->setObjectName("entries");
  entries->setSpacing(5);
  ml->addWidget(entries);
  connect(entries, &QListWidget::currentRowChanged, this, [this] { select(); });
  columns->addWidget(middle, 1);
  auto *detail = new QFrame;
  detail->setObjectName("card");
  auto *dl = new QVBoxLayout(detail);
  dl->setContentsMargins(28, 26, 28, 26);
  dl->setSpacing(16);
  heading = new QLabel(tx("Deine Zugänge", "Your credentials"));
  heading->setObjectName("title");
  heading->setTextFormat(Qt::PlainText);
  heading->setWordWrap(true);
  dl->addWidget(heading);
  subtitle = new QLabel;
  subtitle->setObjectName("muted");
  subtitle->setTextFormat(Qt::PlainText);
  subtitle->setWordWrap(true);
  dl->addWidget(subtitle);
  dl->addSpacing(18);
  auto *caption = new QLabel(tx("Passwort / Token", "Password / token"));
  caption->setObjectName("muted");
  dl->addWidget(caption);
  secret = input("secret", true);
  secret->setReadOnly(true);
  secret->setFocusPolicy(Qt::NoFocus);
  secret->setAttribute(Qt::WA_TransparentForMouseEvents);
  secret->setText("••••••••••••");
  dl->addWidget(secret);
  auto *actions = new QHBoxLayout;
  actions->addWidget(
      button(tx("10 Sekunden zeigen", "Show for 10 seconds"), [this] {
        auto id = selectedId();
        if (id.isEmpty())
          return;
        channel.call({"get", id, "Password"}, [this, id](QStringList fields) {
          if (secret && isOpen && selectedId() == id && !fields.isEmpty()) {
            secret->setEchoMode(QLineEdit::Normal);
            secret->setText(fields[0]);
            wipe(fields[0]);
            revealTimer.start();
          }
        });
      }));
  auto *copy = button(tx("Kopieren", "Copy"), [this] {
    auto id = selectedId();
    if (id.isEmpty())
      return;
    channel.call({"get", id, "Password"}, [this](QStringList fields) {
      if (!fields.isEmpty()) {
        copySecret(fields[0]);
        wipe(fields[0]);
      }
    });
  });
  copy->setObjectName("copy");
  actions->addWidget(copy);
  dl->addLayout(actions);
  dl->addWidget(button(tx("Benutzernamen kopieren", "Copy username"), [this] {
    auto id = selectedId();
    if (id.isEmpty())
      return;
    channel.call({"get", id, "UserName"}, [this](QStringList fields) {
      if (!fields.isEmpty()) {
        copySecret(fields[0]);
        wipe(fields[0]);
      }
    });
  }));
  dl->addWidget(
      button(tx("Bearbeiten / Notiz lesen", "Edit / read note"), [this] {
        auto id = selectedId();
        if (id.isEmpty())
          return;
        channel.call({"edit", id}, [this, id](QStringList fields) {
          if (isOpen && selectedId() == id)
            edit(std::move(fields));
          else
            for (auto &v : fields)
              wipe(v);
        });
      }));
  dl->addSpacing(8);
  dl->addWidget(button(tx("Favorit umschalten", "Toggle favorite"), [this] {
    auto id = selectedId();
    if (id.isEmpty())
      return;
    int i = rowIndex(id);
    if (i < 0)
      return;
    channel.call({"favorite", id, rows.value(i + 4) == "1" ? "0" : "1"},
                 [this](QStringList) { refresh(); });
  }));
  dl->addWidget(
      button(tx("Papierkorb / Wiederherstellen", "Trash / restore"), [this] {
        auto id = selectedId();
        if (id.isEmpty())
          return;
        int i = rowIndex(id);
        if (i < 0)
          return;
        channel.call({"trash", id, rows.value(i + 5) == "1" ? "0" : "1"},
                     [this](QStringList) { refresh(); });
      }));
  dl->addStretch();
  auto *boundary = new QLabel(
      tx("Kein Secret-Zugriff über Lumen/MCP eingerichtet.\nGelöschtes kann in "
         "Historie und Sicherungen verbleiben.",
         "No secret access through Lumen/MCP is configured.\nDeleted content "
         "can remain in history and backups."));
  boundary->setWordWrap(true);
  boundary->setObjectName("muted");
  dl->addWidget(boundary);
  columns->addWidget(detail, 2);
  layout->addLayout(columns, 1);
  auto *footer = new QHBoxLayout;
  status =
      new QLabel(tx("Lokal gespeichert · Sperre nach 5 Minuten · Nur Testdaten",
                    "Stored locally · Locks after 5 minutes · Test data only"));
  status->setObjectName("muted");
  footer->addWidget(status, 1);
  footer->addWidget(
      button(tx("Sicherung exportieren…", "Export backup…"), [this] {
        auto parent = QFileDialog::getExistingDirectory(
            this, tx("Zielordner auswählen", "Choose destination"));
        if (parent.isEmpty() || !isOpen)
          return;
        auto dest = parent + "/Lumen-Vault-" +
                    QUuid::createUuid().toString(QUuid::WithoutBraces);
        if (!QDir().mkdir(dest) ||
            !QFile::setPermissions(dest, QFileDevice::ReadOwner |
                                             QFileDevice::WriteOwner |
                                             QFileDevice::ExeOwner)) {
          status->setText(tx("Sicherungsordner konnte nicht erstellt werden.",
                             "Could not create backup folder."));
          return;
        }
        channel.call({"backup", dest}, [this](QStringList) {
          if (status)
            status->setText(tx("Verschlüsselte Sicherung erstellt.",
                               "Encrypted backup created."));
        });
      }));
  layout->addLayout(footer);
  return page;
}
void VaultWindow::refresh() {
  channel.call({"list"}, [this](QStringList fields) {
    for (auto &v : rows)
      wipe(v);
    rows = std::move(fields);
    {
      QSignalBlocker block(navigation);
      while (navigation->count() > 7)
        delete navigation->takeItem(7);
      QSet<QString> collections;
      for (int i = 0; i + 5 < rows.size(); i += 6)
        if (!rows[i + 3].isEmpty() && rows[i + 5] != "1")
          collections.insert(rows[i + 3]);
      auto sorted = collections.values();
      sorted.sort(Qt::CaseInsensitive);
      for (const auto &collection : sorted) {
        auto *item = new QListWidgetItem(collection, navigation);
        item->setData(Qt::UserRole, "collection:" + collection);
        item->setSizeHint(QSize(170, 46));
      }
      bool found = false;
      for (int i = 0; i < navigation->count(); ++i)
        if (navigation->item(i)->data(Qt::UserRole).toString() == category) {
          navigation->setCurrentRow(i);
          found = true;
          break;
        }
      if (!found) {
        category = "all";
        navigation->setCurrentRow(0);
      }
    }
    filter();
  });
}
void VaultWindow::filter() {
  if (!entries)
    return;
  const auto old = selectedId();
  entries->clear();
  const auto query = search ? search->text() : QString();
  for (int i = 0; i + 5 < rows.size(); i += 6) {
    const bool trash = rows[i + 5] == "1";
    if ((category == "trash") != trash ||
        (category == "favorite" && rows[i + 4] != "1"))
      continue;
    if (category.startsWith("collection:") && category.mid(11) != rows[i + 3])
      continue;
    if (!category.startsWith("collection:") && category != "all" &&
        category != "favorite" && category != "trash" &&
        category != rows[i + 2])
      continue;
    if (!rows[i + 1].contains(query, Qt::CaseInsensitive) &&
        !rows[i + 3].contains(query, Qt::CaseInsensitive))
      continue;
    auto *item = new QListWidgetItem(rows[i + 1] + "\n" + rows[i + 3], entries);
    item->setData(Qt::UserRole, rows[i]);
    item->setSizeHint(QSize(250, 72));
    if (rows[i] == old)
      entries->setCurrentItem(item);
  }
  if (!entries->currentItem() && entries->count())
    entries->setCurrentRow(0);
  select();
}
int VaultWindow::rowIndex(const QString &id) const {
  for (int i = 0; i + 5 < rows.size(); i += 6)
    if (rows[i] == id)
      return i;
  return -1;
}
QString VaultWindow::selectedId() const {
  return entries && entries->currentItem()
             ? entries->currentItem()->data(Qt::UserRole).toString()
             : QString();
}
void VaultWindow::select() {
  hideSecret();
  if (!heading)
    return;
  auto id = selectedId();
  auto i = rowIndex(id);
  heading->setText(i >= 0 ? rows.value(i + 1)
                          : tx("Noch kein Eintrag", "No entry selected"));
  subtitle->setText(i >= 0
                        ? rows.value(i + 3)
                        : tx("Erstelle einen Zugang oder wähle einen Eintrag.",
                             "Create a credential or select an entry."));
}
void VaultWindow::hideSecret() {
  revealTimer.stop();
  if (secret) {
    auto old = secret->text();
    secret->clear();
    wipe(old);
    secret->setEchoMode(QLineEdit::Password);
    secret->setText("••••••••••••");
  }
}
void VaultWindow::copySecret(QString value) {
  clipboardTag = QUuid::createUuid().toString();
  auto *mime = new QMimeData;
  mime->setText(value);
  mime->setData("x-kde-passwordManagerHint", "secret");
  mime->setData("application/x-lumen-vault-owner", clipboardTag.toUtf8());
  QApplication::clipboard()->setMimeData(mime, QClipboard::Clipboard);
  wipe(value);
  clipboardTimer.start();
  if (status)
    status->setText(tx("Kopiert · wird nach 20 Sekunden entfernt",
                       "Copied · clears after 20 seconds"));
}
void VaultWindow::clearOwnClipboard() {
  clipboardTimer.stop();
  auto *clip = QApplication::clipboard();
  auto *mime = clip->mimeData(QClipboard::Clipboard);
  if (!clipboardTag.isEmpty() && mime &&
      mime->data("application/x-lumen-vault-owner") == clipboardTag.toUtf8())
    clip->clear(QClipboard::Clipboard);
  clipboardTag.clear();
}
void VaultWindow::lock() {
  idle.stop();
  hideSecret();
  clearOwnClipboard();
  channel.stop();
  isOpen = false;
  if (editor) {
    editor->reject();
    delete editor;
  }
  for (auto &v : rows)
    wipe(v);
  rows.clear();
  category = "all";
  replacePage(lockedPage());
}
void VaultWindow::screenLock(bool active) {
  if (active)
    lock();
}
void VaultWindow::suspend(bool active) {
  if (active)
    lock();
}
bool VaultWindow::eventFilter(QObject *object, QEvent *event) {
  if (isOpen &&
      (event->type() == QEvent::MouseButtonPress ||
       event->type() == QEvent::KeyPress || event->type() == QEvent::Wheel)) {
    auto *widget = qobject_cast<QWidget *>(object);
    if (widget &&
        (widget->window() == this || (editor && widget->window() == editor)))
      idle.start();
  }
  return QMainWindow::eventFilter(object, event);
}
void VaultWindow::edit(QStringList fields) {
  if (editor || !isOpen)
    return;
  const QString id = fields.isEmpty() ? QString() : selectedId();
  auto value = [&fields](const QString &key) {
    for (int i = 0; i + 1 < fields.size(); i += 2)
      if (fields[i] == key)
        return fields[i + 1];
    return QString();
  };
  auto *dialog = new QDialog(this);
  editor = dialog;
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->setWindowTitle(id.isEmpty() ? tx("Neuer Eintrag", "New entry")
                                      : tx("Eintrag bearbeiten", "Edit entry"));
  dialog->setMinimumWidth(560);
  auto *layout = new QVBoxLayout(dialog);
  layout->setContentsMargins(26, 24, 26, 24);
  layout->setSpacing(14);
  auto *form = new QFormLayout;
  form->setSpacing(12);
  auto *type = new QComboBox;
  type->addItem(tx("Anmeldung", "Login"), "login");
  type->addItem(tx("API-Token", "API token"), "token");
  type->addItem(tx("Sichere Notiz", "Secure note"), "note");
  type->addItem(tx("Wiederherstellungscodes", "Recovery codes"), "recovery");
  type->setCurrentIndex(qMax(0, type->findData(value("LumenType"))));
  form->addRow(tx("Typ", "Type"), type);
  QMap<QString, QLineEdit *> edits;
  const QList<QPair<QString, QString>> definitions{
      {"Title", tx("Name", "Name")},
      {"LumenCollection", tx("Sammlung", "Collection")},
      {"UserName", tx("Benutzername", "Username")},
      {"URL", tx("Website", "Website")},
      {"Password", tx("Passwort / Token", "Password / token")},
      {"LumenTags", tx("Tags", "Tags")},
      {"LumenExpires", tx("Ablaufdatum", "Expiry date")},
      {"LumenPermissions", tx("Berechtigungen (Notiz)", "Permissions (note)")}};
  for (const auto &definition : definitions) {
    auto *field =
        input("edit" + definition.first, definition.first == "Password");
    field->setText(value(definition.first));
    edits[definition.first] = field;
    form->addRow(definition.second, field);
  }
  for (int i = 0; i + 1 < fields.size(); i += 2) {
    const auto &key = fields[i];
    if (edits.contains(key) || key == "Notes" || key.startsWith("Lumen"))
      continue;
    auto *field = input("customExisting", true);
    field->setMaxLength(16384);
    field->setText(fields[i + 1]);
    edits[key] = field;
    form->addRow(key, field);
  }
  auto *generator =
      button(tx("Zufälliges Passwort erzeugen", "Generate random password"),
             [this, field = QPointer<QLineEdit>(edits["Password"])] {
               channel.call({"generate"}, [field](QStringList reply) {
                 if (field && !reply.isEmpty())
                   field->setText(reply[0]);
                 for (auto &v : reply)
                   wipe(v);
               });
             });
  form->addRow("", generator);
  auto *notes = new QPlainTextEdit(value("Notes"));
  notes->setObjectName("editNotes");
  notes->setMaximumHeight(105);
  notes->setInputMethodHints(Qt::ImhSensitiveData | Qt::ImhNoPredictiveText);
  form->addRow(tx("Notiz / Codes", "Note / codes"), notes);
  auto *customName = input("customName");
  auto *customValue = input("customValue", true);
  form->addRow(tx("Zusatzfeld: Name", "Custom field: name"), customName);
  form->addRow(tx("Zusatzfeld: Wert", "Custom field: value"), customValue);
  auto *formWidget = new QWidget;
  formWidget->setLayout(form);
  auto *scroll = new QScrollArea;
  scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame);
  scroll->setWidget(formWidget);
  scroll->setMinimumHeight(400);
  layout->addWidget(scroll);
  dialog->resize(640, 750);
  auto *info = new QLabel(
      tx("Änderungen werden verschlüsselt gespeichert. Sperren verwirft offene "
         "Eingaben.",
         "Changes are saved encrypted. Locking discards unsaved edits."));
  info->setWordWrap(true);
  info->setObjectName("muted");
  layout->addWidget(info);
  auto *buttons = new QHBoxLayout;
  buttons->addStretch();
  buttons->addWidget(
      button(tx("Abbrechen", "Cancel"), [dialog] { dialog->reject(); }));
  auto *save =
      button(tx("Speichern", "Save"),
             [this, dialog = QPointer<QDialog>(dialog), id, edits, type, notes,
              customName, customValue, info] {
               if (channel.busy())
                 return;
               if (edits["Title"]->text().trimmed().isEmpty()) {
                 info->setText(
                     tx("Bitte einen Namen eingeben.", "Please enter a name."));
                 return;
               }
               if (notes->toPlainText().toUtf8().size() > 16384) {
                 info->setText(tx("Notiz zu lang (max. 16 KiB).",
                                  "Note too long (max. 16 KiB)."));
                 return;
               }
               QStringList request{"put",       id,
                                   "LumenType", type->currentData().toString(),
                                   "Notes",     notes->toPlainText()};
               for (auto it = edits.begin(); it != edits.end(); ++it)
                 request << it.key() << it.value()->text();
               if (!customName->text().isEmpty()) {
                 if (customName->text().size() > 100 ||
                     edits.contains(customName->text()) ||
                     customName->text().startsWith("Lumen") ||
                     customName->text() == "Notes") {
                   info->setText(tx("Anderen Feldnamen wählen.",
                                    "Choose another field name."));
                   return;
                 }
                 request << customName->text() << customValue->text();
               }
               channel.call(std::move(request), [this, dialog](QStringList) {
                 if (dialog)
                   dialog->accept();
                 refresh();
               });
             });
  save->setObjectName("save");
  buttons->addWidget(save);
  layout->addLayout(buttons);
  // Only native widgets hold decrypted edit fields. Never persist drafts or
  // geometry.
  for (auto &v : fields)
    wipe(v);
  dialog->setModal(true);
  dialog->show();
  edits["Title"]->setFocus();
}
void VaultWindow::theme() {
  QSettings settings("Lumen", "Assistant");
  auto name = settings.value("appearance", "glass").toString();
  if (name == currentTheme)
    return;
  currentTheme = name;
  QString bg = "#20343f", base = "#182b35", hover = "#344f5d", fg = "#f0f6f8",
          border = "#526d79", muted = "#b1c5cf", accent = "#9be5d8",
          on = "#123a38";
  if (name == "graphite") {
    bg = "#252b2e";
    base = "#1e2427";
    hover = "#35403f";
    fg = "#edf1ef";
    border = "#485453";
    muted = "#aebcb8";
    accent = "#72c9b1";
    on = "#16372e";
  }
  if (name == "atelier") {
    bg = "#f2efe8";
    base = "#fcfaf5";
    hover = "#e5e1d6";
    fg = "#302e29";
    border = "#c4bfb2";
    muted = "#645e54";
    accent = "#52634f";
    on = "#ffffff";
  }
  if (name == "midnight") {
    bg = "#10151f";
    base = "#141c29";
    hover = "#29364e";
    fg = "#eef1fa";
    border = "#3d4c65";
    muted = "#a9b7ce";
    accent = "#a7b6ff";
    on = "#18203d";
  }
  qApp->setStyleSheet(
      QString("QWidget{background:%1;color:%4;font-size:14px;} "
              "QMainWindow,QDialog{background:%1;} "
              "QFrame#card{background:%2;border:1px solid "
              "%5;border-radius:16px;} QLabel{background:transparent;} "
              "QLabel#brand{font-size:22px;font-weight:600;} "
              "QLabel#title{font-size:27px;font-weight:600;} "
              "QLabel#muted{color:%6;} QLabel#status{color:%7;} "
              "QPushButton{background:transparent;border:1px solid "
              "%5;border-radius:9px;padding:7px 14px;} "
              "QPushButton:hover{background:%3;border-color:%7;} "
              "QPushButton:focus{border:2px solid %7;} "
              "QPushButton#primary,QPushButton#save,QPushButton#new{background:"
              "%7;color:%8;border:0;font-weight:600;} "
              "QLineEdit,QPlainTextEdit,QComboBox{background:%2;border:1px "
              "solid %5;border-radius:8px;padding:6px "
              "10px;selection-background-color:%7;selection-color:%8;} "
              "QLineEdit:focus,QPlainTextEdit:focus{border:1px solid %7;} "
              "QListWidget{background:transparent;border:0;outline:0;} "
              "QListWidget::item{padding:8px 12px;border-radius:10px;} "
              "QListWidget::item:selected{background:%3;color:%4;} "
              "QListWidget::item:hover{background:%2;} "
              "QScrollBar:vertical{background:%2;width:8px;} "
              "QScrollBar::handle:vertical{background:%5;border-radius:4px;min-"
              "height:24px;} "
              "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{"
              "height:0;}")
          .arg(bg, base, hover, fg, border, muted, accent, on));
}

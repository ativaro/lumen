// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#include "vault.h"
#include "passkey.h"
#include <KIdleTime>
#include "bookstack.h"
#include "connection.h"
#include <QtEndian>
#include <cstring>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>

static QIcon glyph(const QString &name);

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
// Disable Qt's implicit PRIMARY export: selecting is local to the editor.
// Explicit copy/cut is handled by the window's guarded clipboard path.
class PrivateNotes : public QPlainTextEdit {
public:
  explicit PrivateNotes(const QString &text) : QPlainTextEdit(text) {
    setUndoRedoEnabled(false);
    setAcceptDrops(false);
    setContextMenuPolicy(Qt::NoContextMenu);
  }

protected:
  QMimeData *createMimeDataFromSelection() const override {
    return new QMimeData;
  }
  void insertFromMimeData(const QMimeData *source) override {
    auto text = source->text();
    if (text.size() > 16384) {
      wipe(text);
      return;
    }
    auto current = toPlainText();
    auto cursor = textCursor();
    current.replace(cursor.selectionStart(),
                    cursor.selectionEnd() - cursor.selectionStart(), text);
    auto bytes = current.toUtf8();
    const bool allowed = bytes.size() <= 16384;
    wipe(bytes);
    wipe(current);
    if (allowed)
      insertPlainText(text);
    wipe(text);
  }
  void inputMethodEvent(QInputMethodEvent *event) override {
    auto current = toPlainText();
    auto text = event->commitString();
    current += text;
    auto bytes = current.toUtf8();
    bool allowed =
        bytes.size() <= 16384 && event->preeditString().size() <= 16384;
    wipe(current);
    wipe(text);
    wipe(bytes);
    if (allowed)
      QPlainTextEdit::inputMethodEvent(event);
    else
      event->ignore();
  }
  void keyPressEvent(QKeyEvent *event) override {
    const auto typed = event->text();
    const bool printable = std::any_of(typed.begin(), typed.end(),
                                       [](QChar c) { return c.isPrint(); });
    if (printable || event->key() == Qt::Key_Return ||
        event->key() == Qt::Key_Enter) {
      auto current = toPlainText();
      auto cursor = textCursor();
      current.replace(cursor.selectionStart(),
                      cursor.selectionEnd() - cursor.selectionStart(),
                      event->text());
      auto bytes = current.toUtf8();
      bool allowed = bytes.size() <= 16384;
      wipe(bytes);
      wipe(current);
      if (!allowed) {
        event->accept();
        return;
      }
    }
    QPlainTextEdit::keyPressEvent(event);
  }
};
QLineEdit *vaultInput(const QString &name, bool hidden) {
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
  for (auto &request : queued)
    for (auto &field : request.first)
      wipe(field);
  queued.clear();
  wipe(buffer);
  if (child.state() != QProcess::NotRunning) {
    // EOF allows Session and the wiping allocator to run even after a pending
    // call.
    child.closeWriteChannel();
    if (!child.waitForFinished(1500)) {
      child.kill(); // Hung child only; graceful wiping cannot be promised here.
      child.waitForFinished(1000);
    }
  }
  stopping = false;
}
void Channel::call(QStringList fields, Reply callback) {
  if (pending) {
    if (queued.size() < 8)
      queued.append({std::move(fields), std::move(callback)});
    else {
      for (auto &field : fields)
        wipe(field);
      stop();
      emit failed("Busy");
    }
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
  qsizetype bytesNeeded = 4;
  for (const auto &field : fields)
    bytesNeeded += 4 + field.size() * 3;
  if (bytesNeeded > 4 * 1024 * 1024 || fields.size() > 4096) {
    for (auto &field : fields)
      wipe(field);
    emit failed("Limit");
    return;
  }
  QByteArray payload;
  payload.reserve(bytesNeeded);
  number(payload, fields.size());
  for (auto &field : fields) {
    auto bytes = field.toUtf8();
    number(payload, bytes.size());
    payload += bytes;
    wipe(bytes);
    wipe(field);
  }
  QByteArray message;
  message.reserve(payload.size() + 4);
  number(message, payload.size());
  message += payload;
  wipe(payload);
  pending = std::move(callback);
  deadline.start();
  child.write(message);
  wipe(message);
}
void Channel::read() {
  auto incoming = child.readAllStandardOutput();
  if (stopping) {
    wipe(incoming);
    return;
  }
  buffer += incoming;
  wipe(incoming);
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
  if (!pending && !queued.isEmpty()) {
    auto next = queued.takeFirst();
    call(std::move(next.first), std::move(next.second));
  }
}
VaultWindow::VaultWindow(const QString &root)
    : root(root), channel(root, this) {
  QSettings settings("Lumen", "Assistant");
  const auto language = settings.value("uiLanguage", "system").toString();
  english =
      language == "en" ||
      (language == "system" && QLocale::system().language() != QLocale::German);
  access = new VaultAccess(
      this,
      [this](QString id, std::function<void(QStringList)> callback) {
        if (!isOpen) {
          callback({});
          return;
        }
        channel.call({"edit", id}, std::move(callback));
      },
      english);
  access->setUnlock([this] { return isOpen && !accessLoading; }, [this]() -> QDialog * {
    if (isOpen || !QFileInfo::exists(this->root + "/vault.kdbx")) return nullptr;
    show(); raise(); activateWindow();
    auto *dialog = new QDialog(this);
    dialog->setObjectName("vaultUnlockRequest");
    dialog->setWindowTitle(tx("Lumen Vault entsperren", "Unlock Lumen Vault"));
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->setWindowModality(Qt::WindowModal);
    auto *layout = new QVBoxLayout(dialog);
    auto *notice = new QLabel(tx("Lumen benötigt deinen Tresor. Entsperre ihn lokal; die konkrete Aktion bestätigst du danach separat.",
      "Lumen needs your vault. Unlock it locally; confirm the exact action separately afterwards."));
    notice->setWordWrap(true);
  notice->setMinimumHeight(48); layout->addWidget(notice);
    auto *message = new QLabel; message->setObjectName("requestUnlockError");
    message->setWordWrap(true); layout->addWidget(message);
    auto *password = vaultInput("requestMaster", true);
    password->setPlaceholderText(tx("Hauptpasswort", "Master password")); layout->addWidget(password);
    auto *submit = button(tx("Entsperren", "Unlock"), [this, password] {
      if (channel.busy() || isOpen) return;
      master->setText(password->text()); password->clear(); authorize(false);
    });
    submit->setObjectName("requestUnlock"); layout->addWidget(submit);
    connect(password, &QLineEdit::returnPressed, submit, &QPushButton::click);
    layout->addWidget(button(tx("Abbrechen", "Cancel"), [dialog] { dialog->reject(); }));
    connect(dialog, &QDialog::finished, this, [this, password] {
      password->clear(); if (!isOpen) channel.stop();
    });
    dialog->open(); password->setFocus(); return dialog;
  });
  access->setStore([this](const QJsonObject &args) -> QDialog * {
    showSection(0);
    show();
    raise();
    activateWindow();
    if (!isOpen || editor)
      return nullptr;
    QStringList fields{"Title", args.value("title").toString(), "LumenType",
                       args.value("kind").toString()};
    const auto prefill = args.value("prefill").toObject();
    for (auto it = prefill.begin(); it != prefill.end(); ++it)
      fields << it.key() << it.value().toString();
    edit(std::move(fields), true, args.contains("prefill"));
    if (editor)
      editor->setWindowTitle(tx("Diesen Zugang im Tresor speichern?",
                                "Save this credential in Vault?"));
    return editor;
  });
  setWindowTitle("Lumen Vault");
  resize(1510, 926);
  setMinimumSize(1080, 720);
  idle.setSingleShot(true);
  idle.setParent(this);
  keepalive.setParent(this);
  idle.setObjectName("vaultIdleTimer");
  QSettings vaultSettings("Lumen", "Vault");
  setIdleMinutes(vaultSettings.value("idleMinutes", 15).toInt());
  keepalive.setObjectName("vaultKeepaliveTimer");
  keepalive.setInterval(60000);
  connect(&keepalive, &QTimer::timeout, this, [this] {
    if (isOpen && idle.isActive() && !channel.busy())
      channel.call({"keepalive"}, [](QStringList) {});
  });
  // On Wayland idleTime() cannot be polled; use compositor resume events.
  if (QGuiApplication::platformName() == "wayland" ||
      QGuiApplication::platformName() == "xcb") {
    auto *activity = KIdleTime::instance();
    connect(activity, &KIdleTime::resumingFromIdle, this, [this, activity] {
      sessionActivity();
      activity->catchNextResumeEvent();
    });
    activity->catchNextResumeEvent();
  }
  detailTimer.setSingleShot(true);
  detailTimer.setInterval(60);
  connect(&detailTimer, &QTimer::timeout, this, &VaultWindow::loadDetails);
  revealTimer.setSingleShot(true);
  revealTimer.setInterval(10000);
  clipboardTimer.setSingleShot(true);
  clipboardTimer.setInterval(20000);
  connect(&idle, &QTimer::timeout, this, &VaultWindow::lock);
  connect(&revealTimer, &QTimer::timeout, this, &VaultWindow::hideSecret);
  connect(&clipboardTimer, &QTimer::timeout, this,
          &VaultWindow::clearOwnClipboard);
  connect(&channel, &Channel::failed, this, [this](const QString &code) {
    if (!isOpen && access->waitingForUnlock()) {
      if (auto *message = findChild<QLabel *>("requestUnlockError"))
        message->setText(tx("Entsperren fehlgeschlagen. Bitte Hauptpasswort prüfen oder abbrechen.", "Unlock failed. Check the master password or cancel."));
      return;
    }
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
  sections = new QStackedWidget;
  auto *shell = new QWidget;
  auto *layout = new QVBoxLayout(shell);
  layout->setContentsMargins(0, 0, 0, 0);
  layout->setSpacing(0);
  layout->addWidget(header());
  layout->addWidget(sections, 1);
  setCentralWidget(shell);
  replacePage(lockedPage());
  tray = new QSystemTrayIcon(glyph("object-locked"), this);
  auto *trayMenu = new QMenu(this);
  trayMenu->addAction(tx("Lumen Vault öffnen", "Open Lumen Vault"), this, [this] {
    showNormal(); raise(); activateWindow();
  });
  trayLock = trayMenu->addAction(tx("Jetzt sperren", "Lock now"), this, &VaultWindow::lock);
  trayMenu->addSeparator();
  trayMenu->addAction(tx("Sperren und beenden", "Lock and quit"), this, [this] {
    hide();
    // Avoid the normal process-retirement restart when quitting explicitly.
    disconnect(this, &VaultWindow::retire, nullptr, nullptr);
    lock();
    emit quitRequested();
  });
  tray->setContextMenu(trayMenu);
  connect(tray, &QSystemTrayIcon::activated, this, [this](QSystemTrayIcon::ActivationReason reason) {
    if (reason == QSystemTrayIcon::Trigger) { showNormal(); raise(); activateWindow(); }
  });
  updateHeader();
  tray->show();
  theme();
  themeTimer.setInterval(2000);
  connect(&themeTimer, &QTimer::timeout, this, &VaultWindow::theme);
  themeTimer.start();
  autoSyncTimer.setInterval(60000);
  connect(&autoSyncTimer, &QTimer::timeout, this, &VaultWindow::pollServerSync);
  autoSyncTimer.start();
}
VaultWindow::~VaultWindow() {
  isOpen = false;
  visibilityId.clear();
  if (passkeyBridge) delete passkeyBridge;
  if (autoSyncProcess) {
    autoSyncProcess->disconnect(this);
    autoSyncProcess->kill();
    autoSyncProcess->waitForFinished(1000);
  }
  ++accessRevision;
  delete access;
  access = nullptr;
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
  b->setIconSize(QSize(21, 21));
  b->setCursor(Qt::PointingHandCursor);
  connect(b, &QPushButton::clicked, this, std::move(action));
  return b;
}
void VaultWindow::replacePage(QWidget *page) {
  if (auto *old = credentialPage.data()) {
    sections->removeWidget(old);
    for (auto *field : old->findChildren<QLineEdit *>())
      field->setText({});
    delete old;
  }
  credentialPage = page;
  sections->insertWidget(0, page);
  sections->setCurrentWidget(page);
  updateHeader();
}
class TintedIcon : public QIconEngine {
public:
  explicit TintedIcon(QString name) : name(std::move(name)) {}
  QIconEngine *clone() const override { return new TintedIcon(name); }
  QPixmap pixmap(const QSize &size, QIcon::Mode mode,
                 QIcon::State state) override {
    auto pix = QIcon(":/vault/" + name + ".svg").pixmap(size, mode, state);
    QPainter painter(&pix);
    painter.setCompositionMode(QPainter::CompositionMode_SourceIn);
    painter.fillRect(pix.rect(),
                     QApplication::palette().color(QPalette::WindowText));
    return pix;
  }
  void paint(QPainter *painter, const QRect &rect, QIcon::Mode mode,
             QIcon::State state) override {
    painter->drawPixmap(rect, pixmap(rect.size(), mode, state));
  }

private:
  QString name;
};
static QIcon glyph(const QString &name) { return QIcon(new TintedIcon(name)); }
int VaultWindow::section() const { return 0; }
void VaultWindow::showSection(int index) {
  if (index == 1) {
    hideSecret();
    clearOwnClipboard();
    emit backupsRequested();
  } else if (index == 0) {
    sections->setCurrentWidget(credentialPage.data());
  }
}
QWidget *VaultWindow::lockedPage() {
  auto *page = new QWidget;
  auto *outer = new QVBoxLayout(page);
  outer->setContentsMargins(36, 28, 36, 28);
  outer->addStretch();
  auto *card = new QFrame;
  card->setObjectName("card");
  card->setMinimumWidth(480);
  card->setMaximumWidth(510);
  auto *layout = new QVBoxLayout(card);
  layout->setContentsMargins(36, 30, 36, 30);
  layout->setSpacing(14);
  auto *title = new QLabel(
      tx("Dein Tresor. Lokal bei dir.", "Your vault. Stored locally."));
  title->setObjectName("title");
  layout->addWidget(title);
  auto *notice = new QLabel(tx("Vorabversion.\nDie "
                               "unabhängige Sicherheitsprüfung steht noch aus.",
                               "Prerelease.\nIndependent "
                               "security review is still pending."));
  notice->setWordWrap(true);
  notice->setObjectName("muted");
  layout->addWidget(notice);
  const bool exists = QFileInfo::exists(root + "/vault.kdbx");
  layout->addSpacing(12);
  master = vaultInput("master", true);
  master->setPlaceholderText(tx("Hauptpasswort", "Master password"));
  layout->addWidget(master);
  if (!exists) {
    confirm = vaultInput("confirm", true);
    confirm->setPlaceholderText(
        tx("Hauptpasswort wiederholen", "Repeat master password"));
    layout->addWidget(confirm);
  }
  auto *submit = button(exists ? tx("Entsperren", "Unlock")
                               : tx("Tresor erstellen", "Create vault"),
                        [this, exists] { authorize(!exists); });
  submit->setObjectName("primary");
  layout->addWidget(submit);
  if (exists && !passkeyMetadata().isEmpty()) {
    auto *quick = button(tx("Mit Passkey entsperren", "Unlock with passkey"), [this] { passkey(false); });
    quick->setObjectName("passkeyUnlock");
    layout->addWidget(quick);
  }
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
    help->setMinimumHeight(64);
    help->setObjectName("muted");
    layout->addWidget(help);
    layout->addWidget(button(tx("Verschlüsselte Sicherung wiederherstellen…",
                                "Restore encrypted backup…"),
                             [this] { authorize(false, true); }));
    layout->addWidget(button(tx("Tresor von Lumen Server übernehmen…", "Restore vault from Lumen Server…"), [this] { serverSync(); }));
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
      for (auto &v : args)
        wipe(v);
      wipe(value);
      return;
    }
    args = {"restore", file, value};
  }
  master->setText({});
  if (confirm)
    confirm->setText({});
  wipe(value);
  status->setText(tx("Tresor wird geöffnet…", "Opening vault…"));
  channel.call(std::move(args), [this](QStringList) {
    isOpen = true;
    sessionActivity();
    keepalive.start();
    replacePage(openPage());
    refresh();
  });
}
class EntryDelegate final : public QStyledItemDelegate {
public:
  using QStyledItemDelegate::QStyledItemDelegate;
  void paint(QPainter *p, const QStyleOptionViewItem &option,
             const QModelIndex &index) const override {
    p->save();
    p->setRenderHint(QPainter::Antialiasing);
    const auto palette = QApplication::palette();
    const bool selected = option.state & QStyle::State_Selected;
    const bool hover = option.state & QStyle::State_MouseOver;
    const QRect area = option.rect.adjusted(0, 2, -1, -2);
    if (selected || hover) {
      auto color = palette.color(QPalette::AlternateBase);
      if (!selected)
        color.setAlpha(100);
      p->setPen(Qt::NoPen);
      p->setBrush(color);
      p->drawRoundedRect(area, 8, 8);
      if (selected) {
        p->setBrush(palette.color(QPalette::Highlight));
        p->drawRoundedRect(
            QRect(area.left(), area.top() + 3, 3, area.height() - 6), 1.5, 1.5);
      }
    } else {
      p->setPen(palette.color(QPalette::Mid));
      p->drawLine(area.left() + 16, area.bottom(), area.right() - 16,
                  area.bottom());
    }
    const auto icon = qvariant_cast<QIcon>(index.data(Qt::DecorationRole));
    icon.paint(p, QRect(area.left() + 26, area.center().y() - 17, 34, 34));
    const auto title = index.data(Qt::UserRole + 1).toString();
    const auto subtitle = index.data(Qt::UserRole + 2).toString();
    QFont font = option.font;
    font.setPixelSize(18);
    p->setFont(font);
    p->setPen(palette.color(QPalette::Text));
    QRect text(area.left() + 94, area.top() + 14, area.width() - 136, 27);
    p->drawText(
        text, Qt::AlignVCenter,
        QFontMetrics(font).elidedText(title, Qt::ElideRight, text.width()));
    font.setPixelSize(14);
    p->setFont(font);
    p->setPen(palette.color(QPalette::PlaceholderText));
    text.translate(0, 27);
    p->drawText(
        text, Qt::AlignVCenter,
        QFontMetrics(font).elidedText(subtitle, Qt::ElideRight, text.width()));
    glyph("go-next").paint(
        p, QRect(area.right() - 34, area.center().y() - 9, 18, 18));
    if (option.state & QStyle::State_HasFocus) {
      p->setPen(QPen(palette.color(QPalette::Highlight), 1));
      p->setBrush(Qt::NoBrush);
      p->drawRoundedRect(area.adjusted(1, 1, -1, -1), 8, 8);
    }
    p->restore();
  }
};
static QLabel *symbol(const QString &name, int size = 24) {
  auto *label = new QLabel;
  label->setProperty("glyph", name);
  label->setProperty("glyphSize", size);
  label->setPixmap(glyph(name).pixmap(size, size));
  label->setFixedSize(size, size);
  label->setAlignment(Qt::AlignCenter);
  return label;
}
static void spacedButton(QPushButton *button) {
  const auto text = button->text();
  const auto icon = button->icon();
  button->setAccessibleName(text);
  button->setText({});
  button->setIcon({});
  auto *layout = new QHBoxLayout(button);
  layout->setContentsMargins(16, 0, 16, 0);
  layout->setSpacing(12);
  auto *mark = new QLabel;
  mark->setPixmap(icon.pixmap(button->iconSize()));
  mark->setFixedSize(button->iconSize());
  mark->setAttribute(Qt::WA_TransparentForMouseEvents);
  layout->addWidget(mark);
  auto *caption = new QLabel(text);
  caption->setAttribute(Qt::WA_TransparentForMouseEvents);
  layout->addWidget(caption);
  layout->setAlignment(button->objectName() == "settings" ? Qt::AlignLeft
                                                          : Qt::AlignCenter);
  button->setMinimumWidth(layout->sizeHint().width());
  // Refresh icons with the theme without re-reading any entry data.
  mark->setProperty("buttonIcon", icon);
  mark->setProperty("glyphSize", button->iconSize().width());
}
static QFrame *rule() {
  auto *r = new QFrame;
  r->setObjectName("rule");
  r->setFixedHeight(1);
  return r;
}
QWidget *VaultWindow::header() {
  auto *frame = new QFrame;
  frame->setObjectName("vaultHeader");
  auto *outer = new QVBoxLayout(frame);
  outer->setContentsMargins(0, 0, 0, 0);
  outer->setSpacing(0);
  auto *row = new QHBoxLayout;
  row->setContentsMargins(0, 0, 20, 0);
  row->setSpacing(16);
  auto *brand = new QWidget;
  brand->setFixedWidth(296);
  auto *brandRow = new QHBoxLayout(brand);
  brandRow->setContentsMargins(28, 20, 12, 20);
  brandRow->setSpacing(18);
  brandRow->addWidget(symbol("lumen-mark", 54));
  auto *copy = new QVBoxLayout;
  copy->setSpacing(2);
  auto *title = new QLabel("Lumen Vault");
  title->setObjectName("brand");
  copy->addWidget(title);
  auto *tag = new QLabel(tx("Deine Daten. In deiner Hand.", "Your data. In your hands."));
  tag->setObjectName("tagline");
  copy->addWidget(tag);
  brandRow->addLayout(copy);
  row->addWidget(brand);
  row->addStretch();
  headerIcon = symbol("object-locked", 26);
  row->addWidget(headerIcon);
  headerState = new QLabel;
  headerState->setObjectName("status");
  row->addWidget(headerState);
  headerLock = button(tx("Sperren", "Lock"), [this] { lock(); });
  headerLock->setObjectName("lock");
  headerLock->setIcon(glyph("object-locked"));
  spacedButton(headerLock);
  headerLock->setMinimumWidth(144);
  row->addWidget(headerLock);
  outer->addLayout(row);
  outer->addWidget(rule());
  return frame;
}
void VaultWindow::updateHeader() {
  const auto icon = isOpen ? "object-unlocked" : "object-locked";
  if (tray) {
    tray->setIcon(glyph(icon));
    tray->setToolTip(tx("Lumen Vault · ", "Lumen Vault · ") +
                     (isOpen ? tx("Entsperrt", "Unlocked") : tx("Gesperrt", "Locked")));
    trayLock->setEnabled(isOpen);
  }
  headerIcon->setProperty("glyph", icon);
  headerIcon->setPixmap(glyph(icon).pixmap(26, 26));
  headerState->setText(isOpen ? tx("Entsperrt", "Unlocked") : tx("Gesperrt", "Locked"));
  headerLock->setEnabled(isOpen);
}
QString VaultWindow::kind(const QString &key) const {
  if (key == "token")
    return tx("API-Token", "API token");
  if (key == "note")
    return tx("Sichere Notiz", "Secure note");
  if (key == "recovery")
    return tx("Wiederherstellung", "Recovery codes");
  return tx("Anmeldung", "Login");
}
QWidget *VaultWindow::openPage() {
  auto *page = new QWidget;
  auto *outer = new QVBoxLayout(page);
  outer->setContentsMargins(0, 0, 0, 0);
  outer->setSpacing(0);
  auto *content = new QHBoxLayout;
  content->setSpacing(0);
  auto *sidebar = new QFrame;
  sidebar->setObjectName("sidebar");
  sidebar->setFixedWidth(296);
  auto *sl = new QVBoxLayout(sidebar);
  sl->setContentsMargins(16, 28, 12, 22);
  sl->setSpacing(12);
  auto *caption = new QLabel(tx("Mein Tresor", "My vault"));
  caption->setObjectName("muted");
  caption->setContentsMargins(12, 0, 0, 0);
  sl->addWidget(caption);
  navigation = new QListWidget;
  navigation->setObjectName("navigation");
  navigation->setIconSize(QSize(26, 26));
  navigation->setSpacing(3);
  const QStringList labels{
      tx("Alle Einträge", "All entries"), tx("Favoriten", "Favorites"),
      tx("Passwörter", "Passwords"), tx("API-Tokens", "API tokens"),
      tx("Sichere Notizen", "Secure notes")};
  const QStringList keys{"all", "favorite", "login", "token", "note"};
  const QStringList icons{"view-list-details", "favorite", "dialog-password",
                          "code-context", "document-edit"};
  for (int i = 0; i < labels.size(); ++i) {
    auto *item = new QListWidgetItem(glyph(icons[i]), labels[i], navigation);
    item->setData(Qt::UserRole, keys[i]);
    item->setSizeHint(QSize(200, 50));
  }
  navigation->setCurrentRow(0);
  connect(navigation, &QListWidget::currentRowChanged, this, [this] {
    category = navigation->currentItem()
                   ? navigation->currentItem()->data(Qt::UserRole).toString()
                   : "all";
    filter();
  });
  sl->addWidget(navigation, 1);
  auto *settings = button(tx("Einstellungen", "Settings"), [this] {
    QMenu menu(this);
    menu.addAction(tx("Proton Pass / Passkey einrichten…", "Set up Proton Pass / passkey…"), this, [this] { passkey(true); });
    if (QFileInfo::exists(root + "/passkey"))
      menu.addAction(tx("Passkey-Verknüpfung entfernen…", "Remove passkey link…"), this, &VaultWindow::removePasskey);
    menu.addSeparator();
    menu.addAction(tx("Serverabgleich…", "Server synchronization…"), this, &VaultWindow::serverSync);
    menu.addAction(
        tx("Verschlüsselte Sicherung exportieren…", "Export encrypted backup…"),
        this, &VaultWindow::backup);
    menu.addSeparator();
    menu.addAction(tx("Wiederherstellungscodes", "Recovery codes"), [this] {
      category = "recovery";
      {
        QSignalBlocker block(navigation);
        navigation->setCurrentRow(-1);
      }
      filter();
    });
    menu.addAction(tx("Papierkorb", "Trash"), [this] {
      category = "trash";
      {
        QSignalBlocker block(navigation);
        navigation->setCurrentRow(-1);
      }
      filter();
    });
    menu.addSeparator();
    menu.addAction(
        tx("Über Lumen Vault · Lizenzen", "About Lumen Vault · Licenses"), this,
        &VaultWindow::about);
    menu.exec(QCursor::pos());
  });
  settings->setObjectName("settings");
  settings->setIcon(glyph("configure"));
  settings->setIconSize(QSize(30, 30));
  spacedButton(settings);
  sl->addWidget(settings);
  content->addWidget(sidebar);
  auto *main = new QVBoxLayout;
  main->setContentsMargins(0, 0, 0, 0);
  main->setSpacing(0);
  auto *columns = new QHBoxLayout;
  columns->setSpacing(0);
  auto *middle = new QFrame;
  middle->setObjectName("middle");
  middle->setMinimumWidth(340);
  middle->setMaximumWidth(520);
  auto *ml = new QVBoxLayout(middle);
  ml->setContentsMargins(10, 20, 10, 18);
  ml->setSpacing(18);
  auto *tools = new QHBoxLayout;
  search = vaultInput("search");
  search->setPlaceholderText(tx("Im Tresor suchen …", "Search this vault …"));
  search->addAction(glyph("edit-find"), QLineEdit::LeadingPosition);
  tools->addWidget(search, 1);
  auto *add = button(tx("Neuer Eintrag", "New entry"), [this] { edit(); });
  add->setIcon(glyph("list-add"));
  add->setObjectName("new");
  spacedButton(add);
  tools->addWidget(add);
  ml->addLayout(tools);
  connect(search, &QLineEdit::textChanged, this, [this] { filter(); });
  entries = new QListWidget;
  entries->setObjectName("entries");
  entries->setIconSize(QSize(30, 30));
  entries->setSpacing(0);
  entries->setSortingEnabled(true);
  entries->setMouseTracking(true);
  entries->setItemDelegate(new EntryDelegate(entries));
  ml->addWidget(entries, 1);
  connect(entries, &QListWidget::currentRowChanged, this, [this] { select(); });
  columns->addWidget(middle, 4);
  auto *detail = new QWidget;
  auto *dl = new QVBoxLayout(detail);
  dl->setContentsMargins(28, 28, 28, 32);
  dl->setSpacing(12);
  auto *titleRow = new QHBoxLayout;
  auto *avatar = symbol("dialog-password", 48);
  avatar->setAlignment(Qt::AlignCenter);
  avatar->setFixedSize(102, 102);
  avatar->setObjectName("avatar");
  titleRow->addWidget(avatar);
  titleRow->addSpacing(12);
  auto *titleCol = new QVBoxLayout;
  titleCol->setSpacing(4);
  titleCol->addStretch();
  heading = new QLabel;
  heading->setObjectName("title");
  heading->setTextFormat(Qt::PlainText);
  heading->setWordWrap(true);
  titleCol->addWidget(heading);
  subtitle = new QLabel;
  subtitle->setObjectName("muted");
  subtitle->setTextFormat(Qt::PlainText);
  subtitle->setWordWrap(true);
  titleCol->addWidget(subtitle);
  titleCol->addStretch();
  titleRow->addLayout(titleCol, 1);
  auto *fav = button("", [this] {
    auto id = selectedId();
    int i = rowIndex(id);
    if (i >= 0)
      channel.call({"favorite", id, rows.value(i + 4) == "1" ? "0" : "1"},
                   [this](QStringList) { refresh(); });
  });
  fav->setIcon(glyph("favorite"));
  fav->setToolTip(tx("Favorit umschalten", "Toggle favorite"));
  fav->setAccessibleName(fav->toolTip());
  fav->setObjectName("quiet");
  fav->setFixedWidth(40);
  titleRow->addWidget(fav);
  auto *more = button("⋮", [this] {
    QMenu menu(this);
    menu.addAction(tx("Versionsverlauf…", "Version history…"), this,
                   &VaultWindow::history);
    menu.addSeparator();
    menu.addAction(
        category == "trash" ? tx("Wiederherstellen", "Restore")
                            : tx("In den Papierkorb", "Move to trash"),
        [this] {
          auto id = selectedId();
          int i = rowIndex(id);
          ++accessRevision;
          access->revoke();
          if (i >= 0)
            channel.call({"trash", id, rows.value(i + 5) == "1" ? "0" : "1"},
                         [this](QStringList) { refresh(); });
        });
    menu.exec(QCursor::pos());
  });
  more->setObjectName("quiet");
  more->setFixedWidth(35);
  more->setAccessibleName(tx("Weitere Aktionen", "More actions"));
  titleRow->addWidget(more);
  dl->addLayout(titleRow);
  dl->addSpacing(12);
  dl->addWidget(rule());
  dl->addSpacing(8);
  auto addField = [this, dl](const QString &name, const QString &caption,
                             bool hidden) {
    auto *label = new QLabel(caption);
    label->setObjectName("muted");
    dl->addWidget(label);
    auto *frame = new QFrame;
    frame->setObjectName("fieldRow");
    frame->setFixedHeight(50);
    auto *row = new QHBoxLayout(frame);
    row->setContentsMargins(2, 1, 1, 1);
    row->setSpacing(0);
    auto *field = vaultInput(name, hidden);
    field->setReadOnly(true);
    field->setFocusPolicy(Qt::NoFocus);
    field->setAttribute(Qt::WA_TransparentForMouseEvents);
    field->setClearButtonEnabled(false);
    row->addWidget(field, 1);
    if (hidden) {
      auto *show = button("", [this] {
        auto id = selectedId();
        auto epoch = generation;
        if (id.isEmpty())
          return;
        channel.call({"get", id, "Password"},
                     [this, id, epoch](QStringList fields) {
                       if (secret && isOpen && generation == epoch &&
                           selectedId() == id && !fields.isEmpty()) {
                         secret->setEchoMode(QLineEdit::Normal);
                         secret->setText(fields[0]);
                         revealTimer.start();
                       }
                       for (auto &v : fields)
                         wipe(v);
                     });
      });
      show->setIcon(glyph("view-visible"));
      show->setToolTip(tx("10 Sekunden anzeigen", "Show for 10 seconds"));
      show->setAccessibleName(show->toolTip());
      show->setFixedSize(48, 46);
      show->setProperty("fieldAction", true);
      row->addWidget(show);
    }
    auto *copy = button("", [this, name] {
      auto id = selectedId();
      auto epoch = generation;
      if (id.isEmpty())
        return;
      channel.call({"get", id,
                    name == "secret"    ? "Password"
                    : name == "website" ? "URL"
                                        : "UserName"},
                   [this, id, epoch](QStringList fields) {
                     if (isOpen && generation == epoch && selectedId() == id &&
                         !fields.isEmpty())
                       copySecret(fields[0]);
                     for (auto &v : fields)
                       wipe(v);
                   });
    });
    copy->setIcon(glyph("edit-copy"));
    copy->setToolTip(tx("Kopieren · 20 Sekunden", "Copy · 20 seconds"));
    copy->setAccessibleName(caption + " · " + tx("Kopieren", "Copy"));
    copy->setFixedSize(48, 46);
    copy->setProperty("fieldAction", true);
    if (hidden)
      copy->setObjectName("copy");
    row->addWidget(copy);
    dl->addWidget(frame);
    dl->addSpacing(hidden ? 0 : 12);
    return field;
  };
  website = addField("website", tx("Website", "Website"), false);
  username = addField(
      "username", tx("Benutzername / Token-ID", "Username / token ID"), false);
  secret = addField(
      "secret", tx("Passwort / Token-Secret", "Password / token secret"), true);
  secret->setText("••••••••••••••••••");
  auto passwordFont = secret->font();
  passwordFont.setLetterSpacing(QFont::AbsoluteSpacing, 1.4);
  secret->setFont(passwordFont);
  auto *copyHint = new QLabel(tx("Nach dem Kopieren nach 20 s leeren",
                                 "Clear clipboard 20 seconds after copying"));
  copyHint->setObjectName("caption");
  dl->addWidget(copyHint);
  dl->addSpacing(8);
  dl->addWidget(rule());
  auto *accessRow = new QHBoxLayout;
  accessRow->setContentsMargins(0, 12, 0, 12);
  accessRow->setSpacing(18);
  accessRow->addWidget(symbol("package", 30), 0, Qt::AlignTop);
  auto *accessText = new QVBoxLayout;
  accessText->setSpacing(8);
  accessText->addWidget(new QLabel(tx("Lumen Zugriff", "Lumen access")));
  auto *boundary = new QLabel;
  accessStatus = boundary;
  boundary->setObjectName("accessStatus");
  boundary->setObjectName("accessStatus");
  boundary->setWordWrap(true);
  accessText->addWidget(boundary);
  auto *explanation =
      new QLabel(tx("Lumen sieht Name, Typ und Dienst. Jede Verwendung braucht deine Bestätigung. Ausgeblendete Einträge bleiben für Lumen unsichtbar.",
                    "Lumen sees name, type and service. Each use needs your confirmation. Hidden entries stay invisible to Lumen."));
  explanation->setObjectName("caption");
  explanation->setWordWrap(true);
  accessText->addWidget(explanation);
  accessRow->addLayout(accessText, 1);
  auto *permissions = new QCheckBox(tx("Für Lumen nicht freigeben", "Hide from Lumen"));
  connect(permissions, &QCheckBox::clicked, this, [this] { shareConnection(); });
  permissions->setObjectName("apiAccess");
  accessButton = permissions;
  connect(access, &VaultAccess::changed, boundary, [this] { updateAccess(); });
  updateAccess();
  accessRow->addWidget(permissions, 0, Qt::AlignVCenter);
  dl->addLayout(accessRow);
  dl->addStretch();
  dl->addWidget(rule());
  auto *bottom = new QHBoxLayout;
  auto *versions =
      button(tx("Versionsverlauf", "Version history"), [this] { history(); });
  versions->setObjectName("quiet");
  versions->setIcon(glyph("clock"));
  spacedButton(versions);
  bottom->addWidget(versions);
  bottom->addStretch();
  auto *editButton = button(tx("Bearbeiten", "Edit"), [this] {
    auto id = selectedId();
    if (id.isEmpty())
      return;
    auto epoch = generation;
    channel.call({"edit", id}, [this, id, epoch](QStringList fields) {
      if (isOpen && generation == epoch && selectedId() == id)
        edit(std::move(fields));
      else
        for (auto &v : fields)
          wipe(v);
    });
  });
  editButton->setIcon(glyph("document-edit"));
  editButton->setMinimumWidth(160);
  spacedButton(editButton);
  bottom->addWidget(editButton);
  dl->addLayout(bottom);
  auto *scroll = new QScrollArea;
  scroll->setObjectName("detailScroll");
  scroll->setFrameShape(QFrame::NoFrame);
  scroll->setWidgetResizable(true);
  scroll->setWidget(detail);
  scroll->setMinimumWidth(410);
  columns->addWidget(scroll, 5);
  main->addLayout(columns, 1);
  content->addLayout(main, 1);
  outer->addLayout(content, 1);
  outer->addWidget(rule());
  auto *footer = new QHBoxLayout;
  footer->setContentsMargins(24, 14, 24, 14);
  status = new QLabel(tx("Lokaler Tresor", "Local vault"));
  status->setObjectName("muted");
  footer->addWidget(symbol("database", 22));
  footer->addSpacing(8);
  footer->addWidget(status, 1);
  auto *autoLock = new QComboBox;
  autoLock->setObjectName("vaultAutoLock");
  autoLock->setAccessibleName(tx("Sperren bei Inaktivität", "Lock when idle"));
  for (int minutes : {5, 15, 30})
    autoLock->addItem(tx("Bei Inaktivität · %1 min", "When idle · %1 min").arg(minutes), minutes);
  autoLock->setCurrentIndex(autoLock->findData(idleMinutes));
  autoLock->setToolTip(tx("Aktivität am PC zählt. Bildschirmsperre und Standby sperren sofort. Ohne Desktop-Aktivitätserkennung zählt nur die Bedienung im Tresor.",
                         "PC activity counts. Screen lock and sleep lock immediately. Without desktop activity detection, only Vault interaction counts."));
  connect(autoLock, &QComboBox::currentIndexChanged, this, [this, autoLock] {
    setIdleMinutes(autoLock->currentData().toInt());
    QSettings("Lumen", "Vault").setValue("idleMinutes", idleMinutes);
  });
  footer->addWidget(symbol("clock", 22));
  footer->addWidget(autoLock);
  outer->addLayout(footer);
  return page;
}
void VaultWindow::about() {
  QMessageBox::information(
      this, tx("Über Lumen Vault", "About Lumen Vault"),
      tx("Vorabversion · Nur Testdaten verwenden. Die unabhängige "
         "Sicherheitsprüfung steht noch aus.\n\nQt 6 wird dynamisch unter "
         "LGPLv3 eingebunden, libssh und KDE IdleTime unter LGPL-2.1-or-later. Austausch und Debugging sind erlaubt. "
         "Tresorkern: keepass-rs (MIT), mit dokumentierten lokalen "
         "Korrekturen. Lizenztexte und Quellcode liegen neben der Installation "
         "unter share.",
         "Prerelease · Use synthetic data only. Independent security review is "
         "still pending.\n\nQt 6 is dynamically linked under LGPLv3; libssh and KDE IdleTime under LGPL-2.1-or-later. "
         "Replacement and debugging are permitted. Core: keepass-rs (MIT), "
         "with documented local patches. Notices and source are included in "
         "the installation's share directory."));
}
void VaultWindow::backup() {
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
}
void VaultWindow::history() {
  const auto id = selectedId();
  if (id.isEmpty() || editor || !isOpen)
    return;
  const auto revision = ++accessRevision;
  access->revoke();
  auto epoch = generation;
  channel.call({"history", id}, [this, id, epoch,
                                 revision](QStringList fields) {
    if (!isOpen || generation != epoch || selectedId() != id || editor ||
        revision != accessRevision) {
      for (auto &v : fields)
        wipe(v);
      if (isOpen && generation == epoch && revision == accessRevision &&
          !editor)
        refreshAccess();
      return;
    }
    auto *dialog = new QDialog(this);
    editor = dialog;
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    connect(dialog, &QDialog::finished, this, [this] {
      editor.clear();
      if (isOpen)
        refreshAccess();
    });
    dialog->setWindowTitle(tx("Versionsverlauf", "Version history"));
    dialog->resize(520, 440);
    auto *layout = new QVBoxLayout(dialog);
    auto *info = new QLabel(
        tx("Ältere Feldwerte wiederherstellen oder bewusst bereinigen. Bereits "
           "exportierte Sicherungen bleiben unverändert.",
           "Restore older field values or explicitly remove versions. "
           "Previously exported backups remain unchanged."));
    info->setWordWrap(true);
    layout->addWidget(info);
    auto *list = new QListWidget;
    layout->addWidget(list, 1);
    for (int i = 0; i < fields.size(); ++i)
      list->addItem(QString::number(i + 1) + "  ·  " + fields[i] + " UTC");
    auto *actions = new QHBoxLayout;
    actions->addWidget(button(
        tx("Ansehen…", "View…"),
        [this, id, list, dialog = QPointer<QDialog>(dialog), epoch] {
          const int index = list->currentRow();
          if (index < 0)
            return;
          channel.call(
              {"history-fields", id, QString::number(index)},
              [this, dialog, epoch](QStringList values) {
                if (!dialog || !isOpen || generation != epoch) {
                  for (auto &v : values)
                    wipe(v);
                  return;
                }
                auto *preview = new QDialog(dialog);
                preview->setAttribute(Qt::WA_DeleteOnClose);
                preview->setWindowTitle(
                    tx("Ältere Feldwerte", "Previous field values"));
                auto *outer = new QVBoxLayout(preview);
                auto *form = new QFormLayout;
                for (int i = 0; i + 1 < values.size(); i += 2) {
                  auto *label = new QLabel(values[i]);
                  label->setTextFormat(Qt::PlainText);
                  auto *field = vaultInput("historyField", true);
                  field->setReadOnly(true);
                  field->setMaxLength(16384);
                  field->setFocusPolicy(Qt::NoFocus);
                  field->setAttribute(Qt::WA_TransparentForMouseEvents);
                  field->setText(values[i + 1]);
                  form->addRow(label, field);
                }
                auto *body = new QWidget;
                body->setLayout(form);
                auto *scroll = new QScrollArea;
                scroll->setWidgetResizable(true);
                scroll->setWidget(body);
                outer->addWidget(scroll);
                outer->addWidget(button(
                    tx("10 Sekunden anzeigen", "Show for 10 seconds"),
                    [preview] {
                      for (auto *field : preview->findChildren<QLineEdit *>())
                        field->setEchoMode(QLineEdit::Normal);
                      QTimer::singleShot(10000, preview, [preview] {
                        for (auto *field : preview->findChildren<QLineEdit *>())
                          field->setEchoMode(QLineEdit::Password);
                      });
                    }));
                connect(preview, &QDialog::finished, preview, [preview] {
                  for (auto *field : preview->findChildren<QLineEdit *>())
                    field->setText({});
                });
                for (auto &v : values)
                  wipe(v);
                preview->resize(540, 480);
                preview->setModal(true);
                preview->show();
              });
        }));
    actions->addWidget(
        button(tx("Felder wiederherstellen", "Restore fields"), [this, id, list,
                                                                 dialog] {
          int i = list->currentRow();
          if (i < 0)
            return;
          channel.call({"restore-fields", id, QString::number(i)},
                       [this, dialog = QPointer<QDialog>(dialog)](QStringList) {
                         if (dialog)
                           dialog->accept();
                         refresh();
                       });
        }));
    actions->addWidget(button(tx("Bereinigen…", "Prune…"), [this, id, dialog] {
      bool ok = false;
      int keep = QInputDialog::getInt(
          dialog, tx("Versionen bereinigen", "Prune versions"),
          tx("Wie viele neueste Versionen behalten? Ältere werden entfernt.",
             "How many newest versions should remain? Older versions will be "
             "removed."),
          50, 0, 1000, 1, &ok);
      if (ok && isOpen)
        channel.call({"prune", id, QString::number(keep)},
                     [dialog = QPointer<QDialog>(dialog)](QStringList) {
                       if (dialog)
                         dialog->accept();
                     });
    }));
    layout->addLayout(actions);
    for (auto &v : fields)
      wipe(v);
    dialog->setModal(true);
    dialog->show();
  });
}
void VaultWindow::loadDetails() {
  if (!isOpen || !website || !username)
    return;
  if (channel.busy()) {
    detailTimer.start();
    return;
  }
  const auto id = selectedId();
  if (id.isEmpty())
    return;
  auto epoch = generation;
  channel.call({"summary", id}, [this, id, epoch](QStringList fields) {
    if (isOpen && generation == epoch && selectedId() == id &&
        fields.size() == 3 && website && username && accessButton) {
      website->setText(fields[0]);
      username->setText(fields[1]);
      visibilityId = id;
      accessButton->setChecked(fields[2] == "1");
      updateAccess();
    }
    for (auto &v : fields)
      wipe(v);
  });
}
void VaultWindow::refresh() {
  visibilityId.clear();
  updateCatalogue();
  refreshAccess();
  for (auto &v : rows)
    wipe(v);
  rows.clear();
  loadPage("0");
}
void VaultWindow::updateCatalogue() {
  const auto revision = ++catalogueRevision;
  catalogueEntries = {};
  QFile encrypted(root+"/vault.kdbx");
  QCryptographicHash digest(QCryptographicHash::Sha256);
  if (!isOpen || !encrypted.open(QIODevice::ReadOnly) || !digest.addData(&encrypted)) return;
  catalogueHash = digest.result();
  loadCataloguePage("0", revision);
}
void VaultWindow::loadCataloguePage(QString cursor, quint64 revision) {
  channel.call({"catalogue", cursor}, [this, revision](QStringList fields) {
    if (!isOpen || revision != catalogueRevision || fields.isEmpty()) {
      for (auto &field : fields) wipe(field);
      return;
    }
    const auto next = fields.takeFirst();
    for (int i=0; i+4<fields.size(); i+=5) {
      const auto url = QUrl(fields[i+4].isEmpty() ? fields[i+3] : fields[i+4], QUrl::StrictMode);
      QString origin;
      if (url.isValid() && url.scheme()=="https" && !url.host().isEmpty() && !url.authority().contains('@')) {
        QUrl target; target.setScheme("https"); target.setHost(url.host()); target.setPort(url.port());
        origin = target.toString(QUrl::FullyEncoded);
      }
      auto kind=fields[i+2];
      if (kind=="api") kind="token";
      if (kind.isEmpty()) kind="login";
      if (!QStringList{"login","token","note","recovery"}.contains(kind)) kind="other";
      catalogueEntries.append(QJsonObject{{"id",fields[i]},{"title",fields[i+1].left(200)},
                                         {"kind",kind},{"origin",origin}});
    }
    for (auto &field : fields) wipe(field);
    if (!next.isEmpty()) { loadCataloguePage(next, revision); return; }
    QFile encrypted(root+"/vault.kdbx");
    QCryptographicHash digest(QCryptographicHash::Sha256);
    if (!encrypted.open(QIODevice::ReadOnly) || !digest.addData(&encrypted)) return;
    if (digest.result() != catalogueHash) return;
    QSaveFile output(root+"/assistant-catalogue.json");
    output.setDirectWriteFallback(false);
    if (!output.open(QIODevice::WriteOnly)) return;
    output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    const auto data=QJsonDocument(QJsonObject{{"version",1},{"sha256",QString::fromLatin1(digest.result().toHex())},
      {"updated",QDateTime::currentDateTimeUtc().toString(Qt::ISODate)}, {"entries",catalogueEntries}}).toJson(QJsonDocument::Compact);
    if (output.write(data)!=data.size() || !output.commit()) {
      if (status) status->setText(tx("Eintragsverzeichnis konnte nicht aktualisiert werden.", "Could not update entry catalogue."));
    }
    catalogueEntries = {};
  });
}
void VaultWindow::loadPage(QString cursor) {
  auto epoch = generation;
  channel.call({"page", cursor}, [this, epoch](QStringList fields) {
    if (!isOpen || generation != epoch || fields.isEmpty()) {
      for (auto &v : fields)
        wipe(v);
      return;
    }
    const auto next = fields.takeFirst();
    rows.append(fields);
    if (!next.isEmpty()) {
      loadPage(next);
      return;
    }
    {
      QSignalBlocker block(navigation);
      while (navigation->count() > 5)
        delete navigation->takeItem(5);
      QSet<QString> collections;
      for (int i = 0; i + 5 < rows.size(); i += 6)
        if (!rows[i + 3].isEmpty() && rows[i + 5] != "1")
          collections.insert(rows[i + 3]);
      if (!collections.isEmpty()) {
        auto *header =
            new QListWidgetItem(tx("Sammlungen", "Collections"), navigation);
        header->setFlags(Qt::NoItemFlags);
        header->setSizeHint(QSize(170, 60));
        header->setText({});
        header->setData(Qt::AccessibleTextRole,
                        tx("Sammlungen", "Collections"));
        auto *section = new QWidget;
        section->setAttribute(Qt::WA_TransparentForMouseEvents);
        auto *layout = new QVBoxLayout(section);
        layout->setContentsMargins(14, 10, 16, 0);
        layout->setSpacing(12);
        layout->addWidget(rule());
        auto *caption = new QLabel(tx("Sammlungen", "Collections"));
        caption->setObjectName("muted");
        layout->addWidget(caption);
        navigation->setItemWidget(header, section);
      }
      auto sorted = collections.values();
      sorted.sort(Qt::CaseInsensitive);
      for (const auto &collection : sorted) {
        auto *item =
            new QListWidgetItem(glyph("folder"), collection, navigation);
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
      if (!found && category != "trash" && category != "recovery") {
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
    auto *item = new QListWidgetItem(
        glyph(rows[i + 2] == "token"  ? "code-context"
              : rows[i + 2] == "note" ? "document-edit"
                                      : "dialog-password"),
        rows[i + 1] + "\n" + kind(rows[i + 2]) +
            (rows[i + 3].isEmpty() ? QString() : " · " + rows[i + 3]),
        entries);
    item->setData(Qt::UserRole, rows[i]);
    item->setData(Qt::UserRole + 1, rows[i + 1]);
    item->setData(Qt::UserRole + 2,
                  kind(rows[i + 2]) + (rows[i + 3].isEmpty()
                                           ? QString()
                                           : " · " + rows[i + 3]));
    item->setSizeHint(QSize(250, 84));
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
  updateAccess();
  hideSecret();
  if (website)
    website->setText({});
  if (username)
    username->setText({});
  detailTimer.start();
  if (!heading)
    return;
  auto id = selectedId();
  auto i = rowIndex(id);
  heading->setText(i >= 0 ? rows.value(i + 1)
                          : tx("Noch kein Eintrag", "No entry selected"));
  if (auto *avatar = findChild<QLabel *>("avatar")) {
    const auto name = i >= 0 && rows.value(i + 2) == "token"  ? "code-context"
                      : i >= 0 && rows.value(i + 2) == "note" ? "document-edit"
                      : i >= 0 && rows.value(i + 2) == "recovery"
                          ? "view-barcode"
                          : "dialog-password";
    avatar->setProperty("glyph", name);
    avatar->setPixmap(glyph(name).pixmap(48, 48));
  }
  if (username)
    username->setEchoMode(i >= 0 && rows.value(i + 2) == "token"
                              ? QLineEdit::Password
                              : QLineEdit::Normal);
  subtitle->setText(
      i >= 0 ? kind(rows.value(i + 2)) + (rows.value(i + 3).isEmpty()
                                              ? QString()
                                              : " · " + rows.value(i + 3))
             : tx("Erstelle einen Zugang oder wähle einen Eintrag.",
                  "Create a credential or select an entry."));
}
void VaultWindow::hideSecret() {
  revealTimer.stop();
  if (secret) {
    auto old = secret->text();
    secret->setText({});
    wipe(old);
    secret->setEchoMode(QLineEdit::Password);
    secret->setText("••••••••••••••••••");
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
  ++catalogueRevision;
  catalogueEntries = {};
  if (passkeyBridge) { delete passkeyBridge; passkeyBridge.clear(); }
  if (autoSyncProcess)
    autoSyncProcess->kill();
  const bool wasOpen = isOpen;
  isOpen = false;
  visibilityId.clear();
  ++accessRevision;
  enabledEntries.clear();
  pendingProfiles.clear();
  pendingEntries.clear();
  if (access)
    access->revoke();
  const bool wasVisible = isVisible();
  hide();
  ++generation;
  detailTimer.stop();
  idle.stop();
  keepalive.stop();
  hideSecret();
  clearOwnClipboard();
  isOpen = false;
  visibilityId.clear();
  if (editor) {
    auto dialog = editor;
    editor.clear();
    dialog->reject();
    delete dialog;
  }
  for (auto &v : rows)
    wipe(v);
  rows.clear();
  category = "all";
  replacePage(lockedPage());
  channel.stop();
  if (wasVisible)
    show();
  if (wasOpen)
    emit retire();
}
void VaultWindow::screenLock(bool active) {
  if (active)
    lock();
}
void VaultWindow::suspend(bool active) {
  if (active)
    lock();
}
static bool belongsTo(const QWidget *widget, const QWidget *owner) {
  for (auto *parent = widget; parent; parent = parent->parentWidget())
    if (parent == owner)
      return true;
  return false;
}
bool VaultWindow::eventFilter(QObject *object, QEvent *event) {
  if (isOpen &&
      (event->type() == QEvent::MouseButtonPress ||
       event->type() == QEvent::KeyPress || event->type() == QEvent::Wheel)) {
    auto *widget = qobject_cast<QWidget *>(object);
    if (event->spontaneous() && widget && belongsTo(widget, this))
      sessionActivity();
  }
  auto *widget = qobject_cast<QWidget *>(object);
  const bool ours = widget && belongsTo(widget, this);
  auto *line = ours ? qobject_cast<QLineEdit *>(object) : nullptr;
  auto *notes = ours ? qobject_cast<QPlainTextEdit *>(object) : nullptr;
  if ((line || notes) && event->type() == QEvent::ContextMenu) {
    event->accept();
    return true;
  }
  if ((line || notes) && event->type() == QEvent::KeyPress) {
    auto *key = static_cast<QKeyEvent *>(event);
    if (key->matches(QKeySequence::Copy) || key->matches(QKeySequence::Cut)) {
      const bool cut = key->matches(QKeySequence::Cut);
      auto value =
          line ? line->selectedText() : notes->textCursor().selectedText();
      if (line && line->echoMode() != QLineEdit::Normal) {
        wipe(value);
        return true;
      }
      if (!value.isEmpty())
        copySecret(value);
      wipe(value);
      if (cut) {
        if (line && !line->isReadOnly())
          line->insert({});
        else if (notes && !notes->isReadOnly()) {
          auto c = notes->textCursor();
          c.removeSelectedText();
        }
      }
      return true;
    }
  }
  return QMainWindow::eventFilter(object, event);
}
void VaultWindow::edit(QStringList fields, bool createNew, bool fromChat) {
  ++accessRevision;
  if (!createNew)
    access->revoke();
  if (editor || !isOpen) {
    for (auto &v : fields)
      wipe(v);
    return;
  }
  const QString id = createNew || fields.isEmpty() ? QString() : selectedId();
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
  auto *hidden = new QCheckBox(tx("Für Lumen nicht freigeben", "Hide from Lumen"));
  hidden->setObjectName("editLumenHidden");
  hidden->setChecked(value("LumenHidden") == "1");
  form->addRow("", hidden);
  const auto connectionSettings = VaultConnection::settings(fields);
  auto *connector = new QComboBox;
  connector->setObjectName("editConnector");
  connector->addItem(tx("HTTPS-API", "HTTPS API"), "api");
  connector->addItem(tx("MCP über HTTPS", "MCP over HTTPS"), "mcp");
  connector->setCurrentIndex(
      qMax(0, connector->findData(connectionSettings["connector"].toString())));
  form->addRow(tx("Anbindung", "Connection"), connector);
  auto *auth = new QComboBox;
  auth->setObjectName("editAuth");
  auth->addItem(tx("Bearer-Token", "Bearer token"), "bearer");
  auth->addItem(tx("API-Key in einem Header", "API key in one header"),
                "api_key");
  auth->addItem(tx("Token-ID : Secret (Authorization: Token)",
                   "Token ID : secret (Authorization: Token)"),
                "token_pair");
  auth->addItem(tx("Token-ID und Secret in zwei Headern",
                   "Token ID and secret in two headers"),
                "headers");
  auth->setCurrentIndex(
      qMax(0, auth->findData(connectionSettings["auth"].toString())));
  form->addRow(tx("Anmeldung", "Authentication"), auth);
  QMap<QString, QLineEdit *> edits;
  const QList<QPair<QString, QString>> definitions{
      {"Title", tx("Name", "Name")},
      {"LumenCollection", tx("Sammlung", "Collection")},
      {"UserName", tx("Benutzername", "Username")},
      {"URL", tx("Website / SSH-Adresse", "Website / SSH address")},
      {"Password", tx("Passwort / Token-Secret", "Password / token secret")},
      {"LumenApiIdHeader", tx("Header für Token-ID", "Token ID header")},
      {"LumenApiSecretHeader", tx("Header für Secret", "Secret header")},
      {"LumenTags", tx("Tags", "Tags")},
      {"LumenExpires", tx("Ablaufdatum", "Expiry date")},
      {"LumenPermissions", tx("Berechtigungen (Notiz)", "Permissions (note)")}};
  for (const auto &definition : definitions) {
    auto *field =
        vaultInput("edit" + definition.first, definition.first == "Password" ||
                                             (definition.first == "UserName" &&
                                              type->currentData() == "token"));
    field->setText(value(definition.first));
    edits[definition.first] = field;
    form->addRow(definition.second, field);
  }
  if (type->currentData() == "token") {
    edits["URL"]->setText(connectionSettings["endpoint"].toString());
    if (!value("LumenApiTokenId").isEmpty())
      edits["UserName"]->setText(value("LumenApiTokenId"));
  }
  edits["LumenApiIdHeader"]->setText(
      connectionSettings["id_header"].toString());
  edits["LumenApiSecretHeader"]->setText(
      connectionSettings["secret_header"].toString());
  auto updateApiFields = [this, form, edits, type, connector, auth] {
    const bool token = type->currentData() == "token";
    for (auto *field : {connector, auth}) {
      field->setVisible(token);
      form->labelForField(field)->setVisible(token);
    }
    auto showField = [&](const QString &key, bool visible) {
      edits[key]->setVisible(visible);
      form->labelForField(edits[key])->setVisible(visible);
    };
    showField("LumenApiIdHeader", token && auth->currentData() == "headers");
    showField("LumenApiSecretHeader",
              token && (auth->currentData() == "headers" ||
                        auth->currentData() == "api_key"));
    const bool needsId =
        auth->currentData() == "token_pair" || auth->currentData() == "headers";
    showField("UserName", !token || needsId);
    edits["UserName"]->setEchoMode(token ? QLineEdit::Password
                                         : QLineEdit::Normal);
    qobject_cast<QLabel *>(form->labelForField(edits["UserName"]))
        ->setText(token ? QString::fromUtf8("Token-ID")
                        : tx("Benutzername", "Username"));
    qobject_cast<QLabel *>(form->labelForField(edits["URL"]))
        ->setText(token ? tx("Dienstadresse (HTTPS)", "Service address (HTTPS)")
                        : tx("Website / SSH-Adresse", "Website / SSH address"));
  };
  connect(type, &QComboBox::currentIndexChanged, dialog, updateApiFields);
  connect(auth, &QComboBox::currentIndexChanged, dialog, updateApiFields);
  updateApiFields();
  for (int i = 0; i + 1 < fields.size(); i += 2) {
    const auto &key = fields[i];
    if (edits.contains(key) || key == "Notes" || key.startsWith("Lumen"))
      continue;
    auto *field = vaultInput("customExisting", true);
    field->setMaxLength(16384);
    field->setText(fields[i + 1]);
    edits[key] = field;
    auto *caption = new QLabel(key);
    caption->setTextFormat(Qt::PlainText);
    form->addRow(caption, field);
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
  auto *notes = new PrivateNotes(value("Notes"));
  notes->setObjectName("editNotes");
  notes->setUndoRedoEnabled(false);
  notes->setMaximumHeight(105);
  notes->setInputMethodHints(Qt::ImhSensitiveData | Qt::ImhNoPredictiveText);
  form->addRow(tx("Notiz / Codes", "Note / codes"), notes);
  auto *customName = vaultInput("customName");
  auto *customValue = vaultInput("customValue", true);
  form->addRow(tx("Zusatzfeld: Name", "Custom field: name"), customName);
  form->addRow(tx("Zusatzfeld: Wert", "Custom field: value"), customValue);
  if (fromChat) {
    // Compact, editable review. Save is the only storage consent; no automatic
    // connection grant and no general-purpose metadata intake from callers.
    for (const auto &key : {"LumenCollection", "LumenTags", "LumenExpires", "LumenPermissions"}) {
      edits[key]->hide();
      form->labelForField(edits[key])->hide();
    }
    for (QWidget *widget : QList<QWidget *>{notes, customName, customValue, generator}) {
      widget->hide();
      if (auto *label = form->labelForField(widget)) label->hide();
    }
    auto *hide = new QTimer(dialog);
    hide->setSingleShot(true);
    hide->setInterval(10000);
    connect(hide, &QTimer::timeout, dialog, [edits, type] {
      edits["Password"]->setEchoMode(QLineEdit::Password);
      if (type->currentData() == "token")
        edits["UserName"]->setEchoMode(QLineEdit::Password);
    });
    auto *review = button(tx("Verdeckte Werte kurz anzeigen", "Briefly show hidden values"), [edits, hide] {
      edits["Password"]->setEchoMode(QLineEdit::Normal);
      edits["UserName"]->setEchoMode(QLineEdit::Normal);
      hide->start();
    });
    review->setObjectName("prefillReveal");
    form->addRow("", review);
  }
  auto *formWidget = new QWidget;
  formWidget->setLayout(form);
  auto *scroll = new QScrollArea;
  scroll->setWidgetResizable(true);
  scroll->setFrameShape(QFrame::NoFrame);
  scroll->setWidget(formWidget);
  scroll->setMinimumHeight(fromChat ? 250 : 400);
  layout->addWidget(scroll);
  dialog->resize(640, fromChat ? 560 : 750);
  auto *info = new QLabel(
      tx("Änderungen werden verschlüsselt gespeichert. Sperren verwirft offene "
         "Eingaben.",
         "Changes are saved encrypted. Locking discards unsaved edits."));
  info->setWordWrap(true);
  if (fromChat)
    info->setText(tx("Aus deiner Nachricht übernommen. Bitte prüfe die Felder. Erst mit Speichern wird ein neuer, verschlüsselter Eintrag angelegt.",
                     "Filled from your message. Please review the fields. Only Save creates a new encrypted entry."));
  info->setObjectName("muted");
  layout->addWidget(info);
  auto *buttons = new QHBoxLayout;
  buttons->addStretch();
  buttons->addWidget(
      button(tx("Abbrechen", "Cancel"), [dialog] { dialog->reject(); }));
  auto *save =
      button(tx("Speichern", "Save"), [this, dialog = QPointer<QDialog>(dialog),
                                       id, edits, type, notes, customName,
                                       customValue, info, connector, auth, hidden] {
        if (!dialog || dialog->property("saving").toBool())
          return;
        if (channel.busy()) {
          info->setText(
              tx("Der Tresor arbeitet noch. Bitte gleich nochmals speichern.",
                 "Vault is still working. Please save again in a moment."));
          return;
        }
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
                            "Notes",     notes->toPlainText(),
                            "LumenHidden", hidden->isChecked() ? "1" : "0"};
        for (auto it = edits.begin(); it != edits.end(); ++it)
          request << it.key() << it.value()->text();
        request << "LumenApiConnector" << connector->currentData().toString()
                << "LumenApiAuth" << auth->currentData().toString();
        if (type->currentData() == "token")
          request << "LumenApiBase" << edits["URL"]->text() << "LumenApiTokenId"
                  << edits["UserName"]->text();
        if (!customName->text().isEmpty()) {
          if (customName->text().size() > 100 ||
              edits.contains(customName->text()) ||
              customName->text().startsWith("Lumen") ||
              customName->text() == "Notes") {
            info->setText(
                tx("Anderen Feldnamen wählen.", "Choose another field name."));
            for (auto &v : request)
              wipe(v);
            return;
          }
          request << customName->text() << customValue->text();
        }
        dialog->setProperty("saving", true);
        info->setText(
            tx("Wird verschlüsselt gespeichert …", "Saving encrypted entry …"));
        if (auto *saveButton = dialog->findChild<QPushButton *>("save"))
          saveButton->setEnabled(false);
        channel.call(std::move(request), [this, dialog](QStringList reply) {
          if (dialog && !reply.isEmpty()) {
            dialog->setProperty("savedEntryId", reply[0]);
            dialog->accept();
          }
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
  connect(dialog, &QDialog::finished, this,
          [this, edits, notes, customName, customValue](int result) {
            editor.clear();
            if (result != QDialog::Accepted && isOpen)
              QTimer::singleShot(0, this, &VaultWindow::refreshAccess);
            for (auto *field : edits)
              field->setText({});
            notes->setPlainText({});
            customName->setText({});
            customValue->setText({});
          });
  dialog->setModal(true);
  dialog->show();
  edits["Title"]->setFocus();
}
void VaultWindow::stopAccessServer() { access->close(); }
bool VaultWindow::startAccessServer(const QString &runtime) {
  return access->listen(runtime);
}
// Availability is persisted only inside KDBX. Runtime profiles contain no
// credentials.
void VaultWindow::refreshAccess() {
  const auto revision = ++accessRevision;
  accessLoading = true;
  enabledEntries.clear();
  pendingProfiles.clear();
  pendingEntries.clear();
  access->revoke(true);
  if (isOpen && !editor)
    loadAccessPage("0", revision);
}
void VaultWindow::loadAccessPage(QString cursor, quint64 revision) {
  channel.call({"connections", cursor}, [this, revision](QStringList ids) {
    if (!isOpen || editor || revision != accessRevision || ids.isEmpty())
      return;
    const auto next = ids.takeFirst();
    for (const auto &id : ids)
      enabledEntries.insert(id);
    loadAccessEntries(std::move(ids), next, revision);
  });
}
void VaultWindow::loadAccessEntries(QStringList ids, QString cursor,
                                    quint64 revision) {
  if (!isOpen || editor || revision != accessRevision)
    return;
  if (ids.isEmpty()) {
    if (!cursor.isEmpty())
      loadAccessPage(cursor, revision);
    else {
      accessLoading = false;
      access->setConnections(pendingProfiles, pendingEntries);
      pendingProfiles.clear();
      pendingEntries.clear();
    }
    return;
  }
  const auto id = ids.takeFirst();
  channel.call({"edit", id},
               [this, id, ids, cursor, revision](QStringList fields) {
                 const auto kind = VaultConnection::value(fields, "LumenType");
                 const auto title = VaultConnection::value(fields, "Title");
                 const auto loginScheme = QUrl(VaultConnection::value(fields, "URL")).scheme();
                 const bool enabled = VaultConnection::value(fields, "LumenHidden") != "1";
                 const bool valid = kind == "token" &&
                     VaultConnection::value(fields, "LumenHidden") != "1" &&
                     VaultConnection::problem(fields).isEmpty();
                 const auto profile = VaultConnection::settings(fields);
                 for (auto &field : fields)
                   wipe(field);
                 if (!isOpen || editor || revision != accessRevision)
                   return;
                 if (enabled && (kind == "login" || kind == "token"))
                   pendingEntries.insert(id, {{"title", title}, {"kind", kind}, {"login_scheme", loginScheme}});
                 if (valid)
                   pendingProfiles.insert(id, profile);
                 loadAccessEntries(ids, cursor, revision);
               });
}
void VaultWindow::updateAccess() {
  if (!accessStatus || !accessButton)
    return;
  const bool hidden = accessButton->isChecked();
  accessStatus->setText(hidden
      ? tx("Für Lumen vollständig verborgen", "Completely hidden from Lumen")
      : tx("Für Lumen sichtbar · jede Verwendung bestätigen", "Visible to Lumen · confirm each use"));
  const int row = rowIndex(selectedId());
  accessButton->setEnabled(!accessLoading && row >= 0 && visibilityId == selectedId() &&
                           rows.value(row + 5) != "1");
}
void VaultWindow::shareConnection() {
  const auto id = selectedId();
  if (!isOpen || id.isEmpty() || editor || accessLoading || visibilityId != id)
    return;
  const auto hidden = accessButton->isChecked() ? "1" : "0";
  accessLoading = true;
  ++accessRevision;
  access->revoke();
  updateAccess();
  channel.call({"lumen-hidden", id, hidden}, [this](QStringList) { refresh(); });
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
    bg = "#222529";
    base = "#1a1c1f";
    hover = "#2a2e33";
    fg = "#eff1f3";
    border = "#393e45";
    muted = "#aab1ba";
    accent = "#d7dce2";
    on = "#1a1c1f";
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
  const auto radius = QString::number(name == "graphite" ? 10 : name == "atelier" ? 8 : name == "midnight" ? 6 : 16);
  auto palette = qApp->palette();
  palette.setColor(QPalette::Window, QColor(bg));
  palette.setColor(QPalette::Button, QColor(base));
  palette.setColor(QPalette::ButtonText, QColor(fg));
  palette.setColor(QPalette::WindowText, QColor(fg));
  palette.setColor(QPalette::Text, QColor(fg));
  palette.setColor(QPalette::Base, QColor(base));
  palette.setColor(QPalette::AlternateBase, QColor(hover));
  palette.setColor(QPalette::Highlight, QColor(accent));
  palette.setColor(QPalette::HighlightedText, QColor(on));
  palette.setColor(QPalette::PlaceholderText, QColor(muted));
  palette.setColor(QPalette::Mid, QColor(border));
  qApp->setPalette(palette);
  for (auto *label : findChildren<QLabel *>())
    if (label->property("buttonIcon").isValid()) {
      const int size = label->property("glyphSize").toInt();
      label->setPixmap(qvariant_cast<QIcon>(label->property("buttonIcon"))
                           .pixmap(size, size));
    } else if (label->property("glyph").isValid()) {
      const int size = label->property("glyphSize").toInt();
      label->setPixmap(
          glyph(label->property("glyph").toString()).pixmap(size, size));
    }
  qApp->setStyleSheet(
      QString(
          "QWidget{background:transparent;color:%4;font-size:14px;} "
          "QMainWindow,QDialog{background:%1;} "
          "QFrame#sidebar,QFrame#middle{border:0;border-right:1px solid %5;} "
          "QFrame#sidebar{background:%1;} QFrame#rule{background:%5;} "
          "QLabel#avatar{background:%3;border:1px solid "
          "%5;border-radius:51px;} "
          "QTabBar#vaultSections{background:transparent;} "
          "QTabBar#vaultSections::tab{background:%2;color:%6;border:1px solid "
          "%5;"
          "padding:10px 18px;} "
          "QTabBar#vaultSections::tab:first{border-top-left-radius:%9px;"
          "border-bottom-left-radius:%9px;} "
          "QTabBar#vaultSections::tab:last{border-top-right-radius:%9px;"
          "border-bottom-right-radius:%9px;border-left:0;} "
          "QTabBar#vaultSections::tab:selected{background:%7;color:%8;"
          "font-weight:600;} "
          "QTabBar#vaultSections::tab:hover{color:%4;} "
          "QPushButton#quiet{background:transparent;border:0;padding:6px;} "
          "QPushButton#settings{background:transparent;border:0;text-align:"
          "left;"
          "padding:10px 16px;} "
          "QMenu{background:%2;border:1px solid %5;padding:6px;} "
          "QMenu::item{padding:10px 18px;} "
          "QMenu::item:selected{background:%3;} "
          "QFrame#card{background:%2;border:1px solid "
          "%5;border-radius:%9px;} QLabel{background:transparent;} "
          "QLabel#brand{font-size:18px;font-weight:500;} "
          "QLabel#title{font-size:26px;font-weight:600;} "
          "QLabel#muted{color:%6;} QLabel#status{color:%7;} "
          "QLabel#caption{color:%6;font-size:12px;} "
          "QLabel#tagline{color:%6;font-size:12px;} "
          "QLineEdit#website{color:%7;} "
          "QLineEdit{lineedit-password-character:8226;} "
          "QPushButton{background:%2;border:1px solid "
          "%5;border-radius:%9px;padding:7px 14px;} "
          "QPushButton:hover{background:%3;border-color:%7;} "
          "QPushButton:focus{border:2px solid %7;} "
          "QPushButton#primary,QPushButton#save{background:"
          "%7;color:%8;border:0;font-weight:600;} "
          "QLineEdit,QPlainTextEdit,QComboBox{background:%2;border:1px "
          "solid %5;border-radius:%9px;padding:6px "
          "10px;selection-background-color:%7;selection-color:%8;} "
          "QLineEdit:focus,QPlainTextEdit:focus{border:1px solid %7;} "
          "QFrame#fieldRow{background:%2;border:1px solid "
          "%5;border-radius:%9px;} "
          "QFrame#fieldRow QLineEdit{background:transparent;border:0;} "
          "QPushButton[fieldAction=true]{background:transparent;border:0;"
          "border-left:1px solid %5;border-radius:6px;padding:8px;} "
          "QPushButton[fieldAction=true]:hover{background:%3;} "
          "QPushButton[fieldAction=true]:focus{border:1px solid %7;} "
          "QScrollArea#detailScroll{background:transparent;border:0;} "
          "QTreeWidget{background:%2;border:1px solid "
          "%5;border-radius:%9px;outline:0;} "
          "QTreeWidget::item{padding:10px;} "
          "QTreeWidget::item:selected{background:%3;color:%4;} "
          "QHeaderView::section{background:%2;color:%6;padding:10px;border:0;"
          "border-bottom:1px solid %5;} "
          "QListWidget{background:transparent;border:0;outline:0;} "
          "QListWidget::item{padding:8px 18px;border-radius:%9px;} "
          "QListWidget::item:selected{background:%3;color:%4;border-left:3px "
          "solid %7;} "
          "QListWidget::item:hover{background:%2;} "
          "QScrollBar:vertical{background:%2;width:8px;} "
          "QScrollBar::handle:vertical{background:%5;border-radius:4px;min-"
          "height:24px;} "
          "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{"
          "height:0;}")
          .arg(bg, base, hover, fg, border, muted, accent, on, radius));
}

void VaultWindow::setIdleMinutes(int minutes) {
  idleMinutes = (minutes == 5 || minutes == 15 || minutes == 30) ? minutes : 15;
  idle.setInterval(idleMinutes * 60000);
}
void VaultWindow::sessionActivity() {
  if (isOpen) idle.start();
}
void VaultWindow::closeEvent(QCloseEvent *event) {
  if (editor && editor->isVisible()) {
    event->ignore();
    editor->raise();
    return;
  }
  if (isOpen) {
    hideSecret();
    clearOwnClipboard();
    hide();
    event->ignore();
  } else {
    event->accept();
    emit quitRequested();
  }
}

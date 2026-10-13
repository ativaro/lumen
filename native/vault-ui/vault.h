// SPDX-License-Identifier: LicenseRef-Lumen-EULA
#pragma once
#include <QtDBus>
#include <QtWidgets>
#include <functional>

class VaultAccess;
class PasskeyBridge;
using Reply = std::function<void(QStringList)>;
QLineEdit *vaultInput(const QString &name, bool hidden = false);
void wipe(QString &text);
void wipe(QByteArray &text);
class Channel : public QObject {
  Q_OBJECT
public:
  explicit Channel(QString root, QObject *parent = nullptr);
  void call(QStringList fields, Reply callback);
  void stop();
  bool busy() const { return bool(pending); }
signals:
  void failed(QString code);

private:
  void read();
  QString root;
  QProcess child;
  QTimer deadline;
  QByteArray buffer;
  Reply pending;
  QList<QPair<QStringList, Reply>> queued;
  bool stopping = false;
};
class VaultWindow : public QMainWindow {
  Q_OBJECT
public:
  explicit VaultWindow(const QString &root);
  ~VaultWindow() override;
  QString tx(const char *de, const char *en) const;
  void copySecret(QString value);
  void clearOwnClipboard();
  bool unlocked() const { return isOpen; }
  int section() const;
  void showSection(int index);
  void stopAccessServer();
  bool startAccessServer(const QString &runtime);
signals:
  void backupsRequested();
  void retire();
  void quitRequested();
public slots:
  void lock();
  void screenLock(bool active);
  void suspend(bool active);

protected:
  bool eventFilter(QObject *object, QEvent *event) override;
  void closeEvent(QCloseEvent *event) override;

private:
  QWidget *header();
  void updateHeader();
  QLabel *headerIcon = nullptr, *headerState = nullptr;
  QPushButton *headerLock = nullptr;
  QWidget *lockedPage();
  QWidget *openPage();
  void replacePage(QWidget *page);
  void refresh();
  void updateCatalogue();
  void loadCataloguePage(QString cursor, quint64 revision);
  quint64 catalogueRevision = 0;
  QJsonArray catalogueEntries;
  QByteArray catalogueHash;
  void loadPage(QString cursor);
  void loadDetails();
  void history();
  void backup();
  void serverSync();
  void pollServerSync();
  QTimer autoSyncTimer;
  QPointer<QProcess> autoSyncProcess;
  void about();
  void passkey(bool enroll);
  void removePasskey();
  QJsonObject passkeyMetadata() const;
  QPointer<PasskeyBridge> passkeyBridge;
  QString kind(const QString &key) const;
  void select();
  void filter();
  void edit(QStringList fields = {}, bool createNew = false, bool fromChat = false);
  void shareConnection();
  void updateAccess();
  void refreshAccess();
  void loadAccessPage(QString cursor, quint64 revision);
  void loadAccessEntries(QStringList ids, QString cursor, quint64 revision);
  quint64 accessRevision = 0;
  bool accessLoading = false;
  QSet<QString> enabledEntries;
  QMap<QString, QJsonObject> pendingProfiles, pendingEntries;
  void theme();
  void hideSecret();
  void authorize(bool create, bool restore = false);
  QPushButton *button(const QString &text, std::function<void()> action,
                      QWidget *parent = nullptr);
  QString selectedId() const;
  int rowIndex(const QString &id) const;
  QString root;
  QStackedWidget *sections = nullptr;
  QPointer<QWidget> credentialPage;
  Channel channel;
  VaultAccess *access = nullptr;
  bool isOpen = false, english = false;
  QTimer idle, keepalive, revealTimer, clipboardTimer, themeTimer, detailTimer;
  void sessionActivity();
  void setIdleMinutes(int minutes);
  int idleMinutes = 15;
  QSystemTrayIcon *tray = nullptr;
  QAction *trayLock = nullptr;
  quint64 generation = 0;
  QString clipboardTag, currentTheme, category = "all";
  QStringList rows;
  QPointer<QLineEdit> master, confirm, search, secret, username, website;
  QPointer<QListWidget> entries, navigation;
  QPointer<QLabel> heading, subtitle, status, accessStatus;
  QPointer<QCheckBox> accessButton;
  QString visibilityId;
  QPointer<QDialog> editor;
  QPointer<QWidget> body;
};

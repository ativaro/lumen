// SPDX-License-Identifier: MIT
#pragma once
#include <QtDBus>
#include <QtWidgets>
#include <functional>

class BackupPage;
class VaultAccess;
using Reply = std::function<void(QStringList)>;
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
  void retire();
public slots:
  void lock();
  void screenLock(bool active);
  void suspend(bool active);

protected:
  bool eventFilter(QObject *object, QEvent *event) override;

private:
  QWidget *sectionTabs();
  QWidget *lockedPage();
  QWidget *openPage();
  void replacePage(QWidget *page);
  void refresh();
  void loadPage(QString cursor);
  void loadDetails();
  void history();
  void backup();
  void about();
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
  QMap<QString, QJsonObject> pendingProfiles;
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
  BackupPage *backups = nullptr;
  Channel channel;
  VaultAccess *access = nullptr;
  bool isOpen = false, english = false;
  QTimer idle, revealTimer, clipboardTimer, themeTimer, detailTimer;
  quint64 generation = 0;
  QString clipboardTag, currentTheme, category = "all";
  QStringList rows;
  QPointer<QLineEdit> master, confirm, search, secret, username, website;
  QPointer<QListWidget> entries, navigation;
  QPointer<QLabel> heading, subtitle, status, accessStatus;
  QPointer<QPushButton> accessButton;
  QPointer<QDialog> editor;
  QPointer<QWidget> body;
};

// SPDX-License-Identifier: MIT
#pragma once
#include <QtDBus>
#include <QtWidgets>
#include <functional>

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
public slots:
  void lock();
  void screenLock(bool active);
  void suspend(bool active);

protected:
  bool eventFilter(QObject *object, QEvent *event) override;

private:
  QWidget *lockedPage();
  QWidget *openPage();
  void replacePage(QWidget *page);
  void refresh();
  void select();
  void filter();
  void edit(QStringList fields = {});
  void theme();
  void hideSecret();
  void authorize(bool create, bool restore = false);
  QPushButton *button(const QString &text, std::function<void()> action,
                      QWidget *parent = nullptr);
  QString selectedId() const;
  int rowIndex(const QString &id) const;
  QString root;
  Channel channel;
  bool isOpen = false, english = false;
  QTimer idle, revealTimer, clipboardTimer, themeTimer;
  QString clipboardTag, currentTheme, category = "all";
  QStringList rows;
  QPointer<QLineEdit> master, confirm, search, secret;
  QPointer<QListWidget> entries, navigation;
  QPointer<QLabel> heading, subtitle, status;
  QPointer<QDialog> editor;
  QPointer<QWidget> body;
};

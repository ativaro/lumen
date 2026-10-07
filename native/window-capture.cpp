// Lumen selected-window transport. Uses KWin's documented D-Bus API.
// A dedicated executable keeps capture permission off general Python interpreters.
#include <QCoreApplication>
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusUnixFileDescriptor>
#include <QJsonDocument>
#include <QJsonObject>
#include <QUuid>
#include <cstdio>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/prctl.h>
#include <signal.h>

int main(int argc, char **argv)
{
    const auto parent = getppid();
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) return 2;
    QCoreApplication app(argc, argv);
    if (argc != 3 || QUuid(QString::fromUtf8(argv[1])).isNull()) return 2;
    // Inherit the validated Python lease. Validate it again at the executable
    // boundary so direct invocation cannot capture while Vault holds the lock.
    bool valid = false;
    const int lease = QString::fromUtf8(argv[2]).toInt(&valid);
    const auto runtime = qgetenv("XDG_RUNTIME_DIR");
    if (!valid || lease < 3 || !runtime.startsWith('/')) return 2;
    const int dir = open(runtime.constData(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat directory{}, expected{}, actual{};
    const bool safe = dir >= 0 && !fstat(dir, &directory) && directory.st_uid == getuid()
        && !(directory.st_mode & 0077)
        && !fstatat(dir, "lumen-vault-privacy.lock", &expected, AT_SYMLINK_NOFOLLOW)
        && !fstat(lease, &actual) && S_ISREG(actual.st_mode) && actual.st_uid == getuid()
        && !(actual.st_mode & 0077) && actual.st_nlink == 1
        && actual.st_ino == expected.st_ino && actual.st_dev == expected.st_dev;
    if (dir >= 0) close(dir);
    if (!safe || flock(lease, LOCK_EX | LOCK_NB)) return 2;
    auto call = QDBusMessage::createMethodCall("org.kde.KWin.ScreenShot2",
        "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2", "CaptureWindow");
    QVariantMap options{{"include-decoration", false}, {"include-shadow", false}, {"include-cursor", false}};
    call << QString::fromUtf8(argv[1]) << options
         << QVariant::fromValue(QDBusUnixFileDescriptor(STDOUT_FILENO));
    const auto reply = QDBusConnection::sessionBus().call(call, QDBus::Block, 5000);
    if (reply.type() == QDBusMessage::ErrorMessage || reply.arguments().size() != 1) {
        std::fprintf(stderr, "%s", qPrintable(reply.errorName()));
        return 1;
    }
    const auto meta = qdbus_cast<QVariantMap>(reply.arguments().first());
    const auto bytes = QJsonDocument(QJsonObject::fromVariantMap(meta)).toJson(QJsonDocument::Compact);
    std::fwrite(bytes.constData(), 1, bytes.size(), stderr);
    // KWin owns a duplicate of stdout until its asynchronous writer finishes.
    return 0;
}

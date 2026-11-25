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
#include <sys/prctl.h>
#include <signal.h>

int main(int argc, char **argv)
{
    const auto parent = getppid();
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != parent) return 2;
    QCoreApplication app(argc, argv);
    if (argc != 2 || QUuid(QString::fromUtf8(argv[1])).isNull()) return 2;
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

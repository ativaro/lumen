import QtQuick
import org.kde.kirigami as Kirigami
import QtQuick.Window

Image {
    id: icon
    property string name: ""
    property color color: Kirigami.Theme.textColor
    readonly property var paths: ({
        "notifications": "M6 9a6 6 0 0 1 12 0v5l2 3H4l2-3Z M9 20a3 3 0 0 0 6 0 M12 1v2",
        "notifications-disabled": "M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11",
        "view-fullscreen": "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5",
        "edit-undo": "M4 5v6h6M4 11a8 8 0 1 1 1 8",
        "system-file-manager": "M3 7V5h6l2 2h10v13H3Z",
        "system-search": "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
        "preferences-desktop-locale": "M3 6h12M9 3v3M5 6c0 7 8 10 8 10M13 6c0 7-8 10-8 10M14 21l4-10 4 10m-6-4h4",
        "accessories-text-editor": "M5 3h15v18H5Z M8 3v18M3 7h4m-4 5h4m-4 5h4M11 8h6m-6 4h6",
        "mail-unread": "M3 5h18v14H3Z M3 6l9 7 9-7",
        "document-save": "M4 3h16v18H4Z M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 10v4m-2-2h4",
        "application-pdf": "M5 3h9l5 5v13H5Z M14 3v5h5M8 12h8m-8 4h6",
        "view-calendar": "M3 5h18v16H3Z M7 3v4m10-4v4M3 10h18M7 14h2m3 0h2m3 0h1M7 17h2m3 0h2",
        "folder-development": "M3 7V5h6l2 2h10v13H3Z M9 11l-3 3 3 3m6-6 3 3-3 3",
        "media-playback-start": "M8 4l13 8-13 8Z M3 7v10",
        "folder": "M3 7V5h6l2 2h10v13H3Z",
        "search": "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
        "audio-input-microphone": "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0Z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3m-4 0h8",
        "configure": "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z",
        "adjustlevels": "M3 6h8m4 0h6M3 12h3m4 0h11M3 18h11m4 0h3 M11 3v6m-5 0v6m8 0v6",
        "view-refresh": "M20 8a8 8 0 1 0 0 8 M20 3v5h-5",
        "system-software-update": "M20 8a8 8 0 1 0 0 8 M20 3v5h-5 M12 7v10m-3-3 3 3 3-3",
        "computer": "M3 3h18v14H3Z M12 17v4m-5 0h10",
        "utilities-system-monitor": "M3 3h18v14H3Z M12 17v4m-5 0h10",
        "system-lock-screen": "M5 10h14v11H5Z M8 10V6a4 4 0 0 1 8 0v4 M12 14v3",
        "network-wired": "M4 3h16v12H4Z M12 15v6m-7 0h14M8 7h8",
        "audio-volume-high": "M3 9h4l5-4v14l-5-4H3Z M16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14",
        "audio-volume-muted": "M3 9h4l5-4v14l-5-4H3Z M17 9l5 6m0-6-5 6",
        "brightness-high": "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10 M12 1v2m0 18v2M1 12h2m18 0h2M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2",
        "moon": "M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11",
        "view-task": "M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01",
        "document-open": "M3 7v14h14M10 3h11v11M21 3 9 15",
        "check": "m5 12 4 4L19 6",
        "window-close": "m6 6 12 12M18 6 6 18",
        "chevron": "m9 5 7 7-7 7",
        "arrow-up": "m5 15 7-7 7 7",
        "arrow-down": "m5 9 7 7 7-7",
        "dialog-error": "M12 8v5m0 4h.01 M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20",
        "dialog-question": "M9 8a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 4h.01 M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20"
    })
    source: "data:image/svg+xml;utf8," + encodeURIComponent(name === "lumen"
        ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="' + Kirigami.Theme.highlightColor + '"><ellipse cx="12" cy="5" rx="2.5" ry="4"/><ellipse cx="12" cy="19" rx="2.5" ry="4"/><ellipse cx="5" cy="12" rx="4" ry="2.5"/><ellipse cx="19" cy="12" rx="4" ry="2.5"/><g transform="rotate(45 12 12)" opacity=".7"><ellipse cx="12" cy="5" rx="2.5" ry="4"/><ellipse cx="12" cy="19" rx="2.5" ry="4"/><ellipse cx="5" cy="12" rx="4" ry="2.5"/><ellipse cx="19" cy="12" rx="4" ry="2.5"/></g></g></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="none" stroke="' + color + '" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" d="' + (paths[name] || paths["view-task"]) + '"/></svg>')
    sourceSize.width: Math.ceil(width * Screen.devicePixelRatio)
    sourceSize.height: Math.ceil(height * Screen.devicePixelRatio)
    fillMode: Image.PreserveAspectFit
    smooth: true
}

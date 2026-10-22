import QtQuick
import QtTest
import "../appmenu/contents/ui" as Lumen

TestCase {
    name: "WindowMenuState"
    ListModel { id: windows }
    Lumen.WindowMenuState { id: state; windowModel: windows }
    function init() {
        state.holdActiveWindow = false;
        windows.clear();
        windows.append({IsActive: true, IsMaximized: false, IsFullScreen: false,
            AppName: "Lumen Test A", ApplicationMenuServiceName: "org.lumen.TestA", ApplicationMenuObjectPath: "/Menu"});
        windows.append({IsActive: false, IsMaximized: true, IsFullScreen: false,
            AppName: "Lumen Test B", ApplicationMenuServiceName: "org.lumen.TestB", ApplicationMenuObjectPath: "/Menu"});
        tryCompare(state, "appName", "Lumen Test A");
    }
    function test_maximize_restore_and_fullscreen() {
        compare(state.maximized, false);
        windows.setProperty(0, "IsMaximized", true);
        tryCompare(state, "maximized", true);
        windows.setProperty(0, "IsFullScreen", true);
        tryCompare(state, "fullScreen", true);
        windows.setProperty(0, "IsFullScreen", false);
        windows.setProperty(0, "IsMaximized", false);
        tryCompare(state, "fullScreen", false);
        compare(state.maximized, false);
    }
    function test_switch_and_close_active_window() {
        windows.setProperty(0, "IsActive", false);
        windows.setProperty(1, "IsActive", true);
        tryCompare(state, "appName", "Lumen Test B");
        compare(state.maximized, true);
        windows.remove(1);
        tryCompare(state, "hasMenu", false);
        compare(state.appName, "");
    }
    function test_missing_or_removed_menu() {
        compare(state.hasMenu, true);
        windows.setProperty(0, "ApplicationMenuObjectPath", "");
        tryCompare(state, "hasMenu", false);
        windows.setProperty(0, "ApplicationMenuObjectPath", "/Menu");
        tryCompare(state, "hasMenu", true);
        windows.setProperty(0, "ApplicationMenuServiceName", "");
        tryCompare(state, "hasMenu", false);
    }
    function test_context_title_encoding_preserves_unicode_without_shell_text() {
        const value = {title:"Überblick – Workshop",app:"Chromium"};
        const encoded = Qt.btoa(JSON.stringify(value));
        verify(/^[A-Za-z0-9+/=]+$/.test(encoded));
        compare(Qt.atob(encoded),JSON.stringify(value));
    }
    function test_panel_focus_keeps_menu_until_popup_closes() {
        state.holdActiveWindow = true;
        windows.setProperty(0, "IsActive", false);
        windows.setProperty(1, "IsActive", true);
        compare(state.appName, "Lumen Test A");
        state.holdActiveWindow = false;
        tryCompare(state, "appName", "Lumen Test B");
    }
}

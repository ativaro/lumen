"""Retired local Notes sync hooks for older native window callers."""


def configure(window):
    return None


def synchronize(window):
    return None


def install(window):
    # Existing ToolsWissen callers must not create a timer or expose a local writer.
    return None

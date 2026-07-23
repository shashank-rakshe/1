import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from PySide6.QtWidgets import QApplication, QMessageBox

# The packaged .exe runs with no console window (see dcad.spec's
# console=False), so an uncaught exception would otherwise just vanish --
# the app closes with no visible error at all. Everything below exists so
# a crash is always visible somewhere: a log file next to a working
# directory the app can always write to, and a message box if the Qt event
# loop is far enough along to show one.
_LOG_PATH = Path.home() / ".dcad" / "crash.log"


def _log_crash(exc_type, exc_value, exc_tb) -> str:
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_PATH.write_text(text)
    except OSError:
        pass  # showing the message box below still beats a silent exit
    return text


def _excepthook(exc_type, exc_value, exc_tb):
    text = _log_crash(exc_type, exc_value, exc_tb)
    app = QApplication.instance()
    if app is not None:
        QMessageBox.critical(None, "dcad — unexpected error", f"{text}\n\nAlso saved to {_LOG_PATH}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main():
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except Exception:
        _excepthook(*sys.exc_info())
        sys.exit(1)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        from dcad.ui.main_window import MainWindow
    except Exception:
        # A failure this early (e.g. a missing native OCCT/Qt DLL in a
        # packaged build) happens before QApplication even exists, so
        # there's no message box to show yet -- write the log and print,
        # in case a console *is* attached (e.g. running from a dev venv).
        _log_crash(*sys.exc_info())
        traceback.print_exc()
        sys.exit(1)
    main()

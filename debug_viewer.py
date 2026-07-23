# Diagnostic script -- NOT part of the app. Isolates just the 3D-viewer
# window binding (the part known to differ between Linux and Windows) with
# a print() before and after every step, so we can see exactly which line
# it fails or hangs on. Run with:
#   python debug_viewer.py
# from an activated venv, in the project root (same place you run main.py).

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

print("1. importing Qt...", flush=True)
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt

print("2. importing the OCCT viewer wrapper...", flush=True)
from dcad.viewport.occt_viewer import OcctViewer

print("3. creating QApplication...", flush=True)
app = QApplication(sys.argv)

print("4. creating a plain native-window widget (same setup as the real app)...", flush=True)
widget = QWidget()
widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
widget.setAttribute(Qt.WidgetAttribute.WA_PaintOnScreen, True)
widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
widget.resize(800, 600)
widget.setWindowTitle("debug_viewer")

print("5. showing the widget...", flush=True)
widget.show()

print("6. creating OcctViewer() (Aspect_DisplayConnection, OpenGl_GraphicDriver, V3d_Viewer, AIS_InteractiveContext)...", flush=True)
viewer = OcctViewer()

print("7. OcctViewer() created OK. Getting the widget's native window handle...", flush=True)
window_id = int(widget.winId())
print(f"   window_id = {window_id}", flush=True)

print("8. calling bind_window() -- this is the platform-specific step (WNT_Window on Windows)...", flush=True)
viewer.bind_window(window_id, widget.width(), widget.height())

print("9. bind_window() returned OK. Calling fit_all() and redraw()...", flush=True)
viewer.fit_all()
viewer.redraw()

print("10. everything above succeeded! Starting the Qt event loop -- you should see an empty gray 3D viewport window titled 'debug_viewer'. Close it to end this script.", flush=True)
sys.exit(app.exec())

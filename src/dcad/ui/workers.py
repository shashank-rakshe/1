"""Background worker threads for operations that shouldn't block the UI
thread -- chiefly importing large STEP files, where reading + tessellating
a big assembly can take long enough to freeze a synchronous call."""

from PySide6.QtCore import QThread, Signal

from dcad.kernel import io_step
from dcad.viewport.occt_viewer import tessellate


class StepImportWorker(QThread):
    """Reads a STEP file and tessellates every root shape off the UI
    thread, so a big structural model doesn't freeze the app while it
    loads (the same reason Mayo and other production viewers do this
    off-thread rather than blocking on file I/O + meshing)."""

    succeeded = Signal(list)  # list[TopoDS_Shape]
    failed = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        try:
            shapes = io_step.import_step_multi(self._path)
            for shape in shapes:
                tessellate(shape)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(shapes)

"""Headless (Xvfb) smoke test: boot the real app, exercise primitives/boolean/
pull/STEP through the actual UI code paths, grab a screenshot, then exit."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from dcad.ui.main_window import MainWindow

SCREENSHOT_PATH = Path(__file__).parent.parent / "scratch_screenshot.png"
errors = []


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    def step1():
        try:
            window.add_box()
            window.add_cylinder()
            window.add_sphere()
            window.viewport.fit_all()
        except Exception as exc:
            errors.append(("primitives", exc))
        QTimer.singleShot(300, step2)

    def step2():
        try:
            ids = [o.id for o in window.document.objects]
            assert len(ids) == 3, f"expected 3 objects, got {len(ids)}"
            for shape_id in ids[:2]:
                ais = window.viewport.viewer.ais_for(shape_id)
                window.viewport.viewer.context.AddOrRemoveSelected(ais, True)
            pair = window._selected_pair()
            assert pair is not None, "expected a valid selected pair"
            window.do_union()
            assert len(window.document.objects) == 2, "union should merge two objects into one"
        except Exception as exc:
            errors.append(("boolean", exc))
        QTimer.singleShot(300, step3)

    def step3():
        try:
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS

            obj = window.document.objects[0]
            explorer = TopExp_Explorer(obj.shape, TopAbs_FACE)
            face = TopoDS.Face_s(explorer.Current())
            window.pull_action.setChecked(True)
            window._on_picked_test = True
            from dcad.kernel import direct_edit
            new_shape = direct_edit.pull_face(obj.shape, face, 0.5)
            window.document.replace_shape(obj, new_shape)
            window.viewport.viewer.redisplay_shape(obj.id, new_shape)
            window.pull_action.setChecked(False)
        except Exception as exc:
            errors.append(("pull", exc))
        QTimer.singleShot(300, step4)

    def step4():
        try:
            out = Path(__file__).parent.parent / "scratch_export.step"
            from dcad.kernel import io_step
            io_step.export_step([o.shape for o in window.document.objects], str(out))
            assert out.exists()
            reloaded = io_step.import_step(str(out))
            assert reloaded is not None
        except Exception as exc:
            errors.append(("step_io", exc))
        QTimer.singleShot(300, step5)

    def step5():
        try:
            pixmap = window.grab()
            pixmap.save(str(SCREENSHOT_PATH))
        except Exception as exc:
            errors.append(("screenshot", exc))
        import os
        if os.environ.get("SMOKE_KEEP_OPEN"):
            QTimer.singleShot(int(os.environ.get("SMOKE_HOLD_MS", "4000")), app.quit)
        else:
            app.quit()

    QTimer.singleShot(500, step1)
    app.exec()

    if errors:
        for stage, exc in errors:
            print(f"[FAIL] {stage}: {exc!r}")
        sys.exit(1)
    print("[OK] all smoke steps passed")


if __name__ == "__main__":
    run()

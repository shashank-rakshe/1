"""Headless (Xvfb) smoke test: boot the real app and drive it through the
actual UI methods (primitives, boolean, pull/push, fillet/chamfer, move/
rotate/copy, undo/redo, STEP + project I/O), grab a screenshot, then exit.

Modal QInputDialog prompts are monkeypatched to return fixed values so the
real do_move/do_rotate/do_copy/_apply_edge_op code paths run end-to-end
without blocking on user input.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication, QInputDialog
from PySide6.QtCore import QTimer

from dcad.ui.main_window import MainWindow

SCREENSHOT_PATH = Path(__file__).parent.parent / "scratch_screenshot.png"
PROJECT_PATH = Path(__file__).parent.parent / "scratch_project.dcadproj"
errors = []


def select_by_ids(window, ids):
    window.viewport.clear_selection()
    for shape_id in ids:
        ais = window.viewport.viewer.ais_for(shape_id)
        window.viewport.viewer.context.AddOrRemoveSelected(ais, True)


def by_name(window, name):
    return next(o for o in window.document.objects if o.name == name)


def first_face_of_type(shape, planar: bool):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        is_planar = BRepAdaptor_Surface(face, True).GetType() == GeomAbs_Plane
        if is_planar == planar:
            return face
        explorer.Next()
    raise AssertionError(f"no {'planar' if planar else 'non-planar'} face found")


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    def step_primitives():
        try:
            window.add_box()
            window.add_cylinder()
            window.add_sphere()
            window.viewport.fit_all()
            assert len(window.document.objects) == 3
        except Exception as exc:
            errors.append(("primitives", exc))
        QTimer.singleShot(200, step_boolean)

    def step_boolean():
        try:
            box = by_name(window, "Solid1")
            cyl = by_name(window, "Solid2")
            select_by_ids(window, [box.id, cyl.id])
            assert window._selected_pair() is not None
            window.do_union()
            assert len(window.document.objects) == 2
        except Exception as exc:
            errors.append(("boolean", exc))
        QTimer.singleShot(200, step_pull)

    def step_pull():
        try:
            from dcad.kernel import direct_edit

            sphere = by_name(window, "Solid3")
            curved_face = first_face_of_type(sphere.shape, planar=False)
            try:
                direct_edit.pull_face(sphere.shape, curved_face, 0.5)
                raise AssertionError("pulling a curved face should have raised ValueError")
            except ValueError:
                pass  # expected: pull_face rejects non-planar faces

            union_obj = by_name(window, "UnionResult")
            planar_face = first_face_of_type(union_obj.shape, planar=True)
            with patch.object(QInputDialog, "getDouble", return_value=(0.5, True)):
                window._apply_pull(union_obj, planar_face)
        except Exception as exc:
            errors.append(("pull", exc))
        QTimer.singleShot(200, step_fillet_chamfer)

    def step_fillet_chamfer():
        try:
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS
            from dcad.kernel import primitives

            # Fresh, simple primitives: filleting/chamfering right next to a
            # prior blend on compounded geometry is a much harder case for
            # OCCT's algorithms, and isn't what's under test here.
            fillet_obj = window._add_to_scene(primitives.make_box(4, 4, 4), name="FilletTest")
            explorer = TopExp_Explorer(fillet_obj.shape, TopAbs_EDGE)
            edge = TopoDS.Edge_s(explorer.Current())
            with patch.object(QInputDialog, "getDouble", return_value=(0.5, True)):
                window._apply_edge_op(fillet_obj, edge, "fillet")

            chamfer_obj = window._add_to_scene(primitives.make_box(4, 4, 4), name="ChamferTest")
            explorer2 = TopExp_Explorer(chamfer_obj.shape, TopAbs_EDGE)
            edge2 = TopoDS.Edge_s(explorer2.Current())
            with patch.object(QInputDialog, "getDouble", return_value=(0.5, True)):
                window._apply_edge_op(chamfer_obj, edge2, "chamfer")
        except Exception as exc:
            errors.append(("fillet_chamfer", exc))
        QTimer.singleShot(200, step_sketch)

    def step_sketch():
        try:
            count_before = len(window.document.objects)
            with patch.object(QInputDialog, "getText", return_value=("0, 0, 2, 3", True)), \
                 patch.object(QInputDialog, "getDouble", return_value=(4.0, True)):
                window.do_sketch_rect_extrude()
            assert len(window.document.objects) == count_before + 1

            with patch.object(QInputDialog, "getText", return_value=("0, 0, 1", True)), \
                 patch.object(QInputDialog, "getDouble", return_value=(5.0, True)):
                window.do_sketch_circle_extrude()
            assert len(window.document.objects) == count_before + 2

            with patch.object(QInputDialog, "getText", return_value=("1, 0, 2, 3", True)), \
                 patch.object(QInputDialog, "getDouble", return_value=(360.0, True)):
                window.do_sketch_revolve()
            assert len(window.document.objects) == count_before + 3
        except Exception as exc:
            errors.append(("sketch", exc))
        QTimer.singleShot(200, step_transform)

    def step_transform():
        try:
            sphere = by_name(window, "Solid3")
            select_by_ids(window, [sphere.id])
            with patch.object(QInputDialog, "getText", return_value=("5, 0, 0", True)):
                window.do_move()

            sphere = by_name(window, "Solid3")
            select_by_ids(window, [sphere.id])
            with patch.object(QInputDialog, "getDouble", return_value=(30.0, True)):
                window.do_rotate()

            sphere = by_name(window, "Solid3")
            count_before = len(window.document.objects)
            select_by_ids(window, [sphere.id])
            with patch.object(QInputDialog, "getText", return_value=("3, 0, 0", True)):
                window.do_copy()
            assert len(window.document.objects) == count_before + 1, "copy should add a new object"
        except Exception as exc:
            errors.append(("transform", exc))
        QTimer.singleShot(200, step_undo_redo)

    def step_undo_redo():
        try:
            count_before = len(window.document.objects)
            window.undo()
            assert len(window.document.objects) == count_before - 1, "undo should remove the copy"
            window.redo()
            assert len(window.document.objects) == count_before, "redo should restore the copy"
        except Exception as exc:
            errors.append(("undo_redo", exc))
        QTimer.singleShot(200, step_project_io)

    def step_project_io():
        try:
            from dcad.kernel import project_io

            project_io.save_project(window.document, str(PROJECT_PATH))
            assert PROJECT_PATH.exists()
            reloaded = project_io.load_project(str(PROJECT_PATH))
            assert len(reloaded.objects) == len(window.document.objects)
        except Exception as exc:
            errors.append(("project_io", exc))
        QTimer.singleShot(200, step_step_io)

    def step_step_io():
        try:
            out = Path(__file__).parent.parent / "scratch_export.step"
            from dcad.kernel import io_step

            io_step.export_step([o.shape for o in window.document.objects], str(out))
            assert out.exists()
            reloaded = io_step.import_step(str(out))
            assert reloaded is not None
        except Exception as exc:
            errors.append(("step_io", exc))
        QTimer.singleShot(200, step_screenshot)

    def step_screenshot():
        try:
            window.viewport.fit_all()
            pixmap = window.grab()
            pixmap.save(str(SCREENSHOT_PATH))
        except Exception as exc:
            errors.append(("screenshot", exc))
        import os

        if os.environ.get("SMOKE_KEEP_OPEN"):
            QTimer.singleShot(int(os.environ.get("SMOKE_HOLD_MS", "4000")), app.quit)
        else:
            app.quit()

    QTimer.singleShot(500, step_primitives)
    app.exec()

    if errors:
        for stage, exc in errors:
            print(f"[FAIL] {stage}: {exc!r}")
        sys.exit(1)
    print("[OK] all smoke steps passed")


if __name__ == "__main__":
    run()

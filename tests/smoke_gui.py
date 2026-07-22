"""Headless (Xvfb) smoke test: boot the real app and drive it through the
actual UI methods (primitives, boolean, pull/push, fillet/chamfer, move/
rotate/copy, undo/redo, STEP + project I/O), grab a screenshot, then exit.

Modal QInputDialog prompts are monkeypatched to return fixed values so the
real do_move/do_rotate/do_copy/_apply_edge_op code paths run end-to-end
without blocking on user input.
"""

import math
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication, QInputDialog
from PySide6.QtCore import QTimer, QPoint
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

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
        QTimer.singleShot(200, step_interactive_sketch)

    def step_interactive_sketch():
        try:
            count_before = len(window.document.objects)

            # Extrude session: rectangle, then circle, then a line-drawn
            # triangle (closed via double-click), all on the XY plane.
            window.sketch_extrude_action.setChecked(True)
            assert window.interactive_sketch_active
            assert window.interactive_sketch_finish_mode == "extrude"

            window._on_sketch_hover(2, 3, 0)  # live preview path, before any click
            window._on_sketch_clicked(0, 0, 0)
            window._on_sketch_hover(1, 1, 0)
            window._on_sketch_clicked(2, 3, 0)
            assert len(window.interactive_sketch_profiles) == 1

            window.sketch_entity_actions["circle"].setChecked(True)
            window._on_sketch_clicked(5, 5, 0)
            window._on_sketch_hover(6, 5, 0)
            window._on_sketch_clicked(6, 5, 0)
            assert len(window.interactive_sketch_profiles) == 2

            window.sketch_entity_actions["line"].setChecked(True)
            window._on_sketch_clicked(0, 0, 0)
            window._on_sketch_clicked(4, 0, 0)
            window._on_sketch_hover(4, 3, 0)
            window._on_sketch_clicked(4, 3, 0)
            window._on_sketch_finish_entity()
            assert len(window.interactive_sketch_profiles) == 3

            with patch.object(QInputDialog, "getDouble", return_value=(2.0, True)):
                window.finish_interactive_sketch()
            assert not window.interactive_sketch_active, "Finish Sketch should exit sketch mode"
            assert len(window.document.objects) == count_before + 3, "3 profiles -> 3 new solids"

            # Revolve session: a ring rectangle on the XZ plane.
            count_before = len(window.document.objects)
            window.sketch_revolve_action.setChecked(True)
            assert window.interactive_sketch_finish_mode == "revolve"
            window.sketch_entity_actions["rect"].setChecked(True)
            window._on_sketch_clicked(1, 0, 0)
            window._on_sketch_clicked(2, 0, 3)
            assert len(window.interactive_sketch_profiles) == 1

            with patch.object(QInputDialog, "getDouble", return_value=(360.0, True)):
                window.finish_interactive_sketch()
            assert len(window.document.objects) == count_before + 1

            # Cancel should discard without adding anything.
            count_before = len(window.document.objects)
            window.sketch_extrude_action.setChecked(True)
            window._on_sketch_clicked(10, 10, 0)
            window._on_sketch_clicked(12, 12, 0)
            assert len(window.interactive_sketch_profiles) == 1
            window.cancel_interactive_sketch()
            assert not window.interactive_sketch_active
            assert len(window.document.objects) == count_before, "Cancel Sketch must not add solids"
        except Exception as exc:
            errors.append(("interactive_sketch", exc))
        QTimer.singleShot(200, step_real_mouse_sketch)

    def step_real_mouse_sketch():
        # Drives actual synthesized QMouseEvents through the widget's real
        # event handlers (mousePressEvent/mouseMoveEvent/mouseReleaseEvent),
        # not direct handler calls -- end-to-end proof the pixel-click ->
        # screen_to_plane_point -> profile -> extrude pipeline works.
        try:
            count_before = len(window.document.objects)
            window.sketch_extrude_action.setChecked(True)
            window.sketch_entity_actions["rect"].setChecked(True)

            vp = window.viewport
            p1 = QPoint(vp.width() // 2 - 60, vp.height() // 2 - 40)
            p2 = QPoint(vp.width() // 2 + 60, vp.height() // 2 + 40)
            QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=p1)
            QTest.mouseMove(vp, pos=p2)
            QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=p2)
            assert len(window.interactive_sketch_profiles) == 1, "two real mouse clicks should finalize one rectangle profile"

            with patch.object(QInputDialog, "getDouble", return_value=(3.0, True)):
                window.finish_interactive_sketch()
            assert len(window.document.objects) == count_before + 1, "real-mouse-drawn sketch should extrude into a new solid"
        except Exception as exc:
            errors.append(("real_mouse_sketch", exc))
        QTimer.singleShot(200, step_measure)

    def step_measure():
        try:
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS

            obj_a = by_name(window, "FilletTest")
            obj_b = by_name(window, "ChamferTest")
            face_a = TopoDS.Face_s(TopExp_Explorer(obj_a.shape, TopAbs_FACE).Current())
            face_b = TopoDS.Face_s(TopExp_Explorer(obj_b.shape, TopAbs_FACE).Current())

            window._tool_actions["measure"].setChecked(True)
            assert window.active_tool == "measure"
            window._on_picked(face_a, obj_a.id)
            assert len(window.measure_picks) == 1, "first face pick should be buffered, not yet resolved"
            window._on_picked(face_b, obj_b.id)
            assert len(window.measure_picks) == 0, "second pick should resolve the distance and reset"
            assert "distance" in window.statusBar().currentMessage().lower()

            window._tool_actions["measure"].setChecked(False)
            assert window.active_tool == "select"
        except Exception as exc:
            errors.append(("measure", exc))
        QTimer.singleShot(200, step_surface_workflow)

    def step_surface_workflow():
        # SpaceClaim behavior: closing a sketch makes a flat Surface (zero
        # volume), not a solid. Pull (or Revolve) then thickens/spins it
        # into a real solid. Verify both paths end-to-end.
        try:
            from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID

            def volume_of(shape):
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps

                props = GProp_GProps()
                BRepGProp.VolumeProperties_s(shape, props)
                return props.Mass()

            # -- Pull path: circle sketch on the Extrude plane --
            window.sketch_extrude_action.setChecked(True)
            window.sketch_entity_actions["circle"].setChecked(True)
            window._on_sketch_clicked(20, 20, 0)
            window._on_sketch_clicked(21, 20, 0)  # radius 1
            assert len(window.interactive_sketch_profiles) == 1
            window.finish_interactive_sketch()

            surface = by_name(window, "Surface")
            assert surface.shape.ShapeType() == TopAbs_FACE, "Close Sketch should produce a flat Surface, not a solid"
            assert math.isclose(volume_of(surface.shape), 0.0, abs_tol=1e-9)

            select_by_ids(window, [surface.id])
            window._tool_actions["pull"].setChecked(True)
            with patch.object(QInputDialog, "getDouble", return_value=(3.0, True)):
                window._apply_pull(surface, surface.shape)
            window._tool_actions["pull"].setChecked(False)

            thickened = window.document.get(surface.id)
            assert thickened.shape.ShapeType() == TopAbs_SOLID, "Pull on a Surface should thicken it into a solid"
            assert volume_of(thickened.shape) > 0

            # -- Revolve path: rectangle sketch on the Revolve plane --
            window.sketch_revolve_action.setChecked(True)
            window.sketch_entity_actions["rect"].setChecked(True)
            window._on_sketch_clicked(1, 0, 0)
            window._on_sketch_clicked(2, 0, 3)
            assert len(window.interactive_sketch_profiles) == 1
            window.finish_interactive_sketch()

            surfaces = [o for o in window.document.objects if o.name == "Surface"]
            revolve_surface = surfaces[-1]
            assert revolve_surface.shape.ShapeType() == TopAbs_FACE

            select_by_ids(window, [revolve_surface.id])
            with patch.object(QInputDialog, "getDouble", return_value=(360.0, True)):
                window.do_revolve_surface()
            revolved = window.document.get(revolve_surface.id)
            assert revolved.shape.ShapeType() == TopAbs_SOLID, "Revolve on a Surface should spin it into a solid"
            assert volume_of(revolved.shape) > 0
        except Exception as exc:
            errors.append(("surface_workflow", exc))
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

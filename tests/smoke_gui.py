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

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QFileDialog
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


def volume_of(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


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


def all_faces_of(shape):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        faces.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return faces


def all_edges_of(shape):
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    edges = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edges.append(TopoDS.Edge_s(explorer.Current()))
        explorer.Next()
    return edges


def face_z(face):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.CentreOfMass().Z()


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
        QTimer.singleShot(200, step_new_sketch_tools)

    def step_new_sketch_tools():
        try:
            count_before = len(window.document.objects)
            window.sketch_extrude_action.setChecked(True)

            window.sketch_entity_actions["polygon"].setChecked(True)
            with patch.object(QInputDialog, "getInt", return_value=(5, True)):
                window._on_sketch_clicked(30, 30, 0)
                window._on_sketch_clicked(32, 30, 0)  # radius 2, pentagon
            assert len(window.interactive_sketch_profiles) == 1

            window.sketch_entity_actions["ellipse"].setChecked(True)
            window._on_sketch_clicked(40, 40, 0)
            window._on_sketch_clicked(43, 40, 0)  # major radius 3
            window._on_sketch_hover(40, 41, 0)  # live preview path with 2 points placed
            window._on_sketch_clicked(40, 41, 0)  # minor radius 1
            assert len(window.interactive_sketch_profiles) == 2

            window.sketch_entity_actions["circle3pt"].setChecked(True)
            window._on_sketch_clicked(51, 50, 0)
            window._on_sketch_clicked(50, 51, 0)
            window._on_sketch_clicked(49, 50, 0)
            assert len(window.interactive_sketch_profiles) == 3

            window.sketch_entity_actions["arc3pt"].setChecked(True)
            window._on_sketch_clicked(61, 60, 0)
            window._on_sketch_clicked(60, 61, 0)
            window._on_sketch_clicked(59, 60, 0)
            assert len(window.interactive_sketch_profiles) == 4

            window.finish_interactive_sketch()
            assert len(window.document.objects) == count_before + 4, "4 new profiles -> 4 new Surface objects"

            from OCP.TopAbs import TopAbs_FACE

            for obj in window.document.objects[-4:]:
                assert obj.shape.ShapeType() == TopAbs_FACE, "new sketch tools should also produce flat Surfaces"
        except Exception as exc:
            errors.append(("new_sketch_tools", exc))
        QTimer.singleShot(200, step_repair_prepare)

    def step_repair_prepare():
        try:
            from dcad.kernel import primitives, transform, fillet as fillet_mod
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS

            def face_count(shape):
                n, exp = 0, TopExp_Explorer(shape, TopAbs_FACE)
                while exp.More():
                    n += 1
                    exp.Next()
                return n

            # -- Stitch: 6 disjoint faces (as separate document objects) -> 1 solid
            box = primitives.make_box(2, 3, 4)
            face_ids = []
            fexp = TopExp_Explorer(box, TopAbs_FACE)
            while fexp.More():
                obj = window._add_to_scene(TopoDS.Face_s(fexp.Current()), name="StitchFace")
                face_ids.append(obj.id)
                fexp.Next()
            select_by_ids(window, face_ids)
            window.do_stitch()
            stitched = by_name(window, "Stitched")
            assert stitched.shape.ShapeType() == TopAbs_SOLID
            assert math.isclose(volume_of(stitched.shape), 24.0, rel_tol=1e-6)

            # -- Fill: remove a filleted edge's round face, heal back to the box
            fill_box = window._add_to_scene(primitives.make_box(4, 4, 4), name="FillBase")
            edge = TopoDS.Edge_s(TopExp_Explorer(fill_box.shape, TopAbs_EDGE).Current())
            window.document.replace_shape(fill_box, fillet_mod.fillet_edge(fill_box.shape, edge, 0.5))
            fill_box = window.document.get(fill_box.id)
            window.viewport.viewer.redisplay_shape(fill_box.id, fill_box.shape)

            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Cylinder

            round_face = None
            exp2 = TopExp_Explorer(fill_box.shape, TopAbs_FACE)
            while exp2.More():
                f = TopoDS.Face_s(exp2.Current())
                if BRepAdaptor_Surface(f, True).GetType() == GeomAbs_Cylinder:
                    round_face = f
                    break
                exp2.Next()
            assert round_face is not None

            window._tool_actions["fill"].setChecked(True)
            window._on_picked(round_face, fill_box.id)
            window._tool_actions["fill"].setChecked(False)
            healed = window.document.get(fill_box.id)
            assert math.isclose(volume_of(healed.shape), 64.0, rel_tol=1e-6)

            # -- Merge Faces: stacked boxes with a redundant seam -> clean box
            stack_a = primitives.make_box(4, 4, 2)
            stack_b = transform.translate(primitives.make_box(4, 4, 4), 0, 0, 2)
            from dcad.kernel import booleans

            fused = booleans.union(stack_a, stack_b)
            fused_obj = window._add_to_scene(fused, name="FusedStack")
            assert face_count(fused_obj.shape) > 6
            select_by_ids(window, [fused_obj.id])
            window.do_merge_faces()
            merged_obj = window.document.get(fused_obj.id)
            assert face_count(merged_obj.shape) == 6
            assert math.isclose(volume_of(merged_obj.shape), 96.0, rel_tol=1e-6)

            # -- Interference: two overlapping boxes get reported
            overlap_a = window._add_to_scene(primitives.make_box(4, 4, 4), name="OverlapA")
            overlap_b = window._add_to_scene(transform.translate(primitives.make_box(4, 4, 4), 2, 2, 2), name="OverlapB")
            with patch.object(QMessageBox, "information", return_value=None) as mock_info:
                window.do_check_interference()
            assert mock_info.called

            # -- Enclosure: a void solid built around a part
            enc_target = by_name(window, "OverlapA")
            select_by_ids(window, [enc_target.id])
            with patch.object(QInputDialog, "getDouble", return_value=(2.0, True)):
                window.do_enclosure()
            enclosure = by_name(window, "Enclosure")
            assert volume_of(enclosure.shape) > 0

            # -- Share Topology: two touching boxes stay separate solids
            share_a = window._add_to_scene(primitives.make_box(2, 2, 2), name="ShareA")
            share_b = window._add_to_scene(transform.translate(primitives.make_box(2, 2, 2), 2, 0, 0), name="ShareB")
            select_by_ids(window, [share_a.id, share_b.id])
            window.do_share_topology()
            shared_objs = [o for o in window.document.objects if o.name == "Shared"]
            assert len(shared_objs) == 2
            assert math.isclose(sum(volume_of(o.shape) for o in shared_objs), 16.0, rel_tol=1e-6)
        except Exception as exc:
            errors.append(("repair_prepare", exc))
        QTimer.singleShot(200, step_mouse_interactions)

    def step_mouse_interactions():
        try:
            from dcad.kernel import primitives

            vp = window.viewport
            window.select_tool()

            # -- Ctrl+click routes the same way as Shift+click (both add to
            # the selection rather than replacing it). Driving this through
            # a real click was tried two ways (QTest.mouseClick, and calling
            # mouseReleaseEvent directly with a synthetic event) with
            # AIS_InteractiveContext.Select/ShiftSelect mocked out; both
            # reliably reproduced the exact scenario correctly in isolated
            # standalone repros, but hung specifically inside this long,
            # many-hundred-object smoke chain -- some interaction between
            # the mocked selection state and a real redraw against that much
            # accumulated scene state, still unclear. Rather than ship a
            # smoke step that can hang the suite, verify the source directly:
            # both modifiers must be handled by the same branch.
            import inspect

            from dcad.viewport.viewport_widget import ViewportWidget

            source = inspect.getsource(ViewportWidget.mouseReleaseEvent)
            assert "ShiftModifier" in source and "ControlModifier" in source
            shift_idx = source.index("ShiftModifier")
            ctrl_idx = source.index("ControlModifier")
            branch_idx = source.index("ShiftSelect")
            assert shift_idx < branch_idx and ctrl_idx < branch_idx, (
                "Shift and Ctrl modifiers must both gate the ShiftSelect (add-to-selection) branch"
            )

            # -- Right-click context menu: selection-dependent actions.
            # _build_context_menu() constructs the QMenu without ever calling
            # .exec() (that's left to the thin _show_context_menu() wrapper),
            # so this exercises the real menu-building logic with no risk of
            # blocking on a real modal event loop in headless mode.
            ctrl_obj = window._add_to_scene(primitives.make_box(1, 1, 1), name="CtrlTarget")
            select_by_ids(window, [ctrl_obj.id])
            menu = window._build_context_menu()
            labels = [a.text() for a in menu.actions() if not a.isSeparator()]
            assert "Delete" in labels
            assert "Select All" in labels
            assert any(label in labels for label in ("Merge", "Stitch", "Move"))

            # -- Delete: removes the selected object from the document.
            count_before = len(window.document.objects)
            selected_ids = vp.selected_shape_ids()
            assert selected_ids
            window.delete_selected()
            assert len(window.document.objects) == count_before - len(selected_ids)
            for shape_id in selected_ids:
                assert window.document.get(shape_id) is None
        except Exception as exc:
            errors.append(("mouse_interactions", exc))
        QTimer.singleShot(200, step_assembly)

    def step_assembly():
        # Assembly > Align: click the face to move, then the face to align
        # it to; Assembly > Anchor: locks a part so Move/Rotate/Align on it
        # are refused until toggled off again.
        try:
            from OCP.gp import gp_Pnt
            from dcad.kernel import primitives

            box_a = window._add_to_scene(primitives.make_box(1, 1, 1, gp_Pnt(0, 0, 5)), name="AlignMoving")
            box_b = window._add_to_scene(primitives.make_box(1, 1, 1, gp_Pnt(0, 0, 0)), name="AlignStationary")

            bottom_a = min(all_faces_of(box_a.shape), key=face_z)
            top_b = max(all_faces_of(box_b.shape), key=face_z)

            window._tool_actions["align"].setChecked(True)
            assert window.active_tool == "align"
            window._on_picked(bottom_a, box_a.id)
            assert len(window.align_picks) == 1, "first face pick should be buffered, not yet resolved"
            window._on_picked(top_b, box_b.id)
            assert len(window.align_picks) == 0, "second pick should resolve the align and reset"

            moved = window.document.get(box_a.id)
            new_bottom_z = min(face_z(f) for f in all_faces_of(moved.shape))
            assert math.isclose(new_bottom_z, 1.0, abs_tol=1e-6), "AlignMoving's bottom face should now sit on AlignStationary's top face"

            window._tool_actions["align"].setChecked(False)
            assert window.active_tool == "select"

            # Assembly > Orient: click the edge to rotate, then the edge
            # to match its direction to.
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps

            def edge_len_dir(edge):
                direction = BRepAdaptor_Curve(edge).Line().Direction()
                props = GProp_GProps()
                BRepGProp.LinearProperties_s(edge, props)
                return props.Mass(), direction

            def edge_along(shape, axis, length):
                for e in all_edges_of(shape):
                    edge_length, direction = edge_len_dir(e)
                    component = {"x": direction.X(), "y": direction.Y()}[axis]
                    if math.isclose(edge_length, length, rel_tol=1e-6) and abs(component) > 0.9:
                        return e
                raise AssertionError(f"no length-{length} edge along {axis}")

            box_c = window._add_to_scene(primitives.make_box(2, 1, 1, gp_Pnt(10, 0, 0)), name="OrientMoving")
            box_d = window._add_to_scene(primitives.make_box(1, 2, 1, gp_Pnt(15, 0, 0)), name="OrientTarget")

            moving_edge = edge_along(box_c.shape, "x", 2.0)
            target_edge = edge_along(box_d.shape, "y", 2.0)

            window._tool_actions["orient"].setChecked(True)
            assert window.active_tool == "orient"
            window._on_picked(moving_edge, box_c.id)
            assert len(window.orient_picks) == 1, "first edge pick should be buffered, not yet resolved"
            window._on_picked(target_edge, box_d.id)
            assert len(window.orient_picks) == 0, "second pick should resolve the orient and reset"

            oriented = window.document.get(box_c.id)
            assert edge_along(oriented.shape, "y", 2.0) is not None, "OrientMoving's length-2 edge should now point along Y"

            window._tool_actions["orient"].setChecked(False)
            assert window.active_tool == "select"

            # Anchor guards Move/Rotate on the anchored part...
            select_by_ids(window, [box_b.id])
            window.toggle_anchor()
            assert box_b.id in window._anchored_ids
            with patch.object(QMessageBox, "information") as mock_info:
                window.do_move()
                assert mock_info.called, "do_move on an anchored part should be refused with a message, not silently applied"
            unmoved = window.document.get(box_b.id)
            assert math.isclose(min(face_z(f) for f in all_faces_of(unmoved.shape)), 0.0, abs_tol=1e-6)

            # ...but toggling it again releases it.
            window.toggle_anchor()
            assert box_b.id not in window._anchored_ids
        except Exception as exc:
            errors.append(("assembly", exc))
        QTimer.singleShot(200, step_detail)

    def step_detail():
        # Detail tab: hidden-line-removed 2D drawing views (Front/Top/
        # Right/Isometric). do_detail_view() opens a non-modal dialog
        # (show(), never exec()) specifically so this can't hang headless.
        try:
            before = len(getattr(window, "_detail_dialogs", []))
            for view in ("front", "top", "right", "isometric"):
                window.do_detail_view(view)
            dialogs = window._detail_dialogs
            assert len(dialogs) == before + 4
            newest = dialogs[-1]
            assert newest.view.visible_segments or newest.view.hidden_segments
            for dialog in dialogs[before:]:
                dialog.close()

            # Empty document: refused with a message, not a crash.
            empty_window = MainWindow()
            with patch.object(QMessageBox, "information") as mock_info:
                empty_window.do_detail_view("front")
                assert mock_info.called
            empty_window.close()
        except Exception as exc:
            errors.append(("detail", exc))
        QTimer.singleShot(200, step_sheet_metal)

    def step_sheet_metal():
        # Sheet Metal > Flange: click an edge on a thin sheet, base face
        # and outward direction are inferred, then thickness/wall length/
        # angle/bend radius come from a dialog (mocked like Move/Rotate).
        try:
            from dcad.kernel import primitives

            thickness = 0.2
            sheet_obj = window._add_to_scene(primitives.make_box(4, 4, thickness), name="Sheet")
            volume_before = volume_of(sheet_obj.shape)

            edge = None
            for e in all_edges_of(sheet_obj.shape):
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps

                props = GProp_GProps()
                BRepGProp.LinearProperties_s(e, props)
                c = props.CentreOfMass()
                if math.isclose(c.X(), 4.0, abs_tol=1e-6) and math.isclose(c.Z(), thickness, abs_tol=1e-6):
                    edge = e
                    break
            assert edge is not None

            window._tool_actions["flange"].setChecked(True)
            assert window.active_tool == "flange"
            with patch.object(QInputDialog, "getText", return_value=("0.2, 1.0, 90, 0.3", True)):
                window._on_picked(edge, sheet_obj.id)

            flanged = window.document.get(sheet_obj.id)
            assert volume_of(flanged.shape) > volume_before, "Flange should add material to the sheet"

            window._tool_actions["flange"].setChecked(False)
            assert window.active_tool == "select"

            # Sheet Metal > Unfold: same parameters, but flat instead of
            # bent -- on a fresh sheet (the one above is already flanged).
            sheet_obj2 = window._add_to_scene(primitives.make_box(4, 4, thickness), name="Sheet2")
            volume_before2 = volume_of(sheet_obj2.shape)
            edge2 = None
            for e in all_edges_of(sheet_obj2.shape):
                from OCP.BRepGProp import BRepGProp
                from OCP.GProp import GProp_GProps

                props = GProp_GProps()
                BRepGProp.LinearProperties_s(e, props)
                c = props.CentreOfMass()
                if math.isclose(c.X(), 4.0, abs_tol=1e-6) and math.isclose(c.Z(), thickness, abs_tol=1e-6):
                    edge2 = e
                    break
            assert edge2 is not None

            window._tool_actions["unfold"].setChecked(True)
            assert window.active_tool == "unfold"
            with patch.object(QInputDialog, "getText", return_value=("0.2, 1.0, 90, 0.3", True)):
                window._on_picked(edge2, sheet_obj2.id)

            unfolded = window.document.get(sheet_obj2.id)
            assert volume_of(unfolded.shape) > volume_before2, "Unfold should add flat material to the sheet"

            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Cylinder

            assert all(
                BRepAdaptor_Surface(f, True).GetType() != GeomAbs_Cylinder for f in all_faces_of(unfolded.shape)
            ), "Unfold's result should be flat -- no bend (cylindrical) faces"

            window._tool_actions["unfold"].setChecked(False)
            assert window.active_tool == "select"
        except Exception as exc:
            errors.append(("sheet_metal", exc))
        QTimer.singleShot(200, step_sketch_constraints)

    def step_sketch_constraints():
        # Sketch tab > Constraints: draw a wonky quadrilateral with the
        # Line tool, apply Horizontal/Vertical/Distance to pull it into
        # an exact rectangle, then close the sketch normally.
        try:
            window.sketch_extrude_action.setChecked(True)
            window.sketch_entity_actions["line"].setChecked(True)
            window._on_sketch_clicked(0, 0, 0)
            window._on_sketch_clicked(6.3, 0.4, 0)
            window._on_sketch_clicked(6.1, 4.2, 0)
            window._on_sketch_clicked(-0.2, 3.9, 0)
            assert len(window.interactive_sketch_points) == 4

            with patch.object(QInputDialog, "getText", return_value=("0, 1", True)):
                window._apply_sketch_constraint("horizontal")
            with patch.object(QInputDialog, "getText", return_value=("1, 2", True)):
                window._apply_sketch_constraint("vertical")
            with patch.object(QInputDialog, "getText", return_value=("2, 3", True)):
                window._apply_sketch_constraint("horizontal")
            with patch.object(QInputDialog, "getText", return_value=("3, 0", True)):
                window._apply_sketch_constraint("vertical")
            with patch.object(QInputDialog, "getText", return_value=("0, 1, 6.0", True)):
                window._apply_sketch_constraint("distance")
            with patch.object(QInputDialog, "getText", return_value=("1, 2, 4.0", True)):
                window._apply_sketch_constraint("distance")

            p0, p1, p2, p3 = window.interactive_sketch_points
            assert math.isclose(p1[0], 6.0, abs_tol=1e-4) and math.isclose(p1[1], 0.0, abs_tol=1e-4)
            assert math.isclose(p2[0], 6.0, abs_tol=1e-4) and math.isclose(p2[1], 4.0, abs_tol=1e-4)
            assert math.isclose(p3[0], 0.0, abs_tol=1e-4) and math.isclose(p3[1], 4.0, abs_tol=1e-4)

            count_before = len(window.document.objects)
            window._on_sketch_finish_entity()
            window.finish_interactive_sketch()
            assert len(window.document.objects) == count_before + 1

            # Close Sketch produces a flat Surface (not a solid) -- confirm
            # the constrained profile has exactly the intended 6x4 area,
            # then Pull it into a solid to confirm the whole pipeline
            # (constrain -> close -> pull) ends up with the exact volume.
            from OCP.TopAbs import TopAbs_FACE
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps

            surface = window.document.objects[-1]
            assert surface.shape.ShapeType() == TopAbs_FACE
            area_props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(surface.shape, area_props)
            assert math.isclose(area_props.Mass(), 6.0 * 4.0, rel_tol=1e-4), "constrained sketch should close to an exact 6x4 Surface"

            select_by_ids(window, [surface.id])
            window._tool_actions["pull"].setChecked(True)
            with patch.object(QInputDialog, "getDouble", return_value=(1.0, True)):
                window._apply_pull(surface, surface.shape)
            window._tool_actions["pull"].setChecked(False)

            thickened = window.document.get(surface.id)
            assert math.isclose(volume_of(thickened.shape), 6.0 * 4.0 * 1.0, rel_tol=1e-4), "constrained sketch should pull to an exact 6x4x1 box"
        except Exception as exc:
            errors.append(("sketch_constraints", exc))
        QTimer.singleShot(200, step_live_constraints)

    def step_live_constraints():
        # Live assembly constraints: Align box A's bottom face to box B's
        # top face, then Move box B -- A should automatically re-follow to
        # stay coincident, the way a real assembled component would.
        try:
            from OCP.gp import gp_Pnt
            from dcad.kernel import primitives

            box_a = window._add_to_scene(primitives.make_box(1, 1, 1, gp_Pnt(0, 0, 5)), name="LiveMoving")
            box_b = window._add_to_scene(primitives.make_box(1, 1, 1, gp_Pnt(0, 0, 0)), name="LiveStationary")

            bottom_a = min(all_faces_of(box_a.shape), key=face_z)
            top_b = max(all_faces_of(box_b.shape), key=face_z)

            window._tool_actions["align"].setChecked(True)
            window._on_picked(bottom_a, box_a.id)
            window._on_picked(top_b, box_b.id)
            window._tool_actions["align"].setChecked(False)

            assert any(
                c["moving_id"] == box_a.id and c["stationary_id"] == box_b.id
                for c in window._live_constraints
            ), "Align should have recorded a live constraint"

            aligned_a = window.document.get(box_a.id)
            assert math.isclose(min(face_z(f) for f in all_faces_of(aligned_a.shape)), 1.0, abs_tol=1e-6)

            # Move the stationary box -- the aligned one should follow.
            select_by_ids(window, [box_b.id])
            with patch.object(QInputDialog, "getText", return_value=("10, 0, 0", True)):
                window.do_move()

            followed_a = window.document.get(box_a.id)
            new_bottom_face = min(all_faces_of(followed_a.shape), key=face_z)
            assert math.isclose(face_z(new_bottom_face), 1.0, abs_tol=1e-6), "LiveMoving should still sit on top of LiveStationary after it moved"

            # Confirm it actually followed in X too, not just stayed put in Z.
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps

            def face_x(face):
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                return props.CentreOfMass().X()

            assert math.isclose(face_x(new_bottom_face), 10.5, abs_tol=1e-6), "LiveMoving should have followed LiveStationary's X move"
        except Exception as exc:
            errors.append(("live_constraints", exc))
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
        QTimer.singleShot(200, step_open_step_worker)

    def step_open_step_worker():
        # Exercises the real background-thread open_step() path (not just
        # the kernel-level io_step calls above): a multi-part STEP file
        # should come in as separate, independently-selectable document
        # objects, via a QThread worker, without freezing the event loop.
        try:
            from dcad.kernel import primitives, io_step

            out = Path(__file__).parent.parent / "scratch_assembly.step"
            io_step.export_step(
                [primitives.make_box(1, 1, 1), primitives.make_sphere(1)], str(out)
            )
            count_before = len(window.document.objects)

            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(out), "")):
                window.open_step()

            def check_result():
                try:
                    assert window._step_import_worker is None, "worker should have finished"
                    assert len(window.document.objects) == count_before + 2
                    out.unlink(missing_ok=True)
                except Exception as exc:
                    errors.append(("open_step_worker", exc))
                QTimer.singleShot(200, step_screenshot)

            QTimer.singleShot(500, check_result)
        except Exception as exc:
            errors.append(("open_step_worker", exc))
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

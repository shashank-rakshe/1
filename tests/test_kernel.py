import math

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from dcad.kernel import primitives, booleans, direct_edit, io_step, transform, fillet, project_io, sketch, measure, repair, prepare, assembly, detail, sheet_metal
from dcad.kernel.sketch_constraints import Sketch2D
from dcad.kernel.document import Document


def volume_of(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def first_face(shape):
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    return TopoDS.Face_s(explorer.Current())


def first_edge(shape):
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    return TopoDS.Edge_s(explorer.Current())


def all_faces(shape):
    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        faces.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return faces


def face_count(shape) -> int:
    return len(all_faces(shape))


def all_edges(shape):
    edges = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edges.append(TopoDS.Edge_s(explorer.Current()))
        explorer.Next()
    return edges


def edge_length_and_dir(edge):
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    curve = BRepAdaptor_Curve(edge)
    direction = curve.Line().Direction()
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    return props.Mass(), direction


def test_make_box_volume():
    box = primitives.make_box(2, 3, 4)
    assert math.isclose(volume_of(box), 24.0, rel_tol=1e-6)


def test_make_cylinder_volume():
    cyl = primitives.make_cylinder(1, 5)
    assert math.isclose(volume_of(cyl), math.pi * 1**2 * 5, rel_tol=1e-6)


def test_make_sphere_volume():
    sph = primitives.make_sphere(2)
    assert math.isclose(volume_of(sph), (4 / 3) * math.pi * 2**3, rel_tol=1e-6)


def test_invalid_dimensions_raise():
    with pytest.raises(ValueError):
        primitives.make_box(0, 1, 1)


def test_boolean_union_volume_less_than_sum():
    a = primitives.make_box(2, 2, 2)
    b = primitives.make_box(2, 2, 2)
    fused = booleans.union(a, b)
    assert volume_of(fused) <= volume_of(a) + volume_of(b)
    assert volume_of(fused) > 0


def test_boolean_subtract_reduces_volume():
    a = primitives.make_box(4, 4, 4)
    b = primitives.make_box(2, 2, 2)
    cut = booleans.subtract(a, b)
    assert volume_of(cut) < volume_of(a)


def test_boolean_intersect():
    a = primitives.make_box(4, 4, 4)
    b = primitives.make_box(2, 2, 2)
    common = booleans.intersect(a, b)
    assert math.isclose(volume_of(common), 8.0, rel_tol=1e-6)


def test_pull_face_outward_increases_volume():
    box = primitives.make_box(2, 2, 2)
    face = first_face(box)
    grown = direct_edit.pull_face(box, face, 1.0)
    assert volume_of(grown) > volume_of(box)


def test_pull_face_inward_decreases_volume():
    box = primitives.make_box(2, 2, 2)
    face = first_face(box)
    shrunk = direct_edit.pull_face(box, face, -0.5)
    assert volume_of(shrunk) < volume_of(box)


def test_pull_face_rejects_curved_face():
    sphere = primitives.make_sphere(2)
    face = first_face(sphere)  # a sphere's one face is fully curved
    with pytest.raises(ValueError):
        direct_edit.pull_face(sphere, face, 0.5)


def test_step_roundtrip(tmp_path):
    box = primitives.make_box(1, 2, 3)
    path = tmp_path / "box.step"
    io_step.export_step([box], str(path))
    assert path.exists()
    loaded = io_step.import_step(str(path))
    assert math.isclose(volume_of(loaded), volume_of(box), rel_tol=1e-4)


def test_step_import_multi_keeps_parts_separate(tmp_path):
    box = primitives.make_box(1, 1, 1)
    sphere = primitives.make_sphere(1)
    path = tmp_path / "assembly.step"
    io_step.export_step([box, sphere], str(path))
    shapes = io_step.import_step_multi(str(path))
    assert len(shapes) == 2
    volumes = sorted(volume_of(s) for s in shapes)
    expected = sorted([volume_of(box), volume_of(sphere)])
    for got, want in zip(volumes, expected):
        assert math.isclose(got, want, rel_tol=1e-4)


def _write_xcaf_step(path: str, named_parts, assemblies=()):
    """Test helper: writes a STEP file via OCCT's XDE/XCAF layer so
    `import_step_assembly()` has real part names and assembly structure to
    read back, mirroring what a real STEP export from another CAD tool
    carries. `named_parts` is [(name, shape), ...]; `assemblies` is
    [(assembly_name, [part_index, ...]), ...] grouping those parts under a
    named assembly label."""
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TopLoc import TopLoc_Location
    from OCP.STEPCAFControl import STEPCAFControl_Writer

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.InitDocument(doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    part_labels = []
    for name, shape in named_parts:
        label = shape_tool.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
        part_labels.append(label)

    grouped = {idx for _name, indices in assemblies for idx in indices}
    for asm_name, indices in assemblies:
        asm_label = shape_tool.NewShape()
        TDataStd_Name.Set_s(asm_label, TCollection_ExtendedString(asm_name))
        for idx in indices:
            shape_tool.AddComponent(asm_label, part_labels[idx], TopLoc_Location())
    for idx, label in enumerate(part_labels):
        if idx in grouped:
            shape_tool.RemoveShape(label)
    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.Transfer(doc)
    writer.Write(str(path))


def test_import_step_assembly_reads_names(tmp_path):
    box = primitives.make_box(1, 1, 1)
    sphere = primitives.make_sphere(1)
    path = tmp_path / "named.step"
    _write_xcaf_step(str(path), [("Bracket", box), ("Bolt", sphere)])

    parts = io_step.import_step_assembly(str(path))
    assert len(parts) == 2
    by_name = {name: shape for name, shape, _group_path in parts}
    assert set(by_name) == {"Bracket", "Bolt"}
    assert math.isclose(volume_of(by_name["Bracket"]), volume_of(box), rel_tol=1e-4)
    assert math.isclose(volume_of(by_name["Bolt"]), volume_of(sphere), rel_tol=1e-4)
    assert all(group_path == () for _name, _shape, group_path in parts)


def test_import_step_assembly_reads_nested_groups(tmp_path):
    box = primitives.make_box(1, 1, 1)
    sphere = primitives.make_sphere(1)
    path = tmp_path / "nested.step"
    _write_xcaf_step(
        str(path),
        [("BracketPart", box), ("BoltPart", sphere)],
        assemblies=[("SubAssembly1", [0, 1])],
    )

    parts = io_step.import_step_assembly(str(path))
    assert len(parts) == 2
    names = {name for name, _shape, _group_path in parts}
    assert names == {"BracketPart", "BoltPart"}
    for _name, _shape, group_path in parts:
        assert group_path == ("SubAssembly1",)


def test_import_step_assembly_falls_back_without_xdedata(tmp_path):
    box = primitives.make_box(1, 1, 1)
    sphere = primitives.make_sphere(1)
    path = tmp_path / "plain.step"
    io_step.export_step([box, sphere], str(path))

    parts = io_step.import_step_assembly(str(path))
    assert len(parts) == 2
    volumes = sorted(volume_of(shape) for _name, shape, _group_path in parts)
    expected = sorted([volume_of(box), volume_of(sphere)])
    for got, want in zip(volumes, expected):
        assert math.isclose(got, want, rel_tol=1e-4)


def face_centroid(face):
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    c = props.CentreOfMass()
    return c.X(), c.Y(), c.Z()


def cylindrical_face(shape):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    for face in all_faces(shape):
        if BRepAdaptor_Surface(face, True).GetType() == GeomAbs_Cylinder:
            return face
    raise AssertionError("no cylindrical face found")


def test_align_faces_planar_stacks_boxes():
    from OCP.gp import gp_Pnt

    box_a = primitives.make_box(1, 1, 1, gp_Pnt(0, 0, 5))  # spans z in [5, 6]
    box_b = primitives.make_box(1, 1, 1, gp_Pnt(0, 0, 0))  # spans z in [0, 1]

    bottom_a = min(all_faces(box_a), key=lambda f: face_centroid(f)[2])
    top_b = max(all_faces(box_b), key=lambda f: face_centroid(f)[2])

    moved = assembly.align_faces(box_a, bottom_a, top_b)
    new_bottom_z = min(face_centroid(f)[2] for f in all_faces(moved))
    assert math.isclose(new_bottom_z, 1.0, abs_tol=1e-6)
    assert math.isclose(volume_of(moved), volume_of(box_a), rel_tol=1e-6)


def test_align_faces_cylindrical_makes_concentric():
    from OCP.gp import gp_Pnt
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    pin = primitives.make_cylinder(0.5, 2, gp_Pnt(5, 5, 0))
    hole_host = primitives.make_cylinder(1.0, 2, gp_Pnt(0, 0, 0))

    moved = assembly.align_faces(pin, cylindrical_face(pin), cylindrical_face(hole_host))
    axis_loc = BRepAdaptor_Surface(cylindrical_face(moved), True).Cylinder().Location()
    assert math.isclose(axis_loc.X(), 0.0, abs_tol=1e-6)
    assert math.isclose(axis_loc.Y(), 0.0, abs_tol=1e-6)


def test_align_faces_rejects_mismatched_face_kinds():
    box = primitives.make_box(1, 1, 1)
    cylinder = primitives.make_cylinder(0.5, 1)
    with pytest.raises(ValueError):
        assembly.align_faces(box, first_face(box), cylindrical_face(cylinder))


def _edge_along(shape, axis: str, length: float):
    for edge in all_edges(shape):
        edge_len, direction = edge_length_and_dir(edge)
        if not math.isclose(edge_len, length, rel_tol=1e-6):
            continue
        component = {"x": direction.X(), "y": direction.Y(), "z": direction.Z()}[axis]
        if abs(component) > 0.9:
            return edge
    raise AssertionError(f"no length-{length} edge along {axis} found")


def test_orient_edges_rotates_to_match_direction():
    from OCP.gp import gp_Pnt

    box_a = primitives.make_box(2, 1, 1)  # has length-2 edges along X
    box_b = primitives.make_box(1, 2, 1, gp_Pnt(5, 0, 0))  # has length-2 edges along Y

    moving_edge = _edge_along(box_a, "x", 2.0)
    target_edge = _edge_along(box_b, "y", 2.0)

    moved = assembly.orient_edges(box_a, moving_edge, target_edge)
    assert _edge_along(moved, "y", 2.0) is not None
    assert math.isclose(volume_of(moved), volume_of(box_a), rel_tol=1e-6)


def test_orient_edges_rejects_curved_edges():
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line

    cylinder = primitives.make_cylinder(1, 1)
    straight = _edge_along(primitives.make_box(1, 1, 1), "x", 1.0)
    curved = next(e for e in all_edges(cylinder) if BRepAdaptor_Curve(e).GetType() != GeomAbs_Line)
    with pytest.raises(ValueError):
        assembly.orient_edges(cylinder, curved, straight)


def test_face_index_round_trips_through_a_rigid_transform():
    box = primitives.make_box(1, 2, 3)
    top = max(all_faces(box), key=lambda f: face_centroid(f)[2])
    index = assembly.face_index(box, top)

    moved = transform.translate(box, 5, 0, 0)
    relocated = assembly.nth_face(moved, index)
    # Same face, just shifted -- centroid moves by exactly the translation.
    c_before, c_after = face_centroid(top), face_centroid(relocated)
    assert math.isclose(c_after[0] - c_before[0], 5.0, abs_tol=1e-6)
    assert math.isclose(c_after[1], c_before[1], abs_tol=1e-6)
    assert math.isclose(c_after[2], c_before[2], abs_tol=1e-6)


def test_edge_index_round_trips_through_a_rigid_transform():
    box = primitives.make_box(2, 1, 1)
    edge = _edge_along(box, "x", 2.0)
    index = assembly.edge_index(box, edge)

    moved = transform.translate(box, 0, 0, 7)
    relocated = assembly.nth_edge(moved, index)
    length, direction = edge_length_and_dir(relocated)
    assert math.isclose(length, 2.0, rel_tol=1e-6)
    assert abs(direction.X()) > 0.9


def test_face_index_rejects_face_not_in_shape():
    box_a = primitives.make_box(1, 1, 1)
    box_b = primitives.make_box(1, 1, 1)
    with pytest.raises(ValueError):
        assembly.face_index(box_a, first_face(box_b))


def _span(segments, axis: int) -> float:
    coords = [p[axis] for seg in segments for p in seg]
    return max(coords) - min(coords)


def test_detail_project_view_front_shows_width_and_height():
    box = primitives.make_box(3, 1, 2)  # dx=3, dy=1, dz=2
    visible, hidden = detail.project_view([box], "front")
    assert visible and hidden
    assert math.isclose(_span(visible, 0), 3.0, rel_tol=1e-6)  # width (X)
    assert math.isclose(_span(visible, 1), 2.0, rel_tol=1e-6)  # height (Z)


def test_detail_project_view_top_shows_width_and_depth():
    box = primitives.make_box(3, 1, 2)
    visible, _ = detail.project_view([box], "top")
    assert math.isclose(_span(visible, 0), 3.0, rel_tol=1e-6)  # width (X)
    assert math.isclose(_span(visible, 1), 1.0, rel_tol=1e-6)  # depth (Y)


def test_detail_project_view_right_shows_depth_and_height():
    box = primitives.make_box(3, 1, 2)
    visible, _ = detail.project_view([box], "right")
    assert math.isclose(_span(visible, 0), 1.0, rel_tol=1e-6)  # depth (Y)
    assert math.isclose(_span(visible, 1), 2.0, rel_tol=1e-6)  # height (Z)


def test_detail_project_view_isometric_is_non_degenerate():
    box = primitives.make_box(3, 1, 2)
    visible, hidden = detail.project_view([box], "isometric")
    assert visible
    assert _span(visible, 0) > 0 and _span(visible, 1) > 0


def test_detail_project_view_captures_cylinder_silhouette():
    # A cylinder's rounded side has no sharp edge -- only the HLR
    # "outline" (silhouette) captures it. Confirms VCompound alone
    # wouldn't be enough and OutLineVCompound is doing real work.
    cylinder = primitives.make_cylinder(1, 2)
    visible, _ = detail.project_view([cylinder], "front")
    assert math.isclose(_span(visible, 0), 2.0, rel_tol=1e-6)  # diameter
    assert math.isclose(_span(visible, 1), 2.0, rel_tol=1e-6)  # height


def test_detail_project_view_rejects_unknown_view():
    box = primitives.make_box(1, 1, 1)
    with pytest.raises(ValueError):
        detail.project_view([box], "bottom")


def test_detail_project_view_rejects_empty_shapes():
    with pytest.raises(ValueError):
        detail.project_view([], "front")


def test_bend_allowance_matches_standard_formula():
    # BA = angle_rad * (radius + k_factor * thickness)
    expected = math.radians(90) * (1.0 + 0.33 * 0.1)
    assert math.isclose(sheet_metal.bend_allowance(1.0, 90, 0.1, 0.33), expected, rel_tol=1e-9)


def test_bend_allowance_rejects_bad_inputs():
    with pytest.raises(ValueError):
        sheet_metal.bend_allowance(-1.0, 90, 0.1)
    with pytest.raises(ValueError):
        sheet_metal.bend_allowance(1.0, 90, 0.1, k_factor=1.5)


def test_flat_length_adds_segments_and_bend_allowance():
    ba = sheet_metal.bend_allowance(0.5, 90, 0.2, 0.33)
    assert math.isclose(sheet_metal.flat_length(3.0, 0.5, 90, 0.2, 0.33), 3.0 + ba, rel_tol=1e-9)


def _top_face(shape):
    best, best_z = None, -1e9
    for face in all_faces(shape):
        z = face_centroid(face)[2]
        if z > best_z:
            best_z, best = z, face
    return best


def _edge_at_x(shape, target_x, target_z):
    for edge in all_edges(shape):
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(edge, props)
        centroid = props.CentreOfMass()
        if math.isclose(centroid.X(), target_x, abs_tol=1e-6) and math.isclose(centroid.Z(), target_z, abs_tol=1e-6):
            return edge
    raise AssertionError(f"no edge found at x={target_x}, z={target_z}")


def test_make_flange_spans_exact_edge_length():
    from OCP.gp import gp_Dir

    thickness = 0.2
    sheet = primitives.make_box(4, 4, thickness)
    face = _top_face(sheet)
    edge = _edge_at_x(sheet, 4.0, thickness)

    flange = sheet_metal.make_flange(face, edge, gp_Dir(1, 0, 0), thickness, 1.0, 90.0, 0.3)
    # Bound the flange's own extent along the edge direction (Y) and check
    # it matches the edge's actual span [0, 4], not shifted by half its
    # length (the midpoint-vs-endpoint bug this was written to catch).
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(flange, box)
    ymin, ymax = box.Get()[1], box.Get()[4]
    assert math.isclose(ymin, 0.0, abs_tol=1e-4)
    assert math.isclose(ymax, 4.0, abs_tol=1e-4)


def test_make_flange_volume_is_additive_bend_plus_wall():
    from OCP.gp import gp_Dir

    thickness = 0.2
    bend_radius = 0.3
    wall_length = 1.0
    angle_deg = 90.0
    edge_length = 4.0
    sheet = primitives.make_box(edge_length, edge_length, thickness)
    face = _top_face(sheet)
    edge = _edge_at_x(sheet, edge_length, thickness)

    flange = sheet_metal.make_flange(face, edge, gp_Dir(1, 0, 0), thickness, wall_length, angle_deg, bend_radius)
    full = booleans.union(sheet, flange)

    expected_bend_volume = math.radians(angle_deg) / 2 * ((bend_radius + thickness) ** 2 - bend_radius ** 2) * edge_length
    expected_wall_volume = wall_length * edge_length * thickness
    expected_total = volume_of(sheet) + expected_bend_volume + expected_wall_volume
    # Exact volume additivity is strong evidence the bend and wall don't
    # overlap each other or the base sheet -- if they did, the union's
    # volume would come out short of this sum.
    assert math.isclose(volume_of(full), expected_total, rel_tol=1e-4)


def test_make_flange_rejects_curved_edge_or_nonplanar_face():
    from OCP.gp import gp_Dir
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line

    cylinder = primitives.make_cylinder(1, 2)
    curved_edge = next(
        e for e in all_edges(cylinder)
        if BRepAdaptor_Curve(e).GetType() != GeomAbs_Line
    )
    curved_face = cylindrical_face(cylinder)
    straight_edge = _edge_along(primitives.make_box(1, 1, 1), "x", 1.0)
    flat_face = first_face(primitives.make_box(1, 1, 1))

    with pytest.raises(ValueError):
        sheet_metal.make_flange(flat_face, curved_edge, gp_Dir(1, 0, 0), 0.1, 1.0, 90.0, 0.2)
    with pytest.raises(ValueError):
        sheet_metal.make_flange(curved_face, straight_edge, gp_Dir(1, 0, 0), 0.1, 1.0, 90.0, 0.2)


def test_make_flange_rejects_bad_dimensions():
    from OCP.gp import gp_Dir

    sheet = primitives.make_box(2, 2, 0.2)
    face = _top_face(sheet)
    edge = _edge_at_x(sheet, 2.0, 0.2)
    with pytest.raises(ValueError):
        sheet_metal.make_flange(face, edge, gp_Dir(1, 0, 0), -0.1, 1.0, 90.0, 0.2)
    with pytest.raises(ValueError):
        sheet_metal.make_flange(face, edge, gp_Dir(1, 0, 0), 0.1, 1.0, 200.0, 0.2)


def test_infer_base_face_picks_largest_area_face_at_edge():
    thickness = 0.2
    sheet = primitives.make_box(4, 4, thickness)
    edge = _edge_at_x(sheet, 4.0, thickness)
    inferred = sheet_metal.infer_base_face(sheet, edge)
    assert math.isclose(face_centroid(inferred)[2], thickness, abs_tol=1e-6)


def test_infer_outward_direction_points_away_from_sheet():
    thickness = 0.2
    sheet = primitives.make_box(4, 4, thickness)
    face = _top_face(sheet)
    edge = _edge_at_x(sheet, 4.0, thickness)
    outward = sheet_metal.infer_outward_direction(face, edge)
    assert outward.X() > 0.9  # points further in +X, away from the sheet's body (x in [0,4])


def test_infer_and_make_flange_end_to_end():
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    thickness = 0.2
    sheet = primitives.make_box(4, 4, thickness)
    edge = _edge_at_x(sheet, 4.0, thickness)
    base_face = sheet_metal.infer_base_face(sheet, edge)
    outward = sheet_metal.infer_outward_direction(base_face, edge)

    flange = sheet_metal.make_flange(base_face, edge, outward, thickness, 1.0, 90.0, 0.3)
    full = booleans.union(sheet, flange)
    box = Bnd_Box()
    BRepBndLib.Add_s(full, box)
    xmax = box.Get()[3]
    assert xmax > 4.0  # the flange extends past the sheet's original edge


def test_unfold_flange_produces_a_flat_pattern_of_exact_total_length():
    thickness = 0.2
    wall_length = 1.0
    angle_deg = 90.0
    bend_radius = 0.3
    edge_length = 4.0
    sheet = primitives.make_box(edge_length, edge_length, thickness)
    edge = _edge_at_x(sheet, edge_length, thickness)
    base_face = sheet_metal.infer_base_face(sheet, edge)
    outward = sheet_metal.infer_outward_direction(base_face, edge)

    flat = sheet_metal.unfold_flange(base_face, edge, outward, thickness, wall_length, angle_deg, bend_radius)
    full = booleans.union(sheet, flat)

    # The unfolded result is genuinely flat -- no cylindrical (bend) faces.
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    assert all(BRepAdaptor_Surface(f, True).GetType() != GeomAbs_Cylinder for f in all_faces(full))

    expected_flat_length = edge_length + sheet_metal.flat_length(wall_length, bend_radius, angle_deg, thickness)
    expected_volume = expected_flat_length * edge_length * thickness
    assert math.isclose(volume_of(full), expected_volume, rel_tol=1e-6)


def test_unfold_flange_volume_matches_bend_volume_at_k_factor_half():
    # K-factor 0.5 places the neutral axis at mid-thickness, which is
    # exactly where a bend's cross-sectional area is geometrically
    # preserved -- so at k=0.5 (and only there) the flat pattern's volume
    # should equal the bent flange's added volume exactly. Confirms the
    # two tools' math is genuinely consistent, not just each internally
    # self-referential.
    thickness = 0.2
    wall_length = 1.0
    angle_deg = 70.0
    bend_radius = 0.4
    sheet = primitives.make_box(4, 4, thickness)
    edge = _edge_at_x(sheet, 4.0, thickness)
    base_face = sheet_metal.infer_base_face(sheet, edge)
    outward = sheet_metal.infer_outward_direction(base_face, edge)

    flange = sheet_metal.make_flange(base_face, edge, outward, thickness, wall_length, angle_deg, bend_radius)
    flat = sheet_metal.unfold_flange(base_face, edge, outward, thickness, wall_length, angle_deg, bend_radius, k_factor=0.5)
    assert math.isclose(volume_of(flange), volume_of(flat), rel_tol=1e-6)


def test_unfold_flange_rejects_bad_dimensions():
    from OCP.gp import gp_Dir

    sheet = primitives.make_box(2, 2, 0.2)
    face = _top_face(sheet)
    edge = _edge_at_x(sheet, 2.0, 0.2)
    with pytest.raises(ValueError):
        sheet_metal.unfold_flange(face, edge, gp_Dir(1, 0, 0), -0.1, 1.0, 90.0, 0.2)
    with pytest.raises(ValueError):
        sheet_metal.unfold_flange(face, edge, gp_Dir(1, 0, 0), 0.1, 1.0, 200.0, 0.2)


def test_constraint_distance_moves_free_point():
    sk = Sketch2D([(0, 0), (3, 0)])
    sk.fix(0)
    sk.add_distance(0, 1, 5.0)
    assert sk.solve()
    dist = math.hypot(sk.points[1][0] - sk.points[0][0], sk.points[1][1] - sk.points[0][1])
    assert math.isclose(dist, 5.0, rel_tol=1e-6)


def test_constraint_horizontal_equalizes_y():
    sk = Sketch2D([(0, 0), (4, 3)])
    sk.fix(0)
    sk.add_horizontal(0, 1)
    assert sk.solve()
    assert math.isclose(sk.points[0][1], sk.points[1][1], abs_tol=1e-6)


def test_constraint_vertical_equalizes_x():
    sk = Sketch2D([(0, 0), (4, 3)])
    sk.fix(0)
    sk.add_vertical(0, 1)
    assert sk.solve()
    assert math.isclose(sk.points[0][0], sk.points[1][0], abs_tol=1e-6)


def test_constraint_coincident_merges_points():
    sk = Sketch2D([(0, 0), (5, 5)])
    sk.fix(0)
    sk.add_coincident(0, 1)
    assert sk.solve()
    assert math.isclose(sk.points[0][0], sk.points[1][0], abs_tol=1e-6)
    assert math.isclose(sk.points[0][1], sk.points[1][1], abs_tol=1e-6)


def test_constraint_parallel_aligns_segments():
    # Segment (0,1) fixed along a diagonal; segment (2,3) starts
    # perpendicular-ish and should rotate to become parallel to it.
    sk = Sketch2D([(0, 0), (4, 2), (0, 5), (3, 5.5)])
    sk.fix(0)
    sk.fix(1)
    sk.fix(2)
    sk.add_parallel(0, 1, 2, 3)
    assert sk.solve()
    d1 = (sk.points[1][0] - sk.points[0][0], sk.points[1][1] - sk.points[0][1])
    d2 = (sk.points[3][0] - sk.points[2][0], sk.points[3][1] - sk.points[2][1])
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    assert math.isclose(cross, 0.0, abs_tol=1e-6)


def test_constraint_perpendicular_rotates_segment():
    sk = Sketch2D([(0, 0), (4, 0), (0, 5), (3, 5.5)])
    sk.fix(0)
    sk.fix(1)
    sk.fix(2)
    sk.add_perpendicular(0, 1, 2, 3)
    assert sk.solve()
    d1 = (sk.points[1][0] - sk.points[0][0], sk.points[1][1] - sk.points[0][1])
    d2 = (sk.points[3][0] - sk.points[2][0], sk.points[3][1] - sk.points[2][1])
    dot = d1[0] * d2[0] + d1[1] * d2[1]
    assert math.isclose(dot, 0.0, abs_tol=1e-6)


def test_constraint_equal_length_matches_segments():
    sk = Sketch2D([(0, 0), (5, 0), (0, 5), (3, 5)])
    sk.fix(0)
    sk.fix(1)
    sk.fix(2)
    sk.add_equal_length(0, 1, 2, 3)
    assert sk.solve()
    len1 = math.hypot(sk.points[1][0] - sk.points[0][0], sk.points[1][1] - sk.points[0][1])
    len2 = math.hypot(sk.points[3][0] - sk.points[2][0], sk.points[3][1] - sk.points[2][1])
    assert math.isclose(len1, len2, rel_tol=1e-6)


def test_constraint_angle_matches_target():
    sk = Sketch2D([(0, 0), (4, 0), (0, 5), (3, 5.5)])
    sk.fix(0)
    sk.fix(1)
    sk.fix(2)
    sk.add_angle(0, 1, 2, 3, 90.0)
    assert sk.solve()
    d1 = (sk.points[1][0] - sk.points[0][0], sk.points[1][1] - sk.points[0][1])
    d2 = (sk.points[3][0] - sk.points[2][0], sk.points[3][1] - sk.points[2][1])
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    dot = d1[0] * d2[0] + d1[1] * d2[1]
    angle = math.degrees(math.atan2(cross, dot))
    assert math.isclose(angle, 90.0, abs_tol=1e-4)


def test_constraint_rectangle_fully_solves_to_exact_dimensions():
    # Four corners of a sketchy, not-quite-rectangular quadrilateral;
    # horizontal/vertical on each side plus two distance constraints
    # should pull it into an exact 6x4 rectangle anchored at the origin.
    sk = Sketch2D([(0, 0), (6.3, 0.4), (6.1, 4.2), (-0.2, 3.9)])
    sk.fix(0)
    sk.add_horizontal(0, 1)
    sk.add_vertical(1, 2)
    sk.add_horizontal(2, 3)
    sk.add_vertical(3, 0)
    sk.add_distance(0, 1, 6.0)
    sk.add_distance(1, 2, 4.0)
    assert sk.solve()
    p0, p1, p2, p3 = sk.points
    assert math.isclose(p0[0], 0.0, abs_tol=1e-5) and math.isclose(p0[1], 0.0, abs_tol=1e-5)
    assert math.isclose(p1[0], 6.0, abs_tol=1e-5) and math.isclose(p1[1], 0.0, abs_tol=1e-5)
    assert math.isclose(p2[0], 6.0, abs_tol=1e-5) and math.isclose(p2[1], 4.0, abs_tol=1e-5)
    assert math.isclose(p3[0], 0.0, abs_tol=1e-5) and math.isclose(p3[1], 4.0, abs_tol=1e-5)


def test_constraint_solve_reports_false_when_contradictory():
    # Both points fixed 1 apart, but asked to be 5 apart -- nothing is
    # free to move, so the residual can't be driven to zero.
    sk = Sketch2D([(0, 0), (1, 0)])
    sk.fix(0)
    sk.fix(1)
    sk.add_distance(0, 1, 5.0)
    assert sk.solve() is False


def test_document_add_remove():
    doc = Document()
    box = primitives.make_box(1, 1, 1)
    obj = doc.add(box, "MyBox")
    assert obj.name == "MyBox"
    assert doc.get(obj.id) is obj
    doc.remove(obj)
    assert doc.get(obj.id) is None


def test_document_undo_redo():
    doc = Document()
    doc.snapshot()
    box = primitives.make_box(1, 1, 1)
    obj = doc.add(box)
    assert len(doc.objects) == 1

    doc.snapshot()
    doc.add(primitives.make_box(2, 2, 2))
    assert len(doc.objects) == 2

    assert doc.undo() is True
    assert len(doc.objects) == 1
    assert doc.objects[0].id == obj.id

    assert doc.undo() is True
    assert len(doc.objects) == 0
    assert doc.undo() is False

    assert doc.redo() is True
    assert len(doc.objects) == 1
    assert doc.redo() is True
    assert len(doc.objects) == 2
    assert doc.redo() is False


def test_document_replace_shape_does_not_mutate_snapshot():
    doc = Document()
    box = primitives.make_box(1, 1, 1)
    obj = doc.add(box)
    doc.snapshot()
    new_obj = doc.replace_shape(obj, primitives.make_box(5, 5, 5))
    assert math.isclose(volume_of(doc.objects[0].shape), 125.0, rel_tol=1e-6)
    doc.undo()
    assert math.isclose(volume_of(doc.objects[0].shape), 1.0, rel_tol=1e-6)


def test_translate_moves_bounding_volume_but_not_volume():
    box = primitives.make_box(2, 2, 2)
    moved = transform.translate(box, 10, 0, 0)
    assert math.isclose(volume_of(moved), volume_of(box), rel_tol=1e-6)


def test_rotate_preserves_volume():
    box = primitives.make_box(2, 3, 4)
    rotated = transform.rotate(box, 45)
    assert math.isclose(volume_of(rotated), volume_of(box), rel_tol=1e-6)


def test_duplicate_is_independent_shape():
    box = primitives.make_box(2, 2, 2)
    dup = transform.duplicate(box)
    assert math.isclose(volume_of(dup), volume_of(box), rel_tol=1e-6)
    assert dup is not box


def test_fillet_edge_reduces_volume_slightly():
    box = primitives.make_box(4, 4, 4)
    edge = first_edge(box)
    filleted = fillet.fillet_edge(box, edge, 0.5)
    assert volume_of(filleted) < volume_of(box)
    assert volume_of(filleted) > volume_of(box) * 0.9


def test_chamfer_edge_reduces_volume_slightly():
    box = primitives.make_box(4, 4, 4)
    edge = first_edge(box)
    chamfered = fillet.chamfer_edge(box, edge, 0.5)
    assert volume_of(chamfered) < volume_of(box)


def test_fillet_invalid_radius_raises():
    box = primitives.make_box(2, 2, 2)
    edge = first_edge(box)
    with pytest.raises(ValueError):
        fillet.fillet_edge(box, edge, -1)


def test_project_save_load_roundtrip(tmp_path):
    doc = Document()
    doc.add(primitives.make_box(1, 2, 3), "Box1")
    doc.add(primitives.make_cylinder(1, 5), "Cyl1")
    path = tmp_path / "test.dcadproj"
    project_io.save_project(doc, str(path))
    assert path.exists()

    loaded = project_io.load_project(str(path))
    assert [o.name for o in loaded.objects] == ["Box1", "Cyl1"]
    assert math.isclose(volume_of(loaded.objects[0].shape), volume_of(doc.objects[0].shape), rel_tol=1e-6)
    assert math.isclose(volume_of(loaded.objects[1].shape), volume_of(doc.objects[1].shape), rel_tol=1e-6)


def test_sketch_rectangle_extrude_volume():
    profile = sketch.rectangle_profile(0, 0, 2, 3)
    box = sketch.extrude(profile, 4)
    assert math.isclose(volume_of(box), 24.0, rel_tol=1e-6)


def test_sketch_rectangle_requires_nondegenerate_corners():
    with pytest.raises(ValueError):
        sketch.rectangle_profile(0, 0, 0, 5)


def test_sketch_circle_extrude_volume():
    profile = sketch.circle_profile(0, 0, 1)
    cyl = sketch.extrude(profile, 5)
    assert math.isclose(volume_of(cyl), math.pi * 1**2 * 5, rel_tol=1e-6)


def test_sketch_extrude_zero_height_raises():
    profile = sketch.circle_profile(0, 0, 1)
    with pytest.raises(ValueError):
        sketch.extrude(profile, 0)


def test_sketch_extrude_negative_height_still_produces_volume():
    profile = sketch.rectangle_profile(0, 0, 2, 2)
    box = sketch.extrude(profile, -3)
    assert math.isclose(volume_of(box), 12.0, rel_tol=1e-6)


def test_revolve_profile_full_turn_volume():
    profile = sketch.revolve_profile_rectangle(1, 0, 2, 3)
    ring = sketch.revolve(profile, 360)
    expected = math.pi * (2**2 - 1**2) * 3
    assert math.isclose(volume_of(ring), expected, rel_tol=1e-6)


def test_revolve_profile_half_turn_is_half_volume():
    profile = sketch.revolve_profile_rectangle(1, 0, 2, 3)
    full = sketch.revolve(profile, 360)
    half = sketch.revolve(profile, 180)
    assert math.isclose(volume_of(half), volume_of(full) / 2, rel_tol=1e-6)


def test_revolve_profile_invalid_radius_raises():
    with pytest.raises(ValueError):
        sketch.revolve_profile_rectangle(-1, 0, 2, 3)


def test_revolve_invalid_angle_raises():
    profile = sketch.revolve_profile_rectangle(1, 0, 2, 3)
    with pytest.raises(ValueError):
        sketch.revolve(profile, 400)


def test_rectangle_points_from_corners_xy_plane():
    pts = sketch.rectangle_points_from_corners((0, 0, 0), (2, 3, 0))
    assert pts == [(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 0)]


def test_rectangle_points_from_corners_xz_plane():
    pts = sketch.rectangle_points_from_corners((1, 0, 0), (2, 0, 3))
    assert pts == [(1, 0, 0), (2, 0, 0), (2, 0, 3), (1, 0, 3)]


def test_rectangle_points_from_corners_rejects_non_coplanar():
    with pytest.raises(ValueError):
        sketch.rectangle_points_from_corners((0, 0, 0), (1, 1, 1))


def test_polygon_profile_from_clicked_points_extrude_volume():
    pts = sketch.rectangle_points_from_corners((0, 0, 0), (2, 3, 0))
    profile = sketch.polygon_profile(pts)
    box = sketch.extrude(profile, 4)
    assert math.isclose(volume_of(box), 24.0, rel_tol=1e-6)


def test_polygon_profile_triangle_volume():
    tri = sketch.polygon_profile([(0, 0, 0), (4, 0, 0), (0, 3, 0)])
    solid = sketch.extrude(tri, 2)
    assert math.isclose(volume_of(solid), 0.5 * 4 * 3 * 2, rel_tol=1e-6)


def test_polygon_profile_requires_three_points():
    with pytest.raises(ValueError):
        sketch.polygon_profile([(0, 0, 0), (1, 0, 0)])


def test_circle_profile_3d_on_revolve_plane():
    profile = sketch.circle_profile_3d((2, 0, 1), (0, 1, 0), 0.5)
    solid = sketch.revolve(profile, 360)
    assert volume_of(solid) > 0


def test_circle_profile_3d_invalid_radius_raises():
    with pytest.raises(ValueError):
        sketch.circle_profile_3d((0, 0, 0), (0, 0, 1), -1)


def test_open_polyline_wire_shape_type():
    from OCP.TopAbs import TopAbs_WIRE

    wire = sketch.open_polyline_wire([(0, 0, 0), (1, 0, 0), (1, 1, 0)])
    assert wire.ShapeType() == TopAbs_WIRE


def test_open_polyline_wire_requires_two_points():
    with pytest.raises(ValueError):
        sketch.open_polyline_wire([(0, 0, 0)])


def test_measure_length_of_edge():
    box = primitives.make_box(2, 3, 4)
    edge = first_edge(box)
    assert math.isclose(measure.length_of_edge(edge), 4.0, rel_tol=1e-6)


def test_measure_area_of_face():
    box = primitives.make_box(2, 3, 4)
    face = first_face(box)
    assert math.isclose(measure.area_of_face(face), 12.0, rel_tol=1e-6)


def test_measure_volume_of_solid():
    box = primitives.make_box(2, 3, 4)
    assert math.isclose(measure.volume_of_solid(box), 24.0, rel_tol=1e-6)


def test_measure_distance_between_separated_boxes():
    a = primitives.make_box(1, 1, 1)
    b = transform.translate(primitives.make_box(1, 1, 1), 5, 0, 0)
    assert math.isclose(measure.distance_between(a, b), 4.0, rel_tol=1e-6)


def test_measure_distance_between_touching_boxes_is_zero():
    a = primitives.make_box(1, 1, 1)
    b = transform.translate(primitives.make_box(1, 1, 1), 1, 0, 0)
    assert math.isclose(measure.distance_between(a, b), 0.0, abs_tol=1e-9)


def test_measure_describe_edge_face_solid():
    box = primitives.make_box(2, 3, 4)
    assert measure.describe(first_edge(box)).startswith("Length")
    assert measure.describe(first_face(box)).startswith("Area")
    assert measure.describe(box).startswith("Volume")


def test_regular_polygon_profile_hexagon_area():
    hexagon = sketch.regular_polygon_profile((0, 0, 0), (2, 0, 0), (0, 0, 1), 6)
    expected = 0.5 * 6 * 2**2 * math.sin(2 * math.pi / 6)
    assert math.isclose(measure.area_of_face(hexagon), expected, rel_tol=1e-6)


def test_regular_polygon_profile_requires_three_sides():
    with pytest.raises(ValueError):
        sketch.regular_polygon_profile((0, 0, 0), (1, 0, 0), (0, 0, 1), 2)


def test_regular_polygon_profile_extrudes_to_expected_volume():
    hexagon = sketch.regular_polygon_profile((0, 0, 0), (2, 0, 0), (0, 0, 1), 6)
    solid = sketch.extrude(hexagon, 5)
    expected_area = 0.5 * 6 * 2**2 * math.sin(2 * math.pi / 6)
    assert math.isclose(volume_of(solid), expected_area * 5, rel_tol=1e-6)


def test_ellipse_profile_3d_area():
    ellipse = sketch.ellipse_profile_3d((0, 0, 0), (3, 0, 0), 1.5, (0, 0, 1))
    assert math.isclose(measure.area_of_face(ellipse), math.pi * 3 * 1.5, rel_tol=1e-6)


def test_ellipse_profile_3d_invalid_radius_raises():
    with pytest.raises(ValueError):
        sketch.ellipse_profile_3d((0, 0, 0), (3, 0, 0), 0, (0, 0, 1))


def test_three_point_circle_profile_area():
    circle = sketch.three_point_circle_profile((1, 0, 0), (0, 1, 0), (-1, 0, 0))
    assert math.isclose(measure.area_of_face(circle), math.pi * 1**2, rel_tol=1e-6)


def test_three_point_arc_segment_profile_half_circle_area():
    segment = sketch.three_point_arc_segment_profile((1, 0, 0), (0, 1, 0), (-1, 0, 0))
    assert math.isclose(measure.area_of_face(segment), 0.5 * math.pi * 1**2, rel_tol=1e-6)


def test_stitch_rebuilds_solid_from_exploded_faces():
    from OCP.TopAbs import TopAbs_SOLID

    box = primitives.make_box(2, 3, 4)
    stitched = repair.stitch(all_faces(box))
    assert stitched.ShapeType() == TopAbs_SOLID
    assert math.isclose(volume_of(stitched), 24.0, rel_tol=1e-6)


def test_fill_heals_a_removed_fillet_face():
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    box = primitives.make_box(4, 4, 4)
    filleted = fillet.fillet_edge(box, first_edge(box), 0.5)
    fillet_face = next(
        f for f in all_faces(filleted)
        if BRepAdaptor_Surface(f, True).GetType() == GeomAbs_Cylinder
    )
    healed = repair.fill_faces(filleted, [fillet_face])
    assert math.isclose(volume_of(healed), 64.0, rel_tol=1e-6)


def test_merge_faces_removes_redundant_coplanar_seams():
    box_a = primitives.make_box(4, 4, 2)
    box_b = transform.translate(primitives.make_box(4, 4, 4), 0, 0, 2)
    fused = booleans.union(box_a, box_b)
    assert face_count(fused) > 6, "fusing two stacked boxes should leave redundant seam faces"

    merged = repair.merge_faces(fused)
    assert face_count(merged) == 6
    assert math.isclose(volume_of(merged), 96.0, rel_tol=1e-6)


def test_check_interference_finds_overlapping_pair():
    a = primitives.make_box(4, 4, 4)
    b = transform.translate(primitives.make_box(4, 4, 4), 2, 2, 2)
    c = transform.translate(primitives.make_box(1, 1, 1), 100, 100, 100)
    hits = prepare.check_interference([a, b, c])
    assert len(hits) == 1
    i, j, volume = hits[0]
    assert (i, j) == (0, 1)
    assert math.isclose(volume, 8.0, rel_tol=1e-6)


def test_check_interference_no_overlap():
    a = primitives.make_box(1, 1, 1)
    b = transform.translate(primitives.make_box(1, 1, 1), 5, 0, 0)
    assert prepare.check_interference([a, b]) == []


def test_bounding_box_of_box_primitive():
    box = primitives.make_box(2, 3, 4)
    x0, y0, z0, x1, y1, z1 = prepare.bounding_box(box)
    assert math.isclose(x1 - x0, 2.0, abs_tol=1e-4)
    assert math.isclose(y1 - y0, 3.0, abs_tol=1e-4)
    assert math.isclose(z1 - z0, 4.0, abs_tol=1e-4)


def test_make_enclosure_volume():
    box = primitives.make_box(2, 2, 2)
    enclosure = prepare.make_enclosure([box], margin=1.0)
    assert math.isclose(volume_of(enclosure), 4**3 - 2**3, rel_tol=1e-3)


def test_make_enclosure_requires_positive_margin():
    box = primitives.make_box(2, 2, 2)
    with pytest.raises(ValueError):
        prepare.make_enclosure([box], margin=0)


def test_share_topology_preserves_total_volume():
    from OCP.TopAbs import TopAbs_COMPOUND

    a = primitives.make_box(2, 2, 2)
    b = transform.translate(primitives.make_box(2, 2, 2), 2, 0, 0)
    shared = prepare.share_topology([a, b])
    assert shared.ShapeType() == TopAbs_COMPOUND
    assert math.isclose(volume_of(shared), 16.0, rel_tol=1e-6)


def test_share_topology_requires_two_shapes():
    with pytest.raises(ValueError):
        prepare.share_topology([primitives.make_box(1, 1, 1)])


def test_explode_solids_recovers_individual_bodies():
    a = primitives.make_box(2, 2, 2)
    b = transform.translate(primitives.make_box(2, 2, 2), 2, 0, 0)
    shared = prepare.share_topology([a, b])
    solids = prepare.explode_solids(shared)
    assert len(solids) == 2
    assert math.isclose(sum(volume_of(s) for s in solids), 16.0, rel_tol=1e-6)

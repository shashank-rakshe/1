import math

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from dcad.kernel import primitives, booleans, direct_edit, io_step, transform, fillet, project_io, sketch, measure, repair, prepare
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

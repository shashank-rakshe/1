import math

import pytest
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from dcad.kernel import primitives, booleans, direct_edit, io_step
from dcad.kernel.document import Document


def volume_of(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def first_face(shape):
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    return TopoDS.Face_s(explorer.Current())


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

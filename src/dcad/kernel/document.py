"""In-memory document model: a flat collection of solids.

Kept independent of Qt/AIS so the kernel is testable headless; the
viewport layer mirrors this list into AIS presentations for display.
"""

from dataclasses import dataclass, field
from itertools import count

from OCP.TopoDS import TopoDS_Shape

_ids = count(1)


@dataclass
class DocObject:
    id: int
    shape: TopoDS_Shape
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"Solid{self.id}"


class Document:
    def __init__(self):
        self.objects: list[DocObject] = []

    def add(self, shape: TopoDS_Shape, name: str = "") -> DocObject:
        obj = DocObject(id=next(_ids), shape=shape, name=name)
        self.objects.append(obj)
        return obj

    def remove(self, obj: DocObject) -> None:
        self.objects.remove(obj)

    def replace_shape(self, obj: DocObject, new_shape: TopoDS_Shape) -> None:
        obj.shape = new_shape

    def get(self, obj_id: int) -> DocObject | None:
        return next((o for o in self.objects if o.id == obj_id), None)

    def clear(self) -> None:
        self.objects.clear()

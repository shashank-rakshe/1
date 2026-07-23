"""In-memory document model: a flat collection of solids, with undo/redo.

Kept independent of Qt/AIS so the kernel is testable headless; the
viewport layer mirrors this list into AIS presentations for display.
"""

from dataclasses import dataclass
from itertools import count

from OCP.TopoDS import TopoDS_Shape

_ids = count(1)


@dataclass(frozen=True)
class DocObject:
    id: int
    shape: TopoDS_Shape
    name: str = ""
    group_path: tuple[str, ...] = ()  # ancestor assembly names, from STEP import

    def __post_init__(self):
        if not self.name:
            object.__setattr__(self, "name", f"Solid{self.id}")


class Document:
    """Objects are immutable `DocObject`s; mutations replace list entries
    rather than editing them in place, so undo/redo snapshots (plain list
    copies) stay valid without deep-copying geometry."""

    def __init__(self):
        self.objects: list[DocObject] = []
        self._undo_stack: list[list[DocObject]] = []
        self._redo_stack: list[list[DocObject]] = []

    def snapshot(self) -> None:
        """Record the current state for undo, before a mutation. Clears redo."""
        self._undo_stack.append(list(self.objects))
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(list(self.objects))
        self.objects = self._undo_stack.pop()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(list(self.objects))
        self.objects = self._redo_stack.pop()
        return True

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def add(self, shape: TopoDS_Shape, name: str = "", group_path: tuple[str, ...] = ()) -> DocObject:
        obj = DocObject(id=next(_ids), shape=shape, name=name, group_path=group_path)
        self.objects.append(obj)
        return obj

    def remove(self, obj: DocObject) -> None:
        self.objects.remove(obj)

    def replace_shape(self, obj: DocObject, new_shape: TopoDS_Shape) -> DocObject:
        idx = self.objects.index(obj)
        new_obj = DocObject(id=obj.id, shape=new_shape, name=obj.name, group_path=obj.group_path)
        self.objects[idx] = new_obj
        return new_obj

    def get(self, obj_id: int) -> DocObject | None:
        return next((o for o in self.objects if o.id == obj_id), None)

    def clear(self) -> None:
        self.objects.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()

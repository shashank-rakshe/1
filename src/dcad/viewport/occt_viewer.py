"""Thin wrapper around the OCCT 3D viewer/selection stack (no Qt here)."""

from OCP.Aspect import Aspect_DisplayConnection, Aspect_TypeOfTriedronPosition
from OCP.OpenGl import OpenGl_GraphicDriver
from OCP.V3d import V3d_Viewer, V3d_View
from OCP.AIS import AIS_InteractiveContext, AIS_Shape
from OCP.Xw import Xw_Window
from OCP.Quantity import Quantity_Color, Quantity_NOC_GRAY20, Quantity_NOC_BLACK
from OCP.Graphic3d import Graphic3d_NameOfMaterial, Graphic3d_MaterialAspect
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHAPE, TopAbs_EDGE
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax3

MODE_SOLID = AIS_Shape.SelectionMode_s(TopAbs_SHAPE)
MODE_FACE = AIS_Shape.SelectionMode_s(TopAbs_FACE)
MODE_EDGE = AIS_Shape.SelectionMode_s(TopAbs_EDGE)

PREVIEW_ID = -1


class OcctViewer:
    """Owns the OCCT display connection, viewer, and interactive context.

    Qt widgets bind their native window id via `bind_window()`; the widget
    is responsible for forwarding resize/paint/input events.
    """

    def __init__(self):
        self.display_connection = Aspect_DisplayConnection()
        self.driver = OpenGl_GraphicDriver(self.display_connection)
        self.viewer = V3d_Viewer(self.driver)
        self.viewer.SetDefaultLights()
        self.viewer.SetLightOn()
        self.context = AIS_InteractiveContext(self.viewer)
        self.view: V3d_View | None = None
        self._ais_by_shape_id: dict[int, AIS_Shape] = {}
        self._pick_mode = MODE_SOLID
        self._sketch_plane_point = (0.0, 0.0, 0.0)
        self._sketch_plane_normal = (0.0, 0.0, 1.0)

    def bind_window(self, window_id: int, width: int, height: int) -> None:
        self.view = self.viewer.CreateView()
        window = Xw_Window(self.display_connection, window_id)
        if not window.IsMapped():
            window.Map()
        self.view.SetWindow(window)
        self.view.SetBackgroundColor(Quantity_Color(Quantity_NOC_GRAY20))
        self.view.TriedronDisplay(Aspect_TypeOfTriedronPosition.Aspect_TOTP_LEFT_LOWER, Quantity_Color(Quantity_NOC_BLACK), 0.1)
        self.view.MustBeResized()
        self.view.SetProj(1, -1, 1)

    def resize(self) -> None:
        if self.view is not None:
            self.view.MustBeResized()

    def redraw(self) -> None:
        if self.view is not None:
            self.view.Redraw()

    def fit_all(self) -> None:
        if self.view is not None:
            self.view.FitAll()
            self.view.ZFitAll()

    def display_shape(self, shape_id: int, shape: TopoDS_Shape, material=Graphic3d_NameOfMaterial.Graphic3d_NOM_PLASTIC) -> AIS_Shape:
        ais = AIS_Shape(shape)
        ais.SetMaterial(Graphic3d_MaterialAspect(material))
        self.context.Display(ais, False)
        self.context.SetDisplayMode(ais, 1, False)
        self.context.Deactivate(ais)
        self.context.Activate(ais, self._pick_mode)
        self._ais_by_shape_id[shape_id] = ais
        return ais

    def redisplay_shape(self, shape_id: int, shape: TopoDS_Shape) -> AIS_Shape:
        self.remove_shape(shape_id)
        return self.display_shape(shape_id, shape)

    def remove_shape(self, shape_id: int) -> None:
        ais = self._ais_by_shape_id.pop(shape_id, None)
        if ais is not None:
            self.context.Remove(ais, True)

    def ais_for(self, shape_id: int) -> AIS_Shape | None:
        return self._ais_by_shape_id.get(shape_id)

    def clear_all(self) -> None:
        for shape_id in list(self._ais_by_shape_id):
            self.remove_shape(shape_id)

    def set_pick_mode(self, mode: int) -> None:
        """Switch the active selection granularity (MODE_SOLID or MODE_FACE)."""
        if mode == self._pick_mode:
            return
        self._pick_mode = mode
        for ais in self._ais_by_shape_id.values():
            self.context.Deactivate(ais)
            self.context.Activate(ais, mode)

    def set_sketch_plane(self, plane: gp_Ax3) -> None:
        """Set the plane that `screen_to_plane_point` projects clicks onto."""
        loc = plane.Location()
        direction = plane.Direction()
        self._sketch_plane_point = (loc.X(), loc.Y(), loc.Z())
        self._sketch_plane_normal = (direction.X(), direction.Y(), direction.Z())

    def screen_to_plane_point(self, x: int, y: int) -> tuple:
        """Project a screen pixel onto the current sketch plane, returning
        the (X, Y, Z) world point where the view ray through that pixel
        intersects it.

        V3d_View.Convert()/ConvertToGrid() project onto an internal view
        plane that doesn't track `Viewer.SetPrivilegedPlane()` the way its
        docs suggest, so the sketch plane is intersected manually here
        instead: ConvertWithProj gives a point on the pick ray plus its
        direction, and the plane is stored explicitly by `set_sketch_plane`.
        """
        px, py, pz, vx, vy, vz = self.view.ConvertWithProj(x, y)
        ox, oy, oz = self._sketch_plane_point
        nx, ny, nz = self._sketch_plane_normal
        denom = vx * nx + vy * ny + vz * nz
        if abs(denom) < 1e-12:
            return (px, py, pz)
        t = ((ox - px) * nx + (oy - py) * ny + (oz - pz) * nz) / denom
        return (px + t * vx, py + t * vy, pz + t * vz)

    def set_preview(self, shape: TopoDS_Shape | None) -> None:
        """Show (or clear, if `shape` is None) a temporary, non-document
        preview shape -- used for live rubber-band feedback while sketching."""
        if shape is None:
            self.remove_shape(PREVIEW_ID)
        else:
            self.redisplay_shape(PREVIEW_ID, shape)

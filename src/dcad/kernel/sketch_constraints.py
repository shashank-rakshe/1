"""2D sketch constraint solver -- SpaceClaim's Sketch tab constraint
icons (Horizontal, Vertical, Distance, Parallel, Perpendicular, Equal,
Coincident, Angle) as a small least-squares solver over point
coordinates. This is what separates "click to draw" from a real
parametric sketch: dragging a point, or editing a dimension, re-solves
every other point to keep all constraints satisfied.

Deliberately independent of OCCT -- it operates on plain (x, y) pairs
before they become a wire/face, and works equally for any sketch plane
(the caller decides which two of a 3D point's three coordinates to feed
in, and maps the solved 2D result back)."""

import numpy as np


class Sketch2D:
    """A mutable set of 2D points plus constraints between them. solve()
    adjusts every non-fixed point to satisfy the constraints as closely
    as possible, via Gauss-Newton least squares with a numerical
    Jacobian (points are few enough per sketch that this is cheap, and
    it sidesteps hand-deriving per-constraint analytic derivatives)."""

    def __init__(self, points):
        self.points = [list(map(float, p)) for p in points]
        self.fixed = set()
        self.constraints = []

    def fix(self, index: int) -> None:
        """Mark a point's position as not to be moved by solve() -- every
        sketch needs at least one anchor, or the whole thing can drift/
        rotate freely and still satisfy every relative constraint."""
        self.fixed.add(index)

    def add_coincident(self, i: int, j: int) -> None:
        self.constraints.append(("coincident", i, j))

    def add_horizontal(self, i: int, j: int) -> None:
        self.constraints.append(("horizontal", i, j))

    def add_vertical(self, i: int, j: int) -> None:
        self.constraints.append(("vertical", i, j))

    def add_distance(self, i: int, j: int, distance: float) -> None:
        self.constraints.append(("distance", i, j, distance))

    def add_parallel(self, i: int, j: int, k: int, l: int) -> None:
        """Segment (i,j) parallel to segment (k,l)."""
        self.constraints.append(("parallel", i, j, k, l))

    def add_perpendicular(self, i: int, j: int, k: int, l: int) -> None:
        self.constraints.append(("perpendicular", i, j, k, l))

    def add_equal_length(self, i: int, j: int, k: int, l: int) -> None:
        self.constraints.append(("equal_length", i, j, k, l))

    def add_angle(self, i: int, j: int, k: int, l: int, angle_deg: float) -> None:
        """Angle from segment (i,j) to segment (k,l), measured the same
        way as atan2 (signed, -180..180)."""
        self.constraints.append(("angle", i, j, k, l, angle_deg))

    def _residuals(self, flat: np.ndarray) -> np.ndarray:
        pts = flat.reshape(-1, 2)
        residuals = []
        for constraint in self.constraints:
            kind = constraint[0]
            if kind == "coincident":
                _, i, j = constraint
                residuals.extend(pts[i] - pts[j])
            elif kind == "horizontal":
                _, i, j = constraint
                residuals.append(pts[i, 1] - pts[j, 1])
            elif kind == "vertical":
                _, i, j = constraint
                residuals.append(pts[i, 0] - pts[j, 0])
            elif kind == "distance":
                _, i, j, distance = constraint
                residuals.append(np.hypot(*(pts[j] - pts[i])) - distance)
            elif kind == "parallel":
                _, i, j, k, l = constraint
                d1, d2 = pts[j] - pts[i], pts[l] - pts[k]
                residuals.append(d1[0] * d2[1] - d1[1] * d2[0])  # cross
            elif kind == "perpendicular":
                _, i, j, k, l = constraint
                d1, d2 = pts[j] - pts[i], pts[l] - pts[k]
                residuals.append(d1[0] * d2[0] + d1[1] * d2[1])  # dot
            elif kind == "equal_length":
                _, i, j, k, l = constraint
                residuals.append(np.hypot(*(pts[j] - pts[i])) - np.hypot(*(pts[l] - pts[k])))
            elif kind == "angle":
                _, i, j, k, l, angle_deg = constraint
                d1, d2 = pts[j] - pts[i], pts[l] - pts[k]
                cross = d1[0] * d2[1] - d1[1] * d2[0]
                dot = d1[0] * d2[0] + d1[1] * d2[1]
                residuals.append(np.arctan2(cross, dot) - np.radians(angle_deg))
            else:
                raise ValueError(f"unknown constraint kind {kind!r}")
        return np.array(residuals, dtype=float)

    def _jacobian(self, flat: np.ndarray, free_idx: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        r0 = self._residuals(flat)
        jac = np.zeros((len(r0), len(free_idx)))
        for col, var in enumerate(free_idx):
            flat[var] += eps
            r_plus = self._residuals(flat)
            flat[var] -= 2 * eps
            r_minus = self._residuals(flat)
            flat[var] += eps
            jac[:, col] = (r_plus - r_minus) / (2 * eps)
        return jac

    def solve(self, max_iter: int = 50, tol: float = 1e-9) -> bool:
        """Adjust every non-fixed point to satisfy the constraints.
        Returns whether it converged (residual norm below `tol`) --
        an over-constrained or contradictory set of constraints won't,
        and `self.points` is left at its best (least-squares) effort."""
        flat = np.array(self.points, dtype=float).flatten()
        fixed_vars = {2 * i for i in self.fixed} | {2 * i + 1 for i in self.fixed}
        free_idx = np.array([v for v in range(len(flat)) if v not in fixed_vars])

        if not self.constraints or len(free_idx) == 0:
            self.points = flat.reshape(-1, 2).tolist()
            return len(self._residuals(flat)) == 0 or bool(np.linalg.norm(self._residuals(flat)) < tol)

        for _ in range(max_iter):
            residual = self._residuals(flat)
            if np.linalg.norm(residual) < tol:
                break
            jacobian = self._jacobian(flat, free_idx)
            delta, *_ = np.linalg.lstsq(jacobian, -residual, rcond=None)
            flat[free_idx] += delta

        self.points = flat.reshape(-1, 2).tolist()
        return bool(np.linalg.norm(self._residuals(flat)) < 1e-6)

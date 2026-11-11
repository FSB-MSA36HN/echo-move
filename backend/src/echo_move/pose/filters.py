"""One-Euro filter (Casiez et al., 2012) for keypoint smoothing."""

from __future__ import annotations

import math

Keypoint = list[float]  # [x, y, confidence]


class OneEuro:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x: float | None = None
        self._dx = 0.0
        self._t: float | None = None

    def __call__(self, x: float, t: float) -> float:
        if self._t is None or self._x is None:
            self._t, self._x, self._dx = t, x, 0.0
            return x
        dt = max(t - self._t, 1e-3)
        a_d = 1.0 / (1.0 + self.d_cutoff / (2 * math.pi * dt))
        dx_hat = a_d * (x - self._x) / dt + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = 1.0 / (1.0 + cutoff / (2 * math.pi * dt))
        x_hat = a * x + (1 - a) * self._x
        self._t, self._x, self._dx = t, x_hat, dx_hat
        return x_hat


class KeypointSmoother:
    """Smooths 17 COCO keypoints of one person; resets after a time gap."""

    MAX_GAP_S = 1.0

    def __init__(self, n_points: int = 17, conf_threshold: float = 0.3):
        self.conf_threshold = conf_threshold
        self._fx = [OneEuro() for _ in range(n_points)]
        self._fy = [OneEuro() for _ in range(n_points)]
        self._last_t: float | None = None

    def reset(self) -> None:
        for f in (*self._fx, *self._fy):
            f.reset()
        self._last_t = None

    def apply(self, keypoints: list[Keypoint], t: float) -> list[Keypoint]:
        if self._last_t is not None and not (0 <= t - self._last_t <= self.MAX_GAP_S):
            self.reset()
        self._last_t = t
        out: list[Keypoint] = []
        for i, (x, y, c) in enumerate(keypoints):
            if c > self.conf_threshold:
                out.append([self._fx[i](x, t), self._fy[i](y, t), c])
            else:
                out.append([x, y, c])
        return out

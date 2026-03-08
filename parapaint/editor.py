from __future__ import annotations

import json
import os
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Iterable, List, Optional, Sequence, Set, Tuple

from .oklab import rgb_to_hex

Color = Tuple[int, int, int, int]
Point = Tuple[int, int]


TRANSPARENT: Color = (0, 0, 0, 0)
DEFAULT_PALETTE = [
    (0, 0, 0, 255),
    (255, 255, 255, 255),
    (127, 127, 127, 255),
    (255, 0, 0, 255),
    (255, 170, 0, 255),
    (255, 255, 0, 255),
    (0, 180, 0, 255),
    (0, 170, 255, 255),
    (0, 0, 255, 255),
    (180, 0, 255, 255),
    (255, 0, 255, 255),
    (255, 110, 170, 255),
]
ZOOM_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1500, 2000, 2500, 3000, 3500, 4000]
BRUSH_SHAPES = {
    "Point": [(0, 0)],
    "Plus": [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)],
    "Square": [(dx, dy) for dy in range(-1, 2) for dx in range(-1, 2)],
    "Big Square": [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3)],
    "Circle": [(dx, dy) for dy in range(-1, 2) for dx in range(-1, 2) if dx * dx + dy * dy <= 2],
    "Big Circle": [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if dx * dx + dy * dy <= 4],
    "Diag /": [(-1, 1), (0, 0), (1, -1)],
    "Diag \\": [(-1, -1), (0, 0), (1, 1)],
}


@dataclass
class Layer:
    name: str
    visible: bool = True
    pixels: List[List[Color]] = field(default_factory=list)

    def clone(self) -> "Layer":
        return Layer(self.name, self.visible, [[pixel for pixel in row] for row in self.pixels])


@dataclass
class Snapshot:
    width: int
    height: int
    layers: List[Layer]
    active_layer: int
    selection: Set[Point]


class PixelDocument:
    def __init__(self, width: int = 32, height: int = 32) -> None:
        self.width = width
        self.height = height
        self.layers: List[Layer] = [Layer("Layer 1", pixels=self._blank_pixels(width, height))]
        self.active_layer = 0
        self.selection: Set[Point] = set()
        self.dirty = False
        self.file_path: Optional[str] = None
        self.undo_stack: Deque[Snapshot] = deque(maxlen=50)
        self.redo_stack: Deque[Snapshot] = deque(maxlen=50)
        self.autosave_path = os.path.join(tempfile.gettempdir(), "parapaint_autosave.json")

    @staticmethod
    def _blank_pixels(width: int, height: int) -> List[List[Color]]:
        return [[TRANSPARENT for _ in range(width)] for _ in range(height)]

    def create_snapshot(self) -> Snapshot:
        return Snapshot(
            self.width,
            self.height,
            [layer.clone() for layer in self.layers],
            self.active_layer,
            set(self.selection),
        )

    def _restore_snapshot(self, snapshot: Snapshot) -> None:
        self.width = snapshot.width
        self.height = snapshot.height
        self.layers = [layer.clone() for layer in snapshot.layers]
        self.active_layer = snapshot.active_layer
        self.selection = set(snapshot.selection)
        self.dirty = True

    def commit_history(self) -> None:
        self.undo_stack.append(self.create_snapshot())
        self.redo_stack.clear()
        self.dirty = True

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        current = self.create_snapshot()
        previous = self.undo_stack.pop()
        self.redo_stack.append(current)
        self._restore_snapshot(previous)
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        current = self.create_snapshot()
        upcoming = self.redo_stack.pop()
        self.undo_stack.append(current)
        self._restore_snapshot(upcoming)
        return True

    def add_layer(self, name: Optional[str] = None) -> None:
        if name is None:
            name = f"Layer {len(self.layers) + 1}"
        self.layers.insert(0, Layer(name, pixels=self._blank_pixels(self.width, self.height)))
        self.active_layer = 0
        self.dirty = True

    def toggle_layer_visibility(self, index: int) -> None:
        self.layers[index].visible = not self.layers[index].visible
        self.dirty = True

    def set_active_layer(self, index: int) -> None:
        self.active_layer = index

    def move_layer(self, old_index: int, new_index: int) -> None:
        layer = self.layers.pop(old_index)
        self.layers.insert(new_index, layer)
        self.active_layer = new_index
        self.dirty = True

    def merged_pixel(self, x: int, y: int) -> Color:
        color = TRANSPARENT
        for layer in reversed(self.layers):
            if not layer.visible:
                continue
            pixel = layer.pixels[y][x]
            if pixel[3] > 0:
                color = pixel
        return color

    def get_pixel(self, x: int, y: int, layer_index: Optional[int] = None) -> Color:
        if layer_index is None:
            layer_index = self.active_layer
        return self.layers[layer_index].pixels[y][x]

    def set_pixel(self, x: int, y: int, color: Color, layer_index: Optional[int] = None) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        if layer_index is None:
            layer_index = self.active_layer
        self.layers[layer_index].pixels[y][x] = color

    def apply_points(self, points: Iterable[Point], color: Color) -> None:
        for x, y in points:
            if 0 <= x < self.width and 0 <= y < self.height:
                self.set_pixel(x, y, color)

    def draw_line(self, start: Point, end: Point) -> List[Point]:
        x1, y1 = start
        x2, y2 = end
        points: List[Point] = []
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        while True:
            points.append((x1, y1))
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x1 += sx
            if e2 <= dx:
                err += dx
                y1 += sy
        return points

    def draw_rect(self, start: Point, end: Point) -> List[Point]:
        x1, y1 = start
        x2, y2 = end
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        points: Set[Point] = set()
        for x in range(left, right + 1):
            points.add((x, top))
            points.add((x, bottom))
        for y in range(top, bottom + 1):
            points.add((left, y))
            points.add((right, y))
        return list(points)

    def draw_ellipse(self, start: Point, end: Point) -> List[Point]:
        x1, y1 = start
        x2, y2 = end
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        rx = max((right - left) / 2.0, 0.5)
        ry = max((bottom - top) / 2.0, 0.5)
        cx = left + rx
        cy = top + ry
        points: Set[Point] = set()
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                nx = (x - cx) / rx
                ny = (y - cy) / ry
                distance = nx * nx + ny * ny
                if 0.72 <= distance <= 1.28:
                    points.add((x, y))
        return list(points)

    def flood_fill(self, start: Point, replacement: Color) -> List[Point]:
        x, y = start
        target = self.get_pixel(x, y)
        if target == replacement:
            return []
        queue = deque([start])
        visited: Set[Point] = {start}
        filled: List[Point] = []
        while queue:
            px, py = queue.popleft()
            if self.get_pixel(px, py) != target:
                continue
            filled.append((px, py))
            for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                if 0 <= nx < self.width and 0 <= ny < self.height and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        return filled

    def contiguous_same_color(self, start: Point, color: Optional[Color] = None) -> Set[Point]:
        x, y = start
        target = color or self.merged_pixel(x, y)
        queue = deque([start])
        visited: Set[Point] = {start}
        selected: Set[Point] = set()
        while queue:
            px, py = queue.popleft()
            if self.merged_pixel(px, py) != target:
                continue
            selected.add((px, py))
            for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                if 0 <= nx < self.width and 0 <= ny < self.height and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        return selected

    def all_same_color(self, start: Point, color: Optional[Color] = None) -> Set[Point]:
        x, y = start
        target = color or self.merged_pixel(x, y)
        return {
            (px, py)
            for py in range(self.height)
            for px in range(self.width)
            if self.merged_pixel(px, py) == target
        }

    def select_rect(self, start: Point, end: Point) -> Set[Point]:
        x1, y1 = start
        x2, y2 = end
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return {(x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)}

    def update_selection(self, points: Set[Point], mode: str = "replace") -> None:
        if mode == "add":
            self.selection |= points
        elif mode == "subtract":
            self.selection -= points
        else:
            self.selection = set(points)
        self.dirty = True

    def clear_selection(self) -> None:
        self.selection.clear()
        self.dirty = True

    def delete_selection(self) -> None:
        if not self.selection:
            return
        for x, y in self.selection:
            self.set_pixel(x, y, TRANSPARENT)
        self.dirty = True

    def crop_to_selection(self) -> bool:
        if not self.selection:
            return False
        xs = [x for x, _ in self.selection]
        ys = [y for _, y in self.selection]
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        self.resize_canvas(right - left + 1, bottom - top + 1, offset_x=-left, offset_y=-top)
        self.selection = {(x - left, y - top) for x, y in self.selection}
        self.dirty = True
        return True

    def resize_canvas(self, width: int, height: int, offset_x: int = 0, offset_y: int = 0) -> None:
        new_layers: List[Layer] = []
        for layer in self.layers:
            new_pixels = self._blank_pixels(width, height)
            for y in range(self.height):
                for x in range(self.width):
                    nx = x + offset_x
                    ny = y + offset_y
                    if 0 <= nx < width and 0 <= ny < height:
                        new_pixels[ny][nx] = layer.pixels[y][x]
            new_layers.append(Layer(layer.name, layer.visible, new_pixels))
        self.width = width
        self.height = height
        self.layers = new_layers
        self.selection = {(x + offset_x, y + offset_y) for x, y in self.selection if 0 <= x + offset_x < width and 0 <= y + offset_y < height}
        self.dirty = True

    def serialize(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "active_layer": self.active_layer,
            "layers": [
                {
                    "name": layer.name,
                    "visible": layer.visible,
                    "pixels": layer.pixels,
                }
                for layer in self.layers
            ],
            "selection": list(self.selection),
            "timestamp": time.time(),
        }

    def autosave(self) -> str:
        path = Path(self.autosave_path)
        path.write_text(json.dumps(self.serialize()), encoding="utf-8")
        return str(path)

    def export_to_photoimage(self, photoimage) -> None:
        rows = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                r, g, b, a = self.merged_pixel(x, y)
                if a == 0:
                    row.append("#ffffff")
                else:
                    row.append(rgb_to_hex((r, g, b)))
            rows.append("{" + " ".join(row) + "}")
        photoimage.put(" ".join(rows))

    def import_from_photoimage(self, photoimage) -> None:
        width = photoimage.width()
        height = photoimage.height()
        self.width = width
        self.height = height
        self.layers = [Layer("Layer 1", pixels=self._blank_pixels(width, height))]
        self.active_layer = 0
        for y in range(height):
            for x in range(width):
                pixel = photoimage.get(x, y)
                if isinstance(pixel, tuple):
                    r, g, b = pixel[:3]
                else:
                    if pixel.startswith("#"):
                        pixel = pixel.lstrip("#")
                        r, g, b = int(pixel[0:2], 16), int(pixel[2:4], 16), int(pixel[4:6], 16)
                    else:
                        r, g, b = 255, 255, 255
                self.layers[0].pixels[y][x] = (r, g, b, 255)
        self.selection.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False

    def colors_on_canvas(self) -> Sequence[Color]:
        seen = []
        lookup = set()
        for y in range(self.height):
            for x in range(self.width):
                pixel = self.merged_pixel(x, y)
                if pixel not in lookup and pixel[3] > 0:
                    lookup.add(pixel)
                    seen.append(pixel)
        return seen

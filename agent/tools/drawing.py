import time
import math
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from agent.tools.base import BaseTool
from agent.core import win32_utils
from agent.core.vision import SCREEN_OBSERVER, verify_visual_change

class DrawLineTool(BaseTool):
    """
    Draws a single continuous line stroke inside a graphical application (e.g. Paint).
    Uses distance-interpolated mouse drag and performs before/after visual verification.
    """
    @property
    def name(self) -> str:
        return "draw_line"

    @property
    def description(self) -> str:
        return "Draws a line stroke from (start_x, start_y) to (end_x, end_y) in a canvas window with visual pixel verification."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def required_scope(self) -> str:
        return "computer.mouse"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer", "description": "Starting X coordinate (canvas/content space)"},
                "start_y": {"type": "integer", "description": "Starting Y coordinate (canvas/content space)"},
                "end_x": {"type": "integer", "description": "Ending X coordinate (canvas/content space)"},
                "end_y": {"type": "integer", "description": "Ending Y coordinate (canvas/content space)"},
                "target_window": {"type": "string", "description": "Target application name (default: 'Paint')", "default": "Paint"},
                "coordinate_space": {"type": "string", "enum": ["content", "canvas", "window", "screenshot", "screen"], "default": "content"},
                "duration_ms": {"type": "integer", "description": "Drag duration in milliseconds", "default": 250}
            },
            "required": ["start_x", "start_y", "end_x", "end_y"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target_window = arguments.get("target_window", "Paint")
        coord_space = arguments.get("coordinate_space", "content")
        duration_ms = arguments.get("duration_ms", 250)

        # 1. Resolve coordinates
        resolved_ok, coords, err = win32_utils.resolve_coordinates({
            "target_window": target_window,
            "coordinate_space": coord_space,
            "start_x": arguments.get("start_x", 0),
            "start_y": arguments.get("start_y", 0),
            "end_x": arguments.get("end_x", 0),
            "end_y": arguments.get("end_y", 0)
        })
        if not resolved_ok or not coords:
            return {
                "success": False,
                "action_success": False,
                "result_success": False,
                "error": err or "Failed to resolve line coordinates"
            }

        sx, sy = coords["start_x"], coords["start_y"]
        ex, ey = coords["end_x"], coords["end_y"]

        # 2. Capture baseline physical image before stroke
        img_before = SCREEN_OBSERVER.capture_image()
        win_before = win32_utils.get_active_window_details()

        # 3. Execute atomic drag
        drag_ok = win32_utils.mouse_drag(sx, sy, ex, ey, duration_ms=duration_ms)
        await asyncio.sleep(0.2)

        # 4. Capture physical image after stroke
        img_after = SCREEN_OBSERVER.capture_image()
        win_after = win32_utils.get_active_window_details()

        # 5. Visual verification on crop bounding box
        dist = math.hypot(ex - sx, ey - sy)
        min_pixels = max(4, min(15, int(dist * 0.05)))
        crop_bbox = (min(sx, ex) - 45, min(sy, ey) - 45, max(sx, ex) + 45, max(sy, ey) + 45)
        ver = verify_visual_change(img_before, img_after, region_bbox=crop_bbox, min_changed_pixels=min_pixels)

        result_success = (ver["verification_status"] == "verified_success")

        return {
            "success": result_success if drag_ok else False,
            "action_success": bool(drag_ok),
            "result_success": result_success,
            "verification_status": ver["verification_status"],
            "pixels_changed": ver["pixels_changed"],
            "coordinates_used": {"start_x": sx, "start_y": sy, "end_x": ex, "end_y": ey},
            "target_window_before": win_before,
            "target_window_after": win_after,
            "visual_verification": ver,
            "error": None if result_success else ("Visual verification failed: No visible stroke appeared on canvas." if drag_ok else "Mouse drag aborted.")
        }


class DrawPolylineTool(BaseTool):
    """
    Draws a sequence of connected line segments across a list of coordinate points.
    """
    @property
    def name(self) -> str:
        return "draw_polyline"

    @property
    def description(self) -> str:
        return "Draws connected line segments through a sequence of 2D points [[x1, y1], [x2, y2], ...] in a canvas window."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def required_scope(self) -> str:
        return "computer.mouse"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                    "description": "List of 2D coordinate pairs [[x1, y1], [x2, y2], ...]"
                },
                "closed": {"type": "boolean", "description": "If True, connects the last point back to the first point", "default": False},
                "target_window": {"type": "string", "default": "Paint"},
                "coordinate_space": {"type": "string", "enum": ["content", "canvas", "window", "screenshot", "screen"], "default": "content"}
            },
            "required": ["points"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_points = arguments.get("points", [])
        if len(raw_points) < 2:
            return {"success": False, "action_success": False, "result_success": False, "error": "Polyline requires at least 2 points"}

        target_window = arguments.get("target_window", "Paint")
        coord_space = arguments.get("coordinate_space", "content")
        closed = bool(arguments.get("closed", False))

        pts = list(raw_points)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])

        img_before = SCREEN_OBSERVER.capture_image()
        win_before = win32_utils.get_active_window_details()

        total_segments = len(pts) - 1
        executed_segments = 0
        all_resolved = []

        for i in range(total_segments):
            p1 = pts[i]
            p2 = pts[i + 1]
            resolved_ok, coords, err = win32_utils.resolve_coordinates({
                "target_window": target_window,
                "coordinate_space": coord_space,
                "start_x": p1[0],
                "start_y": p1[1],
                "end_x": p2[0],
                "end_y": p2[1]
            })
            if not resolved_ok or not coords:
                return {"success": False, "action_success": False, "result_success": False, "error": f"Failed resolving point {i} to {i+1}: {err}"}

            all_resolved.append(coords)
            drag_ok = win32_utils.mouse_drag(coords["start_x"], coords["start_y"], coords["end_x"], coords["end_y"], duration_ms=200)
            if not drag_ok:
                break
            executed_segments += 1
            await asyncio.sleep(0.08)

        await asyncio.sleep(0.2)
        img_after = SCREEN_OBSERVER.capture_image()
        win_after = win32_utils.get_active_window_details()

        # Compute bounding box of all points
        all_x = [c["start_x"] for c in all_resolved] + [c["end_x"] for c in all_resolved]
        all_y = [c["start_y"] for c in all_resolved] + [c["end_y"] for c in all_resolved]
        bbox = (min(all_x) - 30, min(all_y) - 30, max(all_x) + 30, max(all_y) + 30)

        ver = verify_visual_change(img_before, img_after, region_bbox=bbox, min_changed_pixels=30 * total_segments)
        result_success = (ver["verification_status"] == "verified_success") and (executed_segments == total_segments)

        return {
            "success": result_success,
            "action_success": executed_segments == total_segments,
            "result_success": result_success,
            "segments_executed": f"{executed_segments}/{total_segments}",
            "verification_status": ver["verification_status"],
            "pixels_changed": ver["pixels_changed"],
            "visual_verification": ver,
            "target_window_before": win_before,
            "target_window_after": win_after,
            "error": None if result_success else "Polyline visual verification failed."
        }


class DrawRectangleTool(BaseTool):
    """
    Draws a rectangle on a canvas with coordinates (x, y, width, height).
    """
    @property
    def name(self) -> str:
        return "draw_rectangle"

    @property
    def description(self) -> str:
        return "Draws a rectangle on the canvas using (x, y, width, height) coordinates."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def required_scope(self) -> str:
        return "computer.mouse"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Top-left X coordinate in canvas space"},
                "y": {"type": "integer", "description": "Top-left Y coordinate in canvas space"},
                "width": {"type": "integer", "description": "Rectangle width in pixels"},
                "height": {"type": "integer", "description": "Rectangle height in pixels"},
                "target_window": {"type": "string", "default": "Paint"},
                "coordinate_space": {"type": "string", "enum": ["content", "canvas", "window", "screenshot", "screen"], "default": "content"}
            },
            "required": ["x", "y", "width", "height"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        x, y = int(arguments["x"]), int(arguments["y"])
        w, h = int(arguments["width"]), int(arguments["height"])
        target_window = arguments.get("target_window", "Paint")
        coord_space = arguments.get("coordinate_space", "content")

        poly = DrawPolylineTool()
        pts = [
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h]
        ]
        return await poly.execute({
            "points": pts,
            "closed": True,
            "target_window": target_window,
            "coordinate_space": coord_space
        })


class DrawShapeTool(BaseTool):
    """
    Draws geometric shapes (such as 3D isometric cubes, rectangles, polygons) on a canvas with visual verification.
    """
    @property
    def name(self) -> str:
        return "draw_shape"

    @property
    def description(self) -> str:
        return "Draws geometric shapes (e.g. 3D isometric cube, polygon) on a canvas window with full visual verification."

    @property
    def category(self) -> str:
        return "computer"

    @property
    def required_scope(self) -> str:
        return "computer.mouse"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shape_type": {"type": "string", "description": "Type of geometric shape ('cube', 'rectangle', 'polyline')", "default": "cube"},
                "x": {"type": "integer", "description": "Origin X coordinate in canvas space", "default": 200},
                "y": {"type": "integer", "description": "Origin Y coordinate in canvas space", "default": 200},
                "size": {"type": "integer", "description": "Dimension/size of shape", "default": 140},
                "depth": {"type": "integer", "description": "Isometric depth for 3D shapes", "default": 60},
                "target_window": {"type": "string", "default": "Paint"},
                "coordinate_space": {"type": "string", "enum": ["content", "canvas", "window", "screenshot", "screen"], "default": "content"}
            },
            "required": ["shape_type"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        shape_type = str(arguments.get("shape_type", "cube")).lower().strip()
        x0 = int(arguments.get("x", 200))
        y0 = int(arguments.get("y", 200))
        size = int(arguments.get("size", 140))
        d = int(arguments.get("depth", 60))
        target_window = arguments.get("target_window", "Paint")
        coord_space = arguments.get("coordinate_space", "content")

        if shape_type == "rectangle":
            rect_tool = DrawRectangleTool()
            return await rect_tool.execute({
                "x": x0, "y": y0,
                "width": size, "height": int(arguments.get("height", size)),
                "target_window": target_window,
                "coordinate_space": coord_space
            })

        # 3D isometric cube vertices
        f_tl = (x0, y0)
        f_tr = (x0 + size, y0)
        f_br = (x0 + size, y0 + size)
        f_bl = (x0, y0 + size)

        b_tl = (x0 + d, y0 - d)
        b_tr = (x0 + size + d, y0 - d)
        b_br = (x0 + size + d, y0 + size - d)
        b_bl = (x0 + d, y0 + size - d)

        segments = [
            ("Front Top", f_tl, f_tr),
            ("Front Right", f_tr, f_br),
            ("Front Bottom", f_br, f_bl),
            ("Front Left", f_bl, f_tl),
            ("Back Top", b_tl, b_tr),
            ("Back Right", b_tr, b_br),
            ("Back Bottom", b_br, b_bl),
            ("Back Left", b_bl, b_tl),
            ("Depth Top-Left", f_tl, b_tl),
            ("Depth Top-Right", f_tr, b_tr),
            ("Depth Bottom-Right", f_br, b_br),
            ("Depth Bottom-Left", f_bl, b_bl),
        ]

        img_before = SCREEN_OBSERVER.capture_image()
        win_before = win32_utils.get_active_window_details()

        line_tool = DrawLineTool()
        strokes_passed = 0
        total_pixels = 0

        for name, p1, p2 in segments:
            res = await line_tool.execute({
                "start_x": p1[0], "start_y": p1[1],
                "end_x": p2[0], "end_y": p2[1],
                "target_window": target_window,
                "coordinate_space": coord_space,
                "duration_ms": 180
            })
            if res.get("result_success"):
                strokes_passed += 1
                total_pixels += res.get("pixels_changed", 0)
            await asyncio.sleep(0.08)

        await asyncio.sleep(0.2)
        img_after = SCREEN_OBSERVER.capture_image()
        win_after = win32_utils.get_active_window_details()

        resolved_ok, sample_origin, _ = win32_utils.resolve_coordinates({
            "target_window": target_window,
            "coordinate_space": coord_space,
            "x": x0,
            "y": y0
        })
        if sample_origin:
            cx, cy = sample_origin["x"], sample_origin["y"]
            shape_bbox = (cx - 30, cy - d - 30, cx + size + d + 30, cy + size + 30)
            ver = verify_visual_change(img_before, img_after, region_bbox=shape_bbox, min_changed_pixels=200)
        else:
            ver = {"verification_status": "execution_success_but_unverified", "pixels_changed": total_pixels}

        final_success = (strokes_passed >= 10) and (ver.get("verification_status") == "verified_success")

        return {
            "success": final_success,
            "action_success": strokes_passed == len(segments),
            "result_success": final_success,
            "segments_verified": f"{strokes_passed}/{len(segments)}",
            "total_pixels_changed": ver.get("pixels_changed", total_pixels),
            "verification_status": ver.get("verification_status"),
            "visual_verification": ver,
            "target_window_before": win_before,
            "target_window_after": win_after,
            "error": None if final_success else f"Shape drawing verification failed: Only {strokes_passed}/{len(segments)} strokes verified."
        }

import os
import io
import math
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageStat
import logging

logger = logging.getLogger("agent.core.image_processing")


class ImageUnderstandingEngine:
    """
    Phase 14: Image & UI Understanding Engine.
    
    Provides:
    - Dimensions, format, and aspect ratio analysis
    - Dominant color and brightness/contrast profiling
    - UI contrast analysis & edge detection
    """

    @staticmethod
    def analyze_image(source: Any) -> Dict[str, Any]:
        """Analyzes visual properties, dimensions, color profile, and brightness."""
        if isinstance(source, str):
            if not os.path.exists(source):
                raise FileNotFoundError(f"Image not found: {source}")
            img = Image.open(source)
        elif isinstance(source, bytes):
            img = Image.open(io.BytesIO(source))
        elif isinstance(source, Image.Image):
            img = source
        else:
            raise TypeError("Source must be file path, bytes, or PIL Image.")

        w, h = img.size
        aspect_ratio = round(w / float(h), 2) if h > 0 else 1.0

        # Convert to RGB for analysis
        rgb_img = img.convert("RGB")
        stat = ImageStat.Stat(rgb_img)

        # Average brightness (perceived luminance: 0.299 R + 0.587 G + 0.114 B)
        avg_r, avg_g, avg_b = stat.mean[:3]
        brightness = round(0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b, 2)

        # Contrast via standard deviation of luminance
        std_r, std_g, std_b = stat.stddev[:3]
        contrast = round(math.sqrt(0.299 * (std_r**2) + 0.587 * (std_g**2) + 0.114 * (std_b**2)), 2)

        # Dominant color
        dom_rgb = (int(avg_r), int(avg_g), int(avg_b))
        dom_hex = f"#{dom_rgb[0]:02x}{dom_rgb[1]:02x}{dom_rgb[2]:02x}"

        return {
            "width": w,
            "height": h,
            "aspect_ratio": aspect_ratio,
            "mode": img.mode,
            "format": getattr(img, "format", "UNKNOWN"),
            "brightness": brightness,
            "contrast": contrast,
            "dominant_color_rgb": dom_rgb,
            "dominant_color_hex": dom_hex
        }


class ImageProcessor:
    """
    Phase 14: Image Editing and Visual Workflow Processor.
    
    Provides:
    - Resize (with or without aspect ratio preservation)
    - Crop
    - Rotate
    - Format conversion (PNG, JPEG, WEBP, BMP)
    - Visual Annotations (bounding boxes, highlights, text)
    - Output verification
    """

    @staticmethod
    def resize_image(
        input_path: str,
        output_path: str,
        width: int,
        height: int,
        preserve_aspect: bool = True
    ) -> Dict[str, Any]:
        """Resizes an image and saves to output_path."""
        with Image.open(input_path) as img:
            if preserve_aspect:
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                new_img = img
            else:
                new_img = img.resize((width, height), Image.Resampling.LANCZOS)
            
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            new_img.save(output_path)

        return {
            "output_path": output_path,
            "new_size": new_img.size,
            "size_bytes": os.path.getsize(output_path)
        }

    @staticmethod
    def crop_image(
        input_path: str,
        output_path: str,
        bbox: Tuple[int, int, int, int]
    ) -> Dict[str, Any]:
        """Crops an image to (left, top, right, bottom) bounding box."""
        with Image.open(input_path) as img:
            cropped = img.crop(bbox)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            cropped.save(output_path)

        return {
            "output_path": output_path,
            "cropped_size": cropped.size,
            "size_bytes": os.path.getsize(output_path)
        }

    @staticmethod
    def rotate_image(
        input_path: str,
        output_path: str,
        angle_degrees: float,
        expand: bool = True
    ) -> Dict[str, Any]:
        """Rotates an image by specified angle."""
        with Image.open(input_path) as img:
            rotated = img.rotate(angle_degrees, expand=expand, resample=Image.Resampling.BICUBIC)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            rotated.save(output_path)

        return {
            "output_path": output_path,
            "new_size": rotated.size,
            "size_bytes": os.path.getsize(output_path)
        }

    @staticmethod
    def convert_format(
        input_path: str,
        output_path: str,
        target_format: str = "PNG"
    ) -> Dict[str, Any]:
        """Converts an image between formats (e.g. JPEG to PNG)."""
        with Image.open(input_path) as img:
            rgb_img = img.convert("RGB") if target_format.upper() in ("JPEG", "JPG") else img
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            rgb_img.save(output_path, format=target_format.upper())

        return {
            "output_path": output_path,
            "format": target_format.upper(),
            "size_bytes": os.path.getsize(output_path)
        }

    @staticmethod
    def annotate_image(
        input_path: str,
        output_path: str,
        annotations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Draws visual annotations (e.g. bounding boxes or highlight overlays) on image.
        Annotations schema: [{"bbox": (x1,y1,x2,y2), "color": "red", "width": 3, "label": "Button"}]
        """
        with Image.open(input_path) as img:
            annotated = img.convert("RGB")
            draw = ImageDraw.Draw(annotated)

            for ann in annotations:
                box = ann.get("bbox")
                color = ann.get("color", "red")
                outline_w = ann.get("width", 3)
                label = ann.get("label")

                if box:
                    draw.rectangle(box, outline=color, width=outline_w)
                    if label:
                        draw.text((box[0], max(0, box[1] - 12)), label, fill=color)

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            annotated.save(output_path)

        return {
            "output_path": output_path,
            "annotations_applied": len(annotations),
            "size_bytes": os.path.getsize(output_path)
        }

    @staticmethod
    def verify_image_output(
        file_path: str,
        expected_min_size: int = 100,
        expected_dimensions: Optional[Tuple[int, int]] = None
    ) -> bool:
        """Verifies that the generated image exists, is valid image data, and meets dimension criteria."""
        if not os.path.exists(file_path):
            return False
        if os.path.getsize(file_path) < expected_min_size:
            return False
        try:
            with Image.open(file_path) as img:
                img.verify()
            with Image.open(file_path) as img:
                if expected_dimensions and img.size != expected_dimensions:
                    return False
            return True
        except Exception:
            return False

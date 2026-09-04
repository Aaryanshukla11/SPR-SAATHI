import pytest
import os
from PIL import Image, ImageDraw

from agent.core.image_processing import (
    ImageUnderstandingEngine, ImageProcessor
)
from agent.core.vision import verify_visual_change


# ============================================================================
# 1. IMAGE UNDERSTANDING TESTS
# ============================================================================

def test_image_understanding_analysis(tmp_path):
    """Verify ImageUnderstandingEngine calculates dimensions, aspect ratio, and color metrics."""
    test_img = tmp_path / "test_pattern.png"
    im = Image.new("RGB", (200, 100), color=(255, 0, 0))  # Solid Red
    im.save(test_img)

    analysis = ImageUnderstandingEngine.analyze_image(str(test_img))
    assert analysis["width"] == 200
    assert analysis["height"] == 100
    assert analysis["aspect_ratio"] == 2.0
    assert analysis["dominant_color_rgb"][0] > 200  # High Red


# ============================================================================
# 2. IMAGE EDITING & TRANSFORMATION TESTS
# ============================================================================

def test_image_resize_and_crop(tmp_path):
    """Verify ImageProcessor resizes and crops image accurately."""
    src = tmp_path / "source.png"
    im = Image.new("RGB", (400, 400), color="blue")
    im.save(src)

    # 1. Resize
    resized_out = tmp_path / "resized.png"
    res_resize = ImageProcessor.resize_image(str(src), str(resized_out), 200, 200, preserve_aspect=False)
    assert os.path.exists(resized_out)
    assert res_resize["new_size"] == (200, 200)

    # 2. Crop
    cropped_out = tmp_path / "cropped.png"
    res_crop = ImageProcessor.crop_image(str(src), str(cropped_out), (50, 50, 150, 150))
    assert os.path.exists(cropped_out)
    assert res_crop["cropped_size"] == (100, 100)


def test_image_rotation_and_format_conversion(tmp_path):
    """Verify ImageProcessor rotates and converts format."""
    src = tmp_path / "canvas.png"
    im = Image.new("RGB", (100, 50), color="green")
    im.save(src)

    # 1. Rotate
    rot_out = tmp_path / "rotated.png"
    ImageProcessor.rotate_image(str(src), str(rot_out), 90, expand=True)
    with Image.open(rot_out) as rot_img:
        assert rot_img.size == (50, 100)

    # 2. Convert to JPEG
    jpeg_out = tmp_path / "converted.jpg"
    res_conv = ImageProcessor.convert_format(str(src), str(jpeg_out), target_format="JPEG")
    assert res_conv["format"] == "JPEG"
    assert os.path.exists(jpeg_out)


def test_image_annotation_and_verification(tmp_path):
    """Verify ImageProcessor applies bounding box annotations and verifies output."""
    src = tmp_path / "screenshot.png"
    im = Image.new("RGB", (300, 200), color="white")
    im.save(src)

    out = tmp_path / "annotated.png"
    annotations = [
        {"bbox": (20, 20, 100, 60), "color": "red", "label": "Submit Button"}
    ]
    res_ann = ImageProcessor.annotate_image(str(src), str(out), annotations)
    assert res_ann["annotations_applied"] == 1

    # Verify output integrity
    is_valid = ImageProcessor.verify_image_output(str(out), expected_dimensions=(300, 200))
    assert is_valid is True


# ============================================================================
# 3. VISUAL VERIFICATION BEFORE VS AFTER
# ============================================================================

def test_visual_verification_detects_changes():
    """Verify verify_visual_change detects visible pixel modifications."""
    im1 = Image.new("RGB", (100, 100), color="white")
    im2 = im1.copy()
    draw = ImageDraw.Draw(im2)
    draw.rectangle((20, 20, 50, 50), fill="black")

    res = verify_visual_change(im1, im2)
    assert res["verification_status"] == "verified_success"
    assert res["change_detected"] is True
    assert res["pixels_changed"] > 100


def test_visual_verification_detects_no_changes():
    """Verify verify_visual_change correctly reports verification_failed when screen did not change."""
    im1 = Image.new("RGB", (100, 100), color="white")
    im2 = Image.new("RGB", (100, 100), color="white")

    res = verify_visual_change(im1, im2)
    assert res["verification_status"] == "verification_failed"
    assert res["change_detected"] is False

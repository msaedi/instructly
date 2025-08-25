import io

import pytest
from PIL import Image

from app.services.image_processing_service import ImageProcessingService


def _make_img_bytes(mode="RGBA", size=(300, 100), color=(0, 128, 255, 255), fmt="PNG") -> bytes:
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_process_valid_png_generates_variants():
    svc = ImageProcessingService()
    # Use a square image to satisfy aspect ratio <= 2:1
    data = _make_img_bytes(size=(300, 300))
    out = svc.process_profile_picture(uploaded_bytes=data, browser_content_type="image/png")
    assert len(out.original) > 0
    assert len(out.display_400) > 0
    assert len(out.thumb_200) > 0


def test_reject_large_aspect_ratio():
    svc = ImageProcessingService()
    # 1000x100 small extreme ratio 10:1
    data = _make_img_bytes(size=(1000, 100))
    with pytest.raises(ValueError):
        svc.process_profile_picture(uploaded_bytes=data, browser_content_type="image/png")

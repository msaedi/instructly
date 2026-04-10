import io

from PIL import Image
import pytest

from app.services.image_processing_service import (
    MAX_PROFILE_PHOTO_BYTES,
    ImageProcessingService,
)


def _make_img_bytes(mode="RGBA", size=(300, 100), color=(0, 128, 255, 255), fmt="PNG") -> bytes:
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_oriented_jpeg_bytes(size=(300, 100), orientation=6) -> bytes:
    img = Image.new("RGB", size, (255, 0, 0))
    exif = Image.Exif()
    exif[274] = orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
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


def test_verify_magic_bytes_rejects_invalid_data():
    svc = ImageProcessingService()
    with pytest.raises(ValueError):
        svc._verify_magic_bytes(b"not-an-image")


def test_enforce_constraints_rejects_invalid_type_and_size():
    svc = ImageProcessingService()
    with pytest.raises(ValueError):
        svc._enforce_constraints("image/gif", b"data")
    with pytest.raises(ValueError):
        svc._enforce_constraints("image/png", b"0" * (MAX_PROFILE_PHOTO_BYTES + 1))


def test_process_profile_picture_applies_exif_orientation_before_encoding():
    svc = ImageProcessingService()
    data = _make_oriented_jpeg_bytes(size=(200, 100), orientation=6)

    out = svc.process_profile_picture(uploaded_bytes=data, browser_content_type="image/jpeg")

    with Image.open(io.BytesIO(out.original)) as normalized:
        assert normalized.size == (100, 200)

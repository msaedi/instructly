"""
ImageProcessingService

Validates and processes profile images:
- Magic bytes verification (JPEG/PNG)
- Size and aspect ratio checks
- Center-crop to square and resize to variants
- Convert transparency to white background
"""

from dataclasses import dataclass
import imghdr
import io
import logging
from typing import Tuple

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024
MAX_ASPECT_RATIO = 2.0  # width/height or height/width must not exceed 2:1


@dataclass
class ProcessedImages:
    original: bytes
    display_400: bytes
    thumb_200: bytes


class ImageProcessingService:
    def __init__(self) -> None:
        pass

    def _verify_magic_bytes(self, data: bytes) -> str:
        kind = imghdr.what(None, h=data)
        if kind not in {"jpeg", "png"}:
            raise ValueError("Invalid image type")
        return "image/jpeg" if kind == "jpeg" else "image/png"

    def _enforce_constraints(self, content_type: str, data: bytes) -> None:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError("Unsupported content type")
        if len(data) > MAX_SIZE_BYTES:
            raise ValueError("File too large")

        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            ratio = width / height if width >= height else height / width
            if ratio > MAX_ASPECT_RATIO:
                raise ValueError("Aspect ratio exceeds 2:1")

    def _normalize_to_jpeg(self, data: bytes) -> Image.Image:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGBA")
            # Flatten transparency to white
            background = Image.new("RGBA", img.size, (255, 255, 255, 255))
            composite = Image.alpha_composite(background, img)
            return composite.convert("RGB")

    def _center_crop_square(self, img: Image.Image) -> Image.Image:
        return ImageOps.fit(
            img, (min(img.size), min(img.size)), method=Image.LANCZOS, centering=(0.5, 0.5)
        )

    def _encode_jpeg(
        self, img: Image.Image, size: Tuple[int, int] | None = None, quality: int = 85
    ) -> bytes:
        out = io.BytesIO()
        work = img
        if size is not None:
            work = img.resize(size, Image.LANCZOS)
        work.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()

    def process_profile_picture(
        self, uploaded_bytes: bytes, browser_content_type: str
    ) -> ProcessedImages:
        # Validate by magic bytes then enforce additional constraints
        detected = self._verify_magic_bytes(uploaded_bytes)
        self._enforce_constraints(detected, uploaded_bytes)

        # Decode and normalize
        base = self._normalize_to_jpeg(uploaded_bytes)

        # Build variants
        square = self._center_crop_square(base)

        original_jpeg = self._encode_jpeg(base, None, quality=85)
        display = self._encode_jpeg(square, (400, 400), quality=85)
        thumb = self._encode_jpeg(square, (200, 200), quality=85)

        return ProcessedImages(original=original_jpeg, display_400=display, thumb_200=thumb)

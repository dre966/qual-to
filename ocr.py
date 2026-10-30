"""OCR using Tesseract via pytesseract."""

from __future__ import annotations

import logging
from pathlib import Path

import pytesseract
from PIL import Image

from config import OCR_LANG, TESSERACT_CMD

log = logging.getLogger("avd_tor_ocr.ocr")

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def ocr_image(image_path: str | Path, lang: str = OCR_LANG) -> str:
    """Run Tesseract OCR on an image file and return the recognized text."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    log.info("OCR: %s (lang=%s)", image_path, lang)
    text = pytesseract.image_to_string(Image.open(image_path), lang=lang)
    log.debug("OCR result:\n%s", text)
    return text


def ocr_region(image_path: str | Path, box, lang: str = OCR_LANG) -> str:
    """OCR a rectangular region of an image.

    ``box`` is (left, top, right, bottom) in pixels.
    """
    image_path = Path(image_path)
    with Image.open(image_path) as img:
        cropped = img.crop(box)
        text = pytesseract.image_to_string(cropped, lang=lang)
    log.info("OCR region %s: %d chars", box, len(text))
    return text

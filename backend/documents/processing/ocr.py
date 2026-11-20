"""OCR using RapidOCR (ONNX runtime, runs on CPU, no external service or API key).

Strategy for poor-quality input:
  1. Light preprocessing (EXIF rotation, grayscale, auto-contrast, upscale small images).
  2. If the result is weak (low confidence or little text), retry with a stronger
     variant (denoise + sharpen) and with 90 / 270 degree rotations.
  3. Keep whichever attempt recognised the most text, weighted by confidence.

Recognised text boxes are regrouped into lines so table rows stay on one line
("Widget   2   50.00   100.00"), which matters for line-item extraction later.
"""
import statistics
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter, ImageOps

_engine = None
_engine_lock = threading.Lock()

# Below this mean confidence (or with almost no text) the stronger variants are tried.
WEAK_CONFIDENCE = 0.65
WEAK_MIN_CHARS = 10
MAX_SIDE = 5000          # larger images are downscaled
MIN_LONG_SIDE = 1000     # smaller images are upscaled
TARGET_LONG_SIDE = 1600


@dataclass
class OcrResult:
    text: str
    confidence: Optional[float]   # mean confidence 0-1, None when nothing was recognised
    score: float                  # sum(confidence * characters): used to compare attempts


def get_engine():
    """Create the OCR engine once per process (model loading is the expensive part)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
    return _engine


def _resize(image: Image.Image) -> Image.Image:
    width, height = image.size
    long_side = max(width, height)
    if long_side > MAX_SIDE:
        scale = MAX_SIDE / long_side
    elif long_side < MIN_LONG_SIDE:
        scale = min(3.0, TARGET_LONG_SIDE / long_side)
    else:
        return image
    return image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)


def _standard(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    gray = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1)
    return _resize(gray)


def _enhanced(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(ImageOps.exif_transpose(image))
    gray = ImageOps.autocontrast(gray, cutoff=2)
    gray = gray.filter(ImageFilter.MedianFilter(3))
    gray = _resize(gray)
    return gray.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))


def _assemble(raw) -> OcrResult:
    """Turn RapidOCR boxes into text, grouping boxes that share a line."""
    items = []
    for box, text, confidence in raw or []:
        text = (text or "").strip()
        if not text:
            continue
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        items.append(
            {
                "x": min(xs),
                "y": (min(ys) + max(ys)) / 2,
                "h": max(ys) - min(ys),
                "text": text,
                "conf": float(confidence),
            }
        )
    if not items:
        return OcrResult("", None, 0.0)

    items.sort(key=lambda item: item["y"])
    median_height = statistics.median(item["h"] for item in items) or 1.0
    lines: list[dict] = []
    for item in items:
        if lines and abs(item["y"] - lines[-1]["y"]) <= 0.6 * median_height:
            line = lines[-1]
            line["items"].append(item)
            line["y"] = sum(i["y"] for i in line["items"]) / len(line["items"])
        else:
            lines.append({"y": item["y"], "items": [item]})

    text = "\n".join(
        "  ".join(i["text"] for i in sorted(line["items"], key=lambda i: i["x"])) for line in lines
    )
    confidence = sum(i["conf"] for i in items) / len(items)
    score = sum(i["conf"] * len(i["text"]) for i in items)
    return OcrResult(text, confidence, score)


def _run(image: Image.Image) -> OcrResult:
    array = np.array(image.convert("RGB"))
    result, _ = get_engine()(array)
    return _assemble(result)


def _is_weak(result: OcrResult) -> bool:
    return (
        result.confidence is None
        or result.confidence < WEAK_CONFIDENCE
        or len(result.text.replace("\n", "").replace(" ", "")) < WEAK_MIN_CHARS
    )


def ocr_image(image: Image.Image) -> OcrResult:
    """OCR a PIL image, retrying with stronger preprocessing when the first pass is weak."""
    best = _run(_standard(image))
    if not _is_weak(best):
        return best

    enhanced = _enhanced(image)
    candidates = [enhanced, enhanced.rotate(90, expand=True), enhanced.rotate(270, expand=True)]
    for candidate in candidates:
        attempt = _run(candidate)
        if attempt.score > best.score:
            best = attempt
        if not _is_weak(best):
            break
    return best

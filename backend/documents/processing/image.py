"""Image extraction (JPG, PNG, TIFF) with OCR. Multi-frame TIFFs yield one page per frame."""
import logging

from PIL import Image, ImageSequence, UnidentifiedImageError

from .base import Extraction, PageResult, clean_text
from .errors import CorruptedFileError
from .ocr import ocr_image

logger = logging.getLogger(__name__)

# Guard against decompression bombs (a tiny file that expands to gigapixels).
Image.MAX_IMAGE_PIXELS = 120_000_000


def _frame_count(image: Image.Image) -> int:
    return max(1, getattr(image, "n_frames", 1))


def extract_image(path: str) -> Extraction:
    try:
        with Image.open(path) as probe:
            probe.load()                    # decode frame 1 now: catches truncated / corrupt data
            total = _frame_count(probe)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise CorruptedFileError(f"The image could not be read (corrupted or invalid) ({type(exc).__name__}).") from exc

    def pages():
        with Image.open(path) as image:
            for index, frame in enumerate(ImageSequence.Iterator(image)):
                number = index + 1
                try:
                    result = ocr_image(frame.copy())
                    yield PageResult(number, clean_text(result.text), "ocr", result.confidence)
                except Exception as exc:  # noqa: BLE001 - isolate a bad frame
                    logger.warning("Image frame %s failed: %s", number, exc)
                    yield PageResult(number, source="ocr", error=f"Frame could not be read ({type(exc).__name__}).")

    return Extraction(total=total, pages=pages())

"""File-type detection and safety validation.

The type is decided from the file *content* (magic bytes), not only the extension,
so a renamed or spoofed file is rejected instead of being passed to a parser.
"""
import os
from pathlib import Path

from . import config
from .errors import CorruptedFileError, FileTooLargeError, UnsupportedFileError

EXTENSION_TYPES = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".tif": "image",
    ".tiff": "image",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
}

SUPPORTED_DESCRIPTION = "PDF, JPG, PNG, TIFF, XLSX, XLS, CSV"


def _sniff(head: bytes) -> str | None:
    """Identify a binary format from its first bytes. Returns None for unknown/text."""
    if head.lstrip(b"\x00\r\n\t ")[:4] == b"%PDF" or b"%PDF" in head[:1024]:
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if head.startswith(b"\xff\xd8\xff"):
        return "image"
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return "image"
    if head.startswith(b"PK\x03\x04"):
        return "xlsx"  # an XLSX is a zip container
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "xls"  # legacy OLE2 container
    return None


def detect_upload_type(name: str, size: int, head: bytes) -> str:
    """Validate a file from its name, size and first bytes (no file on disk needed).

    Returns one of: pdf, image, xlsx, xls, csv.
    Raises UnsupportedFileError / CorruptedFileError / FileTooLargeError.
    """
    extension = Path(name).suffix.lower()
    expected = EXTENSION_TYPES.get(extension)
    if expected is None:
        raise UnsupportedFileError(
            f"Unsupported file type '{extension or 'none'}'. Supported: {SUPPORTED_DESCRIPTION}."
        )
    if size == 0:
        raise CorruptedFileError("The file is empty.")
    if size > config.max_upload_bytes():
        raise FileTooLargeError(
            f"The file is {size / 1_048_576:.1f} MB; the limit is {config.max_upload_bytes() // 1_048_576} MB."
        )

    sniffed = _sniff(head)
    if expected == "csv":
        if sniffed is not None:
            raise CorruptedFileError("The file has a .csv extension but its content is not plain text.")
        if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise CorruptedFileError("The file has a .csv extension but looks like binary data.")
        return "csv"

    if sniffed is None:
        raise CorruptedFileError(
            f"The file content is not a valid {extension.lstrip('.').upper()} (unrecognised file signature)."
        )
    # Excel files are commonly saved with the wrong extension (.xls holding XLSX data, or vice versa).
    if expected in ("xlsx", "xls") and sniffed in ("xlsx", "xls"):
        return sniffed
    if sniffed != expected:
        raise CorruptedFileError(
            f"The file has a {extension} extension but its content looks like {sniffed.upper()}."
        )
    return expected


def detect_file_type(path: str | os.PathLike, original_name: str | None = None) -> str:
    """Same validation for a file on disk."""
    path = Path(path)
    with open(path, "rb") as handle:
        head = handle.read(2048)
    return detect_upload_type(original_name or path.name, path.stat().st_size, head)

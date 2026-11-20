"""Exceptions raised by the document-processing pipelines.

Every one of these is an *expected* failure: the document is marked FAILED with a
human-readable message instead of crashing the worker.
"""


class ProcessingError(Exception):
    """Base class for expected processing failures."""


class UnsupportedFileError(ProcessingError):
    """The file type is not one of PDF, JPG, PNG, TIFF, XLSX, XLS, CSV."""


class CorruptedFileError(ProcessingError):
    """The file is empty, truncated, malformed, or its content does not match its extension."""


class PasswordProtectedError(ProcessingError):
    """The file is encrypted and cannot be read without a password."""


class FileTooLargeError(ProcessingError):
    """The file (or its decompressed content) exceeds the configured safety limit."""

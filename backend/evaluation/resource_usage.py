"""Peak memory of this process (works on Linux/macOS; returns None where the OS has no ``resource`` module)."""
import sys


def peak_memory_mb():
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)

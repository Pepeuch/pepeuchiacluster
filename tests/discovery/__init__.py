"""Progressive Discovery test entry point, retaining historical POC modules."""

from pathlib import Path
import sys
import unittest


POC_ROOT = Path(__file__).resolve().parents[2] / "database" / "poc"
if str(POC_ROOT) not in sys.path:
    sys.path.insert(0, str(POC_ROOT))


def load_new_tests(loader, pattern=None):
    suite = unittest.TestSuite()
    for path in sorted(Path(__file__).parent.glob(pattern or "test_*.py")):
        suite.addTests(loader.loadTestsFromName(f"{__name__}.{path.stem}"))
    return suite


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    # No nested discover: helper modules keep their historical import names,
    # and the legacy forwarding module must not recurse into this entry point.
    for path in sorted(POC_ROOT.glob(pattern or "test_*.py")):
        if path.name != "test_discovery_consolidation.py":
            suite.addTests(loader.loadTestsFromName(path.stem))
    suite.addTests(load_new_tests(loader, pattern))
    return suite

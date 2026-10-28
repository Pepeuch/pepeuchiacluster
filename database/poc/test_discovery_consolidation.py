"""Keep historical unittest discovery inclusive during progressive relocation."""

from tests.discovery import load_new_tests


def load_tests(loader, standard_tests, pattern):
    return load_new_tests(loader, pattern)

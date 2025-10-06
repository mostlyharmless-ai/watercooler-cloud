"""Smoke tests for L0 phase - verify basic package structure."""


def test_import():
    """Verify package can be imported."""
    import watercooler
    assert watercooler.__version__ == "0.0.1"


def test_version_string():
    """Verify version is a string."""
    import watercooler
    assert isinstance(watercooler.__version__, str)
    assert len(watercooler.__version__) > 0

import importlib
import sys


def test_import_aweb_package_does_not_import_cli():
    sys.modules.pop("aweb", None)
    sys.modules.pop("aweb.cli", None)

    module = importlib.import_module("aweb")

    assert module.__file__
    assert "aweb.cli" not in sys.modules

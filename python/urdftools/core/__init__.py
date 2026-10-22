"""Shared application services for desktop and CLI."""
import platform
import sys
from urdftools import __version__


def runtime_status():
    return {"application": "URDFTools", "version": __version__,
            "python": platform.python_version(), "isolated": sys.prefix != sys.base_prefix,
            "capabilities": ["doctor", "health"], "units": "SI"}

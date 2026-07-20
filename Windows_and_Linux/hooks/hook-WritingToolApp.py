"""Prevent PyInstaller from bundling incompatible optional ICU DLLs.

QtCore delay-loads ICU when it is available. The pip PySide6 build works
without ICU, while the surrounding Conda installation exposes an older ICU
that PyInstaller would otherwise collect and that makes packaged QtCore fail.
"""

import os

from PyInstaller.depend import dylib


_original_check_library = dylib.exclude_list.check_library
_optional_incompatible_icu = {"icudt73.dll", "icuuc.dll"}


def _check_library(libname):
    if os.path.basename(libname).lower() in _optional_incompatible_icu:
        return True
    return _original_check_library(libname)


dylib.exclude_list.check_library = _check_library

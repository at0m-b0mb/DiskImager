"""Platform detection helpers – re-exports the correct sub-module."""

import sys

if sys.platform.startswith("linux"):
    from .linux import (  # noqa: F401
        list_physical_drives,
        is_removable,
        is_system_disk,
    )
elif sys.platform == "darwin":
    from .darwin import (  # noqa: F401
        list_physical_drives,
        is_removable,
        is_system_disk,
    )
elif sys.platform == "win32":
    from .windows import (  # noqa: F401
        list_physical_drives,
        is_removable,
        is_system_disk,
    )
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

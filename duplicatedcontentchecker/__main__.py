"""Allow ``python -m duplicatedcontentchecker``."""

import sys

from .cli import main

sys.exit(main())

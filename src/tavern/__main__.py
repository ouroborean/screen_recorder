"""Main entry point for the game."""
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

import tavern  # pylint: disable=wrong-import-position

sys.exit(tavern.main())
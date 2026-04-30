"""pytest configuration: add src/ to sys.path so unit tests can import backend modules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

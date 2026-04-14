import sys
from pathlib import Path

# Add scripts/ to path so tests can import modules directly
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

import sys
from pathlib import Path

# Ensure project root is on sys.path for `import app`.
sys.path.append(str(Path(__file__).resolve().parents[2]))

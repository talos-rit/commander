"""Launch the prepared Commander web console using the existing Python environment."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    from talos import web_interface
    web_interface()

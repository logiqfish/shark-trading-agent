import sys
from pathlib import Path

# Put the skill dir (parent of tests/) on sys.path so `import thesis`
# resolves to ../thesis.py regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

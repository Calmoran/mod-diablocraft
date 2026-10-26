"""Every scripts/ folder on sys.path, so a script imports another by its bare name
wherever it lives (R5: generators in generate/<system>/, tests in tests/<system>/).
A script below the top inserts the scripts root, then imports this."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _d in [ROOT, *sorted(ROOT.glob("generate/*/")), *sorted(ROOT.glob("tests/*/"))]:
    if str(_d) not in sys.path:
        sys.path.append(str(_d))

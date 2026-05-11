import sys
from pathlib import Path
from runpy import run_path


def main(argv):
    target = Path(__file__).resolve().parents[1] / "scripts" / "boundary.py"
    mod = run_path(str(target))
    return mod["main"](argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


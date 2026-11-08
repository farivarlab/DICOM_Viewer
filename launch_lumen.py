"""Desktop entry point, also used by the portable Windows build."""
import argparse
import json
from pathlib import Path
import sys


def main():
    if "--self-test" in sys.argv:
        parser = argparse.ArgumentParser(description="Validate a portable Lumen build locally")
        parser.add_argument("--self-test", action="store_true")
        parser.add_argument("--input", default=None)
        parser.add_argument("--report", required=True)
        args = parser.parse_args()
        try:
            from lumen.selftest import run_selftest
            return run_selftest(args.input, args.report)
        except Exception as exc:
            report = Path(args.report).resolve()
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                                          "error": str(exc)}, indent=2), encoding="utf-8")
            return 1
    from lumen.startup import main as viewer_main
    return viewer_main()


if __name__ == "__main__":
    raise SystemExit(main())

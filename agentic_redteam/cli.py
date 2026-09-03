"""CLI: run one or more scenarios and emit a red-team report.

Usage:
  python -m agentic_redteam.cli [scenario.yaml ...] [-o report.md]
With no paths, runs the whole bundled scenario library.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import summary
from .scenario import Scenario, ScenarioRunner

LIB = Path(__file__).parent / "scenarios"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentic_redteam")
    ap.add_argument("scenarios", nargs="*", help="YAML scenario files (default: full library)")
    ap.add_argument("-o", "--output", help="write Markdown report to this path")
    ap.add_argument("-n", "--trials", type=int, default=1,
                    help="trials per scenario; ASR is estimated over trials (default 1)")
    ap.add_argument("--no-reset", action="store_true", help="do not clear agent memory before each run")
    args = ap.parse_args(argv)

    paths = [Path(p) for p in args.scenarios] or sorted(LIB.glob("*.yaml"))
    runner = ScenarioRunner(reset=not args.no_reset)

    results = []
    for p in paths:
        scenario = Scenario.load(p)
        traces = []
        for i in range(args.trials):
            tag = f" trial {i + 1}/{args.trials}" if args.trials > 1 else ""
            print(f"[*] running {scenario.id}{tag} ...", file=sys.stderr)
            trace = runner.run(scenario)
            print(f"    -> {'COMPROMISED' if trace.success else 'not compromised'}", file=sys.stderr)
            traces.append(trace)
        ok = sum(1 for t in traces if t.success)
        print(f"[=] {scenario.id}: ASR {ok}/{args.trials}", file=sys.stderr)
        results.append((scenario, traces))

    report = summary(results)
    if args.output:
        Path(args.output).write_text(report)
        print(f"[*] report written to {args.output}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

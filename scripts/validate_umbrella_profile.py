#!/usr/bin/env python3
"""Promote a proposed umbrella profile only when its validation report passes every gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from umbrella_profiles import load_profile
from umbrella_runtime import atomic_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path); parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    proposed = json.loads(args.profile.read_text(encoding="utf-8"))
    L = int(proposed["L"])
    load_profile(args.profile, L, require_validated=False)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    proposed["n_lf"] = int(report["n_lf"])
    proposed["epsilon"] = float(report.get("epsilon", proposed["epsilon"]))
    proposed["validation"] = report
    proposed["validated"] = True
    output = args.output or args.profile
    # Validate the in-memory candidate through a same-directory temporary file.
    candidate = output.with_name(output.name + ".candidate")
    atomic_json(candidate, proposed)
    try:
        load_profile(candidate, L, require_validated=True)
        atomic_json(output, proposed)
    finally:
        candidate.unlink(missing_ok=True)
    print(f"validated_profile={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

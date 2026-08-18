#!/usr/bin/env python3
"""Update scripts/hmc_defaults.py from an hmc_tune_suite.jl CSV."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "scripts/hmc_defaults.py"


def parse_csv(path: Path) -> dict[int, tuple[float, int]]:
    values: dict[int, tuple[float, int]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row.get("L"):
                continue
            L = int(row["L"])
            values[L] = (float(row["eps"]), int(row["n_lf"]))
    return values


def replace_block(text: str, name: str, values: dict[int, tuple[float, int]]) -> str:
    pattern = re.compile(
        rf"({name}: dict\[int, tuple\[float, int\]\] = \{{)(.*?)(\n\}})",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"cannot find {name} block in {DEFAULTS_PATH}")
    lines = [f"    {L}: ({eps:.11g}, {n_lf})," for L, (eps, n_lf) in sorted(values.items())]
    replacement = match.group(1) + "\n" + "\n".join(lines) + match.group(3)
    return text[:match.start()] + replacement + text[match.end():]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--defaults", type=Path, default=DEFAULTS_PATH)
    parser.add_argument("--merge", action="store_true",
                        help="merge new L rows into the existing table")
    args = parser.parse_args()
    selected = parse_csv(args.csv)
    if not selected:
        raise SystemExit(f"no rows found in {args.csv}")
    text = args.defaults.read_text(encoding="utf-8")
    if args.merge:
        current = parse_csv(args.csv)  # placeholder
        existing_hmc = {
            int(match.group(1)): (float(match.group(2)), int(match.group(3)))
            for match in re.finditer(r"^\s*(\d+): \(([\d.eE+-]+), (\d+)\),",
                                     text.split("HMC_DEFAULTS")[1].split("STARTUP")[0],
                                     re.MULTILINE)
        }
        selected = {**existing_hmc, **selected}
    text = replace_block(text, "HMC_DEFAULTS", selected)
    args.defaults.write_text(text, encoding="utf-8")
    print(f"updated {args.defaults} with L values: {', '.join(map(str, sorted(selected)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

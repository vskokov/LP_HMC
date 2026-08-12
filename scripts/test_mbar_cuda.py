#!/usr/bin/env python3
"""Compare CPU and Julia/CUDA MBAR bootstraps on identical block resamples."""

from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reweight_binder import (  # noqa: E402
    RunData,
    bootstrap_mbar_errors,
    bootstrap_mbar_errors_cuda,
    group_sources,
)


def main() -> int:
    generator = np.random.default_rng(11)
    runs = []
    for group_index, (Z, m2) in enumerate(((-0.6, -1.85), (-0.9, -2.35))):
        for run_index in range(2):
            values = generator.normal(loc=0.3 * group_index, size=512)
            moment2 = 0.2 + values**2
            runs.append(RunData(
                path=Path("synthetic.csv"), L=8, Z=Z, m2=m2,
                seed=10 * group_index + run_index, epsilon=0.05, n_lf=8,
                order=len(runs), M2=moment2, M4=moment2**2,
                Q=20.0 + values**2, G=30.0 + (values - 0.2)**2,
            ))
    groups = group_sources(runs)[8]
    block_sizes = {(group.L, group.Z, group.m2): 16 for group in groups}
    targets = [(-0.6, -1.85), (-0.75, -2.1), (-0.9, -2.35)]
    options = dict(tolerance=1e-10, max_iterations=10_000)
    cpu = bootstrap_mbar_errors(
        groups, targets, block_sizes, 8, np.random.default_rng(99), jobs=1, **options
    )
    cuda = bootstrap_mbar_errors_cuda(
        groups, targets, block_sizes, 8, np.random.default_rng(99),
        batch_size=4, **options,
    )
    error = float(np.max(np.abs(cpu - cuda)))
    passed = np.allclose(cuda, cpu, rtol=2e-10, atol=2e-12)
    print(f"{'PASS' if passed else 'FAIL'} CUDA MBAR bootstrap max_error={error:.3e}")
    print("CPU ", cpu)
    print("CUDA", cuda)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

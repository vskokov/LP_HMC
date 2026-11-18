#!/usr/bin/env python3
"""Plot the synthetic and HMC deep-modulated structure-factor validation."""

from pathlib import Path
import csv
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lp-hmc")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "reports/structure_factor_cpu/deep_modulated_validation"
data = np.genfromtxt(DIRECTORY / "spectrum.csv", delimiter=",", names=True)
summary = next(csv.DictReader((DIRECTORY / "summary.csv").open()))

figure, axis = plt.subplots(figsize=(7.2, 4.8))
floor = 1e-6
axis.plot(data["q"], np.maximum(data["synthetic_S_per_mode"], floor), marker="o", ms=3,
          label="rotational/phase synthetic average")
axis.plot(data["q"], np.maximum(data["hmc_S_per_mode"], floor), marker="o", ms=3,
          label="HMC from modulated start")
axis.axvline(float(summary["q_mean_field"]), color="k", ls="--", lw=1,
             label=r"$-Z/2$")
axis.set_yscale("log")
axis.set(xlim=(0, 4), xlabel=r"lattice shell $q(k)$", ylabel=r"$S(q)$ per mode",
         title=fr"Deep-modulated validation: $Z={float(summary['Z']):g}$, "
               fr"$m^2={float(summary['m2']):g}$, $L={summary['L']}$")
axis.grid(alpha=0.25); axis.legend(frameon=False)
figure.tight_layout()
figure.savefig(DIRECTORY / "spectrum_validation.png", dpi=180)
print(DIRECTORY / "spectrum_validation.png")

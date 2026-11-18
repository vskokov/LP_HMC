# Manuscript draft

Build all generated figures and the PDF from the repository root:

```bash
MPLCONFIGDIR=/tmp/lp_hmc_matplotlib python3 scripts/build_paper_figures.py
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd paper/main.tex
```

The manuscript deliberately distinguishes three evidence levels:

- direct finite-size measurements;
- restricted-branch free-energy estimates used to seed scans;
- operational coherence thresholds that are not phase boundaries.

The generated `phase_boundary_catalog.csv` records this status and the source
for every point shown in the phase-diagram status figure.  Orange boxes in the
draft are result placeholders, not inferred conclusions.

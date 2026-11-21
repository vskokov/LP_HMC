# Combined (Z, L) umbrella analyses

`runs/cv_umbrella/combined/<Z>/<L>/` (git-ignored) holds symlinks to every completed
run of one (Z, L), across stages, so that `analyze_cv_umbrella.py --dir` combines them:

| dir | runs |
|---|---|
| Zm2/L12 | s2 m2m1p73_s21, validate m2m1p73_s121 |
| Zm2/L18 | s2 m2m1p73_s22, s2_zm2 m2m1p83_s31 |
| Zm2/L24 | s2_zm2 m2m1p88_s32 (local), s2_zm2_ext m2m1p88_s132 (Hazel) |
| Zm2/L30 | s2_zm2 m2m1p9_s33 |
| Zm1p1716/L16 | s2_zm1172 s40, s41, s42; s2_zm1172_prod s816, s826 |
| Zm1p1716/L24 | s2_zm1172_prod s824, s834 |

Analysis: `python3 scripts/analyze_cv_umbrella.py --dir runs/cv_umbrella/combined/<Z>/<L> --bootstrap 40`
(2026-11-21).

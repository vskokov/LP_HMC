"""Validated, umbrella-specific transport profiles and scaling proposals."""

from __future__ import annotations

import json
import math
from pathlib import Path

from hmc_defaults import HMC_DEFAULTS, STARTUP_HMC_DEFAULTS


SUPPORTED_SIZES = (6, 8, 12, 16, 18, 20, 24, 32)
ANCHOR_L = 24
CANONICAL_Z_MAX = 2.0
CANONICAL_BINDER_TOLERANCE = 0.01


def binder_canonical_combined_z(binders: list[float]) -> float:
    if len(binders) < 2:
        raise ValueError("canonical agreement requires two binder estimates")
    return abs(binders[0] - binders[1]) / CANONICAL_BINDER_TOLERANCE


def validate_profile_evidence(L: int, validation: dict[str, object]) -> None:
    required = (
        "worst_phase_hmc_acceptance", "minimum_edge_swap_acceptance",
        "minimum_histogram_overlap", "both_endpoints_visited",
        "stable_diffusion_both_phases", "confirmed_candidates",
        "canonical_combined_z",
    )
    if any(field not in validation for field in required):
        raise ValueError(f"L={L}: validated profile lacks required transport/canonical evidence")
    if not 0.65 <= float(validation["worst_phase_hmc_acceptance"]) <= 0.90:
        raise ValueError(f"L={L}: HMC acceptance is outside the validation band")
    if float(validation["minimum_edge_swap_acceptance"]) < 0.25:
        raise ValueError(f"L={L}: edge swap acceptance is below 0.25")
    if float(validation["minimum_histogram_overlap"]) < 0.30:
        raise ValueError(f"L={L}: histogram overlap is below 0.30")
    if not validation["both_endpoints_visited"] or not validation["stable_diffusion_both_phases"]:
        raise ValueError(f"L={L}: endpoint/diffusion validation did not pass")
    if int(validation["confirmed_candidates"]) < 2:
        raise ValueError(f"L={L}: the best two candidates were not confirmed")
    if abs(float(validation["canonical_combined_z"])) > CANONICAL_Z_MAX:
        raise ValueError(
            f"L={L}: ordered/disordered Binder agreement is worse than "
            f"{CANONICAL_Z_MAX:g} sigma"
        )


def proposed_profile(L: int) -> dict[str, object]:
    if L not in SUPPORTED_SIZES:
        raise ValueError(f"unsupported all-L umbrella size: {L}")
    epsilon = HMC_DEFAULTS.get(L, (0.0, 0))[0]
    if L == 20:
        left, right = HMC_DEFAULTS[18][0], HMC_DEFAULTS[24][0]
        fraction = (math.log(20) - math.log(18)) / (math.log(24) - math.log(18))
        epsilon = math.exp(math.log(left) + fraction * (math.log(right) - math.log(left)))
    # The scaling law counts ladder edges; a ladder has one more window.
    windows = round(160 * (L / ANCHOR_L) ** 1.5) + 1
    windows = max(2, windows)
    minimum = 5 * (windows - 1) ** 2
    startup_eps, startup_n_lf = STARTUP_HMC_DEFAULTS.get(
        L, STARTUP_HMC_DEFAULTS[18]
    )
    return {
        "schema_version": 1, "kind": "umbrella_transport_profile", "L": L,
        "validated": False, "epsilon": epsilon,
        "n_lf": None,
        "umbrella_windows": windows,
        "umbrella_min": 0.0, "umbrella_max": 0.4,
        "umbrella_kappa": 160_000 * (L / ANCHOR_L) ** 3,
        "umbrella_power": 1.3, "swap_every": 1,
        "startup_epsilon": startup_eps,
        "startup_n_lf": startup_n_lf, "startup_sweeps": L**3,
        "minimum_thermalization_sweeps": minimum,
        "maximum_thermalization_sweeps": 5 * minimum,
        "transport_gates": {
            "hmc_acceptance_min": 0.65, "hmc_acceptance_max": 0.90,
            "minimum_edge_swap_acceptance": 0.25,
            "minimum_histogram_overlap": 0.30,
            "both_endpoints_visited": True, "both_phases_stable": True,
        },
        "validation": {
            "provenance": "scaling proposal from validated L=24 anchor",
            "required_tuning": {
                "trajectory_lengths": [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                "epsilon_factors_if_needed": [0.9, 1.0, 1.1],
                "confirmation_candidates": 2,
            },
        },
    }


def load_profile(path: Path, L: int, require_validated: bool = True) -> dict[str, object]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read umbrella profile {path}: {exc}") from exc
    if profile.get("schema_version") != 1 or profile.get("kind") != "umbrella_transport_profile":
        raise ValueError(f"{path}: unsupported umbrella profile schema")
    if int(profile.get("L", -1)) != L:
        raise ValueError(f"{path}: profile L does not match requested L={L}")
    if require_validated and profile.get("validated") is not True:
        raise ValueError(f"{path}: production requires a validated umbrella profile")
    if require_validated:
        if not isinstance(profile.get("n_lf"), int) or int(profile["n_lf"]) < 1:
            raise ValueError(f"{path}: validated profile needs a positive n_lf")
        validation = profile.get("validation", {})
        if not isinstance(validation, dict) or not validation.get("provenance"):
            raise ValueError(f"{path}: validated profile needs validation provenance")
        validate_profile_evidence(L, validation)
    return profile

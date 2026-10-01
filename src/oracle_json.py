"""Lossless deterministic JSON schema for bounded-oracle results.

Python's oracle result uses tuple-valued plans/profiles and tuple keys in
``regret_by_profile``.  This adapter converts those values to a closed JSON
schema and reconstructs the original Python value exactly.
"""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1
TOP_LEVEL_FIELDS = {
    "schema_version", "optimum", "plan_count", "unique_profiles", "worlds",
    "vertices", "regret_by_profile", "h", "sql_profile_checks", "plans",
}


def _integer(value: Any, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an exact integer")
    return value


def _encode_plan(plan: Any) -> Any:
    if type(plan) is int:
        return plan
    if type(plan) not in (tuple, list) or len(plan) != 2:
        raise ValueError("invalid oracle plan")
    return [_encode_plan(plan[0]), _encode_plan(plan[1])]


def _decode_plan(plan: Any) -> Any:
    if type(plan) is int:
        return plan
    if type(plan) is not list or len(plan) != 2:
        raise ValueError("invalid serialized oracle plan")
    return (_decode_plan(plan[0]), _decode_plan(plan[1]))


def _profile(values: Any, name: str) -> tuple[int, ...]:
    if type(values) is not list:
        raise ValueError(f"{name} must be a list")
    return tuple(_integer(value, name) for value in values)


def to_jsonable(result: dict[str, Any]) -> dict[str, Any]:
    required = {
        "optimum", "plan_count", "unique_profiles", "worlds", "vertices",
        "regret_by_profile", "h", "sql_profile_checks", "plans",
    }
    if type(result) is not dict or set(result) != required:
        raise ValueError("unexpected oracle result fields")

    regrets = [
        {"profile": list(profile), "regret": result["regret_by_profile"][profile]}
        for profile in sorted(result["regret_by_profile"])
    ]
    h_rows = [
        {"mask": mask, "profile": list(result["h"][mask])}
        for mask in sorted(result["h"])
    ]
    plans = [
        {"plan": _encode_plan(plan), "profile": list(profile)}
        for plan, profile in result["plans"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "optimum": result["optimum"],
        "plan_count": result["plan_count"],
        "unique_profiles": result["unique_profiles"],
        "worlds": [list(world) for world in result["worlds"]],
        "vertices": result["vertices"],
        "regret_by_profile": regrets,
        "h": h_rows,
        "sql_profile_checks": result["sql_profile_checks"],
        "plans": plans,
    }


def from_jsonable(value: dict[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != TOP_LEVEL_FIELDS:
        raise ValueError("unexpected serialized oracle fields")
    if _integer(value["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported oracle JSON schema")

    worlds_raw = value["worlds"]
    regrets_raw = value["regret_by_profile"]
    h_raw = value["h"]
    plans_raw = value["plans"]
    if not all(type(x) is list for x in (worlds_raw, regrets_raw, h_raw, plans_raw)):
        raise ValueError("oracle collection fields must be lists")

    regret_by_profile: dict[tuple[int, ...], int] = {}
    for row in regrets_raw:
        if type(row) is not dict or set(row) != {"profile", "regret"}:
            raise ValueError("invalid regret_by_profile row")
        profile = _profile(row["profile"], "regret profile")
        if profile in regret_by_profile:
            raise ValueError("duplicate regret profile")
        regret_by_profile[profile] = _integer(row["regret"], "regret")

    h: dict[int, tuple[int, ...]] = {}
    for row in h_raw:
        if type(row) is not dict or set(row) != {"mask", "profile"}:
            raise ValueError("invalid h row")
        mask = _integer(row["mask"], "mask")
        if mask in h:
            raise ValueError("duplicate h mask")
        h[mask] = _profile(row["profile"], "h profile")

    plans: list[tuple[Any, tuple[int, ...]]] = []
    for row in plans_raw:
        if type(row) is not dict or set(row) != {"plan", "profile"}:
            raise ValueError("invalid plan row")
        plans.append((_decode_plan(row["plan"]), _profile(row["profile"], "plan profile")))

    result = {
        "optimum": _integer(value["optimum"], "optimum"),
        "plan_count": _integer(value["plan_count"], "plan_count"),
        "unique_profiles": _integer(value["unique_profiles"], "unique_profiles"),
        "worlds": [_profile(world, "world") for world in worlds_raw],
        "vertices": _integer(value["vertices"], "vertices"),
        "regret_by_profile": regret_by_profile,
        "h": h,
        "sql_profile_checks": _integer(value["sql_profile_checks"], "sql_profile_checks"),
        "plans": plans,
    }
    return result

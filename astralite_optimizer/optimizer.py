"""Optimisation helpers for maximising Astralite within weekly limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set

from pulp import LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum

from .production import ProductionProfile


@dataclass(slots=True)
class OptimizedItem:
    item_id: int
    name: str
    units: float
    astralite: float
    multiplier: float
    facility_minutes: Dict[str, float]
    profile: ProductionProfile


@dataclass(slots=True)
class OptimizationResult:
    items: List[OptimizedItem]
    total_astralite: float
    facility_usage: Dict[str, float]
    status: str


def optimise_portfolio(
    profiles: Sequence[ProductionProfile],
    weekly_limit: float,
    capacities: Mapping[str, float],
    bonus_item_ids: Iterable[int] | None = None,
) -> OptimizationResult:
    """Solve a linear programme that maximises Astralite under the constraints."""

    if weekly_limit <= 0 or not profiles:
        return OptimizationResult([], 0.0, {}, "No capacity")

    bonus_set: Set[int] = set(bonus_item_ids or [])
    variables = {
        profile.item_id: LpVariable(f"x_{profile.item_id}", lowBound=0)
        for profile in profiles
        if profile.sale_value > 0
    }
    if not variables:
        return OptimizationResult([], 0.0, {}, "No variables")

    def item_multiplier(profile: ProductionProfile) -> float:
        return 1.2 if profile.item_id in bonus_set else 1.0

    def item_value(profile: ProductionProfile) -> float:
        return profile.sale_value * item_multiplier(profile)

    ordered_profiles = [profile for profile in profiles if profile.item_id in variables]
    problem = LpProblem("AstraliteOptimisation", LpMaximize)
    problem += lpSum(item_value(profile) * variables[profile.item_id] for profile in ordered_profiles)

    # Facility capacity constraints
    for facility, capacity in capacities.items():
        if capacity is None or capacity <= 0:
            continue
        problem += (
            lpSum(
                profile.facility_minutes.get(facility, 0.0) * variables[profile.item_id]
                for profile in ordered_profiles
            )
            <= capacity
        )

    # Weekly Astralite cap constraint
    problem += (
        lpSum(item_value(profile) * variables[profile.item_id] for profile in ordered_profiles)
        <= weekly_limit
    )

    status_code = problem.solve(PULP_CBC_CMD(msg=False))
    status = LpStatus.get(status_code, str(status_code))

    items: List[OptimizedItem] = []
    facility_usage: Dict[str, float] = {facility: 0.0 for facility in capacities}
    total_astralite = 0.0

    if status_code in (1, "Optimal"):
        for profile in ordered_profiles:
            value = variables[profile.item_id].value() or 0.0
            if value <= 1e-6:
                continue
            multiplier = item_multiplier(profile)
            astralite = item_value(profile) * value
            usage = {
                facility: minutes * value
                for facility, minutes in profile.facility_minutes.items()
                if minutes > 0
            }
            for facility, amount in usage.items():
                facility_usage[facility] = facility_usage.get(facility, 0.0) + amount
            total_astralite += astralite
            items.append(
                OptimizedItem(
                    item_id=profile.item_id,
                    name=profile.name,
                    units=value,
                    astralite=astralite,
                    multiplier=multiplier,
                    facility_minutes=usage,
                    profile=profile,
                )
            )
        items.sort(key=lambda item: item.astralite, reverse=True)
    else:
        facility_usage.clear()

    return OptimizationResult(items=items, total_astralite=total_astralite, facility_usage=facility_usage, status=status)


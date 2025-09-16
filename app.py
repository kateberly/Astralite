"""FastAPI backend and static front-end for the Astralite optimiser."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Mapping

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from astralite_optimizer.data_loader import RemoteDataLoader
from astralite_optimizer.localization import Localization
from astralite_optimizer.optimizer import optimise_portfolio
from astralite_optimizer.production import (
    CRAFT_FACILITY,
    FISH_FACILITY,
    PLANT_FACILITY,
    ProductionCalculator,
    ProductionProfile,
    WEEK_MINUTES,
)
from astralite_optimizer.progression import ProgressionRepository

ABILITY_LABELS: Mapping[int, str] = {
    22: "Construction",
    34: "Planting",
    45: "Star Collecting",
    47: "Fish Keeping",
    48: "Animal Inviting",
}
MODELLED_CATEGORIES = {"plant", "fish", "furniture"}
FARMLAND_ITEMS = (1170000320, 1170000321, 1170000322, 1170000323)
FISH_POND_ITEMS = (1170000419,)
FACILITY_NAMES = {
    PLANT_FACILITY: "Plant plots",
    FISH_FACILITY: "Fish ponds",
    CRAFT_FACILITY: "Crafting queue",
}

loader = RemoteDataLoader()
localisation = Localization(loader.fetch_json("en"))
progression = ProgressionRepository(
    loader.fetch_json("TbHomeAbilityLevelUpRewardShowInfo"),
    loader.fetch_json("TbHomeAbilityTotalLevelValueInfo"),
)
calculator = ProductionCalculator(loader, localisation)
global_config = loader.fetch_json("TbHomeGlobalConfig")
BASE_WEEKLY_LIMIT = int(global_config.get("home_money_max", 100000))

ALL_PROFILES = calculator.supported_profiles()
MODELLED_PROFILES = [profile for profile in ALL_PROFILES if profile.category in MODELLED_CATEGORIES]

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Astralite Optimiser API")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _safe_minutes(value: float) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return float(value)


def _minutes_map(source: Mapping[str, float]) -> Dict[str, float]:
    return {
        facility: round(_safe_minutes(minutes), 4)
        for facility, minutes in source.items()
        if math.isfinite(minutes) and minutes > 0
    }


def _profile_detail(profile: ProductionProfile) -> Dict[str, object]:
    detail: Dict[str, object] = {"category": profile.category}
    if profile.category == "plant":
        growth = calculator.plant_growth.get(profile.item_id)
        if growth:
            detail["growth_minutes"] = round(growth.cycle_minutes, 4)
            detail["average_yield"] = round(growth.average_yield, 4)
            detail["seed_id"] = growth.seed_id
            if growth.farmland_ids:
                detail["farmland_ids"] = growth.farmland_ids
    elif profile.category == "fish":
        growth = calculator.fish_growth.get(profile.item_id)
        if growth:
            detail["growth_minutes"] = round(growth.cycle_minutes, 4)
            detail["fry_id"] = growth.fry_id
    elif profile.category == "furniture":
        craft_minutes = profile.facility_minutes.get(CRAFT_FACILITY)
        if craft_minutes and math.isfinite(craft_minutes):
            detail["craft_minutes"] = round(craft_minutes, 4)
    return detail


def _component_dict(component) -> Dict[str, object]:
    profile = component.profile
    per_unit_minutes: Dict[str, float] = {}
    total_minutes: Dict[str, float] = {}
    notes: List[str] = []
    category: str | None = None
    profile_item_id: int | None = None
    if profile:
        profile_item_id = profile.item_id
        category = profile.category
        for facility, minutes in profile.facility_minutes.items():
            if not math.isfinite(minutes) or minutes <= 0:
                continue
            per_unit_minutes[facility] = round(minutes, 4)
            total_minutes[facility] = round(minutes * component.quantity, 4)
        notes = profile.notes
    return {
        "item_id": component.item_id,
        "name": component.name,
        "quantity": component.quantity,
        "exchange_cost": component.exchange_cost,
        "category": category,
        "profile_item_id": profile_item_id,
        "facility_minutes": per_unit_minutes,
        "total_facility_minutes": total_minutes,
        "notes": notes,
    }


def _profile_dict(profile: ProductionProfile) -> Dict[str, object]:
    return {
        "item_id": profile.item_id,
        "name": profile.name,
        "sale_value": profile.sale_value,
        "ability_id": profile.ability_id,
        "ability_level": profile.ability_level,
        "category": profile.category,
        "facility_minutes": _minutes_map(profile.facility_minutes),
        "notes": profile.notes,
        "components": [_component_dict(component) for component in profile.components],
        "detail": _profile_detail(profile),
    }


class AbilityModel(BaseModel):
    id: int
    label: str
    max_level: int


class ProfileModel(BaseModel):
    item_id: int
    name: str
    sale_value: float
    ability_id: int
    ability_level: int
    category: str
    facility_minutes: Dict[str, float]
    notes: List[str] = Field(default_factory=list)
    components: List[Dict[str, object]] = Field(default_factory=list)
    detail: Dict[str, object] = Field(default_factory=dict)


class InitResponse(BaseModel):
    abilities: List[AbilityModel]
    base_weekly_limit: int
    facility_names: Dict[str, str]
    items: List[ProfileModel]
    modelled_categories: List[str]


class PlanItemModel(BaseModel):
    item_id: int
    name: str
    category: str
    units: float
    astralite: float
    multiplier: float
    per_unit_value: float
    facility_minutes: Dict[str, float]
    per_unit_facility_minutes: Dict[str, float]


class OptimiseResponse(BaseModel):
    status: str
    weekly_limit: float
    weekly_bonus: float
    ability_total: int
    plant_plots: int
    fish_ponds: int
    crafting_slots: int
    items: List[PlanItemModel]
    facility_usage: Dict[str, Dict[str, float]]
    capacities: Dict[str, Dict[str, float]]
    unlocked_item_ids: List[int]
    message: str | None = None


class OptimiseRequest(BaseModel):
    ability_levels: Dict[int, int] = Field(default_factory=dict)
    bonus_item_ids: List[int] = Field(default_factory=list)
    crafting_slots: int = Field(1, ge=1)

    @field_validator("ability_levels", mode="before")
    def _convert_ability_keys(cls, value):
        if isinstance(value, dict):
            return {int(key): int(level) for key, level in value.items()}
        return value

    @field_validator("bonus_item_ids", mode="before")
    def _convert_bonus_ids(cls, value):
        if isinstance(value, list):
            return [int(item) for item in value]
        return value


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Front-end not built yet")
    return FileResponse(index_path)


@app.get("/api/init", response_model=InitResponse)
async def api_init() -> InitResponse:
    abilities = [
        AbilityModel(
            id=ability_id,
            label=label,
            max_level=progression.max_level(ability_id),
        )
        for ability_id, label in ABILITY_LABELS.items()
    ]
    items = [
        ProfileModel(**_profile_dict(profile))
        for profile in sorted(MODELLED_PROFILES, key=lambda prof: prof.name)
    ]
    return InitResponse(
        abilities=abilities,
        base_weekly_limit=BASE_WEEKLY_LIMIT,
        facility_names=FACILITY_NAMES,
        items=items,
        modelled_categories=sorted(MODELLED_CATEGORIES),
    )


def _facility_payload(data: Mapping[str, float]) -> Dict[str, Dict[str, float]]:
    payload: Dict[str, Dict[str, float]] = {}
    for facility, minutes in data.items():
        safe_minutes = _safe_minutes(minutes)
        payload[facility] = {
            "minutes": round(safe_minutes, 4),
            "hours": round(safe_minutes / 60.0, 4),
        }
    return payload


@app.post("/api/optimise", response_model=OptimiseResponse)
async def api_optimise(payload: OptimiseRequest) -> OptimiseResponse:
    ability_levels: Dict[int, int] = {}
    for ability_id in ABILITY_LABELS:
        requested = payload.ability_levels.get(ability_id, 0)
        max_level = progression.max_level(ability_id)
        if max_level:
            ability_levels[ability_id] = max(0, min(int(requested), max_level))
        else:
            ability_levels[ability_id] = max(0, int(requested))

    total_level = sum(ability_levels.values())
    weekly_bonus = progression.weekly_bonus_for_total_level(total_level)
    weekly_limit = BASE_WEEKLY_LIMIT + weekly_bonus

    plant_plots = progression.sum_item_counts(34, ability_levels.get(34, 0), FARMLAND_ITEMS)
    fish_ponds = progression.sum_item_counts(47, ability_levels.get(47, 0), FISH_POND_ITEMS)
    crafting_slots = max(payload.crafting_slots, 1)

    capacities = {
        PLANT_FACILITY: plant_plots * WEEK_MINUTES,
        FISH_FACILITY: fish_ponds * WEEK_MINUTES,
        CRAFT_FACILITY: crafting_slots * WEEK_MINUTES,
    }

    unlocked_profiles = [
        profile
        for profile in MODELLED_PROFILES
        if ability_levels.get(profile.ability_id, 0) >= profile.ability_level
    ]

    bonus_ids = set(payload.bonus_item_ids[:4])
    result = optimise_portfolio(unlocked_profiles, weekly_limit, capacities, bonus_ids)

    plan_items = [
        PlanItemModel(
            item_id=item.item_id,
            name=item.name,
            category=item.profile.category,
            units=round(item.units, 4),
            astralite=round(item.astralite, 4),
            multiplier=item.multiplier,
            per_unit_value=round(item.profile.sale_value * item.multiplier, 4),
            facility_minutes=_minutes_map(item.facility_minutes),
            per_unit_facility_minutes=_minutes_map(item.profile.facility_minutes),
        )
        for item in result.items
    ]

    message: str | None = None
    if not plan_items:
        if not unlocked_profiles:
            message = "Increase ability levels to unlock saleable items."
        else:
            message = "No feasible plan within the current facility limits."

    facility_usage = _facility_payload(result.facility_usage)
    capacities_payload = _facility_payload(capacities)

    return OptimiseResponse(
        status=result.status,
        weekly_limit=weekly_limit,
        weekly_bonus=weekly_bonus,
        ability_total=total_level,
        plant_plots=plant_plots,
        fish_ponds=fish_ponds,
        crafting_slots=crafting_slots,
        items=plan_items,
        facility_usage=facility_usage,
        capacities=capacities_payload,
        unlocked_item_ids=[profile.item_id for profile in unlocked_profiles],
        message=message,
    )

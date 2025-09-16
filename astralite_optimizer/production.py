"""Logic for stitching gameplay datasets into production profiles."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional

from .data_loader import RemoteDataLoader
from .localization import Localization

ABILITY_CATEGORY = {
    22: "furniture",
    34: "plant",
    45: "meteor",
    47: "fish",
    48: "animal",
}

PLANT_FACILITY = "plant_plot"
FISH_FACILITY = "fish_pond"
CRAFT_FACILITY = "crafting"
WEEK_MINUTES = 7 * 24 * 60


@dataclass(slots=True)
class SaleItem:
    item_id: int
    ability_id: int
    ability_level: int
    sale_value: float
    ratio: float
    name: str
    category: str


@dataclass(slots=True)
class PlantGrowth:
    seed_id: int
    harvest_item_id: int
    growth_time_sec: int
    accelerated_time_sec: int
    average_yield: float
    farmland_ids: List[int]

    @property
    def cycle_minutes(self) -> float:
        return self.accelerated_time_sec / 60.0

    @property
    def minutes_per_item(self) -> float:
        if self.average_yield <= 0:
            return math.inf
        return self.cycle_minutes / self.average_yield


@dataclass(slots=True)
class FishGrowth:
    fry_id: int
    fish_id: int
    growth_time_sec: int
    accelerated_time_sec: int
    name: str
    yield_per_cycle: float = 1.0

    @property
    def cycle_minutes(self) -> float:
        return self.accelerated_time_sec / 60.0

    @property
    def minutes_per_item(self) -> float:
        if self.yield_per_cycle <= 0:
            return math.inf
        return self.cycle_minutes / self.yield_per_cycle


@dataclass(slots=True)
class MaterialRequirement:
    item_id: int
    quantity: float


@dataclass(slots=True)
class ComponentRequirement:
    item_id: int
    name: str
    quantity: float
    profile: Optional["ProductionProfile"]
    exchange_cost: Optional[int]


@dataclass(slots=True)
class ProductionProfile:
    item_id: int
    name: str
    sale_value: float
    ability_id: int
    ability_level: int
    category: str
    facility_minutes: Dict[str, float]
    components: List[ComponentRequirement]
    notes: List[str]

    def facility_summary(self) -> Dict[str, float]:
        return {k: round(v, 2) for k, v in self.facility_minutes.items() if v > 0}


def _parse_numbers(text: str) -> List[float]:
    numbers = re.findall(r"\d+(?:\.\d+)?", text or "")
    return [float(value) for value in numbers]


def _parse_average(text: str, fallback: float = 1.0) -> float:
    numbers = _parse_numbers(text)
    if not numbers:
        return fallback
    return sum(numbers) / len(numbers)


class ProductionCalculator:
    """Builds production profiles for saleable items."""

    def __init__(self, loader: RemoteDataLoader, localization: Localization) -> None:
        self._loader = loader
        self._localization = localization
        self.sale_items = self._load_sale_items()
        self.plant_growth = self._load_plant_growth()
        self.fish_growth = self._load_fish_growth()
        self.furniture_recipes = self._load_furniture_recipes()
        self.exchange_costs = self._load_exchange_costs()
        self._profile_cache: Dict[int, ProductionProfile] = {}

    def _load_sale_items(self) -> Dict[int, SaleItem]:
        raw = self._loader.fetch_json("TbHomeProductsSaleInfo")
        sale_items: Dict[int, SaleItem] = {}
        for entry in raw.values():
            item_id = int(entry["item_id"])
            ability_id = int(entry["ability_id"])
            ability_level = int(entry.get("ability_level", 0))
            ratio = float(entry.get("ratio", 0))
            rewards = entry.get("rewards", []) or []
            sale_value = sum(
                float(reward.get("num", 0))
                for reward in rewards
                if int(reward.get("item_id", 0)) == 14
            )
            name = self._localization.item_name(item_id)
            category = ABILITY_CATEGORY.get(ability_id, "other")
            sale_items[item_id] = SaleItem(
                item_id=item_id,
                ability_id=ability_id,
                ability_level=ability_level,
                sale_value=sale_value,
                ratio=ratio,
                name=name,
                category=category,
            )
        return sale_items

    def _load_plant_growth(self) -> Dict[int, PlantGrowth]:
        growth_data = self._loader.fetch_json("TbPlantingGrowthProcess")
        nutrient_data = self._loader.fetch_json("TbPlantingNutrient")
        default_speedup = 0
        for entry in nutrient_data.values():
            if int(entry.get("consume_count", 0)) == 0:
                default_speedup = int(entry.get("speedup_time", 0))
                break
        plant_growth: Dict[int, PlantGrowth] = {}
        for entry in growth_data.values():
            harvest_item = int(entry.get("harvest_item", 0))
            if not harvest_item:
                continue
            stages = entry.get("growth_stages", []) or []
            growth_time_sec = sum(int(stage.get("duration", 0)) for stage in stages)
            accelerated = max(0, growth_time_sec - default_speedup)
            average_yield = _parse_average(entry.get("estimate_harvests", "1"), fallback=1.0)
            farmland_ids = [int(fid) for fid in entry.get("compatible_farmland", []) or []]
            plant_growth[harvest_item] = PlantGrowth(
                seed_id=int(entry["seed"]),
                harvest_item_id=harvest_item,
                growth_time_sec=growth_time_sec,
                accelerated_time_sec=accelerated,
                average_yield=average_yield,
                farmland_ids=farmland_ids,
            )
        return plant_growth

    def _load_fish_growth(self) -> Dict[int, FishGrowth]:
        growth_data = self._loader.fetch_json("TbHomeFishGrowthConfig")
        nutrient_data = self._loader.fetch_json("TbHomeFishNutrientConfig")
        default_speedup = 0
        for entry in nutrient_data.values():
            if int(entry.get("consume_count", 0)) == 0:
                default_speedup = int(entry.get("accelerate_time", 0))
                break
        fish_growth_by_name: Dict[str, FishGrowth] = {}
        for entry in growth_data.values():
            fish_id = int(entry.get("fish_id", 0))
            name = self._localization.get(f"FISH_{fish_id}")
            if not name:
                continue
            growth_time = int(entry.get("growth_time", 0))
            accelerated = max(0, growth_time - default_speedup)
            fish_growth_by_name[name.lower()] = FishGrowth(
                fry_id=int(entry.get("fry_id", 0)),
                fish_id=fish_id,
                growth_time_sec=growth_time,
                accelerated_time_sec=accelerated,
                name=name,
            )
        # Map sale item IDs to growth data via the localised name.
        fish_growth: Dict[int, FishGrowth] = {}
        for sale in self.sale_items.values():
            if sale.category != "fish":
                continue
            key = sale.name.lower()
            if key in fish_growth_by_name:
                fish_growth[sale.item_id] = fish_growth_by_name[key]
        return fish_growth

    def _load_furniture_recipes(self) -> Dict[int, List[MaterialRequirement]]:
        raw = self._loader.fetch_json("TbFurnitureTableMakeInfo")
        recipes: Dict[int, List[MaterialRequirement]] = {}
        for entry in raw.values():
            furniture_id = int(entry["furniture_id"])
            materials = [
                MaterialRequirement(item_id=int(material["item_id"]), quantity=float(material.get("num", 0)))
                for material in entry.get("material_consume", []) or []
            ]
            time_minutes = float(entry.get("time", 0))
            recipes[furniture_id] = materials
            # We store craft time separately in a helper mapping.
            entry["_time_minutes"] = time_minutes
        self._furniture_time: Dict[int, float] = {
            int(entry["furniture_id"]): float(entry.get("_time_minutes", 0))
            for entry in raw.values()
        }
        return recipes

    def _load_exchange_costs(self) -> Dict[int, int]:
        raw = self._loader.fetch_json("TbFurnitureMakeMaterialExchangeInfo")
        return {int(entry["material_item_id"]): int(entry.get("exchange_ratio", 0)) for entry in raw.values()}

    def compute_profile(self, item_id: int) -> Optional[ProductionProfile]:
        return self._compute_profile(item_id, stack=set())

    def _compute_profile(self, item_id: int, stack: set[int]) -> Optional[ProductionProfile]:
        if item_id in self._profile_cache:
            return self._profile_cache[item_id]
        if item_id in stack:
            return None
        sale = self.sale_items.get(item_id)
        if not sale:
            return None
        stack.add(item_id)
        if sale.category == "plant":
            profile = self._build_plant_profile(sale)
        elif sale.category == "fish":
            profile = self._build_fish_profile(sale)
        elif sale.category == "furniture":
            profile = self._build_furniture_profile(sale, stack)
        else:
            profile = self._build_basic_profile(sale)
        stack.remove(item_id)
        if profile:
            self._profile_cache[item_id] = profile
        return profile

    def _build_basic_profile(self, sale: SaleItem) -> ProductionProfile:
        notes = [f"Production data for {sale.category} items is not yet modelled."]
        return ProductionProfile(
            item_id=sale.item_id,
            name=sale.name,
            sale_value=sale.sale_value,
            ability_id=sale.ability_id,
            ability_level=sale.ability_level,
            category=sale.category,
            facility_minutes={},
            components=[],
            notes=notes,
        )

    def _build_plant_profile(self, sale: SaleItem) -> ProductionProfile:
        growth = self.plant_growth.get(sale.item_id)
        facility_minutes: Dict[str, float] = {}
        notes: List[str] = []
        if growth:
            facility_minutes[PLANT_FACILITY] = growth.minutes_per_item
        else:
            notes.append("No planting data available; timing estimates missing.")
        return ProductionProfile(
            item_id=sale.item_id,
            name=sale.name,
            sale_value=sale.sale_value,
            ability_id=sale.ability_id,
            ability_level=sale.ability_level,
            category=sale.category,
            facility_minutes=facility_minutes,
            components=[],
            notes=notes,
        )

    def _build_fish_profile(self, sale: SaleItem) -> ProductionProfile:
        growth = self.fish_growth.get(sale.item_id)
        facility_minutes: Dict[str, float] = {}
        notes: List[str] = []
        if growth:
            facility_minutes[FISH_FACILITY] = growth.minutes_per_item
        else:
            notes.append("No fish growth data available; timing estimates missing.")
        return ProductionProfile(
            item_id=sale.item_id,
            name=sale.name,
            sale_value=sale.sale_value,
            ability_id=sale.ability_id,
            ability_level=sale.ability_level,
            category=sale.category,
            facility_minutes=facility_minutes,
            components=[],
            notes=notes,
        )

    def _build_furniture_profile(self, sale: SaleItem, stack: set[int]) -> ProductionProfile:
        materials = self.furniture_recipes.get(sale.item_id, [])
        facility_minutes: Dict[str, float] = {CRAFT_FACILITY: self._furniture_time.get(sale.item_id, 0.0)}
        components: List[ComponentRequirement] = []
        notes: List[str] = []
        if not materials:
            notes.append("Furniture recipe not found in extracted data.")
        for requirement in materials:
            component_profile = self._compute_profile(int(requirement.item_id), stack)
            component_name = self._localization.item_name(requirement.item_id)
            exchange_cost = self.exchange_costs.get(requirement.item_id)
            components.append(
                ComponentRequirement(
                    item_id=requirement.item_id,
                    name=component_name,
                    quantity=requirement.quantity,
                    profile=component_profile,
                    exchange_cost=exchange_cost,
                )
            )
            if component_profile:
                for facility, minutes in component_profile.facility_minutes.items():
                    facility_minutes[facility] = facility_minutes.get(facility, 0.0) + minutes * requirement.quantity
        return ProductionProfile(
            item_id=sale.item_id,
            name=sale.name,
            sale_value=sale.sale_value,
            ability_id=sale.ability_id,
            ability_level=sale.ability_level,
            category=sale.category,
            facility_minutes=facility_minutes,
            components=components,
            notes=notes,
        )

    def supported_profiles(self) -> List[ProductionProfile]:
        profiles: List[ProductionProfile] = []
        for item_id in self.sale_items:
            profile = self.compute_profile(item_id)
            if profile:
                profiles.append(profile)
        return profiles


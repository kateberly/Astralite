"""Player progression helpers derived from the extracted datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping


@dataclass(slots=True)
class LevelReward:
    ability_id: int
    level: int
    items: Dict[int, int]


@dataclass(slots=True)
class TotalLevelBonus:
    level: int
    weekly_bonus: int


class ProgressionRepository:
    """Aggregates level-up rewards and weekly bonuses."""

    def __init__(
        self,
        reward_data: Mapping[str, Mapping],
        total_level_data: Mapping[str, Mapping],
    ) -> None:
        self._rewards_by_ability: Dict[int, List[LevelReward]] = {}
        for entry in reward_data.values():
            raw_id = int(entry["id"])
            ability_id = raw_id // 1000
            level = raw_id % 1000
            items: Dict[int, int] = {}
            for reward in entry.get("des_item", []) or []:
                item_id = int(reward.get("item_id", 0))
                if not item_id:
                    continue
                items[item_id] = items.get(item_id, 0) + int(reward.get("num", 0))
            self._rewards_by_ability.setdefault(ability_id, []).append(
                LevelReward(ability_id=ability_id, level=level, items=items)
            )

        for rewards in self._rewards_by_ability.values():
            rewards.sort(key=lambda reward: reward.level)

        self._total_level_bonuses: List[TotalLevelBonus] = [
            TotalLevelBonus(level=int(entry["level"]), weekly_bonus=int(entry.get("gold_weekmax", 0)))
            for entry in total_level_data.values()
        ]
        self._total_level_bonuses.sort(key=lambda bonus: bonus.level)

    def ability_reward_items(self, ability_id: int, level: int) -> Dict[int, int]:
        """Return the cumulative item quantities unlocked up to ``level``."""

        totals: Dict[int, int] = {}
        for reward in self._rewards_by_ability.get(ability_id, []):
            if reward.level > level:
                break
            for item_id, qty in reward.items.items():
                totals[item_id] = totals.get(item_id, 0) + qty
        return totals

    def sum_item_counts(self, ability_id: int, level: int, item_ids: Iterable[int]) -> int:
        reward_totals = self.ability_reward_items(ability_id, level)
        return sum(reward_totals.get(item_id, 0) for item_id in item_ids)

    def max_level(self, ability_id: int) -> int:
        rewards = self._rewards_by_ability.get(ability_id, [])
        return rewards[-1].level if rewards else 0

    def weekly_bonus_for_total_level(self, total_level: int) -> int:
        bonus = 0
        for entry in self._total_level_bonuses:
            if entry.level > total_level:
                break
            bonus = entry.weekly_bonus
        return bonus


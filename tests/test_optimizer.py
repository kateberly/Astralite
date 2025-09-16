import math

from astralite_optimizer.data_loader import RemoteDataLoader
from astralite_optimizer.localization import Localization
from astralite_optimizer.production import (
    CRAFT_FACILITY,
    FISH_FACILITY,
    PLANT_FACILITY,
    ProductionCalculator,
)
from astralite_optimizer.progression import ProgressionRepository


def _create_calculator():
    loader = RemoteDataLoader()
    localisation = Localization(loader.fetch_json("en"))
    calculator = ProductionCalculator(loader, localisation)
    return loader, calculator


def test_cozy_bed_profile_has_expected_components():
    loader, calculator = _create_calculator()
    profile = calculator.compute_profile(1170000350)  # Cozy Bed

    assert profile is not None
    assert math.isclose(profile.facility_minutes.get(CRAFT_FACILITY, 0.0), 60.0, rel_tol=1e-6)
    assert math.isclose(profile.facility_minutes.get(PLANT_FACILITY, 0.0), 100.0, rel_tol=1e-6)
    assert math.isclose(profile.facility_minutes.get(FISH_FACILITY, 0.0), 3000.0, rel_tol=1e-6)

    components = {component.name: component for component in profile.components}
    assert "Golden Fragrant Cup" in components
    assert components["Golden Fragrant Cup"].quantity == 50
    assert math.isclose(
        components["Golden Fragrant Cup"].profile.facility_minutes[PLANT_FACILITY],
        2.0,
        rel_tol=1e-6,
    )
    assert "Blinko Fish" in components
    assert math.isclose(
        components["Blinko Fish"].profile.facility_minutes[FISH_FACILITY],
        100.0,
        rel_tol=1e-6,
    )


def test_progression_bonus_and_plots():
    loader = RemoteDataLoader()
    progression = ProgressionRepository(
        loader.fetch_json("TbHomeAbilityLevelUpRewardShowInfo"),
        loader.fetch_json("TbHomeAbilityTotalLevelValueInfo"),
    )

    assert progression.weekly_bonus_for_total_level(1) == 0
    assert progression.weekly_bonus_for_total_level(5) == 50000

    plots = progression.sum_item_counts(34, 20, (1170000320, 1170000321, 1170000322, 1170000323))
    assert plots == 26

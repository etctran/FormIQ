import pytest

from app.schemas.analysis import Exercise


def test_register_and_get_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scoring.profiles as profiles_module
    from app.scoring.profiles import ExerciseProfile, get_profile, register_profile

    # Skip _ensure_loaded's real per-exercise imports so this test is
    # unaffected by however many real profiles exist by the time it runs.
    monkeypatch.setattr(profiles_module, "_loaded", True)
    # register_profile mutates _REGISTRY in place, so patch in a copy —
    # otherwise this test's dummy SQUAT entry leaks into the real registry
    # for the rest of the process (squat.py, once imported, never re-runs
    # its module-level register_profile call to overwrite it back).
    monkeypatch.setattr(profiles_module, "_REGISTRY", dict(profiles_module._REGISTRY))

    dummy = ExerciseProfile(primary_signal=lambda frame: 1.0, fault_rules=[])
    register_profile(Exercise.SQUAT, dummy)
    assert get_profile(Exercise.SQUAT) is dummy


def test_get_profile_raises_for_unregistered_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scoring.profiles as profiles_module
    from app.scoring.profiles import get_profile

    monkeypatch.setattr(profiles_module, "_loaded", True)
    monkeypatch.setattr(profiles_module, "_REGISTRY", {})
    with pytest.raises(KeyError):
        get_profile(Exercise.SQUAT)

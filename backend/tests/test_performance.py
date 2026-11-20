import sys

import pytest

from companion.performance import disable_power_throttling


def test_power_throttling_is_disabled_on_windows_only() -> None:
    assert disable_power_throttling() is (sys.platform == "win32")


def test_other_platforms_are_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert disable_power_throttling() is False

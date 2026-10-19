"""The explanation probe supports an innocent template only when nothing contradicts it."""

from __future__ import annotations

from phos.eval.queue_explain import explain_alert


def test_one_signal_supports_a_sensor_fault() -> None:
    found = explain_alert(("level",), "level", witness=False, work_order=False)
    assert found.strong_innocent == ("sensor_or_device_fault",)
    assert found.has_strong_innocent


def test_a_broad_move_supports_a_process_disturbance() -> None:
    columns = ("a", "b", "c", "d")
    found = explain_alert(columns, "a", witness=False, work_order=False)
    assert found.strong_innocent == ("process_disturbance",)


def test_a_broad_witness_has_no_strong_innocent_member() -> None:
    columns = ("a", "b", "c", "d")
    found = explain_alert(columns, "b", witness=True, work_order=False)
    assert found.strong_innocent == ()
    assert found.has_strong_innocent is False


def test_a_work_order_makes_maintenance_a_strong_member() -> None:
    found = explain_alert(("level",), "level", witness=False, work_order=True)
    assert "engineering_maintenance" in found.strong_innocent
    assert "sensor_or_device_fault" in found.strong_innocent


def test_the_onset_must_be_a_member() -> None:
    try:
        explain_alert(("level",), "other", witness=False, work_order=False)
    except ValueError as error:
        assert "onset" in str(error)
    else:
        raise AssertionError("an onset outside the members was accepted")

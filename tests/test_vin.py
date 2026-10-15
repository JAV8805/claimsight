import pytest

from claimsight.evals.vin import check_digit, is_valid, synthesize

EXAMPLE = "1M8GDM9AXKP042788"  # widely published check-digit example


def test_check_digit_of_known_example() -> None:
    assert check_digit(EXAMPLE) == "X"
    assert is_valid(EXAMPLE)


def test_wrong_check_digit_is_invalid() -> None:
    assert not is_valid("1M8GDM9A1KP042788")


def test_synthesize_keeps_pattern_and_fixes_check_digit() -> None:
    vin = synthesize(EXAMPLE[:11], 123)
    assert vin[:8] == EXAMPLE[:8]  # manufacturer and model kept
    assert vin[9:11] == EXAMPLE[9:11]  # year and plant kept
    assert vin[11:] == "000123"  # invented serial
    assert is_valid(vin)


def test_synthesize_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        synthesize("TOO-SHORT", 1)
    with pytest.raises(ValueError):
        synthesize(EXAMPLE[:11], 1_000_000)

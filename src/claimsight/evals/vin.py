"""VIN utilities: North American check digit and privacy-preserving synthetic VINs."""

import re

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

_TRANSLITERATION = {
    **{str(d): d for d in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}  # fmt: skip
_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def check_digit(vin: str) -> str:
    """Return the expected check digit (position 9) for a 17-character VIN."""
    vin = vin.upper()
    if not VIN_RE.match(vin):
        raise ValueError(f"not a well-formed VIN: {vin!r}")
    total = sum(_TRANSLITERATION[c] * w for c, w in zip(vin, _WEIGHTS, strict=True))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def is_valid(vin: str) -> bool:
    """True if the VIN is well formed and its check digit is correct."""
    try:
        return vin.upper()[8] == check_digit(vin)
    except ValueError:
        return False


def synthesize(pattern: str, serial: int) -> str:
    """Build a synthetic VIN from a real 11-character pattern and an invented serial.

    Positions 1-8 (manufacturer, model) and 10-11 (year, plant) come from the pattern,
    so NHTSA decodes make/model/year correctly. Positions 12-17 are the invented serial,
    so the VIN does not point at a specific real vehicle. Position 9 is recomputed.
    """
    pattern = pattern.upper()
    if len(pattern) != 11:
        raise ValueError("pattern must be the first 11 characters of a VIN")
    if not 0 <= serial <= 999_999:
        raise ValueError("serial must be between 0 and 999999")
    draft = pattern[:8] + "0" + pattern[9:11] + f"{serial:06d}"
    return draft[:8] + check_digit(draft) + draft[9:]

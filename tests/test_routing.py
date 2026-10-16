from claimsight.rules.routing import route


def test_unclarified_event_is_never_fast_tracked() -> None:
    assert route("collision", True, [], event_clarified=True) == "fast_track"
    assert route("collision", True, [], event_clarified=False) == "adjuster_review"


def test_siu_beats_unclarified_event() -> None:
    assert route("collision", True, ["prompt_injection"], event_clarified=False) == "siu_referral"

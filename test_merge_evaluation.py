"""Deterministic tests for the evaluation merge semantics.

Runs standalone (python test_merge_evaluation.py) or via pytest. No network
and no vision calls: it exercises merge_evaluation._decide with crafted votes
so regressions in the PASS/FAIL policy are caught quickly.
"""
from merge_evaluation import _decide


def _vote(branch, pass_, conf, evidence):
    return {"branch": branch, "pass": pass_, "conf": conf, "evidence": evidence}


def test_pass_plus_pass_is_pass():
    vs = [
        _vote("frame", True, 0.9, "Frame 2: a blue circle is visible"),
        _vote("video", True, 0.8, "observed circle for the whole run"),
    ]
    assert _decide(vs, is_move=False, motion_confirmed=False)[0] is True


def test_pass_plus_fail_is_fail():
    vs = [
        _vote("frame", True, 0.9, "Frame 2: a blue circle is visible"),
        _vote("video", False, 0.9, "circle translated out of frame"),
    ]
    decision, evidence = _decide(vs, is_move=False, motion_confirmed=False)
    assert decision is False
    assert "CONTRADICTORY" in " ".join(evidence)


def test_fail_plus_unverifiable_is_fail():
    vs = [_vote("frame", False, 0.6, "no circle visible in any frame")]
    assert _decide(vs, is_move=False, motion_confirmed=False)[0] is False


def test_unsupported_pass_is_fail():
    vs = [_vote("frame", True, 0.95, "")]
    decision, evidence = _decide(vs, is_move=False, motion_confirmed=False)
    assert decision is False


def test_generic_evidence_pass_is_fail():
    vs = [
        _vote(
            "frame",
            True,
            0.95,
            "Evaluator returned unparseable output.",
        )
    ]
    decision, evidence = _decide(vs, is_move=False, motion_confirmed=False)
    assert decision is False


def test_strong_corroborated_pass_is_pass():
    vs = [
        _vote("frame", True, 0.95, "Frame 3: green arrow points right"),
        _vote("video", True, 0.9, "arrow visibly points right throughout"),
    ]
    assert _decide(vs, is_move=False, motion_confirmed=False)[0] is True


def test_single_strong_supported_pass_is_pass():
    vs = [_vote("frame", True, 0.95, "Frame 3: green arrow points right")]
    assert _decide(vs, is_move=False, motion_confirmed=False)[0] is True


def test_unverifiable_no_votes_is_fail():
    assert _decide([], is_move=False, motion_confirmed=False)[0] is False


def test_deterministic_motion_overrides_fail():
    vs = [_vote("frame", False, 0.95, "no movement seen")]
    assert _decide(vs, is_move=True, motion_confirmed=True)[0] is True


if __name__ == "__main__":
    fns = [
        v
        for v in list(globals().values())
        if callable(v) and getattr(v, "__name__", "").startswith("test_")
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as err:
            failed += 1
            print(f"FAIL {fn.__name__}: {err}")
    raise SystemExit(1 if failed else 0)

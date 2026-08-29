"""Merge the three evaluation branches into a final review.

Branches:
  frame    review_animation_v2   -> layout/readability/composition verdicts
  video    video_eval            -> temporal/motion/sequence verdicts
  geometry geometry.py           -> deterministic bounds/overlap errors + motion
  temporal temporal.py           -> deterministic motion/persistence/pacing

Verdict policy (stricter than pass-if-any-confirm, to avoid inflated scores):
  - Deterministic motion evidence (geometry declared motion, temporal motion
    analysis) is ground truth and overrides a fail on movement requirements.
  - Contradictory evidence (a PASS and a FAIL from different branches) FAILS
    and is marked REVIEW in the evidence; it can never automatically PASS.
  - Missing / unverifiable evidence FAILS.
  - A PASS is accepted only when it carries substantive supporting evidence,
    corroborated by a second branch or reaching confidence >= 0.7. A high
    confidence number alone never turns an unsupported PASS into a PASS.
"""
from geometry import has_declared_motion
from vision import is_movement_requirement

CONFIRM_CONFIDENCE = 0.7

# Generic/fallback evidence strings never count as real support.
_UNSUPPORTED_MARKERS = (
    "no branch produced evidence",
    "evaluator returned unparseable output",
    "no branch confirmed",
    "no evidence",
    "unable to verify",
)


def _has_support(v):
    """A vote is 'supported' only when it carries real evidence text.

    Confidence alone must never be treated as support: a high-confidence
    verdict with empty or generic evidence cannot justify a PASS.
    """
    ev = (v.get("evidence") or "").strip()
    if len(ev) < 10:
        return False
    low = ev.lower()
    return not any(m in low for m in _UNSUPPORTED_MARKERS)


def _votes_for(frame_result, video_result, requirements):
    votes = {}
    for requirement in requirements:
        rid = requirement["id"]
        vs = []
        frame_entry = next(
            (e for e in frame_result.get("requirements", []) if e["id"] == rid),
            None,
        )
        if frame_entry:
            vs.append(
                {
                    "branch": "frame",
                    "pass": bool(frame_entry["pass"]),
                    "conf": float(frame_entry.get("confidence", 0.0)),
                    "evidence": frame_entry.get("evidence", ""),
                }
            )
        if video_result and video_result.get("available"):
            v = next(
                (
                    e for e in video_result.get("requirement_verdicts", [])
                    if str(e.get("id")) == rid
                ),
                None,
            )
            if v is not None:
                vs.append(
                    {
                        "branch": "video",
                        "pass": bool(v.get("pass")),
                        "conf": float(v.get("confidence", 0.0)),
                        "evidence": v.get("evidence", ""),
                    }
                )
        votes[rid] = vs
    return votes


def _decide(vs, is_move, motion_confirmed):
    evidence_lines = [f"{v['branch'].upper()}: {v['evidence']}" for v in vs if v["evidence"]]

    # Deterministic motion evidence is ground truth for movement requirements.
    if is_move and motion_confirmed:
        evidence_lines.append("DETERMINISTIC: motion confirmed by temporal/geometry analysis")
        return True, evidence_lines

    if not vs:
        evidence_lines.append("No branch produced evidence (unverifiable).")
        return False, evidence_lines

    passes = [v for v in vs if v["pass"]]
    fails = [v for v in vs if not v["pass"]]

    # Any FAIL present means the evidence is either contradictory or a clean
    # fail; a PASS can never override it (never auto-PASS on contradiction).
    if fails:
        if passes:
            evidence_lines.append(
                "CONTRADICTORY: branches disagree (PASS vs FAIL) - failing conservatively."
            )
        else:
            evidence_lines.append("All branch(es) report FAIL - requirement failed.")
        return False, evidence_lines

    # Only PASS votes remain. Require substantive supporting evidence; an
    # unsupported high-confidence PASS is not accepted.
    supported = [v for v in passes if _has_support(v)]
    strong_supported = [
        v for v in supported if v["conf"] >= CONFIRM_CONFIDENCE
    ]

    if len(supported) >= 2 or strong_supported:
        return True, evidence_lines

    evidence_lines.append(
        "PASS lacks substantive supporting evidence - not accepted (confidence alone)."
    )
    return False, evidence_lines


def _dedupe(defects):
    seen = set()
    out = []
    for d in defects:
        key = (d.get("object"), d.get("frames"), d.get("problem"))
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def merge(frame_result, video_result, geometry_errors, geometry, temporal, requirements, prompt):
    """Combine branches into a final review dict (same shape as v2 output)."""
    motion_confirmed = bool(
        (temporal and temporal.get("has_motion"))
        or (geometry and has_declared_motion(geometry))
    )

    merged_requirements = []
    for requirement in requirements:
        rid = requirement["id"]
        vs = _votes_for(frame_result, video_result, requirements)[rid]
        is_move = is_movement_requirement(requirement["description"])
        decision, evidence_lines = _decide(vs, is_move, motion_confirmed)

        confidence = max((v["conf"] for v in vs), default=0.0)
        merged_requirements.append(
            {
                "id": rid,
                "pass": bool(decision),
                "confidence": confidence,
                "evidence": (" ".join(evidence_lines)).strip()
                or "No branch produced evidence.",
            }
        )

    failed_ids = [e["id"] for e in merged_requirements if not e["pass"]]

    # --- critique merge ---
    critique = dict(frame_result.get("visual_critique", {}) or {})
    defects = list(critique.get("observed_defects", []) or [])

    for d in defects:
        if "source" not in d:
            problem = str(d.get("problem", ""))
            d["source"] = "geometry" if problem.startswith("[hard]") or problem.startswith("[soft]") else "frame"

    if video_result and video_result.get("available"):
        for d in video_result.get("temporal_defects", []):
            defects.append(
                {
                    "object": d.get("object", "?"),
                    "frames": d.get("t", "all"),
                    "problem": d.get("problem", ""),
                    "source": "video",
                }
            )

    for d in geometry_errors:
        if d.get("severity") == "hard":
            defects.append(
                {
                    "object": d["object"],
                    "frames": d.get("frames", "all"),
                    "problem": f"[hard] {d['problem']}",
                    "source": "geometry",
                }
            )

    critique["observed_defects"] = _dedupe(defects)

    if video_result and video_result.get("available"):
        critique["pacing"] = video_result.get("pacing", "")
        critique["sequence_notes"] = video_result.get("sequence_notes", "")
    if temporal:
        critique["temporal_analysis"] = temporal

    # --- repair instructions with prefixes ---
    instructions = []
    for e in merged_requirements:
        if not e["pass"]:
            instructions.append(f"{e['id']} FAILED: {e['evidence'] or 'no branch confirmed'}")

    tag_map = {"video": "TEMPORAL", "frame": "FRAME", "geometry": "GEOMETRY"}
    for d in critique.get("observed_defects", []):
        tag = tag_map.get(d.get("source"), "DEFECT")
        instructions.append(
            f"{tag}: '{d.get('object')}' in {d.get('frames')}: "
            f"{d.get('problem')}. Fix this."
        )

    for s in critique.get("strengths", [])[:3]:
        instructions.append(f"PRESERVE: {s}")

    for imp in critique.get("improvements", []):
        if imp.get("priority") in ("high", "medium"):
            instructions.append(
                f"IMPROVE ({imp.get('priority')}, {imp.get('area')}): "
                f"{imp.get('suggestion')}"
            )

    return {
        "requirements": merged_requirements,
        "repair_instructions": instructions,
        "visual_critique": critique,
        "preserve": critique.get("strengths", []),
        "failed_ids": failed_ids,
    }

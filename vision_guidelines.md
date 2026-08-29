You verify ONE requirement against FRAME-BY-FRAME OBSERVATIONS of an
animation. The observations were written while looking at each frame
individually and are ordered chronologically.

Base your decision ONLY on the observations:
- clearly satisfied -> "pass": true
- clearly violated  -> "pass": false
- uncertain or not verifiable -> "pass": false

Uncertainty counts as failure. Never assume something happened just
because the request suggests it.
If a MEASURED OBJECT POSITIONS block is present, it was extracted
programmatically from the same observations. For any requirement about
movement or position, your decision MUST agree with that measurement.
Quote the relevant observation text in "evidence".
If a PREVIOUS ITERATION note is present, say in the evidence whether
the problem was fixed.



Return ONLY valid JSON:

{"id": "<the requirement id>", "pass": true, "confidence": 0.95, "evidence": "what the observations show"}


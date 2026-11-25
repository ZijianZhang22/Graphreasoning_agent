# Task 1 — Independent reviewer sheet (PENDING)

**Reviewer:** ______________________
**Review date (UTC):** ______________________
**DocAgent source SHA:** `d44ab1bb365fb7c151577dbd321a52fbf06d38ae`
**Wrapper branch:** `feature/docagent-task1-runpod-qwen3-8b`

This form supports Xiangrui's instruction that a **second person**
independently determines whether a stored claim is true at the old snapshot
and supported, contradicted, or unresolved at the new snapshot.

**Important:** The second reviewer should inspect the exact Git source
snapshots and test commands *before* reading the existing verifier verdicts
or agent/oracle grades. They must not sign off on the basis of an AI summary.

## Blind evidence review

For each case: source links and revisions are in `cases.json`.
Ask the reviewer to write their own old/new classification, why, and
supporting file/line or executed command. Do not fill in their answer.

| Case | Reviewer independent label at s | Reviewer independent label at t | Source/command evidence | Agree/disagree after unblinding |
|---|---|---|---|---|
| C01 moved owner | | | | |
| C02 interface/config drift | | | | |
| C03 obsolete test | | | | |
| C04 harmless change | | | | |

### Case-specific checks

**C01:** Locate `_dump_date` in both pinned revisions. Confirm at t which
symbol implementation is actually called by `http_date` and `cookie_date`;
a surviving import or file path alone is not an effective owner.

**C02:** Confirm acceptance and deprecation at s of
`Retry(method_whitelist=...)`. Confirm behavior at t and whether
`Retry(allowed_methods=...)` works. Record the exception type, module
actually imported, and dependencies / environment.

**C03:** Run `pytest --collect-only` with the old file/class selector in
the old revision; old and new selector in the newer revision. Record
exit code, number of collected items, relevant node IDs, and any dependency
errors. Distinguish a missing path (not collected) from a failing test.

**C04:** Compare the actual old/new implementation of `add_one` including
relevant executable AST. Do not infer behavior from just the changed-file
signal.

## Reproducibility / result notes

- Confirm both arm packet initial hashes match for each pair.
- Check real backend identity and at least one event trace per arm.
- Check the independently evaluated oracle; do not equate `live=true`
  with `oracle=pass`.
- Confirm whether the released DocAgent helper's file-level gate succeeded
  separately from the experimental Claim Verifier verdict.
- Record all environment-dependent checks that could not be completed.
- Existing primary memory claims are marked `researcher_authored` and
  are **not** documented historical incidents.
- Offline replay should regenerate the same Markdown without a model call.

## Reviewer final determination

**Accept / Accept with limitations / Disagree:** ______________________

**Disagreements and their resolution (or explicit unresolved status):**

____________________________________________________________________

**Reviewer acknowledgment:** ______________________

**Owner acknowledgment:** ______________________

> Do not edit `cases.json` to `human_review.status=approved` until the
> independent reviewer has genuinely completed this sheet. Keep the original
> model experiment immutable and store this signed review as a separate
> submission artifact.

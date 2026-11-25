# Task 1: four real-source-history case candidates

**Status (2026-11-25):** The upstream *source histories and code fragments* below
have been inspected at the pinned public GitHub commits. No Qwen3:8B session
has been executed and **no result has been claimed**. Labels remain
`human_review.status = pending` until a second researcher checks them.

All four source changes are real commits (`natural_commit`). Every old memory
note and task prompt here was **written for this experiment**
(`note_origin = researcher_authored`). Therefore these are controlled
historical-code case studies, **not historical incidents of an organization
being misled by an actually existing stale document**.

## Case matrix

| Case | Category | Project | s (old) | t (current) | Expected case-only checker | Task type |
|---|---|---|---|---|---|---|
| C01 | moved_owner | Werkzeug | `d9caf5b88cc2` | `0e2cd5013f29` | s supported → t unresolved (original symbol removed) → omit | localize |
| C02 | interface_drift | urllib3 | `9b95f29c575d` | `6446fef0cf43` | s supported → t contradicted → repair from signature | patch |
| C03 | obsolete_test | itsdangerous | `f685200bda58` | `c493cd846e9d` | s supported → t unresolved (old test file removed) → omit | localize |
| C04 | harmless_change | sampleproject | `00bed2f909a4` | `c54b977c7ebf` | s supported → t supported → reuse | patch |

The upstream **case-only checker** reports `unresolved`, not
`contradicted`, when a previous source file or symbol is absent; this is
deliberate. A separate human can establish the new owner or test path by
inspecting the current source. Never relabel an unresolved automated result
as if the released DocAgent checker proved the new location.

### C01 — Werkzeug: implementation moved to another module

- [Actual commit](https://github.com/pallets/werkzeug/commit/0e2cd5013f29cf18eef124e2061929c7cdb2df25)
- [Old implementation](https://github.com/pallets/werkzeug/blob/d9caf5b88cc2a5247de779bd13a69b63d60bd1c4/werkzeug/_internal.py):
  `def _dump_date(d, delim)` formats HTTP/cookie dates.
- [Current original module](https://github.com/pallets/werkzeug/blob/0e2cd5013f29cf18eef124e2061929c7cdb2df25/werkzeug/_internal.py):
  no longer defines `_dump_date`.
- [Current owner](https://github.com/pallets/werkzeug/blob/0e2cd5013f29cf18eef124e2061929c7cdb2df25/werkzeug/http.py):
  the same helper now lives in `werkzeug/http.py`.
- The old note names the old implementation module. The neutral task is
  localization; the answer is stored in the evaluator file, not in prompts.
- Limitation: a disappeared symbol alone does not prove a specific new owner;
  the additional current-file evidence above does.

### C02 — urllib3: removed constructor parameter

- [Old release 1.25.11](https://github.com/urllib3/urllib3/tree/9b95f29c575d73260ec4f5a8c0ea368cf242019e):
  `Retry.__init__(..., method_whitelist=DEFAULT_METHOD_WHITELIST, ...)`.
- [New release 2.0.0](https://github.com/urllib3/urllib3/tree/6446fef0cf432ca035169602a1447a0d8ef53e80):
  `Retry.__init__(..., allowed_methods=DEFAULT_ALLOWED_METHODS, ...)`;
  `method_whitelist` is absent and there is no `**kwargs` alias in this
  signature. This is a genuine interface change, not merely a warning.
- Task: change the default retry method policy to GET and HEAD but preserve
  explicit caller overrides. Oracle imports `Retry` from the patched source,
  checks default methods and explicit override behavior. The old base should
  fail the requested policy, and a correctly patched `t` should pass.
- Python/runtime compatibility of the historical 2.0.0 snapshot still needs
  a live check. Do not treat environment errors as model failures.

### C03 — itsdangerous: obsolete pytest selector

- [Actual rename commit](https://github.com/pallets/itsdangerous/commit/c493cd846e9dc4750e07c9e46785d265e26bf2ca)
- At s, `tests/test_serializer.py` defines `class TestSerializer(object)`.
- At t, that same file's **identical content** is located at
  `tests/test_itsdangerous/test_serializer.py`; the earlier file path is
  gone. A stored `pytest tests/test_serializer.py::TestSerializer` selector
  therefore points to a nonexistent file at t.
- The case runner's localize oracle **only checks the returned selector
  string**. It does not invoke pytest. Before describing this as a
  collection/runtime result, install historical test dependencies and run
  the two selectors on isolated snapshots; record exit code and collected
  node IDs. Path-existence evidence is already verified, but test runtime
  has not been executed.

### C04 — sampleproject: harmless blank-line removal

- [Actual commit](https://github.com/pypa/sampleproject/commit/c54b977c7ebf379f957db1cf7ce776608c67a521)
- `src/sample/simple.py` contains exactly:
  ```python
  def add_one(number):
      return number + 1
  ```
  at both revisions. The commit only removes two trailing blank lines.
- The old note that `add_one` is implemented here stays true despite the
  covered file's changed blob. Task: add `add_two(number)` without breaking
  `add_one`. Oracle imports both from the patched tree, tests positive,
  negative and floating-point examples.
- The upstream file-level gate may mark this as changed. The case-level
  verifier should still mark the old claim supported and reuse it.

## RunPod instructions

From the `docagent_task1_runpod` directory:

```bash
bash launch.sh setup
bash launch.sh smoke
bash launch.sh demo          # constructed C00 only, not counted
bash launch.sh validate "$PWD/cases.json"
python3 verify_case_evidence.py --cache /workspace/docagent-task1/cache
bash launch.sh run "$PWD/cases.json" C01
bash launch.sh run "$PWD/cases.json" C02
bash launch.sh run "$PWD/cases.json" C03
bash launch.sh run "$PWD/cases.json" C04
bash launch.sh report real
```

Each `run` produces one blind and one checked **real model** session when
Ollama is reachable. The `cases.evaluator.json` is read only by the grader.
For each case, review `summary.json`, `ledger.jsonl`, packet hashes and
oracle verdicts. Observed performance, notes taken during sessions,
dependency problems and reviewer decisions belong in subsequent reports,
not in this pre-run evidence file.

**Practical caution:** The old Werkzeug, urllib3, and itsdangerous histories
can take longer to clone/export than the tiny synthetic demo. Some old
dependencies may be incompatible with a modern Python environment; record
them as infrastructure problems rather than changing the s/t revisions
without a documented, matched rerun.

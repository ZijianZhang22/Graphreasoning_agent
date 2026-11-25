# Optional historical-document cases (separate from Xiangrui's required C01–C04)

These two optional cases are **not** part of the four required Task 1 cases.
Both use real repository changes and an old claim grounded in actual
**human-readable historical source documentation**, not invented incidents
of developers being misled. Reviewer sign-off is pending. Never report
them as observed historical documentation failures.

## C05 — Flask: deprecated argument name removed
- Project: https://github.com/pallets/flask
- s `9e686d93b69f0e73f801cc11a57839f4dfe2ca1a`; t `c2810ffdd2f2becbc37d35f63b69034b8b9ed5b8`.
- Verified by GitHub compare: **ahead by one commit, behind by zero**.
- Human documentation **present at s**: `CHANGES.rst` says
  ``attachment_filename`` was renamed to ``download_name``, and
  `src/flask/helpers.py`'s `send_file` docstring explicitly describes
  the rename. Its signature at s still accepts `attachment_filename`.
- The immediate t commit removes the deprecated argument and its related
  compatibility code. AST signature verifier expects `supported` at s
  and `contradicted` at t, with a direct repair to the current signature.
- This is a human-written historical changelog and API docstring, but the
  compact memory sentence was extracted/reworded for the experiment.
- The task asks for the **current argument name**, not the answer in the prompt.

## C06 — Requests: inline typing without ownership change
- Project: https://github.com/psf/requests
- s `8f6cda9969f4a98c45ea2922f6bcbefc02256202`; t `561e4b6889f53584c39a67f8794c53a414f68481` (direct parent/child).
- Human-readable documentation **present at s**:
  `src/requests/api.py`'s `request` function docstring states
  "Constructs and sends a Request"; `docs/user/quickstart.rst`
  documents Requests' HTTP methods.
- The code change adds inline type annotations to the API module, but
  `request` remains implemented in the same file, and its main behavior
  remains to send requests using a Session.
- The AST checker should report `supported` at both revisions;
  `policy_action=reuse` is the expected *verification policy*, **not**
  a claimed agent outcome.

## Reproducibility and limits
Both cases use the exact same existing `cases.py` driver and
`experimental-case-verifier-1`. Reuse the fixed Qwen3:8B model and
matched Blind/Checked arms if running these candidates. They are
**optional extension data**, not pooled with the primary 4-case rates.
A second member should independently inspect each historical text and
verify the case labels before formal reporting.

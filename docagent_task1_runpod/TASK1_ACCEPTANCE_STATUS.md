# Task 1 — acceptance status and remaining evidence

This file tracks **Xiangrui's required four cases only**. C05/C06 and
additional repeat runs are optional and must be reported separately.

## Evidence already collected (2026-11-25)

Primary data: `DocAgent_Task1_Repeated_20261125T213451Z-5947.zip`.
Three matched rounds (24 real Agent sessions; original case prompts unchanged).

| Case | Blind oracle pass | Checked oracle pass | Main behavior demonstrated |
|---|---:|---:|---|
| C01 moved owner | 0/3 | 2/3 | Stale owner can misdirect; checked recovery not certain |
| C02 interface drift | 3/3 | 3/3 | Old API changed, but task can succeed without using old keyword |
| C03 obsolete test | 0/3 | 3/3 | Check suppresses stale selector; agent searches current source |
| C04 harmless change | 3/3 | 3/3 | Correct claim retained despite source bytes changing |

**Important:** Success rate differences are descriptive only. The case
set is purposely selected and does not measure field prevalence. Agent
tool traces must support any statements about *reliance* on old memory.

## Released DocAgent file-level signal (observed in original ZIP)

- C01: `covered_file_changed=true`.
- C02: original gate returned `Unknown docagent_verified_at revision`.
- C03: original gate returned `Unknown docagent_verified_at revision`.
- C04: `covered_file_changed=true`.

Experimental Claim Verifier still returned predicate-level judgments.
The additional `audit_task1_evidence.py` retries the **released helper
unchanged**, using a shared-object Git worktree for a complete s..t
history. Its results must be labelled as a **supplemental audit**, never
substituted into original agent-run histories.

## Pending checks (not claimed completed)

1. C02 runtime probe of the old keyword at s, its rejection at t,
   and `allowed_methods` acceptance at t.
2. C03 actual pytest selector collection at s and t (three invocations),
   with exit codes, collection counts and relevant node IDs.
3. C01 implementation-owner verification and C04 AST equivalence audit.
4. Supplemental released-helper file gate for C02/C03 using actual code.
5. Offline report replay from saved trace files without model calls.
6. **Independent second-person blind source review and sign-off.**

The script runs items 1–5 and writes explicit errors where the RunPod
environment lacks dependencies. Item 6 requires a real second reviewer:
see `TASK1_REVIEW_TEMPLATE.md`.

## Do not overstate

- The primary four notes are `researcher_authored`, not discovered
  historical stale documentation incidents.
- C03 original task Oracle checks a **returned selector string**, not
  actual pytest test execution. The supplemental audit adds collection
  evidence; it does *not* retroactively change the Oracle.
- C02 success in both arms cannot establish that the old keyword
  misdirected the agent.
- A Git file-change warning is not proof that a claim became false.
- The original four cases meet the *count* requirement, but formal
  acceptance also requires the evidence and independent reviewer work.

## Run the supplement on the existing RunPod

```bash
cd /workspace/Graphreasoning_agent
git pull
cd docagent_task1_runpod
python3 -m py_compile audit_task1_evidence.py
python3 audit_task1_evidence.py --runs \
  /workspace/docagent-task1/repeat_batches/20261125T213451Z-5947/runs/primary/round_01
```

Upload the generated ZIP under
`/workspace/docagent-task1/acceptance_audits/` for independent analysis.

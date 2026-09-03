# Phase 9 operational incident record — 2026-09-03

Incident ID: `PHASE9-INC-20260903-001`
Status: `V2_1_ACQUISITION_FAILED_CLOSED_NO_CANONICAL_PUBLICATION_REMOTE_TRANSACTION_INVENTORY_AUDITED`

## Summary

The separately approved exploratory FXCM Drive Vault V2.1 acquisition ran once as GitHub Actions
Run `33705800232`, Run #1, Attempt #1, at reviewed head
`be864557a8e16d253e6aecf1519f85ad6162c1a3`. The workflow completed with conclusion `failure`.
The frozen availability mask described four remote source objects as present that did not satisfy the
frozen acquisition-time object checks. V2.1 therefore failed closed and did not create or publish the
canonical `v2` / `COMMITTED` vault.

This is an exploratory source-integrity and custody incident. It is not a Formal Phase 9 outcome
incident and does not authorize any change to Formal Phase 9, Count-only, Batch 6, returns, or MT5.

## GitHub evidence

- Repository: `tgkfnfnfv9-stack/Gpt-Verification--software`
- Workflow: `phase9-exploratory-fxcm-private-drive-vault-acquisition-v2-1`
- Run URL: `https://github.com/tgkfnfnfv9-stack/Gpt-Verification--software/actions/runs/33705800232`
- Run identity: Run #1, Attempt #1
- Head SHA: `be864557a8e16d253e6aecf1519f85ad6162c1a3`
- Terminal conclusion: `failure`
- Jobs: 17 total; 12 success, 4 failure, 1 skipped
- Public GitHub artifacts: 0
- `preflight`: success
- `prepare-vault`: success
- Successful year jobs: 2012 through 2021 inclusive
- Failed year jobs: 2022, 2023, 2024, 2025
- `finalize-vault`: skipped
- Every executed year job's always-run local price workspace removal step: success

## Exact failures

| Year | Job ID | Failed step | Terminal error |
|---|---:|---|---|
| 2022 | `100495623867` | `Acquire exact frozen-present V2 year inside uncommitted transaction` | `empty frozen source object` |
| 2023 | `100495623829` | `Acquire exact frozen-present V2 year inside uncommitted transaction` | `empty frozen source object` |
| 2024 | `100495623865` | `Acquire exact frozen-present V2 year inside uncommitted transaction` | `source object is not gzip` |
| 2025 | `100495623790` | `Acquire exact frozen-present V2 year inside uncommitted transaction` | `source object too small` |

These failures are consistent with the frozen rule
`frozen_present_object_becomes_unavailable_action = FAIL_NO_SEAL`. They do not permit a dynamic mask
change, forward fill, interpolation, or silent removal of a year, symbol, periodicity, or week.

## Custody state

- `prepare-vault` successfully created the uncommitted transaction named
  `v2-txn-run-33705800232` with initial state `ACQUIRING`.
- Read-only inventory Run `33732233208` independently established that the transaction is the root's
  only child and its metadata is valid. There is no canonical `v2` name match.
- The 2012–2021 year stages each contain 50 valid archive metadata records and one valid year
  manifest: 500 archives and 10 manifests in total, with 2,548,863,404 aggregate archive bytes.
- The failed 2022–2025 year stages exist but are empty: 200 expected archives and four year manifests
  are absent. No partial archive object was observed in those stages.
- `finalize-vault` was skipped, so no transaction-wide manifest or seal was verified and no canonical
  `v2` folder was intentionally published.
- The V2.1 contract prohibits automatic remote cleanup. No Drive object was deleted, renamed, moved,
  patched, or otherwise cleaned up after the failure.
- Secret values were not read or recorded in this incident report.

## Research-boundary effect

- Exploratory FXCM price access occurred under the user's separate one-time V2.1 authorization.
- Formal Phase 9 authorization effect: `false`.
- The user's preregistered acknowledgement already retires Formal Phase 9 unseen claims for the
  exploratory 2019-plus intervals accessed by this run.
- Count-only and Batch 6 remain unauthorized and unexecuted.
- No candidate signal, return, return sign, MFE, MAE, edge, win/loss, profit factor, drawdown,
  p-value, confidence interval, ranking, or MT5 logic was calculated by this workflow.
- Confirmed Phase 9 edge count remains 0.

## Read-only inventory closure

The separately approved metadata-only inventory completed successfully as Run `33732233208`, Run #1,
Attempt #1, at head `800c16257098bc8c2f152fa9d45804ffec81ebad`. The downloaded Artifact's
GitHub digest, exact two-file allowlist, report manifest, canonical JSON, run identities, and price-free
verifier all passed independent verification. The authoritative audit is
`research/phase9-exploratory-fxcm-20260901/results/run-33732233208/FXCM_DRIVE_VAULT_RUN1_READ_ONLY_INDEPENDENT_AUDIT.json`.

The run used Drive metadata `GET` only. Drive file content bytes, Drive mutations, FXCM requests, and
price bytes were all zero. It calculated no research statistics and has no Formal authorization effect.

## Frozen next gate

Stop before cleanup or recovery. A cleanup design and a versioned recovery-acquisition design are
different actions and must not be conflated. Either path requires its own reviewed, versioned contract;
execution then requires a later, separate explicit user approval against the then-current public
`main` SHA. Until a complete canonical vault is independently audited, Count-only and Batch 6 remain
blocked.

## Prohibited follow-up

- Do not rerun or replay V2.1 Run `33705800232`.
- Do not use `Re-run jobs`.
- Do not delete, rename, move, patch, or manually reorganize the Drive transaction.
- Do not change the frozen availability mask in place.
- Do not acquire replacement price objects without a new versioned contract and separate approval.
- Do not run Count-only, Batch 6, Return/OOS, or MT5.
- Do not treat the ten complete year stages as a committed vault before a separately authorized
  recovery completes the missing years and a canonical vault is independently audited.

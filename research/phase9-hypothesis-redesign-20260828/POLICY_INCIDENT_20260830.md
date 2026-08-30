# Policy Incident 2026-08-30

incident_id: `PHASE9-INC-20260830-001`
status: `WORKFLOW_SCHEMA_REJECTED_NO_JOB_NO_DATA_ACCESS_FIXED`

## What happened

Commit `b7a9b6239aa38e44f076ad15fcbe8d5c472c9dc1` added the manual-only
`phase9-acquisition-only` workflow. GitHub created validation Run
`33289406745` on that push and rejected the workflow before constructing a job.

The annotation reported that the `runner` context was unavailable in job-level
`env` for the three `${{ runner.temp }}` expressions.

## Observed facts

- Trigger shown by GitHub: push
- Workflow conclusion: failure
- Jobs: 0
- Steps: 0
- Artifacts: 0
- Authentication attempted: no
- Market-price request: no
- Phase 9 price files: 0
- Return, MFE, MAE, edge, win rate, p-value: not calculated or viewed
- Forbidden-period access: none

This was a workflow schema-validation failure, not an acquisition attempt.

## Fix

The job-level `runner.temp` expressions were removed. A shell step now derives
`RAW_DIR`, `CACHE_ROOT`, and `METADATA_DIR` from GitHub's default `RUNNER_TEMP`
environment variable after the runner starts and writes them to `GITHUB_ENV`.

The acquisition remains fail-closed before credentials and prices because the
dependency and reproducible-runner lock files are intentionally absent.

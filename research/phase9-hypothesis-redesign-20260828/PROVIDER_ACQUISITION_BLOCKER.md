# Phase 9 Provider / Acquisition Blocker

Status: `PUBLIC_ENDPOINT_PATH_REJECTED; JFOREX_SELECTED; S1B_GATE_A_PASS; PRICE_BLOCKED_PENDING_GATE_B_AND_REMAINING_RUNTIME_CONTROLS`

Recorded: 2026-08-29 UTC

This decision was made before any Phase 9 market-price file, return, MFE, MAE,
edge, signal count, or candidate outcome was acquired or inspected.

## Decision

Do not use the rejected `dukascopy-go` public-endpoint path. Phase 8 data
workflows remain disabled. The replacement Phase 9 workflow uses Dukascopy's
official authenticated JForex Tester API. Market-data acquisition remains
blocked; configuring Secrets or giving manual confirmations does not by itself
authorize dispatch.

## Rejected public-endpoint P0 blockers

### 1. Provider automation permission is not established

Dukascopy's official Terms of Use, section 3, says automated devices, programs,
tools, algorithms, processes, or methodologies may not access, acquire, copy, or
monitor website data without Dukascopy's prior express written consent.

Source checked on 2026-08-29:

- https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/

No evidence of prior express written consent is recorded in this repository.
The previous `PRIVATE_NONCOMMERCIAL_RESEARCH_CONFIRMED` workflow input is not a
substitute for provider consent.

### 2. The planned direct-H1 request is not hard-clipped at the frozen boundary

The pinned `dukascopy-go v0.2.0` implementation obtains H1 bars from a monthly
endpoint. For the frozen end date it requests the August 2019 payload and only
then filters rows locally. That request can receive data at or after
`2019-08-28T00:00:00Z`.

This violates the frozen requirement that requests, caches, and artifacts—not
only final CSV rows—must remain inside:

`2013-01-01T00:00:00Z <= timestamp < 2019-08-28T00:00:00Z`

Relevant pinned source:

- tag commit: `7a6759c06b4b9a84af62a3a265fc62443f56f177`
- `pkg/dukascopy/download_bars.go`, `downloadHourlyBars`

M15 uses day-scoped requests, but acquiring M15 alone does not satisfy the
frozen provider-direct H1 requirement. Deriving H1 from M15 is not an allowed
silent substitution.

### 3. Downloader execution license is unresolved

The pinned v0.2.0 tag tree and registered release archive contain no LICENSE
file. The repository statement previously recorded for private research did not
exist in that pinned distribution and has been removed from the authorization
logic. No execution permission is inferred.

## What remains allowed

- Read and test repository code without market data.
- Inspect provider documentation, terms, instrument catalogs, and API schemas
  without viewing price outcomes.
- Select and freeze a compliant provider before the first price acquisition.
- Run plan-only and synthetic-data safety tests.

## Provider decision

The replacement source channel must satisfy all of the following before acquisition:

1. Automated historical-data access is explicitly authorized for this use.
2. Exact `from`/`to` network requests can be hard-clipped before 2019-08-28.
3. Provider-direct M15 and H1 BID/ASK OHLC plus tick-volume-equivalent fields are
   available for all 12 preregistered research instruments.
4. The instrument catalog confirms the two Energy legs and their 2013 coverage.
5. Provider symbols, terms/version evidence, endpoint identity, and downloader
   implementation are committed and hash-locked before price access.

The selected path is the official authenticated JForex Tester API. It retains
Dukascopy and the same 12 research instruments, uses the requested source
period and side directly, and hard-codes the time interval before download.
OANDA v20 remains rejected for this version because it would remap the provider
and Energy symbols.

## Resume conditions

S1B Gate A Run `33376110507` completed the locked 116-JAR static inventory and
recorded 28 native entries. This is evidence only, not acquisition authorization.

Resume acquisition only after all of the following have been completed and
separately audited:

1. Freeze the 28 native entries in a later commit as a Gate B exact-match
   allowlist; do not self-authorize from the same discovery run.
2. Scan the shaded runner and prove actual native loading/mapped-DSO behavior.
3. Enforce child-process and OS-level egress controls.
4. After terms confirmation and a separate manual authorization, observe and
   hash-lock the remote JNLP/runtime closure without requesting market prices.
5. Implement streaming Full-QC for all 48 direct series in the acquisition run.
6. Configure a user-approved private raw-data custody path if raw persistence is
   required; raw prices must not enter Git or public Artifacts.
7. Complete a final pre-dispatch audit. Only then may credentials and the exact
   manual confirmations be used for a single acquisition/QC dispatch.

See `JFOREX_SOURCE_CHANNEL_AMENDMENT.md`, `S1B_RUNTIME_QC_PREFLIGHT.md`, and
`results/s1b-run-33376110507/S1B_AUDIT.json`.

Until then:

- S1B Gate A static inventory: `PASS_EVIDENCE_ONLY`
- Gate B exact-match allowlist: `PENDING_SEPARATE_COMMIT`
- acquisition: `BLOCKED_PENDING_GATE_B_AND_REMAINING_RUNTIME_CONTROLS`
- full quality gate: `BLOCKED`
- Count-only Gate: `BLOCKED`
- return/MFE/MAE/edge backtest: `BLOCKED`
- Development/OOS/Final Holdout access: `PROHIBITED`

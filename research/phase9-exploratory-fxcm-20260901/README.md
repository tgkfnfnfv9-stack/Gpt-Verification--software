# Phase 9 Exploratory FXCM Fast Track

Status: `FX8_H1_ACQUISITION_QC_ONLY_NOT_FORMAL_PHASE9`

This track makes a real, provider-authorized data path executable without
pretending that it completes Formal Phase 9.

- Source: FXCM official `fxcm/MarketData` CandleData endpoint
- Pinned source repository head: `924393dd545fab187527d95ef8b1178284b274b6`
- Instruments: Formal FX 8 only
- Source bars: direct H1 Bid/Ask OHLC
- Period: 2017-01-01 through 2018-12-31 exclusive
- Persistent output: bounded QC/inventory metadata only

FXCM's official README publishes the URL template, 2017--2020 coverage and
Python download examples. The selected years are inside Formal Phase 9's outer
allowed interval. Raw files, canonical prices and full observed-timestamp lists
remain in `RUNNER_TEMP` and are deleted after same-run integrity QC.

This is partial exploratory infrastructure. It has no Formal authorization
effect and does not satisfy the missing XAUUSD, XAGUSD, Brent or WTI inputs,
M15 input, provider schedule, Energy roll metadata, Count-only Gate or Full-QC.
Observed timestamps are not an independent provider schedule.

No signals or outcomes are calculated. Returns, return signs, MFE, MAE, edge,
wins, win rate, Profit Factor, drawdown, cumulative R, p-values, confidence
intervals, rankings and outcome charts are absent by construction.

## QC amendment after the first real run

Run `33477252915` at head `70593000cee5fd113719722fef25505b395df87e`
downloaded the frozen 832 weekly source files, then failed on the first observed
`ASK Open < BID Open` record. Cleanup succeeded and no Artifact was uploaded.
The price-free audit is recorded under `results/run-33477252915/`.

Contract v1.1.0 is a prospective retry amendment. It does not retroactively
validate the failed run. It preserves the exact crossed-open predicate, does
not add a tolerance or change any price, and quarantines both sides of each
crossed row from the ephemeral usable series. Only per-symbol counts and
SHA-256 identities are retained in the price-free inventory. Any nonzero count
keeps Formal Full-QC, Count-only and all outcome work blocked.

## Operational amendments after Runs 2 and 3

Run `33479424685` completed acquisition and QC, but its Artifact manifest
incorrectly included a self-hash captured while the manifest was still empty.
The inventory payload passed independent audit, but that Artifact is not
canonical. Commit `5e97795b0d74e55f87278e01af1668089ad7edf7` changed the
manifest convention to one payload-only line and added a regression test.

Run `33481035804` at that head passed all 13 tests, then stopped during source
download after the remote connection was reset. No Artifact was uploaded and
working-price cleanup succeeded. The prospective V3 operational amendment
retries only transient transport failures, at most four attempts with fixed
1, 2 and 4 second waits. HTTP status, redirect, size, gzip, schema and all QC
failures remain immediately fail-closed. The URL set, period, symbols,
timeframe, provider contract and outcome prohibitions are unchanged.

## Canonical exploratory inventory

Run `33482595275` at head `b2eaf84e774f9ce1272344f71ac14afcb0f6849a`
completed all workflow steps. Artifact `9790552032` was independently checked
against its GitHub digest, exact two-file allowlist, payload-only manifest,
contract, 832 source identities, per-symbol inventories and aggregate hashes.
The exact price-free Artifact payload and its separate canonical allowlist are
stored under `results/run-33482595275/`.

This is canonical only for the exploratory FX8 H1 source/QC inventory. It is
not an independent provider schedule, not Formal Phase 9 price custody, and
does not authorize acquisition, Count-only, signals or outcomes.

# Phase 9 JForex Source-Channel Amendment

Status: `FROZEN_PRE_ACQUISITION_NO_OUTCOME_VIEWED`

Recorded: 2026-08-29 UTC

## Reason

The original uncommitted acquisition draft used `dukascopy-go v0.2.0` against a
public endpoint. Red-team review found three pre-execution blockers: automated
public-endpoint terms, an unresolved downloader license, and a month-scoped H1
request that could receive timestamps beyond the Phase 9 boundary. No Phase 9
market-price file or outcome was acquired.

## Frozen replacement

- Provider remains Dukascopy Bank SA.
- Access channel becomes the official authenticated JForex Tester API.
- Client is `DDS2-jClient-JForex 3.6.51`; JForex API is `2.13.99`.
- The 12 research instruments are unchanged.
- M15 and H1 remain provider-source periods; deriving H1 from M15 is prohibited.
- BID and ASK are acquired in separate source-side Tester runs.
- Canonical `tick_volume` is the BID-bar volume. ASK-bar volume is retained only
  as a quality diagnostic; mismatch counts are recorded and cannot be used to
  choose the more favorable side after acquisition.
- All four runs use `ITesterClient.InterpolationMethod.FOUR_TICKS` only to replay
  the selected provider source bars; the recorded output is the selected
  period/side `IBar`, not a strategy return.
- No order method exists in the acquisition source.

## Time boundaries

Outer frozen authorization remains:

`2013-01-01T00:00:00Z <= timestamp < 2019-08-28T00:00:00Z`

Actual requests are frozen before acquisition as:

| Source | Start inclusive | End exclusive |
|---|---|---|
| M15 BID/ASK, all 12 | 2013-01-01T00:00:00Z | 2019-08-28T00:00:00Z |
| H1 BID/ASK, all 12 | 2013-01-01T00:00:00Z | 2019-08-01T00:00:00Z |

The H1 tail `[2019-08-01, 2019-08-28)` is excluded uniformly at the user's
explicit direction before data acquisition. It may not be restored, replaced
with derived H1, or varied by instrument after counts or outcomes. The exclusion
must be recorded in every acquisition and quality manifest. It reduces coverage
and can cause a candidate to fail Count-only as underpowered; thresholds may not
be relaxed.

## Authentication and secret handling

- Use a Dukascopy JForex demo account governed by its account terms. The frozen
  JNLP endpoint is the demo service; do not enter live-account credentials.
- Store username and password only as repository or environment GitHub Secrets:
  `DUKASCOPY_USERNAME`, `DUKASCOPY_PASSWORD`.
- Never place credentials in workflow inputs, logs, artifacts, Git, or chat.
- The workflow is manual-only and requires both exact confirmation strings.
- Raw CSV and JForex cache remain in unique GitHub runner temporary directories.
- Only metadata, SHA-256, counts, bounded gap samples, dependency identity, and
  runtime identity may be uploaded.

## Gates unchanged

This amendment changes only the acquisition channel and the pre-outcome uniform
H1 tail exclusion. Candidate definitions, instruments, timeframes, thresholds,
controls, multiplicity, outcomes, and cost stresses remain frozen. Full quality
QC, Energy roll metadata, Count-only Gate, and all outcome calculations remain
blocked in that order.

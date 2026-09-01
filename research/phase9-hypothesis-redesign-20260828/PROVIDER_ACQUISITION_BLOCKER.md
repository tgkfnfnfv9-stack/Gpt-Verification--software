# Phase 9 Provider / Acquisition Blocker

Status: `JFOREX_SELECTED; INITIAL_REMOTE_JNLP_IDENTITY_AUDITED; FOLLOWUP_BLOCKED; CONNECTION_DISPATCH_BLOCKED; PROVIDER_SCHEDULE_SOURCE_P0_BLOCKED; PRICE_BLOCKED`

Recorded: 2026-08-29 UTC

Last audited: 2026-09-01 UTC

This decision was made before any Phase 9 market-price file, return, MFE, MAE,
edge, signal count, or candidate outcome was acquired or inspected.

## Decision

Do not use the rejected `dukascopy-go` public-endpoint path. Phase 8 data
workflows remain disabled. The replacement Phase 9 workflow uses Dukascopy's
official authenticated JForex Tester API. Market-data acquisition remains
blocked; configuring Secrets or giving manual confirmations does not by itself
authorize dispatch.

## Provider schedule source P0 blocker (2026-09-01)

The frozen Full-QC contract requires a complete, versioned, price-independent
provider schedule for 12 instruments and M15/H1. The repository currently has
no authoritative source for those historical bytes:

- `data_manifest/trading_calendar.json` still records
  `provider_schedule_version=NO_VERSION_AVAILABLE_YET`.
- No frozen provider schedule source, 24-file inventory, inventory manifest, or
  canonical exact-match allowlist exists.
- A generic Monday-Friday grid, current SDK market-hours template, inferred
  holiday list, or raw-price timestamp set cannot support the contract's
  `complete_interval_inventory=true` claim.
- JForex API 2.13.99 exposes historical offline intervals through
  `IDataService.getOfflineTimeDomains(from,to,instrument)`, but the documented
  access path is through a strategy `IContext` after JForex connection. That
  conflicts with the current prohibition on external JNLP, JForex connect,
  availability access, and price access before the remaining blockers and a
  separate authorization Gate are complete.
- The API describes offline intervals as weekend intervals; completeness for
  historical holidays, maintenance, Energy daily sessions, and session-rule
  changes remains unproven.

Official API references audited without connecting to JForex or requesting data:

- https://www.dukascopy.com/client/javadoc3/com/dukascopy/api/IDataService.html
- https://www.dukascopy.com/client/javadoc3/com/dukascopy/api/IContext.html

Therefore no schedule inventory or allowlist may be fabricated or frozen. Two
resolution paths were considered:

1. identify and hash-lock a Dukascopy-published, versioned, licensed historical
   schedule source covering the complete frozen intervals; or
2. create a separate, user-approved metadata-only connection amendment that
   changes the Gate order and mechanically prohibits availability, historical
   bars, price, order, and Outcome access. This option still needs proof that
   the returned offline domains cover holidays and Energy sessions completely.

The user selected path 2 on 2026-09-01. The amendment is now frozen, but its
connection dispatch remains blocked by the prerequisites below.

`runner/verify_phase9_provider_schedule_readiness.py` and its no-secret/no-price
Actions preflight record this blocked state. They deliberately create no
`.timestamps` files and have no acquisition authorization effect.

## Metadata-only amendment (2026-09-01)

The user approved the recommended metadata-only approach. The separate
`JFOREX_METADATA_ONLY_CONNECTION_AMENDMENT.md` and
`spec/metadata_only_jforex_schedule_gate.frozen.json` preregister the future
narrow schedule-metadata query. The push preflight is deliberately no-secret,
no-JNLP, no-JForex, and no-network. It does not dispatch a connection.

Connection dispatch remains blocked because the remote JNLP/runtime closure,
metadata runner bytecode, exact network destinations, writable-path custody,
and SDK-internal market-byte/cache isolation have not been proven and frozen.
The existing acquisition runner cannot be reused because it contains
availability, subscription, Tester download, bar callback, and price-write
capability. A future runner must be a physically separate `IClient`/`Plugin`
module with an exact owned-bytecode method allowlist.

Even a successful future `getOfflineTimeDomains` observation will be evidence
only. Official documentation guarantees weekend intervals, not a complete
historical holiday, maintenance, Energy session, or versioned schedule source.
No 24-file inventory or canonical allowlist may be created until those semantics
are independently proven. This amendment has no acquisition authorization
effect.

### Local M1 controls (2026-09-01)

The dedicated `runner/jforex-metadata` module, exact owned-bytecode provider
method allowlist, separate synthetic network namespace with an exact Landlock
TCP port plus an exact `/32` host route, and private writable-path custody are
now implemented for
local/synthetic preflight only. The module physically excludes the existing
price acquirer and has no executable authorized dispatch workflow.

The bytecode exact-match result is compiled against a frozen local synthetic
API fixture. It is not evidence of compatibility with the real JForex API
2.13.99 JAR or runtime closure. The initial remote JNLP identity has now been
observed, but the remote runtime closure has not been requested or proven.

`JFOREX_REMOTE_JNLP_OBSERVATION_AMENDMENT.md` and
`spec/remote_jnlp_observation_amendment.frozen.json` governed a single-use
initial identity request. User-approved Run `33500446289` completed successfully
at head `aa9d46a6a42936042a406bdf339f07d378cc79b7`; Job `99832303024`, Artifact
`9797466074`, and independently downloaded Artifact ZIP SHA-256
`5a0339a026ea2ac0a7382b3ad7e0510a303609ab8817d55a268b55108415b8d2`
were independently audited. The one unauthenticated GET returned HTTP 200 and
2445 bytes with body SHA-256
`4e5adcbb29116e7f17b3babfc4aa47590d06baca50a98745d300d4824a1a70e9`;
the TLS certificate DER SHA-256 was
`616df88e991b3d1f0ca1183d5155a243d7dfceb0b3f1461cb4f400d43b6003df`.
No redirect or recursive resource request occurred, and no raw JNLP bytes were
retained in Git or the Artifact.

The three parsed hrefs plus codebase and the explicit-port initial URL form a
five-string exact set with aggregate SHA-256
`72fe580e020440cb273c56eef77b73982b78fb3843b33c1ac32e119b767790ee`.
That set is frozen as evidence-only in
`spec/remote_jnlp_observed_url_allowlist.frozen.json`, strictly after the source
Run and without same-run self-authorization. The single-use authorization is
consumed. Rerun, replay, `libs_3.jnlp`, icon, JAR/resource, connection,
provider-schedule, availability and price requests remain unauthorized and
require a separate explicit Gate and user approval. All provider-schedule,
price, acquisition, Count-only and Outcome states remain blocked.

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
   allowlist; do not self-authorize from the same discovery run. **Completed;
   acquisition authorization remains false.**
2. Scan the shaded runner and prove actual native loading/mapped-DSO behavior.
3. Enforce child-process and OS-level egress controls.
4. Initial JNLP identity is independently audited and exact URL strings are
   frozen. Before any further request, pre-audit a narrower remote-runtime
   closure Gate and obtain a separate manual authorization; do not reuse the
   consumed initial-observation authorization.
5. Implement streaming Full-QC for all 48 direct series in the acquisition run.
6. Configure a user-approved private raw-data custody path if raw persistence is
   required; raw prices must not enter Git or public Artifacts.
7. Complete a final pre-dispatch audit. Only then may credentials and the exact
   manual confirmations be used for a single acquisition/QC dispatch.

See `JFOREX_SOURCE_CHANNEL_AMENDMENT.md`, `S1B_RUNTIME_QC_PREFLIGHT.md`, and
`results/s1b-run-33376110507/S1B_AUDIT.json`.

Until then:

- S1B Gate A static inventory: `PASS_EVIDENCE_ONLY`
- Gate B exact-match allowlist: `FROZEN_EXACT_MATCH_PASS_EVIDENCE_ONLY`
- acquisition: `BLOCKED_PENDING_REMAINING_RUNTIME_CONTROLS`
- full quality gate: `BLOCKED`
- Count-only Gate: `BLOCKED`
- return/MFE/MAE/edge backtest: `BLOCKED`
- Development/OOS/Final Holdout access: `PROHIBITED`

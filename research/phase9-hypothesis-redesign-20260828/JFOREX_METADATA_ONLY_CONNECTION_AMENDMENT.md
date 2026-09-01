# Phase 9 JForex Metadata-only Connection Amendment

Status: `FROZEN_AMENDMENT; CONNECTION_DISPATCH_BLOCKED`

Recorded: 2026-09-01 UTC

## Decision

The user approved preregistering a metadata-only JForex connection path to
investigate the provider-schedule source blocker. This approval authorizes this
amendment and its no-secret static preflight. It does not authorize a JForex
connection, remote JNLP observation, demo-secret configuration, price
acquisition, a provider-schedule inventory, or any research calculation.

The frozen machine-readable authority is
`spec/metadata_only_jforex_schedule_gate.frozen.json`. The current workflow
`.github/workflows/phase9-metadata-only-jforex-gate-preflight.yml` runs on push
without Secrets, Java, JNLP, JForex, or provider network access. Its
authorization effect is none.

## Future narrow exception

If every pre-dispatch blocker in the frozen contract is later satisfied and a
separate manual dispatch is approved, the only provider-data method permitted
to owned code is:

`IContext.getDataService().getOfflineTimeDomains(long,long,Instrument)`

This is a schedule-metadata query, not an instrument-availability query.
`getAvailableInstruments`, subscriptions, Tester data intervals and downloads,
history, feeds, tick/bar values, account values, orders, reports, and Outcomes
remain prohibited. The future implementation must use a dedicated
`IClient`/`Plugin` module that physically excludes the existing acquisition
runner and every strategy price-callback surface. Owned bytecode method
references must match an exact allowlist before any credential is referenced.

The exact 12 instruments are queried for the two frozen windows. The API `to`
argument is the applicable end-exclusive instant minus one millisecond. Raw
`ITimeDomain` start/end milliseconds are evidence only; they must not be
expanded into canonical bar-open files until endpoint semantics and historical
completeness are independently proven.

## Why dispatch is still blocked

- The remote JNLP, recursive runtime closure, TLS/endpoint identity, and the new
  metadata runner/runtime mappings have not been discovered and frozen in a
  strictly earlier commit.
- Existing Gate C3 denies all external sockets. A distinct execution envelope
  must preserve child-process and filesystem controls while default-denying all
  network destinations except a separately frozen exact set.
- Static owned-code inspection cannot prove that the JForex SDK itself receives
  no market bytes or persists no price cache during an authenticated connection.
  That state remains `UNPROVEN`, not `false`.
- Official JForex API 2.13.99 documents offline domains as weekend intervals.
  It does not prove complete historical holiday, maintenance, Energy daily
  session, or session-rule-change coverage, and it does not provide a frozen
  provider schedule dataset version.
- Energy roll/continuous-series metadata remains a separate blocked Gate.

Consequently, a future offline-domain observation remains evidence only. It
cannot set `complete_interval_inventory=true`, create the canonical 24-file
inventory, freeze an allowlist in the same Run, set
`acquisition_authorized=true`, authorize Count-only, or calculate Outcomes.

## Later execution order

1. Build and bytecode-audit the dedicated `IClient`/`Plugin` metadata runner
   and execution envelope with local/synthetic inputs only.
2. Freeze a separate remote-JNLP-observation amendment and obtain separate user
   approval; no remote request is allowed before that approval.
3. Observe remote JNLP/runtime identities without credentials or JForex connect.
4. Independently audit the Run, head, Artifact, and downloaded ZIP SHA.
5. Freeze exact JNLP/runtime/network/mapping/path allowlists in a later Commit.
6. Prove private writable-path custody and the absence of exposed/persisted
   market values; otherwise reject this source path.
7. Require separate exact manual dispatch and demo-account terms confirmation.
8. Observe raw offline domains only, then independently audit semantics.
9. Freeze a canonical schedule allowlist only in another strictly later Commit
   and only if the complete provider-schedule contract is actually proven.

At every step, same-Run self-authorization is prohibited.

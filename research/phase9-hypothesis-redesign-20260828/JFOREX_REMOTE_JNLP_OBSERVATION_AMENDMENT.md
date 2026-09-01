# Phase 9 Remote JNLP Observation Amendment Proposal

Status: `FROZEN_PROPOSAL; SEPARATE_USER_APPROVAL_REQUIRED; NOT_AUTHORIZED`

Recorded: 2026-09-01 UTC

## Decision boundary

This proposal does not authorize a remote request. It freezes the exact scope
that may be submitted for separate user approval after the local/synthetic M1
controls pass. Until the user explicitly approves this proposal,
`external_jnlp_observation_authorized=false` and no workflow implements or
dispatches it.

The machine-readable proposal is
`spec/remote_jnlp_observation_amendment.frozen.json`.

## Proposed observation

The proposed future Run may perform exactly one unauthenticated HTTPS `GET` to:

`https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp`

The exact allowed URL set contains only that URL: scheme `https`, host
`platform.dukascopy.com`, explicit port `443`, path
`/demo_3/jforex_3.jnlp`, and no query, fragment, or userinfo. The Run may issue
at most one request and accept at most 2,097,152 response bytes. It must not
follow a redirect. A redirect status and `Location` may be recorded as evidence
only and requires a later separately frozen amendment before another URL can be
requested.

For a 200 response, the Run may record the TLS peer certificate digest and raw
initial response size/SHA. If the bytes are a JNLP document, codebase, href, and
resource URLs may be parsed locally but must not be fetched. Recursive runtime
requests, JAR downloads, signer inspection, and closure acquisition are outside
this proposal. It may not use
credentials, execute downloaded code, invoke JForex connect, query schedule
metadata or availability, subscribe, access history/feed/tick/bar/price/order/
account data, persist market cache, or inspect any research Outcome.

## Independent identity chain

The single-response observation Artifact must be independently downloaded and audited for Run
ID, attempt, Job ID, head SHA, Artifact ID, ZIP SHA-256, exact member set, and
inner manifest. The observation Run may not freeze or accept its own closure.
The first Run may not authorize following its own observed `Location` or parsed
resource URLs. Each next remote URL set must be exact and created in a strictly
later Commit whose parent and Git object bytes are independently verified.

Even a complete remote runtime identity lock does not authorize a metadata
connection. SDK-internal market-byte/cache isolation, private custody, account
terms, exact destinations, and a separate connection-dispatch confirmation
remain later Gates. Provider schedule, acquisition, Count-only, and Outcomes
remain blocked.

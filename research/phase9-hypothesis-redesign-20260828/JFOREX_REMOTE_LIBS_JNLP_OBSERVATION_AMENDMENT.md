# Phase 9 Remote libs JNLP Observation Amendment

Status: `FROZEN_PENDING_EXACT_MANUAL_SINGLE_USE_APPROVAL`

Recorded: 2026-09-01 UTC

## Purpose

The independently audited initial JNLP observation exposed one extension JNLP
URL. This amendment freezes a single identity-only request to that exact
observed URL so the remote runtime resource references can be inventoried
without credentials, JForex connection, downloaded-code execution, market
data, provider schedules, or research outcomes.

The exact manual confirmation entered in GitHub Actions is the separate user
approval for the one request. Merely committing this amendment does not make a
request and does not authorize a rerun.

## Exact one-shot scope

- URL: `https://platform.dukascopy.com/demo_3/libs_3.jnlp`
- Method: one unauthenticated HTTPS `GET`
- Maximum DNS resolutions: 1
- Maximum TCP connection attempts: 1
- Maximum HTTP requests: 1
- Maximum response body: 2,097,152 bytes
- Redirect following: prohibited
- Recursive resource fetching: prohibited
- Raw JNLP persistence: prohibited
- JAR/resource fetching or execution: prohibited
- Credentials and JForex connection: prohibited
- Schedule, availability, history, price, cache, Count-only and Outcome access:
  prohibited

If HTTP 200 returns an identity-encoded JNLP document, its codebase, hrefs,
resolved exact URLs, response size and SHA-256 may be recorded. The response
body itself is never written. A redirect, non-200 response or any bounded
failure consumes the authorization and requires a new amendment and approval.

## Separation and next Gate

The Run may upload only the identity audit JSON and its SHA-256 manifest. It may
not authorize or fetch any URL it discovers. The Run, Job, head SHA, Artifact,
downloaded ZIP SHA and exact members require independent audit. Only a strictly
later commit may freeze the observed runtime URL set. Every later JAR/resource
request requires another exact, separately approved Gate.

This amendment has no effect on provider-schedule completeness, Energy
metadata, acquisition authorization, Count-only authorization or any formal
Phase 9 result.

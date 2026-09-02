# Phase 9 Remote libs JNLP Observation Reauthorization V2

Status: `FROZEN_PENDING_NEW_EXACT_MANUAL_SINGLE_USE_APPROVAL`

Recorded: 2026-09-02 UTC

## Why V2 is required

Workflow Run `33574659277`, Job `100075864534`, failed in its offline static
verification step before the evidence directory, DNS resolution, TCP connect or
HTTP request step could run. The generated shell contained a literal `+` before
three expected SHA-256 strings, so Bash reported `test: too many arguments`.

The exact request step was `skipped`; therefore this failed Run made zero DNS
resolution calls, zero TCP connection attempts and zero HTTP requests. It did
not retrieve JNLP bytes, resources, schedules, availability, prices or market
data. Count-only and Return/Outcome were not run.

Workflow Run `33575321670` was also `skipped` because V1 was intentionally
limited to run number 1 and attempt 1. It made no request.

The V1 contract states that its authorization is consumed by the first dispatch
regardless of result. V1 must not be rerun or reused. This document freezes a
new V2 workflow and a new exact manual confirmation instead of weakening that
rule.

## Exact V2 scope

- URL: `https://platform.dukascopy.com/demo_3/libs_3.jnlp`
- Method: at most one unauthenticated HTTPS `GET`
- Maximum DNS resolutions: 1
- Maximum TCP connection attempts: 1
- Maximum HTTP requests: 1
- Maximum response body: 2,097,152 bytes
- Redirect following: prohibited
- Recursive resource fetching: prohibited
- Raw JNLP persistence: prohibited
- JAR/resource fetching or execution: prohibited
- Credentials and JForex connection: prohibited
- Schedule, availability, history, price, cache, Count-only and Return/Outcome:
  prohibited

The new manual dispatch token is the approval for this one V2 request. Merely
committing this document does not approve or make the request. The first V2
dispatch consumes the V2 authorization regardless of result; rerun and replay
remain prohibited.

## V2 implementation correction

The V2 workflow uses ordinary Bash variables and arrays instead of generated
line-continuation fragments. Its offline verifier checks that no literal
`= +` corruption exists in the workflow, and its tests execute the exact static
verification commands before any network-capable step. Evidence sealing runs
only after the private evidence directory was initialized.

## Separation and next Gate

The V2 Run may upload only the identity audit JSON and its SHA-256 manifest.
It cannot authorize or fetch any discovered URL. Independent audit of the Run,
head SHA, Job and exact two-file Artifact is required before a later commit may
freeze any runtime URL set. Any JAR/resource request, JForex connection,
provider-schedule query or price acquisition requires a separate later Gate.

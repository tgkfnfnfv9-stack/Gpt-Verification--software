# Remote Runtime Version Decision — 2026-09-02

Status: `REMOTE_JNLP_RESOURCE_DOWNLOAD_REJECTED_AS_STALE_FOR_FROZEN_CHANNEL`

## Evidence

Run `33577505327` observed the exact `libs_3.jnlp` identity with one HTTP GET.
The independently verified document referenced:

- `jForex-3.6.48.jar`
- `JForex-API-2.13.98.jar`
- 33 other JAR identities
- one `libs.jnlp` identity

All 36 references remained `fetched=false`.

The preregistered authenticated source channel is already fixed to:

- `DDS2-jClient-JForex 3.6.51`
- `JForex-API 2.13.99`

Its official Maven dependency set was previously downloaded as opaque bytes,
SHA-locked and independently audited in S1B. The root JAR identities are:

- client 3.6.51 SHA-256:
  `daf2d98cded0a8ff85276965f0c10eb01692acff7949a5898ab295708e2c26c2`
- API 2.13.99 SHA-256:
  `bad5923eb37b07aaf3f8f257eec1cfec57d645c1f61ea68ec2b7e179d3736ac2`

## Decision

Do not request or download the 36 observed `libs_3.jnlp` references. They are
evidence for a different, older runtime and do not close the frozen 3.6.51 /
2.13.99 channel. Downloading them would add a second runtime version and delay
the research goal without authorizing price acquisition.

The 36-entry allowlist remains evidence-only. It has no request, execution,
connection, schedule, price, Count-only or Outcome authorization effect.

## Research priority

Resume blind FX8 MTF hypothesis screening using the already proven FXCM 64-series
reacquisition path. Count-only remains separate from Return/OOS. Formal metals,
energy, provider-schedule and authenticated JForex work remains a separate
blocked track and cannot be used to delay the exploratory edge search.

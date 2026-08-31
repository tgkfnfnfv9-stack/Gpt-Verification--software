# Phase 9 S1B runtime/QC preflight

Status: `RUN_1_NATIVE_INVENTORY_INVALID_CLASS_MAGIC_FIX_PENDING_RERUN`

Run `33374751888` completed successfully at the workflow level and verified all
116 locked JAR SHA-256 values before parsing. Its native inventory is not valid:
28,088 Java `.class` entries beginning with `CAFEBABE` were misclassified as Mach-O
fat binaries. Acquisition remained blocked, no market data or outcomes were accessed,
and this inventory must not be used as a Gate B allowlist. The canonical fail-closed
audit is `results/s1b-run-33374751888/S1B_AUDIT.json`. The classifier now explicitly
excludes this Java-class collision and requires a new workflow run.

## Purpose

S1B is a no-provider-secret, no-price preflight. Checkout uses GitHub Actions' scoped
ephemeral token with `persist-credentials: false`; no Dukascopy or market credential
is referenced. S1B cannot run the JForex acquirer, connect to
the remote JNLP, request instrument availability, download market data, calculate
Count-only coverage, or calculate a research outcome.

Gate A has four narrowly scoped jobs and deliberately executes neither Maven nor
Java:

1. require the 116-JAR SHA-256 manifest extracted from the successful Run
   `33336895081` metadata;
2. fetch only those 116 JARs as opaque bytes from two exact HTTPS repository bases,
   reject redirects and environment proxies, verify each SHA-256 before ZIP parsing,
   and inventory native-looking entries without loading them;
3. exercise a hardened parser against a repository-local synthetic JNLP shape
   without any network request or launch;
4. exercise outcome-free Full-QC primitives with synthetic/adversarial inputs.

The manual workflow is:

```text
.github/workflows/phase9-s1b-runtime-qc-preflight.yml
confirmation = RUN_PHASE9_S1B_NO_SECRET_NO_PRICE_PREFLIGHT
```

It uploads only the exact metadata allowlist in
`data_manifest/data_custody_policy.json`. Raw CSV, cache, JAR, JNLP, database, and
credential material are prohibited from the Artifact.

The 930-file Maven inventory and shaded-runner SHA from Run 5 are retained as
historical evidence, but Gate A does not rebuild or execute them. The shaded runner
is explicitly not scanned in this gate; that remains a blocker for a separately
locked later gate.

## Synthetic Full-QC coverage

`runner/phase9_full_qc.py` currently implements and tests reusable primitives for:

- complete, untruncated scheduled-missing segments including leading/trailing gaps;
- direct M15-to-H1 OHLCV reconciliation without replacement of canonical H1;
- deterministic complete H4/D1 buckets from canonical H1 only;
- fixed FX8, Metals2, and Energy2 timestamp-set overlap;
- fail-closed Energy metadata readiness;
- explicit zero Forward Fill and no Count-only/outcome authorization.

This is not yet the streaming integration over 48 actual source files. Actual
provider calendar coverage, the provider no-synthetic-bar guarantee, BID/ASK paired
derived buckets, all-period group synchronization, and Energy source metadata remain
mandatory before the actual market-data Full-QC gate can pass.

## Gate A does not prove

- an allowlisted native payload or loaded DSO set;
- the shaded runner's native inventory or runtime closure;
- prevention of `System.load*`, child processes, writes, cache mutation, or network;
- JNLP redirect/TLS/SPKI/body/resource locks;
- use of the same locked JNLP bytes by the SDK;
- OS network-namespace default deny;
- actual market-data quality or missingness;
- durable private raw-data custody.

The first native inventory cannot authorize its own contents. It must be audited and
committed as a separate Gate B allowlist. External JNLP observation also requires a
separate terms confirmation and manual authorization; Gate A performs no such
request.

Until later gates pass:

```text
runtime_code_closure_verified              = false
acquisition_authorized                     = false
phase9_price_files_acquired                = 0
actual_market_data_full_quality_gate_passed = false
count_only_authorized                      = false
research_outcomes_calculated               = false
```

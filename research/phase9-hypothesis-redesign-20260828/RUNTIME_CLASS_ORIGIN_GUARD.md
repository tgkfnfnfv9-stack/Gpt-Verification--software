# Phase 9 Java class bytecode execution gate

Status: `PREFLIGHT_RUN_5_PASSED_BUILD_ONLY_ACQUISITION_BLOCKED`

This gate is acquisition-only infrastructure. It does not authorize credentials,
market-price access, Count-only, or outcome calculation.

## Purpose

The JForex SDK receives a JNLP URL during `connect`. The reproducible shaded runner
therefore starts as both:

```text
java -javaagent:/exact/phase9-jforex-acquirer.jar \
     -jar /exact/phase9-jforex-acquirer.jar ...
```

The premain agent inventories the exact shaded JAR and Java runtime archives. Every
non-bootstrap class definition must match all of the following:

1. exact approved archive URI;
2. internal class name present in that archive;
3. SHA-256 of the class bytes present in that archive.

Any mismatch records a rejection and terminates the JVM with exit code 86 before the
class initializer can run. The runner also refuses to start without the agent and
rejects `CLASSPATH`, `JAVA_TOOL_OPTIONS`, `_JAVA_OPTIONS`, and `JDK_JAVA_OPTIONS`.

## Build-only adversarial checks

The manual preflight performs both checks without credentials or market access:

- an approved JForex API class loads from the shaded runner;
- an external probe JAR is rejected with exit code 86 and its sentinel side effect
  remains absent.

The audit files and runner manifest are metadata artifacts. They contain no raw price
data and no research outcomes.

## Java 8 reflection-inflation control

Run `33313439354` stopped with exit code 86 while inventorying the pinned runtime.
The rejected class was `sun/reflect/GeneratedConstructorAccessor1` with no
CodeSource. The guard itself had repeatedly called `MessageDigest.getInstance` and
`String.format` while hashing 42,688 class names, which can trigger Java 8 reflection
inflation.

The remediation does not allow null-CodeSource classes or add a `sun.reflect`
exception. Instead it:

- creates the SHA-256 implementation once and reuses it under synchronization;
- converts digests to hexadecimal without `String.format`;
- requires `-Dsun.reflect.inflationThreshold=2147483647` in every guarded JVM;
- removes per-price-row `String.format` from the future acquisition path;
- captures positive guard stdout/stderr and requires an explicit PASS marker.
- binds every class name and hash to the same exact archive origin;
- halts with code 86 even if policy evaluation or audit writing fails.

The exact threshold is recorded in the guard audit. Missing or different threshold
configuration fails during premain. This remains a build-only preflight and requires
a successful workflow run before any runtime-closure claim can advance.

## Run 5 result

Build-only Run `33336895081` passed all steps on commit
`5392bb18ed4a8db9dc76aa882f7bc41b89ed0ff9`:

- positive guard: `ACTIVE` then `PASSED`, 25 transformed classes checked;
- positive self-test: PASS with empty stderr;
- negative external probe: rejected with exit code 86 before its sentinel existed;
- approved class-name inventory: 42,688;
- runner SHA-256: `545bb9601d547b0edd5476886474a9affb541df5dc1c3fe172cb544c7c1f8204`;
- Maven repository inventory: 930 files and identical across all three builds;
- artifact ZIP SHA-256: `fbf204bb048f795463a46910c669c8bcc9226705cad631798948ef7ca4c6e635`.

The artifact contains 16 metadata files and zero CSV files. Within the completed
workflow steps and emitted metadata, Dukascopy/market credentials, market requests,
forbidden-period access, and research outcomes were not used. This is not an
OS-level packet-capture or egress-closure claim. The canonical audit is
`results/preflight-run-33336895081/PREFLIGHT_AUDIT.json`.

## Scope limit

A passing run proves only that the pre-connect self-test activated the guard,
accepted the approved non-bootstrap classes exercised in that test, and rejected the
external probe before its side effect. Bootstrap-loaded classes are outside the
guard's archive/hash check. This is not a Java bytecode-closure claim. It also does
not prove closure for the actual JNLP connection, JNI/native libraries, child
processes, downloaded-but-not-loaded files, remote configuration interpreted by
already-approved code, or OS-level network egress. It must not set
`runtime_code_closure_verified` or `acquisition_authorized` to true.

The following separate gates remain mandatory:

- exact Java/runtime/native identity and execution sandbox;
- JNLP content and endpoint validation before credentials;
- no unexpected executable/cache mutations;
- provider historical session/calendar inventory;
- complete session-missingness, M15/H1 reconciliation, H4/D1 bucket, cross-market,
  and Energy roll QC;
- same-run full QC or an explicitly approved private immutable raw-data store.

Until all gates pass:

```text
runtime_code_closure_verified = false
acquisition_authorized        = false
phase9_price_files_acquired   = 0
research_outcomes_calculated  = false
```

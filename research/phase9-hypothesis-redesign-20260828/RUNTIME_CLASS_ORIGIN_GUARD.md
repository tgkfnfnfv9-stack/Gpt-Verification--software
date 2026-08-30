# Phase 9 Java class bytecode execution gate

Status: `PREFLIGHT_RUN_4_FAILED_CLOSED_FIX_PENDING_RERUN`

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
a new successful workflow run before any runtime-closure claim can advance.

## Scope limit

A passing run proves only `JAVA_CLASS_BYTECODE_EXECUTION_CLOSURE` for the tested
runtime. It does not by itself prove closure for JNI/native libraries, child
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

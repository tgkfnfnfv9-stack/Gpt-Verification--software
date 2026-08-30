# Phase 9 Java class bytecode execution gate

Status: `PREFLIGHT_IMPLEMENTED_NOT_YET_RUN`

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

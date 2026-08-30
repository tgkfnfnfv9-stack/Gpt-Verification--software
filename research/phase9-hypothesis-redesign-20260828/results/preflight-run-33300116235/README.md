# Phase 9 JForex Build Preflight Run 33300116235

Status: `PASS_BUILD_AUDIT_ONLY_ACQUISITION_NOT_AUTHORIZED`

- Commit: `07e81626bbe482a3f01b93f5e2269e876b8ff186`
- Job: `99226544365` (`preflight`)
- Artifact: `9728657818`
- Artifact ZIP SHA-256: `447ed4ad6a20e5ce642405775648f01560c532a9817aba38008bfb93603818ce`
- Tests: 16/16 passed
- Builds: online 1 + offline 2; all three succeeded
- Isolated Maven repository: 930 files per inventory; all three inventories byte-identical
- Inventory file SHA-256: `d0c37ea7dd7da471bc7d0123cfba5053a6b09bccedd5fbbe5f7d067d2335f908`
- Reproducible runner JAR SHA-256: `0be2a82d99a584a0d299f77d2c74e2802c0c82920963341371ac6b38044e2b3d`

The plan contains 12 instruments × M15/H1 × BID/ASK = 48 unique series.
M15 is `[2013-01-01, 2019-08-28)` and H1 is
`[2013-01-01, 2019-08-01)`. No date input exists.

This was build-only. The workflow contains no Dukascopy secret reference,
JForex authentication, `java -jar`, price request, raw CSV validation, or
outcome calculation. Phase 9 price files remain zero. Missing intervals were
not observed because market data was not acquired.

The inventory is audit evidence, not a frozen acquisition dependency lock.
Exact JDK/Maven/runner pinning, JNLP runtime code closure, provider cache
boundary evidence, and same-run full QC or approved private raw storage remain
blocked gates.

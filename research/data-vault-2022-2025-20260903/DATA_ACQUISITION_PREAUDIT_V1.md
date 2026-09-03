# 2022–2025 Data Acquisition: Price-Free Design Preaudit v1

## Decision

`PRICE_FREE_PREAUDIT_SUPERSEDED_BY_USER_APPROVED_SIMPLE_IMPLEMENTATION`

This document originally recorded approval gate 1. The user subsequently
authorized a simplified FX implementation and its commit/push. Workflow dispatch,
price access, OAuth, Drive access or mutation, and transaction publication remain
unauthorized.

The repository baseline is remote `main` commit
`b06c815547e8dbd354a54c554af4ab8b516da348`. GitHub `main`, `AGENTS.md`,
`PHASE9_OPERATIONS_GUIDE.md`, and the Vault V2/V2.1/V2.2 contracts and audits
were treated as authoritative over the attached project notes.

## Exact acquisition boundary

FX recovery requests and canonical outputs are restricted to the half-open UTC
interval:

`[2022-01-01T00:00:00Z, 2026-01-01T00:00:00Z)`

The user subsequently expanded the separate commodity scope to:

`[2012-01-01T00:00:00Z, 2026-01-01T00:00:00Z)`

Any source row outside that interval is a hard failure. The data are classified
as `EXPLORATORY_ACQUISITION_QC_ONLY`; they have no formal Phase 9 authorization
effect. Years 2022–2023 are designated for later robustness use and 2024–2025
for later final-holdout use; this recovery only stages them as `UNSEALED` and
does not authorize research use. Acquisition/QC may calculate only integrity and completeness
metadata. Signals, Count, Return, PF, win rate, MFE/MAE, rankings, EA generation,
or any research consumption are forbidden.

## A. FX25 recovery design

The frozen symbol set is:

`AUDCAD, AUDCHF, AUDJPY, AUDNZD, AUDUSD, CADCHF, CADJPY, EURAUD, EURCHF, EURGBP, EURJPY, EURNZD, EURUSD, GBPCAD, GBPCHF, GBPJPY, GBPNZD, GBPUSD, NZDCAD, NZDCHF, NZDJPY, NZDUSD, USDCAD, USDCHF, USDJPY`.

The recovery continues the one existing uncommitted transaction
`v2-txn-run-33705800232` in private Drive root
`1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v` (`Phase9 FXCM Data Vault`). It does not
rerun V2/V2.1, rewrite the 2012–2021 objects, or create a second transaction.
The preserved state is 500 archives plus 10 manifests for 2012–2021; the empty
recovery state is 200 archives plus 4 manifests for 2022–2025.

The V2.2 availability mask fixes 10,400 weekly identities: exactly 10,084
`present` identities may be requested and 316 `known-missing` identities must
never be requested or filled. Direct acquisition is FXCM m1/H1, with BID and ASK
OHLC. There are 200 year/symbol/timeframe archives and 400 direct side-series-year
streams. M5/M15/M30/H4/D1/W1 are deterministically regenerated from direct data;
there are 600 derived combined-side series-years (1,200 side-series-years). No
separate derived price copies are stored.

| Year | Frozen present | Known missing | New archives | New manifests |
|---:|---:|---:|---:|---:|
| 2022 | 2,600 | 0 | 50 | 1 |
| 2023 | 2,600 | 0 | 50 | 1 |
| 2024 | 2,479 | 121 | 50 | 1 |
| 2025 | 2,405 | 195 | 50 | 1 |
| **Total** | **10,084** | **316** | **200** | **4** |

Before any request, a metadata-only inventory must again prove the single
transaction identity, `ACQUIRING` state, zero canonical-v2 folders, exact
2012–2021 preserved inventory against frozen canonical digest
`4a0f0cfb78ead6d6730ca7b41b716de8e2fef984e7f36ded17828d9e7b40dc4d`,
and exact current/later empty stages. A mismatch is a hard stop. The failed V2.1
attempt remains non-replayable.

## B. Commodity v1 design

Commodity acquisition is a new contract and must not change FXCM V2. The
proposed provider is Dukascopy Bank SA through authenticated JForex API, pinned
to DDS2 client `3.6.51` and API `2.13.99`. The provider's historical dataset has
no published immutable release ID, so the internal source version is the pinned
runtime and request contract plus SHA-256 for every source payload, canonical
CSV, and timestamp column.

| Canonical symbol | Provider instrument | Semantics |
|---|---|---|
| XAUUSD | `XAU/USD` | provider-native gold/USD quote series |
| XAGUSD | `XAG/USD` | provider-native silver/USD quote series |
| BRENTCMDUSD | `BRENT.CMD/USD` | non-expiring Brent-correlated CFD quote series |
| LIGHTCMDUSD | `LIGHT.CMD/USD` | non-expiring WTI-correlated CFD quote series |

Direct requests are `Period.ONE_MIN` and `Period.ONE_HOUR` for both
`OfferSide.BID` and `OfferSide.ASK`, with UTC bar-open timestamps. JForex's end
bar time is inclusive, so the adapter must translate the contract's exclusive
end to the last eligible bar-open and reject any row at or after
`2026-01-01T00:00:00Z`.

If all years are available, the commodity scope contains 112
year/symbol/timeframe archives and 14 year manifests: 224 direct
side-series-years. The six deterministic derived timeframes contribute 336
combined-side series-years (672 side-series-years), stored as manifest
fingerprints rather than duplicate price files. Actual earliest availability,
row counts, and source identities remain unknown until a separately approved
availability/acquisition gate and therefore are not invented here.

The oil series is provider continuous spot-CFD history influenced by the current
futures contract. The contract forbids local concatenation, back adjustment,
ratio adjustment, or inferred roll dates. Provider roll events and switch
metadata must be recorded separately. Exact historical 2012–2025 holiday,
maintenance, special-closure, and Brent/WTI switch calendars remain blocking
inputs; current website hours cannot be applied retroactively.

Other products are inventory-only and have `acquisition_authorized=false`:
`GAS.CMD/USD, COPPER.CMD/USD, DIESEL.CMD/USD, COFFEE.CMD/USX,
COCOA.CMD/USD, SUGAR.CMD/USD, COTTON.CMD/USX, OJUICE.CMD/USX,
SOYBEAN.CMD/USX, XPT.CMD/USD, XPD.CMD/USD`, plus the 21 index instruments
enumerated in the frozen JSON contract. Adding any instrument requires a new
approval.

## Common QC and storage contract

Each direct source object, canonical CSV byte stream, and normalized timestamp
column has an independent SHA-256. Archive member names are an exact allowlist;
archives are reopened after creation and after private re-download. Duplicate
members, duplicate timestamps, duplicate shards, path traversal, symlinks, and
unknown members are rejected.

Missing output buckets are never interpolated or forward-filled. Their ordered
UTC identities are dropped, counted, and SHA-256 hashed. M5/M15/M30 require the
exact expected direct m1 timestamp set. H4/D1/W1 require set equality with an
independently generated expected H1 timestamp set; both missing and extra
timestamps fail completeness. Grouping observed rows alone is insufficient.

Only source and direct canonical CSVs are placed in the private Vault archives.
Derived series are recreated from the hashed direct canonical input and their
canonical-byte, timestamp-column, and missing-bucket hashes are stored in the
manifest. A consumer must reproduce those hashes before use.

No raw or canonical price bytes may enter Git, logs, caches, or public Actions
artifacts. Private upload is successful only after re-download and SHA-256
agreement for every object. Normal success, handled failure, and handled cancel
paths delete local plaintext in `finally`/shell traps and an unconditional
workflow cleanup step. Abrupt runner destruction cannot execute cleanup code;
the residual control is an ephemeral runner, no cache/artifact upload, no remote
plaintext, and runner teardown.

## Approval gates and blockers

1. **Design and price-free preaudit:** completed by this artifact; no price or
   remote storage access occurred.
2. **Implementation commit/push:** authorized for the simplified FX recovery.
3. **Price acquisition and QC:** not authorized.
4. **Private Drive/Vault write and re-download:** not authorized.
5. **Transaction final publication and cleanup:** not authorized.

The simplified implementation replaces the encrypted handoff with one ephemeral
workflow that performs FX acquisition, QC, private upload, re-download
verification, and local cleanup without any price artifact. Gate 3 execution
still requires a separate explicit approval.

Remaining commodity blockers are:

- Dukascopy license: the JForex EULA is personal/non-commercial, restricts
  redistribution, requires attribution, and requires a simultaneous alternative
  market-data source when consulting quotes. The owner must confirm the lawful
  use case and identify that independent source or obtain provider clarification.
- Commodity completeness: exact versioned 2012–2025 trading/holiday/maintenance
  schedules and energy roll/switch metadata must be supplied or obtained without
  price inspection. All four minimum symbols remain blocked together until this
  metadata contract is complete.
- The new private commodity Vault root does not yet exist. Its logical target is
  `My Drive / Phase9 Commodity Data Vault / commodity-v1/`; the concrete folder
  ID may be created and recorded only under approval 4.
- Before finalizing the mixed-provenance FX transaction, the preserved
  2012–2021 manifests require a price-free compatibility overlay and, at a later
  authorized content gate, high-timeframe re-QC under the independent expected
  timestamp-set rule. Their price archives and original provenance stay
  unchanged.

## Superseded gate-2 change set

The earlier 32-file split-gate plan below is superseded. It is retained only as
historical design context and is not the authorized implementation scope.

- `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_run1_recovery_execution_v2_3.frozen.json`
- `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_recovery_handoff_encryption_v2_3.frozen.json`
- `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_recovery_manifest_overlay_v2_3.frozen.json`
- `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_run1_recovery_local_v2_3.py`
- `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_run1_recovery_upload_v2_3.py`
- `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_run1_finalize_v2_3.py`
- `research/phase9-exploratory-fxcm-20260901/runner/verify_fxcm_drive_vault_run1_recovery_v2_3.py`
- `.github/workflows/phase9-exploratory-fxcm-drive-vault-run1-recovery-local-v2-3.yml`
- `.github/workflows/phase9-exploratory-fxcm-drive-vault-run1-recovery-private-upload-v2-3.yml`
- `.github/workflows/phase9-exploratory-fxcm-drive-vault-run1-finalize-v2-3.yml`
- five FX V2.3 contract/QC/workflow/transaction/security test files listed in
  `spec/acquisition_design_v1.preaudit.json`
- commodity-v1 provider, calendar/roll, manifest, QC, handoff and transaction
  specs; three runners; three workflows; and five test files listed in that JSON

The five Batch 6 fast-track files named in the JSON denylist, all existing Batch
6 v6 files, and all unrelated uncommitted work are outside scope and must remain
byte-identical.

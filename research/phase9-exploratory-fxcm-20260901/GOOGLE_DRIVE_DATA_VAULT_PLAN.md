# Phase 9 FXCM Google Drive Data Vault Plan

Status: `USER_APPROVED_PLAN_NO_PRICE_ACQUISITION_STARTED`

Recorded: 2026-09-02

## Decision

FXCM価格を候補Batchごとに再取得して破棄する運用を終了し、取得・QCと検証を分離する。
一度だけ複数年データを取得してGoogle Driveの非公開研究フォルダへ保存し、以後の
Count-only、Return/OOS、頑健性確認はSHA固定した同じデータを再利用する。

この文書は設計合意だけを記録する。価格取得、availability request、Count、Return、
Outcome計算はまだ開始していない。

## Google Drive target

- folder: `Phase9 FXCM Data Vault`
- folder ID: `1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu`
- URL: `https://drive.google.com/drive/folders/1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu`
- verified state at decision time: empty
- repository is public; raw prices and reusable price archives must not be committed to Git or
  uploaded as public GitHub Artifact
- GitHub Actions access to personal My Drive requires a separately configured least-privilege
  Google OAuth credential. The ChatGPT Drive connector is not a substitute for Actions OAuth.

## Frozen target scope for the acquisition design

- provider: FXCM CandleData, personal non-commercial use only
- target interval: `[2010-01-01T00:00:00Z, 2026-01-01T00:00:00Z)`
- target instruments: 28 G8 currency pairs

```text
AUDCAD AUDCHF AUDJPY AUDNZD AUDUSD
CADCHF CADJPY
CHFJPY
EURAUD EURCAD EURCHF EURGBP EURJPY EURNZD EURUSD
GBPAUD GBPCAD GBPCHF GBPJPY GBPNZD GBPUSD
NZDCAD NZDCHF NZDJPY NZDUSD
USDCAD USDCHF USDJPY
```

The 28-pair list is fixed before the availability inventory. Missing source coverage must be
reported, not silently converted into result-dependent symbol selection. XAUUSD, XAGUSD,
indices, oil and exotic FX are outside this vault version and require separate contracts.

## Direct and derived periodicities

Direct provider inputs:

```text
m1
H1
D1
```

Required fields where supplied by FXCM:

```text
UTC timestamp
BID Open High Low Close
ASK Open High Low Close
Volume
```

Canonical strategy series generated deterministically from closed M1 bars:

```text
M5 M15 M30 H1 H4 D1 W1
```

Provider H1 and D1 are independent QC references for the M1-derived H1 and D1 series. MID may be
derived for signal calculation, but BID/ASK must remain available for spread-inclusive execution.
Tick data is not part of the initial vault. It may be acquired under a separate post-edge Gate
only if MT5 execution validation needs intrabar sequencing or slippage evidence.

## Storage layout and identity

Acquisition should run once from one explicit manual authorization, using a year matrix internally.
The Drive output must be sharded so later tests download only the required subset.

```text
Phase9 FXCM Data Vault/
  v1/
    manifest/
      source_inventory.json
      qc_summary.json
      vault_manifest_sha256.txt
    prices/
      YEAR/
        SYMBOL/
          fxcm-SYMBOL-YEAR-m1.tar.zst
          fxcm-SYMBOL-YEAR-H1.tar.zst
          fxcm-SYMBOL-YEAR-D1.tar.zst
    sealed/
      oos/
      robustness/
      final_holdout/
```

Every shard must have a SHA-256, byte size, row count, first/last UTC timestamp, source URL
identity, side/field schema and QC status in the manifest. A later workflow must fail closed on a
missing shard, duplicate shard, digest mismatch, unexpected member, incomplete UTC bucket,
crossed quote or forbidden forward fill.

## Scientific access boundary

Before acquisition, freeze the exact temporal partition and access policy. Development,
Count-only, Return/OOS, robustness and final holdout must be separate manifest groups. Merely
storing later periods is not permission to read them. OOS or holdout decryption/access is allowed
only after the preceding Gate passes and a separate immutable contract is committed.

Count-only workers may read only data required to create signals and coverage. They must not
calculate, display or persist Return, win/loss, PF, p-value, confidence interval or Outcome.
Return/OOS workers may run only for frozen Count passers. No failed candidate may be rescued by
threshold, direction, symbol, timeframe or exit changes.

## Relationship to Batch 6

Candidates 321 through 324 remain preregistered and Count-unseen. The existing Batch 6 workflow
must not be dispatched while the vault migration is pending. Its candidate rules and frequency
Gates must not change. After the vault is created and independently audited, replace only its data
source with exact manifest-locked Drive shards, then run Count-only.

## Next-session task order

1. Verify latest remote `main` and read this document, `NEXT_SESSION_HANDOFF.md`,
   `NEXT_SESSION_PROMPT.md`, `SESSION_STATE.json` and the frozen Batch 6 contract completely.
2. Do not acquire prices and do not dispatch Batch 6 at session start.
3. Freeze a versioned vault acquisition/custody contract, temporal partition contract, exact
   shard schema, QC rules and OAuth secret names before any source availability or price access.
4. Implement metadata-only availability inventory separately from price acquisition.
5. Implement the one-manual-run year-matrix acquisition, Full-QC, private Drive upload,
   manifest sealing, local cleanup and independent tests. Do not dispatch it yet.
6. Publish the implementation atomically to `main`, then present the single execution link,
   exact inputs and one-time Google OAuth setup steps to the user.
7. Only after explicit manual authorization, acquire once. Independently audit Drive objects and
   manifest identities before any Batch 6 Count.

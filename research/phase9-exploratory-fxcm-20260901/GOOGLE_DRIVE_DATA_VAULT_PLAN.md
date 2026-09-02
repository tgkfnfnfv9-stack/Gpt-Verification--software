# Phase 9 FXCM Google Drive Data Vault Plan

Status: `V1_CONTRACT_AND_IMPLEMENTATION_COMPLETE_NOT_DISPATCHED_NO_PRICE_ACQUISITION`

Recorded: 2026-09-02

## Decision

FXCM価格を候補Batchごとに再取得して破棄する運用を終了し、取得・QCと検証を分離する。
一度だけ複数年データを取得してGoogle Driveの非公開研究フォルダへ保存し、以後の
Count-only、Return/OOS、頑健性確認はSHA固定した同じデータを再利用する。

この文書は設計合意だけを記録する。価格取得、availability request、Count、Return、
Outcome計算はまだ開始していない。

## 2026-09-02 V1契約・実装完了

再利用Vaultの契約と実行コードは完成した。ただし、ファイル公開はworkflow実行許可ではない。

- 取得・custody契約: `spec/fxcm_drive_vault_acquisition_v1.frozen.json`
- 年単位access partition: `spec/fxcm_drive_vault_partitions_v1.frozen.json`
- shard・manifest・archive契約: `spec/fxcm_drive_vault_manifest_schema_v1.frozen.json`
- Formal境界確認: `spec/fxcm_drive_vault_formal_boundary_amendment_v1.frozen.json`
- HEAD-only availability runner: `runner/fxcm_drive_vault_inventory.py`
- 年別取得・QC・package・upload runner: `runner/fxcm_drive_vault_acquire_year.py`
- private Google Drive client: `runner/fxcm_google_drive_private.py`
- Vault promotion/seal runner: `runner/fxcm_drive_vault_finalize.py`
- 公開price-free audit verifier: `runner/verify_fxcm_drive_vault.py`
- Availability workflow: `.github/workflows/phase9-exploratory-fxcm-drive-vault-availability-v1.yml`
- 一括取得workflow: `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml`

両workflowは`workflow_dispatch`専用、確認済みmain SHA完全一致、Run #1 / attempt #1だけを
許可し、まだdispatchしていない。一括取得workflowは16年matrixで年ごとに84 direct shardを
stagingし、各Drive uploadを再downloadしてSHA-256照合する。その後、全1,344 shardだけを
正本へ昇格し、`VAULT_SEAL.json`を最後に作る。途中失敗ではroot sealを作らない。

現在のsource evidenceは21ペア・2017～2020の証明に限定される。28ペア・2010～2025が
存在すると仮定しない。週次objectが1件でも欠ければ、銘柄を減らさずrootをsealしない。

Exploratory専用partitionはcalendar-year shard境界に合わせて次へ固定した。

| Partition | Interval | Drive namespace |
|---|---|---|
| Development | 2010-01-01～2020-01-01 exclusive | `v1/prices/` |
| Strict OOS | 2020-01-01～2022-01-01 exclusive | `v1/sealed/oos/` |
| Robustness | 2022-01-01～2024-01-01 exclusive | `v1/sealed/robustness/` |
| Final holdout | 2024-01-01～2026-01-01 exclusive | `v1/sealed/final_holdout/` |

これはFormal Phase 9の期間ではない。将来2019年以降のVault取得を明示承認して実行した時点で、
旧Formalの2019年以降を「未見」とする主張を終了する。この確認文字列もworkflow必須入力である。

戦略用正本はM1由来系列である。direct H1/D1はQC参照だけに使い、補完・代替しない。
参照OHLC不一致は記録してBatch 6移行を停止するが、構造的に正常なprivate shardのcustody
自体は無効にしない。

## Google Drive target

- folder: `Phase9 FXCM Data Vault`
- folder ID: `1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu`
- URL: `https://drive.google.com/drive/folders/1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu`
- verified state at decision time: empty
- repository is public; raw prices and reusable price archives must not be committed to Git or
  uploaded as public GitHub Artifact
- GitHub Actions access to personal My Drive requires a separately configured least-privilege
  Google OAuth credential. The ChatGPT Drive connector is not a substitute for Actions OAuth.
- The frozen `drive.file` scope does not grant blanket access to My Drive. The existing fixed root
  folder must first be made accessible to the same OAuth client. If root verification fails, setup
  stops without widening scope, checking availability or downloading prices.

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

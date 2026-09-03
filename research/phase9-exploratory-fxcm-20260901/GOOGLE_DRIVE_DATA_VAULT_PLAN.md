# Phase 9 FXCM Google Drive Data Vault Plan

Status: `V2_1_OPERATIONAL_HARDENING_IMPLEMENTED_NOT_EXECUTED_NO_PRICE_ACQUISITION`

Recorded: 2026-09-03

## Decision

FXCM価格を候補Batchごとに再取得して破棄する運用を終了し、取得・QCと検証を分離する。
一度だけ複数年データを取得してGoogle Driveの非公開研究フォルダへ保存し、以後の
Count-only、Return/OOS、頑健性確認はSHA固定した同じデータを再利用する。

## 2026-09-03 V2.1 pre-execution operational hardening

実行前のread-only監査で、旧V2の途中失敗時にroot直下へ部分stageまたは半昇格したcanonical
`v2`が残り、Run #1 / attempt #1を消費した後に安全に再開できないことを確認した。加えて、
owner-only・空rootの実行時検証、source URLのrunner内pin、crossed-open隔離後のgap集計、
public sealの型・SHA検証、旧Batch 6の停止に不足があった。

ユーザーは価格取得とは別に、この運用安全強化を承認した。既存V2凍結5契約は変更せず、
`spec/fxcm_drive_vault_operational_hardening_v2_1.frozen.json`を追加した。旧V2 workflowと
旧Batch 6 workflowは恒久fail-closedとし、新しいmanual single-use workflowを
`.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2-1.yml`へ分離した。

V2.1は価格接続前に固定rootがowner-only、非Shared Drive、非shortcut、children 0件である
ことを確認し、唯一の`v2-txn-run-{run_id}`を作る。14年stage、700 shard、manifest、sealは
すべてそのtransaction内で完成させる。全検証後、transaction folder 1件へのmetadata PATCH
だけでname `v2`、state `COMMITTED`へ公開し、応答喪失時は既知IDをGETして照合する。
PATCH前の失敗・取消ではcanonical `v2`は存在しない。PATCH境界では完全な`v2`/`COMMITTED`
が成立済みの場合があるため、exact original / exact committed以外、または照合不能は
`UNKNOWN_COMMIT_OUTCOME`として自動cleanupせず停止する。cleanupには別の明示承認を要求する。

sourceは`https://candledata.fxcorporate.com:443/{periodicity}/{instrument}/{year}/{week}.csv.gz`
へ完全固定し、redirect、query、fragment、userinfo、別portを拒否する。crossed-open行を除外
したcanonical gapはusable row列で集計する。Batch 6 compatibilityは別の旧64系列照合Gateが
完成するまでfalse固定であり、321～324のCount、Return、Outcomeは未認可のままである。
V2.1専用23 tests、探索track全186 testsは成功した。価格response body、Secret値、Outcomeは
一切参照していない。V2.1取得は、新しい公開main SHAの確認と別の明示承認まで実行しない。

## 2026-09-02 Option 1 / V2 frozen implementation

ユーザーはV1 availabilityの実測結果に基づくOption 1を明示選択した。V2は次へ固定した。

- 2012～2025年、FXCMで全期間利用可能な25通貨ペア
- direct m1/H1 BID/ASK OHLC、14年×25ペア×2 periodicity = 700 shard
- base 36,400 identity、frozen-present 36,000 identity、known-missing 400 identity
- exact mask: `spec/fxcm_drive_vault_availability_mask_v2.frozen.json`
- strategy canonical: M1由来M5/M15/M30/H1/H4/D1/W1
- direct H1: 完全性・OHLC一致のQC参照だけに使用し、価格の補完・代替には使わない
- 既知欠損週: 要求せず、barを生成せず、補完・補間しない
- frozen-presentの取得失敗: workflow失敗、root sealなし
- V1 acquisition: workflow preflightを恒久fail-closed化
- 旧V2 workflow: `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2.yml`（恒久停止）
- V2.1 workflow: `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2-1.yml`

| Partition | Interval | Drive namespace |
|---|---|---|
| Development | 2012-01-01～2020-01-01 exclusive | `v2/prices/` |
| Strict OOS | 2020-01-01～2022-01-01 exclusive | `v2/sealed/oos/` |
| Robustness | 2022-01-01～2024-01-01 exclusive | `v2/sealed/robustness/` |
| Final holdout | 2024-01-01～2026-01-01 exclusive | `v2/sealed/final_holdout/` |

V2のOAuth境界はpersonal My Drive、`drive.file` scope、専用GitHub Environment
`phase9-fxcm-vault-acquisition-v2`、3 secret名だけである。workflowはmanual Run #1 / attempt #1、
review済みmain SHA完全一致、4確認文字列完全一致を要求する。public Artifactは価格・timestamp・
Drive ID・outcomeを含まないexact 2ファイルだけである。

実装・Testsの公開後、専用Environment、required reviewer、OAuth 3 secretsを設定した。
secret値はチャット、Git、ログ、Artifactへ出していない。この設定は価格取得の承認ではない。
V2.1 workflow実行、Count、既存Batch 6は別の明示承認まで行わない。

価格取得、Count、Return、Outcome計算はまだ開始していない。HEAD-only availability
だけはRun `33627420903`で完了し、次の独立監査によりV1 target不成立を確認した。

## 2026-09-02 Availability Run #1 independent audit

- audit: `results/run-33627420903/FXCM_DRIVE_VAULT_AVAILABILITY_INDEPENDENT_AUDIT.json`
- exact target identities: 69,888
- HTTP 200 present: 36,000
- HTTP 404 missing: 33,888
- response body bytes read: 0
- 2010・2011年: m1/H1/D1すべて不在
- direct D1: 全16年・28ペアで不在
- 全期間不在: `CHFJPY`, `EURCAD`, `GBPAUD`
- 25ペアのm1/H1が52週揃う年: 2012～2018、2021～2023
- partial: 2019、2020、2024、2025

Run成功はtarget完全性の成功を意味しない。V1 acquisitionは未承認かつ実行禁止である。
欠損を無視したscope縮小、D1の無断削除、25ペアへの無断変更を行わない。新しいsourceを
選ぶか、別V2 scopeを明示承認して凍結するまでDrive取得を開始しない。

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
許可する。Availability Run #1は消費済みで再実行しない。一括取得workflowは未実行かつ
現在実行禁止である。一括取得workflowは16年matrixで年ごとに84 direct shardを
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
- V2 folder ID: `1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v`
- V2 URL: `https://drive.google.com/drive/folders/1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v`
- V2 root was created by the same OAuth client under the frozen `drive.file` scope
- verified state before price access: empty
- repository is public; raw prices and reusable price archives must not be committed to Git or
  uploaded as public GitHub Artifact
- GitHub Actions access to personal My Drive requires a separately configured least-privilege
  Google OAuth credential. The ChatGPT Drive connector is not a substitute for Actions OAuth.
- The frozen `drive.file` scope does not grant blanket access to My Drive. The fixed V2 root was
  created by the same OAuth client before price access. If exact root verification fails, setup
  stops without widening scope, checking availability or downloading prices.

## Historical rejected V1 target scope

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

## Historical V1 direct and derived periodicities

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

## Historical V1 storage layout and identity

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
   `NEXT_SESSION_PROMPT.md`, `SESSION_STATE.json`, `POLICY_INCIDENT_20260903.md` and the frozen
   read-only inventory contract completely.
2. Treat V2.1 Run `33705800232` as terminal failure. Do not rerun/replay it and do not dispatch
   Batch 6.
3. Do not delete, rename, move, patch or manually reorganize `v2-txn-run-33705800232`.
4. Verify the dedicated Drive metadata GET-only client, sanitized report verifier, manual
   single-use workflow and tests. Publishing them does not authorize dispatch.
5. Only after a separate explicit approval and reviewed public `main` SHA, run the read-only
   inventory once and independently audit its price-free artifact.
6. Design cleanup or versioned recovery only after the exact transaction state is known. Each
   path requires a separate contract and a separate explicit approval.
7. Do not change Batch 6 input until a canonical vault is complete, independently audited and
   proven compatible with the frozen 64-series consumer.

## V2.1 Run #1 terminal update

Run `33705800232` (Run #1, Attempt #1) completed with failure at head
`be864557a8e16d253e6aecf1519f85ad6162c1a3`. Year jobs 2012–2021 succeeded. Years 2022 and
2023 failed on empty frozen source objects, 2024 failed on a non-gzip source object and 2025
failed on a source object below the minimum size. The finalizer was skipped and the run produced
no public artifact. The transactional design therefore withheld canonical `v2` publication.

The exact Drive contents left by the failed run have not been observed. The next gate is frozen in
`spec/fxcm_drive_vault_run1_read_only_inventory_v2_1.frozen.json`. It permits OAuth token exchange
and Drive metadata `GET` only; it has no Drive media-download, mutation, cleanup, transaction
publication, FXCM request, Count, Return or MT5 surface. Its workflow remains undispatched until a
separate explicit user approval.

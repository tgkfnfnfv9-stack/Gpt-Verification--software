# 次セッションへ送る文章

以下のコードブロックを、そのまま新しいセッションへ送る。

```text
GitHub Repository `tgkfnfnfv9-stack/Gpt-Verification--software` のPhase 9研究を引き継いでください。

最初に最新remote mainを確認し、必ず新しいmainを優先してください。

以下のファイルを、省略・部分読み・要約読みせず完全に読んでください。全ファイルを読むまで、
外部接続、Google OAuth設定、価格取得、workflow、Count、Batch 6を実行しないでください。

1. `AGENTS.md`
2. `research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md`
3. `research/phase9-hypothesis-redesign-20260828/NEXT_SESSION_HANDOFF.md`
4. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
5. `research/phase9-exploratory-fxcm-20260901/README.md`
6. `research/phase9-exploratory-fxcm-20260901/GOOGLE_DRIVE_DATA_VAULT_PLAN.md`
7. `research/phase9-exploratory-fxcm-20260901/sources/FXCM_SOURCE_EVIDENCE.md`
8. `research/phase9-exploratory-fxcm-20260901/results/run-33627420903/FXCM_DRIVE_VAULT_AVAILABILITY_INDEPENDENT_AUDIT.json`
9. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_acquisition_v2.frozen.json`
10. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_availability_mask_v2.frozen.json`
11. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_partitions_v2.frozen.json`
12. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_manifest_schema_v2.frozen.json`
13. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_formal_boundary_amendment_v2.frozen.json`
14. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_operational_hardening_v2_1.frozen.json`
14a. `research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260903.md`
14b. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_run1_read_only_inventory_v2_1.frozen.json`
15. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_common.py`
16. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_v2_common.py`
17. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_google_drive_private.py`
18. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_acquire_year.py`
19. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_prepare_v2_1.py`
20. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_acquire_year_v2.py`
21. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_finalize_v2.py`
22. `research/phase9-exploratory-fxcm-20260901/runner/verify_fxcm_drive_vault_v2.py`
22a. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_google_drive_read_only.py`
22b. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_run1_read_only_inventory.py`
22c. `research/phase9-exploratory-fxcm-20260901/runner/verify_fxcm_drive_vault_run1_read_only_inventory.py`
23. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_contract.py`
24. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_qc.py`
25. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_workflow.py`
26. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_transaction.py`
27. `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml`
28. `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2.yml`
29. `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2-1.yml`
29a. `.github/workflows/phase9-exploratory-fxcm-drive-vault-run1-read-only-inventory.yml`
30. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_candidates_v6.frozen.json`
31. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_blind_mtf_count_only_v6.py`
32. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_blind_mtf_count_only_v6.py`
33. `.github/workflows/phase9-exploratory-fxcm-blind-mtf-batch6-count-only.yml`

## 目的

FXCM価格を一度だけ取得し、private Google DriveへSHA固定で保存する。同じデータをGPT側の
Count-only、Return/OOS、新期間、頑健性テストで再利用し、本物の優位性を探す。候補ごとに
取得・監査を繰り返さない。全Gate通過後だけMT5へ進む。

## 現在地

- ユーザー選択: Option 1（FXCM availability実測範囲をV2として使用）
- 確認済みExploratory edge: 0件
- 301～320: 全件救済禁止
- 321～324: 事前登録済み、Count未実行
- 既存Batch 6 workflow: 実行禁止
- V2 Drive folder ID: `1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v`
- V2 Drive folder: V2.1 Run #1の未完了transactionが残っている可能性あり。exact inventory未確認
- V2 target: 2012～2025年、25通貨ペア
- V2 direct: m1/H1 BID/ASK OHLC、提供時だけVolume
- canonical: M1由来M5/M15/M30/H1/H4/D1/W1
- direct H1: QC参照のみ。補完・代替禁止
- shard: 14年×25ペア×2 direct = 700件
- endpoint identity: base 36,400件、frozen-present 36,000件、known-missing 400件
- exact mask: `fxcm_drive_vault_availability_mask_v2.frozen.json`
- known-missing: 要求・補完・補間しない
- frozen-present取得失敗: workflow失敗、root sealなし
- 除外: 2010・2011年、CHFJPY/EURCAD/GBPAUD、direct D1、Tick、金銀、指数、原油、exotic FX
- public Git/public Artifactへ価格・timestamp・OAuth secretを保存しない
- public Run ArtifactへDrive file IDを保存しない
- Availability Run `33627420903`: 実行・独立監査済み、response body 0 byte
- V1 acquisition workflow: 恒久fail-closed、実行しない
- 旧V2 acquisition workflow: 恒久fail-closed、run 0件
- V2.1 acquisition workflow: Run `33705800232`（Run #1 / Attempt #1）を実行済み・failure。再実行禁止
- V2.1 successful years: 2012～2021
- V2.1 failed years: 2022/2023 empty、2024 not gzip、2025 too small
- V2.1 finalizer: skipped。GitHub Artifact 0、canonical `v2`未公開
- read-only transaction inventory: 契約・GET-only client・workflow・Tests実装済み、dispatch未承認・未実行
- V2.1 operational amendment: ユーザー承認済み、ただし価格取得認可効果なし
- V2.1 transaction: owner-only exact-empty root確認後に作成し、全検証後の単一PATCHだけで`v2`/`COMMITTED`へ公開
- 未完了transaction: 自動削除禁止、cleanupは別承認
- Vault価格取得: V2.1 Run #1で実行済み・failure。Formalへの認可効果なし、Count/Returnなし
- Google OAuth client、refresh token、同一client作成root: 設定済み
- GitHub Environment `phase9-fxcm-vault-acquisition-v2`: 作成済み
- required reviewer `tgkfnfnfv9-stack`: 設定済み
- Prevent self-review: off、administrator bypass: off、wait timer: off
- OAuth 3 secrets: Environmentへ設定済み（値を取得・表示・再入力させない）

## V2期間partition

- Development: 2012～2019
- Strict OOS: 2020～2021
- Robustness: 2022～2023
- Final holdout: 2024～2025

これはExploratory専用であり、Formal Phase 9 splitではない。V2で任意の価格response bodyを
読んだ時点で、Formalの2019年以降を未見とする主張は終了する。

Batch 6のCount範囲は凍結済みの
`[2017-01-01T00:00:00Z, 2018-12-31T00:00:00Z)`を変更しない。

## 次に行う作業

1. 最新remote main、Run #1事故正本、read-only inventory契約・client・workflow・Testsを確認する。
2. 現在は停止し、V2.1をrerun/replayしない。Drive objectを変更・削除しない。secret値を取得・表示・再入力させない。
3. ユーザーが新しい公開main SHAを確認し、別の明示承認を与えた場合だけread-only inventory Run #1 / Attempt #1を実行する。
4. metadata-only Artifactを独立監査し、transactionとyear stageのexact状態を確定する。
5. cleanupまたはversioned recoveryは、それぞれ別契約・別承認なしに行わない。
6. canonical vault完成と旧64系列互換性を確認するまでBatch 6へ進まない。321～324の条件とfrequency Gateを変更しない。
7. Count通過候補だけをReturn/OOS→新期間→頑健性へ進める。

取得/QC → Count-only → Return/OOS → 新期間・頑健性 → MT5の順序を厳守してください。
```

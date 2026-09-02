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
14. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_common.py`
15. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_v2_common.py`
16. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_google_drive_private.py`
17. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_acquire_year.py`
18. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_acquire_year_v2.py`
19. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_finalize_v2.py`
20. `research/phase9-exploratory-fxcm-20260901/runner/verify_fxcm_drive_vault_v2.py`
21. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_contract.py`
22. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_qc.py`
23. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_v2_workflow.py`
24. `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml`
25. `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2.yml`
26. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_candidates_v6.frozen.json`
27. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_blind_mtf_count_only_v6.py`
28. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_blind_mtf_count_only_v6.py`
29. `.github/workflows/phase9-exploratory-fxcm-blind-mtf-batch6-count-only.yml`

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
- V2 Drive folder: 同一OAuth clientで作成済み、価格未取得で空
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
- V2 acquisition workflow: 実装済み、未実行
- Vault価格取得: 未開始
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

1. 最新remote main、V2凍結契約、Tests、workflow、Environment設定完了状態を確認する。
2. 現在は停止し、V2 workflowを実行しない。secret値を取得・表示・再入力させない。
3. ユーザーが公開main SHAを確認し、別の明示承認を与えた場合だけV2 Run #1 attempt #1を一度実行する。
4. 取得後はprivate Driveの700 shard、manifest、SHA-256、mask、sealを独立監査する。
5. 旧64系列互換性を確認するまでBatch 6へ進まない。321～324の条件とfrequency Gateを変更しない。
6. Count通過候補だけをReturn/OOS→新期間→頑健性へ進める。

取得/QC → Count-only → Return/OOS → 新期間・頑健性 → MT5の順序を厳守してください。
```

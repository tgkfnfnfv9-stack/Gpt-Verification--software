# 次セッションへ送る文章

以下のコードブロックを、そのまま新しいセッションへ送る。

```text
GitHub Repository `tgkfnfnfv9-stack/Gpt-Verification--software` のPhase 9研究を引き継いでください。

最初に最新remote mainを確認し、必ず新しいmainを優先してください。

以下のファイルを、省略・部分読み・要約読みせず完全に読んでください。全ファイルを読むまで、
外部接続、Google OAuth設定、availability、価格取得、workflow、Batch 6を実行しないでください。

1. `AGENTS.md`
2. `research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md`
3. `research/phase9-hypothesis-redesign-20260828/NEXT_SESSION_HANDOFF.md`
4. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
5. `research/phase9-exploratory-fxcm-20260901/README.md`
6. `research/phase9-exploratory-fxcm-20260901/GOOGLE_DRIVE_DATA_VAULT_PLAN.md`
7. `research/phase9-exploratory-fxcm-20260901/sources/FXCM_SOURCE_EVIDENCE.md`
8. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_acquisition_v1.frozen.json`
9. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_partitions_v1.frozen.json`
10. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_manifest_schema_v1.frozen.json`
11. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_drive_vault_formal_boundary_amendment_v1.frozen.json`
12. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_common.py`
13. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_inventory.py`
14. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_google_drive_private.py`
15. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_acquire_year.py`
16. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_finalize.py`
17. `research/phase9-exploratory-fxcm-20260901/runner/verify_fxcm_drive_vault.py`
18. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_contract.py`
19. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_qc.py`
20. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_security.py`
21. `research/phase9-exploratory-fxcm-20260901/tests/test_fxcm_drive_vault_workflows.py`
22. `.github/workflows/phase9-exploratory-fxcm-drive-vault-availability-v1.yml`
23. `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml`
24. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_candidates_v6.frozen.json`
25. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_blind_mtf_count_only_v6.py`
26. `.github/workflows/phase9-exploratory-fxcm-blind-mtf-batch6-count-only.yml`
27. `research/phase9-exploratory-fxcm-20260901/results/run-33610462879/BLIND_MTF_BATCH5_RETURN_OOS_INDEPENDENT_AUDIT.json`
28. `research/phase9-exploratory-fxcm-20260901/results/run-33627420903/FXCM_DRIVE_VAULT_AVAILABILITY_INDEPENDENT_AUDIT.json`

## 目的

FXCM価格を一度だけ取得し、private Google DriveへSHA固定で保存する。その同じデータを
GPT側のCount-only、Return/OOS、新期間、頑健性テストで再利用し、本物の優位性を探す。
データ取得・監査を候補ごとに繰り返さない。全Gate通過後だけMT5へ進む。

## 現在地

- 確認済みExploratory edge: 0件
- 301～320: 全件救済禁止
- 321～324: 事前登録済み、Count未実行
- 既存Batch 6 workflow: 実行禁止
- Drive folder ID: `1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu`
- 判断時点のDrive folder: 空。次セッションでは外部確認前に正本を読む
- Vault target: 2010～2025年、G8全28通貨ペア
- direct: m1/H1/D1 BID/ASK OHLC、提供時だけVolume
- canonical: M1由来M5/M15/M30/H1/H4/D1/W1
- direct H1/D1: QC参照のみ。補完・代替禁止
- shard: 16年×28ペア×3 direct = 1,344件
- source identity: 16×28×3×52 = 69,888件
- Tick、金銀、指数、原油、exotic FX: V1対象外
- public Git/public Artifactへ価格を保存しない
- availability workflow Run `33627420903`: 実行・独立監査済み
- availability: 69,888件中36,000件存在、33,888件404
- 2010・2011年、direct D1全件、CHFJPY/EURCAD/GBPAUD全期間が不在
- acquisition workflow: 未実行
- Vault価格取得: 未開始
- Google OAuth: 未設定

## 期間partition

- Development: 2010～2019
- Strict OOS: 2020～2021
- Robustness: 2022～2023
- Final holdout: 2024～2025

これはExploratory専用であり、Formal Phase 9 splitではない。2019年以降のVault取得を
実行した時点で、Formalの2019年以降を未見とする主張は終了する。

Batch 6のCount範囲は凍結済みの
`[2017-01-01T00:00:00Z, 2018-12-31T00:00:00Z)`を変更しない。

## 次に行う作業

1. remote main、Availability独立監査正本、Testsを確認する。
2. 凍結V1 targetは不成立なので、一括取得workflow、OAuth設定、Drive書込みを実行しない。
3. G8全28ペア・必要期間・BID/ASK OHLCを満たす別sourceを選ぶか、利用可能なFXCM範囲だけの
   別V2 scopeをユーザーが明示承認するかを決める。黙って25ペアへ縮小しない。
4. 決定後に別versionの取得/custody/partition/shard/QC契約を事前凍結する。
5. 実装・Tests・公開後も、別の明示承認前には価格取得を実行しない。
6. Vault取得後もBatch 6を自動実行しない。旧64系列互換性を確認してから、データ入力だけを
   Vaultへ切り替える。321～324の条件とfrequency Gateは変更しない。

取得/QC → Count-only → Return/OOS → 新期間・頑健性 → MT5の順序を厳守してください。
```

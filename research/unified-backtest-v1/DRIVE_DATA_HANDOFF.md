# Google Driveデータ受渡し契約

汎用経路では、データ取得セッションが取得済みデータを次の形へ自動変換し、owner-only Google Driveへ1 bundleとして保存します。バックテスト基盤側で価格を再取得しません。

FXCM 2022～2025 Vaultには専用の`Unified Backtest from FXCM Vault V1` workflowがあります。こちらは年別archiveを一時領域へ順次取得し、統一入力へ変換して同じjob内でbacktestを実行するため、中間bundleの再uploadもCSVの手作業も不要です。元VaultへのDrive書込みは行いません。

## Bundle内部

```text
DATASET_MANIFEST.json
evidence/timestamp-semantics.json
evidence/provider-timestamp-primary-source.txt
series/<instrument>/M1.csv
series/<instrument>/H1.csv
roll-policy/<instrument>.json   # 連続CFD・先物だけ
evidence/<instrument>-roll-primary-source.txt   # 連続CFD・先物だけ
```

Bundle名は`unified-market-dataset-v1.tar.gz`です。archive直下に余分な親folderを入れません。通常fileとdirectory以外、symlink、hardlink、余分なfileは禁止です。

CSVのexact header：

```csv
timestamp_utc,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close
```

全銘柄についてdirect provider `M1`とdirect provider `H1`を入れます。M5/M15/M30/H4/D1は入れず、バックテスト基盤側で生成します。期間は`2022-01-01T00:00:00Z`以上、`2026-01-01T00:00:00Z`未満です。

## 取得セッションが返す4値

```text
DRIVE_FILE_ID=<Google Drive file ID>
DRIVE_BUNDLE_BYTES=<exact bytes>
DRIVE_BUNDLE_SHA256=<64桁lowercase SHA-256>
DATASET_MANIFEST_SHA256=<64桁lowercase SHA-256>
```

この4値と一緒に、manifestへ入れたexact銘柄一覧（instrument ID、provider symbol、asset class）も人間向け報告へ明記します。実行者はその一覧を確認してからmanifest SHAを承認します。Google Drive objectは本人所有・owner-only・非共有とします。連続CFD・先物はroll policy・一次証拠・適用済みM1/H1 SHAをbundleへ含め、manifestで固定します。

## 次の操作

### FXCM Vault専用経路

別のデータ取得セッションから、successful corrective acquisitionのrun ID、取得commit SHA、4年分のyear manifest SHAを受け取ります。`Unified Backtest from FXCM Vault V1`へ次を入力します。

```text
recovery_run_id=<successful acquisition workflow run ID>
recovery_head_sha=<exact acquisition commit SHA>
expected_year_manifest_sha256s=2022:<sha>,2023:<sha>,2024:<sha>,2025:<sha>
expected_head_sha=<実行を承認した現在のmain SHA>
confirmation=RUN_UNIFIED_BACKTEST_FROM_COMPLETED_FXCM_VAULT_2022_2025
timestamp_assumption_acknowledgement=I_ACCEPT_FXCM_BAR_OPEN_IS_EMPIRICALLY_ALIGNED_NOT_PROVIDER_EXPLICIT
usage_confirmation=I_APPROVE_RESEARCH_INPUT_FROM_2022_2025_FXCM_VAULT
strategy_id=                         # 空欄なら全enabled仮説
phase1_upload_confirmation=          # 通常は空欄
```

adapterは各H1について完全な60本のM1と同一timestampであることを要求します。H1 OHLCはdirect provider値を正本として保持し、M1集約との差は診断件数とhashへ記録します。欠損とcrossed open/closeは補完せず除外します。月次coverage不足は将来情報によるsignal選別に使わずwarningとして件数とhashをsummaryへ残し、backtestは完走させますが昇格不可にします。

### 汎用bundle経路

GitHub Actionsの`Unified Backtest V1`を開き、上記4値と次を入力します。

```text
expected_head_sha=<実行を承認したmainのexact commit SHA>
confirmation=RUN_UNIFIED_BACKTEST
strategy_id=                         # 空欄なら全enabled仮説
phase1_upload_confirmation=          # 通常は空欄
```

通常artifactは価格を含まないsummaryだけです。Phase 1用の価格入りJSONも一時的に受け取る場合だけ、次を指定します。

```text
phase1_upload_confirmation=UPLOAD_PRICE_BEARING_PHASE1
```

この場合のPhase 1 artifact保存期間は1日です。

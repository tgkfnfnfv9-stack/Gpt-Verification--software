# Google Driveデータ受渡し契約

データ取得セッションは、取得済みのGoogle Drive Vaultデータを次の形へ自動変換し、owner-only Google Driveへ1 bundleとして保存します。既存Vaultのunsealed stageや年別archiveをそのまま研究利用せず、取得・QC・利用承認が完了したcanonical M1/H1だけをbundle化します。バックテスト基盤側で価格を再取得しません。

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

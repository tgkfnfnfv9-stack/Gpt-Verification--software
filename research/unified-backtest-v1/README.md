# FX・商品 統一バックテスト基盤 V1

## 目的

同じ市場データを再利用し、仮説ファイルを交換するだけで次を一括実行します。

1. 最低限のデータ品質確認
2. 必要な時間足の生成
3. 仮説のsignal生成とepisode集約
4. 1・3・6本後、4・12・24時間後のspread込みバックテスト
5. 年・銘柄・時間足・BUY/SELL別の集計
6. Phase 1ビューア用JSONの生成

データ取得はこの基盤の責務ではありません。別セッションが作るデータを、下記の入力契約へ合わせて渡します。

## 入力

`DATASET_MANIFEST.json`とCSVを同じデータroot内に置きます。CSVは1銘柄・1時間足ごとのBID/ASK一体型で、次の9列を必須とします。

```csv
timestamp_utc,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close
2022-01-03T00:00:00Z,1.1000,1.1010,1.0990,1.1005,1.1002,1.1012,1.0992,1.1007
```

時刻は検証済みUTC bar openです。入力は全銘柄についてdirect providerの`M1`と`H1`を必須にします。`M5,M15,M30,H4,D1`は基盤内で生成し、持込み済み派生足は受理しません。H1はdirect H1を正本とし、M1由来H1とはtimestamp・BID/ASK OHLCの診断比較だけを行い、自動置換しません。

manifestはtimestamp意味論の一次証拠ファイルまでSHA固定します。連続CFD・先物を使う場合は、銘柄ごとにroll policy・一次証拠・適用済みM1/H1 SHAも必須です。全銘柄×M1/H1の1系列でも欠ける場合、各direct H1に対応する60本のM1が揃わない場合、または評価月のH1が最低240本・15活動日（短い部分月は比例縮小）に届かない場合は実行しません。

manifestの最小例は[`spec/DATASET_MANIFEST.example.json`](spec/DATASET_MANIFEST.example.json)です。各`path`はデータrootからの相対pathで、`sha256`と`bytes`を必須にします。

## 実行

```bash
python research/unified-backtest-v1/runner/unified_backtest.py \
  --data-root /private/market-data \
  --dataset-manifest /private/market-data/DATASET_MANIFEST.json \
  --config research/unified-backtest-v1/spec/backtest_config.v1.json \
  --strategy-registry research/unified-backtest-v1/strategies/registry.v1.json \
  --output-root /private/backtest-result
```

実行時に、必要なM5/M15/M30が入力になければdirect M1から、H4/D1がなければdirect H1から生成します。完全なtimestamp集合を持つbucketだけを採用し、欠損bucketは補完せず落とします。M1は銘柄ごとに検査・集約して破棄するため、現在のH1/D1仮説では全銘柄のM1を同時にメモリ保持しません。

## 新しい仮説の追加

1. `strategies/`へ新しいPythonファイルを追加
2. `registry.v1.json`へ1行追加
3. pluginの専用unit testを追加
4. 同じコマンドを実行

pluginは次の関数だけを公開します。一般Pythonではなく、import・file/network API・private属性・間接callを拒否するsignal専用の制限構文です。

```python
def generate_signals(api, strategy):
    ...
    return [api.signal(strategy["strategy_id"], symbol, "BUY", signal_time, entry_time)]
```

`api.series(symbol, timeframe)`でBID/ASKのmidpoint seriesを参照できます。Return計算、BID/ASK生値、集計、Phase 1出力はengine側が共通処理するため、pluginへ実装しません。pluginファイルはregistryにSHA-256固定し、因果性テストを通したレビュー済みファイルだけを読み込みます。新pluginには、将来部分の価格を変更しても過去signalが変わらないテストを必須にします。

## 出力

- `BACKTEST_SUMMARY.json`: 全仮説・全horizonの機械集計
- `phase1/*.json`: Returnを計算した仮説のPhase 1確認用JSON
- `artifact_manifest_sha256.txt`: 出力fileのSHA-256

Phase 1 JSONは`meta,strategy,charts,trades,notes`の直接root形式です。CountだけでReturn未計算の仮説には作りません。

## 時系列区分

既定configは取得対象の2022～2025年を次の区分で再利用評価します。

- Reused evaluation: 2022～2023
- Reused evaluation: 2024
- Reused evaluation: 2025（既に日付を認識済みなので厳密なholdoutとは呼ばない）

データが存在する区分だけ集計します。過去に閲覧済みの期間は厳密な未使用holdoutとは呼ばず、最終的な採用にはMT5 demo forwardを必須とします。

## データ取得セッションへの引継ぎ

データ取得担当は次だけを返せば、この基盤を変更せず実行できます。

1. `DATASET_MANIFEST.json`
2. manifestに列挙したBID/ASK一体型CSV
3. FXと商品を同じschema・UTCで保存
4. rawデータをGitへcommitしない

Handoff後の次操作は、上記コマンドまたは`Unified Backtest V1` workflowの実行だけです。データ取得側は、取得・QC・利用承認済みのGoogle Drive VaultデータからmanifestとCSVを`unified-market-dataset-v1.tar.gz`へまとめてowner-onlyのGoogle Driveへ保存し、Drive file ID・bundle bytes・bundle SHA-256・manifest SHA-256を返します。workflowには、実行を承認した`main`のexact commit SHAも入力します。workflowはDriveから一時領域へだけ展開し、実行後にbundleとCSVを削除します。生データはGitへcommitしません。

workflowが通常uploadするのは価格を含まないsummaryだけです。Phase 1 JSONにはmidpoint candleと個別約定値が入るため、明示的に`UPLOAD_PRICE_BEARING_PHASE1`を指定した場合だけ、1日保存の別artifactとしてuploadします。

## 判定の固定

- primaryは事前固定の`CLOCK_12H`だけです。
- `BAR_1/3/6`と`CLOCK_4H/24H`は診断用で、良いhorizonへの後付け変更には使いません。
- Entry/Exitは正確なbar openだけを使い、欠損時に次のbarへ繰り越しません。
- BUYはASKで入りBIDで出る、SELLはBIDで入りASKで出るためspreadを必ず含みます。
- commission、slippage、financingは未設定なら0または未算入と明示します。
- `REUSED_2022_2023`、`REUSED_2024`、`REUSED_2025`でprimaryの取引数・completion・平均R・PF・銘柄幅・四半期幅・date-cluster bootstrap下限をすべて満たした場合だけ`ROBUSTNESS_CANDIDATE_REUSED_DATA`と表示します。過去7候補＋今回2候補のBonferroni補正を使います。全期間が再利用評価であり、厳密な未使用holdout合格を意味しません。次にMT5 demo forward確認を経てEA化します。

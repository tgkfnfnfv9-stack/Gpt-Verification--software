# Phase 8 Blind Discovery

更新日: 2026-08-28

## 目的

PA-002を再利用・再最適化せず、次の3系統を独立に探索する。

1. Price Action
2. Volume / Volatility
3. Market Regime / Cross-Market

各系統5候補、合計15候補をOutcome閲覧前に固定した。候補の完全な数値条件は
`spec/candidate_registry.json`、検証手順とGateは
`policy/discovery_protocol.json`を正本とする。

## データ境界

| 区分 | 期間 | Phase 8での扱い |
|---|---|---|
| Warm-up | 2019-07-01〜2019-08-28 | 特徴量計算のみ |
| Discovery | 2019-08-28〜2022-08-28 | 今回評価可能 |
| Development | 2022-08-28〜2024-08-28 | 未取得・未評価 |
| OOS | 2024-08-28〜2025-08-28 | 未取得・未評価 |
| Final Holdout | 2025-08-28〜2026-08-28 | 未取得・未評価 |

WorkflowはDukascopyのBID/ASKバーを取得するが、SignalはBID OHLCとBID tick volumeだけで判定する。
これは別々のBID/ASKバー高値・安値から疑似MIDを作らないためである。Entry/Exit/MFE/MAEは
BUYならASK Entry・BID Exit、SELLならBID Entry・ASK Exitを使う。

## 時間の扱い

- バー数固定: 1、3、6 bars
- 実時間固定: 4、12、24 hours
- Primary: 12 hours
- Signal足終値確定後、次の取引可能バーOpenでEntry
- Split終端を跨ぐOutcomeは除外

同じ「3本」でもM15/H1/H4で実時間が異なるため、バー数固定と実時間固定を混同しない。

## 実行

GitHub Actions workflow:

`.github/workflows/phase8-blind-discovery.yml`

ジョブ:

- M15 Discovery
- H1/H4 Discovery（H4はH1からSide別に集約）

Raw市場データはRepositoryへ保存せず、取得manifest、SHA-256、検証結果だけをArtifactへ保存する。

## 禁止事項

- STRAT-PA-002の閾値変更・派生最適化
- H4だけの後付け採用
- Development/OOS/Final Holdoutの先行閲覧
- 結果を見て銘柄・時間足・方向を候補定義から削除
- Gate通過前のMT5 EA化
- API Key、Token、MT5資格情報の保存


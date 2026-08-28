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

## Discovery最終結果

GitHub Actions run `33210045954` で、登録済み15候補をM15とH1/H4の両層で評価した。
横断判定は有利な時間足だけを採用せず、両層のepisode-weighted mean edgeの小さい方を
順位スコアとした。

- DEVELOPMENT: 0
- WATCH: 0
- REJECT_FOR_DEVELOPMENT: 15

`STRAT-VV-104`は最初の横断判定で唯一WATCHとなったため、run `33213427085`で
全銘柄・M15/H1/H4を同一UTC日×方向episodeへ統合する最終監査を行った。統合Edgeは
`+0.2490 ATR`だったが、95% CI下限、BH-FDR、正の時間足比率の3 Gateに失敗した。
最終判定は`REJECT_FOR_DEVELOPMENT`であり、Phase 8の15候補に生存候補はない。
詳細は`results/RESULTS_SUMMARY.md`と`results/VV104_unified_episode_final_audit.json`を参照。

## 禁止事項

- STRAT-PA-002の閾値変更・派生最適化
- H4だけの後付け採用
- Development/OOS/Final Holdoutの先行閲覧
- 結果を見て銘柄・時間足・方向を候補定義から削除
- Gate通過前のMT5 EA化
- API Key、Token、MT5資格情報の保存

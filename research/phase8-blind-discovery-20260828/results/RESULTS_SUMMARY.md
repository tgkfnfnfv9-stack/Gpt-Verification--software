# Phase 8 Blind Discovery 結果要約

更新日: 2026-08-28  
評価範囲: Discoveryのみ（2019-08-28〜2022-08-28、Warm-upは2019-07-01から）  
初回実行: GitHub Actions run `33210045954`  
最終統合監査: GitHub Actions run `33213427085`

## 結論

| 判定 | 件数 | Strategy ID |
|---|---:|---|
| DEVELOPMENT | 0 | なし |
| WATCH | 0 | なし |
| REJECT_FOR_DEVELOPMENT | 15 | 全候補 |

`STRAT-VV-104`（Low-Participation Expansion Reversal）は唯一WATCHだったが、
全銘柄・M15/H1/H4を同一UTC日×方向episodeへ統合した最終監査で3 Gateに失敗した。
よって`REJECT_FOR_DEVELOPMENT`へ確定し、Phase 8の生存候補は0となった。

## VV-104最終統合監査

| 指標 | 結果 |
|---|---:|
| Matched signals | 4,968 |
| 統合unique episodes | 1,618 |
| Episode-weighted Edge | +0.2490 ATR |
| 95% CI | [-0.0255, 0.5194] |
| One-sided p | 0.0362 |
| BH-FDR adjusted p | 0.5430 |
| 正の銘柄比率 | 66.67% |
| 正の時間足比率 | 66.67% |
| 12時間のSignal Return | -0.3082 ATR |
| 最終判定 | REJECT_FOR_DEVELOPMENT |

失敗Gateは、`95% CI下限 > 0`、`BH-FDR <= 0.10`、
`正の時間足比率 >= 0.67`の3つ。H4 Edgeは`-0.0226 ATR`で、M15とH1だけを
後付け採用することは禁止した。Signal Return自体も負であり、正のEdgeは
matched controlがさらに悪かったことによる相対差である。

## 全15候補の横断結果

EdgeはPrimaryの実時間固定12時間、ATR単位。横断順位はM15とH1/H4の小さい方のEdgeを使い、
有利な時間足だけを選ばない。

| 系統 | Strategy ID | 仮説短名 | M15 episodes | M15 Edge | H1/H4 episodes | H1/H4 Edge | 横断判定 |
|---|---|---|---:|---:|---:|---:|---|
| Price Action | STRAT-PA-101 | Compression Range Break Continuation | 104 | +1.4026 | 74 | -0.3539 | REJECT |
| Price Action | STRAT-PA-102 | NR7 Inside-Bar Release | 1,688 | -0.2199 | 1,355 | -0.0166 | REJECT |
| Price Action | STRAT-PA-103 | EMA Pullback Resumption | 1,698 | -0.2852 | 1,349 | -0.2044 | REJECT |
| Price Action | STRAT-PA-104 | Three-Bar Staircase Continuation | 1,787 | -0.4382 | 1,570 | -0.2960 | REJECT |
| Price Action | STRAT-PA-105 | UTC Overnight Range Break | 1,525 | -0.1066 | 1,412 | -0.0151 | REJECT |
| Volume / Volatility | STRAT-VV-101 | Tick-Volume Range Shock Continuation | 1,654 | -0.2574 | 1,466 | -0.2443 | REJECT |
| Volume / Volatility | STRAT-VV-102 | Low-Vol Squeeze Release | 1,741 | -0.4523 | 1,030 | -0.0873 | REJECT |
| Volume / Volatility | STRAT-VV-103 | Climactic Wick Reversal | 410 | -0.3009 | 187 | +0.0197 | REJECT |
| Volume / Volatility | STRAT-VV-104 | Low-Participation Expansion Reversal | 1,574 | +0.2501 | 444 | +0.1328 | REJECT（最終統合監査） |
| Volume / Volatility | STRAT-VV-105 | Volatility Regime Onset Continuation | 1,351 | -0.1488 | 642 | -0.1139 | REJECT |
| Market Regime / Cross-Market | STRAT-MR-101 | USD Breadth Confirmation | 1,790 | -0.5675 | 1,595 | -0.4509 | REJECT |
| Market Regime / Cross-Market | STRAT-MR-102 | JPY Cross Breadth Confirmation | 1,791 | -0.8578 | 1,435 | -0.6555 | REJECT |
| Market Regime / Cross-Market | STRAT-MR-103 | Gold-Silver Co-Momentum | 1,444 | -1.8263 | 1,002 | -0.8515 | REJECT |
| Market Regime / Cross-Market | STRAT-MR-104 | Brent-WTI Relative-Move Reversion | 1,274 | -0.0005 | 752 | +0.0560 | REJECT |
| Market Regime / Cross-Market | STRAT-MR-105 | Commodity Cross-Family Breadth | 1,375 | -1.2749 | 1,188 | -0.4780 | REJECT |

## 系統別上位5（横断保守順位）

1. Price Action: PA-105, PA-102, PA-103, PA-101, PA-104
2. Volume / Volatility: VV-104, VV-105, VV-101, VV-103, VV-102
3. Market Regime / Cross-Market: MR-104, MR-101, MR-102, MR-105, MR-103

完全な数値Entry、Entry時点情報、対象銘柄・時間足、Sample Size、Matched Control、
バー数固定/実時間固定Return、MFE/MAE、年度別・銘柄別・時間足別、parameter sensitivity、
弱点および判定理由は`phase8_cross_timeframe_decision.json`に保存する。

## 境界と次Gate

- Development、OOS、Final Holdoutは未取得・未評価。
- Final Holdout（2025-08-28〜2026-08-28）は未開封。
- PA-002はREJECT_FOR_DEVELOPMENTのまま。再最適化、H4だけの採用、EA化は禁止。
- Phase 8はDukascopyバーによるDiscovery screenであり、OANDA MT5 tick/cost検証ではない。
- Phase 8の15候補はすべてREJECT_FOR_DEVELOPMENT。追加最適化・閾値変更・時間足選別をしない。
- PA-002を含む正式検証16仮説すべてがDevelopment不採用。
- 次に進む場合はPhase 8の答えを再利用せず、Phase 9として新しい独立仮説をOutcome閲覧前に登録する。

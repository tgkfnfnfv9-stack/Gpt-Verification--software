# Phase 9 自動売買研究｜次セッション引き継ぎ

更新日: 2026-08-28

## 1. 最初に読むファイル

次セッションでは、以下を順番に読む。

1. `research/phase8-blind-discovery-20260828/results/PHASE8_FINAL_DECISION.json`
2. `research/phase8-blind-discovery-20260828/results/RESULTS_SUMMARY.md`
3. `research/phase9-hypothesis-redesign-20260828/README.md`
4. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
5. `research/phase9-hypothesis-redesign-20260828/PHASE8_HYPOTHESIS_REVIEW.md`
6. `research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO.md`
7. `research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.draft.json`
8. `research/phase9-hypothesis-redesign-20260828/DATA_REQUIREMENTS.md`
9. `research/phase9-hypothesis-redesign-20260828/spec/data_requirements.draft.json`
10. `research/phase9-hypothesis-redesign-20260828/policy/hypothesis_stage_policy.json`

## 2. 確定済みの現在地

```text
正式検証済み
├── STRAT-PA-002                  REJECT_FOR_DEVELOPMENT
└── Phase 8の15候補              全件REJECT_FOR_DEVELOPMENT

Phase 9
├── 独立した新仮説               8件
├── 旧仮説を構造から再設計       7件
├── 合計                         15件
├── 状態                         UNTESTED_DRAFT
├── 事前登録                     未実施
├── データ取得                   未実施
└── バックテスト                 0件
```

正式検証済み16仮説にはDevelopment候補が存在しない。

## 3. Phase 9の15候補

### Price Structure

- STRAT-P9-PS-201: Confirmed Balance Break Retest
- STRAT-P9-PS-202: Failed 20-Bar Break Reversal
- STRAT-P9-PS-203: Higher-Timeframe Trend Pullback Re-acceleration
- STRAT-P9-PS-204: European Session Range False-Break
- STRAT-P9-PS-205: Long-Horizon Trend with Intraday Pullback

### Liquidity / Volatility

- STRAT-P9-LV-201: Seasonally Adjusted Participation Shock
- STRAT-P9-LV-202: Squeeze Release Retest
- STRAT-P9-LV-203: Confirmed Climactic Absorption
- STRAT-P9-LV-204: Isolated Illiquidity Dislocation
- STRAT-P9-LV-205: Volatility-Managed Trend Resumption

### Relative Value / Regime

- STRAT-P9-RR-201: Cross-Sectional FX Momentum Rank
- STRAT-P9-RR-202: Currency-Basket Residual Reversion
- STRAT-P9-RR-203: Gold-Silver Dynamic Hedge Residual
- STRAT-P9-RR-204: Brent-WTI Dynamic Hedge Residual
- STRAT-P9-RR-205: FX Carry-Momentum Agreement

完全な数値Entry、Entry時点情報、対象銘柄・時間足、Matched Control、outcome、
sample-size Gate、parameter sensitivity、弱点は`spec/candidate_registry.draft.json`にある。

## 4. 次セッションで最初に決めること

検証コードを書く前に、以下の4点をユーザーと討論する。

1. **PS-201とLV-202の重複**
   - 両方とも「break後のretest保持」である。
   - 1件へ統合するか、PSはprice balance、LVはvolatility squeezeとして明確に分離する。

2. **LV-204の独立性**
   - 旧VV-104の閾値調整は禁止。
   - 残すなら`ImpactScore`、正常spread、peer非確認、midpoint reclaimのすべてを必須にする。

3. **RR-205のデータ可用性**
   - historical 1か月forward pointsまたはpoint-in-time broker financingが必要。
   - 中央銀行政策金利だけで代用しない。
   - データがなければreturnを見る前に候補を削除または独立候補と差し替える。

4. **最終候補数**
   - 現在は15件。
   - 重複を減らして10〜12件にするか、15件を維持してFDR補正するか決定する。

## 5. 必要データ

対象はFX8、Gold、Silver、Brent、WTIの12銘柄。

- M15/H1 BID OHLC
- M15/H1 ASK OHLC
- tick volume
- point-in-time spread
- H4/D1への決定的集計
- cross-market同期情報
- Brent/WTIのroll・取引時間metadata
- RR-205用historical forward/financing data
- provider/version、row counts、gap、SHA-256

提案期間は次のとおり。

- Warm-up: 2013-01-01〜2014-08-28 exclusive
- Phase 9 Discovery: 2014-08-28〜2019-08-28 exclusive
- Development / Walk Forward: 2022-08-28〜2024-08-28 exclusive
- Strict OOS: 2024-08-28〜2025-08-28 exclusive
- Final Holdout: 2025-08-28〜2026-08-28

2019-08-28〜2022-08-28はPhase 8で見ているため、Phase 9の仕様選択・昇格根拠に使わない。

生の市場CSVはGitHubへcommitしない。取得仕様、version、行数、gap、SHA-256、検証コード、
結果だけをGitHubへ保存し、生データは凍結後に再取得可能な仕組みにする。

## 6. 次に実行する順序

```text
15仮説の討論
    ↓
重複・データ不能候補の整理
    ↓
最終候補一覧を確定
    ↓
Entry・対象・期間・Matched Control・Gateを凍結
    ↓
GitHubへ事前登録commit
    ↓
2013〜2019データのavailability確認・取得
    ↓
品質Gateとmanifest生成
    ↓
Phase 9 Discoveryを一括実行
    ↓
REJECT / WATCH / DEVELOPMENT判定
```

データavailability確認でreturn、MFE、MAE、勝率、edgeを計算してはいけない。

## 7. 継続する禁止事項

- PA-002の最適化、閾値変更、H4だけの採用
- Phase 8の15候補の再最適化
- 2019〜2022の結果に合わせたPhase 9条件変更
- 結果を見た後の銘柄・時間足選択
- Development、OOS、Final Holdoutの先行取得・閲覧
- OANDA MT5 EAの実装
- RR-205を政策金利だけで検証
- 生の巨大市場データや認証情報をGitHubへ保存

## 8. 最終運用条件

- Broker: OANDA
- Platform: MT5
- Account: live standard
- EA: 全研究Gateを通過した後のみ可
- 必須Gate: Discovery、Development、Walk Forward、Strict OOS、現実的cost、Final Holdout

## 9. 次セッション開始時の返答内容

次セッションの担当は、最初に日本語で以下を報告する。

1. 正式検証済み16仮説は全件REJECT
2. Phase 9は15件の未検証草案
3. 新規8件、再設計7件
4. データ取得とバックテストは未開始
5. Final Holdoutは未開封
6. 最初の議題はPS-201/LV-202、LV-204、RR-205、最終候補数

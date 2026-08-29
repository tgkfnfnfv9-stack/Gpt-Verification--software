# Phase 9 自動売買研究｜次セッション引き継ぎ

更新日: 2026-08-29

## 最初に読む

1. `research/phase8-blind-discovery-20260828/results/PHASE8_FINAL_DECISION.json`
2. `research/phase8-blind-discovery-20260828/results/RESULTS_SUMMARY.md`
3. `research/phase9-hypothesis-redesign-20260828/README.md`
4. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
5. `research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md`
6. `research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md`
7. `research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json`
8. `research/phase9-hypothesis-redesign-20260828/DATA_REQUIREMENTS.md`
9. `research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json`
10. `research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json`

## 現在地

```text
正式検証済み16件        全件REJECT_FOR_DEVELOPMENT
Phase 9 formal alpha      11件・UNTESTED_PREREGISTERED
Phase 9 risk overlay       1件・UNTESTED_PREREGISTERED
Confirmatory family       12件・BH-FDR q=0.10
市場データ取得            未開始
return/backtest           0件
Development/OOS/Holdout   未取得・未開封
MT5 EA                    禁止
```

PS-201はLV-202へ統合、LV-204は独立性不足でpretest削除、RR-205はcarry data不足でpretest除外、LV-205はPS-205と重複するためrisk overlayへ移動しました。いずれもPhase 9 outcomeを見た統計的REJECTではありません。

## 次の順序

```text
provider・instrument mapping・calendar・versionを結果なしで固定
  ↓
2013-01-01 <= timestamp < 2019-08-28だけ取得
  ↓
品質Gate・manifest
  ↓
count-only sample/coverage Gate
  ├─ 不足: REJECT_AS_UNDERPOWERED、p=1、return非計算
  └─ 通過: 12 confirmatory questionsを同時実行
  ↓
BH-FDR・CI・cost・breadth・sensitivity Gate
```

禁止事項は、旧仮説再最適化、銘柄/時間足の後付け選択、Phase 8期間の再利用、Development/OOS/Final Holdoutの照会・取得、候補差し替え、EA実装です。旧draftは実行に使いません。

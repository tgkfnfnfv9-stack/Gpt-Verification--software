# Phase 9 自動売買研究｜次セッション引き継ぎ

更新日: 2026-08-29

## 最初に読む

1. `PHASE9_OPERATIONS_GUIDE.md`
2. `POLICY_INCIDENT_20260829.md`
3. Phase 8 `results/PHASE8_FINAL_DECISION.json`
4. Phase 8 `results/RESULTS_SUMMARY.md`
5. `README.md`
6. `SESSION_STATE.json`
7. `DESIGN_DECISIONS.md`
8. `HYPOTHESIS_PORTFOLIO_FINAL.md`
9. `spec/candidate_registry.frozen.json`
10. `DATA_REQUIREMENTS.md`
11. `spec/data_requirements.frozen.json`
12. `policy/preregistered_research_policy.json`

## 現在地

- Formal alpha 11件＋risk overlay 1件
- Confirmatory family 12件、全件UNTESTED_PREREGISTERED
- 正式なPhase 9データ取得、return、backtestは未開始
- 旧tmp workflow 2本はfail-closedで無効化
- Phase 9固有outcomeは未閲覧
- 2022〜2026年は旧workflow accessのため後続split有効性の再監査が必要
- EAは禁止

## 次に実行する1作業

Phase 9専用のacquisition-only workflow、source manifest、instrument mapping、calendar、Energy roll規則、境界testを結果なしで作成する。取得許可は`2013-01-01 <= timestamp < 2019-08-28`だけ。取得jobでreturnを計算しない。

# Phase 9 自動売買研究｜次セッション引き継ぎ

更新日: 2026-08-30

## 最初に読む

1. `PHASE9_OPERATIONS_GUIDE.md`
2. `POLICY_INCIDENT_20260829.md`
3. `POLICY_INCIDENT_20260830.md`
4. `PROVIDER_ACQUISITION_BLOCKER.md`
5. `JFOREX_SOURCE_CHANNEL_AMENDMENT.md`
6. Phase 8 `results/PHASE8_FINAL_DECISION.json`
7. Phase 8 `results/RESULTS_SUMMARY.md`
8. `README.md`
9. `SESSION_STATE.json`
10. `DESIGN_DECISIONS.md`
11. `HYPOTHESIS_PORTFOLIO_FINAL.md`
12. `spec/candidate_registry.frozen.json`
13. `DATA_REQUIREMENTS.md`
14. `spec/data_requirements.frozen.json`
15. `policy/preregistered_research_policy.json`

## 現在地

- Formal alpha 11件＋risk overlay 1件
- Confirmatory questions 12件（1 family）、全件UNTESTED_PREREGISTERED
- 正式なPhase 9データ取得、return、backtestは未開始
- Phase 8旧workflowはfail-closedで無効化
- Phase 9固有outcomeは未閲覧
- Phase 9市場price fileは0件。取得は開始していない
- 公開endpoint＋dukascopy-go経路は廃止
- 公式認証JForex Tester API経路を凍結。Build preflight実行待ち
- 実取得は依存lockとfull-QC/raw保管経路を固定するまでfail-closed
- H1は全12・両side共通で2019-08-01以降を事前除外。M15は2019-08-28未満まで
- 2022〜2026年は旧workflow accessのため後続split有効性の再監査が必要
- EAは禁止
- Run `33289406745`はworkflow schema検証失敗。job 0、artifact 0、price/outcome access 0で是正済み

## 次に実行する1作業

`phase9-acquisition-only`を2つの完全一致文字列でmanual dispatchし、認証・price request前に意図的に停止するBuild preflightだけを行う。Artifactの全Maven依存SHAと再現build JAR SHAを監査・凍結し、同一runでfull QCする実装または承認済み非公開raw保管を決めるまで実取得しない。

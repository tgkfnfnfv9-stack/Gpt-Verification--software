# 次セッションへ送る文章

以下をそのままコピーして、新しいセッションへ送る。

```text
GitHub Repository tgkfnfnfv9-stack/Gpt-Verification--software のPhase 9自動売買研究を引き継いでください。

最初に以下を完全に読んでください。

1. AGENTS.md
2. research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md
3. research/phase9-hypothesis-redesign-20260828/PHASE9_DATA_ACQUISITION_VALIDATION_RUNBOOK.md
4. research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260829.md
5. research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260830.md
6. research/phase9-hypothesis-redesign-20260828/PROVIDER_ACQUISITION_BLOCKER.md
7. research/phase9-hypothesis-redesign-20260828/JFOREX_SOURCE_CHANNEL_AMENDMENT.md
8. research/phase8-blind-discovery-20260828/results/PHASE8_FINAL_DECISION.json
9. research/phase8-blind-discovery-20260828/results/RESULTS_SUMMARY.md
10. research/phase9-hypothesis-redesign-20260828/README.md
11. research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json
12. research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md
13. research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md
14. research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json
15. research/phase9-hypothesis-redesign-20260828/DATA_REQUIREMENTS.md
16. research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json
17. research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json
18. research/phase9-hypothesis-redesign-20260828/results/s1b-run-33376110507/S1B_AUDIT.json
19. research/phase9-hypothesis-redesign-20260828/data_manifest/native_entry_allowlist.run33376110507.json
20. research/phase9-hypothesis-redesign-20260828/results/gate-b-native-allowlist/GATE_B_AUDIT.json

8つの論理役割A0〜A7を使用してください。同時実行上限が7なら2波に分け、サブエージェントはread-only監査、主担当だけがGitHubへCommitしてください。作業前後にremote mainを確認し、force push、reset --hard、ユーザー変更の破棄、git add .、git add -Aは禁止です。

現在はFormal alpha 11件＋Risk overlay 1件、全12確認項目がUNTESTED_PREREGISTEREDです。Phase 9の正式取得、Actual Full-QC、Count-only、Return検証は未開始で、価格ファイル0件、確認済み優位性0件です。

S1B Gate A Run 33376110507はcompleted/successです。

- Head SHA: 951c38aaa875180fa7dbbe498866a4e3ece50e9c
- Job ID: 99437846539
- Artifact ID: 9751919672
- Artifact ZIP SHA-256: ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a
- 116 locked JARすべてSHA一致
- Native候補28件
- Run 1のJava .class CAFEBABE誤分類28,088件は除外済み
- Dukascopy/market credential、外部JNLP、JForex connect、market request、禁止期間requestはすべてなし
- Phase 9価格ファイル0、Outcome未計算
- acquisition_authorized=false

Run 2はlocked-JAR静的棚卸しの工学的PASSであり、実データ取得許可ではありません。Gate B exact-match allowlistはRun 2とは別Commitで凍結・検証済みですが、acquisition_authorized=falseのままです。

今回の単一作業は、exact shaded runnerを静的scanし、native load/mapped DSO、child process、write/cache mutation、OS egressをno-secret/no-priceで検証する次Gateを、別のatomic Commitとして設計・実装することです。

Gate BのRun ID、head SHA、116-JAR manifest SHA、Artifact ZIP SHA、各archive path/SHA、entry path/SHA/size/magic、対象OS/arch、fail-closed規則を変更しないでください。次GateでもGate Bだけでacquisition_authorized=trueに変更しないでください。

Remote JNLP lock、streaming 48-series Full-QC、raw custodyが未解決なら、demo secrets設定、外部JNLP接続、availability照会、JForex connect、price取得をしないでください。

将来の正式取得範囲は次だけです。

- 12銘柄 × M15/H1 × BID/ASK = 48系列
- M15: 2013-01-01 inclusiveから2019-08-28 exclusive
- H1: 2013-01-01 inclusiveから2019-08-01 exclusive
- H4/D1はcanonical H1から完全UTC bucketだけを派生
- 欠損は記録し、Forward Fill、期間延長、H1 tailの復活は禁止
- Raw市場CSV、cache、資格情報をGitや公開Artifactへ保存しない

Count-only完了前はReturn、Return符号、MFE、MAE、Edge、勝敗、勝率、Profit Factor、Drawdown、累積R、P値、信頼区間、順位、Outcome chartを計算・表示・閲覧しないでください。Phase 9 JSONを既存Outcome viewerへ読み込まないでください。Development、OOS、Final Holdoutの先行照会・取得、旧仮説の再最適化、結果を見た銘柄・時間足選択、MT5 EA実装は禁止です。

実装、Tests、A7 red-team、GitHubへのatomic Commit、remote head・Actions監査まで進め、Commit SHA、変更ファイル、残Blocker、価格アクセス、禁止期間アクセス、Outcome未計算を報告してください。
```

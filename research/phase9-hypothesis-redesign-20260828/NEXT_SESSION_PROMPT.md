# 次セッションへ送る文章

以下をそのままコピーして、新しいセッションへ送る。

```text
GitHub Repository tgkfnfnfv9-stack/Gpt-Verification--software のPhase 9自動売買研究を引き継いでください。

最初に以下を完全に読んでください。

1. AGENTS.md
2. research/phase9-hypothesis-redesign-20260828/NEXT_SESSION_HANDOFF.md
3. research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md
4. research/phase9-hypothesis-redesign-20260828/PHASE9_DATA_ACQUISITION_VALIDATION_RUNBOOK.md
5. research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260829.md
6. research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260830.md
7. research/phase9-hypothesis-redesign-20260828/PROVIDER_ACQUISITION_BLOCKER.md
8. research/phase9-hypothesis-redesign-20260828/JFOREX_SOURCE_CHANNEL_AMENDMENT.md
9. research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json
10. research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md
11. research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md
12. research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json
13. research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json
14. research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json
15. research/phase9-hypothesis-redesign-20260828/runner/phase9_actual_full_qc.py
16. research/phase9-hypothesis-redesign-20260828/spec/provider_schedule_contract.frozen.json

8つの論理役割A0〜A7を使用してください。同時実行上限が7なら2波に分け、サブエージェントはread-only監査、主担当だけがGitHubへCommitしてください。作業前後にremote mainを確認し、force push、reset --hard、ユーザー変更の破棄、git add .、git add -Aは禁止です。

Actual Full-QC実装基準は9eb7ce667bea8e76a7f9bb1f2d378eebd8957206です。現在のremote mainには、その後の引継ぎ文書Commitも含まれるため、作業開始時に最新remote mainを確認してください。

現在はFormal alpha 11件＋Risk overlay 1件、全12確認項目がUNTESTED_PREREGISTEREDです。Phase 9価格ファイル0件、確認済み優位性0件です。Actual Full-QC契約は実装済みですが、実データでは未実行です。Count-only、Return検証、バックテストは未開始です。

完了済み:

- S1B Gate A Run 33376110507: completed/success
- Gate B native exact allowlist: PASS、取得認可効果なし
- Gate C2 runtime mapping exact allowlist: PASS、取得認可効果なし
- Gate C3 Run 33455444958 / Job 99694321791 / Artifact 9781258311: completed/success
- Gate C3 ZIP SHA-256: 4cee963b9c3ffa7bb88bec5287a36de82ec4197c8c7e7e2277ea313acd4970c8
- Actual Full-QC contract Run 33459534741 / Job 99706597775 / Artifact 9782660195: completed/success
- Actual Full-QC contract ZIP SHA-256: af4d807d725c0a6207e19d3fbadc0157603bb8cd40474545564012938c59f4d5
- Full-QC tests 131 PASS、A6/A7 P0/P1なし
- Credential、外部JNLP、JForex connect、availability、price、禁止期間、Outcomeへのアクセスなし
- acquisition_authorized=false
- count_only_authorized=false

現在はprovider schedule source readinessでP0 BLOCKEDです。`trading_calendar.json`は`provider_schedule_version=NO_VERSION_AVAILABLE_YET`であり、非価格・非JNLP・pre-connectで使えるDukascopy公式version付きcomplete historical schedule sourceはRepositoryにありません。公式`IDataService.getOfflineTimeDomains`は現行経路ではJForex contextを必要とし、接続禁止と循環します。またholiday、maintenance、Energy sessionの完全性も未証明です。

次の単一作業は、generic weekday gridやcurrent session templateをinventoryと偽装せず、provider schedule source P0を解消することです。解決方法は、Dukascopy公式のversion付きcomplete historical schedule sourceを特定・hash-lockするか、availability・bar・price・order・Outcomeを機械的に禁止したmetadata-only JForex connection amendmentを別Commit・別承認で事前登録するかのどちらかです。後者でもholiday/Energy session完全性の証明が必要です。

P0解消後にのみ、provider schedule inventoryを価格データとは独立して正式取得し、Run ID、head SHA、Artifact ID、Artifact ZIP SHA、provider/version、UTC/BAR_OPEN、24 schedule fileのpath/SHA/count/first/last、aggregate SHAを監査した後、別Commitでcanonical exact-match allowlistを凍結してください。

同一Runのinventoryで自己認可しないでください。Canonical path、Git strict ancestor、freeze parent、Git object byte一致、tracked/unmodifiedをfail-closedで検証してください。この作業だけでacquisition_authorized=trueに変更しないでください。

Provider schedule、Energy metadata、Run/Artifact identity、remote JNLP lockなどの残Blockerが解消し、別Gateで明示的に取得認可されるまでは、demo secrets設定、外部JNLP接続、availability照会、JForex connect、price取得をしないでください。

将来の正式取得範囲:

- 12銘柄 × M15/H1 × BID/ASK = 48系列
- M15: 2013-01-01 inclusiveから2019-08-28 exclusive
- H1: 2013-01-01 inclusiveから2019-08-01 exclusive
- H4/D1はcanonical H1から完全UTC bucketだけを派生
- 欠損は記録し、Forward Fill、期間延長、H1 tailの復活は禁止
- Raw市場CSV、cache、資格情報をGitや公開Artifactへ保存しない

Count-only完了前はReturn、Return符号、MFE、MAE、Edge、勝敗、勝率、Profit Factor、Drawdown、累積R、P値、信頼区間、順位、Outcome chartを計算・表示・閲覧しないでください。Phase 9 JSONを既存Outcome viewerへ読み込まないでください。Development、OOS、Final Holdoutの先行照会・取得、旧仮説の再最適化、結果を見た銘柄・時間足選択、MT5 EA実装は禁止です。

実装、Tests、A7 red-team、GitHubへのatomic Commit、remote head・Actions監査まで進め、Commit SHA、変更ファイル、残Blocker、価格アクセス、禁止期間アクセス、Outcome未計算を報告してください。
```

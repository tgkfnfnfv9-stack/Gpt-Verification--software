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
9. research/phase9-hypothesis-redesign-20260828/JFOREX_METADATA_ONLY_CONNECTION_AMENDMENT.md
10. research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json
11. research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md
12. research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md
13. research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json
14. research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json
15. research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json
16. research/phase9-hypothesis-redesign-20260828/runner/phase9_actual_full_qc.py
17. research/phase9-hypothesis-redesign-20260828/spec/provider_schedule_contract.frozen.json
18. research/phase9-hypothesis-redesign-20260828/spec/metadata_only_jforex_schedule_gate.frozen.json
19. research/phase9-hypothesis-redesign-20260828/spec/metadata_only_local_m1_gate.frozen.json
20. research/phase9-hypothesis-redesign-20260828/spec/metadata_owned_method_allowlist.frozen.json
21. research/phase9-hypothesis-redesign-20260828/JFOREX_REMOTE_JNLP_OBSERVATION_AMENDMENT.md
22. research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_observation_amendment.frozen.json
23. research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_initial_observation_gate.frozen.json
24. research/phase9-hypothesis-redesign-20260828/results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json
25. research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_observed_url_allowlist.frozen.json
26. research/phase9-hypothesis-redesign-20260828/runner/verify_phase9_remote_jnlp_independent_audit.py
27. research/phase9-exploratory-fxcm-20260901/README.md
28. research/phase9-exploratory-fxcm-20260901/MULTI_TIMEFRAME_DATA_PLAN.md
29. research/phase9-exploratory-fxcm-20260901/spec/fxcm_multitimeframe_data_requirements.frozen.json
30. research/phase9-exploratory-fxcm-20260901/results/run-33482595275/FXCM_CANONICAL_ALLOWLIST.json

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
- Remote JNLP initial identity observation Run 33500446289 / Job 99832303024 / Artifact 9797466074: completed/success
- Remote observation implementation Commit: aa9d46a6a42936042a406bdf339f07d378cc79b7
- Artifact ZIP SHA-256: 5a0339a026ea2ac0a7382b3ad7e0510a303609ab8817d55a268b55108415b8d2
- exact initial URLへのunauthenticated GET 1回だけを実施。HTTP 200、2445 bytes、body SHA-256 4e5adcbb29116e7f17b3babfc4aa47590d06baca50a98745d300d4824a1a70e9
- redirect、recursive resource、Credential、JForex connect、availability、provider schedule、price、禁止期間、Outcomeへのアクセスなし
- Run/Job/Artifact/head/ZIPは独立監査済み。観測5 exact URLは元Runとは別Commitでevidence-only allowlistとして凍結済み
- 単一使用認可は消費済み。rerun/replay/follow-up URL requestは未認可
- Exploratory FXCM Run 33482595275 / Job 99775327873 / Artifact 9790552032: completed/success
- FX8 direct H1 BID/ASK、2017–2018、832 source objects、98,910 barsを取得・QC済み
- 使用可能97,644 bars、ASK Open < BID Open 1,266 barsは価格変更せずBID/ASK両方を隔離
- raw価格はsame-run cleanup済み。Git/Artifactには価格を保存していない
- MTF必要範囲はFX8 × M15/H1/H4/D1 × BID/ASK = 64系列
- direct m1/H1を取得し、m1→M15、H1→H4/D1を完全UTC bucketだけで生成する要件を凍結済み
- acquisition_authorized=false
- count_only_authorized=false
- research_outcomes_calculated=false

現在の優先課題は、H1だけで止まっているFXCM exploratory trackをマルチタイムフレーム化することです。Formal provider schedule/JForex blockerの追加監査は後回しにしてください。

次の単一作業は、`fxcm_multitimeframe_data_requirements.frozen.json`に完全一致するFX8 m1/H1取得＋M15/H4/D1生成＋QC workflowを実装し、1回実行することです。対象は8通貨ペア、2017-01-01 inclusive～2018-12-31 exclusive、direct m1/H1、BID/ASKです。最終64系列を作ります。

MTFの役割はD1=regime、H4=structure/pullback/range、H1=setup、M15=entry timingです。m1→M15は15本、H1→H4は4本、H1→D1は24本の完全UTC bucketだけを使い、不完全bucketはdrop/count、Forward Fillは禁止します。m1由来H1はdirect H1とのQC照合専用です。

取得/QC Runではsignal count、Return、Return符号、MFE、MAE、Edge、勝敗、勝率、Profit Factor、Drawdown、累積R、P値、信頼区間、順位、Outcome chartを計算しないでください。MTF 64系列QC完了後に別GateでCount-only、その完了後にReturn/OOS検証へ進みます。

公式`getOfflineTimeDomains`はweekend intervalsしか保証せず、holiday、maintenance、Energy daily session、歴史的session-rule変更、provider schedule versionの完全性は未証明です。SDK内部のmarket bytes受信・cache persistenceも`UNPROVEN`です。これらをfalseまたはcompleteと自己申告しないでください。前提証明が揃うまでmanual connection workflowをdispatchせず、24 schedule files、inventory、allowlistを作らないでください。

P0解消後にのみ、provider schedule inventoryを価格データとは独立して正式取得し、Run ID、head SHA、Artifact ID、Artifact ZIP SHA、provider/version、UTC/BAR_OPEN、24 schedule fileのpath/SHA/count/first/last、aggregate SHAを監査した後、別Commitでcanonical exact-match allowlistを凍結してください。

同一Runのinventoryで自己認可しないでください。Canonical path、Git strict ancestor、freeze parent、Git object byte一致、tracked/unmodifiedをfail-closedで検証してください。この作業だけでacquisition_authorized=trueに変更しないでください。

FXCM無料CandleDataにないXAUUSD、XAGUSD、BRENTCMDUSD、LIGHTCMDUSD、tick volumeはFX8 MTF trackへ混ぜないでください。別provider/別trackとして後で固定します。Formal Phase 9のprovider schedule、Energy metadata、remote runtime closure、実API互換性、cache/custody blockerも未解決のままです。

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

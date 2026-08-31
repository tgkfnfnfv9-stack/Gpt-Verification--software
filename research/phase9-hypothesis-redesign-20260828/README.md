# Phase 9 Hypothesis Redesign

更新日: 2026-08-31
状態: `FROZEN_PREREGISTERED_ACQUISITION_BLOCKED`

最初に [PHASE9_OPERATIONS_GUIDE.md](./PHASE9_OPERATIONS_GUIDE.md) を読みます。全手順、仮説一覧、GitHub取得方法、サブエージェント分担、Gate、禁止事項、更新・引き継ぎ方法の運用正本です。

## 科学仕様の正本

- `spec/candidate_registry.frozen.json`
- `spec/data_requirements.frozen.json`
- `policy/preregistered_research_policy.json`

## 現在地

| 項目 | 状態 |
|---|---|
| Formal alpha | 11 |
| Risk overlay | 1 |
| Confirmatory questions | 12 |
| Phase 9 outcome access | なし |
| 正式なPhase 9データ取得 | 未開始 |
| Provider acquisition | S1B Run 33374751888は116 JAR SHA検証成功・native分類誤検出でfail-closed。修正後再Run待ち。実取得はGate B/JNLP/full-QC/raw保管経路待ち |
| Discovery | 未開始 |
| MT5 EA | 禁止 |

旧tmp workflowによる境界事故が確認されています。`POLICY_INCIDENT_20260829.md`を参照してください。2022〜2026年は後続splitとしての有効性再監査が必要です。

公開endpoint取得は`PROVIDER_ACQUISITION_BLOCKER.md`の3件のP0により廃止しました。代わりに`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`で、公式認証JForex Tester API、4つの固定取得run、H1の一律2019年8月除外を結果未閲覧で凍結しています。Java class-origin guard preflight Run `33336895081`は19/19 tests、online 1回＋offline 2回のJAR SHA一致、930-file inventory一致、外部probeのexit 86拒否でSuccessです。実証範囲はpre-connect non-bootstrap self/adversarial testだけで、実際のJForex接続、JNI/native、child process、OS-level egress、full QCは未検証です。これは監査証跡であり取得許可ではありません。市場price fileはまだ0件です。

次のno-provider-secret/no-price段階は`S1B_RUNTIME_QC_PREFLIGHT.md`です。GitHub checkoutの一時token以外にDukascopy・市場資格情報は参照しません。Gate AはRun 5から固定した116-JAR manifestを使い、Maven/Javaを一切実行せず、各JARをSHA一致確認後にだけnative payload静的検査します。あわせてlocal synthetic JNLP parserとsynthetic Full-QC primitivesを検査します。shaded runnerはこのGateでは未検査で、成功しても実取得許可にはなりません。

S1B Run `33374751888`はworkflowとしてSuccessでしたが、Java `.class`とMach-Oの`CAFEBABE` magic衝突により28,088件を誤検出したためnative inventoryを無効としました。116 JARのSHA一致、price file 0、禁止期間accessなし、Outcome未計算は確認済みです。分類器とregression testを修正し、同RunのinventoryからGate B allowlistを作らず再Runします。

`HYPOTHESIS_PORTFOLIO.md`、`spec/*.draft.json`、`policy/hypothesis_stage_policy.json`は履歴であり、実行に使用しません。

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
| Provider acquisition | S1B Gate A Run 33376110507は116 JAR SHA検証・28 native entry静的棚卸しに成功。Gate B/JNLP/shaded runner/native load/OS egress/full-QC/raw保管経路待ちで実取得は未認可 |
| Discovery | 未開始 |
| MT5 EA | 禁止 |

旧tmp workflowによる境界事故が確認されています。`POLICY_INCIDENT_20260829.md`を参照してください。2022〜2026年は後続splitとしての有効性再監査が必要です。

公開endpoint取得は`PROVIDER_ACQUISITION_BLOCKER.md`の3件のP0により廃止しました。代わりに`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`で、公式認証JForex Tester API、4つの固定取得run、H1の一律2019年8月除外を結果未閲覧で凍結しています。Java class-origin guard preflight Run `33336895081`は19/19 tests、online 1回＋offline 2回のJAR SHA一致、930-file inventory一致、外部probeのexit 86拒否でSuccessです。実証範囲はpre-connect non-bootstrap self/adversarial testだけで、実際のJForex接続、JNI/native、child process、OS-level egress、full QCは未検証です。これは監査証跡であり取得許可ではありません。市場price fileはまだ0件です。

`S1B_RUNTIME_QC_PREFLIGHT.md`のGate AはRun #2で完了しました。GitHub checkoutの一時token以外にDukascopy・市場資格情報は参照せず、116-JAR manifest、local synthetic JNLP parser、synthetic Full-QC primitivesを検査済みです。次の単一作業は28 native entryを別commitのGate B exact-match allowlistとして凍結することです。Shaded runnerは未検査で、Gate B完了も実取得許可にはなりません。

S1B Run #1 `33374751888`はworkflowとしてSuccessでしたが、Java `.class`とMach-Oの`CAFEBABE` magic衝突により28,088件を誤検出したためnative inventoryを無効としました。分類器とregression testを修正し、Run #2 `33376110507`で116 JARの全SHA一致、28 native entry、Java class衝突除外、metadata-only 9-file Artifactを確認しました。Artifact ZIP SHA-256は`ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a`です。Price file 0、禁止期間requestなし、Outcome未計算、取得認可falseのままです。正本監査は`results/s1b-run-33376110507/S1B_AUDIT.json`です。

次の単一作業は、Run #2の28 native entryを別commitのexact-match Gate B allowlistとして凍結することです。同一Runのinventoryを自己認可せず、Gate B完了だけで実取得を許可しません。Shaded runner、native load/mapped DSO、child process/OS egress、remote JNLP lock、streaming 48-series Full-QC、raw custodyがすべて別途未解決です。

`HYPOTHESIS_PORTFOLIO.md`、`spec/*.draft.json`、`policy/hypothesis_stage_policy.json`は履歴であり、実行に使用しません。

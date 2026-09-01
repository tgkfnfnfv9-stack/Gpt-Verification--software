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
| Provider acquisition | Gate C1 Run 33451221995でexact shaded runner scan、JNA native load、15 executable mapping、child processなし、外部network I/O成功なしを確認し、別commitのGate C2 exact runtime allowlistへ凍結。Full acquirer closure、取得時egress、remote JNLP、full-QC、raw保管経路待ちで実取得は未認可 |
| Discovery | 未開始 |
| MT5 EA | 禁止 |

旧tmp workflowによる境界事故が確認されています。`POLICY_INCIDENT_20260829.md`を参照してください。2022〜2026年は後続splitとしての有効性再監査が必要です。

公開endpoint取得は`PROVIDER_ACQUISITION_BLOCKER.md`の3件のP0により廃止しました。代わりに`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`で、公式認証JForex Tester API、4つの固定取得run、H1の一律2019年8月除外を結果未閲覧で凍結しています。Java class-origin guard preflight Run `33336895081`は19/19 tests、online 1回＋offline 2回のJAR SHA一致、930-file inventory一致、外部probeのexit 86拒否でSuccessです。実証範囲はpre-connect non-bootstrap self/adversarial testだけで、実際のJForex接続、JNI/native、child process、OS-level egress、full QCは未検証です。これは監査証跡であり取得許可ではありません。市場price fileはまだ0件です。

Provider schedule source P0に対して、`JFOREX_METADATA_ONLY_CONNECTION_AMENDMENT.md`と`spec/metadata_only_jforex_schedule_gate.frozen.json`は、将来のoffline-domain metadata観測境界を2026-09-01に別途凍結しました。現workflowはno-secret/no-JNLP/no-JForex/no-networkの静的preflightだけで、connection dispatchは未認可です。公式APIのweekend intervalだけではholiday、maintenance、Energy session、schedule versionの完全性を証明できないため、24-file inventoryとallowlistは未作成、取得認可はfalseのままです。

`S1B_RUNTIME_QC_PREFLIGHT.md`のGate AはRun #2で完了しました。GitHub checkoutの一時token以外にDukascopy・市場資格情報は参照せず、116-JAR manifest、local synthetic JNLP parser、synthetic Full-QC primitivesを検査済みです。Gate Bは`data_manifest/native_entry_allowlist.run33376110507.json`へ別commitで凍結し、`runner/verify_phase9_gate_b.py`が保存済みRun 2 evidenceとの完全一致をfail-closedで検証します。Shaded runnerは未検査で、Gate B完了も実取得許可にはなりません。

S1B Run #1 `33374751888`はworkflowとしてSuccessでしたが、Java `.class`とMach-Oの`CAFEBABE` magic衝突により28,088件を誤検出したためnative inventoryを無効としました。分類器とregression testを修正し、Run #2 `33376110507`で116 JARの全SHA一致、28 native entry、Java class衝突除外、metadata-only 9-file Artifactを確認しました。Artifact ZIP SHA-256は`ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a`です。Price file 0、禁止期間requestなし、Outcome未計算、取得認可falseのままです。正本監査は`results/s1b-run-33376110507/S1B_AUDIT.json`です。

Gate B監査正本は`results/gate-b-native-allowlist/GATE_B_AUDIT.json`です。Run ID、head SHA、116-JAR manifest SHA、Artifact ZIP SHA、2 archiveと28 entryのpath/SHA/size/magic/OS/archを固定し、未知・追加・欠落・重複・case collisionを拒否します。同一Runのinventoryによる自己認可は行っておらず、`acquisition_authorized=false`です。

Gate C1 Run `33451221995`（Job `99681326258`、head `9699c64b9133482caf22cef07dc9b3bc2fe33a1a`、Artifact `9779840519`、ZIP SHA-256 `d5ea84805732209e85340376de98788f897eba411a3170b300600767252d60f0`）はsuccessです。Artifact 18 filesとmanifest 17 payload hashを独立再検証し、exact shaded runner SHA、JNA load、15 executable mapping、子プロセス0、外部network I/O成功0、price file 0、Outcome空を確認しました。別commitの`data_manifest/runtime_mapping_allowlist.run33451221995.json`と`runner/verify_phase9_gate_c2.py`がpath scope/path/SHA/size/OS/arch、inert syscall type/protocol/countを完全一致で凍結します。Gate C2は取得を認可せず、full acquirer runtime closure、取得時child-process/egress enforcement、remote JNLP lock、streaming 48-series Full-QC、raw custodyが未解決です。

`HYPOTHESIS_PORTFOLIO.md`、`spec/*.draft.json`、`policy/hypothesis_stage_policy.json`は履歴であり、実行に使用しません。

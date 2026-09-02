# Phase 9 Hypothesis Redesign

更新日: 2026-09-02
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

初期JNLP identity Run `33500446289`で観測済みかつ未要求だった
`https://platform.dukascopy.com/demo_3/libs_3.jnlp`について、
`JFOREX_REMOTE_LIBS_JNLP_OBSERVATION_AMENDMENT.md`と
`spec/remote_libs_jnlp_observation_gate.frozen.json`に1回限りの
identity-only Gateを固定しました。Workflowは
`.github/workflows/phase9-remote-libs-jnlp-observation.yml`で、完全一致の
手動確認が別承認になります。資格情報、JForex接続、resource/JAR取得・実行、
schedule、availability、価格、Count-only、Outcomeへの認可効果はありません。

V1 workflow Run `33574659277`はoffline static verificationに混入した
literal `+`で通信前に失敗し、DNS/TCP/HTTP requestは0回でした。Run
`33575321670`はsingle-use条件でskippedです。V1認可は消費済みで再実行せず、
`JFOREX_REMOTE_LIBS_JNLP_OBSERVATION_REAUTHORIZATION_V2.md`、
`spec/remote_libs_jnlp_observation_gate_v2.frozen.json`、
`.github/workflows/phase9-remote-libs-jnlp-observation-v2.yml`に新しい完全一致
手動承認を必要とする修正版V2を固定しました。V2もprice、Count-only、Outcomeを
一切扱いません。

V2 Run `33577505327`はsuccessです。exact `libs_3.jnlp`へのHTTP GETは1回、
responseは200・2,484 bytesで、`libs.jnlp` 1件とJAR 35件の計36 identityを
観測しました。36件すべて`fetched=false`で、資格情報、JForex接続、schedule、
availability、price、Count-only、Outcomeは未実行です。Artifact `9827163991`
（ZIP SHA-256 `1611851b165cf126c4feaecf1789f913c556cfdd2bc7f8501c45c13ad352d548`）を
独立検証し、`results/remote-libs-jnlp-run-33577505327/`へ監査証拠、
`spec/remote_libs_jnlp_observed_url_allowlist.frozen.json`へ36 exact identityを
request未認可のevidence-onlyとして凍結しました。

ただし観測runtimeはclient `3.6.48` / API `2.13.98`で、正式channelに凍結した
`3.6.51` / `2.13.99`とは一致しません。古い36 resourceの取得は研究を前進させず
version混在を生むため停止しました。判断は
`REMOTE_RUNTIME_VERSION_DECISION_20260902.md`に固定しています。探索側では、QC済み
FXCM 64系列を再利用する価格のみの新規MTF仮説4件を結果未閲覧で事前登録し、
Count-only専用Gateを実装しました。通過候補だけを別Return/OOS Gateへ進めます。

Blind MTF Count-only Run `33580789080`はsuccessで、302（455 episodes）と304
（494 episodes）がfrequency PASS、301と303はFAILでした。Artifactは独立監査済みで、
このRunではReturn/Outcome未計算、価格保存0です。302/304だけを対象とする
spread込み12時間固定Return、2017 IS / 2018 OOSの別Gateを結果閲覧前に凍結しました。

Return/OOS Run `33582968006`はsuccessですが、302はIS負かつOOS bootstrap下限負、
304はIS/OOSとも負で、edge PASSは0件でした。両候補は不採用とし、結果後の閾値・
方向・銘柄・exit調整による救済は行いません。次は新しい独立MTF仮説batchへ進みます。

独立batch 2として305〜308をV2 Count前に事前登録し、Returnを扱わない専用
Count-only workflowを実装しました。通過候補が出ても、後続Returnでは過去2候補を
含む累積多重検定補正を行います。

Batch 2 Count-only Run `33585508306`はsuccess。305が441 episodesで唯一PASSし、
306〜308は件数Gate未達で不採用です。305のReturn閲覧前に専用Return/OOS仕様を固定し、
過去302/304を含む累積3候補Bonferroni補正済みmanual Gateを実装しました。

Recovery Run `33587536789`で305のReturn/OOSを完了しました。2017 IS mean R -0.1629、
2018 OOS mean R -0.3254、OOS PF 0.7471で不採用です。302/304/305は全件不採用で、
確認済みedge候補は0件です。結果後の条件変更による救済は行いません。

Batch 3では311/312がCount通過後のReturn/OOSでともに不採用となり、Outcome検定済み
302/304/305/311/312は全件不採用です。Batch 4 Count-only Run `33597873310`では
316だけが1018 episodesでPASSし、313〜315は不採用です。316のReturn閲覧前に、
2017 IS / 2018 OOS、spread込み12時間固定return、累積6候補Bonferroniの専用Gateを
凍結しました。次はそのsingle-use manual workflowを1回だけ実行します。

Batch 4 Return/OOS Run `33604445976`では316も不採用となりました。2017 IS mean Rは
-0.0729、2018 OOS mean Rは+0.0260ですが、補正後bootstrap下限-0.1522、PF 1.0305で、
事前固定した全条件を満たしません。Outcome検定済み6候補は全件不採用です。316を救済せず、
独立mechanism 317〜320をBatch 5 Count閲覧前に事前登録し、Count-only Gateを実装しました。

Batch 5 Count-only Run `33607154053`はsuccessです。317=759、318=148、319=948、
320=664 episodesで、319だけが固定frequency Gateを通過しました。このRunではReturn、
勝敗、PF、P値、Outcomeを計算・表示せず、価格も保存していません。317/318/320は救済せず、
319専用の2017 IS / 2018 OOS、spread込み12時間固定return、累積7候補Bonferroni契約を
Return閲覧前に凍結し、そのsingle-use manual workflowを実行しました。

Batch 5 Return/OOS Run `33610462879`では319も不採用となりました。2017 IS mean R
-0.0750、2018 OOS mean R -0.1259、OOS PF 0.8780、補正後bootstrap下限-0.4417で、
固定GateのOOS最低件数以外を通過していません。追加Run #2はskipされ、研究効果0です。
Outcome検定済み7候補は全件不採用、確認済みedgeは0件です。319を救済せず、独立mechanism
321〜324をBatch 6 Count閲覧前に事前登録し、Count-only Gateを実装しました。

Local M1は`runner/jforex-metadata`、`spec/metadata_owned_method_allowlist.frozen.json`、uplinkなしの独立client/server namespace＋exact `/32` host route＋Landlock/seccomp、専用private custodyとして実装しました。専用moduleは既存price acquirerを物理的に含まず、凍結local synthetic API fixtureでowned bytecodeのDukascopy method referenceをexact-matchします。これは実JForex API 2.13.99 JAR/runtime互換性の証明ではなく、その検証は残Blockerです。初期remote JNLP identity観測はRun `33500446289`、libs JNLP identity観測はRun `33577505327`で完了・独立監査済みで、両URLの再実行は禁止されています。Formal価格・schedule inventory・Outcomeは引き続き0/未計算です。

`S1B_RUNTIME_QC_PREFLIGHT.md`のGate AはRun #2で完了しました。GitHub checkoutの一時token以外にDukascopy・市場資格情報は参照せず、116-JAR manifest、local synthetic JNLP parser、synthetic Full-QC primitivesを検査済みです。Gate Bは`data_manifest/native_entry_allowlist.run33376110507.json`へ別commitで凍結し、`runner/verify_phase9_gate_b.py`が保存済みRun 2 evidenceとの完全一致をfail-closedで検証します。Shaded runnerは未検査で、Gate B完了も実取得許可にはなりません。

S1B Run #1 `33374751888`はworkflowとしてSuccessでしたが、Java `.class`とMach-Oの`CAFEBABE` magic衝突により28,088件を誤検出したためnative inventoryを無効としました。分類器とregression testを修正し、Run #2 `33376110507`で116 JARの全SHA一致、28 native entry、Java class衝突除外、metadata-only 9-file Artifactを確認しました。Artifact ZIP SHA-256は`ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a`です。Price file 0、禁止期間requestなし、Outcome未計算、取得認可falseのままです。正本監査は`results/s1b-run-33376110507/S1B_AUDIT.json`です。

Gate B監査正本は`results/gate-b-native-allowlist/GATE_B_AUDIT.json`です。Run ID、head SHA、116-JAR manifest SHA、Artifact ZIP SHA、2 archiveと28 entryのpath/SHA/size/magic/OS/archを固定し、未知・追加・欠落・重複・case collisionを拒否します。同一Runのinventoryによる自己認可は行っておらず、`acquisition_authorized=false`です。

Gate C1 Run `33451221995`（Job `99681326258`、head `9699c64b9133482caf22cef07dc9b3bc2fe33a1a`、Artifact `9779840519`、ZIP SHA-256 `d5ea84805732209e85340376de98788f897eba411a3170b300600767252d60f0`）はsuccessです。Artifact 18 filesとmanifest 17 payload hashを独立再検証し、exact shaded runner SHA、JNA load、15 executable mapping、子プロセス0、外部network I/O成功0、price file 0、Outcome空を確認しました。別commitの`data_manifest/runtime_mapping_allowlist.run33451221995.json`と`runner/verify_phase9_gate_c2.py`がpath scope/path/SHA/size/OS/arch、inert syscall type/protocol/countを完全一致で凍結します。Gate C2は取得を認可せず、full acquirer runtime closure、取得時child-process/egress enforcement、remote JNLP lock、streaming 48-series Full-QC、raw custodyが未解決です。

`HYPOTHESIS_PORTFOLIO.md`、`spec/*.draft.json`、`policy/hypothesis_stage_policy.json`は履歴であり、実行に使用しません。

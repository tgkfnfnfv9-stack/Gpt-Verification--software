# Phase 9 Exploratory FXCM Fast Track

Status: `DRIVE_VAULT_V2_OPTION1_ENVIRONMENT_CONFIGURED_NOT_EXECUTED; V1_PERMANENTLY_BLOCKED; LEGACY_FX8_BATCH6_PAUSED`

## Current canonical next step: reusable Google Drive Vault

2026-09-02、ユーザーはAvailability Run `33627420903`で確認できたFXCM範囲を使う
Option 1を選択した。V2は2012～2025年、25通貨ペア、direct m1/H1の700 shardとする。
36,400 endpoint identityのうち、HEADで存在を確認したexact 36,000件だけを取得allowlistとし、
既知404の400件をversioned maskへ固定した。既知欠損は要求せず、補完・補間しない。
凍結present identityが取得時に欠けた場合は失敗し、root sealを作らない。

- V2契約正本: `spec/fxcm_drive_vault_*_v2.frozen.json`
- V2 Drive root: `1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v`（同一OAuth clientで作成、価格取得前は空）
- exact availability mask: `spec/fxcm_drive_vault_availability_mask_v2.frozen.json`
- 一括取得: `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2.yml`
- direct: m1/H1 BID/ASK OHLC、提供時だけVolume
- strategy canonical: M1由来M5/M15/M30/H1/H4/D1/W1
- direct H1: QC参照のみ、補完・代替禁止
- partition: Development 2012～2019、Strict OOS 2020～2021、Robustness 2022～2023、Final holdout 2024～2025
- OAuth client、refresh token、同一client作成root: 設定済み（secret値はGitに保存しない）
- GitHub Environment、required reviewer、OAuth 3 secrets: 設定済み（値はチャット・Git・Artifactへ非公開）
- 価格取得、V2 workflow、Count、Batch 6: 未実行
- V1 acquisition workflow: fail-closedで恒久停止
- V2専用11 tests、探索track全174 tests: 成功
- V2 acquisition workflowのpreflightは、app-created root反映後の取得契約SHA-256と同期済み

V2を公開しても実行許可にはならない。別のユーザー明示承認まではV2 workflowを実行しない。
取得後も自動でCountへ進まず、private Drive custodyと旧64系列互換性を独立監査する。

## Historical V1 availability result

候補ごとに2017～2018年を再取得して破棄する運用は終了した。G8全28通貨ペアの
2010～2025年を一度だけ取得し、年×銘柄×direct periodicityの1,344 shardとして
private Google Driveへ保存し、以後は同じSHA-256データを再利用するV1を実装済みである。

- 契約正本: `spec/fxcm_drive_vault_*_v1.frozen.json`
- Availability: `.github/workflows/phase9-exploratory-fxcm-drive-vault-availability-v1.yml`
- 一括取得: `.github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml`
- direct: m1/H1/D1 BID/ASK OHLC、提供時だけVolume
- strategy canonical: M1由来M5/M15/M30/H1/H4/D1/W1
- direct H1/D1: QC参照のみ、補完・代替禁止
- Drive folder ID: `1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu`
- public Git/Artifactの価格: 0件を維持

Availability Run `33627420903`は16年すべて成功し、16 Artifactを独立監査した。
要求69,888 source objectのうち36,000件だけがHTTP 200、33,888件が404だった。
2010・2011年は全件なし、direct D1は全件なし、`CHFJPY`・`EURCAD`・`GBPAUD`は
全期間なしである。response body読取りは0 byte、価格取得も0件である。

正本監査は
`results/run-33627420903/FXCM_DRIVE_VAULT_AVAILABILITY_INDEPENDENT_AUDIT.json`。
凍結V1 targetは成立しないため、一括取得workflowを実行してはならない。対象を黙って
縮小せず、新しいsourceまたは明示承認された別V2 scopeを決めるまで停止する。
321～324と既存Batch 6も未実行のまま維持する。

以下のH1/MTF/Batch履歴は完了済みの旧探索経路として保持する。

This track makes a real, provider-authorized data path executable without
pretending that it completes Formal Phase 9.

- Source: FXCM official `fxcm/MarketData` CandleData endpoint
- Pinned source repository head: `924393dd545fab187527d95ef8b1178284b274b6`
- Instruments: Formal FX 8 only
- Source bars: direct H1 Bid/Ask OHLC
- Period: 2017-01-01 through 2018-12-31 exclusive
- Persistent output: bounded QC/inventory metadata only

FXCM's official README publishes the URL template, 2017--2020 coverage and
Python download examples. The selected years are inside Formal Phase 9's outer
allowed interval. Raw files, canonical prices and full observed-timestamp lists
remain in `RUNNER_TEMP` and are deleted after same-run integrity QC.

This is partial exploratory infrastructure. It has no Formal authorization
effect and does not satisfy the missing XAUUSD, XAGUSD, Brent or WTI inputs,
M15 input, provider schedule, Energy roll metadata, Count-only Gate or Full-QC.
Observed timestamps are not an independent provider schedule.

No signals or outcomes are calculated. Returns, return signs, MFE, MAE, edge,
wins, win rate, Profit Factor, drawdown, cumulative R, p-values, confidence
intervals, rankings and outcome charts are absent by construction.

## QC amendment after the first real run

Run `33477252915` at head `70593000cee5fd113719722fef25505b395df87e`
downloaded the frozen 832 weekly source files, then failed on the first observed
`ASK Open < BID Open` record. Cleanup succeeded and no Artifact was uploaded.
The price-free audit is recorded under `results/run-33477252915/`.

Contract v1.1.0 is a prospective retry amendment. It does not retroactively
validate the failed run. It preserves the exact crossed-open predicate, does
not add a tolerance or change any price, and quarantines both sides of each
crossed row from the ephemeral usable series. Only per-symbol counts and
SHA-256 identities are retained in the price-free inventory. Any nonzero count
keeps Formal Full-QC, Count-only and all outcome work blocked.

## Operational amendments after Runs 2 and 3

Run `33479424685` completed acquisition and QC, but its Artifact manifest
incorrectly included a self-hash captured while the manifest was still empty.
The inventory payload passed independent audit, but that Artifact is not
canonical. Commit `5e97795b0d74e55f87278e01af1668089ad7edf7` changed the
manifest convention to one payload-only line and added a regression test.

Run `33481035804` at that head passed all 13 tests, then stopped during source
download after the remote connection was reset. No Artifact was uploaded and
working-price cleanup succeeded. The prospective V3 operational amendment
retries only transient transport failures, at most four attempts with fixed
1, 2 and 4 second waits. HTTP status, redirect, size, gzip, schema and all QC
failures remain immediately fail-closed. The URL set, period, symbols,
timeframe, provider contract and outcome prohibitions are unchanged.

## Canonical exploratory inventory

Run `33482595275` at head `b2eaf84e774f9ce1272344f71ac14afcb0f6849a`
completed all workflow steps. Artifact `9790552032` was independently checked
against its GitHub digest, exact two-file allowlist, payload-only manifest,
contract, 832 source identities, per-symbol inventories and aggregate hashes.
The exact price-free Artifact payload and its separate canonical allowlist are
stored under `results/run-33482595275/`.

This is canonical only for the exploratory FX8 H1 source/QC inventory. It is
not an independent provider schedule, not Formal Phase 9 price custody, and
does not authorize acquisition, Count-only, signals or outcomes.

## Multi-timeframe next step

H1だけではマルチタイムフレーム研究に不足するため、次の取得要件を
`spec/fxcm_multitimeframe_data_requirements.frozen.json`へ凍結した。詳細と
引継ぎは`MULTI_TIMEFRAME_DATA_PLAN.md`を正本とする。

- direct m1から完全15本bucketでM15を生成
- direct H1をH1正本として使用
- direct H1から完全4本bucketでH4を生成
- direct H1から完全24本bucketでD1を生成
- 8銘柄 × M15/H1/H4/D1 × BID/ASK = 64最終系列
- m1由来H1はdirect H1とのQC照合だけに使用
- 不完全bucketは補完せずdrop/count
- VolumeはFXCM無料CandleDataにないため、volume仮説には使用不可

次のRunは取得・集約・QCだけに限定する。Count-only、signal、Return、
Outcomeは自動的に続けない。金銀・EnergyはFXCM無料CandleDataの範囲外
なので、FX8 MTF trackと混ぜず、別provider/別trackで扱う。

## Blind MTF Count-only V1

既存7候補はFX8 subsetのCount-onlyでReturn Gate通過0件だった。Returnや
Outcomeは一度も計算していない。この状態で、既存候補の閾値を調整せず、
価格だけで成立する新しい独立MTF仮説4件を
`spec/fxcm_blind_mtf_candidates_v1.frozen.json`へ結果未閲覧で事前登録した。

- `EXP-P9-MTF-301`: Asia range break-retest + H4 bias
- `EXP-P9-MTF-302`: H4 liquidity sweep + H1 midpoint rejection
- `EXP-P9-MTF-303`: D1 inside compression + H4 expansion
- `EXP-P9-MTF-304`: D1/H4 alignment + H1 impulse continuation

`.github/workflows/phase9-exploratory-fxcm-blind-mtf-count-only.yml`は、既存の
canonical 64-series identityに一致するデータを一時領域へ再取得し、4候補の
signal/episode件数、期間・銘柄・方向の分布だけを計算する。価格はArtifact前に
破棄する。Return、勝敗、MFE、MAE、Edge、P値、順位、Outcomeは計算しない。
frequency Gate通過候補だけが、後続の別Return/OOS Gate対象になる。

## Blind MTF Count-only Run 33580789080

Run #1 / attempt #1は全step success。Artifact `9828546981`（ZIP SHA-256
`8f597982ac8a879f4c40781665fe12a289733f0ee162bdd486d424b0bed0b1a0`）を
独立検証し、exact 2 files、manifest一致、価格ファイル0、Return/Outcome未計算を
確認した。primary episode件数とfrequency Gateは次のとおり。

| Candidate | Episodes | Active dates | Frequency Gate |
|---|---:|---:|---|
| EXP-P9-MTF-301 | 166 | 153 | FAIL |
| EXP-P9-MTF-302 | 455 | 364 | PASS |
| EXP-P9-MTF-303 | 92 | 89 | FAIL |
| EXP-P9-MTF-304 | 494 | 394 | PASS |

次の別Gateは`EXP-P9-MTF-302`と`EXP-P9-MTF-304`だけを評価する。契約は
`spec/fxcm_blind_mtf_return_oos_v1.frozen.json`へReturn閲覧前に固定した。

- entry: signalで固定済みの次H1 bar open
- LONG: ASK entry / BID exit、SHORT: BID entry / ASK exit
- exit: entryから正確に12時間後のH1 open
- return: executable price差 ÷ entry前H1 ATR14
- split: 2017 IS / 2018 OOS（entry UTC year）
- inference: UTC entry date cluster bootstrap 20,000回
- multiplicity: 2候補Bonferroni、one-sided alpha 0.025 each
- Artifact: summaryのみ。trade row、価格、signal/entry timestampは保存しない

OOS件数、completion、IS/OOS平均、bootstrap lower bound、Profit Factor、
銘柄breadth、四半期breadthの全条件を満たした候補だけが次の新期間確認対象になる。

## Blind MTF Return/OOS Run 33582968006

Run #1 / attempt #1は全step success。Artifact `9829327227`（ZIP SHA-256
`1b91f15f868aaaac845f39b7949a1aea8c776bdddc1242adf01023e9bfae7e33`）を
独立検証し、exact 2 files、manifest一致、価格・trade row・timestamp保存0を確認した。

| Candidate | 2017 mean R | 2018 OOS mean R | OOS PF | Bootstrap lower | Decision |
|---|---:|---:|---:|---:|---|
| EXP-P9-MTF-302 | -0.1384 | 0.0904 | 1.1100 | -0.2371 | REJECT |
| EXP-P9-MTF-304 | -0.1230 | -0.1054 | 0.9120 | -0.4688 | REJECT |

302はOOS平均だけが正でもIS、bootstrap、銘柄breadth、四半期breadthを通らず、
304はIS/OOSとも負。edge PASSは0件。閾値、方向、銘柄、exit horizonを結果後に
調整せず、両候補を不採用とする。次は302/304のrescueではなく、新しい独立仮説を
結果を見る前に別specへ事前登録する。

## Blind MTF Batch 2 Count-only

302/304の不採用確定後、新しい価格のみの独立MTF仮説4件を
`spec/fxcm_blind_mtf_candidates_v2.frozen.json`へ最初のV2 Count前に固定した。

- `EXP-P9-MTF-305`: D1 bias + H4 NR7 compression + H1 release
- `EXP-P9-MTF-306`: D1 three-bar pullback + H4 trend resumption
- `EXP-P9-MTF-307`: H4 double rejection + H1 neckline break
- `EXP-P9-MTF-308`: H4 trend + H1 volatility shock + M15 shallow-pullback continuation

これは302/304のthreshold、direction、symbol、exit horizonの救済ではない。
専用workflowは件数・breadth・年coverageだけを計算し、Return/Outcomeは計算しない。
frequency PASSが出た場合の後続Return Gateは、すでにOutcomeを検定した2候補も含む
cumulative multiplicity correctionを必須とする。

### Batch 2 Count-only Run 33585508306

Run #1 / attempt #1は全step success。Artifact `9830183542`（ZIP SHA-256
`82c450636f6ab27d773df7b1106e42d5933123c5b4948842586a3358127ee82a`）を
独立検証し、exact 2 files、manifest一致、価格・Return・Outcome保存0を確認した。

| Candidate | Episodes | Active dates | Count decision |
|---|---:|---:|---|
| EXP-P9-MTF-305 | 441 | 355 | PASS |
| EXP-P9-MTF-306 | 51 | 51 | REJECT |
| EXP-P9-MTF-307 | 52 | 51 | REJECT |
| EXP-P9-MTF-308 | 260 | 226 | REJECT |

305だけを次のReturn/OOS Gateへ送る。306〜308のthreshold、direction、symbol、
exit horizonを結果後に変更して救済しない。

## Blind MTF Batch 2 Return/OOS Gate

305のReturn閲覧前に`spec/fxcm_blind_mtf_batch2_return_oos_v1.frozen.json`を固定した。
実行定義はH1次バーopen、12時間固定、LONGはASK→BID、SHORTはBID→ASK、
H1 mid ATR14正規化、2017 IS / 2018 OOS。date-cluster bootstrapは20,000回。
過去にOutcomeを検定した302/304を含む累積3候補へBonferroni補正し、片側alphaを
`0.016666666666666666`へ固定した。専用manual workflowはRun #1 / attempt #1のみ許可する。

### Return/OOS pre-outcome cancellation recovery

初回workflowは同時刻に2回dispatchされた。Run `33587087527` #1はcheckout中にcancel、
Run `33587087557` #2はsingle-use guardでskip。両Runとも取得、signal rebuild、Return、
Outcome、artifact生成は未開始であることを独立監査した。統計・signal・exit仕様は変更せず、
pending Run #1をduplicateが置換しない専用recovery workflowへ移行する。

### Batch 2 Return/OOS Recovery Run 33587536789

Run #1 / attempt #1は全step success。Artifact `9830865694`（ZIP SHA-256
`f5d3e7234ed7c438ace9d83c414701aff7c5b92cae57957d316946d70f4d359c`）を
独立検証し、exact 2 files、manifest一致、価格・trade row・timestamp保存0を確認した。

| Candidate | 2017 mean R | 2018 OOS mean R | OOS PF | Bootstrap lower | Decision |
|---|---:|---:|---:|---:|---|
| EXP-P9-MTF-305 | -0.1629 | -0.3254 | 0.7471 | -0.7277 | REJECT |

305はIS/OOSとも負で、OOSの全四半期平均も負。累積3候補補正後のbootstrap下限も負。
threshold、direction、symbol、exit horizonを変更せず不採用とする。現在の探索的
Outcome検定済み候補302/304/305は全件不採用、確認済みedge候補は0件。

## Blind MTF Batch 3 Count-only Preregistration

302/304/305を救済せず、301〜308とmechanismが重複しない4件を、最初のBatch 3
Count閲覧前に`spec/fxcm_blind_mtf_candidates_v3.frozen.json`へ凍結した。

- `EXP-P9-MTF-309`: D1 overextension → H4 exhaustion → H1 recapture
- `EXP-P9-MTF-310`: H4 accepted breakout → structural failure → M15 reversal
- `EXP-P9-MTF-311`: fixed 13:00 UTC London–New York overlap impulse
- `EXP-P9-MTF-312`: target-excluded synchronized cross-pair currency breadth

`runner/fxcm_blind_mtf_count_only_v3.py`と
`.github/workflows/phase9-exploratory-fxcm-blind-mtf-batch3-count-only.yml`は、
件数、active UTC dates、銘柄・方向・年coverage、identity SHAだけを計算する。
Return、MFE、MAE、勝敗、PF、Drawdown、P値、信頼区間、順位、Outcomeは計算・保存しない。
価格は同一RunのArtifact upload前に破棄し、Artifactは価格を含まない2ファイルだけとする。

Count Gate通過候補がある場合だけ、別CommitでReturn/OOS契約を凍結する。その推測統計は
Outcome検定済みの302/304/305とBatch 3通過候補を合わせた累積候補数で多重検定補正する。
Count不通過候補のthreshold、direction、symbol、timeframe、exitは変更せず不採用とする。

### Batch 3 Count-only Run 33591731464

Run #1 / attempt #1は全step success。Artifact `9832271295`（ZIP SHA-256
`d518961c48852a450c587dde85ab4f62f288408c35bfddc1764126baae9ae068`）を
独立検証し、exact 2 files、manifest一致、価格・Return・Outcome保存0を確認した。

| Candidate | Episodes | Active dates | Count decision |
|---|---:|---:|---|
| EXP-P9-MTF-309 | 22 | 20 | REJECT |
| EXP-P9-MTF-310 | 157 | 148 | REJECT |
| EXP-P9-MTF-311 | 280 | 237 | PASS |
| EXP-P9-MTF-312 | 1028 | 516 | PASS |

311と312だけを次のReturn/OOS Gateへ送る。309と310は条件変更による救済を行わない。

## Blind MTF Batch 3 Return/OOS Gate

311/312のReturn閲覧前に`spec/fxcm_blind_mtf_batch3_return_oos_v1.frozen.json`を
固定した。H1次バーopenから12時間後のH1 openまでを、LONG ASK→BID、SHORT
BID→ASKで評価し、entry前H1 mid ATR14で正規化する。2017 IS / 2018 OOS、
UTC entry-date cluster bootstrap 20,000回を使用する。過去にOutcomeを検定した
302/304/305を含む累積5候補にBonferroni補正し、片側alphaは`0.01`である。

OOS最低120件、completion 95%以上、IS/OOS平均正、99% bootstrap下限正、
OOS PF 1.05以上、正のOOS銘柄5以上、正のOOS四半期3以上をすべて要求する。
専用manual workflowはRun #1 / attempt #1のみ許可し、Artifactは価格・trade row・
timestampを含まないsummary 2ファイルだけとする。結果通過時もMT5へ直行せず、
別の新期間・頑健性Gateを必須とする。

### Batch 4 Return/OOS Run 33604445976

Run #1 / attempt #1は全step success。Artifact `9836839336`（ZIP SHA-256
`4dd014a48132c69c55d4e7236d9f719dbc76cb09ace1799de03bd8155f2fdbc2`）を
独立検証し、exact 2 files、manifest一致、価格・trade row・timestamp保存0を確認した。
追加dispatch Run `33604446632`（#2）はsingle-use guardでskip、Artifact 0である。

| Candidate | Completed | 2017 mean R | 2018 OOS mean R | OOS PF | Bootstrap lower | Decision |
|---|---:|---:|---:|---:|---:|---|
| EXP-P9-MTF-316 | 951/1018 | -0.0729 | 0.0260 | 1.0305 | -0.1522 | REJECT |

316はOOS平均と四半期breadthだけを通過したが、completion、IS平均、補正後bootstrap下限、
PF、銘柄breadthを通過しなかった。閾値・方向・銘柄・timeframe・exitを変更せず不採用。
Outcome検定済み6候補は全件不採用で、確認済みedgeは0件である。

## Blind MTF Batch 5 Count-only Preregistration

301〜316を救済せず、次の独立mechanismを最初のBatch 5 Count閲覧前に
`spec/fxcm_blind_mtf_candidates_v5.frozen.json`へ固定した。

- `EXP-P9-MTF-317`: Asia session range → London breakout persistence
- `EXP-P9-MTF-318`: expanded D1 bar extreme-close persistence
- `EXP-P9-MTF-319`: H1 upside/downside realized semivariance imbalance reversion
- `EXP-P9-MTF-320`: fixed-time daily cross-sectional dispersion convergence

専用workflowは件数・coverage・identityだけを計算する。Return、勝敗、PF、P値、信頼区間、
順位、Outcomeは計算・表示・保存しない。通過候補がある場合だけ、既にOutcomeを検定した
6候補を含む累積多重検定補正Return/OOS Gateを別途凍結する。

### Batch 5 Count-only Run 33607154053

Run #1 / attempt #1は全step success。Artifact `9837905049`（ZIP SHA-256
`43967420efba6bd9c8b036e6415db3f73c2e20ab13a41607cd3245dd7dee1c29`）を
独立検証し、exact 2 files、manifest一致、価格保存0、Return/Outcome未計算を確認した。

| Candidate | Episodes | Active dates | Count decision |
|---|---:|---:|---|
| EXP-P9-MTF-317 | 759 | 485 | REJECT |
| EXP-P9-MTF-318 | 148 | 127 | REJECT |
| EXP-P9-MTF-319 | 948 | 570 | PASS |
| EXP-P9-MTF-320 | 664 | 332 | REJECT |

317と320は銘柄集中、318は最低件数と銘柄breadthを通過しなかった。閾値、方向、銘柄、
timeframe、exitを変更せず不採用とし、319だけを別Return/OOS Gateへ送る。

## Blind MTF Batch 5 Return/OOS Gate

319のReturn閲覧前に`spec/fxcm_blind_mtf_batch5_return_oos_v1.frozen.json`を固定した。
H1次バーopenから12時間後のH1 openまでを、LONG ASK→BID、SHORT BID→ASKで評価し、
entry前H1 mid ATR14で正規化する。2017 IS / 2018 OOS、UTC entry-date cluster
bootstrap 20,000回を使用する。過去にOutcomeを検定した302/304/305/311/312/316を
含む累積7候補にBonferroni補正し、片側alphaは`0.05 / 7`である。

OOS最低220件、completion 95%以上、IS/OOS平均正、99.2857% bootstrap下限正、
OOS PF 1.05以上、正のOOS銘柄5以上、正のOOS四半期3以上をすべて要求する。
専用manual workflowはRun #1 / attempt #1のみ許可し、Artifactは価格・trade row・
timestampを含まないsummary 2ファイルだけとする。通過時もMT5へ直行せず、
別の新期間・頑健性Gateを必須とする。

### Batch 5 Return/OOS Run 33610462879

Run #1 / attempt #1は全step success。Artifact `9839175222`（ZIP SHA-256
`ad314ba122d297c213ef96c09905ff3c9e3388dc4ef4712d8b3c7d8a586fe3d1`）を
独立検証し、exact 2 files、manifest一致、価格・trade row・timestamp保存0を確認した。
追加dispatch Run `33610463307`（#2）はsingle-use guardでskip、Artifact 0である。

| Candidate | Completed | 2017 mean R | 2018 OOS mean R | OOS PF | Bootstrap lower | Decision |
|---|---:|---:|---:|---:|---:|---|
| EXP-P9-MTF-319 | 879/948 | -0.0750 | -0.1259 | 0.8780 | -0.4417 | REJECT |

319はOOS最低件数だけを通過し、completion、IS/OOS平均、補正後bootstrap下限、PF、
銘柄breadth、四半期breadthを通過しなかった。条件変更をせず不採用とする。
Outcome検定済み7候補は全件不採用で、確認済みedgeは0件である。

## Blind MTF Batch 6 Count-only Preregistration

301〜320を救済せず、次の独立mechanismを最初のBatch 6 Count閲覧前に
`spec/fxcm_blind_mtf_candidates_v6.frozen.json`へ固定した。

- `EXP-P9-MTF-321`: H1 directional path-efficiency continuation
- `EXP-P9-MTF-322`: H1 same-sign return-run exhaustion reversal
- `EXP-P9-MTF-323`: turn-of-month prior-month momentum
- `EXP-P9-MTF-324`: Friday weekly-stretch position-squaring reversal

専用workflowは件数・coverage・identityだけを計算する。Return、勝敗、PF、P値、信頼区間、
順位、Outcomeは計算・表示・保存しない。通過候補がある場合だけ、既にOutcomeを検定した
7候補を含む累積多重検定補正Return/OOS Gateを別途凍結する。

## Google Drive Data Vault migration decision

ユーザー承認により、候補Batchごとに同じ期間を再取得して破棄する方式から、一度だけ
複数年データを取得し、非公開Google DriveへSHA固定shardとして保存・再利用する方式へ
移行する。設計正本は`GOOGLE_DRIVE_DATA_VAULT_PLAN.md`である。

- V2 Drive folder ID: `1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v`（同一OAuth clientで作成、価格取得前は空）
- V2 target period: 2012-01-01 inclusive ～ 2026-01-01 exclusive
- V2 universe: availability確認済み25通貨ペア
- V2 direct: m1/H1、BID/ASK OHLC、提供時Volume
- derived: M5/M15/M30/H1/H4/D1/W1
- exact identity: base 36,400、取得allowlist 36,000、既知欠損mask 400
- Tick、金銀、指数、原油、exotic FXは初期vault対象外
- OOS、robustness、final holdoutはGate前に読まない別区画
- public Git/Artifactへ価格を保存しない

AvailabilityはRun `33627420903`で完了したが、価格取得は未開始である。V1取得workflowは
恒久停止し、V2取得workflowも別の明示承認前には実行しない。既存Batch 6 workflowはvault
移行と独立監査が完了するまでdispatchしない。321〜324の事前登録条件は変更しない。

### Batch 3 Return/OOS Run 33593743345

Run #1 / attempt #1は全step success。Artifact `9832993158`（ZIP SHA-256
`c5f8c23b2a75b73d76b1584e20d489c08a977634e06c48fc60e42548404df453`）を
独立検証し、exact 2 files、manifest一致、価格・trade row・timestamp保存0を確認した。

| Candidate | Completed | 2017 mean R | 2018 OOS mean R | OOS PF | 99% bootstrap lower | Decision |
|---|---:|---:|---:|---:|---:|---|
| EXP-P9-MTF-311 | 234/280 | 0.2268 | -0.1859 | 0.7819 | -0.6039 | REJECT |
| EXP-P9-MTF-312 | 994/1028 | -0.0616 | -0.0021 | 0.9980 | -0.2578 | REJECT |

311はIS平均だけが正だが、completion、OOS平均、PF、bootstrap、銘柄・四半期breadthを
通らない。312はOOS平均がほぼゼロでも負で、IS平均、PF、bootstrap、銘柄breadthも
通らない。累積5候補補正後のedge PASSは0件。条件変更、方向反転、銘柄限定、exit変更を
行わず、両候補を不採用とする。

## Blind MTF Batch 4 Count-only Preregistration

301〜312を救済せず、次の独立mechanism 4件を最初のBatch 4 Count閲覧前に
`spec/fxcm_blind_mtf_candidates_v4.frozen.json`へ固定した。

- `EXP-P9-MTF-313`: weekend opening gap same-bar reversion
- `EXP-P9-MTF-314`: month-end fixing-window stretch reversal
- `EXP-P9-MTF-315`: Monday five-day cross-sectional relative momentum
- `EXP-P9-MTF-316`: synchronized triangular-parity dislocation reversion

専用workflowは件数、active dates、銘柄・方向・年coverage、identity SHAだけを計算する。
Return、勝敗、PF、P値、信頼区間、順位、Outcomeは計算・表示・保存しない。Count通過候補が
ある場合だけ別Return/OOS Gateを凍結し、既にOutcomeを検定した302/304/305/311/312を
含む累積候補数で多重検定補正する。

### Batch 4 Count-only Run 33597873310

Run #1 / attempt #1は全step success。Artifact `9834301243`（ZIP SHA-256
`db29def40b5110d5564ac7089a6e197a4c8a9b15437a0bdc021464aa084e7ebc`）を
独立検証し、exact 2 files、manifest一致、価格・Return・Outcome保存0を確認した。
誤って追加dispatchされたRun `33597873428`（#2）はsingle-use guardでskipされ、
job実行・Artifact・研究結果への影響はない。

| Candidate | Episodes | Active dates | Count decision |
|---|---:|---:|---|
| EXP-P9-MTF-313 | 147 | 97 | REJECT |
| EXP-P9-MTF-314 | 25 | 19 | REJECT |
| EXP-P9-MTF-315 | 174 | 87 | REJECT |
| EXP-P9-MTF-316 | 1018 | 510 | PASS |

316だけを次のReturn/OOS Gateへ送る。313〜315は閾値・方向・銘柄・timeframe・exitの
変更による救済を行わない。

## Blind MTF Batch 4 Return/OOS Gate

316のReturn閲覧前に`spec/fxcm_blind_mtf_batch4_return_oos_v1.frozen.json`を固定した。
H1次バーopenから12時間後のH1 openまでを、LONG ASK→BID、SHORT BID→ASKで評価し、
entry前H1 mid ATR14で正規化する。2017 IS / 2018 OOS、UTC entry-date cluster
bootstrap 20,000回を使用する。過去にOutcomeを検定した302/304/305/311/312を
含む累積6候補にBonferroni補正し、片側alphaは`0.008333333333333333`である。

OOS最低240件、completion 95%以上、IS/OOS平均正、99.1667% bootstrap下限正、
OOS PF 1.05以上、正のOOS銘柄5以上、正のOOS四半期3以上をすべて要求する。
専用manual workflowはRun #1 / attempt #1のみ許可し、Artifactは価格・trade row・
timestampを含まないsummary 2ファイルだけとする。通過時もMT5へ直行せず、
別の新期間・頑健性Gateを必須とする。

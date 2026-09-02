# Phase 9 Exploratory FXCM Fast Track

Status: `FX8_H1_ACQUISITION_QC_ONLY_NOT_FORMAL_PHASE9`

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

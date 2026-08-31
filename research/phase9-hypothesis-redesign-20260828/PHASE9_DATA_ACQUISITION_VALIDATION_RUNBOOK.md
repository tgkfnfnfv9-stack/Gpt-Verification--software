# Phase 9 データ取得・仮説検証 実行手順書

更新日: 2026-08-31
対象Repository: `tgkfnfnfv9-stack/Gpt-Verification--software`
対象Branch: `main`
S1B Run #2 head commit: `951c38aaa875180fa7dbbe498866a4e3ece50e9c`
現在status: `S1B_GATE_A_PASS_GATE_B_FROZEN_ACQUISITION_BLOCKED`

> 2026-08-30 amendment: 公開endpointと`dukascopy-go v0.2.0`の実行経路は廃止しました。この文書の旧版にあった同toolのコマンドや実行指示は有効ではありません。理由は`PROVIDER_ACQUISITION_BLOCKER.md`、代替正本は`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`です。

## 0. この文書の目的

このファイルだけで、別のChatGPT Workセッションが次を順番どおり実行できるようにする。

1. GitHubの正本確認
2. Phase 9専用データ取得Workflowの作成
3. 許可期間だけの市場データ取得
4. データ品質検査
5. Count-only Gate
6. 12確認項目のDiscovery検証
7. REJECT / DEVELOPMENT判定
8. 結果・manifest・引き継ぎのGitHub保存

この手順はFrozen Entry条件やGateを変更しない。数値仕様は必ずFrozen JSONを使用する。

---

# 1. 現在地

```text
正式検証済み
├─ STRAT-PA-002                  REJECT_FOR_DEVELOPMENT
└─ Phase 8候補15件              全件REJECT_FOR_DEVELOPMENT

Phase 9
├─ Formal alpha                 11件
├─ Risk overlay                  1件
├─ Confirmatory questions       12件
├─ 状態                          UNTESTED_PREREGISTERED
├─ 正式データ取得                未開始
├─ Phase 9 Return計算            0件
└─ MT5 EA                        禁止
```

Phase 9は仮説討論段階ではなく、事前登録済みである。旧Draftを使ってはいけない。

Phase 9専用JForex取得・境界QC基盤は実装済みだが、市場price fileは0件である。Build preflight Run `33336895081`で全Maven依存とrebuild JARのSHA、pre-connect class-origin guardを監査済み。S1B Gate A Run `33376110507`では、Run 5から固定した116個のJARをMaven/Javaを実行せず全SHA一致後に静的検査し、28 native entryとsynthetic Full-QC primitivesを記録した。28件はRun 2とは別commitのGate B exact-match allowlistへ固定し、保存済みevidenceと独立再取得した2 archiveのSHA/entry/OS/archを再検証済み。Shaded runnerその他のblockerは残り、Count-only RunnerとDiscovery Runnerはまだ作らない。

S1B Run #1 `33374751888`は116 JAR SHA検証に成功したが、Java `.class`の`CAFEBABE`をMach-Oとして28,088件誤検出したためnative inventoryを無効化した。分類器修正後のRun #2 `33376110507`は116 JAR全SHA一致、native 28件、class衝突除外で成功した。正本は`results/s1b-run-33376110507/S1B_AUDIT.json`。市場price、禁止期間、Outcomeへのaccessは0、取得認可はfalseである。

---

# 2. 正本として読むファイル

別セッションは作業前に以下を完全に読む。

1. `AGENTS.md`
2. `research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md`
3. `research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260829.md`
4. `research/phase9-hypothesis-redesign-20260828/PROVIDER_ACQUISITION_BLOCKER.md`
5. `research/phase9-hypothesis-redesign-20260828/JFOREX_SOURCE_CHANNEL_AMENDMENT.md`
6. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
7. `research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md`
8. `research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md`
9. `research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json`
10. `research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json`
11. `research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json`

優先順位は次のとおり。

```text
許可・禁止
policy/preregistered_research_policy.json
        ↓
数値Entry・Control・Gate
spec/candidate_registry.frozen.json
        ↓
取得期間・必要Field
spec/data_requirements.frozen.json
        ↓
運用方法
PHASE9_OPERATIONS_GUIDE.md
```

以下は履歴用であり、実行に使用しない。

- `HYPOTHESIS_PORTFOLIO.md`
- `spec/candidate_registry.draft.json`
- `spec/data_requirements.draft.json`
- `policy/hypothesis_stage_policy.json`

---

# 3. 取得できる期間

## 凍結取得期間

| Source | 開始（inclusive） | 終了（exclusive） |
|---|---|---|
| M15 BID/ASK、全12 | `2013-01-01T00:00:00Z` | `2019-08-28T00:00:00Z` |
| H1 BID/ASK、全12 | `2013-01-01T00:00:00Z` | `2019-08-01T00:00:00Z` |

H1の`[2019-08-01, 2019-08-28)`はユーザー指示により結果未閲覧で一律除外済み。後から取得、M15から生成、銘柄別復活をしない。H4/D1はcanonical H1からの派生だけなので、対象終了も`2019-08-01T00:00:00Z`未満である。

## 絶対に取得しない期間

- 2019-08-28以降
- Phase 8 Seen Period
- Development / Walk Forward
- Strict OOS
- Final Holdout

Availability照会、Download、Cache、Return計算のすべてを禁止する。

## 2019年8月などに欠損がある場合

データProviderに一部の日・月のデータが存在しなくても、期間を後ろへ延長しない。

```text
欠損を発見
   ↓
gaps.jsonへ記録
   ↓
Forward Fillしない
   ↓
不完全なH4/D1 bucketを作らない
   ↓
Count-only Gateで十分な件数があるか判定
```

許可される処置：

- 存在するバーだけ取得
- 欠損日・欠損月・Provider errorを記録
- 不完全bucketを削除
- 同期が必要な候補では該当timestampを無効化

禁止される処置：

- 2019-08-28以降で穴埋め
- 別銘柄へ差し替え
- 閾値を緩和
- Forward Fill
- 欠損の多い時間足だけ結果を見て除外

---

# 4. 取得するデータ

## 銘柄

| Asset Class | Symbols |
|---|---|
| FX | AUDJPY、AUDUSD、EURGBP、EURJPY、EURUSD、GBPJPY、GBPUSD、USDJPY |
| Metals | XAUUSD、XAGUSD |
| Energy | BRENTCMDUSD、LIGHTCMDUSD |

## 直接取得する系列

```text
12銘柄 × 2時間足 × 2価格Side = 48系列
```

- Timeframe: M15、H1
- Side: BID、ASK
- Timestamp: UTC bar-open
- Field: Open、High、Low、Close、Tick Volume
- Spread: ASK Open − BID Open

## 集計して作る系列

- H4: H1からUTC固定4時間bucketで作成
- D1: H1から00:00〜24:00 UTCで作成

BIDとASKは別々に集計する。Provider予定barが1本でも欠けるbucketは作らない。

---

# 5. 使用する取得ツール

公式認証JForex Tester APIのみを使用する。

| 項目 | 固定値 |
|---|---|
| Root client | `DDS2-jClient-JForex 3.6.51` |
| JForex API | `2.13.99` |
| Channel | authenticated official JForex Tester API, demo endpoint |
| Timezone | `UTC` |

Public endpointと`dukascopy-go`は、自動access条件、pinned配布物のlicense、H1月単位requestが禁止境界後までresponse/cacheに入れる可能性により禁止する。

---

# 6. GitHubに作るファイル

最初の実装commitでは以下を作る。

```text
.github/workflows/
└─ phase9-acquisition-only.yml

research/phase9-hypothesis-redesign-20260828/
├─ data_manifest/
│  ├─ source_versions.json
│  ├─ instrument_mapping.json
│  ├─ trading_calendar.json
│  └─ energy_roll_rules.json
├─ runner/
│  ├─ acquire_phase9_data.py
│  ├─ validate_phase9_acquisition.py
│  └─ jforex/
└─ tests/
   └─ test_phase9_acquisition.py
```

まだ作らないもの：

- Return計算Runner
- MFE / MAE計算
- Matched Edge計算
- Backtest結果JSON
- MT5 EA

---

# 7. Phase 9 Acquisition/QC Workflow

## Trigger

Workflowは手動実行だけにする。

```yaml
on:
  workflow_dispatch:

permissions:
  contents: read
```

`push` Triggerを付けない。旧一時Workflow事故を繰り返さないためである。

## 日付Input

Workflow DispatchのInputで日付を受け取らない。コードへ固定する。

```text
M15 = [2013-01-01T00:00:00Z, 2019-08-28T00:00:00Z)
H1  = [2013-01-01T00:00:00Z, 2019-08-01T00:00:00Z)
```

## 実行順序

1. 完了済みBuild preflightのdependency inventory、runtime identity、runner JAR SHAを監査資料として固定する。これは取得許可ではない。
2. 完了済みS1B Gate A Run `33376110507`の116 JAR SHA、28 native entry、synthetic QC、認可falseを検証する。
3. 28 native entryを別commitのGate B exact-match allowlistとして凍結する。同一Runのinventoryで自己認可しない。（完了、取得認可への効果なし）
4. Shaded runner scan、実native load/mapped DSO、child process/OS egressを検証する。（次の単一作業）
5. 規約確認と別の手動承認後に限り、price requestなしでremote JNLP/runtime closureを観測・hash-lockする。
6. Streaming 48-series Full-QCを同一取得runへ実装し、必要ならユーザー承認済み非公開raw保管を決める。
7. 最終pre-dispatch監査後に限り、buildと分離されたsecret-scoped acquisition/QC workflowの一度の実取得を許可する。

Run 5の後、`.github/workflows/phase9-s1b-runtime-qc-preflight.yml`を`RUN_PHASE9_S1B_NO_SECRET_NO_PRICE_PREFLIGHT`で実行済み。このGate AはMaven/Javaを実行せず、Run 5から固定した116-JAR manifestを2つの完全一致HTTPS repository baseからopaque bytesとして取得した。Redirectとenvironment proxyを拒否し、各SHA一致後にだけZIPを開き、Run #2でnative 28件を記録した。Local synthetic JNLP、synthetic Full-QCも通過した。同一runで発見したnative resourceを同一runの許可表に使わず、別commitの`data_manifest/native_entry_allowlist.run33376110507.json`へGate B allowlistを凍結した。`runner/verify_phase9_gate_b.py`は未知・追加・欠落・重複・case collisionを拒否し、authorizationをすべてfalseに固定する。外部JNLP観測は規約確認と別の手動承認まで実行しない。

取得runnerは日付引数を受け付けず、M15/H1×BID/ASKの4 processで48ファイルを出力する。不完全downloadは必ずfail-closedとする。

## 境界Assert

全CSVについて次を機械検査する。

```text
minimum timestamp >= 2013-01-01T00:00:00Z
M15 maximum timestamp < 2019-08-28T00:00:00Z
H1 maximum timestamp < 2019-08-01T00:00:00Z
```

1本でも範囲外ならWorkflow全体を失敗させる。

## Artifact

Uploadしてよいもの：

- `source_versions.json`
- `instrument_mapping.json`
- `row_counts.txt`
- `sha256.txt`
- `gaps.json`
- `cross_market_overlap.json`
- `energy_roll_inventory.json`
- `quality_report.json`

Uploadしないもの：

- `data/*.csv`
- API Key
- GitHub Token
- OANDA / MT5認証情報
- `.env`

Raw CSVはGitへCommitせず、公開Artifactにも入れない。

---

# 8. Data Quality Gate

Return計算前に48系列すべてを検査する。

| No. | 検査 | 合格条件 |
|---:|---|---|
| 1 | Timestamp順序 | 厳密な昇順 |
| 2 | Duplicate | 0件 |
| 3 | OHLC Geometry | High≥Open/Close、Low≤Open/Close |
| 4 | Price | 全て正 |
| 5 | Volume | 0以上 |
| 6 | BID/ASK | ASK Open≥BID Open |
| 7 | Boundary | 全barが2013-01-01以上、M15は2019-08-28未満、H1は2019-08-01未満 |
| 8 | Gap | 全欠損を記録 |
| 9 | First/Last | series別に記録 |
| 10 | Row Count | series別に記録 |
| 11 | SHA-256 | CSVごとに記録 |
| 12 | Cross-market同期 | FX8、金銀、原油別に記録 |
| 13 | Energy Roll | 候補日を記録 |
| 14 | H4/D1集計 | 完全bucketだけ作成 |
| 15 | Forward Fill | 0件 |

品質検査で計算してよいもの：

- bar数
- 欠損数
- 同期bar数
- spreadのデータ品質統計
- timestamp範囲
- SHA-256

計算してはいけないもの：

- Entry後Return
- MFE
- MAE
- Edge
- 勝率
- Profit Factor
- P値

---

# 9. Count-only Gate

Data Quality Gate合格後、別Runnerを作る。

推奨ファイル：

```text
research/phase9-hypothesis-redesign-20260828/runner/phase9_count_only.py
research/phase9-hypothesis-redesign-20260828/tests/test_phase9_count_only.py
.github/workflows/phase9-count-only.yml
```

## Count-onlyで計算できるもの

- Frozen Entry feature
- Signal true / false
- Signal timestamp
- Direction
- Episode ID
- Control候補の存在数
- 銘柄別件数
- 時間足別件数
- 12か月Block別件数
- UTC日数
- Cross-market同期率

## Count-onlyで計算できないもの

- Entry後の価格差
- Returnの符号
- MFE / MAE
- Signal Return
- Control Return
- Matched Edge
- Bootstrap
- FDR

コード内でOutcome関数自体をImportしない構成を推奨する。

## 最低件数

| Gate Profile | Primary最低件数 | Active UTC Date最低数 |
|---|---:|---:|
| Broad Multi-Asset 3TF | 500 | 250 |
| Broad Multi-Asset 2TF | 500 | 250 |
| FX Cross-Section H4 | 250 | 125 |
| FX Network 2TF | 250 | 125 |
| Two-Leg Pair H4 | 250 | 125 |
| Risk Overlay H4 | 500 | 250 |

候補別の銘柄・時間足・Block coverage条件は
`spec/candidate_registry.frozen.json`の`sample_size_and_coverage_profiles`を直接読む。

Count Gate不合格時：

```text
Decision = REJECT_AS_UNDERPOWERED
p = 1
Return = 未計算
```

禁止：

- 閾値緩和
- 期間延長
- 銘柄削除
- 時間足削除
- Episode定義変更
- 別仮説との交換

---

# 10. Discovery検証

Count-only Gateを通過した候補だけを対象にする。
ただし多重検定FamilyはFrozenの12確認項目を維持し、Underpowered候補は`p=1`として含める。

推奨ファイル：

```text
research/phase9-hypothesis-redesign-20260828/runner/phase9_discovery.py
research/phase9-hypothesis-redesign-20260828/tests/test_phase9_discovery.py
.github/workflows/phase9-discovery-locked.yml
```

## Entry

- 最終確認barを`t`
- Entryを次の取引可能bar open `e`
- `t`以降の情報をEntry判定へ使わない
- Entry遅延が2 nominal timeframeを超えたEventは無効

## Executable Price

| Side | Entry | Exit |
|---|---|---|
| BUY | ASK Open | BID Close |
| SELL | BID Open | ASK Close |

RR-203、RR-204は両脚それぞれにBID/ASKとCostを適用する。

## Primary Outcome

- Entryから12実時間
- Entry時点のlagged ATR14単位
- Entry+12h以前の有効な最後のClose
- Closeの古さが1 nominal timeframeを超えたEventは無効

## Secondary Outcome

- 1時間、4時間、24時間
- 4bar、12bar
- 12実時間内MFE / MAE

Secondary OutcomeやSubgroupは、Primary不合格候補を救済できない。

## Matched Control

- 同一候補・銘柄・時間足・仮想方向
- Treatmentより前のbarだけ
- Controlの12h Outcomeが`t`より前に確定
- 過去90暦日以内
- 同一年、UTC 4時間Block、方向をExact Match
- ATR percentile ±10
- Spread percentile ±10
- 60bar Return z ±0.5
- 5件要求、最低3件
- Reuse上限3
- 未来Returnによる選択禁止

## Episode

```text
strategy_id + UTC calendar date + normalized side
```

同一Episode内は平均し、Episode weightを1にする。
BootstrapはUTC calendar date clusterで10,000回実行する。

## Cost Stress

- BID/ASK spreadをExecutable Priceへ内包
- さらにFilled legごとに`0.25 × (Entry Spread + Exit Spread)`を控除
- Provider commission / financingがpoint-in-timeで取得できる場合は追加
- OANDA固有Cost検証は後段階で必須

## Multiple Testing

- Confirmatory Question: 12件
- Benjamini-Hochberg
- FDR: `q <= 0.10`
- Underpowered / Data Insufficient: `p=1`
- Family分割禁止

## Sensitivity

- Base＋one-at-a-time 6変種＝7仕様
- 7仕様中5仕様以上で正符号が必要
- Sensitivityは不安定性によるRejectにだけ使用
- 最良Sensitivityを採用しない

---

# 11. Discovery判定

## DEVELOPMENT

以下をすべて通過した場合だけ。

1. Count / Coverage Gate合格
2. Primary Effect `>= 0.05` standardized unit
3. Bootstrap 95% CI下限 `> 0`
4. BH adjusted p `<= 0.10`
5. Cost Stress後のRaw Signal Mean `> 0`
6. Frozen Breadth Sign Gate合格
7. Sensitivity正符号が7仕様中5以上

## REJECT_FOR_DEVELOPMENT

Return検証を実行し、上記Gateを1つでも失敗した候補。

## REJECT_AS_UNDERPOWERED

Count-only Gate失敗。Returnは計算しない。

## DATA_INSUFFICIENT

Frozen必須Fieldがない。Returnは計算しない。同じPhaseで差し替えない。

## WATCH

結果未閲覧の運用・データ保留だけに使用する。
統計的な惜しい結果をWATCHにしない。

---

# 12. Discovery出力

各候補について最低限、次を保存する。

- Strategy ID
- 仮説
- Frozen Entry条件
- Entry時点で利用した情報
- 対象銘柄・時間足
- Signal数
- Unified Episode数
- Matched Control定義と成立率
- 12h Return
- Matched Edge
- MFE / MAE
- 95% CI
- Raw p
- BH adjusted p
- 年度Block別
- 銘柄別
- 時間足別
- BUY / SELLまたはResidual Side別
- Parameter Sensitivity
- Cost Stress
- Weakness
- Failed Gate
- REJECT / DEVELOPMENT判定

推奨成果物：

```text
results/
├─ phase9_count_only_report.json
├─ phase9_discovery_report.json
├─ phase9_cross_candidate_decision.json
├─ phase9_results_summary.md
├─ ARTIFACTS.json
├─ source_versions.json
├─ row_counts.txt
├─ sha256.txt
├─ gaps.json
├─ cross_market_overlap.json
└─ energy_roll_inventory.json
```

Raw市場CSVは含めない。

---

# 13. GitHub Actionsの実行順序

```text
Commit A
Provider/Mapping/Calendar/JForex Workflow/Tests
        ↓
Run A0
Build preflightのみ（認証・priceの前に停止）
        ↓
Commit A1
全依存lock・runner JAR SHA・S1Bの116-JAR静的inventory・full-QC/raw保管経路を凍結
        ↓
Run A1
一度のAcquisition + QCのみ
        ↓
QC metadataをGitHubへ保存
        ↓
Commit B
Count-only Runner/Workflow/Tests
        ↓
Run B
Count-onlyのみ
        ↓
Count Gate結果をGitHubへ保存
        ↓
Commit C
Locked Discovery Runner/Workflow/Tests
        ↓
Run C（一度だけ）
全12確認項目を同時検証
        ↓
結果・Decision・HandoffをGitHubへ保存
```

各Commit後にActionsを確認し、旧tmp Workflowが起動していないことを確認する。

---

# 14. 8つの論理役割

別セッションでは次の8役割で監査する。同時実行上限が7なら2波に分ける。

| ID | 役割 | 確認内容 |
|---|---|---|
| A0 | 主担当 | 統合、GitHub Commit、最終判断 |
| A1 | Frozen Candidate監査 | ID、Entry、未来情報、重複 |
| A2 | Data Boundary監査 | 期間、BID/ASK、欠損、集計 |
| A3 | GitHub Actions監査 | Trigger、権限、Artifact、旧Workflow |
| A4 | Provider監査 | Symbol、Version、Calendar、License |
| A5 | QC/Manifest監査 | Row、Gap、SHA、同期、Energy Roll |
| A6 | Count-only漏洩監査 | Return・MFE・MAEを計算していないか |
| A7 | Red-team | 過学習、後付け選択、Cost、再現性 |

サブエージェントは原則read-only。Commit・PushはA0だけが行う。

---

# 15. GitHub更新手順

## 作業前

```bash
git fetch origin
git status --short --branch
git rev-parse origin/main
```

最新mainと作業基点が違う場合、変更を作る前に最新内容を読み直す。

## Commit前

```bash
python -m json.tool research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json >/dev/null
python -m json.tool research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json >/dev/null
python -m json.tool research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json >/dev/null
python -m unittest discover -s research/phase9-hypothesis-redesign-20260828/tests -v
git diff --check
git status --short
```

確認済みPathだけを明示してStageする。`git add .`や`git add -A`を使わない。

## Push後

1. Remote main SHAを再取得
2. 更新ファイルをGitHubから再読
3. Actions一覧を確認
4. 意図しないWorkflowがあれば停止
5. Run ID、Conclusion、Artifact、Outcome accessを記録

Force Pushは禁止。

---

# 16. 停止条件

次のどれかが起きたら、Returnを計算せず停止する。

- Frozen JSONのBlob SHA不一致
- Remote mainが作業中に更新された
- 2019-08-28以降のtimestampを取得
- 欠損をForward Fillした
- ASK < BID
- Provider / Symbol mappingが未確定
- Energy Rollを識別できない
- Count-only前にOutcomeを計算した
- Raw市場CSVや秘密情報がGitにStageされた
- 旧tmp Workflowが起動した

停止した場合は`POLICY_INCIDENT_YYYYMMDD.md`を新規作成し、ユーザーへ報告する。

---

# 17. 別セッションへ送る実行指示

コピー用の最新完成文は`NEXT_SESSION_PROMPT.md`を正本とする。Gate B完了後の単一作業は、exact shaded runnerの静的scanと、native load/mapped DSO、child process、OS egressをno-secret/no-priceで検証する次Gateの設計である。Gate B完了だけでは実取得を認可しない。

---

# 18. 作業完了報告テンプレート

```text
対象Repository:
対象Branch:
開始Commit:
終了Commit:
現在Stage:

作成・更新ファイル:
GitHub Actions Run ID:
Run Conclusion:

取得期間:
取得Series数:
成功Series数:
欠損・失敗Series:
境界外Timestamp:
Forward Fill:
Raw CSVのGit/Artifact保存:

Quality Gate:
Count-only Gate:
Phase 9 Return計算:
MFE/MAE/Edge閲覧:
禁止期間Access:

Policy Incident:
Blocker:
次に実行する1作業:
```

---

# 19. 最終研究フロー

```text
Phase 9 Acquisition / QC
          ↓
Count-only Gate
          ↓
Locked Discovery（12件同時）
          ↓
Survivor Freeze
          ↓
Development Protocol Freeze
          ↓
Walk Forward
          ↓
Strict OOS
          ↓
OANDA MT5 Cost Validation
          ↓
Final Holdout 1回だけ
          ↓
EA Safety / Demo Forward
          ↓
OANDA MT5 Live Standard
```

現在は最初の`Phase 9 Acquisition / QC`のS1B Gate AとGate B allowlist固定を完了し、shaded runner/native load/OS egressのno-secret/no-price検証へ進む段階である。市場price fileは0件で、Actual Full-QCとCount-only以降は未開始である。

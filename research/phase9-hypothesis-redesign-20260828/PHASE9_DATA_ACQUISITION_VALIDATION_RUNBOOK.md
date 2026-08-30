# Phase 9 データ取得・仮説検証 実行手順書

更新日: 2026-08-30  
対象Repository: `tgkfnfnfv9-stack/Gpt-Verification--software`  
対象Branch: `main`  
基準main commit: `efda1604fc8776a033fea43982f113e2a2cdc6f4`

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

現在のGitHubにはPhase 9専用のデータ取得Workflow、Count-only Runner、Discovery Runnerがまだない。
したがって、最初の実装作業はPhase 9専用取得・品質検査基盤の作成である。

---

# 2. 正本として読むファイル

別セッションは作業前に以下を完全に読む。

1. `AGENTS.md`
2. `research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md`
3. `research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260829.md`
4. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
5. `research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md`
6. `research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md`
7. `research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json`
8. `research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json`
9. `research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json`

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

## 許可期間

```text
2013-01-01T00:00:00Z <= timestamp < 2019-08-28T00:00:00Z
```

| 用途 | 開始 | 終了（exclusive） |
|---|---|---|
| Warm-up | 2013-01-01 | 2014-08-28 |
| Phase 9 Discovery | 2014-08-28 | 2019-08-28 |

取得コマンド上の終了は次とする。

```text
--to '2019-08-27 23:59'
```

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

Phase 8で再現実績がある次のバージョンを固定する。

| 項目 | 固定値 |
|---|---|
| Downloader | `dukascopy-go v0.2.0` |
| Archive SHA-256 | `f78f621d747e7584be2ae6789f6b97e22ae656203cc9ab7a32766f699e455e4b` |
| Engine | `jetta` |
| Timezone | `UTC` |

インストール例：

```bash
set -euo pipefail

url='https://github.com/Nosvemos/dukascopy-go/releases/download/v0.2.0/dukascopy-go_0.2.0_linux_amd64.tar.gz'
curl -L --fail --retry 3 -o /tmp/dukascopy-go.tar.gz "$url"

echo 'f78f621d747e7584be2ae6789f6b97e22ae656203cc9ab7a32766f699e455e4b  /tmp/dukascopy-go.tar.gz' \
  | sha256sum -c -

install_dir="$(mktemp -d)"
tar -xzf /tmp/dukascopy-go.tar.gz -C "$install_dir"
binary="$(find "$install_dir" -type f -name dukascopy-go | head -1)"
chmod +x "$binary"
sudo install "$binary" /usr/local/bin/dukascopy-go
dukascopy-go --version
```

Energy symbolを結果計算前に確認する。

```bash
dukascopy-go instruments --query brent
dukascopy-go instruments --query light
```

---

# 6. GitHubに作るファイル

最初の実装commitでは以下を作る。

```text
.github/workflows/
└─ phase9-acquisition-qc.yml

research/phase9-hypothesis-redesign-20260828/
├─ data_manifest/
│  ├─ source_versions.json
│  ├─ instrument_mapping.json
│  ├─ trading_calendar.json
│  └─ energy_roll_rules.json
├─ runner/
│  ├─ validate_phase9_data.py
│  └─ aggregate_phase9_timeframes.py
└─ tests/
   ├─ test_phase9_boundary.py
   ├─ test_phase9_data_quality.py
   └─ test_phase9_aggregation.py
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
FROM = 2013-01-01
TO   = 2019-08-27 23:59
END_EXCLUSIVE = 2019-08-28T00:00:00Z
```

## 取得コマンド

```bash
set -euo pipefail
mkdir -p data results

symbols=(
  AUDJPY AUDUSD EURGBP EURJPY
  EURUSD GBPJPY GBPUSD USDJPY
  XAUUSD XAGUSD BRENTCMDUSD LIGHTCMDUSD
)

for timeframe_spec in 'm15:M15' 'h1:H1'; do
  cli_timeframe="${timeframe_spec%%:*}"
  file_timeframe="${timeframe_spec##*:}"

  for symbol in "${symbols[@]}"; do
    for side in bid ask; do
      output="data/${symbol}_${file_timeframe}_${side}.csv"

      dukascopy-go download \
        --symbol "$symbol" \
        --timeframe "$cli_timeframe" \
        --side "$side" \
        --from '2013-01-01' \
        --to '2019-08-27 23:59' \
        --timezone UTC \
        --output "$output" \
        --engine jetta \
        --parallelism 4
    done
  done
done
```

Providerが欠損区間でCommandを非0終了する場合は、年または月単位に分割取得する。
分割範囲は許可期間内だけとし、結合時はHeader重複、timestamp重複、順序を検査する。
取得できなかった区間は`gaps.json`に残す。

## 境界Assert

全CSVについて次を機械検査する。

```text
minimum timestamp >= 2013-01-01T00:00:00Z
maximum timestamp < 2019-08-28T00:00:00Z
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
| 7 | Boundary | 全barが2013-01-01以上、2019-08-28未満 |
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
Provider/Mapping/Calendar/Acquisition-QC Workflow/Tests
        ↓
Run A
Acquisition + QCのみ
        ↓
QC結果をGitHubへ保存
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

以下をそのままコピーして送る。

```text
GitHub Repository tgkfnfnfv9-stack/Gpt-Verification--software のPhase 9自動売買研究を続けてください。

最初に次を完全に読んでください。

1. AGENTS.md
2. research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md
3. research/phase9-hypothesis-redesign-20260828/PHASE9_DATA_ACQUISITION_VALIDATION_RUNBOOK.md
4. research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260829.md
5. research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json
6. research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json
7. research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json
8. research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json

8つの論理役割A0〜A7を使ってください。同時実行上限が7なら2波に分け、サブエージェントはread-only監査、主担当だけがGitHubへCommitしてください。

現在はFormal alpha 11件＋Risk overlay 1件、全12確認項目がUNTESTED_PREREGISTEREDです。Phase 9固有Returnは未計算です。

今回実行する作業は、Phase 9専用のAcquisition/QC基盤の作成と実行です。

作成対象：

- .github/workflows/phase9-acquisition-qc.yml
- data_manifest/source_versions.json
- data_manifest/instrument_mapping.json
- data_manifest/trading_calendar.json
- data_manifest/energy_roll_rules.json
- runner/validate_phase9_data.py
- runner/aggregate_phase9_timeframes.py
- 境界・品質・集計Tests

取得許可期間は2013-01-01 inclusiveから2019-08-28 exclusiveだけです。日付をWorkflow InputにせずHard-codeし、取得後にも全timestampをAssertしてください。

12銘柄、M15/H1、BID/ASKの48系列をdukascopy-go v0.2.0で取得します。2019年8月などProvider欠損があれば欠損として記録し、その区間だけ飛ばしてください。Forward Fill、期間延長、2019-08-28以降での穴埋めは禁止です。

今回はデータ品質検査だけを行い、Return、MFE、MAE、Edge、勝率、P値を計算しないでください。Raw CSVをGitや公開Artifactへ保存しないでください。

実装、Tests、GitHub反映、Workflow実行、Run監査、QC結果保存まで進めてください。作業後はRepository、Branch、Commit、Run ID、取得期間、48系列の成否、欠損、SHA、Outcome未計算、禁止期間Accessの有無、次作業を日本語で報告してください。
```

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

現在は最初の`Phase 9 Acquisition / QC`を実装する段階である。

# Phase 9 統合運用ガイド

guide_version: `1.3.0`
status: `OPERATIONS_CANONICAL`
更新日: 2026-08-31
対象リポジトリ: `tgkfnfnfv9-stack/Gpt-Verification--software`
対象ブランチ: `main`
凍結仕様の基準コミット: `e94cd52a0ec5a990f32c3740ba83736beb95d709`

凍結正本のGit blob anchor:

- `candidate_registry.frozen.json`: `8740f58efe48c40ba0664606194b18b40cf14c27`
- `data_requirements.frozen.json`: `7e6a476366140e07edac4e4316f8c08a6ab4ae92`
- `preregistered_research_policy.json`: `8483418a6a75f5a6ea7d6b54ca54beb68896855f`

> このファイルは「何を、どの順番で、どう実行・監査・更新するか」の正本です。数値条件を変更する権限はありません。矛盾時は`spec/*.frozen.json`と`policy/preregistered_research_policy.json`を優先します。

## 1. 60秒で分かる現在地

```text
正式検証済み
├─ STRAT-PA-002                 REJECT_FOR_DEVELOPMENT
└─ Phase 8候補15件             全件REJECT_FOR_DEVELOPMENT

Phase 9
├─ Formal alpha                11件
├─ Risk overlay                 1件
├─ Confirmatory questions      12件
├─ 状態                         全件UNTESTED_PREREGISTERED
├─ 正式なPhase 9データ取得      未開始
├─ Provider acquisition         S1B_GATE_A_PASS / GATE_B_FROZEN / PRICE_BLOCKED
├─ Phase 9 return/backtest       0件
└─ MT5 EA                       禁止
```

旧一時workflowによる境界事故があります。詳細は`POLICY_INCIDENT_20260829.md`を必ず読みます。Phase 9候補の結果は実行・閲覧していませんが、2022〜2026年を「一度も取得されていない」とは表現しません。

## 2. 情報源の優先順位

情報の種類ごとに優先順位を分けます。

### 研究仕様・許可・禁止

矛盾した場合は上ほど優先します。

1. `policy/preregistered_research_policy.json`
2. `spec/candidate_registry.frozen.json`
3. `spec/data_requirements.frozen.json`
4. `DESIGN_DECISIONS.md`
5. `HYPOTHESIS_PORTFOLIO_FINAL.md`、`DATA_REQUIREMENTS.md`
6. 本ガイド
7. `NEXT_SESSION_HANDOFF.md`、`README.md`
8. 履歴・draft

`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`と`data_manifest/*.json`は、凍結JSONのouter authorizationを拡大せず、より狭い取得範囲と実行経路を事前固定する運用正本です。矛盾時は、より狭くfail-closedな制約を採用し、期間・銘柄・Gateを拡大しません。

### 事故・実行履歴・データアクセスの観測事実

1. 最新の`POLICY_INCIDENT_*.md`とGitHub run metadata
2. `SESSION_STATE.json`
3. Handoff/README
4. 凍結時点のstatus label

frozen JSON内の`MASKED_NOT_DOWNLOADED`等は基準commit時点の事前登録snapshotです。凍結後に判明したアクセス事故の事実だけは、incidentとSESSION_STATEの最新記録を優先します。この例外は数値仕様、許可期間、Gate、候補を変更しません。

本ガイドは手順正本ですが、研究数値・期間・Gateを上書きしません。

### 実行禁止の旧草案

- `HYPOTHESIS_PORTFOLIO.md`
- `spec/candidate_registry.draft.json`
- `spec/data_requirements.draft.json`
- `policy/hypothesis_stage_policy.json`

## 3. セッション開始時に読む順番

1. `PHASE9_OPERATIONS_GUIDE.md`
2. `POLICY_INCIDENT_20260829.md`
3. `POLICY_INCIDENT_20260830.md`
4. `PROVIDER_ACQUISITION_BLOCKER.md`
5. `JFOREX_SOURCE_CHANNEL_AMENDMENT.md`
6. Phase 8 `results/PHASE8_FINAL_DECISION.json`
7. Phase 8 `results/RESULTS_SUMMARY.md`
8. Phase 9 `README.md`
9. `SESSION_STATE.json`
10. `DESIGN_DECISIONS.md`
11. `HYPOTHESIS_PORTFOLIO_FINAL.md`
12. `spec/candidate_registry.frozen.json`
13. `DATA_REQUIREMENTS.md`
14. `spec/data_requirements.frozen.json`
15. `policy/preregistered_research_policy.json`

数値Entryは必ず`candidate_registry.frozen.json`、取得境界は`data_requirements.frozen.json`、許可・禁止は`preregistered_research_policy.json`から読みます。HandoffやMarkdown要約だけで実装しません。

## 4. GitHubの最新状態を確認する

### ChatGPT Workで作業する場合

1. GitHub接続でrepository full nameを完全一致確認
2. `main`の最新commitを取得
3. 上記15項目をGitHubから直接読む
4. 書込前に再度remote headを確認
5. 変更は1つのatomic commitへまとめる
6. push後にremote headと更新ファイルを再取得する

### ローカルGitを使用する場合

```bash
git fetch origin
git switch main
git status --short --branch
git pull --ff-only origin main
git rev-parse HEAD
```

dirty worktreeを勝手にreset、checkout、削除しません。サブエージェントはcheckout・pull・commit・pushを行わず、主担当だけがGit操作します。

### Gitへ追加するファイルの安全規則

- `git add -A`、`git add .`、無確認globを使わず、確認済みpathだけを明示します。
- `.gitignore`を維持し、raw market data、download/cache、`.env*`、秘密鍵、credential fileを拒否します。
- push前にstaged path、diff、JSON/YAML、secret、raw data混入を検査します。
- raw dataはGitおよび公開Artifactへ載せません。必要なら、ユーザーが許可した非公開保管先を別途決めます。
- non-fast-forward、remote head変更、凍結正本blob SHA不一致のいずれかで停止して再監査します。

## 5. サブエージェント運用

8つの論理役割を使用します。同時実行上限を開始時に確認します。現在のChatGPT Work環境は主担当を含め最大7並列のため、8役割を2波に分けます。

| ID | 役割 | 主な出力 |
|---|---|---|
| A0 | 主担当・統合・GitHub書込 | 計画、最終判断、atomic commit、検証 |
| A1 | 凍結候補監査 | candidate ID、Entry、情報時点、重複 |
| A2 | データ仕様監査 | 期間、fields、BID/ASK、集計、欠損 |
| A3 | GitHub Actions監査 | workflow、trigger、取得範囲、Artifact |
| A4 | Provider監査 | symbol mapping、calendar、version、license |
| A5 | QC/Manifest監査 | row count、gap、SHA、同期、roll |
| A6 | Count-only漏洩監査 | forward outcome非計算、coverage Gate |
| A7 | Red-team | 過学習、future access、cost、再現性、事故 |

### 固定ルール

- サブエージェントは原則read-only監査
- 同一ファイルを複数agentが同時編集しない
- 各agentは入力、判断、未確認点を報告
- 主担当が矛盾を解決し、最終内容だけをcommit
- agentの多数決で凍結仕様を変更しない
- 重大問題を発見したら実行を止め、incidentまたはdecision logへ残す

## 6. Phase 9の検証仮説

完全な数値条件は`spec/candidate_registry.frozen.json`が唯一の正本です。

| ID | 対象・時間足 | 種別 | 要点 |
|---|---|---|---|
| PS-202 | 全12、M15/H1/H4 | 反転 | 20本高安の明確なbreak後、2本以内に旧境界内へ戻る失敗breakを反対方向へ取る |
| PS-203 | 全12、M15/H1/H4 | 継続 | 完成済みH4/D1 trend中、限定pullback後の構造的再加速を取る |
| PS-204 | FX8＋金銀、M15/H1 | 反転 | UTC 00:00〜06:00 rangeの欧州時間false breakを反対方向へ取る |
| PS-205 | 全12、H1/H4 | 継続 | D1 20/60日trendとintraday pullback後の再開を取る |
| LV-201 | 全12、M15/H1/H4 | 継続 | 同一UTC slot比の参加量shock、正常spread、次足確認で追随 |
| LV-202 | 全12、M15/H1/H4 | 継続 | volatility圧縮20本balanceのbreak、retest保持、再確認で追随 |
| LV-203 | 全12、M15/H1/H4 | 反転 | climactic range・volume・wick後のmidpoint回復で反転 |
| RR-201 | FX8、H4 | 継続 | 5通貨の20/60日strength順位とH4 pullbackを組み合わせる |
| RR-202 | FX8、H1/H4 | 相対反転 | 他7pairから推定した理論値への残差乖離が収束を始めた方向 |
| RR-203 | 金銀、H4 | 相対反転 | Gold/Silverのdynamic hedge residual平均回帰 |
| RR-204 | Brent/WTI、H4 | 相対反転 | Brent/WTIのdynamic hedge residual平均回帰 |
| RISK-P9-RO-201 | PS-205 H4 signal共有 | Risk overlay | 年率10% target-vol、0.25〜1.50倍size。独立alphaではない |

### 草案からの処置

- PS-201 → LV-202へ結果未閲覧で統合
- LV-204 → 旧VV-104との独立性不足でpretest削除
- RR-205 → point-in-time carry data不足でpretest除外、差し替えなし
- LV-205 → PS-205とsignalが重複するためrisk overlay化

## 7. データ期間

| Source timeframe | 取得開始（inclusive） | 取得終了（exclusive） | 処置 |
|---|---|---|---|
| M15 | `2013-01-01T00:00:00Z` | `2019-08-28T00:00:00Z` | 凍結outer intervalの上限まで |
| H1 | `2013-01-01T00:00:00Z` | `2019-08-01T00:00:00Z` | 2019年8月を全12・BID/ASKで一律事前除外 |

Warm-upは2013-01-01以上2014-08-28未満、Discoveryは2014-08-28以降で各source timeframeの取得終了未満です。終了境界はすべてexclusiveです。

H1の`[2019-08-01, 2019-08-28)`は結果未閲覧で一律除外しました。同じPhase 9で後から取得、M15から生成、または個別銘柄だけ復活させません。M15も2019-08-28以降を要求・取得・cacheしません。

H4とD1はcanonical H1からの派生のみなので、最終的な対象終了はいずれも`2019-08-01T00:00:00Z`未満です。

2019〜2022年はPhase 8で使用済みです。2022〜2026年には旧戦略workflowのアクセス履歴があるため、厳格なDevelopment/OOS/Holdoutとしての有効性は後続protocolを凍結する前に再監査します。Phase 9候補結果はまだ計算していません。

## 8. GitHub上にあるデータ取得方法

### 現在の実行判断

公開website endpointと`dukascopy-go`の組合せは、自動access条件、配布license、H1月単位requestの禁止境界超過の3点で廃止しました。詳細は`PROVIDER_ACQUISITION_BLOCKER.md`を参照します。

代替として、公式認証JForex Tester APIと公式SDKを使う取得経路を`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`で事前凍結しました。Build preflight Run `33336895081`はpre-connect non-bootstrap class-origin試験に成功しました。S1B Gate A Run `33376110507`は、Run 5から固定した116個のJARをMaven/Javaを実行せず取得し、全SHA一致後に28 native entryを静的列挙し、repository-local synthetic JNLPとsynthetic Full-QC primitivesを完了しました。その28件はRun 2とは別commitの`data_manifest/native_entry_allowlist.run33376110507.json`へGate B exact-match allowlistとして凍結し、Artifact ZIP、2 archive、28 entryを独立再検証済みです。Shaded runner、native load/mapped DSO、child process/OS egress、remote JNLP、streaming actual Full-QC、raw custodyが未解決であり、S1B成功もGate B成功も実取得許可ではありません。

### 再利用できる参考実装

- `.github/workflows/phase8-blind-discovery.yml`
- `.github/workflows/phase8-vv104-unified-audit.yml`

両方ともPhase 8用の参考実装であり、Phase 9ではそのまま実行しません。

### 正式なPhase 9取得方式

- Channel: authenticated Dukascopy JForex Tester API
- Root client: `DDS2-jClient-JForex 3.6.51`
- API: `JForex-API 2.13.99`
- Root POM SHA-256: `ea80b6e0c938ca4831d723f29ec2ca311967788b00c6218c6768b91cbdb28bd9`
- Root JAR SHA-256: `daf2d98cded0a8ff85276965f0c10eb01692acff7949a5898ab295708e2c26c2`
- Timezone: UTC
- Source: M15、H1
- Side: BID、ASK
- 12銘柄
- Process: M15/H1 × BID/ASKの4回
- Expected output: 48 CSV
- CSV名: `${symbol}_${M15|H1}_${bid|ask}.csv`

workflow inputに日付はありません。Java runnerがtimeframe別の境界をhard-codeし、Python validatorが48ファイルの境界、BID/ASK同期、OHLC、spreadなどを再検査します。H4/D1集計とCount-onlyはこの取得runで実行しません。

### GitHub Actions実行手順

1. `.github/workflows/phase9-acquisition-only.yml`を`workflow_dispatch`で開く。
2. `confirmation`へ`BUILD_PHASE9_JFOREX_PREFLIGHT_ONLY`を入力する。
3. workflowが凍結anchor、manifest、runner test、official root dependency SHAを検証する。
4. 空の専用Maven repoでonline buildし、同じrepoだけを使うoffline rebuildを2回行う。
5. 3回の依存inventory完全一致、3回のrunner JAR SHA一致、runtime identityをmetadata Artifactへ保存する。
6. このworkflowにはDukascopy・市場Secrets、JForex認証、price request、raw CSV、QC、Outcomeのstepを置かない。checkoutの一時GitHub tokenは永続化しない。

Run 5監査後のS1B Gate Aは`.github/workflows/phase9-s1b-runtime-qc-preflight.yml`を使い、confirmationへ`RUN_PHASE9_S1B_NO_SECRET_NO_PRICE_PREFLIGHT`を完全一致入力します。GitHub checkoutのscoped ephemeral tokenは使用しますが永続化せず、Dukascopy・市場資格情報は参照しません。Maven、Java、外部JNLP request、JForex connect、market request、native executionは行いません。116個のlocked JARはredirect/proxyなしで取得し、SHA一致後にだけ静的に開きます。Artifactはdata custody policyの完全allowlistを全検査した成功時だけuploadします。

S1B Run #1 `33374751888`は116 JARの全SHA一致まで成功しましたが、Java `.class`の`CAFEBABE`をMach-O fat magicと誤認しました。28,088件のfalse positiveを含むため同Runのnative inventoryは無効で、Gate B allowlistに使いません。

衝突除外とregression testを反映したRun #2 `33376110507`はcompleted/successです。116 JARの全SHA一致、28 native entry、Java class衝突除外、exact 9-file metadata Artifactを確認しました。Artifact ZIP SHA-256は`ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a`です。取得・価格・禁止期間・Outcomeへのaccessは0で、全認可はfalseです。正本監査は`results/s1b-run-33376110507/S1B_AUDIT.json`です。

このArtifactはlocked JAR/native inventoryとsynthetic QCの監査資料であり、取得許可そのものではありません。shaded runner、JNLP接続がMaven closure外の実行codeを追加取得しないことの検証と、full-QC/raw保管経路の決定後に、別のsecret-scoped acquisition/QC workflowを事前監査します。

Gate B監査正本は`results/gate-b-native-allowlist/GATE_B_AUDIT.json`です。Verifierは`runner/verify_phase9_gate_b.py`で、Run ID、head SHA、116-JAR manifest SHA、Artifact ZIP SHA、archive/entryの完全集合と各fieldを照合します。未知archive、追加・欠落・重複entry、case collision、未知magic/target、authorization反転はfail-closedです。Gate B後も`acquisition_authorized=false`、価格0件、Outcome未計算を維持します。

workflowはprice、return、edgeの実行ボタンを自動的に続けません。取得成功後も`full_quality_gate_passed=false`のまま停止し、calendar、H4/D1 bucket、Energy rollを別工程で監査します。

凍結JNLPはdemo serviceです。Repository secretsにはJForex demo accountの認証情報だけを登録し、live accountの認証情報を使いません。ただしSecrets設定自体がまだ未認可です。2026-09-01時点ではlocal/synthetic専用Plugin module、owned-bytecode exact allowlist、synthetic exact-destination network namespace、private custodyまでを実装し、exact initial URLのidentityだけを単一GETで観測・独立監査しました。remote JNLP/runtime closure、実network destination、SDK内部price受信・cache非露出の証明は未完了です。初期観測の単一使用認可は消費済みで、rerun/replay/follow-up URL、Secrets、JForex接続、provider schedule、availability、price取得を認可しません。現在のmetadata-only preflightもlocal/synthetic controlsだけを検証し、取得認可効果を持ちません。単一の`tick_volume`はBID bar volumeをcanonicalとし、ASK volumeは不一致件数のQCだけに使います。

### Remote JNLP initial identity observation（単一使用）

`.github/workflows/phase9-remote-jnlp-initial-observation.yml`は手動`workflow_dispatch`専用です。confirmationには`OBSERVE_PHASE9_REMOTE_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS`を完全一致入力します。実行できるのはこのworkflowの`run_number=1`かつ`run_attempt=1`だけで、最初のdispatchが成功・失敗にかかわらず承認を消費します。rerunや第2回dispatchは未認可です。

許可範囲は`https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp`へのunauthenticated HTTPS GET 1回、response body最大2 MiBだけです。redirectは追跡せずLocationを記録するだけで、埋込resource URLは受信済みbytesからlocal parseするだけです。raw JNLP bytes、証明書DER、JAR、cookie、credentialはArtifactへ保存しません。Artifactはidentity audit JSONとそのSHA manifestの2ファイルだけです。同じRunで観測URLをallowlist化せず、後続URL request、JForex connect、schedule/availability/price、Count-only、Outcomeへ進みません。

この単一使用workflowはRun `33500446289`（head `aa9d46a6a42936042a406bdf339f07d378cc79b7`、Job `99832303024`、Artifact `9797466074`）でcompleted/successとなり、認可を消費しました。Artifact ZIP SHA-256は`5a0339a026ea2ac0a7382b3ad7e0510a303609ab8817d55a268b55108415b8d2`で独立downloadと一致しています。HTTP 200、2445 bytes、body SHA-256 `4e5adcbb29116e7f17b3babfc4aa47590d06baca50a98745d300d4824a1a70e9`、TLS certificate DER SHA-256 `616df88e991b3d1f0ca1183d5155a243d7dfceb0b3f1461cb4f400d43b6003df`を確認し、redirect/recursive resource requestは0でした。

観測した3 href、codebase、explicit-port initial URLの5 exact stringは、元Runとは別の後続Commitで`spec/remote_jnlp_observed_url_allowlist.frozen.json`へevidence-onlyとして凍結しました。aggregate SHA-256は`72fe580e020440cb273c56eef77b73982b78fb3843b33c1ac32e119b767790ee`です。このallowlistはrequest許可ではありません。初期URLの再実行、`libs_3.jnlp`、icon、JAR/resourceなどを要求するには、対象と上限を凍結した別Gateおよび別ユーザー承認が必要です。

### 12銘柄

| Asset | 研究ID / Dukascopy確認対象 |
|---|---|
| FX | AUDJPY、AUDUSD、EURGBP、EURJPY、EURUSD、GBPJPY、GBPUSD、USDJPY |
| Metals | XAUUSD、XAGUSD |
| Energy | BRENTCMDUSD、LIGHTCMDUSD |

OANDA MT5側のsymbol、contract size、lot、session、financing/rollは将来のcost protocol前に別途固定します。

### Artifact方針

既存Phase 8 workflowは`results/`だけを14日Artifact保存し、raw CSVはrunner一時領域で消えます。Phase 9でもraw巨大CSVをGitや公開Artifactへ載せず、runner一時領域またはユーザー承認済みの非公開保管だけを使います。再現用script、manifest、version、row counts、gap、SHA-256、同期、roll inventory、結果だけをGitへ保存します。

### 使用禁止

- `.github/workflows/tmp-gbpjpy-h1-v8.yml`
- `.github/workflows/tmp-gbpjpy-h1-v8b.yml`
- `.github/workflows/phase8-blind-discovery.yml`
- `.github/workflows/phase8-vv104-unified-audit.yml`

Phase 8の2本はfail-closedに無効化済みです。Phase 9 workflowは完全一致確認付きmanual Build preflightだけを許可し、workflow定義からcredential・price stepを除去しています。

## 9. Phase 9の全工程

```text
S0 正本・事前登録確認
 ↓
S1 Provider / mapping / calendar / version固定
 ↓
S2 許可期間だけ取得
 ↓
S3 Data Quality Gate
 ↓
S4 Count-only Gate
 ↓
S5 12確認項目を同時Discovery
 ↓
S6 Survivor再凍結
 ↓
S7 Development protocolを結果未閲覧で新規凍結
 ↓
S8 Walk-Forward protocolを新規凍結・実行
 ↓
S9 Strict OOS protocolを新規凍結・一度だけ実行
 ↓
S10 OANDA MT5 cost protocolを新規凍結・実行
 ↓
S11 Final Holdout protocolを新規凍結・一度だけ実行
 ↓
S12 EA safety protocol・demo forward
 ↓
S13 live許可
```

Development以降は順序と候補期間だけが登録され、Phase 9専用の数値Gate・fold・合否規則は未確定です。次段階のavailability照会・取得前に、その段階専用protocolを結果未閲覧で別commitへ凍結します。旧`common_edge_policy.yaml`はprovisionalであり、Phase 9正式Gateとして使いません。

## 10. Stage別手順

| Stage | 入力 | 実施 | 出力・Gate |
|---|---|---|---|
| S0 | frozen registry/data/policy | head・JSON・hash・draft排除確認 | preregistration integrity |
| S1 | provider metadata | 認証API、hard-clipped request、provider、12 symbol、calendar、roll、version、client SHAを結果なしで固定 | metadata-only amendment凍結済み。実接続はremote runtime/egress/price-isolation証明待ち |
| S2 | S1 manifest | 12×M15/H1×BID/ASK=48系列をtimeframe別の許可期間だけ取得 | runner一時raw、metadata row count・SHA、full QCは未通過で停止 |
| S3 | 48系列 | timestamp、duplicate、OHLC、spread、gap、missingness、同期、roll、H1→H4/D1監査 | quality report |
| S4 | quality通過data | signal flag、episode、control availability、group countだけ計算 | PASSまたはREJECT_AS_UNDERPOWERED |
| S5 | count通過候補 | 12h return、control edge、cost、bootstrap、FDRをlocked run | DEVELOPMENTまたはREJECT |
| S6 | Discovery survivor | code/data/hash/decision固定 | 次段階候補commit |
| S7以降 | 前段階PASS | 次段階protocolを先に凍結してから当該splitだけ開く | stage terminal decision |

### S1で固定するファイル

- `source_versions.json`
- `instrument_mapping.json`
- `trading_calendar.json`
- `energy_roll_rules.json`
- Phase 9専用acquisition workflow
- boundary tests

### S2取得コマンドの原則

日付をworkflow inputにしません。コードにhard-codeし、取得後にもassertします。

```text
M15: [2013-01-01T00:00:00Z, 2019-08-28T00:00:00Z)
H1:  [2013-01-01T00:00:00Z, 2019-08-01T00:00:00Z)
assert no H1 row exists in 2019-08
assert no row reaches 2019-08-28T00:00:00Z
```

取得jobでbacktest、return、MFE、MAE、edge、勝率を計算しません。

### S3品質Gate

- timestamp厳密昇順、duplicate 0
- OHLC geometry正常、price > 0、volume >= 0
- ASK open >= BID open
- provider calendarに対するgap・session missingness
- first/last timestamp、row count、SHA-256
- FX8、金銀、原油の同期bar数
- Energy roll-date inventory
- H1→H4/D1完全bucket
- no forward fill

### S4 Count-only Gate

計算可能なのはEntry feature、signal flag、episode ID、control availability、instrument/timeframe/block/date別件数だけです。forward return、MFE、MAE、edge、その符号は禁止です。

不合格：

```text
REJECT_AS_UNDERPOWERED
p = 1
return非計算
条件緩和・銘柄/時間足削除・期間延長・候補差替え禁止
```

候補profile別の完全な最低件数・coverageは`candidate_registry.frozen.json`を参照します。

### S5 Discovery

- Primary: executable BID/ASKによる12実時間return
- prior-only matched control
- UTC日cluster episode
- Bootstrap 10,000回
- 12確認項目を1 familyとしてBH-FDR `q<=0.10`
- stressed raw return、CI、breadth、sensitivityを全てGate化
- RR-203/RR-204は2脚portfolio risk unit
- RISK-P9-RO-201はpaired Delta episode Sharpe
- subgroupや最良sensitivityによる救済禁止

## 11. 絶対禁止事項

- PA-002、Phase 8候補の再最適化
- frozen Entry・対象・時間足・期間・control・Gate変更
- M15で2019-08-28以降、またはH1で2019-08-01以降をPhase 9取得jobで照会・download・cache
- H1の2019年8月tailをM15から後付け集計して復活
- Count-only前のreturn、return符号、MFE、MAE、edge、勝敗、勝率、Profit Factor、Drawdown、累積R、p値、信頼区間、順位、Outcome chartの生成・閲覧
- Count-only前のPhase 9 JSONを既存Outcome viewerへ読ませること
- 結果後の銘柄・時間足・side選択
- favorable subgroupやsensitivityによる救済
- Underpowered/Data insufficient候補の差し替え
- raw市場CSV、API key、GitHub token、OANDA/MT5認証情報のcommit
- Final Holdoutの複数回実行
- 全Gate前のMT5 EA実装
- 旧tmp workflowの再有効化

## 12. ファイルの役割と更新規則

| ファイル | 役割 | 更新 |
|---|---|---|
| `PHASE9_OPERATIONS_GUIDE.md` | 手順・参照・GitHub・agent運用 | 運用変更時 |
| `SESSION_STATE.json` | 現在状態・incident・次action | 各作業終了時 |
| `NEXT_SESSION_HANDOFF.md` | 次回への差分・入口 | セッション終了時 |
| `README.md` | 索引 | 正本追加時 |
| `DESIGN_DECISIONS.md` | 研究設計判断 | 新しい事前判断時 |
| `spec/*.frozen.json` | 凍結数値仕様 | 原則変更禁止 |
| `policy/preregistered_research_policy.json` | 許可・禁止 | 原則変更禁止 |
| `POLICY_INCIDENT_*.md` | 境界事故の監査記録 | 事故時に追記せず新規作成 |

仕様変更が必要なら実行を止め、新version、理由、outcome access状況を記録し、ユーザー承認後に新しいpreregistration commitを作ります。

## 13. GitHub更新手順

1. remote headと対象repo/branch確認
2. 変更対象と既存SHA確認
3. unrelated fileを変更しない
4. サブエージェント監査
5. 主担当が変更を統合
6. JSON parse、YAML trigger、link、secret scan、diff check
7. 1つのatomic commitを作成
8. non-forceで`main`更新
9. remote headと各fileを再取得
10. Actions runを確認し、意図しないworkflowが起動していないことを確認
11. repo、branch、files、commit、tests、data access、outcome access、残作業を報告

## 14. 次セッション引き継ぎテンプレート

```text
開始commit:
終了commit:
現在Stage:
Formal alpha / overlay:
Agent rolesと重要結論:
更新ファイル:
取得した期間:
Manifest / SHA:
Quality / Count Gate:
Phase 9 outcome accessed:
禁止期間access:
Policy incident:
Blocker:
次に実行する1作業:
```

ガイド全文をHandoffへ複製せず、Handoffは今回の差分と次の1作業だけを書きます。

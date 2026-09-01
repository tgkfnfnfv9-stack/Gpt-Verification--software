# Phase 9 自動売買研究｜次セッション引継ぎ

更新日: 2026-09-01

Repository: `tgkfnfnfv9-stack/Gpt-Verification--software`

Actual Full-QC実装基準: `9eb7ce667bea8e76a7f9bb1f2d378eebd8957206`

現在のremote mainは、この実装基準より後の引継ぎ文書Commitを含む。次セッション開始時に必ずremote mainを再確認する。

## 1. この引継ぎの結論

Phase 9では、実価格データを受け入れて検査するActual Full-QC契約まで実装・監査済み。
provider scheduleのauthoritative/versioned/price-independent source自体は未固定であり、inventoryと別Commit allowlistは未取得・未凍結。2026-09-01にremote JNLP initial identity observation Run `33500446289`をユーザー承認された単一GETとして完了し、Run/Job/Artifact/head/ZIPを独立監査した。観測した5 exact URLは元Runとは別の後続Commitでevidence-only allowlistとして凍結したが、単一使用認可は消費済みであり、follow-up URL、接続dispatch、正式取得はいずれも未認可である。

```text
Phase 9仮説凍結
  ↓ 完了
S1B Gate A：locked JAR / native inventory
  ↓ PASS
Gate B：28 native entry exact allowlist
  ↓ PASS（取得認可効果なし）
Gate C1/C2：runtime socket・mapping inventory / allowlist
  ↓ PASS（取得認可効果なし）
Gate C3：child process・OS egress・custody実行境界
  ↓ PASS（取得認可効果なし）
Actual 48-series Full-QC契約
  ↓ 実装・Tests・A6/A7 PASS
Provider schedule source readiness
  ↓ P0 BLOCKED（公式version付き完全履歴source未固定）
Metadata-only JForex amendment / static Gate
  ↓ FROZEN（no-secret/no-connect、dispatch認可なし）
Local M1 module / bytecode / network / custody
  ↓ 実装済み（local/syntheticのみ、認可効果なし）
Remote JNLP initial identity observation
  ↓ Run 33500446289 PASS・独立監査・別Commit exact URL freeze（再実行/後続request未認可）
Remote JNLP/runtime/network/price-isolation discovery
  ↓ 初期identityのみ完了、runtime closure未解決
Provider schedule inventory / allowlist
  ↓ 未開始
正式48系列取得 → Actual Full-QC → Count-only → Return検証
```

## 2. 最初に完全に読む

1. `/AGENTS.md`
2. `research/phase9-hypothesis-redesign-20260828/NEXT_SESSION_HANDOFF.md`
3. `research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md`
4. `research/phase9-hypothesis-redesign-20260828/PHASE9_DATA_ACQUISITION_VALIDATION_RUNBOOK.md`
5. `research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260829.md`
6. `research/phase9-hypothesis-redesign-20260828/POLICY_INCIDENT_20260830.md`
7. `research/phase9-hypothesis-redesign-20260828/PROVIDER_ACQUISITION_BLOCKER.md`
8. `research/phase9-hypothesis-redesign-20260828/JFOREX_SOURCE_CHANNEL_AMENDMENT.md`
9. `research/phase9-hypothesis-redesign-20260828/JFOREX_METADATA_ONLY_CONNECTION_AMENDMENT.md`
10. `research/phase8-blind-discovery-20260828/results/PHASE8_FINAL_DECISION.json`
11. `research/phase8-blind-discovery-20260828/results/RESULTS_SUMMARY.md`
12. `research/phase9-hypothesis-redesign-20260828/README.md`
13. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
14. `research/phase9-hypothesis-redesign-20260828/DESIGN_DECISIONS.md`
15. `research/phase9-hypothesis-redesign-20260828/HYPOTHESIS_PORTFOLIO_FINAL.md`
16. `research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json`
17. `research/phase9-hypothesis-redesign-20260828/DATA_REQUIREMENTS.md`
18. `research/phase9-hypothesis-redesign-20260828/spec/data_requirements.frozen.json`
19. `research/phase9-hypothesis-redesign-20260828/policy/preregistered_research_policy.json`
20. `research/phase9-hypothesis-redesign-20260828/results/s1b-run-33376110507/S1B_AUDIT.json`
21. `research/phase9-hypothesis-redesign-20260828/runner/phase9_actual_full_qc.py`
22. `research/phase9-hypothesis-redesign-20260828/spec/provider_schedule_contract.frozen.json`
23. `research/phase9-hypothesis-redesign-20260828/spec/metadata_only_jforex_schedule_gate.frozen.json`
24. `research/phase9-hypothesis-redesign-20260828/spec/metadata_only_local_m1_gate.frozen.json`
25. `research/phase9-hypothesis-redesign-20260828/spec/metadata_owned_method_allowlist.frozen.json`
26. `research/phase9-hypothesis-redesign-20260828/JFOREX_REMOTE_JNLP_OBSERVATION_AMENDMENT.md`
27. `research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_observation_amendment.frozen.json`
28. `research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_initial_observation_gate.frozen.json`
29. `research/phase9-hypothesis-redesign-20260828/results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json`
30. `research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_observed_url_allowlist.frozen.json`
31. `research/phase9-hypothesis-redesign-20260828/runner/verify_phase9_remote_jnlp_independent_audit.py`

凍結仕様の優先順位は、candidate registry、data requirements、preregistered policy。Markdown要約で凍結仕様を変更しない。

## 3. 現在の研究状態

| 項目 | 現在値 |
|---|---|
| Phase 8正式仮説 | PA-002を含む16件、全件 `REJECT_FOR_DEVELOPMENT` |
| Phase 9 formal alpha | 11件 |
| Phase 9 risk overlay | 1件 |
| Phase 9確認項目 | 12件、全件 `UNTESTED_PREREGISTERED` |
| Phase 9正式取得 | 未開始 |
| Phase 9価格ファイル | 0件 |
| Actual Full-QC | 契約実装済み、実データでは未実行 |
| Count-only | 未開始 |
| Return検証・バックテスト | 未開始 |
| 確認済みPhase 9優位性 | 0件 |
| MT5 EA | 実装禁止 |
| `acquisition_authorized` | `false` |
| `count_only_authorized` | `false` |
| `research_outcomes_calculated` | `false` |

## 4. 完了済み証跡

### 4.1 S1B Gate A / Gate B

- S1B Run ID: `33376110507`
- Job ID: `99437846539`
- Artifact ID: `9751919672`
- Head SHA: `951c38aaa875180fa7dbbe498866a4e3ece50e9c`
- Artifact ZIP SHA-256: `ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a`
- Locked JAR: 116/116 SHA一致
- Native候補: 28件
- Java `.class` CAFEBABE誤分類28,088件は除外済み
- Gate B allowlist: `data_manifest/native_entry_allowlist.run33376110507.json`
- Gate Bは別Commit exact-match PASS。ただし取得認可効果なし。

### 4.2 Gate C2 runtime mapping allowlist

- Source Run ID: `33451221995`
- Job ID: `99681326258`
- Artifact ID: `9779840519`
- Source head: `9699c64b9133482caf22cef07dc9b3bc2fe33a1a`
- Artifact ZIP SHA-256: `d5ea84805732209e85340376de98788f897eba411a3170b300600767252d60f0`
- Executable mapping: 15件
- Allowlist: `data_manifest/runtime_mapping_allowlist.run33451221995.json`
- Exact-match PASS。ただし取得認可効果なし。

### 4.3 Gate C3 execution envelope

- GitHub Commit: `795dcef802d16310c0350b7c20e0871919e76882`
- Run ID: `33455444958`
- Job ID: `99694321791`
- Artifact ID: `9781258311`
- Artifact ZIP SHA-256: `4cee963b9c3ffa7bb88bec5287a36de82ec4197c8c7e7e2277ea313acd4970c8`
- Workflow: `completed / success`
- Seccomp/Landlock child-process・external socket境界: PASS
- Same-run custody・cleanup: PASS
- Credential、JForex、price、禁止期間、Outcomeアクセス: なし
- `acquisition_authorized=false`

### 4.4 Actual Full-QC contract preflight

- GitHub Commit: `9eb7ce667bea8e76a7f9bb1f2d378eebd8957206`
- Run ID: `33459534741`
- Job ID: `99706597775`
- Artifact ID: `9782660195`
- Artifact ZIP SHA-256: `af4d807d725c0a6207e19d3fbadc0157603bb8cd40474545564012938c59f4d5`
- Workflow: `completed / success`
- Tests: 131 PASS。ローカルでは既存Gate C3 Landlock test 1件skip、GitHub jobはsuccess。
- A6/A7 read-only監査: P0/P1なし、PASS
- Workflow artifact: blocked-state監査JSON＋manifestの2件のみ
- `provider_schedule_inventory_acquired=false`
- `actual_market_data_full_quality_gate_passed=false`
- `acquisition_authorized=false`
- `count_only_authorized=false`
- `research_outcomes_calculated=false`

### 4.5 Metadata-only JForex amendment preflight

- User approval: metadata-only方式のamendment実装を承認
- Contract: `spec/metadata_only_jforex_schedule_gate.frozen.json`
- Workflow: `.github/workflows/phase9-metadata-only-jforex-gate-preflight.yml`
- Scope: no-secret / no-JNLP / no-JForex / no-network static verification only
- `metadata_only_connection_amendment_authorized=true`
- `connection_dispatch_authorized=false`
- `external_jnlp_observation_authorized=false`
- `demo_credentials_may_be_configured=false`
- Provider schedule inventory / allowlist: 未取得・未凍結
- 価格・availability・禁止期間・Outcomeアクセス: なし
- 取得認可効果: なし

### 4.6 Local M1 controls

- Dedicated module: `runner/jforex-metadata`
- Local contract: `spec/metadata_only_local_m1_gate.frozen.json`
- Owned bytecode allowlist: `spec/metadata_owned_method_allowlist.frozen.json`
- Workflow: `.github/workflows/phase9-metadata-local-m1-preflight.yml`
- Network: uplinkなしの独立client/server namespace間に`198.18.0.2/32 -> 198.18.0.1/32:38443`のhost routeだけを作るsynthetic test。targetは別PID namespaceのUID 65534で実行し、Landlock/seccompで他port、他address、UDP/raw/AF_UNIX、child、setns/unshare、外部writeを拒否
- Custody: exact private 0700 directories / 0600 regular single-link files
- Existing price acquirer: moduleから物理的に除外
- Compile proof: 凍結したlocal synthetic API fixtureに対するexact bytecode allowlistのみPASS。実JForex API 2.13.99 JAR/runtime互換性は未検証であり残Blocker
- Remote amendment: `JFOREX_REMOTE_JNLP_OBSERVATION_AMENDMENT.md`
- `connection_dispatch_authorized=false`
- schedule/price/Outcomeアクセス: なし

### 4.7 Remote JNLP initial identity observation

- Implementation Commit: `aa9d46a6a42936042a406bdf339f07d378cc79b7`
- Run ID: `33500446289`（run_number 1 / run_attempt 1 / completed-success）
- Job ID: `99832303024`
- Artifact ID: `9797466074`
- Artifact ZIP SHA-256: `5a0339a026ea2ac0a7382b3ad7e0510a303609ab8817d55a268b55108415b8d2`
- Exact request: `https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp`へのunauthenticated GET 1回
- Response: HTTP 200、2445 bytes、body SHA-256 `4e5adcbb29116e7f17b3babfc4aa47590d06baca50a98745d300d4824a1a70e9`
- TLS certificate DER SHA-256: `616df88e991b3d1f0ca1183d5155a243d7dfceb0b3f1461cb4f400d43b6003df`
- Redirect: 0、recursive resource request: 0、raw JNLP/JAR/credential/market CSV保存: 0
- Locally parsed href: 3件、canonical exact URL set: 5件、aggregate SHA-256 `72fe580e020440cb273c56eef77b73982b78fb3843b33c1ac32e119b767790ee`
- 独立監査: `results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json`
- 後続URL凍結: `spec/remote_jnlp_observed_url_allowlist.frozen.json`（元Runとは別Commit、evidence-only）
- 単一使用認可は消費済み。rerun/replay、`libs_3.jnlp`、icon、その他resourceのrequestはすべて未認可
- `external_jnlp_observation_authorized=false`、`followup_url_request_authorized=false`
- provider schedule/availability/JForex connect/price/禁止期間/Outcomeアクセス: なし

## 5. Actual Full-QCに実装済みの検査

- exact 12銘柄 × M15/H1 × BID/ASK = 48系列
- CSV header、ASCII、UTC `Z`、時刻整列、期間境界
- timestamp厳密昇順、重複拒否、OHLC geometry、finite、正価格、非負volume
- BID/ASK timestamp exact match、ASK openがBID open未満なら拒否
- canonical tick volume sideはBID。ASK volume差は診断件数として記録
- M15完全4本とdirect H1のOHLCV照合
- complete M15があるのにdirect H1が欠ける場合を記録
- H4/D1はcanonical H1の完全UTC 4/24本だけから派生
- H4/D1派生OHLCV digest
- FX8、Metals2、Energy2の固定group同期監査
- Provider scheduleによる全欠損分類、Forward Fill 0
- Raw/scheduleのowner、mode、link count、device、inode、size、mtime、SHA固定
- Root directory identity固定
- Reportは固定dirfd＋`O_EXCL`＋hard-link no-clobber＋fsync
- Canonical allowlist path、Git strict ancestor、freeze parent、Git object byte一致、tracked/unmodifiedを検証
- 同一Runの自己申告allowlistを拒否
- Return/Outcome関連値は生成しない

## 6. 正式取得範囲

- AUDJPY、AUDUSD、EURGBP、EURJPY、EURUSD、GBPJPY、GBPUSD、USDJPY
- XAUUSD、XAGUSD
- BRENTCMDUSD、LIGHTCMDUSD
- 12銘柄 × M15/H1 × BID/ASK = 48系列
- M15: `[2013-01-01T00:00:00Z, 2019-08-28T00:00:00Z)`
- H1: `[2013-01-01T00:00:00Z, 2019-08-01T00:00:00Z)`
- H4/D1: canonical H1から完全UTC bucketだけを派生
- 欠損は記録。不完全bucketはdrop
- Forward Fill、期間延長、M15からのH1 tail復活は禁止
- Raw CSV、cache、資格情報をGitまたは公開Artifactへ保存しない

## 7. 次に行う単一作業

初期JNLP観測は完了して単一使用認可を消費した。次は、凍結済み5 exact URLを証拠としてremote runtime closureをどう検証するか、別の限定Gateと別ユーザー承認を事前設計・監査する。現時点ではどのURLもrequestしない。特に`https://platform.dukascopy.com/demo_3/libs_3.jnlp`、icon、JAR/resource、redirect先の取得、初期URLのrerun/replayは禁止する。

2026-09-01のA0〜A7監査で確認した境界:

- `ITesterClient`と既存acquirerはavailability、download、bar/price capabilityを含むため再利用禁止
- 将来runnerは別moduleの`IClient` + `Plugin`とし、価格callback surface自体を含めない
- owned codeで許可するprovider-data callは`getOfflineTimeDomains`だけ
- SDK内部のmarket bytes受信・cache persistenceは`UNPROVEN`であり、falseと主張しない
- 既存Gate C3は外部socket全面拒否のため、接続用に緩和せず別execution envelopeを作る
- classic seccompだけではdestinationを絞れないため、別network namespace＋exact destination default-denyが必要
- remote JNLP/runtime/endpointを発見したRunで自己認可せず、独立監査後の別Commitでallowlistを凍結する
- offline domainは公式上weekend intervalsであり、holiday、maintenance、Energy daily session、歴史的rule change、provider schedule versionの完全性は未証明

この前提証明が揃うまでmanual connection workflowをdispatchせず、Secretsも設定しない。24 schedule files、inventory、allowlistはまだ作らない。すべての段階で`acquisition_authorized=false`、`count_only_authorized=false`、Outcome未計算を維持する。

## 8. 残りの順序

1. 完了済み初期Runを再実行せず、remote runtime closure用の限定Gateを事前設計・監査する
2. 新たなexact URL requestごとに、別ユーザー承認を得てから単一使用workflowを実装する
3. remote runtime/provider version/API互換性を観測し、Run/Artifactを独立監査してさらに後の別Commitで凍結する
4. SDK内部market bytes/cache isolationとTOCTOU-resistant custodyを証明する
5. 別manual Gateでoffline-domain evidenceを観測し、完全性を独立証明する
6. Provider schedule exact allowlistをさらに後の別Commitで検証する
7. Energy roll/session metadataを価格非参照で固定する
8. すべてのBlocker解消後に、明示的な取得認可を別Gateで凍結する
9. JForexから48系列だけをsame-run private領域へ取得する
10. Actual Full-QCを実行しrawをcleanupする
11. Actual Full-QC PASS後も自動では進まず、別GateでCount-onlyを認可する
12. Count-only完了後にReturn検証する
13. 12仮説の共通ルールを抽出し、マルチタイムフレーム戦略へ進む

## 9. 絶対禁止

- Provider schedule未固定のままprice取得へ進む
- Gate単体で `acquisition_authorized=true` にする
- Phase 8の再最適化、結果を見た銘柄・時間足選択
- Frozen Entry、threshold、target、period、Gate、control、cost、episodeの変更
- M15で2019-08-28以降、H1で2019-08-01以降の照会・取得・cache
- Development、OOS、Final Holdoutの先行照会・取得・閲覧
- 欠損のForward Fill、期間延長、候補差替え
- Count-only完了前のReturn、符号、MFE、MAE、Edge、勝敗、勝率、Profit Factor、Drawdown、累積R、P値、信頼区間、順位、Outcome chartの生成・閲覧
- Phase 9 JSONを既存Outcome viewerへ読み込む
- Raw市場データ、cache、JAR、remote JNLP bytes、資格情報をCommitまたは公開Artifactへ保存
- MT5 EA実装

## 10. Git運用

- 作業前後にremote mainを確認
- サブエージェントはread-only監査
- GitHubへのCommitは主担当だけ
- Atomic Commit
- 明示pathだけを`git add -- <paths>`
- `git add .`、`git add -A`、force push、`reset --hard`、ユーザー変更破棄は禁止

## 11. 次セッションへ送る文章

コピー用全文は `NEXT_SESSION_PROMPT.md` を使用する。

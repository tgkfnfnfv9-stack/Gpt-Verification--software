# Phase 9 自動売買研究｜次セッション引き継ぎ

更新日: 2026-08-31
Repository: `tgkfnfnfv9-stack/Gpt-Verification--software`
基準Run: [S1B Gate A Run 33376110507](https://github.com/tgkfnfnfv9-stack/Gpt-Verification--software/actions/runs/33376110507)

## 最初に読む

1. `/AGENTS.md`
2. `PHASE9_OPERATIONS_GUIDE.md`
3. `PHASE9_DATA_ACQUISITION_VALIDATION_RUNBOOK.md`
4. `POLICY_INCIDENT_20260829.md`
5. `POLICY_INCIDENT_20260830.md`
6. `PROVIDER_ACQUISITION_BLOCKER.md`
7. `JFOREX_SOURCE_CHANNEL_AMENDMENT.md`
8. Phase 8 `results/PHASE8_FINAL_DECISION.json`
9. Phase 8 `results/RESULTS_SUMMARY.md`
10. `README.md`
11. `SESSION_STATE.json`
12. `DESIGN_DECISIONS.md`
13. `HYPOTHESIS_PORTFOLIO_FINAL.md`
14. `spec/candidate_registry.frozen.json`
15. `DATA_REQUIREMENTS.md`
16. `spec/data_requirements.frozen.json`
17. `policy/preregistered_research_policy.json`
18. `results/s1b-run-33376110507/S1B_AUDIT.json`

数値Entryはcandidate registry、取得outer boundaryはdata requirements、許可・禁止はpreregistered policyを正本とする。Markdown要約やdraftで凍結仕様を変更しない。H1の終了境界はouter authorizationをさらに狭めた運用上のfail-closed制約である。

## 研究状態

| 項目 | 現在値 |
|---|---|
| Phase 8正式仮説 | PA-002を含む16件、全件REJECT_FOR_DEVELOPMENT |
| Phase 9 formal alpha | 11件 |
| Phase 9 risk overlay | 1件 |
| Confirmatory questions | 12件、1 family |
| Phase 9 status | 全12件 `UNTESTED_PREREGISTERED` |
| Phase 9正式取得 | 未開始 |
| Phase 9価格ファイル | 0件 |
| Actual market Full-QC | 未実施 |
| Count-only Gate | 未開始 |
| Phase 9 outcome | 未計算・未閲覧 |
| 確認済みPhase 9優位性 | 0件 |
| MT5 EA | 禁止 |

2022〜2026年には旧非Phase9 workflowのアクセス履歴がある。Phase 9候補code・Phase 9 outcomeは実行・閲覧していないが、「将来期間へ一度もアクセスしていない」とは表現しない。後続splitの有効性は専用protocol凍結前に再監査する。

## S1B Gate A Run #2

- Run ID: `33376110507`
- Job ID: `99437846539`
- Artifact ID: `9751919672`
- Head SHA: `951c38aaa875180fa7dbbe498866a4e3ece50e9c`
- Workflow: `completed / success`
- Artifact ZIP SHA-256: `ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a`
- Artifact: exact metadata allowlist 9件、manifest対象8件のSHA一致
- Locked JAR: 116/116 SHA一致、合計66,837,102 bytes
- Source: Maven Central 94件、Dukascopy public repository 22件
- Redirect: なし
- Environment proxy: なし
- Maven/Java実行: なし
- Native候補: 28件
  - zstd-jni 18件
  - JNA 10件
  - ELF 18 / Mach-O 3 / PE 6 / suffix-only 1
- Run #1のJava `.class` `CAFEBABE`誤分類28,088件は除外済み
- Synthetic QC primitives: PASS
- Actual market data QC: 未実施
- Dukascopy・市場credential: 参照なし
- 外部JNLP request/launch: なし
- JForex connect: なし
- Market price request: なし
- 禁止期間request: なし
- Phase 9価格ファイル: 0
- Return/MFE/MAE/Edge/勝率/P値: 未計算
- Acquisition authorization: `false`

Run #2はlocked-JAR静的棚卸しの工学的PASSであり、実データ取得、Count-only、仮説検証の許可ではない。Run証跡は`results/s1b-run-33376110507/`へmetadata-onlyで保存している。

## 正式取得時の固定範囲

直接取得は次の48系列だけ。

`12銘柄 × M15/H1 × BID/ASK = 48系列`

- FX8: AUDJPY、AUDUSD、EURGBP、EURJPY、EURUSD、GBPJPY、GBPUSD、USDJPY
- Metals2: XAUUSD、XAGUSD
- Energy2: BRENTCMDUSD、LIGHTCMDUSD
- M15: `[2013-01-01T00:00:00Z, 2019-08-28T00:00:00Z)`
- H1: `[2013-01-01T00:00:00Z, 2019-08-01T00:00:00Z)`
- H4/D1: canonical H1から完全UTC bucketだけを派生し、終了は2019-08-01未満
- 欠損は記録し、不完全bucketをdropする
- Forward Fill、期間延長、M15からのH1 tail復活は禁止
- Raw市場CSV、cache、資格情報をGitまたは公開Artifactへ保存しない
- Private immutable raw storageは未承認。現状はsame-run一時領域＋Full-QC後削除だけ

## 残るBlocker

1. Run #2の28 native entryを別commitのexact-match Gate B allowlistとして未固定
2. Shaded runner未検査
3. 実際にloadされるnative/mapped DSO未検証
4. Child process、`System.load*`、write/cache mutation、OS egress default-deny未強制
5. Remote JNLP未観測・未lock。規約確認と別の明示的手動承認が必要
6. 48系列を読むstreaming Full-QC経路が未実装・未実行
7. Same-run ephemeral raw custodyまたは承認済みprivate immutable storageが未固定

Demo secrets設定、外部JNLP接続、JForex connect、availability照会、price取得はまだ禁止。

## 次に実行する1作業

Run #2の28 native entryを人手監査し、別commitでGate B exact-match allowlistを凍結する。

Gate Bには最低限、Run ID、head SHA、116-JAR manifest SHA、Artifact ZIP SHA、archive path/SHA、entry path/SHA/size/magic、対象OS/arch、未知・追加・欠落・重複・case collisionのfail-closed規則を固定する。同一Runの棚卸しで自己認可しない。Gate B完了だけでは実price取得を許可しない。

## 絶対禁止

- Phase 8の再最適化、結果を見た銘柄・時間足選択
- Frozen Entry、threshold、target、period、Gate、control、outcome、cost、episode変更
- Draftの実行
- M15で2019-08-28以降、H1で2019-08-01以降の照会・取得・cache
- Development、OOS、Final Holdoutの照会・取得・閲覧
- 欠損のForward Fill、期間延長、候補差替え
- Count-only完了前のreturn、符号、MFE、MAE、Edge、勝敗、勝率、PF、DD、累積R、P値、CI、順位、Outcome chartの生成・閲覧
- Phase 9 JSONを既存Outcome viewerへ読み込むこと
- Raw市場データ、download/cache、JAR本体、remote JNLP bytes、資格情報のCommit
- MT5 EA実装

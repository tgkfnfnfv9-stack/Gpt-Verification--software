# 次セッションへ送る文章

以下のコードブロックを、そのまま新しいセッションへ送る。

```text
GitHub Repository `tgkfnfnfv9-stack/Gpt-Verification--software` のPhase 9自動売買研究を引き継いでください。

最初にremote `main`を確認し、次のファイルを省略せず完全に読んでください。

1. `AGENTS.md`
2. `research/phase9-hypothesis-redesign-20260828/NEXT_SESSION_HANDOFF.md`
3. `research/phase9-hypothesis-redesign-20260828/SESSION_STATE.json`
4. `research/phase9-exploratory-fxcm-20260901/README.md`
5. `research/phase9-exploratory-fxcm-20260901/MULTI_TIMEFRAME_DATA_PLAN.md`
6. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_candidates_v1.frozen.json`
7. `research/phase9-exploratory-fxcm-20260901/results/run-33580789080/BLIND_MTF_COUNT_INDEPENDENT_AUDIT.json`
8. `research/phase9-exploratory-fxcm-20260901/results/run-33582968006/BLIND_MTF_RETURN_OOS_INDEPENDENT_AUDIT.json`
9. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_candidates_v2.frozen.json`
10. `research/phase9-exploratory-fxcm-20260901/results/run-33585508306/BLIND_MTF_BATCH2_COUNT_ONLY_INDEPENDENT_AUDIT.json`
11. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_batch2_return_oos_v1.frozen.json`
12. `research/phase9-exploratory-fxcm-20260901/results/run-33587536789/BLIND_MTF_BATCH2_RETURN_OOS_INDEPENDENT_AUDIT.json`

作業開始時点の基準remote commitは`6c7be3c06e69d9b758189ebcbaf281016e639468`です。ただし、必ず最新remote `main`を再確認してください。

## 最終目的

GPT側で複数銘柄・複数時間足の実データを使い、結果後の条件調整に頼らない本物の優位性を見つけることです。優位性が未見OOS・新期間・頑健性確認を通過した場合だけMT5化し、その後にGPT判断＋自動売買へ進みます。

データ取得や監査を無限に続けること自体が目的ではありません。Formal provider/JForex blockerは別trackとして保持し、Exploratory FXCMによる優位性探索を止めないでください。

## 取得・QC済みデータ

- Provider: FXCM CandleData（個人・非商用利用）
- 対象: `AUDJPY, AUDUSD, EURGBP, EURJPY, EURUSD, GBPJPY, GBPUSD, USDJPY`
- 期間: 2017-01-01 inclusive ～ 2018-12-31 exclusive
- direct取得: M1/H1 BID/ASK
- 生成: M1→M15、H1→H4/D1
- 完全UTC bucketのみ使用。不完全bucketはdrop/count。Forward Fill禁止
- 最終構成: FX8 × M15/H1/H4/D1 × BID/ASK = 64系列
- MTF QC Run: `33508634314`、完了・成功
- 価格データは各Run内でcleanup済み。Git/Artifactへ永続保存していない

## 完了済み探索

### Blind MTF Batch 1

- 301: Count 166、REJECT
- 302: Count 455、Count PASS → Return/OOS REJECT
- 303: Count 92、REJECT
- 304: Count 494、Count PASS → Return/OOS REJECT

Return/OOS Run `33582968006`:

- 302: IS mean R `-0.1384168981`、OOS mean R `0.0903906529`、OOS PF `1.1100053237`、bootstrap lower `-0.2371380984`
- 304: IS mean R `-0.1230096695`、OOS mean R `-0.105445562`、OOS PF `0.9120453609`、bootstrap lower `-0.4688187438`
- edge PASS 0件

### Blind MTF Batch 2

- 305: Count 441、Count PASS → Return/OOS REJECT
- 306: Count 51、REJECT
- 307: Count 52、REJECT
- 308: Count 260、REJECT

Count Run `33585508306`、Return/OOS Recovery Run `33587536789`は完了・成功。

305 Return/OOS:

- completed outcomes: 420/441
- 2017 IS mean R: `-0.1628590969`
- 2018 OOS mean R: `-0.3253655373`
- OOS PF: `0.7470933829`
- 累積3候補Bonferroni補正済みbootstrap lower: `-0.7277185378`
- OOS positive instruments: 4/8
- OOS positive quarters: 0/4
- edge PASS: false

初回Return workflowのRun `33587087527`はcheckout中cancel、重複Run `33587087557`はskip。両方とも取得・Return・Outcome・Artifact 0であることを監査済みです。その後、統計仕様を変えずRecovery Run `33587536789`を実行しています。

## 現在地

- Outcome検定済み探索候補: 302、304、305の3件
- 3件すべて正式に不採用
- 確認済みExploratory edge: 0件
- 301/303/306/307/308もCount Gate不通過で不採用
- 失敗候補のthreshold、direction、symbol、timeframe、exit horizon変更による救済は禁止
- MT5 EA実装はまだ禁止

## 次の単一作業

302/304/305の派生・微調整ではない、新しい独立mechanismの価格MTF仮説Batch 3を、Countを見る前に事前登録してください。

最低条件:

1. 既存301～308とのmechanism重複を明示的に検査する
2. 仮説、方向、対象8銘柄、使用時間足、閾値、重複排除、Count Gateを結果閲覧前に凍結する
3. Count-only専用workflowを実装する
4. Count-only RunではReturn、Return符号、MFE、MAE、勝敗、勝率、PF、Drawdown、P値、信頼区間、順位、Outcomeを計算・表示しない
5. Count通過候補だけを後続の別Return/OOS Gateへ進める
6. 後続Return/OOSでは、既にOutcomeを検定した3候補も含む累積多重検定補正を必須とする
7. 通過しない候補は救済しない

新しいBatchは、少なくとも以下のように既存候補とは異なる独立mechanismを優先して検討してください。

- 過伸展後の平均回帰
- 失敗ブレイク後の反転
- 時刻固定のsession効果。ただし301のAsia range break-retestとは重複させない
- 複数通貨ペアの同時breadthを使うcross-pair確認

候補数を増やすこと自体を目的にせず、経済的・市場構造上の理由を説明できる仮説だけを事前登録してください。

## 厳守事項

- 取得/QC → Count-only → Return/OOS → 新期間・頑健性 → MT5のGate順序を守る
- 結果を見た後の閾値変更、銘柄限定、方向限定、exit変更は禁止
- 価格CSV、cache、資格情報をGitや公開Artifactへ保存しない
- `audit/`などユーザー所有の未追跡変更へ触れない
- `git add .`、`git add -A`、force push、reset --hardは禁止
- Commit対象を明示的にstageし、remote head・tree一致まで確認する
- Formal Phase 9とExploratory FXCMを混同しない
- Formal 12市場のprovider schedule、Energy metadata、JForex runtime closureは未解決の別track

まず「何を新規仮説として選び、なぜ既存301～308と独立なのか」を短く示し、その後は事前登録、実装、Tests、GitHub公開まで止まらず進めてください。手動workflowが必要になった時点で、リンクと入力値をコピー可能な形で提示してください。
```

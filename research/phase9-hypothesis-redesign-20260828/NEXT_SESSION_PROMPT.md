# 次セッションへ送る文章

以下のコードブロックを、そのまま新しいセッションへ送る。

```text
GitHub Repository `tgkfnfnfv9-stack/Gpt-Verification--software` のPhase 9自動売買研究を引き継いでください。

最初に最新remote `main`を確認し、次のファイルを省略せず完全に読んでください。

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
13. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_candidates_v3.frozen.json`
14. `research/phase9-exploratory-fxcm-20260901/results/run-33591731464/BLIND_MTF_BATCH3_COUNT_ONLY_INDEPENDENT_AUDIT.json`
15. `research/phase9-exploratory-fxcm-20260901/spec/fxcm_blind_mtf_batch3_return_oos_v1.frozen.json`
16. `research/phase9-exploratory-fxcm-20260901/runner/fxcm_blind_mtf_batch3_return_oos.py`
17. `.github/workflows/phase9-exploratory-fxcm-blind-mtf-batch3-return-oos.yml`

必ず最新remote `main`を再確認し、workflowが公開済みのcommitと一致することを確認してください。

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

- 301: Count 166、REJECT
- 302: Count 455、Return/OOS REJECT
- 303: Count 92、REJECT
- 304: Count 494、Return/OOS REJECT
- 305: Count 441、Return/OOS REJECT
- 306: Count 51、REJECT
- 307: Count 52、REJECT
- 308: Count 260、REJECT
- Outcome検定済み302/304/305は全件不採用
- 確認済みExploratory edgeは0件

## Batch 3 Count-only完了

Run `33591731464`（Run #1 / attempt #1）は全step success。Artifact `9832271295`、
ZIP SHA-256 `d518961c48852a450c587dde85ab4f62f288408c35bfddc1764126baae9ae068`。
exact 2 files、manifest、価格0、Return/Outcome未計算を独立監査済みです。

- 309: primary 22、active dates 20、REJECT
- 310: primary 157、active dates 148、REJECT
- 311: primary 280、active dates 237、Count PASS
- 312: primary 1028、active dates 516、Count PASS

309/310は救済しません。311/312だけを次のReturn/OOS Gateへ進めます。

## Return閲覧前に凍結済みのBatch 3 Gate

- 対象: 311、312だけ
- Return/Outcome閲覧前の凍結: true
- entry: signalで固定済みの次H1 bar open
- exit: entryから正確に12時間後のH1 open
- LONG: ASK entry / BID exit
- SHORT: BID entry / ASK exit
- normalization: entry前H1 mid ATR14
- split: 2017 IS / 2018 OOS（entry UTC year）
- bootstrap: UTC entry-date cluster、20,000回
- multiplicity: 過去302/304/305を含む累積5候補Bonferroni
- one-sided alpha each: 0.01（99% lower bound）
- minimum OOS outcomes: 120（Countだけを見てReturn前に固定）
- passはcompletion、IS/OOS平均、bootstrap下限、PF、銘柄breadth、四半期breadthの全条件必須
- Artifactはsummaryのみ。価格、trade row、signal/entry timestampを保存しない
- passしても次は別の新期間・頑健性Gate。MT5へ自動移行しない

## 次の単一作業

公開済みの`.github/workflows/phase9-exploratory-fxcm-blind-mtf-batch3-return-oos.yml`を
Run #1 / attempt #1として1回だけ手動実行してください。

実行リンク:
`https://github.com/tgkfnfnfv9-stack/Gpt-Verification--software/actions/workflows/phase9-exploratory-fxcm-blind-mtf-batch3-return-oos.yml`

入力値:

confirmation:
`RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH3_RETURN_OOS_2017_2018_V1`

usage_confirmation:
`I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA`

Run完了後はArtifactを独立監査し、凍結済みGateの全条件を候補別に再計算・照合してください。通過候補がある場合だけ新期間・頑健性確認へ進め、不通過候補は閾値、方向、銘柄、timeframe、exit horizonを変更して救済しないでください。

## 厳守事項

- 取得/QC → Count-only → Return/OOS → 新期間・頑健性 → MT5のGate順序を守る
- 結果を見た後の閾値変更、銘柄限定、方向限定、exit変更は禁止
- 価格CSV、cache、資格情報をGitや公開Artifactへ保存しない
- `audit/`などユーザー所有の未追跡変更へ触れない
- `git add .`、`git add -A`、force push、reset --hardは禁止
- Commit対象を明示的にstageし、remote head・tree一致まで確認する
- Formal Phase 9とExploratory FXCMを混同しない
- Formal 12市場のprovider schedule、Energy metadata、JForex runtime closureは未解決の別track

まず最新remote、workflow SHA、single-use条件を確認し、実行リンクと入力値をコピー可能な形で提示してください。
```

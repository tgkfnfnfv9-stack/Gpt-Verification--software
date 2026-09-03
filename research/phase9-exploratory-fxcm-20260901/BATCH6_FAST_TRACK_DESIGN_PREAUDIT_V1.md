# Batch 6 Fast Track V1 — 設計・価格非参照事前監査

更新日: 2026-09-03  
対象Repository: `tgkfnfnfv9-stack/Gpt-Verification--software`  
監査対象main: `1c013f04a6217ff2db900519bd7963e5d745cc25`  
判定: `BLOCK_FAST_TRACK_EXECUTION_PENDING_P0_RESOLUTION`

## 結論

候補321〜324のFast Trackは、入力経路の設計までは作成したが、実装・価格参照・Count実行へ進めてはいけない。

旧Batch 6 workflowは恒久fail-closedのまま維持し、旧runnerも実行に再利用しない。価格取得、Drive内容読み取り、Drive変更、workflow dispatch、Count、Return/OOS、commit、pushは実施していない。

## 固定した範囲

| 項目 | 固定値 |
|---|---|
| 候補 | `EXP-P9-MTF-321`〜`324` |
| 銘柄 | FX8 |
| 期間 | `[2017-01-01T00:00:00Z, 2018-12-31T00:00:00Z)` |
| direct入力 | `m1`, `H1` |
| side | BID, ASK |
| 最終時間足 | M15, H1, H4, D1 |
| 経路A | 2 year manifest＋32 archive |
| 経路B | 1,664 source request |
| 最終系列 | 64 side-series |

`end_exclusive`は`2018-12-31T00:00:00Z`であり、2018-12-31の1日分は対象外である。`2019-01-01`へ広げない。

## P0停止理由

1. **候補323のfuture availabilityと窓長・時刻意味論**  
   旧scannerは、08:00時点では未確定の当日後半H1を含む「完成D1 bucketの存在」で月初日を選んでいる。また20日returnには21本のcloseが必要であり、20本ではoff-by-oneになる。08:00 H1が`bar-open`ならそのclose確定は09:00であるため、08:00の情報cutoffとentry時刻の関係も未確定である。月初日、20-return、ATR、decision/entryを因果的に事前固定できなければ323を差し替えず退役させる。

2. **episode定義と実装の不一致**  
   凍結仕様は`EARLIEST_SIGNAL_PER_OVERLAP_COMPONENT`だが、旧共有実装はUTC日×方向で銘柄横断の追加縮約を行い、overlapも推移閉包ではないgreedy処理である。candidate＋instrument＋direction単位の推移的componentとして事前固定する必要がある。

3. **候補323のCount Gate実現可能性が未証明**  
   共通の月初日かつ旧追加縮約を維持する条件では月最大2 episode、24か月で通常最大48となり、最低120件と整合しない。これは条件付きの上限であり、欠損や銘柄別日付で変わる。正しいcandidate＋instrument＋direction単位で得られる8銘柄×24か月＝192は、warm-up、欠損、シグナル不成立、episode重複をすべて無視した粗い機会上限にすぎず、実現可能なCount上限ではない。したがって最低120件の実現可能性は未証明のままであり、価格非参照の機会幾何証明を先に行う。

4. **独立mechanismの再監査が必要**  
   321は不採用319、324は不採用314と構造的に近い。凍結前に作成されたprovenance証拠で独立性を説明できなければ、Outcomeを追加閲覧せず、その候補を同Batch内で差し替えず退役させる。

5. **旧MTF基準は構造QC不合格**  
   m1派生H1とdirect H1のOHLC不一致4,297件、m1-only 4件、direct-H1-only 69,108件、provider schedule未証明である。旧validatorはstructural QC passを要求していない。

6. **Count runtimeが隔離されていない**  
   旧v6は複数世代runnerを動的importし、過去Return/OOS auditも読む。全依存SHAが固定されず、full checkout、既存results、Return codeへアクセスできる。

7. **cleanup証明が不正確**  
   旧workflowは取得途中失敗時にcleanupをskipし得る。さらに価格0件をcleanup前に自己申告している。

8. **未完了Drive transactionはcanonicalではない**  
   2017・2018がmetadata上完全でも、transaction全体は`ACQUIRING`である。Batch 6限定のread-only例外を版付きで固定し、別承認を得るまで内容を読まない。

9. **Vault V2のH4/D1 completeness判定に欠陥がある**  
   既存H1 timestampをgroup化しているため、H4の3/4本やD1の23/24本でも完成扱いになり得る。期待timestamp集合を独立生成し、完全一致しないbucketを必ずdropする必要がある。

10. **候補324の96時間coverage意味論が未固定**  
    endpointだけを要求するか、内部96時間の全H1観測を要求するかでシグナル母集団が変わる。Count前に一方を固定し、既存凍結規則への追加になる場合はprospective amendmentとする。

## P0の閉鎖段階

P0は、閉鎖する段階を次の2種類に分ける。現在の設計版は実装を承認していないため、後者をこの版だけで閉じたとは扱わない。

| 閉鎖段階 | 対象 | 閉鎖条件 |
|---|---|---|
| 科学仕様P0 | 323のfuture availability、episode意味論、323のfrequency feasibility、mechanism独立性、direct H1をcanonicalとするMTF QC方針、324の96時間coverage | 実装着手前に、Outcomeを追加閲覧せずprospective仕様・根拠・テスト期待値を凍結して再監査PASS |
| control実装P0 | Count runtime隔離、cleanupとattestation、未完了transaction用の限定input control、Vault V2 H4/D1 completeness | 科学仕様P0の閉鎖後、別途承認された実装と価格非参照の静的監査でcontrolを完成させる。外部access・Count開始前にPASS必須 |

実データ固有のmanifest、archive、series identity、QC結果は、control実装P0を閉じた後も実行時Gateとして残り、実行時に不一致なら停止する。

## 入力経路の判断

P0解消後の第一候補は経路Aとする。

```text
科学仕様P0の修正・価格非参照再監査
        ↓ PASS
別承認によるcontrol実装・静的監査
        ↓ PASS
経路A1: 2017/2018 manifest 2件と32 archive identityを固定
        ↓ 別承認・PASS
経路A2: 32 archiveだけread → 独立QC → 一時64系列 → Count-only
        ↓
cleanup実測 → exact-schema sealer → 価格非包含Artifact
```

経路AでSHA、source identity、64系列identity、期間境界、QCのいずれかが不一致なら停止する。同じrunで経路Bへ切り替えない。

経路Bは別version、別workflow、別承認でのみ検討する。経路Aの承認をFXCM再取得へ流用しない。

## 科学仕様として実装前に固定する事項

- 候補323の因果的な月初判定
- 候補323の20-return＝21 close、08:00 bar-open、09:00 close確定、entry時刻
- 推移的overlap componentとepisode key
- 323の価格非参照frequency feasibility
- 321/319、324/314の独立性判断
- direct H1を唯一のcanonicalとし、m1派生H1は診断専用とするprospective QC amendment
- m1派生H1とのexact comparisonは必須だが、Count通過にexact equalityは要求しない根拠とテスト
- source parse/hash/QC/aggregationはDecimal、Count midpointはlegacy IEEE-754 binary64とする数値境界
- 旧64系列identityとの完全一致Gate
- 候補324のendpoint-only対full-96h coverageの事前固定
- 候補321・322で「観測上連続するH1」が実時間gapをまたいでよいかの事前固定
- 2017〜2018を反復して仮説生成に使用しているため、今回結果はprogram-levelの untouched OOSではなくexploratoryであることの固定

## 別承認後の実装・静的監査で閉じる事項

- self-contained Count-only runnerと完全なclosure SHA
- network、repository、既存resultsを持ち込まないCount runtime
- `additionalProperties: false`相当の再帰的exact出力schema
- 全失敗経路のlocal cleanupとcleanup後sealing
- 未完了transactionからの2 manifest＋32 archive限定read-only control
- 各archiveがexact 54 regular members（payload manifest、canonical CSV、52 source gzip）であること、32 archive全体の1,664 source member identity、およびsafe extraction・duplicate/unknown member拒否
- H4/D1の期待timestamp集合による完全性検査

## 今回作成したファイル

- `BATCH6_FAST_TRACK_DESIGN_PREAUDIT_V1.md`
- `spec/fxcm_blind_mtf_batch6_fast_track_design_v1.frozen.json`
- `runner/verify_fxcm_blind_mtf_batch6_fast_track_design.py`
- `tests/test_fxcm_blind_mtf_batch6_fast_track_design.py`
- `results/batch6-fast-track-design-v1/BLIND_MTF_BATCH6_FAST_TRACK_DESIGN_INDEPENDENT_AUDIT.json`

専用testは10件すべてPASS。実装runner、実行workflow、execution contractは作成していない。

## 次に必要な確認

最初に必要なのは、上記の**停止判定を含む設計・事前監査だけをGitHubへ反映してよいか**の確認である。反映を承認しても、価格参照、Drive access、実装、workflow dispatch、Count、Return/OOSは承認されない。

その後、P0を解消する科学仕様のprospective再登録範囲を提示し、別途確認を得る。

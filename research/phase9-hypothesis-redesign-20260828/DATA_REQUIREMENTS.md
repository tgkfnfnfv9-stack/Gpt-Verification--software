# Phase 9 必要データと取得前Gate

更新日: 2026-08-28
状態: `DRAFT_NOT_DOWNLOADED`

## 1. 現在の方針

Phase 9候補は未凍結・未検証である。候補一覧、数値条件、対象銘柄、時間足、期間、
Matched Control、multiple-testing Gateを凍結するまで市場データを取得・検証しない。

GitHubには次を保存する。

- データ取得仕様
- 使用銘柄・期間・時間足
- point-in-time情報ルール
- 取得スクリプトとversion pin
- 行数、期間、欠損状況
- ファイルごとのSHA-256
- 検証コード、検証結果、decision log

生の市場CSVは容量・利用条件・再現性の問題があるためGitHubへcommitしない。
GitHub Actionsで再取得可能にし、必要な場合だけ短期保存Artifactとして扱う。

## 2. 必須銘柄

### FX

- AUDJPY
- AUDUSD
- EURGBP
- EURJPY
- EURUSD
- GBPJPY
- GBPUSD
- USDJPY

### Precious Metals

- XAUUSD
- XAGUSD

### Energy

- BRENTCMDUSD
- LIGHTCMDUSD（WTI）

銘柄は結果を見て追加・除外しない。データ自体が存在しない場合は、returnを計算する前に
`DATA_UNAVAILABLE`として記録し、対象集合の変更は再登録を必要とする。

## 3. 必須期間

| 用途 | 期間 | 状態 |
|---|---|---|
| Warm-up候補 | 2013-01-01〜2014-08-27 | 提案・未取得 |
| Phase 9 Discovery候補 | 2014-08-28〜2019-08-27 | 提案・未取得 |
| Phase 8で見た期間 | 2019-08-28〜2022-08-27 | Phase 9仕様選択には汚染済み。昇格根拠に使わない |
| Development / Walk Forward | 2022-08-28〜2024-08-27 | 未取得・未開封 |
| Strict OOS | 2024-08-28〜2025-08-27 | 未取得・未開封 |
| Final Holdout | 2025-08-28〜2026-08-28 | 未取得・未開封。最終Gate前は絶対に開けない |

Warm-upはD1の252本percentile、120日pair formation、60日momentum、
M15/H1/H4の240本rolling statisticsをDiscovery初日から計算するために必要である。

期間境界はすべてUTCで、終了日はexclusiveとして実装する。

## 4. 基本市場データ

全銘柄について最低限、M15とH1の以下を取得する。

| 項目 | 必須内容 |
|---|---|
| Timestamp | UTC、bar open time、timezone付きまたはUTC明記 |
| BID OHLC | Open / High / Low / Close |
| ASK OHLC | Open / High / Low / Close |
| Tick Volume | 同じ定義で連続取得。true exchange volumeとは呼ばない |
| Spread | ASK Open − BID Open。可能ならbar内spread統計も保持 |
| Source metadata | provider、instrument ID、取得version、取得日時 |

H4とD1はM15/H1から決定的に集計し、BIDとASKを混ぜない。

- Open: 最初のbar
- High: 最大値
- Low: 最小値
- Close: 最後のbar
- Tick Volume: 合計
- 欠損barを含む集計bucketは作らない
- D1境界は00:00 UTC

## 5. 候補別の追加データ

| 候補 | 追加データ | 取得できない場合 |
|---|---|---|
| PS-204 | 00:00〜10:00 UTCの欠損のないM15/H1 | その日を無効化 |
| LV-201/203/204 | 同一UTC slotのtick volume履歴 | 候補を検証不能とする |
| LV-201/204 | point-in-timeのBID/ASK spread | spreadを後から固定値で代用しない |
| RR-201/202 | FX8銘柄の同一timestamp同期bar | 1銘柄でも欠けたtimestampを無効化 |
| RR-203 | XAUUSD/XAGUSDの同期H4・D1 | 欠損期間を無効化 |
| RR-204 | Brent/WTI同期H4・D1、roll/session metadata | roll歪みを識別できなければ候補保留 |
| RR-205 | historical 1か月forward pointsまたはpoint-in-time broker financing | 取得不能なら結果を見る前に候補を削除・差し替え |

RR-205では中央銀行政策金利だけをtradable carryとして使用しない。

## 6. OANDA MT5との対応確認

Discovery sourceと最終運用先で次を対応表にする。

- 銘柄名
- 最小価格単位
- contract size
- lot step
- 最小lot
- 取引時間
- 平常spread
- commission
- financing / swap
- metals・energyのrollまたはfinancing条件
- stop level / freeze level

これはDiscoveryのentry edgeを作るためではなく、OANDA MT5で実際に再現可能かを判定するために使う。

## 7. データ品質Gate

Returnを計算する前に、各fileへ次を実行する。

1. timestamp昇順、重複0件
2. `High >= max(Open, Close)`、`Low <= min(Open, Close)`
3. 価格とvolumeが非負、価格0を禁止
4. ASK Open >= BID Open
5. 期待bar間隔とのgap一覧を出力
6. 最初・最後のtimestamp、行数を記録
7. UTC session別の欠損率を記録
8. 全fileのSHA-256を記録
9. cross-market候補の同期可能bar数を、return計算前に記録
10. Energyのroll候補日をreturn計算前に記録

品質Gate不合格を理由に、成績を見て銘柄や時間足を除外してはいけない。

## 8. GitHubへ残す予定の取得成果物

```text
research/phase9-hypothesis-redesign-20260828/
├── data_manifest/
│   ├── source_versions.json
│   ├── row_counts.txt
│   ├── sha256.txt
│   ├── gaps.json
│   ├── cross_market_overlap.json
│   └── energy_roll_inventory.json
├── runner/
│   ├── acquire_phase9_data.py
│   ├── validate_phase9_data.py
│   └── aggregate_phase9_timeframes.py
└── results/
    └── discovery結果（仮説凍結後のみ）
```

現時点では上記の生データ取得をまだ実行しない。

## 9. データ取得を開始できる条件

- 最終候補数を確定
- PS-201とLV-202を統合するか決定
- LV-204を独立仮説として残すか決定
- RR-205のcarry data可用性をreturn閲覧前に決定
- Candidate Registryを`FROZEN_PREREGISTERED`へ変更
- Discovery期間とWarm-up期間を確定
- sample-size Gateとmultiple-testing補正を確定
- GitHubへ凍結commitを作成

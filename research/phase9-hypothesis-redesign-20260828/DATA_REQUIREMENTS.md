# Phase 9 必要データと取得前Gate

更新日: 2026-08-29  
状態: `FROZEN_PREREGISTERED_NOT_DOWNLOADED`

## 許可された取得範囲

```text
2013-01-01T00:00:00Z <= timestamp < 2019-08-28T00:00:00Z
```

Warm-upは2013-01-01〜2014-08-28 exclusive、Discoveryは2014-08-28〜2019-08-28 exclusiveです。2019-08-28以降のPhase 8期間、Development、OOS、Final Holdoutはavailability照会、一括download、cache作成も禁止します。

## 対象と基本系列

- FX8: AUDJPY、AUDUSD、EURGBP、EURJPY、EURUSD、GBPJPY、GBPUSD、USDJPY
- Metals: XAUUSD、XAGUSD
- Energy: BRENTCMDUSD、LIGHTCMDUSD
- Provider M15 BID/ASK OHLCとtick volume
- Provider H1 BID/ASK OHLCとtick volume
- H4/D1はcanonical H1だけからUTC固定bucketで決定的集計
- M15/H1は直接系列を使用し、H4/D1にM15とH1を混在させない
- 欠損bucketは作らず、forward fillしない
- tick volumeをtrue exchange volumeまたはsigned flowと呼ばない

## 候補別追加要件

| 対象 | 追加要件 |
|---|---|
| PS-204 | 00:00〜10:00 UTCの完全なM15/H1 |
| LV-201/203 | 過去40 trading-dayの同一UTC slot tick volume |
| LV-201 | point-in-time BID/ASK spread |
| LV-202 | 12本median TR、lagged 240本percentile、20本boundary |
| RR-201/202 | FX8の同一timestamp同期 |
| RR-203 | 金銀の同期H4/D1と両脚cost |
| RR-204 | Brent/WTI同期H4/D1、roll/session metadata、両脚cost |
| RISK-P9-RO-201 | PS-205 H4 timestamp、RV20、managed/unitのpaired execution |

## Return計算前Gate

1. provider、version、instrument mapping、trading calendarをcommit
2. timestamp昇順、重複0
3. OHLC geometry、正価格、非負volume
4. BID/ASK非交差
5. gap、row count、first/last timestamp、session missingness
6. SHA-256
7. cross-market同期bar数
8. Energy roll inventory
9. H1からH4/D1へのbucket完全性
10. Entry feature、signal flag、episode ID、control availability、group countだけでcoverage Gate

Coverage不足は`REJECT_AS_UNDERPOWERED`、p=1です。returnは計算せず、閾値緩和・銘柄/時間足削除・期間延長・候補差し替えを行いません。

## GitHubへ保存

取得・検証script、provider/version、row counts、gap、同期状況、roll inventory、SHA-256、結果を保存します。生の巨大市場CSV、認証情報はcommitしません。

OANDAのcontract size、lot、spread、commission、financing/swap、roll、stop/freeze levelは将来の実運用cost検証用として維持します。全Gate通過前にEAを実装しません。

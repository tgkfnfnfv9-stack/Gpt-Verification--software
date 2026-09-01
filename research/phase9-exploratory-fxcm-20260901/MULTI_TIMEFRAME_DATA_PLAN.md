# Phase 9 FXCMマルチタイムフレーム・データ計画

更新日: 2026-09-01

## 結論

現在取得済みなのはFX8のH1だけであり、このままではD1/H4/H1/M15を使った完全なマルチタイムフレーム検証はできない。

次はFXCM公式CandleDataから同じ8通貨ペアの`m1`と`H1`を取得し、M15、H4、D1を決定論的に生成する。最終的に必要な価格系列は次の64系列である。

```text
8銘柄 × 4時間足（M15/H1/H4/D1）× 2 side（BID/ASK）= 64系列
```

## データフロー

```text
FXCM direct m1
  ├─ 15本完全bucket → M15（エントリータイミング）
  └─ 60本完全bucket → H1照合専用QC

FXCM direct H1
  ├─ そのまま       → H1（セットアップ確認）
  ├─ 4本完全bucket  → H4（構造・押し目・レンジ）
  └─ 24本完全bucket → D1（相場環境・大局方向）
```

不完全bucketは補完せずdropして件数を記録する。Forward Fill、価格補間、将来データによるbucket完成は禁止する。

## 必要なデータ

| 項目 | 内容 |
|---|---|
| Provider | FXCM MarketData CandleData |
| 銘柄 | AUDJPY、AUDUSD、EURGBP、EURJPY、EURUSD、GBPJPY、GBPUSD、USDJPY |
| 期間 | 2017-01-01 inclusive ～ 2018-12-31 exclusive |
| 直接取得 | m1、H1 |
| 生成 | M15、H4、D1 |
| Side | BID、ASK |
| 最終系列 | 64系列 |
| 予定source objects | 1,664件（m1 832件＋H1 832件） |
| Timezone | UTC |
| Volume | FXCM無料CandleDataでは利用不可 |

## 取得済みH1

Run `33482595275`で、FX8・H1・2017–2018を取得・QC済み。

- Source objects: 832件
- Observed bars: 98,910本
- Usable bars: 97,644本
- `ASK Open < BID Open`: 1,266本をBID/ASK両方とも隔離
- Artifact: `9790552032`
- Artifact ZIP SHA-256: `42c0f5c6d42cfd94eef1cee1c9850f91db8cd64718e2739f1083227de36705ae`
- Raw prices: same-run QC後に削除済み

これは取得失敗ではない。ただしH1だけなのでMTF研究は未開始であり、異常1,266本があるためFormal Full-QC PASSでもない。

## MTFで優位性を探す順序

```text
D1 regime
  ↓
H4 structure / pullback / range
  ↓
H1 setup
  ↓
M15 entry trigger
  ↓
Count-only coverage Gate
  ↓
Return / cost stress / OOS validation
```

1. D1でtrend、range、volatility regimeを分類する。
2. H4で押し目、戻り、breakout前後、range位置を判定する。
3. H1で事前登録済みsetupの成立を判定する。
4. M15でentry timingを確定する。
5. 最初はsignal件数だけを集計し、データ不足・極端な偏りを確認する。
6. Count-only完了後に限り、Return、勝率、Profit Factor、Drawdown、cost stressを計算する。
7. 銘柄別結果を見てルールを変更せず、共通ルールの再現性をOOSで確認する。

## QC必須条件

- CSV schema完全一致
- UTC timestamp厳密昇順、重複なし
- finiteかつ正のOHLC
- `High >= max(Open, Close, Low)`、`Low <= min(Open, Close, High)`
- BID/ASK timestamp完全一致
- `ASK Open < BID Open`は価格修正せず隔離
- m1→M15は15本完全bucketのみ
- m1→H1とdirect H1を完全bucketで照合
- H1→H4は4本、H1→D1は24本完全bucketのみ
- gap、drop、異常件数とSHA-256を記録
- Forward Fillなし
- Return・Outcomeを取得/QC Runで計算しない

## GitHubに保存するもの／しないもの

GitHubへ保存する:

- 取得・集約・QCコード
- 凍結データ要件
- Run ID、Job ID、head SHA、Artifact ID
- source/output SHA-256
- bar count、first/last、gap/drop/異常件数
- 価格を含まないQC結果

GitHubへ保存しない:

- rawまたは派生価格CSV
- gzip price objects
- 全timestamp列
- FXCM資格情報
- Return、勝率などのOutcome（Count-only完了前）

## 未解決範囲

FXCM無料CandleDataは21 FXペアのm1/H1/D1であり、次は含まれない。

- XAUUSD
- XAGUSD
- BRENTCMDUSD
- LIGHTCMDUSD
- tick volume

したがって、まずFX8の64 MTF系列を取得・QCする。その後、金銀・EnergyはFXCM APIまたは別の事前固定providerから取得し、provider差を混ぜず別trackとして検証する。

## 次セッションの最初の単一作業

`spec/fxcm_multitimeframe_data_requirements.frozen.json`に完全一致するFX8 m1/H1取得＋M15/H4/D1生成＋QC workflowを実装し、GitHub Actionsで1回実行する。

このRunでは価格取得と品質検査だけを行い、signal count、Return、MFE、MAE、勝敗、勝率、Profit Factor、Drawdown、P値、順位、Outcome chartは計算しない。

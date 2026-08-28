# Primary Research Notes

参照日: 2026-08-28

## 1. Time-series momentum

- Moskowitz, Ooi and Pedersen, *Time Series Momentum*
  Journal page: https://www.sciencedirect.com/science/article/pii/S0304405X11002613
  Author PDF: https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
- 対象はequity index、currency、commodity、bond futuresで、主な継続時間軸は1〜12か月。
- Phase 9への含意: 12時間のbreakoutを同じ現象と呼ばず、D1の20日・60日方向をregimeとして使う。
- 限界: 論文はOANDA spot/CFDのM15/H1 execution edgeを保証しない。

## 2. Currency cross-sectional momentum

- Menkhoff et al., *Currency Momentum Strategies*
  BIS Working Paper 366: https://www.bis.org/publ/work366.htm
- 過去winner/loser currency間のcross-sectional return差を研究し、取引コストが一部を説明する。
- Phase 9への含意: 全USD/JPY pairの同方向breadthではなく、currency strengthの相対順位を使う。
- 限界: 週次・月次portfolio研究をH4 entryへそのまま移植しない。D1 regimeとH4 triggerを分離する。

## 3. Carry and momentum

- Burnside, Eichenbaum and Rebelo, *Carry Trade and Momentum in Currency Markets*
  NBER Working Paper 16942: https://www.nber.org/system/files/working_papers/w16942/w16942.pdf
- carryとmomentumは別のcurrency strategyとして検討され、両方のcost/riskを含める必要がある。
- Phase 9への含意: RR-205ではspot OHLCからcarryを推測せず、historical forward pointsまたは再現可能なfinancing seriesを必須にする。
- 限界: policy-rate differentialは実際のtradable carryの代用として不十分。

## 4. Order flow and FX price dynamics

- Chaboud et al., *Order Flow and Exchange Rate Dynamics in Electronic Brokerage System Data*
  Federal Reserve IFDP: https://www.federalreserve.gov/econres/ifdp/order-flow-and-exchange-rate-dynamics-in-electronic-brokerage-system-data.htm
- 電子brokerageのorder flowと短期FX returnの関係を扱う。
- Phase 9への含意: retail tick volumeをsigned order flowと同一視しない。LV候補ではvolumeを参加度proxyとしてのみ扱い、price confirmationとspread正常性を別に要求する。

## 5. Pair relative value

- Gatev, Goetzmann and Rouwenhorst, *Pairs Trading: Performance of a Relative-Value Arbitrage Rule*
  NBER Working Paper 7032: https://www.nber.org/system/files/working_papers/w7032/w7032.pdf
- normalized price distanceを用いたpair formation/tradingを検討する。
- Phase 9への含意: 24時間return差だけでなく、長いformation window、hedge ratio、residual、mean-reversion stabilityをentry前に測る。
- 限界: equity pairsの結果は金銀・Brent/WTIへ直接一般化できない。

## 6. Volatility as a state variable

- Engle, *Risk and Volatility: Econometric Models and Financial Practice*
  American Economic Association: https://pubs.aeaweb.org/doi/10.1257/0002828041464597
- Moreira and Muir, *Volatility Managed Portfolios*
  NBER Working Paper 22208: https://www.nber.org/papers/w22208
- Phase 9への含意: realized volatilityの上昇自体から方向を予測せず、position size、entry許可、risk budgetへ使う。
- 限界: volatility scalingの有効性とintraday entry edgeは別の検証対象である。

## 7. Sampling and microstructure noise

- Aït-Sahalia, Mykland and Zhang, microstructure noise and sampling frequency
  Federal Reserve IFDP 905: https://www.federalreserve.gov/pubs/ifdp/2007/905/ifdp905.htm
- Phase 9への含意: M15/H1/H4のbar数固定と12時間の実時間固定を区別し、低い時間足ほどspread/slippage感応度を厳しくする。

## 採用しなかった外挿

- 長期momentum論文を根拠にM15 breakout continuationを正当化しない。
- institutional order-flow研究を根拠にtick volumeをsigned flowと呼ばない。
- equity pairsの成績をBrent-WTIやGold-Silverの期待収益として入力しない。
- carry候補をpolicy rateだけで検証しない。

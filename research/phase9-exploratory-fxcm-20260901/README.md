# Phase 9 Exploratory FXCM Fast Track

Status: `FX8_H1_ACQUISITION_QC_ONLY_NOT_FORMAL_PHASE9`

This track makes a real, provider-authorized data path executable without
pretending that it completes Formal Phase 9.

- Source: FXCM official `fxcm/MarketData` CandleData endpoint
- Pinned source repository head: `924393dd545fab187527d95ef8b1178284b274b6`
- Instruments: Formal FX 8 only
- Source bars: direct H1 Bid/Ask OHLC
- Period: 2017-01-01 through 2018-12-31 exclusive
- Persistent output: bounded QC/inventory metadata only

FXCM's official README publishes the URL template, 2017--2020 coverage and
Python download examples. The selected years are inside Formal Phase 9's outer
allowed interval. Raw files, canonical prices and full observed-timestamp lists
remain in `RUNNER_TEMP` and are deleted after same-run integrity QC.

This is partial exploratory infrastructure. It has no Formal authorization
effect and does not satisfy the missing XAUUSD, XAGUSD, Brent or WTI inputs,
M15 input, provider schedule, Energy roll metadata, Count-only Gate or Full-QC.
Observed timestamps are not an independent provider schedule.

No signals or outcomes are calculated. Returns, return signs, MFE, MAE, edge,
wins, win rate, Profit Factor, drawdown, cumulative R, p-values, confidence
intervals, rankings and outcome charts are absent by construction.

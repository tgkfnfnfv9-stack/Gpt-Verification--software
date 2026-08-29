# Phase 8 仮説レビュー

## 結論

Phase 8の15件は、閾値の微調整で救う段階ではない。多くはSensitivityでも符号が変わらず、
Signal Return自体が負だった。改善は旧IDの再最適化ではなく、情報構造・時間軸・確認方法を
変えた新しい仮説としてのみ行う。

## 共通の失敗原因

1. **継続仮説への偏り**: 15件中12件が短期継続を予想し、同じ失敗因子へ集中した。
2. **確認前に入る**: breakout、volume shock、squeeze、wickを信号バーだけで判断した。
3. **時間軸の不一致**: 数日〜数か月で報告されるmomentumを、M15/H1/H4の12時間へ直接縮めた。
4. **相対値ではなく共通方向を追った**: USD/JPY/commodity breadthは同期後の高値掴みになり得た。
5. **tick volumeの季節性未調整**: UTC時刻、曜日、銘柄別の平常参加度との差を十分に分離しなかった。
6. **pair spreadが静的**: Brent-WTIを単純な24時間リターン差で扱い、動的hedge ratioと平均回帰速度を使わなかった。
7. **relative edgeと絶対収益を混同し得る設計**: VV-104はcontrolより良かったが、12時間Signal Returnは負だった。

## 旧候補ごとの処置

| 旧ID | 判定 | 処置 | Phase 9との関係 |
|---|---|---|---|
| PA-101 | REJECT | PA-102と統合して再設計 | PS-201はbreak直後ではなくretest確認後のみ。旧閾値の調整ではない |
| PA-102 | REJECT | PA-101へ統合 | 単独のNR7/inside-barという形状依存を廃止 |
| PA-103 | REJECT | 再設計 | PS-203はD1/H4 regimeと構造的再加速を要求 |
| PA-104 | REJECT | 廃止 | 3本連続という短期形状に独立した改善根拠がない |
| PA-105 | REJECT | 廃止 | session breakout continuationは再利用しない。PS-204は「失敗とrange復帰」を別イベントとして新設 |
| VV-101 | REJECT | 再設計 | LV-201は生volume比ではなく同一UTC slotの季節調整残差とspread正常性を使用 |
| VV-102 | REJECT | 再設計 | LV-202はreleaseそのものではなく、release後のretest保持を要求 |
| VV-103 | REJECT | 再設計 | LV-203はwickだけで反転せず、次バーのmidpoint回復を要求 |
| VV-104 | REJECT | 旧仮説は廃止 | LV-204は低volume expansionの閾値変更ではなく、illiquidity残差・peer非確認・reclaimの複合仮説 |
| VV-105 | REJECT | 方向予測として廃止 | LV-205ではvolatilityを方向ではなくexposure調整に限定 |
| MR-101 | REJECT | 廃止 | broad USD continuationは再利用しない |
| MR-102 | REJECT | 廃止 | broad JPY continuationは再利用しない |
| MR-103 | REJECT | 廃止 | 金銀の同方向momentumを捨て、RR-203はhedged residual回帰を新設 |
| MR-104 | REJECT | 再設計 | RR-204は24時間差ではなく長期rolling beta residualとhalf-lifeを使用 |
| MR-105 | REJECT | 廃止 | 金属とenergyを同一方向へ束ねる仮説を再利用しない |

## 改善可能と判断した内容

- **確認の追加**は、旧閾値の最適化ではなく、entry時点を「現象発生」から「現象確認」へ移す変更である。
- **長期regimeとの整合**は、短期momentumを延命するのではなく、既存研究と同じ時間軸へ戻す変更である。
- **季節調整**はtick volumeの測定誤差を減らす変更で、方向を結果に合わせる変更ではない。
- **動的hedge residual**は共通betaを除去し、pair relative valueを測る対象そのものを修正する。
- **volatility sizing**はvolatilityを方向signalとして使わず、risk stateとして扱う。

## 改善不可と判断した内容

- M15だけ、H1だけ、特定銘柄だけを採用すること。
- Phase 8で良かった方向へentry sideを反転すること。
- VV-104のvolume閾値、range閾値、時間足を調整すること。
- MR-104のH1/H4だけを使うこと。
- 旧Discovery期間を繰り返し実行し、最も良い仕様をPhase 9として登録すること。


## Phase 9事前登録時の追加処置（2026-08-29）

- Draft PS-201は、結果未閲覧で統合LV-202へ吸収した。
- Draft LV-204は、旧VV-104との独立性不足によりpretest削除した。
- Draft RR-205は、point-in-time carry data未確保によりDATA_INSUFFICIENT_PRETESTとし、Phase 9で差し替えない。
- Draft LV-205はPS-205とsignal generatorが重複するため、独立alphaではなくRISK-P9-RO-201へ移動した。
- Phase 8で見た銘柄別・時間足別の成績は、これらの仕様・対象・Gate選択に使用していない。

# Phase 9 仮説ポートフォリオ（討論用草案）

全候補は`UNTESTED_DRAFT`であり、`WATCH`や`DEVELOPMENT`ではない。
下記の数値は検証結果から選んだ最適値ではなく、仮説を曖昧にしないための初期仕様である。
討論後、結果を見る前に最終仕様を凍結する。

## Price Structure

| ID | 仮説と主要Entry | 対象 | 最低episode | 主な弱点 |
|---|---|---|---:|---|
| P9-PS-201 | 8本balance幅≤1.25 ATR、20本高安を0.10 ATR突破後、3本以内のretestが0.25 ATR以上range内へ戻らず、0.05 ATR外で再確定したら継続 | 全12銘柄、M15/H1/H4 | 500 | entryが遅い、LV-202と重複 |
| P9-PS-202 | 20本高安を0.15 ATR超えて終値breakした後、2本以内に0.10 ATR以上range内へ復帰したら反転 | 全12銘柄、M15/H1/H4 | 500 | 通常のretestを誤って反転扱いする可能性 |
| P9-PS-203 | M15→H4、H1/H4→D1のEMA20/60 trendと傾き0.25 ATRを確認し、0.50〜1.75 ATR pullback後の2本構造breakで再開 | 全12銘柄、M15/H1/H4 | 500 | 上位足同期と日足close定義 |
| P9-PS-204 | 00:00〜06:00 UTC rangeを06:00〜10:00に0.15 ATR break後、2本以内に0.10 ATR内部へ戻れば反転 | FX8＋金銀、M15/H1 | 500 | DSTを使わない固定UTC、news影響 |
| P9-PS-205 | D1の20日・60日return同方向かつ60日move≥2.5 ATR、H1/H4で0.50〜1.50 ATR pullback後の3本構造break | 全12銘柄、H1/H4 | 500 | 反転が遅い、financing未反映 |

## Liquidity / Volatility

| ID | 仮説と主要Entry | 対象 | 最低episode | 主な弱点 |
|---|---|---|---:|---|
| P9-LV-201 | 同一UTC slotの過去40日比でtick volume≥1.75、range≥1.5 ATR、spread≤80 percentile、次バーがmidpointを維持すれば継続 | 全12銘柄、M15/H1/H4 | 500 | tick volumeはsigned flowではない、spread履歴が必要 |
| P9-LV-202 | 直前12本のmedian TR≤過去240本の20 percentile、1.25 ATR release後、3本以内のretest保持で継続 | 全12銘柄、M15/H1/H4 | 500 | PS-201と重複、entry遅延 |
| P9-LV-203 | 3本move≥1 ATR後、range≥2.5 ATR、季節調整volume≥1.5、wick≥40%。次バーがmidpointを回復すれば反転 | 全12銘柄、M15/H1/H4 | 500 | H4で希少、slippage大 |
| P9-LV-204 | range/季節調整volumeのimpact score≥90 percentile、volume≤0.8、peer move≤0.3 ATR、2本以内のmidpoint reclaimで反転 | 全12銘柄、M15/H1/H4 | 500 | spread/peer同期必須、VV-104との差を厳格に維持 |
| P9-LV-205 | 方向はD1の20/60日trend、H4 pullback再開でentry。volatilityは0.25〜1.50倍のposition sizeにのみ使用 | 全12銘柄、H4 | 500 | event edgeよりrisk overlayの検証、target vol固定が必要 |

## Relative Value / Regime

| ID | 仮説と主要Entry | 対象 | 最低episode | 主な弱点 |
|---|---|---|---:|---|
| P9-RR-201 | 8 FX pairから5通貨の20/60日strengthを推定し、gap上位25%、直近5日のうち3日安定、H4 pullback後に相対momentum方向 | FX8、H4 | 250 | cross-sectionが小さい、JPY集中の可能性 |
| P9-RR-202 | 対象pairを除く7 pairから12本implied returnを作り、240本residual z≥2、2本以内にzが0.25戻れば相対回帰 | FX8、H1/H4 | 250 | 同期欠損、pair固有news |
| P9-RR-203 | 過去120 D1のGold-Silver rolling beta、R²≥0.60、half-life 2〜30日、H4 residual z≥2から0.25戻ればbeta hedge回帰 | 金銀、H4 | 250 | 関係崩壊、二脚cost/margin |
| P9-RR-204 | 過去120 D1のBrent-WTI rolling beta、R²≥0.70、half-life 2〜30日、H4 residual z≥2から0.25戻ればbeta hedge回帰 | Brent/WTI、H4 | 250 | roll歪み、構造的oil shock |
| P9-RR-205 | 実際の1か月forward/financing carry≥2%年率、D1 60日momentum同方向≥2 ATR、RV≤80 percentile、H4 pullback再開 | FX8、H4 | 250 | point-in-time carry data未確保、carry crash |

## 共通評価設計

- Entryは最終確認バー`t`の次の取引可能バー始値。`t`より後の情報は禁止。
- Primary outcomeはEntryから12実時間後までのdirection-adjusted return。4本・12本のバー数固定も別に集計する。
- 12実時間内のMFE・MAE、年度別・銘柄別・時間足別・BUY/SELL別・volatility quintile別を出す。
- Matched controlは同銘柄、同時間足、同方向、同年、同UTC sessionで固定し、ATR percentile±10、spread percentile±10、60本return z±0.5以内から未来returnを見ずに1対1選択する。
- 同銘柄・同方向で12時間windowが重なるsignalは最初の1件へ統合する。
- sensitivityは各候補のJSONに記載した3水準をone-at-a-timeで評価し、最良水準を採用するために使わない。
- raw signal returnが現実的cost後に非正なら、controlとの差が正でも`DEVELOPMENT`へ進めない。

## 討論で優先して決める5点

1. PS-201とLV-202は重複が大きいため、両方残すか片方へ統合するか。
2. LV-204は旧VV-104の最適化に見えないよう、spread・peer非確認・reclaimを必須の別メカニズムとして維持できるか。
3. RR-205用のpoint-in-time forward/financing dataを確保できるか。できなければ検証前に候補差し替え。
4. 2014-08-28〜2019-08-28に全銘柄の必要データがあるか。欠ける場合も結果ではなくdata availabilityだけで期間を再定義する。
5. 15件を一度に凍結するか、重複を減らして10〜12件に絞りmultiple-testing burdenを下げるか。

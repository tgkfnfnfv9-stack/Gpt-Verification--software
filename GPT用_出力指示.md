# ChatGPTへの検証データ出力指示

検証が終わったら、このHTMLビューアで読めるJSONファイルを作ってください。

- 銘柄・時間足・期間を `charts` に入れる
- OHLCは `candles` に入れる
- EMA・ボリンジャーバンド・VWAPなど価格上の指標は `overlays` に入れる
- RSI・MACD・ATR・出来高など別枠指標は `panes` に入れる
- 売買結果は `trades` に入れる
- `side` は BUY / SELL、`result` は WIN / LOSS を使用する
- 画面で読む文章は日本語で書く
- JSON以外の説明はファイル内に入れない

形式は `GPT出力JSON_仕様.md` に合わせてください。

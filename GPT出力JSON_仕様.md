# GPT出力JSON 形式（v003）

HTMLビューアへ読み込ませるJSONの基本構造です。キー名は機械処理のため英語ですが、画面表示は日本語です。

```json
{
  "meta": {
    "report_title": "ゴールド RFR 検証",
    "status": "検証済み"
  },
  "strategy": {
    "strategy_id": "RFR_XAUUSD_M5_v01",
    "name": "レンジ下抜け高速復帰",
    "hypothesis": "レンジ下限を一度抜けた後、短時間で復帰した場面を狙う",
    "entry_logic": ["条件1", "条件2"],
    "exit_logic": ["損切り条件", "利確条件"],
    "future_tests": ["次に試す条件"]
  },
  "charts": [
    {
      "id": "xauusd_m5",
      "symbol": "XAUUSD",
      "timeframe": "M5",
      "period": "2025-01-01 ～ 2025-12-31",
      "candles": [
        {"time":"2025-01-01T00:00:00","open":1,"high":2,"low":0.5,"close":1.5,"volume":100}
      ],
      "overlays": [],
      "panes": []
    }
  ],
  "trades": [
    {
      "no": 1,
      "chart_id": "xauusd_m5",
      "side": "BUY",
      "entry_i": 100,
      "exit_i": 120,
      "entry_price": 2650.0,
      "exit_price": 2670.0,
      "stop": 2640.0,
      "target": 2670.0,
      "r": 2.0,
      "result": "WIN",
      "confidence": 85,
      "setup": "高速復帰",
      "note": "狙い通りの形"
    }
  ],
  "notes": ["検証メモ"]
}
```

## インジケータ

価格チャート上に重ねる指標は `overlays`、RSI・MACD・ATR・出来高など別枠の指標は `panes` に入れます。

ビューアは読み込んだ `trades` から、トレード数・勝率・期待値・PF・最大DD・累積Rを自動計算します。


## 動作するサンプル

`samples/GPT出力データ_サンプル.json` は複数銘柄・時間足・インジケータを含む読み込み確認用データです。すべて架空であり、実相場の検証結果ではありません。上記の短いJSON例は構造説明用であり、実際にはトレードの足番号までのローソク足が必要です。

## 値と順序のルール

- `charts[].id` は同一JSON内で一意の文字列とします。
- `candles` は時刻の昇順に並べ、OHLCを有限の数値とします。`high` は始値・終値以上、`low` は始値・終値以下にします。
- `time` はタイムゾーンを明示したISO 8601形式（例：`2025-01-06T00:00:00+00:00`）を推奨します。表示時刻は閲覧端末のローカル時間です。
- `chart_id` は対応するチャートの `id` と一致させます。
- `entry_i` / `exit_i` は対応する `candles` の0始まりの整数添字で、`0 <= entry_i <= exit_i < candles.length` とします。
- `entry_price` / `exit_price` / `stop` / `target` は数値です。`stop` / `target` の未設定値は `null` にします。
- `side` は `BUY` / `SELL`、`result` は `WIN` / `LOSS` / `EVEN` とします。結果と `r` の符号を一致させてください。
- `r` は有限の数値で、初期リスクに対する確定損益の倍率です。コストを含むかは `notes` などに明記してください。
- `trades` は決済時刻の昇順を推奨します。最大DDと累積Rは配列順で計算され、ビューア側で並べ替えません。
- `confidence` は任意の数値です。根拠のない信頼度を付けず、不明なら省略または `null` にしてください。
- トレードがないチャートも表示できます（`trades: []`）。
- 本ビューアは欠損値を補正する場合があるため、入力元で参照ID・足番号・損益値を検証してください。

## インジケータの詳しい形式

各値の配列は `candles` と同じ順序・長さにそろえます。計算期間が足りない先頭部分などは `null` にします。ビューアは渡された値を描画するだけで、EMA・RSI等を計算しません。

```json
{
  "overlays": [
    {"kind": "line", "label": "SMA(5)", "values": [null, 100, 101]},
    {"kind": "band", "label": "バンド", "upper": [null, 102, 103], "middle": [null, 100, 101], "lower": [null, 98, 99]}
  ],
  "panes": [
    {"label": "RSI", "min": 0, "max": 100, "levels": [30, 70], "series": [
      {"kind": "line", "label": "RSI(14)", "values": [null, 48, 52]}
    ]},
    {"label": "MACD", "zero_line": true, "series": [
      {"kind": "line", "label": "MACD", "values": [null, 0.2, 0.3]},
      {"kind": "line", "label": "シグナル", "values": [null, 0.1, 0.2]},
      {"kind": "histogram", "label": "ヒストグラム", "values": [null, 0.1, 0.1]}
    ]}
  ]
}
```

この指標例の数値も形式説明用です。`min` / `max` を省略すると表示範囲から自動調整されます。`levels` は水平補助線、`zero_line` はゼロ基準線です。色はビューアが自動指定します。

## 集計

`summary` を入力しても、ビューアは `trades[].r` から集計し直します。勝率・期待値・PFはRベースで、最大DDは決済トレード列の累積Rベースです。詳しい定義は `README.md` を参照してください。実検証を行っていないデータを「検証済み」と表示しないでください。

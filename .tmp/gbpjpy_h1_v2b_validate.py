import json
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, "/tmp")
from gbpjpy_h1_v2_opt import load_csv, aggregate_h1, ema, atr_wilder, detect_entries, simulate_from_entries, metrics, roundm, candle_json, median_spread

OUT=Path("results"); OUT.mkdir(exist_ok=True)

BASE={"trend_close":"ema20","slope_lb":5,"h0_window":3,"atr_mult":1.5,"sweep_lookback":12,
      "recovery_bars":4,"recovery_pct":0.70,"breakout_bars":8,"breakout_buffer":0.0,
      "retest_bars":4,"retest_touch":0.25,"retest_hold":0.10,"confirm":"bullish","session":"all"}
ROBUST={"trend_close":"ema20","slope_lb":5,"h0_window":5,"atr_mult":1.0,"sweep_lookback":12,
        "recovery_bars":4,"recovery_pct":0.45,"breakout_bars":10,"breakout_buffer":0.03,
        "retest_bars":6,"retest_touch":0.50,"retest_hold":0.20,"confirm":"none","session":"london"}

def slice_bars(xs,start,end):
    return [b for b in xs if start <= b.dt < end]

def run_period(bid15,ask15,start,end,p,target,maxhold,stopbuf):
    b15=slice_bars(bid15,start,end); a15=slice_bars(ask15,start,end)
    bid=aggregate_h1(b15); ask=aggregate_h1(a15)
    closes=[b.close for b in bid]; e20=ema(closes,20); e50=ema(closes,50); atr=atr_wilder(bid,14)
    entries=detect_entries(bid,e20,e50,atr,p)
    trades=simulate_from_entries(bid,ask,entries,atr,target,maxhold,stopbuf)
    return bid,ask,e20,e50,atr,trades

def quarter_metrics(trades,bars):
    q={}
    for t in trades:
        d=bars[t["entry_i"]].dt
        key=f"{d.year}-Q{(d.month-1)//3+1}"
        q.setdefault(key,[]).append(t)
    return {k:roundm(metrics(v)) for k,v in sorted(q.items())}

def main():
    bid15=load_csv(Path("data/GBPJPY_M15_bid.csv"))
    ask15=load_csv(Path("data/GBPJPY_M15_ask.csv"))
    old_s=datetime(2023,8,27); old_e=datetime(2024,8,27)
    new_s=datetime(2024,8,27); new_e=datetime(2026,8,27)

    ob,oa,oe20,oe50,oatr,old_r=run_period(bid15,ask15,old_s,old_e,ROBUST,2.25,24,0.0)
    _,_,_,_,_,old_b=run_period(bid15,ask15,old_s,old_e,BASE,2.0,24,0.10)
    nb,na,ne20,ne50,natr,new_r=run_period(bid15,ask15,new_s,new_e,ROBUST,2.25,24,0.0)
    _,_,_,_,_,new_b=run_period(bid15,ask15,new_s,new_e,BASE,2.0,24,0.10)

    y1=[t for t in new_r if nb[t["entry_i"]].dt < datetime(2025,8,27)]
    y2=[t for t in new_r if nb[t["entry_i"]].dt >= datetime(2025,8,27)]
    b1=[t for t in new_b if nb[t["entry_i"]].dt < datetime(2025,8,27)]
    b2=[t for t in new_b if nb[t["entry_i"]].dt >= datetime(2025,8,27)]

    summary={
      "data_source":"Dukascopy JForex / jetta endpoint via dukascopy-go v0.2.0; GBPJPY M15 BID+ASK aggregated to H1",
      "candidate_status":"V2b 固定候補。最新2年の候補比較後、追加の過去1年を独立確認期間として検証。",
      "v1_baseline":{
        "rules":BASE,"target_r":2.0,"max_hold_hours":24,"stop_buffer_atr":0.10,
        "prior_1y_untouched":roundm(metrics(old_b)),
        "latest_2y":roundm(metrics(new_b)),
        "latest_year1":roundm(metrics(b1)),"latest_year2":roundm(metrics(b2))
      },
      "v2b":{
        "rules":ROBUST,"target_r":2.25,"max_hold_hours":24,"stop_buffer_atr":0.0,
        "prior_1y_untouched":roundm(metrics(old_r)),
        "latest_2y":roundm(metrics(new_r)),
        "latest_year1":roundm(metrics(y1)),"latest_year2":roundm(metrics(y2)),
        "quarterly_latest_2y":quarter_metrics(new_r,nb),
        "quarterly_prior_1y":quarter_metrics(old_r,ob)
      },
      "comparison":{
        "entry_count_change_latest_2y":metrics(new_r)["trades"]-metrics(new_b)["trades"],
        "expectancy_change_latest_2y":round(metrics(new_r)["expectancy_r"]-metrics(new_b)["expectancy_r"],3),
        "pf_change_latest_2y":round(metrics(new_r)["pf"]-metrics(new_b)["pf"],3),
        "goal_met_latest_2y":metrics(new_r)["trades"]>metrics(new_b)["trades"] and metrics(new_r)["expectancy_r"]>metrics(new_b)["expectancy_r"],
        "prior_1y_confirmation_positive":metrics(old_r)["expectancy_r"]>0 and metrics(old_r)["pf"]>1
      },
      "execution":"シグナルはBID、BUY EntryはASK始値、SL/TP/時間決済はBID。同一H1足でSL/TP両方到達はSL先着。実BID/ASKスプレッド反映、手数料・追加スリッページなし。"
    }
    print("=== V2B VALIDATION ===")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

    cid="gbpjpy_h1_flush_recovery_v2b"
    tj=[]
    for no,t in enumerate(new_r,1):
        tj.append({"no":no,"chart_id":cid,"side":"BUY","entry_i":t["entry_i"],"exit_i":t["exit_i"],
                   "entry_price":round(t["entry_price"],6),"exit_price":round(t["exit_price"],6),
                   "stop":round(t["stop"],6),"target":round(t["target"],6),"r":round(t["r"],6),
                   "result":t["result"],"confidence":None,"setup":"Flush Recovery London Retest V2b",
                   "note":f"drop={t['drop_atr']:.2f}ATR recovery={t['recovery_ratio']:.0%} {t['exit_reason']}"})
    report={
      "meta":{"report_title":"GBPJPY H1 Flush Recovery V2b 改善検証","status":"検証済み"},
      "strategy":{
        "strategy_id":"FLUSH_RECOVERY_GBPJPY_H1_V2B",
        "name":"GBPJPY H1 上昇Flush→回復→高値更新→London押し目BUY",
        "hypothesis":"V1の形を維持しつつ、Flush条件と回復・リテスト許容幅を緩めて機会を増やし、London時間帯に限定して質を維持する。",
        "entry_logic":[
          "EMA20 > EMA50、EMA50が5本前より上向き、H0終値 > EMA20",
          "H0は直前5本の最高値。H0前12本安値をSweepし、H0→Flush安値が1.0ATR以上",
          "4本以内にSweep水準へ終値復帰し、下落幅の45%以上を回復",
          "回復後10本以内にH0+0.03ATRを終値突破",
          "突破後6本以内にH0+0.50ATR以内へ押し、終値H0-0.20ATR以上を維持",
          "リテスト足が06:00～15:59 UTC（London時間帯条件）なら、次足ASK始値でBUY"
        ],
        "exit_logic":[
          "SL = Flush安値（追加ATRバッファなし）",
          "TP = 2.25R",
          "最大保有 = 24時間",
          "EntryはASK、SL/TP/時間決済はBID。同一足SL/TPはSL先着として保守的に判定。",
          "手数料・追加スリッページなし。実BID/ASKスプレッドは反映。"
        ],
        "future_tests":["MT5ブローカー実価格で再検証","手数料・スリッページを追加","フォワード期間で継続監視"]
      },
      "charts":[{
        "id":cid,"symbol":"GBPJPY","timeframe":"H1","period":"2024-08-27 ～ 2026-08-26",
        "candles":[candle_json(b) for b in nb],
        "overlays":[{"kind":"line","label":"EMA20","values":[round(x,6) for x in ne20]},
                    {"kind":"line","label":"EMA50","values":[round(x,6) for x in ne50]}],
        "panes":[{"label":"ATR(14)","min":0,"series":[{"kind":"line","label":"ATR(14)","values":[round(x,6) for x in natr]}]}]
      }],
      "trades":tj,
      "notes":[
        f"V1最新2年: {roundm(metrics(new_b))}",
        f"V2b最新2年: {roundm(metrics(new_r))}",
        f"V2b追加の過去1年独立確認: {roundm(metrics(old_r))}",
        "V2bは最新2年の候補比較を見た後に採用したため、最新2年だけでは完全な未使用検証ではない。そこで2023-08-27～2024-08-26を追加の独立確認期間として検証した。"
      ]
    }
    (OUT/"gbpjpy_h1_flush_recovery_v2b_2y.json").write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    (OUT/"gbpjpy_h1_flush_recovery_v2b_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Viewer JSON bytes", (OUT/"gbpjpy_h1_flush_recovery_v2b_2y.json").stat().st_size)

if __name__=="__main__":
    main()

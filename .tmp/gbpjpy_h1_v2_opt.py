import csv, json, math, os, random, statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Tuple

START_DATE = "2024-08-27"
END_DATE = "2026-08-27"
SPLIT_DATE = datetime(2025, 8, 27)
OUTPUT_DIR = Path("results")
OUTPUT_DIR.mkdir(exist_ok=True)
SYMBOL = "GBPJPY"

@dataclass
class Bar:
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

def norm(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())

def parse_dt(x: str) -> datetime:
    s = str(x).strip().strip('"')
    s = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            d = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            if d.tzinfo is not None:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        except Exception:
            continue
    raise ValueError(s)

def pick_key(fieldnames, candidates):
    m = {norm(k): k for k in fieldnames}
    for c in candidates:
        if norm(c) in m:
            return m[norm(c)]
    return None

def load_csv(path: Path) -> List[Bar]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        tk = pick_key(r.fieldnames, ["timestamp","time","datetime","date"])
        ok = pick_key(r.fieldnames, ["open"]); hk = pick_key(r.fieldnames, ["high"])
        lk = pick_key(r.fieldnames, ["low"]); ck = pick_key(r.fieldnames, ["close"])
        vk = pick_key(r.fieldnames, ["volume","tick_volume"])
        out = []
        for row in r:
            try:
                b = Bar(parse_dt(row[tk]), float(row[ok]), float(row[hk]), float(row[lk]), float(row[ck]),
                        float(row[vk]) if vk and row.get(vk) not in (None,"") else 0.0)
                if b.high >= max(b.open,b.close) and b.low <= min(b.open,b.close) and b.open > 0 and b.close > 0:
                    out.append(b)
            except Exception:
                pass
    out.sort(key=lambda x:x.dt)
    dd={b.dt:b for b in out}
    return [dd[k] for k in sorted(dd)]

def aggregate_h1(bars: List[Bar]) -> List[Bar]:
    groups={}
    for b in bars:
        k=b.dt.replace(minute=0,second=0,microsecond=0)
        groups.setdefault(k,[]).append(b)
    out=[]
    for k in sorted(groups):
        g=sorted(groups[k],key=lambda x:x.dt)
        out.append(Bar(k,g[0].open,max(x.high for x in g),min(x.low for x in g),g[-1].close,sum(x.volume for x in g)))
    return out

def ema(vals, p):
    a=2/(p+1); out=[vals[0]]
    for v in vals[1:]: out.append(a*v+(1-a)*out[-1])
    return out

def atr_wilder(bars,p=14):
    tr=[bars[0].high-bars[0].low]
    for i in range(1,len(bars)):
        pc=bars[i-1].close
        tr.append(max(bars[i].high-bars[i].low,abs(bars[i].high-pc),abs(bars[i].low-pc)))
    out=[tr[0]]
    for i in range(1,len(tr)):
        out.append(sum(tr[:i+1])/(i+1) if i<p else (out[-1]*(p-1)+tr[i])/p)
    return out

def median_spread(bid,ask):
    am={x.dt:x for x in ask}; xs=[]
    for b in bid:
        a=am.get(b.dt)
        if a and a.open>=b.open: xs.append(a.open-b.open)
    return statistics.median(xs) if xs else 0.0

def metrics(ts):
    rs=[t["r"] for t in ts]; n=len(rs)
    if not n:
        return {"trades":0,"win_rate":0.0,"expectancy_r":0.0,"pf":0.0,"max_dd_r":0.0,"cum_r":0.0}
    pos=sum(x for x in rs if x>0); neg=-sum(x for x in rs if x<0)
    pf=pos/neg if neg>0 else (999.0 if pos>0 else 0.0)
    eq=peak=mdd=0.0
    for x in rs:
        eq += x; peak=max(peak,eq); mdd=max(mdd,peak-eq)
    return {"trades":n,"win_rate":100*sum(x>0 for x in rs)/n,"expectancy_r":sum(rs)/n,
            "pf":pf,"max_dd_r":mdd,"cum_r":sum(rs)}

def roundm(m):
    return {k:(round(v,3) if isinstance(v,float) else v) for k,v in m.items()}

def session_ok(hour, session):
    if session=="all": return True
    if session=="london": return 6 <= hour < 16
    if session=="london_ny": return 6 <= hour < 21
    if session=="core": return 7 <= hour < 18
    if session=="ny": return 12 <= hour < 21
    return True

def detect_entries(bars,e20,e50,atr,p):
    events=[]; i=60
    while i < len(bars)-50:
        hw=p["h0_window"]
        h0_idx=max(range(i-hw,i), key=lambda z: bars[z].high)
        h0=bars[h0_idx].high
        if not (1 <= i-h0_idx <= hw): i+=1; continue
        tlb=p["slope_lb"]
        trend_close = bars[h0_idx].close > (e20[h0_idx] if p["trend_close"]=="ema20" else e50[h0_idx])
        if not (e20[h0_idx] > e50[h0_idx] and e50[h0_idx] > e50[h0_idx-tlb] and trend_close):
            i+=1; continue
        a0=atr[h0_idx]
        if a0<=0: i+=1; continue
        ref_start=max(0,h0_idx-p["sweep_lookback"])
        if h0_idx-ref_start < max(5,p["sweep_lookback"]//2): i+=1; continue
        prior_low=min(bars[z].low for z in range(ref_start,h0_idx))
        flush_low=bars[i].low; drop=h0-flush_low
        if drop < p["atr_mult"]*a0 or not (flush_low < prior_low):
            i+=1; continue
        rec_idx=None; rec_ratio=None
        for j in range(i+1,min(len(bars),i+p["recovery_bars"]+1)):
            ratio=(bars[j].close-flush_low)/drop if drop>0 else 0
            if bars[j].close > prior_low and ratio >= p["recovery_pct"]:
                rec_idx=j; rec_ratio=ratio; break
        if rec_idx is None: i+=1; continue
        bo_idx=None
        for k in range(rec_idx,min(len(bars)-1,rec_idx+p["breakout_bars"]+1)):
            if bars[k].close > h0 + p["breakout_buffer"]*a0:
                bo_idx=k; break
        if bo_idx is None: i+=1; continue
        ret=None
        a_bo=atr[bo_idx]
        for q in range(bo_idx+1,min(len(bars)-1,bo_idx+p["retest_bars"]+1)):
            near=bars[q].low <= h0 + p["retest_touch"]*a_bo
            holds=bars[q].close >= h0 - p["retest_hold"]*a_bo
            if p["confirm"]=="none":
                turns=True
            elif p["confirm"]=="bullish":
                turns=(bars[q].close > bars[q].open or bars[q].close > bars[q-1].close)
            else:
                turns=(bars[q].close > bars[q].open and bars[q].close > bars[q-1].close)
            if near and holds and turns and session_ok(bars[q].dt.hour,p["session"]):
                ret=q; break
        if ret is not None and ret+1 < len(bars):
            events.append({"entry_i":ret+1,"flush_i":i,"h0_i":h0_idx,"retest_i":ret,"breakout_i":bo_idx,
                           "h0":h0,"prior_low":prior_low,"flush_low":flush_low,"atr":a0,
                           "drop_atr":drop/a0,"recovery_i":rec_idx,"recovery_ratio":rec_ratio})
        i=bo_idx+1
    return events

def simulate_from_entries(bid,ask,entries,atr,target_r=2.0,max_hold=24,stop_buffer=0.10):
    amap={b.dt:b for b in ask}; fspread=median_spread(bid,ask)
    trades=[]; next_allowed=0
    for ev in entries:
        ei=ev["entry_i"]
        if ei < next_allowed or ei>=len(bid): continue
        ab=amap.get(bid[ei].dt)
        entry=ab.open if ab else bid[ei].open+fspread
        stop=ev["flush_low"]-stop_buffer*ev["atr"]
        risk=entry-stop
        if risk<=0 or risk/entry>0.05: continue
        target=entry+target_r*risk
        end=min(len(bid)-1,ei+max_hold-1)
        xi=end; xp=bid[end].close; reason="TIME"
        for z in range(ei,end+1):
            hs=bid[z].low<=stop; ht=bid[z].high>=target
            if hs and ht:
                xi=z; xp=stop; reason="SL_SAME_BAR"; break
            if hs:
                xi=z; xp=stop; reason="SL"; break
            if ht:
                xi=z; xp=target; reason=f"TP{target_r:.2f}R"; break
        r=(xp-entry)/risk
        window=bid[ei:end+1]
        trades.append({**ev,"entry_i":ei,"exit_i":xi,"entry_price":entry,"exit_price":xp,
                       "stop":stop,"target":target,"r":r,"result":"WIN" if r>0 else ("LOSS" if r<0 else "EVEN"),
                       "exit_reason":reason,
                       "mfe_r":(max(x.high for x in window)-entry)/risk,
                       "mae_r":(min(x.low for x in window)-entry)/risk})
        next_allowed=xi+1
    return trades

def split_trades(ts,bars):
    train=[t for t in ts if bars[t["entry_i"]].dt < SPLIT_DATE]
    test=[t for t in ts if bars[t["entry_i"]].dt >= SPLIT_DATE]
    h1=datetime(2025,2,27)
    train_a=[t for t in train if bars[t["entry_i"]].dt < h1]
    train_b=[t for t in train if bars[t["entry_i"]].dt >= h1]
    return train,test,train_a,train_b

def make_random_params(seed=5626,n=1800):
    rng=random.Random(seed)
    opts={
        "trend_close":["ema20","ema50"], "slope_lb":[2,3,5,8], "h0_window":[3,4,5,6],
        "atr_mult":[0.8,1.0,1.2,1.35,1.5], "sweep_lookback":[6,8,10,12,16],
        "recovery_bars":[3,4,5,6,8], "recovery_pct":[0.45,0.55,0.65,0.70],
        "breakout_bars":[6,8,10,12,16], "breakout_buffer":[0.0,0.03,0.05],
        "retest_bars":[3,4,6,8,10], "retest_touch":[0.10,0.20,0.25,0.35,0.50],
        "retest_hold":[0.05,0.10,0.15,0.20], "confirm":["none","bullish","strong"],
        "session":["all","london","london_ny","core","ny"]
    }
    seen=set(); arr=[]
    while len(arr)<n:
        p={k:rng.choice(v) for k,v in opts.items()}
        key=tuple(sorted(p.items()))
        if key in seen: continue
        seen.add(key); arr.append(p)
    base={"trend_close":"ema20","slope_lb":5,"h0_window":3,"atr_mult":1.5,"sweep_lookback":12,
          "recovery_bars":4,"recovery_pct":0.70,"breakout_bars":8,"breakout_buffer":0.0,
          "retest_bars":4,"retest_touch":0.25,"retest_hold":0.10,"confirm":"bullish","session":"all"}
    arr.append(base)
    return arr

def objective(m,ma,mb):
    if m["trades"]<11 or ma["trades"]<4 or mb["trades"]<4: return -999
    score=m["expectancy_r"] + 0.035*math.log1p(m["trades"]) + 0.04*min(m["pf"],2.5)
    score -= 0.22*abs(ma["expectancy_r"]-mb["expectancy_r"])
    if ma["expectancy_r"]<0: score += 0.8*ma["expectancy_r"]
    if mb["expectancy_r"]<0: score += 0.8*mb["expectancy_r"]
    return score

def candle_json(b):
    return {"time":b.dt.isoformat(timespec="seconds")+"+00:00","open":round(b.open,6),"high":round(b.high,6),
            "low":round(b.low,6),"close":round(b.close,6),"volume":round(b.volume,4)}

def main():
    bid15=load_csv(Path("data/GBPJPY_M15_bid.csv"))
    ask15=load_csv(Path("data/GBPJPY_M15_ask.csv"))
    bid=aggregate_h1(bid15); ask=aggregate_h1(ask15)
    closes=[b.close for b in bid]
    e20=ema(closes,20); e50=ema(closes,50); atr=atr_wilder(bid,14)

    baseline_p={"trend_close":"ema20","slope_lb":5,"h0_window":3,"atr_mult":1.5,"sweep_lookback":12,
          "recovery_bars":4,"recovery_pct":0.70,"breakout_bars":8,"breakout_buffer":0.0,
          "retest_bars":4,"retest_touch":0.25,"retest_hold":0.10,"confirm":"bullish","session":"all"}
    baseline_entries=detect_entries(bid,e20,e50,atr,baseline_p)
    baseline_trades=simulate_from_entries(bid,ask,baseline_entries,atr,2.0,24,0.10)
    baseline_train,baseline_test,_,_=split_trades(baseline_trades,bid)

    stage=[]
    params_list=make_random_params()
    for idx,p in enumerate(params_list):
        entries=detect_entries(bid,e20,e50,atr,p)
        ts=simulate_from_entries(bid,ask,entries,atr,1.75,24,0.10)
        tr,te,ha,hb=split_trades(ts,bid)
        m=metrics(tr); ma=metrics(ha); mb=metrics(hb)
        sc=objective(m,ma,mb)
        if sc>-900:
            stage.append((sc,p,entries,m,ma,mb))
    stage.sort(key=lambda x:x[0],reverse=True)
    top=stage[:50]

    exits=[]
    for base_score,p,entries,_,_,_ in top:
        for target_r in [1.25,1.5,1.75,2.0,2.25,2.5]:
            for max_hold in [12,18,24,36]:
                for stop_buffer in [0.0,0.05,0.10,0.15]:
                    ts=simulate_from_entries(bid,ask,entries,atr,target_r,max_hold,stop_buffer)
                    tr,te,ha,hb=split_trades(ts,bid)
                    m=metrics(tr); ma=metrics(ha); mb=metrics(hb)
                    sc=objective(m,ma,mb)
                    if m["trades"]>=12:
                        exits.append((sc,p,target_r,max_hold,stop_buffer,entries,tr,te,ha,hb,m,ma,mb))
    exits.sort(key=lambda x:(x[0],x[10]["expectancy_r"],x[10]["trades"]),reverse=True)

    chosen=None
    for row in exits:
        sc,p,trg,mh,sb,entries,tr,te,ha,hb,m,ma,mb=row
        if m["trades"]>=14 and ma["expectancy_r"]>0 and mb["expectancy_r"]>0 and m["pf"]>1.15:
            chosen=row; break
    if chosen is None: chosen=exits[0]

    sc,p,trg,mh,sb,entries,tr,te,ha,hb,m,ma,mb=chosen
    full=simulate_from_entries(bid,ask,entries,atr,trg,mh,sb)
    full_m=metrics(full); test_m=metrics(te)

    top_report=[]
    for row in exits[:15]:
        sc0,p0,trg0,mh0,sb0,en0,tr0,te0,ha0,hb0,m0,ma0,mb0=row
        top_report.append({"score":round(sc0,4),"params":p0,"target_r":trg0,"max_hold":mh0,"stop_buffer":sb0,
                           "development":roundm(m0),"development_first_half":roundm(ma0),"development_second_half":roundm(mb0),
                           "holdout":roundm(metrics(te0))})

    summary={
      "data_source":"Dukascopy JForex / jetta endpoint via dukascopy-go v0.2.0; GBPJPY M15 BID+ASK aggregated to H1",
      "period":f"{START_DATE} ～ {END_DATE}",
      "development_period":"2024-08-27 ～ 2025-08-26",
      "holdout_period":"2025-08-27 ～ 2026-08-26",
      "median_spread":median_spread(bid,ask),
      "baseline_v1_B":{"params":baseline_p,"target_r":2.0,"max_hold":24,"stop_buffer":0.10,
                       "full":roundm(metrics(baseline_trades)),"development":roundm(metrics(baseline_train)),
                       "holdout":roundm(metrics(baseline_test))},
      "v2_selected":{"params":p,"target_r":trg,"max_hold":mh,"stop_buffer":sb,
                     "development":roundm(m),"development_first_half":roundm(ma),"development_second_half":roundm(mb),
                     "holdout":roundm(test_m),"full":roundm(full_m)},
      "selection_note":"V2の条件と決済パラメータは前半1年（development）のみで選択。後半1年（holdout）は選択後に一度だけ評価。",
      "meets_user_goal_full": bool(full_m["trades"]>metrics(baseline_trades)["trades"] and full_m["expectancy_r"]>metrics(baseline_trades)["expectancy_r"]),
      "top_development_candidates":top_report
    }
    print("=== OPTIMIZATION SUMMARY ===")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

    chart_id="gbpjpy_h1_flush_recovery_v2"
    trades_json=[]
    for no,t in enumerate(full,1):
        trades_json.append({
          "no":no,"chart_id":chart_id,"side":"BUY","entry_i":t["entry_i"],"exit_i":t["exit_i"],
          "entry_price":round(t["entry_price"],6),"exit_price":round(t["exit_price"],6),
          "stop":round(t["stop"],6),"target":round(t["target"],6),"r":round(t["r"],6),
          "result":t["result"],"confidence":None,"setup":"上昇中Flush→高速回復→高値更新→押し目維持",
          "note":f"drop={t['drop_atr']:.2f}ATR recovery={t['recovery_ratio']:.0%} {t['exit_reason']}"
        })
    report={
      "meta":{"report_title":"GBPJPY H1 Flush Recovery V2 検証","status":"検証済み"},
      "strategy":{
        "strategy_id":"FLUSH_RECOVERY_GBPJPY_H1_V2",
        "name":"上昇トレンド Flush Recovery Retest V2",
        "hypothesis":"上昇トレンド中に直近安値を急落で掃除し、短時間で回復・高値更新した後、旧高値付近の押し目を維持した場面を買う。",
        "entry_logic":[
          f"EMA20 > EMA50、EMA50が{p['slope_lb']}本前より上向き、H0終値>{p['trend_close'].upper()}",
          f"H0は直前{p['h0_window']}本の最高値、H0前{p['sweep_lookback']}本安値を下抜き、下落幅>={p['atr_mult']}ATR",
          f"{p['recovery_bars']}本以内にSweep水準へ終値復帰、下落幅の{round(p['recovery_pct']*100)}%以上回復",
          f"回復後{p['breakout_bars']}本以内にH0+{p['breakout_buffer']}ATRを終値突破",
          f"突破後{p['retest_bars']}本以内にH0+{p['retest_touch']}ATR以内へ押し、終値がH0-{p['retest_hold']}ATR以上を維持",
          f"確認={p['confirm']}、時間帯={p['session']}（UTC）、次足ASK始値でBUY"
        ],
        "exit_logic":[
          f"SL = Flush安値 - {sb}ATR",
          f"TP = {trg}R",
          f"最大保有 = {mh}時間",
          "BUY EntryはASK、SL/TP/時間決済はBID。SLとTPが同一H1足で両方到達した場合はSL先着として保守的に判定。",
          "手数料・追加スリッページは未加算。BID/ASKスプレッドは実データで反映。"
        ],
        "future_tests":[
          "MT5実ブローカーのGBPJPY H1データで再検証",
          "スリッページと手数料を追加した再検証",
          "さらに別期間の完全未使用データでフォワード確認"
        ]
      },
      "charts":[{
        "id":chart_id,"symbol":"GBPJPY","timeframe":"H1","period":"2024-08-27 ～ 2026-08-26",
        "candles":[candle_json(b) for b in bid],
        "overlays":[
          {"kind":"line","label":"EMA20","values":[round(x,6) for x in e20]},
          {"kind":"line","label":"EMA50","values":[round(x,6) for x in e50]}
        ],
        "panes":[{"label":"ATR(14)","min":0,"series":[{"kind":"line","label":"ATR(14)","values":[round(x,6) for x in atr]}]}]
      }],
      "trades":trades_json,
      "notes":[
        "データ: Dukascopy GBPJPY M15 BID/ASKをH1へ集約。",
        "パラメータ選択は前半1年のみ。後半1年はホールドアウト。",
        f"V1 B 全期間: {roundm(metrics(baseline_trades))}",
        f"V2 前半1年: {roundm(m)}",
        f"V2 後半1年ホールドアウト: {roundm(test_m)}",
        f"V2 全期間: {roundm(full_m)}"
      ]
    }
    out=OUTPUT_DIR/"gbpjpy_h1_flush_recovery_v2_2y.json"
    out.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    (OUTPUT_DIR/"gbpjpy_h1_flush_recovery_v2_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Viewer JSON: {out} bytes={out.stat().st_size}")

if __name__=="__main__":
    main()

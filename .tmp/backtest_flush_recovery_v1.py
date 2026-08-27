import csv, json, math, os, statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

START_DATE = "2024-08-27"
END_DATE = "2026-08-27"
OUTPUT_DIR = Path("results")
OUTPUT_DIR.mkdir(exist_ok=True)
SYMBOLS = ["GBPJPY", "XAUUSD"]
TIMEFRAMES = ["M15", "H1"]

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
    if not s:
        raise ValueError("empty timestamp")
    try:
        v = float(s)
        if v > 1e12:
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).replace(tzinfo=None)
        if v > 1e9:
            return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
    except ValueError:
        pass
    s = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            d = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            if d.tzinfo is not None:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        except Exception:
            continue
    raise ValueError(f"unparseable timestamp: {x}")

def pick_key(fieldnames, candidates):
    m = {norm(k): k for k in fieldnames}
    for c in candidates:
        if norm(c) in m:
            return m[norm(c)]
    for nk, orig in m.items():
        for c in candidates:
            nc = norm(c)
            if nk.endswith(nc) or nc in nk:
                return orig
    return None

def load_csv(path: Path) -> List[Bar]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError(f"No header: {path}")
        fields = reader.fieldnames
        tk = pick_key(fields, ["timestamp", "time", "date", "datetime"])
        ok = pick_key(fields, ["open"]); hk = pick_key(fields, ["high"])
        lk = pick_key(fields, ["low"]); ck = pick_key(fields, ["close"])
        vk = pick_key(fields, ["volume", "tick_volume", "tickvolume"])
        if not all([tk, ok, hk, lk, ck]):
            raise RuntimeError(f"Unrecognized columns in {path}: {fields}")
        out = []
        for row in reader:
            try:
                d = parse_dt(row[tk])
                b = Bar(d, float(row[ok]), float(row[hk]), float(row[lk]), float(row[ck]), float(row[vk]) if vk and row.get(vk) not in (None, "") else 0.0)
                if b.high < b.low or b.open <= 0 or b.close <= 0:
                    continue
                out.append(b)
            except Exception:
                continue
    out.sort(key=lambda b: b.dt)
    dedup = {b.dt: b for b in out}
    return [dedup[k] for k in sorted(dedup)]

def aggregate_h1(bars: List[Bar]) -> List[Bar]:
    groups: Dict[datetime, List[Bar]] = {}
    for b in bars:
        key = b.dt.replace(minute=0, second=0, microsecond=0)
        groups.setdefault(key, []).append(b)
    out = []
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda b: b.dt)
        out.append(Bar(key, g[0].open, max(x.high for x in g), min(x.low for x in g), g[-1].close, sum(x.volume for x in g)))
    return out

def ema(values: List[float], period: int) -> List[float]:
    if not values: return []
    a = 2.0 / (period + 1.0); out = [values[0]]
    for v in values[1:]: out.append(a * v + (1-a) * out[-1])
    return out

def atr_wilder(bars: List[Bar], period: int = 14) -> List[float]:
    if not bars: return []
    tr = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        prev = bars[i-1].close
        tr.append(max(bars[i].high-bars[i].low, abs(bars[i].high-prev), abs(bars[i].low-prev)))
    out = [tr[0]]
    for i in range(1, len(tr)):
        out.append(sum(tr[:i+1])/(i+1) if i < period else (out[-1]*(period-1)+tr[i])/period)
    return out

def median_spread(bid: List[Bar], ask: List[Bar]) -> float:
    am = {b.dt:b for b in ask}; vals=[]
    for b in bid:
        a=am.get(b.dt)
        if a:
            s=a.open-b.open
            if s>=0: vals.append(s)
    return statistics.median(vals) if vals else 0.0

def find_events(bars: List[Bar]):
    closes=[b.close for b in bars]
    e20=ema(closes,20); e50=ema(closes,50); atr=atr_wilder(bars,14)
    events=[]; i=60
    while i < len(bars)-20:
        h0_idx=max(range(i-3,i), key=lambda z: bars[z].high); h0=bars[h0_idx].high
        if not (1 <= i-h0_idx <= 3): i += 1; continue
        if not (e20[h0_idx] > e50[h0_idx] and e50[h0_idx] > e50[h0_idx-5] and bars[h0_idx].close > e20[h0_idx]): i += 1; continue
        a0=atr[h0_idx]
        if a0 <= 0: i += 1; continue
        ref_start=max(0,h0_idx-12)
        if h0_idx-ref_start < 8: i += 1; continue
        prior_low=min(bars[z].low for z in range(ref_start,h0_idx)); flush_low=bars[i].low; drop=h0-flush_low
        if drop < 1.5*a0 or not (flush_low < prior_low): i += 1; continue
        rec_idx=None; rec_ratio=None
        for j in range(i+1, min(len(bars), i+5)):
            ratio=(bars[j].close-flush_low)/drop if drop>0 else 0
            if bars[j].close > prior_low and ratio >= 0.70:
                rec_idx=j; rec_ratio=ratio; break
        if rec_idx is None: i += 1; continue
        bo_idx=None
        for k in range(rec_idx, min(len(bars)-1, rec_idx+9)):
            if bars[k].close > h0: bo_idx=k; break
        if bo_idx is None: i += 1; continue
        events.append({"flush_i":i,"h0_i":h0_idx,"h0":h0,"prior_low":prior_low,"flush_low":flush_low,"atr":a0,"drop_atr":drop/a0,"recovery_i":rec_idx,"recovery_ratio":rec_ratio,"breakout_i":bo_idx,"ema20":e20,"ema50":e50,"atr_series":atr})
        i = bo_idx + 1
    return events,e20,e50,atr

def build_entries(bars: List[Bar], events, variant: str):
    entries=[]
    for ev in events:
        bo=ev["breakout_i"]
        if variant=="A":
            if bo+1 < len(bars): entries.append((bo+1,ev))
        else:
            a=ev["atr_series"][bo]; ret=None
            for p in range(bo+1, min(len(bars)-1, bo+5)):
                near=bars[p].low <= ev["h0"]+0.25*a
                holds=bars[p].close >= ev["h0"]-0.10*a
                turns=bars[p].close > bars[p].open or (p>0 and bars[p].close > bars[p-1].close)
                if near and holds and turns: ret=p; break
            if ret is not None and ret+1 < len(bars): entries.append((ret+1,ev))
    return entries

def simulate(symbol, tf, bid: List[Bar], ask: List[Bar], variant: str):
    events,e20,e50,atr=find_events(bid); candidates=build_entries(bid,events,variant)
    askmap={b.dt:b for b in ask}; fallback_spread=median_spread(bid,ask)
    maxbars=96 if tf=="M15" else 24; bars_per_hour=4 if tf=="M15" else 1
    trades=[]; next_allowed=0
    for entry_i,ev in candidates:
        if entry_i < next_allowed or entry_i >= len(bid): continue
        ab=askmap.get(bid[entry_i].dt); entry=(ab.open if ab else bid[entry_i].open+fallback_spread)
        stop=ev["flush_low"]-0.10*ev["atr"]; risk=entry-stop
        if risk <= 0 or risk/entry > 0.05: continue
        target=entry+2*risk; end_i=min(len(bid)-1,entry_i+maxbars-1)
        exit_i=end_i; exit_price=bid[end_i].close; exit_reason="TIME"
        for z in range(entry_i,end_i+1):
            hit_sl=bid[z].low<=stop; hit_tp=bid[z].high>=target
            if hit_sl and hit_tp: exit_i=z; exit_price=stop; exit_reason="SL_SAME_BAR"; break
            if hit_sl: exit_i=z; exit_price=stop; exit_reason="SL"; break
            if hit_tp: exit_i=z; exit_price=target; exit_reason="TP2R"; break
        r=(exit_price-entry)/risk; first_rates={}
        for nr in (1,2,3):
            lvl=entry+nr*risk; outcome=False
            for z in range(entry_i,end_i+1):
                hs=bid[z].low<=stop; ht=bid[z].high>=lvl
                if hs and ht: outcome=False; break
                if hs: outcome=False; break
                if ht: outcome=True; break
            first_rates[nr]=outcome
        window=bid[entry_i:end_i+1]; mfe=(max(x.high for x in window)-entry)/risk; mae=(min(x.low for x in window)-entry)/risk
        horizon={}
        for h in (4,12,24):
            hi=entry_i+h*bars_per_hour; horizon[h]=(bid[hi].close-entry)/risk if hi < len(bid) else None
        shape_score=max(0,min(99,round(50+(ev["drop_atr"]-1.5)*10+(ev["recovery_ratio"]-0.70)*50)))
        trades.append({"entry_i":entry_i,"exit_i":exit_i,"entry_price":entry,"exit_price":exit_price,"stop":stop,"target":target,"r":r,"result":"WIN" if r>0 else "LOSS","exit_reason":exit_reason,"event":ev,"mfe_r":mfe,"mae_r":mae,"first1":first_rates[1],"first2":first_rates[2],"first3":first_rates[3],"h4":horizon[4],"h12":horizon[12],"h24":horizon[24],"shape_score":shape_score})
        next_allowed=exit_i+1
    return trades,e20,e50,atr,events

def metrics(trades):
    rs=[t["r"] for t in trades]; n=len(rs)
    if not n:
        return {"trades":0,"win_rate":0,"expectancy_r":0,"pf":0,"max_dd_r":0,"cum_r":0,"first_1r_rate":0,"first_2r_rate":0,"first_3r_rate":0,"positive_4h_rate":0,"positive_12h_rate":0,"positive_24h_rate":0,"avg_mfe_r":0,"avg_mae_r":0}
    pos=sum(x for x in rs if x>0); neg=-sum(x for x in rs if x<0); pf=(pos/neg) if neg>0 else (999.0 if pos>0 else 0.0)
    eq=0; peak=0; mdd=0
    for x in rs: eq+=x; peak=max(peak,eq); mdd=max(mdd,peak-eq)
    def rate_bool(k): return 100*sum(1 for t in trades if t[k])/n
    def rate_pos(k):
        vals=[t[k] for t in trades if t[k] is not None]
        return 100*sum(1 for x in vals if x>0)/len(vals) if vals else 0
    return {"trades":n,"win_rate":100*sum(1 for x in rs if x>0)/n,"expectancy_r":sum(rs)/n,"pf":pf,"max_dd_r":mdd,"cum_r":sum(rs),"first_1r_rate":rate_bool("first1"),"first_2r_rate":rate_bool("first2"),"first_3r_rate":rate_bool("first3"),"positive_4h_rate":rate_pos("h4"),"positive_12h_rate":rate_pos("h12"),"positive_24h_rate":rate_pos("h24"),"avg_mfe_r":sum(t["mfe_r"] for t in trades)/n,"avg_mae_r":sum(t["mae_r"] for t in trades)/n}

def fmtm(m): return {k:(round(v,3) if isinstance(v,float) else v) for k,v in m.items()}
def candle_json(b): return {"time":b.dt.isoformat(timespec="seconds"),"open":round(b.open,6),"high":round(b.high,6),"low":round(b.low,6),"close":round(b.close,6),"volume":round(b.volume,4)}
def overlay_series(name, vals, bars): return {"name":name,"type":"line","data":[{"time":bars[i].dt.isoformat(timespec="seconds"),"value":round(vals[i],6)} for i in range(len(bars))]}

def main():
    data={}; data_info={}
    for sym in SYMBOLS:
        bid15=load_csv(Path("data")/f"{sym}_M15_bid.csv"); ask15=load_csv(Path("data")/f"{sym}_M15_ask.csv")
        if len(bid15)<1000 or len(ask15)<1000: raise RuntimeError(f"Insufficient data {sym}: bid={len(bid15)} ask={len(ask15)}")
        data[(sym,"M15")]=(bid15,ask15); data[(sym,"H1")]=(aggregate_h1(bid15),aggregate_h1(ask15))
        data_info[sym]={"m15_bid_rows":len(bid15),"m15_ask_rows":len(ask15),"first":bid15[0].dt.isoformat(),"last":bid15[-1].dt.isoformat(),"median_spread":median_spread(bid15,ask15)}
    all_results={"A":{},"B":{}}; calc_cache={}
    for variant in ("A","B"):
        for sym in SYMBOLS:
            for tf in TIMEFRAMES:
                bid,ask=data[(sym,tf)]; ts,e20,e50,atr,events=simulate(sym,tf,bid,ask,variant); key=f"{sym}_{tf}"
                all_results[variant][key]={"trades":ts,"metrics":metrics(ts),"events":len(events)}; calc_cache[(variant,sym,tf)]=(e20,e50,atr)
    pooled={}
    for v in ("A","B"):
        t=[]
        for k in all_results[v]: t.extend(all_results[v][k]["trades"])
        pooled[v]=metrics(t)
    if pooled["B"]["trades"]>=10 and (pooled["B"]["expectancy_r"] > pooled["A"]["expectancy_r"]+0.03 or (abs(pooled["B"]["expectancy_r"]-pooled["A"]["expectancy_r"])<=0.03 and pooled["B"]["pf"]>pooled["A"]["pf"])): chosen="B"
    else: chosen="A"
    pm=pooled[chosen]; good_groups=sum(1 for k,v in all_results[chosen].items() if v["metrics"]["expectancy_r"]>0 and v["metrics"]["pf"]>1.0)
    if pm["trades"]>=30 and pm["expectancy_r"]>=0.15 and pm["pf"]>=1.25 and good_groups>=3: verdict="採用候補"
    elif pm["trades"]>=20 and pm["expectancy_r"]>0 and pm["pf"]>1.05 and good_groups>=2: verdict="要改善（優位性あり）"
    else: verdict="V1不採用"
    charts=[]; viewer_trades=[]; no=1
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            bid,ask=data[(sym,tf)]; e20,e50,atr=calc_cache[(chosen,sym,tf)]; chart_id=f"{sym.lower()}_{tf.lower()}"
            charts.append({"id":chart_id,"symbol":sym,"timeframe":tf,"period":f"{START_DATE} ～ {END_DATE}","candles":[candle_json(b) for b in bid],"overlays":[overlay_series("EMA20",e20,bid),overlay_series("EMA50",e50,bid)],"panes":[]})
            for t in all_results[chosen][f"{sym}_{tf}"]["trades"]:
                note=(f"{chosen} / drop={t['event']['drop_atr']:.2f}ATR / recovery={t['event']['recovery_ratio']*100:.1f}% / MFE={t['mfe_r']:.2f}R / MAE={t['mae_r']:.2f}R / 1R先着={'○' if t['first1'] else '×'} / 3R先着={'○' if t['first3'] else '×'} / exit={t['exit_reason']}")
                viewer_trades.append({"no":no,"chart_id":chart_id,"side":"BUY","entry_i":t["entry_i"],"exit_i":t["exit_i"],"entry_price":round(t["entry_price"],6),"exit_price":round(t["exit_price"],6),"stop":round(t["stop"],6),"target":round(t["target"],6),"r":round(t["r"],4),"result":t["result"],"confidence":t["shape_score"],"setup":"高値更新即BUY" if chosen=="A" else "高値更新後リテストBUY","note":note}); no+=1
    per_group={v:{k:{"events":x["events"],**fmtm(x["metrics"])} for k,x in all_results[v].items()} for v in ("A","B")}
    summary={"data_source":"Dukascopy JForex / jetta endpoint via dukascopy-go; M15 BID+ASK, H1 aggregated from M15","period":f"{START_DATE} ～ {END_DATE}","data_info":data_info,"rules":{"trend":"EMA20 > EMA50、EMA50 > 5本前EMA50、H0時点終値 > EMA20","flush":"H0が直前1～3本内、H0→安値が1.5ATR以上、H0前12本安値を下抜く","recovery":"4本以内に下抜き水準へ終値復帰し、下落幅の70%以上を回復","breakout":"回復後8本以内にH0を終値で更新","A":"高値更新確定の次足始値でBUY","B":"高値更新後4本以内にH0付近をリテストして維持→次足始値でBUY","stop":"Flush安値 - 0.10ATR","target":"2R","max_hold":"24時間","execution":"シグナルはBID、BUY EntryはASK始値、Exit/SL/TPはBID。SL/TP同一足はSL先着として保守的判定。手数料・追加スリッページなし"},"pooled":{"A":fmtm(pooled["A"]),"B":fmtm(pooled["B"])},"per_group":per_group,"chosen_variant":chosen,"verdict":verdict,"robust_positive_groups":good_groups}
    with (OUTPUT_DIR/"summary.json").open("w",encoding="utf-8") as f: json.dump(summary,f,ensure_ascii=False,indent=2)
    notes=[f"判定: {verdict}",f"採用して表示するEntry方式: {chosen}（{'高値更新即BUY' if chosen=='A' else '高値更新後リテストBUY'}）",f"A pooled: N={pooled['A']['trades']}, 勝率={pooled['A']['win_rate']:.1f}%, 期待値={pooled['A']['expectancy_r']:.3f}R, PF={pooled['A']['pf']:.3f}, 最大DD={pooled['A']['max_dd_r']:.2f}R",f"B pooled: N={pooled['B']['trades']}, 勝率={pooled['B']['win_rate']:.1f}%, 期待値={pooled['B']['expectancy_r']:.3f}R, PF={pooled['B']['pf']:.3f}, 最大DD={pooled['B']['max_dd_r']:.2f}R","大口の意図は価格データだけでは断定せず、『上昇トレンド→急落/sweep→高速回復→高値更新』という観測可能な形を検証した。","初回研究のため手数料・追加スリッページは未反映。BUYのスプレッドはBID/ASK実データでEntryに反映。最終採用前にMT5ブローカーデータで再検証する。"]
    viewer={"meta":{"report_title":"Flush Recovery Breakout V1 / GBPJPY・XAUUSD M15/H1 直近2年","status":f"検証済み・{verdict}"},"strategy":{"strategy_id":"FRB_BUY_V1_20260827","name":"上昇トレンド急落Sweep→高速回復→高値更新BUY","hypothesis":"上昇トレンド中に直近安値を急激に掃除した後、短時間で回復し急落前高値を更新する局面は、その後も上昇継続しやすいかを検証する。","entry_logic":[summary["rules"]["trend"],summary["rules"]["flush"],summary["rules"]["recovery"],summary["rules"]["breakout"],summary["rules"][chosen]],"exit_logic":[summary["rules"]["stop"],summary["rules"]["target"],summary["rules"]["max_hold"]],"future_tests":["ATR閾値1.25/1.75/2.0比較","回復速度2/3/4本比較","ロンドン・NYセッション分離","高値更新幅の最低条件追加","MT5ブローカー実データ＋スリッページで再検証"]},"charts":charts,"trades":viewer_trades,"notes":notes}
    outpath=OUTPUT_DIR/"flush_recovery_v1_GBPJPY_XAUUSD_M15_H1_2y.json"
    with outpath.open("w",encoding="utf-8") as f: json.dump(viewer,f,ensure_ascii=False,separators=(",",":"))
    print("=== DATA INFO ==="); print(json.dumps(data_info,ensure_ascii=False,indent=2)); print("=== SUMMARY ==="); print(json.dumps(summary,ensure_ascii=False,indent=2)); print(f"Viewer JSON: {outpath} bytes={outpath.stat().st_size}")

if __name__ == "__main__": main()

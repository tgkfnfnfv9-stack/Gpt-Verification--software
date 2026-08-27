import csv, json, math, random, statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

START="2022-08-27"
END="2026-08-27"
OUT=Path("results"); OUT.mkdir(exist_ok=True)

@dataclass
class Bar:
    dt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float=0.0

def norm(s): return ''.join(ch.lower() for ch in s if ch.isalnum())
def parse_dt(x):
    s=str(x).strip().strip('"').replace('Z','+00:00')
    try:
        v=float(s)
        if v>1e12: return datetime.fromtimestamp(v/1000,tz=timezone.utc).replace(tzinfo=None)
        if v>1e9: return datetime.fromtimestamp(v,tz=timezone.utc).replace(tzinfo=None)
    except: pass
    for fmt in (None,'%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y/%m/%d %H:%M:%S'):
        try:
            d=datetime.fromisoformat(s) if fmt is None else datetime.strptime(s,fmt)
            if d.tzinfo: d=d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        except: pass
    raise ValueError(s)

def pick(fields,cands):
    m={norm(k):k for k in fields}
    for c in cands:
        if norm(c) in m: return m[norm(c)]
    for nk,orig in m.items():
        for c in cands:
            if nk.endswith(norm(c)): return orig
    return None

def load(path):
    with open(path,'r',encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f); fields=r.fieldnames
        tk=pick(fields,['timestamp','time','date','datetime']); ok=pick(fields,['open']); hk=pick(fields,['high']); lk=pick(fields,['low']); ck=pick(fields,['close']); vk=pick(fields,['volume','tick_volume','tickvolume'])
        out=[]
        for row in r:
            try:
                b=Bar(parse_dt(row[tk]),float(row[ok]),float(row[hk]),float(row[lk]),float(row[ck]),float(row[vk]) if vk and row.get(vk) not in (None,'') else 0.0)
                if b.high>=max(b.open,b.close) and b.low<=min(b.open,b.close) and b.open>0 and b.close>0: out.append(b)
            except: pass
    d={b.dt:b for b in out}; return [d[k] for k in sorted(d)]

def h1(bars):
    g={}
    for b in bars: g.setdefault(b.dt.replace(minute=0,second=0,microsecond=0),[]).append(b)
    out=[]
    for k in sorted(g):
        z=sorted(g[k],key=lambda x:x.dt)
        out.append(Bar(k,z[0].open,max(x.high for x in z),min(x.low for x in z),z[-1].close,sum(x.volume for x in z)))
    return out

def ema(vals,p):
    a=2/(p+1); out=[vals[0]]
    for v in vals[1:]: out.append(a*v+(1-a)*out[-1])
    return out

def atr(bars,p):
    tr=[bars[0].high-bars[0].low]
    for i in range(1,len(bars)):
        pc=bars[i-1].close
        tr.append(max(bars[i].high-bars[i].low,abs(bars[i].high-pc),abs(bars[i].low-pc)))
    out=[tr[0]]
    for i in range(1,len(tr)):
        out.append(sum(tr[:i+1])/(i+1) if i<p else (out[-1]*(p-1)+tr[i])/p)
    return out

def medspread(bid,ask):
    am={x.dt:x for x in ask}; s=[]
    for b in bid:
        a=am.get(b.dt)
        if a and a.open>=b.open: s.append(a.open-b.open)
    return statistics.median(s)

def metrics(ts):
    rs=[t['r'] for t in ts]; n=len(rs)
    if not n: return {'trades':0,'win_rate':0,'expectancy_r':0,'pf':0,'max_dd_r':0,'cum_r':0}
    pos=sum(x for x in rs if x>0); neg=-sum(x for x in rs if x<0); pf=pos/neg if neg>0 else 999.0
    eq=peak=mdd=0.0
    for x in rs:
        eq+=x; peak=max(peak,eq); mdd=max(mdd,peak-eq)
    return {'trades':n,'win_rate':100*sum(1 for x in rs if x>0)/n,'expectancy_r':sum(rs)/n,'pf':pf,'max_dd_r':mdd,'cum_r':sum(rs)}

def fmt(m): return {k:(round(v,3) if isinstance(v,float) else v) for k,v in m.items()}

def in_period(t,a,b): return datetime.fromisoformat(a)<=t<datetime.fromisoformat(b)
def subset(ts,a,b,bars): return [t for t in ts if in_period(bars[t['entry_i']].dt,a,b)]

def session_ok(h,s):
    if s=='london': return 6<=h<16
    if s=='london_ny': return 6<=h<21
    if s=='core': return 8<=h<17
    return True

def rvol_series(bars,lb=20):
    v=[b.volume for b in bars]; out=[None]*len(v)
    for i in range(lb,len(v)):
        med=statistics.median(v[i-lb:i]); out[i]=v[i]/med if med>0 else None
    return out

def detect(bars,e20,e50,a14,a50,rv,p):
    ev=[]; i=70; n=len(bars)
    while i<n-60:
        hw=p['h0_window']; h0i=max(range(i-hw,i),key=lambda z:bars[z].high); h0=bars[h0i].high
        if not 1<=i-h0i<=hw: i+=1; continue
        sl=p['slope_lb']
        if not (e20[h0i]>e50[h0i] and e50[h0i]>e50[h0i-sl] and bars[h0i].close>e20[h0i]): i+=1; continue
        a0=a14[h0i]
        if a0<=0: i+=1; continue
        prior_low=min(bars[z].low for z in range(max(0,h0i-p['sweep_lookback']),h0i))
        fl=bars[i].low; drop=h0-fl; sweep_depth=(prior_low-fl)/a0
        if drop<p['atr_mult']*a0 or fl>=prior_low or sweep_depth<p['sweep_depth']: i+=1; continue
        if rv[i] is None or rv[i]<p['rvol_min']: i+=1; continue
        vr=a14[i]/a50[i] if a50[i]>0 else 0
        if vr<p['vol_ratio_min']: i+=1; continue
        rec=None; rr=0
        for j in range(i+1,min(n,i+p['recovery_bars']+1)):
            ratio=(bars[j].close-fl)/drop if drop>0 else 0
            if bars[j].close>prior_low and ratio>=p['recovery_pct']:
                rec=j; rr=ratio; break
        if rec is None: i+=1; continue
        bo=None
        for k in range(rec,min(n-1,rec+p['breakout_bars']+1)):
            if bars[k].close>h0+p['breakout_buffer']*a0:
                bo=k; break
        if bo is None: i+=1; continue
        if p['breakout_rvol_min']>0 and (rv[bo] is None or rv[bo]<p['breakout_rvol_min']): i=bo+1; continue
        ret=None; abo=a14[bo]
        for q in range(bo+1,min(n-1,bo+p['retest_bars']+1)):
            near=bars[q].low<=h0+p['retest_touch']*abo
            hold=bars[q].close>=h0-p['retest_hold']*abo
            if near and hold and session_ok(bars[q].dt.hour,p['session']): ret=q; break
        if ret is not None and ret+1<n:
            ev.append({'entry_i':ret+1,'flush_i':i,'recovery_i':rec,'breakout_i':bo,'retest_i':ret,'h0':h0,'flush_low':fl,'atr0':a0,'drop_atr':drop/a0,'sweep_depth_atr':sweep_depth,'flush_rvol':rv[i],'vol_ratio':vr,'recovery_ratio':rr})
        i=bo+1
    return ev

def simulate(bid,ask,events,target_r=2.25,max_hold=24,stop_buffer=0.0):
    am={x.dt:x for x in ask}; fs=medspread(bid,ask); out=[]; next_allowed=0
    for e in events:
        ii=e['entry_i']
        if ii<next_allowed or ii>=len(bid): continue
        ab=am.get(bid[ii].dt); entry=ab.open if ab else bid[ii].open+fs
        stop=e['flush_low']-stop_buffer*e['atr0']; risk=entry-stop
        if risk<=0 or risk/entry>0.05: continue
        target=entry+target_r*risk; end=min(len(bid)-1,ii+max_hold-1)
        xi=end; xp=bid[end].close; reason='TIME'
        for z in range(ii,end+1):
            hs=bid[z].low<=stop; ht=bid[z].high>=target
            if hs and ht: xi=z; xp=stop; reason='SL_SAME_BAR'; break
            if hs: xi=z; xp=stop; reason='SL'; break
            if ht: xi=z; xp=target; reason=f'TP{target_r}R'; break
        r=(xp-entry)/risk
        out.append({'entry_i':ii,'exit_i':xi,'entry_price':entry,'exit_price':xp,'stop':stop,'target':target,'r':r,'result':'WIN' if r>0 else ('LOSS' if r<0 else 'EVEN'),'exit_reason':reason,'event':e})
        next_allowed=xi+1
    return out

def random_params(rng):
    return {
      'slope_lb':rng.choice([2,5]),
      'h0_window':rng.choice([3,5,7]),
      'atr_mult':rng.choice([0.75,0.9,1.0,1.15,1.3]),
      'sweep_lookback':rng.choice([10,12,16]),
      'sweep_depth':rng.choice([0.0,0.03,0.06,0.10]),
      'recovery_bars':rng.choice([4,6,8]),
      'recovery_pct':rng.choice([0.40,0.45,0.55,0.65]),
      'breakout_bars':rng.choice([8,10,14,18]),
      'breakout_buffer':rng.choice([0.0,0.02,0.04]),
      'retest_bars':rng.choice([4,6,10,14]),
      'retest_touch':rng.choice([0.35,0.50,0.65]),
      'retest_hold':rng.choice([0.15,0.20,0.30]),
      'session':rng.choice(['london','london_ny']),
      'rvol_min':rng.choice([0.65,0.75,0.85,0.95]),
      'vol_ratio_min':rng.choice([0.75,0.85,0.95]),
      'breakout_rvol_min':rng.choice([0.0,0.65,0.80])
    }

def keyp(p): return json.dumps(p,sort_keys=True)

def main():
    bid=h1(load('data/GBPJPY_M15_bid.csv')); ask=h1(load('data/GBPJPY_M15_ask.csv'))
    closes=[b.close for b in bid]; e20=ema(closes,20); e50=ema(closes,50); a14=atr(bid,14); a50=atr(bid,50); rv=rvol_series(bid,20)
    rng=random.Random(20260827); seen=set(); cand=[]
    for _ in range(1200):
        p=random_params(rng); kp=keyp(p)
        if kp in seen: continue
        seen.add(kp)
        ev=detect(bid,e20,e50,a14,a50,rv,p); ts=simulate(bid,ask,ev,2.25,24,0.0)
        yA=subset(ts,'2023-08-27','2024-08-27',bid); yB=subset(ts,'2024-08-27','2025-08-27',bid); dev=yA+yB
        ma,mb,md=metrics(yA),metrics(yB),metrics(dev)
        if ma['trades']<8 or mb['trades']<8 or md['trades']<22: continue
        if ma['expectancy_r']<0.05 or mb['expectancy_r']<0.05 or md['expectancy_r']<0.18 or md['pf']<1.35: continue
        score=md['expectancy_r'] + 0.008*min(md['trades'],45) + 0.04*math.log(max(md['pf'],1)) - 0.018*md['max_dd_r'] + 0.12*min(ma['expectancy_r'],mb['expectancy_r'])
        cand.append((score,p,ma,mb,md))
    cand.sort(key=lambda x:x[0],reverse=True)
    if not cand: raise RuntimeError('no candidates')

    # Select only from development data. Prefer a robust candidate near the top with >=26 dev trades.
    chosen=None
    for x in cand[:80]:
        if x[4]['trades']>=26:
            chosen=x; break
    if chosen is None: chosen=cand[0]
    score,p,ma,mb,md=chosen
    ev=detect(bid,e20,e50,a14,a50,rv,p)

    # Exit variants chosen on development only for the fixed entry setup.
    exits=[]
    for target in [1.75,2.0,2.25,2.5]:
      for hold in [18,24,36]:
        ts=simulate(bid,ask,ev,target,hold,0.0)
        a=subset(ts,'2023-08-27','2024-08-27',bid); b=subset(ts,'2024-08-27','2025-08-27',bid); d=a+b
        m=metrics(d); m1=metrics(a); m2=metrics(b)
        if m1['trades']<8 or m2['trades']<8 or min(m1['expectancy_r'],m2['expectancy_r'])<0: continue
        es=m['expectancy_r']+0.03*math.log(max(m['pf'],1))-0.012*m['max_dd_r']
        exits.append((es,target,hold,m1,m2,m))
    exits.sort(reverse=True,key=lambda x:x[0])
    ex=exits[0]; _,target,hold,_,_,_=ex
    allts=simulate(bid,ask,ev,target,hold,0.0)

    prior=subset(allts,'2022-08-27','2023-08-27',bid)
    yA=subset(allts,'2023-08-27','2024-08-27',bid)
    yB=subset(allts,'2024-08-27','2025-08-27',bid)
    holdout=subset(allts,'2025-08-27','2026-08-27',bid)
    latest2=subset(allts,'2024-08-27','2026-08-27',bid)

    # V4 reference on latest2 (known result from prior research)
    v4_ref={'trades':19,'win_rate':78.947,'expectancy_r':0.855,'pf':5.849,'max_dd_r':3.0,'cum_r':16.242}

    # Robustness around selected volume / volatility thresholds, entry rules otherwise fixed.
    robust=[]
    for rvmin in sorted(set([max(0.55,p['rvol_min']-0.10),p['rvol_min'],p['rvol_min']+0.10])):
      for vrmin in sorted(set([max(0.65,p['vol_ratio_min']-0.10),p['vol_ratio_min'],p['vol_ratio_min']+0.10])):
        pp=dict(p); pp['rvol_min']=round(rvmin,2); pp['vol_ratio_min']=round(vrmin,2)
        t=simulate(bid,ask,detect(bid,e20,e50,a14,a50,rv,pp),target,hold,0.0)
        robust.append({'rvol_min':pp['rvol_min'],'vol_ratio_min':pp['vol_ratio_min'],'dev':fmt(metrics(subset(t,'2023-08-27','2025-08-27',bid))),'latest_year_holdout':fmt(metrics(subset(t,'2025-08-27','2026-08-27',bid)))})

    # Build latest-2y viewer JSON.
    start_i=next(i for i,b in enumerate(bid) if b.dt>=datetime(2024,8,27))
    end_i=next((i for i,b in enumerate(bid) if b.dt>=datetime(2026,8,27)),len(bid))
    cb=bid[start_i:end_i]
    chart_id='gbpjpy_h1_flush_recovery_v5_robust'
    def cj(b): return {'time':b.dt.isoformat(timespec='seconds')+'+00:00','open':round(b.open,6),'high':round(b.high,6),'low':round(b.low,6),'close':round(b.close,6),'volume':round(b.volume,4)}
    chart={'id':chart_id,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(b) for b in cb],
      'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[start_i:end_i]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[start_i:end_i]]}],
      'panes':[{'label':'ATR(14)','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14[start_i:end_i]]}]},{'label':'出来高','series':[{'kind':'histogram','label':'H1 Volume','values':[round(x.volume,4) for x in cb]}]},{'label':'RVOL20','levels':[p['rvol_min'],1.0],'series':[{'kind':'line','label':'RVOL20','values':[None if x is None else round(x,6) for x in rv[start_i:end_i]]}]},{'label':'ATR14 / ATR50','levels':[p['vol_ratio_min'],1.0],'series':[{'kind':'line','label':'Volatility Ratio','values':[round(a14[i]/a50[i],6) if a50[i]>0 else None for i in range(start_i,end_i)]}]}]}
    vt=[]
    for no,t in enumerate(latest2,1):
        e=t['event']; nt={'no':no,'chart_id':chart_id,'side':'BUY','entry_i':t['entry_i']-start_i,'exit_i':t['exit_i']-start_i,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V5 Robust','note':f"Flush RVOL={e['flush_rvol']:.2f}, ATR比={e['vol_ratio']:.2f}, Drop={e['drop_atr']:.2f}ATR, Sweep={e['sweep_depth_atr']:.2f}ATR, {t['exit_reason']}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)

    summary={'data_source':'Dukascopy JForex / jetta via dukascopy-go v0.2.0; GBPJPY M15 BID+ASK aggregated to H1','period_all':'2022-08-27 ～ 2026-08-27','selection_policy':'Entry/exit parameters selected only on 2023-08-27～2025-08-26 development. 2025-08-27～2026-08-26 evaluated after selection. 2022-08-27～2023-08-26 is additional prior validation.','selected_params':p,'selected_target_r':target,'selected_max_hold_hours':hold,'development_yearA':fmt(metrics(yA)),'development_yearB':fmt(metrics(yB)),'development_2y':fmt(metrics(yA+yB)),'latest_year_holdout':fmt(metrics(holdout)),'prior_year_validation':fmt(metrics(prior)),'latest_2y':fmt(metrics(latest2)),'v4_reference_latest_2y':v4_ref,'robustness_volume_volatility':robust,'top_development_candidates':[{'score':round(x[0],4),'params':x[1],'yearA':fmt(x[2]),'yearB':fmt(x[3]),'dev':fmt(x[4])} for x in cand[:12]]}
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V5 Robust','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V5_ROBUST','name':'Flush Recovery V5 Robust','hypothesis':'上昇中のSweep/Flushが相対出来高と十分なボラティリティを伴い、短時間で回復して高値を更新した後の押し目は再上昇しやすい。','entry_logic':[f"選択条件: {json.dumps(p,ensure_ascii=False)}",'価格・Volume・Volatility条件はEntryより前に確定したデータのみ使用','BUY EntryはASK始値'],'exit_logic':[f'Flush安値をSL',f'TP {target}R',f'最大保有 {hold}時間','同一H1足でSL/TP両方到達はSL先着扱い'],'future_tests':['MT5ブローカーのtick volumeで再検証','未使用の将来期間を継続ウォークフォワード','銘柄横断で同じ閾値が機能するか確認']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V5_Robust_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V5_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('=== V5 SUMMARY ===')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

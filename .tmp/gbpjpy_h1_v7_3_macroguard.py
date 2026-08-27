import csv, importlib.util, json, math, statistics
from datetime import datetime, date
from pathlib import Path

spec=importlib.util.spec_from_file_location('m','/tmp/gbpjpy_h1_v8_macro.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b=m.b
OUT=Path('results'); OUT.mkdir(exist_ok=True)

def fm(ts): return b.fmt(b.metrics(ts))
def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)

def load_daily(path, col):
    rows=[]
    with open(path,'r',encoding='utf-8-sig') as f:
        r=csv.DictReader(f)
        for row in r:
            ds=row.get('DATE') or row.get('observation_date') or row.get('date')
            vs=row.get(col) or row.get('value')
            if not ds or not vs or vs in ('.','NA',''): continue
            try: rows.append((datetime.fromisoformat(ds).date(),float(vs)))
            except: pass
    rows.sort(); return rows

def load_monthly(path, col):
    return load_daily(path,col)

def shift_month(d, n):
    k=d.year*12+(d.month-1)+n
    return date(k//12,k%12+1,1)

def vix_features(rows,dt):
    vals=[(d,v) for d,v in rows if d<dt.date()]
    if not vals: return None
    cur=vals[-1][1]
    prev20=[v for _,v in vals[-20:]]
    med20=statistics.median(prev20) if prev20 else cur
    prev5=vals[-6][1] if len(vals)>=6 else vals[0][1]
    return {'vix':cur,'vix_ratio20':cur/med20 if med20>0 else 1.0,'vix_chg5':cur-prev5}

def yield_features(uk,jp,dt):
    # Conservative publication timing: use only observations at least two calendar months old.
    # Example: a March H1 entry can use January monthly yield data, never February/March.
    cutoff=shift_month(date(dt.year,dt.month,1),-2)
    ud={d:v for d,v in uk if d<=cutoff}; jd={d:v for d,v in jp if d<=cutoff}
    common=sorted(set(ud)&set(jd))
    if not common: return None
    d0=common[-1]; sp=ud[d0]-jd[d0]
    d3=common[-4] if len(common)>=4 else common[0]
    d6=common[-7] if len(common)>=7 else common[0]
    return {'yield_month':d0.isoformat(),'uk10':ud[d0],'jp10':jd[d0],'spread':sp,'spread_chg3':sp-(ud[d3]-jd[d3]),'spread_chg6':sp-(ud[d6]-jd[d6])}

def features(vx,uk,jp,dt):
    a=vix_features(vx,dt); c=yield_features(uk,jp,dt)
    if a is None or c is None: return None
    a.update(c); return a

def block(f,cfg):
    if f is None: return True
    mode=cfg['mode']; vm=cfg.get('vix_max'); sm=cfg.get('spread_min'); cm=cfg.get('chg3_min'); ex=cfg.get('extreme_vix')
    high=(vm is not None and f['vix']>vm)
    low=(sm is not None and f['spread']<sm)
    falling=(cm is not None and f['spread_chg3']<cm)
    extreme=(ex is not None and f['vix']>ex)
    if mode=='vix_only': return high
    if mode=='spread_only': return low
    if mode=='vix_and_spread': return high and low
    if mode=='vix_and_fall': return high and falling
    if mode=='vix_and_macro': return high and (low or falling)
    if mode=='extreme_or_combo': return extreme or (high and (low or falling))
    raise ValueError(mode)

def complexity(cfg):
    return 1+sum(cfg.get(k) is not None for k in ('vix_max','spread_min','chg3_min','extreme_vix'))

def build_candidates():
    out=[]
    for vm in [18,20,22,25,27.5,30]: out.append({'mode':'vix_only','vix_max':vm,'spread_min':None,'chg3_min':None,'extreme_vix':None})
    for sm in [0.25,0.5,0.75,1.0,1.25,1.5,1.75,2.0,2.25]: out.append({'mode':'spread_only','vix_max':None,'spread_min':sm,'chg3_min':None,'extreme_vix':None})
    for vm in [18,20,22,25,27.5,30]:
      for sm in [0.5,0.75,1.0,1.25,1.5,1.75,2.0]: out.append({'mode':'vix_and_spread','vix_max':vm,'spread_min':sm,'chg3_min':None,'extreme_vix':None})
      for cm in [-0.75,-0.5,-0.35,-0.25,-0.15,0.0]: out.append({'mode':'vix_and_fall','vix_max':vm,'spread_min':None,'chg3_min':cm,'extreme_vix':None})
      for sm in [0.75,1.0,1.25,1.5,1.75]:
       for cm in [-0.5,-0.35,-0.25,-0.15,0.0]: out.append({'mode':'vix_and_macro','vix_max':vm,'spread_min':sm,'chg3_min':cm,'extreme_vix':None})
       for cm in [-0.35,-0.25,-0.15]: out.append({'mode':'extreme_or_combo','vix_max':vm,'spread_min':sm,'chg3_min':cm,'extreme_vix':35})
    return out

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P)
    base=m.simulate_v7(bid,ask,events,a14,m.V7X)
    vx=load_daily('data/VIXCLS.csv','VIXCLS')
    uk=load_monthly('data/UK10Y.csv','IRLTLT01GBM156N'); jp=load_monthly('data/JP10Y.csv','IRLTLT01JPM156N')
    feats={e['entry_i']:features(vx,uk,jp,bid[e['entry_i']].dt) for e in events}
    years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    C=[]
    for cfg in build_candidates():
        ev=[e for e in events if not block(feats[e['entry_i']],cfg)]
        ts=m.simulate_v7(bid,ask,ev,a14,m.V7X)
        ym=[b.metrics(sub(ts,a,z,bid)) for a,z in years]; dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
        if dm['trades']<45 or min(y['trades'] for y in ym)<3: continue
        if ym[0]['expectancy_r']<0 or dm['expectancy_r']<0.38: continue
        exps=[y['expectancy_r'] for y in ym]; mn=min(exps); sd=statistics.pstdev(exps)
        if mn < -0.25: continue
        score=dm['expectancy_r']+0.005*min(dm['trades'],74)+0.18*ym[0]['expectancy_r']+0.10*mn-0.07*sd+0.025*math.log(max(dm['pf'],1))-0.016*dm['max_dd_r']-0.012*(complexity(cfg)-2)
        C.append((score,cfg,ym,dm,ev,ts))
    C.sort(key=lambda x:x[0],reverse=True)
    if not C: raise RuntimeError('No V7.3 macro guard candidate')
    # Select from development only. Prefer simple conjunction guards and at least 50 dev trades.
    chosen=next((x for x in C[:80] if x[1]['mode'] in ('vix_and_spread','vix_and_fall','vix_and_macro') and x[3]['trades']>=50),C[0])
    score,cfg,ym,dm,ev,ts=chosen
    periods={'external_new_2019_20':('2019-08-27','2020-08-27'),'covid_known_2020_21':('2020-08-27','2021-08-27'),'development_2020_25':('2020-08-27','2025-08-27'),'recent_external_2025_26':('2025-08-27','2026-08-27'),'latest_2y':('2024-08-27','2026-08-27'),'full_2019_26':('2019-08-27','2026-08-27')}
    bm={k:fm(sub(base,a,z,bid)) for k,(a,z) in periods.items()}; gm={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}
    top=[]
    for x in C[:25]:
        top.append({'score':round(x[0],4),'cfg':x[1],'complexity':complexity(x[1]),'dev_years':[b.fmt(y) for y in x[2]],'development':b.fmt(x[3]),'external_2019_20':fm(sub(x[5],'2019-08-27','2020-08-27',bid)),'recent_external_2025_26':fm(sub(x[5],'2025-08-27','2026-08-27',bid)),'latest_2y':fm(sub(x[5],'2024-08-27','2026-08-27',bid))})
    summary={'data_source':'Dukascopy GBPJPY H1 BID+ASK + FRED VIXCLS daily + OECD/FRED UK/Japan 10Y monthly yields','timing':{'vix':'strictly prior calendar-date close only','yield':'conservative 2-calendar-month lag; current/previous month monthly averages are never used'},'research_policy':'V7 entry/exit fixed. Macro guard selected only on 2020-08-27～2025-08-26 development, including known COVID weakness. 2019-08-27～2020-08-26 and 2025-08-27～2026-08-26 are reported after selection and not used by the selector.','v6_entry_params':m.V6P,'v7_exit':m.V7X,'selected_v7_3_guard':cfg,'guard_meaning':'Block a V7 GBPJPY long only when the selected global-risk and UK-Japan yield/carry conditions indicate macro pressure. Conjunction modes deliberately avoid discarding every high-VIX trade.','v7_baseline':bm,'v7_3_macro_guard':gm,'development_years':[b.fmt(y) for y in ym],'top_candidates':top,'interpretation':['A local stop-sweep/recovery pattern can lose reliability when cross-asset risk repricing and GBP-vs-JPY yield support move against the long direction.','Monthly yield inputs are deliberately lagged and therefore represent slow macro regime, not event-time surprise.','This does not replace a historical BoE/BoJ/high-impact calendar blackout test.']}
    print('=== V7.3 MACRO GUARD SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))
    latest=sub(ts,'2024-08-27','2026-08-27',bid); si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_v7_3_macroguard'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    vv=[]; sv=[]; cv=[]
    for i in range(si,ei):
        f=features(vx,uk,jp,bid[i].dt); vv.append(None if f is None else round(f['vix'],4)); sv.append(None if f is None else round(f['spread'],5)); cv.append(None if f is None else round(f['spread_chg3'],5))
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'Previous VIX','series':[{'kind':'line','label':'VIX','values':vv}]},{'label':'UK10Y-JP10Y (2m lag)','series':[{'kind':'line','label':'Yield spread','values':sv},{'kind':'line','label':'3m spread change','values':cv}]}]}
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']; f=feats[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7.3 Macro Guard','note':f"exit={t['exit_reason']}, VIX={f['vix']:.2f}, spread={f['spread']:.2f}, d3={f['spread_chg3']:.2f}, ymonth={f['yield_month']}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7.3 Macro Guard','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_3_MACRO','name':'V7 + Macro Risk Guard','hypothesis':'Technical stop-sweep/recovery longs are less reliable when global risk and GBP-vs-JPY yield/carry regime are simultaneously hostile.','entry_logic':['V6/V7 technical entry unchanged','Macro guard '+json.dumps(cfg,ensure_ascii=False),'VIX prior-date only; monthly yields use 2-month lag'],'exit_logic':['V7 exit unchanged'],'future_tests':['Historical BoE/BoJ decision blackout','UK/JP high-impact economic calendar','MT5 broker data and execution costs']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_3_MacroGuard_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_3_MacroGuard_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

import csv, importlib.util, json, math, statistics
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('m','/tmp/gbpjpy_h1_v8_macro.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b=m.b
OUT=Path('results'); OUT.mkdir(exist_ok=True)

def fm(ts): return b.fmt(b.metrics(ts))
def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)

def load_vix(path):
    rows=[]
    with open(path,'r',encoding='utf-8-sig') as f:
        r=csv.DictReader(f)
        for row in r:
            ds=row.get('DATE') or row.get('observation_date') or row.get('date')
            vs=row.get('VIXCLS') or row.get('value')
            if not ds or not vs or vs in ('.','NA',''): continue
            try: rows.append((datetime.fromisoformat(ds).date(),float(vs)))
            except: pass
    rows.sort(); return rows

def vix_features(rows,dt):
    vals=[(d,v) for d,v in rows if d<dt.date()]
    if not vals: return None
    cur=vals[-1][1]
    prev20=[v for _,v in vals[-20:]]
    med20=statistics.median(prev20) if prev20 else cur
    prev5=vals[-6][1] if len(vals)>=6 else vals[0][1]
    return {'vix':cur,'ratio20':cur/med20 if med20>0 else 1.0,'chg5':cur-prev5,'med20':med20}

def allow(f,cfg):
    if f is None: return False
    if cfg['level_max'] is not None and f['vix']>cfg['level_max']: return False
    if cfg['ratio20_max'] is not None and f['ratio20']>cfg['ratio20_max']: return False
    if cfg['chg5_max'] is not None and f['chg5']>cfg['chg5_max']: return False
    return True

def complexity(cfg): return sum(v is not None for v in cfg.values())

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P)
    base=m.simulate_v7(bid,ask,events,a14,m.V7X)
    vx=load_vix('data/VIXCLS.csv'); feats={e['entry_i']:vix_features(vx,bid[e['entry_i']].dt) for e in events}
    years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    levels=[None,20,22,25,30,35]
    ratios=[None,1.05,1.10,1.15,1.20,1.30,1.50]
    chgs=[None,2,4,6,8,10,15]
    C=[]
    for lv in levels:
      for rr in ratios:
       for cg in chgs:
        cfg={'level_max':lv,'ratio20_max':rr,'chg5_max':cg}
        if complexity(cfg)==0: continue
        ev=[e for e in events if allow(feats[e['entry_i']],cfg)]
        ts=m.simulate_v7(bid,ask,ev,a14,m.V7X)
        ym=[b.metrics(sub(ts,a,z,bid)) for a,z in years]; dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
        if dm['trades']<38 or min(y['trades'] for y in ym)<3: continue
        if ym[0]['expectancy_r']<0 or dm['expectancy_r']<0.35: continue
        mn=min(y['expectancy_r'] for y in ym); sd=statistics.pstdev([y['expectancy_r'] for y in ym])
        score=dm['expectancy_r']+0.006*min(dm['trades'],70)+0.20*ym[0]['expectancy_r']+0.10*mn-0.07*sd+0.02*math.log(max(dm['pf'],1))-0.014*dm['max_dd_r']-0.025*(complexity(cfg)-1)
        C.append((score,cfg,ym,dm,ev,ts))
    C.sort(key=lambda x:x[0],reverse=True)
    if not C: raise RuntimeError('No VIX shock candidate with nonnegative COVID year')
    # Prefer a simple one/two-filter plateau and >=42 trades.
    chosen=next((x for x in C[:80] if complexity(x[1])<=2 and x[3]['trades']>=42),C[0])
    score,cfg,ym,dm,ev,ts=chosen
    periods={'external_new_2019_20':('2019-08-27','2020-08-27'),'covid_known_2020_21':('2020-08-27','2021-08-27'),'old_external_2021_22':('2021-08-27','2022-08-27'),'development_2020_25':('2020-08-27','2025-08-27'),'recent_2025_26':('2025-08-27','2026-08-27'),'latest_2y':('2024-08-27','2026-08-27'),'full_2019_26':('2019-08-27','2026-08-27')}
    bm={k:fm(sub(base,a,z,bid)) for k,(a,z) in periods.items()}; gm={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}
    summary={'data_source':'Dukascopy H1 + FRED VIXCLS daily','timing':'Every VIX feature uses observations strictly before the H1 entry calendar date. No same-day close/future data.','research_policy':'Known-bad 2020-21 moved into development. New external 2019-08-27～2020-08-26 is untouched for V7.2 selection and includes first COVID shock months.','v6_entry_params':m.V6P,'v7_exit':m.V7X,'selected_vix_shock_guard':cfg,'feature_meaning':{'level_max':'maximum previous daily VIX close','ratio20_max':'previous VIX / median of previous up-to-20 daily VIX observations','chg5_max':'previous VIX minus VIX about five trading days earlier'},'v7_baseline':bm,'v7_2_guard':gm,'dev_years':[b.fmt(y) for y in ym],'top_candidates':[{'score':round(x[0],4),'cfg':x[1],'complexity':complexity(x[1]),'years':[b.fmt(y) for y in x[2]],'dev':b.fmt(x[3]),'external_2019_20':fm(sub(x[5],'2019-08-27','2020-08-27',bid)),'recent_2025_26':fm(sub(x[5],'2025-08-27','2026-08-27',bid))} for x in C[:20]],'interpretation':'VIX shock guard is a cross-asset risk/fundamental regime proxy. It does not prove a specific news cause; it attempts to suppress technical longs when risk repricing is unusually strong.','future':['Historical BoE/BoJ and UK/JP high-impact economic-calendar blackout should be tested separately.','UK-Japan rate/yield differential is the next GBPJPY-specific fundamental variable if external crisis performance remains weak.']}
    print('=== V7.2 VIX SHOCK SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))
    latest=sub(ts,'2024-08-27','2026-08-27',bid); si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_v7_2_vixshock'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    vixv=[]; ratv=[]
    for i in range(si,ei):
        f=vix_features(vx,bid[i].dt); vixv.append(None if f is None else round(f['vix'],4)); ratv.append(None if f is None else round(f['ratio20'],6))
    panes=[{'label':'Previous VIX','series':[{'kind':'line','label':'VIX','values':vixv}]},{'label':'VIX / 20d median','series':[{'kind':'line','label':'VIX shock ratio','values':ratv}]}]
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':panes}
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']; f=feats[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7.2 VIX Shock Guard','note':f"exit={t['exit_reason']}, VIX={f['vix']:.2f}, ratio20={f['ratio20']:.2f}, chg5={f['chg5']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7.2 VIX Shock Guard','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_2_VIXSHOCK','name':'V7 + VIX Shock Guard','hypothesis':'When global risk repricing is unusually strong, technical stop-sweep/recovery longs are less reliable.','entry_logic':['V6 entry unchanged','VIX guard '+json.dumps(cfg,ensure_ascii=False),'All VIX inputs strictly prior-date'],'exit_logic':['V7 exit unchanged'],'future_tests':['BoE/BoJ economic calendar blackout','UK-JP yield differential','MT5 broker swap/tick volume']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_2_VIXShock_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_2_VIXShock_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

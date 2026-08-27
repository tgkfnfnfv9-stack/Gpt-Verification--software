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

def daily_closes(path):
    bars=b.load(path)
    d={}
    for x in bars:
        d[x.dt.date()]=x.close
    return sorted(d.items())

def prior_features(vix_rows, uj_rows, gu_rows, dt):
    day=dt.date()
    vv=[(d,v) for d,v in vix_rows if d<day]
    uj=[(d,v) for d,v in uj_rows if d<day]
    gu=[(d,v) for d,v in gu_rows if d<day]
    if not vv or len(uj)<6 or len(gu)<6: return None
    vix=vv[-1][1]
    vix5=vv[-6][1] if len(vv)>=6 else vv[0][1]
    ujret=uj[-1][1]/uj[-6][1]-1.0 if uj[-6][1] else 0.0
    guret=gu[-1][1]/gu[-6][1]-1.0 if gu[-6][1] else 0.0
    return {'vix':vix,'vix_chg5':vix-vix5,'usdjpy_ret5':ujret,'gbpusd_ret5':guret}

def allow(f,cfg):
    if f is None: return False
    # Layer 1: panic ceiling. Extremely high VIX blocks regardless of FX legs.
    if cfg['hard_vix'] is not None and f['vix']>cfg['hard_vix']: return False
    # Layer 2: risk-off only matters for GBPJPY long when yen is actually strengthening.
    if f['vix']>cfg['soft_vix'] and f['usdjpy_ret5']<cfg['usdjpy_min']: return False
    # Optional Layer 3: even at lower VIX, block if GBP weakens while JPY strengthens.
    if cfg['gbpusd_min'] is not None and f['usdjpy_ret5']<cfg['usdjpy_min'] and f['gbpusd_ret5']<cfg['gbpusd_min']: return False
    return True

def complexity(cfg): return 2 + (1 if cfg['hard_vix'] is not None else 0) + (1 if cfg['gbpusd_min'] is not None else 0)

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P)
    base=m.simulate_v7(bid,ask,events,a14,m.V7X)

    vx=load_vix('data/VIXCLS.csv')
    uj=daily_closes('data/USDJPY_M15_bid.csv')
    gu=daily_closes('data/GBPUSD_M15_bid.csv')
    feats={e['entry_i']:prior_features(vx,uj,gu,bid[e['entry_i']].dt) for e in events}

    # Selection uses 2020-08-27..2025-08-27. Known V7 COVID weakness is deliberately in development.
    # 2025-26 is not used for parameter selection. 2018-19 is fresh external validation.
    years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    C=[]
    for soft in [18,20,22,25,27.5]:
      for hard in [None,30,35,40,50]:
       if hard is not None and hard<=soft: continue
       for ujmin in [-0.020,-0.015,-0.010,-0.0075,-0.005,0.0]:
        for gmin in [None,-0.020,-0.015,-0.010,-0.005,0.0]:
          cfg={'soft_vix':soft,'hard_vix':hard,'usdjpy_min':ujmin,'gbpusd_min':gmin}
          ev=[e for e in events if allow(feats[e['entry_i']],cfg)]
          ts=m.simulate_v7(bid,ask,ev,a14,m.V7X)
          ym=[b.metrics(sub(ts,a,z,bid)) for a,z in years]
          dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
          if dm['trades']<55 or min(y['trades'] for y in ym)<5: continue
          # Main objective: repair COVID year without destroying the rest of V7.
          if ym[0]['expectancy_r']<-0.03 or dm['expectancy_r']<0.40 or dm['pf']<2.0: continue
          exps=[y['expectancy_r'] for y in ym]
          mn=min(exps); sd=statistics.pstdev(exps)
          score=(dm['expectancy_r'] + 0.005*min(dm['trades'],75) + 0.22*ym[0]['expectancy_r'] +
                 0.10*mn - 0.07*sd + 0.02*math.log(max(dm['pf'],1)) - 0.012*dm['max_dd_r'] -
                 0.018*max(0,complexity(cfg)-2))
          C.append((score,cfg,ym,dm,ev,ts))
    C.sort(key=lambda x:x[0],reverse=True)
    if not C: raise RuntimeError('No stable V7.3 candidate')

    # Prefer simple/plateau candidate with enough development trades and nonnegative worst development year.
    chosen=next((x for x in C[:100] if complexity(x[1])<=3 and x[3]['trades']>=58 and min(y['expectancy_r'] for y in x[2])>=0),C[0])
    score,cfg,ym,dm,ev,ts=chosen

    periods={
      'external_fresh_2018_19':('2018-08-27','2019-08-27'),
      'external_seen_2019_20':('2019-08-27','2020-08-27'),
      'covid_known_2020_21':('2020-08-27','2021-08-27'),
      'development_2020_25':('2020-08-27','2025-08-27'),
      'recent_holdout_2025_26':('2025-08-27','2026-08-27'),
      'latest_2y':('2024-08-27','2026-08-27'),
      'full_2018_26':('2018-08-27','2026-08-27')}
    bm={k:fm(sub(base,a,z,bid)) for k,(a,z) in periods.items()}
    gm={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}

    # Sensitivity around chosen thresholds. This is diagnostic only, not used to replace chosen config.
    sensitivity=[]
    tests=[]
    for dv in [-2,0,2]:
        cc=dict(cfg); cc['soft_vix']=max(15,cfg['soft_vix']+dv); tests.append(('soft_vix',cc['soft_vix'],cc))
    for du in [-0.005,0,0.005]:
        cc=dict(cfg); cc['usdjpy_min']=cfg['usdjpy_min']+du; tests.append(('usdjpy_min',round(cc['usdjpy_min'],4),cc))
    if cfg['hard_vix'] is not None:
        for dh in [-5,0,5]:
            cc=dict(cfg); cc['hard_vix']=cfg['hard_vix']+dh
            if cc['hard_vix']>cc['soft_vix']: tests.append(('hard_vix',cc['hard_vix'],cc))
    seen=set()
    for field,val,cc in tests:
        key=json.dumps(cc,sort_keys=True)
        if key in seen: continue
        seen.add(key)
        ee=[e for e in events if allow(feats[e['entry_i']],cc)]
        tt=m.simulate_v7(bid,ask,ee,a14,m.V7X)
        sensitivity.append({'parameter':field,'value':val,'development_2020_25':fm(sub(tt,'2020-08-27','2025-08-27',bid)),'fresh_2018_19':fm(sub(tt,'2018-08-27','2019-08-27',bid)),'recent_2025_26':fm(sub(tt,'2025-08-27','2026-08-27',bid)),'latest_2y':fm(sub(tt,'2024-08-27','2026-08-27',bid))})

    summary={
      'data_source':'Dukascopy GBPJPY BID+ASK + USDJPY BID + GBPUSD BID M15 aggregated/derived daily, plus FRED VIXCLS daily',
      'timing':'Every cross-asset feature uses observations strictly before the GBPJPY H1 entry calendar date. Same-day closes are never used.',
      'research_policy':'2020-21 known weakness is development. 2025-26 is holdout for V7.3 selection. 2018-08-27～2019-08-26 is newly downloaded fresh external validation.',
      'base_v6_entry_params':m.V6P,'base_v7_exit':m.V7X,
      'selected_v7_3_guard':cfg,
      'guard_logic':['Block if previous VIX > hard_vix','Block if previous VIX > soft_vix AND USDJPY prior 5-trading-day return < usdjpy_min','Optional: block when USDJPY is weak and GBPUSD prior 5-day return < gbpusd_min'],
      'interpretation':'VIX measures broad risk repricing; USDJPY verifies whether that risk-off is actually producing yen strength; GBPUSD optionally verifies whether sterling itself is weakening. This is a market-regime proxy, not proof of a specific fundamental cause.',
      'v7_baseline':bm,'v7_3_guard':gm,'development_years':[b.fmt(y) for y in ym],
      'top_candidates':[{'score':round(x[0],4),'cfg':x[1],'complexity':complexity(x[1]),'dev':b.fmt(x[3]),'years':[b.fmt(y) for y in x[2]],'fresh_2018_19':fm(sub(x[5],'2018-08-27','2019-08-27',bid)),'recent_2025_26':fm(sub(x[5],'2025-08-27','2026-08-27',bid)),'latest_2y':fm(sub(x[5],'2024-08-27','2026-08-27',bid))} for x in C[:25]],
      'sensitivity':sensitivity,
      'next_research':['Historical BoE/BoJ decision blackout remains separate because an accurate event calendar is required.','UK-Japan yield differential can be added only with a sufficiently frequent, timestamp-safe historical source.']}
    print('=== V7.3 CROSS-ASSET REGIME SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    # Viewer JSON: latest 2 years only.
    latest=sub(ts,'2024-08-27','2026-08-27',bid)
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_v7_3_crossasset'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    vixv=[]; ujv=[]; guv=[]
    for i in range(si,ei):
        f=prior_features(vx,uj,gu,bid[i].dt)
        vixv.append(None if f is None else round(f['vix'],4)); ujv.append(None if f is None else round(100*f['usdjpy_ret5'],4)); guv.append(None if f is None else round(100*f['gbpusd_ret5'],4))
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'Previous VIX','series':[{'kind':'line','label':'VIX','values':vixv}]},{'label':'Cross-asset 5d return %','series':[{'kind':'line','label':'USDJPY 5d %','values':ujv},{'kind':'line','label':'GBPUSD 5d %','values':guv}]}]}
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']; f=feats[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7.3 Cross-Asset Regime Guard','note':f"exit={t['exit_reason']}, VIX={f['vix']:.2f}, USDJPY5d={100*f['usdjpy_ret5']:.2f}%, GBPUSD5d={100*f['gbpusd_ret5']:.2f}%"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7.3 Cross-Asset Regime Guard','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_3_CROSSASSET','name':'V7 + Cross-Asset Fundamental/Risk Guard','hypothesis':'Technical recovery longs degrade when broad risk-off is confirmed by actual yen strength; use VIX plus USDJPY, optionally GBPUSD, to distinguish dangerous macro repricing from benign elevated volatility.','entry_logic':['V6/V7 technical entry unchanged','Cross-asset guard '+json.dumps(cfg,ensure_ascii=False),'All external features prior-date only'],'exit_logic':['V7 exit unchanged'],'future_tests':['BoE/BoJ event blackout','UK-JP yield differential','MT5 broker retest']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_3_CrossAsset_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_3_CrossAsset_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

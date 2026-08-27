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
    bars=b.load(path); d={}
    for x in bars: d[x.dt.date()]=x.close
    return sorted(d.items())

def prior_features(vix_rows,uj_rows,gu_rows,dt):
    day=dt.date(); vv=[x for x in vix_rows if x[0]<day]; uj=[x for x in uj_rows if x[0]<day]; gu=[x for x in gu_rows if x[0]<day]
    if not vv or len(uj)<6 or len(gu)<6: return None
    vix=vv[-1][1]; vix5=vv[-6][1] if len(vv)>=6 else vv[0][1]
    ujret=uj[-1][1]/uj[-6][1]-1.0 if uj[-6][1] else 0.0
    guret=gu[-1][1]/gu[-6][1]-1.0 if gu[-6][1] else 0.0
    return {'vix':vix,'vix_chg5':vix-vix5,'usdjpy_ret5':ujret,'gbpusd_ret5':guret}

def allow(f,cfg):
    if f is None: return False
    if cfg['hard_vix'] is not None and f['vix']>cfg['hard_vix']: return False
    mode=cfg['mode']
    if mode=='AND':
        # High global risk only blocks if yen is actually strengthening.
        if f['vix']>cfg['soft_vix'] and f['usdjpy_ret5']<cfg['usdjpy_min']: return False
    elif mode=='TRIPLE':
        # Most selective: high AND rising VIX AND yen strength.
        if f['vix']>cfg['soft_vix'] and f['vix_chg5']>cfg['vix_chg_min'] and f['usdjpy_ret5']<cfg['usdjpy_min']: return False
    elif mode=='OR':
        # More defensive: high VIX plus either rising stress or yen strength.
        if f['vix']>cfg['soft_vix'] and (f['vix_chg5']>cfg['vix_chg_min'] or f['usdjpy_ret5']<cfg['usdjpy_min']): return False
    elif mode=='LEGS':
        # Risk-off confirmation plus an independent GBP weakness / JPY strength check.
        if f['vix']>cfg['soft_vix'] and f['usdjpy_ret5']<cfg['usdjpy_min']: return False
        if f['usdjpy_ret5']<cfg['usdjpy_min'] and f['gbpusd_ret5']<cfg['gbpusd_min']: return False
    return True

def complexity(cfg):
    return 2 + (1 if cfg['hard_vix'] is not None else 0) + (1 if cfg['mode'] in ('TRIPLE','OR') else 0) + (1 if cfg['mode']=='LEGS' else 0)

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P); base=m.simulate_v7(bid,ask,events,a14,m.V7X)
    vx=load_vix('data/VIXCLS.csv'); uj=daily_closes('data/USDJPY_M15_bid.csv'); gu=daily_closes('data/GBPUSD_M15_bid.csv')
    feats={e['entry_i']:prior_features(vx,uj,gu,bid[e['entry_i']].dt) for e in events}

    dev_years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    C=[]
    modes=['AND','TRIPLE','OR','LEGS']
    for mode in modes:
      for soft in [18,20,22,25,27.5]:
       for hard in [None,30,35,40,50]:
        if hard is not None and hard<=soft: continue
        for ujmin in [-0.020,-0.015,-0.010,-0.0075,-0.005,0.0]:
         chgs=[0,2,4,6] if mode in ('TRIPLE','OR') else [None]
         gmins=[-0.020,-0.015,-0.010,-0.005,0.0] if mode=='LEGS' else [None]
         for chg in chgs:
          for gmin in gmins:
           cfg={'mode':mode,'soft_vix':soft,'hard_vix':hard,'usdjpy_min':ujmin,'vix_chg_min':chg,'gbpusd_min':gmin}
           ev=[e for e in events if allow(feats[e['entry_i']],cfg)]
           ts=m.simulate_v7(bid,ask,ev,a14,m.V7X)
           ym=[b.metrics(sub(ts,a,z,bid)) for a,z in dev_years]; dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
           if dm['trades']<43 or min(y['trades'] for y in ym)<3: continue
           if dm['expectancy_r']<0.34 or dm['pf']<1.75: continue
           # Must at least improve known COVID weakness versus V7 baseline -0.183R.
           if ym[0]['expectancy_r']<=-0.18: continue
           exps=[y['expectancy_r'] for y in ym]; mn=min(exps); sd=statistics.pstdev(exps)
           score=(dm['expectancy_r'] + 0.0055*min(dm['trades'],75) + 0.30*ym[0]['expectancy_r'] +
                  0.08*mn - 0.065*sd + 0.02*math.log(max(dm['pf'],1)) - 0.012*dm['max_dd_r'] -
                  0.018*max(0,complexity(cfg)-2))
           C.append((score,cfg,ym,dm,ev,ts))
    C.sort(key=lambda x:x[0],reverse=True)
    if not C: raise RuntimeError('No candidate even after relaxed stability screen')

    # Chosen only from development. Holdouts below are reported after fixing it.
    chosen=next((x for x in C[:120] if complexity(x[1])<=4 and x[3]['trades']>=45),C[0])
    score,cfg,ym,dm,ev,ts=chosen
    periods={'external_fresh_2018_19':('2018-08-27','2019-08-27'),'external_seen_2019_20':('2019-08-27','2020-08-27'),'covid_known_2020_21':('2020-08-27','2021-08-27'),'development_2020_25':('2020-08-27','2025-08-27'),'recent_holdout_2025_26':('2025-08-27','2026-08-27'),'latest_2y':('2024-08-27','2026-08-27'),'full_2018_26':('2018-08-27','2026-08-27')}
    bm={k:fm(sub(base,a,z,bid)) for k,(a,z) in periods.items()}; gm={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}

    # Acceptance is deliberately evaluated after selection.
    fresh=b.metrics(sub(ts,'2018-08-27','2019-08-27',bid)); recent=b.metrics(sub(ts,'2025-08-27','2026-08-27',bid)); latest=b.metrics(sub(ts,'2024-08-27','2026-08-27',bid))
    accepted=(fresh['expectancy_r']>=0 and recent['expectancy_r']>=0.20 and latest['expectancy_r']>=0.40 and latest['pf']>=2.0)

    top=[]
    for x in C[:30]:
        top.append({'score':round(x[0],4),'cfg':x[1],'complexity':complexity(x[1]),'dev':b.fmt(x[3]),'years':[b.fmt(y) for y in x[2]],'fresh_2018_19':fm(sub(x[5],'2018-08-27','2019-08-27',bid)),'seen_2019_20':fm(sub(x[5],'2019-08-27','2020-08-27',bid)),'recent_2025_26':fm(sub(x[5],'2025-08-27','2026-08-27',bid)),'latest_2y':fm(sub(x[5],'2024-08-27','2026-08-27',bid))})

    summary={'data_source':'Dukascopy GBPJPY BID+ASK plus USDJPY/GBPUSD BID, M15-derived H1/daily; FRED VIXCLS daily','timing':'All VIX/USDJPY/GBPUSD regime inputs use only dates strictly before the GBPJPY H1 entry date.','research_policy':'2020-21 known weakness is development. Candidate selection never uses 2025-26 or fresh 2018-19.','selected_v7_3_guard':cfg,'selected_score':round(score,4),'accepted_as_upgrade':accepted,'acceptance_rule':'fresh 2018-19 expectancy>=0; recent 2025-26 expectancy>=0.20; latest2y expectancy>=0.40 and PF>=2.0','guard_logic':{'AND':'high VIX AND yen strength','TRIPLE':'high+rising VIX AND yen strength','OR':'high VIX AND (rising VIX OR yen strength)','LEGS':'AND plus independent GBP weakness + yen strength block','hard_vix':'panic ceiling regardless of FX legs'},'v7_baseline':bm,'v7_3_candidate':gm,'development_years':[b.fmt(y) for y in ym],'top_candidates':top,'interpretation':'This layer tries to distinguish elevated-but-benign volatility from true GBPJPY-hostile risk-off by requiring external confirmation from yen strength and, in one family, sterling weakness. It is a regime proxy, not proof of a news cause.','decision':'ACCEPT V7.3' if accepted else 'REJECT V7.3; keep V7/V7.2 and do not promote this filter','next_research':['If rejected, next fundamental test should use timestamp-safe BoE/BoJ decision/event calendars or UK-Japan yield differential rather than adding more chart indicators.']}
    print('=== V7.3 ADAPTIVE MACRO GUARD ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    latest_trades=sub(ts,'2024-08-27','2026-08-27',bid); si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_v7_3_adaptive'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    vixv=[]; ujv=[]; guv=[]
    for i in range(si,ei):
        f=prior_features(vx,uj,gu,bid[i].dt); vixv.append(None if f is None else round(f['vix'],4)); ujv.append(None if f is None else round(100*f['usdjpy_ret5'],4)); guv.append(None if f is None else round(100*f['gbpusd_ret5'],4))
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'Previous VIX','series':[{'kind':'line','label':'VIX','values':vixv}]},{'label':'Prior 5d FX return %','series':[{'kind':'line','label':'USDJPY 5d %','values':ujv},{'kind':'line','label':'GBPUSD 5d %','values':guv}]}]}
    vt=[]
    for no,t in enumerate(latest_trades,1):
        e=t['event']; f=feats[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7.3 Adaptive Macro Guard','note':f"exit={t['exit_reason']}, VIX={f['vix']:.2f}, USDJPY5d={100*f['usdjpy_ret5']:.2f}%, GBPUSD5d={100*f['gbpusd_ret5']:.2f}%"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7.3 Adaptive Macro Guard','status':'検証済み' if accepted else '候補・不採用'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_3_ADAPTIVE','name':'V7 + Adaptive Macro Guard','hypothesis':'Risk-off should suppress GBPJPY long only when broad stress is confirmed by actual yen strength rather than VIX level alone.','entry_logic':['V7 technical entry unchanged','Adaptive macro guard '+json.dumps(cfg,ensure_ascii=False),'All external data prior-date only'],'exit_logic':['V7 exit unchanged'],'future_tests':['BoE/BoJ event blackout','UK-JP yield differential']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_3_AdaptiveMacro_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_3_AdaptiveMacro_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
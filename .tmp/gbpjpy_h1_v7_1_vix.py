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
            if not ds or not vs or vs in ('.','NA',''):
                continue
            try: rows.append((datetime.fromisoformat(ds).date(),float(vs)))
            except: pass
    rows.sort()
    return rows

def prev_vix(rows, dt):
    d=dt.date(); val=None
    for rd,v in rows:
        if rd>=d: break
        val=v
    return val

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P)
    base=m.simulate_v7(bid,ask,events,a14,m.V7X)
    vixrows=load_vix('data/VIXCLS.csv')
    event_vix={e['entry_i']:prev_vix(vixrows,bid[e['entry_i']].dt) for e in events}

    dev_years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    candidates=[]
    for vmax in [18,20,22,25,27.5,30,35,40,50,80]:
        ev=[e for e in events if event_vix[e['entry_i']] is not None and event_vix[e['entry_i']]<=vmax]
        ts=m.simulate_v7(bid,ask,ev,a14,m.V7X)
        ym=[b.metrics(sub(ts,a,z,bid)) for a,z in dev_years]
        dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
        covid=ym[0]
        if dm['trades']<35 or min(x['trades'] for x in ym)<3: continue
        mn=min(x['expectancy_r'] for x in ym); sd=statistics.pstdev([x['expectancy_r'] for x in ym])
        score=dm['expectancy_r']+0.006*min(dm['trades'],75)+0.35*covid['expectancy_r']+0.12*mn-0.08*sd+0.025*math.log(max(dm['pf'],1))-0.015*dm['max_dd_r']
        candidates.append((score,vmax,ym,dm,ev,ts))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if not candidates: raise RuntimeError('No VIX candidates')
    # Prefer a threshold plateau with COVID nonnegative if available, while retaining >=40 dev trades.
    good=[x for x in candidates if x[2][0]['expectancy_r']>=0 and x[3]['trades']>=40]
    chosen=good[0] if good else candidates[0]
    score,vmax,ym,dm,ev,ts=chosen

    periods={'external_new_2019_20':('2019-08-27','2020-08-27'),'covid_known_2020_21':('2020-08-27','2021-08-27'),'old_external_2021_22':('2021-08-27','2022-08-27'),'development_2020_25':('2020-08-27','2025-08-27'),'recent_2025_26':('2025-08-27','2026-08-27'),'latest_2y':('2024-08-27','2026-08-27'),'full_2019_26':('2019-08-27','2026-08-27')}
    base_m={k:fm(sub(base,a,z,bid)) for k,(a,z) in periods.items()}
    guard_m={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}

    threshold_table=[]
    for _,thr,yms,dmm,ee,tt in sorted(candidates,key=lambda x:x[1]):
        threshold_table.append({'vix_max':thr,'covid_2020_21':b.fmt(yms[0]),'development_2020_25':b.fmt(dmm),'external_new_2019_20':fm(sub(tt,'2019-08-27','2020-08-27',bid)),'recent_2025_26':fm(sub(tt,'2025-08-27','2026-08-27',bid)),'latest_2y':fm(sub(tt,'2024-08-27','2026-08-27',bid))})

    summary={'data_source':'Dukascopy JForex BID+ASK M15 aggregated H1 + FRED VIXCLS daily','vix_timing':'For each H1 entry, use the most recent VIX close from a strictly earlier calendar date; same-day VIX close is never used, avoiding lookahead.','research_policy':'V7 weakness in 2020-21 is known, so 2020-21 is included in VIX threshold development. 2019-08-27～2020-08-26 is new external validation and includes Mar-Aug 2020 COVID shock months.','v6_entry_params':m.V6P,'v7_exit':m.V7X,'selected_vix_max':vmax,'rule':'Only allow GBPJPY long entries when previous available daily VIX close <= selected threshold.','rationale':'VIX is an options-implied measure of near-term equity volatility/risk sentiment. Yen commonly appreciates in risk-off episodes, so high VIX can conflict with GBPJPY long mean-recovery setups.','v7_baseline':base_m,'v7_1_vix_guard':guard_m,'development_years':[b.fmt(x) for x in ym],'threshold_table':threshold_table,'top_candidates':[{'score':round(x[0],4),'vix_max':x[1],'years':[b.fmt(y) for y in x[2]],'dev':b.fmt(x[3])} for x in candidates],'live_fundamental_layer':['VIX guard is cross-asset risk proxy, not a substitute for economic calendar.','Add hard blackout around BoE/BoJ decisions and high-impact UK/JP releases after historical calendar validation.','Emergency central-bank/geopolitical shock => HOLD until risk regime normalizes.']}
    print('=== V7.1 VIX SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    latest=sub(ts,'2024-08-27','2026-08-27',bid)
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_flush_recovery_v7_1_vix_guard'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    vix_series=[]
    for i in range(si,ei): vix_series.append(prev_vix(vixrows,bid[i].dt))
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'VIX previous daily close','levels':[vmax],'series':[{'kind':'line','label':'VIX','values':[None if x is None else round(x,4) for x in vix_series]}]}]}
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']; vv=event_vix[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7.1 VIX Guard','note':f"exit={t['exit_reason']}, prevVIX={vv:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7.1 VIX Risk Guard','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_1_VIX','name':'V7 + VIX Risk-Off Guard','hypothesis':'Disable GBPJPY long technical setup when global risk aversion is elevated.','entry_logic':['V6 entry rules unchanged',f'Previous available daily VIX close <= {vmax}','Same-day VIX close is not used'],'exit_logic':['V7 exit unchanged: SL=Flush-0.10ATR','TP=2.50R','16h+ stagnant range exit','max 30h'],'future_tests':['BoE/BoJ + UK/JP high-impact economic calendar blackout','MT5 broker swap and tick volume','future walk-forward']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_1_VIXGuard_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_1_VIXGuard_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

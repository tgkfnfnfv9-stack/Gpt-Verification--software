import importlib.util, json, math, statistics
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('m','/tmp/gbpjpy_h1_v8_macro.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b=m.b
OUT=Path('results'); OUT.mkdir(exist_ok=True)

def fm(ts): return b.fmt(b.metrics(ts))
def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); e200=b.ema(c,200); a14=b.atr(bid,14); a50=b.atr(bid,50); a240=b.atr(bid,240); rv=b.rvol_series(bid,20)
    base_events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P)
    feats={e['entry_i']:m.macro_features(bid,a14,a240,e200,e) for e in base_events}
    base_ts=m.simulate_v7(bid,ask,base_events,a14,m.V7X)

    dev_years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    candidates=[]
    for vmax in [1.00,1.10,1.20,1.30,1.45,1.60,1.80,2.20]:
      for rmin in [-5.0,-3.0,-2.0,-1.5,-1.0,-0.5]:
        for smin in [-1.0,-0.50,-0.25,-0.10,0.0]:
            cfg={'macro_vol_max':vmax,'ret24_min':rmin,'ema200_slope_min':smin}
            ev=[e for e in base_events if m.gate_event(e,feats[e['entry_i']],cfg)]
            ts=m.simulate_v7(bid,ask,ev,a14,m.V7X)
            ym=[b.metrics(sub(ts,a,z,bid)) for a,z in dev_years]
            dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
            covid=ym[0]
            if dm['trades']<38 or min(x['trades'] for x in ym)<4: continue
            mn=min(x['expectancy_r'] for x in ym); sd=statistics.pstdev([x['expectancy_r'] for x in ym])
            # Main aim: improve known COVID-era failure without destroying normal-regime edge.
            score=(dm['expectancy_r']+0.008*min(dm['trades'],75)+0.28*covid['expectancy_r']+
                   0.12*mn-0.08*sd+0.025*math.log(max(dm['pf'],1))-0.015*dm['max_dd_r'])
            candidates.append((score,cfg,ym,dm,ev,ts))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if not candidates: raise RuntimeError('No macro candidates at all')

    positive_covid=[x for x in candidates if x[2][0]['expectancy_r']>=0 and x[3]['expectancy_r']>=0.30]
    pool=positive_covid if positive_covid else candidates
    # Prefer a plateau candidate with at least 45 trades in the five-year development block.
    chosen=next((x for x in pool[:80] if x[3]['trades']>=45),pool[0])
    score,cfg,ym,dm,ev,ts=chosen

    periods={
      'external_new_2019_20':('2019-08-27','2020-08-27'),
      'covid_known_2020_21':('2020-08-27','2021-08-27'),
      'old_external_2021_22':('2021-08-27','2022-08-27'),
      'development_2020_25':('2020-08-27','2025-08-27'),
      'recent_2025_26':('2025-08-27','2026-08-27'),
      'latest_2y':('2024-08-27','2026-08-27'),
      'full_2019_26':('2019-08-27','2026-08-27')}
    v8m={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}
    v7m={k:fm(sub(base_ts,a,z,bid)) for k,(a,z) in periods.items()}

    # Nearby threshold robustness.
    robust=[]
    for field,vals in [
      ('macro_vol_max',[max(0.9,cfg['macro_vol_max']-0.1),cfg['macro_vol_max'],cfg['macro_vol_max']+0.1]),
      ('ret24_min',[cfg['ret24_min']-0.5,cfg['ret24_min'],cfg['ret24_min']+0.5]),
      ('ema200_slope_min',[cfg['ema200_slope_min']-0.1,cfg['ema200_slope_min'],cfg['ema200_slope_min']+0.1])]:
        for val in sorted(set(vals)):
            cc=dict(cfg); cc[field]=val
            ee=[e for e in base_events if m.gate_event(e,feats[e['entry_i']],cc)]
            tt=m.simulate_v7(bid,ask,ee,a14,m.V7X)
            robust.append({'parameter':field,'value':val,'covid_2020_21':fm(sub(tt,'2020-08-27','2021-08-27',bid)),'development_2020_25':fm(sub(tt,'2020-08-27','2025-08-27',bid)),'external_new_2019_20':fm(sub(tt,'2019-08-27','2020-08-27',bid)),'recent_2025_26':fm(sub(tt,'2025-08-27','2026-08-27',bid))})

    summary={
      'data_source':'Dukascopy JForex BID+ASK M15 aggregated H1, 2019-08-27～2026-08-26',
      'research_policy':'2020-21 is no longer holdout because V7 weakness there is known. V8 macro gate is selected using 2020-08-27～2025-08-26. 2019-08-27～2020-08-26 is newly downloaded external validation and includes Mar-Aug 2020 COVID shock months. 2025-08-27～2026-08-26 remains recent revalidation, not untouched.',
      'v6_entry_params':m.V6P,'v7_exit':m.V7X,
      'selected_macro_gate':cfg,
      'gate_meaning':{'macro_vol_max':'ATR14/ATR240 maximum','ret24_min':'minimum 24h return normalized by ATR240','ema200_slope_min':'minimum 24h EMA200 slope normalized by ATR240'},
      'v7_baseline':v7m,'v8_macro_guard':v8m,
      'v8_development_years':[b.fmt(x) for x in ym],
      'nearby_robustness':robust,
      'top_candidates':[{'score':round(x[0],4),'cfg':x[1],'years':[b.fmt(y) for y in x[2]],'dev':b.fmt(x[3])} for x in candidates[:15]],
      'fundamental_interpretation':'The gate is a market-internal proxy, not direct fundamental data. It attempts to detect periods when macro repricing overwhelms local technical structure: abnormal medium-term volatility, strong bearish 24h repricing, or a falling slow trend.',
      'live_layer':['Hard blackout around scheduled BoE/BoJ decisions and top-tier UK/JP releases should be tested separately with historical economic-calendar data.','Emergency central-bank/geopolitical shock should force HOLD until volatility normalizes.','MT5 broker swap/rollover must be added in final broker-specific test.']}
    print('=== V8 MACRO2 SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    latest=sub(ts,'2024-08-27','2026-08-27',bid)
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_flush_recovery_v8_macro_guard'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    gatevals=[]
    for i in range(si,ei):
        if i<240: gatevals.append(None); continue
        f={'macro_vol_ratio':a14[i]/max(a240[i],1e-12),'ret24_atr240':(bid[i].close-bid[i-24].close)/max(a240[i],1e-12),'ema200_slope24_atr240':(e200[i]-e200[i-24])/max(a240[i],1e-12)}
        gatevals.append(1 if (f['macro_vol_ratio']<=cfg['macro_vol_max'] and f['ret24_atr240']>=cfg['ret24_min'] and f['ema200_slope24_atr240']>=cfg['ema200_slope_min']) else 0)
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]},{'kind':'line','label':'EMA200','values':[round(x,6) for x in e200[si:ei]]}],'panes':[{'label':'ATR14/ATR240','levels':[cfg['macro_vol_max']],'series':[{'kind':'line','label':'Macro Vol Ratio','values':[round(a14[i]/a240[i],6) if a240[i]>0 else None for i in range(si,ei)]}]},{'label':'Macro Gate','levels':[0.5],'series':[{'kind':'line','label':'Gate 1=ON','values':gatevals}]}]}
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']; f=feats[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V8 Macro Guard','note':f"exit={t['exit_reason']}, MacroVol={f['macro_vol_ratio']:.2f}, Ret24={f['ret24_atr240']:.2f}, EMA200Slope={f['ema200_slope24_atr240']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V8 Macro Guard','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V8_MACRO_GUARD','name':'V7 + Macro/Fundamental Shock Proxy Guard','hypothesis':'Disable the technical setup when market-internal evidence suggests macro repricing is dominating.','entry_logic':['V6 entry rules unchanged','Macro gate '+json.dumps(cfg,ensure_ascii=False),'All gate data is known before entry'],'exit_logic':['V7 exit unchanged: SL=Flush-0.10ATR','TP=2.50R','16h+ stagnant range exit','max 30h'],'future_tests':['Historical economic calendar blackout','BoE/BoJ/CPI/employment surprise layer','MT5 broker swap and tick volume']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V8_MacroGuard_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V8_MacroGuard_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

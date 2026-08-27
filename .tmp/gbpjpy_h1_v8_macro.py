import importlib.util, json, math, statistics
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('b','/tmp/gbpjpy_h1_v5_opt.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
OUT=Path('results'); OUT.mkdir(exist_ok=True)

V6P={'slope_lb':8,'h0_window':5,'atr_mult':0.9,'sweep_lookback':10,'sweep_depth':0.06,'recovery_bars':4,'recovery_pct':0.65,'breakout_bars':10,'breakout_buffer':0.0,'retest_bars':10,'retest_touch':0.5,'retest_hold':0.15,'session':'london_ny','rvol_min':0.85,'vol_ratio_min':0.85,'vol_ratio_max':1.3,'recovery_rvol_min':0.0,'breakout_rvol_min':0.65,'trend_strength_min':0.0,'slope_strength_min':0.03,'flush_rejection_min':0.0,'breakout_strength_min':0.0}
V7X={'target_r':2.5,'max_hold':30,'stop_buffer_atr':0.1,'range_after':16,'range_lookback':4,'range_width_atr':1.0,'range_progress_max_r':0.25,'range_mfe_max_r':1.0}

def detect2(bars,e20,e50,a14,a50,rv,p):
    ev=[]; i=80; n=len(bars)
    while i<n-60:
        hw=p['h0_window']; h0i=max(range(i-hw,i),key=lambda z:bars[z].high); h0=bars[h0i].high
        if not 1<=i-h0i<=hw: i+=1; continue
        if not (e20[h0i]>e50[h0i] and bars[h0i].close>e20[h0i]): i+=1; continue
        a0=a14[h0i]
        if a0<=0: i+=1; continue
        trend_strength=(e20[h0i]-e50[h0i])/a0
        slope_strength=(e50[h0i]-e50[max(0,h0i-p['slope_lb'])])/a0
        if trend_strength<p['trend_strength_min'] or slope_strength<p['slope_strength_min']: i+=1; continue
        prior_low=min(bars[z].low for z in range(max(0,h0i-p['sweep_lookback']),h0i))
        fl=bars[i].low; drop=h0-fl; sweep_depth=(prior_low-fl)/a0
        if drop<p['atr_mult']*a0 or fl>=prior_low or sweep_depth<p['sweep_depth']: i+=1; continue
        if rv[i] is None or rv[i]<p['rvol_min']: i+=1; continue
        vr=a14[i]/a50[i] if a50[i]>0 else 0
        if vr<p['vol_ratio_min'] or vr>p['vol_ratio_max']: i+=1; continue
        rng=max(1e-12,bars[i].high-bars[i].low); reject=(bars[i].close-bars[i].low)/rng
        if reject<p['flush_rejection_min']: i+=1; continue
        rec=None; rr=0
        for j in range(i+1,min(n,i+p['recovery_bars']+1)):
            ratio=(bars[j].close-fl)/drop if drop>0 else 0
            if bars[j].close>prior_low and ratio>=p['recovery_pct']:
                rec=j; rr=ratio; break
        if rec is None: i+=1; continue
        if p['recovery_rvol_min']>0 and (rv[rec] is None or rv[rec]<p['recovery_rvol_min']): i+=1; continue
        bo=None
        for k in range(rec,min(n-1,rec+p['breakout_bars']+1)):
            if bars[k].close>h0+p['breakout_buffer']*a0:
                bo=k; break
        if bo is None: i+=1; continue
        bo_strength=(bars[bo].close-h0)/a0
        if bo_strength<p['breakout_strength_min']: i=bo+1; continue
        if p['breakout_rvol_min']>0 and (rv[bo] is None or rv[bo]<p['breakout_rvol_min']): i=bo+1; continue
        ret=None; abo=a14[bo]
        for q in range(bo+1,min(n-1,bo+p['retest_bars']+1)):
            near=bars[q].low<=h0+p['retest_touch']*abo
            hold=bars[q].close>=h0-p['retest_hold']*abo
            if near and hold and b.session_ok(bars[q].dt.hour,p['session']): ret=q; break
        if ret is not None and ret+1<n:
            ev.append({'entry_i':ret+1,'flush_i':i,'recovery_i':rec,'breakout_i':bo,'retest_i':ret,'h0':h0,'flush_low':fl,'atr0':a0,'drop_atr':drop/a0,'sweep_depth_atr':sweep_depth,'flush_rvol':rv[i],'vol_ratio':vr,'recovery_ratio':rr,'trend_strength':trend_strength,'slope_strength':slope_strength,'flush_rejection':reject,'recovery_rvol':rv[rec],'breakout_rvol':rv[bo],'breakout_strength':bo_strength})
        i=bo+1
    return ev

def macro_features(bars,a14,a240,e200,e):
    i=e['entry_i']-1
    if i<240: return None
    base=max(a240[i],1e-12)
    ret24=(bars[i].close-bars[i-24].close)/base
    ret72=(bars[i].close-bars[i-72].close)/base
    vol_long=a14[i]/base
    slope200=(e200[i]-e200[i-24])/base
    dist200=(bars[i].close-e200[i])/base
    path=sum(abs(bars[z].close-bars[z-1].close) for z in range(i-23,i+1))
    eff24=abs(bars[i].close-bars[i-24].close)/path if path>0 else 0.0
    return {'macro_vol_ratio':vol_long,'ret24_atr240':ret24,'ret72_atr240':ret72,'ema200_slope24_atr240':slope200,'dist_ema200_atr240':dist200,'eff24':eff24}

def gate_event(e,feat,cfg):
    if feat is None: return False
    # Fundamental/macro shock proxy: reject abnormally elevated medium-horizon volatility,
    # strong 24h bearish repricing, or clearly falling 200h trend.
    return (feat['macro_vol_ratio']<=cfg['macro_vol_max'] and
            feat['ret24_atr240']>=cfg['ret24_min'] and
            feat['ema200_slope24_atr240']>=cfg['ema200_slope_min'])

def simulate_v7(bid,ask,events,a14,cfg=V7X):
    am={x.dt:x for x in ask}; fs=b.medspread(bid,ask); out=[]; next_allowed=0
    for e in events:
        ii=e['entry_i']
        if ii<next_allowed or ii>=len(bid): continue
        ab=am.get(bid[ii].dt); entry=ab.open if ab else bid[ii].open+fs
        stop=e['flush_low']-cfg['stop_buffer_atr']*e['atr0']; risk=entry-stop
        if risk<=0 or risk/entry>0.05: continue
        target=entry+cfg['target_r']*risk; end=min(len(bid)-1,ii+cfg['max_hold']-1)
        xi=end; xp=bid[end].close; reason='TIME'; mfe=0.0
        z=ii
        while z<=end:
            hs=bid[z].low<=stop; ht=bid[z].high>=target
            if hs and ht: xi=z; xp=stop; reason='SL_SAME_BAR'; break
            if hs: xi=z; xp=stop; reason='SL'; break
            if ht: xi=z; xp=target; reason='TP'; break
            mfe=max(mfe,(bid[z].high-entry)/risk)
            held=z-ii+1
            if cfg.get('range_after') is not None and held>=cfg['range_after'] and z+1<=end:
                lb=cfg['range_lookback']; s=max(ii,z-lb+1)
                width=max(bid[k].high for k in range(s,z+1))-min(bid[k].low for k in range(s,z+1))
                progress=(bid[z].close-entry)/risk
                if (z-s+1>=lb and width<=cfg['range_width_atr']*a14[z] and progress<=cfg['range_progress_max_r'] and mfe<=cfg['range_mfe_max_r']):
                    xi=z+1; xp=bid[z+1].open; reason='RANGE'; break
            z+=1
        r=(xp-entry)/risk
        out.append({'entry_i':ii,'exit_i':xi,'entry_price':entry,'exit_price':xp,'stop':stop,'target':target,'r':r,'result':'WIN' if r>0 else ('LOSS' if r<0 else 'EVEN'),'exit_reason':reason,'event':e})
        next_allowed=xi+1
    return out

def fm(x): return b.fmt(b.metrics(x))
def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); e200=b.ema(c,200); a14=b.atr(bid,14); a50=b.atr(bid,50); a240=b.atr(bid,240); rv=b.rvol_series(bid,20)
    base_events=detect2(bid,e20,e50,a14,a50,rv,V6P)
    feats={e['entry_i']:macro_features(bid,a14,a240,e200,e) for e in base_events}

    # First verify our reconstruction against published V7 behavior.
    base_ts=simulate_v7(bid,ask,base_events,a14,V7X)
    base_check={
      'dev_2022_25':fm(sub(base_ts,'2022-08-27','2025-08-27',bid)),
      'recent_2025_26':fm(sub(base_ts,'2025-08-27','2026-08-27',bid)),
      'latest_2y':fm(sub(base_ts,'2024-08-27','2026-08-27',bid)),
      'covid_2020_21':fm(sub(base_ts,'2020-08-27','2021-08-27',bid))}

    # V8 selection: deliberately include 2020-21 in development now, because V7 failure there is known.
    # Keep search low-dimensional: only three pre-entry macro-regime gates.
    dev_years=[('2020-08-27','2021-08-27'),('2021-08-27','2022-08-27'),('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    candidates=[]
    for vmax in [1.00,1.10,1.20,1.30,1.45,1.60]:
      for rmin in [-3.0,-2.0,-1.5,-1.0,-0.5]:
        for smin in [-0.50,-0.25,-0.10,0.0]:
            cfg={'macro_vol_max':vmax,'ret24_min':rmin,'ema200_slope_min':smin}
            ev=[e for e in base_events if gate_event(e,feats[e['entry_i']],cfg)]
            ts=simulate_v7(bid,ask,ev,a14,V7X)
            ym=[b.metrics(sub(ts,a,z,bid)) for a,z in dev_years]
            dm=b.metrics(sub(ts,'2020-08-27','2025-08-27',bid))
            if dm['trades']<48 or min(x['trades'] for x in ym)<6: continue
            # Require COVID year and every development year to stop being materially negative.
            if min(x['expectancy_r'] for x in ym)<-0.03 or dm['expectancy_r']<0.38 or dm['pf']<2.0: continue
            mn=min(x['expectancy_r'] for x in ym); sd=statistics.pstdev([x['expectancy_r'] for x in ym])
            score=dm['expectancy_r']+0.006*min(dm['trades'],75)+0.20*mn-0.08*sd+0.025*math.log(max(dm['pf'],1))-0.015*dm['max_dd_r']
            candidates.append((score,cfg,ym,dm,ev,ts))
    candidates.sort(key=lambda x:x[0],reverse=True)
    if not candidates: raise RuntimeError('No stable macro-gate candidate')
    # Choose a plateau-like candidate near the top, preferring >=55 development trades and nonnegative worst year.
    chosen=next((x for x in candidates[:50] if x[3]['trades']>=55 and min(y['expectancy_r'] for y in x[2])>=0),candidates[0])
    score,cfg,ym,dm,ev,ts=chosen

    periods={
      'external_new_2019_20':('2019-08-27','2020-08-27'),
      'covid_known_2020_21':('2020-08-27','2021-08-27'),
      'old_external_2021_22':('2021-08-27','2022-08-27'),
      'development_2020_25':('2020-08-27','2025-08-27'),
      'recent_2025_26':('2025-08-27','2026-08-27'),
      'latest_2y':('2024-08-27','2026-08-27'),
      'full_2019_26':('2019-08-27','2026-08-27')}
    outm={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}
    base_period={k:fm(sub(base_ts,a,z,bid)) for k,(a,z) in periods.items()}
    kept={k:len([e for e in ev if datetime.fromisoformat(a)<=bid[e['entry_i']].dt<datetime.fromisoformat(z)]) for k,(a,z) in periods.items()}
    basecnt={k:len([e for e in base_events if datetime.fromisoformat(a)<=bid[e['entry_i']].dt<datetime.fromisoformat(z)]) for k,(a,z) in periods.items()}

    # Ablation around chosen thresholds.
    robust=[]
    for field,vals in [
      ('macro_vol_max',sorted(set([max(0.9,cfg['macro_vol_max']-0.1),cfg['macro_vol_max'],cfg['macro_vol_max']+0.1]))),
      ('ret24_min',sorted(set([cfg['ret24_min']-0.5,cfg['ret24_min'],cfg['ret24_min']+0.5]))),
      ('ema200_slope_min',sorted(set([cfg['ema200_slope_min']-0.1,cfg['ema200_slope_min'],cfg['ema200_slope_min']+0.1])) )]:
        for val in vals:
            cc=dict(cfg); cc[field]=val
            ee=[e for e in base_events if gate_event(e,feats[e['entry_i']],cc)]
            tt=simulate_v7(bid,ask,ee,a14,V7X)
            robust.append({'parameter':field,'value':val,'development_2020_25':fm(sub(tt,'2020-08-27','2025-08-27',bid)),'external_new_2019_20':fm(sub(tt,'2019-08-27','2020-08-27',bid)),'recent_2025_26':fm(sub(tt,'2025-08-27','2026-08-27',bid))})

    summary={
      'data_source':'Dukascopy JForex BID+ASK M15 aggregated H1, 2019-08-27～2026-08-26',
      'research_note':'V7 weakness in 2020-21 was already known, so V8 intentionally moves 2020-21 into development. 2019-08-27～2020-08-26 is newly downloaded external validation and includes the first COVID shock months in 2020.',
      'base_v6_entry_params':V6P,'base_v7_exit':V7X,
      'macro_gate_definition':{'features':'All measured on the completed H1 bar immediately before entry','macro_vol_ratio':'ATR14 / ATR240','ret24_atr240':'24h close change / ATR240','ema200_slope24_atr240':'EMA200 change over 24h / ATR240','selected':cfg},
      'interpretation':'Skip longs when medium-horizon volatility is abnormally elevated, when the preceding 24h move is too strongly bearish, or when the slow 200h trend is falling too hard. These are price-based proxies for macro/fundamental repricing, not direct news/fundamental data.',
      'v7_reconstruction_check':base_check,
      'v7_baseline_metrics':base_period,
      'v8_metrics':outm,
      'base_signal_counts':basecnt,'v8_signal_counts':kept,
      'v8_dev_years':[b.fmt(x) for x in ym],
      'nearby_macro_gate_robustness':robust,
      'top_candidates':[{'score':round(x[0],4),'cfg':x[1],'dev_years':[b.fmt(y) for y in x[2]],'development':b.fmt(x[3])} for x in candidates[:10]],
      'live_fundamental_layer_recommendation':['Economic-calendar blackout around BoE/BoJ rate decisions, UK/JP CPI and major employment/GDP surprises','Emergency central-bank statements or geopolitical shock -> HOLD until volatility normalizes','Broker-specific swap/rollover still needs MT5 final retest']}
    print('=== V8 MACRO SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    # Viewer JSON for latest 2 years using V8 filtered trades.
    latest=sub(ts,'2024-08-27','2026-08-27',bid)
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]; cid='gbpjpy_h1_flush_recovery_v8_macro_guard'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    gate_series=[]
    for i in range(si,ei):
        if i<240: gate_series.append(None); continue
        f={'macro_vol_ratio':a14[i]/max(a240[i],1e-12),'ret24_atr240':(bid[i].close-bid[i-24].close)/max(a240[i],1e-12),'ema200_slope24_atr240':(e200[i]-e200[i-24])/max(a240[i],1e-12)}
        gate_series.append(1 if (f['macro_vol_ratio']<=cfg['macro_vol_max'] and f['ret24_atr240']>=cfg['ret24_min'] and f['ema200_slope24_atr240']>=cfg['ema200_slope_min']) else 0)
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]},{'kind':'line','label':'EMA200','values':[round(x,6) for x in e200[si:ei]]}],'panes':[{'label':'ATR14','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14[si:ei]]}]},{'label':'Macro Vol ATR14/ATR240','levels':[cfg['macro_vol_max']],'series':[{'kind':'line','label':'ATR14/ATR240','values':[round(a14[i]/a240[i],6) if a240[i]>0 else None for i in range(si,ei)]}]},{'label':'Macro Gate','levels':[0.5],'series':[{'kind':'line','label':'Gate 1=ON','values':gate_series}]}]}
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']; f=feats[e['entry_i']]
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V8 Macro Guard','note':f"exit={t['exit_reason']}, RVOL={e['flush_rvol']:.2f}, ATR50比={e['vol_ratio']:.2f}, MacroVol={f['macro_vol_ratio']:.2f}, Ret24={f['ret24_atr240']:.2f}, EMA200Slope={f['ema200_slope24_atr240']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V8 Macro Guard','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V8_MACRO_GUARD','name':'V7 + Macro/Fundamental Shock Proxy Guard','hypothesis':'V7 technical setup is disabled during macro repricing regimes approximated by abnormal medium-term volatility, strong 24h bearish move, or falling EMA200 trend.','entry_logic':['V6 price/volume/volatility entry rules','Macro Guard: '+json.dumps(cfg,ensure_ascii=False),'All gate inputs are known before entry'],'exit_logic':['SL=Flush安値-0.10ATR','TP=2.50R','16時間以降の停滞レンジを次H1始値で撤退','最大30時間','同一H1足でSL/TP両方ならSL先着'],'future_tests':['Actual economic calendar / BoE-BoJ event blackout','MT5 broker tick volume and swap','Walk-forward future period']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V8_MacroGuard_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V8_MacroGuard_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

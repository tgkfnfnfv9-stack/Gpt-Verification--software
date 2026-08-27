import importlib.util, json, math, random, statistics
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('b','/tmp/gbpjpy_h1_v5_opt.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
spec2=importlib.util.spec_from_file_location('v6','/tmp/gbpjpy_h1_v6_regime.py')
v6=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(v6)
OUT=Path('results'); OUT.mkdir(exist_ok=True)

V6P={
 'slope_lb':8,'h0_window':5,'atr_mult':0.9,'sweep_lookback':10,'sweep_depth':0.06,
 'recovery_bars':4,'recovery_pct':0.65,'breakout_bars':10,'breakout_buffer':0.0,
 'retest_bars':10,'retest_touch':0.5,'retest_hold':0.15,'session':'london_ny',
 'rvol_min':0.85,'vol_ratio_min':0.85,'vol_ratio_max':1.30,'recovery_rvol_min':0.0,
 'breakout_rvol_min':0.65,'trend_strength_min':0.0,'slope_strength_min':0.03,
 'flush_rejection_min':0.0,'breakout_strength_min':0.0
}

def exit_sim(bid,ask,events,a14,cfg):
    am={x.dt:x for x in ask}; fs=b.medspread(bid,ask); out=[]; next_allowed=0
    for e in events:
        ii=e['entry_i']
        if ii<next_allowed or ii>=len(bid): continue
        ab=am.get(bid[ii].dt); entry=ab.open if ab else bid[ii].open+fs
        stop0=e['flush_low']-cfg['stop_buffer_atr']*e['atr0']; risk=entry-stop0
        if risk<=0 or risk/entry>0.05: continue
        target=entry+cfg['target_r']*risk
        stop=stop0; be_armed=False; end=min(len(bid)-1,ii+cfg['max_hold']-1)
        xi=end; xp=bid[end].close; reason='TIME'; range_signal_i=None
        peak_high=bid[ii].high
        for z in range(ii,end+1):
            # Existing protective orders are evaluated intrabar. Conservative tie-break: stop first.
            hs=bid[z].low<=stop; ht=bid[z].high>=target
            if hs and ht: xi=z; xp=stop; reason='SL_SAME_BAR' if not be_armed else 'BE_SAME_BAR'; break
            if hs: xi=z; xp=stop; reason='SL' if not be_armed else 'BE'; break
            if ht: xi=z; xp=target; reason='TP'; break
            peak_high=max(peak_high,bid[z].high)

            # Arm break-even only after the bar is complete; it becomes active from the next H1 bar.
            if cfg['be_trigger_r'] is not None and not be_armed:
                mfe=(peak_high-entry)/risk
                if mfe>=cfg['be_trigger_r']:
                    stop=max(stop,entry+cfg['be_offset_r']*risk); be_armed=True

            # Range/stagnation decision uses completed bars only, and exits at next BID open.
            held=z-ii+1
            if cfg['range_after'] is not None and held>=cfg['range_after'] and z<end:
                lb=cfg['range_lookback']
                if z-lb+1>=ii:
                    win=bid[z-lb+1:z+1]
                    width=max(x.high for x in win)-min(x.low for x in win)
                    atr_now=a14[z]
                    progress=(bid[z].close-entry)/risk
                    mfe=(peak_high-entry)/risk
                    if width<=cfg['range_width_atr']*atr_now and progress<=cfg['range_progress_max_r'] and mfe<=cfg['range_mfe_max_r']:
                        nx=z+1; xi=nx; xp=bid[nx].open; reason='RANGE'; range_signal_i=z; break
        r=(xp-entry)/risk
        out.append({'entry_i':ii,'exit_i':xi,'entry_price':entry,'exit_price':xp,'stop':stop0,'target':target,'r':r,'result':'WIN' if r>0 else ('LOSS' if r<0 else 'EVEN'),'exit_reason':reason,'range_signal_i':range_signal_i,'event':e})
        next_allowed=xi+1
    return out

def metrics_reason(ts):
    d={}
    for t in ts: d[t['exit_reason']]=d.get(t['exit_reason'],0)+1
    return d

def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)
def fm(m): return b.fmt(m)

def cfg_key(c): return json.dumps(c,sort_keys=True)

def random_cfg(r):
    range_on=r.random()<0.75
    be_on=r.random()<0.70
    return {
      'target_r':r.choice([2.0,2.25,2.5,2.75]),
      'max_hold':r.choice([18,24,30,36]),
      'stop_buffer_atr':r.choice([0.0,0.05,0.10]),
      'be_trigger_r':r.choice([0.75,1.0,1.25]) if be_on else None,
      'be_offset_r':r.choice([0.0,0.10]) if be_on else 0.0,
      'range_after':r.choice([8,12,16]) if range_on else None,
      'range_lookback':r.choice([4,6]) if range_on else 4,
      'range_width_atr':r.choice([0.8,1.0,1.2]) if range_on else 1.0,
      'range_progress_max_r':r.choice([0.25,0.50,0.75]) if range_on else 0.5,
      'range_mfe_max_r':r.choice([0.75,1.0,1.25]) if range_on else 1.0,
    }

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    ev=v6.detect2(bid,e20,e50,a14,a50,rv,V6P)

    baseline_cfg={'target_r':2.25,'max_hold':24,'stop_buffer_atr':0.0,'be_trigger_r':None,'be_offset_r':0.0,'range_after':None,'range_lookback':4,'range_width_atr':1.0,'range_progress_max_r':0.5,'range_mfe_max_r':1.0}
    baseline=exit_sim(bid,ask,ev,a14,baseline_cfg)

    years=[('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    rng=random.Random(2026082707); seen=set(); C=[]
    # include baseline and deterministic random candidates
    configs=[baseline_cfg]
    for _ in range(2600): configs.append(random_cfg(rng))
    for cfg in configs:
        k=cfg_key(cfg)
        if k in seen: continue
        seen.add(k)
        ts=exit_sim(bid,ask,ev,a14,cfg)
        ym=[b.metrics(sub(ts,a,z,bid)) for a,z in years]; dev=b.metrics(sub(ts,'2022-08-27','2025-08-27',bid))
        if min(x['trades'] for x in ym)<8 or dev['trades']<30: continue
        if min(x['expectancy_r'] for x in ym)<0.03 or dev['expectancy_r']<0.30 or dev['pf']<1.7: continue
        exps=[x['expectancy_r'] for x in ym]; mn=min(exps); sd=statistics.pstdev(exps)
        complexity=(0.018 if cfg['be_trigger_r'] is not None else 0)+(0.022 if cfg['range_after'] is not None else 0)+(0.010 if cfg['stop_buffer_atr']>0 else 0)
        score=dev['expectancy_r']+0.16*mn-0.10*sd+0.045*math.log(max(dev['pf'],1))-0.030*dev['max_dd_r']+0.0025*min(dev['trades'],50)-complexity
        C.append((score,cfg,ym,dev,ts))
    C.sort(reverse=True,key=lambda x:x[0])
    if not C: raise RuntimeError('no V7 exit candidates')

    # Prefer a top robust candidate that materially reduces development DD vs V6 baseline without collapsing expectancy.
    base_dev=b.metrics(sub(baseline,'2022-08-27','2025-08-27',bid))
    chosen=None
    for x in C[:120]:
        m=x[3]
        if m['max_dd_r']<=base_dev['max_dd_r']-0.35 and m['expectancy_r']>=base_dev['expectancy_r']-0.12 and m['pf']>=2.0:
            chosen=x; break
    if chosen is None: chosen=C[0]
    score,cfg,ym,dev,allts=chosen

    external=sub(allts,'2021-08-27','2022-08-27',bid)
    recent=sub(allts,'2025-08-27','2026-08-27',bid)
    latest2=sub(allts,'2024-08-27','2026-08-27',bid)
    full4=sub(allts,'2022-08-27','2026-08-27',bid)
    base_external=sub(baseline,'2021-08-27','2022-08-27',bid)
    base_recent=sub(baseline,'2025-08-27','2026-08-27',bid)
    base_latest2=sub(baseline,'2024-08-27','2026-08-27',bid)
    base_full4=sub(baseline,'2022-08-27','2026-08-27',bid)

    # Nearby robustness checks around key selected exit parameters; not used for selection.
    neighbors=[]
    variants=[]
    for tr in sorted(set([max(1.75,cfg['target_r']-0.25),cfg['target_r'],min(3.0,cfg['target_r']+0.25)])):
      nc=dict(cfg); nc['target_r']=tr; variants.append(('target',tr,nc))
    if cfg['be_trigger_r'] is not None:
      for bt in sorted(set([max(0.75,cfg['be_trigger_r']-0.25),cfg['be_trigger_r'],min(1.5,cfg['be_trigger_r']+0.25)])):
        nc=dict(cfg); nc['be_trigger_r']=bt; variants.append(('be_trigger',bt,nc))
    if cfg['range_after'] is not None:
      for ra in sorted(set([max(6,cfg['range_after']-4),cfg['range_after'],min(20,cfg['range_after']+4)])):
        nc=dict(cfg); nc['range_after']=ra; variants.append(('range_after',ra,nc))
    for name,val,nc in variants:
        ts=exit_sim(bid,ask,ev,a14,nc)
        neighbors.append({'parameter':name,'value':val,'development_3y':fm(b.metrics(sub(ts,'2022-08-27','2025-08-27',bid))),'external_2021_22':fm(b.metrics(sub(ts,'2021-08-27','2022-08-27',bid))),'recent_2025_26':fm(b.metrics(sub(ts,'2025-08-27','2026-08-27',bid)))})

    summary={
      'data_source':'Dukascopy JForex BID+ASK M15 aggregated H1',
      'entry_rules':'V6 entry rules frozen; only exit/risk/time-range logic optimized for V7',
      'selection_policy':'V7 exit parameters selected on 2022-08-27～2025-08-26 only. 2021-08-27～2022-08-26 is independent prior validation for V7 exits. 2025-08-27～2026-08-26 is recent revalidation, not untouched.',
      'v6_entry_params':V6P,
      'v6_baseline_exit':baseline_cfg,
      'v7_exit_params':cfg,
      'v6_baseline_development_3y':fm(base_dev),
      'v7_development_years':[fm(x) for x in ym],
      'v7_development_3y':fm(dev),
      'v7_external_2021_22':fm(b.metrics(external)),
      'v7_recent_2025_26':fm(b.metrics(recent)),
      'v7_latest_2y':fm(b.metrics(latest2)),
      'v7_full_2022_26':fm(b.metrics(full4)),
      'v6_external_2021_22':fm(b.metrics(base_external)),
      'v6_recent_2025_26':fm(b.metrics(base_recent)),
      'v6_latest_2y':fm(b.metrics(base_latest2)),
      'v6_full_2022_26':fm(b.metrics(base_full4)),
      'v7_exit_reasons_development':metrics_reason(sub(allts,'2022-08-27','2025-08-27',bid)),
      'v7_exit_reasons_recent':metrics_reason(recent),
      'nearby_exit_robustness':neighbors,
      'top_exit_candidates':[{'score':round(x[0],4),'cfg':x[1],'years':[fm(y) for y in x[2]],'dev':fm(x[3])} for x in C[:12]]
    }
    print('=== V7 SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    # Viewer latest 2 years
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]
    cid='gbpjpy_h1_flush_recovery_v7_exit_range'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'ATR14','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14[si:ei]]}]},{'label':'Volume','series':[{'kind':'histogram','label':'H1 Volume','values':[round(x.volume,4) for x in cb]}]},{'label':'RVOL20','levels':[V6P['rvol_min'],1.0],'series':[{'kind':'line','label':'RVOL20','values':[None if x is None else round(x,6) for x in rv[si:ei]]}]},{'label':'ATR14/ATR50','levels':[V6P['vol_ratio_min'],V6P['vol_ratio_max']],'series':[{'kind':'line','label':'Vol Ratio','values':[round(a14[i]/a50[i],6) if a50[i]>0 else None for i in range(si,ei)]}]}]}
    vt=[]
    for no,t in enumerate(latest2,1):
        e=t['event']; nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7 Exit+Range','note':f"exit={t['exit_reason']}, RVOL={e['flush_rvol']:.2f}, ATR比={e['vol_ratio']:.2f}, BOvol={e['breakout_rvol']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    exit_logic=[
      f"初期SL=Flush安値 - {cfg['stop_buffer_atr']}×Flush ATR",
      f"基本TP={cfg['target_r']}R",
      f"最大保有={cfg['max_hold']}時間",
      (f"MFE {cfg['be_trigger_r']}R到達後、次足からSLを建値{('+'+str(cfg['be_offset_r'])+'R') if cfg['be_offset_r'] else ''}へ移動" if cfg['be_trigger_r'] is not None else '建値移動なし'),
      (f"{cfg['range_after']}時間経過後、直近{cfg['range_lookback']}本の値幅<={cfg['range_width_atr']}×ATR14、現在進捗<={cfg['range_progress_max_r']}R、MFE<={cfg['range_mfe_max_r']}Rならレンジ判定し次足BID始値で撤退" if cfg['range_after'] is not None else 'レンジ早期撤退なし'),
      '同一H1足でSL/TP両方ならSL先着'
    ]
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7 Exit + Range','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_EXIT_RANGE','name':'V6 Entry + V7 Dynamic Exit / Range Escape','hypothesis':'V6の優位なエントリーを固定し、利益保護・時間切れ・レンジ停滞撤退を組み合わせることで、期待値を大きく落とさずドローダウンと無駄な保有を減らす。','entry_logic':['V6 entry rules frozen',json.dumps(V6P,ensure_ascii=False),'全条件はEntry前に確定','BUYはASK始値'],'exit_logic':exit_logic,'future_tests':['MT5 broker tick volume再検証','V7 exit rulesを完全未使用の将来期間でウォークフォワード','range判定を実現ボラティリティでも比較']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_ExitRange_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()

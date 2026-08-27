import csv,json,statistics
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path

OUT=Path('results'); OUT.mkdir(exist_ok=True)
START='2024-08-27'; END='2026-08-27'
@dataclass
class Bar:
    dt:datetime; open:float; high:float; low:float; close:float; volume:float=0.0

def parse_dt(s):
    s=str(s).strip().replace('Z','+00:00')
    try:
        x=float(s); return datetime.fromtimestamp(x/1000 if x>1e12 else x,tz=timezone.utc).replace(tzinfo=None)
    except: pass
    d=datetime.fromisoformat(s)
    if d.tzinfo: d=d.astimezone(timezone.utc).replace(tzinfo=None)
    return d

def norm(s): return ''.join(ch.lower() for ch in s if ch.isalnum())
def load(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f); m={norm(x):x for x in r.fieldnames}
        def k(*xs):
            for x in xs:
                if norm(x) in m:return m[norm(x)]
            return None
        tk=k('timestamp','time','datetime','date'); ok=k('open'); hk=k('high'); lk=k('low'); ck=k('close'); vk=k('volume','tick_volume','tickvolume')
        a=[]
        for z in r:
            try:a.append(Bar(parse_dt(z[tk]),float(z[ok]),float(z[hk]),float(z[lk]),float(z[ck]),float(z[vk]) if vk and z.get(vk) else 0.0))
            except:pass
    a.sort(key=lambda b:b.dt); return list({b.dt:b for b in a}.values())

def h1(a):
    g={}
    for b in a:g.setdefault(b.dt.replace(minute=0,second=0,microsecond=0),[]).append(b)
    out=[]
    for t in sorted(g):
        x=sorted(g[t],key=lambda b:b.dt); out.append(Bar(t,x[0].open,max(v.high for v in x),min(v.low for v in x),x[-1].close,sum(v.volume for v in x)))
    return out

def ema(v,p):
    a=2/(p+1); o=[v[0]]
    for x in v[1:]:o.append(a*x+(1-a)*o[-1])
    return o

def atr(b,p):
    tr=[b[0].high-b[0].low]
    for i in range(1,len(b)):
        pc=b[i-1].close; tr.append(max(b[i].high-b[i].low,abs(b[i].high-pc),abs(b[i].low-pc)))
    o=[tr[0]]
    for i in range(1,len(tr)):o.append(sum(tr[:i+1])/(i+1) if i<p else (o[-1]*(p-1)+tr[i])/p)
    return o

def metrics(ts):
    rs=[t['r'] for t in ts]; n=len(rs)
    if not n:return {'trades':0,'win_rate':0,'expectancy_r':0,'pf':0,'max_dd_r':0,'cum_r':0}
    pos=sum(x for x in rs if x>0); neg=-sum(x for x in rs if x<0); eq=peak=dd=0
    for x in rs:eq+=x; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {'trades':n,'win_rate':round(100*sum(x>0 for x in rs)/n,3),'expectancy_r':round(sum(rs)/n,3),'pf':round(pos/neg if neg else 999,3),'max_dd_r':round(dd,3),'cum_r':round(sum(rs),3)}

def run(bid,ask):
    cl=[x.close for x in bid]; e20=ema(cl,20); e50=ema(cl,50); a14=atr(bid,14); a50=atr(bid,50)
    vols=[x.volume for x in bid]; rv=[None]*len(bid)
    for i in range(20,len(bid)):
        med=statistics.median(vols[i-20:i]); rv[i]=vols[i]/med if med>0 else None
    events=[]; i=60
    while i<len(bid)-50:
        h0i=max(range(i-5,i),key=lambda z:bid[z].high); h0=bid[h0i].high
        if not (1<=i-h0i<=5):i+=1;continue
        if not(e20[h0i]>e50[h0i] and e50[h0i]>e50[h0i-5] and bid[h0i].close>e20[h0i]):i+=1;continue
        aa=a14[h0i]; prior=min(bid[z].low for z in range(max(0,h0i-12),h0i)); fl=bid[i].low; drop=h0-fl
        if drop<1.5*aa or not fl<prior:i+=1;continue
        if rv[i] is None or rv[i]<0.80 or a14[i]/a50[i]<0.85:i+=1;continue
        ri=None; rr=None
        for j in range(i+1,min(len(bid),i+7)):
            r=(bid[j].close-fl)/drop
            if bid[j].close>prior and r>=0.45:ri=j;rr=r;break
        if ri is None:i+=1;continue
        bi=None
        for k in range(ri,min(len(bid)-1,ri+11)):
            if bid[k].close>h0:bi=k;break
        if bi is None:i+=1;continue
        ti=None; abo=a14[bi]
        for q in range(bi+1,min(len(bid)-1,bi+7)):
            if bid[q].low<=h0+0.70*abo and bid[q].close>=h0-0.20*abo and 6<=bid[q].dt.hour<16:ti=q;break
        if ti is not None and ti+1<len(bid):events.append({'entry_i':ti+1,'flush_i':i,'flush_low':fl,'drop_atr':drop/aa,'flush_rvol':rv[i],'volratio':a14[i]/a50[i],'recovery_i':ri,'breakout_i':bi,'retest_i':ti})
        i=bi+1
    am={x.dt:x for x in ask}; spreads=[am[x.dt].open-x.open for x in bid if x.dt in am and am[x.dt].open>=x.open]; fallback=statistics.median(spreads)
    ts=[]; nextok=0
    for ev in events:
        ei=ev['entry_i']
        if ei<nextok:continue
        ab=am.get(bid[ei].dt); entry=ab.open if ab else bid[ei].open+fallback; stop=ev['flush_low']; risk=entry-stop
        if risk<=0 or risk/entry>0.05:continue
        target=entry+2.25*risk; end=min(len(bid)-1,ei+23); exi=end; exp=bid[end].close; reason='TIME'
        for z in range(ei,end+1):
            hs=bid[z].low<=stop; ht=bid[z].high>=target
            if hs and ht:exi=z;exp=stop;reason='SL_SAME_BAR';break
            if hs:exi=z;exp=stop;reason='SL';break
            if ht:exi=z;exp=target;reason='TP2.25R';break
        r=(exp-entry)/risk
        ts.append({'entry_i':ei,'exit_i':exi,'entry_price':entry,'exit_price':exp,'stop':stop,'target':target,'r':r,'result':'WIN' if r>0 else ('LOSS' if r<0 else 'EVEN'),'exit_reason':reason,**ev})
        nextok=exi+1
    return ts,e20,e50,a14,a50,rv,fallback

def cj(b):return {'time':b.dt.replace(tzinfo=timezone.utc).isoformat(timespec='seconds'),'open':round(b.open,6),'high':round(b.high,6),'low':round(b.low,6),'close':round(b.close,6),'volume':round(b.volume,4)}

b15=load('data/GBPJPY_M15_bid.csv'); a15=load('data/GBPJPY_M15_ask.csv'); bid=h1(b15); ask=h1(a15)
ts,e20,e50,a14,a50,rv,spread=run(bid,ask)
split=datetime(2025,8,27)
y1=[t for t in ts if bid[t['entry_i']].dt<split]; y2=[t for t in ts if bid[t['entry_i']].dt>=split]
chart_id='gbpjpy_h1_flush_recovery_v5'
tr=[]
for no,t in enumerate(ts,1):
    tr.append({'no':no,'chart_id':chart_id,'side':'BUY','entry_i':t['entry_i'],'exit_i':t['exit_i'],'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V5','note':f"drop={t['drop_atr']:.2f}ATR / RVOL20={t['flush_rvol']:.2f}x / ATR14/ATR50={t['volratio']:.2f} / {t['exit_reason']}"})
ratio=[None if a50[i]==0 else a14[i]/a50[i] for i in range(len(bid))]
report={'meta':{'report_title':'GBPJPY H1 Flush Recovery V5','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V5','name':'強いFlush + Volume + Volatility + 柔軟回復/押し目','hypothesis':'大口ストップ巻き込み仮説では、Flush自体は十分深い一方、回復と押し目の時間・深さを少し柔軟にした方が本物の再上昇を拾える可能性がある。','entry_logic':['EMA20>EMA50かつEMA50上向き','直近12本安値Sweep + 1.5ATR以上のFlush','Flush RVOL20>=0.80','ATR14/ATR50>=0.85','6本以内に45%以上回復','10本以内にH0終値突破','6本以内にH0+0.70ATRまでの押し目、H0-0.20ATR以上を終値維持、London時間','次足ASK始値BUY'],'exit_logic':['SL=Flush安値','TP=2.25R','最大24時間','同一H1足でSL/TP両方ならSL先着'], 'future_tests':['追加の未使用期間で固定条件再検証','MT5ブローカーtick volumeで再検証']},'charts':[{'id':chart_id,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in bid],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50]}],'panes':[{'label':'ATR14','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14]}]},{'label':'Volume','series':[{'kind':'histogram','label':'H1 Volume','values':[round(x.volume,4) for x in bid]}]},{'label':'RVOL20','levels':[0.8,1.0],'series':[{'kind':'line','label':'RVOL20','values':[None if x is None else round(x,6) for x in rv]}]},{'label':'ATR14/ATR50','levels':[0.85,1.0],'series':[{'kind':'line','label':'ATR14/ATR50','values':[None if x is None else round(x,6) for x in ratio]}]}]}],'trades':tr,'notes':[f'V5 full: {metrics(ts)}',f'Year1: {metrics(y1)}',f'Year2: {metrics(y2)}',f'Median spread={spread:.6f}','シグナル=BID、BUY Entry=ASK、決済=BID。実BID/ASKスプレッド反映。手数料・追加スリッページなし。']}
summary={'period':'2024-08-27 ～ 2026-08-26','data':'Dukascopy M15 BID+ASK aggregated H1','rules':report['strategy']['entry_logic'],'full_2y':metrics(ts),'year1':metrics(y1),'year2':metrics(y2),'median_spread':spread}
(OUT/'GBPJPY_H1_FlushRecovery_V5_2y.json').write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
(OUT/'GBPJPY_H1_FlushRecovery_V5_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
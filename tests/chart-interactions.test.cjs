'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const sample=fs.readFileSync(path.join(root,'samples/GPT出力データ_サンプル.json'),'utf8');

// Exercise the actual inline application and registered handlers, without browser dependencies.
// Canvas is a drawing stub: these tests do not certify real-browser gesture delivery or layout.
function setup(filename){
  const elements=new Map(),windowListeners=new Map();
  const drawing=new Proxy({}, {get:(obj,key)=>obj[key]??(()=>{}),set:(obj,key,value)=>(obj[key]=value,true)});
  function element(id){
    if(elements.has(id))return elements.get(id);
    const listeners=new Map(),captures=new Set();
    const e={innerHTML:'',textContent:'',style:{},disabled:false,value:'',className:'',
      classList:{add(){},remove(){},toggle(){}},
      addEventListener(name,fn,options){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push({fn,options})},
      getBoundingClientRect:()=>({width:id==='equity'?300:400,height:id==='equity'?170:710,left:20,top:0}),
      getContext:()=>drawing,
      setPointerCapture:id=>captures.add(id),hasPointerCapture:id=>captures.has(id),releasePointerCapture:id=>captures.delete(id),
      listeners,captures};
    elements.set(id,e);return e;
  }
  const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>[]},
    window:{addEventListener(name,fn){windowListeners.set(name,fn)}},devicePixelRatio:1,
    console:{warn(){}},confirm:()=>true});
  const run=code=>vm.runInContext(code,context);
  const html=fs.readFileSync(process.env.VIEWER_HTML||path.join(root,filename),'utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  run(script);
  const chart=element('chart');
  function fire(type,id=1,x=190,y=100,extra={}){
    let prevented=false;
    const e={pointerId:id,pointerType:'touch',button:0,clientX:x,clientY:y,deltaY:100,preventDefault(){prevented=true},...extra};
    const handlers=chart.listeners.get(type)||[];
    assert.ok(handlers.length,`${type} must have a registered handler`);
    for(const {fn} of handlers)fn(e);
    return {prevented};
  }
  const view=()=>JSON.parse(run('JSON.stringify(view)'));
  const span=()=>{const v=view();return v.end-v.start};
  async function load(){context.files=[{name:'sample.json',type:'application/json',text:async()=>sample}];await run('loadJsonFiles(files)');run('view={start:10,end:50};drawChart()')}
  return {run,context,element,chart,fire,view,span,load,html,windowEvent:name=>windowListeners.get(name)()};
}
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);

for(const filename of ['index.html','report.html']){
  test(`${filename}: single finger pans and clamps to both ends`,async()=>{
    const h=setup(filename);await h.load();
    h.fire('pointerdown');assert.ok(h.chart.captures.has(1));
    h.fire('pointermove',1,230);near(h.view().start,5);near(h.span(),40);
    h.fire('pointermove',1,10000);near(h.view().start,0);
    h.fire('pointermove',1,-10000);near(h.view().end,63);
    h.fire('pointerup');assert.equal(h.run('drag'),null);assert.equal(h.chart.captures.size,0);
    const ended=h.view();h.fire('pointermove',1,250);assert.deepEqual(h.view(),ended);
  });
  test(`${filename}: pinch zoom anchors the moving midpoint`,async()=>{
    const h=setup(filename);await h.load();
    const candleAt=x=>h.view().start+(x-30)/320*h.span();
    const anchor=candleAt(210);
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);
    h.fire('pointermove',1,90);h.fire('pointermove',2,330);
    near(h.span(),40*160/240);near(candleAt(210),anchor);
    h.fire('pointermove',1,106);h.fire('pointermove',2,346);
    near(candleAt(226),anchor);
    h.fire('pointermove',1,146);h.fire('pointermove',2,306);
    near(h.span(),40);near(candleAt(226),anchor);
  });
  test(`${filename}: vertical pinch and extreme distances stay finite`,async()=>{
    const h=setup(filename);await h.load();
    h.fire('pointerdown',1,190,100);h.fire('pointerdown',2,190,200);
    h.fire('pointermove',2,190,300);near(h.span(),20);
    h.fire('pointermove',2,190,100000);near(h.span(),5);
    h.fire('pointermove',2,190,100);near(h.span(),63);
    assert.ok(Number.isFinite(h.view().start)&&Number.isFinite(h.view().end));
  });
  test(`${filename}: two fingers to one rebases without a jump`,async()=>{
    const h=setup(filename);await h.load();
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);h.fire('pointermove',2,330);
    const before=h.view();h.fire('pointerup',2,330);assert.deepEqual(h.view(),before);
    h.fire('lostpointercapture',2,330);assert.deepEqual(h.view(),before);
    h.fire('pointermove',1,130);assert.deepEqual(h.view(),before);
    h.fire('pointermove',1,146);near(h.view().start,before.start-16/320*(before.end-before.start));
  });
  test(`${filename}: cancel, lost capture and blur cannot leave a stuck drag`,async()=>{
    const h=setup(filename);await h.load();
    for(const event of ['pointercancel','lostpointercapture']){
      h.fire('pointerdown');h.fire(event);assert.equal(h.run('drag'),null);assert.equal(h.run('chartPointers.size'),0);
      const v=h.view();h.fire('pointermove',1,250);assert.deepEqual(h.view(),v);
    }
    h.fire('pointerdown',1);h.fire('pointerdown',2);h.windowEvent('blur');
    assert.equal(h.run('chartPointers.size'),0);assert.equal(h.chart.captures.size,0);
  });
  test(`${filename}: chart changes, trade navigation, full view and resize reset gestures`,async()=>{
    const h=setup(filename);await h.load();
    for(const action of [()=>h.run('switchChart(1)'),()=>h.run('focusTrade(0)'),()=>h.element('allView').onclick(),()=>h.windowEvent('resize')]){
      h.fire('pointerdown');action();assert.equal(h.run('chartPointers.size'),0);assert.equal(h.run('drag'),null);
      const v=h.view();h.fire('pointermove',1,240);assert.deepEqual(h.view(),v);
    }
  });
  test(`${filename}: mouse drag, wheel and tooltip still work`,async()=>{
    const h=setup(filename);await h.load();
    h.fire('pointerdown',1,190,100,{pointerType:'mouse',button:2});assert.equal(h.run('drag'),null);
    h.fire('pointerdown',1,190,100,{pointerType:'mouse'});h.fire('pointermove',1,230,100,{pointerType:'mouse'});near(h.view().start,5);
    h.fire('pointerup',1,230,100,{pointerType:'mouse'});
    const old=h.span();assert.ok(h.fire('wheel',1,190,100,{deltaY:-100}).prevented);assert.ok(h.span()<old);
    h.fire('mousemove',1,190,100,{pointerType:'mouse'});assert.equal(h.element('tooltip').style.display,'block');
  });
  test(`${filename}: empty and one-candle datasets remain safe`,async()=>{
    const h=setup(filename);h.fire('pointerdown');h.fire('pointermove');assert.equal(h.run('drag'),null);
    assert.equal(h.fire('wheel').prevented,false);
    await h.load();h.run('DATA.charts[0].candles=DATA.charts[0].candles.slice(0,1);DATA.trades=[];switchChart(0)');
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);h.fire('pointermove',2,330);
    assert.deepEqual(h.view(),{start:0,end:0});
    h.run('clearAllDatasets()');assert.equal(h.run('DATA'),null);assert.equal(h.chart.captures.size,0);
  });
  test(`${filename}: imports, deletion, filters, escaping and statistics regressions`,async()=>{
    const h=setup(filename);await h.load();await h.load();assert.equal(h.run('DATASETS.length'),2);
    assert.equal(h.run('DATA.summary.buy.trades'),2);assert.equal(h.run('DATA.summary.sell.trades'),2);
    assert.deepEqual(JSON.parse(h.run('JSON.stringify(calcStats([{r:2},{r:-1},{r:1.5},{r:-1}]))')),
      {trades:4,win_rate:50,expectancy_r:.375,profit_factor:1.75,max_dd_r:1,total_r:1.5});
    h.run("filter='SELL';renderRows()");assert.equal((h.element('tradeRows').innerHTML.match(/<tr /g)||[]).length,2);
    h.run('removeChartFromActive(1)');assert.equal(h.run('DATA.charts.length'),1);assert.equal(h.run('DATA.trades.length'),2);
    h.run('removeDataset(0)');assert.equal(h.run('DATASETS.length'),1);
    h.context.files=[{name:'bad.json',type:'application/json',text:async()=>'{'}];await h.run('loadJsonFiles(files)');assert.equal(h.run('DATASETS.length'),1);
    h.run('DATA.strategy.name="<img src=x onerror=alert(1)>";renderStrategy()');assert.ok(!h.element('strategyBody').innerHTML.includes('<img'));
    h.run('clearAllDatasets()');assert.equal(h.run('DATA'),null);
  });
}
test('Both entry points contain identical HTML',()=>assert.equal(fs.readFileSync(path.join(root,'index.html'),'utf8'),fs.readFileSync(path.join(root,'report.html'),'utf8')));

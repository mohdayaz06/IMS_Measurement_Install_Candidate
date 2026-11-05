const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
function runClient(overrides={}){
 const state={claimed:false,status:null,headers:{},event:null};
 const mocks={getRequestPath:()=>'/ims/events/a',getRequestMethod:()=> 'POST',getRequestHeader:k=>k==='origin'?'https://shop.example':'',
  getRequestBody:()=>JSON.stringify({event_id:'e',visitor_id:'v',ts:'2026-11-04T00:00:00Z',analytics_consent:true,marketing_consent:false}),
  claimRequest:()=>state.claimed=true,runContainer:(e,cb)=>{state.event=e;cb();},setResponseStatus:v=>state.status=v,
  setResponseHeader:(k,v)=>state.headers[k]=v,returnResponse:()=>{},JSON,...overrides};
 const code=fs.readFileSync('integrations/sgtm-http-client.js','utf8');
 vm.runInNewContext('(function(data){'+code+'})',{require:n=>mocks[n]})({collectPath:'/ims/events/a',verifiedPath:'/ims/verified',allowedOrigins:'https://shop.example',gatewayKey:'secret'});
 return state;
}
test('server GTM client enforces origin and maps only normalized event fields',()=>{const s=runClient();assert.equal(s.status,202);assert.equal(s.event.event_name,'ims_touch');assert.equal(s.event.ims_visitor_id,'v');assert.equal(s.event.ims_marketing_consent,0);});
test('server GTM client rejects unapproved origin',()=>{const s=runClient({getRequestHeader:()=> 'https://bad.example'});assert.equal(s.status,403);assert.equal(s.event,null);});
test('server GTM verified route rejects missing secret',()=>{const s=runClient({getRequestPath:()=>'/ims/verified'});assert.equal(s.status,401);assert.equal(s.event,null);});
test('server GTM preflight sends restricted CORS without firing tags',()=>{const s=runClient({getRequestMethod:()=> 'OPTIONS'});assert.equal(s.status,204);assert.equal(s.headers['Access-Control-Allow-Origin'],'https://shop.example');assert.equal(s.event,null);});
test('GTM imports have valid structured sections and sandbox source',()=>{
 for(const f of ['dist/ims-http-client.tpl','dist/ims-ledger-forwarder.tpl']){
  const s=fs.readFileSync(f,'utf8');
  for(const name of ['INFO','TEMPLATE_PARAMETERS','SERVER_PERMISSIONS']){
   const r=new RegExp('___'+name+'___\\s*([\\s\\S]*?)(?=___|$)');assert.doesNotThrow(()=>JSON.parse(s.match(r)[1]));
  }
  assert(s.includes('___SANDBOXED_JS_FOR_SERVER___'));
 }
});
function connector(role='client'){
 const user=new Map();const script=new Map([['IMS_BASE_URL','https://tracking.example']]);const props=m=>({getProperty:k=>m.get(k),setProperty:(k,v)=>m.set(k,v),deleteProperty:k=>m.delete(k)});
 const ctx={PropertiesService:{getScriptProperties:()=>props(script),getUserProperties:()=>props(user)},
  UrlFetchApp:{fetch:(url,options)=>({getResponseCode:()=>200,getContentText:()=>JSON.stringify(url.endsWith('/api/session')?{role}: {rows:[{date:'2026-11-04',channel:'meta',media_cost:200,vendor_cost:100}]})})},console};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('reporting/community-connector/Code.js','utf8'),ctx);return ctx;
}
test('Looker connector refuses agency credentials',()=>{const c=connector('agency');assert.equal(c.setKey({key:'secret'}).errorCode,'INVALID_CREDENTIALS');});
test('Looker connector projects requested safe fields and formats dates',()=>{const c=connector();assert.equal(c.setKey({key:'client'}).errorCode,'NONE');const r=c.getData({configParams:{report:'attribution'},dateRange:{startDate:'2026-11-01',endDate:'2026-11-04'},fields:[{name:'date'},{name:'media_cost'}]});assert.equal(r.rows[0].values[0],'20261104');assert.equal(r.rows[0].values[1],200);assert(!JSON.stringify(r).includes('vendor_cost'));});
test('Looker connector rejects unsupported hidden raw cost field',()=>{const c=connector();c.setKey({key:'client'});assert.throws(()=>c.getData({dateRange:{startDate:'2026-11-01',endDate:'2026-11-04'},fields:[{name:'vendor_cost'}]}));});
test('Shopify generated pixel is self-contained and valid JavaScript',()=>{const code=fs.readFileSync('dist/shopify-custom-pixel.js','utf8');assert.doesNotThrow(()=>new vm.Script(code));assert(code.includes('const imsEmbedded='));assert(!code.includes("s.src=IMS_BASE+'/pixel.js'"));});

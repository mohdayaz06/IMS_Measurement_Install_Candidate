/* IMS v2 collection SDK. No secrets, costs, or markup belong in this file. */
(function(w){
  'use strict';
  const uuid=()=>crypto.randomUUID();
  function create(options){
    const base=new URL(options.baseUrl).origin, tenant=options.tenant;
    let allowed=false, marketing=false, visitor=null;
    const storage=options.storage||w.localStorage;
    const key='ims:v2:'+tenant;
    async function identity(){
      if(!allowed)return null;
      if(visitor)return visitor;
      let record;try{record=JSON.parse(await storage.getItem(key)||'null');}catch(_){}
      if(record&&record.expires>Date.now()) visitor=record.id;
      else {visitor=uuid();await storage.setItem(key,JSON.stringify({id:visitor,expires:Date.now()+30*86400000}));}
      return visitor;
    }
    async function consent(granted,marketingGranted){
      allowed=granted===true;
      marketing=allowed&&marketingGranted===true;
      if(!allowed){visitor=null;await storage.removeItem(key);await storage.removeItem(key+':session');}
    }
    function source(page,referrer){
      const u=new URL(page),p=u.searchParams;
      if(p.has('utm_source'))return {source:p.get('utm_source'),medium:p.get('utm_medium')||'',campaign:p.get('utm_campaign')||'(none)'};
      if(p.has('gclid')||p.has('gbraid')||p.has('wbraid'))return {source:'google',medium:'cpc',campaign:'(unmapped)'};
      // A Facebook click ID alone does not prove a paid click.
      let ref;try{ref=new URL(referrer);}catch(_){}
      if(ref&&ref.hostname!==u.hostname){
        if(/(^|\.)google\.[a-z.]+$/.test(ref.hostname))return {source:'google',medium:'organic',campaign:'(none)'};
        return {source:ref.hostname,medium:'referral',campaign:'(none)'};
      }
      return {source:'direct',medium:'',campaign:'(none)'};
    }
    async function send(raw){
      if(!allowed)return {status:'consent_denied'};
      const id=await identity();
      const signals={};
      if(marketing&&raw.page_url){
        const p=new URL(raw.page_url).searchParams;
        for(const key of ['gclid','gbraid','wbraid'])if(p.has(key))signals[key]=p.get(key);
        if(p.has('fbclid'))signals.fbc='fb.1.'+Date.now()+'.'+p.get('fbclid');
        try{const match=w.document.cookie.match(/(?:^|; )_fbp=([^;]+)/);if(match)signals.fbp=decodeURIComponent(match[1]);}catch(_){}
      }
      const event={event_id:uuid(),visitor_id:id,analytics_consent:true,marketing_consent:marketing,signals,ts:new Date().toISOString(),...raw};
      if(options.mode==='sgtm'){
        if(typeof w.gtag!=='function')throw Error('Configure gtag and GA4 server_container_url first');
        w.gtag('event','ims_touch',{
          send_to:options.measurementId,
          ims_event_id:event.event_id,ims_visitor_id:id,ims_ts:event.ts,
          ims_source:event.source,ims_medium:event.medium,ims_campaign:event.campaign,
          ims_order_id:event.order_id||'',ims_analytics_consent:1,ims_marketing_consent:marketing?1:0,
          ims_gclid:signals.gclid,ims_gbraid:signals.gbraid,ims_wbraid:signals.wbraid,ims_fbc:signals.fbc,ims_fbp:signals.fbp,
          page_location:raw.page_url?new URL(raw.page_url).origin+new URL(raw.page_url).pathname:undefined
        });
        return {status:'queued_to_sgtm',event_id:event.event_id};
      }
      const response=await fetch(options.collectUrl || base+'/collect/'+encodeURIComponent(tenant),{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(event),
        credentials:'omit',keepalive:true,referrerPolicy:'no-referrer'
      });
      if(!response.ok)throw Error('IMS collection failed: '+response.status);
      return response.json();
    }
    async function simpliPurchase(orderId,details){
      const c=options.simpli;
      if(!marketing||!c||!c.url)return {status:'not_configured_or_consent_denied'};
      const record=key+':simplifi:'+orderId+':'+c.url;
      if(await storage.getItem(record))return {status:'duplicate_suppressed'};
      const value=Number(details&&details.value),currency=String(details&&details.currency||'');
      if(c.url.indexOf('{{value}}')>=0&&(!Number.isFinite(value)||value<0))throw Error('Simpli.fi conversion value missing');
      const url=c.url.replace(/\{\{(order_id|value|currency)\}\}/g,(_,name)=>encodeURIComponent(String(name==='order_id'?orderId:name==='value'?value:currency)));
      const parsed=new URL(url);
      if(parsed.protocol!=='https:'||!(parsed.hostname==='simpli.fi'||parsed.hostname.endsWith('.simpli.fi')))throw Error('Use an approved HTTPS Simpli.fi tag URL');
      await new Promise((resolve,reject)=>{
        const el=c.type==='script'?w.document.createElement('script'):new w.Image();
        const timer=setTimeout(()=>reject(Error('Simpli.fi request timed out')),8000);
        el.onload=()=>{clearTimeout(timer);if(c.type==='script')el.remove();resolve();};
        el.onerror=()=>{clearTimeout(timer);if(c.type==='script')el.remove();reject(Error('Simpli.fi request failed'));};
        el.src=url;if(c.type==='script'){el.async=true;w.document.head.appendChild(el);}
      });
      await storage.setItem(record,String(Date.now()));
      return {status:'browser_request_loaded_not_platform_attribution'};
    }
    return {
      consent,
      visitorId:identity,
      pageView:async function(page,referrer){
        if(!allowed)return {status:'consent_denied'};
        // Track one acquisition touch per 30-minute session; tagged arrivals start a new touch.
        const acquisition=source(page,referrer), tagged=new URL(page).searchParams.has('utm_source');
        let session;try{session=JSON.parse(await storage.getItem(key+':session')||'null');}catch(_){}
        if(!tagged&&session&&session.until>Date.now())return {status:'same_session'};
        const result=await send({...acquisition,page_url:page});
        await storage.setItem(key+':session',JSON.stringify({until:Date.now()+1800000}));
        return result;
      },
      observeOrder:async function(orderId,details){
        const id=String(orderId).split('/').pop();
        const result=await send({source:'direct',medium:'',campaign:'(none)',order_id:id});
        if(marketing&&options.simpli)result.simplifi=await simpliPurchase(id,details||{});
        return result;
      }
    };
  }
  w.IMSAttribution={create};
})(window);

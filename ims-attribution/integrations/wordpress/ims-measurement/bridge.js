(function(){
  'use strict';
  const config=window.IMS_MERCHANT;if(!config||!window.IMSAttribution)return;
  const t=window.IMSAttribution.create(config);
  async function consent(detail){
    const allowed=detail.analytics===true;
    await t.consent(allowed,detail.marketing===true);
    const body=new URLSearchParams({action:'ims_measurement_identity',nonce:config.nonce,analytics:allowed?'1':'0',visitor:allowed?await t.visitorId():''});
    const r=await fetch(config.ajax,{method:'POST',body,credentials:'same-origin'});
    if(!r.ok)throw Error('IMS merchant identity bridge failed');
    if(allowed)await t.pageView(location.href,document.referrer);
  }
  window.addEventListener('ims:consent',e=>consent(e.detail||{}).catch(()=>console.error('IMS consent/identity bridge failed')));
  if(window.IMS_CURRENT_CONSENT)consent(window.IMS_CURRENT_CONSENT).catch(()=>console.error('IMS initialization failed'));
})();

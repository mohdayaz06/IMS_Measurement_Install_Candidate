/* IMS Looker Studio Community Connector. Only CLIENT credentials accepted.
   Set Script Property IMS_BASE_URL once to the fixed API HTTPS origin.
   Deploy as a Community Connector. No agency credentials in Script Properties.
*/
function getAuthType(){return {type:'KEY'};}
function setKey(request){
  const key=request.key;
  try{
    const r=imsFetch_('/api/session',key);
    if(r.role!=='client')return {errorCode:'INVALID_CREDENTIALS'};
    PropertiesService.getUserProperties().setProperty('IMS_CLIENT_TOKEN',key);
    return {errorCode:'NONE'};
  }catch(e){return {errorCode:'INVALID_CREDENTIALS'};}
}
function isAuthValid(){
  try{return imsFetch_('/api/session').role==='client';}catch(e){return false;}
}
function resetAuth(){PropertiesService.getUserProperties().deleteProperty('IMS_CLIENT_TOKEN');}
function isAdminUser(){return false;}
function getConfig(){
  return {configParams:[
    {type:'SELECT_SINGLE',name:'report',displayName:'Report',options:[{label:'Attribution',value:'attribution'},{label:'CTV household association',value:'ctv'},{label:'Approved incremental experiments',value:'experiments'}]},
    {type:'SELECT_SINGLE',name:'model',displayName:'Attribution model',options:[{label:'Last non-direct touch',value:'last_touch'},{label:'First non-direct touch',value:'first_touch'},{label:'Linear',value:'linear'},{label:'Position based',value:'position_based'}]},
    {type:'SELECT_SINGLE',name:'window',displayName:'CTV association window',options:[{label:'24 hours',value:'24'},{label:'7 days',value:'168'},{label:'30 days',value:'720'}]}
  ],dateRangeRequired:true};
}
function imsBase_(){
  const s=PropertiesService.getScriptProperties().getProperty('IMS_BASE_URL')||'';
  if(!/^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(s))throw Error('Configure fixed HTTPS IMS_BASE_URL');
  return s;
}
function imsFetch_(path,key){
  const token=key||PropertiesService.getUserProperties().getProperty('IMS_CLIENT_TOKEN');
  if(!token)throw Error('Client credential required');
  const r=UrlFetchApp.fetch(imsBase_()+path,{headers:{Authorization:'Bearer '+token},muteHttpExceptions:true,followRedirects:false});
  if(r.getResponseCode()!==200)throw Error('IMS request failed');
  return JSON.parse(r.getContentText());
}
function defs_(type){
  const dimension=(name,type)=>({name:name,label:name.replace(/_/g,' '),dataType:'STRING',semantics:{conceptType:'DIMENSION',semanticType:type||'TEXT'}});
  const metric=name=>({name:name,label:name.replace(/_/g,' '),dataType:'NUMBER',semantics:{conceptType:'METRIC',semanticType:'NUMBER',isReaggregatable:true}});
  if(type==='ctv')return ['campaign','currency','start_date','end_date'].map(n=>dimension(n,n.endsWith('_date')?'YEAR_MONTH_DAY':'TEXT')).concat(['associated_orders','associated_net_revenue','media_cost','unknown_network_type_orders'].map(metric));
  if(type==='experiments')return ['experiment','unit_type','status','currency','published_at','warnings'].map(n=>dimension(n)).concat(['treatment_units','control_units','revenue_lift_per_unit','revenue_lift_ci_low','revenue_lift_ci_high','relative_revenue_lift','incremental_revenue_treatment_population','incremental_media_cost','incremental_roas','p_value','sample_ratio_p_value'].map(metric));
  return [dimension('date','YEAR_MONTH_DAY'),dimension('channel'),dimension('campaign'),dimension('currency'),dimension('model')].concat(['revenue','orders','impressions','clicks','media_cost'].map(metric));
}
function getSchema(request){return {schema:defs_((request.configParams||{}).report||'attribution')};}
function getData(request){
  if(!isAuthValid())throw Error('A client credential is required; agency credentials are refused');
  const cfg=request.configParams||{},type=cfg.report||'attribution',range=request.dateRange;
  if(!range||!/^\d{4}-\d{2}-\d{2}$/.test(range.startDate)||!/^\d{4}-\d{2}-\d{2}$/.test(range.endDate))throw Error('Date range required');
  const dates='start='+encodeURIComponent(range.startDate)+'&end='+encodeURIComponent(range.endDate);
  let rows;
  if(type==='ctv'){
    const r=imsFetch_('/api/ctv/report?'+dates+'&window_hours='+encodeURIComponent(cfg.window||'168'));
    rows=r.rows.map(x=>Object.assign({},x,{currency:r.currency,start_date:range.startDate,end_date:range.endDate}));
  }else if(type==='experiments'){
    rows=imsFetch_('/api/experiments/published').rows.filter(x=>x.end.slice(0,10)>=range.startDate&&x.start.slice(0,10)<=range.endDate).map(x=>Object.assign({},x,{warnings:(x.warnings||[]).join('; '),revenue_lift_ci_low:(x.revenue_lift_95_ci||[])[0],revenue_lift_ci_high:(x.revenue_lift_95_ci||[])[1]}));
  }else{
    rows=imsFetch_('/api/report?'+dates+'&model='+encodeURIComponent(cfg.model||'last_touch')).rows;
  }
  const permitted=defs_(type),names=new Set((request.fields||[]).map(x=>x.name));
  const schema=permitted.filter(x=>names.has(x.name));
  if(schema.length!==names.size)throw Error('Unsupported report field');
  return {schema:schema,rows:rows.map(row=>({values:schema.map(field=>{
    const v=row[field.name];return field.semantics.semanticType==='YEAR_MONTH_DAY'&&v?String(v).replace(/-/g,''):v===undefined?null:v;
  })})),filtersApplied:false};
}

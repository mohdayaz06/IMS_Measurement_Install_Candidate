"""Explicit analyst approval boundary for client-facing experiment results."""
import json
from . import experiments
from .core import now

SAFE={'experiment','unit_type','treatment_units','control_units','status','revenue_per_treatment_unit',
      'revenue_per_control_unit','revenue_lift_per_unit','revenue_lift_95_ci','relative_revenue_lift',
      'incremental_revenue_treatment_population','conversion_rate_treatment','conversion_rate_control',
      'conversion_rate_difference','p_value','sample_ratio_p_value','incremental_media_cost','incremental_roas','warnings'}

def publish(store,tenant,experiment,data,actor):
    if data.get('analyst_approved') is not True or data.get('holdout_enforcement_verified') is not True:
        raise ValueError('Analyst approval and verified campaign holdout enforcement required')
    result=experiments.analyze(store,tenant,experiment,data.get('billable_incremental_cost'))
    if result['status']!='final':raise ValueError('Only completed experiments can be published')
    if result.get('warnings') and data.get('acknowledge_warnings') is not True:
        raise ValueError('Acknowledge statistical/data warnings before publication')
    safe={k:v for k,v in result.items() if k in SAFE}
    with store.db() as db:
        e=db.execute('SELECT start,end FROM experiments WHERE tenant=? AND id=?',(tenant,experiment)).fetchone()
        safe.update(start=e['start'],end=e['end'],published_at=now(),currency=store.tenant(tenant)['currency'])
        db.execute('INSERT INTO experiment_publications VALUES(?,?,?,?) ON CONFLICT(tenant,experiment) DO UPDATE SET published=excluded.published,body=excluded.body',(tenant,experiment,now(),json.dumps(safe)))
        store.audit(db,tenant,actor,'experiment.publish',{'experiment':experiment})
    return safe

def listed(store,tenant):
    with store.db() as db:
        return [json.loads(r['body']) for r in db.execute('SELECT body FROM experiment_publications WHERE tenant=? ORDER BY published DESC',(tenant,))]

def unpublish(store,tenant,experiment,actor):
    with store.db() as db:
        db.execute('DELETE FROM experiment_publications WHERE tenant=? AND experiment=?',(tenant,experiment))
        store.audit(db,tenant,actor,'experiment.unpublish',{'experiment':experiment})
    return {'status':'unpublished'}

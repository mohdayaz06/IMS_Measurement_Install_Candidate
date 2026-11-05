"""Fixed-horizon randomized-unit analysis. Assignment is NOT ad suppression."""
import hashlib
import hmac
import math
import random
import secrets
from datetime import datetime, timezone
from .core import ident, money, now, stamp

def create(store, tenant, data):
    start,end=stamp(data['start']),stamp(data['end'])
    if start>=end or start<=now():
        raise ValueError('Register experiment before its future start')
    fraction=float(data.get('treatment_fraction',.5))
    if not .05<=fraction<=.95:
        raise ValueError('Treatment fraction must be .05–.95')
    if data.get('unit_type') not in {'customer','geo_cluster','household_ip'}:
        raise ValueError('Unit must be customer, geo_cluster or household_ip')
    minimum=int(data.get('min_units_per_arm',100))
    if minimum<20:
        raise ValueError('Minimum is 20 independent units per arm')
    with store.db() as db:
        db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?)',
                   (tenant,ident(data['id']),start,end,fraction,secrets.token_hex(32),
                    data['unit_type'],str(data['hypothesis'])[:1000],minimum))
        store.audit(db,tenant,'agency','experiment.register',{'id':data['id'],'unit_type':data['unit_type']})
    return {'status':'registered','warning':'Campaign team must enforce assignment before exposure.'}

def enroll(store,tenant,experiment,unit):
    unit=ident(unit)
    with store.db() as db:
        e=db.execute('SELECT * FROM experiments WHERE tenant=? AND id=?',(tenant,experiment)).fetchone()
        if not e:
            raise ValueError('Unknown experiment')
        old=db.execute('SELECT arm FROM units WHERE tenant=? AND experiment=? AND unit=?',(tenant,experiment,unit)).fetchone()
        if old:
            return {'arm':old['arm'],'unit':unit}
        if now()>=e['start']:
            raise ValueError('Enroll all units before start; prevent outcome-dependent enrollment')
        number=int.from_bytes(hmac.new(e['salt'].encode(),unit.encode(),hashlib.sha256).digest()[:8],'big')/2**64
        arm='treatment' if number<e['fraction'] else 'control'
        db.execute('INSERT INTO units VALUES(?,?,?,?,?)',(tenant,experiment,unit,arm,now()))
    return {'unit':unit,'arm':arm}

def outcome(store,tenant,experiment,data):
    ts=stamp(data['ts'])
    with store.db() as db:
        e=db.execute('SELECT * FROM experiments WHERE tenant=? AND id=?',(tenant,experiment)).fetchone()
        if not e or not e['start']<=ts<e['end'] or ts>now():
            raise ValueError('Outcome outside experiment window or in future')
        unit=ident(data['unit'])
        if not db.execute('SELECT 1 FROM units WHERE tenant=? AND experiment=? AND unit=?',(tenant,experiment,unit)).fetchone():
            raise ValueError('Unit not enrolled')
        values=(tenant,experiment,ident(data['outcome_id']),unit,ts,money(data['revenue']))
        old=db.execute('SELECT * FROM outcomes WHERE tenant=? AND experiment=? AND outcome=?',values[:3]).fetchone()
        if old and tuple(old)!=values:
            raise ValueError('Conflicting outcome replay')
        db.execute('INSERT OR IGNORE INTO outcomes VALUES(?,?,?,?,?,?)',values)

def mean(xs):
    return sum(xs)/len(xs)

def percentile(xs,p):
    a=sorted(xs); n=(len(a)-1)*p; i=int(n)
    return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(n-i)

def analyze(store,tenant,experiment,incremental_media_cost=None,iterations=2000):
    with store.db() as db:
        e=db.execute('SELECT * FROM experiments WHERE tenant=? AND id=?',(tenant,experiment)).fetchone()
        if not e:
            raise ValueError('Unknown experiment')
        rows=db.execute('SELECT u.unit,u.arm,COALESCE(SUM(o.revenue),0)/100.0 AS revenue,COUNT(o.outcome) AS purchases FROM units u LEFT JOIN outcomes o ON u.tenant=o.tenant AND u.experiment=o.experiment AND u.unit=o.unit WHERE u.tenant=? AND u.experiment=? GROUP BY u.unit,u.arm ORDER BY u.unit',(tenant,experiment)).fetchall()
    treatment=[r['revenue'] for r in rows if r['arm']=='treatment']
    control=[r['revenue'] for r in rows if r['arm']=='control']
    nt,nc=len(treatment),len(control)
    result={'experiment':experiment,'unit_type':e['unit_type'],'treatment_units':nt,'control_units':nc,
            'status':'final' if now()>=e['end'] else 'in_progress',
            'method':'intention_to_treat; unit bootstrap 95% CI; Monte Carlo label permutation two-sided p',
            'exposure_enforcement':'external campaign suppression required; not verified by software'}
    if not nt or not nc:
        return {**result,'status':'insufficient_data'}
    expected=(nt+nc)*e['fraction']
    chi=(nt-expected)**2/expected+(nc-((nt+nc)-expected))**2/((nt+nc)-expected)
    srm=math.erfc(math.sqrt(chi/2))
    diff=mean(treatment)-mean(control)
    # Bounded O(n * iterations); v1 supports <=20k enrolled units for interactive analysis.
    if nt+nc>20000:
        raise ValueError('Use offline analysis for >20,000 units')
    rng=random.Random(1947)
    bootstrap=[]; extreme=0; combined=treatment+control
    for _ in range(iterations):
        bootstrap.append(mean(rng.choices(treatment,k=nt))-mean(rng.choices(control,k=nc)))
        rng.shuffle(combined)
        if abs(mean(combined[:nt])-mean(combined[nt:]))>=abs(diff)-1e-12:
            extreme+=1
    control_mean=mean(control)
    inc=diff*nt
    cost=money(incremental_media_cost)/100 if incremental_media_cost is not None else None
    tconv=sum(r['purchases']>0 for r in rows if r['arm']=='treatment')/nt
    cconv=sum(r['purchases']>0 for r in rows if r['arm']=='control')/nc
    warnings=[]
    if min(nt,nc)<e['min_units']:
        warnings.append('Below prespecified minimum sample size')
    if srm<.01:
        warnings.append('Sample ratio mismatch: investigate before interpretation')
    if result['status']!='final':
        warnings.append('Fixed horizon not reached; do not use interim p values for stopping')
    if e['unit_type']=='geo_cluster':
        warnings.append('Resampling unit is entire randomized geography; inspect size balance and spillover')
    if e['unit_type']=='household_ip':
        warnings.append('IP-defined network units can merge/split households; causal interpretation also requires stable comparable outcome matching in both arms')
    result.update(revenue_per_treatment_unit=mean(treatment),revenue_per_control_unit=control_mean,
                  revenue_lift_per_unit=diff,revenue_lift_95_ci=[percentile(bootstrap,.025),percentile(bootstrap,.975)],
                  relative_revenue_lift=diff/control_mean if control_mean else None,
                  incremental_revenue_treatment_population=inc,
                  conversion_rate_treatment=tconv,conversion_rate_control=cconv,
                  conversion_rate_difference=tconv-cconv,
                  p_value=(extreme+1)/(iterations+1),sample_ratio_p_value=srm,
                  incremental_media_cost=cost,incremental_roas=inc/cost if cost else None,
                  warnings=warnings,
                  interpretation='Causal interpretation requires enforced randomization, complete outcomes, no material spillover, and an appropriate prespecified sample size. Geo conversion rates mean share of geographies with any purchase.')
    return result

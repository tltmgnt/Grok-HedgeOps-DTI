#!/usr/bin/env python3
"""Fail-closed local TECT evidence-register checker; NOT a scientific truth oracle."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATES = ('GENERATED','UNVERIFIED','SUPPORTED','ADVERSARIAL_TEST','REPRODUCED','VALIDATED','STABLE','ASSURED','CONTESTED')
ATTACKS = {'source_poisoning','contradiction_injection','assumption_violation'}

def demand(ok, why):
    if not ok: raise ValueError(why)

def stamp(s):
    t=datetime.fromisoformat(s.replace('Z','+00:00'))
    demand(t.tzinfo is not None, 'timezone required')
    return t.astimezone(timezone.utc)

def check(r, root, now=None):
    now=now or datetime.now(timezone.utc)
    demand(r.get('schema_version')=='tect-evidence-v1', 'schema_version')
    demand(r.get('repository','').startswith('tltmgnt/'), 'repository')
    demand(r.get('canonical_tect')=={'repository':'tltmgnt/ResearchOs','runtime':'tect_runtime','version':'0.1.0'},'canonical TECT drift')
    demand(r.get('policy_version')=='1.0' and r.get('independent_reproduction_verified') is False and r.get('deployment_authorized') is False,'policy and external scope')
    claims=r.get('claims'); evidence=r.get('evidence'); reviews=r.get('reviews')
    demand(isinstance(claims,list) and claims and isinstance(evidence,list) and isinstance(reviews,list),'lists required')
    byid={}
    for c in claims:
        cid=c.get('id')
        demand(isinstance(cid,str) and cid and cid not in byid,'claim identity')
        demand(type(c.get('version')) is int and c['version']>0,'claim version')
        demand(all(isinstance(c.get(k),str) and c[k].strip() for k in ('statement','scope','source_ref','limitations')),'claim declaration')
        demand(isinstance(c.get('assumptions'),list) and c['assumptions'],'assumptions')
        demand(c.get('state') in STATES and c.get('deployment_authorized') is False,'state / authority')
        demand(isinstance(c.get('dependencies'),list),'dependencies')
        byid[cid]=c
    def walk(k, active):
        demand(k not in active,'dependency cycle')
        for d in byid[k]['dependencies']:
            demand(d in byid and d!=k,'invalid dependency')
            walk(d,active|{k})
    for k in byid: walk(k,set())
    bound={k:[] for k in byid}; ids=set()
    for e in evidence:
        key=e.get('id')
        demand(isinstance(key,str) and key and key not in ids,'evidence identity')
        ids.add(key)
        k=e.get('claim_id'); demand(k in byid and e.get('claim_version')==byid[k]['version'],'stale evidence version')
        demand(e.get('kind') in ('validation','reproduction','attack','contradiction') and e.get('result') in ('PASS','FAIL','UNCERTAIN'),'evidence outcome')
        demand(all(isinstance(e.get(f),str) and e[f].strip() for f in ('actor','source_id','method','group','scope','assumptions')),'provenance missing')
        demand(stamp(e['observed_at'])<=now<stamp(e['expires_at']),'expired/future evidence')
        name=e['artifact_path']; rel=Path(name)
        demand(not rel.is_absolute() and '..' not in rel.parts,'unsafe artifact path')
        path=(root/rel).resolve()
        demand(path.is_relative_to(root.resolve()) and path.is_file(),'artifact missing')
        demand(hashlib.sha256(path.read_bytes()).hexdigest()==e['sha256'],'artifact digest mismatch')
        if e['kind']=='attack': demand(e.get('attack_class') in ATTACKS,'attack class')
        bound[k].append(e)
    for review in reviews:
        k=review.get('claim_id')
        demand(k in byid and review.get('claim_version')==byid[k]['version'],'stale review')
        demand(review.get('policy_version')=='1.0','review policy drift')
        demand(isinstance(review.get('reviewer'),str) and review['reviewer'].strip(),'reviewer missing')
        demand(stamp(review['observed_at'])<=now<stamp(review['expires_at']),'expired review')
        path=Path(review['artifact_path'])
        demand(not path.is_absolute() and '..' not in path.parts,'review path')
        file=(root/path).resolve()
        demand(file.is_relative_to(root.resolve()) and file.is_file(),'review missing')
        demand(hashlib.sha256(file.read_bytes()).hexdigest()==review['sha256'],'review digest mismatch')
    summary=[]
    for c in claims:
        k=c['id']; s=c['state']; ev=bound[k]; blockers=[]
        v=[e for e in ev if e['kind']=='validation' and e['result']=='PASS']
        attacks={e['attack_class'] for e in ev if e['kind']=='attack' and e['result']=='PASS'}
        if s not in ('GENERATED','UNVERIFIED','CONTESTED'):
            if not v: blockers.append('NO_VALIDATION')
            if any(e['kind']=='contradiction' and e['result']=='PASS' for e in ev): blockers.append('UNRESOLVED_CONTRADICTION')
            if any(byid[d]['state'] not in ('SUPPORTED','ADVERSARIAL_TEST','REPRODUCED','VALIDATED','STABLE','ASSURED') for d in c['dependencies']): blockers.append('UNVERIFIED_DEPENDENCY')
        if s in ('ADVERSARIAL_TEST','REPRODUCED','VALIDATED','STABLE','ASSURED') and attacks!=ATTACKS: blockers.append('ATTACK_COVERAGE_MISSING')
        if s in ('REPRODUCED','VALIDATED','STABLE','ASSURED'):
            reps=[e for e in ev if e['kind']=='reproduction' and e['result']=='PASS']
            if not any(a['group']!=b['group'] and a['actor']!=b['actor'] and a['source_id']!=b['source_id'] and a['sha256']!=b['sha256'] for a in v for b in reps): blockers.append('SEPARATE_REPRODUCTION_MISSING')
        if s in ('VALIDATED','STABLE','ASSURED') and not any(x['claim_id']==k and x['claim_version']==c['version'] and x.get('decision')=='PASS' and x.get('scope')==c['scope'] for x in reviews): blockers.append('REVIEW_MISSING')
        if s in ('STABLE','ASSURED') and not any(e['kind']=='attack' and e['result']=='PASS' and type(e.get('distance')) in (float,int) and 0<=e['distance']<0.1 for e in ev): blockers.append('STABILITY_SCOPE_MISSING')
        if s=='ASSURED': blockers.append('EXTERNAL_AUTHORITY_NOT_AUTHENTICATED')
        demand(not blockers, 'unsafe promotion '+k+': '+','.join(blockers))
        summary.append({'claim_id':k,'declared_state':s,'evidence_count':len(ev)})
    return {'result':'REGISTER_CONSISTENT_NOT_ASSURED','repository':r['repository'],'claims':summary,
            'scientific_validity_established':False,'external_identity_authenticated':False,'deployment_authorized':False}

def selftest():
    import copy
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        root=Path(tmp); (root/'source').write_text('synthetic')
        c={'id':'test','version':1,'statement':'fictional','scope':'test','source_ref':'source','limitations':'no real data','assumptions':['synthetic'],'state':'UNVERIFIED','dependencies':[],'deployment_authorized':False}
        r={'schema_version':'tect-evidence-v1','repository':'tltmgnt/synthetic','canonical_tect':{'repository':'tltmgnt/ResearchOs','runtime':'tect_runtime','version':'0.1.0'},'policy_version':'1.0','independent_reproduction_verified':False,'deployment_authorized':False,'claims':[c],'evidence':[],'reviews':[]}
        assert check(r,root)['result']=='REGISTER_CONSISTENT_NOT_ASSURED'
        bad=copy.deepcopy(r); bad['claims'][0]['state']='SUPPORTED'
        try: check(bad,root); raise AssertionError('unsupported promotion accepted')
        except ValueError: pass
        bad=copy.deepcopy(r); bad['canonical_tect']['version']='9.0'
        try: check(bad,root); raise AssertionError('authority drift accepted')
        except ValueError: pass
        bad=copy.deepcopy(r); bad['claims'][0]['dependencies']=['test']
        try: check(bad,root); raise AssertionError('cycle accepted')
        except ValueError: pass
        bad=copy.deepcopy(r); bad['claims'][0]['state']='ASSURED'
        try: check(bad,root); raise AssertionError('ASSURED accepted')
        except ValueError: pass
    return 'synthetic conservative and negative controls passed'

if __name__=='__main__':
    try:
        if '--self-test' in sys.argv: print(selftest())
        else:
            root=Path(__file__).resolve().parent.parent
            p=root/'evidence_tect/register.json' if len(sys.argv)==1 else Path(sys.argv[1]).resolve()
            demand(p.is_relative_to(root),'register must be inside repository')
            print(json.dumps(check(json.loads(p.read_text(encoding='utf-8')),root),indent=2))
    except (ValueError,KeyError,TypeError,OSError,AssertionError) as exc:
        print('TECT EVIDENCE GATE FAILED:',exc,file=sys.stderr)
        sys.exit(2)

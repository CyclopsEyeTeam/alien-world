"""Bounded mathematical working conclusions, never semantic truth authority."""
from collections import OrderedDict,deque
import copy,hashlib,json,math,re
from world_clock import validate_stamp
from bearing import ownership

SCHEMA='ALIEN_YIELD_MATH'
EPS=1e-10
MAX_STREAMS=8
MAX_RECORDS=128
MAX_EVIDENCE=512
# Owner-approved 4 Nov 2026 warm start: per-recipe forecaster losses carried
# across opens. A prior only ranks experts for the mixture blend after each has
# scored a fresh real target; it never adds support, n or a conclusion.
PRIOR_ROUNDS=3
MAX_PRIORS=8
EXPERT=re.compile(r'(adaptive_mean|trend|harmonic|conditional|(lag|drift)([2-9]|1[0-6]))')

def unit(x):return max(0.,min(1.,x))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def finite(x):return type(x) in (int,float) and math.isfinite(x) and 0<=x<=1
def mse(a,b):return sum((x-y)**2 for x,y in zip(a,b))/len(a)
def signature(v):return ','.join(str(min(7,int(x*8))) for x in v)
def lower_bound(wins):
 n=len(wins)
 if not n:return 0.
 p=sum(wins)/n;z=1.96
 return (p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)

class PatternLearner:
 def __init__(self,state=None):
  self.streams=OrderedDict();self.recipes=OrderedDict();self.records=OrderedDict();self.evidence=OrderedDict()
  self.timeline=None;self.retired=deque(maxlen=64)
  self.counts=dict(observations=0,refused=0,unique_patterns=0,reinforced=0,established=0,revised=0)
  self.historical={};self.last_skill=0.;self.priors=OrderedDict();self.warm_blends=0
  if state is not None:self._restore(state)
 def _refuse(self):self.counts['refused']+=1;return dict(accepted=False,conclusions=[],prediction_error=None,baseline_error=None,prediction_skill=0.)
 def _new(self,source,names,epoch,scope):
  recipe_key=digest([source.split('|',1)[0],names]);recipe=self.recipes.get(recipe_key,{})
  size=len(names)
  return dict(source=source,names=names,epoch=epoch,scope=scope,recipe_key=recipe_key,n=0,tick=None,
   history=deque(maxlen=32),mean=[0.]*size,ewma=recipe.get('mean',[0.]*size)[:],cov=[[0.]*size for _ in names],
   transitions=OrderedDict(copy.deepcopy(recipe.get('transitions',[]))),models={},motifs=OrderedDict(),
   prior=dict(self.priors.get(recipe_key,{})))
 def _experts(self,s):
  h=s['history']
  if not h:return {}
  result={'persistence':h[-1],'mean':s['mean'][:],'adaptive_mean':s['ewma'][:]}
  if len(h)>=2:result['trend']=[unit(2*a-b) for a,b in zip(h[-1],h[-2])]
  if len(h)>=3:result['harmonic']=[unit(a-b+c) for a,b,c in zip(h[-1],h[-2],h[-3])]
  for lag in (2,4,8):
   if len(h)>=lag:result['lag'+str(lag)]=h[-lag]
  # Explore periods supported by two observed cycles inside the existing
  # 32-sample memory. Predictions are still scored only on the next real input;
  # each lag retains its own losses, so a broken rhythm can be revised.
  for lag in range(3,min(16,len(h)//2)+1):
   if lag not in (4,8):result['lag'+str(lag)]=h[-lag]
  # Seasonal drift: one period ago plus the level change over the last period,
  # so rising or falling rhythms are not mistaken for broken ones.
  for lag in range(2,min(16,(len(h)-1)//2)+1):
   result['drift'+str(lag)]=[unit(a+b-c) for a,b,c in zip(h[-lag],h[-1],h[-1-lag])]
  row=s['transitions'].get(signature(h[-1]))
  if row and row['n']>=2:result['conditional']=row['mean'][:]
  # Mixture: inverse-loss blend of the three experts with the best scored
  # record so far. Losses come only from earlier real targets.
  # Warm start: an expert with a prior from the last opening is eligible after
  # one fresh scored target, its loss shrunk toward the prior by PRIOR_ROUNDS
  # pseudo-rounds; experts without a prior still need four fresh rounds.
  prior=s.get('prior') or {}
  scored=sorted(((m['n']*m['loss']+PRIOR_ROUNDS*prior[name])/(m['n']+PRIOR_ROUNDS) if name in prior else m['loss'],name)
                for name,m in s['models'].items()
                if name in result and name!='mixture' and (m['n']>=4 or name in prior and m['n']>=1))[:3]
  if len(scored)>=2 and any(s['models'][name]['n']<4 for _,name in scored):self.warm_blends+=1
  s['blend']=[name for _,name in scored] if len(scored)>=2 else []
  if len(scored)>=2:
   weights=[1/(loss+1e-6) for loss,_ in scored];total=sum(weights)
   result['mixture']=[unit(sum(w*result[name][i] for w,(_,name) in zip(weights,scored))/total)
                      for i in range(len(h[-1]))]
  return result
 def _redundant(self,s,name,gain):
  """A new conclusion that only restates a simpler expert is not recorded.

  lagL/driftL repeating a shorter period that divides L, driftL that adds
  nothing to lagL, and a mixture that does not beat its own members would
  otherwise crowd other streams' conclusions out of the bounded queue.
  """
  def matched(other):
   m=s['models'].get(other)
   return m is not None and m['n']>=4 and m.get('skill',0.)>=gain-.02
  if name=='mixture':
   return any(s['models'].get(other,{}).get('skill',0.)>=gain for other in s.get('blend',()))
  for prefix in ('lag','drift'):
   if name.startswith(prefix) and name[len(prefix):].isdigit():
    period=int(name[len(prefix):])
    if any(period%d==0 and matched(prefix+str(d)) for d in range(2,period)):return True
    return prefix=='drift' and matched('lag'+str(period))
  return False
 def _record(self,s,family,parameter,support,quality,state,changes,**extra):
  ident=digest([s['scope'],s['source'],s['names'],family,parameter])[:24]
  old=self.records.get(ident)
  if old and old['state']=='established' and state!='established':state='revised'
  if old is None and state=='revised':return
  if old is None:self.counts['unique_patterns']+=1
  changed=old is None or state!=old['state'] or support>=max(4,old.get('_emitted_support',1)*2)
  value=dict(id=ident,source=s['source'],family=family,parameter=parameter,state=state,support=support,
   confidence=round(unit(quality),6),uncertainty=round(1-unit(quality),6),authority='unauthority',semantic_verification='unknown',
   world_stamp=copy.deepcopy(s['stamp']),source_epoch=s['epoch'],feature_names=s['names'][:],independent_outside_evidence=False,**extra)
  value.pop('control',None);value['owned']=ownership(state)
  value['_emitted_support']=support if changed else old.get('_emitted_support',support)
  self.records[ident]=value;self.records.move_to_end(ident)
  while len(self.records)>MAX_RECORDS:self.records.popitem(last=False)
  if changed:
   if state in ('reinforced','established','revised') and (old is None or old['state']!=state):self.counts[state]+=1
   changes.append({k:copy.deepcopy(v) for k,v in value.items() if not k.startswith('_')})
 def observe(self,source,epoch,features,stamp,evidence,eligible=True):
  stamp=validate_stamp(stamp)
  if (type(source) is not str or not 1<=len(source)<=96 or type(epoch) is not int or not 0<=epoch<2**64 or
      type(features) is not dict or not 1<=len(features)<=16 or type(evidence) is not str or not 1<=len(evidence)<=128 or eligible is not True or stamp is None):return self._refuse()
  if any(type(k) is not str or re.fullmatch(r'[a-z][a-z0-9_]{0,31}',k) is None or not finite(v) for k,v in features.items()):return self._refuse()
  timeline=(stamp['world_id'],stamp['segment_id'])
  if timeline!=self.timeline:
   if timeline in self.retired:return self._refuse()
   if self.timeline is not None:self.retired.append(self.timeline)
   self.timeline=timeline;self.streams.clear();self.records.clear()
  names=sorted(features);stream_key=(source,tuple(names))
  highest=max((row['epoch'] for row in self.streams.values() if row['source']==source),default=None)
  if highest is not None and epoch<highest:return self._refuse()
  if highest is not None and epoch>highest:
   for k,r in list(self.streams.items()):
    if r['source']==source:del self.streams[k]
   for k,r in list(self.records.items()):
    if r['source']==source:del self.records[k]
  s=self.streams.get(stream_key)
  scope=[*timeline,epoch]
  if s and epoch<s['epoch']:return self._refuse()
  if s and (epoch!=s['epoch']):
   for k,r in list(self.records.items()):
    if r['source']==source:del self.records[k]
   s=None
  evidence_key=digest([timeline,source,epoch,evidence])
  if evidence_key in self.evidence or s and stamp['tick']<=s['tick']:return self._refuse()
  if s is None:s=self._new(source,names,epoch,scope);self.streams[stream_key]=s
  self.streams.move_to_end(stream_key)
  while len(self.streams)>MAX_STREAMS:
   _,victim=self.streams.popitem(last=False);self._remember_recipe(victim)
   for k,r in list(self.records.items()):
    if r['source']==victim['source']:del self.records[k]
  values=[float(features[n]) for n in names];forecasts=self._experts(s);changes=[];error=baseline=None;best=None;skill=0.
  s['stamp']=copy.deepcopy(stamp)
  if forecasts:
   baseline=min(mse(forecasts['persistence'],values),mse(forecasts['mean'],values))
   for name,prediction in forecasts.items():
    if name in ('persistence','mean'):continue
    loss=mse(prediction,values);m=s['models'].setdefault(name,dict(n=0,loss=0.,baseline=0.,wins=deque(maxlen=32)))
    m['n']+=1;a=1. if m['n']==1 else .12
    m['loss']+=(loss-m['loss'])*a;m['baseline']+=(baseline-m['baseline'])*a;m['wins'].append(loss+1e-9<baseline)
    gain=unit(1-m['loss']/m['baseline']) if m['baseline']>EPS else 0.
    m['skill']=gain;m['bound']=lower_bound(m['wins'])
    if best is None or gain>skill:best=name;skill=gain;error=loss
    previous=next((r for r in self.records.values() if r['source']==source and r['family']=='prediction' and r['parameter']==name),None)
    if m['n']>=4 and (gain>.05 and not self._redundant(s,name,gain) or previous):
     state='established' if m['n']>=32 and gain>.2 and m['bound']>.5 else 'reinforced' if m['n']>=8 and gain>.15 else 'candidate'
     extra=dict(blend=s['blend'][:]) if name=='mixture' else {}
     self._record(s,'prediction',name,m['n'],gain*m['bound'],state,changes,skill=round(gain,6),win_lower_bound=round(m['bound'],6),prediction_error=loss,baseline_error=baseline,forecast_tick=s['tick'],**extra)
  # Update only after scoring old forecasts against this real target.
  s['stamp']=copy.deepcopy(stamp);s['tick']=stamp['tick'];s['n']+=1
  if forecasts:
   token=signature(s['history'][-1]);row=s['transitions'].get(token,dict(n=0,mean=[0.]*len(values)))
   row['n']+=1
   for i,x in enumerate(values):row['mean'][i]+=(x-row['mean'][i])/min(64,row['n'])
   s['transitions'][token]=row;s['transitions'].move_to_end(token)
   while len(s['transitions'])>64:s['transitions'].popitem(last=False)
  old=s['ewma'][:];a=1. if s['n']==1 else .08;delta=[v-m for v,m in zip(values,old)]
  for i,x in enumerate(values):
   s['mean'][i]+=(x-s['mean'][i])/s['n'];s['ewma'][i]+=a*delta[i]
   for j in range(len(values)):s['cov'][i][j]=(1-a)*(s['cov'][i][j]+a*delta[i]*delta[j])
  s['history'].append(values)
  token=signature(values);motif=s['motifs'].get(token,0)+1;s['motifs'][token]=motif;s['motifs'].move_to_end(token)
  while len(s['motifs'])>32:s['motifs'].popitem(last=False)
  recent=[signature(v) for v in s['history']]
  tracked={r['parameter'] for r in self.records.values() if r['source']==source and r['family']=='recurrence' and r['feature_names']==names}
  if motif>=2:tracked.add(token)
  for pattern in sorted(tracked):
   count=recent.count(pattern);ratio=count/len(recent)
   state='established' if count>=12 and ratio>=.2 else 'reinforced' if count>=4 else 'candidate' if count else 'revised'
   previous=next((r for r in self.records.values() if r['source']==source and r['family']=='recurrence' and r['parameter']==pattern and r['feature_names']==names),None)
   if previous and previous['state']=='revised' and count<=previous['support'] and state!='established':state='revised'
   self._record(s,'recurrence',pattern,count,count/(count+4),state,changes,frequency=round(ratio,6),lifetime_support=s['motifs'].get(pattern,0))
  if s['n']>=8:
   h=list(s['history']);stable=[]
   for i,name in enumerate(names):
    spread=max(v[i] for v in h)-min(v[i] for v in h)
    if spread<.025:stable.append((name,spread))
    old_record=next((r for r in self.records.values() if r['source']==source and r['family']=='stability' and r['parameter']==name),None)
    if spread<.025 or old_record:
     state='established' if s['n']>=24 and spread<.025 else 'reinforced' if spread<.025 else 'revised'
     self._record(s,'stability',name,s['n'],unit(1-spread),state,changes,spread=spread)
   relations=[]
   for i in range(len(names)):
    for j in range(i):
     variance=s['cov'][i][i]*s['cov'][j][j]
     r=max(-1.,min(1.,s['cov'][i][j]/math.sqrt(variance))) if variance>1e-10 else 0.
     parameter=names[j]+'~'+names[i]
     relations.append((abs(r),parameter,r,i,j))
   selected=sorted(relations,reverse=True)[:4]
   for strength,parameter,r,i,j in relations:
    prior=any(v['source']==source and v['family']=='relationship' and v['parameter']==parameter for v in self.records.values())
    if (strength>=.75 and (strength,parameter,r,i,j) in selected) or prior:
     varied=sum(abs(a[i]-b[i])>1e-6 and abs(a[j]-b[j])>1e-6 for a,b in zip(h,h[1:]))
     state='established' if varied>=16 and strength>=.9 else 'reinforced' if varied>=4 and strength>=.75 else 'candidate' if strength>=.75 else 'revised'
     self._record(s,'relationship',parameter,varied,strength*varied/(varied+4),state,changes,coefficient=r,slope=s['cov'][i][j]/max(EPS,s['cov'][j][j]),causation=False)
  self.evidence[evidence_key]=None
  while len(self.evidence)>MAX_EVIDENCE:self.evidence.popitem(last=False)
  self.counts['observations']+=1;self.last_skill=skill
  self._remember_recipe(s)
  return dict(accepted=True,conclusions=changes,prediction_error=error,baseline_error=baseline,prediction_skill=skill,novelty=1/(motif+1),observations=s['n'])
 def _remember_recipe(self,s):
  self.recipes[s['recipe_key']]=dict(source=s['source'].split('|',1)[0],names=s['names'][:],mean=s['ewma'][:],transitions=copy.deepcopy(list(s['transitions'].items())))
  self.recipes.move_to_end(s['recipe_key'])
  while len(self.recipes)>MAX_STREAMS:self.recipes.popitem(last=False)
  skill=sorted((m['loss'],name) for name,m in s['models'].items() if name!='mixture' and m['n']>=4 and EXPERT.fullmatch(name))[:MAX_PRIORS]
  if len(skill)>=2:
   self.priors[s['recipe_key']]={name:round(loss,9) for loss,name in skill};self.priors.move_to_end(s['recipe_key'])
  for key in [k for k in self.priors if k not in self.recipes]:del self.priors[key]
 def skill_snapshot(self):return dict(schema=SCHEMA,version=1,priors=[[k,sorted(v.items())] for k,v in self.priors.items()])
 def restore_skill(self,state):
  if type(state) is not dict or set(state)!={'schema','version','priors'} or state['schema']!=SCHEMA or type(state['version']) is not int or state['version']!=1 or type(state['priors']) is not list or len(state['priors'])>MAX_STREAMS:raise ValueError('invalid forecaster priors')
  priors=OrderedDict()
  for item in state['priors']:
   if type(item) not in (list,tuple) or len(item)!=2 or type(item[0]) is not str or item[0] not in self.recipes or item[0] in priors or type(item[1]) not in (list,tuple) or not 2<=len(item[1])<=MAX_PRIORS:raise ValueError('invalid forecaster prior')
   row={}
   for pair in item[1]:
    if type(pair) not in (list,tuple) or len(pair)!=2 or type(pair[0]) is not str or EXPERT.fullmatch(pair[0]) is None or pair[0] in row or not finite(pair[1]):raise ValueError('invalid forecaster loss')
    row[pair[0]]=float(pair[1])
   priors[item[0]]=row
  self.priors=priors
 def conclusions(self):return [{k:copy.deepcopy(v) for k,v in r.items() if not k.startswith('_')} for r in self.records.values()]
 def summary(self):return dict(self.counts,active_streams=len(self.streams),active_conclusions=len(self.records),recent_evidence=len(self.evidence),prediction_skill=self.last_skill,recipes=len(self.recipes),warm_priors=len(self.priors),warm_blends=self.warm_blends)
 def snapshot(self):return dict(schema=SCHEMA,version=1,recipes=copy.deepcopy(list(self.recipes.items())),historical={k:self.historical.get(k,0)+v for k,v in self.counts.items()})
 def _restore(self,state):
  if type(state) is not dict or set(state)!={'schema','version','recipes','historical'} or state['schema']!=SCHEMA or type(state['version']) is not int or state['version']!=1:raise ValueError('unsupported yielding learner state')
  recipes=state['recipes'];historical=state['historical']
  if type(recipes) is not list or len(recipes)>MAX_STREAMS or type(historical) is not dict or set(historical)!=set(self.counts) or any(type(v) is not int or not 0<=v<2**63 for v in historical.values()):raise ValueError('invalid yielding bounds')
  for item in recipes:
   if type(item) not in (list,tuple) or len(item)!=2:raise ValueError('invalid recipe')
   ident,r=item
   if type(ident) is not str or type(r) is not dict or set(r)!={'source','names','mean','transitions'}:raise ValueError('invalid recipe')
   names=r['names'];mean=r['mean'];rows=r['transitions']
   if type(r['source']) is not str or not 1<=len(r['source'])<=96 or type(names) is not list or not 1<=len(names)<=16 or any(type(n) is not str or re.fullmatch(r'[a-z][a-z0-9_]{0,31}',n) is None for n in names) or names!=sorted(set(names)):raise ValueError('invalid recipe feature names')
   if ident!=digest([r['source'],names]) or ident in self.recipes or type(mean) is not list or len(mean)!=len(names) or not all(finite(v) for v in mean) or type(rows) is not list or len(rows)>64:raise ValueError('invalid recipe values')
   seen=set()
   for entry in rows:
    if type(entry) not in (list,tuple) or len(entry)!=2:raise ValueError('invalid transition')
    token,row=entry
    if type(token) is not str or len(token)>32 or len(token.split(','))!=len(names) or any(v not in '01234567' or len(v)!=1 for v in token.split(',')) or token in seen:raise ValueError('invalid transition key')
    if type(row) is not dict or set(row)!={'n','mean'} or type(row['n']) is not int or not 1<=row['n']<2**63 or type(row['mean']) is not list or len(row['mean'])!=len(names) or not all(finite(v) for v in row['mean']):raise ValueError('invalid transition values')
    seen.add(token)
   self.recipes[ident]=copy.deepcopy(r)
  self.historical=dict(historical)

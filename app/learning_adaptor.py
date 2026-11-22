"""Turn measured mathematical patterns into material Alien can encounter itself.

RAM formulations are provisional. A yielded conclusion waits for its real
archive acknowledgement and enters the existing unauthority/mirror pathway.
"""
import asyncio,copy,hashlib,math
from collections import OrderedDict
from yield_math import PatternLearner,digest
from bearing import created_claim,ownership,obtained
from world_clock import validate_stamp,tick_distance
from temporal_rift import TemporalFlow
from content_cache import CacheBusy

STATES={'candidate':1,'reinforced':2,'established':3,'revised':4}
CROSSING_REASONS=('published','no_anchor','no_peer','paused','settling','narrowed','source_expired','preference_withdrawn','gain_disabled','obsolete','archive_refused','archive_failed','cancelled')

class LearningAdaptor:
 def __init__(self,cache,clock,runtime,archive=None,math_events=(),sensory_validator=None,source_validator=None):
  self.cache=cache;self.archive=archive or cache;self.clock=clock;self.runtime=runtime
  self.math_events=tuple(math_events);self.sensory_validator=sensory_validator;self.source_validator=source_validator
  self.alphabet=None
  self.rift=None
  self.crossing_counts=dict(attempts=0,**{reason:0 for reason in CROSSING_REASONS})
  self._crossing_token=None;self._crossing_selection=None
  self.temporal_rejected=0
  try:self.temporal=TemporalFlow(self.archive.get_json('learning.temporal.flow','v1'))
  except (OSError,ValueError,TypeError,KeyError):self.temporal=TemporalFlow();self.temporal_rejected=1
  self.bus=None;self.loop=None;self.pending=OrderedDict();self.inflight=None;self.last_yield=None;self.last_novelty=0.
  self.closed=False;self.sleeping=False;self.dreaming=False;self.load_high=False;self.family_use={};self.source_use={}
  self.counts=dict(yielded=0,reinforced=0,established=0,revised=0,coalesced=0,discarded=0,
   deferred_load=0,deferred_sleep=0,deferred_dream=0,deferred_closed=0,archive_refused=0,archive_failed=0,checkpoint_busy=0,checkpoint_io_failed=0,checkpoint_invalid=0,durable_committed=0,obsolete=0,deferred=0,state_rejected=0,alphabet_written_yields=0,bearing_refused=0,curious_yields=0)
  try:self.model=PatternLearner(self.archive.get_json('learning.yield.model','v1'))
  except (OSError,ValueError,TypeError,KeyError):self.model=PatternLearner();self.counts['state_rejected']+=1
  else:
   # Separate key: an earlier release reading the model state is unaffected.
   # Priors belong to restored recipes, so they are read only after those.
   try:
    priors=self.archive.get_json('learning.yield.skill','v1')
    if priors is not None:self.model.restore_skill(priors)
   except (OSError,ValueError,TypeError,KeyError):self.model.priors.clear();self.counts['state_rejected']+=1
 def _bind(self,bus):
  self.bus=bus
  try:self.loop=asyncio.get_running_loop()
  except RuntimeError:pass
 def _allowed(self):return not (self.closed or self.sleeping or self.dreaming or self.load_high)
 def _observe(self,source,epoch,features,stamp,evidence,scope='self',paced=False):
  # Only the service's already validated, currently owned alphabet computation
  # has this bounded load lane. Every other observation retains the old gate.
  paced=(paced is True and self.alphabet is not None and type(source) is str and source.startswith('native.alphabet.') and
         self.alphabet.source_active(dict(source=source,source_epoch=epoch,world_stamp=stamp)))
  if not self._allowed() and not (paced and not (self.closed or self.sleeping or self.dreaming)):
   self.counts['deferred']+=1;reason='closed' if self.closed else 'load' if self.load_high else 'sleep' if self.sleeping else 'dream'
   self.counts['deferred_'+reason]+=1;return False
  result=self.model.observe(source,epoch,features,stamp,evidence)
  if not result['accepted']:return False
  self.temporal.observe(source,epoch,features,stamp,evidence)
  self.temporal.prune(stamp,self.source_validator)
  self.last_novelty=result['novelty']
  for ident,row in list(self.pending.items()):
   if not self._active(row):del self.pending[ident];self.counts['obsolete']+=1
  for row in result['conclusions']:
   row=dict(row,source_scope=scope)
   if row['id'] in self.pending:self.counts['coalesced']+=1
   self.pending[row['id']]=row;self.pending.move_to_end(row['id'])
   if len(self.pending)>16:
    families={r['family']:sum(v['family']==r['family'] for v in self.pending.values()) for r in self.pending.values()}
    choices=[k for k,r in self.pending.items() if families[r['family']]>1]
    victim=min(choices,key=lambda k:(STATES[self.pending[k]['state']],self.pending[k]['confidence']))
    del self.pending[victim];self.counts['discarded']+=1
  if self.model.counts['observations']%32==0:self.checkpoint()
  return True
 def on_event(self,name,body,bus):
  if self.closed:return
  if created_claim(body):
   self.counts['bearing_refused']+=1;return
  self._bind(bus)
  if name=='shutdown':self.close();return
  # Owner-approved 3 Nov 2026: native load reads high whenever ticks are a
  # little late, while learning costs almost no CPU. Shed only at native
  # level 2 (ticks over 1.85x late); a load body without a level still sheds.
  if name=='load':self.load_high=bool(body.get('high')) and (body.get('level') is None or body.get('level')>=2);return
  if name=='enter_sleep':self.sleeping=True;self.temporal.prune(None);return
  if name=='wake':self.sleeping=False;return
  if name=='dream_begin':self.dreaming=True;self.temporal.prune(None);return
  if name=='dream_end':self.dreaming=False;return
  if name=='tick':self.drain(bus);return
  if body.get('derived_learning') or body.get('dream') or body.get('dreamed') or body.get('replayed'):return
  if ('alphabet' in body or str(body.get('source','')).startswith('native.alphabet.') or
      body.get('constant')=='alphabet' or body.get('focus')=='alphabet'):
   # A malformed or forged representation cannot fall through and become an
   # apparently ordinary native.math.material observation.
   measurement=self.alphabet.measurement(body) if self.alphabet is not None and name=='numeric_pattern' else None
   if measurement is not None:
    self._observe(measurement['source'],measurement['epoch'],measurement['features'],measurement['stamp'],measurement['evidence'],'self',paced=True)
   return
  stamp=self.clock.stamp()
  if stamp is None:return
  features={};source=None
  if name=='frame_stats':
   for key in ('entropy','color_var'):
    value=body.get(key)
    if type(value) in (int,float) and math.isfinite(value) and 0<=value<=(1.5 if key=='color_var' else 1.):features[key]=value/(1.5 if key=='color_var' else 1.)
   source='native.field'
  elif name in self.math_events:
   value=body.get('log')
   if type(value) in (int,float) and math.isfinite(value):features['log_scale']=.5+math.atan(value)/math.pi
   value=body.get('scale')
   if type(value) in (int,float) and math.isfinite(value) and 0<=value<=1:features['scale']=float(value)
   focus=body.get('focus');source='native.math.'+(focus if focus in ('pi','prime','scale','fraction','irrational','phi') else 'material')
   number=body.get('prime' if focus=='prime' else 'walk')
   if type(number) is int and abs(number)<=10**12:
    features['cursor_mod2']=(number%2)
    features['cursor_mod3']=(number%3)/2
    features['cursor_mod5']=(number%5)/4
    phase=math.tau*((number%256)/256)
    features['cursor_sin']=(math.sin(phase)+1)/2
    features['cursor_cos']=(math.cos(phase)+1)/2
  if features and source:self._observe(source,0,features,stamp,digest([name,stamp,features]))
 def accept_sensory(self,row):
  """This entrance requires the existing registry's *completed* training gate."""
  if not callable(self.sensory_validator) or not self.sensory_validator(row):return False
  if type(row) is not dict or row.get('dreamed') or row.get('replayed'):return False
  meta=row.get('neural',{})
  if meta.get('dreamed') or meta.get('expression_ids') or not row.get('eligible',{}).get('cache'):return False
  vision=row.get('vision',{});source=vision.get('source');runtime=vision.get('eye_runtime');epoch=vision.get('epoch')
  if source not in ('own_display','art','desktop') or type(runtime) is not str:return False
  from neural_types import FEATURE_NAMES
  features={k:v for k,v in row.get('features',{}).items() if k in FEATURE_NAMES}
  return self._observe('eye.'+source+'|'+runtime,epoch,features,row.get('grounding',{}).get('stamp'),row.get('id',''),'mixed_unknown' if source=='desktop' else 'self')
 def _active(self,row):
  current=self.model.records.get(row['id'])
  if current is None or current['source_epoch']!=row['source_epoch'] or current['feature_names']!=row['feature_names']:return False
  try:return self.source_validator is None or bool(self.source_validator(row))
  except (ValueError,KeyError,TypeError):return False
 def variation(self):
  if not self.model.counts['observations']:return None
  return dict(temperature=.8+.7*(1-self.model.last_skill)+.25*self.last_novelty+.15*self.temporal.variation(),novelty=self.last_novelty,phase=self.model.counts['unique_patterns']+3*self.counts['yielded'])
 def _dispatch(self,callback):
  if self.closed:return
  if self.loop is not None:
   if self.loop.is_closed():return
   self.loop.call_soon_threadsafe(callback)
  else:callback()
 def _crossing_begin(self,token,selection):
  self.crossing_counts['attempts']+=1;self._crossing_token=token;self._crossing_selection=selection
 def _crossing_finish(self,token,reason):
  if self._crossing_token is not token:return
  self.crossing_counts[reason]+=1;self._crossing_token=None;self._crossing_selection=None
 def drain(self,bus=None):
  if bus is not None:self._bind(bus)
  stamp=self.clock.stamp()
  self.temporal.prune(stamp,self.source_validator)
  spacing=16 if self.load_high else 4
  if self.closed or self.sleeping or self.dreaming or self.bus is None or self.inflight or not self.pending or stamp is None or (self.last_yield is not None and tick_distance(self.last_yield,stamp) is not None and tick_distance(self.last_yield,stamp)<spacing):return
  # Old contexts are history; they cannot claim fresh establishment now.
  for ident,row in list(self.pending.items()):
   if tick_distance(row['world_stamp'],stamp) is None or not self._active(row):del self.pending[ident];self.counts['obsolete']+=1
  eligible=[k for k,row in self.pending.items() if not self.load_high or row['source'].startswith('native.alphabet.')]
  if not eligible:return
  ident=max(eligible,key=lambda k:(STATES[self.pending[k]['state']]+.5*self.pending[k]['confidence']+.05*math.log1p(self.pending[k]['support'])+.1*self.temporal.affinity(self.pending[k])+(self.rift.bias(self.pending[k]) if self.rift is not None else 0.))/self._use_divisor(self.pending[k]))
  # Noise can meet an older pending conclusion. The salt is not stored, does not
  # read the archive, and does not move rift pressure, marks, or peer choice.
  if len(eligible)>=3 and self._passive_encounter():ident=eligible[self._encounter_salt(stamp)%len(eligible)]
  row=copy.deepcopy(self.pending[ident]);token=object();temporal=self.temporal.context(row)
  self._crossing_begin(token,self.temporal.selection_reason(temporal))
  try:
   ref=self.cache.append('learning.yield.conclusion',dict(schema='ALIEN_YIELDED_CONCLUSION_V1',runtime=self.runtime,conclusion=row,temporal=temporal))
   self.inflight=(token,row,ref,self.bus,temporal)
   def succeeded():self._dispatch(lambda:self._ack(token))
   def failed(_error):self._dispatch(lambda:self._failed(token))
   if getattr(self.cache,'background_writer',False):self.cache.after_flush(succeeded,failed)
   else:self.cache.flush();succeeded()
  except (OSError,ValueError):
   self.inflight=None;self.counts['archive_refused']+=1;self._crossing_finish(token,'archive_refused')
 def _failed(self,token):
  if self.inflight and self.inflight[0] is token:
   self.inflight=None;self.counts['archive_failed']+=1;self._crossing_finish(token,'archive_failed')
 def _ack(self,token):
  if self.closed or not self.inflight or self.inflight[0] is not token:return
  _,row,ref,bus,temporal=self.inflight;self.inflight=None;self.counts['durable_committed']+=1
  current=self.clock.stamp();latest=self.pending.get(row['id'])
  obsolete=latest!=row or tick_distance(row['world_stamp'],current) is None or self.bus is not bus
  active=not obsolete and self._active(row)
  if obsolete or not active:
   if latest==row:self.pending.pop(row['id'],None)
   self.counts['obsolete']+=1
   reason='obsolete' if obsolete else 'paused' if self.sleeping or self.dreaming else 'source_expired'
   self._crossing_finish(token,reason);return
  self.pending.pop(row['id'],None);self.last_yield=copy.deepcopy(current)
  text=self._text(row)
  reason=self.temporal.assessment(temporal,current,self.source_validator)
  if not temporal['paths']['lateral'] and self._crossing_selection is not None:reason=self._crossing_selection
  crossing=reason is None
  if crossing:text+=' ↔'+str(len(temporal['paths']['lateral']))
  locus=hashlib.sha256((row['id']+(':'+temporal['paths']['lateral'][0]['node']['id'] if crossing else '')).encode()).digest()
  fx=round(.12+.76*(int.from_bytes(locus[:4],'big')/0xffffffff),6)
  fy=round(.12+.76*(int.from_bytes(locus[4:8],'big')/0xffffffff),6)
  payload=dict(text=text,label='yielded '+row['family'],authority='unauthority',semantic_verification='unknown',
   derived_learning=True,independent_outside_evidence=False,learning_ref=ref,conclusion=row,
   world_stamp=copy.deepcopy(row['world_stamp']),source='alien.learning',confidence=0.,
   x=fx,y=fy,
   progression=dict(learning=row.get('skill',0.),growth=.5 if row['state']=='candidate' else 1.,formulation=1.,understanding=row.get('skill',0.)),
   owned=ownership(row.get('state')),control=obtained())
  # One established pipeline receives it; no new root/register doorway exists.
  if crossing:
   payload['temporal']=temporal;self.temporal.committed(temporal)
   bus.publish('temporal_rift',dict(payload));self._crossing_finish(token,'published')
   if self.rift is not None:self.rift.feedback(row,temporal,bus)
  else:self._crossing_finish(token,reason)
  bus.publish('learning_conclusion',dict(payload));bus.publish('residue',dict(payload))
  # A scalar receipt of an actually published, durable alphabet conclusion or
  # usable alphabet crossing, never a count of provisional RAM formulations.
  if row['source'].startswith('native.alphabet.') or crossing and any(path['node']['source'].startswith('native.alphabet.') for path in temporal['paths']['lateral']):self.counts['alphabet_written_yields']+=1
  self.counts['yielded']+=1
  for family in self.family_use:self.family_use[family]*=.8
  self.family_use[row['family']]=self.family_use.get(row['family'],0.)+1.
  if self.source_use.get(row['source'],0.)<.5:self.counts['curious_yields']+=1
  for source in self.source_use:self.source_use[source]*=.8
  self.source_use[row['source']]=self.source_use.get(row['source'],0.)+1.
  if len(self.source_use)>16:del self.source_use[min(self.source_use,key=self.source_use.get)]
  if row['state'] in ('reinforced','established','revised'):self.counts[row['state']]+=1
 def _use_divisor(self,row):
  # Curious expression (owner-approved 3 Nov 2026): recently expressed
  # families and source streams both fade, so a wider spread is yielded.
  return 1+self.family_use.get(row['family'],0.)+self.source_use.get(row['source'],0.)
 def _passive_encounter(self):
  rift=self.rift
  return rift is not None and rift.passive_now()
 def _encounter_salt(self,stamp):
  node=''
  for item in reversed(self.temporal.nodes.values()):
   if item.get('live'):node=item['id'];break
  pi=stamp['pi']
  material=f"{stamp['world_id']}|{stamp['segment_id']}|{stamp['tick']}|{stamp['slot']}|{pi[0]}|{pi[1]}|{node}"
  return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8],'big')
 def _text(self,row):
  p=row['parameter'];support=row['support'];state=row['state']
  if row.get('blend'):p+='('+'+'.join(row['blend'])+')'
  if row['family']=='prediction':return f"{p} Δ²={row['prediction_error']:.4g} / {row['baseline_error']:.4g} ×{support} {state}"
  if row['family']=='relationship':return f"{p.replace('~','↔')} r={row['coefficient']:.3g} ×{support} {state}"
  if row['family']=='stability':return f"{p} Δ={row['spread']:.3g} ×{support} {state}"
  return f"{p} ↻{support} {state}"
 def checkpoint(self):
  try:self.archive.set_json('learning.yield.model','v1',self.model.snapshot())
  except (OSError,ValueError) as error:self._checkpoint_failed(error)
  try:self.archive.set_json('learning.temporal.flow','v1',self.temporal.snapshot())
  except (OSError,ValueError) as error:self._checkpoint_failed(error)
  try:self.archive.set_json('learning.yield.skill','v1',self.model.skill_snapshot())
  except (OSError,ValueError) as error:self._checkpoint_failed(error)
 def _checkpoint_failed(self,error):
  self.counts['archive_failed']+=1
  category='busy' if isinstance(error,CacheBusy) else 'io_failed' if isinstance(error,OSError) else 'invalid'
  self.counts['checkpoint_'+category]+=1
 def summary(self):
  s=self.model.summary();s['computed_establishments']=s.pop('established');s['computed_revisions']=s.pop('revised');s.pop('reinforced')
  s['working_established']=sum(r['state']=='established' for r in self.model.records.values());s['working_revised']=sum(r['state']=='revised' for r in self.model.records.values())
  s.update({'temporal_'+k:v for k,v in self.temporal.summary().items()});s['temporal_state_rejected']=self.temporal_rejected
  if self.rift is not None:s.update({'rift_'+k:v for k,v in self.rift.summary().items()})
  s.update({'crossing_'+k:v for k,v in self.crossing_counts.items()});s['crossing_inflight']=int(self._crossing_token is not None)
  import spark_rift
  if spark_rift.ACTIVE is not None:s.update({'spark_'+k:v for k,v in spark_rift.ACTIVE.summary().items()})
  if self.alphabet is not None:
   s.update({'alphabet_'+k:v for k,v in self.alphabet.summary().items() if type(v) in (int,float,bool)})
  return dict(s,**self.counts,pending=len(self.pending),inflight=int(self.inflight is not None),closed=self.closed,sleeping=self.sleeping,dreaming=self.dreaming,load_high=self.load_high)
 def close(self):
  if self.closed:return
  if self._crossing_token is not None:self._crossing_finish(self._crossing_token,'cancelled')
  if self.rift is not None:self.rift.close()
  self.temporal.prune(None);self.checkpoint();self.closed=True;self.pending.clear();self.inflight=None

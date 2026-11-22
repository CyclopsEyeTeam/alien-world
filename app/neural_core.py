"""A grounded electrical organ on the existing hive clock and source contracts."""
import asyncio,copy,json,math,uuid
from collections import OrderedDict,deque
from content_cache import ContentCache
from world_clock import validate_stamp,tick_distance
from vision_origin import validate_vision
from neural_types import FEATURE_NAMES,digest,number,validate_expression,validate_presented,validate_sensory
from neural_model import NeuralField

def bounded(rows,limit):
 while len(rows)>limit:rows.popitem(last=False)
def unit(value):return max(0.,min(1.,float(value)))
def finite(value,default=0.):
 return float(value) if type(value) in (int,float) and math.isfinite(value) else default

class NeuralSystem:
 def __init__(self,ns,hub,cache):
  self.ns=ns;self.hub=hub;self.cache=cache;self.bus=None;self.supervisor=None
  self.archive=cache.namespace('0'*32) if getattr(cache,'background_writer',False) else ContentCache(cache.path,'0'*32)
  self.model=NeuralField(self.archive.get_json('neural.model','v1'))
  self.raw=OrderedDict();self.situated=OrderedDict();self.source_last=OrderedDict();self.similar=OrderedDict();self.active_eye_runtime=None;self.retired_eye=OrderedDict()
  self.pending_mirrors=OrderedDict();self.mirror_receipts=OrderedDict();self.approbations=OrderedDict();self.confirmed=OrderedDict()
  self.trace_reservations=OrderedDict();self.root_writers=[]
  self.outputs=OrderedDict();self.presentations=OrderedDict();self.trained=OrderedDict();self.mirror_history=deque(maxlen=8);self.marks=deque(maxlen=16);self.chain=[]
  self.continuity='';self.load=dict(known=False,level=0,high=False);self.optional_high=False;self.optional_until=0;self.sleeping=False;self.dreaming=False;self.serial=0
  self.stamp=hub.clock.stamp();self.segment=None;self.recent_spikes=deque(maxlen=256);self.last_output=-1000;self.last_gain=OrderedDict();self.learned=0;self.last_stats={};self.last_mirrored_region=None
 def clock(self):return self.hub.clock.stamp()
 def register_eye(self,nonce):
  from neural_types import uuid as valid_uuid
  valid_uuid(nonce)
  if nonce in self.retired_eye or self.active_eye_runtime not in (None,nonce):return False
  self.active_eye_runtime=nonce;return True
 def retire_eye(self,nonce):
  from neural_types import uuid as valid_uuid
  valid_uuid(nonce);self.retired_eye[nonce]=True;bounded(self.retired_eye,64)
  if self.active_eye_runtime==nonce:self.active_eye_runtime=None
  return True
 def _active(self,vision):
  key=(vision['source'],vision['eye_runtime']);last=self.source_last.get(key)
  return vision['eye_runtime']==self.active_eye_runtime and vision['eye_runtime'] not in self.retired_eye and last is not None and last[0]==vision['epoch']
 def learning_source_active(self,source,eye_runtime,epoch):
  return self._active(dict(source=source,eye_runtime=eye_runtime,epoch=epoch))
 def gain(self):
  if self.supervisor is not None and 'neural_gain' in self.ns['GENE_NAMES']:return unit(self.supervisor.genome.g('neural_gain'))
  return .5
 def observe(self,name,body):
  self.serial+=1;stamp=self.clock()
  if name=='tick':
   segment=None if stamp is None else (stamp['world_id'],stamp['segment_id'])
   if segment!=self.segment:
    self.raw.clear();self.situated.clear();self.source_last.clear();self.similar.clear();self.pending_mirrors.clear();self.mirror_receipts.clear();self.approbations.clear();self.outputs.clear();self.presentations.clear();self.recent_spikes.clear();self.last_gain.clear();self.model.reset_temporal();self.segment=segment
   self.stamp=stamp
   if stamp and stamp['tick']>=self.optional_until:self.optional_high=False
   mark=str(body.get('continuity') or '').lower()
   if len(mark)==6 and all(c in '0123456789abcdef' for c in mark):self.continuity=mark
   try:self.archive.flush_if_due()
   except OSError as error:self.storage_error=type(error).__name__+': '+str(error)[:160]
  elif name=='load':self.load=dict(known=True,level=max(0,min(3,int(body.get('level') or 0))),high=bool(body.get('high')))
  elif name=='neural_optional_load':
   self.optional_high=bool(body.get('high'));self.optional_until=max(0,int(body.get('expires_tick') or 0))
  elif name=='enter_sleep':self.sleeping=True
  elif name=='wake':self.sleeping=False
  elif name=='dream_begin':self.dreaming=True
  elif name=='dream_end':self.dreaming=False
  elif name in ('chain_extended','attraction_rise','chain_peak','chain_broken'):
   if name=='chain_broken':self.chain=[]
   else:
    ref=str(body.get('ref') or '')[:40];row=dict(ref=ref,pull=unit(finite(body.get('pull'))),held=unit(finite(body.get('held'))))
    self.chain=[x for x in self.chain if x['ref']!=ref]+[row];self.chain=self.chain[-8:]
  elif name=='mirror_truth':
   self.mirror_history.append(digest(dict(ref=str(body.get('ref',''))[:40],text=str(body.get('text',''))[:80]))[:16])
   ref=body.get('ref');candidate=self.pending_mirrors.get(ref);meta=body.get('neural')
   if candidate and body.get('mirror') is True and isinstance(meta,dict) and meta==self.metadata(candidate['id']) and self.can_promote(candidate,'root'):
    self.mirror_receipts[ref]=dict(id=candidate['id'],serial=self.serial,stamp=copy.deepcopy(stamp));bounded(self.mirror_receipts,128)
    self.last_mirrored_region=copy.deepcopy(candidate['region'])
  elif name=='approbation_marked':
   ref=body.get('ref');held=unit(finite(body.get('held')))
   self.marks.append(dict(ref=str(ref or '')[:40],held=held,stamp=copy.deepcopy(stamp)))
   mirror=self.mirror_receipts.get(ref)
   if mirror and self.serial>mirror['serial'] and held>=float(self.ns.get('ROOT_HELD',.55)):
    self.approbations[ref]=dict(held=held,serial=self.serial,stamp=copy.deepcopy(stamp));bounded(self.approbations,128)
 def _features(self,summary):
  field=summary.get('field') or {};cues=summary.get('neural') or {};out={}
  for name in FEATURE_NAMES:
   # Native field defaults do not establish a measured temporal baseline.
   value=cues.get(name) if name in ('change','motion_energy','flicker_density','persistence','dwell') else cues.get(name,field.get(name))
   if type(value) in (int,float) and math.isfinite(value):out[name]=unit(value)
  hue=cues.get('dominant_hue')
  if hue is None and finite(field.get('saturation'))>.05:hue=field.get('hue')
  if type(hue) in (int,float) and math.isfinite(hue):
   out['hue_sin']=(math.sin(2*math.pi*hue)+1)/2;out['hue_cos']=(math.cos(2*math.pi*hue)+1)/2
  attention=summary.get('attention') or {}
  for dest,source in (('attention_x','x'),('attention_y','y'),('attention_strength','strength')):
   if dest not in out and type(attention.get(source)) in (int,float):out[dest]=unit(attention[source])
  return out
 def ingest(self,body):
  stamp=validate_stamp(body.get('world_stamp'));current=self.clock()
  if stamp is None or current is None or tick_distance(stamp,current) is None or stamp['tick']>current['tick'] or current['tick']-stamp['tick']>64:return []
  vision=validate_vision(body.get('vision'))
  if vision['runtime']!=self.hub.runtime or vision['world_id']!=current['world_id']:return []
  if not self.register_eye(vision['eye_runtime']):return []
  sensory=validate_sensory(body.get('sensory'),vision['source']);key=(vision['source'],vision['eye_runtime']);last=self.source_last.get(key)
  if last and (vision['epoch']<last[0] or vision['sequence']<=last[1]):return []
  self.source_last[key]=(vision['epoch'],vision['sequence']);bounded(self.source_last,16)
  try:summary=json.loads(body.get('text',''))
  except (ValueError,TypeError):return []
  if not isinstance(summary,dict):return []
  features=self._features(summary)
  if not features:return []
  region=dict(x=features.get('attention_x',.5),y=features.get('attention_y',.5))
  identity=digest(dict(vision=vision,stamp=stamp,sensory=sensory))[:32]
  raw=dict(id=identity,vision=vision,features=features,region=region,sensory=sensory,world_stamp=stamp,source_receipt=body.get('context_ref'),authority='unauthority',semantic_verification='unknown',dreamed=False)
  self.raw[identity]=copy.deepcopy(raw);bounded(self.raw,256);self.recent_spikes.append(stamp['tick']);return [raw]
 def ground(self,raw,genome):
  raw={k:v for k,v in raw.items() if k not in ('context_ref','receipt_context_ref')} if isinstance(raw,dict) else raw
  ident=raw.get('id') if isinstance(raw,dict) else None;stored=self.raw.get(ident)
  if stored is None or stored!=raw:return None
  if not self._active(raw['vision']):return None
  current=self.clock();stamp=raw['world_stamp'];window=4+round(60*unit(genome.g('grounding_window')))
  same=tick_distance(current,stamp)
  if same is None or current['tick']<stamp['tick'] or same>window:return None
  features=dict(raw['features']);vision=raw['vision'];source_key=(vision['source'],vision['eye_runtime'],vision['epoch'])
  signature=digest(dict(source=source_key,region=[round(raw['region']['x']*8),round(raw['region']['y']*8)],features={k:round(v*8) for k,v in features.items() if k!='dwell'}))[:24]
  old=self.similar.get(signature);span=None if old is None else tick_distance(old,stamp)
  self.similar[signature]=copy.deepcopy(stamp);bounded(self.similar,256)
  if span is not None and 0<span<=window:features['dwell']=unit(span/max(1,window))
  quality=(.45 if len(self.continuity)==6 else 0.)+(.2 if self.load['known'] else 0.)+.2*(len(features)/len(FEATURE_NAMES))
  if span is not None and 0<span<=window:quality+=.15
  clarity=sum(features.get(k,0.) for k in ('persistence','colour_dominance','contrast','saturation'))/4
  dreamed=bool(raw.get('dreamed'));reafferent=bool(raw['sensory']['expression_ids'])
  gain=unit(genome.g('neural_gain'))
  threshold=.45+.3*unit(genome.g('grounding_strictness'))-.1*(gain-.5);situated=quality>=threshold
  physical=situated and self.load['known'] and span is not None and span>0 and span<=window and clarity>=(.45-.1*gain) and not dreamed and not reafferent and not self.sleeping and not self.dreaming
  grounding=dict(stamp=copy.deepcopy(current),ticks_since_similar=span,signature=signature,chain=copy.deepcopy(self.chain),approbation=list(self.marks)[-4:],continuity=self.continuity,load=copy.deepcopy(self.load),sleep=self.sleeping,dream=self.dreaming or dreamed,mirror_hash=digest(list(self.mirror_history))[:16],quality=quality,duration_basis='admitted_native_ticks',context_window=window)
  grounding.update(strictness=unit(genome.g('grounding_strictness')),neural_gain=gain,required_quality=threshold,clarity=clarity,required_clarity=.45-.1*gain)
  meta=dict(spike_id=ident,grounding_hash=digest(grounding),source_scope=raw['sensory']['source_scope'],expression_ids=list(raw['sensory']['expression_ids']),dreamed=dreamed)
  context=self.model_context(raw,current);vector=self.model.encode(features,context)
  result=dict(raw,features=features,grounding=grounding,neural=meta,eligible=dict(mirror=situated and not dreamed and not reafferent,cache=situated,attraction=situated,root=physical),neural_vector=vector,authority='authority' if physical else 'unauthority',text='sensory:'+vision['source']+':'+signature[:12],label='situated '+vision['source'],worth=round(unit(.35+.4*quality+.15*clarity),4),x=raw['region']['x'],y=raw['region']['y'])
  result['candidate_digest']=digest(result);self.situated[ident]=copy.deepcopy(result);bounded(self.situated,128)
  return result
 def model_context(self,raw,stamp):
  v=raw['vision'];return dict(world_id=stamp['world_id'],segment_id=stamp['segment_id'],runtime=self.hub.runtime,eye_runtime=v['eye_runtime'],source=v['source'],epoch=v['epoch'],load=self.load['level'],sleep=self.sleeping,chain=len(self.chain),continuity=self.continuity)
 def canonical(self,ident):return copy.deepcopy(self.situated.get(ident))
 def metadata(self,ident):
  row=self.situated.get(ident);return copy.deepcopy(row['neural']) if row else None
 def can_promote(self,payload,target='mirror'):
  if not isinstance(payload,dict):return False
  meta=payload.get('neural') or {};ident=meta.get('spike_id',payload.get('id'));row=self.situated.get(ident)
  if row is None or target not in row['eligible'] or not row['eligible'][target]:return False
  if not self._active(row['vision']):return False
  # A thin native derivative may carry only the registered metadata. A full
  # situated payload must match every byte, preventing changed cues/stamps.
  if 'candidate_digest' in payload and {k:v for k,v in payload.items() if k not in ('context_ref','receipt_context_ref')}!=row:return False
  if meta!=row['neural']:return False
  age=tick_distance(self.clock(),row['grounding']['stamp'])
  if age is None or self.clock()['tick']<row['grounding']['stamp']['tick'] or age>row['grounding']['context_window']:return False
  if target in ('root','mirror') and (meta['dreamed'] or meta['expression_ids']):return False
  if target in ('root','mirror') and any(payload.get(flag) for flag in ('dream','dreamed','replayed','echo')):return False
  if target in ('root','mirror') and (self.sleeping or self.dreaming):return False
  return True
 def register_mirror(self,payload,ref):
  if not isinstance(ref,str) or not ref.startswith('mirror:n:') or len(ref)>40 or not self.can_promote(payload,'mirror'):return None
  ident=payload['neural']['spike_id'];canonical=self.situated[ident]
  if ref in self.pending_mirrors and self.pending_mirrors[ref]['id']!=ident:return None
  self.pending_mirrors[ref]=copy.deepcopy(canonical);bounded(self.pending_mirrors,128);return self.metadata(ident)
 def confirm_mirror(self,ref,held):
  row=self.pending_mirrors.get(ref);mirror=self.mirror_receipts.get(ref);mark=self.approbations.get(ref)
  if not row or not mirror or not mark or row['id'] in self.confirmed or not self.can_promote(row,'root'):return None
  if finite(held)<float(self.ns.get('ROOT_HELD',.55)) or mark['held']>finite(held)+1e-8 or mark['serial']<=mirror['serial']:return None
  return dict(schema='ALIEN_SENSORY_TRACE_V1',spike_id=row['id'],mirror_ref=ref,world_stamp=copy.deepcopy(mark['stamp']),source_stamp=copy.deepcopy(row['world_stamp']),grounding=copy.deepcopy(row['grounding']),grounding_hash=row['neural']['grounding_hash'],source_scope=row['neural']['source_scope'],vision=copy.deepcopy(row['vision']),expression_ids=[],dreamed=False,semantic_verification='unknown',independent_outside_evidence=False,claim='measured_sensory_receipt',confirmation='internal_mirror_and_approbation',held=mark['held'],candidate_digest=row['candidate_digest'])
 def commit_trace(self,trace):
  if not isinstance(trace,dict):return False
  expected=self.confirm_mirror(trace.get('mirror_ref'),trace.get('held',0.))
  if expected is None or expected!=trace:return False
  self.confirmed[trace['spike_id']]=copy.deepcopy(trace);bounded(self.confirmed,256)
  signature=(trace['world_stamp']['world_id'],trace['world_stamp']['segment_id'],trace['grounding']['signature']);tick=trace['world_stamp']['tick'];last=self.last_gain.get(signature)
  if last is None or tick-last>=max(32,trace['grounding']['context_window']):
   self.last_gain[signature]=tick;bounded(self.last_gain,128);self._strengthen_gain()
  if self.bus:self.bus.publish('neural_trace_confirmed',dict(trace=trace,neural=self.metadata(trace['spike_id']),authority='authority',semantic_verification='unknown'))
  return True
 def reserve_trace(self,ref,held):
  """Linearize approval on its native tick, before a possibly slow disk fence."""
  trace=self.confirm_mirror(ref,held)
  if trace is None or len(self.trace_reservations)>=128 or any(row['trace']['spike_id']==trace['spike_id'] for row in self.trace_reservations.values()):return None
  token=uuid.uuid4().hex
  self.trace_reservations[token]=dict(trace=copy.deepcopy(trace),runtime=self.hub.runtime,world=self.hub.clock.world_id)
  return token,copy.deepcopy(trace)
 def cancel_trace(self,token):return self.trace_reservations.pop(token,None)
 def complete_trace(self,token,trace):
  reserved=self.trace_reservations.get(token)
  if not reserved or reserved['trace']!=trace or reserved['runtime']!=self.hub.runtime or reserved['world']!=self.hub.clock.world_id or trace['spike_id'] in self.confirmed:return False
  # This is already-approved history. Later ticks, sleep or source retirement
  # cannot re-stamp it or revoke the earlier electrical approval.
  del self.trace_reservations[token]
  self.confirmed[trace['spike_id']]=copy.deepcopy(trace);bounded(self.confirmed,256)
  signature=(trace['world_stamp']['world_id'],trace['world_stamp']['segment_id'],trace['grounding']['signature']);tick=trace['world_stamp']['tick'];last=self.last_gain.get(signature)
  if last is None or tick-last>=max(32,trace['grounding']['context_window']):
   self.last_gain[signature]=tick;bounded(self.last_gain,128);self._strengthen_gain()
  if self.bus:self.bus.publish('neural_trace_confirmed',dict(trace=trace,neural=copy.deepcopy(self.situated.get(trace['spike_id'],{}).get('neural')),authority='authority',semantic_verification='unknown'))
  return True
 def _strengthen_gain(self):
  sup=self.supervisor
  if sup is None or 'neural_gain' not in self.ns['GENE_NAMES']:return
  genome=sup.genome.copy();idx=self.ns['GENE_NAMES'].index('neural_gain');genome.genes[idx]=unit(genome.genes[idx]+.004);sup.genome=genome
  if self.bus:self.bus.publish('mutation_applied',dict(genes=list(genome.genes),generation=genome.generation,source='grounded_neural_cycle',authority='unauthority'))
 def train(self,payload):
  if not self.can_promote(payload,'cache') or payload['neural']['dreamed'] or payload['neural']['expression_ids'] or self.sleeping or self.load['high'] or self.optional_high:return None
  row=self.situated[payload['id']]
  if row['id'] in self.trained:return None
  stats=self.model.learn(row['features'],self.model_context(row,row['grounding']['stamp']),row['id'],row['grounding']['stamp']['tick'],eligible=True)
  # Registry integrity fields remain immutable; training receipts are separate.
  if not stats.get('updated',True):return None
  self.trained[row['id']]=True;bounded(self.trained,256);self.last_stats=stats;self.learned+=1
  self.cache.append('neural.situated',dict(candidate=row,learning=stats))
  receiver=getattr(getattr(self.hub,'progression',None),'accept_sensory',None)
  if callable(receiver):receiver(row)
  if self.learned%16==0:self.archive.set_json('neural.model','v1',self.model.snapshot())
  return stats
 def expression(self,kind,payload):
  stamp=self.clock()
  if stamp is None or stamp['tick']-self.last_output<4:return None
  if self.optional_high and kind in ('weak','situated','dream'):return None
  meta=payload.get('neural') or {};row=self.situated.get(meta.get('spike_id',payload.get('id')))
  if row is None:
   if kind=='dream' and meta.get('dreamed'):row=payload
   elif meta:return None
   elif kind in ('weak','dream'):row=payload
   elif kind in ('mirror','approbation','root','situated'):
    last=next(reversed(self.situated.values()),{})
    base_region=last.get('region',dict(x=.5,y=.5))
    row=dict(id=None,features=last.get('features',{}),region=dict(x=payload.get('x',base_region.get('x',.5)),y=payload.get('y',base_region.get('y',.5))))
    meta=dict(grounding_hash=digest(dict(stamp=stamp,chain=self.chain,continuity=self.continuity,mirrors=list(self.mirror_history))))
   else:return None
  marker=row.get('grounding') or {};features=row.get('features') or {}
  region=row.get('region') or dict(x=payload.get('x',.5),y=payload.get('y',.5))
  strong=kind not in ('weak','dream');strength=(.12 if not strong else min(.6,.15+.4*finite(payload.get('worth'),.5)))*(.6+.8*self.gain())
  strength=min(.75,strength)
  cx=unit(region.get('x',.5));cy=unit(region.get('y',.5));r0=max(.04,min(.32,.07+.06*strength))
  base_hue=unit(features.get('hue_sin',.62 if payload.get('temporal') else .14 if payload.get('owned') else .55))
  regions=[dict(x=cx,y=cy,radius=r0,strength=strength,hue=base_hue)]
  lateral=payload.get('temporal',{}).get('paths',{}).get('lateral',[]) if isinstance(payload.get('temporal'),dict) else []
  if lateral:
   for idx,hop in enumerate(lateral[:2]):
    node_id=str(hop.get('node',{}).get('id') or '0');angle=((int(node_id[:8] or '0',16)%360)/360)*math.tau;dist=.14+.04*idx
    regions.append(dict(x=unit(min(.88,max(.12,cx+dist*math.cos(angle)))),y=unit(min(.88,max(.12,cy+dist*math.sin(angle)))),radius=max(.04,min(.32,r0*.82)),strength=round(strength*.85,6),hue=unit((base_hue+.28*(idx+1))%1.)))
  elif kind in ('mirror','approbation','root') or payload.get('owned') is True:
   count=2 if kind=='root' else 1
   seed_angle=((stamp['slot']%8)/8+(int(self.continuity or '0',16)%256)/256)*math.tau
   for idx in range(count):
    angle=seed_angle+idx*(math.tau/max(2,count+1));dist=.11+.03*idx
    regions.append(dict(x=unit(min(.9,max(.1,cx+dist*math.cos(angle)))),y=unit(min(.9,max(.1,cy+dist*math.sin(angle)))),radius=max(.04,min(.32,r0*(.78-.1*idx))),strength=round(strength*(.8-.12*idx),6),hue=unit((base_hue+.19*(idx+1))%1.)))
  ident=uuid.uuid4().hex
  value=dict(event='neural_expression',version=1,output_id=ident,runtime=self.hub.runtime,world_id=stamp['world_id'],stamp=copy.deepcopy(stamp),expires_tick=stamp['tick']+(8 if strong else 3),kind=kind,regions=regions[:4],marker=dict(tick_echo=stamp['slot'],chain_residue=unit(max((x['pull'] for x in self.chain),default=0.)),continuity=self.continuity,grounding=str(meta.get('grounding_hash',''))[:16]),causal_spike_id=row.get('id'),semantic_verification='unknown')
  value=validate_expression(value);self.outputs[ident]=value;bounded(self.outputs,32);self.last_output=stamp['tick'];return value
 def presented(self,record):
  record=validate_presented(record);output=self.outputs.get(record['output_id']);stamp=self.clock()
  if output is None or record['runtime']!=self.hub.runtime or record['world_id']!=self.hub.clock.world_id or record['stamp']!=output['stamp'] or stamp is None or tick_distance(stamp,output['stamp']) is None or not output['stamp']['tick']<=record['render_tick']<=min(output['expires_tick'],stamp['tick']):return False
  if record['surface']=='eye' and (record.get('eye_runtime')!=self.active_eye_runtime or record.get('eye_runtime') in self.retired_eye):return False
  key=(record['output_id'],record['surface'])
  if key in self.presentations:return False
  try:self.cache.append('neural.presented',record)
  except OSError as error:
   self.storage_error=type(error).__name__+': '+str(error)[:160];return False
  self.presentations[key]=record;bounded(self.presentations,64);return True
 def dream_replay(self,genome):
  if not self.situated:return None
  previous=copy.deepcopy(next(reversed(self.situated.values())));previous['id']=uuid.uuid4().hex
  previous['dreamed']=True;previous['neural']['dreamed']=True;previous['neural']['spike_id']=previous['id'];previous['authority']='unauthority';previous['eligible']={name:False for name in ('mirror','root','attraction','cache')};previous['grounding']=dict(previous['grounding'],dream=True,imagined=True,partial=True,quality=previous['grounding']['quality']*.5,required_quality=previous['grounding']['required_quality']*.5,imagined_tick=self.clock()['tick'] if self.clock() else None,imagined_chain=copy.deepcopy(self.chain));previous['neural']['grounding_hash']=digest(previous['grounding']);previous.pop('candidate_digest',None);previous['candidate_digest']=digest(previous)
  return previous
 def summary(self):
  stamp=self.clock();ticks=list(self.recent_spikes)
  recent=[n for n in ticks if stamp and 0<=stamp['tick']-n<=64];row=next(reversed(self.situated.values()),{})
  features=row.get('features') or {}
  hue=None
  if 'hue_sin' in features and 'hue_cos' in features:hue=round((math.atan2(2*features['hue_sin']-1,2*features['hue_cos']-1)/math.tau)%1,4)
  return dict(version=1,dominant_chroma=hue,spikes_per_tick=round(len(recent)/64,4),last_mirrored_region=copy.deepcopy(self.last_mirrored_region),grounded_samples=len(self.situated),internally_confirmed=len(self.confirmed),sleep=self.sleeping,source_scope='self_or_mixed_unknown',semantic_verification='unknown')
 def close(self):
  try:self.archive.set_json('neural.model','v1',self.model.snapshot())
  finally:
   try:
    language=getattr(self,'language',None)
    if language is not None:language.close()
   finally:self.archive.close()
 async def drain(self):
  """Let loop-owned root ACK callbacks finish before the final hub snapshot."""
  loop=asyncio.get_running_loop();deadline=loop.time()+4
  while any(writer._root_waiting() or writer._dirty for writer in self.root_writers):
   if loop.time()>=deadline:raise OSError('sensory root archive acknowledgement did not drain')
   for writer in self.root_writers:
    if writer._dirty and not writer._root_waiting():writer.flush()
   await asyncio.sleep(.05)
  errors=[writer._archive_state['error'] for writer in self.root_writers if writer._archive_state['error']]
  if errors:raise OSError('sensory root archive failed: '+errors[0])

def make_agents(ns,system=None):
 Base=ns.get('NEURAL_BASE_AGENT',ns['Agent'])
 class NeuralInterfaceAgent(Base):
  name='neural'
  def __init__(self,params,genome):super().__init__(params);self.genome=genome.copy();self.system=system or ns['NEURAL_SYSTEM'];self.last_dream=-100
  async def run(self,bus,stop):
   self._queue=bus.subscribe('eye_sensory','situated_spike','mirror_truth','approbation_marked','attraction_rise','neural_trace_confirmed','root_truth_delta','temporal_rift','learning_conclusion','tick','mutation_applied','generation_complete','load','enter_sleep','wake','shutdown')
   while not stop.is_set():
    self.beat(bus);event=await ns['wait_evt'](self._queue,self.pace(.25));
    if event is None:continue
    name=event['name'];body=event.get('payload') or {};kind=None
    if name=='shutdown':return
    if name in ('mutation_applied','generation_complete'):
     genome=ns['take_genome'](body)
     if genome is not None:self.genome=genome
    elif name in ('load','enter_sleep','wake'):
     (self.notice_load if name=='load' else lambda p:self.notice_sleep(name,p))(body)
    elif name=='eye_sensory':
     for raw in self.system.ingest(body):bus.publish('neural_spike',raw)
     stamp=self.system.clock();recent=[tick for tick in self.system.recent_spikes if stamp and 0<=stamp['tick']-tick<=8]
     if len(recent)>12:bus.publish('neural_pressure',dict(spikes_per_tick=len(recent)/8,world_stamp=stamp,authority='unauthority'))
    elif name=='situated_spike':self.system.train(body);kind='situated' if self.system.can_promote(body,'cache') else 'weak'
    elif name in ('mirror_truth','approbation_marked','attraction_rise'):
     if body.get('neural') or finite(body.get('worth'))>=.62 or finite(body.get('held'))>=.55 or finite(body.get('pull'))>=.65:kind={'mirror_truth':'mirror','approbation_marked':'approbation','attraction_rise':'situated'}[name]
    elif name in ('neural_trace_confirmed','root_truth_delta'):kind='root'
    elif name=='temporal_rift':kind='mirror'
    elif name=='learning_conclusion' and body.get('owned') is True:kind='approbation'
    elif name=='tick':
     current=self.system.clock()
     if current and self.system.sleeping and current['tick']-self.last_dream>=16:
      self.last_dream=current['tick'];dream=self.system.dream_replay(self.genome)
      if dream:
       bus.publish('dreamed_neural_activity',dream);body=dream;kind='dream'
    if kind:
     expression=self.system.expression(kind,body)
     if expression:bus.publish('neural_expression',expression)
 class GroundingAgent(Base):
  name='grounding'
  def __init__(self,params,genome):super().__init__(params);self.genome=genome.copy();self.system=system or ns['NEURAL_SYSTEM']
  async def run(self,bus,stop):
   self._queue=bus.subscribe('neural_spike','mutation_applied','generation_complete','load','enter_sleep','wake','shutdown')
   while not stop.is_set():
    self.beat(bus);event=await ns['wait_evt'](self._queue,self.pace(.25))
    if event is None:continue
    name=event['name'];body=event.get('payload') or {}
    if name=='shutdown':return
    if name in ('mutation_applied','generation_complete'):
     genome=ns['take_genome'](body)
     if genome is not None:self.genome=genome
    elif name=='neural_spike':
     situated=self.system.ground(body,self.genome)
     if situated:bus.publish('situated_spike',situated)
    elif name=='load':self.notice_load(body)
    else:self.notice_sleep(name,body)
 return dict(NeuralInterfaceAgent=NeuralInterfaceAgent,NeuralAgent=NeuralInterfaceAgent,GroundingAgent=GroundingAgent)

def install(ns,hub,cache):
 system=NeuralSystem(ns,hub,cache);hub.neural=system;ns['NEURAL_SYSTEM']=system;ns.update(make_agents(ns,system))
 from neural_native import bind_native
 bind_native(ns,system)
 Base=ns['EventBus']
 class NeuralBus(Base):
  def __init__(self):super().__init__();system.bus=self
  def _emit(self,name,body):
   result=super()._emit(name,body);system.observe(name,body)
   if name=='neural_expression':hub.send(validate_expression(body))
   return result
 ns['EventBus']=NeuralBus
 from spark_rift import install as install_spark
 install_spark(ns)
 from language_native import install as install_language
 system.language=install_language(ns,hub,cache,system)
 if getattr(getattr(hub,'progression',None),'adaptor',None) is not None and getattr(hub,'alphabet',None) is not None:
  from rift_interface import install as install_rift
  install_rift(ns,hub,cache)
 return system

def ansi_main(ns):
 """Keep the native ANSI entrance while using the same cache/grounding layers."""
 import fcntl,os,tempfile
 from pathlib import Path
 from native_cache import install as install_cache
 from integration import Hub
 from progression import install as install_progression
 release=Path(__file__).resolve().parents[1]
 data=release.parent.parent/'data' if release.parent.name=='releases' else release/'work'/'ansi'
 root=data/'sessions';root.mkdir(parents=True,exist_ok=True,mode=0o700)
 lease=open(data/'launcher.lock','a')
 try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:lease.close();raise SystemExit('Alien World is already running')
 session=Path(tempfile.mkdtemp(prefix='ansi-',dir=root))
 for name in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'):os.environ.pop(name,None)
 from async_cache import AsyncContentCache
 with lease,AsyncContentCache(data/'alien.cache',uuid.uuid4().hex) as cache:
  install_cache(ns,session,cache);hub=Hub(ns,session,cache=cache);progression=install_progression(ns,cache,hub);neural=install(ns,hub,cache)
  ns['llm_endpoint']=lambda:None;ns['try_remote_embed']=lambda text:None
  original=ns['amain']
  async def run(visual):
   try:hub.start();return await original(visual)
   finally:
    try:await neural.drain()
    finally:
     try:hub.close()
     finally:
      try:progression.close()
      finally:neural.close()
  ns['amain']=run
  return ns['main']()

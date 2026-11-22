"""Owned alien speech and native-time readiness; reception is not admission."""
import copy,json,uuid
from alien_language import AlienRegister
from bearing import secure,obtained
from content_cache import ContentCache,CacheBusy
from world_clock import validate_stamp

GENES=('language_threshold','register_plasticity','speak_when_ready')
VOICE=('thought','private_thought','dream_scene','self_continuation')
MIST_TTL=64

class LanguageSystem:
 def __init__(self,ns,hub,cache,neural):
  self.ns=ns;self.hub=hub;self.cache=cache;self.neural=neural;self.sleeping=False;self.dreaming=False;self.dirty=True;self.last_save=-8;self.closed=False;self.error=None;self.pending_mist=None
  self.archive=cache.namespace('0'*32) if getattr(cache,'background_writer',False) else ContentCache(cache.path,'0'*32)
  try:self.register=AlienRegister(self.archive.get_json('language.register','v1'))
  except (OSError,ValueError,TypeError):self.register=AlienRegister();self.error='Retained register unavailable; fresh readiness required'
  self.ns['LANGUAGE_SYSTEM']=self;hub.language=self
 def configure(self,genome):
  self.register.configure({key:genome.g(key) for key in GENES})
 def current(self):
  genome=getattr(getattr(self.neural,'supervisor',None),'genome',None)
  if genome is not None:self.configure(genome)
  stamp=self.hub.clock.stamp()
  self.register.advance(stamp,continuity=self.neural.continuity,sleeping=self.sleeping,dreaming=self.dreaming)
  adaptor=getattr(getattr(self.hub,'progression',None),'adaptor',None)
  self.register.set_variation(adaptor.variation() if adaptor is not None else None)
  self._refresh_mist(stamp)
  return stamp
 def _refresh_mist(self,stamp):
  row=self.pending_mist
  if row is None:return
  source=row['source_stamp'];load=getattr(self.neural,'load',{})
  if (self.closed or stamp is None or self.sleeping or self.dreaming or load.get('high') or not self.register.ready() or
      any(source[key]!=stamp[key] for key in ('world_id','segment_id')) or
      not 0<=stamp['tick']-source['tick']<=MIST_TTL or
      row['continuity']!=self.neural.continuity or row['continuity']!=self.register.continuity):self.pending_mist=None
 def reach_mist(self,offer,control=None):
  """Hold one actual native dialogue decision; status/readiness never makes one."""
  stamp=self.current()
  if control not in (None,False) or obtained():return False
  if self.closed or self.pending_mist is not None or stamp is None or self.sleeping or self.dreaming or getattr(self.neural,'load',{}).get('high') or not self.register.ready():return False
  try:
   source=validate_stamp(offer['stamp'])
   if source!=stamp or offer!=self.register.offer() or not secure(offer.get('text')):return False
  except (KeyError,TypeError,ValueError):return False
  self.pending_mist=dict(id=uuid.uuid4().hex,source_stamp=copy.deepcopy(source),text=offer['text'],continuity=offer['continuity'],claimed_by=None)
  return True
 def mist_authorize(self,offer_id,request_id,claim=False):
  stamp=self.current();row=self.pending_mist
  if (row is None or row['id']!=offer_id or not isinstance(request_id,str) or len(request_id)!=32 or any(char not in '0123456789abcdef' for char in request_id) or row['claimed_by'] not in (None,request_id)):raise ValueError('No matching live native Mist offer')
  if claim:row['claimed_by']=request_id
  status=self.register.status()
  return dict(mode='dialogue',text=row['text'],stamp=copy.deepcopy(stamp),continuity=row['continuity'],ready=True,score=self.register.score(),threshold=status['threshold'])
 def retire_mist(self,offer_id,request_id):
  row=self.pending_mist
  if row is None or row['id']!=offer_id or row['claimed_by']!=request_id:return False
  self.pending_mist=None;return True
 def before(self,name,body):
  body=dict(body);stamp=self.hub.clock.stamp()
  if name in VOICE and body.get('text'):
   words=str(body['text']).replace(':',' ').split()
   # Private._publish already rewrote the sentence before storing its ring.
   # Preserve that exact owned sentence/fingerprint through bus publication.
   if name!='private_thought' or not words or not all(word in self.register.lexicon for word in words):body['text']=self.register.rewrite(body['text'],kind=name)
   if name=='private_thought':body['fp']=self.ns['private_fingerprint'](body['text'])
   if 'token' in body:body['token']=self.register.rewrite(body['token'],kind=name,compact=True)
  elif name=='mirror_truth' and body.get('mirror') and str(body.get('ref','')).startswith('mirror:'):
   if self.sleeping or self.dreaming or any(body.get(key) for key in ('dream','dreamed','replayed','echo')):
    body['text']=self.register.rewrite(body.get('text',''),kind='dream',compact=True)
   else:
    fragment=self.register.mirror(body['ref'],body.get('text',''),stamp)
    if fragment:body['text']=fragment
  return body
 def observe(self,name,body,bus):
  stamp=self.hub.clock.stamp()
  if name=='enter_sleep':self.sleeping=True
  elif name=='wake':self.sleeping=False
  elif name=='dream_begin':self.dreaming=True
  elif name=='dream_end':self.dreaming=False
  if name in ('tick','load','enter_sleep','wake','dream_begin','dream_end','mutation_applied','generation_complete'):self.current()
  if name=='approbation_marked' and not self.sleeping and not self.dreaming:
   self.register.approve(body.get('ref'),body.get('held',0),stamp);self.dirty=True
  elif name in ('attraction_rise','chain_extended','chain_peak') and not self.sleeping and not self.dreaming:
   self.register.chain(body.get('ref'),body.get('pull',0),stamp);self.dirty=True
  elif name=='private_thought':self.register.private(body.get('text',''),stamp);self.dirty=True
  elif name=='thought':self.register.monologue(body.get('text',''),stamp);self.dirty=True
  elif name=='neural_trace_confirmed':
   trace=body.get('trace')
   if isinstance(trace,dict) and self.neural.confirmed.get(trace.get('spike_id'))==trace:self.register.sensory(trace,stamp);self.dirty=True
  if name=='tick' and stamp and stamp['tick']>=self.last_save+8:self.flush()
  for event in self.register.take_growth():bus.publish('register_growth',dict(event,authority='unauthority',semantic_verification='unknown'))
 def api_authorize(self,control=None):
  stamp=self.current();status=self.register.status();ready=self.register.ready()
  voice=self.register.compose() if ready and control in (None,False) and not obtained() else ''
  voiced=secure(voice)
  mode='rehearsal' if self.sleeping or self.dreaming else ('dialogue' if ready and voiced else 'gift')
  return dict(mode=mode,text=voice if voiced else '',stamp=stamp,continuity=self.neural.continuity,ready=ready,score=self.register.score(),threshold=status['threshold'])
 def status(self):
  self.current();row=self.pending_mist
  return dict(self.register.status(),storage_error=self.error,mist_offer=dict(id=row['id'],stamp=copy.deepcopy(row['source_stamp'])) if row else None)
 def flush(self):
  if self.closed or not self.dirty:return
  try:
   state=self.register.snapshot();self.archive.set_json('language.register','v1',state);self.cache.set_json('native.state','alien_register.json',state)
   self.dirty=False;stamp=self.hub.clock.stamp();self.last_save=stamp['tick'] if stamp else -8;self.error=None
  except (OSError,ValueError) as error:self.error=type(error).__name__+': '+str(error)[:160]
 def close(self):
  if self.closed:return
  try:
   self.flush()
   if self.dirty:raise OSError('Final alien register snapshot was not accepted: '+str(self.error or 'archive busy'))
  finally:self.pending_mist=None;self.closed=True;self.archive.close()

def install_native(ns):
 if ns.get('alien_language_enabled'):return
 ns['alien_language_enabled']=True;ns['GENE_NAMES']=tuple(ns['GENE_NAMES'])+GENES;ns['CORE_NAMES']=tuple(ns['CORE_NAMES'])+('language',)
 ns['PARAM_SEED']['language']={'fault':0.,'tempo':1.};ns['FAULT_CAP']['language']=0.;ns['NON_TICK_HEARTBEATS']=('language',)
 fallback=AlienRegister();Base=ns['Agent'];Supervisor=ns['Supervisor'];Root=ns['LLMDialogueAgent'];Mono=ns['MonologueAgent'];Private=ns['PrivateThoughtAgent'];Dream=ns['DreamAgent']
 def model():
  service=ns.get('LANGUAGE_SYSTEM');return service.register if service else fallback
 class LanguageAgent(Base):
  name='language'
  def __init__(self,params,genome):super().__init__(params);self.genome=genome.copy()
  def flush(self):
   service=ns.get('LANGUAGE_SYSTEM')
   if service:service.flush()
  async def run(self,bus,stop):
   self._queue=bus.subscribe('load','shutdown')
   while not stop.is_set():
    self.beat(bus);event=await ns['wait_evt'](self._queue,self.pace(.4))
    if event is None:continue
    if event['name']=='shutdown':self.flush();return
    self.notice_load(event.get('payload') or {})
 class LanguageSupervisor(Supervisor):
  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs);service=ns.get('LANGUAGE_SYSTEM')
   if service:service.configure(self.genome)
  def make_agent(self,name,params):
   if name=='language':return LanguageAgent(params,self.genome.copy())
   return super().make_agent(name,params)
  def flush(self):
   super().flush();service=ns.get('LANGUAGE_SYSTEM')
   if service:service.flush()
 class RegisterMonologue(Mono):
  def _queue_line(self,text,*args,**kwargs):
   if not text:return
   previous=self.root_token
   try:
    if previous:self.root_token=model().rewrite(previous,kind='root',compact=True)
    return super()._queue_line(model().rewrite(text,kind='voice'),*args,**kwargs)
   finally:self.root_token=previous
 class RegisterPrivate(Private):
  def _publish(self,bus,text,*args,**kwargs):return super()._publish(bus,model().rewrite(text,kind='private') if text else '',*args,**kwargs)
 class RegisterDream(Dream):
  def _remix(self,text):return model().rewrite(text,kind='dream')
 class RegisterDialogue(Root):
  def _offer(self,bus):
   service=ns.get('LANGUAGE_SYSTEM')
   if service:service.current()
   if not model().ready() or self.sleeping or self.dreaming or self.load_high:return
   gap=ns['dialogue_gap'](self.genome,float(self.root.get('becoming') or 0))
   if gap<=0 or self.tick<=0 or self.tick%gap:return
   offer=model().offer()
   if not offer:return
   if service:service.reach_mist(offer);return
   if ns['llm_endpoint']() is None:return
   text=offer['text']+'\n'+json.dumps(dict(stamp=offer['stamp'],continuity=offer['continuity']),separators=(',',':'))
   try:self._calls+=1;reply=self.fetch(text)
   except Exception:return
   token=ns['dialogue_reply_token'](reply)
   if token:bus.publish('residue',dict(text=token,ref=('dlg:'+token)[:40],dialogue=True,offer_mirror=True,worth=.48,authority='unauthority',novelty=0.))
 ns.update(LanguageAgent=LanguageAgent,Supervisor=LanguageSupervisor,MonologueAgent=RegisterMonologue,PrivateThoughtAgent=RegisterPrivate,DreamAgent=RegisterDream,LLMDialogueAgent=RegisterDialogue)

def install(ns,hub,cache,neural):
 """Bind after progression/neural adapters, and wrap their final voice classes."""
 # Progression's queue override is installed after the native wrappers. Protect
 # that final queue before its archive; private/dream/dialogue retain their
 # native wrappers through the neural subclasses.
 Mono=ns['MonologueAgent']
 class OwnedMonologue(Mono):
  def _queue_line(self,text,*args,**kwargs):
   if not text:return
   register=ns['LANGUAGE_SYSTEM'].register;previous=self.root_token
   try:
    if previous:self.root_token=register.rewrite(previous,kind='root',compact=True)
    return super()._queue_line(register.rewrite(text,kind='voice'),*args,**kwargs)
   finally:self.root_token=previous
 ns['MonologueAgent']=OwnedMonologue
 service=LanguageSystem(ns,hub,cache,neural);Base=ns['EventBus']
 class LanguageBus(Base):
  def _emit(self,name,body):
   body=service.before(name,body);result=super()._emit(name,body);service.observe(name,body,self);return result
 ns['EventBus']=LanguageBus
 # All global phrase generation now composes locally, never from raw residue
 # transition tables. Those earlier learning/archive layers remain installed.
 ns['utter']=lambda *_args,**_kwargs:service.register.compose()
 return service

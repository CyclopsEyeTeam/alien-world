"""Small online associations and prequential feedback; no model calls or truth grades.

The byte cache holds the archive. Working sets and formulation walks stay bounded
so a longer history does not create an ever-growing RAM/CPU bill.
"""
from collections import OrderedDict
import hashlib,json,math,re,uuid
from content_cache import ContentCache,read_reference
from world_clock import validate_stamp

VALUES=('learning','growth','formulation','understanding')
def tokens(text):return re.findall(r"\b[\w'-]+\b",text.casefold())
def key(text):return hashlib.sha256(text.encode()).hexdigest()
def unit(value):return max(0.,min(1.,float(value)))

class DiskQueue:
 """Lossless per-world FIFO in the content cache, with no resident text backlog."""
 def __new__(cls,cache,continuous=False):
  if continuous:
   from continuing_queue import ThoughtQueue
   return ThoughtQueue(cache)
  return super().__new__(cls)
 def __init__(self,cache,continuous=False):self.cache=cache;self.prefix=uuid.uuid4().hex;self.head=0;self.tail=0
 def __len__(self):return self.tail-self.head
 def append(self,value):
  self.cache.set_json('monologue.pending',self.prefix+':'+str(self.tail),list(value));self.tail+=1
 def pop(self,index=0):
  if index!=0 or not self:raise IndexError('pending queue is empty')
  value=self.cache.get_json('monologue.pending',self.prefix+':'+str(self.head))
  if not isinstance(value,list):raise RuntimeError('pending monologue cache unavailable')
  self.head+=1;return tuple(value)

class Learning:
 """Word transitions and per-source conditional numeric predictions.

Each prediction is scored against the NEXT observation before updating its
conditional mean. Persistence is the explicit comparison. An unfamiliar state
or source epoch provides no evidence of understanding.
"""
 def __init__(self,cache,hub=None):
  self.cache=cache;self.adaptor=None;self.text_learning=None
  # Reserved archive namespace is a library, never an Alien world or timeline.
  self.archive=cache.namespace('0'*32) if getattr(cache,'background_writer',False) else ContentCache(cache.path,'0'*32)
  self.lexicon=OrderedDict();self.observers=OrderedDict()
  self.seeds=self.archive.get_json('language.context','seeds',[]);self.last_values={k:0. for k in VALUES}
  self.prior_words=[]
  for record in self.history(limit=16):
   body=record['payload'];text=body.get('payload',body).get('text','')
   self.prior_words.extend(tokens(text))
  self.prior_words=list(dict.fromkeys(self.prior_words))[-1024:]
  if hub is not None:
   from learning_adaptor import LearningAdaptor
   def canonical(row):
    system=getattr(hub,'neural',None)
    return bool(system and system.can_promote(row,'cache') and row.get('id') in system.trained)
   def source_active(row):
    if row['source'].startswith('native.alphabet.'):
     alphabet=getattr(hub,'alphabet',None)
     return bool(alphabet and alphabet.source_active(row))
    if not row['source'].startswith('eye.'):return True
    system=getattr(hub,'neural',None);label,runtime=row['source'].split('|',1)
    return bool(system and system.learning_source_active(label[4:],runtime,row['source_epoch']))
   self.adaptor=LearningAdaptor(cache,hub.clock,getattr(hub,'runtime','hive'),archive=self.archive,sensory_validator=canonical,source_validator=source_active)
 def accept_sensory(self,row):return bool(self.adaptor and self.adaptor.accept_sensory(row))
 def close(self):
  try:
   if self.text_learning is not None:self.text_learning.close()
   alphabet=getattr(self,'alphabet',None)
   if alphabet is not None:alphabet.close()
   pending=getattr(self,'pending',None)
   if pending is not None and hasattr(pending,'close'):pending.close()
   if self.adaptor:self.adaptor.close()
  finally:self.archive.close()
 def flush_if_due(self):return self.archive.flush_if_due()
 def remember(self,kind,value,stamp):
  ref=self.cache.append(kind,value)
  self.archive.append('history.index',dict(kind=kind,world_id=self.cache.world_id,stamp=stamp,cache_ref=ref))
  return ref
 def history(self,limit=32):
  self.cache.flush();self.archive.flush();out=[]
  for row in self.archive.records('history.index',limit=limit):
   record=json.loads(self.archive.get(row['cache_ref']))
   raw=read_reference(self.cache.path,record['cache_ref'],record['world_id'])
   if raw is not None:out.append(dict(record,payload=json.loads(raw)))
  return out
 def _row(self,word):
  row=self.lexicon.get(word)
  if row is None:
   row=self.archive.get_json('language.links',key(word),{'word':word,'next':{}});self.lexicon[word]=row
  self.lexicon.move_to_end(word)
  if len(self.lexicon)>512:self.lexicon.popitem(last=False)
  return row
 def absorb(self,text,provenance=None):
  input_ref=self.cache.append('language.input',dict(text=text,provenance=provenance,semantic_verification='unknown'))
  words=tokens(text);new=0;edges=0
  for left,right in zip(words,words[1:]):
   row=self._row(left);edges+=1
   edge_key=key(left+'\0'+right);edge=self.archive.get_json('language.edge',edge_key,{'left':left,'right':right,'count':0})
   if not edge['count']:new+=1
   edge['count']+=1;edge['last_world']=self.cache.world_id;edge['latest_input_ref']=input_ref;self.archive.set_json('language.edge',edge_key,edge)
   row['next'][right]=edge['count']
   # Full edges are individually retained; a common word cannot accumulate a
   # huge in-memory successor dictionary or rewrite it on every encounter.
   if len(row['next'])>64:
    retained=sorted(row['next'],key=lambda word:row['next'][word],reverse=True)[:63]
    row['next']={word:row['next'][word] for word in dict.fromkeys(retained+[right])}
   self.archive.set_json('language.links',key(left),row)
  # These are only a working seed sample; every association remains on disk.
  self.seeds=list(dict.fromkeys(self.seeds+words))[-256:]
  self.archive.set_json('language.context','seeds',self.seeds)
  reinforced=max(0,edges-new)
  learning=reinforced/max(1,edges) if edges>0 else 0.
  understanding=(reinforced/edges)*min(1.,edges/4.) if reinforced>0 and edges>=2 else 0.
  result=dict(learning=learning,growth=new/max(1,edges),formulation=float(edges>0),understanding=understanding,semantic_verification='unknown',new_associations=new)
  self.last_values=result;return result
 def compose(self,rng,words):
  pool=list(dict.fromkeys(self.seeds+list(words)[-1024:]))
  if not pool:return ''
  connected=[w for w in pool if w in self.lexicon and self.lexicon[w].get('next')]
  word=rng.choice(connected if connected and rng.random()<.75 else pool);out=[word]
  for _ in range(rng.randint(7,23)):
   options=self._row(word)['next']
   if options:
    recent=set(out[-2:])
    weights=[v*(.25 if k in recent and len(options)>1 else 1.)*(1.25 if k in self.lexicon and self.lexicon[k].get('next') else 1.) for k,v in options.items()]
    word=rng.choices(list(options),weights=weights,k=1)[0]
   elif len(out)>3 and rng.random()<.4:break
   else:word=rng.choice(pool)
   out.append(word)
  return ' '.join(out)
 def observe(self,source,epoch,features,stamp):
  stamp=validate_stamp(stamp)
  if stamp is None:return None
  values=[unit(x) for x in features]
  if not values or len(values)>32 or any(not math.isfinite(float(x)) for x in features):return None
  ident=':'.join((stamp['world_id'],stamp['segment_id'],source,str(epoch)))
  state=self.observers.get(ident)
  if state is None:
   state={'last':None,'last_key':None,'loss':0.,'baseline':0.,'scored':0,'steps':0,'mean':[0.]*len(values)}
   self.observers[ident]=state
  self.observers.move_to_end(ident)
  if len(self.observers)>12:self.observers.popitem(last=False)
  previous=state['last'];error=baseline=None;formulation=0.;growth=0.
  if previous is not None and len(previous)==len(values):
   # A learned expectation can carry forward. Its previous-observation link
   # cannot: that link is isolated by world, segment, helper and source epoch.
   row_key=key(source.split(':',1)[0]+':'+str(len(values))+':'+state['last_key'])
   row=self.archive.get_json('learning.transitions',row_key,{'n':0,'mean':[0.]*len(values)})
   if row['n']>=3:
    error=sum((a-b)**2 for a,b in zip(row['mean'],values))/len(values)
    # Compare with the stronger simple alternative for this observation. A
    # running mean must not look like understanding merely by beating noise.
    baseline=min(sum((a-b)**2 for a,b in zip(previous,values))/len(values),sum((a-b)**2 for a,b in zip(state['mean'],values))/len(values))
    state['scored']+=1;state['loss']+=error;state['baseline']+=baseline;formulation=1.
   growth=float(row['n']==0);row['n']+=1
   row['mean']=[old+(new-old)/row['n'] for old,new in zip(row['mean'],values)]
   row['last_world']=self.cache.world_id;self.archive.set_json('learning.transitions',row_key,row)
  state['last']=values;state['last_key']=','.join(str(min(7,int(x*8))) for x in values);state['steps']+=1
  state['mean']=[old+(new-old)/state['steps'] for old,new in zip(state['mean'],values)]
  understanding=0.
  if state['scored']>=12 and state['baseline']>1e-9:understanding=unit(1-state['loss']/state['baseline'])
  result=dict(learning=understanding,growth=growth,formulation=formulation,understanding=understanding,prediction_error=error,baseline_error=baseline,evaluated=state['scored'],semantic_verification='unknown')
  self.cache.append('learning.feedback',dict(source=source,epoch=epoch,stamp=stamp,features=values,values=result))
  self.cache.set_json('learning.state',key(ident),state);self.last_values=result;return result

def numeric_features(text):
 """Stable named field measurements only; omit IDs and arbitrary region ordering."""
 try:value=json.loads(text)
 except (ValueError,TypeError):return []
 field=value.get('field',{})
 result=[]
 def visit(node):
  if isinstance(node,dict):
   for name in sorted(node):visit(node[name])
  elif isinstance(node,list):
   for child in node:visit(child)
  elif type(node) in (int,float) and math.isfinite(node):result.append(unit(node))
 visit(field)
 return result[:32]

def install(ns,cache,hub):
 """Wrap the frozen seams; leave the preserved original source unchanged."""
 model=Learning(cache,hub);hub.progression=model;model.adaptor.math_events=tuple(ns['MATH_EVENTS']);BaseBus=ns['EventBus'];BaseMonologue=ns['MonologueAgent'];BaseValuation=ns['ValuationAgent']
 from alphabet_rift import AlphabetRift
 model.alphabet=AlphabetRift(cache,hub.clock,getattr(hub,'runtime','hive'));hub.alphabet=model.alphabet;model.adaptor.alphabet=model.alphabet
 if getattr(cache,'background_writer',False) and callable(getattr(cache,'put_batch_json',None)):
  from text_learning import TextLearning
  model.text_learning=TextLearning(cache,model,hub.clock)
 model.own_publication=0
 pending=DiskQueue(cache,continuous=bool(ns.get('_CONTINUOUS_WORLD')));model.pending=pending
 class ProgressBus(BaseBus):
  def _emit(self,name,body):
   body=dict(body)
   if name=='residue' and (body.get('origin') or body.get('vision')):
    stamp=hub.clock.stamp();vision=body.get('vision')
    if vision:
     # Epoch and helper identity fence temporal learning across reconnects.
     result=model.observe(vision['source']+':'+vision['eye_runtime'],vision['epoch'],numeric_features(body.get('text','')),stamp)
    elif model.text_learning is not None:
     body['progression_pending']=model.text_learning.offer(body.get('text',''),dict(stamp=stamp,origin=body.get('origin')));result=None
    else:result=model.absorb(body.get('text',''),dict(stamp=stamp,origin=body.get('origin')))
    if result:body['progression']=result
   if name=='thought':model.remember('monologue.history',dict(stamp=hub.clock.stamp(),payload=body),hub.clock.stamp())
   result=super()._emit(name,body)
   if (name in ('thought','self_continuation') and body.get('text') and not model.adaptor.sleeping and not model.adaptor.dreaming and body.get('kind')!='dream' and
       not any(body.get(flag) for flag in ('dream','dreamed','replayed','echo','amplified','retag','derived_learning'))):
    # The outer LanguageBus has already supplied the final owned public line.
    # Retain only typed publication provenance, never private source history.
    # Receipt order disambiguates distinct same-tick lines; it is not a clock.
    model.own_publication+=1;runtime=getattr(hub,'runtime','hive')
    provenance=dict(event=name,runtime=runtime,source_stamp=hub.clock.stamp(),publication_id=runtime+':'+str(model.own_publication))
    for field in ('context_ref','id','vid'):
     value=body.get(field)
     if isinstance(value,str) and len(value)<=256:provenance[field]=value
    model.alphabet.offer('own',body['text'],provenance=provenance)
   model.adaptor.on_event(name,body,self)
   # Adaptor lifecycle/clock handling precedes any study on this native tick.
   # Issued numeric_pattern events then re-enter the same existing bus.
   model.alphabet.on_event(name,body,self)
   if name=='tick' and model.text_learning is not None and not (model.adaptor.closed or model.adaptor.sleeping or model.adaptor.dreaming):model.text_learning.pump(self)
   if name=='tick' and hasattr(pending,'pump'):pending.pump()
   if name in ('tick','shutdown'):
    try:model.flush_if_due()
    except (OSError,ValueError) as error:hub.archive_flush_error=type(error).__name__+': '+str(error)[:160]
   return result
 class OpenMonologue(BaseMonologue):
  def __init__(self,*args,**kw):
   super().__init__(*args,**kw);self.pending=pending
   self.words=list(dict.fromkeys(model.archive.get_json('language.context','voice_words',[])+model.prior_words))[-1024:];self.word_set=set(self.words)
  def _say(self,*args,**kwargs):
   held=getattr(pending,'held',None);delivery=held is not None and not held['said']
   try:result=super()._say(*args,**kwargs)
   except BaseException:
    if delivery:pending.abort()
    raise
   if delivery:pending.finish()
   return result
  def _absorb(self,text):
   cache.append('monologue.vocabulary',dict(text=text,stamp=hub.clock.stamp()))
   for word in tokens(text):
    if word not in self.word_set:self.word_set.add(word);self.words.append(word)
   # The recent working vocabulary is bounded; the full original text is retained.
   if len(self.words)>1024:self.words=self.words[-1024:];self.word_set=set(self.words)
   model.archive.set_json('language.context','voice_words',self.words)
  def _queue_line(self,text,kind,auth,leak=None,from_residue=False,depth=0):
   if not text:return
   if self.root_pull>0 and self.root_token and self.root_token not in text:text=self.root_token+' '+text
   value=(text,kind,'authority' if auth=='authority' else 'unauthority',leak,from_residue,max(0,int(depth)))
   cache.append('monologue.formed',dict(stamp=hub.clock.stamp(),text=text,kind=kind,authority=value[2]))
   self.pending.append(value)
 class LearningValuation(BaseValuation):
  def _on(self,bus,event):
   if event['name']!='progression_feedback':return super()._on(bus,event)
   payload=event.get('payload',{})
   if model.text_learning is None or not model.text_learning.claim_feedback(payload):return
   body=self.score('residue',dict(payload,authority='unauthority'))
   body.update(id='text:'+payload['id'],derived_learning=True,independent_outside_evidence=False,
    semantic_verification='unknown',learning_ref=payload.get('source_ref'),source_stamp=payload.get('source_stamp'),world_stamp=payload.get('world_stamp'))
   bus.publish('valuation',body)
  async def run(self,bus,stop):
   class TextBus:
    def subscribe(_self,*names):return bus.subscribe(*dict.fromkeys((*names,'progression_feedback')))
    def __getattr__(_self,name):return getattr(bus,name)
   return await super().run(TextBus(),stop)
  def score(self,name,payload,now=None):
   body=super().score(name,payload,now)
   values=payload.get('progression')
   if name!='private_thought' and isinstance(values,dict):
    gain=sum(unit(values.get(value,0)) for value in VALUES)*.025
    body['worth']=round(unit(body['worth']+gain),4);body['show']=body['worth']>=body['threshold'];body['progression']=dict(values)
    if body['show']:self.last_external=ns['time'].monotonic() if now is None else now
   return body
 def formulate(rng,stems,words,cut):
  # Native pacing is unchanged. Content grows from encountered words/transitions,
  # rather than repeatedly choosing from the fixed THOUGHTS/DREAMS sentence banks.
  return model.compose(rng,words) or '…'
 ns.update(EventBus=ProgressBus,MonologueAgent=OpenMonologue,ValuationAgent=LearningValuation,utter=formulate)
 return model

"""Explicit adapters around the complete native hive; reception is not confirmation.

The neural registry owns eligibility. These adapters retain native agents and
their pacing while carrying bounded sensory lineage through their existing paths.
"""
import asyncio,copy,json,math,re,uuid
from world_clock import validate_stamp

NEW_GENES=('neural_gain','grounding_strictness','grounding_window')
NEW_AGENTS=('neural','grounding')
TAG_KEYS=('neural','neural_vector','grounding','world_stamp','vision')

def _json_copy(value,limit=32768):
    raw=json.dumps(value,allow_nan=False,ensure_ascii=False,separators=(',',':'))
    if len(raw.encode())>limit:raise ValueError('neural metadata exceeds allowance')
    return json.loads(raw)

def _neural(payload):return isinstance(payload,dict) and isinstance(payload.get('neural'),dict)

def _tag(target,source,replay=False,dreamed=False):
    for key in TAG_KEYS:
        if key in source:target[key]=_json_copy(source[key])
    if _neural(target):
        target['semantic_verification']='unknown'
        if replay or dreamed:
            target['neural']['replay']=True
            target['authority']='unauthority'
            if replay:target['replayed']=True
            if dreamed:target['dreamed']=True;target['neural']['dreamed']=True
    return target

def _trace(value):
    if not isinstance(value,dict) or value.get('schema')!='ALIEN_SENSORY_TRACE_V1':return None
    if value.get('semantic_verification')!='unknown' or value.get('dreamed') is not False or value.get('replay') or value.get('expression_ids')!=[]:return None
    if not isinstance(value.get('spike_id'),str) or re.fullmatch('[0-9a-f]{32}',value['spike_id']) is None:return None
    if not isinstance(value.get('mirror_ref'),str) or not value['mirror_ref'].startswith('mirror:n:') or len(value['mirror_ref'])>40:return None
    if value.get('claim')!='measured_sensory_receipt' or value.get('confirmation')!='internal_mirror_and_approbation' or value.get('independent_outside_evidence') is not False:return None
    if value.get('source_scope') not in ('self','mixed_unknown'):return None
    if type(value.get('held')) not in (int,float) or not math.isfinite(value['held']) or not .55<=value['held']<=1:return None
    if not isinstance(value.get('candidate_digest'),str) or re.fullmatch('[0-9a-f]{64}',value['candidate_digest']) is None:return None
    try:
        from neural_types import digest
        from vision_origin import validate_vision
        world=validate_stamp(value.get('world_stamp'));source=validate_stamp(value.get('source_stamp'));grounding=value.get('grounding')
        if world is None or source is None or not isinstance(grounding,dict):return None
        required={'stamp','ticks_since_similar','signature','chain','approbation','continuity','load','sleep','dream','mirror_hash','quality','strictness','neural_gain','required_quality','clarity','required_clarity','duration_basis','context_window'}
        if not required<=set(grounding) or grounding['duration_basis']!='admitted_native_ticks':return None
        ground_stamp=validate_stamp(grounding.get('stamp'));vision=validate_vision(value.get('vision'))
        if ground_stamp is None or any(world[key]!=source[key] or source[key]!=ground_stamp[key] for key in ('world_id','segment_id')):return None
        if not source['tick']<=ground_stamp['tick']<=world['tick'] or vision['world_id']!=world['world_id']:return None
        if value['source_scope']!=('mixed_unknown' if vision['source']=='desktop' else 'self'):return None
        if not isinstance(value.get('grounding_hash'),str) or value['grounding_hash']!=digest(grounding):return None
        if grounding.get('sleep') is not False or grounding.get('dream') is not False:return None
        if not isinstance(grounding['chain'],list) or len(grounding['chain'])>8 or not isinstance(grounding['approbation'],list) or len(grounding['approbation'])>4:return None
        if not isinstance(grounding['continuity'],str) or re.fullmatch('[0-9a-f]{6}',grounding['continuity']) is None:return None
        if not isinstance(grounding['load'],dict) or grounding['load'].get('known') is not True:return None
        duration=grounding.get('ticks_since_similar');window=grounding.get('context_window')
        if type(duration) is not int or type(window) is not int or not 4<=window<=64 or not 0<duration<=window:return None
        for key in ('quality','strictness','neural_gain','required_quality','clarity','required_clarity'):
            if type(grounding[key]) not in (int,float) or not math.isfinite(grounding[key]) or not 0<=grounding[key]<=1:return None
        quality_threshold=.45+.3*grounding['strictness']-.1*(grounding['neural_gain']-.5)
        clarity_threshold=.45-.1*grounding['neural_gain']
        if abs(grounding['required_quality']-quality_threshold)>1e-6 or abs(grounding['required_clarity']-clarity_threshold)>1e-6:return None
        if grounding['quality']<grounding['required_quality'] or grounding['clarity']<grounding['required_clarity']:return None
        return _json_copy(value,16384)
    except (ValueError,TypeError):return None

class _Queue:
    def __init__(self,queue,transform):self.queue=queue;self.transform=transform
    async def get(self):return self.transform(await self.queue.get())
    def get_nowait(self):return self.transform(self.queue.get_nowait())
    def __getattr__(self,name):return getattr(self.queue,name)

class _Bus:
    def __init__(self,bus,extra=(),transform=None,publish=None):self.bus=bus;self.extra=extra;self.transform=transform;self.republish=publish
    def subscribe(self,*names):
        queue=self.bus.subscribe(*dict.fromkeys((*names,*self.extra)))
        return _Queue(queue,self.transform) if self.transform else queue
    def publish(self,name,payload=None):
        if self.republish:return self.republish(name,dict(payload or {}))
        return self.bus.publish(name,payload)
    def unsubscribe(self,queue):return self.bus.unsubscribe(queue.queue if isinstance(queue,_Queue) else queue)
    def __getattr__(self,name):return getattr(self.bus,name)

def install_native(ns):
    """Called once by the active complete source, before any agent is created."""
    if ns.get('neural_enabled'):return
    ns['GENE_NAMES']=tuple(ns['GENE_NAMES'])+NEW_GENES
    ns['CORE_NAMES']=tuple(ns['CORE_NAMES'])+NEW_AGENTS
    ns['NEURAL_BASE_AGENT']=ns['Agent'];ns['neural_enabled']=True;ns['NEURAL_INTERFACE_ENABLED']=True
    for name in NEW_AGENTS:ns['PARAM_SEED'][name]={'fault':0.,'tempo':1.};ns['FAULT_CAP'][name]=0.
    BaseSupervisor=ns['Supervisor'];BaseTick=ns['TickAgent']
    class Supervisor(BaseSupervisor):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            system=ns.get('NEURAL_SYSTEM')
            if system is not None:system.supervisor=self
        def make_agent(self,name,params):
            if name in NEW_AGENTS:
                cls=ns.get('NeuralAgent' if name=='neural' else 'GroundingAgent')
                if cls is None:raise RuntimeError('neural agents must be bound before native startup')
                return cls(params,self.genome.copy())
            return super().make_agent(name,params)
        def flush(self):
            super().flush()
            for name in NEW_AGENTS:
                slot=self.slots.get(name);flush=getattr(slot['agent'],'flush',None) if slot else None
                if flush is not None:flush()
    class TickAgent(BaseTick):
        async def run(self,bus,stop):
            self._queue=bus.subscribe('heartbeat','residue','dream_begin','cache_written','cache_recalled',*ns['BALANCE_EVENTS'],'private_thought','generation_complete','mutation_applied','enter_sleep','wake','shutdown')
            while not stop.is_set():
                self.beat(bus);evt=await ns['wait_evt'](self._queue,self.pace(.2/self.tempo))
                if evt is None:continue
                name=evt['name'];payload=evt.get('payload') or {}
                if name=='shutdown':return
                if name in ('enter_sleep','wake'):self.notice_sleep(name,payload);continue
                if name=='heartbeat':
                    if payload.get('agent') not in (*NEW_AGENTS,*ns.get('NON_TICK_HEARTBEATS',())):self.note_heartbeat(bus)
                    continue
                self.note_event(name,payload)
    ns.update(Supervisor=Supervisor,TickAgent=TickAgent)
    from neural_core import make_agents
    ns.update(make_agents(ns))

def bind_native(ns,system):
    """Bind after cache, semantic and progression adapters; before amain starts."""
    if ns.get('_neural_native_bound'):raise ValueError('native neural adapters are already bound')
    ns['_neural_native_bound']=True;ns['NEURAL_SYSTEM']=system
    receipts={};lineage={}
    def remember_ref(ref,meta):
        lineage[ref]=_json_copy(meta)
        while len(lineage)>128:lineage.pop(next(iter(lineage)))
    def canonical(payload,target):
        if not _neural(payload) or not system.can_promote(payload,target):return None
        row=system.canonical(payload['neural'].get('spike_id'))
        return row if isinstance(row,dict) and system.can_promote(row,target) else None
    def matched(payload,target):
        ref=payload.get('ref');saved=receipts.get(ref)
        return bool(saved and _neural(payload) and saved.get('spike_id')==payload['neural'].get('spike_id') and saved.get('grounding_hash')==payload['neural'].get('grounding_hash') and canonical(payload,target))
    old_normalize=ns['normalize_root'];old_empty=ns['empty_root'];old_link=ns['_feeling_link'];old_cache_item=ns['_cache_item'];old_stamp=ns['stamp_authority'];old_offer=ns['dialogue_offer']
    def empty_root():return dict(old_empty(),sensory_version=1,sensory_traces=[])
    def normalize_root(raw):
        result=old_normalize(raw);traces=[]
        if isinstance(raw,dict) and type(raw.get('sensory_version',1)) is int and raw.get('sensory_version',1)==1:
            for item in list(raw.get('sensory_traces') or [])[-32:]:
                clean=_trace(item)
                if clean is not None:traces.append(clean)
        result.update(sensory_version=1,sensory_traces=traces);return result
    def feeling_link(raw):
        result=old_link(raw)
        if result is not None and _neural(raw):_tag(result,raw)
        return result
    def cache_item(raw):
        result=old_cache_item(raw)
        if result is not None and _neural(raw):_tag(result,raw)
        return result
    def stamp_authority(name,payload):
        if name=='vector_match' and any(_neural(hit) for hit in payload.get('hits',[]) if isinstance(hit,dict)):
            body=dict(payload);legacy=[hit for hit in body.get('hits',[]) if isinstance(hit,dict) and not _neural(hit)]
            if not legacy:body['authority']='unauthority'
            elif body.get('authority') not in ('authority','unauthority'):
                body['authority']=old_stamp(name,dict(body,hits=legacy)).get('authority','unauthority')
            return old_stamp(name,body)
        return old_stamp(name,payload)
    def dialogue_offer(continuity,residues,mirrors,chains,fingerprint,neural_summary=None):
        base=old_offer(continuity,residues,mirrors,chains,fingerprint)
        if neural_summary is None:return base
        safe={str(k)[:24]:v for k,v in list(neural_summary.items())[:8] if type(v) in (int,float) and math.isfinite(v)} if isinstance(neural_summary,dict) else {}
        addition=' neural_summary:'+json.dumps(safe,separators=(',',':'),sort_keys=True)[:96]
        return base[:max(0,240-len(addition))]+addition if safe else base
    ns.update(empty_root=empty_root,normalize_root=normalize_root,_feeling_link=feeling_link,_cache_item=cache_item,stamp_authority=stamp_authority,dialogue_offer=dialogue_offer)
    BaseMirror=ns['MirrorAgent'];BaseFeeling=ns['FeelingAgent'];BaseRoot=ns['LLMDialogueAgent'];BaseVector=ns['VectorAgent'];BaseMemory=ns['VectorMemory'];BaseCache=ns['CacheAgent'];BaseValuation=ns['ValuationAgent'];BaseDream=ns['DreamAgent'];BasePrivate=ns['PrivateThoughtAgent'];BaseMonologue=ns['MonologueAgent'];BaseFeedback=ns['FeedbackAgent'];BaseLoad=ns['LoadAgent']
    class MirrorAgent(BaseMirror):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self._neural_pending=[]
        def note(self,bus,name,payload):
            if name in ('eye_sensory','neural_spike'):return True
            if name=='situated_spike':
                row=canonical(payload,'mirror')
                chance=ns['mirror_chance_of'](self.genome)
                if row is None or chance<=0 or self.rng.random()>=chance:return True
                ref='mirror:n:'+uuid.uuid4().hex[:30]
                self._neural_pending.append(dict(due=self.tick+ns['mirror_delay_ticks'](self.genome,self.sleeping,self.dreaming),ref=ref,payload=row))
                self._neural_pending=sorted(self._neural_pending,key=lambda item:float(item['payload'].get('worth',0)),reverse=True)[:8]
                return True
            if _neural(payload) and name in ('residue','fragment_ready','dreamed_input','valuation'):return True
            return super().note(bus,name,payload)
        def _release(self,bus,tick):
            due=[item for item in self._neural_pending if item['due']<=tick];self._neural_pending=[item for item in self._neural_pending if item['due']>tick]
            for item in due:
                row=canonical(item['payload'],'mirror')
                if row is None or self.sleeping or self.dreaming:continue
                meta=system.register_mirror(row,item['ref'])
                if not isinstance(meta,dict):continue
                receipts[item['ref']]=_json_copy(meta)
                while len(receipts)>64:receipts.pop(next(iter(receipts)))
                token=ns['mirror_token'](row.get('label','')) or 'sense:'+str(row['neural']['spike_id'])[:16]
                body=_tag(dict(text=token,ref=item['ref'],source='neural',transform='situated',tick=int(tick),mirror=True,authority='authority',worth=max(.62,float(row.get('worth',.62))),confidence=0.,semantic_verification='unknown'),row)
                body['neural'].update(meta);remember_ref(item['ref'],body['neural']);bus.publish('mirror_truth',body);self.events.append('mirror_truth')
                self.refs.append(dict(source='neural',tick=int(tick),ref=item['ref'],transform='situated'));self.refs=self.refs[-8:]
            return super()._release(bus,tick)
        async def run(self,bus,stop):return await super().run(_Bus(bus,('situated_spike',)),stop)
    class FeelingAgent(BaseFeeling):
        def _stimulus(self,name,payload):
            if name in ('eye_sensory','neural_spike'):return None
            if name=='situated_spike':
                row=canonical(payload,'attraction')
                if row is None:return None
                ref='neur:'+str(row['neural']['spike_id'])[:32];remember_ref(ref,row['neural'])
                return ref,.18*self._gain(),0.,'neural',float(row.get('worth',0))
            if _neural(payload):
                if name not in ('mirror_truth','valuation') or not matched(payload,'attraction'):return None
                remember_ref(payload['ref'],payload['neural'])
            elif str(payload.get('ref','')).startswith('mirror:n:'):return None
            return super()._stimulus(name,payload)
        def _public_links(self):
            rows=super()._public_links()
            for row in rows:
                meta=lineage.get(row.get('ref'))
                if meta:row['neural']=_json_copy(meta);row['semantic_verification']='unknown'
            return rows
        def _body(self,link,**kwargs):
            body=super()._body(link,**kwargs);meta=lineage.get(link.get('ref'))
            if meta:body['neural']=_json_copy(meta);body['semantic_verification']='unknown'
            return body
        async def run(self,bus,stop):return await super().run(_Bus(bus,('situated_spike',)),stop)
    class LLMDialogueAgent(BaseRoot):
        # A supervisor can replace the dialogue agent while a fence is pending.
        # Its one root and ordered approval queue belong to this installation.
        _archive_state=dict(root=None,queue=[],pending=None,error=None)
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            state=self._archive_state
            if state['root'] is None:state['root']=self.root
            else:self.root=state['root']
            self.archive_error=state['error']
            if hasattr(system,'root_writers'):system.root_writers[:]=[self]
        def _root_waiting(self):
            state=self._archive_state
            return bool(state['pending'] or state['queue'])
        def flush(self):
            if self._root_waiting():self._dirty=True;return
            if getattr(ns.get('content_cache'),'background_writer',False):
                from content_cache import CacheBusy
                try:self._save_current()
                except CacheBusy:self._dirty=True
                except OSError as error:
                    self._dirty=True;self._archive_state['error']=self.archive_error=type(error).__name__+': '+str(error)[:160]
                return
            return super().flush()
        def _save_current(self):
            # Native save_root intentionally swallows storage errors. This
            # asynchronous owner needs a real acceptance result for its merge.
            ns['content_cache'].set_json('native.state','root_truth.json',dict(v=1,**ns['normalize_root'](self.root)));self._dirty=False
        def _root_failed(self,item,error):
            state=self._archive_state
            if state['pending'] is not item:return
            system.cancel_trace(item['token']);state['pending']=None
            for queued in state['queue']:system.cancel_trace(queued['token'])
            state['queue'].clear();state['error']=self.archive_error=type(error).__name__+': '+str(error)[:160]
            # The staged head was never public in RAM. If a post-commit readback
            # failed, enqueue the current, unconfirmed root as the next head.
            try:self._save_current()
            except (OSError,ValueError):pass
        def _start_root(self):
            from content_cache import CacheBusy
            state=self._archive_state;cache=ns['content_cache']
            if state['pending'] or not state['queue'] or state['error']:return
            item=state['queue'].pop(0);state['pending']=item
            proposed=copy.deepcopy(self.root);proposed['sensory_version']=1
            proposed['sensory_traces']=(list(proposed.get('sensory_traces',[]))+[item['trace']])[-32:]
            proposed=dict(v=1,**ns['normalize_root'](proposed))
            def failed(error):self._root_failed(item,error)
            def complete():
                if state['pending'] is not item:return
                try:
                    saved=cache.read_committed_json('native.state','root_truth.json')
                    if not any(row==item['trace'] for row in (saved or {}).get('sensory_traces',[])):raise OSError('sensory root trace was not committed')
                    if not system.complete_trace(item['token'],item['trace']):raise ValueError('sensory root reservation refused')
                except (OSError,ValueError) as error:failed(error);return
                self.root['sensory_version']=1
                self.root['sensory_traces']=(list(self.root.get('sensory_traces',[]))+[item['trace']])[-32:]
                # Merge into the current root, preserving ordinary mutations
                # that happened while the private proposal was on disk.
                self._dirty=True;self._emit_delta();merge()
            def merge():
                if state['pending'] is not item:return
                try:self._save_current()
                except CacheBusy:
                    try:cache.after_flush(merge,failed)
                    except (OSError,ValueError) as error:failed(error)
                    return
                except (OSError,ValueError) as error:failed(error);return
                state['pending']=None;self._start_root()
            def stage():
                if state['pending'] is not item:return
                try:cache.stage_json('native.state','root_truth.json',proposed)
                except CacheBusy:
                    try:cache.after_flush(stage,failed)
                    except (OSError,ValueError) as error:failed(error)
                    return
                except (OSError,ValueError) as error:failed(error);return
                try:cache.after_flush(complete,failed)
                except (OSError,ValueError) as error:failed(error)
            stage()
        def _emit_delta(self):
            from neural_types import digest
            key=digest(self.root)
            if key==getattr(self,'_neural_root_hash',None):return
            self._neural_root_hash=key;bus=getattr(system,'bus',None)
            if bus is not None:bus.publish('root_truth_delta',dict(root_hash=key,mirrors=len(self.root.get('mirrors',[])),sensory_traces=len(self.root.get('sensory_traces',[])),slices=len(self.root.get('slices',[])),chains=len(self.root.get('chains',[])),becoming=float(self.root.get('becoming',0)),authority='unauthority',semantic_verification='unknown'))
        def _mark(self):
            super()._mark();self._emit_delta()
        def _note_mirror(self,payload):
            if _neural(payload) or str(payload.get('ref','')).startswith('mirror:n:'):
                if not matched(payload,'mirror'):return
                super()._note_mirror(payload)
                for row in self.pending:
                    if row['ref']==payload['ref']:_tag(row,payload)
                return
            return super()._note_mirror(payload)
        def _admit(self,payload):
            ref=str(payload.get('ref',''))
            if not _neural(payload) and not ref.startswith('mirror:n:'):return super()._admit(payload)
            if not ref.startswith('mirror:n:') or not matched(payload,'root'):return
            if not any(row.get('ref')==ref and _neural(row) for row in self.pending):return
            try:held=float(payload.get('held',0))
            except (TypeError,ValueError):return
            cache=ns.get('content_cache')
            if getattr(cache,'background_writer',False):
                state=self._archive_state
                if state['error'] or len(state['queue'])>=32:return
                reserved=system.reserve_trace(ref,held)
                if reserved is None:return
                token,trace=reserved;trace=_trace(trace)
                if trace is None:system.cancel_trace(token);return
                state['queue'].append(dict(token=token,trace=trace));self._start_root();return
            trace=_trace(system.confirm_mirror(ref,held))
            if trace is None or any(item.get('mirror_ref')==ref for item in self.root.get('sensory_traces',[])):return
            previous=copy.deepcopy(self.root)
            self.root['sensory_version']=1;self.root['sensory_traces']=(list(self.root.get('sensory_traces',[]))+[trace])[-32:]
            try:
                self.flush()
                cache=ns.get('content_cache')
                if cache is not None:cache.flush()
                saved=ns['load_root'](self.path)
                if not any(row.get('mirror_ref')==ref for row in saved.get('sensory_traces',[])):raise OSError('sensory root trace was not stored')
                if not system.commit_trace(trace):raise ValueError('sensory trace commit refused')
            except (OSError,ValueError):
                self.root=previous
                self.flush()
                return
            self._dirty=False
            self._emit_delta()
    class VectorMemory(BaseMemory):
        def load(self,path):
            super().load(path)
            try:
                raw=json.loads(path.read_text()).get('items',[])[:ns['MAX_VECTORS']]
                valid=[row for row in raw if isinstance(row,dict) and isinstance(row.get('label'),str) and isinstance(row.get('vec'),list) and len(row['vec'])==ns['DIM']]
                for item,row in zip(self.items,valid):
                    if _neural(row):_tag(item,row);item.update(authority='unauthority',confidence=0.)
            except (OSError,ValueError,TypeError):pass
        def nearest(self,vec,k=3,window=None):
            items=self.items[-int(window):] if window and window>0 else self.items
            if len(vec)==128:
                ranked=[(sum(a*b for a,b in zip(vec,row['neural_vector'])),row) for row in items if isinstance(row.get('neural_vector'),list) and len(row['neural_vector'])==128]
            else:ranked=[(ns['dot'](vec,row['vec']),row) for row in items if len(row.get('vec',[]))==len(vec)]
            output=[]
            for score,row in sorted(ranked,key=lambda pair:pair[0],reverse=True)[:k]:
                hit={key:copy.deepcopy(row.get(key)) for key in ('label','kind','genes','confidence','authority','context_ref','input_id','source','origin','vision')};hit['score']=round(score,4)
                if _neural(row):_tag(hit,row);hit.update(authority='unauthority',confidence=0.)
                output.append(hit)
            return output
    class VectorAgent(BaseVector):
        def _neural_store(self,payload,kind):
            row=canonical(payload,'cache')
            if row is None:return False
            text=str(row.get('text') or row.get('label') or '')
            if not text:return False
            before=self.memory.items[-1] if self.memory.items else None
            self.memory.add(text,ns['compose_vector'](text,None),kind,None,0.,'unauthority')
            if self.memory.items and self.memory.items[-1] is not before:
                _tag(self.memory.items[-1],row);self.memory.items[-1].update(authority='unauthority',confidence=0.)
                return True
            return False
        async def run(self,bus,stop):
            def take(event):
                name=event['name'];body=event.get('payload') or {}
                if name=='situated_spike':self._neural_store(body,'neural');return dict(event,name='neural_consumed')
                if _neural(body):
                    if name=='mirror_truth' and matched(body,'cache'):self._neural_store(body,'neural_mirror')
                    return dict(event,name='neural_consumed')
                return event
            return await super().run(_Bus(bus,('situated_spike',),take),stop)
    class CacheAgent(BaseCache):
        def _snapshot(self,kind,payload,residue_id):
            entry=super()._snapshot(kind,payload,residue_id)
            if _neural(payload):_tag(entry,payload)
            return entry
        def _public(self,item):
            body=super()._public(item)
            if _neural(item):_tag(body,item)
            return body
        def _consider(self,bus,event):
            name=event['name'];body=event.get('payload') or {}
            if name in ('eye_sensory','neural_spike'):return
            if name=='situated_spike':
                row=canonical(body,'cache')
                if row is not None:self._maybe_write(bus,'residue',row,.65,residue_id=str(row.get('id','')))
                return
            if _neural(body) and name in ('valuation','mirror_truth','residue') and canonical(body,'cache') is None:return
            return super()._consider(bus,event)
        def _publish_recall(self,bus,entry):
            if not _neural(entry):return super()._publish_recall(bus,entry)
            def publish(name,body):return bus.publish(name,_tag(body,entry,replay=True))
            return super()._publish_recall(_Bus(bus,publish=publish),entry)
        async def run(self,bus,stop):return await super().run(_Bus(bus,('situated_spike',)),stop)
    class ValuationAgent(BaseValuation):
        def score(self,name,payload,now=None):
            result=super().score(name,payload,now)
            if _neural(payload):_tag(result,payload);result['confidence']=0.
            return result
    class FeedbackAgent(BaseFeedback):
        def _on_valuation(self,bus,payload):
            if not _neural(payload):return super()._on_valuation(bus,payload)
            def publish(name,body):return bus.publish(name,_tag(body,payload,replay=True))
            return super()._on_valuation(_Bus(bus,publish=publish),payload)
    class DreamAgent(BaseDream):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self._sensory_ancestry=[]
        async def run(self,bus,stop):
            def take(event):
                if event['name']=='situated_spike':
                    body=event.get('payload') or {};row=canonical(body,'attraction')
                    if row is not None:
                        self._sensory_ancestry=(self._sensory_ancestry+[row])[-4:];self._remember(str(row.get('text') or row.get('label') or ''),False)
                    return dict(event,name='neural_context')
                return event
            def publish(name,body):
                if name=='dream_scene' and self._sensory_ancestry:
                    _tag(body,self._sensory_ancestry[-1],replay=True,dreamed=True)
                    body['neural']['ancestry']=[row['neural']['spike_id'] for row in self._sensory_ancestry]
                return bus.publish(name,body)
            return await super().run(_Bus(bus,('situated_spike',),take,publish),stop)
    class PrivateThoughtAgent(BasePrivate):
        def notice(self,bus,name,payload,now=None):
            if name in ('neural_spike','dreamed_neural_activity'):
                at=ns['time'].monotonic() if now is None else now
                if not self.load_pause and at>=self.next_at:
                    self._publish(bus,'a spike has not found its ground' if name=='neural_spike' else 'the eye lingered in a possible field',0.,'');self.next_at=at+4/max(self.tempo,.2)
                return True
            if name=='situated_spike':
                if canonical(payload,'attraction') is not None and not self.load_pause and not self.sleeping:
                    at=ns['time'].monotonic() if now is None else now
                    if at>=self.next_at:self._publish(bus,'a sensation found its context',0.,'');self.next_at=at+4/max(self.tempo,.2)
                return True
            return super().notice(bus,name,payload,now)
        async def run(self,bus,stop):return await super().run(_Bus(bus,('situated_spike','neural_spike','dreamed_neural_activity')),stop)
    class MonologueAgent(BaseMonologue):
        async def run(self,bus,stop):
            def take(event):
                if event['name'] in ('neural_spike','dreamed_neural_activity'):
                    now=ns['time'].monotonic()
                    if not self.load_high and not self.sleeping and now>=getattr(self,'_raw_neural_next',0):
                        self._queue_line('a spike arrived ungrounded' if event['name']=='neural_spike' else 'the eye lingered in a possible field','aside','unauthority',False);self._raw_neural_next=now+8
                    return dict(event,name='neural_context')
                if event['name']=='situated_spike':
                    row=canonical(event.get('payload') or {},'attraction')
                    tick=(row.get('world_stamp') or {}).get('tick') if row else None
                    if row is not None and type(tick) is int and tick>=getattr(self,'_neural_said_tick',-32)+32 and not self.load_high and not self.sleeping:
                        self._queue_line('the sensed field found a place in this tick','aside','unauthority',False);self._neural_said_tick=tick
                    return dict(event,name='neural_context')
                return event
            return await super().run(_Bus(bus,('situated_spike','neural_spike','dreamed_neural_activity'),take),stop)
    class LoadAgent(BaseLoad):
        async def run(self,bus,stop):
            self._neural_pressure_until=None;self._neural_tick=0
            def take(event):
                name=event['name'];body=event.get('payload') or {}
                if name=='neural_pressure':
                    stamp=body.get('world_stamp') or {};tick=stamp.get('tick')
                    if type(tick) is int:
                        prior=self._neural_pressure_until;self._neural_pressure_until=tick+8
                        identity=(stamp.get('world_id'),stamp.get('segment_id'))
                        if prior is None or identity!=getattr(self,'_neural_pressure_identity',None) or tick>=getattr(self,'_neural_pressure_sent',-4)+4:
                            self.events.append('neural_pressure');self._neural_pressure_sent=tick;self._neural_pressure_identity=identity
                            bus.publish('neural_optional_load',dict(high=True,expires_tick=tick+8,spikes_per_tick=float(body.get('spikes_per_tick',0)),world_stamp=stamp,authority='unauthority'))
                    return dict(event,name='neural_load_consumed')
                if name=='tick':
                    tick=body.get('tick');self._neural_tick=tick if type(tick) is int else self._neural_tick
                    if self._neural_pressure_until is not None and self._neural_tick>=self._neural_pressure_until:
                        self._neural_pressure_until=None;bus.publish('neural_optional_load',dict(high=False,expires_tick=self._neural_tick,spikes_per_tick=0.,authority='unauthority'))
                return event
            return await super().run(_Bus(bus,('neural_pressure',),take),stop)
    ns.update(MirrorAgent=MirrorAgent,FeelingAgent=FeelingAgent,LLMDialogueAgent=LLMDialogueAgent,VectorMemory=VectorMemory,VectorAgent=VectorAgent,CacheAgent=CacheAgent,ValuationAgent=ValuationAgent,FeedbackAgent=FeedbackAgent,DreamAgent=DreamAgent,PrivateThoughtAgent=PrivateThoughtAgent,MonologueAgent=MonologueAgent,LoadAgent=LoadAgent)
    ns['NEURAL_MIRROR_RECEIPTS']=receipts
    return system

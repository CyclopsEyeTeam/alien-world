"""Main-owned native tick admission and narrow local control; no new hive clock."""
import uuid,json,asyncio,copy
from pathlib import Path
from collections import deque,OrderedDict
from world_clock import WorldClock,tick_distance
from ingress import TimeBuffer,Busy
from semantics import Contexts,memory_class,BufferedSemanticConsumer
from prep_process import Preparer,read_packet,write_packet

class Hub:
    def __init__(self,ns,directory,cache=None):
        self.ns=ns;self.cache=cache;self.directory=ns['Path'](directory) if cache is not None else Path(directory);self.runtime=uuid.uuid4().hex;self.clock=WorldClock(world_id=cache.world_id if cache is not None else None);self.contexts=Contexts(self.runtime)
        self.buffer=TimeBuffer(runtime=self.runtime,max_bytes=14*1024*1024)
        self.api_inputs=OrderedDict()
        self.api_language=None
        self.last_api_receipt=None
        self.eye_pending=None;self.eye_last=OrderedDict();self.last_eye_receipt=None
        self.latest_art=None;self.pending_art=None;self.art_sequence=0
        self.buffer.receipt_handler=self._buffer_receipt
        self.preparer=Preparer(self.directory);self.consumer=None;self.control=None;self.loop=None;self.outbox=deque();self.pump_task=None;self.last_control=0;self.health_count=0;self.last_receipt=None;self.prep_error=None
        self.cache_agent=None;self.contexts.references=self.live_context_references
        self.archive_flush_error=None
        path=self.directory/'world-clock.json'
        try:
            if path.stat().st_size<8192:
                saved=json.loads(path.read_text());from world_clock import validate_stamp
                stamp=validate_stamp(saved.get('stamp'))
                if stamp:
                    self.clock.world_id=stamp['world_id'];self.clock.segment_id=stamp['segment_id'];self.clock.tick=stamp['tick'];self.clock.period=stamp['period']
        except (OSError,ValueError,TypeError):pass
        try:
            from world_clock import validate_stamp
            path=self.directory/'temporal.json'
            if path.stat().st_size<1024*1024:
                rows=json.loads(path.read_text()).get('contexts',{})
                for ref,row in list(rows.items())[-self.contexts.limit:]:
                    if not isinstance(ref,str) or len(ref)>96 or not isinstance(row,dict):continue
                    saved_origin=row.get('origin');saved_vision=row.get('vision')
                    row=dict(stamp=validate_stamp(row.get('stamp')),kind=str(row.get('kind',''))[:32],input_id=str(row.get('input_id',''))[:96],source=str(row.get('source',''))[:256],material='not_restored')
                    if saved_origin:
                        from api_origin import validate_origin
                        row['origin']=validate_origin(saved_origin)
                    if saved_vision:
                        from vision_origin import validate_vision
                        row['vision']=validate_vision(saved_vision)
                    self.contexts.rows[ref]=row
        except (OSError,ValueError,TypeError,AttributeError):pass
        self.install()
    def live_context_references(self):
        refs=set()
        if self.consumer:refs.update(x.get('context_ref') for x in self.consumer.memory.items)
        if self.cache_agent:refs.update(x.get('context_ref') for x in self.cache_agent.entries)
        refs.update(x.get('consumer',{}).get('context_ref') for x in self.buffer.receipts.values())
        return refs-{None,''}
    def install(self):
        import contextvars
        vector_task=contextvars.ContextVar('candidate_vector_consumer',default=None)
        hub=self;ns=self.ns;BaseBus=ns['EventBus'];BaseVector=ns['VectorAgent'];BaseCache=ns['CacheAgent'];clean=ns['_cache_item'];bonus=ns['tick_distance_bonus']
        BaseMemory=memory_class(ns)
        class OriginMemory(BaseMemory):
            def add(self,*a,**kw):
                ref=self.pending_context;super().add(*a,**kw);context=hub.contexts.get(ref)
                if context and context.get('origin') and self.items and self.items[-1].get('context_ref')==ref:
                    self.items[-1].update(origin=context['origin'],confidence=0.,authority='unauthority')
                if context and context.get('vision') and self.items and self.items[-1].get('context_ref')==ref:
                    self.items[-1].update(vision=context['vision'],confidence=0.,authority='unauthority')
        ns['VectorMemory']=OriginMemory
        class LinkedBus(BaseBus):
            def subscribe(self,*names):
                queue=super().subscribe(*names);vector=vector_task.get()
                if vector is not None:
                    original=queue.get_nowait
                    def take():
                        event=original()
                        if vector_task.get() is vector:vector.memory.pending_context=event.get('payload',{}).get('context_ref')
                        return event
                    queue.get_nowait=take
                return queue
            def _emit(self,name,body):
                body=dict(body);changed=False
                if name=='tick':
                    if ns.get('_CONTINUOUS_WORLD'):
                        if hub.clock.tick is not None and body['tick']<hub.clock.tick:raise ValueError('Continuing world refuses backward tick')
                        if body.get('resumed'):body.update(delta=0,jump=0,discontinuity=False)
                    changed=hub.clock.observe(body['tick'],body.get('resumed',False));body['world_stamp']=hub.clock.stamp()
                    if changed and ns.get('_CONTINUOUS_WORLD'):
                        try:ns['atomic_write'](hub.directory/'world-clock.json',json.dumps({'stamp':hub.clock.stamp()}))
                        except (OSError,ValueError) as error:hub.archive_flush_error=type(error).__name__+': tick checkpoint unavailable'
                if name!='heartbeat' and name!='tick':
                    receipt=hub.contexts.add(hub.clock.stamp(),name,source=str(body.get('id') or body.get('vid') or '')[:256])
                    if isinstance(body.get('context_ref'),str):body['receipt_context_ref']=receipt
                    else:body['context_ref']=receipt
                super()._emit(name,body)
                if name=='art_ready' or (name=='svg_ready' and hub.cache is None):hub.capture_art(body)
                if name=='tick' and changed:
                    hub.admit(self)
                    if hub.cache is not None:
                        health=hub.archive_status()
                        if health is None or not health['failed'] and health['writer_alive']:
                            try:hub.cache.flush_if_due();hub.archive_flush_error=None
                            except (OSError,ValueError) as error:hub.archive_flush_error=type(error).__name__+': '+str(error)[:160]
        class LinkedVector(BaseVector):
            def __init__(self,*a,**kw):
                super().__init__(*a,**kw);hub.consumer=BufferedSemanticConsumer(ns,self.memory,hub.contexts)
            async def run(self,*a,**kw):
                token=vector_task.set(self)
                try:return await super().run(*a,**kw)
                finally:vector_task.reset(token)
            def _weight(self,payload,*a,**kw):
                self.memory.pending_context=payload.get('context_ref');return super()._weight(payload,*a,**kw)
        class LinkedCache(BaseCache):
            def __init__(self,*a,**kw):super().__init__(*a,**kw);hub.cache_agent=self
            def _snapshot(self,kind,payload,residue_id):
                item=super()._snapshot(kind,payload,residue_id)
                if isinstance(payload.get('context_ref'),str):item['context_ref']=payload['context_ref']
                context=hub.contexts.get(item.get('context_ref'))
                if context and context.get('vision'):item['vision']=context['vision']
                return item
            def _public(self,item):
                body=super()._public(item)
                if 'context_ref' in item:body['context_ref']=item['context_ref']
                context=hub.contexts.get(item.get('context_ref'))
                if context and context.get('origin'):body['origin']=context['origin']
                vision=hub.cache_vision(item,context)
                if vision:body['vision']=vision
                return body
            def lookup(self,query):
                body=dict(query);stamp=hub.clock.stamp()
                if 'context_ref' not in body and stamp is not None and self.current_tick==stamp['tick'] and body.get('tick')==stamp['tick']:
                    body['context_ref']=hub.contexts.add(stamp,'cache_query')
                return super().lookup(body)
            def _publish_recall(self,bus,entry):
                class RecallReceipt:
                    def publish(_self,name,payload):
                        if name=='cache_recalled':
                            payload=dict(payload,context_ref=entry.get('context_ref',''))
                            context=hub.contexts.get(entry.get('context_ref'))
                            if context and context.get('origin'):payload['origin']=context['origin']
                            vision=hub.cache_vision(entry,context)
                            if vision:payload['vision']=vision
                        return bus.publish(name,payload)
                return super()._publish_recall(RecallReceipt(),entry)
        def clean_link(item):
            result=clean(item)
            if result is not None and isinstance(item.get('context_ref'),str) and len(item['context_ref'])<=96:result['context_ref']=item['context_ref']
            if result is not None and item.get('vision'):
                from vision_origin import validate_vision
                try:result['vision']=validate_vision(item['vision'])
                except ValueError:pass
            return result
        def known_bonus(entry,query,echo):
            a=hub.contexts.get(entry.get('context_ref'));b=hub.contexts.get(query.get('context_ref'))
            if not a or not b or tick_distance(a['stamp'],b['stamp']) is None:return 0.0
            return bonus(dict(entry,tick=a['stamp']['tick']),dict(query,tick=b['stamp']['tick']),echo)
        ns.update(EventBus=LinkedBus,VectorAgent=LinkedVector,CacheAgent=LinkedCache,_cache_item=clean_link,tick_distance_bonus=known_bonus)
    def note_health(self):self.health_count+=1
    @staticmethod
    def cache_vision(item,context):
        from vision_origin import validate_vision
        value=context.get('vision') if context else item.get('vision')
        if value:
            try:return validate_vision(value)
            except ValueError:pass
        return None
    def _buffer_receipt(self,receipt):
        if self.eye_pending and receipt.get('id')==self.eye_pending['id'] and receipt.get('state')!='consumed':self.finish_eye(receipt)
    def finish_eye(self,receipt):
        if not self.eye_pending or self.eye_pending['id']!=receipt.get('id'):return
        value=self.eye_pending['vision'];self.eye_pending=None
        self.last_eye_receipt=dict(event='eye_receipt',runtime=self.runtime,world_id=self.clock.world_id,eye_runtime=value['eye_runtime'],source=value['source'],sequence=value['sequence'],epoch=value['epoch'],result=copy.deepcopy(receipt))
        self.send(self.last_eye_receipt)
    def capture_art(self,body):
        if self.cache is not None:
            from content_cache import read_reference
            try:
                ref=body.get('cache_ref');title=body.get('title','')
                if not isinstance(title,str):return
                png=read_reference(self.cache.path,ref,self.clock.world_id,kind='art.png',max_bytes=8*1024*1024)
                if png is None or not png.startswith(b'\x89PNG\r\n\x1a\n'):return
            except (OSError,ValueError):return
            record=dict(event='alien_art',runtime=self.runtime,world_id=self.clock.world_id,stamp=self.clock.stamp(),sequence=self.art_sequence+1,title=title[:80],cache_ref=ref)
            self._publish_art(record);return
        # Only the native publication's inline SVG is admitted. No path is read.
        svg=body.get('svg');title=body.get('title','')
        if not isinstance(svg,str) or not isinstance(title,str):return
        try:
            if not 1<=len(svg.encode('utf-8'))<=65536:return
            record=dict(event='alien_art',runtime=self.runtime,world_id=self.clock.world_id,stamp=self.clock.stamp(),sequence=self.art_sequence+1,title=title[:80],svg=svg)
            from ingress import packed
            # The optional get_art reply has a small wrapper around the event.
            if len(packed(dict(seq=2**64-1,ok=True,result=record)))>128*1024:return
        except (ValueError,UnicodeError):return
        self._publish_art(record)
    def _publish_art(self,record):
        self.art_sequence+=1;self.latest_art=record
        if not self.control:return
        # Unaccepted observations may coalesce; admitted input receipts never do.
        for index,queued in enumerate(self.outbox):
            if queued.get('event')=='alien_art':self.outbox[index]=record;self.pending_art=None;self.wakeup.set();return
        if len(self.outbox)<32:self.outbox.append(record);self.pending_art=None
        else:self.pending_art=record
        self.wakeup.set()
    def archive_status(self):
        """Memory-only writer health; a volatile receipt is not a durable ACK."""
        if self.cache is None or not getattr(self.cache,'background_writer',False):return None
        state=self.cache.statistics();reason=None
        if state['failed']:reason='Content archive writer failed; input is waiting'
        elif not state['writer_alive']:reason='Content archive writer is unavailable; input is waiting'
        elif self.archive_flush_error:reason='Content archive flush failed; input is waiting'
        elif (state['pending_bytes']*4>=state.get('max_pending_bytes',32*1024*1024)*3 or
              state['pending_records']*4>=state.get('max_pending_records',4096)*3):reason='Content archive is busy; input is waiting'
        return dict(state,admission_paused=reason is not None,admission_reason=reason,flush_error=self.archive_flush_error)
    def admit(self,bus):
        health=self.archive_status()
        if health is not None and health['admission_paused']:return
        text=getattr(getattr(self,'progression',None),'text_learning',None)
        first=next(iter(self.buffer.pending.values()),None)
        self.text_admission_waiting=bool(text is not None and first and first.get('origin') and not text.can_accept())
        if self.text_admission_waiting:return
        if self.consumer:
            receipt=self.buffer.on_tick(self.clock,self.consumer)
            if receipt:
                self.last_receipt=receipt;item=self.buffer.retained.get(receipt['id'])
                eye=self.eye_pending if self.eye_pending and self.eye_pending['id']==receipt['id'] else None
                request_id=next((rid for rid,ident in self.api_inputs.items() if ident==receipt['id']),None)
                alphabet=getattr(self,'alphabet',None)
                if alphabet is not None and item and not item.get('vision') and receipt['state']=='consumed':
                    provenance=dict(event='admitted_written',input_id=item['id'],source=item['source'],runtime=self.runtime,
                        source_stamp=copy.deepcopy(receipt['admitted_stamp']),admitted_stamp=copy.deepcopy(receipt['admitted_stamp']),
                        context_ref=receipt['consumer']['context_ref'])
                    if item.get('origin'):provenance['origin']=copy.deepcopy(item['origin'])
                    alphabet.offer('incoming',item['text'],provenance=provenance)
                pool=(getattr(self,'ns',None) or {}).get('SPARK_POOL')
                # Plain admitted words (owner input, named observers) are outside
                # charge. API and Eye items already charge through their residue.
                if pool is not None and item and receipt['state']=='consumed' and not item.get('vision') and not item.get('origin'):pool.charge(item['text'])
                if item and item.get('origin'):
                    # Direct semantic insertion already succeeded, at this native tick.
                    ref=receipt['consumer']['context_ref'];request_id=item['origin']['request_id']
                    bus.publish('residue',dict(id=item['id'],text=item['text'],label=item['label'],source='api-residue',authority='unauthority',confidence=0.,context_ref=ref,origin=item['origin']))
                if request_id:
                    self.last_api_receipt=dict(event='api_receipt',runtime=self.runtime,world_id=self.clock.world_id,request_id=request_id,result=receipt)
                    self.send(self.last_api_receipt)
                if eye and receipt['state']=='consumed':
                    ref=receipt['consumer']['context_ref']
                    event='eye_sensory' if self.ns.get('NEURAL_INTERFACE_ENABLED') else 'residue'
                    body=dict(id=receipt['id'],text=eye['text'],label=eye['label'],source='eye:'+eye['vision']['source'],authority='unauthority',confidence=0.,context_ref=ref,vision=eye['vision'])
                    if event=='eye_sensory':body.update(sensory=eye.get('sensory'),world_stamp=receipt['admitted_stamp'])
                    bus.publish(event,body)
                    self.finish_eye(receipt)
    def status(self):
        value=dict(runtime=self.runtime,clock=self.clock.stamp(),buffer=self.buffer.status(),last_receipt=self.last_receipt,last_api_receipt=self.last_api_receipt,last_eye_receipt=self.last_eye_receipt,preparer_pid=self.preparer.process.pid if self.preparer.process else None,preparation_error=self.prep_error)
        if hasattr(self,'profile'):value['worker_profile']=self.profile.snapshot()
        from remote_diagnostics import snapshot
        remote=snapshot(getattr(self,'remote_field_statistics',None))
        if remote:value['remote_field']=remote
        archive=self.archive_status()
        if archive is not None:value['archive']=archive
        neural=self.ns.get('NEURAL_SYSTEM')
        if neural is not None:value['neural_summary']=neural.summary()
        adaptor=getattr(getattr(self,'progression',None),'adaptor',None)
        if adaptor is not None:value['learning']=adaptor.summary()
        text=getattr(getattr(self,'progression',None),'text_learning',None)
        if text is not None:
            value.setdefault('learning',{}).update(text.summary())
            value['learning']['text_admission_waiting']=int(getattr(self,'text_admission_waiting',False))
        language=getattr(self,'language',None)
        if language is not None and hasattr(language,'status'):value['language']=language.status()
        if self.ns.get('_CONTINUOUS_WORLD'):
            saved=self.cache.get_json('world.lifecycle','v1',{})
            value['continuity']={'interruptions':saved.get('interruptions',0),'interrupted':saved.get('interrupted',False)}
        return value
    def language_authorization(self,mist_offer_id=None,request_id=None,claim=False):
        language=getattr(self,'language',None) or self.ns.get('LANGUAGE_SYSTEM')
        if language is None:
            if mist_offer_id is not None:raise ValueError('Native Mist offers are unavailable')
            return None
        from api_config import language_authorization
        stamp=self.clock.stamp()
        try:
            if mist_offer_id is not None:
                authorize=getattr(language,'mist_authorize',None)
                if not callable(authorize):raise ValueError('Native Mist offers are unavailable')
                value=authorize(mist_offer_id,request_id,claim=claim)
            else:value=language.api_authorize()
            grant=language_authorization(value,self.clock.world_id,stamp['segment_id'] if stamp else None)
            if grant['stamp']!=stamp:raise ValueError('language stamp is not current')
            if grant['mode']=='rehearsal':raise ValueError('alien language is rehearsing')
            return grant
        except (OSError,TypeError,ValueError,KeyError):raise ValueError('Alien language is waiting; no model request authorized') from None
    def handle(self,record):
        seq=record.get('seq')
        try:
            if type(seq) is not int or seq<=self.last_control or seq>=2**64:raise ValueError('duplicate or stale control sequence')
            self.last_control=seq;op=record.get('op')
            if op=='submit':
                if self.prep_error:raise ValueError('preparer unavailable; input not accepted')
                ident=self.buffer.submit(seq,record.get('text'),record.get('label',''),record.get('source',''),record.get('authority','unauthority'),self.clock.stamp())
                result=dict(id=ident,state='received',admitted_stamp=None)
            elif op in ('reserve_api','authorize_api','submit_api','cancel_api'):
                from api_origin import validate_origin
                import re
                rid=record.get('request_id')
                if record.get('runtime')!=self.runtime or record.get('world_id')!=self.clock.world_id or self.clock.stamp() is None or not isinstance(rid,str) or not re.fullmatch('[0-9a-f]{32}',rid):raise ValueError('stale or invalid API world')
                mist_id=record.get('mist_offer_id')
                if mist_id is not None and (not isinstance(mist_id,str) or not re.fullmatch('[0-9a-f]{32}',mist_id)):raise ValueError('invalid native Mist offer')
                if op=='reserve_api':
                    if self.prep_error or not self.consumer:raise ValueError('hive not ready')
                    health=self.archive_status()
                    if health is not None and health['admission_paused']:raise Busy(health['admission_reason'])
                    if rid in self.api_inputs:raise ValueError('duplicate API request')
                    grant=self.language_authorization(mist_id,rid)
                    self.buffer.reserve_api(rid)
                    if mist_id is not None:
                        try:grant=self.language_authorization(mist_id,rid,claim=True)
                        except BaseException:self.buffer.release_api(rid);raise
                    self.api_language=dict(request_id=rid,grant=grant,mist_offer_id=mist_id) if grant is not None else None
                    result=copy.deepcopy(grant) if grant is not None else True
                elif op=='authorize_api':
                    held=self.api_language
                    if self.buffer.api_reservation!=rid or not held or held['request_id']!=rid:raise ValueError('no matching language reservation')
                    if held.get('mist_offer_id')!=mist_id:raise ValueError('native Mist offer does not match the reservation')
                    initial=held['grant'];grant=self.language_authorization(mist_id,rid)
                    if grant is None or grant['stamp']['segment_id']!=initial['stamp']['segment_id']:raise ValueError('language timeline changed')
                    if initial['mode']=='dialogue' and grant['mode']!='dialogue':raise ValueError('alien register is no longer ready')
                    result=copy.deepcopy(grant)
                elif op=='submit_api':
                    value=validate_origin(record.get('origin'));held=self.api_language
                    held_mist=held.get('mist_offer_id') if held and held['request_id']==rid else None
                    if mist_id is not None and mist_id!=held_mist:raise ValueError('native Mist offer does not match the response')
                    if (value['provider']=='mist')!=(held_mist is not None):raise ValueError('response provider does not match the native Mist reservation')
                    if held_mist is not None:
                        if value['request_id']!=rid:raise ValueError('native Mist response belongs to another request')
                        # Readiness authorizes departure. A reply already in
                        # flight still returns as unknown residue while the
                        # hive sleeps or its register is developing again.
                    ident=self.buffer.submit_api(rid,seq,record.get('text'),value,self.clock.stamp())
                    if held_mist is not None:self.language.retire_mist(held_mist,rid)
                    self.api_language=None
                    self.api_inputs[rid]=ident
                    while len(self.api_inputs)>128:self.api_inputs.popitem(last=False)
                    result=dict(id=ident,state='received',admitted_stamp=None)
                else:
                    held=self.api_language
                    if held and held['request_id']==rid and mist_id is not None and held.get('mist_offer_id')!=mist_id:raise ValueError('native Mist offer does not match the cancellation')
                    result=self.buffer.release_api(rid) or self.buffer.cancel(self.api_inputs.get(rid))
                    if held and held['request_id']==rid:
                        if held.get('mist_offer_id') is not None:self.language.retire_mist(held['mist_offer_id'],rid)
                        self.api_language=None
            elif op=='query':result=self.consumer.query(record.get('text'),record.get('since')) if self.consumer else []
            elif op in ('submit_eye','cancel_eye'):
                from vision_origin import validate_vision,validate_summary,label
                if self.clock.stamp() is None or record.get('runtime')!=self.runtime or record.get('world_id')!=self.clock.world_id:raise ValueError('stale or invalid Eye world')
                if op=='submit_eye':
                    if self.prep_error or not self.consumer:raise ValueError('hive not ready')
                    if self.eye_pending is not None:raise Busy('Eye input is already waiting; retry later')
                    value=validate_vision(record.get('vision'));text=validate_summary(record.get('text'))
                    if value['runtime']!=self.runtime or value['world_id']!=self.clock.world_id:raise ValueError('stale Eye evidence identity')
                    key=(value['source'],value['eye_runtime']);last=self.eye_last.get(key)
                    if last and (value['sequence']<=last[0] or value['epoch']<last[1]):raise ValueError('duplicate or stale Eye evidence')
                    from neural_types import validate_sensory
                    sensory=validate_sensory(record.get('sensory'),value['source'])
                    name=label(value['source']);ident=self.buffer.submit(seq,text,name,'eye:'+value['source'],'unauthority',self.clock.stamp(),vision=value)
                    self.eye_pending=dict(id=ident,vision=value,text=text,label=name,sensory=sensory)
                    self.eye_last[key]=(value['sequence'],value['epoch']);self.eye_last.move_to_end(key)
                    while len(self.eye_last)>128:self.eye_last.popitem(last=False)
                    result=dict(id=ident,state='received',admitted_stamp=None)
                else:
                    pending=self.eye_pending
                    neural=self.ns.get('NEURAL_SYSTEM')
                    retired=neural.retire_eye(record.get('eye_runtime')) if neural is not None else False
                    result=bool(pending and (record.get('id') is None or pending['id']==record.get('id')) and pending['vision']['eye_runtime']==record.get('eye_runtime') and self.buffer.cancel(pending['id'])) or retired
            elif op=='register_eye':
                neural=self.ns.get('NEURAL_SYSTEM')
                if neural is None or record.get('runtime')!=self.runtime or record.get('world_id')!=self.clock.world_id:raise ValueError('stale Eye registration')
                result=neural.register_eye(record.get('eye_runtime'))
            elif op=='neural_presented':
                neural=self.ns.get('NEURAL_SYSTEM')
                if neural is None:raise ValueError('neural surface is unavailable')
                result=neural.presented(record.get('record'))
            elif op=='get_art':result=copy.deepcopy(self.latest_art)
            elif op=='status':result=self.status()
            elif op=='resize':
                from protocol import _geometry
                cols,rows=record.get('cols'),record.get('rows');_geometry(cols,rows)
                setter=self.ns.get('set_display_geometry')
                if setter is None:raise ValueError('display sizing unavailable')
                setter(cols,rows);result=dict(cols=cols,rows=rows)
            elif op=='cancel':result=self.buffer.cancel(record.get('id'))
            else:raise ValueError('unsupported control operation')
            return dict(seq=seq,ok=True,result=result)
        except (ValueError,TypeError) as error:return dict(seq=seq,ok=False,error=str(error))
    def start(self,control=None):
        self.loop=asyncio.get_running_loop();self.control=control;self.preparer.start()
        self.wakeup=asyncio.Event();self.control_paused=False
        self.loop.add_reader(self.preparer.socket.fileno(),self.prepared)
        if control:self.loop.add_reader(control.fileno(),self.incoming)
        self.pump_task=self.loop.create_task(self.pump())
    def send(self,record):
        if self.control:self.outbox.append(record);self.wakeup.set()
    def incoming(self):
        try:
            for _ in range(8):
                if len(self.outbox)>=32:
                    self.loop.remove_reader(self.control.fileno());self.control_paused=True;return
                record=read_packet(self.control)
                if record is None:return
                self.send(self.handle(record))
        except (EOFError,OSError,ValueError):
            self.loop.remove_reader(self.control.fileno());self.control.close();self.control=None
        finally:self.wakeup.set()
    def prepared(self):
        try:
            reply=self.preparer.receive()
            if reply:self.buffer.complete(reply)
        except (EOFError,OSError,ValueError) as error:
            self.preparation_failed(error)
        finally:self.wakeup.set()
    def preparation_failed(self,error):
        self.prep_error=type(error).__name__
        if self.preparer.socket:
            self.loop.remove_reader(self.preparer.socket.fileno());self.loop.remove_writer(self.preparer.socket.fileno())
        self.preparer.stop();self.buffer.fail_preparer()
        if self.eye_pending:self.buffer.cancel(self.eye_pending['id'],'preparer failed')
    async def pump(self):
        try:
            while True:
                await self.wakeup.wait();self.wakeup.clear()
                if self.prep_error is None:
                    job=self.buffer.next_job()
                    try:
                        if job and not self.preparer.send(job):
                            self.buffer.pending[job['id']]['state']='received';self.buffer.inflight=None
                            self.loop.add_writer(self.preparer.socket.fileno(),self.wakeup.set)
                        else:self.loop.remove_writer(self.preparer.socket.fileno())
                    except (OSError,ValueError) as error:self.preparation_failed(error)
                if self.control:
                    if self.pending_art is not None and len(self.outbox)<32:
                        self.outbox.append(self.pending_art);self.pending_art=None
                    while self.outbox:
                        try:
                            if not write_packet(self.control,self.outbox[0]):
                                self.loop.add_writer(self.control.fileno(),self.wakeup.set);break
                            self.outbox.popleft()
                        except (OSError,ValueError):self.control.close();self.control=None;self.outbox.clear();break
                    if self.control and self.pending_art is not None and len(self.outbox)<32:self.wakeup.set()
                    if self.control:
                        if not self.outbox:self.loop.remove_writer(self.control.fileno())
                        if self.control_paused and len(self.outbox)<16:self.loop.add_reader(self.control.fileno(),self.incoming);self.control_paused=False
        except asyncio.CancelledError:pass
    def flush(self):
        # Bounded candidate-only metadata, never an original state path.
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.ns['atomic_write'](self.directory/'world-clock.json',json.dumps(dict(stamp=self.clock.stamp())))
        self.ns['atomic_write'](self.directory/'temporal.json',json.dumps(dict(contexts=self.contexts.rows,status=self.buffer.status())))
        if self.cache is not None:self.cache.flush()
    def close(self):
        if self.pump_task:self.pump_task.cancel()
        if self.loop:
            for sock in (self.preparer.socket,self.control):
                if sock:
                    try:self.loop.remove_reader(sock.fileno())
                    except (OSError,ValueError):pass
                    try:self.loop.remove_writer(sock.fileno())
                    except (OSError,ValueError):pass
        self.preparer.stop()
        if self.eye_pending:self.buffer.cancel(self.eye_pending['id'],'world closed')
        self.buffer.fail_preparer()
        if self.control:self.control.close();self.control=None
        self.flush()

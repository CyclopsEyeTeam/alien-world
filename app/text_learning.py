"""Bounded text associations with independent reads and atomic native cursors.

The original residue is never replayed here. A crash between derived feedback
publication and its history ACK can repeat that internal feedback; completed
association chunks cannot repeat. Pending cache heads remain provisional RAM.
"""
from collections import OrderedDict
import copy,hashlib,json,math,re,sqlite3,threading,uuid
from pathlib import Path
from content_cache import CacheBusy,MAX_BYTES,_json,_unpack,json_bytes
from world_clock import validate_stamp,tick_distance
from rift_interface import owned_projection

TEXT_NUMBERS=('text_queued','text_completed','text_chunks','text_pending','text_refused',
              'text_read_errors','text_archive_failed','text_feedback','text_feedback_rejected','text_inflight')
TEXT_BOOLS=('text_reader_alive','text_closed')
_QUEUE='language.text.queue';_JOB='language.text.job';_LIB='0'*32


def _key(value):return hashlib.sha256(value.encode()).hexdigest()

def text_progression_result(new,end):
    reinforced=max(0,end-new)
    learning=reinforced/max(1,end) if end>0 else 0.
    growth=new/max(1,end)
    formulation=float(end>0)
    understanding=(reinforced/end)*min(1.,end/4.) if reinforced>0 and end>=2 else 0.
    return dict(learning=learning,growth=growth,formulation=formulation,understanding=understanding,semantic_verification='unknown',new_associations=new)

def _stamp(value):
    try:return validate_stamp(value)
    except (TypeError,ValueError,KeyError,OverflowError):return None

def _head(db,world,kind,key,default=None):
    row=db.execute('SELECT r.id,r.payload,r.digest,r.size FROM heads h JOIN records r ON r.world=h.world AND r.id=h.id WHERE h.world=? AND h.kind=? AND h.key=?',(world,kind,key)).fetchone()
    if row is None:return default,None
    ref=f'alien-cache:v1:{world}:{row[0]}:{row[2]}'
    return _json(_unpack(row[1:],ref,MAX_BYTES)),ref

def _job(value):
    if (type(value) is not dict or set(value)!={'version','cursor','new','done','feedback','result'} or
        type(value['version']) is not int or value['version']!=1 or
        any(type(value[k]) is not int or not 0<=value[k]<2**64 for k in ('cursor','new')) or
        any(type(value[k]) is not bool for k in ('done','feedback')) or
        value['result'] is not None and type(value['result']) is not dict or
        value['feedback'] and not value['done']):raise ValueError('Invalid saved text job')
    return value

def read_chunk(path,world,request):
    """Owned reader seam. Never opens the actor's shared native read connection."""
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=.05)
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        key=request['key'];job,_=_head(db,world,_JOB,key)
        job=_job(job)
        source=request.get('source')
        if source is None:
            value,ref=_head(db,world,'language.input',key)
            if (type(value) is not dict or set(value)!={'text','provenance','semantic_verification'} or
                type(value['text']) is not str or len(value['text'].encode('utf-8'))>65536 or
                value['provenance'] is not None and type(value['provenance']) is not dict or
                value['semantic_verification']!='unknown'):raise ValueError('Invalid saved text input')
            provenance=value['provenance'] or {};original=provenance.get('stamp')
            if original is not None and (_stamp(original) is None or original['world_id']!=world):raise ValueError('Invalid text source stamp')
            source=dict(words=tuple(re.findall(r"\b[\w'-]+\b",value['text'].casefold())),ref=ref,stamp=copy.deepcopy(original))
        words=source['words'];end=max(0,len(words)-1)
        if job['cursor']>end or job['new']>job['cursor'] or job['done'] and (job['cursor']!=end or job['result'] is None):raise ValueError('Invalid text cursor')
        if job['done']:
            value=job['result'];expected=text_progression_result(job['new'],end);legacy=dict(expected,learning=0.,understanding=0.)
            if (set(value)!=set(expected) or type(value.get('new_associations')) is not int or
                any(type(value.get(k)) not in (int,float) or not 0<=value[k]<=1 for k in ('learning','growth','formulation','understanding')) or value not in (expected,legacy)):raise ValueError('Invalid saved text completion')
        rows={};edges={};seeds=None
        if not job['done'] and job['cursor']<end:
            for i in range(job['cursor'],min(end,job['cursor']+request['limit'])):
                left,right=words[i:i+2];edge_key=_key(left+'\0'+right)
                if left not in rows:
                    row,_=_head(db,_LIB,'language.links',_key(left),{'word':left,'next':{}})
                    if (type(row) is not dict or row.get('word')!=left or type(row.get('next')) is not dict or
                        len(row['next'])>10000 or any(type(k) is not str or type(v) is not int or v<0 for k,v in row['next'].items())):raise ValueError('Invalid text link')
                    rows[left]=row
                if edge_key not in edges:
                    edge,_=_head(db,_LIB,'language.edge',edge_key,{'left':left,'right':right,'count':0})
                    if (type(edge) is not dict or edge.get('left')!=left or edge.get('right')!=right or
                        type(edge.get('count')) is not int or edge['count']<0):raise ValueError('Invalid text edge')
                    edges[edge_key]=edge
        elif not job['done']:
            seeds,_=_head(db,_LIB,'language.context','seeds',[])
            if type(seeds) is not list or len(seeds)>256 or any(type(s) is not str for s in seeds):raise ValueError('Invalid text seeds')
        return dict(key=key,job=job,source=source,rows=rows,edges=edges,seeds=seeds)
    finally:db.close()


class TextLearning:
    def __init__(self,cache,model,clock,*,chunk_edges=4,capacity=8,reader=read_chunk):
        if type(chunk_edges) is not int or not 1<=chunk_edges<=8 or type(capacity) is not int or not 1<=capacity<=32:raise ValueError('Invalid text allowance')
        if not callable(getattr(cache,'put_batch_json',None)) or not getattr(cache,'background_writer',False):raise ValueError('Text learning requires the background archive')
        self.cache=cache;self.model=model;self.clock=clock;self.chunk_edges=chunk_edges;self.capacity=capacity;self.reader=reader
        self.prefix=uuid.uuid4().hex;self.head=self.tail=0;self._physical_head=0
        absent=object();saved=cache.get_json(_QUEUE,'v1',absent)
        if saved is not absent:
            if (type(saved) is not dict or set(saved)!={'version','prefix','head','tail'} or
                type(saved['version']) is not int or saved['version']!=1 or type(saved['prefix']) is not str or re.fullmatch('[0-9a-f]{32}',saved['prefix']) is None or
                any(type(saved[k]) is not int for k in ('head','tail')) or not 0<=saved['head']<=saved['tail']<2**64 or saved['tail']-saved['head']>32):raise ValueError('Saved text queue is damaged')
            self.prefix=saved['prefix'];self.head=self._physical_head=saved['head'];self.tail=saved['tail']
        self.closed=False;self._active=None;self._commit=None;self._read_fence=None;self._ready=None;self._fatal=False;self._last_tick=None;self._retry_until=-1
        self._condition=threading.Condition();self._task=None;self._result=None;self._busy=False;self._stop=False;self._thread=None
        self._issued=OrderedDict()
        self._counts=dict(text_queued=0,text_completed=0,text_chunks=0,text_refused=0,text_read_errors=0,text_archive_failed=0,text_feedback=0,text_feedback_rejected=0)
    def _header(self,head=None,tail=None):return dict(version=1,prefix=self.prefix,head=self.head if head is None else head,tail=self.tail if tail is None else tail)
    def _now(self):return _stamp(self.clock.stamp())
    def can_accept(self):
        if self.closed or self._fatal or self.tail-self._physical_head>=self.capacity or self.tail>=2**64-1:return False
        state=self.cache.statistics()
        return not state['failed'] and state['writer_alive']
    def offer(self,text,provenance=None):
        try:
            if not self.can_accept() or type(text) is not str or len(text.encode('utf-8'))>65536 or provenance is not None and type(provenance) is not dict:raise ValueError('Text source unavailable')
            if provenance and provenance.get('stamp') is not None:
                original=_stamp(provenance['stamp'])
                if original is None or original['world_id']!=self.cache.world_id:raise ValueError('Invalid text source stamp')
            source=dict(text=text,provenance=copy.deepcopy(provenance),semantic_verification='unknown')
            if len(json_bytes(source))>128*1024:raise ValueError('Text provenance exceeds allowance')
            key=self.prefix+':'+str(self.tail);job=dict(version=1,cursor=0,new=0,done=False,feedback=False,result=None)
            self.cache.put_batch_json([(self.cache.world_id,'language.input',key,source),(self.cache.world_id,_JOB,key,job),(self.cache.world_id,_QUEUE,'v1',self._header(tail=self.tail+1))])
        except (OSError,ValueError,TypeError,OverflowError):self._counts['text_refused']+=1;return False
        self.tail+=1;self._counts['text_queued']+=1;return True
    def _run_reader(self):
        while True:
            with self._condition:
                while self._task is None and not self._stop:self._condition.wait()
                if self._stop:return
                request=self._task;self._task=None;self._busy=True
            try:result=self.reader(self.cache.path,self.cache.world_id,request);error=None
            except Exception as caught:result=None;error=caught
            with self._condition:
                self._busy=False
                if not self._stop:self._result=(result,error)
                self._condition.notify_all()
    def _submit(self):
        if self._thread is None:
            self._thread=threading.Thread(target=self._run_reader,name='alien-text-reader',daemon=True)
            try:self._thread.start()
            except (OSError,RuntimeError):
                self._thread=None;self._counts['text_read_errors']+=1;now=self._now();self._retry_until=now['tick']+4 if now else -1;return
        request=dict(key=self.prefix+':'+str(self.head),limit=self.chunk_edges)
        if self._active is not None:request['source']=self._active['source']
        with self._condition:
            self._task=request;self._condition.notify()
    def _schedule_read(self):
        if self._read_fence is None:self._read_fence=self.cache.barrier()
        if not self._read_fence.done():return
        try:self._read_fence.result()
        except (OSError,ValueError):self._fatal=True;self._counts['text_archive_failed']+=1;return
        self._read_fence=None;self._submit()
    def _stage(self,mode,entries,update):
        try:
            self.cache.put_batch_json(entries)
            # The accepted logical header is the predecessor for a concurrent
            # offer; physical capacity remains held until its real ACK.
            if mode=='dequeue':self.head=update['head']
            self._commit=(self.cache.barrier(),mode,update)
        except (OSError,ValueError):
            self._counts['text_archive_failed']+=1;now=self._now();self._retry_until=(now['tick']+4) if now else -1
            return False
        return True
    def _prepared(self,data):
        job=copy.deepcopy(data['job']);source=data['source'];words=source['words'];end=max(0,len(words)-1)
        if job['cursor']<end:
            rows=copy.deepcopy(data['rows']);edges=copy.deepcopy(data['edges']);stop=min(end,job['cursor']+self.chunk_edges)
            # The native LRU preserves legacy insertion-order tie breaking.
            for left in rows:
                if left in self.model.lexicon:rows[left]=copy.deepcopy(self.model.lexicon[left])
            for i in range(job['cursor'],stop):
                left,right=words[i:i+2];row=rows[left];edge=edges[_key(left+'\0'+right)]
                if edge['count']==0:job['new']+=1
                edge['count']+=1;edge['last_world']=self.cache.world_id;edge['latest_input_ref']=source['ref'];row['next'][right]=edge['count']
                if len(row['next'])>64:
                    retained=sorted(row['next'],key=lambda word:row['next'][word],reverse=True)[:63]
                    row['next']={word:row['next'][word] for word in dict.fromkeys(retained+[right])}
            job['cursor']=stop
            entries=[(_LIB,'language.edge',key,value) for key,value in edges.items()]+[(_LIB,'language.links',_key(word),value) for word,value in rows.items()]+[(self.cache.world_id,_JOB,data['key'],job)]
            return 'chunk',entries,dict(job=job,rows=rows)
        seeds=list(dict.fromkeys(data['seeds']+list(words)))[-256:]
        result=text_progression_result(job['new'],end)
        job.update(done=True,result=result)
        return 'finish',[(_LIB,'language.context','seeds',seeds),(self.cache.world_id,_JOB,data['key'],job)],dict(job=job,seeds=seeds,result=result)
    def _accept_commit(self):
        future,mode,value=self._commit
        if not future.done():return False
        self._commit=None
        try:future.result()
        except (OSError,ValueError):self._fatal=True;self._counts['text_archive_failed']+=1;return False
        if mode=='dequeue':
            self._physical_head=value['head'];self._active=None;self._ready=None;self._counts['text_completed']+=1
        else:
            self._active['job']=value['job']
            if mode=='chunk':
                self._counts['text_chunks']+=1
                for word,row in value['rows'].items():
                    self.model.lexicon[word]=row;self.model.lexicon.move_to_end(word)
                    while len(self.model.lexicon)>512:self.model.lexicon.popitem(last=False)
            if mode=='finish':self.model.seeds=value['seeds'];self.model.last_values=value['result']
        return True
    def _feedback(self,bus,now):
        active=self._active;job=active['job']
        if job['feedback']:
            target=self.head+1
            self._stage('dequeue',[(self.cache.world_id,_QUEUE,'v1',self._header(head=target))],dict(head=target));return
        if not active.get('said'):
            body=dict(id=uuid.uuid4().hex,ref=active['key'],source_ref=active['source']['ref'],source_stamp=copy.deepcopy(active['source']['stamp']),world_stamp=copy.deepcopy(now),progression=copy.deepcopy(job['result']),authority='unauthority',semantic_verification='unknown',derived_learning=True,independent_outside_evidence=False)
            self._issued[body['id']]=copy.deepcopy(body)
            while len(self._issued)>64:self._issued.popitem(last=False)
            bus.publish('progression_feedback',body);active['said']=True;active['publication']=copy.deepcopy(now);self._counts['text_feedback']+=1
        if self.closed:return
        updated=copy.deepcopy(job);updated['feedback']=True
        receipt=dict(source_ref=active['source']['ref'],source_stamp=copy.deepcopy(active['source']['stamp']),world_stamp=active['publication'],progression=copy.deepcopy(job['result']),semantic_verification='unknown',derived_learning=True)
        self._stage('feedback',[(self.cache.world_id,'language.text.feedback',active['key'],receipt),(self.cache.world_id,_JOB,active['key'],updated)],dict(job=updated))
    def claim_feedback(self,payload):
        ident=payload.get('id') if type(payload) is dict else None
        issued=self._issued.get(ident) if type(ident) is str else None;now=self._now()
        valid=not self.closed and issued is not None and now is not None and owned_projection(payload,issued)
        if valid:
            distance=tick_distance(issued['world_stamp'],now)
            valid=distance is not None and issued['world_stamp']['tick']<=now['tick'] and distance<=64
        if not valid:self._counts['text_feedback_rejected']+=1;return False
        del self._issued[ident];return True
    def pump(self,bus):
        if self.closed or self._fatal:return
        now=self._now()
        if now is None or now['world_id']!=self.cache.world_id:return
        tick=(now['world_id'],now['segment_id'],now['tick'])
        if self._last_tick is not None and tick[:2]==self._last_tick[:2] and tick[2]<=self._last_tick[2]:return
        self._last_tick=tick
        if now['tick']<self._retry_until:return
        if self._commit is not None:
            self._accept_commit();return
        with self._condition:
            result=self._result;self._result=None;reading=self._busy or self._task is not None
        if result is not None:
            data,error=result
            if error is not None:
                self._counts['text_read_errors']+=1;self._retry_until=now['tick']+4;return
            self._active=data
            try:
                if not data['job']['done']:self._ready=self._prepared(data)
            except (KeyError,TypeError,ValueError,OverflowError):
                self._counts['text_read_errors']+=1;self._retry_until=now['tick']+4;return
        if self._ready is not None:
            mode,entries,update=self._ready
            if self._stage(mode,entries,update):self._ready=None
            return
        if self._active is not None and self._active['job']['done']:
            self._feedback(bus,now);return
        if self.head>=self.tail or reading:return
        self._schedule_read()
    def summary(self):
        return dict(self._counts,text_pending=self.tail-self._physical_head,text_inflight=int(self._active is not None or self._commit is not None or self._busy or self._task is not None or self._read_fence is not None or self._result is not None),text_reader_alive=bool(self._thread and self._thread.is_alive()),text_closed=self.closed)
    def close(self):
        self.closed=True;self._issued.clear()
        with self._condition:self._stop=True;self._task=None;self._result=None;self._condition.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():self._thread.join(.25)

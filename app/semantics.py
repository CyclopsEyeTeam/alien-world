"""Bounded temporal context sidecar; content features remain separate from time."""
from collections import OrderedDict
import copy,json,math,time
from world_clock import validate_stamp,tick_distance

class Contexts:
    def __init__(self,runtime,limit=512):
        self.runtime=runtime;self.limit=limit;self.sequence=0;self.rows=OrderedDict();self.references=lambda:set()
    def add(self,stamp,kind,input_id='',source='',origin=None,vision=None):
        self.sequence+=1;ref=f'{self.runtime}:{self.sequence}'
        self.rows[ref]=dict(stamp=validate_stamp(stamp),kind=str(kind)[:32],input_id=str(input_id)[:96],source=str(source)[:256],material='available' if input_id else 'not_stored')
        if origin:
            from api_origin import validate_origin
            self.rows[ref]['origin']=validate_origin(origin)
        if vision:
            from vision_origin import validate_vision
            self.rows[ref]['vision']=validate_vision(vision)
        if len(self.rows)>self.limit:
            protected=self.references()|{ref}
            while len(self.rows)>self.limit:
                victim=next((key for key in self.rows if key not in protected),next(iter(self.rows)))
                self.rows.pop(victim)
        return ref
    def get(self,ref):return copy.deepcopy(self.rows.get(ref))
    def evict_material(self,input_id):
        for row in self.rows.values():
            if row['input_id']==input_id:row['material']='evicted'

def memory_class(ns):
    Base=ns['VectorMemory']
    class LinkedMemory(Base):
        def __init__(self):super().__init__();self.pending_context=None
        def add(self,*args,**kw):
            before=self.items[-1] if self.items else None;super().add(*args,**kw)
            if self.items and self.items[-1] is not before and self.pending_context:self.items[-1]['context_ref']=self.pending_context
            self.pending_context=None
        def add_buffered(self,item,ref):
            prepared=item['prepared']
            record=dict(label=prepared['label'],vec=[round(v,5) for v in prepared['vec']],kind='buffered_input',t=round(time.time(),3),genes=None,confidence=0.0,authority=item['authority'],input_id=item['id'],source=item['source'],context_ref=ref)
            if item.get('origin'):record['origin']=copy.deepcopy(item['origin'])
            if item.get('vision'):record['vision']=copy.deepcopy(item['vision'])
            self.items.append(record)
            self.items=self.items[-ns['MAX_VECTORS']:];self.dirty=True
        def nearest(self,vec,k=3,window=None):
            items=self.items[-int(window):] if window and window>0 else self.items
            hits=sorted(((ns['dot'](vec,x['vec']),x) for x in items if len(x.get('vec',[]))==len(vec)),key=lambda x:x[0],reverse=True)[:k]
            return [dict({key:item.get(key) for key in ('label','kind','genes','confidence','authority','context_ref','input_id','source','origin','vision')},score=round(score,4)) for score,item in hits]
        def load(self,path):
            super().load(path)
            try:
                if path.stat().st_size>4*1024*1024:return
                raw=json.loads(path.read_text()).get('items',[])[:ns['MAX_VECTORS']]
                valid=[x for x in raw if isinstance(x,dict) and isinstance(x.get('label'),str) and isinstance(x.get('vec'),list) and len(x['vec'])==ns['DIM']]
                for item,record in zip(self.items,valid):
                    confidence=record.get('confidence')
                    if type(confidence) in (int,float) and math.isfinite(confidence):item['confidence']=ns['clamp01'](confidence)
                    for key,limit in (('context_ref',96),('input_id',96),('source',256)):
                        value=record.get(key)
                        if isinstance(value,str) and len(value)<=limit:item[key]=value
                    if record.get('origin'):
                        from api_origin import validate_origin
                        item['origin']=validate_origin(record['origin']);item['confidence']=0.;item['authority']='unauthority'
                    if record.get('vision'):
                        from vision_origin import validate_vision
                        item['vision']=validate_vision(record['vision']);item['confidence']=0.;item['authority']='unauthority'
            except (OSError,ValueError,TypeError):pass
    return LinkedMemory

class BufferedSemanticConsumer:
    def __init__(self,ns,memory,contexts):self.ns=ns;self.memory=memory;self.contexts=contexts
    def consume(self,item,stamp):
        ref=self.contexts.add(stamp,'eye_perception' if item.get('vision') else 'buffered_input',item['id'],item['source'],item.get('origin'),item.get('vision'))
        if item.get('vision') and self.ns.get('NEURAL_INTERFACE_ENABLED'):
            # Physical receipt is not yet permission for semantic memory. The
            # registered grounding agent owns the next promotion decision.
            return dict(context_ref=ref,consumer='grounding_pending',consumed_stamp=copy.deepcopy(stamp))
        self.memory.add_buffered(item,ref)
        # The direct consumer can acknowledge its own insertion, not other agents.
        if not any(x.get('input_id')==item['id'] for x in self.memory.items):raise RuntimeError('semantic insertion missing')
        return dict(context_ref=ref,consumer='buffered_semantics',consumed_stamp=copy.deepcopy(stamp))
    def material_evicted(self,ident):self.contexts.evict_material(ident)
    def query(self,text,since=None):
        if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=1024:raise ValueError('query must be 1..1024 UTF-8 bytes')
        since=validate_stamp(since);vec=self.ns['compose_vector'](text,None);rows=[]
        for item in self.memory.items:
            if item.get('kind')!='buffered_input':continue
            context=self.contexts.get(item.get('context_ref'));stamp=context['stamp'] if context else None
            if since is not None and (tick_distance(since,stamp) is None or stamp['tick']<since['tick']):continue
            rows.append(dict(label=item['label'],source=item.get('source',''),input_id=item.get('input_id'),context_ref=item.get('context_ref'),admitted_stamp=stamp,content_similarity=round(self.ns['dot'](vec,item['vec']),4),authority=item.get('authority'),material=context.get('material') if context else 'unknown',origin=copy.deepcopy(item.get('origin')),vision=copy.deepcopy(item.get('vision'))))
        rows.sort(key=lambda x:x['content_similarity'],reverse=True);return rows[:5]

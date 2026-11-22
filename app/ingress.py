"""Bounded volatile intake. Accepted pending data never enters the lossy hive bus."""
from collections import OrderedDict
import json,math,uuid,copy
from world_clock import validate_stamp
LIMIT=16*1024*1024
RESULT=4096
MAX_INPUT=65536
MAX_WIRE=128*1024
DIM=24
class Busy(ValueError):pass

def packed(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
class TimeBuffer:
    def __init__(self,runtime=None,max_bytes=LIMIT,retained_limit=128):
        self.runtime=runtime or uuid.uuid4().hex;self.max_bytes=max_bytes;self.retained_limit=retained_limit
        self.pending=OrderedDict();self.retained=OrderedDict();self.receipts=OrderedDict();self.used_bytes=0
        self.last_sequence=0;self.inflight=None;self.cancelled_reservation=0;self.last_tick=None;self.eviction_handler=None;self.evicted_count=0
        self.api_reservation=None
        self.receipt_handler=None
    def reserve_api(self,request_id):
        if self.api_reservation:raise Busy('API reservation already occupied')
        while self.used_bytes+65536>self.max_bytes and self.retained:self._evict()
        if len(self.pending)>=256 or self.used_bytes+65536>self.max_bytes:raise Busy('time buffer full; API request not started')
        self.api_reservation=request_id;self.used_bytes+=65536
    def release_api(self,request_id):
        if self.api_reservation!=request_id:return False
        self.api_reservation=None;self.used_bytes-=65536;return True
    def submit_api(self,request_id,sequence,text,origin,received_stamp=None):
        from api_origin import validate_origin,LABEL
        origin=validate_origin(origin)
        if origin['request_id']!=request_id or self.api_reservation!=request_id:raise ValueError('no matching API reservation')
        if not isinstance(text,str) or not 1<=len(text.encode())<=4096:raise ValueError('API text exceeds 4KiB')
        self.release_api(request_id)
        try:return self.submit(sequence,text,LABEL,'api-residue','unauthority',received_stamp,origin)
        except Exception:
            self.api_reservation=request_id;self.used_bytes+=65536;raise
    def _evict(self):
        ident,item=self.retained.popitem(last=False);self.used_bytes-=item['_cost'];self.evicted_count+=1
        if self.eviction_handler:self.eviction_handler(ident)
    def submit(self,sequence,text,label='',source='',authority='unauthority',received_stamp=None,origin=None,vision=None):
        if type(sequence) is not int or sequence<=self.last_sequence or sequence>=2**64:raise ValueError('duplicate or invalid input sequence')
        if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=MAX_INPUT:raise ValueError('text must be 1..65536 UTF-8 bytes')
        if not isinstance(label,str) or len(label)>80 or not isinstance(source,str) or len(source)>256:raise ValueError('oversized label/source')
        if authority not in ('authority','unauthority'):raise ValueError('invalid source authority')
        item=dict(id=f'{self.runtime}:{sequence}',runtime=self.runtime,text=text,label=label,source=source,authority=authority,received_stamp=validate_stamp(received_stamp),admitted_stamp=None,state='received')
        if origin is not None:
            from api_origin import validate_origin
            item['origin']=validate_origin(origin)
        if vision is not None:
            from vision_origin import validate_vision,validate_summary
            if origin is not None or authority!='unauthority':raise ValueError('Eye evidence cannot claim API or native authority')
            item['vision']=validate_vision(vision);validate_summary(text)
            if item['vision']['runtime']!=self.runtime:raise ValueError('stale Eye buffer runtime')
        job={k:item[k] for k in ('id','runtime','text','label')}
        if len(packed(job))>MAX_WIRE:raise ValueError('encoded preparation envelope exceeds channel limit; input not accepted')
        # Reserve the stored input plus its bounded serialized IPC copy.
        cost=2*len(packed(item))+RESULT+512
        if cost>self.max_bytes:raise Busy('input exceeds available RAM allowance')
        while self.used_bytes+cost>self.max_bytes and self.retained:self._evict()
        if len(self.pending)>=256-bool(self.api_reservation) or self.used_bytes+cost>self.max_bytes:raise Busy('time buffer full; retry later')
        item['_cost']=cost;self.pending[item['id']]=item;self.used_bytes+=cost;self.last_sequence=sequence
        return item['id']
    def next_job(self):
        if self.inflight:return None
        for item in self.pending.values():
            if item['state']=='received':
                item['state']='preparing';self.inflight=item['id']
                return {k:item[k] for k in ('id','runtime','text','label')}
        return None
    def complete(self,result):
        if not isinstance(result,dict) or result.get('runtime')!=self.runtime:raise ValueError('stale preparation runtime')
        ident=result.get('id')
        if ident not in self.pending:
            if self.inflight==ident:
                self.inflight=None;self.used_bytes-=self.cancelled_reservation;self.cancelled_reservation=0
            return False
        item=self.pending[ident]
        if item['state']!='preparing' or ident!=self.inflight:raise ValueError('unexpected or duplicate preparation')
        if len(packed(result))>RESULT:raise ValueError('oversized preparation result')
        label=result.get('label');vec=result.get('vec')
        if not isinstance(label,str) or not 1<=len(label)<=80 or not isinstance(vec,list) or len(vec)!=DIM or any(type(x) not in (int,float) or not math.isfinite(x) for x in vec):raise ValueError('invalid prepared content')
        item['prepared']=copy.deepcopy(result);item['state']='ready';self.inflight=None;return True
    def _receipt(self,ident,receipt):
        self.receipts[ident]=copy.deepcopy(receipt)
        while len(self.receipts)>256:self.receipts.popitem(last=False)
        if self.receipt_handler:self.receipt_handler(copy.deepcopy(receipt))
    def cancel(self,ident,reason='cancelled'):
        item=self.pending.pop(ident,None)
        if item is None:return False
        if self.inflight==ident:self.cancelled_reservation=item['_cost']
        else:self.used_bytes-=item['_cost']
        # A cancelled running preparation still occupies the sole physical slot
        # until its result arrives (or the preparer is declared failed).
        self._receipt(ident,dict(id=ident,state='failed' if reason!='cancelled' else 'cancelled',reason=reason,admitted_stamp=item['admitted_stamp']));return True
    def fail_preparer(self):
        if self.inflight in self.pending:self.cancel(self.inflight,'preparer failed')
        self.used_bytes-=self.cancelled_reservation;self.cancelled_reservation=0;self.inflight=None
    def on_tick(self,clock,consumer):
        stamp=clock.stamp()
        if stamp is None:return None
        key=(stamp['world_id'],stamp['segment_id'],stamp['tick'])
        if key==self.last_tick:return None
        self.last_tick=key;self.eviction_handler=consumer.material_evicted
        if not self.pending:return None
        ident,item=next(iter(self.pending.items()))
        if item['state']!='ready':return None
        item['admitted_stamp']=copy.deepcopy(stamp);item['state']='admitted'
        try:answer=consumer.consume(item,stamp)
        except Exception as error:
            self.cancel(ident,'semantic handoff failed: '+type(error).__name__);return self.receipts[ident]
        item['state']='consumed';self.pending.pop(ident);self.retained[ident]=item
        receipt=dict(id=ident,state='consumed',admitted_stamp=stamp,consumer=answer)
        self._receipt(ident,receipt)
        while len(self.retained)>self.retained_limit:self._evict()
        return copy.deepcopy(receipt)
    def status(self):
        return dict(pending=len(self.pending),ready=sum(x['state']=='ready' for x in self.pending.values()),retained=len(self.retained),used_bytes=self.used_bytes,max_bytes=self.max_bytes,evicted_material=self.evicted_count,inflight=self.inflight,api_reserved=bool(self.api_reservation))

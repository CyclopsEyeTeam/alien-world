"""GUI-owned feed; durable accounting is acknowledged without blocking GTK."""
import time,uuid,hashlib,copy
from collections import OrderedDict
from dataclasses import replace
from api_config import Config,build_body,language_authorization
from api_origin import origin
from api_quota import QuotaDenied,QuotaUnavailable

class Feed:
 def diagnostic_event(self,kind):
  observer=getattr(self,'on_diagnostic',None)
  if callable(observer):
   try:observer(kind)
   except Exception:pass
 def __init__(self,quota,keys,driver,control,later,cancel_timer,content_sink=None,content_flush=None,on_admitted=None,content_after_flush=None):
  self.quota=quota;self.keys=keys;self.driver=driver;self.control=control;self.later=later;self.cancel_timer=cancel_timer
  self.config=Config();self.enabled=False;self.generation=0;self.active=None;self.timer=None;self.world=None;self.state=None;self.state_at=time.monotonic();self.message='Feed off';self.closed=False
  self.configs=(self.config,);self.source_index=0;self.previous=OrderedDict();self.seen_receipts=OrderedDict();self.mist_seen=OrderedDict()
  self.content_sink=content_sink;self.content_flush=content_flush;self.content_after_flush=content_after_flush;self.on_admitted=on_admitted
  self.background_quota=bool(getattr(quota,'background_worker',False));self.quota_pending=0;self.reset_pending=False;self.close_error=None
  self._quota_jobs={};self._refresh_pending=False;self._refresh_waiters=[]
  self.refresh_quota()
 def _state(self,value=None):
  if value is None:value=self.quota.status()
  self.state=copy.deepcopy(value);self.state_at=time.monotonic()
 def _quota_submit(self,operation,args=(),success=None,error=None,a=None):
  """Only the worker executes SQLite. A queued operation is never a saved ACK."""
  token=object();job=dict(done=False,future=None,operation=operation,owner=a)
  self._quota_jobs[token]=job;self.quota_pending+=1
  if a is not None:a['quota_pending']=a.get('quota_pending',0)+1
  def retire():
   if job['done']:return False
   job['done']=True;self._quota_jobs.pop(token,None);self.quota_pending-=1
   if a is not None:a['quota_pending']-=1
   return True
  def completed(result):
   if not retire():return
   try:self._state()
   except (QuotaUnavailable,ValueError,OSError):pass
   if success:success(result)
   if a is not None:self._cancel_done(a)
  def failed(exception):
   if not retire():return
   if error:error(exception)
   if a is not None:self._cancel_done(a)
  job['success']=completed;job['error']=failed
  try:job['future']=self.quota.submit(operation,args=args,success=completed,error=failed)
  except (QuotaUnavailable,ValueError,OSError) as exception:failed(exception)
  return job['future']
 def refresh_quota(self,success=None,error=None):
  if not self.background_quota:
   try:self._state()
   except (QuotaUnavailable,ValueError,OSError) as exception:
    self.state=None;self.message='Allowance unavailable; feed remains off'
    if error:error(exception)
    return False
   if success:success()
   return True
  if self.closed:return False
  if success or error:self._refresh_waiters.append((success,error))
  if self._refresh_pending:return True
  self._refresh_pending=True
  def completed(result):
   self._refresh_pending=False;self._state(result);waiters=self._refresh_waiters;self._refresh_waiters=[]
   if not self.closed:
    for done,_ in waiters:
     if done:done()
  def failed(exception):
   self._refresh_pending=False;self.state=None;waiters=self._refresh_waiters;self._refresh_waiters=[]
   if self.closed:return
   self.enabled=False;self._unschedule();self.message='Allowance unavailable; feed remains off'
   for _,failure in waiters:
    if failure:failure(exception)
  # _quota_submit owns counting; refresh is exactly the same serialized status operation.
  self._quota_submit('status',success=completed,error=failed);return True
 def configure(self,config):self.configure_many((config,))
 def configure_many(self,configs):
  configs=tuple(configs)
  if not 1<=len(configs)<=3 or sum(c.provider=='mist' for c in configs)>1 or sum(c.provider!='mist' for c in configs)>2:raise ValueError('choose up to two providers and one local mist source')
  for config in configs:config.validate(require_model=False)
  self.disable();self.configs=configs;self.config=configs[0];self.source_index=0
 def _unschedule(self):
  if self.timer is not None:self.cancel_timer(self.timer);self.timer=None
 def _schedule_timer(self,minimum=0):
  if self.closed or not self.enabled or self.active or self.state is None:return
  if self._maybe_mist():return
  if not any(c.provider!='mist' for c in self.configs):return
  delay=max(minimum,self.state['next_auto_after'])
  def wake():self.timer=None;self.request(manual=False)
  self.timer=self.later(delay,wake)
 def _schedule(self,minimum=0):
  self._unschedule()
  if self.closed or not self.enabled or self.active:return
  if not self.background_quota:
   if self.refresh_quota():self._schedule_timer(minimum)
   return
  generation=self.generation
  def ready():
   if self.generation==generation:self._schedule_timer(minimum)
  self.refresh_quota(ready)
 def enable(self):
  if self.closed or self.reset_pending:return False
  try:
   for config in self.configs:
    if config.provider=='mist':config.validate()
    else:build_body(config)
  except ValueError:self.message='Choose valid provider, endpoint, model and prompt';return False
  if not self.world or not self.world.get('clock') or self.world.get('preparation_error'):self.message='Wait for the running hive';return False
  if self.background_quota:
   self.enabled=True;self.message='Checking allowance';self._schedule();return True
  if not self.refresh_quota():return False
  self.enabled=True;self.message='Feed enabled';self._schedule();return True
 def _fields(self,a):
  fields=dict(runtime=a['runtime'],world_id=a['world_id'],request_id=a['id'])
  if a.get('mist_offer_id'):fields['mist_offer_id']=a['mist_offer_id']
  return fields
 def _cancel_done(self,a):
  if self.active is not a or a.get('job') or a.get('quota_pending'):return
  finish=a.get('finish_requested')
  if (a.get('invalid') or finish) and (a.get('cancel_ack') or self.closed):
   message,minimum=finish or (a.get('cancel_message','Feed off • cancellation acknowledged'),30 if self.enabled else 0)
   self._finish(a,message,minimum)
 def _cancel_buffer(self,a):
  if a.get('cancel_sent') or self.closed:return
  a['cancel_requested']=True
  def acknowledged(reply):
   a['cancel_ack']=bool(reply.get('ok')) or bool(self.world and self.world.get('runtime')!=a['runtime'])
   if not a['cancel_ack']:a['cancel_sent']=False;self._retry_cancel(a);return
   self._cancel_done(a)
  try:sent=self.control('cancel_api',acknowledged,**self._fields(a))
  except (OSError,ValueError):sent=None
  a['cancel_sent']=bool(sent)
  if not sent:self._retry_cancel(a)
 def _retry_cancel(self,a):
  if self.closed or a.get('cancel_retry'):return
  def retry():a['cancel_retry']=None;self._cancel_buffer(a)
  a['cancel_retry']=self.later(.2,retry)
 def _receipt_failed(self,a,exception):
  if self.closed:
   self.close_error=self.close_error or 'Receipt drain failed: '+str(exception)[:160];return
  self.enabled=False;self._unschedule();self.message='Receipt storage unavailable; feed off';a['invalid']=True;self._cancel_buffer(a)
 def _record(self,a,status,then=None,fail=None,**extra):
  if not a['spent']:
   if then:then()
   return True
  metadata=dict(origin=a.get('origin'),provider=a.get('provider'),requested_model=a.get('requested_model'),input_id=a.get('input_id'),**extra)
  for key in ('cache_ref','content_hash'):
   if a.get(key):metadata[key]=a[key]
  a['record_serial']=a.get('record_serial',0)+1;serial=a['record_serial']
  def saved(_result=None):
   if serial>=a.get('saved_record_serial',0):
    a['saved_record_serial']=serial
    self.previous[a['id']]={k:a.get(k) for k in ('id','runtime','world_id','generation','invalid','spent','text','origin','input_id','provider','requested_model','cache_ref','content_hash')}
    self.previous[a['id']]['status']=status
    while len(self.previous)>128:self.previous.popitem(last=False)
   if then:then()
  def failed(exception):
   self._receipt_failed(a,exception)
   if fail:fail(exception)
  args=(a['id'],status,'' if self.content_sink else a.get('text',''),copy.deepcopy(metadata))
  if self.background_quota:return self._quota_submit('record',args,success=saved,error=failed,a=a) is not None
  try:self.quota.record(*args);saved();return True
  except (QuotaUnavailable,ValueError,OSError) as exception:failed(exception);return False
 def disable(self):
  self.enabled=False;self.generation+=1;self._unschedule();self.message='Feed off'
  a=self.active
  if a:
   a['invalid']=True
   if a.get('lookup'):a['lookup'].cancel()
   self._cancel_buffer(a);self._record(a,'cancelled')
   if a.get('job'):a['job'].cancel()
   self._cancel_done(a)
 def close(self):
  if self.closed:return
  self.closed=True;job=self.active.get('job') if self.active else None;self.disable();deadline=time.monotonic()+4
  try:
   if job and hasattr(job,'close'):job.close()
  except Exception as exception:self.close_error='Request close failed: '+str(exception)[:160]
  if self.background_quota:
   # GTK cannot run dispatched callbacks while closing. Deliver a completed
   # reservation once here so its cancellation receipt joins the worker FIFO.
   for pending in list(self._quota_jobs.values()):
    if pending['operation']!='reserve' or pending['done'] or pending['future'] is None:continue
    try:result=pending['future'].result(timeout=max(0.,deadline-time.monotonic()))
    except Exception as exception:
     self.close_error=self.close_error or 'Allowance drain failed: '+str(exception)[:160]
     if pending['future'].done():pending['error'](exception)
    else:pending['success'](result)
   try:self.quota.close(timeout=max(0.,deadline-time.monotonic()))
   except Exception as exception:self.close_error=self.close_error or 'Allowance drain failed: '+str(exception)[:160]
 def reset_allowance(self):
  if self.closed or self.active is not None or self.quota_pending or self.reset_pending:return False
  self.disable();self.reset_pending=True;self.message='Resetting allowance • feed off'
  def done(state):self._state(state);self.reset_pending=False;self.message='Allowance reset • 0/33 • feed off'
  def failed(exception):self.reset_pending=False;self.message='Allowance reset failed • feed off'
  if self.background_quota:return self._quota_submit('reset',success=done,error=failed) is not None
  try:done(self.quota.reset());return True
  except (QuotaUnavailable,ValueError,OSError) as exception:failed(exception);return False
 def observe(self,state):
  if self.world and (self.world.get('runtime')!=state.get('runtime') or (self.world.get('clock') or {}).get('world_id')!=(state.get('clock') or {}).get('world_id')):self.disable()
  self.world=state
  if state.get('preparation_error') and self.enabled:self.disable();self.message='Preparer unavailable; feed off'
  receipt=state.get('last_api_receipt')
  if receipt:self.receipt(receipt)
  self._maybe_mist()
 def _maybe_mist(self):
  """A status advertises a native decision, never a prompt or a GUI decision."""
  if self.closed or not self.enabled or self.active or self.reset_pending or self.state is None or not self.world:return False
  if not any(c.provider=='mist' for c in self.configs):return False
  offer=(self.world.get('language') or {}).get('mist_offer')
  if not isinstance(offer,dict) or set(offer)!={'id','stamp'}:return False
  import re
  from world_clock import validate_stamp,tick_distance
  ident=offer['id'];stamp=validate_stamp(offer['stamp']);current=validate_stamp(self.world.get('clock'))
  if not isinstance(ident,str) or re.fullmatch('[0-9a-f]{32}',ident) is None or ident in self.mist_seen:return False
  if stamp is None or current is None or tick_distance(stamp,current) is None or not 0<=current['tick']-stamp['tick']<=64:return False
  try:state=self.quota.status()
  except (QuotaUnavailable,ValueError,OSError):return False
  if state['blocked'] or state['next_auto_after']>0:return False
  return self.request(manual=False,_mist_offer=offer)
 def _valid(self,a):return not self.closed and self.active is a and self.enabled and not a['invalid'] and a['generation']==self.generation and self.world and self.world.get('runtime')==a['runtime'] and (self.world.get('clock') or {}).get('world_id')==a['world_id']
 def _finish(self,a,message,minimum=0):
  if self.active is not a:return
  if a.get('quota_pending') or (a.get('cancel_requested') and not a.get('cancel_ack') and not self.closed):a['finish_requested']=(message,minimum);return
  self.active=None;self.message=message;self._schedule(minimum)
 def request(self,manual=True,_mist_offer=None):
  if self.closed or self.reset_pending or not self.enabled or self.active or not self.world or not self.world.get('clock'):return False
  clouds=tuple(c for c in self.configs if c.provider!='mist')
  if _mist_offer is None:
   if not clouds:self.message='Waiting for Alien to reach the mist';return False
   config=clouds[self.source_index%len(clouds)]
  else:
   config=next((c for c in self.configs if c.provider=='mist'),None)
   if config is None:return False
  self._unschedule()
  if self.background_quota:
   try:self._state()
   except (QuotaUnavailable,ValueError,OSError):self.message='Waiting for allowance';self._schedule();return False
   if self.state['used']>=33 and self.state['retry_after']<=0:
    generation=self.generation
    self.refresh_quota(lambda:self.request(manual,_mist_offer=_mist_offer) if self.generation==generation else None);return True
  elif not self.refresh_quota():self.disable();return False
  if self.state['blocked'] or (not manual and self.state['next_auto_after']>0):self.message='Waiting for the shared allowance';self._schedule();return False
  a=dict(id=uuid.uuid4().hex,runtime=self.world['runtime'],world_id=self.world['clock']['world_id'],generation=self.generation,invalid=False,spent=False,config=config,provider=config.provider,requested_model=config.model,job=None,lookup=None,quota_pending=0)
  if _mist_offer is not None:
   a['mist_offer_id']=_mist_offer['id'];self.mist_seen[_mist_offer['id']]=True
   while len(self.mist_seen)>64:self.mist_seen.popitem(last=False)
  self.active=a;self.message='Reserving time-buffer space'
  def reserved(reply):
   if not self._valid(a):self._cancel_buffer(a);return
   if not reply.get('ok'):self._finish(a,'Buffer busy; no request spent',30);return
   try:
    grant=reply.get('result')
    if isinstance(grant,dict):
     grant=language_authorization(grant,a['world_id'],(self.world.get('clock') or {}).get('segment_id'))
     if grant['mode']=='rehearsal':raise ValueError('Rehearsal keeps dialogue inside')
     if config.provider=='mist' and (not a.get('mist_offer_id') or grant['mode']!='dialogue'):raise ValueError('Mist requires Alien reach')
     a['language']=grant;a['base_config']=config;a['config']=self._language_config(config,grant)
    elif grant is True:
     if config.provider=='mist':raise ValueError('Mist requires a held native offer')
     if config.provider!='mist':
      from neural_summary import public_neural_prompt
      a['config']=public_neural_prompt(config,self.world.get('neural_summary'))
    else:raise ValueError('Language authorization unavailable')
   except (ValueError,TypeError):self._language_refused(a,'Language is waiting; no request spent');return
   if a['config'].provider=='mist':
    from mist import LOCAL_MIST_TOKEN
    self._key(a,LOCAL_MIST_TOKEN,None);return
   self.message='Reading local provider key'
   try:a['lookup']=self.keys.lookup(a['config'],lambda key,error:self._key(a,key,error))
   except Exception:self.disable();self.message='Provider key unavailable; feed off'
  try:sent=self.control('reserve_api',reserved,**self._fields(a))
  except (OSError,ValueError):sent=None
  if not sent:self._finish(a,'Input channel busy; no request spent',30);return False
  return True
 def _language_config(self,config,grant):
  if config.provider!='mist' and grant['mode']=='gift':return config
  if grant['mode']!='dialogue':raise ValueError('real calls are unavailable during rehearsal')
  stamp=grant['stamp'];pi=stamp['pi'];marker='⟦t'+str(stamp['tick'])+';π'+str(pi[0])+'/'+str(pi[1])+';c'+grant['continuity']+';s'+stamp['segment_id'][:8]+'⟧'
  runtime=replace(config,prompt=config.prompt if config.provider=='mist' else grant['text'],utterance=grant['text']+'\n'+marker);build_body(runtime);return runtime
 def _language_refused(self,a,message):
  a['invalid']=True;a['cancel_message']=message;self.message=message
  if a['spent']:self._record(a,'cancelled')
  self._cancel_buffer(a)
 def _live_language_config(self,a,reply):
  if not reply.get('ok'):raise ValueError('live authorization refused')
  initial=a['language'];fresh=language_authorization(reply.get('result'),a['world_id'],initial['stamp']['segment_id'])
  if fresh['mode']=='rehearsal' or (initial['mode']=='dialogue' and fresh['mode']!='dialogue'):raise ValueError('alien dialogue is waiting')
  if a.get('mist_offer_id') and (fresh['mode']!='dialogue' or fresh['text']!=initial['text']):raise ValueError('native mist offer changed')
  return self._language_config(a['base_config'],fresh) if initial['mode']=='dialogue' else a['base_config']
 def _key(self,a,key,error):
  if not self._valid(a):return
  a['lookup']=None
  if error or not key:self.disable();self.message='Provider key unavailable; feed off';return
  if 'language' in a:
   self.message='Checking live alien language'
   def authorized(reply):
    if not self._valid(a):self._cancel_buffer(a);return
    try:
     a['config']=self._live_language_config(a,reply);self._dispatch(a,key)
    except (ValueError,TypeError):self._language_refused(a,'Language changed; no request spent')
   try:sent=self.control('authorize_api',authorized,**self._fields(a))
   except (OSError,ValueError):sent=None
   if not sent:self._language_refused(a,'Language channel busy; no request spent')
   return
  self._dispatch(a,key)
 def _dispatch(self,a,key):
  if not self._valid(a):return
  def validate_material():
   if len(key.encode())>4096 or any(ord(c)<33 for c in key) or any(key in text for text in (a['config'].prompt,a['config'].utterance,a['config'].model,a['config'].url())):raise ValueError()
   build_body(a['config'])
  try:validate_material()
  except (ValueError,TypeError):self.disable();self.message='Key invalid or overlaps request material';return
  def launch():
   if not self._valid(a):self._cancel_buffer(a);return
   try:validate_material()
   except (ValueError,TypeError):self.disable();self.message='Key invalid or overlaps request material';return
   if a['config'].provider!='mist':self.source_index=(self.source_index+1)%sum(c.provider!='mist' for c in self.configs)
   self.message='Request in progress • '+a['config'].provider+' • unregistered authority'
   self.diagnostic_event('dispatch')
   try:a['job']=self.driver.start(a['config'],key,lambda result:self._result(a,result))
   except Exception:self._record(a,'error');self._cancel_buffer(a);self._finish(a,'Request worker unavailable')
  def charged(state):
   self._state(state);a['spent']=True
   if not self._valid(a):self._record(a,'cancelled',then=lambda:self._cancel_done(a));self._cancel_buffer(a);return
   if self.background_quota and 'language' in a:
    # A durable reservation can wait behind storage. The earlier language grant
    # cannot authorize a helper after the hive has changed during that wait.
    self.message='Checking live alien language after allowance'
    def authorized(reply):
     if not self._valid(a):self._cancel_buffer(a);return
     try:a['config']=self._live_language_config(a,reply)
     except (ValueError,TypeError):self._language_refused(a,'Language changed; allowance spent');return
     launch()
    try:sent=self.control('authorize_api',authorized,**self._fields(a))
    except (OSError,ValueError):sent=None
    if not sent:self._language_refused(a,'Language channel busy; allowance spent')
    return
   launch()
  def denied(exception):self._cancel_buffer(a);self._finish(a,'Shared allowance unavailable',30)
  if self.background_quota:
   self.message='Reserving shared allowance';self._quota_submit('reserve',(a['id'],),success=charged,error=denied,a=a)
  else:
   try:charged(self.quota.reserve(a['id']))
   except (QuotaDenied,QuotaUnavailable,ValueError,OSError) as exception:denied(exception)
 def _result(self,a,result):
  self.diagnostic_event('reply')
  a['job']=None
  if not self._valid(a):self._cancel_buffer(a);self._cancel_done(a);return
  if not result.get('ok'):self._record(a,'error');self._cancel_buffer(a);self._finish(a,'Request failed; allowance spent');return
  try:
   a['text']=result['text']
   if not isinstance(a['text'],str) or not 1<=len(a['text'].encode())<=4096:raise ValueError()
   a['origin']=origin(a['config'].provider,a['config'].model,a['id'],a['config'].prompt_hash(),result.get('reported_model',''))
  except (KeyError,ValueError,TypeError):self._record(a,'error');self._cancel_buffer(a);self._finish(a,'Unsupported response discarded');return
  if self.content_sink:
   try:
    payload=a['text'].encode('utf-8');a['content_hash']=hashlib.sha256(payload).hexdigest();ref=self.content_sink('api_response',a['id'],payload,metadata=dict(origin=a['origin'],runtime=a['runtime'],world_id=a['world_id']))
    if not isinstance(ref,str) or not 1<=len(ref)<=512:raise ValueError('invalid content reference')
    if self.content_after_flush:
     a['storage_pending']=True;self.message='Saving received material • admission tick unknown'
     def committed():
      if not a.get('storage_pending'):return
      a['storage_pending']=False
      if not self._valid(a):self._cancel_buffer(a);self._cancel_done(a);return
      a['cache_ref']=ref;self._submit_result(a)
     def failed(_error):
      if not a.get('storage_pending'):return
      a['storage_pending']=False
      if not self._valid(a):self._cancel_buffer(a);self._cancel_done(a);return
      self._storage_failed(a)
     a['storage_ticket']=self.content_after_flush(committed,failed);return
    if self.content_flush:self.content_flush()
    a['cache_ref']=ref
   except Exception:a['storage_pending']=False;self._storage_failed(a);return
  self._submit_result(a)
 def _storage_failed(self,a):
  self.enabled=False;self._unschedule();a['invalid']=True;self._record(a,'error',content_storage='unavailable');self._cancel_buffer(a);self._finish(a,'Content storage unavailable; feed off')
 def _submit_result(self,a):
  if not self._valid(a):return
  def submit():
   if not self._valid(a):self._cancel_buffer(a);return
   def submitted(reply):
    if not self._valid(a):self._cancel_buffer(a);return
    if not reply.get('ok'):self._record(a,'error');self._cancel_buffer(a);self._finish(a,'Material was not accepted');return
    a['input_id']=reply['result']['id']
    self._record(a,'submitted',then=lambda:self._waiting(a))
   try:sent=self.control('submit_api',submitted,text=a['text'],origin=a['origin'],**self._fields(a))
   except (OSError,ValueError):sent=None
   if not sent:self._record(a,'error');self._cancel_buffer(a);self._finish(a,'Input channel busy; response discarded')
  self._record(a,'received',then=submit)
 def _waiting(self,a):
  if self._valid(a):self.message='Material waiting • admission tick unknown'
 def receipt(self,message):
  a=self.active if self.active and self.active['id']==message.get('request_id') else self.previous.get(message.get('request_id'))
  if not a or message.get('request_id')!=a['id'] or message.get('runtime')!=a['runtime'] or message.get('world_id')!=a['world_id']:return
  if self.previous.get(a['id'],{}).get('status')=='admitted':return
  result=message.get('result',{});signature=(message.get('request_id'),result.get('id'),result.get('state'))
  if signature in self.seen_receipts:return
  self.seen_receipts[signature]=True
  while len(self.seen_receipts)>256:self.seen_receipts.popitem(last=False)
  if result.get('state')=='consumed':
   a['input_id']=result.get('id');stamp=result.get('admitted_stamp')
   def admitted():
    if not self._valid(a):return
    if self.on_admitted and a.get('text'):
     try:self.on_admitted(dict(request_id=a['id'],text=a['text'],origin=a.get('origin'),admitted_stamp=stamp,cache_ref=a.get('cache_ref')))
     except Exception:self.message='Material entered; floating display unavailable'
    self._finish(a,'Material entered at tick %s'%(stamp.get('tick') if stamp else 'unknown'))
   self._record(a,'admitted',then=admitted,admitted_stamp=stamp)
  elif result.get('state') in ('failed','cancelled'):self._record(a,'error');self._finish(a,'Material was not admitted')
 def status_text(self):
  if not self.state:return self.message
  countdown=max(0,self.state['next_auto_after']-(time.monotonic()-self.state_at))
  return '%s • %d/33 used • %d remaining • next automatic opportunity in %ds'%(self.message,self.state['used'],self.state['remaining'],countdown+0.999)

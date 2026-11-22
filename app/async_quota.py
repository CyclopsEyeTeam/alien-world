"""Serial durable allowance operations, away from the display/event thread.

Cached status is advisory. Only a completed reserve operation authorizes a
provider attempt. Receipt continuations likewise run after the existing ledger
transaction commits. No credential, model call or hive clock belongs here.
"""
from collections import deque
from concurrent.futures import Future
import copy
import json
import threading
import time

from api_quota import QuotaLedger,QuotaDenied,QuotaUnavailable

_OPERATIONS={'status','reserve','record','reset','receipts'}
_MAX_ARGUMENT_BYTES=16384


def _future():
 result=Future();result.set_running_or_notify_cancel();return result


class _Job:
 def __init__(self,operation,args):
  self.operation=operation;self.args=args;self.future=_future();self.observers=[]


class QuotaWorker:
 background_worker=True
 def __init__(self,directory,dispatch,now_ns=None,boot_id=None,max_pending=64):
  if not callable(dispatch):raise ValueError('allowance callbacks require an owner dispatcher')
  if type(max_pending) is not int or not 1<=max_pending<=4096:raise ValueError('invalid allowance queue capacity')
  self.directory=directory;self.dispatch=dispatch;self.max_pending=max_pending
  self.condition=threading.Condition(threading.RLock());self.jobs=deque();self.pending=0;self.callbacks=0
  self.closed=False;self.error=None;self.dispatch_error=None;self.cached=None;self.cached_at=None;self.saved=[];self.coalesced=None
  self.ready=_future();self._settings={}
  if now_ns is not None:self._settings['now_ns']=now_ns
  if boot_id is not None:self._settings['boot_id']=boot_id
  self.thread=threading.Thread(target=self._run,name='alien-api-allowance',daemon=True);self.thread.start()
 def status(self):
  with self.condition:
   if self.error is not None:raise self.error
   if self.cached is None:raise QuotaUnavailable('allowance worker is initializing')
   state=copy.deepcopy(self.cached);elapsed=max(0.,time.monotonic()-self.cached_at)
  for key in ('retry_after','next_auto_after'):state[key]=max(0.,state[key]-elapsed)
  state['blocked']=state['retry_after']>0
  return state
 def receipts(self):
  with self.condition:
   if self.error is not None:raise self.error
   if self.cached is None:raise QuotaUnavailable('allowance worker is initializing')
   return copy.deepcopy(self.saved)
 def statistics(self):
  with self.condition:
   return dict(pending_operations=self.pending,pending_callbacks=self.callbacks,max_pending=self.max_pending,
               ready=self.cached is not None,closed=self.closed,failed=self.error is not None,
               error=str(self.error) if self.error else None,dispatch_error=self.dispatch_error,worker_alive=self.thread.is_alive())
 def _check(self):
  if self.closed:raise QuotaUnavailable('allowance worker is closed')
  if self.error is not None:raise self.error
 def _observer(self,job,success,error):
  if success is None and error is None:return
  if success is not None and not callable(success) or error is not None and not callable(error):raise ValueError('invalid allowance callback')
  if self.callbacks>=self.max_pending:raise QuotaUnavailable('allowance callback queue is full')
  job.observers.append((success,error));self.callbacks+=1
 def submit(self,operation,args=(),success=None,error=None):
  if operation not in _OPERATIONS:raise ValueError('unsupported allowance operation')
  if not isinstance(args,(tuple,list)):raise ValueError('allowance arguments must be a sequence')
  raw=json.dumps(args,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
  if len(raw)>_MAX_ARGUMENT_BYTES:raise ValueError('allowance arguments exceed capacity')
  frozen=json.loads(raw)
  with self.condition:
   self._check()
   if self.pending>=self.max_pending:raise QuotaUnavailable('allowance operation queue is full')
   job=_Job(operation,frozen);self._observer(job,success,error)
   self.jobs.append(job);self.pending+=1;self.coalesced=None
   if operation=='status':self.coalesced=job
   self.condition.notify();return job.future
 def refresh(self,success=None,error=None):
  with self.condition:
   self._check();job=self.coalesced
   if job is not None and not job.future.done():
    self._observer(job,success,error);return job.future
   return self.submit('status',success=success,error=error)
 def _state(self,value):
  with self.condition:self.cached=copy.deepcopy(value);self.cached_at=time.monotonic()
 def _receipt(self,args):
  ident,status=args[:2];text=args[2] if len(args)>2 else '';metadata=args[3] if len(args)>3 else None
  row=dict(id=ident,status=status,text=text,metadata=copy.deepcopy(metadata or {}))
  with self.condition:
   for index,existing in enumerate(self.saved):
    if existing['id']==ident:self.saved[index]=row;break
   else:self.saved.append(row)
   self.saved=self.saved[-128:]
 def _notify(self,success,error,result,failure):
  chosen=error if failure is not None else success;value=failure if failure is not None else copy.deepcopy(result)
  invoked=[False];released=[False]
  def release():
   with self.condition:
    if not released[0]:released[0]=True;self.callbacks-=1;self.condition.notify_all()
  def invoke():
   with self.condition:
    if invoked[0]:return False
    invoked[0]=True
   try:
    if chosen is not None:chosen(value)
   finally:release()
   return False
  if chosen is None:release();return
  try:self.dispatch(invoke)
  except BaseException as exception:
   # A failed owner-loop dispatcher cannot revoke already committed data.
   # It is diagnostic, while the caller's Future remains a durability receipt.
   with self.condition:self.dispatch_error=type(exception).__name__+': '+str(exception)[:160]
   release()
 def _complete(self,job,result=None,failure=None):
  with self.condition:
   self.pending-=1
   if self.coalesced is job:self.coalesced=None
   observers=list(job.observers);self.condition.notify_all()
  if failure is None:job.future.set_result(copy.deepcopy(result))
  else:job.future.set_exception(failure)
  for success,error in observers:self._notify(success,error,result,failure)
 def _failed(self,error):
  failure=error if isinstance(error,QuotaUnavailable) else QuotaUnavailable('allowance worker failed; preserve ledger')
  with self.condition:
   self.error=failure;waiting=list(self.jobs);self.jobs.clear();self.coalesced=None;self.condition.notify_all()
  if not self.ready.done():self.ready.set_exception(failure)
  for job in waiting:self._complete(job,failure=failure)
  return failure
 def _run(self):
  try:
   ledger=QuotaLedger(self.directory,**self._settings);self._state(ledger.status())
   saved=ledger.receipts()
   with self.condition:self.saved=copy.deepcopy(saved)
   self.ready.set_result(self.status())
   while True:
    with self.condition:
     while not self.jobs and not self.closed:self.condition.wait()
     if not self.jobs:return
     job=self.jobs.popleft()
    try:
     result=getattr(ledger,job.operation)(*job.args)
     if job.operation in ('status','reserve','reset'):self._state(result)
     elif job.operation=='record':self._receipt(job.args)
     elif job.operation=='receipts':
      with self.condition:self.saved=copy.deepcopy(result)
    except QuotaDenied as error:
     # A full allowance is a normal refusal, not storage corruption. Refresh
     # its advisory status on this same thread before reporting the denial.
     try:self._state(ledger.status())
     except QuotaUnavailable as failure:
      with self.condition:self.error=failure
      self._complete(job,failure=failure);self._failed(failure);return
     self._complete(job,failure=error)
    except (ValueError,TypeError) as error:self._complete(job,failure=error)
    except BaseException as error:
     failure=error if isinstance(error,QuotaUnavailable) else QuotaUnavailable('allowance operation failed; preserve ledger')
     with self.condition:self.error=failure
     self._complete(job,failure=failure);self._failed(failure);return
    else:self._complete(job,result=result)
  except BaseException as error:self._failed(error)
 def close(self,timeout=4):
  if type(timeout) not in (int,float) or not 0<=timeout<=60:raise ValueError('invalid allowance drain timeout')
  with self.condition:self.closed=True;self.condition.notify_all()
  if threading.current_thread() is self.thread:raise QuotaUnavailable('allowance callbacks must close from their owner loop')
  self.thread.join(timeout=timeout)
  if self.thread.is_alive():raise QuotaUnavailable('allowance records did not drain before close')
  with self.condition:
   if self.error is not None:raise self.error
   if self.pending:raise QuotaUnavailable('allowance work remains unacknowledged')

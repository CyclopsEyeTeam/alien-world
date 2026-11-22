"""Bounded FIFO with a cancellation slot; a full socket never discards a stop."""
from collections import deque
class SendQueue:
 def __init__(self,write,limit=64):self.write=write;self.limit=limit;self.pending=deque()
 def put(self,record):
  operation=record.get('op');cancel=operation in ('cancel_api','cancel_eye')
  if len(self.pending)>=self.limit and cancel and any(r.get('op')==operation for r in self.pending):return False
  maximum=self.limit+(2 if cancel else 0)
  if len(self.pending)>=maximum:return False
  if not self.pending and self.write(record):return True
  self.pending.append(record);return True
 def flush(self):
  while self.pending:
   if not self.write(self.pending[0]):return False
   self.pending.popleft()
  return True

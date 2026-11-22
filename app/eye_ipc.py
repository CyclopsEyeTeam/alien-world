"""Private bounded Eye messages, with immutable anonymous image blobs over SCM_RIGHTS.

Images never need a pathname. Each received descriptor is checked, read once
and closed before returning. A full socket discards only the unsent image.
"""
import array,fcntl,json,os,socket,stat

MAX_WIRE=128*1024
MAX_BLOB=8*1024*1024
_SEALS=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL

def _wire(record,size):
 if not isinstance(record,dict):raise ValueError('Eye record must be an object')
 try:data=json.dumps({'v':1,'record':record,'blob_bytes':size},ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
 except (TypeError,ValueError,RecursionError):raise ValueError('invalid Eye record') from None
 if len(data)>MAX_WIRE:raise ValueError('Eye record exceeds channel bound')
 return data

def send(sock,record,blob=None):
 """Send atomically, returning False on backpressure without retaining an FD."""
 if blob is not None and (not isinstance(blob,bytes) or not 1<=len(blob)<=MAX_BLOB):raise ValueError('Eye blob exceeds channel bound')
 size=len(blob) if blob is not None else 0;data=_wire(record,size);fd=None
 try:
  ancillary=[]
  if blob is not None:
   fd=os.memfd_create('alien-eye-image',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
   view=memoryview(blob)
   while view:
    count=os.write(fd,view)
    if count<=0:raise OSError('image channel write failed')
    view=view[count:]
   fcntl.fcntl(fd,fcntl.F_ADD_SEALS,_SEALS);os.lseek(fd,0,os.SEEK_SET)
   ancillary=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))]
  try:count=sock.sendmsg([data],ancillary,socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)
  except BlockingIOError:return False
  if count!=len(data):raise ValueError('incomplete Eye message')
  return True
 finally:
  if fd is not None:os.close(fd)

def recv(sock):
 """Return (record, image bytes or None), or None when no complete message waits."""
 try:data,ancillary,flags,_address=sock.recvmsg(MAX_WIRE+1,socket.CMSG_SPACE(4*4),socket.MSG_DONTWAIT|socket.MSG_CMSG_CLOEXEC)
 except BlockingIOError:return None
 fds=[];bad_ancillary=False
 try:
  for level,kind,value in ancillary:
   if level!=socket.SOL_SOCKET or kind!=socket.SCM_RIGHTS:bad_ancillary=True;continue
   values=array.array('i');values.frombytes(value[:len(value)-len(value)%values.itemsize]);fds.extend(values)
   if len(value)%values.itemsize:bad_ancillary=True
  if flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC) or len(data)>MAX_WIRE or bad_ancillary:raise ValueError('truncated or unsupported Eye message')
  if not data:raise EOFError('Eye channel closed')
  try:
   value=json.loads(data);json.dumps(value,allow_nan=False)
  except (ValueError,TypeError,UnicodeError,RecursionError):raise ValueError('invalid Eye message') from None
  if not isinstance(value,dict) or set(value)!={'v','record','blob_bytes'} or type(value['v']) is not int or value['v']!=1 or not isinstance(value['record'],dict):raise ValueError('invalid Eye envelope')
  size=value['blob_bytes']
  if type(size) is not int or not 0<=size<=MAX_BLOB or len(fds)!=(1 if size else 0):raise ValueError('invalid Eye blob descriptors')
  blob=None
  if size:
   fd=fds[0];info=os.fstat(fd)
   try:sealed=fcntl.fcntl(fd,fcntl.F_GET_SEALS)
   except OSError:raise ValueError('Eye image must be a sealed anonymous file') from None
   if not stat.S_ISREG(info.st_mode) or info.st_size!=size or sealed&_SEALS!=_SEALS:raise ValueError('invalid or mutable Eye image')
   os.lseek(fd,0,os.SEEK_SET);chunks=[];remaining=size
   while remaining:
    part=os.read(fd,min(remaining,1024*1024))
    if not part:raise ValueError('short Eye image')
    chunks.append(part);remaining-=len(part)
   blob=b''.join(chunks)
  return value['record'],blob
 finally:
  for fd in fds:
   try:os.close(fd)
   except OSError:pass

"""Owner-selected local credentials. Never source the file or export its contents."""
import os,stat,re,resource
from pathlib import Path
from api_config import PRESETS
NAMES={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}
def read_keys(path):
 fd=None
 try:
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>16384:raise ValueError()
  raw=os.read(fd,16385)
  if len(raw)>16384:raise ValueError()
  values={}
  for line in raw.decode('utf-8').splitlines():
   match=re.fullmatch(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*',line)
   if not match or match[1] not in NAMES.values():continue
   name,value=match.groups()
   if name in values:raise ValueError()
   if value[:1] in ('"',"'"):
    quote=value[0];end=value.find(quote,1)
    if end<1 or (value[end+1:].strip() and not value[end+1:].lstrip().startswith('#')):raise ValueError()
    value=value[1:end]
   else:value=re.split(r'\s+#',value,maxsplit=1)[0].strip()
   if not 1<=len(value.encode())<=4096 or any(ord(c)<33 for c in value):raise ValueError()
   values[name]=value
  return values
 except (OSError,ValueError,UnicodeError):raise ValueError('Local key file unavailable or invalid') from None
 finally:
  if fd is not None:os.close(fd)
class Token:
 def __init__(self):self.cancelled=False
 def cancel(self):self.cancelled=True
class FileKeys:
 def __init__(self,path,dispatch=None):
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));self.path=Path(path);self.source_label='Keys from '+str(self.path)
  if dispatch is None:
   from gi.repository import GLib
   dispatch=GLib.idle_add
  self.dispatch=dispatch
 def lookup(self,config,callback):
  token=Token()
  def done():
   if token.cancelled:return False
   key=None;error=None
   try:
    if config.provider=='mist':
     from mist import LOCAL_MIST_TOKEN
     config.validate();key=LOCAL_MIST_TOKEN
    else:
     if config.provider not in NAMES or config.url()!=PRESETS[config.provider]:raise ValueError()
     key=read_keys(self.path).get(NAMES[config.provider])
    if not key:raise ValueError()
   except (ValueError,OSError):error='Key unavailable; check the local file and official provider endpoint'
   if not token.cancelled:callback(key,error)
   return False
  self.dispatch(done);return token

"""Async system keyring only. No fallback files and no stored-key UI prefill."""
import hashlib,resource
class Keyring:
 def __init__(self,profile):
  resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  import gi
  gi.require_version('Secret','1');from gi.repository import Secret,Gio
  self.S=Secret;self.Gio=Gio;self.profile=hashlib.sha256(str(profile).encode()).hexdigest()
  self.schema=Secret.Schema.new('org.cyclops.AlienWorld.ApiKey',Secret.SchemaFlags.NONE,{'profile':Secret.SchemaAttributeType.STRING,'binding':Secret.SchemaAttributeType.STRING})
 def _attrs(self,config):return {'profile':self.profile,'binding':config.key_binding()}
 def lookup(self,config,callback):
  cancel=self.Gio.Cancellable()
  def done(_source,result,*_):
   try:key=self.S.password_lookup_finish(result)
   except Exception:callback(None,'Keyring unavailable or locked');return
   callback(key,None if key else 'No saved key for this endpoint')
  self.S.password_lookup(self.schema,self._attrs(config),cancel,done,None);return cancel
 def save(self,config,key,callback):
  cancel=self.Gio.Cancellable()
  def done(_source,result,*_):
   try:ok=self.S.password_store_finish(result)
   except Exception:callback('Keyring unavailable or locked');return
   callback(None if ok else 'Keyring did not save the key')
  self.S.password_store(self.schema,self._attrs(config),self.S.COLLECTION_DEFAULT,'Alien World API · '+config.provider,key,cancel,done,None);return cancel

"""Installation-wide rolling allowance. Host elapsed time never enters hive ticks."""
from pathlib import Path
from contextlib import contextmanager
import sqlite3,time,os,fcntl,json
WINDOW=3600*10**9
LIMIT=33
SPACING=WINDOW//LIMIT+1
class QuotaDenied(RuntimeError):pass
class QuotaUnavailable(RuntimeError):pass

def boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def elapsed_ns():return time.clock_gettime_ns(time.CLOCK_BOOTTIME)

class QuotaLedger:
 def __init__(self,directory,now_ns=elapsed_ns,boot_id=None):
  self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.root.chmod(0o700)
  self.path=self.root/'quota.sqlite3';self.sentinel=self.root/'quota.initialized';self.now_ns=now_ns;self.boot=boot_id or globals()['boot_id']()
  fd=os.open(self.root/'quota-init.lock',os.O_CREAT|os.O_RDWR,0o600)
  try:
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:raise QuotaUnavailable('allowance initialization busy') from None
   if not self.path.exists():
    if self.sentinel.exists():raise QuotaUnavailable('initialized allowance is missing')
    dbfd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(dbfd)
    try:
     with self._db() as c:
      c.execute('CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
      c.execute('CREATE TABLE attempts(id TEXT PRIMARY KEY,ns INTEGER NOT NULL)')
      c.execute('CREATE TABLE receipts(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,status TEXT NOT NULL,text TEXT NOT NULL,metadata TEXT NOT NULL)')
      c.executemany('INSERT INTO meta VALUES(?,?)',[('version','1'),('boot',self.boot),('last',str(self._now())),('blocked','0')])
    except Exception:raise QuotaUnavailable('allowance initialization failed; preserve ledger') from None
   else:
    with self._db() as c:self._meta(c)
   # These control tables retain owner-cleared reservation identities. The
   # existing version/four-key metadata and receipt contents remain intact.
   with self._db() as c:
    c.execute('CREATE TABLE IF NOT EXISTS retired_attempts(id TEXT PRIMARY KEY,ns INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS reset_audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,ns INTEGER NOT NULL,boot TEXT NOT NULL,cleared INTEGER NOT NULL)')
   if not self.sentinel.exists():
    mark=os.open(self.sentinel,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:os.write(mark,b'initialized\n');os.fsync(mark)
    finally:os.close(mark)
  finally:os.close(fd)
 def _now(self):
  value=self.now_ns()
  if type(value) is not int or not 0<=value<2**63:raise QuotaUnavailable('invalid allowance clock')
  return value
 @contextmanager
 def _db(self):
  if not self.path.exists():raise QuotaUnavailable('allowance ledger missing')
  c=None
  try:
   c=sqlite3.connect(self.path,timeout=.2,isolation_level=None);c.execute('BEGIN IMMEDIATE');yield c;c.commit()
  except sqlite3.Error:
   if c:c.rollback()
   raise QuotaUnavailable('allowance ledger unavailable; preserve evidence') from None
  except BaseException:
   if c:c.rollback()
   raise
  finally:
   if c:c.close()
 def _meta(self,c):
  m=dict(c.execute('SELECT k,v FROM meta'))
  if set(m)!={'version','boot','last','blocked'} or m['version']!='1':raise QuotaUnavailable('unsupported allowance ledger')
  for field in ('last','blocked'):
   try:value=int(m[field])
   except (ValueError,TypeError):raise QuotaUnavailable('invalid allowance accounting; preserve ledger') from None
   if str(value)!=m[field] or not 0<=value<2**63:raise QuotaUnavailable('invalid allowance accounting; preserve ledger')
  if not isinstance(m['boot'],str) or not 1<=len(m['boot'])<=128 or int(m['blocked'])>int(m['last'])+WINDOW:raise QuotaUnavailable('invalid allowance accounting; preserve ledger')
  return m
 def _maintain(self,c):
  m=self._meta(c);now=self._now();last=int(m['last']);blocked=int(m['blocked'])
  rows=c.execute('SELECT id,ns FROM attempts').fetchall()
  self._reservations(rows,last)
  if m['boot']!=self.boot:
   c.execute('INSERT OR IGNORE INTO retired_attempts(id,ns) SELECT id,ns FROM attempts')
   blocked=now+WINDOW;last=now;c.execute('DELETE FROM attempts');m['boot']=self.boot
  elif now<last:blocked=max(blocked,last+WINDOW)
  last=max(last,now)
  c.executemany('UPDATE meta SET v=? WHERE k=?',[(self.boot,'boot'),(str(last),'last'),(str(blocked),'blocked')])
  c.execute('DELETE FROM attempts WHERE ns<=?',(now-WINDOW,))
  count,oldest,newest=c.execute('SELECT count(*),min(ns),max(ns) FROM attempts').fetchone()
  retry=max(0,blocked-now,(oldest+WINDOW-now) if count>=LIMIT else 0)
  auto=max(retry,(newest+SPACING-now) if newest is not None else 0)
  return dict(used=count,remaining=max(0,LIMIT-count),limit=LIMIT,retry_after=retry/1e9,next_auto_after=max(0,auto)/1e9,blocked=retry>0),now
 def _reservations(self,rows,last):
  if len(rows)>LIMIT or any(not isinstance(ident,str) or not 1<=len(ident)<=96 or type(ns) is not int or not 0<=ns<=last for ident,ns in rows):raise QuotaUnavailable('invalid reservations; preserve ledger')
 def status(self):
  with self._db() as c:state,_=self._maintain(c)
  return state
 def reserve(self,ident):
  if not isinstance(ident,str) or not 1<=len(ident)<=96:raise QuotaDenied('invalid request identifier')
  denial=None
  with self._db() as c:
   state,now=self._maintain(c)
   duplicate=c.execute('SELECT 1 FROM attempts WHERE id=? UNION ALL SELECT 1 FROM receipts WHERE id=? UNION ALL SELECT 1 FROM retired_attempts WHERE id=?',(ident,ident,ident)).fetchone()
   if duplicate:denial='request identifier already reserved'
   elif state['blocked'] or state['used']>=LIMIT:denial=str(LIMIT)+'-per-hour allowance unavailable'
   else:c.execute('INSERT INTO attempts VALUES(?,?)',(ident,now))
  if denial:raise QuotaDenied(denial)
  return self.status()
 def record(self,ident,status,text='',metadata=None):
  if status not in ('error','cancelled','received','submitted','admitted'):raise ValueError('invalid request receipt status')
  if not isinstance(text,str) or len(text.encode('utf-8'))>4096:raise ValueError('receipt text too large')
  meta=json.dumps(metadata or {},ensure_ascii=False,allow_nan=False)
  if len(meta.encode('utf-8'))>4096:raise ValueError('receipt metadata too large')
  with self._db() as c:
   if not c.execute('SELECT 1 FROM attempts WHERE id=? UNION ALL SELECT 1 FROM receipts WHERE id=? UNION ALL SELECT 1 FROM retired_attempts WHERE id=?',(ident,ident,ident)).fetchone():raise QuotaUnavailable('unreserved request receipt')
   c.execute('INSERT INTO receipts(id,status,text,metadata) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,text=excluded.text,metadata=excluded.metadata',(ident,status,text,meta))
   c.execute('DELETE FROM receipts WHERE seq NOT IN (SELECT seq FROM receipts ORDER BY seq DESC LIMIT 128)')
 def receipts(self):
  with self._db() as c:rows=c.execute('SELECT id,status,text,metadata FROM receipts ORDER BY seq').fetchall()
  return [dict(id=i,status=s,text=t,metadata=json.loads(m)) for i,s,t,m in rows]
 def reset(self):
  """Owner-only control: start a fresh allowance without erasing receipts.

  The feed refuses this action while a physical request is active. Reservation
  identities are retained even when a prior interrupted request had no receipt.
  An explicit owner reset also acknowledges a changed boot/elapsed clock; it
  cannot replace a missing or corrupt ledger.
  """
  with self._db() as c:
   meta=self._meta(c);rows=c.execute('SELECT id,ns FROM attempts').fetchall();self._reservations(rows,int(meta['last']));now=self._now()
   c.execute('INSERT OR IGNORE INTO retired_attempts(id,ns) SELECT id,ns FROM attempts')
   c.execute('DELETE FROM attempts')
   c.executemany('UPDATE meta SET v=? WHERE k=?',[(self.boot,'boot'),(str(now),'last'),('0','blocked')])
   c.execute('INSERT INTO reset_audit(ns,boot,cleared) VALUES(?,?,?)',(now,self.boot,len(rows)))
  return self.status()

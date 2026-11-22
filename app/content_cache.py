"""One versioned byte archive, with separate fresh-world namespaces.

Only this module interprets cache references. They are identities, never paths or
instructions. Payloads are bounded zlib-compressed bytes; no executable serializer
is used. Short write batches commit on flush (or close), with SQLite's durable
rollback journal. A published reference is flushed before an external reader sees it.
"""
import hashlib,json,os,re,sqlite3,time,uuid,zlib
from pathlib import Path

MAX_BYTES=16*1024*1024
MAX_METADATA=256*1024
MAX_PENDING_BYTES=32*1024*1024
REF=re.compile(r'alien-cache:v1:([0-9a-f]{32}):([0-9a-f]{32}):([0-9a-f]{64})\Z')
KIND=re.compile(r'[a-z][a-z0-9_.-]{0,63}\Z')

class CacheBusy(OSError):pass

def json_bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def _json(raw):
    def bad(value):raise ValueError('non-finite cache number')
    return json.loads(raw.decode('utf-8'),parse_constant=bad)

def reference_identity(ref):
    match=REF.fullmatch(ref) if isinstance(ref,str) else None
    if match is None:raise ValueError('invalid content cache reference')
    return match.groups()

def _world(world):
    if not isinstance(world,str) or not re.fullmatch('[0-9a-f]{32}',world):raise ValueError('invalid cache world identity')
    return world

def _kind(kind):
    if not isinstance(kind,str) or KIND.fullmatch(kind) is None:raise ValueError('invalid content kind')
    return kind

def _unpack(row,ref,max_bytes):
    if row is None:return None
    payload,digest,size=row
    if not isinstance(payload,bytes) or type(size) is not int or not 0<=size<=min(max_bytes,MAX_BYTES) or len(payload)>MAX_BYTES+65536:raise ValueError('cache payload exceeds allowance')
    if digest!=reference_identity(ref)[2]:raise ValueError('cache reference digest mismatch')
    try:
        decoder=zlib.decompressobj();raw=decoder.decompress(payload,size+1)
    except zlib.error:raise ValueError('damaged compressed cache payload') from None
    if len(raw)!=size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('damaged cache payload')
    return raw

def read_reference(path,ref,world_id,kind=None,max_bytes=MAX_BYTES):
    """Read one committed record without creating a file or taking write authority."""
    world,ident,_=reference_identity(ref)
    if world!=_world(world_id):raise ValueError('cache reference belongs to a different world')
    if kind is not None:_kind(kind)
    if type(max_bytes) is not int or not 0<=max_bytes<=MAX_BYTES:raise ValueError('invalid cache read allowance')
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('content cache is unavailable')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.05)
    try:
        if db.execute('PRAGMA user_version').fetchone()[0]!=1:raise ValueError('unsupported content cache schema')
        row=db.execute('SELECT payload,digest,size,kind FROM records WHERE world=? AND id=?',(world,ident)).fetchone()
        if row is None:return None
        if kind is not None and row[3]!=kind:raise ValueError('unexpected cache content kind')
        return _unpack(row[:3],ref,max_bytes)
    except sqlite3.Error as error:raise OSError('content cache reference is unavailable') from error
    finally:db.close()

class ContentCache:
    def __init__(self,path,world_id):
        self.world_id=_world(world_id);self.path=Path(path).absolute()
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.path.is_symlink():raise ValueError('content cache must not be a symlink')
        if not self.path.exists():
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        if not self.path.is_file():raise ValueError('content cache must be a regular file')
        self.db=sqlite3.connect(self.path,timeout=.75,isolation_level=None)
        self.pending=[];self.pending_bytes=0;self.last_flush=time.monotonic();self.closed=False
        try:
            version=self.db.execute('PRAGMA user_version').fetchone()[0]
            tables={row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if not ((version==0 and not tables) or (version==1 and tables=={'records','heads'})):raise ValueError('unsupported content cache schema; preserve file')
            os.chmod(self.path,0o600)
            self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA synchronous=FULL');self.db.execute('PRAGMA temp_store=MEMORY')
            if version==0 and not tables:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('CREATE TABLE records(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,world TEXT NOT NULL,kind TEXT NOT NULL,key TEXT NOT NULL,payload BLOB NOT NULL,digest TEXT NOT NULL,size INTEGER NOT NULL,metadata BLOB NOT NULL)')
                self.db.execute('CREATE INDEX world_kind ON records(world,kind,seq)')
                self.db.execute('CREATE TABLE heads(world TEXT NOT NULL,kind TEXT NOT NULL,key TEXT NOT NULL,id TEXT NOT NULL,PRIMARY KEY(world,kind,key))')
                self.db.execute('PRAGMA user_version=1');self.db.commit()
            elif version!=1 or tables!={'records','heads'}:raise ValueError('unsupported content cache schema; preserve file')
        except BaseException:self.db.close();self.closed=True;raise
    def __enter__(self):return self
    def __exit__(self,kind,value,trace):
        self.close()
    def _open(self):
        if self.closed:raise ValueError('content cache is closed')
    def put(self,kind,key,value,metadata=None):
        self._open();_kind(kind)
        if not isinstance(key,str) or not 1<=len(key.encode('utf-8'))<=512:raise ValueError('invalid cache key')
        if not isinstance(value,bytes) or len(value)>MAX_BYTES:raise ValueError('cache content must be bounded bytes')
        if metadata is not None and not isinstance(metadata,dict):raise ValueError('cache metadata must be an object')
        encoded=json_bytes(metadata or {})
        if len(encoded)>MAX_METADATA:raise ValueError('cache metadata exceeds allowance')
        if self.pending_bytes+len(value)+len(encoded)>MAX_PENDING_BYTES:
            self.flush()
            if self.pending_bytes+len(value)+len(encoded)>MAX_PENDING_BYTES:raise CacheBusy('content cache batch is full')
        ident=uuid.uuid4().hex;digest=hashlib.sha256(value).hexdigest();ref=f'alien-cache:v1:{self.world_id}:{ident}:{digest}'
        self.pending.append((ident,self.world_id,kind,key,zlib.compress(value,3),digest,len(value),encoded))
        self.pending_bytes+=len(value)+len(encoded);self.flush_if_due()
        return ref
    def get(self,ref):
        self._open();world,ident,_=reference_identity(ref)
        if world!=self.world_id:return None
        pending=next((row for row in reversed(self.pending) if row[0]==ident),None)
        if pending is not None:return _unpack((pending[4],pending[5],pending[6]),ref,MAX_BYTES)
        row=self.db.execute('SELECT payload,digest,size FROM records WHERE world=? AND id=?',(world,ident)).fetchone()
        return _unpack(row,ref,MAX_BYTES)
    def get_json(self,kind,key,default=None):
        self._open();_kind(kind)
        pending=next((row for row in reversed(self.pending) if row[2]==kind and row[3]==key),None)
        if pending is not None:return _json(self.get(f'alien-cache:v1:{self.world_id}:{pending[0]}:{pending[5]}'))
        row=self.db.execute('SELECT r.id,r.digest FROM heads h JOIN records r ON r.id=h.id AND r.world=h.world WHERE h.world=? AND h.kind=? AND h.key=?',(self.world_id,kind,key)).fetchone()
        if row is None:return default
        return _json(self.get(f'alien-cache:v1:{self.world_id}:{row[0]}:{row[1]}'))
    def set_json(self,kind,key,value):
        self._open();_kind(kind);raw=json_bytes(value);digest=hashlib.sha256(raw).hexdigest()
        pending=next((row for row in reversed(self.pending) if row[2]==kind and row[3]==key),None)
        if pending is not None:
            if pending[5]==digest:return f'alien-cache:v1:{self.world_id}:{pending[0]}:{digest}'
        else:
            row=self.db.execute('SELECT r.id,r.digest FROM heads h JOIN records r ON r.id=h.id AND r.world=h.world WHERE h.world=? AND h.kind=? AND h.key=?',(self.world_id,kind,key)).fetchone()
            if row is not None and row[1]==digest:return f'alien-cache:v1:{self.world_id}:{row[0]}:{digest}'
        return self.put(kind,key,raw)
    def append(self,kind,value,metadata=None):return self.put(kind,uuid.uuid4().hex,value if isinstance(value,bytes) else json_bytes(value),metadata)
    def records(self,kind,limit=100):
        self._open();_kind(kind)
        if type(limit) is not int or not 1<=limit<=10000:raise ValueError('invalid cache record limit')
        rows=[(row[0],row[3],row[5],row[6],row[7],None) for row in reversed(self.pending) if row[2]==kind]
        rows+=self.db.execute('SELECT id,key,digest,size,metadata,seq FROM records WHERE world=? AND kind=? ORDER BY seq DESC LIMIT ?',(self.world_id,kind,limit)).fetchall()
        return [dict(cache_ref=f'alien-cache:v1:{self.world_id}:{ident}:{digest}',kind=kind,key=key,size=size,metadata=_json(meta),sequence=seq) for ident,key,digest,size,meta,seq in rows[:limit]]
    def flush_if_due(self):
        if self.pending and (len(self.pending)>=32 or time.monotonic()-self.last_flush>=1):
            try:self.flush(wait=False)
            except CacheBusy:return False
        return True
    def flush(self,wait=True):
        self._open()
        if self.pending:
            # Background batches never queue behind another writer. A required
            # publication/close can wait through an ordinary HDD commit, rather
            # than treating its short exclusive lock as a storage failure.
            self.db.execute('PRAGMA busy_timeout='+('750' if wait else '0'))
            try:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.executemany('INSERT INTO records(id,world,kind,key,payload,digest,size,metadata) VALUES(?,?,?,?,?,?,?,?)',self.pending)
                self.db.executemany('INSERT INTO heads(world,kind,key,id) VALUES(?,?,?,?) ON CONFLICT(world,kind,key) DO UPDATE SET id=excluded.id',[(row[1],row[2],row[3],row[0]) for row in self.pending])
                self.db.commit()
            except sqlite3.OperationalError as error:
                self.db.rollback()
                if 'locked' in str(error).lower() or 'busy' in str(error).lower():raise CacheBusy('content cache writer is busy') from None
                raise OSError('content cache commit failed') from error
            except BaseException:self.db.rollback();raise
            finally:self.db.execute('PRAGMA busy_timeout=750')
        self.pending=[];self.pending_bytes=0;self.last_flush=time.monotonic()
    def close(self):
        if self.closed:return
        try:
            for attempt in range(4):
                try:self.flush();break
                except CacheBusy:
                    if attempt==3:raise
                    time.sleep(.01)
        finally:self.db.close();self.closed=True

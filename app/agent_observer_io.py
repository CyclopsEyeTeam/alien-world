"""Same-owner status, literal words and small drawings for separate observers.

All callbacks run on the GTK main context. Words enter only the existing bounded
submit/preparation/native-tick path, with fixed external unauthority provenance.
A received reply acknowledges queue ownership, never learning or semantic truth.
A sender may name itself (observer_participants); the name is unverified
provenance, rate-limited per participant, and never authority or storage.
"""
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import observer_participants as participants

SCHEMA='ALIEN_AGENT_OBSERVER_IO_V1'
MAX_WIRE=32*1024
MAX_CLIENTS=8
MAX_REQUESTS=128
TIMEOUT_MS=10_000
STATUS_FIELDS=('schema','ready','pid','window_id','size','crop','runtime','world_id','segment_id','drawn_sequence')
IDENTIFIER=re.compile('[0-9a-f]{32}')
BINDING_FIELDS=('pid','window_id','runtime','world_id','segment_id','size','crop')


def same_owner_peer(connection,uid=None):
    """Linux supplies credentials; caller JSON never chooses its peer identity."""
    try:
        _pid,peer_uid,_gid=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
        return peer_uid==(os.getuid() if uid is None else uid)
    except (OSError,AttributeError,struct.error):
        return False


def window_status(window):
    """Actual GTK client/field geometry in physical pixels; not a capture receipt."""
    import gi
    gi.require_version('GdkX11','3.0')
    from gi.repository import GdkX11  # Registers X11 window access, without creating a window.
    world=window.world or {};stamp=world.get('clock') or {}
    result=dict(schema=SCHEMA,ready=False,pid=os.getpid(),window_id=0,size=[0,0],crop=[0,0,0,0],
                runtime=world.get('runtime'),world_id=stamp.get('world_id'),segment_id=stamp.get('segment_id'),
                drawn_sequence=int(getattr(window.area,'drawn_sequence',0)))
    native=window.get_window()
    point=window.area.translate_coordinates(window,0,0) if native is not None else None
    if native is None or point is None:return result
    scale=window.get_scale_factor()
    result.update(window_id=int(native.get_xid()),
                  size=[window.get_allocated_width()*scale,window.get_allocated_height()*scale],
                  crop=[point[0]*scale,point[1]*scale,window.area.get_allocated_width()*scale,window.area.get_allocated_height()*scale])
    result['ready']=bool(not window.stopped and not window.area.failed and window.area.gpu is not None
                         and window.message is not None and result['drawn_sequence']>0
                         and all(isinstance(result[k],str) and IDENTIFIER.fullmatch(result[k])
                                 for k in ('runtime','world_id','segment_id')))
    return result


class AgentObserverEndpoint:
    def __init__(self,status,control,*,directory=None,glib=None):
        self.status_callback=status;self.control=control;self.GLib=glib
        if directory is None:
            runtime=os.environ.get('XDG_RUNTIME_DIR')
            if not runtime:raise ValueError('Observer runtime directory unavailable')
            directory=Path(runtime)/'alienworld-observer'
        self.directory=Path(directory);self.path=self.directory/(str(os.getpid())+'.sock')
        self.listener=None;self.listener_watch=0;self.socket_identity=None
        self.clients={};self.requests=OrderedDict();self.closed=False;self.limits=participants.Limiter()

    def start(self):
        if self.listener is not None or self.closed:raise ValueError('Observer endpoint already started or closed')
        self.directory.mkdir(mode=0o700,exist_ok=True)
        info=self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('Observer directory must be a private owner directory')
        if self.path.is_symlink():raise ValueError('Observer socket cannot be a symbolic link')
        if self.path.exists():
            old=self.path.lstat()
            if not stat.S_ISSOCK(old.st_mode) or old.st_uid!=os.getuid():raise ValueError('Existing observer path preserved')
            with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as probe:
                probe.settimeout(.1)
                try:probe.connect(str(self.path))
                except ConnectionRefusedError:pass
                else:raise ValueError('Observer endpoint is already active')
            if (self.path.lstat().st_dev,self.path.lstat().st_ino)!=(old.st_dev,old.st_ino):
                raise ValueError('Observer socket changed during admission')
            self.path.unlink()
        if self.GLib is None:
            from gi.repository import GLib
            self.GLib=GLib
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        try:
            listener.setblocking(False);listener.bind(str(self.path));os.chmod(self.path,0o600)
            info=self.path.lstat();self.socket_identity=(info.st_dev,info.st_ino)
            listener.listen(MAX_CLIENTS);self.listener=listener
            self.listener_watch=self.GLib.io_add_watch(listener.fileno(),self.GLib.IO_IN|self.GLib.IO_HUP|self.GLib.IO_ERR,self._accept)
        except BaseException:
            listener.close();self.close();raise
        return self

    def _status(self):
        value=self.status_callback()
        if not isinstance(value,dict):raise ValueError('status unavailable')
        # Never serialize the full Window.world or any future private status fields.
        result={key:value.get(key) for key in STATUS_FIELDS}
        result['schema']=SCHEMA
        if result['pid']!=os.getpid() or type(result['ready']) is not bool:raise ValueError('status unavailable')
        # A context fence, not permission or proof that an agent looked at pixels.
        context={key:result[key] for key in BINDING_FIELDS}
        result['binding']=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        return result

    def _accept(self,_fd,condition):
        if self.closed:return False
        if condition&(self.GLib.IO_HUP|self.GLib.IO_ERR):
            self.listener_watch=0;self.close();return False
        for _ in range(4):
            try:connection,_address=self.listener.accept()
            except BlockingIOError:break
            connection.setblocking(False)
            if not same_owner_peer(connection) or len(self.clients)>=MAX_CLIENTS:
                connection.close();continue
            client=dict(socket=connection,watch=0,timer=0,response=None,request_id=None)
            self.clients[connection]=client
            client['timer']=self.GLib.timeout_add(TIMEOUT_MS,self._expire,client)
            self._read_watch(client)
        return True

    def _read_watch(self,client):
        client['watch']=self.GLib.io_add_watch(client['socket'].fileno(),self.GLib.IO_IN|self.GLib.IO_HUP|self.GLib.IO_ERR,self._receive,client)

    def _receive(self,_fd,condition,client):
        client['watch']=0
        if client['socket'] not in self.clients:return False
        try:
            data,_ancillary,flags,_address=client['socket'].recvmsg(MAX_WIRE+1)
            if not data:self._drop(client);return False
            if len(data)>MAX_WIRE or flags&socket.MSG_TRUNC:raise ValueError('oversized request')
            def invalid_constant(_value):raise ValueError('invalid JSON constant')
            request=json.loads(data.decode('utf-8'),parse_constant=invalid_constant)
            self._dispatch(client,request)
        except BlockingIOError:
            if condition&(self.GLib.IO_HUP|self.GLib.IO_ERR):self._drop(client)
            else:self._read_watch(client)
        except (UnicodeError,ValueError,TypeError):self._reply(client,dict(ok=False,error='invalid_request'))
        except OSError:self._drop(client)
        return False

    def _dispatch(self,client,request):
        if not isinstance(request,dict):raise ValueError('invalid request')
        if request=={'op':'status'}:
            try:result=self._status()
            except (ValueError,TypeError,AttributeError):self._reply(client,dict(ok=False,error='status_unavailable'));return
            self._reply(client,dict(ok=True,result=result));return
        op=request.get('op')
        base={'op','request_id','runtime','world_id','binding'}
        if op=='words' and set(request) in (base|{'text'},base|{'text','participant'}):pass
        elif op=='drawing' and set(request)==base|{'participant','title','png_base64'}:pass
        else:raise ValueError('Unsupported observer operation')
        rid=request['request_id']
        if not isinstance(rid,str) or not IDENTIFIER.fullmatch(rid):raise ValueError('Invalid request id')
        try:name=participants.participant(request.get('participant'))
        except ValueError:self._reply(client,dict(ok=False,error='invalid_participant'));return
        if op=='drawing':
            if name is None:self._reply(client,dict(ok=False,error='invalid_participant'));return
            try:reading=participants.decode_drawing(request['png_base64'],request['title'])
            except ValueError:self._reply(client,dict(ok=False,error='invalid_drawing'));return
            text=participants.drawing_text(name,request['title'],reading)
        else:
            text=request['text']
            if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=4096:raise ValueError('Invalid words')
        try:status=self._status()
        except (ValueError,TypeError,AttributeError):self._reply(client,dict(ok=False,error='status_unavailable'));return
        if not status['ready']:
            self._reply(client,dict(ok=False,error='world_unavailable'));return
        if request['runtime']!=status['runtime'] or request['world_id']!=status['world_id']:
            self._reply(client,dict(ok=False,error='world_changed'));return
        if request['binding']!=status['binding']:
            self._reply(client,dict(ok=False,error='observation_changed'));return
        fingerprint=hashlib.sha256(json.dumps([request['runtime'],request['world_id'],request['binding'],op,name,text],ensure_ascii=False).encode()).hexdigest()
        old=self.requests.get(rid)
        if old is not None:
            if old['fingerprint']!=fingerprint:self._reply(client,dict(ok=False,error='request_id_conflict'));return
            self.requests.move_to_end(rid)
            if old['answer'] is not None:self._reply(client,old['answer'])
            else:old['waiting'].append(client);client['request_id']=rid
            return
        while len(self.requests)>=MAX_REQUESTS:
            oldest=next((key for key,item in self.requests.items() if item['answer'] is not None),None)
            if oldest is None:self._reply(client,dict(ok=False,error='input_busy'));return
            self.requests.pop(oldest)
        allowed,detail=self.limits.take(name,op)
        if not allowed:
            answer=dict(ok=False,error='rate_limited',retry_after_s=detail) if detail!='participants_full' else dict(ok=False,error='participants_full')
            self._reply(client,answer);return
        entry=dict(fingerprint=fingerprint,answer=None,waiting=[client])
        self.requests[rid]=entry;client['request_id']=rid
        def acknowledged(reply):
            if self.closed or entry['answer'] is not None:return
            result=reply.get('result') if isinstance(reply,dict) and reply.get('ok') is True else None
            if (isinstance(result,dict) and isinstance(result.get('id'),str) and 1<=len(result['id'])<=96
                    and result.get('state')=='received' and result.get('admitted_stamp') is None):
                answer=dict(ok=True,result=dict(request_id=rid,input_id=result['id'],state='received',admitted_stamp=None,
                                                source=participants.source(name),authority='unauthority'))
                # Unnamed (existing MCP) replies keep their exact earlier shape.
                if name is not None:answer['result'].update(participant=name,kind=op)
                self.limits.note(name,'received')
            else:answer=dict(ok=False,error='input_refused');self.limits.note(name,'refused')
            self._complete(entry,answer)
        try:sequence=self.control('submit',acknowledged,text=text,label=participants.label(name,op),source=participants.source(name),authority='unauthority')
        except (OSError,ValueError,TypeError):
            # A dispatch exception is physically ambiguous; retain its ID and never retry it as a fresh submission.
            self._complete(entry,dict(ok=False,error='input_status_unknown'));return
        if sequence is None and entry['answer'] is None:
            self._complete(entry,dict(ok=False,error='input_busy'));self.requests.pop(rid,None)

    def participant_summary(self):
        """Scalar counts per participant name; never any text."""
        return self.limits.summary()

    def _complete(self,entry,answer):
        entry['answer']=answer
        waiting=entry['waiting'];entry['waiting']=[]
        for client in waiting:self._reply(client,answer)

    def _reply(self,client,answer):
        if client['socket'] not in self.clients:return
        client['response']=json.dumps(answer,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        self._flush(client)

    def _flush(self,client):
        try:
            if client['socket'].send(client['response'])!=len(client['response']):self._drop(client);return
        except BlockingIOError:
            client['watch']=self.GLib.io_add_watch(client['socket'].fileno(),self.GLib.IO_OUT|self.GLib.IO_HUP|self.GLib.IO_ERR,self._write_ready,client);return
        except OSError:pass
        self._drop(client)

    def _write_ready(self,_fd,_condition,client):
        client['watch']=0
        if client['socket'] in self.clients:self._flush(client)
        return False

    def _expire(self,client):
        client['timer']=0;self._drop(client);return False

    def _drop(self,client):
        connection=client['socket']
        if self.clients.pop(connection,None) is None:return
        for field in ('watch','timer'):
            if client[field]:self.GLib.source_remove(client[field]);client[field]=0
        entry=self.requests.get(client.get('request_id'))
        if entry is not None:entry['waiting']=[c for c in entry['waiting'] if c is not client]
        connection.close()

    def close(self):
        if self.closed:return
        self.closed=True
        if self.listener_watch:self.GLib.source_remove(self.listener_watch);self.listener_watch=0
        for client in list(self.clients.values()):self._drop(client)
        self.requests.clear()
        if self.listener is not None:self.listener.close();self.listener=None
        if self.socket_identity is not None:
            try:
                info=self.path.lstat()
                if (info.st_dev,info.st_ino)==self.socket_identity and stat.S_ISSOCK(info.st_mode):self.path.unlink()
            except OSError:pass # A stale private socket must never block owner Stop.

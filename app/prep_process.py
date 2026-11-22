"""Own one low-duty-cycle preparer; no event bus or hive identity."""
import socket,subprocess
from pathlib import Path
from ingress import packed
MAX_WIRE=128*1024

def read_packet(sock):
    try:data,_,flags,_=sock.recvmsg(MAX_WIRE)
    except BlockingIOError:return None
    if not data:raise EOFError('preparer disconnected')
    if flags&socket.MSG_TRUNC:raise ValueError('oversized control packet')
    import json
    value=json.loads(data)
    if not isinstance(value,dict):raise ValueError('invalid control record')
    return value

def write_packet(sock,value):
    data=packed(value)
    if len(data)>MAX_WIRE:raise ValueError('oversized control record')
    try:return sock.send(data)==len(data)
    except BlockingIOError:return False

class Preparer:
    def __init__(self,directory):self.directory=Path(directory);self.process=None;self.socket=None;self.forced=False;self.log=None
    def start(self):
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);a.setblocking(False);b.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,262144)
        self.socket=a;self.log=open(self.directory/'preparer.log','ab')
        try:
            self.process=subprocess.Popen(['/usr/bin/python3','-B',str(Path(__file__).with_name('prepare.py')),'--fd',str(b.fileno())],pass_fds=(b.fileno(),),stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        except BaseException:self.stop();raise
        finally:b.close()
    def send(self,job):return write_packet(self.socket,job)
    def receive(self):return read_packet(self.socket)
    def stop(self):
        if self.socket:self.socket.close();self.socket=None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.forced=True;self.process.kill();self.process.wait(timeout=2)
        if self.log:self.log.close();self.log=None

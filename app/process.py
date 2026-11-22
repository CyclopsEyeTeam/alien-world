"""Own one native worker, using continuing storage or an isolated fixture."""
import os,socket,subprocess,sys,tempfile
from pathlib import Path
from pacing import Pacer
from protocol import _geometry,MAX_PACKET
class Worker:
    def __init__(self,session_parent,*,cols=160,rows=48,fps=0,content_cache=None,continuous=False):
        _geometry(cols,rows)
        Pacer(fps);self.parent=Path(session_parent);self.cols=cols;self.rows=rows;self.fps=fps
        self.continuous=bool(continuous)
        self.content_cache=Path(content_cache) if content_cache else self.parent/'alien.cache'
        self.process=None;self.socket=None;self.control=None;self.log=None;self.session=None;self.forced=False;self.stop_error=None
    def start(self):
        if self.process is not None:raise RuntimeError('worker already started')
        self.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.continuous:
            if self.parent.is_symlink():raise ValueError('World directory must not be a symlink')
            self.directory=self.parent
        else:self.directory=Path(tempfile.mkdtemp(prefix='fresh-',dir=self.parent))
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);a.setblocking(False);b.setblocking(False)
        b.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,MAX_PACKET*4)
        self.socket=a;self.log=open(self.directory/'engine.log','ab')
        c,d=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);c.setblocking(False);d.setblocking(False)
        c.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,262144);d.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,262144);self.control=c
        # Engine requires an empty data folder; process logs live alongside it.
        state=self.directory/('runtime' if self.continuous else 'state')
        if state.is_symlink():raise ValueError('Runtime directory must not be a symlink')
        state.mkdir(mode=0o700,exist_ok=self.continuous)
        self.session=state;self.state=state
        try:
            self.process=subprocess.Popen([sys.executable or '/usr/bin/python3','-B',str(Path(__file__).with_name('engine.py')),'--fd',str(b.fileno()),'--control-fd',str(d.fileno()),'--session',str(state),'--content-cache',str(self.content_cache),'--cols',str(self.cols),'--rows',str(self.rows),'--fps',str(self.fps)]+(['--continue-world'] if self.continuous else []),
                stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,pass_fds=(b.fileno(),d.fileno()),start_new_session=True,
                env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        except BaseException:
            self.stop();raise
        finally:b.close();d.close()
    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                code=self.process.wait(timeout=15)
                if code:self.stop_error='Engine exited with status '+str(code)
            except subprocess.TimeoutExpired:
                import signal
                self.forced=True;self.stop_error='Engine archive drain exceeded 15 seconds'
                os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=2)
        if self.socket:self.socket.close();self.socket=None
        if self.control:self.control.close();self.control=None
        if self.log:self.log.close();self.log=None

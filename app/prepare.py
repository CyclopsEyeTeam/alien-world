"""Bounded local content preparation. CPU allowance uses measured process CPU."""
import time,resource,argparse,socket
from prep_process import read_packet,write_packet
from ingress import MAX_INPUT,RESULT,packed

def main(fd):
    import os,signal,ctypes
    parent=os.getppid();lib=ctypes.CDLL(None)
    if lib.prctl(1,signal.SIGTERM,0,0,0)!=0:raise RuntimeError('parent lifecycle containment unavailable')
    if os.getppid()!=parent:return
    wall0=time.monotonic();cpu0=time.process_time()
    inherited=resource.getrlimit(resource.RLIMIT_AS)[1];limit=128*1024*1024
    if inherited!=resource.RLIM_INFINITY:limit=min(limit,inherited)
    resource.setrlimit(resource.RLIMIT_AS,(limit,limit));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    from reference import load_reference
    ns=load_reference();sock=socket.socket(fileno=fd);sock.setblocking(True)
    def allowance():
        debt=(time.process_time()-cpu0)/.1-(time.monotonic()-wall0)
        if debt>0:time.sleep(debt)
    try:
        allowance()
        while True:
            try:job=read_packet(sock)
            except EOFError:return
            if job is None:continue
            text=job.get('text');label=job.get('label','')
            if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=MAX_INPUT or not isinstance(label,str) or len(label)>80:raise ValueError('invalid preparation input')
            normal=' '.join(text.split());label=label or normal[:80] or '(whitespace)'
            result=dict(runtime=job['runtime'],id=job['id'],label=label,vec=ns['compose_vector'](normal,None))
            if len(packed(result))>RESULT:raise ValueError('preparation result exceeds allowance')
            allowance();write_packet(sock,result)
            job=result=text=normal=None
    finally:sock.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fd',type=int,required=True);main(p.parse_args().fd)

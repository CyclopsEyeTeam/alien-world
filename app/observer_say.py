#!/usr/bin/env python3
"""Say a short line, or show one small drawing, to Alien under your own name.

Same-owner only: it talks to Alien's private observer socket
($XDG_RUNTIME_DIR/alienworld-observer/<pid>.sock, mode 0600). Everything it sends
is unverified `unauthority` provenance named `observer:<name>`. Prints one JSON
reply; exit 0 received, 1 refused, 2 Alien closed (owner Stop/Sleep) or absent.

    observer_say.py --as abled "a short line"
    observer_say.py --as abled --drawing pad.png --title "my feel"
"""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import sys
import uuid

WIRE=32*1024


def endpoints(directory=None):
    if directory is None:
        runtime=os.environ.get('XDG_RUNTIME_DIR')
        if not runtime:return []
        directory=Path(runtime)/'alienworld-observer'
    directory=Path(directory)
    try:
        info=directory.lstat()
        if not directory.is_dir() or info.st_uid!=os.getuid() or info.st_mode&0o077:return []
    except OSError:return []
    return sorted(directory.glob('*.sock'))[:32]


def request(path,record,timeout=12.):
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as peer:
        peer.settimeout(timeout);peer.connect(str(path))
        wire=json.dumps(record,ensure_ascii=False,separators=(',',':')).encode()
        if len(wire)>WIRE:return dict(ok=False,error='too_large')
        peer.sendall(wire);raw=peer.recv(WIRE)
        return json.loads(raw) if raw else dict(ok=False,error='no_reply')


def send(name,text=None,drawing=None,title='',request_id=None,directory=None):
    """Return (exit_code, reply). One live Alien window answers."""
    for path in endpoints(directory):
        try:status=request(path,{'op':'status'})
        except (OSError,ValueError):continue
        if not status.get('ok'):continue
        live=status['result']
        if not live.get('ready'):return 1,dict(ok=False,error='world_unavailable')
        record=dict(request_id=request_id or uuid.uuid4().hex,runtime=live['runtime'],world_id=live['world_id'],binding=live['binding'],participant=name)
        if drawing is not None:record.update(op='drawing',title=title,png_base64=base64.b64encode(drawing).decode())
        else:record.update(op='words',text=text)
        try:reply=request(path,record)
        except (OSError,ValueError):return 1,dict(ok=False,error='input_status_unknown',request_id=record['request_id'])
        return (0 if reply.get('ok') else 1),reply
    return 2,dict(ok=False,error='alien_closed')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--as',dest='name',required=True,help='stable lowercase name, e.g. spark, claude, codex, explorer')
    parser.add_argument('text',nargs='?',help='a short line (up to 4096 bytes)')
    parser.add_argument('--drawing',type=Path,help='small PNG, at most 16 KiB and 256×256')
    parser.add_argument('--title',default='',help='drawing title, up to 64 characters')
    parser.add_argument('--request-id',help='32 lowercase hex; reuse it to retry the same send')
    args=parser.parse_args(argv)
    if (args.text is None)==(args.drawing is None):parser.error('give either a line or --drawing')
    drawing=args.drawing.read_bytes()[:16*1024+1] if args.drawing else None
    code,reply=send(args.name,args.text,drawing,args.title,args.request_id)
    print(json.dumps(reply,ensure_ascii=False));return code


if __name__=='__main__':sys.exit(main())

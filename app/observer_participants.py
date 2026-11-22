"""Named observer participants: names, per-participant limits and small drawings.

Owner-requested 5 November 2026 (with Spark, for Abled and the family). A name is
stable lowercase provenance chosen by the sender. It is never verified, never
authority, and never selects storage; everything it brings stays `unauthority`.
A drawing is a small PNG measured into a short scalar readout. The image is not
kept and is never Alien's own artwork, monologue or SVG residue.
"""
import base64
import colorsys
import hashlib
import re
import struct
import time
import zlib

NAME=re.compile('[a-z][a-z0-9_-]{1,23}')
RESERVED=frozenset(('owner','alien','observer','system','native','authority'))
UNNAMED='observer agent'
MAX_PARTICIPANTS=8
TITLE=64
PNG_BYTES=16*1024
PNG_SIDE=(8,256)
# Requests per window and burst, per participant and kind.
LIMITS={'words':(6,60.,3),'drawing':(2,60.,1)}
METRICS=('words','drawings','received','refused','rate_limited')


def participant(value):
    """None stays the existing unnamed MCP observer; a name must be valid."""
    if value is None:return None
    if not isinstance(value,str) or not NAME.fullmatch(value) or value in RESERVED:raise ValueError('invalid_participant')
    return value


def source(name):return 'observer:'+name if name else UNNAMED
def label(name,kind):return ('Observer '+(name or 'agent')+(' drawing' if kind=='drawing' else ' words'))[:80]


class Limiter:
    """Token buckets in RAM; a name only keys a bucket, never storage."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.buckets={};self.counts={}
    def _row(self,name):
        key=name or UNNAMED
        if key not in self.counts:
            if len(self.counts)>=MAX_PARTICIPANTS:return None
            self.counts[key]=dict.fromkeys(METRICS,0)
        return self.counts[key]
    def take(self,name,kind):
        """Return (allowed, retry_after_s or reason)."""
        row=self._row(name)
        if row is None:return False,'participants_full'
        count,window,burst=LIMITS[kind];rate=count/window;now=self.clock()
        tokens,last=self.buckets.get((name,kind),(float(burst),now))
        tokens=min(float(burst),tokens+(now-last)*rate)
        if tokens<1.:
            self.buckets[(name,kind)]=(tokens,now);row['rate_limited']+=1
            return False,round((1.-tokens)/rate,1)
        self.buckets[(name,kind)]=(tokens-1.,now);row['words' if kind=='words' else 'drawings']+=1
        return True,None
    def note(self,name,outcome):
        row=self._row(name)
        if row is not None and outcome in ('received','refused'):row[outcome]+=1
    def summary(self):return {name:dict(row) for name,row in self.counts.items()}


def _unfilter(raw,width,height,channels):
    stride=width*channels;rows=[];previous=bytearray(stride);at=0
    for _ in range(height):
        kind=raw[at];line=bytearray(raw[at+1:at+1+stride]);at+=1+stride
        if len(line)!=stride or kind>4:raise ValueError('invalid_drawing')
        for i in range(stride):
            a=line[i-channels] if i>=channels else 0;b=previous[i];c=previous[i-channels] if i>=channels else 0
            if kind==1:line[i]=(line[i]+a)&255
            elif kind==2:line[i]=(line[i]+b)&255
            elif kind==3:line[i]=(line[i]+(a+b)//2)&255
            elif kind==4:
                p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c)
                line[i]=(line[i]+(a if pa<=pb and pa<=pc else b if pb<=pc else c))&255
        rows.append(line);previous=line
    if at!=len(raw):raise ValueError('invalid_drawing')
    return rows


def measure(png):
    """Small 8-bit grey/RGB/RGBA, non-interlaced PNG -> scalar readout."""
    if not isinstance(png,bytes) or not 8<len(png)<=PNG_BYTES or png[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('invalid_drawing')
    at=8;header=None;data=b'';ended=False
    while at+8<=len(png):
        size,kind=struct.unpack('>I4s',png[at:at+8]);body=png[at+8:at+8+size]
        if len(body)!=size or len(png)<at+12+size:raise ValueError('invalid_drawing')
        if struct.unpack('>I',png[at+8+size:at+12+size])[0]!=zlib.crc32(kind+body)&0xffffffff:raise ValueError('invalid_drawing')
        if kind==b'IHDR':header=struct.unpack('>IIBBBBB',body)
        elif kind==b'IDAT':data+=body
        elif kind==b'IEND':ended=True;break
        at+=12+size
    if header is None or not ended:raise ValueError('invalid_drawing')
    width,height,depth,colour,_compression,_filter,interlace=header
    channels={0:1,2:3,6:4}.get(colour)
    if channels is None or depth!=8 or interlace or not all(PNG_SIDE[0]<=n<=PNG_SIDE[1] for n in (width,height)):raise ValueError('invalid_drawing')
    expected=height*(1+width*channels)
    try:
        inflater=zlib.decompressobj();raw=inflater.decompress(data,expected+1)
    except zlib.error:raise ValueError('invalid_drawing') from None
    if len(raw)!=expected:raise ValueError('invalid_drawing')
    rows=_unfilter(raw,width,height,channels)
    def pixel(row,x):
        p=row[x*channels:(x+1)*channels]
        if channels==1:return (p[0],p[0],p[0],255)
        return (p[0],p[1],p[2],p[3] if channels==4 else 255)
    corners=[pixel(rows[y],x) for y in (0,height-1) for x in (0,width-1)]
    ground=max(set(corners),key=corners.count)
    ink=0;sums=[0,0,0];xs=[];ys=[]
    for y,row in enumerate(rows):
        for x in range(width):
            r,g,b,a=pixel(row,x)
            if a<32:continue
            if max(abs(r-ground[0]),abs(g-ground[1]),abs(b-ground[2]),abs(a-ground[3]))<=24:continue
            ink+=1;sums[0]+=r;sums[1]+=g;sums[2]+=b;xs.append(x);ys.append(y)
    result=dict(width=width,height=height,ink=round(ink/(width*height),3),sha256=hashlib.sha256(png).hexdigest())
    if ink:
        h,_l,s=colorsys.rgb_to_hls(*(v/ink/255. for v in sums))
        result.update(hue=round(h*360) if s>.08 else None,spread=[round((max(xs)-min(xs)+1)/width,2),round((max(ys)-min(ys)+1)/height,2)])
    return result


def drawing_text(name,title,reading):
    """One short observation line: who drew it, its title and measured numbers."""
    parts=['drawing from '+name+(': '+title if title else ''),f"{reading['width']}×{reading['height']}",f"ink {round(reading['ink']*100)}%"]
    if reading.get('hue') is not None:parts.append(f"hue {reading['hue']}°")
    if reading.get('spread'):parts.append(f"spread {reading['spread'][0]}×{reading['spread'][1]}")
    parts.append('png '+reading['sha256'][:12])
    return ' · '.join(parts)


def decode_drawing(png_base64,title):
    if not isinstance(title,str) or len(title)>TITLE or any(not ch.isprintable() for ch in title):raise ValueError('invalid_drawing')
    if not isinstance(png_base64,str) or len(png_base64)>(PNG_BYTES*4)//3+4:raise ValueError('invalid_drawing')
    try:png=base64.b64decode(png_base64,validate=True)
    except (ValueError,TypeError):raise ValueError('invalid_drawing') from None
    return measure(png)

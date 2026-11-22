"""Bounded local character/RGB frames. No commands, paths or identity authority."""
from dataclasses import dataclass,field
import math,socket,struct
from reference import Frame
from collections.abc import Sequence
MAX_PACKET=512*1024
MAX_COLS,MAX_ROWS=512,128
HEADER=struct.Struct('!4sQdHH3BddQQ')
CELL=struct.Struct('!IBBB')
class PacketError(ValueError):pass
try:
    from _fast_cells import encode_cells as _encode_cells
except ImportError:
    _encode_cells=None
class Emitter:
    """Sequence outlives any renderer agent replacement inside this worker."""
    def __init__(self):self.sequence=0
    def packet(self,frame,**fields):
        self.sequence+=1
        return encode(frame,sequence=self.sequence,**fields)
_WIRE_ORIGIN=object()
@dataclass(frozen=True)
class Message:
    frame:Frame
    sequence:int
    timestamp:float
    entropy:float
    colour:float
    tick:int
    generation:int
    _wire:bytes=field(default=b'',init=False,repr=False,compare=False)
    _wire_origin:object=field(default=None,init=False,repr=False,compare=False)

_PACKED_ORIGIN=object()
@dataclass(frozen=True,slots=True)
class PackedRow(Sequence):
    data:bytes
    offset:int
    cols:int
    def __len__(self):return self.cols
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i] for i in range(*index.indices(self.cols)))
        if index<0:index+=self.cols
        if not 0<=index<self.cols:raise IndexError(index)
        code,r,g,b=CELL.unpack_from(self.data,self.offset+index*CELL.size);return chr(code),(r,g,b)
    def __iter__(self):
        for code,r,g,b in CELL.iter_unpack(memoryview(self.data)[self.offset:self.offset+self.cols*CELL.size]):yield chr(code),(r,g,b)
    def __hash__(self):return hash(tuple(self))
    def __eq__(self,other):
        try:return len(self)==len(other) and all(a==b for a,b in zip(self,other))
        except TypeError:return False
@dataclass(frozen=True,slots=True)
class PackedRows(Sequence):
    data:bytes
    cols:int
    rows:int
    codes:frozenset
    _origin:object=field(default=None,init=False,repr=False,compare=False)
    def __len__(self):return self.rows
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i] for i in range(*index.indices(self.rows)))
        if index<0:index+=self.rows
        if not 0<=index<self.rows:raise IndexError(index)
        return PackedRow(self.data,HEADER.size+index*self.cols*CELL.size,self.cols)
    def __hash__(self):return hash(tuple(self))
    def __eq__(self,other):
        try:return len(self)==len(other) and all(a==b for a,b in zip(self,other))
        except TypeError:return False
    def records(self):return CELL.iter_unpack(memoryview(self.data)[HEADER.size:])
def packed_rows(frame):
    cells=frame.cells
    return cells if isinstance(cells,PackedRows) and cells._origin is _PACKED_ORIGIN else None

def source_packet(message):
    """Reuse only immutable bytes retained by this decoder, outside authority.

    The frozen message and its byte origin travel together. Hand-built messages
    still take the ordinary validating encoder path; no caller-supplied bytes
    bypass that validation. Retention is bounded by the frame channel's owners.
    """
    if message._wire_origin is _WIRE_ORIGIN:return message._wire
    return encode(message.frame,sequence=message.sequence,timestamp=message.timestamp,entropy=message.entropy,colour=message.colour,tick=message.tick,generation=message.generation)

def _geometry(cols,rows):
    if type(cols) is not int or type(rows) is not int or not (20<=cols<=MAX_COLS and 8<=rows<=MAX_ROWS):raise PacketError('unsupported grid geometry')
def _number(x,maximum):
    if type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=maximum:raise PacketError('invalid numeric frame field')
def _integer(x,minimum=0):
    if type(x) is not int or not minimum<=x<2**64:raise PacketError('invalid integer frame field')
def _rgb(value):
    if len(value)!=3 or any(type(x) is not int or not 0<=x<=255 for x in value):raise PacketError('invalid RGB value')
def encode(frame,*,sequence,timestamp,entropy,colour,tick,generation):
    rows=len(frame.cells);cols=len(frame.cells[0]) if rows else 0;_geometry(cols,rows)
    _integer(sequence,1);_integer(tick);_integer(generation);_number(timestamp,1e12);_number(entropy,1);_number(colour,1.5);_rgb(frame.void)
    data=bytearray(HEADER.pack(b'AFL1',sequence,timestamp,cols,rows,*frame.void,entropy,colour,tick,generation))
    if _encode_cells is not None:
        _encode_cells(data,frame.cells,cols,PacketError)
    else:
        pack=CELL.pack;extend=data.extend
        for row in frame.cells:
            if len(row)!=cols:raise PacketError('ragged grid')
            for char,rgb in row:
                if not isinstance(char,str) or len(char)!=1 or 0xD800<=ord(char)<=0xDFFF:raise PacketError('invalid character')
                if len(rgb)!=3 or type(rgb[0]) is not int or not 0<=rgb[0]<=255 or type(rgb[1]) is not int or not 0<=rgb[1]<=255 or type(rgb[2]) is not int or not 0<=rgb[2]<=255:raise PacketError('invalid RGB value')
                extend(pack(ord(char),rgb[0],rgb[1],rgb[2]))
    if len(data)>MAX_PACKET:raise PacketError('oversized frame')
    return bytes(data)
def decode(data,last_sequence=None,*,packed=False):
    if type(data) not in (bytes,bytearray,memoryview):raise PacketError('invalid packet type')
    if not HEADER.size<=(data.nbytes if type(data) is memoryview else len(data))<=MAX_PACKET:raise PacketError('invalid packet length')
    data=bytes(data)
    if not HEADER.size<=len(data)<=MAX_PACKET:raise PacketError('invalid packet length')
    magic,seq,stamp,cols,rows,r,g,b,entropy,colour,tick,generation=HEADER.unpack_from(data)
    if magic!=b'AFL1':raise PacketError('wrong frame format')
    _geometry(cols,rows);_integer(seq,1);_number(stamp,1e12);_number(entropy,1);_number(colour,1.5)
    if last_sequence is not None and seq<=last_sequence:raise PacketError('stale frame sequence')
    if len(data)!=HEADER.size+cols*rows*CELL.size:raise PacketError('invalid packet length')
    if packed:
        codes=set()
        for code,red,green,blue in CELL.iter_unpack(memoryview(data)[HEADER.size:]):
            if code>0x10FFFF or 0xD800<=code<=0xDFFF:raise PacketError('invalid character')
            codes.add(code)
        cells=PackedRows(data,cols,rows,frozenset(codes));object.__setattr__(cells,'_origin',_PACKED_ORIGIN)
        message=Message(Frame(cells,(r,g,b)),seq,stamp,entropy,colour,tick,generation)
    else:
        cells=[];offset=HEADER.size
        for y in range(rows):
            row=[]
            for x in range(cols):
                code,red,green,blue=CELL.unpack_from(data,offset);offset+=CELL.size
                if code>0x10FFFF or 0xD800<=code<=0xDFFF:raise PacketError('invalid character')
                row.append((chr(code),(red,green,blue)))
            cells.append(tuple(row))
        message=Message(Frame(tuple(cells),(r,g,b)),seq,stamp,entropy,colour,tick,generation)
    object.__setattr__(message,'_wire',data);object.__setattr__(message,'_wire_origin',_WIRE_ORIGIN)
    return message
def send_frame(sock,data):
    if len(data)>MAX_PACKET:raise PacketError('oversized frame')
    try:
        if sock.send(data)!=len(data):raise PacketError('incomplete local frame write')
        return True
    except BlockingIOError:return False

def receive_latest(sock,last_sequence=None,*,packed=False):
    latest=None
    for _ in range(32):
        try:data,ancillary,flags,address=sock.recvmsg(MAX_PACKET)
        except BlockingIOError:return latest
        if not data:
            if latest:return latest
            raise EOFError('field worker stopped')
        if flags&socket.MSG_TRUNC:raise PacketError('truncated local frame')
        latest=decode(data,last_sequence,packed=packed);last_sequence=latest.sequence
    return latest

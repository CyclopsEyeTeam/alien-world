"""Bounded character-to-atlas mapping; preserves each cell's foreground RGB."""
class GlyphMap:
    def __init__(self):self.chars=['?'];self.indices={'?':0};self.version=0
    def ensure(self,chars):
        needed=set(chars)|{'?'}
        combined=set(self.chars)|needed
        if len(combined)<=256:new=self.chars+sorted(combined-set(self.chars))
        else:new=['?']+sorted(needed-{'?'})[:255]
        if new!=self.chars:self.chars=new;self.indices={c:i for i,c in enumerate(new)};self.version+=1

def texture_bytes(frame,mapping):
    mapping.ensure(char for row in frame.cells for char,rgb in row)
    data=bytearray();missing=0
    for row in frame.cells:
        for char,rgb in row:
            index=mapping.indices.get(char)
            if index is None:index=0;missing+=1
            data.extend((*rgb,index))
    return bytes(data),missing


class TextureWorkspace:
    """Renderer-owned synchronous staging. Messages never borrow this array."""
    def __init__(self):self.data=bytearray();self.shape=None;self.allocations=0;self.reuses=0;self.packed_frames=0;self.legacy_frames=0
    def prepare(self,cols,rows):
        shape=(cols,rows)
        if shape!=self.shape:self.data=bytearray(cols*rows*4);self.shape=shape;self.allocations+=1
        else:self.reuses+=1
        return self.data
    def summary(self):return dict(allocations=self.allocations,reuses=self.reuses,bytes=len(self.data),packed_frames=self.packed_frames,legacy_frames=self.legacy_frames)

def texture_buffer(frame,mapping,workspace):
    from protocol import packed_rows
    packed=packed_rows(frame);rows=len(frame.cells);cols=len(frame.cells[0]);data=workspace.prepare(cols,rows);missing=0;at=0
    if packed is not None:
        mapping.ensure(chr(code) for code in packed.codes);indices={ord(char):value for char,value in mapping.indices.items()};workspace.packed_frames+=1
        for code,r,g,b in packed.records():
            index=indices.get(code)
            if index is None:index=0;missing+=1
            data[at]=r;data[at+1]=g;data[at+2]=b;data[at+3]=index;at+=4
    else:
        mapping.ensure(char for row in frame.cells for char,rgb in row);workspace.legacy_frames+=1
        for row in frame.cells:
            for char,(r,g,b) in row:
                index=mapping.indices.get(char)
                if index is None:index=0;missing+=1
                data[at]=r;data[at+1]=g;data[at+2]=b;data[at+3]=index;at+=4
    return data,missing

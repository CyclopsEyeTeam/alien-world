"""Chroma's native GL foundation with a bounded character/RGB glyph display."""
import ctypes as C
import math
import io,os,sys,time
from dataclasses import dataclass
import cairo
import gi
gi.require_version('Pango','1.0')
gi.require_version('PangoCairo','1.0')
from gi.repository import Gio,Pango,PangoCairo
from vendor.chroma_gl import GL,VERTEX,Surface
from glyphs import GlyphMap,texture_bytes,TextureWorkspace,texture_buffer
from neural_surface import ExpressionLayer
from neural_types import validate_expression,validate_sensory
import background_pulse
import calm_field

MAX_CAPTURE_PIXELS=8*1024*1024
MAX_CAPTURE_PNG=8*1024*1024

def display_background(message):
    """What the window paints under the cells: the frame's own native void, lightly warmed by the pulse
    (background_pulse, owner-requested 10 November 2026). The native frame itself is never changed."""
    if message is None:return (.02,.02,.03)
    return background_pulse.pulse(tuple(v/255 for v in message.frame.void),message.tick)

class _PNGBuffer(io.BytesIO):
    def write(self,data):
        if self.tell()+len(data)>MAX_CAPTURE_PNG:raise ValueError('Eye image exceeds channel bound')
        return super().write(data)

def pixels_png(gl,width,height):
    """Read the currently drawn physical framebuffer, without changing its pixels.

    BGRA is Cairo's native little-endian ARGB32 storage. GL scanlines are
    bottom-up; only their order changes. No cell metadata is used to form pixels.
    """
    if type(width) is not int or type(height) is not int or width<1 or height<1 or width*height>MAX_CAPTURE_PIXELS:raise ValueError('Eye capture exceeds pixel bound')
    if sys.byteorder!='little':raise ValueError('unsupported framebuffer byte order')
    def integer(name):
        value=C.c_int();gl.GetIntegerv(name,C.byref(value));return value.value
    if integer(0x88ED):raise ValueError('pixel pack buffer is in use')
    if integer(0x80A9):raise ValueError('multisample readback unavailable')
    stores={key:integer(key) for key in (0x0D05,0x0D02,0x0D03,0x0D04,0x806B,0x806C)}
    read=integer(0x8CAA);draw=integer(0x8CA6);stride=width*4;size=stride*height
    raw=(C.c_ubyte*size)();top=bytearray(size);top_memory=(C.c_ubyte*size).from_buffer(top);image=None
    try:
        gl.BindFramebuffer(0x8CA8,draw)
        for key in stores:gl.PixelStorei(key,1 if key==0x0D05 else 0)
        gl.ReadPixels(0,0,width,height,0x80E1,0x1401,C.cast(raw,C.c_void_p))
        if hasattr(gl,'library'):
            error=gl.library.glGetError;error.restype=C.c_uint;error.argtypes=[]
            if error():raise ValueError('framebuffer readback unavailable')
        address=C.addressof(raw);destination=C.addressof(top_memory)
        for row in range(height):C.memmove(destination+row*stride,address+(height-row-1)*stride,stride)
        image=cairo.ImageSurface.create_for_data(top,cairo.FORMAT_ARGB32,width,height,stride);out=_PNGBuffer();image.write_to_png(out)
        return out.getvalue()
    finally:
        if image is not None:image.finish()
        C.memset(C.addressof(raw),0,size);C.memset(C.addressof(top_memory),0,size)
        for key,value in stores.items():gl.PixelStorei(key,value)
        gl.BindFramebuffer(0x8CA8,read)

def expression_probe_rectangles(record,width,height):
    """At most four16x16 probes. A missed expression withholds its receipt."""
    if record is None or width<1 or height<1:return []
    rectangles=[];pw=min(16,width);ph=min(16,height)
    for region in record['regions']:
        if region['strength']<=0:continue
        for index in range(8):
            angle=index*math.pi/4;u=region['x']+region['radius']*math.cos(angle);v=region['y']+region['radius']*math.sin(angle)
            if not (0<=u<=1 and 0<=v<=1):continue
            x=max(0,min(width-pw,min(width-1,int(u*width))-pw//2));top=max(0,min(height-ph,min(height-1,int(v*height))-ph//2))
            rectangle=(x,height-top-ph,pw,ph)
            if rectangle not in rectangles:rectangles.append(rectangle)
            break
    return rectangles

def read_probe_pixels(gl,rectangles):
    """Read at most4KiB from the actual bound framebuffer, restoring GL state."""
    if len(rectangles)>4 or any(w<1 or h<1 or w>16 or h>16 or x<0 or y<0 for x,y,w,h in rectangles):raise ValueError('invalid expression probe')
    def integer(name):
        value=C.c_int();gl.GetIntegerv(name,C.byref(value));return value.value
    if integer(0x88ED) or integer(0x80A9):raise ValueError('expression visibility readback unavailable')
    stores={key:integer(key) for key in (0x0D05,0x0D02,0x0D03,0x0D04,0x806B,0x806C)}
    read=integer(0x8CAA);draw=integer(0x8CA6);data=bytearray()
    try:
        gl.BindFramebuffer(0x8CA8,draw)
        for key in stores:gl.PixelStorei(key,1 if key==0x0D05 else 0)
        for x,y,w,h in rectangles:
            raw=(C.c_ubyte*(w*h*4))()
            try:
                gl.ReadPixels(x,y,w,h,0x80E1,0x1401,C.cast(raw,C.c_void_p))
                if hasattr(gl,'library'):
                    error=gl.library.glGetError;error.restype=C.c_uint;error.argtypes=[]
                    if error():raise ValueError('expression visibility readback failed')
                data.extend(raw)
            finally:C.memset(C.addressof(raw),0,len(raw))
        return data
    except Exception:
        data[:]=b'\0'*len(data);raise
    finally:
        for key,value in stores.items():gl.PixelStorei(key,value)
        gl.BindFramebuffer(0x8CA8,read)

def render_with_visibility(renderer,width,height,record):
    """Same frozen native frame before/after the expression; only a real diff proves it."""
    rectangles=expression_probe_rectangles(record,width,height)
    if not rectangles:renderer.render(width,height,record);return False
    before=None;after=None
    renderer.render(width,height,None)
    try:
        try:before=read_probe_pixels(renderer.gl,rectangles)
        except Exception:pass # Optional proof failure never stops the native field.
        # Always leave the requested final frame in the framebuffer. The
        # auxiliary native draw is never separately presented or captured.
        renderer.render(width,height,record)
        if before is None:return False
        try:after=read_probe_pixels(renderer.gl,rectangles)
        except Exception:return False
        return before!=after
    finally:
        for data in (before,after):
            if data is not None:data[:]=b'\0'*len(data)

@dataclass(frozen=True)
class TerminalFont:
    description:str
    dpi:float
    cell_width:int
    cell_height:int

def terminal_font(widget):
    name='DejaVu Sans Mono 10'
    source=Gio.SettingsSchemaSource.get_default()
    schema=source.lookup('org.cinnamon.desktop.interface',True) if source else None
    if schema and schema.has_key('monospace-font-name'):
        name=Gio.Settings.new_full(schema,None,None).get_string('monospace-font-name') or name
    description=Pango.FontDescription.from_string(name);context=widget.get_pango_context()
    dpi=PangoCairo.context_get_resolution(context)
    if dpi<=0:dpi=widget.get_screen().get_resolution()
    if dpi<=0:dpi=96
    metrics=context.get_metrics(description,context.get_language())
    layout=Pango.Layout.new(context);layout.set_font_description(description);layout.set_text('M',-1)
    width=max(1,layout.get_pixel_size()[0])
    height=max(1,math.ceil((metrics.get_ascent()+metrics.get_descent())/Pango.SCALE))
    return TerminalFont(description.to_string(),dpi,width,height)
FRAGMENT=b'''#version 150 core
in vec2 uv; out vec4 frag;
uniform sampler2D cells; uniform sampler2D atlas;
uniform vec4 geometry; uniform vec3 background;
uniform vec3 viewportPx;
uniform vec3 glassState;
uniform int squareCount;
uniform vec4 squareBox[18];
uniform vec4 squareCol[18];
uniform int neuralCount;
uniform vec4 neural0,neural1,neural2,neural3,neuralHues,neuralMarker;
vec4 neuralRegion(int i){if(i==0)return neural0;if(i==1)return neural1;if(i==2)return neural2;return neural3;}
vec3 neuralRGB(float h){vec3 p=abs(fract(vec3(h)+vec3(0.,2./3.,1./3.))*6.-3.);return .95*mix(vec3(1.),clamp(p-1.,0.,1.),.65);}
void main(){
 vec2 grid=geometry.xy;
 vec2 position=min(uv*grid,grid-vec2(0.0001));
 ivec2 cell=ivec2(floor(position));
 vec4 value=texelFetch(cells,cell,0);
 int glyph=int(floor(value.a*255.0+0.5));
 vec2 tile=vec2(glyph%16,glyph/16);
 vec2 within=fract(position);
 vec2 atlasUV=(tile+within)/16.0;
 float ink=texture(atlas,atlasUV).a;
 vec3 bg=background;
 float spiralCover=0.0;
 if(squareCount>0){
  vec2 fragPx=uv*viewportPx.xy;
  vec3 sqLight=vec3(0.0);
  const float fw=1.25;
  for(int i=0;i<18;i++){
   if(i>=squareCount)break;
   vec4 box=squareBox[i];
   vec4 col=squareCol[i];
   vec2 rel=fragPx-box.xy;
   float hs=box.z;
   float sw=box.w;
   float depth=clamp(4.0*hs/max(1.0,min(viewportPx.x,viewportPx.y)),0.0,1.0);
   if(abs(sw)<0.0005){
    vec2 d=abs(rel);
    float cheb=max(d.x,d.y);
    if(cheb<hs+fw){
     float edge=1.0-smoothstep(hs-fw,hs+fw,cheb);
     float rim=1.0+0.18*(1.0-smoothstep(0.0,max(2.5,hs*0.14),abs(cheb-hs*0.88)));
     float weight=col.a*edge*rim;
     if(glassState.z>0.5){
      float border=pow(max(0.0,1.0-abs(cheb-hs*0.94)/max(fw,hs*0.055)),2.0);
      float travel=pow(0.5+0.5*cos((rel.x+rel.y)/max(hs,1.0)*3.0-glassState.x*2.0+float(i)),8.0);
      weight=col.a*edge*((0.70+0.18*depth)+border*(1.8+depth+1.6*glassState.y*travel));
     }
     sqLight+=col.rgb*weight;
    }
   }else{
    float sdir=sw>=0.0?1.0:-1.0;
    float mag=abs(sw);
    bool inward=mag>2.0;
    float arms=inward?1.0:(mag>1.0?3.0:2.0);
    float p=clamp(inward?mag-2.0:(mag>1.0?mag-1.0:mag),0.0,1.0);
    float rad=length(rel);
    float soft=fw*(1.0+2.4*p);
    if(rad<hs*1.42+soft){
     float rot=inward?0.0:sdir*p*(1.8+2.4*p);
     float cs=cos(rot); float sn=sin(rot);
     vec2 rc=vec2(rel.x*cs+rel.y*sn,-rel.x*sn+rel.y*cs);
     float rcheb=max(abs(rc.x),abs(rc.y));
     float shapeD=mix(rcheb,rad,smoothstep(0.0,0.38,p));
     if(inward){
      float rounded=pow(pow(abs(rc.x),6.0)+pow(abs(rc.y),6.0),1.0/6.0);
      shapeD=mix(rcheb,rounded,smoothstep(0.0,0.38,p));
     }
     if(shapeD<hs+soft){
      float edge=1.0-smoothstep(hs-soft,hs+soft,shapeD);
      float rn=rad/max(hs,1.0);
      float ang=rad>0.0001?atan(rel.y,rel.x):0.0;
      float wind=5.2*log(1.0+rn*(2.4+2.2*p));
      float phase=arms*(sdir*ang)+wind-p*10.5;
      if(inward)phase=sdir*ang+22.619467*(shapeD/max(hs,1.0))+p*10.053096;
      float ribbon=inward?smoothstep(0.55,0.93,0.5+0.5*cos(phase)):smoothstep(0.24,0.86,0.5+0.5*cos(phase));
      float eyeInner=inward?smoothstep(0.008,0.055,rn):smoothstep(0.03*p,0.32*p,rn);
      float eye=mix(1.0,eyeInner,smoothstep(0.24,0.74,p));
      float carve=smoothstep(0.03,0.32,p);
      float sqRim=1.0+0.18*(1.0-smoothstep(0.0,max(2.5,hs*0.14),abs(rcheb-hs*0.88)));
      float rim=mix(sqRim,1.18,carve);
      float mask=mix(1.0,ribbon*eye,carve);
      vec3 armCol=mix(col.rgb,col.gbr,0.40*carve*clamp(rn,0.0,1.0));
      float weight=col.a*edge*rim*mask;
      if(glassState.z>0.5){
       float crest=pow(0.5+0.5*cos(phase),12.0);
       float travel=pow(0.5+0.5*cos(rn*10.0-glassState.x*2.0+ang),8.0);
       float filWidth=max(0.045,fw/max(hs,1.0)*2.4);
       float filament=1.0-smoothstep(filWidth*0.35,filWidth,abs(sin(phase*0.5+0.55)));
       float head=pow(max(0.0,cos(ang-glassState.x*0.7-float(i)*1.7)),8.0);
       float tail=smoothstep(0.12,0.3,rn)*(1.0-smoothstep(0.85,1.08,rn));
       weight=col.a*edge*eye*((0.72*mask+(2.6+1.8*depth)*crest*carve)*(0.84+0.16*depth)
          +1.6*glassState.y*travel*mask+0.85*carve*filament*head*tail);
      }
      sqLight+=armCol*weight;
      float large=smoothstep(0.055,0.14,hs/min(viewportPx.x,viewportPx.y));
      spiralCover=max(spiralCover,clamp(col.a*edge*mask*carve*large,0.0,1.0));
     }
    }
   }
  }
  if(glassState.z>0.5){
   float peak=max(sqLight.r,max(sqLight.g,sqLight.b));
   if(peak>0.0){
    float tone=min(max(0.0,0.66-max(bg.r,max(bg.g,bg.b))),0.70*peak/(0.38+peak));
    bg+=sqLight/peak*tone;
   }
  }else bg=clamp(bg+sqLight/(vec3(1.0)+sqLight*0.55),0.0,0.66);
 }
 vec3 native= mix(bg,value.rgb,ink);
 if(spiralCover>0.0 && ink>0.0)native=mix(bg,native,1.0-0.24*spiralCover);
 if(neuralCount>0 && ink==0.){
  for(int i=0;i<4;i++){
   if(i>=neuralCount)break;
   vec4 region=neuralRegion(i);vec2 delta=uv-region.xy;
   float d=length(delta);float angle=atan(delta.y,delta.x);
   float ring=1.-smoothstep(.0025,.006,abs(d-region.z));
   float dash=.55+.45*step(0.,sin(angle*(5.+mod(neuralMarker.x,4.))+(neuralMarker.z+neuralMarker.w)*6.283185));
   float amount=ring*dash*region.w*(.12+.06*neuralMarker.y);
   native=mix(native,neuralRGB(neuralHues[i]),amount);
  }
 }
 frag=vec4(native,1.0);
}'''
class GlyphRenderer:
    def __init__(self,gl,font,scale=1,profile=None):
        self.font=font;self.scale=scale;self.workspace=TextureWorkspace();self.profile=profile
        self.gl=gl;self.program=0;self.vao=C.c_uint();self.textures=(C.c_uint*2)();self.mapping=GlyphMap()
        self.atlas_version=-1;self.message=None;self.missing=0;self._t0=None;self._chroma=calm_field.ReactiveChroma()
        shaders=[]
        try:
            for kind,data in ((0x8B31,VERTEX),(0x8B30,FRAGMENT)):
                shader=gl.CreateShader(kind);shaders.append(shader);ptr=C.c_char_p(data)
                gl.ShaderSource(shader,1,C.byref(ptr),None);gl.CompileShader(shader);ok=C.c_int();gl.GetShaderiv(shader,0x8B81,C.byref(ok))
                if not ok.value:raise RuntimeError('Glyph shader compilation failed')
            self.program=gl.CreateProgram()
            for shader in shaders:gl.AttachShader(self.program,shader)
            gl.LinkProgram(self.program);ok=C.c_int();gl.GetProgramiv(self.program,0x8B82,C.byref(ok))
            if not ok.value:raise RuntimeError('Glyph shader link failed')
            self.uniforms={name:gl.GetUniformLocation(self.program,name.encode()) for name in ('cells','atlas','geometry','background','viewportPx','glassState','squareCount','neuralCount','neural0','neural1','neural2','neural3','neuralHues','neuralMarker')}
            self.sq_box_locs=tuple(gl.GetUniformLocation(self.program,f'squareBox[{i}]'.encode()) for i in range(18))
            self.sq_col_locs=tuple(gl.GetUniformLocation(self.program,f'squareCol[{i}]'.encode()) for i in range(18))
            gl.GenVertexArrays(1,C.byref(self.vao));gl.GenTextures(2,self.textures)
            for i,texture in enumerate(self.textures):
                gl.BindTexture(0x0DE1,texture)
                for key,val in ((0x2801,0x2600 if i==0 else 0x2601),(0x2800,0x2600 if i==0 else 0x2601),(0x2802,0x812F),(0x2803,0x812F)):gl.TexParameteri(0x0DE1,key,val)
        except Exception:self.close();raise
        finally:
            for shader in shaders:gl.DeleteShader(shader)
    def close(self):
        gl=self.gl;gl.DeleteTextures(2,self.textures)
        if self.vao.value:gl.DeleteVertexArrays(1,C.byref(self.vao));self.vao.value=0
        if self.program:gl.DeleteProgram(self.program);self.program=0
    def atlas(self):
        width=self.font.cell_width;height=self.font.cell_height
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width*16*self.scale,height*16*self.scale);ctx=cairo.Context(surface)
        ctx.scale(self.scale,self.scale);ctx.set_source_rgba(1,1,1,1)
        layout=PangoCairo.create_layout(ctx);PangoCairo.context_set_resolution(layout.get_context(),self.font.dpi)
        layout.set_font_description(Pango.FontDescription.from_string(self.font.description))
        for i,char in enumerate(self.mapping.chars):
            x=i%16*width;y=i//16*height
            ctx.save();ctx.rectangle(x,y,width,height);ctx.clip();ctx.move_to(x,y);layout.set_text(char,-1);PangoCairo.show_layout(ctx,layout);ctx.restore()
        surface.flush();return bytes(surface.get_data())
    def upload(self,message):
        gl=self.gl
        if self.profile is not None:raw,self.missing=self.profile.call('texture',texture_buffer,message.frame,self.mapping,self.workspace)
        else:raw,self.missing=texture_buffer(message.frame,self.mapping,self.workspace)
        cols=len(message.frame.cells[0]);rows=len(message.frame.cells)
        gl.PixelStorei(0x0CF5,1);gl.ActiveTexture(0x84C0);gl.BindTexture(0x0DE1,self.textures[0])
        buf=(C.c_ubyte*len(raw)).from_buffer(raw);gl.TexImage2D(0x0DE1,0,0x8058,cols,rows,0,0x1908,0x1401,C.cast(buf,C.c_void_p))
        if self.mapping.version!=self.atlas_version:
            data=self.atlas();buf=C.create_string_buffer(data)
            gl.ActiveTexture(0x84C1);gl.BindTexture(0x0DE1,self.textures[1])
            gl.TexImage2D(0x0DE1,0,0x8058,self.font.cell_width*16*self.scale,self.font.cell_height*16*self.scale,0,0x80E1,0x1401,C.cast(buf,C.c_void_p));self.atlas_version=self.mapping.version
        self.message=message;self._chroma.observe(message)
    def render(self,width,height,expression=None):
        gl=self.gl
        for state in (0x0BE2,0x0B71,0x0B90,0x0C11,0x0BD0,0x8DB9,0x0B44):gl.Disable(state)
        background=display_background(self.message)
        gl.Viewport(0,0,width,height);gl.ClearColor(*background,1);gl.Clear(0x4000)
        if self.message is None:return
        cols=len(self.message.frame.cells[0]);rows=len(self.message.frame.cells)
        gl.UseProgram(self.program);gl.BindVertexArray(self.vao.value)
        gl.Uniform1i(self.uniforms['cells'],0);gl.Uniform1i(self.uniforms['atlas'],1)
        gl.Uniform4f(self.uniforms['geometry'],cols,rows,self.font.cell_width,self.font.cell_height);gl.Uniform3f(self.uniforms['background'],*background)
        ts=getattr(self.message,'timestamp',None)
        if self._t0 is None and isinstance(ts,(int,float)) and math.isfinite(ts):self._t0=float(ts)
        reactive=self._chroma.observe(self.message)
        squares=calm_field.underlight_squares(self.message,width,height,self._t0,reactive)
        glass_on=calm_field.ENABLED and calm_field.ELECTRIC_GLASS_ENABLED
        glass_time=max(0.0,float(ts)-self._t0) if self._t0 is not None and isinstance(ts,(int,float)) and math.isfinite(ts) else float(self.message.tick)*0.14
        gl.Uniform3f(self.uniforms['glassState'],glass_time,reactive[1],float(glass_on))
        gl.Uniform3f(self.uniforms['viewportPx'],float(width),float(height),0.0)
        gl.Uniform1i(self.uniforms['squareCount'],len(squares))
        for idx,(cx,cy,hs,fw,sr,sg,sb,sa) in enumerate(squares):
            gl.Uniform4f(self.sq_box_locs[idx],cx,cy,hs,fw)
            gl.Uniform4f(self.sq_col_locs[idx],sr,sg,sb,sa)
        regions=expression['regions'] if expression is not None else []
        gl.Uniform1i(self.uniforms['neuralCount'],len(regions))
        hues=[0.]*4
        for index in range(4):
            region=regions[index] if index<len(regions) else dict(x=0.,y=0.,radius=0.,strength=0.,hue=0.)
            gl.Uniform4f(self.uniforms['neural'+str(index)],region['x'],region['y'],region['radius'],region['strength']);hues[index]=region['hue']
        gl.Uniform4f(self.uniforms['neuralHues'],*hues)
        marker=expression['marker'] if expression is not None else dict(tick_echo=0,chain_residue=0.,continuity='',grounding='')
        gl.Uniform4f(self.uniforms['neuralMarker'],marker['tick_echo']%256,marker['chain_residue'],(int(marker['continuity'] or '0',16)%1024)/1024,(int(marker['grounding'] or '0',16)%1024)/1024)
        gl.ActiveTexture(0x84C0);gl.BindTexture(0x0DE1,self.textures[0]);gl.ActiveTexture(0x84C1);gl.BindTexture(0x0DE1,self.textures[1])
        gl.DrawArrays(0x0004,0,3)

class FieldSurface(Surface):
    def __init__(self,owner):
        from types import SimpleNamespace
        self.owner=owner;self.pending=None;self.drawn_sequence=0;self.font=None;self.neural=None;self.native_tick=None;self.neural_context=validate_sensory(None,'own_display')
        super().__init__(SimpleNamespace(base=0,baker=None),{},owner.gpu_failed)
        self.connect('render',lambda *_:self.render_field())
    def create_context(self,_area):
        context=self.get_window().create_gl_context();context.set_use_es(False);context.set_required_version(3,2);context.realize();return context
    def initialize(self,_area):
        try:
            self.make_current()
            if self.get_error():raise RuntimeError('GL context unavailable')
            gl=GL();self.renderer_name=gl.GetString(0x1F01).decode()
            if os.environ.get('ALIEN_REQUIRE_HARDWARE_GL','').strip() in ('1','true','yes'):
                if any(x in self.renderer_name.lower() for x in ('llvmpipe','softpipe','software')):raise RuntimeError('Hardware GL is unavailable')
            self.font=terminal_font(self);self.gpu=GlyphRenderer(gl,self.font,self.get_scale_factor(),getattr(self.owner,'profile',None));self.owner.renderer=self.renderer_name
        except Exception as error:self.fail(error)
    def present(self,message):self.pending=message;self.queue_render()
    def expression(self,record):
        value=validate_expression(record);world=getattr(self.owner,'world',None)
        if not world or value['runtime']!=world['runtime'] or value['world_id']!=world['clock']['world_id'] or value['stamp']['segment_id']!=world['clock']['segment_id']:return False
        if self.neural is None:self.neural=ExpressionLayer(value['runtime'],value['world_id'])
        accepted=self.neural.offer(value)
        if accepted:self.queue_render()
        return accepted
    def clear_expression(self):
        if self.neural is not None:self.neural.current=None
        self.queue_render()
    def render_field(self):
        if self.failed or not self.gpu:return True
        try:
            diagnostic_started=time.perf_counter();diagnostic_uploaded=0.
            if self.pending:
                self.gpu.upload(self.pending);self.pending=None
                diagnostic_uploaded=(time.perf_counter()-diagnostic_started)*1000
            message=self.gpu.message;tick=message.tick if message else 0
            if self.neural is not None and ((self.native_tick is not None and tick<self.native_tick) or (self.neural.current is not None and getattr(self.owner,'world',None) and self.neural.current['stamp']['segment_id']!=self.owner.world['clock']['segment_id'])):self.neural.current=None
            self.native_tick=tick
            value=self.neural.at(tick) if self.neural is not None else None
            scale=self.get_scale_factor();width=self.get_allocated_width()*scale;height=self.get_allocated_height()*scale
            if value is not None and getattr(self,'visibility_attempted',None)!=value['output_id']:
                self.visibility_attempted=value['output_id'];self.visibility_proved=value['output_id'] if render_with_visibility(self.gpu,width,height,value) else None
            else:self.gpu.render(width,height,value)
            self.drawn_sequence=self.gpu.message.sequence if self.gpu.message else 0
            if self.neural is not None:
                receipt=self.neural.receipt('field',tick,self.drawn_sequence,visible=message is not None and value is not None and getattr(self,'visibility_proved',None)==value['output_id'])
                if receipt is not None:self.owner.neural_presented(receipt)
                # An unproved expression may still affect an unprobed pixel.
                # Preserve that conservative capture ancestry independently
                # from the stricter, actually-visible presentation receipt.
                ids=[value['output_id']] if value is not None and any(r['strength']>0 for r in value['regions']) else []
                self.neural_context=validate_sensory(dict(version=1,expression_ids=ids,source_scope='self',measurement='sampled_geometry_colour_change'),'own_display')
            self.owner.neural_context=self.neural_context
            diagnostic=getattr(self.owner,'diagnostic_draw',None)
            if callable(diagnostic):diagnostic(self.drawn_sequence,diagnostic_uploaded,max(0.,(time.perf_counter()-diagnostic_started)*1000-diagnostic_uploaded))
        except Exception as error:self.fail(error)
        if not self.failed and self.gpu.message is not None:self.capture_eye()
        return True
    def capture_eye(self):
        """Optional consumer readback, after a genuine render and before GTK presents."""
        due=getattr(self.owner,'eye_capture_due',None);receive=getattr(self.owner,'eye_frame',None)
        if not callable(due) or not callable(receive):return
        try:
            if not due():return
            scale=self.get_scale_factor();width=self.get_allocated_width()*scale;height=self.get_allocated_height()*scale
            captured=time.monotonic_ns();image=pixels_png(self.gpu.gl,width,height);message=self.gpu.message
            receive(image,dict(sequence=message.sequence,tick=message.tick,generation=message.generation,width=width,height=height,captured_ns=captured,neural_context=self.neural_context))
        except Exception:
            failed=getattr(self.owner,'eye_capture_failed',None)
            if callable(failed):
                try:failed('Eye framebuffer capture unavailable')
                except Exception:pass

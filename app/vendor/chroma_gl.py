"""GTK's existing GL context, with typed system-libGL calls; no extra packages."""
import ctypes as C
import os
from pathlib import Path
import time
import cairo
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib

VERTEX = b'''#version 150 core
out vec2 uv;
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);
uv=vec2(p.x,1.0-p.y);gl_Position=vec4(p*2.0-1.0,0,1);}'''

class GL:
    def __init__(self):
        lib=C.CDLL('libGL.so.1')
        U,I,F,P=C.c_uint,C.c_int,C.c_float,C.c_void_p
        definitions={
            'GetString':(C.c_char_p,[U]), 'GetIntegerv':(None,[U,C.POINTER(I)]),
            'Disable':(None,[U]), 'ClearColor':(None,[F,F,F,F]),'Clear':(None,[U]),
            'Viewport':(None,[I,I,I,I]), 'Finish':(None,[]),
            'CreateShader':(U,[U]),'ShaderSource':(None,[U,I,C.POINTER(C.c_char_p),P]),
            'CompileShader':(None,[U]),'GetShaderiv':(None,[U,U,C.POINTER(I)]),
            'GetShaderInfoLog':(None,[U,I,P,P]),'DeleteShader':(None,[U]),
            'CreateProgram':(U,[]),'AttachShader':(None,[U,U]),'LinkProgram':(None,[U]),
            'GetProgramiv':(None,[U,U,C.POINTER(I)]),'GetProgramInfoLog':(None,[U,I,P,P]),
            'DeleteProgram':(None,[U]),'UseProgram':(None,[U]),
            'GetUniformLocation':(I,[U,C.c_char_p]),'Uniform1i':(None,[I,I]),
            'Uniform1f':(None,[I,F]),'Uniform3f':(None,[I,F,F,F]),'Uniform4f':(None,[I,F,F,F,F]),
            'GenVertexArrays':(None,[I,C.POINTER(U)]),'BindVertexArray':(None,[U]),
            'DeleteVertexArrays':(None,[I,C.POINTER(U)]),'DrawArrays':(None,[U,I,I]),
            'GenTextures':(None,[I,C.POINTER(U)]),'DeleteTextures':(None,[I,C.POINTER(U)]),
            'BindTexture':(None,[U,U]),'ActiveTexture':(None,[U]),
            'TexParameteri':(None,[U,U,I]),'PixelStorei':(None,[U,I]),
            'TexImage2D':(None,[U,I,I,I,I,I,U,U,P]),
            'CopyTexSubImage2D':(None,[U,I,I,I,I,I,I,I]),
            'GenFramebuffers':(None,[I,C.POINTER(U)]),'DeleteFramebuffers':(None,[I,C.POINTER(U)]),
            'BindFramebuffer':(None,[U,U]),'FramebufferTexture2D':(None,[U,U,U,U,I]),
            'CheckFramebufferStatus':(U,[U]),'ReadPixels':(None,[I,I,I,I,U,U,P])}
        for name,(restype,args) in definitions.items():
            fn=getattr(lib,'gl'+name);fn.restype=restype;fn.argtypes=args;setattr(self,name,fn)
        self.library=lib

class Snapshot:
    """A bounded GPU-resident background, read back only for renderer fallback."""
    def __init__(self,renderer,width,height):
        self.renderer=renderer;self.width=width;self.height=height
    def to_cairo(self):
        r=self.renderer;gl=r.gl;saved=C.c_int();gl.GetIntegerv(0x8CA6,C.byref(saved))
        try:
            gl.BindFramebuffer(0x8D40,r.fbos[2])
            gl.FramebufferTexture2D(0x8D40,0x8CE0,0x0DE1,r.textures[3],0)
            return r.pixels_from_bound(self.width,self.height)
        finally:gl.BindFramebuffer(0x8D40,saved.value)

class DeferredSnapshot:
    """Keep GL work in the render phase instead of switching contexts on input."""
    def __init__(self,renderer,previous,wave,width,height,now):
        self.renderer=renderer;self.previous=previous;self.wave=wave
        self.width=width;self.height=height;self.now=now
        self.depth=1+(previous.depth if isinstance(previous,DeferredSnapshot) else 0)
    def to_cairo(self):
        self.renderer.resolve_base()
        base=self.renderer.field.base
        return base.to_cairo() if hasattr(base,'to_cairo') else base

class Renderer:
    def __init__(self, gl, field, constants):
        self.gl=gl;self.field=field;self.constants=constants
        self.program=0;self.vao=C.c_uint();self.textures=(C.c_uint*4)();self.fbos=(C.c_uint*3)()
        self.width=self.height=0;self.base_ref=None;self.snapshot_size=None
        shaders=[]
        try:
            for kind,source in ((0x8B31,VERTEX),(0x8B30,Path(__file__).with_name('colour_wave.frag').read_bytes())):
                shader=gl.CreateShader(kind);shaders.append(shader);ptr=C.c_char_p(source)
                gl.ShaderSource(shader,1,C.byref(ptr),None);gl.CompileShader(shader)
                ok=C.c_int();gl.GetShaderiv(shader,0x8B81,C.byref(ok))
                if not ok.value:
                    buf=C.create_string_buffer(8192);gl.GetShaderInfoLog(shader,8192,None,buf);raise RuntimeError(buf.value.decode())
            self.program=gl.CreateProgram()
            for shader in shaders:gl.AttachShader(self.program,shader)
            gl.LinkProgram(self.program);ok=C.c_int();gl.GetProgramiv(self.program,0x8B82,C.byref(ok))
            if not ok.value:
                buf=C.create_string_buffer(8192);gl.GetProgramInfoLog(self.program,8192,None,buf);raise RuntimeError(buf.value.decode())
            self.uniforms={name:gl.GetUniformLocation(self.program,name.encode()) for name in ('previous','copyOnly','geometry','timing','settings','target','breadth','tearShape','tearMotion','scuff')}
            gl.GenVertexArrays(1,C.byref(self.vao));gl.GenTextures(4,self.textures);gl.GenFramebuffers(3,self.fbos)
            for texture in self.textures:
                gl.BindTexture(0x0DE1,texture)
                for key,val in ((0x2801,0x2601),(0x2800,0x2601),(0x2802,0x812F),(0x2803,0x812F)):gl.TexParameteri(0x0DE1,key,val)
        except Exception:
            self.close();raise
        finally:
            for shader in shaders:gl.DeleteShader(shader)

    def close(self):
        gl=self.gl
        gl.DeleteFramebuffers(3,self.fbos);gl.DeleteTextures(4,self.textures)
        if self.vao.value:gl.DeleteVertexArrays(1,C.byref(self.vao))
        if self.program:gl.DeleteProgram(self.program);self.program=0
        self.base_ref=None

    def setup(self,width,height):
        gl=self.gl
        for state in (0x0BE2,0x0B71,0x0B90,0x0C11,0x0BD0,0x8DB9,0x0B44):gl.Disable(state)
        gl.UseProgram(self.program);gl.BindVertexArray(self.vao.value);gl.ActiveTexture(0x84C0)
        gl.Uniform1i(self.uniforms['previous'],0)
        if (width,height)!=(self.width,self.height):
            self.width,self.height=width,height
            for i in range(2):
                gl.BindTexture(0x0DE1,self.textures[i]);gl.TexImage2D(0x0DE1,0,0x8058,width,height,0,0x1908,0x1401,None)
                gl.BindFramebuffer(0x8D40,self.fbos[i]);gl.FramebufferTexture2D(0x8D40,0x8CE0,0x0DE1,self.textures[i],0)
                if gl.CheckFramebufferStatus(0x8D40)!=0x8CD5:raise RuntimeError('Colour framebuffer is incomplete')

    def copy(self,texture,fbo,width,height):
        gl=self.gl;gl.BindFramebuffer(0x8D40,fbo);gl.Viewport(0,0,width,height)
        gl.Uniform1i(self.uniforms['copyOnly'],1);gl.BindTexture(0x0DE1,texture);gl.DrawArrays(0x0004,0,3)

    def base(self):
        gl=self.gl;field=self.field;gl.BindFramebuffer(0x8D40,self.fbos[0]);gl.Viewport(0,0,self.width,self.height)
        if isinstance(field.base,int):
            gl.ClearColor(*self.constants['rgb'](field.base),1);gl.Clear(0x4000);self.base_ref=None
        elif isinstance(field.base,Snapshot):
            self.copy(self.textures[3],self.fbos[0],self.width,self.height)
        else:
            if self.base_ref is not field.base:
                surface=field.base;surface.flush();stride=surface.get_stride();rows=surface.get_data()
                data=b''.join(bytes(rows[y*stride:y*stride+surface.get_width()*4]) for y in range(surface.get_height()-1,-1,-1))
                buf=C.create_string_buffer(data);gl.BindTexture(0x0DE1,self.textures[2]);gl.PixelStorei(0x0CF5,1)
                gl.TexImage2D(0x0DE1,0,0x8058,surface.get_width(),surface.get_height(),0,0x80E1,0x1401,C.cast(buf,C.c_void_p));self.base_ref=surface
            self.copy(self.textures[2],self.fbos[0],self.width,self.height)

    def wave(self,wave,now,source,destination,refract,scuff=0.):
        gl=self.gl;u=self.uniforms;const=self.constants
        density=const['DENSITIES'][wave.density];material=const['MATERIALS'][wave.material]
        shown=now
        if scuff>0:
            shown=wave.start+wave.duration*float(const.get('AGENT_GHOST_PROGRESS',.52))
        gl.BindFramebuffer(0x8D40,self.fbos[destination]);gl.Viewport(0,0,self.width,self.height)
        gl.BindTexture(0x0DE1,self.textures[source]);gl.Uniform1i(u['copyOnly'],0)
        gl.Uniform4f(u['geometry'],self.width,self.height,wave.x,wave.y)
        gl.Uniform4f(u['timing'],max(0,min(1,(shown-wave.start)/wave.duration)),density[1],density[2],material[1])
        gl.Uniform4f(u['settings'],const['CHOICES']['effect'].index(wave.effect),
                     {'Off':0,'Soft':.16,'Bright':.30}[wave.pulse],float(wave.material=='Gel'),float(refract))
        gl.Uniform4f(u['tearShape'],*wave.shape[:4]);gl.Uniform4f(u['tearMotion'],*wave.shape[4:])
        gl.Uniform3f(u['target'],*const['rgb'](wave.colour));gl.Uniform1f(u['breadth'],material[2])
        gl.Uniform1f(u['scuff'],scuff);gl.DrawArrays(0x0004,0,3)

    def compose_scuff(self,width,height,now,scuff):
        self.resolve_base();self.setup(width,height);self.base()
        self.wave(scuff.wave,now,0,1,False,scuff.strength(now))
        return 1

    def compose(self,width,height,now,waves=None):
        self.resolve_base()
        self.setup(width,height);self.base();source=0
        for i,wave in enumerate(self.field.waves if waves is None else waves):
            destination=1-source
            self.wave(wave,now,source,destination,i>0 or not isinstance(self.field.base,int));source=destination
        return source

    def render(self,width,height,scale=1,now=None):
        gl=self.gl;now=time.monotonic() if now is None else now;self.field.advance(now)
        destination=C.c_int();gl.GetIntegerv(0x8CA6,C.byref(destination))
        scuff=getattr(self.field,'scuff',None)
        if not self.field.waves and scuff is None:
            gl.Disable(0x0BD0);gl.Disable(0x8DB9);gl.Disable(0x0C11);gl.ClearColor(*self.constants['rgb'](self.field.target),1);gl.Clear(0x4000);return
        rw,rh=self.field.render_size(width,height)
        source=self.compose_scuff(rw,rh,now,scuff) if scuff is not None and not self.field.waves else self.compose(rw,rh,now)
        self.copy(self.textures[source],destination.value,width*scale,height*scale)

    def write_png(self,path,width,height):
        gl=self.gl;gl.Finish();gl.PixelStorei(0x0D05,1)
        buf=(C.c_ubyte*(width*height*4))()
        gl.ReadPixels(0,0,width,height,0x80E1,0x1401,buf)
        raw=bytes(buf);stride=width*4
        data=bytearray(b''.join(raw[y*stride:(y+1)*stride] for y in range(height-1,-1,-1)))
        surface=cairo.ImageSurface.create_for_data(data,cairo.FORMAT_RGB24,width,height,stride)
        owned=cairo.ImageSurface(cairo.FORMAT_RGB24,width,height)
        ctx=cairo.Context(owned);ctx.set_source_surface(surface,0,0);ctx.paint()
        owned.write_to_png(str(path))

    def pixels_from_bound(self,width,height):
        gl=self.gl;buf=(C.c_ubyte*(width*height*4))()
        gl.ReadPixels(0,0,width,height,0x80E1,0x1401,buf)
        raw=bytes(buf);stride=width*4;data=bytearray(b''.join(raw[y*stride:(y+1)*stride] for y in range(height-1,-1,-1)))
        return cairo.ImageSurface.create_for_data(data,cairo.FORMAT_RGB24,width,height,stride)

    def pixels(self,source):
        self.gl.BindFramebuffer(0x8D40,self.fbos[source])
        return self.pixels_from_bound(self.width,self.height)

    def resolve_base(self):
        pending=[];base=self.field.base
        while isinstance(base,DeferredSnapshot):
            pending.append(base);base=base.previous
        if not pending:
            return
        self.field.base=base
        for job in reversed(pending):
            self.bake(job.width,job.height,job.now,job.wave)

    def bake(self,width,height,now,wave):
        rw,rh=self.field.render_size(width,height);gl=self.gl;saved=C.c_int();gl.GetIntegerv(0x8CA6,C.byref(saved))
        try:
            source=self.compose(rw,rh,now,[wave])
            gl.BindFramebuffer(0x8D40,self.fbos[source]);gl.BindTexture(0x0DE1,self.textures[3])
            if self.snapshot_size!=(rw,rh):
                gl.TexImage2D(0x0DE1,0,0x8058,rw,rh,0,0x1908,0x1401,None);self.snapshot_size=(rw,rh)
            gl.CopyTexSubImage2D(0x0DE1,0,0,0,0,0,rw,rh)
            self.field.base=Snapshot(self,rw,rh)
        finally:gl.BindFramebuffer(0x8D40,saved.value)

class Surface(Gtk.GLArea):
    def __init__(self,field,constants,fallback):
        super().__init__();self.field=field;self.constants=constants;self.fallback=fallback;self.gpu=None;self.failed=False
        self.set_required_version(3,2);self.set_auto_render(False);self.set_has_alpha(False)
        self.connect('create-context',self.create_context)
        self.connect('realize',self.initialize);self.connect('unrealize',self.dispose)

    def create_context(self,_area):
        # GLArea normally switches between an offscreen context and GTK's paint
        # context twice per frame. NVIDIA can stall during those handoffs even
        # when the shader is fast. Use the public shared paint context directly
        # when it supports our shader; GTK still owns presentation and timing.
        own=None
        try:
            own=self.get_window().create_gl_context()
            own.set_use_es(False);own.set_required_version(3,2);own.realize()
            shared=own.get_shared_context()
            if shared is not None:
                shared.make_current()
                gl=GL();major=C.c_int();minor=C.c_int()
                gl.GetIntegerv(0x821B,C.byref(major));gl.GetIntegerv(0x821C,C.byref(minor))
                if not shared.get_use_es() and (major.value,minor.value)>=(3,2):
                    return shared
        except GLib.Error:
            pass
        return own

    def fail(self,error):
        if not self.failed:
            self.failed=True;print('Chroma: using Cairo fallback:',error,flush=True);GLib.idle_add(self.fallback,self)

    def initialize(self,_area):
        try:
            self.make_current()
            if self.get_error():raise RuntimeError(str(self.get_error()))
            gl=GL();self.renderer_name=gl.GetString(0x1F01).decode()
            if os.environ.get('ALIEN_REQUIRE_HARDWARE_GL','').strip() in ('1','true','yes'):
                if any(name in self.renderer_name.lower() for name in ('llvmpipe','softpipe','software')):raise RuntimeError('software GL context')
            self.gpu=Renderer(gl,self.field,self.constants);self.field.baker=self.bake
            # Cinnamon's X11 FRAME_DRAWN acknowledgement can arrive a refresh
            # late and freeze GTK's clock at 30 Hz despite sub-ms GPU work.
            # The compositor already synchronizes display presentation. Keep
            # GTK's refresh-limited clock, without this second per-window wait.
            if self.get_screen().is_composited():
                try:
                    gi.require_version('GdkX11','3.0')
                    from gi.repository import GdkX11
                    native=self.get_toplevel().get_window()
                    if isinstance(native,GdkX11.X11Window):
                        native.set_frame_sync_enabled(False)
                except (ImportError,ValueError):
                    pass
            print('Chroma renderer: GPU — '+self.renderer_name+'; '+('shared window context' if self.get_context().get_shared_context() is None else 'independent context'),flush=True)
        except Exception as error:self.fail(error)

    def bake(self,width,height,now):
        if self.gpu and not self.failed:
            self.field.base=DeferredSnapshot(self.gpu,self.field.base,self.field.waves.pop(0),width,height,now)
            if self.field.base.depth>16:
                # Bound pathological input bursts that cannot be displayed in one
                # frame. Ordinary clicking needs no GL calls in the input handler.
                self.make_current();self.gpu.resolve_base()
        else:
            self.field.bake_oldest(width,height,now)

    def render_field(self):
        if self.failed or not self.gpu:return True
        try:self.gpu.render(self.get_allocated_width(),self.get_allocated_height(),self.get_scale_factor())
        except Exception as error:self.fail(error);return True
        window=self.get_toplevel()
        if window is not None and hasattr(window,'consider_agent_shot'):
            try:window.consider_agent_shot(self)
            except Exception as error:print('Chroma agent capture failed:',error,flush=True)
        return True

    def queue_draw(self):
        self.queue_render()

    def dispose(self,_area):
        self.field.baker=None
        if self.gpu:
            self.make_current()
            if not self.get_error():
                if hasattr(self.field.base,'to_cairo'):
                    self.field.base=self.field.base.to_cairo()
                self.gpu.close()
            elif hasattr(self.field.base,'to_cairo'):
                self.field.base=self.field.target
            self.gpu=None

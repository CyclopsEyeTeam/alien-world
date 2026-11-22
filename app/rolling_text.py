"""Transient, literal API text and passive random pi-swirl binary/symbol/number interpolation over the native display."""
import cairo,colorsys,math,time
from collections import deque
import calm_field

LANE_ACCENTS={
 'observer':(.28,.92,.85),
 'mist':(.76,.52,.98),
 'api':(.96,.76,.34),
}

PI_DIGITS=(
 '3.14159265358979323846264338327950288419716939937510'
 '58209749445923078164062862089986280348253421170679'
)
PI_BINARY='11.0010010000111111011010101000100010000101101000110000100011010011'

BINARY_TOKENS=('0','1','01','10','11','00','101','010','001','110')
SYMBOL_TOKENS=('π','∆','∑','∞','≈','√','◊','∂','∇','+','*','#','%','·','░','▒','▓')
CALM_SYMBOL_TOKENS=('π','∞','≈','◊','+','·','·','◦')
NUMBER_TOKENS=(
 '3.14','159','265','358','979','323','846','264','338','327',
 '950','288','419','716','939','937','510','582','097','494',
 '3','1','4','1','5','9','2','6','5','3','5','8','9','7','9',
)

def source_lane(source):
 text=str(source or '').casefold()
 if 'observer' in text:return 'observer'
 if any(k in text for k in ('mist','nanofable','lfm','remotehand','local')):return 'mist'
 return 'api'

def _clamp01(v):
 return 0. if v<0. else (1. if v>1. else v)

def pi_interpolate(a,b,u):
 """Smooth cosine interpolation in pi fashion: (1 - cos(pi * u)) / 2."""
 w=.5-.5*math.cos(math.pi*_clamp01(u))
 return a+(b-a)*w

def interpolate_pos(p0,p1,u):
 """Interpolate 2D coordinates (x0, y0) -> (x1, y1) with a slight pi-harmonic orthogonal curl."""
 u_clamped=_clamp01(u)
 w=.5-.5*math.cos(math.pi*u_clamped)
 curl=math.sin(math.pi*u_clamped)*.08
 dx=p1[0]-p0[0];dy=p1[1]-p0[1]
 return (p0[0]+dx*w-dy*curl,p0[1]+dy*w+dx*curl)

def interpolate_rgb(c0,c1,u):
 return (
  pi_interpolate(c0[0],c1[0],u),
  pi_interpolate(c0[1],c1[1],u),
  pi_interpolate(c0[2],c1[2],u),
 )

def _hash01(a,b,c=0):
 n=(int(a)*374761393+int(b)*668265263+int(c)*2147483647)&0xFFFFFFFF
 n=(n^(n>>13))*1274126177&0xFFFFFFFF
 return ((n^(n>>16))&0xFFFFFF)/float(0x1000000)

def _hsv(h,s,v):
 return colorsys.hsv_to_rgb(h%1.,max(0.,min(1.,s)),max(0.,min(1.,v)))

def morph_state_for_particle(index,t,seed=0):
 """Return (token_a, token_b, blend, family_a, family_b) cycling Binary -> Symbols -> Pi Numbers."""
 rate=.32+.11*_hash01(index,17,seed)
 phase=(t*rate+index*(math.pi/5.)+_hash01(index,31,seed)*3.)%3.
 stage_a=int(phase)%3
 stage_b=(stage_a+1)%3
 frac=phase-int(phase)
 blend=.5-.5*math.cos(math.pi*_clamp01(frac))
 drift=int(t*(.45+.08*(index%5))+index*3)
 families=(BINARY_TOKENS,SYMBOL_TOKENS,NUMBER_TOKENS)
 fam_names=('binary','symbol','number')
 tok_a=families[stage_a][(index*7+drift)%len(families[stage_a])]
 tok_b=families[stage_b][(index*11+drift+1)%len(families[stage_b])]
 return dict(
  token_a=tok_a,
  token_b=tok_b,
  blend=blend,
  family_a=fam_names[stage_a],
  family_b=fam_names[stage_b],
 )

class RollingQueue:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.messages=deque();self.started=None
 @property
 def current(self):return self.messages[0] if self.messages else None
 def add(self,text,source):
  if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=4096 or not isinstance(source,str) or len(source)>256:return False
  if len(self.messages)>=33:return False
  self.messages.append(dict(text=text,source=source));return True
 def clear(self):self.messages.clear();self.started=None
 def frame(self,viewport_height,content_height):
  if not self.messages:return None
  now=self.clock()
  if self.started is None:self.started=now
  # Even newline-heavy responses leave within 75 seconds; all text still passes
  # through the viewport, and the complete response remains in the byte archive.
  speed=max(30,(max(0,content_height)+max(0,viewport_height))/75)
  elapsed=max(0.,now-self.started)
  y=viewport_height-24-elapsed*speed
  if y+content_height<=0:self.messages.popleft();self.started=None;return None
  opacity=max(0.,min(1.,(viewport_height-y)/48,(y+content_height)/80))
  if calm_field.ENABLED:
   drift_x=round(math.sin(elapsed*.32)*3.2,4)
   phase=round((elapsed*.28)%1.,6)
  else:
   drift_x=round(math.sin(elapsed*1.15)*6.,4)
   phase=round((elapsed*.85)%1.,6)
  lane=source_lane(self.messages[0]['source'])
  return dict(y=y,opacity=opacity,drift_x=drift_x,phase=phase,lane=lane,queue_depth=len(self.messages))

def source_label(origin):
 origin=origin or {};provider=origin.get('provider','External provider');model=origin.get('reported_model') or origin.get('requested_model','')
 return (str(provider)+(' · '+str(model) if model else '')+' · floating signal · meaning unknown')[:256]

class RollingText:
 def __init__(self,overlay):
  import gi
  gi.require_version('Gtk','3.0');gi.require_version('Pango','1.0');gi.require_version('PangoCairo','1.0')
  from gi.repository import Gtk,GLib,Pango,PangoCairo
  self.GLib=GLib;self.Pango=Pango;self.PangoCairo=PangoCairo;self.queue=RollingQueue();self.timer=0;self.layout=None;self.layout_key=None
  self.t0=time.monotonic();self.tick=0;self.generation=0;self.sequence=0;self.entropy=.5;self.colour=.5
  self.sampled_glyphs=deque(maxlen=24)
  self._jolt=0.;self._entropy_ema=.5;self._colour_ema=.5
  self._chroma_hue=0.;self._chroma_target=0.;self._chroma_energy=0.
  self.glyph_layouts={}
  self.widget=Gtk.DrawingArea();self.widget.set_has_window(False);self.widget.set_can_focus(False);self.widget.set_hexpand(True);self.widget.set_vexpand(True)
  self.widget.set_halign(Gtk.Align.FILL);self.widget.set_valign(Gtk.Align.FILL);overlay.add_overlay(self.widget);overlay.set_overlay_pass_through(self.widget,True)
  self.widget.connect('draw',self.draw)
 def pulse(self,message=None):
  if message is not None:
   prev_tick=self.tick;prev_gen=self.generation
   self.tick=getattr(message,'tick',self.tick)
   self.generation=getattr(message,'generation',self.generation)
   self.sequence=getattr(message,'sequence',self.sequence)
   self.entropy=float(getattr(message,'entropy',self.entropy) or .5)
   self.colour=float(getattr(message,'colour',self.colour) or .5)
   rise=self.entropy-self._entropy_ema
   if rise>0:self._jolt=min(1.,self._jolt+rise*3.2)
   surge=min(1.,abs(rise)*16.+abs(self.colour-self._colour_ema)*4.5)
   if self.tick!=prev_tick:
    surge=max(surge,.48);self._chroma_target=(self._chroma_target+.11)%1.
   if self.generation!=prev_gen:
    surge=1.;self._chroma_target=(self._chroma_target+.382)%1.
   if surge>.06:
    self._chroma_energy=min(1.,max(self._chroma_energy,surge))
    self._chroma_target=(self._chroma_target+surge*.21)%1.
   self._entropy_ema+=(self.entropy-self._entropy_ema)*.08
   self._colour_ema+=(self.colour-self._colour_ema)*.08
   frame=getattr(message,'frame',None)
   cells=getattr(frame,'cells',None)
   if cells:
    try:
     rows=len(cells);cols=len(cells[0]) if rows else 0
     if rows>0 and cols>0:
      rx=int(_hash01(self.sequence,self.tick,1)*cols)%cols
      ry=int(_hash01(self.sequence,self.tick,2)*rows)%rows
      ch,rgb=cells[ry][rx]
      if ch and ch!=' ':
       self.sampled_glyphs.append((ch,rgb))
    except Exception:
     pass
  self.widget.queue_draw()
 def admitted(self,record):
  if not self.queue.add(record.get('text'),source_label(record.get('origin'))):return False
  self._chroma_target=(self._chroma_target+.29)%1.;self._chroma_energy=1.;self._jolt=min(1.,self._jolt+.55)
  if not self.timer:self.timer=self.GLib.timeout_add(50,self.advance)
  self.widget.queue_draw();return True
 def advance(self):
  layout=self.current_layout()
  if layout is not None:self.queue.frame(self.widget.get_allocated_height(),layout.get_pixel_size()[1])
  self.widget.queue_draw()
  if self.queue.messages:return True
  self.layout=None;self.layout_key=None;self.timer=0;return False
 def current_layout(self):
  item=self.queue.current
  if item is None:return None
  width=self.widget.get_allocated_width();margin=max(16,min(44,width//20));line_width=max(1,width-2*margin-24)
  key=(id(item),line_width)
  if key!=self.layout_key:
   header=item['source'].replace('\0','\ufffd')
   body=item['text'].replace('\0','\ufffd')
   self.layout=self.widget.create_pango_layout('');self.layout.set_font_description(self.Pango.FontDescription('Sans 13'));self.layout.set_width(line_width*self.Pango.SCALE);self.layout.set_wrap(self.Pango.WrapMode.WORD_CHAR)
   self.layout.set_text(header+'\n'+body,-1)
   attrs=self.Pango.AttrList();header_bytes=len(header.encode('utf-8'))
   font_attr=self.Pango.attr_font_desc_new(self.Pango.FontDescription('Monospace Bold 10'))
   font_attr.start_index=0;font_attr.end_index=header_bytes;attrs.insert(font_attr)
   self.layout.set_attributes(attrs);self.layout_key=key
  return self.layout
 def _token_layout(self,widget,text,size_pt=11):
  key=(text,size_pt)
  lay=self.glyph_layouts.get(key)
  if lay is None:
   if len(self.glyph_layouts)>256:self.glyph_layouts.clear()
   lay=widget.create_pango_layout(text)
   lay.set_font_description(self.Pango.FontDescription(f'Monospace Bold {size_pt}'))
   self.glyph_layouts[key]=lay
  return lay
 def _token_layout_regular(self,widget,text,size_pt=9):
  key=('reg',text,size_pt)
  lay=self.glyph_layouts.get(key)
  if lay is None:
   if len(self.glyph_layouts)>256:self.glyph_layouts.clear()
   lay=widget.create_pango_layout(text)
   lay.set_font_description(self.Pango.FontDescription(f'Monospace {size_pt}'))
   self.glyph_layouts[key]=lay
  return lay
 def _vortex_centers(self,t,w,h):
  """Three passive random vortex attractors wandering on irrational pi-harmonic paths."""
  centers=[]
  for k in range(3):
   phase_x=t/(math.pi*(1.15+.28*k))+k*(math.tau/3.)
   phase_y=t/(math.pi*(1.42+.23*k))+k*(math.tau/3.)+math.pi/4.
   wx=.5+.31*math.sin(phase_x)+.08*math.cos(t*.23-k*math.pi)
   wy=.5+.29*math.cos(phase_y)+.08*math.sin(t*.19+k*math.pi*.7)
   centers.append((wx*w,wy*h))
  return centers
 def _draw_pi_swirl_calm(self,widget,cr,width,height,card_rect=None):
  # Smooth monotonic clock without worker-burst sequence lurching, at a lively flowing pace.
  raw_t=time.monotonic()-self.t0
  t=raw_t*1.35
  dh=((self._chroma_target-self._chroma_hue+.5)%1.)-.5
  self._chroma_hue=(self._chroma_hue+dh*.14)%1.
  self._chroma_energy*=.95
  jolt=max(self._jolt,self._chroma_energy*.65);self._jolt*=.90
  max_r=min(width,height)*.33
  hue_shift=(self.colour*.55+t*.026+self._chroma_hue)%1.
  centers=self._vortex_centers(t*.72,width,height)
  from recipe_palette import recipe_rgb, table_for
  rtable=table_for(raw_t+self._chroma_hue*5.5,self.colour)
  def _c_col(h,s,v):
   if rtable is not None:
    rgb=recipe_rgb(rtable,h,s,v)
    return rgb[0]/255.,rgb[1]/255.,rgb[2]/255.
   return _hsv(h,s,v)
  cr.save();cr.rectangle(0,0,width,height);cr.clip()

  def _card_fade(px,py):
   if card_rect is None:return 1.
   cx0,cy0,cw,ch=card_rect
   dx=max(cx0-px,0.,px-(cx0+cw))
   dy=max(cy0-py,0.,py-(cy0+ch))
   d=math.hypot(dx,dy)
   return _clamp01(d/56.)

  # 1. Three soft orbital halos + rotating pi/binary/symbol markers
  ring_labels=('π·3·1·4·','1·0·1·1·','∞·∆·◊·≈·')
  for k,(vx,vy) in enumerate(centers):
   ring_r=max_r*(.17+.025*math.sin(t*.6+k*math.pi))
   base_hue=(hue_shift+k*.33+.08)%1.
   r_col,g_col,b_col=_c_col(base_hue,.84,.96)
   cf=_card_fade(vx,vy)
   cr.save()
   cr.translate(vx,vy);cr.scale(1.14,.86)
   cr.set_source_rgba(r_col,g_col,b_col,.12*cf)
   cr.set_line_width(.95)
   cr.arc(0.,0.,ring_r,0.,math.tau);cr.stroke()
   cr.restore()
   ring_str=ring_labels[k%len(ring_labels)]
   for idx,ch in enumerate(ring_str):
    ang=(idx/len(ring_str))*math.tau+t*(.38 if k!=1 else -.32)+k*math.pi*.5
    rx=vx+math.cos(ang)*ring_r*1.14
    ry=vy+math.sin(ang)*ring_r*.86
    if not (10<=rx<=width-10 and 10<=ry<=height-10):continue
    fade=_card_fade(rx,ry)
    if fade<.05:continue
    lay=self._token_layout_regular(widget,ch,9)
    cr.set_source_rgba(r_col,g_col,b_col,(.24+.08*math.sin(t*1.3+idx))*fade)
    cr.move_to(rx-3,ry-5)
    self.PangoCairo.show_layout(cr,lay)

  # 2. 28 wandering & swirling cosmos motes morphing Binary <-> Symbols <-> Pi
  num_particles=28
  arm_nodes={0:[],1:[],2:[]}
  calm_families=(BINARY_TOKENS,CALM_SYMBOL_TOKENS,NUMBER_TOKENS)
  for i in range(num_particles):
   v_idx=i%3
   vx,vy=centers[v_idx]
   arm=(i//3)%2
   slot=i//6
   total_slots=max(1,(num_particles+5)//6)
   s=(slot+.5)/total_slots
   seed_x=_hash01(i,101,self.generation)
   seed_y=_hash01(i,202,self.generation)
   rand_x=width*(.06+.88*((seed_x+math.sin(t*(.16+.04*(i%5))+i*1.7)*.28)%1.))
   rand_y=height*(.06+.88*((seed_y+math.cos(t*(.14+.04*(i%4))+i*2.3)*.28)%1.))
   omega=.58+.34/(.32+s)
   theta=arm*math.pi+s*math.tau*1.61803398875-t*omega*(1. if v_idx!=1 else -1.)
   rad=max_r*(.12+.84*(s**.86))*(1.+.07*math.sin(math.pi*s*2.5-t*.9+i))
   swirl_x=vx+math.cos(theta)*rad*1.16
   swirl_y=vy+math.sin(theta)*rad*.86
   capture_wave=.56+.42*math.sin(t*(.28+.04*(i%6))+i*(math.pi/8.))
   ix,iy=interpolate_pos((rand_x,rand_y),(swirl_x,swirl_y),capture_wave)
   if not (10<=ix<=width-22 and 10<=iy<=height-16):continue
   fade=_card_fade(ix,iy)
   if fade<.05:continue
   arm_nodes[v_idx].append((ix,iy,s,i,fade))

   morph=morph_state_for_particle(i,t*.85,seed=self.generation)
   blend=morph['blend']
   stage_a=0 if morph['family_a']=='binary' else (1 if morph['family_a']=='symbol' else 2)
   stage_b=0 if morph['family_b']=='binary' else (1 if morph['family_b']=='symbol' else 2)
   drift=int(t*.38+i*3)
   tok_a=calm_families[stage_a][(i*7+drift)%len(calm_families[stage_a])]
   tok_b=calm_families[stage_b][(i*11+drift+1)%len(calm_families[stage_b])]
   hue_a=(hue_shift+v_idx*.31+s*.36+stage_a*.17)%1.
   hue_b=(hue_shift+v_idx*.31+s*.36+stage_b*.17)%1.
   col_a=_c_col(hue_a,.86,.97)
   col_b=_c_col(hue_b,.88,.98)
   r,g,b=interpolate_rgb(col_a,col_b,blend)
   base_alpha=(.26+.16*(1.-.4*s)+.06*math.sin(t*1.5+i)+min(.08,jolt*.10))*fade
   tok=tok_a if blend<.5 else tok_b
   cross=1.-.28*math.sin(math.pi*blend)
   lay=self._token_layout_regular(widget,tok,10 if s<.4 else 9)
   cr.set_source_rgba(r,g,b,base_alpha*cross)
   cr.move_to(ix,iy)
   self.PangoCairo.show_layout(cr,lay)

  # 3. Constellation filaments + travelling light beads
  for v_idx,nodes in arm_nodes.items():
   if len(nodes)<3:continue
   for j in range(len(nodes)-2):
    x0,y0,s0,idx0,f0=nodes[j]
    x1,y1,s1,idx1,f1=nodes[j+2]
    dist=math.hypot(x1-x0,y1-y0)
    if dist>max_r*.72 or dist<10.:continue
    fade=min(f0,f1)
    mx,my=interpolate_pos((x0,y0),(x1,y1),.5)
    fh=(hue_shift+v_idx*.31+s0*.34)%1.
    fr,fg,fb=_c_col(fh,.80,.95)
    cr.set_source_rgba(fr,fg,fb,.11*fade)
    cr.set_line_width(.9)
    cr.move_to(x0+3,y0+5);cr.curve_to(mx+3,my+5,mx+3,my+5,x1+3,y1+5)
    cr.stroke()
    u_pulse=(t*.85+idx0*.21)%1.
    px_b,py_b=interpolate_pos((x0+3,y0+5),(x1+3,y1+5),u_pulse)
    cr.set_source_rgba(fr,fg,fb,.30*fade)
    cr.arc(px_b,py_b,1.5,0.,math.tau);cr.fill()

  # 4. Four ephemeral random geometric curiosities (breathing rings & arcs in random spots)
  for slot in range(4):
   cpos=t*.16+slot*.61803398875
   cyc=int(math.floor(cpos))
   cu=cpos-cyc
   env=math.sin(math.pi*cu)
   if env<.08:continue
   rx=width*(.10+.80*_hash01(slot,311,cyc+self.generation))
   ry=height*(.12+.76*_hash01(slot,419,cyc+self.generation))
   fade=_card_fade(rx,ry)*env
   if fade<.05:continue
   ch=(hue_shift+_hash01(slot,523,cyc))%1.
   cr_c,cg_c,cb_c=_c_col(ch,.86,.97)
   rad_c=8.+18.*cu+6.*_hash01(slot,617,cyc)
   cr.set_source_rgba(cr_c,cg_c,cb_c,.24*fade)
   cr.set_line_width(1.0)
   a_start=t*.9+slot*1.7
   cr.arc(rx,ry,rad_c,a_start,a_start+math.pi*1.35);cr.stroke()
   cr.set_source_rgba(cr_c,cg_c,cb_c,.36*fade)
   cr.arc(rx+math.cos(a_start)*rad_c,ry+math.sin(a_start)*rad_c,1.8,0.,math.tau);cr.fill()
  cr.restore()
 def draw_pi_swirl(self,widget,cr,width,height,card_rect=None):
  if width<64 or height<64:return
  if calm_field.ENABLED:
   self._draw_pi_swirl_calm(widget,cr,width,height,card_rect)
   return
  t=time.monotonic()-self.t0+self.sequence*.012
  jolt=self._jolt;self._jolt*=.92
  centers=self._vortex_centers(t,width,height)
  max_r=min(width,height)*.33
  hue_shift=(self.colour*.65+t*.028)%1.
  cr.save();cr.rectangle(0,0,width,height);cr.clip()

  # 1. Faint rotating pi-constant and binary-pi inner rings around each passive vortex center
  for k,(vx,vy) in enumerate(centers):
   ring_r=max_r*(.16+.03*math.sin(t*.7+k*math.pi))
   ring_str=PI_DIGITS[:20] if k%2==0 else PI_BINARY[:20]
   base_hue=(hue_shift+k*(1./3.)+.12)%1.
   r_col,g_col,b_col=_hsv(base_hue,.78,.96)
   for idx,ch in enumerate(ring_str):
    ang=(idx/len(ring_str))*math.tau+t*(.52 if k%2==0 else -.44)+k*math.pi*.5
    rx=vx+math.cos(ang)*ring_r*1.12
    ry=vy+math.sin(ang)*ring_r*.88
    if not (8<=rx<=width-8 and 8<=ry<=height-8):continue
    lay=self._token_layout(widget,ch,9)
    cr.set_source_rgba(r_col,g_col,b_col,.30+.14*math.sin(t*2.+idx))
    cr.move_to(rx-4,ry-6)
    self.PangoCairo.show_layout(cr,lay)

  # 2. Passive random particles interpolating in position and morphing Binary <-> Symbols <-> Pi Numbers
  num_particles=66
  arm_nodes={0:[],1:[],2:[]}
  for i in range(num_particles):
   v_idx=i%3
   vx,vy=centers[v_idx]
   arm=(i//3)%2
   slot=i//6
   total_slots=max(1,num_particles//6)
   s=(slot+.5)/total_slots

   # Passive random wandering position across the field
   seed_x=_hash01(i,101,self.generation)
   seed_y=_hash01(i,202,self.generation)
   freq_x=.17+.29*_hash01(i,303)
   freq_y=.15+.27*_hash01(i,404)
   rand_x=width*(.06+.88*((seed_x+math.sin(t*freq_x+i*1.7)*.28)%1.))
   rand_y=height*(.06+.88*((seed_y+math.cos(t*freq_y+i*2.3)*.28)%1.))

   # Swirling pi-spiral orbital position around vortex v_idx
   # Differential angular velocity (inner swirls faster in pi ratio)
   omega=(math.pi/2.6)+.52/(.28+s)
   theta=arm*math.pi+s*math.tau*1.61803398875-t*omega*(1. if v_idx!=1 else -1.)
   rad=max_r*(.08+.88*(s**.86))*(1.+.10*math.sin(math.pi*s*3.-t*1.4+i))
   swirl_x=vx+math.cos(theta)*rad*1.16
   swirl_y=vy+math.sin(theta)*rad*.88

   # Smooth pi-interpolation factor between passive random scatter and pi-spiral vortex
   capture_wave=.56+.44*math.sin(t*(.42+.05*(i%7))+i*(math.pi/9.))
   ix,iy=interpolate_pos((rand_x,rand_y),(swirl_x,swirl_y),capture_wave)
   if jolt>.02:
    ix+=math.sin(t*8.5+i*2.1)*jolt*7.
    iy+=math.cos(t*7.3+i*1.7)*jolt*5.
   if not (6<=ix<=width-18 and 6<=iy<=height-14):continue
   arm_nodes[v_idx].append((ix,iy,s,i))

   # Morph state between Binary, Symbols, and Pi Numbers
   morph=morph_state_for_particle(i,t,seed=self.generation)
   blend=morph['blend']

   # Interpolate colour between the two morph stages
   hue_a=(hue_shift+v_idx*.28+s*.35+(.0 if morph['family_a']=='binary' else (.16 if morph['family_a']=='symbol' else .32)))%1.
   hue_b=(hue_shift+v_idx*.28+s*.35+(.0 if morph['family_b']=='binary' else (.16 if morph['family_b']=='symbol' else .32)))%1.
   col_a=_hsv(hue_a,.82,.98)
   col_b=_hsv(hue_b,.86,1.0)
   r,g,b=interpolate_rgb(col_a,col_b,blend)

   # Tangential unit offset for smooth cross-fade glyph interpolation
   tx=-math.sin(theta)*5.5
   ty=math.cos(theta)*5.5
   base_alpha=.42+.36*(1.-.45*s)+.12*math.sin(t*2.4+i)+jolt*.22
   size_pt=(11 if s<.45 else 10)+(2 if jolt>.4 else 0)

   if blend<.18:
    lay=self._token_layout(widget,morph['token_a'],size_pt)
    cr.set_source_rgba(r,g,b,base_alpha)
    cr.move_to(ix,iy)
    self.PangoCairo.show_layout(cr,lay)
   elif blend>.82:
    lay=self._token_layout(widget,morph['token_b'],size_pt)
    cr.set_source_rgba(r,g,b,base_alpha)
    cr.move_to(ix,iy)
    self.PangoCairo.show_layout(cr,lay)
   else:
    # Simultaneous interpolated glyph cross-fade (token_a morphing into token_b along the swirl tangent)
    lay_a=self._token_layout(widget,morph['token_a'],size_pt)
    lay_b=self._token_layout(widget,morph['token_b'],size_pt)
    cr.set_source_rgba(col_a[0],col_a[1],col_a[2],base_alpha*(1.-blend))
    cr.move_to(ix-tx*blend,iy-ty*blend)
    self.PangoCairo.show_layout(cr,lay_a)
    cr.set_source_rgba(col_b[0],col_b[1],col_b[2],base_alpha*blend)
    cr.move_to(ix+tx*(1.-blend),iy+ty*(1.-blend))
    self.PangoCairo.show_layout(cr,lay_b)

  # 3. Delicate interpolated phase filaments connecting consecutive nodes along each pi-swirl arm
  for v_idx,nodes in arm_nodes.items():
   if len(nodes)<3:continue
   for j in range(len(nodes)-2):
    x0,y0,s0,idx0=nodes[j]
    x1,y1,s1,idx1=nodes[j+2]
    dist=math.hypot(x1-x0,y1-y0)
    if dist>max_r*.75 or dist<8.:continue
    mx,my=interpolate_pos((x0,y0),(x1,y1),.5)
    fh=(hue_shift+v_idx*.31+s0*.4)%1.
    fr,fg,fb=_hsv(fh,.75,.95)
    cr.set_source_rgba(fr,fg,fb,.13)
    cr.set_line_width(1.1)
    cr.move_to(x0+4,y0+6);cr.quadratic_curve_to(mx+4,my+6,x1+4,y1+6) if hasattr(cr,'quadratic_curve_to') else cr.curve_to(mx+4,my+6,mx+4,my+6,x1+4,y1+6)
    cr.stroke()
    # Tiny interpolated midpoint binary/dot pulse running along the filament
    u_pulse=(t*1.3+idx0*.19)%1.
    px,py=interpolate_pos((x0+4,y0+6),(x1+4,y1+6),u_pulse)
    cr.set_source_rgba(fr,fg,fb,.38)
    cr.arc(px,py,1.6,0,math.tau);cr.fill()

  cr.restore()
 draw_cosmos=draw_pi_swirl
 def draw(self,widget,cr):
  width,height=widget.get_allocated_width(),widget.get_allocated_height()
  layout=self.current_layout()
  frame=None;content_width=0;content_height=0;margin=max(16,min(44,width//20))
  card_rect=None
  if layout is not None:
   content_width,content_height=layout.get_pixel_size();frame=self.queue.frame(height,content_height)
   if frame is None:self.layout_key=None
   else:
    x_c=margin+12+frame.get('drift_x',0.);y_c=frame['y']
    box_w_c=min(max(120,content_width+24),max(120,width-2*margin))
    card_rect=(x_c-12,y_c-8,box_w_c,content_height+16)
  self.draw_pi_swirl(widget,cr,width,height,card_rect)
  if layout is None or frame is None:return False
  alpha=frame['opacity'];x=margin+12+frame.get('drift_x',0.);y=frame['y']
  accent=LANE_ACCENTS.get(frame.get('lane','api'),LANE_ACCENTS['api'])
  box_w=min(max(120,content_width+24),max(120,width-2*margin))
  cr.save();cr.rectangle(0,0,width,height);cr.clip()
  if calm_field.ENABLED:
   bx,by,bw,bh=x-12,y-8,box_w,content_height+16
   cr.set_source_rgba(.02,.04,.07,.74*alpha);cr.rectangle(bx,by,bw,bh);cr.fill()
   cr.set_source_rgba(*accent,.20*alpha);cr.set_line_width(.9);cr.rectangle(bx,by,bw,bh);cr.stroke()
   cr.set_source_rgba(*accent,.86*alpha);cr.rectangle(bx,by,2.5,bh);cr.fill()
   glyphs=list(self.sampled_glyphs)
   if glyphs:
    for gi,(gx,gy) in enumerate(((bx+bw-11.,by+4.),(bx+bw-11.,by+bh-14.))):
     gch,grgb=glyphs[gi%len(glyphs)]
     lay=self._token_layout_regular(widget,gch,8)
     cr.set_source_rgba(grgb[0]/255.,grgb[1]/255.,grgb[2]/255.,.34*alpha)
     cr.move_to(gx,gy)
     self.PangoCairo.show_layout(cr,lay)
   cr.move_to(x+1,y+1.5);cr.set_source_rgba(0,0,0,.78*alpha);self.PangoCairo.show_layout(cr,self.layout)
   cr.move_to(x,y);cr.set_source_rgba(.93,.96,.99,alpha);self.PangoCairo.show_layout(cr,self.layout)
   if content_height>40:
    gr=cairo.LinearGradient(0.,y+content_height-20.,0.,y+content_height+6.)
    gr.add_color_stop_rgba(0.,.02,.04,.07,0.)
    gr.add_color_stop_rgba(1.,.02,.04,.07,.80*alpha)
    cr.set_source(gr);cr.rectangle(bx,y+content_height-20.,bw,26.);cr.fill()
   cr.restore();return False
  cr.set_source_rgba(.03,.05,.09,.68*alpha);cr.rectangle(x-12,y-8,box_w,content_height+16);cr.fill()
  glyphs=list(self.sampled_glyphs)
  cr.set_source_rgba(*accent,(.10 if glyphs else .28)*alpha);cr.set_line_width(1.);cr.rectangle(x-12,y-8,box_w,content_height+16);cr.stroke()
  cr.set_source_rgba(*accent,.92*alpha);cr.rectangle(x-12,y-8,3,content_height+16);cr.fill()
  if glyphs:
   # Border stitched from real sampled field glyphs — the panel reads as
   # assembled from field material rather than pasted on top of it.
   bx,by=x-12,y-8;bw,bh=box_w,content_height+16
   n_top=max(2,int(bw)//22);n_side=max(2,int(bh)//18)
   span_top=max(1,n_top-1);span_side=max(1,n_side-1)
   positions=[(bx+12.+(bw-24.)*i/span_top,by-7.) for i in range(n_top)]
   positions+=[(bx+12.+(bw-24.)*i/span_top,by+bh-9.) for i in range(n_top)]
   positions+=[(bx+bw-9.,by+8.+(bh-16.)*i/span_side) for i in range(n_side)]
   for gi,(gx,gy) in enumerate(positions):
    gch,grgb=glyphs[gi%len(glyphs)]
    lay=self._token_layout(widget,gch,8)
    cr.set_source_rgba(grgb[0]/255.,grgb[1]/255.,grgb[2]/255.,.52*alpha)
    cr.move_to(gx+(_hash01(gi,7,1)-.5)*6.,gy+(_hash01(gi,11,2)-.5)*4.)
    self.PangoCairo.show_layout(cr,lay)
  cr.move_to(x+1,y+2);cr.set_source_rgba(0,0,0,.9*alpha);self.PangoCairo.show_layout(cr,self.layout)
  cr.move_to(x,y);cr.set_source_rgba(.92,.97,1,alpha);self.PangoCairo.show_layout(cr,self.layout)
  # Trailing dissolve: the last strip of text sinks into the panel floor, so a
  # model reply that ends mid-word reads as fading back into the field.
  if content_height>40:
   gr=cairo.LinearGradient(0.,y+content_height-20.,0.,y+content_height+6.)
   gr.add_color_stop_rgba(0.,.03,.05,.09,0.)
   gr.add_color_stop_rgba(1.,.03,.05,.09,.78*alpha)
   cr.set_source(gr);cr.rectangle(x-12,y+content_height-20.,box_w,26.);cr.fill()
  cr.restore();return False
 def clear(self):
  if self.timer:self.GLib.source_remove(self.timer);self.timer=0
  self.queue.clear();self.layout=None;self.layout_key=None;self.widget.queue_draw()

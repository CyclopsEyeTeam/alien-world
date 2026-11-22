"""Bounded measured cues and separate, temporary drawing expressions.

No owner input, model call, native clock or retained Eye ink is created here.
"""
import colorsys,math,time
from collections import OrderedDict
from neural_types import validate_expression,validate_presented

def retained_ancestry(*groups):
 """Keep a permanent old witness plus recent IDs; overflow never cleans taint."""
 result=list(dict.fromkeys(ident for group in groups for ident in group))
 return result if len(result)<=8 else result[:1]+result[-7:]

class ExpressionLayer:
 def __init__(self,runtime,world):
  self.runtime=runtime;self.world=world;self.current=None;self.seen=OrderedDict();self.reported=None;self.presented_ids=[]
 def offer(self,record):
  value=validate_expression(record)
  if value['runtime']!=self.runtime or value['world_id']!=self.world:raise ValueError('expression belongs to another world')
  ident=value['output_id']
  if ident in self.seen:return False
  self.seen[ident]=None
  while len(self.seen)>128:self.seen.popitem(last=False)
  self.current=value;self.reported=None;return True
 def at(self,tick):
  value=self.current
  if value is None:return None
  if type(tick) is not int or tick<value['stamp']['tick']:
   return None
  if tick>value['expires_tick']:
   self.current=None;return None
  return value
 def receipt(self,surface,tick,sequence=None,now_ns=None,eye_runtime=None,visible=True):
  value=self.at(tick)
  if not visible or value is None or not any(r['strength']>0 for r in value['regions']):self.presented_ids=[];return None
  self.presented_ids=[value['output_id']]
  if self.reported==value['output_id']:return None
  record=dict(version=1,output_id=value['output_id'],runtime=self.runtime,world_id=self.world,surface=surface,stamp=value['stamp'],render_tick=tick,presented_ns=time.monotonic_ns() if now_ns is None else now_ns)
  if sequence is not None:record['display_sequence']=sequence
  if eye_runtime is not None:record['eye_runtime']=eye_runtime
  record=validate_presented(record);self.reported=value['output_id'];return record

class SensoryMetrics:
 """Fresh-capture proxies; held animation never calls measure()."""
 def __init__(self):self.previous_ns=None;self.attention=None;self.dwell=0
 def measure(self,glimpse,percept,sight,captured_ns):
  report=sight.report;mask=sight.policy.observed(glimpse);seen=[i for i,ok in enumerate(mask) if ok]
  field=percept.field
  out=dict(brightness=field.brightness,saturation=field.saturation,density=field.density,contrast=field.contrast)
  previous=self.previous_ns is not None and 0<captured_ns-self.previous_ns<=2_500_000_000
  if report is not None:
   out['sight']={name:getattr(report,name) for name in ('observed_cells','changed_cells','vivid_cells','luminance_cells','chromatic_cells','structural_cells','surfaces','new_keys','lost_keys') if hasattr(report,name)}
   if previous:
    out['persistence']=report.persistence
    if report.observed_cells:out['flicker_density']=report.luminance_cells/report.observed_cells
  if previous:
   out['change']=field.change
   area=sum(r.box.area for r in percept.regions)
   if area:out['motion_energy']=min(1.,math.sqrt(sum(r.box.area*(r.motion.dx*r.motion.dx+r.motion.dy*r.motion.dy) for r in percept.regions)/(2*area)))
  if seen:
   out['edge']=sum(getattr(glimpse,name)[i] for name in ('edges_horizontal','edges_vertical','edges_rising','edges_falling') for i in seen)/(4*len(seen))
   bins=[0.]*12;vectors=[[0.,0.] for _ in bins]
   for i in seen:
    hue=glimpse.hue[i];weight=glimpse.saturation[i];index=min(11,int(hue*12));bins[index]+=weight;vectors[index][0]+=weight*math.cos(2*math.pi*hue);vectors[index][1]+=weight*math.sin(2*math.pi*hue)
   total=sum(bins)
   if total>1e-9:
    best=max(range(12),key=bins.__getitem__);x,y=vectors[best]
    out['colour_dominance']=bins[best]/total;out['dominant_hue']=(math.atan2(y,x)/(2*math.pi))%1.
  attention=percept.attention
  if attention is not None:
   point=(attention.x,attention.y)
   self.dwell=min(128,self.dwell+1) if previous and self.attention is not None and math.dist(point,self.attention)<=.06 else 1
   out.update(attention_x=attention.x,attention_y=attention.y,attention_strength=attention.strength,attention_dwell_samples=self.dwell)
   self.attention=point
  else:self.attention=None;self.dwell=0
  self.previous_ns=captured_ns
  return out

def sprite_rectangles(sprites,masks):
 """Whole-pixel bounds, including outlines, glow, moving and depth sprites."""
 rectangles=[]
 for sprite in sprites:
  if sprite.kind=='attention':
   left=math.floor(sprite.x-sprite.radius)-1;top=math.floor(sprite.y-sprite.radius)-1
   right=math.ceil(sprite.x+sprite.radius)+1;bottom=math.ceil(sprite.y+sprite.radius)+1
  else:
   left=math.floor(sprite.x-masks.margin)-1;top=math.floor(sprite.y-masks.margin)-1
   right=math.ceil(sprite.x-masks.margin+masks.width)+1;bottom=math.ceil(sprite.y-masks.margin+masks.height)+1
  rectangles.append((left,top,right-left,bottom-top))
 return rectangles

def eye_protected_rectangles(box,fraction):
 from cyclops_eye.box import compose,depth_sprites
 sprites=compose(box.scene,box.state,fraction,box.geometry,box.linger,box.fresh)
 if box.depth is not None:sprites+=depth_sprites(box.depth.view(fraction),box.geometry,box._occupied)
 return sprite_rectangles(sprites,box.masks)

def paint_expression_cairo(cr,record,width,height,protected,projection=None):
 """A separate layer; no glyph/scene/state is replaced or relabelled as ink."""
 if record is None or width<1 or height<1 or not any(r['strength']>0 for r in record['regions']):return False
 import cairo
 mask=cairo.ImageSurface(cairo.FORMAT_A8,width,height);mc=cairo.Context(mask)
 mc.set_antialias(cairo.ANTIALIAS_NONE);mc.set_source_rgba(1,1,1,1);mc.paint();mc.set_operator(cairo.OPERATOR_CLEAR)
 for x,y,w,h in protected:mc.rectangle(x,y,w,h)
 mc.fill();mask.flush()
 # If every region is masked, there was no visible expression to receipt.
 layer=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height);draw=cairo.Context(layer)
 marker=record['marker'];phase=((marker['tick_echo']%8)/8+(int(marker['continuity'] or '0',16)%1024)/1024+(int(marker['grounding'] or '0',16)%1024)/1024)*math.tau
 centers=[]
 for region in record['regions']:
  if region['strength']<=0:continue
  if projection is None:x,y=region['x']*width,region['y']*height;radius=region['radius']*min(width,height)
  else:x,y,radius=projection(region)
  centers.append((x,y,radius,region))
  draw.set_source_rgba(*colorsys.hsv_to_rgb(region['hue'],.65,.95),.18*region['strength'])
  draw.set_line_width(1.5+1.5*marker['chain_residue']);draw.set_dash((max(2.,radius*.2),max(2.,radius*.12)),phase)
  draw.arc(x,y,max(2.,radius),phase,phase+math.tau);draw.stroke()
  # Small context knots make the tick/chain fragment visible without a panel.
  draw.set_dash(())
  for index in range(1+marker['tick_echo']%3):
   angle=phase+index*.35;draw.arc(x+radius*math.cos(angle),y+radius*math.sin(angle),1.5,0,math.tau);draw.fill()
 if len(centers)>=2:
  x0,y0,_,r0=centers[0]
  for x1,y1,_,r1 in centers[1:]:
   draw.set_source_rgba(*colorsys.hsv_to_rgb((r0['hue']+r1['hue'])*.5,.55,.95),.12*min(r0['strength'],r1['strength']))
   draw.set_line_width(1.+marker['chain_residue']);draw.set_dash((3.,4.),phase)
   draw.move_to(x0,y0);draw.line_to(x1,y1);draw.stroke()
  draw.set_dash(())
 layer.flush()
 # Measure actual drawable alpha against the mask before claiming presentation.
 composited=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height);cc=cairo.Context(composited);cc.set_source_surface(layer,0,0);cc.mask_surface(mask,0,0);composited.flush()
 visible=bool(bytes(composited.get_data()).strip(b'\0'))
 if visible:
  cr.save();cr.set_source_surface(composited,0,0);cr.paint();cr.restore()
 # These locally generated pixels are owned by Cairo until its draw target
 # releases them (GTK may record a surface pattern for later presentation).
 # They never become screenshot files or native retained Eye ink.
 return visible

def paint_eye_expression(cr,box,record,fraction,size):
 if record is None or box.state is None or box.scene is None:return False
 from cyclops_eye.third_eye import C0,C1,R0,R1
 def projection(region):
  x,y=box.geometry.xy(C0+(C1-C0)*region['x'],R0+(R1-R0)*region['y'])
  return x,y,region['radius']*min((C1-C0)*box.geometry.pitch_x,(R1-R0)*box.geometry.pitch_y)
 return paint_expression_cairo(cr,record,*size,eye_protected_rectangles(box,fraction),projection)

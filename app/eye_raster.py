"""Native Eye raster reduction for explicit in-memory rendered pixels.

Selectively ported from the preserved Eye MCP raster adapter, rather than
adopting its older Eye implementation. The current snapshot supplies sight.
"""
from dataclasses import replace
import math,cairo
from zilo_outside_look.x11_glimpse import CONTRAST,DETAIL,X11Glimpser,_surface
class RasterGlimpser(X11Glimpser):
 def __init__(self,width,height):
  if not 2<=width<=8192 or not 2<=height<=8192 or width*height>8_388_608:raise ValueError('unsupported raster dimensions')
  self.origin=(0,0);self.width=width;self.height=height;self.cols=min(64,width);self.rows=min(36,height);self._contrast=CONTRAST
  self._allocate([_surface(math.ceil(width/2),math.ceil(height/2)),_surface(self.cols*DETAIL,self.rows*DETAIL)])
  self._started=0.;self.last_ms=0.;self._image=None
 def _copy_screen(self):
  half,work=self._server;cr=cairo.Context(half);cr.scale(.5,.5);cr.set_source_surface(self._image,0,0)
  cr.get_source().set_filter(cairo.FILTER_BILINEAR);cr.get_source().set_extend(cairo.EXTEND_PAD);cr.set_operator(cairo.OPERATOR_SOURCE);cr.paint()
  cr=cairo.Context(work);cr.scale(work.get_width()/half.get_width(),work.get_height()/half.get_height());cr.set_source_surface(half,0,0)
  cr.get_source().set_filter(cairo.FILTER_BILINEAR);cr.get_source().set_extend(cairo.EXTEND_PAD);cr.set_operator(cairo.OPERATOR_SOURCE);cr.paint()
  cr=cairo.Context(self._base);cr.set_source_surface(work,0,0);cr.set_operator(cairo.OPERATOR_SOURCE);cr.paint()
 def look(self,image,time_ms=0):
  if (image.get_width(),image.get_height())!=(self.width,self.height):raise ValueError('raster dimensions changed')
  self._image=image
  try:return replace(self.glimpse(),time_ms=time_ms)
  finally:self._image=None

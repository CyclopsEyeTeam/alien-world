"""Native-sized cell geometry; unsupported viewports never silently lose cells."""
import math
from protocol import _geometry

def grid_for_viewport(width,height,cell_width,cell_height):
    values=(width,height,cell_width,cell_height)
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):raise ValueError('invalid viewport or font metrics')
    cols=math.floor(width/cell_width);rows=math.floor(height/cell_height)
    _geometry(cols,rows)
    return cols,rows

def initial_geometry(cols,rows,width,height,cell_width,cell_height):
    if cols is None and rows is None:return grid_for_viewport(width,height,cell_width,cell_height)
    if cols is None or rows is None:raise ValueError('explicit geometry requires both columns and rows')
    _geometry(cols,rows)
    return cols,rows

"""Frame-invariant scalar preparation. Preserve original float expression order."""
import math
from recipe_palette import table_for, recipe_rgb
import calm_field

def prepare_state(ns,genome,t,cols,rows,chroma_hue=0.0,chroma_pulse=0.0):
    calm=bool(ns.get('_CALM_FIELD')) and calm_field.ENABLED
    if calm:
        freq=.080+genome.g('wave_freq')*.155
        speed=.95+genome.g('wave_speed')*1.55
        amp=.28+genome.g('wave_amp')*.82
        noise=genome.g('noise');spark=genome.g('spark')
        spread=.62+genome.g('color_spread')*.46+.36*chroma_pulse
        density=genome.g('density')
        cols=max(1,cols);rows=max(1,rows)
        palette=1.05+genome.g('palette')*1.15
        fv=ns.get('flow_vector')
        flow=fv(t) if fv is not None else (1.0,0.0,0.0,t)
        fdx,fdy,flow_a,phi=flow
        tspeed=phi*speed;tslow=t*.92
        spos=t*(.95+noise*.90)
        if math.isfinite(spos):
            fl=math.floor(spos)
            su=spos-fl
            tick=int(fl)&0x3FFFFFFF
            shimmer_blend=su*su*(3.0-2.0*su)
        else:
            tick=0;shimmer_blend=0.0
        cpos=t*.92
        if math.isfinite(cpos):
            cfl=math.floor(cpos)
            cu=cpos-cfl
            cur_tick=int(cfl)&0x3FFFFFFF
            cur_blend=cu*cu*(3.0-2.0*cu)
        else:
            cur_tick=0;cur_blend=0.0
        period_f=13.0+genome.g('ripple')*18.0
        swell_freq=6.283185307179586/period_f
        swell_shift=phi*(3.8+genome.g('wave_speed')*5.2)
        period=0;crest=0
        bands=calm_field.CALM_CHAR_BANDS
        band=bands[genome.choice('palette',len(bands))]
        hue0=genome.g('hue')
        hue_drift=(t*.078+.14*math.sin(t*.045)+chroma_hue)%1.0 if math.isfinite(t) else 0.0
        phase=tspeed*.47;dark_limit=.36-.07*density
        inv_span=1.0/(1.0-dark_limit)
        x3c=.37*fdx-.21*fdy;y3c=.37*fdy+.21*fdx
        spark_limit=1.0-spark*.042;band_last=len(band)-1;saturation=min(1.0,.86+.13*density+.10*chroma_pulse)
        recipe_table=table_for(t+chroma_hue*5.0,hue0)
        return dict(calm=True,freq=freq,amp=amp,noise=noise,spread=spread,density=density,cols=cols,rows=rows,
                    palette=palette,tspeed=tspeed,tslow=tslow,tick=tick,period=period,crest=crest,
                    band=band,hue0=hue0,hue_drift=hue_drift,phase=phase,dark_limit=dark_limit,
                    spark_limit=spark_limit,band_last=band_last,saturation=saturation,fdx=fdx,fdy=fdy,
                    x3c=x3c,y3c=y3c,recipe_table=recipe_table,shimmer_blend=shimmer_blend,
                    swell_freq=swell_freq,swell_shift=swell_shift,inv_span=inv_span,
                    cur_tick=cur_tick,cur_blend=cur_blend,curiosities=calm_field.CALM_CURIOSITIES)
    freq=.07+genome.g('wave_freq')*.42
    speed=.35+genome.g('wave_speed')*2.4
    amp=.25+genome.g('wave_amp')*1.5
    noise=genome.g('noise');spark=genome.g('spark');spread=genome.g('color_spread');density=genome.g('density')
    cols=max(1,cols);rows=max(1,rows)
    palette=1.0+genome.g('palette')*2.0
    fv=ns.get('flow_vector')
    flow=fv(t) if fv is not None else (1.0,0.0,0.0,t)
    fdx,fdy,flow_a,phi=flow
    tspeed=phi*speed;tslow=t*.65
    tick=int(t*(3.0+noise*10.0))
    period=6+int(genome.g('ripple')*22)
    crest=int(phi*(4.0+genome.g('wave_speed')*8.0))%period
    band=ns['CHAR_BANDS'][genome.choice('palette',len(ns['CHAR_BANDS']))]
    hue0=genome.g('hue')
    phase=tspeed*.47;dark_limit=.20*(1.15-density)
    x3c=.37*fdx-.21*fdy;y3c=.37*fdy+.21*fdx
    spark_limit=1.0-spark*.055;band_last=len(band)-1;saturation=.42+.55*density
    recipe_table=table_for(t,hue0)
    return dict(calm=False,freq=freq,amp=amp,noise=noise,spread=spread,density=density,cols=cols,rows=rows,
                palette=palette,tspeed=tspeed,tslow=tslow,tick=tick,period=period,crest=crest,
                band=band,hue0=hue0,hue_drift=0.0,phase=phase,dark_limit=dark_limit,spark_limit=spark_limit,
                band_last=band_last,saturation=saturation,fdx=fdx,fdy=fdy,x3c=x3c,y3c=y3c,
                recipe_table=recipe_table,shimmer_blend=0.0,swell_freq=0.0,swell_shift=0.0,inv_span=1.0,
                cur_tick=0,cur_blend=0.0,curiosities='')

def prepare_cell(ns,genome,t,cols,rows,chroma_hue=0.0,chroma_pulse=0.0):
    s=prepare_state(ns,genome,t,cols,rows,chroma_hue,chroma_pulse)
    calm=s['calm']
    freq=s['freq'];amp=s['amp'];noise=s['noise'];spread=s['spread'];palette=s['palette']
    tspeed=s['tspeed'];tslow=s['tslow'];tick=s['tick'];period=s['period'];crest=s['crest']
    band=s['band'];hue0=s['hue0'];hue_drift=s['hue_drift'];cols=s['cols'];rows=s['rows']
    fdx=s['fdx'];fdy=s['fdy'];x3c=s['x3c'];y3c=s['y3c']
    sparks=ns['SPARKS'];hashmix=ns['hashmix'];hsv=ns['hsv_to_rgb'];clamp=ns['clamp01'];sin=math.sin
    # These terms depend on one axis only. Preserve each original arithmetic
    # expression rather than combine factors (which would change rounding).
    xs=[]
    if calm:
        hue_origin=hue0+hue_drift
        for x in range(cols):
            fraction=x/cols
            xs.append((x*freq*fdx,x*-fdy,x*x3c,x*fdx,
                       .12*sin(fraction*6.283*palette+tslow),
                       hue_origin+fraction*spread*1.48+.10*sin(fraction*10.166407384630519-tslow*.61),
                       (hue_origin+fraction*spread*1.48)%1.0))
        ys=[]
        for y in range(rows):
            yf=y/rows
            ys.append((y*freq*fdy,y*fdx,y*y3c,y*fdy,
                       yf*.44+.08*sin(yf*8.885765876316732+tslow*.47)))
    else:
        for x in range(cols):
            fraction=x/cols
            xs.append((x*freq*fdx,x*-fdy,x*x3c,x*fdx,
                       .16*sin(fraction*6.283*palette+tslow),
                       hue0+fraction*spread*.85,(hue0+fraction*spread)%1.0))
        ys=[]
        for y in range(rows):
            ys.append((y*freq*fdy,y*fdx,y*y3c,y*fdy,(y/rows)*.05))
    phase=s['phase'];dark_limit=s['dark_limit']
    spark_limit=s['spark_limit'];band_last=s['band_last'];saturation=s['saturation']
    table=s['recipe_table']
    if calm:
        shimmer_blend=s['shimmer_blend'];swell_freq=s['swell_freq']
        swell_shift=s['swell_shift'];inv_span=s['inv_span']
        cur_tick=s['cur_tick'];cur_blend=s['cur_blend'];curiosities=s['curiosities']
        tick1=(tick+1)&0x3FFFFFFF
        cur_tick1=(cur_tick+1)&0x3FFFFFFF
        sparks_n=len(sparks)
        cur_n=len(curiosities)
        def cell_calm(x,y):
            xw,xn,x3,xp,palette_wave,hue_base,dark_hue=xs[x]
            yw,yc,y3,yp,hue_y=ys[y]
            w1=sin(xw+yw+tspeed)
            w2=sin((xn+yc)*freq*1.37-tspeed*.83)
            w3=sin((x3+y3)*freq*2.1+phase)
            warp=sin((xw+yw)*.5+w2*amp)
            value=(w1*.46+w2*.34+w3*.22)*(.62+.38*warp)
            value+=palette_wave
            n0=hashmix(x,y,tick)
            n1=hashmix(x,y,tick1)
            n=n0+(n1-n0)*shimmer_blend
            value+=(n-.5)*noise*.18
            sw=.5+.5*sin(((xp+yp)-swell_shift)*swell_freq)
            value+=.11*(sw*sw*sw)
            light=clamp(.5+.5*value)
            if light<dark_limit:
                cn0=hashmix(x,y,cur_tick)
                cn1=hashmix(x,y,cur_tick1)
                a0=(cn0-.875)*8.0*(1.0-cur_blend)
                a1=(cn1-.875)*8.0*cur_blend
                c_raw=a0 if a0>=a1 else a1
                if c_raw>0.0:
                    c_slot=cur_tick if a0>=a1 else cur_tick1
                    c_strength=clamp(c_raw)
                    c_idx=(x*11+y*23+(c_slot&0xFFFF)*5)%cur_n
                    c_char=curiosities[c_idx]
                    c_hue=(dark_hue+.37+.46*w2+.22*w1+hue_y)%1.0
                    c_sat=.84;c_val=.58+.42*c_strength
                    if table is not None:return c_char,recipe_rgb(table,c_hue,c_sat,c_val)
                    return c_char,hsv(c_hue,c_sat,c_val)
                return ' ',hsv(dark_hue,.35,.02)
            reach=clamp((light-dark_limit)*inv_span)
            shaped=reach*(.64+.36*reach)
            index=int(shaped*band_last);char=band[max(0,min(band_last,index))];sparked=False
            if n>spark_limit and reach>.26:
                char=sparks[(x*7+y*13)%sparks_n];sparked=True
            hue=(hue_base+.34*value+.24*warp+.14*shaped+hue_y)%1.0
            if sparked:
                hue=(hue+.41)%1.0
                twinkle=clamp((n-spark_limit)*28.0)
                sat=.72;val=.82+.18*twinkle
                if table is not None:return char,recipe_rgb(table,hue,sat,val)
            else:
                sat=saturation*(1.0-.06*shaped)
                val=.56+.43*(reach*(1.22-.22*reach))
                if table is not None:return char,recipe_rgb(table,hue,sat,val)
            return char,hsv(hue,sat,val)
        return cell_calm
    def cell(x,y):
        xw,xn,x3,xp,palette_wave,hue_base,dark_hue=xs[x]
        yw,yc,y3,yp,hue_y=ys[y]
        w1=sin(xw+yw+tspeed)
        w2=sin((xn+yc)*freq*1.37-tspeed*.83)
        w3=sin((x3+y3)*freq*2.1+phase)
        warp=sin((xw+yw)*.5+w2*amp)
        value=(w1*.46+w2*.34+w3*.22)*(.62+.38*warp)
        value+=palette_wave
        n=hashmix(x,y,tick)
        value+=(n-.5)*noise*.95
        if period>0 and int(xp+yp)%period==crest:value+=.22
        light=clamp(.5+.5*value)
        if light<dark_limit:return ' ',hsv(dark_hue,.35,.02)
        index=int(light*band_last);char=band[max(0,min(band_last,index))];sparked=False
        if n>spark_limit and light>.34:
            char=sparks[int(n*997)%len(sparks)];sparked=True
        hue=(hue_base+.08*value+hue_y)%1.0
        if sparked:hue=(hue*.35+.52)%1.0;sat,val=.22,1.0
        else:
            sat=saturation;val=.12+.88*light
            if table is not None:return char,recipe_rgb(table,hue,sat,val)
        return char,hsv(hue,sat,val)
    return cell

def renderer_class(ns):
    profile=ns.get('_STAGE_METRICS')
    sample=ns['sample_xy']
    class PreparedRenderer(ns['RenderAgent']):
        def _prepare_field(self,cols,rows,t):
            self.prepared_cell=prepare_cell(ns,self.genome,t,cols,rows,getattr(self,'_chroma_hue',0.0),getattr(self,'_chroma_pulse',0.0))
            # sample_xy's axes are independent. A one-cell companion axis
            # keeps it in bounds even when a zoom-out clips the real edge.
            xs=[sample(x,0,self.scale,cols,1) for x in range(cols)]
            ys=[sample(0,y,self.scale,1,rows) for y in range(rows)]
            self.prepared_x=[None if p is None else p[0] for p in xs]
            self.prepared_y=[None if p is None else p[1] for y,p in enumerate(ys)]
        def _frame(self,cols,rows,t):
            if profile is None:self._prepare_field(cols,rows,t)
            else:profile.call('field_prepare',self._prepare_field,cols,rows,t)
            return super()._frame(cols,rows,t)
        def _cell(self,x,y,t,cols,rows,void):
            sx=self.prepared_x[x];sy=self.prepared_y[y]
            return (' ',void) if sx is None or sy is None else self.prepared_cell(sx,sy)
    return PreparedRenderer

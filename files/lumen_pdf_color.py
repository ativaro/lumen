"""PDF colour spaces and tint functions; Qt supplies only colour/profile conversion."""
import itertools
import math
from PySide6.QtGui import QColor, QColorSpace
from lumen_pdf import Name, PDFError, Stream, integer


def values(data,count=None):
    if not isinstance(data,(list,tuple)) or (count is not None and len(data)!=count) or any(type(v) not in (int,float) or not math.isfinite(v) for v in data):
        raise PDFError('Ungültige PDF-Farbwerte.')
    return data


def function(document,reference,inputs,depth=0):
    if depth>32:raise PDFError('PDF-Farbfunktion zu tief.')
    obj=document.resolve(reference)
    if isinstance(obj,list):return [function(document,f,inputs,depth+1)[0] for f in obj]
    attrs=obj.attrs if isinstance(obj,Stream) else obj
    if not isinstance(attrs,dict):raise PDFError('PDF-Farbfunktion fehlt.')
    domain=values(document.resolve(attrs.get('Domain')))
    if len(domain)!=2*len(inputs):raise PDFError('PDF-Farbfunktion hat falsche Eingabezahl.')
    source=[max(domain[2*i],min(domain[2*i+1],v)) for i,v in enumerate(values(inputs))]
    limits=document.resolve(attrs.get('Range'));kind=attrs.get('FunctionType')
    if limits is not None:
        values(limits)
        if len(limits)%2:raise PDFError('Ungültiger PDF-Farbbereich.')
    if kind==2:
        if len(source)!=1:raise PDFError('PDF-Exponentialfunktion erwartet einen Wert.')
        first=values(document.resolve(attrs.get('C0',[0])));last=values(document.resolve(attrs.get('C1',[1])),len(first))
        exponent=values([attrs.get('N')])[0]
        try:factor=math.pow(source[0],exponent)
        except (ValueError,OverflowError) as exc:raise PDFError('Ungültige PDF-Exponentialfunktion.') from exc
        result=[a+factor*(b-a) for a,b in zip(first,last)]
    elif kind==3:
        functions=document.resolve(attrs.get('Functions'));bounds=values(document.resolve(attrs.get('Bounds')));encode=values(document.resolve(attrs.get('Encode')))
        if len(source)!=1 or not isinstance(functions,list) or not functions or len(bounds)!=len(functions)-1 or len(encode)!=2*len(functions):raise PDFError('Ungültige zusammengesetzte PDF-Farbfunktion.')
        edges=[domain[0],*bounds,domain[1]]
        # Equal neighbouring bounds are common and leave an interval without width, which is never chosen for a value inside the domain.
        if any(a>b for a,b in zip(edges,edges[1:])) or edges[0]>=edges[-1]:raise PDFError('Ungültige PDF-Funktionsgrenzen.')
        index=min(sum(source[0]>=b for b in bounds),len(functions)-1);a,b=edges[index:index+2]
        result=function(document,functions[index],[encode[index*2]+((source[0]-a)/(b-a) if b>a else 0)*(encode[index*2+1]-encode[index*2])],depth+1)
    elif kind==0:
        if not isinstance(obj,Stream) or limits is None:raise PDFError('PDF-Abtastfunktion fehlt.')
        sizes=document.resolve(attrs.get('Size'));bits=integer(attrs.get('BitsPerSample'),1,32)
        if not isinstance(sizes,list) or len(sizes)!=len(source) or len(sizes)>8 or attrs.get('Order',1)!=1:raise PDFError('Ungültige PDF-Abtastfunktion.')
        sizes=[integer(s,1,65536) for s in sizes];channels=len(limits)//2
        total=math.prod(sizes)*channels
        if total>8_000_000:raise PDFError('PDF-Funktionsbudget überschritten.')
        raw=document.decode(obj)
        if len(raw)*8<total*bits:raise PDFError('Unvollständige PDF-Funktionswerte.')
        encode=values(document.resolve(attrs.get('Encode',[v for s in sizes for v in (0,s-1)])),2*len(source))
        decode=values(document.resolve(attrs.get('Decode',limits)),2*channels);points=[]
        for i,x in enumerate(source):
            lo,hi=domain[2*i:2*i+2]
            if hi<=lo:raise PDFError('Ungültiger PDF-Funktionseingabebereich.')
            p=max(0,min(sizes[i]-1,encode[2*i]+(x-lo)/(hi-lo)*(encode[2*i+1]-encode[2*i])))
            low=int(p);points.append([(low,1-(p-low)),(min(low+1,sizes[i]-1),p-low)])
        result=[0.0]*channels
        for corner in itertools.product(*points):
            offset=0;stride=1;weight=1
            for (index,factor),size in zip(corner,sizes):offset+=index*stride;stride*=size;weight*=factor
            if weight==0:continue
            for channel in range(channels):
                bit=(offset*channels+channel)*bits;start=bit//8;count=(bit%8+bits+7)//8
                sample=(int.from_bytes(raw[start:start+count],'big')>>(count*8-bit%8-bits))&((1<<bits)-1)
                result[channel]+=weight*(decode[2*channel]+sample/((1<<bits)-1)*(decode[2*channel+1]-decode[2*channel]))
    else:
        from lumen_pdf_calculator import calculate
        if kind!=4 or not isinstance(obj,Stream):raise PDFError('Unbekannte PDF-Farbfunktion.')
        result=calculate(document.decode(obj),source)
    values(result)
    if limits is not None:
        if len(limits)!=2*len(result):raise PDFError('PDF-Farbfunktion hat falsche Ausgabezahl.')
        result=[max(limits[2*i],min(limits[2*i+1],x)) for i,x in enumerate(result)]
    return result


class ColorSpace:
    def __init__(self,document,definition,resources=None,depth=0):
        if depth>16:raise PDFError('PDF-Farbraum zu tief.')
        self.document=document;self.definition=document.resolve(definition);self.profile=None
        self.base=None;self.lookup=None;self.tint=None;self.attrs={}
        if isinstance(self.definition,Name) and resources:
            named=document.resolve(resources.get('ColorSpace',{}))
            alias=named.get(self.definition) if isinstance(named,dict) else None
            if alias is not None:self.definition=document.resolve(alias)
        parts=self.definition if isinstance(self.definition,list) else [self.definition]
        if not parts:raise PDFError('Leerer PDF-Farbraum.')
        self.kind=parts[0];self.components={'DeviceGray':1,'G':1,'DeviceRGB':3,'RGB':3,'DeviceCMYK':4,'CMYK':4,'CalGray':1,'CalRGB':3,'Lab':3}.get(self.kind)
        if self.kind in ('CalGray','CalRGB','Lab'):
            if len(parts)!=2:raise PDFError('Ungültiger kalibrierter PDF-Farbraum.')
            self.attrs=document.resolve(parts[1])
            if not isinstance(self.attrs,dict):raise PDFError('PDF-Farbkalibrierung fehlt.')
            white=values(self.attrs.get('WhitePoint'),3)
            if white[0]<=0 or white[1]!=1 or white[2]<=0:raise PDFError('Ungültiger PDF-Weißpunkt.')
        elif self.kind=='ICCBased':
            if len(parts)!=2:raise PDFError('Ungültiger PDF-ICC-Farbraum.')
            profile=document.resolve(parts[1])
            if not isinstance(profile,Stream):raise PDFError('PDF-ICC-Profil fehlt.')
            self.components=integer(profile.attrs.get('N'),1,4)
            if self.components not in (1,3,4):raise PDFError('Ungültige PDF-ICC-Komponenten.')
            self.profile=QColorSpace.fromIccProfile(document.decode(profile))
            if not self.profile.isValid():raise PDFError('Ungültiges PDF-ICC-Profil.')
            self.attrs=profile.attrs
        elif self.kind in ('Indexed','I'):
            if len(parts)!=4:raise PDFError('Ungültige PDF-Farbpalette.')
            self.components=1;self.high=integer(document.resolve(parts[2]),0,255)
            self.base=ColorSpace(document,parts[1],resources,depth+1);table=document.resolve(parts[3])
            self.lookup=document.decode(table) if isinstance(table,Stream) else table
            if not isinstance(self.lookup,bytes) or len(self.lookup)<(self.high+1)*self.base.components:raise PDFError('Unvollständige PDF-Farbpalette.')
        elif self.kind in ('Separation','DeviceN'):
            if len(parts)<4:raise PDFError('Ungültiger PDF-Sonderfarbraum.')
            names=document.resolve(parts[1]);names=names if isinstance(names,list) else [names]
            if not names or len(names)>32 or any(not isinstance(n,Name) for n in names):raise PDFError('Ungültige PDF-Sonderfarben.')
            self.components=len(names);self.base=ColorSpace(document,parts[2],resources,depth+1);self.tint=parts[3]
        elif self.components is None:raise PDFError('Unbekannter PDF-Farbraum: '+str(self.kind))

    def ranges(self):
        if self.kind in ('Indexed','I'):return [0,self.high]
        if self.kind=='Lab':return [0,100,*values(self.attrs.get('Range',[-100,100,-100,100]),4)]
        return values(self.attrs.get('Range',[0,1]*self.components),2*self.components)

    def rgb(self,samples):
        samples=values(samples,self.components)
        if self.lookup is not None:
            index=max(0,min(self.high,math.floor(samples[0]+.5)));n=self.base.components;limits=self.base.ranges()
            return self.base.rgb([limits[2*i]+self.lookup[index*n+i]/255*(limits[2*i+1]-limits[2*i]) for i in range(n)])
        if self.tint is not None:return self.base.rgb(function(self.document,self.tint,samples))
        if self.kind in ('CalGray','CalRGB','Lab'):
            white=self.attrs['WhitePoint']
            if self.kind=='CalGray':xyz=[w*max(0,min(1,samples[0]))**self.attrs.get('Gamma',1) for w in white]
            elif self.kind=='CalRGB':
                gamma=values(self.attrs.get('Gamma',[1,1,1]),3);matrix=values(self.attrs.get('Matrix',[1,0,0,0,1,0,0,0,1]),9)
                abc=[max(0,min(1,v))**g for v,g in zip(samples,gamma)];xyz=[sum(matrix[i+3*j]*abc[j] for j in range(3)) for i in range(3)]
            else:
                l,a,b=samples;y=(l+16)/116
                def lab(v):return v**3 if v>=6/29 else 108/841*(v-4/29)
                xyz=[white[0]*lab(y+a/500),white[1]*lab(y),white[2]*lab(y-b/200)]
            # Bradford chromatic adaptation from the declared white to D65.
            matrix=((.8951,.2664,-.1614),(-.7502,1.7135,.0367),(.0389,-.0685,1.0296))
            mul=lambda m,v:[sum(a*b for a,b in zip(row,v)) for row in m]
            origin=mul(matrix,white);target=mul(matrix,[.95047,1,1.08883]);cone=mul(matrix,xyz)
            adapted=mul(((.9869929,-.1470543,.1599627),(.4323053,.5183603,.0492912),(-.0085287,.0400428,.9684867)),[v*t/o for v,t,o in zip(cone,target,origin)])
            linear=mul(((3.2404542,-1.5371385,-.4985314),(-.969266,1.8760108,.041556),(.0556434,-.2040259,1.0572252)),adapted)
            return tuple(max(0,min(1,12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055)) for v in linear)
        samples=[max(0,min(1,v)) for v in samples]
        if self.profile:
            source=QColor.fromCmykF(*samples) if len(samples)==4 else QColor.fromRgbF(*(samples*3 if len(samples)==1 else samples))
            result=self.profile.transformationToColorSpace(QColorSpace.NamedColorSpace.SRgb).map(source)
            return result.redF(),result.greenF(),result.blueF()
        if len(samples)==1:return tuple(samples*3)
        if len(samples)==3:return tuple(samples)
        c,m,y,k=samples;return (1-c)*(1-k),(1-m)*(1-k),(1-y)*(1-k)

    def color(self,samples):return QColor.fromRgbF(*self.rgb(samples))

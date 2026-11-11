"""Interpret PDF content in Lumen; Qt only supplies font outlines and painting.

PDF 1.7 chapters 4/5: graphics, text, fonts, images and coordinate systems.
No QtPdf/QPdfWriter, fallback renderer, network resources or document execution.
"""
from copy import copy
import math
import os
import re
import unicodedata
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QColorSpace, QFont, QGuiApplication, QImage, QImageReader, QPainter, QPainterPath, QPen, QPicture, QRawFont, QTransform, QPolygonF
from lumen_pdf import Document, Name, Operator, PDFError, Ref, Stream, Syntax, UnsupportedPDF, integer, pdf_string

_gui = None


def gui():
    from PySide6.QtWidgets import QApplication
    global _gui
    if QGuiApplication.instance() is None:
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        _gui=QApplication(['lumen-pdf'])


def numbers(values,count=None):
    if count is not None and len(values)!=count or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e8 for v in values):
        raise PDFError('Ungültige PDF-Grafikoperanden.')
    return values


def rectangle(value):
    if not isinstance(value,list): raise PDFError('Ungültiges PDF-Rechteck.')
    x0,y0,x1,y1=numbers(value,4)
    if x1<=x0 or y1<=y0: raise PDFError('Leeres PDF-Rechteck.')
    return QRectF(x0,y0,x1-x0,y1-y0)


def color(values,space):
    from lumen_pdf_color import ColorSpace
    if isinstance(space,ColorSpace):return space.color(values)
    numbers(values)
    if any(not 0<=v<=1 for v in values): raise PDFError('PDF-Farbe außerhalb des Bereichs.')
    if space=='DeviceGray' and len(values)==1: return QColor.fromRgbF(values[0],values[0],values[0])
    if space=='DeviceRGB' and len(values)==3: return QColor.fromRgbF(*values)
    if space=='DeviceCMYK' and len(values)==4: return QColor.fromCmykF(*values)
    raise UnsupportedPDF('PDF-Farbraum noch nicht unterstützt: '+str(space))


def unicode_map(document,reference):
    if reference is None: return {}
    stream=document.resolve(reference)
    if not isinstance(stream,Stream): raise UnsupportedPDF('Benannte Unicode-CMaps noch nicht unterstützt.')
    syntax=Syntax(document.decode(stream)); values=[]; result={}; expanded=0
    while True:
        syntax.skip()
        if syntax.pos==len(syntax.data): break
        values.append(syntax.value())
        if len(values)>200000: raise PDFError('PDF-Unicode-CMap zu groß.')
    for index,value in enumerate(values):
        if value=='usecmap': raise UnsupportedPDF('Vererbte PDF-Unicode-CMap noch nicht unterstützt.')
        if value not in ('beginbfchar','beginbfrange'): continue
        count=integer(values[index-1],0,65536); pos=index+1
        for _ in range(count):
            width=2 if value=='beginbfchar' else 3
            operands=values[pos:pos+width]; pos+=width
            if len(operands)!=width or not isinstance(operands[0],bytes): raise PDFError('Ungültige PDF-Unicode-Zuordnung.')
            if value=='beginbfchar': entries=[(operands[0],operands[1])]
            else:
                first,last,destination=operands
                if not isinstance(last,bytes) or len(first)!=len(last) or not 1<=len(first)<=4: raise PDFError('Ungültiger PDF-Unicode-Bereich.')
                a,b=int.from_bytes(first,'big'),int.from_bytes(last,'big')
                if not 0<=b-a<=65536: raise PDFError('PDF-Unicode-Bereich zu groß.')
                if isinstance(destination,list):
                    if len(destination)!=b-a+1: raise PDFError('Unvollständiger PDF-Unicode-Bereich.')
                    entries=((n.to_bytes(len(first),'big'),u) for n,u in zip(range(a,b+1),destination))
                elif isinstance(destination,bytes):
                    if not destination or len(destination)>256 or expanded+(b-a+1)*len(destination)>1024**2: raise PDFError('PDF-Unicode-Expansionsbudget überschritten.')
                    base=int.from_bytes(destination,'big')
                    if base+b-a>=1<<(8*len(destination)): raise PDFError('PDF-Unicode-Bereich läuft über.')
                    entries=((n.to_bytes(len(first),'big'),(base+n-a).to_bytes(len(destination),'big')) for n in range(a,b+1))
                else: raise PDFError('Ungültiges PDF-Unicode-Ziel.')
            for code,text in entries:
                if not 1<=len(code)<=4 or not isinstance(text,bytes) or len(text)%2: raise PDFError('Ungültiges PDF-Unicode-Zeichen.')
                expanded+=len(text)
                if len(text)>256 or expanded>1024**2: raise PDFError('PDF-Unicode-Expansionsbudget überschritten.')
                try: result[code]=text.decode('utf-16-be')
                except UnicodeError as error: raise PDFError('Ungültiges Unicode im PDF.') from error
                if len(result)>65536: raise PDFError('PDF-Unicode-CMap zu groß.')
    return result


def symbol_cmap(table):
    """Character codes of a symbolic TrueType font: its (3,0) or (1,0) cmap, formats 0, 4 and 6."""
    import struct
    try:
        count=struct.unpack_from('>H',table,2)[0];found={}
        for index in range(min(count,32)):
            platform,encoding,offset=struct.unpack_from('>HHI',table,4+index*8)
            if (platform,encoding) in ((3,0),(1,0)):found[platform]=offset
        if not found:return None
        platform=3 if 3 in found else 1;offset=found[platform];kind=struct.unpack_from('>H',table,offset)[0];codes={}
        if kind==0:
            codes={code:gid for code,gid in enumerate(table[offset+6:offset+262]) if gid}
        elif kind==6:
            first,number=struct.unpack_from('>HH',table,offset+6)
            for index,gid in enumerate(struct.unpack_from('>%dH'%min(number,65536),table,offset+10)):
                if gid:codes[first+index]=gid
        elif kind==4:
            segments=struct.unpack_from('>H',table,offset+6)[0]//2;base=offset+14
            ends=struct.unpack_from('>%dH'%segments,table,base);starts=struct.unpack_from('>%dH'%segments,table,base+2+segments*2)
            deltas=struct.unpack_from('>%dH'%segments,table,base+2+segments*4);ranges=base+2+segments*6
            for index in range(segments):
                if starts[index]>ends[index] or ends[index]-starts[index]>65535 or len(codes)>65536:continue
                shift=struct.unpack_from('>H',table,ranges+index*2)[0]
                for code in range(starts[index],ends[index]+1):
                    if code==0xFFFF:continue
                    gid=code if not shift else struct.unpack_from('>H',table,ranges+index*2+shift+(code-starts[index])*2)[0]
                    if gid or not shift:gid=(gid+deltas[index])&0xFFFF
                    if gid:codes[code]=gid
        else:return None
        return platform,codes
    except (struct.error,IndexError):return None


class Font:
    def __init__(self,document,resource):
        self.document=document; self.attrs=document.resolve(resource)
        if not isinstance(self.attrs,dict): raise PDFError('PDF-Schrift fehlt.')
        subtype=self.attrs.get('Subtype'); self.composite=subtype=='Type0'; self.widths={}; self.differences={}; self.symbols=None
        if subtype not in ('Type0','Type1','TrueType'): raise UnsupportedPDF('PDF-Schrifttyp noch nicht unterstützt: '+str(subtype))
        self.mapping=unicode_map(document,self.attrs.get('ToUnicode'))
        self.base=str(self.attrs.get('BaseFont','')); self.bold='bold' in self.base.lower(); self.italic=any(s in self.base.lower() for s in ('italic','oblique'))
        attrs=self.attrs
        if self.composite:
            if attrs.get('Encoding')!='Identity-H': raise UnsupportedPDF('PDF-CID-Schrift benötigt derzeit Identity-H.')
            descendants=document.resolve(attrs.get('DescendantFonts'))
            if not isinstance(descendants,list) or len(descendants)!=1: raise PDFError('Ungültige PDF-CID-Schrift.')
            attrs=document.resolve(descendants[0]); self.default_width=attrs.get('DW',1000)
            entries=document.resolve(attrs.get('W',[])); pos=0
            while pos<len(entries):
                start=integer(entries[pos],0,65535); pos+=1; widths=document.resolve(entries[pos]); pos+=1
                if isinstance(widths,list):
                    numbers(widths)
                    if start+len(widths)>65536: raise PDFError('PDF-Schriftbreiten außerhalb des Bereichs.')
                    self.widths.update({start+i:v for i,v in enumerate(widths)})
                else:
                    end=integer(widths,start,65535); width=entries[pos]; pos+=1; numbers([width])
                    self.widths.update({i:width for i in range(start,end+1)})
            self.gidmap=document.resolve(attrs.get('CIDToGIDMap',Name('Identity')))
            if isinstance(self.gidmap,Stream): self.gidmap=document.decode(self.gidmap)
            elif self.gidmap!='Identity': raise UnsupportedPDF('PDF-CID-Zuordnung noch nicht unterstützt.')
        else:
            self.default_width=None
            entries=document.resolve(attrs.get('Widths',[])); first=attrs.get('FirstChar',0)
            if not isinstance(entries,list): raise PDFError('Ungültige PDF-Schriftbreiten.')
            numbers(entries); integer(first,0,255)
            if first+len(entries)>256: raise PDFError('PDF-Schriftbreiten außerhalb des Bereichs.')
            self.widths={first+i:width for i,width in enumerate(entries)}
        descriptor=document.resolve(attrs.get('FontDescriptor',{}))
        if not isinstance(descriptor,dict): raise PDFError('Ungültiger PDF-Schriftdeskriptor.')
        fontfile=descriptor.get('FontFile2') or descriptor.get('FontFile3') or descriptor.get('FontFile')
        self.embedded=bool(fontfile)
        if fontfile:
            stream=document.resolve(fontfile)
            if not isinstance(stream,Stream): raise PDFError('PDF-Schriftdatei fehlt.')
            self.raw=QRawFont(QByteArray(document.decode(stream)),1000,QFont.HintingPreference.PreferNoHinting)
            if not self.raw.isValid(): raise UnsupportedPDF('Eingebettetes PDF-Schriftformat wird noch nicht unterstützt.')
            # A symbolic TrueType font without an encoding selects glyphs through its own cmap, not by character name.
            self.symbols=symbol_cmap(bytes(self.raw.fontTable('cmap'))) if subtype=='TrueType' and 'Encoding' not in self.attrs and not self.composite else None
        else:
            base=self.base.split('+')[-1]
            if self.composite:raise UnsupportedPDF('Nicht eingebettete PDF-CID-Schrift noch nicht verfügbar: '+base)
            # A font the file does not carry is replaced by the metric-compatible Liberation family of the same
            # kind; the widths still come from the PDF, so the layout stays where the author put it.
            flags=descriptor.get('Flags',0) if type(descriptor.get('Flags',0)) is int else 0;name=base.lower()
            family=('Liberation Mono' if flags&1 or any(part in name for part in ('courier','mono','consol')) else
                    'Liberation Serif' if flags&2 or any(part in name for part in ('times','serif','georgia','garamond','cambria','palatino')) and 'sans' not in name else 'Liberation Sans')
            font=QFont(family); font.setPixelSize(1000); font.setBold(self.bold); font.setItalic(self.italic)
            self.raw=QRawFont.fromFont(font)
            if not self.raw.isValid(): raise PDFError('Systemschrift für PDF fehlt.')
        self.ascent=descriptor.get('Ascent',self.raw.ascent()); self.descent=descriptor.get('Descent',-self.raw.descent())
        numbers([self.ascent,self.descent]); self.code_width=2 if self.composite else 1
        self.encoding=document.resolve(self.attrs.get('Encoding',Name('StandardEncoding')))
        if isinstance(self.encoding,dict):
            diffs=document.resolve(self.encoding.get('Differences',[])); cursor=0
            if not isinstance(diffs,list): raise PDFError('Ungültige PDF-Schriftkodierung.')
            for value in diffs:
                if type(value) is int: cursor=integer(value,0,255)
                elif isinstance(value,Name): self.differences[integer(cursor,0,255)]=str(value); cursor+=1
                else: raise PDFError('Ungültige PDF-Zeichenkodierung.')
            self.encoding=self.encoding.get('BaseEncoding',Name('StandardEncoding'))
        if not self.composite and self.encoding not in ('WinAnsiEncoding','MacRomanEncoding','StandardEncoding'):
            raise UnsupportedPDF('PDF-Schriftkodierung noch nicht unterstützt: '+str(self.encoding))
        self.glyph_names={}; self.name_text={}
        if self.differences:
            if not hasattr(self.raw,'glyphCount'): raise UnsupportedPDF('PDF-Schriftkodierung benötigt Qt 6.11.')
            for gid in range(min(self.raw.glyphCount(),65536)): self.glyph_names[self.raw.glyphName(gid)]=gid
            for cp in range(32,65536):
                if 0xD800<=cp<=0xDFFF: continue
                glyphs=self.raw.glyphIndexesForString(chr(cp))
                if glyphs and glyphs[0]: self.name_text.setdefault(self.raw.glyphName(glyphs[0]),chr(cp))

    def glyphs(self,data):
        if not isinstance(data,bytes) or len(data)%self.code_width: raise PDFError('Ungültige PDF-Textzeichenfolge.')
        for pos in range(0,len(data),self.code_width):
            code=data[pos:pos+self.code_width]; cid=int.from_bytes(code,'big'); text=self.mapping.get(code)
            if self.composite:
                if text is None: raise UnsupportedPDF('PDF-CID-Schrift ohne vollständige Unicode-Zuordnung.')
                gid=cid if self.gidmap=='Identity' else int.from_bytes(self.gidmap[cid*2:cid*2+2],'big')
            elif cid in self.differences:
                name=self.differences[cid]; gid=self.glyph_names.get(name)
                if text is None:
                    text=self.name_text.get(name)
                    if text is None and re.fullmatch(r'uni(?:[0-9A-Fa-f]{4})+',name): text=bytes.fromhex(name[3:]).decode('utf-16-be')
                    if text is None and re.fullmatch(r'u[0-9A-Fa-f]{4,6}',name): text=chr(int(name[1:],16))
                if text is None or gid is None: raise UnsupportedPDF('PDF-Zeichenname noch nicht unterstützt: '+name)
            elif self.symbols and (symbol:=next((self.symbols[1][c] for c in ((cid,0xF000+cid,0xF100+cid,0xF200+cid) if self.symbols[0]==3 else (cid,)) if c in self.symbols[1]),0)):
                gid=symbol
                if text is None:
                    if not 32<=cid<=126:raise UnsupportedPDF('PDF-Symbolschrift ohne Unicode-Zuordnung.')
                    text=chr(cid)
            else:
                if self.encoding=='StandardEncoding':
                    if not 32<=cid<=126: raise UnsupportedPDF('Erweiterte PDF-StandardEncoding noch nicht unterstützt.')
                    visible=chr(cid)
                    if cid==39: visible='’'
                    if cid==96: visible='‘'
                else:
                    try: visible=code.decode('cp1252' if self.encoding=='WinAnsiEncoding' else 'mac_roman')
                    except UnicodeError as error: raise PDFError('Nicht zugeordnetes PDF-Zeichen.') from error
                glyphs=self.raw.glyphIndexesForString(visible); gid=glyphs[0] if glyphs else 0
                if text is None: text=visible
            if not gid and text.strip(): raise UnsupportedPDF('PDF-Zeichen fehlt in der ausgewählten Schrift.')
            width=self.widths.get(cid,self.default_width)
            if width is None: width=self.raw.advancesForGlyphIndexes([gid])[0].x()
            numbers([width]); yield cid,gid,text,width


class Page:
    def __init__(self,document,index,rotation=0):
        gui(); self.document=document; integer(index,0,len(document)-1); self.index=index; self.attrs=dict(document.pages[index])
        if type(rotation) is not int or rotation not in (0,90,180,270):raise PDFError('Ungültige PDF-Drehung.')
        self.attrs['Rotate']=(self.attrs.get('Rotate') or 0)+rotation
        self.hidden=0;self.hidden_layers=self._layers()
        from lumen_pdf_transparency import group
        self.page_group=group(document,self.attrs.get('Group')) or {}
        unit=self.document.resolve(self.attrs.get('UserUnit',1));numbers([unit])
        if not 0<unit<=75000:raise PDFError('Ungültige PDF-Seiteneinheit.')
        media=rectangle(self.attrs['MediaBox']); crop=rectangle(self.attrs.get('CropBox') or self.attrs['MediaBox']); self.box=media.intersected(crop)
        if self.box.isEmpty(): raise PDFError('Leerer PDF-Seitenausschnitt.')
        self.rotation=self.attrs.get('Rotate') or 0
        if type(self.rotation) is not int or self.rotation%90: raise PDFError('Ungültige PDF-Seitendrehung.')
        self.rotation%=360; w,h=self.box.width(),self.box.height(); x,y=self.box.x(),self.box.y()
        transforms={0:QTransform(1,0,0,-1,-x,y+h),90:QTransform(0,1,1,0,-y,-x),180:QTransform(-1,0,0,1,x+w,-y),270:QTransform(0,-1,-1,0,y+h,x+w)}
        self.transform=transforms[self.rotation]*QTransform.fromScale(unit,unit)
        self.width,self.height=(h*unit,w*unit) if self.rotation%180 else (w*unit,h*unit)
        self.fonts={}; self.spans=[]; self.characters=[]; self.operations=0; self.image_count=0; self.image_pixels=0; self.character_units=0
        self.collect=True;self.effects=False;self.effect_pixels=0;self.effect_depth=0;self.tiles={}
        self.picture=QPicture(); painter=QPainter(self.picture)
        try:
            self._draw(painter)
        finally: painter.end()
        self.words=self._words()

    def _layers(self):
        """Layer groups that the document's default configuration switches off."""
        resolve=self.document.resolve;properties=resolve(self.document.catalog.get('OCProperties'))
        if properties is None:return []
        config=resolve(properties.get('D',{})) if isinstance(properties,dict) else None
        groups=resolve(properties.get('OCGs',[])) if isinstance(properties,dict) else None
        if not isinstance(config,dict) or not isinstance(groups,list) or len(groups)>10000:raise PDFError('Ungültige PDF-Ebenen.')
        def listed(key):
            entries=resolve(config.get(key,[])) or []
            if not isinstance(entries,list) or len(entries)>10000:raise PDFError('Ungültige PDF-Ebenen.')
            return [resolve(entry) for entry in entries]
        off=listed('OFF')
        if config.get('BaseState')=='OFF':
            on=listed('ON');off=[group for group in map(resolve,groups) if not any(group is shown for shown in on)]
        return [group for group in off if isinstance(group,dict)]

    def _visible(self,reference):
        """Whether content tagged with this layer group or membership dictionary is shown."""
        resolve=self.document.resolve;value=resolve(reference)
        if value is None:return True
        if not isinstance(value,dict):raise PDFError('Ungültige PDF-Ebenenzuordnung.')
        if value.get('Type')!='OCMD':return not any(value is group for group in self.hidden_layers)
        if 'VE' in value:raise UnsupportedPDF('PDF-Ebenenausdruck noch nicht unterstützt.')
        members=resolve(value.get('OCGs',[]));members=members if isinstance(members,list) else [members]
        states=[not any(resolve(member) is group for group in self.hidden_layers) for member in members[:10000] if resolve(member) is not None]
        if not states:return True
        return {'AllOn':all(states),'AnyOff':not all(states),'AllOff':not any(states)}.get(str(value.get('P','AnyOn')),any(states))

    def _draw(self,painter):
        self.hidden=0
        painter.setClipRect(QRectF(0,0,self.width,self.height));painter.setTransform(self.transform,True)
        painter.save()
        try:self._interpret(self.document.contents(self.index),self.document.resolve(self.attrs.get('Resources')) or {},painter,set())
        finally:painter.restore()
        self._annotations(painter)

    def _annotations(self,painter):
        annotations=self.document.resolve(self.attrs.get('Annots',[]))
        if not isinstance(annotations,list) or len(annotations)>10000:raise PDFError('Ungültige PDF-Anmerkungsliste.')
        for reference in annotations:
            annotation=self.document.resolve(reference)
            if not isinstance(annotation,dict):raise PDFError('Ungültige PDF-Anmerkung.')
            if annotation.get('F',0)&(1|2|32) or not self._visible(annotation.get('OC')):continue
            rect=rectangle(self.document.resolve(annotation.get('Rect')));appearance=self.document.resolve(annotation.get('AP',{}));appearance=self.document.resolve(appearance.get('N')) if isinstance(appearance,dict) else None
            if isinstance(appearance,dict):appearance=self.document.resolve(appearance.get(annotation.get('AS')))
            if isinstance(appearance,Stream):
                matrix=QTransform(*numbers(appearance.attrs.get('Matrix',[1,0,0,1,0,0]),6));bbox=matrix.mapRect(rectangle(appearance.attrs.get('BBox')))
                if bbox.isEmpty():raise PDFError('Leere PDF-Anmerkungsdarstellung.')
                transform=QTransform(rect.width()/bbox.width(),0,0,rect.height()/bbox.height(),rect.x()-bbox.x()*rect.width()/bbox.width(),rect.y()-bbox.y()*rect.height()/bbox.height())
                count_chars=len(self.characters);count_spans=len(self.spans);painter.save();painter.setClipRect(rect,Qt.ClipOperation.IntersectClip)
                try:
                    painter.setTransform(transform,True);self._form(appearance,{},painter,set(),0,None)
                finally:painter.restore()
                del self.characters[count_chars:];del self.spans[count_spans:]
                continue
            kind=annotation.get('Subtype');components=annotation.get('C',[0,0,0] if kind=='Link' else [1,1,0]);shade=color(components,{1:'DeviceGray',3:'DeviceRGB',4:'DeviceCMYK'}.get(len(components)))
            if kind=='Link':
                border=annotation.get('Border',[0,0,1]);settings=self.document.resolve(annotation.get('BS',{}));width=settings.get('W',border[2] if len(border)>=3 else 1)
                numbers([width]);painter.setPen(QPen(shade,width));painter.setBrush(Qt.BrushStyle.NoBrush)
                if width>0:painter.drawRect(rect)
            elif kind=='Text':painter.fillRect(rect,shade)
            elif kind=='Highlight':
                points=annotation.get('QuadPoints',[]);numbers(points)
                if len(points)%8:raise PDFError('Ungültige PDF-Markierung.')
                shade.setAlphaF(.35)
                for start in range(0,len(points),8):
                    q=points[start:start+8];painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(shade);painter.drawPolygon(QPolygonF([QPointF(q[i],q[i+1]) for i in (0,2,6,4)]))
            else:raise UnsupportedPDF('PDF-Anmerkungsdarstellung fehlt: '+str(kind))

    def _resource(self,resources,category,name):
        dictionary=self.document.resolve(resources.get(category,{}))
        if not isinstance(dictionary,dict) or name not in dictionary: raise PDFError('PDF-Ressource fehlt: '+str(name))
        return self.document.resolve(dictionary[name])

    def _font(self,resources,name):
        resource=self._resource(resources,'Font',name); key=id(resource)
        if key not in self.fonts:
            if len(self.fonts)>=64: raise PDFError('Zu viele PDF-Schriften auf einer Seite.')
            self.fonts[key]=Font(self.document,resource)
        return self.fonts[key]

    def _form(self,obj,resources,painter,forms,depth,state,mask_group=False):
        from lumen_pdf_transparency import group,paint
        if id(obj) in forms:raise PDFError('Zyklische PDF-Form.')
        box=numbers(self.document.resolve(obj.attrs.get('BBox')),4) if isinstance(self.document.resolve(obj.attrs.get('BBox')),list) else None
        if box and (box[0]==box[2] or box[1]==box[3]):return  # a form without area shows nothing
        settings=group(self.document,obj.attrs.get('Group'))
        # With normal blending inside, a group gives the same result isolated or not; such a group is
        # composited on its own surface, and a blend mode inside it, which would need the backdrop, is refused.
        flat=bool(settings and not mask_group and state is not None and not settings.get('I',False)
                  and (state['fillalpha']!=1 or state['blend'] not in ('Normal','Compatible') or state['mask']))
        def draw(output):
            output.save()
            try:
                output.setTransform(QTransform(*numbers(obj.attrs.get('Matrix',[1,0,0,1,0,0]),6)),True)
                # The two corners of a form's box may come in either order.
                output.setClipRect(QRectF(QPointF(box[0],box[1]),QPointF(box[2],box[3])).normalized() if box else rectangle(obj.attrs.get('BBox')),Qt.ClipOperation.IntersectClip)
                inherited=copy(state) if state is not None else None
                if settings and inherited is not None:
                    inherited.update(fillalpha=1,strokealpha=1,blend=Name('Normal'),mask=None,knockout=None,flat=flat)
                    if settings.get('K'):
                        # A group that was not given its own surface starts from what is already on the page.
                        device=output.device();backdrop=None
                        if not self.collect and not settings.get('I') and state.get('knockout') is None and isinstance(device,QImage):
                            self.effect_pixels+=device.width()*device.height()
                            if self.effect_pixels>160_000_000:raise PDFError('PDF-Transparenzbudget überschritten.')
                            backdrop=device.copy()
                        inherited['knockout']=dict(backdrop=backdrop)
                if settings and inherited is not None and (settings.get('I') or mask_group):inherited['blendspace']=settings.get('CS',inherited['blendspace'])
                self._interpret(self.document.decode(obj),self.document.resolve(obj.attrs.get('Resources',resources)),output,forms|{id(obj)},depth+1,inherited)
            finally:output.restore()
        if settings and (settings.get('I') or flat or state is not None and state.get('knockout') is not None) and not mask_group and state is not None:paint(self,painter,state,'fill',draw,isolated=True)
        else:draw(painter)

    def _interpret(self,data,resources,painter,forms,depth=0,initial_state=None):
        from lumen_pdf_transparency import paint,BLENDS
        if depth>32: raise PDFError('PDF-Formen zu tief verschachtelt.')
        syntax=Syntax(data); operands=[]; stack=[]; marks=[]; path=QPainterPath(); clipping=None; text=False; matrix=QTransform(); line=QTransform()
        state=dict(fill=QColor('black'),stroke=QColor('black'),width=1,cap=0,join=0,miter=10,dash=[],phase=0,fillspace='DeviceGray',strokespace='DeviceGray',font=None,size=0,charspace=0,wordspace=0,scale=1,leading=0,rise=0,mode=0,fillalpha=1,strokealpha=1,blend=Name('Normal'),mask=None,fillpattern=None,strokepattern=None)
        state['blendspace']=self.page_group.get('CS',Name('DeviceRGB'))
        if initial_state is not None: state=copy(initial_state)
        default_transform=QTransform(painter.transform())
        def converted(result):
            if state['blendspace']=='DeviceGray':
                from lumen_pdf_transparency import gray_color
                gradient=result.gradient()
                if gradient:
                    gradient.setStops([(t,gray_color(c)) for t,c in gradient.stops()]);result=QBrush(gradient)
                else:result=QBrush(gray_color(result.color()))
            return result
        def tile(pattern,output):
            # One cell of a coloured tiling pattern, drawn once at the output resolution and repeated as a texture.
            stream,base=pattern;attrs=stream.attrs
            transform=QTransform(*numbers(attrs.get('Matrix',[1,0,0,1,0,0]),6))*base
            box=rectangle(attrs.get('BBox'));xstep,ystep=(abs(v) for v in numbers([attrs.get('XStep'),attrs.get('YStep')],2))
            current,ok=output.transform().inverted()
            if not ok or not xstep or not ystep:raise PDFError('Ungültiges PDF-Kachelmuster.')
            w=math.ceil(xstep*math.hypot(transform.m11(),transform.m12()));h=math.ceil(ystep*math.hypot(transform.m21(),transform.m22()))
            if not 1<=w<=4096 or not 1<=h<=4096:raise UnsupportedPDF('PDF-Kachelmuster in dieser Größe noch nicht unterstützt.')
            key=(id(stream),w,h);cell=self.tiles.get(key)
            if cell is None:
                self.effect_pixels+=w*h
                if self.effect_pixels>160_000_000 or len(self.tiles)>=64:raise PDFError('PDF-Transparenzbudget überschritten.')
                cell=QImage(w,h,QImage.Format.Format_ARGB32_Premultiplied);cell.fill(Qt.GlobalColor.transparent)
                inner=QPainter(cell);collect=self.collect;self.collect=False
                try:
                    inner.setRenderHints(output.renderHints());inner.scale(w/xstep,h/ystep);inner.translate(-box.x(),-box.y())
                    inner.setClipRect(box)
                    self._interpret(self.document.decode(stream),self.document.resolve(attrs.get('Resources',resources)),inner,forms|{id(stream)},depth+1)
                finally:self.collect=collect;inner.end()
                self.tiles[key]=cell
            result=QBrush(cell)
            result.setTransform(QTransform(xstep/w,0,0,ystep/h,box.x(),box.y())*transform*current)
            return result
        def brush(slot,output,background=False):
            pattern=state[slot+'pattern']
            if pattern is None:return None if background else converted(QBrush(state[slot]))
            from lumen_pdf_shading import brush as shading_brush
            if isinstance(pattern[0],Stream):return None if background else tile(pattern,output)
            attrs,base=pattern;transform=QTransform(*numbers(attrs.get('Matrix',[1,0,0,1,0,0]),6))*base
            shade=self.document.resolve(attrs.get('Shading'))
            if background and (not isinstance(shade,dict) or 'Background' not in shade):return None
            inverse,ok=transform.inverted()
            if not ok:raise PDFError('Ungültige PDF-Mustermatrix.')
            bounds=inverse.mapRect(output.transform().mapRect(output.clipBoundingRect()))
            result,clip=shading_brush(self.document,attrs.get('Shading'),resources,bounds)
            current,ok=output.transform().inverted()
            if not ok:raise PDFError('Ungültige PDF-Grafikmatrix.')
            relative=transform*current
            if background:
                from lumen_pdf_color import ColorSpace
                result=QBrush(ColorSpace(self.document,shade.get('ColorSpace'),resources).color(self.document.resolve(shade['Background'])))
                extent=QPainterPath();extent.addRect(bounds);clip=extent.subtracted(clip)
            result=converted(result);result.setTransform(relative);output.setClipPath(relative.map(clip),Qt.ClipOperation.IntersectClip)
            return result
        def pen(output,background=False):
            shade=brush('stroke',output,background)
            if shade is None:return None
            result=QPen(shade,state['width']); result.setCapStyle((Qt.PenCapStyle.FlatCap,Qt.PenCapStyle.RoundCap,Qt.PenCapStyle.SquareCap)[state['cap']]); result.setJoinStyle((Qt.PenJoinStyle.MiterJoin,Qt.PenJoinStyle.RoundJoin,Qt.PenJoinStyle.BevelJoin)[state['join']]); result.setMiterLimit(state['miter'])
            if state['dash']:
                width=state['width'] or 1; result.setDashPattern([v/width for v in state['dash']]); result.setDashOffset(state['phase']/width)
            return result
        def draw_path(output,outline,slot):
            for background in (True,False):
                output.save()
                try:
                    shade=brush(slot,output,background) if slot=='fill' else pen(output,background)
                    if shade is not None:
                        if slot=='fill':output.fillPath(outline,shade)
                        else:output.setPen(shade);output.setBrush(Qt.BrushStyle.NoBrush);output.drawPath(outline)
                finally:output.restore()
        def stroke(outline):
            def draw(output):
                if state.get('adjust'):output.setRenderHint(QPainter.RenderHint.Antialiasing,False)
                draw_path(output,outline,'stroke')
            paint(self,painter,state,'stroke',draw)
        def fill(outline):
            paint(self,painter,state,'fill',lambda output:draw_path(output,outline,'fill'))
        def fill_stroke(outline):
            if state['fillalpha']==state['strokealpha']==1 and not state['mask'] and state['blend'] in ('Normal','Compatible'):
                fill(outline);stroke(outline);return
            # PDF fill-and-stroke is one implicit knockout group: the stroke
            # replaces the fill underneath, then the whole object is composited.
            def draw(output):
                output.save()
                try:output.setOpacity(state['fillalpha']);draw_path(output,outline,'fill')
                finally:output.restore()
                output.setOpacity(state['strokealpha']);output.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                draw_path(output,outline,'stroke')
            paint(self,painter,dict(state,fillalpha=1),'fill',draw,isolated=True)
        def show(data):
            nonlocal matrix
            if not text or state['font'] is None or state['size']<=0: raise PDFError('PDF-Text ohne Schrift oder Textobjekt.')
            font=state['font']; size=state['size']; start=len(self.characters)
            to_normal=self.transform.inverted()[0]*QTransform(1,0,0,-1,-self.box.x(),self.box.bottom())
            baseline=matrix*painter.transform()*to_normal
            angle=round(math.degrees(math.atan2(baseline.m12()*state['scale'],baseline.m11()*state['scale'])),6)
            straight=QTransform().rotate(-angle)
            to_layout=self.transform.inverted()[0]*QTransform(1,0,0,-1,0,self.attrs['MediaBox'][3])*straight
            layout_bbox=None
            for cid,gid,letter,width in font.glyphs(data):
                advance=(width/1000*size+state['charspace']+(state['wordspace'] if cid==32 and not font.composite else 0))*state['scale']
                text_transform=QTransform(size/1000*state['scale'],0,0,-size/1000,0,state['rise'])*matrix
                glyph_transform=text_transform*painter.transform()
                outline=text_transform.map(font.raw.pathForGlyph(gid))
                if state['mode']==2:fill_stroke(outline)
                elif state['mode']==0:fill(outline)
                elif state['mode']==1:stroke(outline)
                rect=QRectF(0,-font.ascent,max(width,1),font.ascent-font.descent)
                bounds=glyph_transform.mapRect(rect)
                layout_rect=(glyph_transform*to_layout).mapRect(rect)
                layout_bbox=layout_rect if layout_bbox is None else layout_bbox.united(layout_rect)
                if self.collect and not self.hidden:self.characters.append((bounds,letter,state['mode'],angle,(glyph_transform*to_normal*straight).mapRect(rect)))
                self.character_units+=len(letter)
                if self.character_units>500000: raise PDFError('Zu viele PDF-Textzeichen auf einer Seite.')
                matrix=QTransform(1,0,0,1,advance,0)*matrix
            chars=self.characters[start:]
            if chars:
                bbox=QRectF(chars[0][0])
                for char in chars[1:]: bbox=bbox.united(char[0])
                self.spans.append(dict(text=''.join(c[1] for c in chars),bbox=[bbox.left(),bbox.top(),bbox.right(),bbox.bottom()],layout_bbox=[layout_bbox.left(),layout_bbox.top(),layout_bbox.right(),layout_bbox.bottom()],size=size*math.hypot(baseline.m21(),baseline.m22()),color=state['fill'].rgb()&0xffffff,bold=font.bold,italic=font.italic,mode=state['mode'],angle=angle))
        while True:
            syntax.skip()
            if syntax.pos==len(data): break
            value=syntax.value()
            if not isinstance(value,Operator):
                operands.append(value)
                if len(operands)>100000: raise PDFError('Zu viele PDF-Operanden.')
                continue
            op=str(value); a=operands; operands=[]; self.operations+=1
            if self.operations>1000000: raise PDFError('PDF-Grafikbudget überschritten.')
            if op=='q':
                numbers(a,0); stack.append(copy(state)); painter.save()
                if len(stack)>64: raise PDFError('PDF-Grafikstack zu tief.')
            elif op=='Q':
                if path.elementCount(): raise UnsupportedPDF('PDF-Grafikzustandswechsel innerhalb eines offenen Pfads noch nicht unterstützt.')
                numbers(a,0)
                if not stack: raise PDFError('PDF-Grafikstack ist leer.')
                state=stack.pop(); painter.restore()
            elif op=='cm':
                if path.elementCount(): raise UnsupportedPDF('PDF-Koordinatenwechsel innerhalb eines offenen Pfads noch nicht unterstützt.')
                painter.setTransform(QTransform(*numbers(a,6)),True)
            elif op in ('m','l'):
                x,y=numbers(a,2)
                if op=='m': path.moveTo(x,y)
                else: path.lineTo(x,y)
            elif op=='c': path.cubicTo(*numbers(a,6))
            elif op=='v':
                x2,y2,x3,y3=numbers(a,4); current=path.currentPosition(); path.cubicTo(current,QPointF(x2,y2),QPointF(x3,y3))
            elif op=='y':
                x1,y1,x3,y3=numbers(a,4); path.cubicTo(x1,y1,x3,y3,x3,y3)
            elif op=='h': numbers(a,0); path.closeSubpath()
            elif op=='re':
                x,y,w,h=numbers(a,4); path.moveTo(x,y); path.lineTo(x+w,y); path.lineTo(x+w,y+h); path.lineTo(x,y+h); path.closeSubpath()
            elif op in ('W','W*'): numbers(a,0); clipping=Qt.FillRule.OddEvenFill if op=='W*' else Qt.FillRule.WindingFill
            elif op in ('n','S','s','f','F','f*','B','B*','b','b*'):
                numbers(a,0)
                if op in ('s','b','b*'): path.closeSubpath()
                path.setFillRule(Qt.FillRule.OddEvenFill if '*' in op else Qt.FillRule.WindingFill)
                if op in ('B','B*','b','b*'):fill_stroke(path)
                elif op in ('S','s'):stroke(path)
                elif op!='n':fill(path)
                if clipping is not None: path.setFillRule(clipping); painter.setClipPath(path,Qt.ClipOperation.IntersectClip); clipping=None
                path=QPainterPath()
            elif op in ('w','M'):
                value=numbers(a,1)[0]
                if value<0: raise PDFError('Negative PDF-Linienbreite.')
                state['width' if op=='w' else 'miter']=value
            elif op in ('J','j'): state['cap' if op=='J' else 'join']=integer(a[0],0,2) if len(a)==1 else integer(None)
            elif op=='d':
                if len(a)!=2 or not isinstance(a[0],list): raise PDFError('Ungültiges PDF-Strichmuster.')
                numbers(a[0]); numbers(a[1:]); dash=a[0]
                if len(dash)>64 or any(v<0 for v in dash) or dash and not any(dash): raise PDFError('Ungültiges PDF-Strichmuster.')
                state.update(dash=dash*2 if len(dash)%2 else dash,phase=a[1])
            elif op in ('g','rg','k','G','RG','K'):
                space={'g':'DeviceGray','rg':'DeviceRGB','k':'DeviceCMYK'}[op.lower()]; slot='fill' if op.islower() else 'stroke'; state[slot]=color(a,space); state[slot+'space']=space;state[slot+'pattern']=None
            elif op in ('cs','CS'):
                if len(a)!=1 or not isinstance(a[0],Name):raise PDFError('Ungültiger PDF-Farbraum.')
                if a[0]=='Pattern':
                    slot='fill' if op=='cs' else 'stroke';state[slot+'space']='Pattern';state[slot+'pattern']=None;continue
                space=a[0] if a[0] in ('DeviceGray','DeviceRGB','DeviceCMYK') else self._resource(resources,'ColorSpace',a[0])
                from lumen_pdf_color import ColorSpace
                space=ColorSpace(self.document,space,resources);slot='fill' if op=='cs' else 'stroke'
                state[slot+'space']=space
                state[slot+'pattern']=None
                initial=[0]*space.components
                if space.kind in ('DeviceCMYK','CMYK'):initial[-1]=1
                if space.tint is not None:initial=[1]*space.components
                state[slot]=space.color(initial)
            elif op in ('sc','SC','scn','SCN'):
                slot='fill' if op.islower() else 'stroke'
                if state[slot+'space']=='Pattern':
                    if len(a)!=1 or not isinstance(a[0],Name):raise PDFError('Ungültige PDF-Musterfarbe.')
                    pattern=self._resource(resources,'Pattern',a[0])
                    if isinstance(pattern,Stream) and pattern.attrs.get('PatternType')==1:
                        if pattern.attrs.get('PaintType')!=1 or id(pattern) in forms:raise UnsupportedPDF('Ungefärbtes PDF-Kachelmuster noch nicht unterstützt.')
                    elif not isinstance(pattern,dict) or pattern.get('PatternType')!=2:raise PDFError('Ungültiges PDF-Muster.')
                    elif pattern.get('ExtGState'):raise UnsupportedPDF('PDF-Verlaufsmuster mit eigenem Grafikzustand noch nicht unterstützt.')
                    state[slot+'pattern']=(pattern,default_transform)
                else:state[slot]=color(a,state[slot+'space'])
            elif op=='BT':
                numbers(a,0)
                if text: raise PDFError('Verschachteltes PDF-Textobjekt.')
                text=True; matrix=QTransform(); line=QTransform()
            elif op=='ET':
                numbers(a,0)
                if not text: raise PDFError('PDF-Textende ohne Beginn.')
                text=False
            elif op=='Tf':
                if len(a)!=2 or not isinstance(a[0],Name): raise PDFError('Ungültige PDF-Schriftauswahl.')
                numbers(a[1:]); state.update(font=self._font(resources,a[0]),size=a[1])
            elif op in ('Tc','Tw','Tz','TL','Ts'):
                value=numbers(a,1)[0]; key={'Tc':'charspace','Tw':'wordspace','Tz':'scale','TL':'leading','Ts':'rise'}[op]; state[key]=value/100 if op=='Tz' else value
            elif op=='Tr':
                if len(a)!=1: raise PDFError('Ungültiger PDF-Textmodus.')
                mode=integer(a[0],0,7)
                if mode>=4: raise UnsupportedPDF('PDF-Text-Clipping noch nicht unterstützt.')
                state['mode']=mode
            elif op=='Tm': matrix=QTransform(*numbers(a,6)); line=QTransform(matrix)
            elif op in ('Td','TD'):
                x,y=numbers(a,2)
                if op=='TD': state['leading']=-y
                line=QTransform(1,0,0,1,x,y)*line; matrix=QTransform(line)
            elif op=='T*': numbers(a,0); line=QTransform(1,0,0,1,0,-state['leading'])*line; matrix=QTransform(line)
            elif op in ('Tj','TJ',"'",'"'):
                if op in ("'",'"'):
                    if op=='"':
                        if len(a)!=3: raise PDFError('Ungültiger PDF-Textoperator.')
                        numbers(a[:2]); state.update(wordspace=a[0],charspace=a[1]); a=a[2:]
                    line=QTransform(1,0,0,1,0,-state['leading'])*line; matrix=QTransform(line)
                if len(a)!=1: raise PDFError('Ungültiger PDF-Textoperator.')
                chunks=a[0] if op=='TJ' and isinstance(a[0],list) else a
                for chunk in chunks:
                    if isinstance(chunk,bytes): show(chunk)
                    elif type(chunk) in (int,float) and op=='TJ': numbers([chunk]); matrix=QTransform(1,0,0,1,-chunk/1000*state['size']*state['scale'],0)*matrix
                    else: raise PDFError('Ungültiger PDF-Textoperator.')
            elif op=='Do':
                if len(a)!=1 or not isinstance(a[0],Name): raise PDFError('Ungültiges PDF-XObject.')
                obj=self._resource(resources,'XObject',a[0])
                if not isinstance(obj,Stream): raise PDFError('PDF-XObject ist kein Stream.')
                if not self._visible(obj.attrs.get('OC')):continue
                if obj.attrs.get('Subtype')=='Image':
                    image=self._image(obj,resources,state['fill'])
                    if state['blendspace']=='DeviceGray':
                        from lumen_pdf_transparency import gray_image
                        image=gray_image(image)
                    def draw(output):
                        output.setTransform(QTransform(1/image.width(),0,0,-1/image.height(),0,1),True);output.drawImage(0,0,image)
                    paint(self,painter,state,'fill',draw);self.image_count+=1
                elif obj.attrs.get('Subtype')=='Form':
                    self._form(obj,resources,painter,forms,depth,state)
                else: raise UnsupportedPDF('PDF-XObject-Typ noch nicht unterstützt.')
            elif op in ('BX','EX'):pass  # compatibility markers; an operator this engine lacks is still refused by name
            elif op in ('BMC','BDC','EMC','MP','DP'):
                # A marked span can sit on a hidden layer, or carry the text to read in place of its glyphs.
                if op=='BMC':marks.append((False,None,0))
                elif op=='BDC':
                    if len(a)!=2:raise PDFError('Ungültige PDF-Inhaltsmarkierung.')
                    properties=self._resource(resources,'Properties',a[1]) if isinstance(a[1],Name) else a[1]
                    if not isinstance(properties,dict) or len(marks)>=64:raise PDFError('Ungültige PDF-Inhaltsmarkierung.')
                    hide=a[0]=='OC' and not self._visible(properties);actual=self.document.resolve(properties.get('ActualText'))
                    if actual is not None and not isinstance(actual,bytes):raise PDFError('Ungültiger PDF-Markierungstext.')
                    self.hidden+=hide;marks.append((hide,None if actual is None else ''.join(c for c in pdf_string(actual) if unicodedata.category(c)!='Cf'),len(self.characters)))
                elif op=='EMC' and marks:
                    hide,actual,start=marks.pop();self.hidden-=hide;span=self.characters[start:]
                    if actual is not None and self.collect and span:
                        bounds=QRectF(span[0][0]);area=QRectF(span[0][4])
                        for character in span[1:]:bounds=bounds.united(character[0]);area=area.united(character[4])
                        self.characters[start:]=[(bounds,actual,span[0][2],span[0][3],area)] if actual.strip() else []
            elif op=='gs':
                if len(a)!=1 or not isinstance(a[0],Name): raise PDFError('Ungültiger PDF-Grafikzustand.')
                settings=self._resource(resources,'ExtGState',a[0])
                if not isinstance(settings,dict): raise PDFError('Ungültiger PDF-Grafikzustand.')
                defaults={'Type':Name('ExtGState'),'CA':1,'ca':1,'BM':Name('Normal'),'SMask':Name('None'),'AIS':False,'TK':True,'OP':False,'op':False,'OPM':0,'SA':False}
                for key,value in settings.items():
                    value=self.document.resolve(value)
                    if key in ('ca','CA'):
                        numbers([value])
                        if not 0<=value<=1:raise PDFError('Ungültige PDF-Deckkraft.')
                        state['fillalpha' if key=='ca' else 'strokealpha']=value;continue
                    if key=='BM':
                        modes=value if isinstance(value,list) else [value]
                        chosen=next((m for m in modes if isinstance(m,Name) and m in BLENDS),None)
                        if chosen is None:raise UnsupportedPDF('PDF-Mischmodus noch nicht unterstützt: '+str(value))
                        if state.get('flat') and chosen not in ('Normal','Compatible'):raise UnsupportedPDF('PDF-Mischmodus in nicht isolierter transparenter Gruppe noch nicht unterstützt.')
                        state['blend']=chosen;continue
                    if key=='SMask':
                        if value=='None':state['mask']=None
                        elif isinstance(value,dict):
                            inherited=copy(state);inherited['mask']=None;state['mask']=(value,QTransform(painter.transform()),resources,inherited);self.effects=True
                        else:raise PDFError('Ungültige PDF-Weichmaske.')
                        continue
                    if key=='SA' and type(value) is bool:state['adjust']=value;continue
                    if key=='AIS' and type(value) is bool:
                        # Alpha as shape only changes the result inside a knockout group.
                        if value and state.get('knockout') is not None:raise UnsupportedPDF('PDF-Alpha als Form in Knockout-Gruppe noch nicht unterstützt.')
                        continue
                    # The same line settings as the w, J, j and M operators.
                    if key in ('LW','ML'):
                        numbers([value])
                        if value<0 or key=='ML' and value<1:raise PDFError('Ungültige PDF-Linienangabe.')
                        state['width' if key=='LW' else 'miter']=value;continue
                    if key in ('LC','LJ'):state['cap' if key=='LC' else 'join']=integer(value,0,2);continue
                    # Overprint only changes separations on a press; on screen without overprint preview it draws as usual.
                    if key in ('OP','op') and type(value) is bool or key=='OPM' and value in (0,1):continue
                    if key=='SM':
                        numbers([value]);
                        if not 0<=value<=1:raise PDFError('Ungültige PDF-Kurvenglättung.')
                        continue  # Qt adaptively flattens curves at the output resolution.
                    if key not in defaults or value!=defaults[key]: raise UnsupportedPDF('PDF-Grafikzustand noch nicht unterstützt: '+str(key))
            elif op=='sh':
                if len(a)!=1 or not isinstance(a[0],Name):raise PDFError('Ungültiger PDF-Verlauf.')
                shading=self._resource(resources,'Shading',a[0])
                from lumen_pdf_shading import brush as shading_brush
                def draw(output):
                    bounds=output.clipBoundingRect();shade,clip=shading_brush(self.document,shading,resources,bounds)
                    output.setClipPath(clip,Qt.ClipOperation.IntersectClip);output.fillRect(bounds,converted(shade))
                paint(self,painter,state,'fill',draw)
            elif op in ('ri','i'):
                if op=='i': numbers(a,1)
                elif len(a)!=1 or not isinstance(a[0],Name): raise PDFError('Ungültige PDF-Renderingabsicht.')
            else: raise UnsupportedPDF('PDF-Grafikoperator noch nicht unterstützt: '+op)
        if operands or stack or text: raise PDFError('Unvollständiger PDF-Grafikstream.')
        self.hidden-=sum(mark[0] for mark in marks)

    def _image(self,stream,resources=None,fill=None):
        from lumen_pdf_image import image
        return image(self,stream,resources or {},fill or QColor('black'))

    def _words(self):
        words=[]; text=''; rect=None; previous=None;last_angle=None
        normal=QTransform(1,0,0,-1,-self.box.x(),self.box.bottom())
        to_normal=self.transform.inverted()[0]*normal
        to_display=to_normal.inverted()[0]
        # Many writers position words without drawing a space; a tenth of the line height separates them, kerning stays below it.
        for displayed,letter,mode,angle,bounds in self.characters:
            if any(unicodedata.bidirectional(c) in ('R','AL','RLE','RLO','RLI') for c in letter):raise UnsupportedPDF('Rechts-nach-links-PDF-Text wird noch nicht zuverlässig gelesen.')
            gap=previous is not None and (angle!=last_angle or abs(bounds.top()-previous.top())>max(2,bounds.height()*.4) or bounds.left()-previous.right()>max(1,bounds.height()*.1))
            if letter.isspace() or gap:
                if text: words.append([rect.left(),rect.top(),rect.right(),rect.bottom(),text,0,0,last_angle]); text=''; rect=None
            if not letter.isspace(): text+=letter; rect=QRectF(bounds) if rect is None else rect.united(bounds)
            previous=bounds;last_angle=angle
        if text: words.append([rect.left(),rect.top(),rect.right(),rect.bottom(),text,0,0,last_angle])
        # Stable geometric order is local to this backend; never reuse old word
        # indices until the Reader migration has re-anchored existing notes.
        words.sort(key=lambda w:(w[7],round(w[1],1),w[0]))
        line=-1; last_y=None;last_angle=None
        for word in words:
            angle=word.pop()
            if last_y is None or angle!=last_angle or abs(word[1]-last_y)>max(2,(word[3]-word[1])*.4): line+=1; last_y=word[1];last_angle=angle
            word[6]=line
            mapped=(QTransform().rotate(angle)*to_display).mapRect(QRectF(word[0],word[1],word[2]-word[0],word[3]-word[1]))
            word[:4]=[mapped.left(),mapped.top(),mapped.right(),mapped.bottom()]
        return words

    def text(self):
        lines={}
        for word in self.words: lines.setdefault(word[6],[]).append(word[4])
        return '\n'.join(' '.join(words) for words in lines.values())

    def render(self,scale=1):
        numbers([scale]); w=math.ceil(self.width*scale); h=math.ceil(self.height*scale)
        if scale<=0 or w<=0 or h<=0 or w*h>40000000: raise PDFError('PDF-Vorschaubild zu groß oder ungültig.')
        image=QImage(w,h,QImage.Format.Format_ARGB32_Premultiplied); image.fill(Qt.GlobalColor.transparent); painter=QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform); painter.scale(scale,scale)
            if self.effects:
                self.collect=False;self.operations=0;self.image_pixels=0;self.character_units=0;self.effect_pixels=0;self.effect_depth=0
                count=self.image_count
                try:self._draw(painter)
                finally:self.image_count=count
            else:painter.drawPicture(0,0,self.picture)
        finally:painter.end();self.collect=True
        output=QImage(w,h,QImage.Format.Format_RGB888);output.fill(QColor('white'));painter=QPainter(output)
        try:painter.drawImage(0,0,image)
        finally:painter.end()
        return output


def png(image):
    buffer=QBuffer(); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer,'PNG'): raise PDFError('PDF-Vorschaubild konnte nicht gespeichert werden.')
    return bytes(buffer.data())

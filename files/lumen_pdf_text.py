"""Own PDF font embedding and text placement; Qt provides general text shaping."""
import hashlib
import math
import struct
import unicodedata
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont,QImage,QTextCharFormat,QTextLayout,QTextOption,QRawFont,QTransform
from lumen_pdf import Name,PDFError,UnsupportedPDF,serialize
from lumen_pdf_page import gui,rectangle


def truetype(raw):
    tags=('OS/2','cmap','cvt ','fpgm','gasp','glyf','head','hhea','hmtx','kern','loca','maxp','name','post','prep','GDEF','GPOS','GSUB')
    tables={tag:bytes(raw.fontTable(tag)) for tag in tags if raw.fontTable(tag)}
    if any(tag not in tables for tag in ('head','hhea','hmtx','maxp','glyf','loca','cmap')) or raw.fontTable('fvar'):
        raise UnsupportedPDF('Für diesen Text fehlt eine einbettbare statische TrueType-Schrift.')
    os2=tables.get('OS/2',b'')
    if len(os2)>=10 and int.from_bytes(os2[8:10],'big')&0x202: raise UnsupportedPDF('Diese Schrift erlaubt keine PDF-Einbettung als Konturen.')
    tables['head']=tables['head'][:8]+bytes(4)+tables['head'][12:]
    def checksum(data):
        data+=bytes(-len(data)%4);return sum(struct.unpack('>'+str(len(data)//4)+'I',data))&0xffffffff
    count=len(tables);power=int(math.log2(count));header=struct.pack('>IHHHH',0x10000,count,16*(1<<power),power,16*count-16*(1<<power));directory=bytearray();body=bytearray();head=0
    for tag,data in sorted(tables.items()):
        offset=12+count*16+len(body)
        if tag=='head':head=offset
        directory.extend(tag.encode()+struct.pack('>III',checksum(data),offset,len(data)));body.extend(data);body.extend(bytes(-len(data)%4))
    result=bytearray(header+directory+body);result[head+8:head+12]=((0xB1B0AFBA-checksum(bytes(result)))&0xffffffff).to_bytes(4,'big')
    return bytes(result)


def glyph_path(raw,gid):
    """Secondary glyphs of a Unicode cluster need outlines, not empty CMap targets."""
    path=raw.pathForGlyph(gid);data=bytearray();index=0
    while index<path.elementCount():
        element=path.elementAt(index)
        if element.isCurveTo():
            points=[path.elementAt(index+j) for j in range(3)];data.extend(b' '.join(serialize(v) for p in points for v in (p.x,p.y))+b' c\n');index+=3
        else:data.extend(serialize(element.x)+b' '+serialize(element.y)+(b' m\n' if element.isMoveTo() else b' l\n'));index+=1
    return bytes(data)+b'f\n'


class TextWriter:
    def __init__(self,writer):
        gui();self.writer=writer;self.fonts={}
    def _font(self,raw):
        key=(raw.familyName(),raw.styleName(),hashlib.sha256(bytes(raw.fontTable('head'))+bytes(raw.fontTable('name'))).digest())
        if key not in self.fonts:
            data=truetype(raw);size=raw.pixelSize();name=Name('LumenFont'+str(len(self.fonts)+1)+('-Bold' if raw.weight()>=QFont.Weight.DemiBold else '')+('-Italic' if raw.style()!=QFont.Style.StyleNormal else ''));scale=1000/size
            descriptor=self.writer.add({'Type':Name('FontDescriptor'),'FontName':name,'Flags':4,'FontBBox':[-2000,-2000,4000,4000],'ItalicAngle':-12 if raw.style()!=QFont.Style.StyleNormal else 0,'Ascent':raw.ascent()*scale,'Descent':-raw.descent()*scale,'CapHeight':raw.capHeight()*scale,'StemV':80,'FontFile2':self.writer.stream(data,Length1=len(data))})
            descendant=self.writer.add({'Type':Name('Font'),'Subtype':Name('CIDFontType2'),'BaseFont':name,'CIDSystemInfo':{'Registry':b'Adobe','Ordering':b'Identity','Supplement':0},'FontDescriptor':descriptor,'DW':1000})
            parent=self.writer.add({'Type':Name('Font'),'Subtype':Name('Type0'),'BaseFont':name,'Encoding':Name('Identity-H'),'DescendantFonts':[descendant]})
            self.fonts[key]={'name':str(name),'ref':parent,'child':descendant,'codes':{},'mapping':[]}
        return self.fonts[key]
    def _code(self,raw,gid,text):
        if gid==0 and text.strip():raise UnsupportedPDF('In den installierten Schriften fehlt ein Zeichen der Übersetzung.')
        font=self._font(raw);key=(gid,text)
        if key not in font['codes']:
            cid=len(font['mapping'])+1
            if cid>65535:raise PDFError('Zu viele Schriftzeichen im PDF-Export.')
            font['codes'][key]=cid;font['mapping'].append((gid,text,raw.advancesForGlyphIndexes([gid])[0].x()*1000/raw.pixelSize()))
        return font,font['codes'][key]
    def finalize(self):
        for font in self.fonts.values():
            entries=font['mapping'];gidmap=b'\0\0'+b''.join(gid.to_bytes(2,'big') for gid,_,_ in entries)
            child=self.writer.objects[font['child'].number-1];child.update(CIDToGIDMap=self.writer.stream(gidmap),W=[1,[width for _,_,width in entries]])
            cmap=bytearray(b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /LumenUnicode def /CMapType 2 def 1 begincodespacerange <0000> <ffff> endcodespacerange\n')
            for start in range(0,len(entries),100):
                batch=entries[start:start+100];cmap.extend(f'{len(batch)} beginbfchar\n'.encode())
                for i,(_,text,_) in enumerate(batch,start+1):cmap.extend(f'<{i:04x}> <{text.encode("utf-16-be").hex()}>\n'.encode())
                cmap.extend(b'endbfchar\n')
            cmap.extend(b'endcmap CMapName currentdict /CMap defineresource pop end end')
            self.writer.objects[font['ref'].number-1]['ToUnicode']=self.writer.stream(bytes(cmap))

    def box(self,page,rect,parts,styles,min_scale=.6,invisible=False,angle=0):
        """Write shaped text into a top-left rectangle; fail rather than clip overflow."""
        area=rectangle(list(rect));text=''.join(parts).replace('\n','\u2028')
        if not text:return 1
        if any(unicodedata.bidirectional(c) in ('R','AL','RLE','RLO','RLI') for c in text):raise UnsupportedPDF('Rechts-nach-links-Text kann noch nicht zuverlässig in PDF geschrieben werden.')
        if len(text)>100000 or len(parts)!=len(styles):raise PDFError('Ungültiger PDF-Textauftrag.')
        device=QImage(1,1,QImage.Format.Format_RGB888);device.setDotsPerMeterX(2835);device.setDotsPerMeterY(2835)
        # Use a single complete font family: Qt 6.11 reports invalid string indices
        # for some fallback runs. Never emit a plausible-looking wrong ToUnicode.
        family=None
        characters={ord(c) for c in text if c not in '\n\u2028' and unicodedata.category(c)!='Cf'}
        for candidate in ('Liberation Sans','DejaVu Sans','Noto Sans','Noto Sans Math'):
            complete=True
            for style in styles:
                font=QFont(candidate);font.setBold(bool(style.get('bold')));font.setItalic(bool(style.get('italic')));raw=QRawFont.fromFont(font)
                if not raw.isValid() or any(not raw.supportsCharacter(c) for c in characters):complete=False;break
            if complete:family=raw.familyName();break
        if family is None:raise UnsupportedPDF('Für diesen Text fehlt eine vollständig passende einbettbare Schrift.')
        selected=None
        for step in range(21):
            scale=1-(1-min_scale)*step/20;font=QFont(family);font.setPointSizeF(max(.5,styles[0]['size']*scale));layout=QTextLayout(text,font,device);formats=[];offset=0
            for part,style in zip(parts,styles):
                fmt=QTextCharFormat();fmt.setFontFamilies([family]);fmt.setFontPointSize(max(.5,style['size']*scale));fmt.setFontWeight(QFont.Weight.Bold if style.get('bold') else QFont.Weight.Normal);fmt.setFontItalic(bool(style.get('italic')))
                item=QTextLayout.FormatRange();item.start=offset;item.length=len(part.encode('utf-16-le'))//2;item.format=fmt;formats.append(item);offset+=item.length
            layout.setFormats(formats);option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);layout.beginLayout();height=0;fit=True
            while True:
                line=layout.createLine()
                if not line.isValid():break
                line.setLineWidth(area.width());line.setPosition(QPointF(0,height));height+=line.height()
                if line.naturalTextWidth()>area.width()+.01 or height>area.height()+.01:fit=False;break
            layout.endLayout()
            if fit:selected=layout;break
        if selected is None:raise PDFError('Übersetzung passt nicht in den ursprünglichen Textbereich. Bitte kürzer formulieren lassen.')
        runs=selected.glyphRuns(-1,-1,QTextLayout.GlyphRunRetrievalFlag.RetrieveAll)
        indices=sorted({i for run in runs for i in run.stringIndexes()}|{len(text.encode('utf-16-le'))//2});ends={a:b for a,b in zip(indices,indices[1:])};used=set();source=text.encode('utf-16-le');content=bytearray();resources=page.setdefault('Resources',{});fonts=resources.setdefault('Font',{})
        glyphs=[]
        for run in runs:
            raw=run.rawFont()
            if raw.familyName()!=family:raise UnsupportedPDF('PDF-Schriftfallback liefert keine verlässlichen Textpositionen.')
            glyphs.extend((index,gid,position,raw) for gid,position,index in zip(run.glyphIndexes(),run.positions(),run.stringIndexes()))
        for index,gid,position,raw in sorted(glyphs,key=lambda item:item[0]):
            value=source[index*2:ends.get(index,index)*2].decode('utf-16-le').replace('\u2028','\n') if index not in used else '';used.add(index)
            style_index=next((i for i,f in enumerate(formats) if f.start<=index<f.start+f.length),0);rgb=styles[style_index].get('color',0)
            r,g,b=((rgb>>16&255)/255,(rgb>>8&255)/255,(rgb&255)/255);x=area.x()+position.x();y=page['MediaBox'][3]-area.y()-position.y()
            if not value:
                if not invisible:content.extend(b'q '+b' '.join(serialize(v) for v in (r,g,b))+b' rg 1 0 0 -1 '+serialize(x)+b' '+serialize(y)+b' cm '+glyph_path(raw,gid)+b' Q\n')
                continue
            font,cid=self._code(raw,gid,value);fonts[font['name']]=font['ref']
            content.extend(b'q BT 0 Tc 0 Tw 100 Tz 0 Ts 0 Tr /'+font['name'].encode()+b' '+serialize(raw.pixelSize())+b' Tf '+b' '.join(serialize(v) for v in (r,g,b))+b' rg '+(b'3 Tr ' if invisible else b'')+b'1 0 0 1 '+serialize(x)+b' '+serialize(y)+b' Tm '+serialize(cid.to_bytes(2,'big'))+b' Tj ET Q\n')
        if type(angle) not in (int,float) or not math.isfinite(angle):raise PDFError('Ungültiger PDF-Textwinkel.')
        if angle:
            flip=QTransform(1,0,0,-1,0,page['MediaBox'][3]);transform=flip*QTransform().rotate(angle)*flip
            content=b'q '+b' '.join(serialize(v) for v in (transform.m11(),transform.m12(),transform.m21(),transform.m22(),transform.dx(),transform.dy()))+b' cm\n'+content+b'Q\n'
        existing=page.get('Contents');streams=list(existing) if isinstance(existing,list) else [existing] if existing else [];streams.append(self.writer.stream(bytes(content)));page['Contents']=streams
        return scale

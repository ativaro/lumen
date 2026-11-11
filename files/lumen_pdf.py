"""Lumen's own PDF object reader/writer. No external PDF backend.

Format: Adobe PDF Reference 1.7, chapter 3 (syntax, filters, file structure).
https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf
Unsupported features are errors, never a request to repair or guess the file.
"""
from dataclasses import dataclass
import base64
import math
import os
from pathlib import Path
import re
import tempfile
import zlib

MAX_FILE = 512 * 1024**2
MAX_STREAM = 64 * 1024**2
MAX_OBJECTS = 200000
MAX_DEPTH = 64
MAX_ITEMS = 1000000
SPACE = b'\x00\t\n\x0c\r '
DELIMITERS = SPACE + b'()<>[]{}/%'
NUMBER = re.compile(rb'[+-]?(?:\d+\.?\d*|\.\d+)\Z')


class PDFError(ValueError):
    pass


class UnsupportedPDF(PDFError):
    pass


class Name(str):
    """PDF name, distinct from byte strings and content operators."""


class Operator(str):
    pass


@dataclass(frozen=True)
class Ref:
    number: int
    generation: int = 0


@dataclass
class Stream:
    attrs: dict
    raw: bytes


def integer(value, low=0, high=MAX_OBJECTS):
    if type(value) is not int or not low <= value <= high:
        raise PDFError('Ungültige PDF-Ganzzahl oder überschrittenes Limit.')
    return value


class Syntax:
    def __init__(self, data, position=0):
        self.data, self.pos, self.items = data, position, 0

    def skip(self):
        while self.pos < len(self.data):
            if self.data[self.pos] in SPACE:
                self.pos += 1
            elif self.data[self.pos] == 37:
                match = re.compile(rb'[\r\n]').search(self.data,self.pos)
                self.pos = match.end() if match else len(self.data)
            else:
                break

    def word(self):
        self.skip(); start = self.pos
        while self.pos < len(self.data) and self.data[self.pos] not in DELIMITERS:
            self.pos += 1
        if self.pos == start:
            raise PDFError('Unerwartetes PDF-Zeichen.')
        return self.data[start:self.pos]

    def expect(self, expected):
        if self.word() != expected:
            raise PDFError('Ungültige PDF-Struktur: ' + expected.decode('ascii'))

    def value(self, depth=0):
        if depth > MAX_DEPTH or self.items >= MAX_ITEMS:
            raise PDFError('PDF-Verschachtelung oder Objektgröße überschritten.')
        self.items += 1
        self.skip(); data = self.data; start = self.pos
        if start >= len(data): raise PDFError('Unerwartetes PDF-Ende.')
        if data.startswith(b'<<', start):
            self.pos += 2; result = {}
            while True:
                self.skip()
                if data.startswith(b'>>', self.pos): self.pos += 2; return result
                key = self.value(depth + 1)
                if not isinstance(key, Name) or key in result:
                    raise PDFError('Ungültiger oder doppelter PDF-Dictionary-Schlüssel.')
                result[key] = self.value(depth + 1)
        char = data[start]; self.pos += 1
        if char == 91:
            result = []
            while True:
                self.skip()
                if self.pos < len(data) and data[self.pos] == 93:
                    self.pos += 1; return result
                result.append(self.value(depth + 1))
        if char == 40:
            result = bytearray(); nesting = 1
            while self.pos < len(data):
                char = data[self.pos]; self.pos += 1
                if char == 92:
                    if self.pos == len(data): break
                    char = data[self.pos]; self.pos += 1
                    if char in b'\r\n':
                        if char == 13 and data[self.pos:self.pos+1] == b'\n': self.pos += 1
                        continue
                    if 48 <= char <= 55:
                        digits = bytes([char])
                        for _ in range(2):
                            if self.pos < len(data) and 48 <= data[self.pos] <= 55:
                                digits += data[self.pos:self.pos+1]; self.pos += 1
                            else: break
                        result.append(int(digits, 8) & 255)
                    else: result.append({110:10,114:13,116:9,98:8,102:12}.get(char,char))
                elif char == 40:
                    nesting += 1
                    if nesting > MAX_DEPTH: raise PDFError('PDF-Zeichenfolge zu tief verschachtelt.')
                    result.append(char)
                elif char == 41:
                    nesting -= 1
                    if not nesting: return bytes(result)
                    result.append(char)
                elif char == 13:
                    if data[self.pos:self.pos+1] == b'\n': self.pos += 1
                    result.append(10)
                else: result.append(char)
                if len(result) > MAX_STREAM: raise PDFError('PDF-Zeichenfolge zu groß.')
            raise PDFError('Nicht abgeschlossene PDF-Zeichenfolge.')
        if char == 60:
            end = data.find(b'>', self.pos)
            if end < 0: raise PDFError('Nicht abgeschlossene PDF-Hexzeichenfolge.')
            raw = bytes(c for c in data[self.pos:end] if c not in SPACE)
            if len(raw) > MAX_STREAM * 2: raise PDFError('PDF-Hexzeichenfolge zu groß.')
            self.pos = end + 1
            try: return bytes.fromhex((raw + (b'0' if len(raw) % 2 else b'')).decode('ascii'))
            except ValueError as error: raise PDFError('Ungültige PDF-Hexzeichenfolge.') from error
        if char == 47:
            end = self.pos
            while end < len(data) and data[end] not in DELIMITERS: end += 1
            raw = data[self.pos:end]; self.pos = end
            if re.search(rb'#(?![0-9a-fA-F]{2})',raw): raise PDFError('Ungültiger PDF-Name.')
            return Name(re.sub(rb'#([0-9a-fA-F]{2})',lambda m:bytes([int(m[1],16)]),raw).decode('latin1'))
        self.pos = start; token = self.word()
        if token == b'true': return True
        if token == b'false': return False
        if token == b'null': return None
        # Presentation exporters sometimes append a signed tail to a zero real.
        # Match established readers' zero-prefix recovery; never reinterpret an
        # integer/object reference or a general unknown operator this way.
        if len(token)<=100 and re.fullmatch(rb'[+-]?0\.0+[+-]\d+',token):return 0.0
        if NUMBER.fullmatch(token):
            if len(token)>100: raise PDFError('PDF-Zahl zu lang.')
            result = float(token) if b'.' in token else int(token)
            if not math.isfinite(result): raise PDFError('Ungültige PDF-Zahl.')
            if type(result) is int and result >= 0:
                saved = self.pos
                # PDF comments are whitespace, including between reference tokens.
                try:
                    second=self.word()
                    if second.isdigit() and len(second)<=5 and self.word()==b'R':
                        return Ref(integer(result,1),integer(int(second),0,65535))
                except PDFError:
                    pass
                self.pos=saved
            return result
        try: return Operator(token.decode('ascii'))
        except UnicodeDecodeError as error: raise PDFError('Ungültiger PDF-Operator.') from error


def _bounded(data):
    if len(data)>MAX_STREAM: raise PDFError('Dekomprimierter PDF-Stream zu groß.')
    return data


def _predict(data, params):
    predictor = params.get('Predictor',1)
    if predictor == 1: return data
    columns=integer(params.get('Columns',1),1,100000)
    colors=integer(params.get('Colors',1),1,32)
    bits=params.get('BitsPerComponent',8)
    if bits not in (1,2,4,8,16): raise UnsupportedPDF('PDF-Prädiktor mit unbekannter Bittiefe.')
    stride=(columns*colors*bits+7)//8; bpp=max(1,(colors*bits+7)//8)
    if stride>MAX_STREAM: raise PDFError('PDF-Bildzeile zu groß.')
    if predictor==2:
        if bits!=8: raise UnsupportedPDF('TIFF-PDF-Prädiktor unterstützt derzeit 8 Bit.')
        if len(data)%stride: raise PDFError('Unvollständige TIFF-PDF-Zeile.')
        result=bytearray(data)
        for row in range(0,len(result),stride):
            for col in range(bpp,stride): result[row+col]=(result[row+col]+result[row+col-bpp])&255
        return bytes(result)
    if not 10<=predictor<=15: raise UnsupportedPDF('Unbekannter PDF-Prädiktor.')
    if len(data)%(stride+1): raise PDFError('Unvollständige PNG-PDF-Zeile.')
    result=bytearray(); previous=bytearray(stride)
    for start in range(0,len(data),stride+1):
        kind=data[start]; row=bytearray(data[start+1:start+1+stride])
        if kind>4: raise PDFError('Ungültiger PNG-PDF-Prädiktor.')
        for i in range(stride):
            left=row[i-bpp] if i>=bpp else 0; up=previous[i]; corner=previous[i-bpp] if i>=bpp else 0
            if kind==1: value=left
            elif kind==2: value=up
            elif kind==3: value=(left+up)//2
            elif kind==4:
                p=left+up-corner; distances=(abs(p-left),abs(p-up),abs(p-corner))
                value=(left,up,corner)[distances.index(min(distances))]
            else: value=0
            row[i]=(row[i]+value)&255
        result.extend(row); previous=row
    return bytes(result)


def decoded(stream, resolve=lambda value:value):
    if any(key in stream.attrs for key in ('F','FFilter','FDecodeParms')): raise UnsupportedPDF('Externe PDF-Streamdaten werden nicht geöffnet.')
    data=stream.raw; filters=resolve(stream.attrs.get('Filter')) or []; params=resolve(stream.attrs.get('DecodeParms')) or []
    if isinstance(filters,Name): filters=[filters]; params=[params or {}]
    if not isinstance(filters,list) or len(filters)>8: raise PDFError('Ungültige PDF-Filterkette.')
    if not isinstance(params,list): raise PDFError('Ungültige PDF-Filterparameter.')
    if len(data)>MAX_STREAM*2: raise PDFError('Kodierter PDF-Stream zu groß.')
    for index,name in enumerate(filters):
        name=resolve(name); options=resolve(params[index]) if index<len(params) else {}
        options=options or {}
        if not isinstance(options,dict): raise PDFError('Ungültige PDF-Filterparameter.')
        try:
            if name in ('FlateDecode','Fl'):
                decoder=zlib.decompressobj(); data=decoder.decompress(data,MAX_STREAM+1)
                _bounded(data)
                if decoder.unconsumed_tail: raise PDFError('Beschädigter oder zu großer Flate-PDF-Stream.')
                if not decoder.eof:
                    # Some writers leave out the closing checksum, or its last bytes. The data is then complete exactly
                    # when the decoder, given four more bytes, reaches the end: it either objects to that checksum
                    # or, where the missing bytes happen to be zero, accepts it.
                    try: decoder.decompress(bytes(4)); complete=decoder.eof
                    except zlib.error as error: complete='incorrect data check' in str(error)
                    if not complete: raise PDFError('Beschädigter oder zu großer Flate-PDF-Stream.')
                data=_predict(data,options)
            elif name in ('LZWDecode','LZW'):
                early=integer(options.get('EarlyChange',1),0,1); bit=0; width=9; table=[bytes([i]) for i in range(256)]+[b'',b'']; result=bytearray(); previous=None; ended=False
                while bit+width<=len(data)*8:
                    start=bit//8; shift=bit%8; count=(shift+width+7)//8
                    code=(int.from_bytes(data[start:start+count],'big')>>(count*8-shift-width))&((1<<width)-1); bit+=width
                    if code==257: ended=True; break
                    if code==256:
                        table=table[:258]; width=9; previous=None; continue
                    if code<len(table): entry=table[code]
                    elif code==len(table) and previous is not None: entry=previous+previous[:1]
                    else: raise PDFError('Ungültiger LZW-PDF-Code.')
                    result.extend(entry); _bounded(result)
                    if previous is not None and len(table)<4096:
                        table.append(previous+entry[:1])
                        if width<12 and len(table)+early==(1<<width): width+=1
                    previous=entry
                if not ended: raise PDFError('LZW-PDF-Ende fehlt.')
                data=_predict(bytes(result),options)
            elif name in ('ASCIIHexDecode','AHx'):
                raw=bytes(c for c in data if c not in SPACE)
                if not raw.endswith(b'>'): raise PDFError('ASCIIHex-PDF-Ende fehlt.')
                raw=raw[:-1]; data=bytes.fromhex((raw+(b'0' if len(raw)%2 else b'')).decode('ascii'))
            elif name in ('ASCII85Decode','A85'):
                raw=bytes(c for c in data if c not in SPACE)
                if not raw.endswith(b'~>'): raise PDFError('ASCII85-PDF-Ende fehlt.')
                encoded=raw[:-2]; short=encoded.count(b'z'); ordinary=len(encoded)-short
                if short*4+(ordinary//5)*4+max(0,ordinary%5-1)>MAX_STREAM: raise PDFError('Dekomprimierter ASCII85-PDF-Stream zu groß.')
                data=base64.a85decode(encoded,adobe=False)
            elif name in ('RunLengthDecode','RL'):
                result=bytearray(); pos=0; ended=False
                while pos<len(data):
                    count=data[pos]; pos+=1
                    if count==128: ended=True; break
                    if count<128:
                        if pos+count+1>len(data): raise PDFError('Unvollständiger RunLength-PDF-Stream.')
                        result.extend(data[pos:pos+count+1]); pos+=count+1
                    else:
                        if pos==len(data): raise PDFError('Unvollständiger RunLength-PDF-Stream.')
                        result.extend(data[pos:pos+1]*(257-count)); pos+=1
                    _bounded(result)
                if not ended: raise PDFError('RunLength-PDF-Ende fehlt.')
                data=bytes(result)
            else: raise UnsupportedPDF('PDF-Filter noch nicht unterstützt: '+str(name))
        except (zlib.error,UnicodeError,ValueError) as error:
            if isinstance(error,PDFError): raise
            raise PDFError('Beschädigter PDF-Stream.') from error
        _bounded(data)
    return _bounded(data)


def pdf_string(value):
    if not isinstance(value,bytes): return ''
    if value.startswith(b'\xfe\xff'): return value[2:].decode('utf-16-be',errors='replace')
    if value.startswith(b'\xef\xbb\xbf'): return value[3:].decode('utf-8',errors='replace')
    # PDFDocEncoding differs from Latin-1 in these ranges (PDF 1.7, appendix D).
    specials='˘ˇˆ˙˝˛˚˜'
    extended='•†‡…—–ƒ⁄‹›−‰„“”‘’‚™ﬁﬂŁŒŠŸŽıłœšž'
    return ''.join(specials[c-24] if 24<=c<=31 else extended[c-128] if 128<=c<=158 else '€' if c==160 else chr(c) for c in value)


class Document:
    def __init__(self, source, password=""):
        if isinstance(source,bytes): self.data=source
        else:
            with Path(source).open('rb') as stream: self.data=stream.read(MAX_FILE+1)
        if len(self.data)>MAX_FILE: raise PDFError('PDF größer als 512 MiB.')
        if not re.match(rb'%PDF-[12]\.\d[\r\n]',self.data): raise PDFError('PDF-Kopf fehlt.')
        self.xref={}; self.cache={}; self.active=set(); self.object_streams={}; self.decoded_size=0
        self.trailer={}; self.pages=[]; self.page_refs=[]; self.security=None; self.encrypted=False
        match=re.search(rb'startxref\s+(\d+)\s+%%EOF\s*\Z',self.data[-4096:])
        if not match: raise PDFError('PDF-Abschluss oder Querverweis fehlt.')
        self._xrefs(int(match[1]))
        if self.trailer.get('Encrypt') is not None:
            from lumen_pdf_security import Security
            self.encrypted=True
            attrs=self.resolve(self.trailer['Encrypt'])
            attrs={k:self.resolve(v) for k,v in attrs.items()}
            if isinstance(attrs.get('CF'),dict): attrs['CF']={k:self.resolve(v) for k,v in attrs['CF'].items()}
            self.security=Security(attrs,self.trailer.get('ID'),password)
        self.catalog=self.resolve(self.trailer.get('Root'))
        if not isinstance(self.catalog,dict) or self.catalog.get('Type')!='Catalog': raise PDFError('PDF-Katalog fehlt.')
        self._pages(self.catalog.get('Pages'),{},set())
        if not self.pages: raise PDFError('PDF hat keine Seiten.')
        self.metadata=self.resolve(self.trailer.get('Info')) or {}
        if not isinstance(self.metadata,dict): raise PDFError('Ungültige PDF-Metadaten.')
        self.metadata={str(k).lower():pdf_string(self.resolve(v)) for k,v in self.metadata.items()}

    def _indirect(self, offset, expected=None, bootstrap=False):
        integer(offset,0,len(self.data)-1); syntax=Syntax(self.data,offset)
        number=integer(syntax.value(),1); generation=integer(syntax.value(),0,65535); syntax.expect(b'obj')
        if expected and expected!=Ref(number,generation): raise PDFError('PDF-Objekt und Querverweis stimmen nicht überein.')
        value=syntax.value(); syntax.skip()
        if isinstance(value,dict) and self.data[syntax.pos:syntax.pos+6]==b'stream':
            syntax.pos+=6
            if self.data[syntax.pos:syntax.pos+2]==b'\r\n': syntax.pos+=2
            elif self.data[syntax.pos:syntax.pos+1]==b'\n': syntax.pos+=1
            else: raise PDFError('PDF-Stream-Zeilenumbruch fehlt.')
            length=value.get('Length')
            if not bootstrap: length=self.resolve(length)
            length=integer(length,0,MAX_FILE); end=syntax.pos+length
            if end>len(self.data): raise PDFError('PDF-Stream reicht über Dateiende.')
            value=Stream(value,self.data[syntax.pos:end]); syntax.pos=end; syntax.expect(b'endstream')
        syntax.expect(b'endobj'); return Ref(number,generation),value

    def _xref_section(self,offset):
        integer(offset,0,len(self.data)-1); syntax=Syntax(self.data,offset); syntax.skip(); entries={}
        if self.data[syntax.pos:syntax.pos+4]==b'xref':
            syntax.expect(b'xref')
            while True:
                syntax.skip()
                if self.data[syntax.pos:syntax.pos+7]==b'trailer': syntax.expect(b'trailer'); break
                start=integer(syntax.value()); count=integer(syntax.value())
                if start+count>MAX_OBJECTS or len(entries)+count>MAX_OBJECTS: raise PDFError('Zu viele PDF-Objekte.')
                for number in range(start,start+count):
                    position=integer(syntax.value(),0,max(len(self.data),MAX_OBJECTS)); generation=integer(syntax.value(),0,65536); flag=syntax.word()
                    # Pillow emits 65536 for the unused free entry. It is never resolved.
                    if flag==b'n' and (generation>65535 or position>=len(self.data)):raise PDFError('Ungültiger PDF-Querverweis.')
                    if flag not in (b'n',b'f') or number in entries: raise PDFError('Ungültiger PDF-Querverweis.')
                    entries[number]=(1 if flag==b'n' else 0,position,generation)
            trailer=syntax.value()
            if not isinstance(trailer,dict): raise PDFError('Ungültiger PDF-Trailer.')
            return trailer,entries
        _,stream=self._indirect(offset,bootstrap=True)
        if not isinstance(stream,Stream) or stream.attrs.get('Type')!='XRef': raise PDFError('PDF-Querverweisstream fehlt.')
        attrs=stream.attrs; widths=attrs.get('W'); size=integer(attrs.get('Size'))
        if not isinstance(widths,list) or len(widths)!=3: raise PDFError('Ungültige PDF-Querverweisbreiten.')
        for width in widths: integer(width,0,8)
        stride=sum(widths)
        if not stride: raise PDFError('Leerer PDF-Querverweis.')
        indices=attrs.get('Index',[0,size])
        if not isinstance(indices,list) or len(indices)%2: raise PDFError('Ungültiger PDF-Querverweisindex.')
        data=decoded(stream); pos=0
        for start,count in zip(indices[::2],indices[1::2]):
            integer(start); integer(count)
            if start+count>size or len(entries)+count>MAX_OBJECTS: raise PDFError('PDF-Querverweisindex außerhalb des Bereichs.')
            for number in range(start,start+count):
                if pos+stride>len(data) or number in entries: raise PDFError('Ungültiger PDF-Querverweisstream.')
                fields=[]
                for column,width in enumerate(widths):
                    fields.append(int.from_bytes(data[pos:pos+width],'big') if width else (1 if column==0 else 0)); pos+=width
                if fields[0] not in (0,1,2): raise UnsupportedPDF('Unbekannter PDF-Querverweistyp.')
                entries[number]=tuple(fields)
        if pos!=len(data): raise PDFError('PDF-Querverweislänge stimmt nicht.')
        return attrs,entries

    def _xrefs(self,offset):
        visited=set()
        while True:
            if offset in visited or len(visited)>=256: raise PDFError('Zyklische oder zu viele PDF-Revisionen.')
            visited.add(offset); trailer,entries=self._xref_section(offset)
            hybrid=trailer.get('XRefStm')
            if hybrid is not None:
                if hybrid in visited: raise PDFError('Zyklischer hybrider PDF-Querverweis.')
                visited.add(hybrid); extra,more=self._xref_section(hybrid); entries.update(more)
            for number,entry in entries.items(): self.xref.setdefault(number,entry)
            if len(self.xref)>MAX_OBJECTS: raise PDFError('Zu viele PDF-Objekte.')
            for key,value in trailer.items(): self.trailer.setdefault(key,value)
            offset=trailer.get('Prev')
            if offset is None: break
            integer(offset,0,len(self.data)-1)
        integer(self.trailer.get('Size'))

    def resolve(self,value):
        if not isinstance(value,Ref): return value
        if value in self.cache: return self.cache[value]
        if value in self.active or len(self.active)>MAX_DEPTH: raise PDFError('Zyklische PDF-Objektauflösung.')
        entry=self.xref.get(value.number)
        # ISO 32000-1 7.3.10: an undefined indirect object denotes PDF null.
        # Required objects are still validated by their consuming structures.
        if not entry or entry[0]==0:return None
        if entry[0]==1 and entry[2]!=value.generation or entry[0]==2 and value.generation!=0:return None
        self.active.add(value)
        try:
            if entry[0]==1: _,result=self._indirect(entry[1],value)
            else:
                stream_number,index=entry[1:]
                if stream_number not in self.object_streams:
                    stream=self.resolve(Ref(stream_number))
                    if not isinstance(stream,Stream) or stream.attrs.get('Type')!='ObjStm': raise PDFError('PDF-Objektstream fehlt.')
                    data=self.decode(stream); count=integer(stream.attrs.get('N')); first=integer(stream.attrs.get('First'),0,len(data))
                    syntax=Syntax(data[:first]); headers=[]
                    for _ in range(count): headers.append((integer(syntax.value(),1),integer(syntax.value(),0,len(data)-first)))
                    syntax.skip()
                    if syntax.pos!=first or len(set(n for n,_ in headers))!=len(headers): raise PDFError('Ungültiger PDF-Objektstream-Kopf.')
                    offsets=[offset for _,offset in headers]
                    if offsets!=sorted(set(offsets)): raise PDFError('Ungültige PDF-Objektstream-Offsets.')
                    self.object_streams[stream_number]=(data,first,headers)
                data,first,headers=self.object_streams[stream_number]
                if not 0<=index<len(headers) or headers[index][0]!=value.number: raise PDFError('PDF-Objektstream-Index stimmt nicht.')
                end=first+headers[index+1][1] if index+1<len(headers) else len(data)
                syntax=Syntax(data[first+headers[index][1]:end]); result=syntax.value(); syntax.skip()
                if syntax.pos!=len(syntax.data): raise PDFError('Ungültiger PDF-Objektstream-Inhalt.')
            if entry[0]==1 and self.security is not None: result=self.security.value(result,value,self.resolve)
            if isinstance(result,(Ref,Operator)): raise PDFError('Ungültiger indirekter PDF-Objektwert.')
            self.cache[value]=result; return result
        finally: self.active.remove(value)

    def decode(self,stream):
        if not isinstance(stream,Stream): raise PDFError('PDF-Stream erwartet.')
        result=decoded(stream,self.resolve); self.decoded_size+=len(result)
        if self.decoded_size>1024**3: raise PDFError('PDF-Dekompressionsbudget überschritten.')
        return result

    def _pages(self,reference,inherited,visited,depth=0):
        if depth>MAX_DEPTH or len(visited)>MAX_OBJECTS: raise PDFError('PDF-Seitenbaum zu groß.')
        if not isinstance(reference,Ref) or reference in visited: raise PDFError('Zyklischer oder ungültiger PDF-Seitenbaum.')
        visited.add(reference); node=self.resolve(reference)
        if not isinstance(node,dict): raise PDFError('Ungültiger PDF-Seitenknoten.')
        attrs=dict(inherited)
        for key in ('Resources','MediaBox','CropBox','Rotate'):
            if key in node: attrs[key]=self.resolve(node[key])
        if node.get('Type')=='Pages':
            kids=self.resolve(node.get('Kids'))
            if not isinstance(kids,list): raise PDFError('PDF-Seitenliste fehlt.')
            before=len(self.pages)
            for kid in kids: self._pages(kid,attrs,visited,depth+1)
            if node.get('Count')!=len(self.pages)-before: raise PDFError('PDF-Seitenzahl und Seitenbaum stimmen nicht überein.')
        elif node.get('Type')=='Page':
            attrs.update(node)
            for key in ('Resources','MediaBox','CropBox','Rotate'): attrs[key]=self.resolve(attrs.get(key,inherited.get(key)))
            box=attrs.get('MediaBox')
            if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box) or box[0]>=box[2] or box[1]>=box[3]: raise PDFError('Ungültige PDF-Seitengröße.')
            if max(abs(v) for v in box)>1000000: raise PDFError('PDF-Seitenkoordinaten zu groß.')
            self.pages.append(attrs); self.page_refs.append(reference)
            if len(self.pages)>10000: raise PDFError('Mehr als 10.000 PDF-Seiten.')
        else: raise PDFError('Unbekannter PDF-Seitenknoten.')

    def destination(self,value):
        """Resolve both legacy /Dests and the PDF name tree (ISO 32000-1 12.3.2)."""
        seen=set()
        def resolve(value,depth=0):
            if depth>MAX_DEPTH:raise PDFError('PDF-Seitenverweis zu tief.')
            value=self.resolve(value)
            if isinstance(value,(Name,bytes)):
                key=value
                if key in seen:raise PDFError('Zyklischer PDF-Seitenverweis.')
                seen.add(key)
                legacy=self.resolve(self.catalog.get('Dests',{}))
                found=legacy.get(str(value)) if isinstance(value,Name) and isinstance(legacy,dict) else None
                if found is None:
                    names=self.resolve(self.catalog.get('Names',{}))
                    root=self.resolve(names.get('Dests')) if isinstance(names,dict) else None
                    visited=set();wanted=value.encode('latin1') if isinstance(value,Name) else value
                    def search(node,level=0):
                        node=self.resolve(node)
                        if not isinstance(node,dict) or level>MAX_DEPTH or id(node) in visited or len(visited)>=MAX_OBJECTS:
                            raise PDFError('Ungültiger PDF-Zielnamenbaum.')
                        visited.add(id(node));entries=self.resolve(node.get('Names',[]))
                        if not isinstance(entries,list) or len(entries)%2:raise PDFError('Ungültige PDF-Zielnamenliste.')
                        for i in range(0,len(entries),2):
                            if self.resolve(entries[i])==wanted:return entries[i+1]
                        children=self.resolve(node.get('Kids',[]))
                        if not isinstance(children,list):raise PDFError('Ungültiger PDF-Zielnamenbaum.')
                        for child in children:
                            result=search(child,level+1)
                            if result is not None:return result
                        return None
                    if root is not None:found=search(root)
                return resolve(found,depth+1) if found is not None else None
            if isinstance(value,dict):return resolve(value.get('D'),depth+1)
            return value if isinstance(value,list) else None
        return resolve(value)

    def toc(self):
        outlines=self.resolve(self.catalog.get('Outlines'))
        if not outlines:return []
        result=[];visited=set();page_numbers={ref:i+1 for i,ref in enumerate(self.page_refs)}
        def walk(ref,level):
            while ref is not None:
                if not isinstance(ref,Ref) or ref in visited or len(visited)>=2000 or level>32:raise PDFError('Ungültiges PDF-Inhaltsverzeichnis.')
                visited.add(ref);node=self.resolve(ref)
                dest=self.resolve(node.get('Dest'))
                if dest is None:
                    action=self.resolve(node.get('A')) or {};dest=self.resolve(action.get('D')) if action.get('S')=='GoTo' else None
                dest=self.destination(dest)
                if dest and isinstance(dest[0],Ref) and dest[0] in page_numbers:result.append([level,pdf_string(self.resolve(node.get('Title'))),page_numbers[dest[0]]])
                if node.get('First'):walk(node['First'],level+1)
                ref=node.get('Next')
        walk(outlines.get('First'),1);return result

    def contents(self,index):
        contents=self.resolve(self.pages[index].get('Contents'))
        if contents is None: return b''
        if not isinstance(contents,list): contents=[contents]
        result=bytearray()
        for item in contents:
            result.extend(self.decode(self.resolve(item))); result.extend(b'\n'); _bounded(result)
        return bytes(result)

    def page(self,index):
        from lumen_pdf_page import Page
        return Page(self,integer(index,0,len(self.pages)-1))

    def __enter__(self):return self
    def __exit__(self,*args):pass
    def __len__(self): return len(self.pages)


def serialize(value,depth=0):
    if depth>MAX_DEPTH: raise PDFError('PDF-Ausgabe zu tief verschachtelt.')
    if isinstance(value,Ref): return f'{integer(value.number,1)} {integer(value.generation,0,65535)} R'.encode()
    if isinstance(value,Name):
        return b'/'+b''.join(bytes([c]) if 33<=c<=126 and c not in DELIMITERS+b'#' else f'#{c:02X}'.encode() for c in value.encode('latin1'))
    if isinstance(value,bytes): return b'<'+value.hex().encode()+b'>'
    if value is None: return b'null'
    if type(value) is bool: return b'true' if value else b'false'
    if type(value) is int: return str(value).encode()
    if type(value) is float:
        if not math.isfinite(value): raise PDFError('Ungültige PDF-Ausgabezahl.')
        from decimal import Decimal
        result=format(Decimal(repr(value)),'f')
        if '.' in result:result=result.rstrip('0').rstrip('.')
        if len(result)>100:raise PDFError('PDF-Ausgabezahl außerhalb des darstellbaren Bereichs.')
        return result.encode()
    if isinstance(value,list): return b'['+b' '.join(serialize(v,depth+1) for v in value)+b']'
    if isinstance(value,dict): return b'<< '+b' '.join(serialize(Name(k),depth+1)+b' '+serialize(v,depth+1) for k,v in value.items())+b' >>'
    if isinstance(value,Stream):
        attrs=dict(value.attrs,Length=len(value.raw))
        return serialize(attrs,depth+1)+b'\nstream\n'+value.raw+b'\nendstream'
    raise PDFError('Nicht serialisierbarer PDF-Wert.')


class Writer:
    def __init__(self):
        self.objects=[]; self.page_refs=[]; self.imported={}; self.pending_pages={}
        self.root=self.add({'Type':Name('Catalog')}); self.tree=self.add({'Type':Name('Pages')})
        self.objects[self.root.number-1]['Pages']=self.tree

    def add(self,value):
        if len(self.objects)>=MAX_OBJECTS: raise PDFError('Zu viele PDF-Ausgabeobjekte.')
        self.objects.append(value); return Ref(len(self.objects))

    def stream(self,data,**attrs):
        _bounded(data)
        return self.add(Stream(dict(attrs,Filter=Name('FlateDecode')),zlib.compress(data)))

    def clone(self,document,value,depth=0):
        if depth>MAX_DEPTH: raise PDFError('PDF-Kopierstruktur zu tief.')
        if isinstance(value,Ref):
            key=(document,value)
            if key not in self.imported:
                new=self.add(None); self.imported[key]=new
                resolved=document.resolve(value)
                if isinstance(resolved,dict) and resolved.get('Type')=='Page': self.pending_pages[key]=new
                else:self.objects[new.number-1]=self.clone(document,resolved,depth+1)
            return self.imported[key]
        if isinstance(value,Stream): return Stream(self.clone(document,value.attrs,depth+1),value.raw)
        if isinstance(value,dict): return {k:self.clone(document,v,depth+1) for k,v in value.items()}
        if isinstance(value,list): return [self.clone(document,v,depth+1) for v in value]
        return value

    def add_page(self,width,height,content=b'',resources=None):
        if not all(type(v) in (int,float) and math.isfinite(v) and 0<v<=1000000 for v in (width,height)): raise PDFError('Ungültige PDF-Ausgabeseite.')
        ref=self.add({'Type':Name('Page'),'Parent':self.tree,'MediaBox':[0,0,width,height],'Resources':resources or {},'Contents':self.stream(content)})
        self.page_refs.append(ref); return self.objects[ref.number-1]

    def copy_page(self,document,index,rotation=0):
        integer(index,0,len(document)-1)
        if rotation not in (0,90,180,270): raise PDFError('Ungültige PDF-Drehung.')
        source=document.pages[index]
        if document.catalog.get('OCProperties'): raise UnsupportedPDF('Seiten mit PDF-Ebenen können noch nicht kopiert werden.')
        if document.catalog.get('OutputIntents'): raise UnsupportedPDF('PDF-Ausgabefarbprofile werden beim Kopieren noch nicht unterstützt.')
        # Preserve page content/resources only. Catalog attachments and actions are
        # deliberately not traversed. Annotation page links use the shared page map.
        key=(document,document.page_refs[index]); ref=self.pending_pages.pop(key,None) or self.add(None);self.imported.setdefault(key,ref)
        page={key:self.clone(document,value) for key,value in source.items() if key in ('MediaBox','CropBox','TrimBox','BleedBox','ArtBox','UserUnit','Resources','Contents','Group') and value is not None}
        page.update(Type=Name('Page'),Parent=self.tree,Rotate=(source.get('Rotate') or 0)+rotation)
        page['Rotate']%=360
        annotations=document.resolve(source.get('Annots',[]))
        if not isinstance(annotations,list): raise PDFError('Ungültige PDF-Anmerkungsliste.')
        if annotations:
            page['Annots']=[]
            for annotation in annotations:
                value=document.resolve(annotation)
                if not isinstance(value,dict): raise PDFError('Ungültige PDF-Anmerkung.')
                action=document.resolve(value.get('A')) or {};destination=document.resolve(value.get('Dest'))
                if isinstance(action,dict) and action.get('S')=='GoTo':destination=document.resolve(action.get('D'))
                if isinstance(destination,(Name,bytes)):
                    destination=document.destination(destination)
                    if destination is None:raise UnsupportedPDF('Benanntes PDF-Seitenziel fehlt.')
                    value=dict(value)
                    if action.get('S')=='GoTo':value['A']=dict(action,D=destination)
                    else:value['Dest']=destination
                page['Annots'].append(self.add(self.clone(document,{k:v for k,v in value.items() if k not in ('P','Parent')})))
        self.objects[ref.number-1]=page; self.page_refs.append(ref); return page

    def bytes(self):
        if not self.page_refs: raise PDFError('Keine PDF-Ausgabeseiten.')
        if self.pending_pages: raise UnsupportedPDF('PDF-Verweise führen auf nicht ausgewählte Seiten; diese Seiten ebenfalls exportieren.')
        self.objects[self.tree.number-1].update(Kids=self.page_refs,Count=len(self.page_refs))
        output=bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'); offsets=[]
        for number,value in enumerate(self.objects,1):
            offsets.append(len(output)); output.extend(f'{number} 0 obj\n'.encode()+serialize(value)+b'\nendobj\n')
            if len(output)>MAX_FILE: raise PDFError('PDF-Ausgabe größer als 512 MiB.')
        position=len(output); output.extend(f'xref\n0 {len(offsets)+1}\n0000000000 65535 f \n'.encode())
        for offset in offsets: output.extend(f'{offset:010d} 00000 n \n'.encode())
        output.extend(b'trailer\n'+serialize({'Size':len(offsets)+1,'Root':self.root})+f'\nstartxref\n{position}\n%%EOF\n'.encode())
        return bytes(output)

    def save(self,target):
        target=Path(target)
        if target.suffix.lower()!='.pdf': raise PDFError('Als PDF speichern.')
        if os.path.lexists(target): raise FileExistsError('PDF-Zieldatei existiert bereits.')
        data=self.bytes(); check=Document(data)
        if len(check)!=len(self.page_refs): raise PDFError('PDF-Ausgabeprüfung fehlgeschlagen.')
        with tempfile.NamedTemporaryFile(prefix='.lumen-pdf-',suffix='.pdf',dir=target.parent,delete=False) as stream:
            staged=Path(stream.name)
            try:
                stream.write(data); stream.flush(); os.fsync(stream.fileno()); os.link(staged,target)
            finally: staged.unlink(missing_ok=True)
        return str(target)

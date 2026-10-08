"""PDF image samples, decode arrays, palettes and masks; native bitmap codecs only."""
import math
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QColorSpace, QImage, QImageReader
from lumen_pdf import Name, Stream, PDFError, integer
from lumen_pdf_color import ColorSpace, values


def samples(raw,width,height,channels,bits):
    stride=(width*channels*bits+7)//8
    if len(raw)!=height*stride:raise PDFError('PDF-Pixeldaten und Größe stimmen nicht überein.')
    maximum=(1<<bits)-1
    for y in range(height):
        row=raw[y*stride:(y+1)*stride]
        for x in range(width):
            pixel=[]
            for channel in range(channels):
                bit=(x*channels+channel)*bits;offset=bit//8
                if bits==16:value=int.from_bytes(row[offset:offset+2],'big')
                else:value=(row[offset]>>(8-bits-bit%8))&maximum
                pixel.append(value)
            yield pixel


def image(page,stream,resources,fill,active=None):
    document=page.document;attrs={k:document.resolve(v) for k,v in stream.attrs.items()};active=set() if active is None else active
    if id(stream) in active or len(active)>16:raise PDFError('Zyklische PDF-Bildmaske.')
    active=active|{id(stream)}
    w=integer(attrs.get('Width'),1,20000);h=integer(attrs.get('Height'),1,20000)
    page.image_pixels+=w*h
    if w*h>40_000_000 or page.image_pixels>80_000_000:raise PDFError('PDF-Bildbudget überschritten.')
    stencil=attrs.get('ImageMask',False)
    if type(stencil) is not bool:raise PDFError('Ungültige PDF-Bildmaske.')
    bits=attrs.get('BitsPerComponent',1 if stencil else None)
    if bits not in (1,2,4,8,16) or type(bits) is not int or stencil and bits!=1:raise PDFError('Ungültige PDF-Bittiefe.')
    space=ColorSpace(document,Name('DeviceGray') if stencil else attrs.get('ColorSpace'),resources)
    channels=space.components;decode=values(attrs.get('Decode',space.ranges()),2*channels);maximum=(1<<bits)-1
    filters=attrs.get('Filter') or [];filters=[filters] if isinstance(filters,Name) else filters
    if not isinstance(filters,list) or len(filters)>8:raise PDFError('Ungültige PDF-Bildfilterkette.')
    filters=[document.resolve(f) for f in filters];terminal=filters[-1] if filters else None
    raw=None;result=None
    if terminal in ('DCTDecode','DCT','JPXDecode'):
        params=attrs.get('DecodeParms') or [];params=[params] if isinstance(params,dict) else params
        prefix=dict(attrs,Filter=filters[:-1],DecodeParms=params[:-1])
        encoded=document.decode(Stream(prefix,stream.raw))
        buffer=QBuffer();buffer.setData(QByteArray(encoded));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader=QImageReader(buffer,b'JP2' if terminal=='JPXDecode' else b'JPEG');size=reader.size()
        if size.width()!=w or size.height()!=h:raise PDFError('PDF-Bildkopf und Größe stimmen nicht überein.')
        native=reader.read()
        if native.isNull():raise PDFError('PDF-Bild konnte nicht dekodiert werden.')
        fmt={1:QImage.Format.Format_Grayscale8,3:QImage.Format.Format_RGB888,4:QImage.Format.Format_CMYK8888}.get(channels)
        if fmt is None:raise PDFError('Ungültige JPEG-/JPX-Farbkomponenten.')
        native=native.convertToFormat(fmt);view=bytes(native.constBits());raw=b''.join(view[y*native.bytesPerLine():y*native.bytesPerLine()+w*channels] for y in range(h))
        # Native JPEG codecs normalize Adobe's inverted CMYK samples. PDF applies
        # its own Decode array, so restore the encoded component convention first.
        if terminal in ('DCTDecode','DCT') and channels==4 and b'Adobe' in encoded[:65536]:raw=raw.translate(bytes(255-v for v in range(256)))
        bits=8;maximum=255
    else:raw=document.decode(stream)
    stride=(w*channels*bits+7)//8
    if len(raw)!=h*stride:raise PDFError('PDF-Pixeldaten und Größe stimmen nicht überein.')
    if stencil:
        result=QImage(raw,w,h,stride,QImage.Format.Format_Mono).copy()
        result.setColorTable([fill.rgba() if decode[i]==0 else QColor(0,0,0,0).rgba() for i in range(2)])
        if decode not in ([0,1],[1,0]):raise PDFError('Ungültige PDF-Schablonendekodierung.')
        result=result.convertToFormat(QImage.Format.Format_ARGB32)
    elif bits==8 and decode==[0,1]*channels and space.kind in ('DeviceRGB','RGB','DeviceGray','G','DeviceCMYK','CMYK','ICCBased'):
        fmt={1:QImage.Format.Format_Grayscale8,3:QImage.Format.Format_RGB888,4:QImage.Format.Format_CMYK8888}[channels]
        result=QImage(raw,w,h,stride,fmt).copy()
        if space.profile:
            result.setColorSpace(space.profile);result=result.convertedToColorSpace(QColorSpace.NamedColorSpace.SRgb)
            if result.isNull():raise PDFError('PDF-Bildprofil konnte nicht angewendet werden.')
        result=result.convertToFormat(QImage.Format.Format_ARGB32)
    else:
        pixels=bytearray()
        for pixel in samples(raw,w,h,channels,bits):
            decoded=[decode[2*i]+v/maximum*(decode[2*i+1]-decode[2*i]) for i,v in enumerate(pixel)]
            # Indexed default Decode uses the sample's integer index, regardless
            # of the palette's highest used entry (ISO 32000-1 table 89).
            if space.lookup is not None and 'Decode' not in attrs:decoded=pixel
            pixels.extend(round(max(0,min(1,c))*255) for c in space.rgb(decoded))
        result=QImage(bytes(pixels),w,h,w*3,QImage.Format.Format_RGB888).copy().convertToFormat(QImage.Format.Format_ARGB32)
    mask=attrs.get('SMask');soft=isinstance(mask,Stream)
    if not soft:mask=attrs.get('Mask')
    if isinstance(mask,Stream):
        if soft and document.resolve(mask.attrs.get('ColorSpace')) not in (Name('DeviceGray'),Name('G')):raise PDFError('PDF-Weichmaske benötigt Graustufen.')
        overlay=image(page,mask,resources,QColor('black'),active)
        if soft:alpha=overlay.convertToFormat(QImage.Format.Format_Grayscale8)
        else:alpha=overlay.convertToFormat(QImage.Format.Format_Alpha8)
        alpha=alpha.scaled(w,h,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation if attrs.get('Interpolate') else Qt.TransformationMode.FastTransformation)
        matte=document.resolve(mask.attrs.get('Matte')) if soft else None
        if matte is not None:
            backdrop=space.rgb(values(matte,channels))
            for y in range(h):
                for x in range(w):
                    a=alpha.pixelColor(x,y).redF();pixel=result.pixelColor(x,y)
                    if a>0:result.setPixelColor(x,y,QColor.fromRgbF(*(max(0,min(1,(c-(1-a)*b)/a)) for c,b in zip((pixel.redF(),pixel.greenF(),pixel.blueF()),backdrop))))
        result.setAlphaChannel(alpha)
    elif isinstance(mask,list):
        values(mask,channels*2);alpha=bytearray()
        for pixel in samples(raw,w,h,channels,bits):alpha.append(0 if all(mask[2*i]<=v<=mask[2*i+1] for i,v in enumerate(pixel)) else 255)
        result.setAlphaChannel(QImage(bytes(alpha),w,h,w,QImage.Format.Format_Grayscale8).copy())
    elif mask not in (None,Name('None')):raise PDFError('Ungültige PDF-Bildmaske.')
    return result

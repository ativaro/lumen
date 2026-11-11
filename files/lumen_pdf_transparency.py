"""PDF compositing with bounded native RGBA surfaces at the requested resolution."""
from copy import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QColor, QTransform
from lumen_pdf import Name, PDFError, UnsupportedPDF, Stream
from lumen_pdf_color import ColorSpace, values, function

BLENDS={name:getattr(QPainter.CompositionMode,'CompositionMode_'+qt) for name,qt in
        [('Normal','SourceOver'),('Compatible','SourceOver'),*[(n,n) for n in
        ('Multiply','Screen','Overlay','Darken','Lighten','ColorDodge','ColorBurn','HardLight','SoftLight','Difference','Exclusion')]]}


def gray_color(color):
    level=.30*color.redF()+.59*color.greenF()+.11*color.blueF()
    return QColor.fromRgbF(level,level,level,color.alphaF())


def luminance(raw):
    """(30 R + 59 G + 11 B + 50) // 100 for every RGBA pixel, as whole-buffer integer arithmetic instead of a loop."""
    count=len(raw)//4
    def lanes(channel):
        wide=bytearray(count*4);wide[0::4]=channel;return int.from_bytes(wide,'little')
    # Each pixel has a 32-bit lane; 167773 / 2**24 is 1/100 closely enough to be exact for these sums.
    total=(30*lanes(raw[0::4])+59*lanes(raw[1::4])+11*lanes(raw[2::4])+50*lanes(b'\1'*count))*167773
    return total.to_bytes(count*4,'little')[3::4]


def gray_image(image):
    source=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=bytes(source.constBits())
    data=bytearray(len(raw))
    data[0::4]=data[1::4]=data[2::4]=luminance(raw)
    data[3::4]=raw[3::4]
    return QImage(bytes(data),image.width(),image.height(),image.width()*4,QImage.Format.Format_RGBA8888).copy()


def group(document,reference):
    attrs=document.resolve(reference)
    if attrs is None:return None
    if not isinstance(attrs,dict) or attrs.get('S')!='Transparency':raise PDFError('Ungültige PDF-Transparenzgruppe.')
    if any(type(attrs.get(k,False)) is not bool for k in ('I','K')):raise PDFError('Ungültige PDF-Gruppenattribute.')
    space=document.resolve(attrs.get('CS',Name('DeviceRGB')))
    if space not in (Name('DeviceRGB'),Name('DeviceGray')):raise UnsupportedPDF('PDF-Gruppenfarbraum noch nicht unterstützt: '+str(space))
    return attrs


def surface(page,painter,background=Qt.GlobalColor.transparent):
    device=painter.device();w,h=device.width(),device.height()
    page.effect_pixels+=w*h
    if w*h<=0 or page.effect_pixels>160_000_000:raise PDFError('PDF-Transparenzbudget überschritten.')
    image=QImage(w,h,QImage.Format.Format_ARGB32_Premultiplied);image.fill(background)
    if image.isNull():raise PDFError('PDF-Transparenzfläche konnte nicht angelegt werden.')
    output=QPainter(image);output.setRenderHints(painter.renderHints());output.setTransform(painter.transform())
    if painter.hasClipping():output.setClipPath(painter.clipPath())
    return image,output


def soft_mask(page,painter,entry):
    attrs,transform,resources,inherited=entry;document=page.document
    form=document.resolve(attrs.get('G'))
    if not isinstance(form,Stream) or form.attrs.get('Subtype')!='Form':raise PDFError('PDF-Weichmaskengruppe fehlt.')
    settings=group(document,form.attrs.get('Group')) or {}  # a mask form without its group entry uses the defaults
    subtype=attrs.get('S')
    if subtype not in ('Alpha','Luminosity'):raise PDFError('Ungültige PDF-Weichmaske.')
    space=ColorSpace(document,settings.get('CS',Name('DeviceRGB')),resources)
    background=QColor(0,0,0,0) if subtype=='Alpha' else space.color(values(document.resolve(attrs.get('BC',[0]*space.components)),space.components))
    image,output=surface(page,painter,background)
    collect=page.collect;page.collect=False
    try:
        output.setTransform(transform)
        state=copy(inherited);state.update(fillalpha=1,strokealpha=1,blend=Name('Normal'),mask=None)
        page._form(form,resources,output,set(),0,state,mask_group=True)
    finally:page.collect=collect;output.end()
    rgba=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=bytes(rgba.constBits())
    if subtype=='Alpha':alpha=raw[3::4]
    else:alpha=luminance(raw)
    transfer=document.resolve(attrs.get('TR',Name('Identity')))
    if transfer!='Identity':
        table=bytes(round(max(0,min(1,function(document,transfer,[v/255])[0]))*255) for v in range(256));alpha=alpha.translate(table)
    return QImage(alpha,image.width(),image.height(),image.width(),QImage.Format.Format_Grayscale8).copy()


def paint(page,painter,state,slot,draw,isolated=False):
    if page.hidden:return  # content on a layer that is switched off
    opacity=state[slot+'alpha'];blend=state['blend'];mask=state['mask']
    # In a knockout group an opaque object already replaces what lies under it; only a transparent one needs the group's backdrop.
    knock=state.get('knockout')
    replacing=knock is not None and (opacity<1 or blend not in ('Normal','Compatible') or bool(mask))
    if mask or isolated or replacing:page.effects=True
    if page.collect or not (mask or isolated or replacing):
        painter.save()
        try:painter.setOpacity(opacity);painter.setCompositionMode(BLENDS[blend]);draw(painter)
        finally:painter.restore()
        return
    page.effect_depth+=1
    if page.effect_depth>16:raise PDFError('PDF-Transparenz zu tief verschachtelt.')
    try:
        image,output=surface(page,painter)
        try:draw(output)
        finally:output.end()
        shape=image.copy() if replacing and mask else image
        if mask:
            alpha=soft_mask(page,painter,mask)
            # setAlphaChannel multiplies the existing alpha, preserving holes.
            image.setAlphaChannel(alpha)
        if replacing:
            # The object is composited with the group's initial backdrop, and that result replaces
            # everything drawn so far inside the object's shape.
            page.effect_pixels+=image.width()*image.height()
            if page.effect_pixels>160_000_000:raise PDFError('PDF-Transparenzbudget überschritten.')
            Mode=QPainter.CompositionMode
            result=knock['backdrop'].copy() if knock.get('backdrop') is not None else QImage(image.size(),image.format())
            if knock.get('backdrop') is None:result.fill(Qt.GlobalColor.transparent)
            composer=QPainter(result)
            try:
                composer.setOpacity(opacity);composer.setCompositionMode(BLENDS[blend]);composer.drawImage(0,0,image)
                composer.setOpacity(1);composer.setCompositionMode(Mode.CompositionMode_DestinationIn);composer.drawImage(0,0,shape)
            finally:composer.end()
            painter.save()
            try:
                painter.resetTransform()
                painter.setCompositionMode(Mode.CompositionMode_DestinationOut);painter.drawImage(0,0,shape)
                painter.setCompositionMode(Mode.CompositionMode_Plus);painter.drawImage(0,0,result)
            finally:painter.restore()
            return
        painter.save()
        try:
            painter.resetTransform();painter.setOpacity(opacity);painter.setCompositionMode(BLENDS[blend]);painter.drawImage(0,0,image)
        finally:painter.restore()
    finally:page.effect_depth-=1

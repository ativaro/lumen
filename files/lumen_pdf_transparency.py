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


def gray_image(image):
    source=image.convertToFormat(QImage.Format.Format_RGBA8888);raw=bytes(source.constBits())
    data=bytearray(len(raw))
    data[0::4]=data[1::4]=data[2::4]=bytes((30*r+59*g+11*b+50)//100 for r,g,b in zip(raw[0::4],raw[1::4],raw[2::4]))
    data[3::4]=raw[3::4]
    return QImage(bytes(data),image.width(),image.height(),image.width()*4,QImage.Format.Format_RGBA8888).copy()


def group(document,reference):
    attrs=document.resolve(reference)
    if attrs is None:return None
    if not isinstance(attrs,dict) or attrs.get('S')!='Transparency':raise PDFError('Ungültige PDF-Transparenzgruppe.')
    if any(type(attrs.get(k,False)) is not bool for k in ('I','K')):raise PDFError('Ungültige PDF-Gruppenattribute.')
    if attrs.get('K'):raise UnsupportedPDF('PDF-Knockout-Gruppe noch nicht unterstützt.')
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
    settings=group(document,form.attrs.get('Group'))
    if settings is None:raise PDFError('PDF-Weichmaske ohne Transparenzgruppe.')
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
    else:alpha=bytes((30*r+59*g+11*b+50)//100 for r,g,b in zip(raw[0::4],raw[1::4],raw[2::4]))
    transfer=document.resolve(attrs.get('TR',Name('Identity')))
    if transfer!='Identity':
        table=bytes(round(max(0,min(1,function(document,transfer,[v/255])[0]))*255) for v in range(256));alpha=alpha.translate(table)
    return QImage(alpha,image.width(),image.height(),image.width(),QImage.Format.Format_Grayscale8).copy()


def paint(page,painter,state,slot,draw,isolated=False):
    opacity=state[slot+'alpha'];blend=state['blend'];mask=state['mask']
    if mask or isolated:page.effects=True
    if page.collect or not (mask or isolated):
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
        if mask:
            alpha=soft_mask(page,painter,mask)
            # setAlphaChannel multiplies the existing alpha, preserving holes.
            image.setAlphaChannel(alpha)
        painter.save()
        try:
            painter.resetTransform();painter.setOpacity(opacity);painter.setCompositionMode(BLENDS[blend]);painter.drawImage(0,0,image)
        finally:painter.restore()
    finally:page.effect_depth-=1

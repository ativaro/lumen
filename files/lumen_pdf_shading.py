"""PDF axial/radial shading functions mapped to native vector gradients."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QLinearGradient, QRadialGradient, QPainterPath, QTransform
from lumen_pdf import PDFError, UnsupportedPDF
from lumen_pdf_color import ColorSpace, function, values


def brush(document, reference, resources, bounds):
    attrs=document.resolve(reference)
    if not isinstance(attrs,dict):raise PDFError('PDF-Verlauf fehlt.')
    kind=attrs.get('ShadingType');coords=list(document.resolve(attrs.get('Coords',[])))
    values(coords,4 if kind==2 else 6)
    space=ColorSpace(document,attrs.get('ColorSpace'),resources)
    domain=values(document.resolve(attrs.get('Domain',[0,1])),2)
    if domain[0]>=domain[1]:raise PDFError('Ungültiger PDF-Verlaufsbereich.')
    extend=document.resolve(attrs.get('Extend',[False,False]))
    if not isinstance(extend,list) or len(extend)!=2 or any(type(v) is not bool for v in extend):raise PDFError('Ungültige PDF-Verlaufsfortsetzung.')
    clip=QPainterPath();clip.addRect(bounds)
    if kind==2:
        x0,y0,x1,y1=coords;dx,dy=x1-x0,y1-y0
        if dx==dy==0:raise PDFError('PDF-Verlauf hat keine Achse.')
        gradient=QLinearGradient(x0,y0,x1,y1)
        basis=QTransform(dx,dy,-dy,dx,x0,y0);inverse,ok=basis.inverted()
        if not ok:raise PDFError('Ungültige PDF-Verlaufsachse.')
        region=inverse.mapRect(bounds).adjusted(-1,-1,1,1)
        if not extend[0]:region.setLeft(max(region.left(),0))
        if not extend[1]:region.setRight(min(region.right(),1))
        clip=QPainterPath()
        if region.width()>0:clip.addRect(region);clip=basis.map(clip)
    elif kind==3:
        x0,y0,r0,x1,y1,r1=coords
        if min(r0,r1)<0 or coords[:3]==coords[3:]:raise PDFError('Ungültige PDF-Verlaufskreise.')
        gradient=QRadialGradient(QPointF(x1,y1),r1,QPointF(x0,y0),r0)
        if (x1-x0)**2+(y1-y0)**2 <= (r1-r0)**2:
            small=QPainterPath();small.addEllipse(QPointF(x0,y0),r0,r0)
            large=QPainterPath();large.addEllipse(QPointF(x1,y1),r1,r1)
            if r1>=r0:
                if not extend[0]:clip=clip.subtracted(small)
                if not extend[1]:clip=clip.intersected(large)
            else:
                if not extend[0]:clip=clip.intersected(small)
                if not extend[1]:clip=clip.subtracted(large)
        elif not all(extend):raise UnsupportedPDF('Nicht eingeschlossener radialer PDF-Verlauf ohne Fortsetzung.')
    else:raise UnsupportedPDF('PDF-Verlaufstyp noch nicht unterstützt: '+str(kind))
    # Sample the colour function and include stitching boundaries so plateaus
    # and discontinuities keep their positions in the native gradient table.
    stops={i/255 for i in range(256)}
    spec=document.resolve(attrs.get('Function'))
    if isinstance(spec,dict) and spec.get('FunctionType')==3:
        for boundary in values(document.resolve(spec.get('Bounds',[]))):
            t=(boundary-domain[0])/(domain[1]-domain[0])
            if 0<t<1:stops.update((max(0,t-1e-7),t))
    for t in sorted(stops):gradient.setColorAt(t,space.color(function(document,attrs.get('Function'),[domain[0]+t*(domain[1]-domain[0])])))
    if 'BBox' in attrs:
        from lumen_pdf_page import rectangle
        box=QPainterPath();box.addRect(rectangle(document.resolve(attrs['BBox'])));clip=clip.intersected(box)
    return QBrush(gradient),clip

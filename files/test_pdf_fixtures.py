"""Small PDF test documents built from explicit format operators, without a PDF library."""
from lumen_pdf import Writer,Name,serialize


def document(texts=('',),size=(595,842),font_size=11,position=(50,80),rotations=None,toc=None):
    writer=Writer();font=writer.add({'Type':Name('Font'),'Subtype':Name('Type1'),'BaseFont':Name('Helvetica'),'Encoding':Name('WinAnsiEncoding')})
    for index,text in enumerate(texts):
        content=b'BT /F1 '+serialize(font_size)+b' Tf '+serialize(position[0])+b' '+serialize(size[1]-position[1])+b' Td '+serialize(text.encode('cp1252'))+b' Tj ET\n' if text else b''
        page=writer.add_page(*size,content,{'Font':{'F1':font}})
        if rotations:page['Rotate']=rotations[index]
    if toc:
        tree=writer.add({'Type':Name('Outlines')});refs=[writer.add({}) for _ in toc]
        for index,((level,title,page),ref) in enumerate(zip(toc,refs)):
            assert level==1,'This fixture only needs top-level outlines'
            value=writer.objects[ref.number-1];value.update(Title=title.encode(),Parent=tree,Dest=[writer.page_refs[page-1],Name('Fit')])
            if index:value['Prev']=refs[index-1]
            if index+1<len(refs):value['Next']=refs[index+1]
        writer.objects[tree.number-1].update(First=refs[0],Last=refs[-1],Count=len(refs));writer.objects[writer.root.number-1]['Outlines']=tree
    return writer


def add_content(writer,page,content):
    old=page.get('Contents');page['Contents']=(list(old) if isinstance(old,list) else [old] if old else [])+[writer.stream(content)]


def add_image(writer,page,pixels,width,height,rect):
    ref=writer.stream(pixels,Type=Name('XObject'),Subtype=Name('Image'),Width=width,Height=height,ColorSpace=Name('DeviceRGB'),BitsPerComponent=8)
    page['Resources'].setdefault('XObject',{})['I1']=ref;x0,y0,x1,y1=rect
    add_content(writer,page,b'q '+b' '.join(serialize(n) for n in (x1-x0,0,0,y1-y0,x0,page['MediaBox'][3]-y1))+b' cm /I1 Do Q\n')


def add_link(writer,page):
    page.setdefault('Annots',[]).append(writer.add({'Type':Name('Annot'),'Subtype':Name('Link'),'Rect':[40,435,125,458],'Border':[0,0,0],'A':{'S':Name('URI'),'URI':b'https://example.org'}}))

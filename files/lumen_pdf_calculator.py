"""Bounded PDF type-4 calculator functions (no filesystem, loops or PostScript VM)."""
import math
import re
from lumen_pdf import PDFError


def calculate(data,inputs):
    if len(data)>1_000_000:raise PDFError('PDF-Rechenfunktion zu groß.')
    tokens=re.findall(rb'%[^\r\n]*|[{}]|[^\x00\t\n\f\r {}]+',data);position=0
    def parse(depth=0):
        nonlocal position
        if depth>32:raise PDFError('PDF-Rechenfunktion zu tief.')
        procedure=[]
        while position<len(tokens):
            token=tokens[position];position+=1
            if token.startswith(b'%'):continue
            if token==b'}':
                if not depth:raise PDFError('Unerwartetes Ende einer PDF-Rechenfunktion.')
                return procedure
            if token==b'{':procedure.append(parse(depth+1))
            else:
                try:value=float(token) if b'.' in token or b'e' in token.lower() else int(token)
                except ValueError:value=token.decode('ascii')
                procedure.append(value)
        if depth:raise PDFError('PDF-Rechenfunktion nicht geschlossen.')
        return procedure
    code=parse()
    if len(code)!=1 or not isinstance(code[0],list):raise PDFError('PDF-Rechenfunktion benötigt einen Block.')
    stack=list(inputs);steps=0
    def pop():
        if not stack:raise PDFError('PDF-Rechenstack ist leer.')
        return stack.pop()
    def numeric():
        value=pop()
        if type(value) not in (int,float) or not math.isfinite(value):raise PDFError('PDF-Rechenzahl erwartet.')
        return value
    def whole():
        value=pop()
        if type(value) is not int:raise PDFError('Ganze PDF-Rechenzahl erwartet.')
        return value
    def execute(code,depth=0):
        nonlocal steps
        if depth>32:raise PDFError('PDF-Rechenfunktion zu tief.')
        for op in code:
            steps+=1
            if steps>10000 or len(stack)>100:raise PDFError('PDF-Rechenbudget überschritten.')
            if isinstance(op,(int,float,list)):stack.append(op);continue
            if op in ('true','false'):stack.append(op=='true')
            elif op in ('abs','ceiling','floor','ln','log','neg','round','sin','cos','sqrt','truncate','cvi','cvr'):
                a=numeric();stack.append({'abs':abs,'ceiling':math.ceil,'floor':math.floor,'ln':math.log,'log':math.log10,'neg':lambda x:-x,'round':lambda x:math.floor(x+.5),'sin':lambda x:math.sin(math.radians(x)),'cos':lambda x:math.cos(math.radians(x)),'sqrt':math.sqrt,'truncate':math.trunc,'cvi':int,'cvr':float}[op](a))
            elif op in ('add','sub','mul','div','idiv','mod','exp','atan'):
                b=numeric();a=numeric();stack.append({'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,'div':lambda:a/b,'idiv':lambda:math.trunc(a/b),'mod':lambda:a-math.trunc(a/b)*b,'exp':lambda:math.pow(a,b),'atan':lambda:math.degrees(math.atan2(a,b))%360}[op]())
            elif op in ('eq','ne','gt','ge','lt','le'):
                b=pop();a=pop();stack.append({'eq':lambda:a==b,'ne':lambda:a!=b,'gt':lambda:a>b,'ge':lambda:a>=b,'lt':lambda:a<b,'le':lambda:a<=b}[op]())
            elif op in ('and','or','xor'):
                b=pop();a=pop()
                if type(a) is not type(b) or type(a) not in (bool,int):raise PDFError('Ungültige PDF-Bitoperation.')
                stack.append({'and':lambda:a&b,'or':lambda:a|b,'xor':lambda:a^b}[op]())
            elif op=='not':
                a=pop()
                if type(a) not in (bool,int):raise PDFError('Ungültige PDF-Negation.')
                stack.append(not a if type(a) is bool else ~a)
            elif op=='bitshift':
                shift=whole();a=whole()&0xffffffff
                stack.append(0 if abs(shift)>=32 else (a<<shift)&0xffffffff if shift>=0 else a>>-shift)
            elif op in ('if','ifelse'):
                alternate=pop() if op=='ifelse' else [];procedure=pop();condition=pop()
                if type(condition) is not bool or not isinstance(procedure,list) or not isinstance(alternate,list):raise PDFError('Ungültige PDF-Rechenbedingung.')
                execute(procedure if condition else alternate,depth+1)
            elif op=='dup':value=pop();stack.extend([value,value])
            elif op=='exch':b=pop();a=pop();stack.extend([b,a])
            elif op=='pop':pop()
            elif op in ('copy','index'):
                n=whole()
                if n<0 or n>len(stack)-(op=='index'):raise PDFError('Ungültiger PDF-Stackindex.')
                if op=='index':stack.append(stack[-n-1])
                elif n:stack.extend(stack[-n:])
            elif op=='roll':
                count=whole();n=whole()
                if not 0<=n<=len(stack):raise PDFError('Ungültige PDF-Stackrotation.')
                if n:
                    count%=n
                    if count:stack[-n:]=stack[-count:]+stack[-n:-count]
            else:raise PDFError('Unbekannter PDF-Rechenoperator: '+op)
    try:execute(code[0])
    except (ValueError,OverflowError,ZeroDivisionError,TypeError) as exc:raise PDFError('Ungültige PDF-Rechenfunktion.') from exc
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in stack):raise PDFError('Ungültige PDF-Rechenausgabe.')
    return stack

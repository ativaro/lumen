"""PDF standard security handlers (R2–R6), implemented from ISO 32000.

OpenSSL supplies only the general AES/RC4 primitives, through its public EVP API.
PDF key derivation/object encryption/filter selection are Lumen code.
https://pdf-issues.pdfa.org/32000-2-2020/clause07.html#764-standard-security-handler
https://docs.openssl.org/3.0/man3/EVP_EncryptInit/
"""
import ctypes as C
import ctypes.util
import hashlib
import hmac
import stringprep
import unicodedata
from lumen_pdf import PDFError, UnsupportedPDF, Stream, Name, integer

PAD=bytes.fromhex('28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a')
_library=None
_providers=[]


class PasswordRequired(PDFError):
    pass


def crypto(name,key,data,iv=None,encrypt=False,padding=False):
    """Bounded EVP call; no password, key, or plaintext is passed to a process."""
    global _library
    if name not in ('rc4','aes-128-cbc','aes-256-cbc','aes-256-ecb') or len(data)>512*1024**2:
        raise PDFError('Ungültiger PDF-Kryptoauftrag.')
    expected={'aes-128-cbc':16,'aes-256-cbc':32,'aes-256-ecb':32}
    if name=='rc4':
        if not 5<=len(key)<=16: raise PDFError('Ungültiger PDF-RC4-Schlüssel.')
    elif len(key)!=expected[name] or ('cbc' in name and (not isinstance(iv,bytes) or len(iv)!=16)):
        raise PDFError('Ungültiger PDF-AES-Schlüssel oder Initialisierungsvektor.')
    if _library is None:
        path=ctypes.util.find_library('crypto')
        if not path: raise UnsupportedPDF('OpenSSL fehlt für verschlüsselte PDFs.')
        lib=C.CDLL(path); ptr=C.c_void_p; integer_type=C.c_int
        declarations={
            'EVP_CIPHER_CTX_new':([],ptr),'EVP_CIPHER_CTX_free':([ptr],None),
            'EVP_get_cipherbyname':([C.c_char_p],ptr),
            'EVP_CipherInit_ex':([ptr,ptr,ptr,ptr,ptr,integer_type],integer_type),
            'EVP_CIPHER_CTX_set_key_length':([ptr,integer_type],integer_type),
            'EVP_CIPHER_CTX_set_padding':([ptr,integer_type],integer_type),
            'EVP_CipherUpdate':([ptr,ptr,C.POINTER(integer_type),ptr,integer_type],integer_type),
            'EVP_CipherFinal_ex':([ptr,ptr,C.POINTER(integer_type)],integer_type),
            'OSSL_PROVIDER_load':([ptr,C.c_char_p],ptr),
        }
        for symbol,(arguments,result) in declarations.items():
            method=getattr(lib,symbol); method.argtypes=arguments; method.restype=result
        _providers.append(lib.OSSL_PROVIDER_load(None,b'default')); _library=lib
    lib=_library
    if name=='rc4' and len(_providers)==1: _providers.append(lib.OSSL_PROVIDER_load(None,b'legacy'))
    cipher=lib.EVP_get_cipherbyname(name.encode()); ctx=lib.EVP_CIPHER_CTX_new()
    if not cipher or not ctx:
        if ctx:lib.EVP_CIPHER_CTX_free(ctx)
        raise UnsupportedPDF('PDF-Verschlüsselungsverfahren ist in OpenSSL nicht verfügbar.')
    try:
        def checked(result):
            if result!=1: raise PDFError('PDF-Entschlüsselung fehlgeschlagen oder Daten beschädigt.')
        checked(lib.EVP_CipherInit_ex(ctx,cipher,None,None,None,int(encrypt)))
        checked(lib.EVP_CIPHER_CTX_set_key_length(ctx,len(key)))
        checked(lib.EVP_CIPHER_CTX_set_padding(ctx,int(padding)))
        checked(lib.EVP_CipherInit_ex(ctx,None,None,key,iv,int(encrypt)))
        output=C.create_string_buffer(len(data)+32); used=C.c_int(); tail=C.c_int()
        checked(lib.EVP_CipherUpdate(ctx,output,C.byref(used),data,len(data)))
        checked(lib.EVP_CipherFinal_ex(ctx,C.byref(output,used.value),C.byref(tail)))
        return output.raw[:used.value+tail.value]
    finally: lib.EVP_CIPHER_CTX_free(ctx)


def password_bytes(password,revision):
    if not isinstance(password,str) or len(password)>10000: raise PDFError('PDF-Passwort zu lang oder ungültig.')
    if revision<5:
        try: return password.encode('latin1')[:32]
        except UnicodeError: raise PasswordRequired('PDF-Passwort ist nicht korrekt.')
    if revision==6:
        password=''.join(' ' if stringprep.in_table_c12(c) else c for c in password if not stringprep.in_table_b1(c))
        password=unicodedata.ucd_3_2_0.normalize('NFKC',password)
        prohibited=(stringprep.in_table_a1,stringprep.in_table_c12,stringprep.in_table_c21,stringprep.in_table_c22,stringprep.in_table_c3,stringprep.in_table_c4,stringprep.in_table_c5,stringprep.in_table_c6,stringprep.in_table_c7,stringprep.in_table_c8,stringprep.in_table_c9)
        if any(test(c) for c in password for test in prohibited): raise PasswordRequired('PDF-Passwort enthält unzulässige Zeichen.')
        if any(stringprep.in_table_d1(c) for c in password) and (any(stringprep.in_table_d2(c) for c in password) or not stringprep.in_table_d1(password[0]) or not stringprep.in_table_d1(password[-1])):
            raise PasswordRequired('Ungültige PDF-Passwortrichtung.')
    return password.encode('utf-8')[:127]


def hash6(password,salt,user=b'',revision=6):
    result=hashlib.sha256(password+salt+user).digest()
    if revision==5: return result
    rounds=0; end=0
    while rounds<64 or end>rounds-32:
        block=(password+result+user)*64
        encoded=crypto('aes-128-cbc',result[:16],block,result[16:32],encrypt=True)
        result=(hashlib.sha256,hashlib.sha384,hashlib.sha512)[sum(encoded[:16])%3](encoded).digest()
        rounds+=1; end=encoded[-1]
        if rounds>288: raise PDFError('PDF-Passworthash überschreitet sein Budget.')
    return result[:32]


class Security:
    def __init__(self,attrs,identifiers,password):
        if not isinstance(attrs,dict) or attrs.get('Filter')!='Standard': raise UnsupportedPDF('PDF-Sicherheitsverfahren wird nicht unterstützt.')
        self.attrs=attrs; self.revision=integer(attrs.get('R'),2,6); self.version=attrs.get('V'); self.metadata=attrs.get('EncryptMetadata',True)
        self.methods={}; self.owner=False
        if type(self.metadata) is not bool: raise PDFError('Ungültige PDF-Metadatenverschlüsselung.')
        self.permissions=integer(attrs.get('P'),-2**31,2**31-1)
        revision=self.revision; password=password_bytes(password,revision)
        expected=48 if revision>=5 else 32
        if any(not isinstance(attrs.get(k),bytes) or len(attrs[k])!=expected for k in ('O','U')): raise PDFError('Ungültige PDF-Passwortdaten.')
        if revision>=5:
            if self.version!=5 or attrs.get('Length',256)!=256: raise UnsupportedPDF('Unbekannte PDF-AES-256-Konfiguration.')
            if any(not isinstance(attrs.get(k),bytes) or len(attrs[k])!=size for k,size in (('OE',32),('UE',32),('Perms',16))): raise PDFError('Ungültige PDF-Schlüsseldaten.')
            key=None
            for field,encrypted,user in (('O','OE',attrs['U']),('U','UE',b'')):
                entry=attrs[field]
                if hmac.compare_digest(hash6(password,entry[32:40],user,revision),entry[:32]):
                    key=crypto('aes-256-cbc',hash6(password,entry[40:48],user,revision),attrs[encrypted],bytes(16)); self.owner=field=='O'; break
            if key is None: raise PasswordRequired('PDF-Passwort erforderlich oder nicht korrekt.')
            perms=crypto('aes-256-ecb',key,attrs['Perms'])
            if perms[:4]!=(self.permissions&0xffffffff).to_bytes(4,'little') or perms[4:8]!=b'\xff'*4 or perms[8:12]!=(b'T' if self.metadata else b'F')+b'adb': raise PDFError('PDF-Berechtigungsprüfung fehlgeschlagen.')
            self.key=key
        else:
            if self.version not in (1,2,4): raise UnsupportedPDF('Unbekannte ältere PDF-Verschlüsselung.')
            if not isinstance(identifiers,list) or not identifiers or not isinstance(identifiers[0],bytes): raise PDFError('PDF-Dateikennung zur Entschlüsselung fehlt.')
            bits=attrs.get('Length',40)
            if type(bits) is not int or not 40<=bits<=128 or bits%8: raise PDFError('Ungültige PDF-Schlüssellänge.')
            length=5 if revision==2 else bits//8
            def key_for(candidate):
                raw=(candidate+PAD)[:32]+attrs['O']+(self.permissions&0xffffffff).to_bytes(4,'little')+identifiers[0]
                if revision==4 and not self.metadata: raw+=b'\xff'*4
                digest=hashlib.md5(raw).digest()
                if revision>=3:
                    for _ in range(50): digest=hashlib.md5(digest[:length]).digest()
                return digest[:length]
            def valid(candidate):
                key=key_for(candidate)
                if revision==2: expected=crypto('rc4',key,PAD)
                else:
                    expected=crypto('rc4',key,hashlib.md5(PAD+identifiers[0]).digest())
                    for turn in range(1,20): expected=crypto('rc4',bytes(b^turn for b in key),expected)
                return key if hmac.compare_digest(expected,attrs['U'][:len(expected)]) else None
            key=valid(password)
            if key is None:
                digest=hashlib.md5((password+PAD)[:32]).digest()
                if revision>=3:
                    for _ in range(50): digest=hashlib.md5(digest).digest()
                owner_key=digest[:length]; candidate=attrs['O']
                for turn in (range(19,-1,-1) if revision>=3 else [0]): candidate=crypto('rc4',bytes(b^turn for b in owner_key),candidate)
                key=valid(candidate); self.owner=key is not None
            if key is None: raise PasswordRequired('PDF-Passwort erforderlich oder nicht korrekt.')
            self.key=key
        for slot in ('StmF','StrF'):
            if self.version<4: self.methods[slot]='V2'; continue
            selected=attrs.get(slot,'Identity')
            if selected=='Identity': self.methods[slot]='Identity'; continue
            info=attrs.get('CF',{}).get(selected)
            if not isinstance(info,dict) or info.get('AuthEvent','DocOpen')!='DocOpen': raise UnsupportedPDF('PDF-Kryptofilter wird nicht unterstützt.')
            method=info.get('CFM')
            if method not in (('AESV3',) if revision>=5 else ('V2','AESV2')): raise UnsupportedPDF('PDF-Kryptofilter wird nicht unterstützt.')
            self.methods[slot]=method

    def decrypt(self,data,reference,method):
        if method=='Identity': return data
        if method=='AESV3': key=self.key
        else:
            material=self.key+reference.number.to_bytes(3,'little')+reference.generation.to_bytes(2,'little')
            if method=='AESV2': material+=b'sAlT'
            key=hashlib.md5(material).digest()[:min(len(self.key)+5,16)]
        if method=='V2': return crypto('rc4',key,data)
        if len(data)<32 or len(data)%16: raise PDFError('Ungültige verschlüsselte PDF-Daten.')
        return crypto('aes-256-cbc' if method=='AESV3' else 'aes-128-cbc',key,data[16:],data[:16],padding=True)

    def value(self,value,reference,resolve=lambda v:v):
        if isinstance(value,Stream):
            if value.attrs.get('Type')=='XRef': return value
            attrs=self.value(value.attrs,reference,resolve); method=self.methods['StmF']
            if attrs.get('Type')=='Metadata' and not self.metadata: method='Identity'
            filters=resolve(attrs.get('Filter')) or []; filters=[filters] if isinstance(filters,Name) else filters
            if not isinstance(filters,list):raise PDFError('Ungültige PDF-Kryptofilterkette.')
            if any(resolve(f)=='Crypt' for f in filters): raise UnsupportedPDF('Expliziter PDF-Stream-Kryptofilter wird noch nicht unterstützt.')
            return Stream(attrs,self.decrypt(value.raw,reference,method))
        if isinstance(value,bytes): return self.decrypt(value,reference,self.methods['StrF'])
        if isinstance(value,list): return [self.value(v,reference,resolve) for v in value]
        if isinstance(value,dict): return {k:self.value(v,reference,resolve) for k,v in value.items()}
        return value

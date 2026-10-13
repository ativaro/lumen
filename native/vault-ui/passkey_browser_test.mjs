// Synthetic WebAuthn transport, real WebCrypto; never touches a personal browser.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const code=readFileSync(new URL('passkey.js',import.meta.url),'utf8');
const enc=a=>Buffer.from(a).toString('base64url');
async function scenario({enroll=false,prf=true,typed=false,cancel=false,configFailure=false,english=false}={}) {
  const els={confirm:{disabled:true},status:{textContent:''}};
  const salt=webcrypto.getRandomValues(new Uint8Array(32));
  const secret=new Uint8Array(32).fill(7);
  const requests=[];let creates=0,gets=0;
  const config={language:english?"en":"de",enroll,salt:enc(salt),binding:enc(salt),challenge:enc(salt),credential:enc(new Uint8Array([1,2,3]))};
  const context=vm.createContext({
    location:{hash:'#synthetic-nonce'},history:{replaceState(){}},document:{getElementById:id=>els[id],documentElement:{lang:"de"},querySelector:()=>({textContent:""})},
    crypto:webcrypto,TextEncoder,Uint8Array,ArrayBuffer,atob,btoa,
    fetch:async (path,options)=>{
      assert.equal(options.headers['X-Lumen-Token'],'synthetic-nonce');requests.push({path,options});
      return {ok:!configFailure,json:async()=>config};
    },
    navigator:{credentials:{
      create:async options=>{creates++;assert.equal(options.publicKey.authenticatorSelection.userVerification,'required');return {rawId:new Uint8Array([1,2,3]).buffer,getClientExtensionResults:()=>({prf:{enabled:prf}})};},
      get:async options=>{
        gets++;assert.equal(options.publicKey.userVerification,'required');assert.equal(options.publicKey.rpId,'localhost');
        if(cancel){const error=new Error('denied');error.name='NotAllowedError';throw error;}
        return {rawId:new Uint8Array([1,2,3]).buffer,response:{clientDataJSON:new Uint8Array([4]).buffer,authenticatorData:new Uint8Array([5]).buffer},
          getClientExtensionResults:()=>prf?{prf:{results:{first:typed?secret:secret.buffer}}}:{}};
      }
    }}
  });
  vm.runInContext(code,context);
  await new Promise(resolve=>setImmediate(resolve));
  if(!configFailure)await els.confirm.onclick();
  return {els,requests,creates,gets,secret,config};
}
for(const english of [false,true])for(const enroll of [false,true])for(const typed of [false,true]) {
  const r=await scenario({enroll,typed,english});const done=r.requests.find(x=>x.path==='/complete');assert.ok(done);
  const body=JSON.parse(done.options.body);assert.match(body.key,/^[0-9a-f]{64}$/);
  assert.equal(body.credential,r.config.credential);assert.equal(r.creates,enroll?1:0);
  assert.ok(r.secret.every(v=>v===0));assert.ok(!done.options.body.includes('password'));
}
for(const args of [{prf:false},{enroll:true,prf:false},{cancel:true},{configFailure:true}]) {
  const r=await scenario(args);assert.ok(!r.requests.some(x=>x.path==='/complete'));
}
console.log('12 browser-flow cases passed: enrollment/unlock, ArrayBuffer/typed PRF, absence, cancellation, expired bridge');

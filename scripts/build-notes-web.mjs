// Bundle the shared Server components offline, with the already installed libraries.
import {readFile,writeFile,mkdtemp,symlink,unlink,rm,readdir} from 'node:fs/promises';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const web=resolve(process.argv[2]||'../lumen-server/web');
const {build}=await import(join(web,'node_modules/vite/dist/node/index.js'));
const source=join(root,'files/notes_web'),temp=await mkdtemp('/tmp/lumen-notes-desktop-');
await symlink(join(web,'node_modules'),join(source,'node_modules'));
try {
 const result=await build({configFile:false,define:{'process.env.NODE_ENV':'"production"'},esbuild:{jsx:'automatic'},root:source,logLevel:'warn',build:{outDir:temp,emptyOutDir:true,assetsInlineLimit:1000000,lib:{entry:join(source,'src/main.tsx'),name:'LumenNotes',cssFileName:'notes',formats:['iife'],fileName:()=> 'notes.js'},rollupOptions:{output:{assetFileNames:'[name][extname]'}}}});
 const js=await readFile(join(temp,'notes.js'),'utf8'),css=await readFile(join(temp,'notes.css'),'utf8').catch(()=>readFile(join(temp,'style.css'),'utf8'));
 if(js.includes('</script'))throw Error('Unsafe script boundary');
 await writeFile(join(source,'notes.js'),js);await writeFile(join(source,'notes.css'),css);
 await writeFile(join(source,'index.html'),`<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' qrc:; style-src 'self' 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"><title>Lumen Notes</title><link rel="stylesheet" href="notes.css"><div id="root"></div><script src="qrc:///qtwebchannel/qwebchannel.js"></script><script src="notes.js"></script></html>`);
 const names=new Set();for(const id of Object.keys((Array.isArray(result)?result[0]:result).output.find(x=>x.type==='chunk').modules)){const match=id.match(/node_modules\/((?:@[^/]+\/)?[^/]+)/);if(match)names.add(match[1]);}
 let notices='Lumen Notes Desktop bundled third-party notices\n\n=== Native UI font (SIL OFL) ===\n'+(await readFile(join(root,'files/fonts/OFL.txt'),'utf8')).replace(/\r\n/g,'\n').replace(/[ \t]+$/gm,'')+'\n';const packages=[];
 for(const name of [...names].sort()) {const dir=join(web,'node_modules',name),pkg=JSON.parse(await readFile(join(dir,'package.json'),'utf8'));const files=(await readdir(dir)).filter(x=>/^(license|licence|copying)(\.|$)/i.test(x));if(!files.length)throw Error('Missing license '+name);notices+=`\n=== ${name} ${pkg.version} (${pkg.license}) ===\n`;for(const f of files)notices+=await readFile(join(dir,f),'utf8')+'\n';packages.push({name,version:pkg.version,license:pkg.license});}
 const upstream={};for(const name of ['note-editor.tsx','note-rich-document.ts','i18n.tsx','en.json','ui.tsx','knowledge.css','style.css','main.tsx','appearance.css']){const data=await readFile(join(source,'src',name));upstream[name]=createHash('sha256').update(data).digest('hex');}
 await writeFile(join(source,'server-sources.json'),JSON.stringify(upstream,null,2)+'\n');
 await writeFile(join(source,'NOTICES.txt'),notices);await writeFile(join(source,'dependencies.json'),JSON.stringify(packages,null,2)+'\n');
 console.log(JSON.stringify({bytes:Buffer.byteLength(js)+Buffer.byteLength(css),packages:packages.length,sha256:createHash('sha256').update(js).digest('hex')}));
}finally{await unlink(join(source,'node_modules'));await rm(temp,{recursive:true,force:true});}

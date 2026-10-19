import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {BookOpen, Folder, Plus, Save, Ellipsis, LockKeyhole, Unlock} from 'lucide-react';
import {NoteEditor} from './note-editor';
import {noteSummary} from './note-rich-document';
import {Empty} from './ui';
import {tr, choose, locale, useLanguage} from './i18n';
import '@fontsource/dm-sans/400.css';
import '@fontsource/dm-sans/500.css';
import '@fontsource/dm-sans/600.css';
import '@fontsource/dm-sans/700.css';
import './knowledge.css';
import './style.css';
import './panorama.css';
import './appearance.css';
import './desktop.css';

declare global {interface Window {qt:any; QWebChannel:any; lumenNotes:any;}}
type Doc={id:string;title:string;body:string;tags:string[];updated:number;shared:boolean};
type State={epoch:number;ack:number;doc:Doc|null;notes:Doc[];more:boolean;collections:{id:string;title:string;name:string}[];collection:string;q:string;status:string;banner:string;conflict:boolean;busy:boolean;ready:boolean;dirty:boolean;language:'de'|'en';appearance:Record<string,string>};
let bridge:any;
const summaries=new Map<string,string>();
function summary(note:Doc) {const key=note.id+'\0'+note.body;if(!summaries.has(key)){if(summaries.size>=500)summaries.clear();summaries.set(key,noteSummary(note.body));}return summaries.get(key)!;}
function command(action:string, values:object={}) {bridge.command(JSON.stringify({action,...values}));}
function App() {
 const [state,setState]=useState<State|null>(null), [doc,setDoc]=useState<Doc|null>(null), [tag,setTag]=useState('');
 const [collectionsOpen,setCollectionsOpen]=useState(false);
 const sequence=useRef(0), current=useRef<Doc|null>(null), epoch=useRef(-1);
 current.current=doc;
 window.lumenNotes={flush:()=>current.current?JSON.stringify({action:'edit',id:current.current.id,epoch:epoch.current,sequence:sequence.current,title:current.current.title,body:current.current.body}):null};
 useLanguage();
 useEffect(()=>{
  new window.QWebChannel(window.qt.webChannelTransport,(channel:any)=>{
   bridge=channel.objects.notes;
   function receive(raw:string) {
    const next:State=JSON.parse(raw);
    for(const [key,value] of Object.entries(next.appearance||{})) {
      document.documentElement.style.setProperty(key==='color-scheme'?key:'--'+key,value);
    }
    choose(next.language,false);
    if(next.epoch!==epoch.current){epoch.current=next.epoch;sequence.current=0;setDoc(next.doc);setTag('');}
    else if(next.ack>=sequence.current)setDoc(next.doc);
    setState(next);
   }
   bridge.changed.connect(receive);bridge.snapshot(receive);
  });
  const keys=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();command('save');}};
  window.addEventListener('keydown',keys);return ()=>window.removeEventListener('keydown',keys);
 },[]);
 function edit(next:Doc) {
  setDoc(next);current.current=next;sequence.current++;
  command('edit',{id:next.id,epoch:epoch.current,sequence:sequence.current,title:next.title,body:next.body});
 }
 if(!state)return <p role="status">{tr('Notiz wird geladen …')}</p>;
 const disabled=state.busy||!state.ready;
 return <main className="panorama desktop-notes"><div className="content">
  <div className="knowledge-workspace">
   <nav className="knowledge-navigation" aria-label={tr('Bereiche und Sammlungen')}>
    <button className="desktop-collections-toggle" aria-expanded={collectionsOpen} aria-controls="desktop-collections" onClick={()=>setCollectionsOpen(!collectionsOpen)}><Folder size={16}/>{tr('Sammlungen')}</button>
    <div id="desktop-collections" className={'desktop-collections'+(collectionsOpen?' is-open':'')}>
    <div className="knowledge-areas"><span className="knowledge-caption"><BookOpen size={17}/> {tr('Meine Notizen')}</span></div>
    <h2 className="knowledge-caption">{tr('Sammlungen')}</h2>
    <button className="knowledge-new-collection" disabled={disabled} onClick={()=>command('create_collection')}><Plus size={16}/>{tr('Neue Sammlung')}</button>
    <div className="knowledge-collection-list">{state.collections.filter(c=>!c.id.startsWith('tag:')).map(c=><button key={c.id} disabled={disabled}
     className={state.collection===c.id?'active':''} aria-current={state.collection===c.id?'page':undefined} onClick={()=>{command('collection',{id:c.id});setCollectionsOpen(false);}}>
     {c.id?<Folder size={16}/>:<BookOpen size={16}/>}<span>{c.title}</span>
    </button>)}</div>
    </div>
   </nav>
   <section className="knowledge-notes" aria-label={tr('Notizliste')}>
    <input aria-label={tr('Notizen finden')} placeholder={tr('Text oder #tags suchen …')} value={state.q} maxLength={200} disabled={disabled} onChange={e=>{setState({...state,q:e.target.value});command('search',{value:e.target.value});}}/>
    <small className="muted">{tr('Mehrere #tags müssen alle passen. Untertags werden mitgefunden.')}</small>
    <div className="knowledge-list-heading"><h2>{state.collection?state.collections.find(c=>c.id===state.collection)?.name:tr('Zuletzt bearbeitet')}</h2><button disabled={disabled} aria-label={tr('Neue Notiz')} onClick={()=>command('create')}><Plus size={16}/>{tr('Neu')}</button></div>
    <div className="inline-actions"><button disabled={disabled} onClick={()=>command('daily')}>{tr('Tagesnotiz')}</button><button disabled={disabled} onClick={()=>command('template')}>{tr('Aus Vorlage')}</button></div>
    <div className="knowledge-note-list" aria-busy={!state.ready}>
     {state.notes.map(n=><button className={'doc-row'+(doc?.id===n.id?' active':'')} key={n.id} title={n.title} disabled={disabled} aria-pressed={doc?.id===n.id} onClick={()=>command('open',{id:n.id})}>
      <span><strong>{n.title}</strong><small>{summary(n).slice(0,75)||tr('Noch ohne Inhalt')}</small>{!!n.tags.length&&<small className="note-tags" aria-label={tr('Tags')}>{n.tags.map(t=>'#'+t).join(' · ')}</small>}<small>{n.id.includes('/')?n.id.slice(0,n.id.lastIndexOf('/')):tr('Eigene Notiz')}</small></span>
     </button>)}
     {state.more&&<button disabled={disabled} onClick={()=>command('more_notes')}>{tr('Weitere Notizen laden')}</button>}
     {!state.notes.length&&<p className="muted">{tr('Keine Notizen in dieser Auswahl.')}</p>}
    </div>
   </section>
   {doc?<section className="editor knowledge-editor" aria-label={tr('Geöffnete Notiz')}>
    <div className="desktop-note-heading">
    <div className="knowledge-editor-heading"><span className="knowledge-location">{doc.id.includes('/')?doc.id.slice(0,doc.id.lastIndexOf('/')):tr('Meine Notizen')}</span>
     <details className="desktop-tag-entry" key={doc.id}><summary><Plus size={15}/>{tr('Tag hinzufügen')}</summary><form className="inline-actions" onSubmit={e=>{e.preventDefault();command('tag',{id:doc.id,epoch:epoch.current,tag,checked:true});setTag('');const details=e.currentTarget.closest('details');if(details)details.open=false;}}><input aria-label={tr('Tag hinzufügen')} placeholder={tr('Tag hinzufügen')} value={tag} maxLength={200} disabled={disabled} onChange={e=>setTag(e.target.value)}/><button disabled={disabled||!tag.trim()} type="submit">{tr('Hinzufügen')}</button></form></details>
     <button className="knowledge-share" disabled={disabled} aria-pressed={doc.shared} onClick={()=>command('share',{id:doc.id,epoch:epoch.current})}>{doc.shared?<Unlock size={15}/>:<LockKeyhole size={15}/>} {tr(doc.shared?'Für Lumen freigegeben':'Nur für mich')}</button>
     <details className="knowledge-more" key={doc.id} onKeyDown={e=>{if(e.key==='Escape'){e.currentTarget.open=false;e.currentTarget.querySelector('summary')?.focus();}}}><summary><Ellipsis size={18}/>{tr('Mehr')}</summary><div className="knowledge-actions"><button disabled={disabled} onClick={()=>command('more')}>{tr('Weitere Werkzeuge')}</button><button disabled={disabled} onClick={()=>command('history')}>{tr('Frühere Fassungen …')}</button><button disabled={disabled} onClick={()=>command('archive')}>{tr('Notiz entfernen …')}</button></div></details>
    </div>
    <input className="title-input" aria-label={tr('Notiztitel')} value={doc.title} maxLength={300} readOnly={disabled} onChange={e=>edit({...doc,title:e.target.value})}/>
    {!!doc.tags.length&&<div className="note-tags-editor" aria-label={tr('Tags')}>{doc.tags.map(t=><span className="note-tag" key={t}>#{t}<button disabled={disabled} aria-label={tr('Tag entfernen')+': '+t} onClick={()=>command('tag',{id:doc.id,epoch:epoch.current,tag:t,checked:false})}>×</button></span>)}</div>}
    </div>
    {state.banner&&<p role="alert">{state.banner}</p>}
    {state.conflict&&<div className="inline-actions"><button disabled={disabled} onClick={()=>command('reload')}>{tr('Externe Fassung laden')}</button><button disabled={disabled} onClick={()=>command('copy')}>{tr('Entwurf als Kopie')}</button></div>}
    <NoteEditor key={epoch.current} value={doc.body} readOnly={disabled} onChange={body=>{if(current.current)edit({...current.current,body});}}/>
    <div className="inline-actions knowledge-save"><div className="desktop-note-status"><span className="muted" role="status">{state.status}</span>{!!doc.updated&&<span className="knowledge-timestamp muted">{tr('Geändert: ')}<time>{new Date(doc.updated*1000).toLocaleString(locale())}</time></span>}</div><button className="primary" disabled={disabled||!state.dirty} onClick={()=>command('save')}><Save size={16}/>{tr('Speichern')}</button></div>
   </section>:<Empty icon={BookOpen} title={tr('Ein guter Platz für deine Gedanken')} text={tr('Wähle eine Notiz oder halte einen neuen Gedanken fest.')}/>}
  </div>
 </div></main>;
}
createRoot(document.getElementById('root')!).render(<App/>);

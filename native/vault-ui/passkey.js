// SPDX-License-Identifier: LicenseRef-Lumen-EULA
"use strict";
const token = location.hash.slice(1);
history.replaceState(null, "", "/");
const button = document.getElementById("confirm"), status = document.getElementById("status");
const encode = a => btoa(String.fromCharCode(...new Uint8Array(a))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
const decode = s => Uint8Array.from(atob(s.replaceAll("-", "+").replaceAll("_", "/")), c => c.charCodeAt(0));
const headers = {"X-Lumen-Token": token};
let config;
let english = navigator.language?.startsWith("en") || false;
const text = (de,en) => english ? en : de;
fetch("/config", {headers, cache: "no-store"}).then(async r => {
  if (!r.ok) throw Error();
  config = await r.json();
  english = config.language === "en";
  if (english) {
    document.documentElement.lang = "en";
    document.querySelector("h1").textContent = "Your vault. Simply unlocked.";
    document.querySelector("main > p").textContent = "Confirm your passkey with Proton Pass or another compatible provider.";
    document.querySelector("small").textContent = "Your master password stays in the native vault. Close this page to cancel.";
    button.textContent = "Continue with passkey";
  }
  button.disabled = false;
  status.textContent = config.enroll ? text("Passkey einmalig einrichten. Dein Hauptpasswort bleibt der Wiederherstellungsweg.","Set up a passkey once. Your master password remains your recovery method.") : text("Bereit. Bitte bestätige deinen Passkey.","Ready. Please confirm your passkey.");
}).catch(() => { status.textContent = text("Verbindung abgelaufen. Bitte erneut in Lumen Vault starten.","Connection expired. Start again in Lumen Vault."); });
button.onclick = async () => {
  button.disabled = true;
  let prf, derived;
  try {
    let id = config.credential ? decode(config.credential) : null;
    if (config.enroll) {
      const created = await navigator.credentials.create({publicKey: {
        challenge: decode(config.challenge), rp: {id:"localhost",name:"Lumen Vault Desktop"},
        user: {id:decode(config.binding), name:"Lumen Vault Desktop",displayName:"Lumen Vault Desktop"},
        pubKeyCredParams:[{type:"public-key",alg:-7},{type:"public-key",alg:-257}],
        authenticatorSelection:{residentKey:"preferred",userVerification:"required"},
        attestation:"none",timeout:60000,extensions:{prf:{}}
      }});
      if (!created?.getClientExtensionResults()?.prf?.enabled) throw Error(text("Dieser Anbieter unterstützt keine PRF-Tresorentsperrung.","This provider does not support PRF vault unlock."));
      id = created.rawId;
    }
    const result = await navigator.credentials.get({publicKey: {
      challenge:decode(config.challenge),rpId:"localhost",allowCredentials:[{type:"public-key",id}],
      userVerification:"required",timeout:60000,extensions:{prf:{eval:{first:decode(config.salt)}}}
    }});
    prf = result?.getClientExtensionResults()?.prf?.results?.first;
    if (!prf || prf.byteLength !== 32) throw Error(text("Dieser Anbieter unterstützt keine PRF-Tresorentsperrung.","This provider does not support PRF vault unlock."));
    const key = await crypto.subtle.importKey("raw",prf,"HKDF",false,["deriveBits"]);
    derived = new Uint8Array(await crypto.subtle.deriveBits({name:"HKDF",hash:"SHA-256",salt:decode(config.salt),info:new TextEncoder().encode("Lumen Desktop Vault v1:"+config.binding)},key,256));
    const reply = await fetch("/complete",{method:"POST",headers:{...headers,"Content-Type":"application/json"},body:JSON.stringify({
      key:Array.from(derived,v=>v.toString(16).padStart(2,"0")).join(""),credential:encode(result.rawId),
      clientData:encode(result.response.clientDataJSON),authData:encode(result.response.authenticatorData)
    })});
    if (!reply.ok) throw Error(text("Lokale Übergabe nicht bestätigt. Bitte in Lumen Vault erneut starten.","Local handoff failed. Start again in Lumen Vault."));
    status.textContent = text("Bestätigung übergeben. Lumen Vault prüft den Schlüssel. Du kannst diese Seite schließen.","Confirmation sent. Lumen Vault is checking the key. You can close this page.");
  } catch (error) {
    status.textContent = error.name === "NotAllowedError" ? text("Abgebrochen oder nicht verfügbar. Verwende bei Bedarf dein Hauptpasswort.","Cancelled or unavailable. You can use your master password.") : error.message || text("Passkey nicht verfügbar.","Passkey unavailable.");
    button.disabled = false;
  } finally {
    if (prf) new Uint8Array(prf.buffer || prf,prf.byteOffset || 0,prf.byteLength).fill(0);
    if (derived) derived.fill(0);
  }
};

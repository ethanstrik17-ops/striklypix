"""Password protection for the website.

Each page is encrypted with AES-256-GCM using a key derived from your password (PBKDF2, 200k rounds)
and wrapped in a small unlock page. The browser decrypts it locally with the built-in Web Crypto API,
so the real content never sits on the web in readable form, even though the hosting is public.
The pick log is stored encrypted the same way.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 200_000


def _key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(password.encode())


def encrypt_bytes(data: bytes, password: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(12)
    return salt + nonce + AESGCM(_key(password, salt)).encrypt(nonce, data, None)


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    return AESGCM(_key(password, salt)).decrypt(nonce, ct, None)


def lock_page(html: str, password: str, title: str = "StriklyPix", salt: bytes | None = None) -> str:
    """Wrap a page in a password prompt. Pass the same `salt` for every page of one build: then the
    browser derives the key once, caches it, and every other page opens instantly with no flash."""
    salt, nonce = salt or os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(password, salt)).encrypt(nonce, html.encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content="noindex,nofollow">
<meta http-equiv=Cache-Control content="no-cache"><meta name=theme-color content="#070b16">
<title>{title}</title><style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0b1020;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#0f172a}}
body.ask{{background:#0b1020}}form{{display:none;background:#fff;border-radius:16px;padding:28px;width:min(92vw,360px);
box-shadow:0 10px 40px rgba(0,0,0,.3)}}body.ask form{{display:block}}
h1{{font-size:22px;margin:0 0 4px;font-weight:800}}p{{color:#64748b;font-size:13px;margin:0 0 18px}}
input[type=password]{{width:100%;box-sizing:border-box;font-size:16px;padding:12px;border:1px solid #cbd5e1;border-radius:10px}}
button{{width:100%;margin-top:12px;font-size:16px;font-weight:650;padding:12px;border:0;border-radius:10px;background:#15803d;color:#fff}}
label{{display:flex;gap:8px;align-items:center;font-size:13px;color:#475569;margin-top:12px}}#e{{color:#b91c1c;font-size:13px;min-height:18px;margin-top:8px}}
</style></head><body><form id=f><h1>Strikly<span style="color:#16a34a">Pix</span></h1><p>Private page. Enter your password.</p>
<input id=pw type=password autocomplete=current-password placeholder=Password>
<label><input id=rm type=checkbox checked> Remember on this device</label><button>Unlock</button><div id=e></div></form>
<script>
const S="{b(salt)}",N="{b(nonce)}",C="{b(ct)}",KK="sp_k_"+S;
const d=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0)),en=u=>btoa(String.fromCharCode(...new Uint8Array(u)));
const ls={{get:k=>{{try{{return localStorage.getItem(k)}}catch(e){{return null}}}},set:(k,v)=>{{try{{localStorage.setItem(k,v)}}catch(e){{}}}},
 del:k=>{{try{{localStorage.removeItem(k)}}catch(e){{}}}}}};
const ready=()=>document.readyState==='loading'?new Promise(r=>document.addEventListener('DOMContentLoaded',r,{{once:true}})):Promise.resolve();
async function show(key){{const pt=await crypto.subtle.decrypt({{name:'AES-GCM',iv:d(N)}},key,d(C));
 await ready();  // replace the whole lock page only once it has finished loading (otherwise its layout leaks in)
 document.open();document.write(new TextDecoder().decode(pt));document.close();}}
async function derive(pw){{const base=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
 return crypto.subtle.deriveKey({{name:'PBKDF2',salt:d(S),iterations:{ITER},hash:'SHA-256'}},base,{{name:'AES-GCM',length:256}},true,['decrypt']);}}
async function withPw(pw,remember){{const key=await derive(pw);await crypto.subtle.decrypt({{name:'AES-GCM',iv:d(N)}},key,d(C));
 if(remember){{ls.set('sp_pw',pw);ls.set(KK,en(await crypto.subtle.exportKey('raw',key)));}}await show(key);}}
function ask(){{document.body.classList.add('ask');document.getElementById('pw').focus();}}
(async()=>{{const raw=ls.get(KK);
 if(raw){{try{{await show(await crypto.subtle.importKey('raw',d(raw),'AES-GCM',false,['decrypt']));return}}catch(e){{ls.del(KK)}}}}
 const pw=ls.get('sp_pw');if(pw){{try{{await withPw(pw,true);return}}catch(e){{ls.del('sp_pw')}}}}ask();}})();
document.getElementById('f').onsubmit=async ev=>{{ev.preventDefault();
 try{{await withPw(document.getElementById('pw').value,document.getElementById('rm').checked)}}
 catch(e){{document.getElementById('e').textContent='Wrong password.'}}}};
</script></body></html>"""

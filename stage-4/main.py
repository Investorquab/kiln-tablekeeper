#!/usr/bin/env python3
"""Tablekeeper Stage 4 reservation service."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LOCK = threading.RLock()
STATE = {"users": {}, "restaurants": {}, "reservations": {}, "tokens": {}, "receipts": {},
         "policies": {}, "histories": {}, "series": {}, "restaurant_revisions": {},
         "closures": {}, "replans": {}}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
REF_RE = re.compile(r"^[A-Z0-9]{6,12}$")
LOCAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

APP_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tablekeeper | A table worth gathering around</title>
<style>
:root{color-scheme:light;--ink:#233b32;--muted:#60736a;--leaf:#17523f;--leaf-dark:#103d2f;--leaf2:#e5efe8;--cream:#fbf7ef;--paper:#fffefa;--line:#d9dfd7;--gold:#a25d19;--red:#963f32;--shadow:0 16px 42px rgba(34,56,44,.09);--shadow-soft:0 7px 22px rgba(34,56,44,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 92% 9%,rgba(226,207,162,.2),transparent 28rem),var(--cream);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}a{color:var(--leaf);text-underline-offset:3px}button,input,select{font:inherit}button,a,input,select{outline-offset:3px}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #bb6b18;outline-offset:3px}button{border:0;border-radius:11px;padding:.76rem 1.05rem;background:var(--leaf);color:white;font-weight:750;cursor:pointer;box-shadow:0 5px 12px rgba(23,82,63,.13);transition:background .18s ease,transform .18s ease,box-shadow .18s ease}button:hover{background:var(--leaf-dark);transform:translateY(-1px);box-shadow:0 8px 18px rgba(23,82,63,.17)}button:active{transform:translateY(0)}button:disabled{cursor:not-allowed;opacity:.58;box-shadow:none;transform:none}input,select{width:100%;min-height:48px;border:1px solid #b8c5bb;border-radius:10px;background:#fff;padding:.65rem .78rem;color:var(--ink);transition:border-color .18s ease,box-shadow .18s ease}input:hover,select:hover{border-color:#80978a}input:focus,select:focus{border-color:var(--leaf);box-shadow:0 0 0 3px rgba(23,82,63,.12);outline:none}label{display:grid;gap:.42rem;font-size:.94rem;font-weight:700}.top{position:relative;z-index:2;background:rgba(255,254,250,.94);border-bottom:1px solid rgba(217,223,215,.9);box-shadow:0 3px 16px rgba(34,56,44,.035);backdrop-filter:blur(14px)}.nav{max-width:1120px;min-height:76px;margin:auto;padding:.8rem 1.2rem;display:flex;gap:.65rem;align-items:center;flex-wrap:wrap}.brand{display:inline-flex;align-items:center;gap:.6rem;font-family:Georgia,serif;font-size:1.45rem;font-weight:bold;color:var(--ink);text-decoration:none;margin-right:auto;letter-spacing:-.025em}.brand:before{content:"";width:14px;height:22px;border-radius:14px 2px 14px 2px;background:linear-gradient(145deg,#477b57,#17523f);transform:rotate(18deg);box-shadow:5px 4px 0 -2px #c28a36}.nav a:not(.brand){text-decoration:none;font-size:.94rem;font-weight:700;color:#43594e;padding:.55rem .8rem;border-radius:999px;transition:background .18s ease,color .18s ease}.nav a:not(.brand):hover,.nav a[aria-current="page"]{background:var(--leaf2);color:var(--leaf)}.userbar{display:flex;gap:.6rem;align-items:center;color:var(--muted);font-size:.9rem}.userbar [data-testid="current-user"]{font-weight:700;color:var(--ink)}.userbar button{padding:.48rem .75rem;font-size:.88rem;box-shadow:none}.shell{max-width:1120px;min-height:calc(100vh - 76px);margin:0 auto;padding:clamp(1.8rem,5vw,3.4rem) 1.25rem 5rem}.eyebrow{text-transform:uppercase;letter-spacing:.15em;color:var(--gold);font-size:.72rem;font-weight:850}.hero{position:relative;max-width:760px;margin:.1rem 0 2rem;padding:.4rem 0}.hero:after{content:"";position:absolute;z-index:-1;right:2%;top:4%;width:clamp(100px,18vw,165px);aspect-ratio:1;border-radius:50%;background:radial-gradient(circle at 38% 34%,rgba(231,215,177,.42),rgba(229,239,232,.58) 58%,transparent 70%);pointer-events:none}.hero h1{max-width:700px;font:clamp(2.35rem,6vw,4rem)/1.02 Georgia,serif;letter-spacing:-.04em;margin:.6rem 0}.hero p{max-width:590px;color:var(--muted);font-size:clamp(1rem,2vw,1.12rem);margin:.8rem 0 0}.panel{background:linear-gradient(145deg,rgba(255,254,250,.99),rgba(255,254,250,.94));border:1px solid rgba(217,223,215,.94);border-radius:20px;box-shadow:var(--shadow-soft);padding:clamp(1.1rem,3.2vw,1.7rem);margin:1.1rem 0;transition:box-shadow .2s ease,border-color .2s ease}.panel:hover{border-color:#cbd8cc;box-shadow:var(--shadow)}.filters{display:grid;grid-template-columns:2fr 1.25fr 1fr auto;gap:1rem;align-items:end}.filters button{min-height:48px;white-space:nowrap}.section-head{display:flex;align-items:end;justify-content:space-between;gap:1rem;margin:2.15rem 0 .95rem}.section-head h2{font:clamp(1.4rem,3vw,1.75rem)/1.15 Georgia,serif;letter-spacing:-.02em;margin:.3rem 0 0}.hint,.muted{color:var(--muted)}.hint{font-size:.9rem}.grid-wrap{overflow-x:auto;border-radius:15px}.availability-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,205px),1fr));gap:.75rem}.slot{position:relative;width:100%;min-height:88px;text-align:left;background:linear-gradient(135deg,#edf4ed,#e3eee6);color:var(--ink);border:1px solid #c8d8cb;display:flex;flex-direction:column;justify-content:center;gap:.35rem;padding:.85rem 1rem;box-shadow:none}.slot:before{content:"";position:absolute;inset:10px auto 10px 0;width:3px;border-radius:3px;background:#61906b;opacity:.8}.slot:hover{background:linear-gradient(135deg,#e3efe4,#d7e7da);border-color:#9db9a2;box-shadow:0 7px 18px rgba(23,82,63,.1)}.slot[aria-pressed="true"]{border-color:#b9792e;box-shadow:0 0 0 3px rgba(187,107,24,.2)}.slot[data-available="false"]{background:#f2f1ed;color:#6f7973;border-color:#e0dfd8}.slot[data-available="false"]:before{background:#9aa39c;opacity:.45}.slot .kind{font-size:.8rem;font-weight:550;color:var(--muted)}.availability-grid[aria-busy="true"] .slot{background:linear-gradient(100deg,#f1f1e9 25%,#f7f5ed 42%,#f1f1e9 63%);background-size:220% 100%;animation:shimmer 1.6s ease-in-out infinite}.availability-grid[aria-busy="true"] .slot:before{opacity:.15}.feedback{border-radius:12px;padding:.85rem 1rem;margin:.85rem 0;font-size:.94rem;animation:arrive .22s ease-out}.error{background:#fbefeb;color:#722e27;border:1px solid #e7bdb3}.success{background:#edf5eb;color:#234d32;border:1px solid #bfd5c1}.uncertain{background:#fff5df;color:#704b0b;border:1px solid #ead29d}.booking-layout{display:grid;grid-template-columns:1fr minmax(250px,.65fr);gap:1.5rem;align-items:start;border-top:3px solid #b88739;scroll-margin-top:1rem}.booking-layout>div:first-child{padding:.3rem .2rem}.booking-summary{font:700 clamp(1.15rem,2vw,1.45rem)/1.3 Georgia,serif;margin:.5rem 0}.booking-layout .muted{margin:.45rem 0}.booking-form-fields{display:grid;gap:.85rem;margin:0;padding:1rem;background:#f8f6ef;border:1px solid #e4e1d6;border-radius:14px}.booking-form-fields button{width:100%;margin-top:.15rem}.footer-note{font-size:.88rem;color:var(--muted)}.confirmation{border-left:4px solid #2e744e;background:linear-gradient(120deg,#fffefa,#f4f8f1);scroll-margin-top:1rem}.confirmation h3{margin:.25rem 0 .55rem;font:clamp(1.45rem,3vw,1.8rem)/1.15 Georgia,serif;letter-spacing:-.02em}.confirmation [data-testid="confirmation-details"]{font-weight:650}.reference{font:700 1.25rem ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.08em;color:var(--leaf)}.auth-card,.lookup-card{max-width:600px;margin:1.8rem auto;border-top:3px solid #b88739}.auth-form{display:grid;gap:1rem}.auth-form button{width:100%;margin-top:.2rem}.auth-links{margin:1.1rem 0 .1rem;color:var(--muted);text-align:center}.auth-links a{font-weight:750}.detail{display:grid;gap:.75rem;max-width:620px;margin:1.25rem auto;padding:clamp(1.2rem,4vw,1.8rem)}.detail strong{font:700 1.3rem Georgia,serif}.detail [data-testid="reservation-tables"]{font-weight:750;color:var(--leaf)}.detail button{margin-top:.45rem;background:#934538;box-shadow:0 5px 12px rgba(147,69,56,.12)}.detail button:hover{background:#77372d}.status-pill{display:inline-block;width:max-content;background:var(--leaf2);color:var(--leaf);border-radius:99px;padding:.28rem .75rem;font-size:.84rem;font-weight:800}.status-pill:before{content:"";display:inline-block;width:7px;height:7px;margin:0 .45rem .05rem 0;border-radius:50%;background:currentColor}.status-pill[class*="cancelled"]{background:#f8e9e5;color:#843c31}.empty{padding:1.15rem 1.25rem;border:1px dashed #c3cec4;border-radius:14px;background:rgba(255,254,250,.65);color:var(--muted);line-height:1.6}#results{min-height:3rem}#booking-area{scroll-margin-top:1rem}#auth-shortcuts{white-space:nowrap;color:var(--muted);font-size:.92rem}#auth-shortcuts a{font-weight:700;text-decoration:none}#auth-shortcuts a:hover{text-decoration:underline}
.discovery-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin:0 0 1rem}.discovery-heading p{margin:0;color:var(--muted);font:italic 1.08rem Georgia,serif}.field-note,.detail-caption{font-size:.8rem;font-weight:500;color:var(--muted)}.detail-caption{margin-top:.15rem}.status-pill[class*="confirmed"]{background:var(--leaf2);color:var(--leaf)}
@keyframes arrive{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}@keyframes shimmer{to{background-position:-220% 0}}
@media(max-width:760px){.shell{padding:1.7rem 1rem 3.5rem}.nav{min-height:68px;padding:.7rem 1rem;gap:.35rem}.brand{width:100%;margin:0 0 .15rem}.nav a:not(.brand){padding:.48rem .65rem;font-size:.9rem}.userbar{margin-left:auto}.filters{grid-template-columns:1fr 1fr;gap:.85rem}.filters label:first-child{grid-column:1/-1}.filters button{grid-column:1/-1;width:100%}.booking-layout{grid-template-columns:1fr;gap:1rem}.section-head{align-items:start;flex-direction:column;gap:.45rem;margin-top:1.8rem}.availability-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem}.slot{min-width:0;min-height:82px;padding:.7rem .75rem;font-size:.91rem}.slot strong{overflow-wrap:anywhere}.hero:after{right:0;top:12%}.discovery-heading{align-items:flex-start;flex-direction:column;gap:.25rem}.panel:hover{box-shadow:var(--shadow-soft)}}
@media(max-width:400px){.nav{padding-inline:.75rem;gap:.25rem}.nav a:not(.brand){padding:.45rem .55rem;font-size:.86rem}.shell{padding-inline:.8rem}.availability-grid{gap:.5rem}.slot{padding:.65rem .6rem;font-size:.86rem}.slot .kind{font-size:.75rem}.panel{border-radius:16px}.hero h1{font-size:clamp(2.15rem,12vw,3rem)}#auth-shortcuts{font-size:.86rem}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
</style></head><body><header class="top"><nav class="nav" aria-label="Main navigation"><a class="brand" href="/">Tablekeeper</a><a href="/">Find a table</a><a href="/lookup">Your booking</a><span class="userbar" id="userbar"></span><span id="auth-shortcuts"><a href="/login">Log in</a> · <a href="/signup">Join us</a></span></nav></header><main class="shell" id="app"></main>
<script>
(() => {
const app=document.getElementById('app'), userbar=document.getElementById('userbar'), shortcuts=document.getElementById('auth-shortcuts');
const tid=(s)=>`[data-testid="${s}"]`, esc=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token=localStorage.getItem('tk-token')||'', user=JSON.parse(localStorage.getItem('tk-user')||'null');
let restaurants=[], restaurant=null, searchSeq=0, confirmationSeq=0, lastSearch=null, selection=null, requestState=null, confirmed=null, pendingChoice=null;
const headers=(extra={})=>Object.assign({'Accept':'application/json'},token?{'Authorization':'Bearer '+token}:{},extra);
async function api(path,opts={}){const h=headers(opts.headers||{});if(opts.body!==undefined)h['Content-Type']='application/json';const res=await fetch(path,{...opts,headers:h});let data=null;try{data=await res.json()}catch{}return {res,data}}
function updateUser(){userbar.innerHTML='';shortcuts.hidden=!!user;if(user){const span=document.createElement('span');span.dataset.testid='current-user';span.textContent=user.display_name;const b=document.createElement('button');b.type='button';b.dataset.testid='logout-button';b.textContent='Log out';b.onclick=()=>{token='';user=null;localStorage.removeItem('tk-token');localStorage.removeItem('tk-user');updateUser();renderPage()};userbar.append(span,b)}}
function feedback(id,msg,kind='error',root=app){let e=root.querySelector(tid(id));if(!msg){e?.remove();return}if(!e){e=document.createElement('p');e.dataset.testid=id;e.className='feedback '+kind;e.setAttribute('role','status');root.append(e)}e.textContent=msg;e.className='feedback '+kind}
function shell(title,kicker,copy){return `<div class="hero"><span class="eyebrow">${kicker}</span><h1>${title}</h1><p>${copy}</p></div>`}
function formPage(mode){const signup=mode==='signup';app.innerHTML=`${shell(signup?'A warmer welcome starts here':'Good to see you again',signup?'Join the table':'Welcome back',signup?'Create your diner account to keep reservations and changes together.':'Sign in to book a table and keep your plans close.')}<section class="panel auth-card"><form class="auth-form" id="auth-form">${signup?`<label>Your name<input data-testid="signup-display-name" name="display_name" autocomplete="name" required maxlength="100"></label>`:''}<label>Email address<input data-testid="${signup?'signup-email':'login-email'}" name="email" type="email" autocomplete="email" required></label><label>Password<input data-testid="${signup?'signup-password':'login-password'}" name="password" type="password" autocomplete="${signup?'new-password':'current-password'}" minlength="8" required></label><div id="auth-feedback" aria-live="polite"></div><button data-testid="${signup?'signup-submit':'login-submit'}" type="submit">${signup?'Create account':'Log in'}</button></form><p class="auth-links">${signup?'Already have an account? <a href="/login">Log in</a>':'New to Tablekeeper? <a href="/signup">Create an account</a>'}</p></section>`;
document.getElementById('auth-form').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.currentTarget),body={email:fd.get('email'),password:fd.get('password')};if(signup)body.display_name=fd.get('display_name');try{const {res,data}=await api('/auth/'+mode,{method:'POST',body:JSON.stringify(body)});if(!res.ok){feedback('auth-error',data?.error?.message||'We could not sign you in. Check your details.','error',document.getElementById('auth-feedback'));return}token=data.token;user={display_name:data.display_name||data.user?.display_name,user_id:data.user_id||data.user?.id||data.id};localStorage.setItem('tk-token',token);localStorage.setItem('tk-user',JSON.stringify(user));updateUser();location.href='/'}catch{feedback('auth-error','A connection issue stopped the request. Please try again.','error',document.getElementById('auth-feedback'))}}}
function localDatePlus(days){const d=new Date();d.setDate(d.getDate()+days);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function tableLabels(ids){return ids.map(id=>{const t=restaurant?.tables?.find(x=>x.id===id);return t?.label||id})}
function clearBookingFeedback(){feedback('booking-error','');feedback('booking-uncertain','');feedback('confirmation','')}
function renderBooking(){let box=document.getElementById('booking-area');if(!selection){box.innerHTML='';return}if(!token){feedback('auth-error','Please log in before reserving this table.','error',box);return}const labels=tableLabels(selection.table_ids);box.innerHTML=`<section class="panel booking-layout" data-testid="booking-form"><div><span class="eyebrow">Your table</span><p class="booking-summary" data-testid="booking-summary">${esc(labels.map(x=>'Table '+x).join(' + '))} · ${esc(selection.starts_at_local.slice(11))}</p><p class="muted">${esc(restaurant.name)} · ${esc(selection.starts_at_local.slice(0,10))}</p></div><form class="booking-form-fields" id="booking-submit-form"><label>Party size<input data-testid="booking-party-size" name="party_size" type="number" min="1" max="1000" required value="${esc(selection.party_size)}"></label><div id="booking-feedback"></div><button data-testid="booking-submit" type="submit">Reserve this table</button><span class="footer-note">We’ll hold your details while you confirm.</span></form></section><div id="confirmation-area"></div>`;
document.getElementById('booking-submit-form').onsubmit=submitBooking; if(confirmed)showConfirmation(confirmed)}
async function showConfirmation(receipt){feedback('booking-error','');feedback('booking-uncertain','');const area=document.getElementById('confirmation-area');if(!area)return;const seq=++confirmationSeq;area.innerHTML=`<section class="panel confirmation" data-testid="confirmation"><span class="eyebrow">Reservation saved</span><h3>Refreshing your booking details…</h3><p class="reference" data-testid="confirmation-reference">${esc(receipt.reference)}</p><p class="feedback uncertain" role="status">Checking the current table assignment…</p></section>`;let current=null,error=null;try{const {res,data}=await api(`/reservations/${encodeURIComponent(receipt.reference)}`);if(!res.ok)error=data?.error?.message||'The current table assignment could not be loaded.';else current=data}catch{error='A connection issue stopped us from refreshing the current table assignment.'}if(seq!==confirmationSeq)return;if(!current){area.innerHTML=`<section class="panel confirmation" data-testid="confirmation"><span class="eyebrow">Reservation saved</span><h3>Your booking is confirmed</h3><p class="reference" data-testid="confirmation-reference">${esc(receipt.reference)}</p><p class="feedback uncertain" data-testid="confirmation-refresh-error" role="status">${esc(error)}</p><button data-testid="confirmation-refresh" type="button">Refresh booking details</button></section>`;area.querySelector(tid('confirmation-refresh')).onclick=()=>showConfirmation(receipt);return}confirmed=current;const ids=current.table_ids||[current.table_id];const labels=tableLabels(ids);area.innerHTML=`<section class="panel confirmation" data-testid="confirmation"><span class="eyebrow">All set</span><h3>We’ve saved your table</h3><p class="reference" data-testid="confirmation-reference">${esc(current.reference)}</p><p data-testid="confirmation-details">${esc(restaurant?.name||'Restaurant')} · ${esc(labels.map(x=>'Table '+x).join(' + '))} · ${esc(current.starts_at_local.slice(11))}</p><p data-testid="confirmation-tables">${esc(labels.map(x=>'Table '+x).join(' + '))}</p></section>`}
function optionCells(slot,party){const at=slot.starts_at_local.slice(11), singles=(restaurant.tables||[]).map(t=>({ids:[t.id],capacity:t.capacity,available:(slot.available_table_ids||[]).includes(t.id)}));const pairs=(restaurant.combinable||[]).map(ids=>({ids,capacity:ids.reduce((n,id)=>n+(restaurant.tables.find(t=>t.id===id)?.capacity||0),0),available:(slot.available_options||[]).some(o=>o.table_ids.length===ids.length&&o.table_ids.every((id,i)=>id===ids[i]))})).filter(o=>o.capacity>=party);return singles.concat(pairs).map(o=>{const labels=tableLabels(o.ids).map(x=>'Table '+x).join(' + '), key=o.ids.join('+');return `<button type="button" class="slot" data-testid="slot-${esc(key)}-${esc(at)}" data-available="${o.available?'true':'false'}" aria-pressed="${selection&&selection.starts_at_local===slot.starts_at_local&&selection.table_ids.join('|')===o.ids.join('|')?'true':'false'}" ${o.available?'':'disabled'} data-choice="${esc(JSON.stringify({table_ids:o.ids,starts_at_local:slot.starts_at_local}))}"><strong>${esc(labels)}</strong><span class="kind">${esc(at)} · seats ${o.capacity}</span></button>`}).join('')}
function chooseCell(button){if(lastSearch?.loading){pendingChoice=JSON.parse(button.dataset.choice);return}if(button.dataset.available!=='true')return;selection={...JSON.parse(button.dataset.choice),party_size:Number(document.querySelector(tid('party-size-input')).value)};requestState=null;confirmed=null;renderGrid(lastSearch.data,lastSearch.party);renderBooking()}
function renderGrid(data,party){const area=document.getElementById('results');if(!area)return;if(!data.slots.length){area.innerHTML='<div class="empty" data-testid="no-slots">There are no seating times on this day. Try another date.</div>';return}area.innerHTML=`<div class="grid-wrap"><div class="availability-grid" data-testid="availability-grid">${data.slots.map(s=>optionCells(s,party)).join('')}</div></div>`;area.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>chooseCell(b))}
function renderPendingGrid(date,party){const area=document.getElementById('results');if(!restaurant||!area)return;let day;try{day=new Date(date+'T12:00:00').getDay()}catch{return}const wd=['sun','mon','tue','wed','thu','fri','sat'][day], hours=(restaurant.opening_hours||[]).find(h=>h.weekday===wd);if(!hours){area.innerHTML='<div class="empty">Finding the right table…</div>';return}const parse=s=>Number(s.slice(0,2))*60+Number(s.slice(3,5)), start=parse(hours.opens), stop=parse(hours.closes)-restaurant.reservation_duration_minutes, slots=[];for(let m=start;m<=stop;m+=restaurant.slot_minutes)slots.push({starts_at_local:`${date}T${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`,available_table_ids:[],available_options:[]});if(!slots.length){area.innerHTML='<div class="empty">Finding the right table…</div>';return}area.innerHTML=`<div class="grid-wrap"><div class="availability-grid" data-testid="availability-grid" aria-busy="true">${slots.map(s=>optionCells(s,party)).join('')}</div><span class="hint">Checking current availability…</span></div>`;area.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>chooseCell(b))}
function resolvePendingChoice(choice,data,party){if(!choice)return;const slot=data.slots.find(s=>s.starts_at_local===choice.starts_at_local);if(!slot)return;const available=choice.table_ids.length===1?(slot.available_table_ids||[]).includes(choice.table_ids[0]):(slot.available_options||[]).some(o=>o.table_ids.length===choice.table_ids.length&&o.table_ids.every((id,i)=>id===choice.table_ids[i]));if(!available)return;selection={...choice,party_size:party};requestState=null;confirmed=null;renderGrid(data,party);renderBooking()}
async function performSearch(){const form=document.getElementById('search-form');if(!form)return;const rid=form.elements.restaurant_id.value,date=form.elements.date.value,party=Number(form.elements.party_size.value),seq=++searchSeq;pendingChoice=null;lastSearch={rid,date,party,loading:true};renderPendingGrid(date,party);try{const {res,data}=await api(`/availability?restaurant_id=${encodeURIComponent(rid)}&date=${encodeURIComponent(date)}&party_size=${encodeURIComponent(party)}`);if(seq!==searchSeq)return;if(!res.ok){lastSearch.loading=false;document.getElementById('results').innerHTML='<div class="empty">Availability could not be loaded. Please try again.</div>';return}restaurant=restaurants.find(x=>x.id===rid)||restaurant;lastSearch.data=data;lastSearch.loading=false;renderGrid(data,party);const choice=pendingChoice;pendingChoice=null;resolvePendingChoice(choice,data,party)}catch{if(seq!==searchSeq)return;lastSearch.loading=false;pendingChoice=null;document.getElementById('results').innerHTML='<div class="empty">We couldn’t reach the restaurant. Please try again.</div>'}}
async function submitBooking(e){e.preventDefault();if(!selection||!token)return;const party=Number(e.currentTarget.elements.party_size.value);const body={restaurant_id:restaurant.id,starts_at_local:selection.starts_at_local,party_size:party};if(selection.table_ids.length===1)body.table_id=selection.table_ids[0];else body.table_ids=selection.table_ids;const fingerprint=JSON.stringify(body);if(!requestState||requestState.fingerprint!==fingerprint)requestState={fingerprint,body,key:(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random())};feedback('booking-error','');feedback('booking-uncertain','');try{const {res,data}=await api('/reservations',{method:'POST',headers:{'Idempotency-Key':requestState.key},body:JSON.stringify(requestState.body)});if(res.ok){showConfirmation(data);return}if(res.status===409&&data?.error?.code==='table_unavailable'){feedback('booking-error','That table was just taken. Choose another available table and try again.');await performSearch();return}feedback('booking-error',data?.error?.message||'We could not complete that reservation. Check your selection and try again.')}catch{feedback('booking-error','');feedback('booking-uncertain','We haven’t received a confirmation yet. Your selection is saved here; retry to check the original request.','uncertain')}}
function searchPage(){app.innerHTML=`${shell('A good meal starts with the right table','Find your place','Choose a restaurant, date and party size. We’ll show the seats that fit your evening.')}<section class="panel discovery-panel"><div class="discovery-heading"><span class="eyebrow">Plan your visit</span><p>Find a seat that feels just right.</p></div><form id="search-form" class="filters" aria-label="Find restaurant availability"><label>Restaurant<select data-testid="restaurant-select" name="restaurant_id" required></select><span class="field-note">Choose where you’d like to dine.</span></label><label>Date<input data-testid="date-input" name="date" type="date" value="${localDatePlus(7)}" required><span class="field-note">Pick the day that works for you.</span></label><label>Party size<input data-testid="party-size-input" name="party_size" type="number" min="1" max="1000" value="2" required><span class="field-note">How many guests?</span></label><button data-testid="search-button" type="submit">Find a table</button></form></section><div class="section-head"><div><span class="eyebrow">Available seating</span><h2>Make room for a good evening</h2></div><span class="hint">Choose an open table or a declared pair.</span></div><div id="results" aria-live="polite"><div class="empty">Choose a restaurant, date and party size to see available tables.</div></div><div id="booking-area"></div>`;const select=document.querySelector(tid('restaurant-select'));select.innerHTML=restaurants.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('');if(restaurant)select.value=restaurant.id;document.getElementById('search-form').onsubmit=e=>{e.preventDefault();selection=null;requestState=null;confirmed=null;document.getElementById('booking-area').innerHTML='';performSearch()};if(lastSearch){select.value=lastSearch.rid;document.querySelector(tid('date-input')).value=lastSearch.date;document.querySelector(tid('party-size-input')).value=lastSearch.party;performSearch()}}
function renderLookup(r){const detail=document.getElementById('lookup-result');const ids=r.table_ids||[r.table_id];const labels=tableLabels(ids);detail.innerHTML=`<section class="panel detail" data-testid="reservation-detail"><span class="eyebrow">Your reservation</span><span class="status-pill status-${esc(r.status)}" data-testid="reservation-status">${esc(r.status)}</span><strong>${esc(restaurant?.name||r.restaurant_id)}</strong><span class="detail-caption">Current seating</span><span data-testid="reservation-tables">${esc(labels.join(' + '))}</span><span class="detail-caption">Date and time</span><time datetime="${esc(r.starts_at_local)}">${esc(r.starts_at_local)}</time><span class="detail-caption">Reference</span><span class="reference">${esc(r.reference)}</span>${r.status==='confirmed'?'<button data-testid="reservation-cancel-button" type="button">Cancel reservation</button>':''}</section>`;const cancel=detail.querySelector(tid('reservation-cancel-button'));if(cancel)cancel.onclick=async()=>{feedback('reservation-error','');try{const {res,data}=await api(`/reservations/${encodeURIComponent(r.reference)}/cancel`,{method:'POST'});if(!res.ok){feedback('reservation-error',data?.error?.message||'This reservation could not be cancelled.');return}renderLookup(data)}catch{feedback('reservation-error','We could not reach the restaurant. Please try again.')}}}
function lookupPage(){app.innerHTML=`${shell('Your plans, close at hand','Reservation lookup','Enter your confirmation reference to see or cancel a reservation.')}<section class="panel lookup-card"><form id="lookup-form" class="auth-form"><label>Confirmation reference<input data-testid="lookup-reference-input" autocomplete="off" required><span class="field-note">You’ll find it in your booking confirmation.</span></label><div id="lookup-feedback" aria-live="polite"></div><button data-testid="lookup-submit" type="submit">Look up reservation</button></form></section><div id="lookup-result" aria-live="polite"></div>`;document.getElementById('lookup-form').onsubmit=async e=>{e.preventDefault();feedback('reservation-error','');document.getElementById('lookup-result').innerHTML='';const ref=e.currentTarget.querySelector('input').value.trim();try{const {res,data}=await api('/reservations/'+encodeURIComponent(ref));if(!res.ok){feedback('reservation-error',data?.error?.message||'Reservation not found.','error',document.getElementById('lookup-feedback'));return}renderLookup(data)}catch{feedback('reservation-error','We could not reach the restaurant. Please try again.','error',document.getElementById('lookup-feedback'))}}}
function renderPage(){updateUser();const path=location.pathname;document.querySelectorAll('.nav a[href]:not(.brand)').forEach(a=>{if(a.getAttribute('href')===path)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});if(path==='/signup'){formPage('signup');return}if(path==='/login'){formPage('login');return}if(path==='/lookup'){lookupPage();return}searchPage()}
async function start(){try{const {res,data}=await api('/restaurants');if(res.ok){const listed=data.restaurants||[];restaurants=await Promise.all(listed.map(r=>getRestaurant(r.id)));restaurants=restaurants.filter(Boolean);if(restaurants.length)restaurant=restaurants[0]}}catch{}renderPage()}
async function getRestaurant(id){try{const {res,data}=await api('/restaurants/'+encodeURIComponent(id));if(res.ok)return data}catch{}return restaurants.find(r=>r.id===id)||null}
start();
})();
</script></body></html>'''


class ApiError(Exception):
    def __init__(self, status, code, message=None):
        self.status, self.code = status, code
        self.message = message or code.replace("_", " ")


def fail(status, code):
    raise ApiError(status, code)


def bad_type():
    fail(400, "malformed_request")


def valid(condition, code="validation_failed"):
    if not condition:
        fail(422, code)


def is_int(value):
    return type(value) is int


def require_str(obj, key, *, special=False):
    if key not in obj:
        fail(422, "validation_failed")
    value = obj[key]
    if not isinstance(value, str):
        if special:
            fail(422, "validation_failed")
        bad_type()
    return value


def obj_body(value):
    if not isinstance(value, dict):
        bad_type()
    return value


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return {"salt": salt.hex(), "digest": digest.hex()}


def check_password(password, record):
    try:
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(record["salt"]),
                                n=2**14, r=8, p=1, dklen=32).hex()
        return hmac.compare_digest(digest, record["digest"])
    except (KeyError, ValueError, TypeError):
        return False


def now_rfc3339():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_local(value):
    if not isinstance(value, str) or not LOCAL_RE.fullmatch(value):
        fail(422, "validation_failed")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        fail(422, "validation_failed")


def resolve_local(naive, zone):
    aware = naive.replace(tzinfo=zone, fold=0)
    # A round trip distinguishes skipped wall times from ordinary/ambiguous times.
    if aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
        fail(422, "invalid_local_time")
    return aware


def parse_clock(value):
    if not isinstance(value, str):
        bad_type()
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        fail(422, "validation_failed")
    try:
        return time.fromisoformat(value)
    except ValueError:
        fail(422, "validation_failed")


def validate_id(value):
    valid(isinstance(value, str) and 1 <= len(value) <= 64)


def build_fixture(fixture):
    obj_body(fixture)
    users_in = fixture.get("users", [])
    restaurants_in = fixture.get("restaurants", [])
    reservations_in = fixture.get("reservations", [])
    for rows in (users_in, restaurants_in, reservations_in):
        if not isinstance(rows, list):
            bad_type()
    new = {"users": {}, "restaurants": {}, "reservations": {}, "tokens": {}, "receipts": {},
           "policies": {}, "histories": {}, "series": {}, "restaurant_revisions": {},
           "closures": {}, "replans": {}}
    for row in users_in:
        obj_body(row)
        uid = require_str(row, "id")
        email = require_str(row, "email")
        password = require_str(row, "password")
        display = require_str(row, "display_name")
        validate_id(uid)
        valid(bool(EMAIL_RE.fullmatch(email)) and len(email) <= 254)
        valid(len(password) >= 8)
        valid(1 <= len(display) <= 100)
        key = email.lower()
        valid(uid not in new["users"] and all(u["email"].lower() != key for u in new["users"].values()))
        new["users"][uid] = {"id": uid, "email": email, "display_name": display,
                             "password_hash": password_hash(password)}
    for row in restaurants_in:
        obj_body(row)
        rid = require_str(row, "id")
        name = require_str(row, "name")
        tzname = require_str(row, "timezone")
        validate_id(rid)
        valid(1 <= len(name) <= 120)
        try:
            ZoneInfo(tzname)
        except (ZoneInfoNotFoundError, ValueError):
            fail(422, "validation_failed")
        settings = {}
        for field in ("slot_minutes", "reservation_duration_minutes", "cancellation_cutoff_minutes"):
            value = row.get(field)
            if not is_int(value):
                bad_type()
            lo, hi = (1, 1440) if field != "cancellation_cutoff_minutes" else (0, 2**31 - 1)
            valid(lo <= value <= hi)
            settings[field] = value
        hours = row.get("opening_hours")
        tables = row.get("tables")
        if not isinstance(hours, list) or not isinstance(tables, list):
            bad_type()
        checked_hours = []
        seen_days = set()
        for entry in hours:
            obj_body(entry)
            wd = require_str(entry, "weekday")
            valid(wd in WEEKDAYS and wd not in seen_days)
            opens, closes = parse_clock(entry.get("opens")), parse_clock(entry.get("closes"))
            valid(opens < closes)
            seen_days.add(wd)
            checked_hours.append({"weekday": wd, "opens": opens.strftime("%H:%M"),
                                  "closes": closes.strftime("%H:%M")})
        checked_tables, table_ids = [], set()
        for table in tables:
            obj_body(table)
            tid = require_str(table, "id")
            label = require_str(table, "label")
            capacity = table.get("capacity")
            validate_id(tid)
            valid(1 <= len(label) <= 64 and is_int(capacity) and 1 <= capacity <= 1000)
            valid(tid not in table_ids)
            table_ids.add(tid)
            checked_tables.append({"id": tid, "label": label, "capacity": capacity})
        combinable = row.get("combinable", [])
        if not isinstance(combinable, list):
            bad_type()
        checked_pairs, seen_pairs = [], set()
        for pair in combinable:
            if not isinstance(pair, list):
                bad_type()
            valid(len(pair) == 2)
            for tid in pair:
                if not isinstance(tid, str):
                    bad_type()
            valid(pair[0] != pair[1] and pair[0] in table_ids and pair[1] in table_ids)
            pair_key = frozenset(pair)
            valid(pair_key not in seen_pairs)
            seen_pairs.add(pair_key)
            checked_pairs.append(list(pair))
        manager_ids = row.get("manager_user_ids",
                              [next(iter(new["users"]))] if new["users"] else [])
        valid(isinstance(manager_ids, list) and
              all(isinstance(user_id, str) and user_id in new["users"]
                  for user_id in manager_ids))
        valid(rid not in new["restaurants"])
        new["restaurants"][rid] = {"id": rid, "name": name, "timezone": tzname, **settings,
                                   "opening_hours": checked_hours, "tables": checked_tables,
                                   "combinable": checked_pairs,
                                   "manager_user_ids": list(manager_ids)}
        new["policies"][rid] = []
        new["restaurant_revisions"][rid] = 0
        new["closures"][rid] = []
    # Seed reservations use the same validation/occupancy contract as live bookings.
    for row in reservations_in:
        obj_body(row)
        uid = require_str(row, "user_id")
        ref = require_str(row, "reference")
        rid = require_str(row, "restaurant_id")
        selection = read_table_selection(row, allow_legacy=True, strict=True)
        local = require_str(row, "starts_at_local", special=True)
        party = row.get("party_size")
        if not is_int(party):
            bad_type()
        res_id = require_str(row, "id")
        valid(uid in new["users"] and rid in new["restaurants"] and REF_RE.fullmatch(ref)
              and len(ref) <= 12 and 1 <= party <= 1000)
        valid(1 <= len(res_id) <= 64)
        restaurant = new["restaurants"][rid]
        tables = resolve_tables(restaurant, selection, fixture=True)
        seeded_status = row.get("status", "confirmed")
        valid(seeded_status in ("confirmed", "cancelled"))
        details = booking_details(restaurant, tables, local, party, new, skip_ref=None,
                                  check_occupancy=seeded_status == "confirmed")
        valid(ref not in new["reservations"] and all(x["id"] != res_id for x in new["reservations"].values()))
        reservation = {"reservation_id": res_id, "reference": ref, "restaurant_id": rid,
                       "table_ids": [t["id"] for t in tables], "party_size": party, "status": seeded_status,
                       "starts_at_local": local, "starts_at": details["starts_at"],
                       "ends_at": details["ends_at"], "created_at": row.get("created_at", now_rfc3339()),
                       "user_id": uid}
        valid(isinstance(reservation["created_at"], str))
        if len(tables) == 1:
            reservation["table_id"] = tables[0]["id"]
        reservation["revision"] = 1
        reservation["accepted_terms"] = policy_terms(new, restaurant, local)
        new["reservations"][ref] = reservation
        append_history(new, reservation, "created", creation_changes(reservation),
                       at=reservation["created_at"])
    return new


def find_table(restaurant, table_id):
    return next((table for table in restaurant["tables"] if table["id"] == table_id), None)


def read_table_selection(body, *, allow_legacy=True, strict=False):
    if "table_id" in body and "table_ids" in body:
        fail(422, "validation_failed")
    if "table_ids" in body:
        value = body["table_ids"]
        if not isinstance(value, list):
            if strict:
                fail(422, "validation_failed")
            bad_type()
        for tid in value:
            if not isinstance(tid, str):
                if strict:
                    fail(422, "validation_failed")
                bad_type()
        valid(1 <= len(value) <= 2, "combination_not_allowed" if len(value) > 2 else "validation_failed")
        valid(len(set(value)) == len(value))
        return list(value)
    if "table_id" in body:
        value = body["table_id"]
        if not isinstance(value, str):
            if strict:
                fail(422, "validation_failed")
            bad_type()
        return [value]
    if allow_legacy:
        fail(422, "validation_failed")
    return None


def res_table_ids(reservation):
    values = reservation.get("table_ids")
    if isinstance(values, list):
        return values
    return [reservation["table_id"]] if isinstance(reservation.get("table_id"), str) else []


def policy_zero(restaurant):
    return {
        "policy_version": 0,
        "slot_minutes": restaurant["slot_minutes"],
        "reservation_duration_minutes": restaurant["reservation_duration_minutes"],
        "cancellation_cutoff_minutes": restaurant["cancellation_cutoff_minutes"],
        "opening_hours": copy.deepcopy(restaurant["opening_hours"]),
        "capacities": {table["id"]: table["capacity"] for table in restaurant["tables"]},
    }


def selected_policy(state, restaurant, local):
    local_date = date.fromisoformat(local) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", local) else parse_local(local).date()
    eligible = [policy for policy in state.get("policies", {}).get(restaurant["id"], [])
                if date.fromisoformat(policy["effective_from"]) <= local_date]
    if not eligible:
        return policy_zero(restaurant)
    return max(eligible, key=lambda policy: (policy["effective_from"], policy["policy_version"]))


def policy_terms(state, restaurant, local):
    policy = selected_policy(state, restaurant, local)
    return {"policy_version": policy["policy_version"],
            "slot_minutes": policy["slot_minutes"],
            "reservation_duration_minutes": policy["reservation_duration_minutes"],
            "cancellation_cutoff_minutes": policy["cancellation_cutoff_minutes"],
            "opening_hours": copy.deepcopy(policy["opening_hours"]),
            "capacities": copy.deepcopy(policy["capacities"])}


def policy_zero_terms(restaurant):
    return policy_zero(restaurant)


def validate_policy(body, restaurant):
    obj_body(body)
    required = ("effective_from", "slot_minutes", "reservation_duration_minutes",
                "cancellation_cutoff_minutes", "opening_hours", "capacities")
    valid(all(key in body for key in required))
    effective = body["effective_from"]
    valid(isinstance(effective, str))
    try:
        parsed = date.fromisoformat(effective)
    except ValueError:
        fail(422, "validation_failed")
    valid(parsed.isoformat() == effective)
    for key in ("slot_minutes", "reservation_duration_minutes"):
        valid(is_int(body[key]) and 1 <= body[key] <= 1440)
    valid(is_int(body["cancellation_cutoff_minutes"]) and
          0 <= body["cancellation_cutoff_minutes"] <= 10080)
    hours = body["opening_hours"]
    valid(isinstance(hours, list))
    checked, seen = [], set()
    for entry in hours:
        valid(isinstance(entry, dict))
        weekday = entry.get("weekday")
        valid(isinstance(weekday, str) and weekday in WEEKDAYS and weekday not in seen and
              isinstance(entry.get("opens"), str) and isinstance(entry.get("closes"), str))
        opens, closes = parse_clock(entry.get("opens")), parse_clock(entry.get("closes"))
        valid(opens < closes)
        seen.add(weekday)
        checked.append({"weekday": weekday, "opens": opens.strftime("%H:%M"),
                        "closes": closes.strftime("%H:%M")})
    capacities = body["capacities"]
    ids = {table["id"] for table in restaurant["tables"]}
    valid(isinstance(capacities, dict) and set(capacities) == ids and
          all(is_int(value) and 1 <= value <= 100 for value in capacities.values()))
    return {"effective_from": effective, "slot_minutes": body["slot_minutes"],
            "reservation_duration_minutes": body["reservation_duration_minutes"],
            "cancellation_cutoff_minutes": body["cancellation_cutoff_minutes"],
            "opening_hours": checked, "capacities": copy.deepcopy(capacities)}


def current_series(state, series_id, uid):
    series = state.get("series", {}).get(series_id)
    if not series or series.get("user_id") != uid:
        fail(404, "not_found")
    response = {key: copy.deepcopy(value) for key, value in series.items()
                if key not in ("user_id", "occurrences")}
    response["occurrences"] = []
    for item in series["occurrences"]:
        response["occurrences"].append({"index": item["index"], "reference": item["reference"],
            "exception": item["exception"],
            "reservation": public_reservation(state["reservations"][item["reference"]])})
    return response


def creation_changes(reservation):
    table_ids = res_table_ids(reservation)
    if len(table_ids) > 1:
        table_change = {"field": "table_ids", "from": None, "to": list(table_ids)}
    else:
        table_change = {"field": "table_id", "from": None, "to": table_ids[0]}
    return [table_change,
            {"field": "starts_at_local", "from": None, "to": reservation["starts_at_local"]},
            {"field": "party_size", "from": None, "to": reservation["party_size"]}]


def selection_change(before, after):
    old_ids, new_ids = res_table_ids(before), res_table_ids(after)
    if old_ids == new_ids:
        return None
    if len(old_ids) > 1 or len(new_ids) > 1:
        return {"field": "table_ids", "from": list(old_ids), "to": list(new_ids)}
    return {"field": "table_id", "from": old_ids[0], "to": new_ids[0]}


def append_history(state, reservation, event, changes, *, at=None):
    reference = reservation["reference"]
    rows = state.setdefault("histories", {}).setdefault(reference, [])
    rows.append({"seq": len(rows) + 1, "at": at or now_rfc3339(), "event": event,
                 "changes": copy.deepcopy(changes), "revision": reservation["revision"],
                 "accepted_terms": copy.deepcopy(reservation["accepted_terms"])})


def reservation_cutoff(reservation):
    cutoff = reservation["accepted_terms"]["cancellation_cutoff_minutes"]
    return (datetime.fromisoformat(reservation["starts_at"]).astimezone(timezone.utc) -
            timedelta(minutes=cutoff))


def reservation_in_series(state, reference):
    for series in state.get("series", {}).values():
        for occurrence in series["occurrences"]:
            if occurrence["reference"] == reference:
                return series, occurrence
    return None, None


def bump_series_for_reservations(state, references, *, exception):
    affected = {}
    for reference in references:
        series, occurrence = reservation_in_series(state, reference)
        if series is None:
            continue
        affected[series["series_id"]] = series
        if exception:
            occurrence["exception"] = True
    for series in affected.values():
        series["revision"] += 1


def bump_restaurant_revision(state, restaurant_id):
    revisions = state.setdefault("restaurant_revisions", {})
    revisions[restaurant_id] = revisions.get(restaurant_id, 0) + 1


def has_overlap(state, restaurant_id, table_ids, start_utc, end_utc, skip_ref=None):
    selected = set(table_ids)
    for existing in state["reservations"].values():
        if (existing["reference"] == skip_ref or existing["status"] != "confirmed" or
                existing["restaurant_id"] != restaurant_id or
                not selected.intersection(res_table_ids(existing))):
            continue
        other_start = datetime.fromisoformat(existing["starts_at"]).astimezone(timezone.utc)
        other_end = datetime.fromisoformat(existing["ends_at"]).astimezone(timezone.utc)
        if start_utc < other_end and other_start < end_utc:
            return True
    return False


def closure_overlap(state, restaurant_id, table_ids, start_utc, end_utc):
    selected = set(table_ids)
    for closure in state.get("closures", {}).get(restaurant_id, []):
        if closure["table_id"] not in selected:
            continue
        closed_from = datetime.fromisoformat(closure["from"]).astimezone(timezone.utc)
        closed_to = datetime.fromisoformat(closure["to"]).astimezone(timezone.utc)
        if start_utc < closed_to and closed_from < end_utc:
            return True
    return False


def resolve_tables(restaurant, selection, fixture=False):
    if len(selection) > 2:
        fail(422, "combination_not_allowed")
    tables = [find_table(restaurant, tid) for tid in selection]
    if any(table is None for table in tables):
        fail(422 if fixture else 404, "validation_failed" if fixture else "not_found")
    if len(tables) == 2:
        pair = next((declared for declared in restaurant.get("combinable", [])
                     if frozenset(declared) == frozenset(selection)), None)
        if pair is None:
            fail(422, "combination_not_allowed")
        tables = [find_table(restaurant, tid) for tid in pair]
    return tables


def booking_details(restaurant, tables, local, party, state, skip_ref=None, check_occupancy=True,
                    policy=None):
    naive = parse_local(local)
    zone = ZoneInfo(restaurant["timezone"])
    aware = resolve_local(naive, zone)
    policy = policy or selected_policy(state, restaurant, local)
    weekday = WEEKDAYS[naive.weekday()]
    hours = next((h for h in policy["opening_hours"] if h["weekday"] == weekday), None)
    if not hours:
        fail(422, "outside_opening_hours")
    opens, closes = parse_clock(hours["opens"]), parse_clock(hours["closes"])
    start_clock = naive.time()
    if start_clock < opens or start_clock >= closes:
        fail(422, "outside_opening_hours")
    offset_minutes = int((datetime.combine(naive.date(), start_clock) -
                          datetime.combine(naive.date(), opens)).total_seconds() // 60)
    if offset_minutes % policy["slot_minutes"]:
        fail(422, "not_on_slot_grid")
    end_utc = aware.astimezone(timezone.utc) + timedelta(minutes=policy["reservation_duration_minutes"])
    end_zone = end_utc.astimezone(zone)
    if end_zone.date() != naive.date() or end_zone.time().replace(tzinfo=None) > closes:
        fail(422, "outside_opening_hours")
    capacity = sum(policy["capacities"][table["id"]] for table in tables)
    if party > capacity:
        fail(422, "party_exceeds_capacity")
    start_utc = aware.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(minutes=policy["reservation_duration_minutes"])
    if check_occupancy and closure_overlap(state, restaurant["id"], [table["id"] for table in tables], start_utc, end_utc):
        fail(409, "table_unavailable")
    if check_occupancy and has_overlap(state, restaurant["id"],
                                       [table["id"] for table in tables],
                                       start_utc, end_utc, skip_ref):
        fail(409, "table_unavailable")
    return {"starts_at": aware.isoformat(timespec="seconds"),
            "ends_at": end_utc.astimezone(zone).isoformat(timespec="seconds"),
            "start_utc": start_utc, "end_utc": end_utc,
            "policy": copy.deepcopy(policy)}


def public_reservation(reservation):
    result = {k: v for k, v in reservation.items() if k != "user_id"}
    ids = res_table_ids(reservation)
    result["table_ids"] = list(ids)
    if len(ids) == 1:
        result["table_id"] = ids[0]
    else:
        result.pop("table_id", None)
    return result


def resolve_user(state, token_header):
    if not isinstance(token_header, str) or not token_header.startswith("Bearer "):
        fail(401, "unauthenticated")
    token = token_header[7:]
    uid = state["tokens"].get(token)
    if not uid or uid not in state["users"]:
        fail(401, "unauthenticated")
    return uid


def validate_body_fields(body):
    # Unknown fields are ignored. Validate known field types before semantic checks.
    for key in ("restaurant_id", "table_id"):
        if key in body and not isinstance(body[key], str):
            bad_type()
    if "starts_at_local" in body and not isinstance(body["starts_at_local"], str):
        fail(422, "validation_failed")
    if "party_size" in body and not is_int(body["party_size"]):
        fail(422, "validation_failed")
    if "table_ids" in body:
        if not isinstance(body["table_ids"], list):
            bad_type()
        if any(not isinstance(tid, str) for tid in body["table_ids"]):
            bad_type()
    if "expected_revision" in body:
        valid(is_int(body["expected_revision"]) and body["expected_revision"] > 0)


def check_expected_revision(body, reservation):
    if "expected_revision" not in body:
        return
    revision = body["expected_revision"]
    valid(is_int(revision) and revision > 0)
    if revision != reservation["revision"]:
        fail(409, "stale_revision")


def response_reservation(state, ref):
    return public_reservation(state["reservations"][ref])


class Handler(BaseHTTPRequestHandler):
    server_version = "Tablekeeper/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_json(self, status, value=None):
        payload = b"" if status == 204 else json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def send_html(self, status, value):
        payload = value.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status, code):
        self.send_json(status, {"error": {"code": code, "message": code.replace("_", " ")}})

    def read_json(self):
        length = self.headers.get("Content-Length")
        if length is None:
            return None
        try:
            count = int(length)
            if count < 0 or count > 2_000_000:
                raise ValueError()
            if count == 0:
                return None
            data = self.rfile.read(count)
            return json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            fail(400, "malformed_request")

    def handle_request(self):
        path = urlsplit(self.path)
        route = unquote(path.path)
        method = self.command
        body = None
        if method in ("POST", "PATCH", "PUT"):
            body = self.read_json()
        with LOCK:
            # Idempotency is checked after parse and authentication, before request validation.
            public = (method == "GET" and (route in ("/restaurants", "/availability") or
                      route.startswith("/restaurants/")))
            auth_exempt = route in ("/health", "/_test/reset", "/_test/export", "/_test/import",
                                    "/auth/signup", "/auth/login", "/", "/signup", "/login", "/lookup")
            if method == "GET" and (re.fullmatch(r"/reservations/[^/]+/(?:history|decision)", route) or
                                     re.fullmatch(r"/series/[^/]+", route)):
                auth_exempt = True
            uid = None
            private_read = method == "GET" and (re.fullmatch(r"/reservations/[^/]+/(?:history|decision)", route) or
                                                  re.fullmatch(r"/series/[^/]+", route))
            if private_read and self.headers.get("Authorization"):
                try:
                    uid = resolve_user(STATE, self.headers.get("Authorization"))
                except ApiError:
                    uid = None
            elif not public and not auth_exempt:
                uid = resolve_user(STATE, self.headers.get("Authorization"))
            is_policy_write = bool(re.fullmatch(r"/restaurants/[^/]+/policies", route))
            is_replan_preview = bool(re.fullmatch(r"/restaurants/[^/]+/replans", route))
            is_replan_apply = bool(re.fullmatch(r"/restaurants/[^/]+/replans/[^/]+/apply", route))
            is_series_amend = bool(re.fullmatch(r"/series/[^/]+/amend", route))
            idempotent_write = (method == "POST" and
                                (route in ("/reservations", "/reservation-moves", "/series") or
                                 is_policy_write or is_replan_preview or is_replan_apply or
                                 is_series_amend))
            if idempotent_write:
                body = obj_body(body)
                key = self.headers.get("Idempotency-Key", "")
                if not key:
                    fail(400, "missing_idempotency_key")
                valid(1 <= len(key) <= 255)
                rkey = uid + "\0" + key
                existing = STATE["receipts"].get(rkey)
                if existing:
                    if existing["method"] != method or existing["path"] != route or existing["body"] != body:
                        fail(409, "idempotency_key_reuse")
                    self.send_json(200, existing["response"])
                    return
            status, result = self.dispatch(method, route, parse_qs(path.query, keep_blank_values=True), body, uid)
            if status == 201 and idempotent_write:
                rkey = uid + "\0" + key
                STATE["receipts"][rkey] = {"method": method, "path": route,
                                            "body": copy.deepcopy(body), "response": copy.deepcopy(result)}
            if method == "GET" and route in ("/", "/signup", "/login", "/lookup"):
                self.send_html(status, result)
            else:
                self.send_json(status, result)

    def _handle(self):
        try:
            self.handle_request()
        except ApiError as exc:
            self.send_error_json(exc.status, exc.code)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            try:
                self.send_error_json(500, "internal_error")
            except (BrokenPipeError, ConnectionResetError):
                pass

    do_GET = _handle
    do_POST = _handle
    do_PATCH = _handle
    do_PUT = _handle
    do_DELETE = _handle

    def dispatch(self, method, route, query, body, uid):
        global STATE
        if method == "GET" and route in ("/", "/signup", "/login", "/lookup"):
            return 200, APP_HTML
        if method == "GET" and route == "/health":
            return 200, {"status": "ok"}
        if method == "POST" and route == "/_test/reset":
            STATE = build_fixture(obj_body(body))
            return 204, None
        if method == "GET" and route == "/_test/export":
            return 200, {"track": "tablekeeper", "format_version": 1,
                         "state": copy.deepcopy(STATE)}
        if method == "POST" and route == "/_test/import":
            obj_body(body)
            legacy_export = {"users", "restaurants", "reservations", "tokens", "idempotency"}
            if set(body) == legacy_export:
                imported = body
            else:
                valid(body.get("track") == "tablekeeper" and
                      type(body.get("format_version")) is int and
                      body.get("format_version") == 1)
                imported = body.get("state")
            if not isinstance(imported, dict):
                fail(422, "validation_failed")
            imported = adapt_legacy_import_state(imported)
            imported = upgrade_stage2_state(imported)
            imported = upgrade_stage4_state(imported)
            validate_import_state(imported)
            STATE = copy.deepcopy(imported)
            return 204, None
        if method == "POST" and route in ("/auth/signup", "/auth/login"):
            obj_body(body)
            for field in ("email", "password"):
                if field in body and not isinstance(body[field], str):
                    bad_type()
            email, password = body.get("email"), body.get("password")
            valid(isinstance(email, str) and bool(EMAIL_RE.fullmatch(email)) and len(email) <= 254)
            valid(isinstance(password, str))
            if route == "/auth/signup":
                if "display_name" not in body:
                    fail(422, "validation_failed")
                display = body["display_name"]
                if not isinstance(display, str):
                    bad_type()
                valid(len(password) >= 8 and 1 <= len(display) <= 100)
                if any(u["email"].lower() == email.lower() for u in STATE["users"].values()):
                    fail(409, "email_taken")
                uid = "u_" + uuid.uuid4().hex
                user = {"id": uid, "email": email, "display_name": display,
                        "password_hash": password_hash(password)}
                STATE["users"][uid] = user
                token = secrets.token_urlsafe(32)
                STATE["tokens"][token] = uid
                return 201, {"user_id": uid, "display_name": display, "token": token}
            user = next((u for u in STATE["users"].values() if u["email"].lower() == email.lower()), None)
            if not user or not check_password(password, user["password_hash"]):
                fail(401, "unauthenticated")
            token = secrets.token_urlsafe(32)
            STATE["tokens"][token] = user["id"]
            return 200, {"user_id": user["id"], "display_name": user["display_name"], "token": token}
        if method == "GET" and route == "/restaurants":
            return 200, {"restaurants": [{"id": r["id"], "name": r["name"], "timezone": r["timezone"]}
                                           for r in STATE["restaurants"].values()]}
        match = re.fullmatch(r"/restaurants/([^/]+)", route)
        if method == "GET" and match:
            restaurant = STATE["restaurants"].get(match.group(1))
            if not restaurant:
                fail(404, "not_found")
            return 200, copy.deepcopy(restaurant)
        match = re.fullmatch(r"/restaurants/([^/]+)/policies", route)
        if match and method == "GET":
            rid = match.group(1)
            if rid not in STATE["restaurants"]:
                fail(404, "not_found")
            return 200, {"policies": copy.deepcopy(STATE["policies"][rid])}
        if match and method == "POST":
            rid = match.group(1)
            restaurant = STATE["restaurants"].get(rid)
            if not restaurant:
                fail(404, "not_found")
            if uid not in restaurant.get("manager_user_ids", []):
                fail(403, "forbidden")
            policy = validate_policy(body, restaurant)
            policy["policy_version"] = len(STATE["policies"][rid]) + 1
            STATE["policies"][rid].append(policy)
            bump_restaurant_revision(STATE, rid)
            return 201, copy.deepcopy(policy)
        if method == "GET" and route == "/availability":
            rid = single_param(query, "restaurant_id")
            date_value = single_param(query, "date")
            party_text = single_param(query, "party_size")
            valid(rid is not None and date_value is not None and party_text is not None)
            explain_values = query.get("explain")
            if explain_values is not None:
                valid(len(explain_values) == 1 and explain_values[0] == "true")
            restaurant = STATE["restaurants"].get(rid)
            if not restaurant:
                fail(404, "not_found")
            valid(re.fullmatch(r"\d+", party_text) is not None)
            party = int(party_text)
            valid(1 <= party <= 1000)
            try:
                target_date = date.fromisoformat(date_value)
            except ValueError:
                fail(422, "validation_failed")
            if target_date.isoformat() != date_value:
                fail(422, "validation_failed")
            policy = selected_policy(STATE, restaurant, date_value)
            hours = next((h for h in policy["opening_hours"] if h["weekday"] == WEEKDAYS[target_date.weekday()]), None)
            slots = []
            if hours:
                opens, closes = parse_clock(hours["opens"]), parse_clock(hours["closes"])
                minute = opens.hour * 60 + opens.minute
                close_min = closes.hour * 60 + closes.minute
                while minute + policy["reservation_duration_minutes"] <= close_min:
                    naive = datetime.combine(target_date, time(minute // 60, minute % 60))
                    try:
                        aware = resolve_local(naive, ZoneInfo(restaurant["timezone"]))
                    except ApiError as exc:
                        if exc.code != "invalid_local_time":
                            raise
                        minute += restaurant["slot_minutes"]
                        continue
                    end_utc = aware.astimezone(timezone.utc) + timedelta(minutes=policy["reservation_duration_minutes"])
                    end_local = end_utc.astimezone(ZoneInfo(restaurant["timezone"]))
                    if end_local.date() == target_date and end_local.time().replace(tzinfo=None) <= closes:
                        available = []
                        options = []
                        explanations = []
                        for table in restaurant["tables"]:
                            cap_holds = policy["capacities"][table["id"]] >= party
                            free_start = aware.astimezone(timezone.utc)
                            overlap_holds = not has_overlap(STATE, rid, [table["id"]], free_start, end_utc) and not closure_overlap(STATE, rid, [table["id"]], free_start, end_utc)
                            is_available = cap_holds and overlap_holds
                            if is_available:
                                available.append(table["id"])
                                options.append({"table_ids": [table["id"]], "capacity": policy["capacities"][table["id"]]})
                            explanations.append({"table_id": table["id"], "policy_version": policy["policy_version"],
                                "available": is_available, "rules": [{"rule": "capacity", "holds": cap_holds},
                                {"rule": "no_overlap", "holds": overlap_holds}]})
                        for pair in restaurant.get("combinable", []):
                            tables = [find_table(restaurant, tid) for tid in pair]
                            cap = sum(policy["capacities"][t["id"]] for t in tables)
                            cap_holds = cap >= party
                            free_start = aware.astimezone(timezone.utc)
                            overlap_holds = not has_overlap(STATE, rid, pair, free_start, end_utc) and not closure_overlap(STATE, rid, pair, free_start, end_utc)
                            if cap_holds and overlap_holds:
                                options.append({"table_ids": list(pair),
                                                "capacity": cap})
                        slot = {"starts_at_local": naive.strftime("%Y-%m-%dT%H:%M"),
                                      "starts_at": aware.isoformat(timespec="seconds"),
                                      "available_table_ids": available,
                                      "available_options": options}
                        if explain_values is not None:
                            slot["explain"] = explanations
                        slots.append(slot)
                    minute += policy["slot_minutes"]
            return 200, {"restaurant_id": rid, "date": date_value,
                         "timezone": restaurant["timezone"], "slots": slots}
        if method == "POST" and route == "/reservations":
            validate_body_fields(body)
            rid = require_str(body, "restaurant_id")
            selection = read_table_selection(body, allow_legacy=False)
            if selection is None:
                fail(422, "validation_failed")
            local = require_str(body, "starts_at_local", special=True)
            party = body.get("party_size")
            if not is_int(party):
                fail(422, "validation_failed")
            valid(1 <= party <= 1000)
            restaurant = STATE["restaurants"].get(rid)
            if not restaurant:
                fail(404, "not_found")
            tables = resolve_tables(restaurant, selection)
            details = booking_details(restaurant, tables, local, party, STATE)
            ref = make_reference()
            res_id = "res_" + uuid.uuid4().hex
            reservation = {"reservation_id": res_id, "reference": ref, "restaurant_id": rid,
                           "table_ids": [t["id"] for t in tables], "party_size": party, "status": "confirmed",
                           "starts_at_local": local, "starts_at": details["starts_at"],
                           "ends_at": details["ends_at"], "created_at": now_rfc3339(), "user_id": uid,
                           "revision": 1, "accepted_terms": policy_terms(STATE, restaurant, local)}
            if len(tables) == 1:
                reservation["table_id"] = tables[0]["id"]
            STATE["reservations"][ref] = reservation
            append_history(STATE, reservation, "created", creation_changes(reservation))
            bump_restaurant_revision(STATE, rid)
            return 201, public_reservation(reservation)
        if method == "GET" and route == "/reservations":
            rows = [public_reservation(r) for r in STATE["reservations"].values() if r["user_id"] == uid]
            rows.sort(key=lambda r: datetime.fromisoformat(r["starts_at"]).astimezone(timezone.utc), reverse=True)
            return 200, {"reservations": rows}
        match = re.fullmatch(r"/reservations/([^/]+)(?:/(cancel))?", route)
        history_match = re.fullmatch(r"/reservations/([^/]+)/(history|decision)", route)
        if history_match and method == "GET":
            ref, suffix = history_match.groups()
            reservation = STATE["reservations"].get(ref)
            if not reservation or reservation["user_id"] != uid:
                fail(404, "not_found")
            if suffix == "history":
                return 200, {"reference": ref, "entries": copy.deepcopy(STATE["histories"].get(ref, []))}
            return 200, {"reference": ref, "revision": reservation["revision"],
                         "accepted_terms": copy.deepcopy(reservation["accepted_terms"])}
        series_match = re.fullmatch(r"/series/([^/]+)", route)
        if series_match and method == "GET":
            return 200, current_series(STATE, series_match.group(1), uid)
        if method == "POST" and route == "/series":
            return 201, self.create_series(body, uid)
        amend_match = re.fullmatch(r"/series/([^/]+)/amend", route)
        if method == "POST" and amend_match:
            return 201, self.amend_series(amend_match.group(1), body, uid)
        preview_match = re.fullmatch(r"/restaurants/([^/]+)/replans", route)
        if method == "POST" and preview_match:
            return 201, self.preview_replan(preview_match.group(1), body, uid)
        apply_match = re.fullmatch(r"/restaurants/([^/]+)/replans/([^/]+)/apply", route)
        if method == "POST" and apply_match:
            return 201, self.apply_replan(apply_match.group(1), apply_match.group(2), uid)
        if match:
            ref, cancel_suffix = match.group(1), match.group(2)
            reservation = STATE["reservations"].get(ref)
            if not reservation or reservation["user_id"] != uid:
                fail(404, "not_found")
            restaurant = STATE["restaurants"][reservation["restaurant_id"]]
            if method == "GET" and not cancel_suffix:
                return 200, public_reservation(reservation)
            if method == "POST" and cancel_suffix:
                if reservation["status"] == "cancelled":
                    return 200, public_reservation(reservation)
                cutoff = reservation_cutoff(reservation)
                if datetime.now(timezone.utc) >= cutoff:
                    fail(409, "cutoff_passed")
                reservation["status"] = "cancelled"
                reservation["revision"] += 1
                append_history(STATE, reservation, "cancelled", [])
                bump_series_for_reservations(STATE, [ref], exception=False)
                bump_restaurant_revision(STATE, reservation["restaurant_id"])
                return 200, public_reservation(reservation)
            if method == "PATCH" and not cancel_suffix:
                body = obj_body(body)
                return 200, self.patch_one(ref, body)
        if method == "POST" and route == "/reservation-moves":
            return 201, self.move_batch(body, uid)
        fail(404, "not_found")

    def patch_one(self, ref, body):
        reservation = STATE["reservations"][ref]
        check_expected_revision(body, reservation)
        if reservation["status"] == "cancelled":
            fail(409, "reservation_cancelled")
        restaurant = STATE["restaurants"][reservation["restaurant_id"]]
        if datetime.now(timezone.utc) >= reservation_cutoff(reservation):
            fail(409, "cutoff_passed")
        validate_body_fields(body)
        rid = reservation["restaurant_id"]
        selection = read_table_selection(body, allow_legacy=False)
        if selection is None:
            selection = res_table_ids(reservation)
        local = body.get("starts_at_local", reservation["starts_at_local"])
        party = body.get("party_size", reservation["party_size"])
        valid(isinstance(local, str) and is_int(party) and 1 <= party <= 1000)
        tables = resolve_tables(restaurant, selection)
        new_ids = [table["id"] for table in tables]
        if (new_ids == res_table_ids(reservation) and local == reservation["starts_at_local"]
                and party == reservation["party_size"]):
            return public_reservation(reservation)
        details = booking_details(restaurant, tables, local, party, STATE, skip_ref=ref)
        changed = copy.deepcopy(reservation)
        changed.pop("table_id", None)
        changed.update(table_ids=new_ids, starts_at_local=local, party_size=party,
                           starts_at=details["starts_at"], ends_at=details["ends_at"])
        if len(tables) == 1:
            changed["table_id"] = tables[0]["id"]
        changes = []
        table_change = selection_change(reservation, changed)
        if table_change:
            changes.append(table_change)
        if reservation["starts_at_local"] != local:
            changes.append({"field": "starts_at_local", "from": reservation["starts_at_local"], "to": local})
        if reservation["party_size"] != party:
            changes.append({"field": "party_size", "from": reservation["party_size"], "to": party})
        changed["revision"] += 1
        changed["accepted_terms"] = policy_terms(STATE, restaurant, local)
        STATE["reservations"][ref] = changed
        append_history(STATE, changed, "changed", changes)
        series, occurrence = reservation_in_series(STATE, ref)
        if series:
            occurrence["exception"] = True
            series["revision"] += 1
        bump_restaurant_revision(STATE, reservation["restaurant_id"])
        return public_reservation(changed)

    def amend_series(self, series_id, body, uid):
        obj_body(body)
        series = STATE["series"].get(series_id)
        if not series or series.get("user_id") != uid:
            fail(404, "not_found")
        expected = body.get("expected_revision")
        from_index = body.get("from_index")
        local_time = body.get("local_time")
        valid(is_int(expected) and expected >= 1 and is_int(from_index) and
              0 <= from_index < len(series["occurrences"]) and isinstance(local_time, str) and
              re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", local_time) is not None)
        if expected != series["revision"]:
            fail(409, "stale_revision")
        staged = copy.deepcopy(STATE)
        staged_series = staged["series"][series_id]
        restaurant_id = next(staged["reservations"][item["reference"]]["restaurant_id"]
                             for item in staged_series["occurrences"])
        restaurant = staged["restaurants"][restaurant_id]
        now = datetime.now(timezone.utc)
        eligible = [item for item in staged_series["occurrences"]
                    if item["index"] >= from_index and not item["exception"] and
                    staged["reservations"][item["reference"]]["status"] == "confirmed"]
        changes = []
        # Hide all old positions while constructing the final set; every check runs before commit.
        for item in eligible:
            staged["reservations"][item["reference"]]["status"] = "__amending__"
        for item in eligible:
            ref = item["reference"]
            old = STATE["reservations"][ref]
            naive = parse_local(old["starts_at_local"])
            new_local = datetime.combine(naive.date(), parse_clock(local_time)).strftime("%Y-%m-%dT%H:%M")
            if new_local == old["starts_at_local"]:
                staged["reservations"][ref] = copy.deepcopy(old)
                continue
            if now >= reservation_cutoff(old):
                fail(409, "cutoff_passed")
            tables = resolve_tables(restaurant, res_table_ids(old))
            terms = policy_terms(staged, restaurant, new_local)
            details = booking_details(restaurant, tables, new_local, old["party_size"], staged,
                                      skip_ref=ref, check_occupancy=False, policy=terms)
            changed = copy.deepcopy(old)
            changed.update(starts_at_local=new_local, starts_at=details["starts_at"],
                           ends_at=details["ends_at"], accepted_terms=terms)
            changed["revision"] += 1
            staged["reservations"][ref] = changed
            changes.append((ref, old, changed))
        for item in eligible:
            ref = item["reference"]
            if staged["reservations"][ref]["status"] == "__amending__":
                staged["reservations"][ref]["status"] = "confirmed"
        # Non-occupancy validation above has precedence over all occupancy conflicts.
        for ref, old, changed in changes:
            tables = resolve_tables(restaurant, res_table_ids(changed))
            booking_details(restaurant, tables, changed["starts_at_local"], changed["party_size"],
                            staged, skip_ref=ref, policy=changed["accepted_terms"])
        if changes:
            for ref, old, changed in changes:
                staged["reservations"][ref] = changed
                append_history(staged, changed, "changed", [{"field": "starts_at_local",
                    "from": old["starts_at_local"], "to": changed["starts_at_local"]}])
            staged_series["revision"] += 1
            bump_restaurant_revision(staged, restaurant_id)
        result = current_series(staged, series_id, uid)
        STATE.clear()
        STATE.update(staged)
        return result

    def preview_replan(self, restaurant_id, body, uid):
        restaurant = STATE["restaurants"].get(restaurant_id)
        if not restaurant:
            fail(404, "not_found")
        if uid not in restaurant.get("manager_user_ids", []):
            fail(403, "forbidden")
        obj_body(body)
        table_id = require_str(body, "table_id")
        table = find_table(restaurant, table_id)
        if table is None:
            fail(404, "not_found")
        start_text, end_text = require_str(body, "from"), require_str(body, "to")
        try:
            start, end = datetime.fromisoformat(start_text), datetime.fromisoformat(end_text)
        except ValueError:
            fail(422, "validation_failed")
        valid(start.tzinfo is not None and start.utcoffset() is not None and
              end.tzinfo is not None and end.utcoffset() is not None and start < end)
        start_utc, end_utc = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        considered = [r for r in STATE["reservations"].values()
                      if r["restaurant_id"] == restaurant_id and r["status"] == "confirmed" and
                      start_utc < datetime.fromisoformat(r["ends_at"]).astimezone(timezone.utc) and
                      datetime.fromisoformat(r["starts_at"]).astimezone(timezone.utc) < end_utc]
        considered.sort(key=lambda r: r["reference"])
        if (len(restaurant["tables"]) > 6 or len(restaurant.get("combinable", [])) > 4 or
                len(considered) > 6):
            fail(422, "planning_limit")
        table_options = [[t["id"]] for t in restaurant["tables"]] + [list(p) for p in restaurant.get("combinable", [])]
        fixed = [r for r in STATE["reservations"].values() if r["restaurant_id"] == restaurant_id and
                 r["status"] == "confirmed" and r not in considered]
        options = {}
        for reservation in considered:
            terms = reservation["accepted_terms"]
            choices = []
            rstart = datetime.fromisoformat(reservation["starts_at"]).astimezone(timezone.utc)
            rend = datetime.fromisoformat(reservation["ends_at"]).astimezone(timezone.utc)
            for rank, ids in enumerate(table_options):
                capacity = sum(terms["capacities"].get(tid, -1) for tid in ids)
                if capacity < reservation["party_size"] or closure_overlap(STATE, restaurant_id, ids, rstart, rend):
                    continue
                if table_id in ids and rstart < end_utc and start_utc < rend:
                    continue
                conflict = False
                for other in fixed:
                    if not set(ids).intersection(res_table_ids(other)):
                        continue
                    os = datetime.fromisoformat(other["starts_at"]).astimezone(timezone.utc)
                    oe = datetime.fromisoformat(other["ends_at"]).astimezone(timezone.utc)
                    if rstart < oe and os < rend:
                        conflict = True
                        break
                if not conflict:
                    choices.append((rank, ids, capacity))
            options[reservation["reference"]] = choices
        best = None
        chosen = []
        def search(index):
            nonlocal best
            if index == len(considered):
                moved = sum(list(ids) != res_table_ids(reservation)
                            for reservation, (_, ids, _) in zip(considered, chosen))
                unused = sum(capacity - reservation["party_size"]
                             for reservation, (_, _, capacity) in zip(considered, chosen))
                ranks = tuple(rank for rank, _, _ in chosen)
                score = (moved, unused, ranks)
                if best is None or score < best[0]:
                    best = (score, list(chosen))
                return
            reservation = considered[index]
            rstart = datetime.fromisoformat(reservation["starts_at"]).astimezone(timezone.utc)
            rend = datetime.fromisoformat(reservation["ends_at"]).astimezone(timezone.utc)
            for choice in options[reservation["reference"]]:
                _, ids, _ = choice
                if any(set(ids).intersection(set(prev[1])) and
                       rstart < datetime.fromisoformat(prev_res["ends_at"]).astimezone(timezone.utc) and
                       datetime.fromisoformat(prev_res["starts_at"]).astimezone(timezone.utc) < rend
                       for prev_res, prev in zip(considered[:index], chosen)):
                    continue
                chosen.append(choice)
                search(index + 1)
                chosen.pop()
        search(0)
        if best is None:
            fail(409, "no_feasible_plan")
        assignments = [{"reference": reservation["reference"], "table_ids": list(choice[1]),
                        "changed": list(choice[1]) != res_table_ids(reservation)}
                       for reservation, choice in zip(considered, best[1])]
        plan_id = "plan_" + uuid.uuid4().hex
        result = {"plan_id": plan_id, "restaurant_revision": STATE["restaurant_revisions"][restaurant_id],
                  "closure": {"table_id": table_id, "from": start_text, "to": end_text},
                  "assignments": assignments, "moved_count": best[0][0], "unused_seats": best[0][1]}
        STATE["replans"][plan_id] = {"restaurant_id": restaurant_id, "owner_user_id": uid,
            "restaurant_revision": result["restaurant_revision"], "closure": copy.deepcopy(result["closure"]),
            "assignments": copy.deepcopy(assignments), "response": copy.deepcopy(result),
            "applied_key": None, "applied_response": None}
        return result

    def apply_replan(self, restaurant_id, plan_id, uid):
        plan = STATE["replans"].get(plan_id)
        if not plan or plan["restaurant_id"] != restaurant_id:
            fail(404, "not_found")
        restaurant = STATE["restaurants"].get(restaurant_id)
        if not restaurant:
            fail(404, "not_found")
        if uid not in restaurant.get("manager_user_ids", []):
            fail(403, "forbidden")
        key = self.headers.get("Idempotency-Key", "")
        receipt_id = uid + "\0" + key
        if plan["applied_key"] is not None:
            if plan["applied_key"] == receipt_id:
                return copy.deepcopy(plan["applied_response"])
            fail(409, "plan_already_applied")
        if STATE["restaurant_revisions"][restaurant_id] != plan["restaurant_revision"]:
            fail(409, "stale_plan")
        staged = copy.deepcopy(STATE)
        staged_plan = staged["replans"][plan_id]
        moved_refs = []
        results = []
        for assignment in plan["assignments"]:
            ref = assignment["reference"]
            reservation = staged["reservations"].get(ref)
            if not reservation or reservation["status"] != "confirmed":
                fail(409, "stale_plan")
            old_ids = res_table_ids(reservation)
            new_ids = assignment["table_ids"]
            if assignment["changed"]:
                reservation.pop("table_id", None)
                reservation["table_ids"] = list(new_ids)
                if len(new_ids) == 1:
                    reservation["table_id"] = new_ids[0]
                reservation["revision"] += 1
                entry = append_history(staged, reservation, "reassigned", [{"field": "table_ids",
                    "from": list(old_ids), "to": list(new_ids)}])
                staged["histories"][ref][-1]["plan_id"] = plan_id
                moved_refs.append(ref)
            results.append(public_reservation(reservation))
        closure = copy.deepcopy(plan["closure"])
        staged["closures"].setdefault(restaurant_id, []).append(closure)
        affected = {reservation_in_series(staged, ref)[0]["series_id"]
                    for ref in moved_refs if reservation_in_series(staged, ref)[0]}
        for sid in affected:
            staged["series"][sid]["revision"] += 1
        bump_restaurant_revision(staged, restaurant_id)
        result = {"plan_id": plan_id, "restaurant_revision": staged["restaurant_revisions"][restaurant_id],
                  "reservations": results}
        staged_plan["applied_key"] = receipt_id
        staged_plan["applied_response"] = copy.deepcopy(result)
        STATE.clear()
        STATE.update(staged)
        return result

    def create_series(self, body, uid):
        obj_body(body)
        anchor_ref = body.get("anchor_reference")
        count = body.get("count")
        interval = body.get("interval_weeks")
        valid(isinstance(anchor_ref, str))
        valid(is_int(count) and 2 <= count <= 12 and is_int(interval) and 1 <= interval <= 4)
        anchor = STATE["reservations"].get(anchor_ref)
        if not anchor or anchor["user_id"] != uid:
            fail(404, "not_found")
        if anchor["status"] == "cancelled":
            fail(409, "reservation_cancelled")
        if datetime.now(timezone.utc) >= reservation_cutoff(anchor):
            fail(409, "cutoff_passed")
        if reservation_in_series(STATE, anchor_ref)[0]:
            fail(409, "already_in_series")
        staged = copy.deepcopy(STATE)
        original = staged["reservations"][anchor_ref]
        restaurant = staged["restaurants"][original["restaurant_id"]]
        anchor_naive = parse_local(original["starts_at_local"])
        sid = "series_" + uuid.uuid4().hex
        occurrences = [{"index": 0, "reference": anchor_ref, "exception": False}]
        for index in range(1, count):
            target_date = anchor_naive.date() + timedelta(days=index * interval * 7)
            local = datetime.combine(target_date, anchor_naive.time()).strftime("%Y-%m-%dT%H:%M")
            tables = resolve_tables(restaurant, res_table_ids(original))
            details = booking_details(restaurant, tables, local, original["party_size"], staged)
            reference = make_reference()
            reservation = {"reservation_id": "res_" + uuid.uuid4().hex, "reference": reference,
                "restaurant_id": restaurant["id"], "table_ids": [t["id"] for t in tables],
                "party_size": original["party_size"], "status": "confirmed",
                "starts_at_local": local, "starts_at": details["starts_at"], "ends_at": details["ends_at"],
                "created_at": now_rfc3339(), "user_id": uid, "revision": 1,
                "accepted_terms": policy_terms(staged, restaurant, local)}
            if len(tables) == 1:
                reservation["table_id"] = tables[0]["id"]
            staged["reservations"][reference] = reservation
            append_history(staged, reservation, "created", creation_changes(reservation))
            occurrences.append({"index": index, "reference": reference, "exception": False})
        staged["series"][sid] = {"series_id": sid, "user_id": uid, "revision": 1,
            "interval_weeks": interval, "occurrences": occurrences}
        bump_restaurant_revision(staged, restaurant["id"])
        result = current_series(staged, sid, uid)
        STATE.clear()
        STATE.update(staged)
        return result

    def move_batch(self, body, uid):
        obj_body(body)
        moves = body.get("moves")
        valid(isinstance(moves, list) and 1 <= len(moves) <= 8)
        refs = []
        for move in moves:
            obj_body(move)
            ref = move.get("reference")
            valid(isinstance(ref, str) and ref not in refs)
            refs.append(ref)
        originals = []
        for ref in refs:
            record = STATE["reservations"].get(ref)
            if not record or record["user_id"] != uid:
                fail(404, "not_found")
            originals.append(copy.deepcopy(record))
        original_by_ref = {record["reference"]: record for record in originals}
        restaurants = {r["restaurant_id"] for r in originals}
        valid(len(restaurants) == 1)
        # Decide request-shape and revision errors for the whole batch before
        # evaluating any move's policy or occupancy semantics.
        for ref, move in zip(refs, moves):
            check_expected_revision(move, original_by_ref[ref])
            validate_body_fields(move)
            read_table_selection(move, allow_legacy=False)
            local = move.get("starts_at_local", original_by_ref[ref]["starts_at_local"])
            party = move.get("party_size", original_by_ref[ref]["party_size"])
            valid(isinstance(local, str) and is_int(party) and 1 <= party <= 1000)
        # Validation happens against a staged state; no mutation occurs until every move passes.
        staged = copy.deepcopy(STATE)
        now = datetime.now(timezone.utc)
        # Remove all participating old occupancies while validating final combined positions.
        for ref in refs:
            staged["reservations"][ref]["status"] = "__moving__"
        results = []
        for ref, move in zip(refs, moves):
            current = staged["reservations"][ref]
            rest = staged["restaurants"][current["restaurant_id"]]
            check_expected_revision(move, original_by_ref[ref])
            if original_by_ref[ref]["status"] == "cancelled":
                fail(409, "reservation_cancelled")
            if now >= reservation_cutoff(original_by_ref[ref]):
                fail(409, "cutoff_passed")
            validate_body_fields(move)
            selection = read_table_selection(move, allow_legacy=False)
            if selection is None:
                selection = res_table_ids(original_by_ref[ref])
            local = move.get("starts_at_local", current["starts_at_local"])
            party = move.get("party_size", current["party_size"])
            valid(isinstance(local, str) and is_int(party) and 1 <= party <= 1000)
            tables = resolve_tables(rest, selection)
            new_ids = [t["id"] for t in tables]
            if (new_ids == res_table_ids(original_by_ref[ref]) and
                local == original_by_ref[ref]["starts_at_local"] and party == original_by_ref[ref]["party_size"]):
                results.append(public_reservation(original_by_ref[ref]))
                continue
            details = booking_details(rest, tables, local, party, staged, skip_ref=ref, check_occupancy=False)
            before = copy.deepcopy(original_by_ref[ref])
            current.pop("table_id", None)
            current.update(table_ids=new_ids, starts_at_local=local, party_size=party,
                           starts_at=details["starts_at"], ends_at=details["ends_at"], status="confirmed")
            current["revision"] += 1
            current["accepted_terms"] = policy_terms(staged, rest, local)
            if len(tables) == 1:
                current["table_id"] = tables[0]["id"]
            changes = []
            table_change = selection_change(before, current)
            if table_change:
                changes.append(table_change)
            if before["starts_at_local"] != local:
                changes.append({"field": "starts_at_local", "from": before["starts_at_local"], "to": local})
            if before["party_size"] != party:
                changes.append({"field": "party_size", "from": before["party_size"], "to": party})
            append_history(staged, current, "changed", changes)
            results.append(public_reservation(current))
        # Restore confirmed statuses for entries not yet visited while checking pairwise conflicts.
        for ref in refs:
            staged["reservations"][ref]["status"] = "confirmed"
        # Validate each staged final position against all other final reservations.
        for ref in refs:
            r = staged["reservations"][ref]
            rest = staged["restaurants"][r["restaurant_id"]]
            tables = resolve_tables(rest, res_table_ids(r))
            booking_details(rest, tables, r["starts_at_local"], r["party_size"], staged, skip_ref=ref)
        for ref in refs:
            STATE["reservations"][ref] = staged["reservations"][ref]
            if staged["reservations"][ref]["revision"] != original_by_ref[ref]["revision"]:
                series, occurrence = reservation_in_series(staged, ref)
                if series:
                    occurrence["exception"] = True
        if any(staged["reservations"][ref]["revision"] != original_by_ref[ref]["revision"] for ref in refs):
            bump_restaurant_revision(staged, next(iter(restaurants)))
            changed_refs = [ref for ref in refs if staged["reservations"][ref]["revision"] != original_by_ref[ref]["revision"]]
            # Apply series increments once per affected series, after marking exceptions.
            affected = {reservation_in_series(staged, ref)[0]["series_id"]
                        for ref in changed_refs if reservation_in_series(staged, ref)[0]}
            for sid in affected:
                staged["series"][sid]["revision"] += 1
            STATE.clear()
            STATE.update(staged)
        return {"reservations": results}


def single_param(query, key):
    values = query.get(key)
    return values[0] if values else None


def make_reference():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    while True:
        ref = "".join(secrets.choice(alphabet) for _ in range(8))
        if ref not in STATE["reservations"]:
            return ref


def adapt_legacy_import_state(state):
    """Translate the Stage 1 export shape before strict Stage 2 validation."""
    legacy_keys = {"users", "restaurants", "reservations", "tokens", "idempotency"}
    if set(state) != legacy_keys:
        return state

    users = state.get("users")
    restaurants = state.get("restaurants")
    reservations = state.get("reservations")
    tokens = state.get("tokens")
    idempotency = state.get("idempotency")
    valid(all(isinstance(value, dict) for value in (users, restaurants, reservations, tokens)))
    valid(isinstance(idempotency, list))

    converted_users = {}
    for uid, user in users.items():
        valid(isinstance(uid, str) and isinstance(user, dict) and
              user.get("id") == uid and isinstance(user.get("password"), str))
        converted_users[uid] = {
            "id": uid,
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "password_hash": password_hash(user["password"]),
        }

    converted_restaurants = copy.deepcopy(restaurants)
    for rid, restaurant in converted_restaurants.items():
        valid(isinstance(restaurant, dict) and restaurant.get("id") == rid and
              isinstance(restaurant.get("tables"), dict))
        tables = restaurant["tables"]
        valid(all(isinstance(table, dict) and table.get("id") == table_id
                  for table_id, table in tables.items()))
        restaurant["tables"] = list(tables.values())

    converted_receipts = {}
    for record in idempotency:
        valid(isinstance(record, dict) and isinstance(record.get("scope"), list) and
              len(record["scope"]) == 4)
        uid, method, path, key = record["scope"]
        response = record.get("response")
        body_hash = record.get("body_hash")
        valid(isinstance(uid, str) and uid in converted_users and method == "POST" and
              path in ("/reservations", "/reservation-moves") and
              isinstance(key, str) and 1 <= len(key) <= 255 and
              record.get("status") == 201 and isinstance(response, dict) and
              isinstance(body_hash, str) and re.fullmatch(r"[0-9a-f]{64}", body_hash))

        request_body = None
        if path == "/reservations":
            if (response.get("user_id") == uid and
                    all(field in response for field in
                        ("restaurant_id", "table_id", "starts_at_local", "party_size"))):
                request_body = {field: response[field] for field in
                                ("restaurant_id", "table_id", "starts_at_local", "party_size")}
        else:
            moved = response.get("reservations")
            if isinstance(moved, list) and moved and all(
                    isinstance(item, dict) and item.get("user_id") == uid and
                    all(field in item for field in
                        ("reference", "table_id", "party_size", "starts_at_local"))
                    for item in moved):
                request_body = {"moves": [
                    {field: item[field] for field in
                     ("reference", "table_id", "party_size", "starts_at_local")}
                    for item in moved
                ]}

        if request_body is not None:
            candidate_hash = hashlib.sha256(json.dumps(
                request_body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if hmac.compare_digest(candidate_hash, body_hash):
                receipt_key = uid + "\0" + key
                valid(receipt_key not in converted_receipts)
                converted_receipts[receipt_key] = {
                    "method": method,
                    "path": path,
                    "body": request_body,
                    "response": copy.deepcopy(response),
                }

    return {
        "users": converted_users,
        "restaurants": converted_restaurants,
        "reservations": copy.deepcopy(reservations),
        "tokens": copy.deepcopy(tokens),
        "receipts": converted_receipts,
    }


def upgrade_stage2_state(state):
    """Upgrade a validated Stage 2 state shape without losing Stage 2 receipts."""
    if not isinstance(state, dict) or "users" not in state or "restaurants" not in state:
        return state
    stage3_keys = {"users", "restaurants", "reservations", "tokens", "receipts",
                   "policies", "histories", "series", "restaurant_revisions"}
    if set(state) == stage3_keys:
        return state
    if set(state) != {"users", "restaurants", "reservations", "tokens", "receipts"}:
        return state
    upgraded = copy.deepcopy(state)
    upgraded["policies"] = {rid: [] for rid in upgraded["restaurants"]}
    upgraded["restaurant_revisions"] = {rid: 0 for rid in upgraded["restaurants"]}
    upgraded["series"] = {}
    upgraded["histories"] = {}
    for rid, restaurant in upgraded["restaurants"].items():
        restaurant.setdefault("combinable", [])
        restaurant.setdefault("manager_user_ids", [])
    for ref, reservation in upgraded["reservations"].items():
        if "table_ids" not in reservation:
            reservation["table_ids"] = [reservation["table_id"]]
        rid = reservation["restaurant_id"]
        restaurant = upgraded["restaurants"][rid]
        reservation.setdefault("revision", 1)
        reservation.setdefault("accepted_terms", policy_terms(upgraded, restaurant,
                                                                 reservation["starts_at_local"]))
        upgraded["histories"][ref] = [{"seq": 1, "at": reservation["created_at"],
            "event": "created", "changes": creation_changes(reservation),
            "revision": reservation["revision"],
            "accepted_terms": copy.deepcopy(reservation["accepted_terms"])}]
    return upgraded


def upgrade_stage4_state(state):
    """Add Stage 4 state containers while preserving all populated Stage 3 data."""
    if not isinstance(state, dict):
        return state
    stage3_keys = {"users", "restaurants", "reservations", "tokens", "receipts",
                   "policies", "histories", "series", "restaurant_revisions"}
    stage4_keys = stage3_keys | {"closures", "replans"}
    if set(state) == stage4_keys:
        return state
    if set(state) != stage3_keys:
        return state
    upgraded = copy.deepcopy(state)
    upgraded["closures"] = {rid: [] for rid in upgraded["restaurants"]}
    upgraded["replans"] = {}
    return upgraded


def validate_import_state(state):
    required = {"users", "restaurants", "reservations", "tokens", "receipts",
                "policies", "histories", "series", "restaurant_revisions", "closures", "replans"}
    valid(isinstance(state, dict) and set(state) == required and
          all(isinstance(state[k], dict) for k in required))

    for rid, restaurant in state["restaurants"].items():
        valid(isinstance(rid, str) and isinstance(restaurant, dict) and
              restaurant.get("id") == rid)

    # Reuse fixture validation for restaurant fields while accepting Stage 1 exports,
    # which predate the optional combinable field.
    for rid, restaurant in state["restaurants"].items():
        managers = restaurant.get("manager_user_ids", [])
        valid(isinstance(managers, list) and all(isinstance(uid, str) and uid in state["users"]
                                                for uid in managers))
        valid(isinstance(state["policies"].get(rid), list) and
              is_int(state["restaurant_revisions"].get(rid)) and
              state["restaurant_revisions"][rid] >= 0)
        policies = state["policies"][rid]
        for version, policy in enumerate(policies, 1):
            checked = validate_policy(policy, restaurant)
            valid(policy.get("policy_version") == version and
                  checked["effective_from"] == policy.get("effective_from"))
    try:
        fixture_restaurants = copy.deepcopy(list(state["restaurants"].values()))
        for restaurant in fixture_restaurants:
            restaurant["manager_user_ids"] = []
        build_fixture({"users": [], "restaurants": fixture_restaurants,
                       "reservations": []})
    except ApiError:
        fail(422, "validation_failed")

    email_keys = set()
    for uid, user in state["users"].items():
        valid(isinstance(uid, str) and 1 <= len(uid) <= 64 and isinstance(user, dict))
        email = user.get("email")
        display = user.get("display_name")
        password = user.get("password_hash")
        valid(user.get("id") == uid and isinstance(email, str) and
              bool(EMAIL_RE.fullmatch(email)) and len(email) <= 254)
        valid(1 <= len(display) <= 100 if isinstance(display, str) else False)
        valid(isinstance(password, dict) and set(password) == {"salt", "digest"} and
              isinstance(password.get("salt"), str) and
              re.fullmatch(r"[0-9a-f]{32}", password["salt"]) is not None and
              isinstance(password.get("digest"), str) and
              re.fullmatch(r"[0-9a-f]{64}", password["digest"]) is not None)
        email_key = email.lower()
        valid(email_key not in email_keys)
        email_keys.add(email_key)

    for token, uid in state["tokens"].items():
        valid(isinstance(token, str) and bool(token) and isinstance(uid, str) and
              uid in state["users"])

    reservation_ids = set()
    for ref, record in state["reservations"].items():
        valid(isinstance(ref, str) and REF_RE.fullmatch(ref) is not None and
              isinstance(record, dict) and record.get("reference") == ref)
        rid, uid = record.get("restaurant_id"), record.get("user_id")
        valid(isinstance(rid, str) and rid in state["restaurants"] and
              isinstance(uid, str) and uid in state["users"])
        res_id = record.get("reservation_id")
        valid(isinstance(res_id, str) and 1 <= len(res_id) <= 64 and
              res_id not in reservation_ids)
        reservation_ids.add(res_id)
        valid(record.get("status") in ("confirmed", "cancelled"))
        valid(is_int(record.get("revision")) and record["revision"] >= 1)
        terms = record.get("accepted_terms")
        valid(isinstance(terms, dict) and set(terms) == {"policy_version", "slot_minutes",
            "reservation_duration_minutes", "cancellation_cutoff_minutes", "opening_hours", "capacities"})
        policy_version = terms.get("policy_version")
        valid(is_int(policy_version) and policy_version >= 0)
        if policy_version == 0:
            valid(terms == policy_zero(state["restaurants"][rid]))
        else:
            source_policy = next((p for p in state["policies"][rid]
                                  if p["policy_version"] == policy_version), None)
            valid(source_policy is not None)
            expected_terms = {key: value for key, value in source_policy.items()
                              if key != "effective_from"}
            valid(terms == expected_terms)
        party = record.get("party_size")
        valid(is_int(party) and 1 <= party <= 1000)

        if "table_ids" in record:
            table_ids = record["table_ids"]
            valid(isinstance(table_ids, list) and 1 <= len(table_ids) <= 2 and
                  all(isinstance(tid, str) for tid in table_ids) and
                  len(set(table_ids)) == len(table_ids))
            if len(table_ids) == 1:
                valid("table_id" not in record or record["table_id"] == table_ids[0])
            else:
                valid("table_id" not in record)
        else:
            table_id = record.get("table_id")
            valid(isinstance(table_id, str))
            table_ids = [table_id]

        restaurant = state["restaurants"][rid]
        tables = resolve_tables(restaurant, table_ids, fixture=True)
        local = record.get("starts_at_local")
        valid(isinstance(local, str))
        try:
            details = booking_details(restaurant, tables, local, party, state,
                                      skip_ref=ref, check_occupancy=False, policy=terms)
        except ApiError:
            fail(422, "validation_failed")
        valid(record.get("starts_at") == details["starts_at"] and
              record.get("ends_at") == details["ends_at"])
        for field in ("created_at", "starts_at", "ends_at"):
            value = record.get(field)
            valid(isinstance(value, str))
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                fail(422, "validation_failed")
            valid(parsed.tzinfo is not None)

    # Reject snapshots containing conflicting confirmed bookings as invalid state.
    for ref, record in state["reservations"].items():
        if record["status"] != "confirmed":
            continue
        restaurant = state["restaurants"][record["restaurant_id"]]
        tables = resolve_tables(restaurant, res_table_ids(record), fixture=True)
        try:
            booking_details(restaurant, tables, record["starts_at_local"],
                            record["party_size"], state, skip_ref=ref, policy=record["accepted_terms"])
        except ApiError:
            fail(422, "validation_failed")

    for key, receipt in state["receipts"].items():
        valid(isinstance(key, str) and key.count("\0") == 1 and isinstance(receipt, dict))
        uid, idempotency_key = key.split("\0", 1)
        valid(uid in state["users"] and 1 <= len(idempotency_key) <= 255)
        receipt_path = receipt.get("path")
        valid(receipt.get("method") == "POST" and
              (receipt_path in ("/reservations", "/reservation-moves", "/series") or
               isinstance(receipt_path, str) and re.fullmatch(r"/series/[^/]+/amend", receipt_path) or
               isinstance(receipt_path, str) and re.fullmatch(r"/restaurants/[^/]+/replans(?:/[^/]+/apply)?", receipt_path) or
               isinstance(receipt_path, str) and re.fullmatch(r"/restaurants/[^/]+/policies", receipt_path)) and
              isinstance(receipt.get("body"), dict) and
              isinstance(receipt.get("response"), dict))

    valid(isinstance(state["histories"], dict) and set(state["histories"]) == set(state["reservations"]))
    for ref, entries in state["histories"].items():
        valid(isinstance(entries, list) and len(entries) >= 1)
        for seq, entry in enumerate(entries, 1):
            valid(isinstance(entry, dict) and entry.get("seq") == seq and
                  entry.get("event") in ("created", "changed", "cancelled", "reassigned") and
                  isinstance(entry.get("changes"), list) and is_int(entry.get("revision")) and
                  isinstance(entry.get("accepted_terms"), dict) and isinstance(entry.get("at"), str))
            if entry.get("event") == "reassigned":
                valid(isinstance(entry.get("plan_id"), str) and
                      any(isinstance(change, dict) and change.get("field") == "table_ids"
                          for change in entry["changes"]))
    valid(isinstance(state["series"], dict))
    series_refs = set()
    for sid, series in state["series"].items():
        valid(isinstance(series, dict) and series.get("series_id") == sid and
              series.get("user_id") in state["users"] and is_int(series.get("revision")) and
              series["revision"] >= 1 and is_int(series.get("interval_weeks")) and
              1 <= series["interval_weeks"] <= 4 and
              isinstance(series.get("occurrences"), list) and 2 <= len(series["occurrences"]) <= 12)
        for index, occurrence in enumerate(series["occurrences"]):
            ref = occurrence.get("reference") if isinstance(occurrence, dict) else None
            valid(occurrence.get("index") == index and isinstance(ref, str) and
                  ref in state["reservations"] and ref not in series_refs and
                  state["reservations"][ref]["user_id"] == series["user_id"] and
                  type(occurrence.get("exception")) is bool)
            series_refs.add(ref)

    valid(isinstance(state["closures"], dict) and set(state["closures"]) == set(state["restaurants"]))
    for rid, closures in state["closures"].items():
        valid(isinstance(closures, list))
        for closure in closures:
            valid(isinstance(closure, dict) and set(closure) == {"table_id", "from", "to"} and
                  isinstance(closure.get("table_id"), str) and
                  find_table(state["restaurants"][rid], closure["table_id"]) is not None and
                  isinstance(closure.get("from"), str) and isinstance(closure.get("to"), str))
            try:
                closed_from, closed_to = datetime.fromisoformat(closure["from"]), datetime.fromisoformat(closure["to"])
            except ValueError:
                fail(422, "validation_failed")
            valid(closed_from.tzinfo is not None and closed_from.utcoffset() is not None and
                  closed_to.tzinfo is not None and closed_to.utcoffset() is not None and
                  closed_from < closed_to)
    for record in state["reservations"].values():
        if record["status"] != "confirmed":
            continue
        start_utc = datetime.fromisoformat(record["starts_at"]).astimezone(timezone.utc)
        end_utc = datetime.fromisoformat(record["ends_at"]).astimezone(timezone.utc)
        valid(not closure_overlap(state, record["restaurant_id"], res_table_ids(record), start_utc, end_utc))

    valid(isinstance(state["replans"], dict))
    for plan_id, plan in state["replans"].items():
        valid(isinstance(plan_id, str) and isinstance(plan, dict) and
              plan.get("restaurant_id") in state["restaurants"] and
              plan.get("owner_user_id") in state["users"] and
              is_int(plan.get("restaurant_revision")) and plan["restaurant_revision"] >= 0 and
              isinstance(plan.get("closure"), dict) and isinstance(plan.get("assignments"), list) and
              isinstance(plan.get("response"), dict) and
              (plan.get("applied_key") is None or isinstance(plan.get("applied_key"), str)) and
              (plan.get("applied_response") is None or isinstance(plan.get("applied_response"), dict)))
        closure = plan["closure"]
        valid(set(closure) == {"table_id", "from", "to"} and
              find_table(state["restaurants"][plan["restaurant_id"]], closure.get("table_id")) is not None)
        refs = []
        for assignment in plan["assignments"]:
            valid(isinstance(assignment, dict) and isinstance(assignment.get("reference"), str) and
                  assignment["reference"] in state["reservations"] and
                  isinstance(assignment.get("table_ids"), list) and type(assignment.get("changed")) is bool)
            refs.append(assignment["reference"])
        valid(refs == sorted(refs) and len(refs) == len(set(refs)) and
              plan["response"].get("plan_id") == plan_id)


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()

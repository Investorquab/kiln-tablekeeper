#!/usr/bin/env python3
"""Tablekeeper Stage 1 HTTP service."""
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
STATE = {"users": {}, "restaurants": {}, "reservations": {}, "tokens": {}, "receipts": {}}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
REF_RE = re.compile(r"^[A-Z0-9]{6,12}$")
LOCAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

APP_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tablekeeper | A table worth gathering around</title>
<style>
:root{--ink:#233b32;--muted:#60736a;--leaf:#17523f;--leaf2:#e5efe8;--cream:#fbf7ef;--paper:#fffefa;--line:#d9dfd7;--gold:#a25d19;--red:#963f32;--shadow:0 12px 32px rgba(34,56,44,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--cream);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}a{color:var(--leaf)}button,input,select{font:inherit}button,a,input,select{outline-offset:3px}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #bb6b18;outline-offset:3px}button{border:0;border-radius:10px;padding:.72rem 1rem;background:var(--leaf);color:white;font-weight:700;cursor:pointer}button:hover{background:#103d2f}button:disabled{cursor:not-allowed;opacity:.58}input,select{width:100%;min-height:44px;border:1px solid #aebdb3;border-radius:9px;background:white;padding:.55rem .7rem;color:var(--ink)}label{display:grid;gap:.35rem;font-weight:650}.top{background:var(--paper);border-bottom:1px solid var(--line)}.nav{max-width:1100px;margin:auto;padding:.8rem 1.2rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap}.brand{font-family:Georgia,serif;font-size:1.35rem;font-weight:bold;color:var(--ink);text-decoration:none;margin-right:auto}.nav a:not(.brand){text-decoration:none;font-weight:650}.userbar{display:flex;gap:.6rem;align-items:center;color:var(--muted);font-size:.92rem}.userbar button{padding:.4rem .7rem}.shell{max-width:1100px;margin:0 auto;padding:2rem 1.2rem 4rem}.eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--gold);font-size:.75rem;font-weight:800}.hero{max-width:720px;margin:.5rem 0 1.6rem}.hero h1{font:clamp(2rem,5vw,3.25rem)/1.05 Georgia,serif;margin:.45rem 0}.hero p{color:var(--muted);margin:.6rem 0}.panel{background:var(--paper);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:clamp(1rem,3vw,1.5rem);margin:1rem 0}.filters{display:grid;grid-template-columns:2fr 1.25fr 1fr auto;gap:.8rem;align-items:end}.section-head{display:flex;align-items:end;justify-content:space-between;gap:1rem;margin:1.8rem 0 .8rem}.section-head h2{font:1.5rem Georgia,serif;margin:0}.hint,.muted{color:var(--muted)}.grid-wrap{overflow-x:auto}.availability-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr));gap:.65rem}.slot{width:100%;min-height:75px;text-align:left;background:var(--leaf2);color:var(--ink);border:1px solid #c7d7cb;display:flex;flex-direction:column;gap:.1rem}.slot:hover{background:#d7e7da}.slot[aria-pressed="true"]{box-shadow:0 0 0 3px #bb6b18}.slot[data-available="false"]{background:#f0efeb;color:#69756f;border-color:#dddcd5}.slot .kind{font-size:.78rem;font-weight:500;color:var(--muted)}.feedback{border-radius:10px;padding:.7rem .85rem;margin:.75rem 0}.error{background:#f9e9e5;color:#722e27;border:1px solid #e7bdb3}.success{background:#e8f2e8;color:#234d32;border:1px solid #bfd5c1}.uncertain{background:#fff3d9;color:#704b0b;border:1px solid #ead29d}.booking-layout{display:grid;grid-template-columns:1fr minmax(220px,.55fr);gap:1rem;align-items:start}.booking-summary{font-weight:750;font-size:1.1rem}.booking-form-fields{display:grid;gap:.8rem;margin-top:1rem}.confirmation{border-left:4px solid #2e744e}.confirmation h3{margin:.1rem 0 .4rem;font:1.4rem Georgia,serif}.reference{font:700 1.25rem ui-monospace,monospace;letter-spacing:.08em}.auth-card,.lookup-card{max-width:560px;margin:2rem auto}.auth-form{display:grid;gap:1rem}.auth-links{margin-top:1rem;color:var(--muted)}.detail{display:grid;gap:.5rem}.status-pill{display:inline-block;width:max-content;background:var(--leaf2);color:var(--leaf);border-radius:99px;padding:.2rem .65rem;font-weight:750}.empty{padding:1rem;border:1px dashed #bdc9bf;border-radius:12px;color:var(--muted)}.footer-note{font-size:.9rem;color:var(--muted)}
@media(max-width:680px){.shell{padding:1.35rem .85rem 3rem}.nav{padding:.7rem .85rem;gap:.65rem}.brand{width:100%;margin:0}.userbar{margin-left:auto}.filters{grid-template-columns:1fr 1fr}.filters label:first-child{grid-column:1/-1}.filters button{grid-column:1/-1;width:100%}.booking-layout{grid-template-columns:1fr}.section-head{align-items:start;flex-direction:column}.availability-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.slot{min-width:0;padding:.6rem .65rem;font-size:.92rem}}
@media(max-width:360px){.availability-grid{grid-template-columns:1fr}.nav{gap:.5rem}.shell{padding-inline:.7rem}}
</style></head><body><header class="top"><nav class="nav"><a class="brand" href="/">Tablekeeper</a><a href="/">Find a table</a><a href="/lookup">Your booking</a><span class="userbar" id="userbar"></span><span id="auth-shortcuts"><a href="/login">Log in</a> · <a href="/signup">Join us</a></span></nav></header><main class="shell" id="app"></main>
<script>
(() => {
const app=document.getElementById('app'), userbar=document.getElementById('userbar'), shortcuts=document.getElementById('auth-shortcuts');
const tid=(s)=>`[data-testid="${s}"]`, esc=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token=localStorage.getItem('tk-token')||'', user=JSON.parse(localStorage.getItem('tk-user')||'null');
let restaurants=[], restaurant=null, searchSeq=0, lastSearch=null, selection=null, requestState=null, confirmed=null;
const headers=(extra={})=>Object.assign({'Accept':'application/json'},token?{'Authorization':'Bearer '+token}:{},extra);
async function api(path,opts={}){const h=headers(opts.headers||{});if(opts.body!==undefined)h['Content-Type']='application/json';const res=await fetch(path,{...opts,headers:h});let data=null;try{data=await res.json()}catch{}return {res,data}}
function updateUser(){userbar.innerHTML='';shortcuts.hidden=!!user;if(user){const span=document.createElement('span');span.dataset.testid='current-user';span.textContent=user.display_name;const b=document.createElement('button');b.type='button';b.dataset.testid='logout-button';b.textContent='Log out';b.onclick=()=>{token='';user=null;localStorage.removeItem('tk-token');localStorage.removeItem('tk-user');updateUser();renderPage()};userbar.append(span,b)}}
function feedback(id,msg,kind='error',root=app){let e=root.querySelector(tid(id));if(!msg){e?.remove();return}if(!e){e=document.createElement('p');e.dataset.testid=id;e.className='feedback '+kind;e.setAttribute('role','status');root.append(e)}e.textContent=msg;e.className='feedback '+kind}
function shell(title,kicker,copy){return `<div class="hero"><span class="eyebrow">${kicker}</span><h1>${title}</h1><p>${copy}</p></div>`}
function formPage(mode){const signup=mode==='signup';app.innerHTML=`${shell(signup?'A warmer welcome starts here':'Good to see you again',signup?'Join the table':'Welcome back',signup?'Create your diner account to save and manage reservations.':'Sign in to book a table and keep your plans close.')}<section class="panel auth-card"><form class="auth-form" id="auth-form">${signup?`<label>Your name<input data-testid="signup-display-name" name="display_name" autocomplete="name" required maxlength="100"></label>`:''}<label>Email address<input data-testid="${signup?'signup-email':'login-email'}" name="email" type="email" autocomplete="email" required></label><label>Password<input data-testid="${signup?'signup-password':'login-password'}" name="password" type="password" autocomplete="${signup?'new-password':'current-password'}" minlength="8" required></label><div id="auth-feedback"></div><button data-testid="${signup?'signup-submit':'login-submit'}" type="submit">${signup?'Create account':'Log in'}</button></form><p class="auth-links">${signup?'Already have an account? <a href="/login">Log in</a>':'New to Tablekeeper? <a href="/signup">Create an account</a>'}</p></section>`;
document.getElementById('auth-form').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.currentTarget),body={email:fd.get('email'),password:fd.get('password')};if(signup)body.display_name=fd.get('display_name');try{const {res,data}=await api('/auth/'+mode,{method:'POST',body:JSON.stringify(body)});if(!res.ok){feedback('auth-error',data?.error?.message||'We could not sign you in. Check your details.','error',document.getElementById('auth-feedback'));return}token=data.token;user={display_name:data.display_name,user_id:data.user_id};localStorage.setItem('tk-token',token);localStorage.setItem('tk-user',JSON.stringify(user));updateUser();location.href='/'}catch{feedback('auth-error','A connection issue stopped the request. Please try again.','error',document.getElementById('auth-feedback'))}}}
function localDatePlus(days){const d=new Date();d.setDate(d.getDate()+days);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function tableLabels(ids){return ids.map(id=>{const t=restaurant?.tables?.find(x=>x.id===id);return t?.label||id})}
function clearBookingFeedback(){feedback('booking-error','');feedback('booking-uncertain','');feedback('confirmation','')}
function renderBooking(){let box=document.getElementById('booking-area');if(!selection){box.innerHTML='';return}if(!token){feedback('auth-error','Please log in before reserving this table.','error',box);return}const labels=tableLabels(selection.table_ids);box.innerHTML=`<section class="panel booking-layout" data-testid="booking-form"><div><span class="eyebrow">Your table</span><p class="booking-summary" data-testid="booking-summary">${esc(labels.map(x=>'Table '+x).join(' + '))} · ${esc(selection.starts_at_local.slice(11))}</p><p class="muted">${esc(restaurant.name)} · ${esc(selection.starts_at_local.slice(0,10))}</p></div><form class="booking-form-fields" id="booking-submit-form"><label>Party size<input data-testid="booking-party-size" name="party_size" type="number" min="1" max="1000" required value="${esc(selection.party_size)}"></label><div id="booking-feedback"></div><button data-testid="booking-submit" type="submit">Reserve this table</button><span class="footer-note">We’ll hold your details while you confirm.</span></form></section><div id="confirmation-area"></div>`;
document.getElementById('booking-submit-form').onsubmit=submitBooking; if(confirmed)showConfirmation(confirmed)}
function showConfirmation(receipt){confirmed=receipt;feedback('booking-error','');feedback('booking-uncertain','');const area=document.getElementById('confirmation-area');if(!area)return;const ids=receipt.table_ids||[receipt.table_id];const labels=tableLabels(ids);area.innerHTML=`<section class="panel confirmation" data-testid="confirmation"><span class="eyebrow">All set</span><h3>We’ve saved your table</h3><p class="reference" data-testid="confirmation-reference">${esc(receipt.reference)}</p><p data-testid="confirmation-details">${esc(restaurant?.name||'Restaurant')} · ${esc(labels.map(x=>'Table '+x).join(' + '))} · ${esc(receipt.starts_at_local.slice(11))}</p><p data-testid="confirmation-tables">${esc(labels.map(x=>'Table '+x).join(' + '))}</p></section>`}
function optionCells(slot,party){const at=slot.starts_at_local.slice(11), singles=(restaurant.tables||[]).map(t=>({ids:[t.id],capacity:t.capacity,available:(slot.available_table_ids||[]).includes(t.id)}));const pairs=(restaurant.combinable||[]).map(ids=>({ids,capacity:ids.reduce((n,id)=>n+(restaurant.tables.find(t=>t.id===id)?.capacity||0),0),available:(slot.available_options||[]).some(o=>o.table_ids.length===ids.length&&o.table_ids.every((id,i)=>id===ids[i]))})).filter(o=>o.capacity>=party);return singles.concat(pairs).map(o=>{const labels=tableLabels(o.ids).map(x=>'Table '+x).join(' + '), key=o.ids.join('+');return `<button type="button" class="slot" data-testid="slot-${esc(key)}-${esc(at)}" data-available="${o.available?'true':'false'}" aria-pressed="${selection&&selection.starts_at_local===slot.starts_at_local&&selection.table_ids.join('|')===o.ids.join('|')?'true':'false'}" ${o.available?'':'disabled'} data-choice="${esc(JSON.stringify({table_ids:o.ids,starts_at_local:slot.starts_at_local}))}"><strong>${esc(labels)}</strong><span class="kind">${esc(at)} · seats ${o.capacity}</span></button>`}).join('')}
function renderGrid(data,party){const area=document.getElementById('results');if(!area)return;if(!data.slots.length){area.innerHTML='<div class="empty" data-testid="no-slots">There are no seating times on this day. Try another date.</div>';return}area.innerHTML=`<div class="grid-wrap"><div class="availability-grid" data-testid="availability-grid">${data.slots.map(s=>optionCells(s,party)).join('')}</div></div>`;area.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>{if(b.dataset.available!=='true')return;selection={...JSON.parse(b.dataset.choice),party_size:Number(document.querySelector(tid('party-size-input')).value)};requestState=null;confirmed=null;renderGrid(lastSearch.data,lastSearch.party);renderBooking()})}
async function performSearch(){const form=document.getElementById('search-form');if(!form)return;const rid=form.elements.restaurant_id.value,date=form.elements.date.value,party=Number(form.elements.party_size.value),seq=++searchSeq;lastSearch={rid,date,party};const results=document.getElementById('results');results.innerHTML='<div class="empty">Finding the right table…</div>';try{const {res,data}=await api(`/availability?restaurant_id=${encodeURIComponent(rid)}&date=${encodeURIComponent(date)}&party_size=${encodeURIComponent(party)}`);if(seq!==searchSeq)return;if(!res.ok){results.innerHTML='<div class="empty">Availability could not be loaded. Please try again.</div>';return}restaurant=restaurants.find(x=>x.id===rid)||restaurant;lastSearch.data=data;renderGrid(data,party)}catch{if(seq!==searchSeq)return;results.innerHTML='<div class="empty">We couldn’t reach the restaurant. Please try again.</div>'}}
async function submitBooking(e){e.preventDefault();if(!selection||!token)return;const party=Number(e.currentTarget.elements.party_size.value);const body={restaurant_id:restaurant.id,starts_at_local:selection.starts_at_local,party_size:party};if(selection.table_ids.length===1)body.table_id=selection.table_ids[0];else body.table_ids=selection.table_ids;const fingerprint=JSON.stringify(body);if(!requestState||requestState.fingerprint!==fingerprint)requestState={fingerprint,body,key:(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random())};feedback('booking-error','');feedback('booking-uncertain','');try{const {res,data}=await api('/reservations',{method:'POST',headers:{'Idempotency-Key':requestState.key},body:JSON.stringify(requestState.body)});if(res.ok){showConfirmation(data);return}if(res.status===409&&data?.error?.code==='table_unavailable'){feedback('booking-error','That table was just taken. Choose another available table and try again.');await performSearch();return}feedback('booking-error',data?.error?.message||'We could not complete that reservation. Check your selection and try again.')}catch{feedback('booking-error','');feedback('booking-uncertain','We haven’t received a confirmation yet. Your selection is saved here; retry to check the original request.','uncertain')}}
function searchPage(){app.innerHTML=`${shell('A good meal starts with the right table','Find your place','Choose a restaurant, date and party size. We’ll show the seats that fit your evening.')}<section class="panel"><form id="search-form" class="filters"><label>Restaurant<select data-testid="restaurant-select" name="restaurant_id" required></select></label><label>Date<input data-testid="date-input" name="date" type="date" value="${localDatePlus(7)}" required></label><label>Party size<input data-testid="party-size-input" name="party_size" type="number" min="1" max="1000" value="2" required></label><button data-testid="search-button" type="submit">Find a table</button></form></section><div class="section-head"><div><span class="eyebrow">Available seating</span><h2>Make room for a good evening</h2></div><span class="hint">Choose an open table or a declared pair.</span></div><div id="results"><div class="empty">Choose your date and search to see available tables.</div></div><div id="booking-area"></div>`;const select=document.querySelector(tid('restaurant-select'));select.innerHTML=restaurants.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('');if(restaurant)select.value=restaurant.id;document.getElementById('search-form').onsubmit=e=>{e.preventDefault();selection=null;requestState=null;confirmed=null;document.getElementById('booking-area').innerHTML='';performSearch()};if(lastSearch){select.value=lastSearch.rid;document.querySelector(tid('date-input')).value=lastSearch.date;document.querySelector(tid('party-size-input')).value=lastSearch.party;performSearch()}}
function renderLookup(r){const detail=document.getElementById('lookup-result');const ids=r.table_ids||[r.table_id];const labels=tableLabels(ids);detail.innerHTML=`<section class="panel detail" data-testid="reservation-detail"><span class="eyebrow">Your reservation</span><span class="status-pill" data-testid="reservation-status">${esc(r.status)}</span><strong>${esc(restaurant?.name||r.restaurant_id)}</strong><span data-testid="reservation-tables">${esc(labels.map(x=>'Table '+x).join(' + '))}</span><span>${esc(r.starts_at_local)}</span>${r.status==='confirmed'?'<button data-testid="reservation-cancel-button" type="button">Cancel reservation</button>':''}</section>`;const cancel=detail.querySelector(tid('reservation-cancel-button'));if(cancel)cancel.onclick=async()=>{feedback('reservation-error','');try{const {res,data}=await api(`/reservations/${encodeURIComponent(r.reference)}/cancel`,{method:'POST'});if(!res.ok){feedback('reservation-error',data?.error?.message||'This reservation could not be cancelled.');return}renderLookup(data)}catch{feedback('reservation-error','We could not reach the restaurant. Please try again.')}}}
function lookupPage(){app.innerHTML=`${shell('Your plans, close at hand','Reservation lookup','Enter your confirmation reference to see or cancel a reservation.')}<section class="panel lookup-card"><form id="lookup-form" class="auth-form"><label>Confirmation reference<input data-testid="lookup-reference-input" autocomplete="off" required></label><div id="lookup-feedback"></div><button data-testid="lookup-submit" type="submit">Look up reservation</button></form></section><div id="lookup-result"></div>`;document.getElementById('lookup-form').onsubmit=async e=>{e.preventDefault();feedback('reservation-error','');document.getElementById('lookup-result').innerHTML='';const ref=e.currentTarget.querySelector('input').value.trim();try{const {res,data}=await api('/reservations/'+encodeURIComponent(ref));if(!res.ok){feedback('reservation-error',data?.error?.message||'Reservation not found.','error',document.getElementById('lookup-feedback'));return}renderLookup(data)}catch{feedback('reservation-error','We could not reach the restaurant. Please try again.','error',document.getElementById('lookup-feedback'))}}}
function renderPage(){updateUser();const path=location.pathname;if(path==='/signup'){formPage('signup');return}if(path==='/login'){formPage('login');return}if(path==='/lookup'){lookupPage();return}searchPage()}
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
    new = {"users": {}, "restaurants": {}, "reservations": {}, "tokens": {}, "receipts": {}}
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
        valid(rid not in new["restaurants"])
        new["restaurants"][rid] = {"id": rid, "name": name, "timezone": tzname, **settings,
                                   "opening_hours": checked_hours, "tables": checked_tables,
                                   "combinable": checked_pairs}
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
        new["reservations"][ref] = reservation
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


def booking_details(restaurant, tables, local, party, state, skip_ref=None, check_occupancy=True):
    naive = parse_local(local)
    zone = ZoneInfo(restaurant["timezone"])
    aware = resolve_local(naive, zone)
    weekday = WEEKDAYS[naive.weekday()]
    hours = next((h for h in restaurant["opening_hours"] if h["weekday"] == weekday), None)
    if not hours:
        fail(422, "outside_opening_hours")
    opens, closes = parse_clock(hours["opens"]), parse_clock(hours["closes"])
    start_clock = naive.time()
    if start_clock < opens or start_clock >= closes:
        fail(422, "outside_opening_hours")
    offset_minutes = int((datetime.combine(naive.date(), start_clock) -
                          datetime.combine(naive.date(), opens)).total_seconds() // 60)
    if offset_minutes % restaurant["slot_minutes"]:
        fail(422, "not_on_slot_grid")
    end_utc = aware.astimezone(timezone.utc) + timedelta(minutes=restaurant["reservation_duration_minutes"])
    end_zone = end_utc.astimezone(zone)
    if end_zone.date() != naive.date() or end_zone.time().replace(tzinfo=None) > closes:
        fail(422, "outside_opening_hours")
    capacity = sum(table["capacity"] for table in tables)
    if party > capacity:
        fail(422, "party_exceeds_capacity")
    start_utc = aware.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(minutes=restaurant["reservation_duration_minutes"])
    if check_occupancy:
        for existing in state["reservations"].values():
            if existing["reference"] == skip_ref or existing["status"] != "confirmed":
                continue
            if existing["restaurant_id"] != restaurant["id"] or not set(res_table_ids(existing)).intersection(t["id"] for t in tables):
                continue
            other_start = datetime.fromisoformat(existing["starts_at"]).astimezone(timezone.utc)
            other_end = datetime.fromisoformat(existing["ends_at"]).astimezone(timezone.utc)
            if start_utc < other_end and other_start < end_utc:
                fail(409, "table_unavailable")
    return {"starts_at": aware.isoformat(timespec="seconds"),
            "ends_at": end_utc.astimezone(zone).isoformat(timespec="seconds"),
            "start_utc": start_utc, "end_utc": end_utc}


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
            uid = None
            if not public and not auth_exempt:
                uid = resolve_user(STATE, self.headers.get("Authorization"))
            if method in ("POST",) and route in ("/reservations", "/reservation-moves"):
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
            if status == 201 and method == "POST" and route in ("/reservations", "/reservation-moves"):
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
            valid(body.get("track") == "tablekeeper" and type(body.get("format_version")) is int
                  and body.get("format_version") == 1)
            imported = body.get("state")
            if not isinstance(imported, dict):
                fail(422, "validation_failed")
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
        if method == "GET" and route == "/availability":
            rid = single_param(query, "restaurant_id")
            date_value = single_param(query, "date")
            party_text = single_param(query, "party_size")
            valid(rid is not None and date_value is not None and party_text is not None)
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
            hours = next((h for h in restaurant["opening_hours"] if h["weekday"] == WEEKDAYS[target_date.weekday()]), None)
            slots = []
            if hours:
                opens, closes = parse_clock(hours["opens"]), parse_clock(hours["closes"])
                minute = opens.hour * 60 + opens.minute
                close_min = closes.hour * 60 + closes.minute
                while minute + restaurant["reservation_duration_minutes"] <= close_min:
                    naive = datetime.combine(target_date, time(minute // 60, minute % 60))
                    try:
                        aware = resolve_local(naive, ZoneInfo(restaurant["timezone"]))
                    except ApiError as exc:
                        if exc.code != "invalid_local_time":
                            raise
                        minute += restaurant["slot_minutes"]
                        continue
                    end_utc = aware.astimezone(timezone.utc) + timedelta(minutes=restaurant["reservation_duration_minutes"])
                    end_local = end_utc.astimezone(ZoneInfo(restaurant["timezone"]))
                    if end_local.date() == target_date and end_local.time().replace(tzinfo=None) <= closes:
                        available = []
                        options = []
                        for table in restaurant["tables"]:
                            if table["capacity"] < party:
                                continue
                            try:
                                booking_details(restaurant, [table], naive.strftime("%Y-%m-%dT%H:%M"), party, STATE)
                            except ApiError as exc:
                                if exc.code not in ("table_unavailable", "party_exceeds_capacity"):
                                    raise
                            else:
                                available.append(table["id"])
                                options.append({"table_ids": [table["id"]], "capacity": table["capacity"]})
                        for pair in restaurant.get("combinable", []):
                            tables = [find_table(restaurant, tid) for tid in pair]
                            if sum(t["capacity"] for t in tables) < party:
                                continue
                            try:
                                booking_details(restaurant, tables, naive.strftime("%Y-%m-%dT%H:%M"), party, STATE)
                            except ApiError as exc:
                                if exc.code not in ("table_unavailable", "party_exceeds_capacity"):
                                    raise
                            else:
                                options.append({"table_ids": list(pair),
                                                "capacity": sum(t["capacity"] for t in tables)})
                        slots.append({"starts_at_local": naive.strftime("%Y-%m-%dT%H:%M"),
                                      "starts_at": aware.isoformat(timespec="seconds"),
                                      "available_table_ids": available,
                                      "available_options": options})
                    minute += restaurant["slot_minutes"]
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
                           "ends_at": details["ends_at"], "created_at": now_rfc3339(), "user_id": uid}
            if len(tables) == 1:
                reservation["table_id"] = tables[0]["id"]
            STATE["reservations"][ref] = reservation
            return 201, public_reservation(reservation)
        if method == "GET" and route == "/reservations":
            rows = [public_reservation(r) for r in STATE["reservations"].values() if r["user_id"] == uid]
            rows.sort(key=lambda r: datetime.fromisoformat(r["starts_at"]).astimezone(timezone.utc), reverse=True)
            return 200, {"reservations": rows}
        match = re.fullmatch(r"/reservations/([^/]+)(?:/(cancel))?", route)
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
                cutoff = datetime.fromisoformat(reservation["starts_at"]).astimezone(timezone.utc) - timedelta(minutes=restaurant["cancellation_cutoff_minutes"])
                if datetime.now(timezone.utc) >= cutoff:
                    fail(409, "cutoff_passed")
                reservation["status"] = "cancelled"
                return 200, public_reservation(reservation)
            if method == "PATCH" and not cancel_suffix:
                body = obj_body(body)
                return 200, self.patch_one(ref, body)
        if method == "POST" and route == "/reservation-moves":
            return 201, self.move_batch(body, uid)
        fail(404, "not_found")

    def patch_one(self, ref, body):
        reservation = STATE["reservations"][ref]
        if reservation["status"] == "cancelled":
            fail(409, "reservation_cancelled")
        restaurant = STATE["restaurants"][reservation["restaurant_id"]]
        cutoff = datetime.fromisoformat(reservation["starts_at"]).astimezone(timezone.utc) - timedelta(minutes=restaurant["cancellation_cutoff_minutes"])
        if datetime.now(timezone.utc) >= cutoff:
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
        details = booking_details(restaurant, tables, local, party, STATE, skip_ref=ref)
        reservation.pop("table_id", None)
        reservation.update(table_ids=[t["id"] for t in tables], starts_at_local=local, party_size=party,
                           starts_at=details["starts_at"], ends_at=details["ends_at"])
        if len(tables) == 1:
            reservation["table_id"] = tables[0]["id"]
        return public_reservation(reservation)

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
            if original_by_ref[ref]["status"] == "cancelled":
                fail(409, "reservation_cancelled")
            cutoff = datetime.fromisoformat(original_by_ref[ref]["starts_at"]).astimezone(timezone.utc) - timedelta(minutes=rest["cancellation_cutoff_minutes"])
            if now >= cutoff:
                fail(409, "cutoff_passed")
            validate_body_fields(move)
            selection = read_table_selection(move, allow_legacy=False)
            if selection is None:
                selection = res_table_ids(original_by_ref[ref])
            local = move.get("starts_at_local", current["starts_at_local"])
            party = move.get("party_size", current["party_size"])
            valid(isinstance(local, str) and is_int(party) and 1 <= party <= 1000)
            tables = resolve_tables(rest, selection)
            details = booking_details(rest, tables, local, party, staged, skip_ref=ref, check_occupancy=False)
            current.pop("table_id", None)
            current.update(table_ids=[t["id"] for t in tables], starts_at_local=local, party_size=party,
                           starts_at=details["starts_at"], ends_at=details["ends_at"], status="confirmed")
            if len(tables) == 1:
                current["table_id"] = tables[0]["id"]
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


def validate_import_state(state):
    required = {"users", "restaurants", "reservations", "tokens", "receipts"}
    valid(isinstance(state, dict) and set(state) == required and
          all(isinstance(state[k], dict) for k in required))

    for rid, restaurant in state["restaurants"].items():
        valid(isinstance(rid, str) and isinstance(restaurant, dict) and
              restaurant.get("id") == rid)

    # Reuse fixture validation for restaurant fields while accepting Stage 1 exports,
    # which predate the optional combinable field.
    try:
        build_fixture({"users": [], "restaurants": list(state["restaurants"].values()),
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
                                      skip_ref=ref, check_occupancy=False)
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
                            record["party_size"], state, skip_ref=ref)
        except ApiError:
            fail(422, "validation_failed")

    for key, receipt in state["receipts"].items():
        valid(isinstance(key, str) and key.count("\0") == 1 and isinstance(receipt, dict))
        uid, idempotency_key = key.split("\0", 1)
        valid(uid in state["users"] and 1 <= len(idempotency_key) <= 255)
        valid(receipt.get("method") == "POST" and
              receipt.get("path") in ("/reservations", "/reservation-moves") and
              isinstance(receipt.get("body"), dict) and
              isinstance(receipt.get("response"), dict))


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()

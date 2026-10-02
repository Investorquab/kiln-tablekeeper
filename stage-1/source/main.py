import copy
import hashlib
import json
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

HOST="0.0.0.0"
PORT=int(os.environ.get("PORT","8080"))
LOCK=threading.RLock()
WEEKDAYS=("mon","tue","wed","thu","fri","sat","sun")
REF_RE=re.compile(r"^[A-Z0-9]{6,12}$")
STATE={"users":{},"restaurants":{},"reservations":{},"tokens":{},"idempotency":{}}

def utc_now(): return datetime.now(timezone.utc)
def iso(dt): return dt.isoformat()
def new_id(p): return f"{p}_{uuid.uuid4().hex}"
def reference(): return secrets.token_hex(5).upper()
def body_hash(b): return hashlib.sha256(json.dumps(b,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def json_response(h,status,payload):
    raw=json.dumps(payload,separators=(",",":")).encode()
    h.send_response(status); h.send_header("Content-Type","application/json"); h.send_header("Content-Length",str(len(raw))); h.end_headers(); h.wfile.write(raw)
def error(h,status,code): json_response(h,status,{"error":{"code":code}})
def no_content(h): h.send_response(204); h.send_header("Content-Length","0"); h.end_headers()

def read_json(h):
    try: n=int(h.headers.get("Content-Length","0")); raw=h.rfile.read(n); return json.loads(raw.decode())
    except Exception as e: raise ValueError("malformed_request") from e

def parse_id(v): return isinstance(v,str) and 1<=len(v)<=64
def parse_party(v): return isinstance(v,int) and not isinstance(v,bool) and v>0

def restaurant_public(r):
    return {"id":r["id"],"name":r["name"],"timezone":r["timezone"],"slot_minutes":r["slot_minutes"],
            "reservation_duration_minutes":r["reservation_duration_minutes"],
            "cancellation_cutoff_minutes":r["cancellation_cutoff_minutes"],
            "opening_hours":copy.deepcopy(r["opening_hours"]),
            "tables":[{"id":t["id"],"label":t["label"],"capacity":t["capacity"]} for t in r["tables"].values()]}

def local_to_aware(r,v):
    if not isinstance(v,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}",v): return None
    try:
        n=datetime.strptime(v,"%Y-%m-%dT%H:%M"); z=ZoneInfo(r["timezone"]); a=n.replace(tzinfo=z,fold=0)
        if a.astimezone(timezone.utc).astimezone(z).replace(tzinfo=None)!=n: return None
        return a
    except Exception: return None

def opening_for(r,n):
    return next((x for x in r["opening_hours"] if x["weekday"]==WEEKDAYS[n.weekday()]),None)

def validate_slot(r,v):
    if not isinstance(v,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}",v): return None,"validation_failed"
    try: n=datetime.strptime(v,"%Y-%m-%dT%H:%M")
    except Exception: return None,"validation_failed"
    a=local_to_aware(r,v)
    if a is None: return None,"invalid_local_time"
    o=opening_for(r,n)
    if o is None: return None,"outside_opening_hours"
    try: op=time.fromisoformat(o["opens"]); cl=time.fromisoformat(o["closes"])
    except Exception: return None,"validation_failed"
    sm=n.hour*60+n.minute; om=op.hour*60+op.minute; cm=cl.hour*60+cl.minute; d=r["reservation_duration_minutes"]
    if sm<om or sm+d>cm: return None,"outside_opening_hours"
    if (sm-om)%r["slot_minutes"]!=0: return None,"not_on_slot_grid"
    end=(a.astimezone(timezone.utc)+timedelta(minutes=d)).astimezone(ZoneInfo(r["timezone"]))
    return (n,a,end),None

def reservation_public(r): return copy.deepcopy(r)

def reservation_times(r):
    return datetime.fromisoformat(r["starts_at"]),datetime.fromisoformat(r["ends_at"])

def has_conflict(rid,tid,start,end,exclude_refs=()):
    excluded=set(exclude_refs)
    for ref,r in STATE["reservations"].items():
        if ref in excluded or r["status"]!="confirmed" or r["restaurant_id"]!=rid or r["table_id"]!=tid: continue
        rs,re_=reservation_times(r)
        if start<re_ and rs<end: return True
    return False

def cutoff_passed(r,rest):
    s,_=reservation_times(r)
    return utc_now()>=s.astimezone(timezone.utc)-timedelta(minutes=rest["cancellation_cutoff_minutes"])

def load_fixture(fixture):
    if not isinstance(fixture,dict): raise ValueError("validation_failed")
    users=fixture.get("users",[]); restaurants=fixture.get("restaurants",[]); reservations=fixture.get("reservations",[])
    if not all(isinstance(x,list) for x in (users,restaurants,reservations)): raise ValueError("validation_failed")
    ns={"users":{},"restaurants":{},"reservations":{},"tokens":{},"idempotency":{}}
    for u in users:
        if not isinstance(u,dict) or not parse_id(u.get("id")) or not isinstance(u.get("email"),str) or not isinstance(u.get("password"),str): raise ValueError("validation_failed")
        dn=u.get("display_name",u.get("name",u["id"]))
        if not isinstance(dn,str): raise ValueError("validation_failed")
        ns["users"][u["id"]]={"id":u["id"],"email":u["email"],"password":u["password"],"display_name":dn}
    for r in restaurants:
        req=("name","timezone","slot_minutes","reservation_duration_minutes","cancellation_cutoff_minutes","opening_hours","tables")
        if not isinstance(r,dict) or not parse_id(r.get("id")) or any(k not in r for k in req): raise ValueError("validation_failed")
        try: ZoneInfo(r["timezone"])
        except Exception: raise ValueError("validation_failed")
        ts={}
        if not isinstance(r["tables"],list): raise ValueError("validation_failed")
        for t in r["tables"]:
            if not isinstance(t,dict) or not parse_id(t.get("id")) or not isinstance(t.get("capacity"),int) or isinstance(t.get("capacity"),bool) or t["capacity"]<=0 or t["id"] in ts: raise ValueError("validation_failed")
            ts[t["id"]]={"id":t["id"],"label":t.get("label",t["id"]),"capacity":t["capacity"]}
        oh=r["opening_hours"]
        if not isinstance(oh,list): raise ValueError("validation_failed")
        noh=[]
        for x in oh:
            if not isinstance(x,dict) or x.get("weekday") not in WEEKDAYS: raise ValueError("validation_failed")
            try: time.fromisoformat(x["opens"]); time.fromisoformat(x["closes"])
            except Exception: raise ValueError("validation_failed")
            noh.append({"weekday":x["weekday"],"opens":x["opens"],"closes":x["closes"]})
        ns["restaurants"][r["id"]]={"id":r["id"],"name":r["name"],"timezone":r["timezone"],"slot_minutes":r["slot_minutes"],
            "reservation_duration_minutes":r["reservation_duration_minutes"],
            "cancellation_cutoff_minutes":r["cancellation_cutoff_minutes"],"opening_hours":noh,"tables":ts,
            "manager_user_ids":list(r.get("manager_user_ids",[]))}
    for x in reservations:
        if not isinstance(x,dict) or not REF_RE.fullmatch(x.get("reference","")): raise ValueError("validation_failed")
        if x["reference"] in ns["reservations"]: raise ValueError("validation_failed")
        rest=ns["restaurants"].get(x.get("restaurant_id")); uid=x.get("user_id"); tid=x.get("table_id")
        if rest is None or uid not in ns["users"] or tid not in rest["tables"]: raise ValueError("validation_failed")
        if not parse_party(x.get("party_size")) or x["party_size"]>rest["tables"][tid]["capacity"]: raise ValueError("validation_failed")
        parsed,code=validate_slot(rest,x.get("starts_at_local"))
        if code is not None: raise ValueError("validation_failed")
        _,a,e=parsed; created=x.get("created_at") or iso(utc_now())
        status=x.get("status","confirmed")
        if status not in ("confirmed","cancelled"): raise ValueError("validation_failed")
        item={"restaurant_id":rest["id"],"table_id":tid,"party_size":x["party_size"],"starts_at_local":x["starts_at_local"],
              "starts_at":iso(a),"ends_at":iso(e),"reservation_id":x.get("reservation_id",x.get("id",new_id("reservation"))),
              "created_at":created,"updated_at":x.get("updated_at",created),"reference":x["reference"],"status":status,"user_id":uid}
        ns["reservations"][x["reference"]]=item
    with LOCK:
        global STATE
        STATE=ns

def default_fixture():
    return {"users":[{"id":"u_ada","email":"ada@example.com","password":"correct horse","display_name":"Ada"},
                     {"id":"u_bob","email":"bob@example.com","password":"correct horse","display_name":"Bob"}],
            "restaurants":[{"id":"r_anker","name":"Zum Anker","timezone":"Europe/Berlin","slot_minutes":30,"reservation_duration_minutes":90,
                            "cancellation_cutoff_minutes":120,"opening_hours":[{"weekday":d,"opens":"18:00","closes":"23:00"} for d in WEEKDAYS],
                            "tables":[{"id":"t_1","label":"1","capacity":2},{"id":"t_2","label":"2","capacity":4},{"id":"t_3","label":"3","capacity":6}]}],"reservations":[]}
def reset_state(): load_fixture(default_fixture())

def auth_user(h):
    x=h.headers.get("Authorization","")
    if not x.startswith("Bearer "): return None
    with LOCK:
        uid=STATE["tokens"].get(x[7:])
        return STATE["users"].get(uid)

def idem_lookup(uid,m,p,k,b):
    r=STATE["idempotency"].get((uid,m,p,k))
    if r is None:return None
    return ("conflict",) if r["body_hash"]!=body_hash(b) else r
def idem_store(uid,m,p,k,b,status,response):
    STATE["idempotency"][(uid,m,p,k)]={"body_hash":body_hash(b),"status":status,"response":copy.deepcopy(response)}

def create_reservation(uid,b):
    rest=STATE["restaurants"].get(b.get("restaurant_id"))
    if rest is None:return None,404,"not_found"
    tid=b.get("table_id")
    if tid not in rest["tables"]:return None,404,"not_found"
    party=b.get("party_size")
    if not parse_party(party):return None,422,"validation_failed"
    if party>rest["tables"][tid]["capacity"]:return None,422,"party_exceeds_capacity"
    parsed,code=validate_slot(rest,b.get("starts_at_local"))
    if code:return None,422,code
    _,a,e=parsed
    if has_conflict(rest["id"],tid,a,e):return None,409,"table_unavailable"
    now=iso(utc_now()); ref=reference()
    r={"restaurant_id":rest["id"],"table_id":tid,"party_size":party,"starts_at_local":b["starts_at_local"],
       "starts_at":iso(a),"ends_at":iso(e),"reservation_id":new_id("reservation"),"created_at":now,
       "updated_at":now,"reference":ref,"status":"confirmed","user_id":uid}
    STATE["reservations"][ref]=r
    return r,201,None

class Handler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args),flush=True)
    def do_GET(self):
        try:self.route("GET")
        except Exception as e: print("GET error:",e,flush=True); error(self,500,"internal_error")
    def do_POST(self):
        try:self.route("POST")
        except ValueError as e: error(self,400,"malformed_request" if str(e)=="malformed_request" else "validation_failed")
        except Exception as e: print("POST error:",e,flush=True); error(self,500,"internal_error")
    def do_PATCH(self):
        try:self.route("PATCH")
        except ValueError:error(self,400,"malformed_request")
        except Exception as e: print("PATCH error:",e,flush=True); error(self,500,"internal_error")

    def route(self,method):
        u=urlparse(self.path); path=u.path; q=parse_qs(u.query,keep_blank_values=True)
        if method=="GET" and path=="/health": return json_response(self,200,{"status":"ok"})
        if method=="POST" and path=="/_test/reset": return self.reset()
        if method=="GET" and path=="/_test/export": return json_response(self,200,export_state())
        if method=="POST" and path=="/_test/import": return self.import_state()
        if method=="GET" and path=="/restaurants": 
            with LOCK:return json_response(self,200,{"restaurants":[restaurant_public(r) for r in STATE["restaurants"].values()]})
        m=re.fullmatch(r"/restaurants/([^/]+)",path)
        if method=="GET" and m:
            with LOCK:
                r=STATE["restaurants"].get(m.group(1))
                return json_response(self,200,restaurant_public(r)) if r else error(self,404,"not_found")
        if method=="GET" and path=="/availability": return self.availability(q)
        if method=="POST" and path=="/auth/signup": return self.signup()
        if method=="POST" and path=="/auth/login": return self.login()
        user=auth_user(self)
        if path=="/reservations" or path=="/reservation-moves" or path.startswith("/reservations/"):
            if user is None:return error(self,401,"unauthenticated")
        if method=="GET" and path=="/reservations": return self.list_res(user["id"])
        if method=="POST" and path=="/reservations": return self.create_res(user["id"])
        if method=="POST" and path=="/reservation-moves": return self.moves(user["id"])
        m=re.fullmatch(r"/reservations/([^/]+)",path)
        if m:
            if method=="GET":return self.get_res(user["id"],m.group(1))
            if method=="PATCH":return self.patch(user["id"],m.group(1))
        m=re.fullmatch(r"/reservations/([^/]+)/cancel",path)
        if method=="POST" and m:return self.cancel(user["id"],m.group(1))
        error(self,404,"not_found")

    def reset(self):
        f=read_json(self)
        if not isinstance(f,dict):return error(self,422,"validation_failed")
        try:load_fixture(f)
        except Exception:return error(self,422,"validation_failed")
        no_content(self)

    def signup(self):
        b=read_json(self)
        if not isinstance(b,dict):return error(self,422,"validation_failed")
        for k in ("email","password","display_name"):
            if k in b and not isinstance(b[k],str):return error(self,400,"malformed_request")
        email=b.get("email");pw=b.get("password");dn=b.get("display_name")
        if not email or not pw or not dn or "@" not in email or "." not in email.rsplit("@",1)[-1] or len(pw)<8:return error(self,422,"validation_failed")
        with LOCK:
            if any(u["email"].lower()==email.lower() for u in STATE["users"].values()):return error(self,409,"email_taken")
            uid=new_id("u");tok=secrets.token_urlsafe(32)
            STATE["users"][uid]={"id":uid,"email":email,"password":pw,"display_name":dn};STATE["tokens"][tok]=uid
        json_response(self,201,{"id":uid,"email":email,"display_name":dn,"token":tok,"user":{"id":uid,"email":email,"display_name":dn}})

    def login(self):
        b=read_json(self)
        if not isinstance(b,dict):return error(self,422,"validation_failed")
        email=b.get("email");pw=b.get("password")
        with LOCK:u=next((u for u in STATE["users"].values() if u["email"].lower()==str(email).lower() and u["password"]==pw),None)
        if u is None:return error(self,401,"unauthenticated")
        tok=secrets.token_urlsafe(32)
        with LOCK:STATE["tokens"][tok]=u["id"]
        json_response(self,200,{"token":tok,"user":{"id":u["id"],"email":u["email"],"display_name":u["display_name"]}})

    def availability(self,q):
        rid=q.get("restaurant_id",[None])[0];dv=q.get("date",[None])[0];raw=q.get("party_size",[None])[0]
        if rid is None or dv is None or raw is None or not re.fullmatch(r"\d+",str(raw)):return error(self,422,"validation_failed")
        ps=int(raw)
        if ps<=0:return error(self,422,"validation_failed")
        try:date=datetime.strptime(dv,"%Y-%m-%d").date()
        except:return error(self,422,"validation_failed")
        with LOCK:r=STATE["restaurants"].get(rid)
        if r is None:return error(self,404,"not_found")
        op=next((x for x in r["opening_hours"] if x["weekday"]==WEEKDAYS[date.weekday()]),None)
        slots=[]
        if op:
            a=time.fromisoformat(op["opens"]);c=time.fromisoformat(op["closes"]);cur=datetime.combine(date,a);endd=datetime.combine(date,c);dur=r["reservation_duration_minutes"]
            while cur+timedelta(minutes=dur)<=endd:
                lv=cur.strftime("%Y-%m-%dT%H:%M");parsed,code=validate_slot(r,lv)
                if code is None:
                    _,st,en=parsed
                    avail=[tid for tid,t in r["tables"].items() if t["capacity"]>=ps and not has_conflict(rid,tid,st,en)]
                    slots.append({"starts_at_local":lv,"starts_at":iso(st),"ends_at":iso(en),"available_table_ids":avail})
                cur+=timedelta(minutes=r["slot_minutes"])
        json_response(self,200,{"restaurant_id":rid,"date":dv,"timezone":r["timezone"],"slots":slots})

    def create_res(self,uid):
        b=read_json(self)
        if not isinstance(b,dict):return error(self,422,"validation_failed")
        key=self.headers.get("Idempotency-Key")
        if not key:return error(self,400,"missing_idempotency_key")
        with LOCK:
            old=idem_lookup(uid,"POST","/reservations",key,b)
            if old==("conflict",):return error(self,409,"idempotency_key_reuse")
            if old is not None:return json_response(self,200,old["response"])
            r,st,code=create_reservation(uid,b)
            if r is None:return error(self,st,code)
            resp=reservation_public(r);idem_store(uid,"POST","/reservations",key,b,201,resp);json_response(self,201,resp)

    def list_res(self,uid):
        with LOCK:
            xs=[reservation_public(r) for r in STATE["reservations"].values() if r["user_id"]==uid];xs.sort(key=lambda r:r["starts_at"],reverse=True)
        json_response(self,200,{"reservations":xs})

    def owned(self,uid,ref):
        r=STATE["reservations"].get(ref);return r if r is not None and r["user_id"]==uid else None
    def get_res(self,uid,ref):
        with LOCK:r=self.owned(uid,ref)
        return json_response(self,200,reservation_public(r)) if r else error(self,404,"not_found")

    def cancel(self,uid,ref):
        with LOCK:
            r=self.owned(uid,ref)
            if r is None:return error(self,404,"not_found")
            if r["status"]=="confirmed":
                rest=STATE["restaurants"][r["restaurant_id"]]
                if cutoff_passed(r,rest):return error(self,409,"cutoff_passed")
                r["status"]="cancelled";r["updated_at"]=iso(utc_now())
            json_response(self,200,reservation_public(r))

    def patch(self,uid,ref):
        b=read_json(self)
        if not isinstance(b,dict):return error(self,422,"validation_failed")
        with LOCK:
            r=self.owned(uid,ref)
            if r is None:return error(self,404,"not_found")
            if r["status"]!="confirmed":return error(self,409,"reservation_cancelled")
            rest=STATE["restaurants"][r["restaurant_id"]]
            if cutoff_passed(r,rest):return error(self,409,"cutoff_passed")
            tid=b.get("table_id",r["table_id"]);ps=b.get("party_size",r["party_size"]);lv=b.get("starts_at_local",r["starts_at_local"])
            if tid not in rest["tables"]:return error(self,404,"not_found")
            if not parse_party(ps):return error(self,422,"validation_failed")
            if ps>rest["tables"][tid]["capacity"]:return error(self,422,"party_exceeds_capacity")
            parsed,code=validate_slot(rest,lv)
            if code:return error(self,422,code)
            _,st,en=parsed
            if has_conflict(rest["id"],tid,st,en,exclude_refs={ref}):return error(self,409,"table_unavailable")
            up=copy.deepcopy(r);up.update({"table_id":tid,"party_size":ps,"starts_at_local":lv,"starts_at":iso(st),"ends_at":iso(en),"updated_at":iso(utc_now())})
            STATE["reservations"][ref]=up
        json_response(self,200,reservation_public(up))

    def moves(self,uid):
        b=read_json(self)
        if not isinstance(b,dict):return error(self,422,"validation_failed")
        key=self.headers.get("Idempotency-Key")
        if not key:return error(self,400,"missing_idempotency_key")
        with LOCK:
            old=idem_lookup(uid,"POST","/reservation-moves",key,b)
            if old==("conflict",):return error(self,409,"idempotency_key_reuse")
            if old is not None:return json_response(self,200,old["response"])
            moves=b.get("moves")
            if not isinstance(moves,list) or not 1<=len(moves)<=8:return error(self,422,"validation_failed")
            refs=[x.get("reference") if isinstance(x,dict) else None for x in moves]
            if len(set(refs))!=len(refs) or any(x is None for x in refs):return error(self,422,"validation_failed")
            rs=[]
            for ref in refs:
                r=self.owned(uid,ref)
                if r is None:return error(self,404,"not_found")
                if r["status"]!="confirmed":return error(self,409,"reservation_cancelled")
                rs.append(r)
            if len({r["restaurant_id"] for r in rs})!=1:return error(self,422,"validation_failed")
            rest=STATE["restaurants"][rs[0]["restaurant_id"]];proposed={}
            for mv,r in zip(moves,rs):
                if cutoff_passed(r,rest):return error(self,409,"cutoff_passed")
                tid=mv.get("table_id",r["table_id"]);ps=mv.get("party_size",r["party_size"]);lv=mv.get("starts_at_local",r["starts_at_local"])
                if tid not in rest["tables"]:return error(self,404,"not_found")
                if not parse_party(ps):return error(self,422,"validation_failed")
                if ps>rest["tables"][tid]["capacity"]:return error(self,422,"party_exceeds_capacity")
                parsed,code=validate_slot(rest,lv)
                if code:return error(self,422,code)
                _,st,en=parsed;proposed[r["reference"]]=(tid,ps,lv,st,en)
            batch=set(proposed)
            for tid,ps,lv,st,en in proposed.values():
                if has_conflict(rest["id"],tid,st,en,exclude_refs=batch):return error(self,409,"table_unavailable")
            vals=list(proposed.values())
            for i,a in enumerate(vals):
                for b2 in vals[i+1:]:
                    if a[0]==b2[0] and a[3]<b2[4] and b2[3]<a[4]:return error(self,409,"table_unavailable")
            out=[]
            for r in rs:
                tid,ps,lv,st,en=proposed[r["reference"]];up=copy.deepcopy(r);up.update({"table_id":tid,"party_size":ps,"starts_at_local":lv,"starts_at":iso(st),"ends_at":iso(en),"updated_at":iso(utc_now())});out.append(up)
            for up in out:STATE["reservations"][up["reference"]]=up
            resp={"reservations":[reservation_public(x) for x in out]};idem_store(uid,"POST","/reservation-moves",key,b,201,resp);json_response(self,201,resp)

def export_state():
    with LOCK:
        s=copy.deepcopy(STATE)
        s["idempotency"]=[{"scope":list(k),"body_hash":v["body_hash"],"status":v["status"],"response":copy.deepcopy(v["response"])} for k,v in STATE["idempotency"].items()]
        return s

def import_snapshot(snap):
    if not isinstance(snap,dict) or any(k not in snap for k in ("users","restaurants","reservations","tokens","idempotency")):raise ValueError("validation")
    if not all(isinstance(snap[k],dict) for k in ("users","restaurants","reservations","tokens")) or not isinstance(snap["idempotency"],list):raise ValueError("validation")
    idem={}
    for x in snap["idempotency"]:
        if not isinstance(x,dict) or not isinstance(x.get("scope"),list) or len(x["scope"])!=4:raise ValueError("validation")
        idem[tuple(x["scope"])]={"body_hash":x.get("body_hash"),"status":x.get("status"),"response":copy.deepcopy(x.get("response"))}
    ns={"users":copy.deepcopy(snap["users"]),"restaurants":copy.deepcopy(snap["restaurants"]),"reservations":copy.deepcopy(snap["reservations"]),"tokens":copy.deepcopy(snap["tokens"]),"idempotency":idem}
    with LOCK:
        global STATE;STATE=ns

reset_state()

if __name__=="__main__":
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

import os
import time
import uuid
from datetime import datetime


def _load_dotenv(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Tiny .env reader so secrets stay out of code and shell history."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

from authlib.integrations.flask_client import OAuth  # noqa: E402
from flask import (Flask, abort, flash, redirect, render_template_string,  # noqa: E402
                   request, send_file, session, url_for)
from markupsafe import Markup  # noqa: E402
from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

from cleanup import run as run_cleanup  # noqa: E402
from store import get_store  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config.update(
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB per upload
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
)
store = get_store()

# Google sign-in is enabled only when both env vars are set.
GOOGLE_ENABLED = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
oauth = OAuth(app)
if GOOGLE_ENABLED:
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

UNITS = {"minutes": 60, "hours": 3600, "days": 86400, "weeks": 604800}
GHOSTS = ["#7c3aed", "#ec4899", "#06b6d4", "#f59e0b", "#10b981", "#ef4444"]

# ----------------------------------------------------------------- layout --
LAYOUT = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CraDocs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#faf7ff;--ink:#2b1b4d;--mute:#6b5f8a;--pur:#7c3aed;--pur-d:#5b21b6;--pur-l:#f1eaff;--pur-m:#cdbcfb;
--yel:#ffc400;--yel-l:#fff6cc;--yel-m:#ffe066;--red:#dc2626;--pink:#ec4899;--cyan:#06b6d4;--org:#f59e0b;--grn:#16a34a;
--px:'Press Start 2P',ui-monospace,monospace;--body:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
::selection{background:var(--yel);color:var(--ink)}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.5;min-height:100vh}
h1,h2,h3,.px{font-family:var(--px);font-weight:400;letter-spacing:0;line-height:1.6}
button,input,select{font-family:inherit}
a{color:var(--pur-d)}
:focus-visible{outline:3px solid var(--yel);outline-offset:2px}
/* header */
.top{position:sticky;top:0;z-index:20;background:#fff;border-bottom:4px solid var(--pur);box-shadow:0 4px 0 var(--yel);
 display:flex;align-items:center;gap:14px;padding:10px 18px}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--pur-d);font-family:var(--px);font-size:14px}
.logo{width:36px;height:36px}
.jaw-t,.jaw-b{transform-box:view-box;transform-origin:16px 16px}
.brand:hover .jaw-t{animation:chomp-t .4s steps(2,end) infinite alternate}.brand:hover .jaw-b{animation:chomp-b .4s steps(2,end) infinite alternate}
@keyframes chomp-t{to{transform:rotate(-26deg)}}@keyframes chomp-b{to{transform:rotate(26deg)}}
.search{flex:1;max-width:560px}
.search input{width:100%;background:var(--pur-l);color:var(--ink);border:2px solid transparent;border-radius:8px;padding:10px 14px;font-size:15px;outline:0}
.search input:focus{background:#fff;border-color:var(--pur)}
.spacer{flex:1}
.avatar{width:38px;height:38px;border:3px solid var(--ink);border-radius:8px;background:var(--yel);color:var(--ink);font-family:var(--px);font-size:12px;cursor:pointer;
 box-shadow:3px 3px 0 var(--ink)}
.avatar:hover{background:var(--yel-m)}
.menu{position:absolute;right:0;top:48px;background:#fff;color:var(--ink);border:3px solid var(--ink);border-radius:8px;min-width:210px;display:none;z-index:30;
 box-shadow:5px 5px 0 var(--yel);padding:8px}
.menu.open{display:block}
.menu a,.menu button{display:block;width:100%;text-align:left;padding:9px 12px;color:var(--ink);text-decoration:none;background:none;border:0;border-radius:6px;font-size:15px;cursor:pointer}
.menu a:hover,.menu button:hover{background:var(--yel-l)}
.menu .who{font-size:13px;color:var(--mute);padding:4px 12px 8px;border-bottom:1px solid var(--pur-l);margin-bottom:6px}
/* start strip */
.start{background:var(--yel-l);border-bottom:4px solid var(--pur);padding:24px 0 8px}
.wrap{max-width:1040px;margin:0 auto;padding:0 18px}
.start h2{font-size:12px;margin:0 0 6px;color:var(--ink)}
.hint{color:var(--mute);font-size:14px}
.tiles{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px;padding-bottom:22px}
.tile{width:200px;background:#fff;border:3px solid var(--ink);border-top:10px solid var(--yel);border-radius:10px;color:var(--ink);cursor:pointer;padding:14px;text-align:left;
 box-shadow:5px 5px 0 var(--pur);transition:transform .12s,box-shadow .12s}
.tile:hover{transform:translate(-3px,-3px);box-shadow:8px 8px 0 var(--pur)}
.tile:active{transform:translate(2px,2px);box-shadow:2px 2px 0 var(--pur)}
.tile .ico{height:70px;display:grid;place-items:center;font-family:var(--px);font-size:40px;color:var(--pur)}
.tile .ico svg{width:58px;height:58px}
.tile-name{font-family:var(--px);font-size:10px;margin-top:10px;line-height:1.7}.tile-sub{font-size:14px;color:var(--mute);margin-top:2px}
/* recent */
.recent{padding-top:28px;padding-bottom:80px}
.recent-head{display:flex;align-items:center;gap:14px;margin-bottom:20px;flex-wrap:wrap}
.recent-head h2{flex:0 1 auto;margin:0 auto 0 0;font-size:12px;color:var(--ink);background:linear-gradient(transparent 62%,var(--yel) 62%);padding:0 4px}
.score{font-size:14px;color:var(--mute)}
select{background:#fff;color:var(--ink);border:2px solid var(--pur-m);border-radius:8px;padding:8px 10px;font-size:14px;cursor:pointer}
.icon-btn{background:#fff;color:var(--pur-d);border:2px solid var(--pur-m);border-radius:8px;width:40px;height:40px;font-size:16px;cursor:pointer}
.icon-btn:hover{border-color:var(--pur);background:var(--yel-l)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:22px}
.card{background:#fff;border:3px solid var(--ink);border-top:8px solid var(--yel);border-radius:10px;position:relative;box-shadow:5px 5px 0 var(--pur-m);
 transition:transform .12s,box-shadow .12s;animation:rise .3s ease-out both}
.card:hover{transform:translate(-3px,-3px);box-shadow:8px 8px 0 var(--pur)}
.thumb{display:grid;place-items:center;height:140px;border-bottom:3px solid var(--ink);position:relative;text-decoration:none;color:inherit;
 background:radial-gradient(circle,#cdbcfb99 2px,transparent 2.6px) 0 0/20px 20px,var(--pur-l)}
.thumb svg{width:76px;height:76px;filter:drop-shadow(3px 3px 0 #2b1b4d26)}
.badge{position:absolute;left:10px;top:10px;background:var(--yel);color:var(--ink);font-family:var(--px);font-size:8px;padding:5px 6px;border:2px solid var(--ink)}
.badge.lock{left:auto;right:10px;background:var(--pur-d);color:#fff;border-color:var(--pur-d)}
.meta{padding:12px 14px 14px;position:relative}
.title{font-family:var(--px);font-size:10px;line-height:1.7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:36px}
.owner{font-size:14px;color:var(--mute);margin:4px 0 10px}
.dots{position:absolute;right:8px;top:8px;width:34px;height:34px;font-size:18px}
.hp{display:grid;grid-template-columns:auto 1fr;gap:4px 8px;align-items:center}
.hp-label{font-family:var(--px);font-size:8px;color:var(--pur-d)}
.hp-bar{height:12px;background:var(--pur-l);border:2px solid var(--ink);border-radius:7px;overflow:hidden}
.hp-fill{height:100%;width:100%;transition:width 1s linear}
.hp-fill.ok{background:var(--grn)}.hp-fill.mid{background:var(--yel)}.hp-fill.low{background:var(--red)}
.hp-fill.max{background:linear-gradient(90deg,var(--pur),var(--yel))}
.hp-text{grid-column:1/-1;font-size:13px;color:var(--ink);text-align:right;font-variant-numeric:tabular-nums}
@keyframes rise{from{transform:translateY(10px);opacity:0}}
.lane{position:relative;height:26px;margin:12px 0 0;overflow:hidden;background:radial-gradient(circle,var(--pur) 3px,transparent 3.5px) 0 50%/28px 26px repeat-x}
.runner{position:absolute;left:0;top:0;height:26px;display:flex;gap:6px;animation:run 10s linear infinite}
.runner:before{content:"";position:absolute;right:100%;top:0;width:100vw;height:26px;background:var(--yel-l)}
.runner svg{width:26px;height:26px}
@keyframes run{from{transform:translateX(-120px)}to{transform:translateX(1200px)}}
.card:hover .thumb svg,.tile:hover .ico svg{animation:bob .5s steps(2) infinite alternate}
@keyframes bob{to{transform:translateY(-6px) rotate(-4deg)}}
.card.soon{animation:wiggle 2.4s ease-in-out infinite}
@keyframes wiggle{0%,90%,100%{transform:rotate(0)}93%{transform:rotate(-1.2deg)}96%{transform:rotate(1.2deg)}}
.snack:after{content:"\\25BC";position:absolute;right:16px;bottom:10px;font-size:14px;color:var(--pur);animation:blink .8s steps(2) infinite}
@keyframes blink{50%{opacity:.2}}
/* 3D */
.scene{perspective:900px}
.cube{position:relative;width:90px;height:90px;transform-style:preserve-3d;animation:spin 14s linear infinite}
.cube:hover{animation-duration:3.5s}
.face{position:absolute;inset:0;border:3px solid var(--ink);background:#fff;display:grid;place-items:center;font-family:var(--px);font-size:34px;color:var(--pur)}
.face svg{width:54px;height:54px}
.f1{transform:translateZ(45px);background:var(--yel-l)}.f2{transform:rotateY(90deg) translateZ(45px);background:var(--pur-l)}
.f3{transform:rotateY(180deg) translateZ(45px);background:var(--yel-l)}.f4{transform:rotateY(-90deg) translateZ(45px);background:var(--pur-l)}
.f5{transform:rotateX(90deg) translateZ(45px);background:var(--yel)}.f6{transform:rotateX(-90deg) translateZ(45px);background:var(--pur-m)}
@keyframes spin{from{transform:rotateX(-22deg) rotateY(0)}to{transform:rotateX(-22deg) rotateY(360deg)}}
.cube-shadow{position:absolute;left:50%;bottom:-26px;width:80px;height:14px;margin-left:-40px;border-radius:50%;background:#2b1b4d33;animation:sh 14s linear infinite}
@keyframes sh{50%{transform:scaleX(.8)}}
.hero3d{position:absolute;right:56px;top:20px;z-index:2}
.start{position:relative}
.title-screen .hero3d{position:relative;right:auto;top:auto;display:flex;justify-content:center;margin:6px 0 34px}
.card,.tile{transform-style:preserve-3d;will-change:transform}
.thumb:after{content:"";position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .2s;
 background:radial-gradient(circle at var(--gx,50%) var(--gy,50%),#ffffffb0,transparent 55%)}
.card:hover .thumb:after{opacity:1}
.btn{box-shadow:0 4px 0 var(--ink),0 8px 0 #2b1b4d33}
.btn:active{transform:translateY(4px);box-shadow:0 0 0 var(--ink)}
.floaters{position:fixed;inset:0;z-index:-1;pointer-events:none;overflow:hidden}
.fl{position:absolute;perspective:600px;animation:drift var(--d) ease-in-out infinite alternate}
.mini{width:var(--s);height:var(--s);position:relative;transform-style:preserve-3d;animation:tumble var(--t) linear infinite}
.mini i{position:absolute;inset:0;border:2px solid var(--ink);opacity:.75}
.mini i:nth-child(1){transform:translateZ(calc(var(--s)/2))}.mini i:nth-child(2){transform:rotateY(90deg) translateZ(calc(var(--s)/2))}
.mini i:nth-child(3){transform:rotateY(180deg) translateZ(calc(var(--s)/2))}.mini i:nth-child(4){transform:rotateY(-90deg) translateZ(calc(var(--s)/2))}
.mini i:nth-child(5){transform:rotateX(90deg) translateZ(calc(var(--s)/2))}.mini i:nth-child(6){transform:rotateX(-90deg) translateZ(calc(var(--s)/2))}
@keyframes drift{from{transform:translate(0,0)}to{transform:translate(26px,-46px)}}
@keyframes tumble{to{transform:rotateX(360deg) rotateY(360deg)}}
@media(max-width:980px){.start .hero3d{display:none}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
.marquee svg{animation:bob 1s steps(2) infinite alternate}.marquee svg:nth-child(2){animation-delay:.15s}.marquee svg:nth-child(3){animation-delay:.3s}.marquee svg:nth-child(4){animation-delay:.45s}
.empty svg{animation:bob 1s steps(2) infinite alternate}
.card.soon{border-color:var(--red);border-top-color:var(--red);box-shadow:5px 5px 0 #fecaca}
.card.poof{animation:poof .5s ease-in forwards}
@keyframes poof{to{transform:scale(.9);opacity:0}}
.grid.list{grid-template-columns:1fr}
.grid.list .card{display:flex;align-items:center}.grid.list .thumb{height:84px;width:110px;border:0;border-right:3px solid var(--ink);flex:none}
.grid.list .thumb svg{width:44px;height:44px}.grid.list .meta{flex:1}
.empty{text-align:center;padding:60px 0;color:var(--mute)}
.empty svg{width:84px;height:84px}
.empty p{font-size:17px}
/* dialog boxes */
.dbox{background:#fff;color:var(--ink);border:3px solid var(--ink);border-radius:12px;box-shadow:8px 8px 0 var(--yel)}
dialog{border:0;background:none;padding:0;width:min(600px,94vw);max-height:92vh;overflow:visible}
dialog::backdrop{background:rgba(43,27,77,.55)}
dialog[open]{animation:pop .15s ease-out}
@keyframes pop{from{transform:scale(.96);opacity:0}}
.dlg{padding:26px;max-height:90vh;overflow:auto}
.dbox h2{margin:0 0 16px;font-size:13px;color:var(--ink);background:linear-gradient(transparent 62%,var(--yel) 62%);display:inline-block;padding:0 4px}
label.l{display:block;font-size:13px;font-weight:600;color:var(--mute);margin:16px 0 5px}
.in{width:100%;padding:9px 11px;border:2px solid var(--ink);border-radius:6px;font-size:15px;background:#fff;color:var(--ink)}
.in:focus{outline:3px solid var(--yel);border-color:var(--pur)}
.drop{display:block;border:3px dashed var(--pur);border-radius:10px;padding:18px;text-align:center;color:var(--ink);cursor:pointer;background:var(--pur-l);font-size:15px}
.drop.over,.drop:hover{background:var(--yel-l);border-color:var(--ink)}
.drop svg{width:40px;height:40px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.pill{border:2px solid var(--ink);background:#fff;border-radius:999px;padding:4px 12px;font-size:14px;cursor:pointer;color:var(--ink)}
.pill:hover{background:var(--yel-l)}.pill.on{background:var(--yel);font-weight:600;box-shadow:2px 2px 0 var(--ink)}
.row{display:flex;gap:12px}.row>*{flex:1}
.sw{display:flex;align-items:center;gap:10px;margin-top:14px;cursor:pointer;font-size:15px}
.sw input{width:20px;height:20px;accent-color:var(--pur)}
.actions{display:flex;justify-content:flex-end;gap:12px;margin-top:24px;flex-wrap:wrap}
.btn{border:3px solid var(--ink);border-radius:8px;background:var(--yel);color:var(--ink);font-family:var(--px);font-size:10px;padding:12px 16px;cursor:pointer;
 text-decoration:none;display:inline-block;box-shadow:3px 3px 0 var(--ink);transition:transform .08s}
.btn:hover{background:var(--yel-m);transform:translate(-1px,-1px)}
.btn:active{transform:translate(3px,3px);box-shadow:0 0 0 var(--ink)}
.btn.text{background:#fff;color:var(--ink)}.btn.text:hover{background:var(--pur-l)}.btn.danger{background:var(--red);color:#fff}
/* pages */
.auth{min-height:calc(100vh - 72px);display:grid;place-items:center;padding:24px 16px}
.stack{width:min(480px,100%)}
.box{padding:28px 30px}.box.wide{width:min(660px,100%)}
.title-screen{text-align:center;margin-bottom:24px}
.title-screen h1{font-size:clamp(24px,5.5vw,40px);color:var(--pur);margin:10px 0;text-shadow:4px 4px 0 var(--yel)}
.marquee{height:38px;margin:4px 0;display:flex;justify-content:center}
.marquee .chase{display:flex;gap:12px}
.marquee svg{width:36px;height:36px}
.press{font-family:var(--px);font-size:10px;color:var(--mute)}
.gbtn{display:flex;align-items:center;justify-content:center;gap:12px;border:3px solid var(--ink);border-radius:8px;padding:11px;color:var(--ink);text-decoration:none;
 font-weight:600;font-size:15px;background:#fff;box-shadow:3px 3px 0 var(--ink);margin-top:16px}
.gbtn:hover{background:var(--yel-l)}.gbtn:active{transform:translate(3px,3px);box-shadow:none}
.or{display:flex;align-items:center;gap:10px;color:var(--mute);font-size:13px;margin:16px 0 0}
.or:before,.or:after{content:"";flex:1;border-top:2px solid var(--pur-l)}
.sprite-big{display:block;margin:0 auto 8px;width:64px;height:64px}
.stat{font-size:15px;color:var(--mute)}
/* notifications */
.snack{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);width:min(620px,92vw);z-index:60;padding:16px 22px;font-size:15px;font-weight:500;
 border-left:10px solid var(--yel);animation:up .25s ease-out}
.snack.out{animation:out .35s ease-in forwards}
@keyframes up{from{opacity:0;transform:translate(-50%,16px)}}
@keyframes out{to{opacity:0;transform:translate(-50%,16px)}}
#confetti{position:fixed;inset:0;pointer-events:none;z-index:99}
@media(max-width:640px){.row{flex-direction:column}.brand span{display:none}}
</style></style></head><body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
 <symbol id="s-pac" viewBox="0 0 32 32"><path d="M16 16 L29 7 A16 16 0 1 0 29 25 Z" fill="#ffc400" stroke="#2b1b4d" stroke-width="1.5"/><circle cx="17" cy="8" r="2.4" fill="#000"/></symbol>
 <symbol id="s-ghost" viewBox="0 0 32 32"><path d="M3 30 V15 A13 13 0 0 1 29 15 V30 L24.7 25.5 L20.3 30 L16 25.5 L11.7 30 L7.3 25.5 Z" fill="currentColor"/>
  <ellipse cx="11.5" cy="14" rx="3.6" ry="4.4" fill="#fff"/><ellipse cx="21" cy="14" rx="3.6" ry="4.4" fill="#fff"/>
  <circle cx="13" cy="15" r="1.9" fill="#5b21b6"/><circle cx="22.5" cy="15" r="1.9" fill="#5b21b6"/></symbol>
 <symbol id="s-bolt" viewBox="0 0 32 32"><path d="M19 2 L6 18 H15 L12 30 L26 13 H17 Z" fill="#ffd400" stroke="#000" stroke-width="1.5"/></symbol>
 <symbol id="s-lock" viewBox="0 0 32 32"><rect x="6" y="14" width="20" height="15" rx="2" fill="#ffd400"/><path d="M10 14 V10 a6 6 0 0 1 12 0 V14" fill="none" stroke="#ffd400" stroke-width="3.5"/><rect x="14.5" y="19" width="3" height="5" fill="#000"/></symbol>
 <symbol id="s-cherry" viewBox="0 0 32 32"><path d="M16 4 Q22 6 24 14 M16 4 Q12 8 10 18" fill="none" stroke="#3ddc4a" stroke-width="2.5"/><circle cx="10" cy="22" r="6" fill="#ef4444"/><circle cx="24" cy="20" r="6" fill="#ef4444"/><circle cx="8" cy="20" r="1.6" fill="#fff"/><circle cx="22" cy="18" r="1.6" fill="#fff"/></symbol>
 <symbol id="s-up" viewBox="0 0 32 32"><path d="M16 3 L28 17 H20 V29 H12 V17 H4 Z" fill="#06b6d4" stroke="#000" stroke-width="1.5"/></symbol>
</svg>
<div class="floaters" id="floaters"></div>
<header class="top">
 <a class="brand" href="/">
  <svg class="logo" viewBox="0 0 32 32"><path class="jaw-t" d="M0 16 A16 16 0 0 1 32 16 Z" fill="#ffc400" stroke="#2b1b4d" stroke-width="1.5"/><path class="jaw-b" d="M0 16 A16 16 0 0 0 32 16 Z" fill="#ffc400" stroke="#2b1b4d" stroke-width="1.5"/><circle cx="18" cy="8" r="2.2" fill="#000"/></svg>
  <span>CRADOCS</span></a>
 {% if session.user %}
 <div class="search"><input id="q" type="search" placeholder="Search documents" oninput="applyFilter()" autocomplete="off"></div>
 <span class="spacer"></span>
 <div style="position:relative">
  <button class="avatar" onclick="toggleMenu(event,'acct')" title="{{ session.user }}">{{ session.user[0]|upper }}</button>
  <div class="menu" id="acct"><div class="who">{{ session.user }}</div><a href="/">Home</a><a href="/logout">Sign out</a></div>
 </div>
 {% endif %}
</header>
{{ body }}
{% for cat, m in get_flashed_messages(with_categories=true) %}<div class="snack dbox" data-cat="{{ cat }}"><span class="stx">{{ m }}</span></div>{% endfor %}
<canvas id="confetti"></canvas>
<script>
function toggleMenu(e,id){e.stopPropagation();const m=document.getElementById(id);const was=m.classList.contains('open');
 document.querySelectorAll('.menu.open').forEach(x=>x.classList.remove('open'));if(!was)m.classList.add('open')}
document.addEventListener('click',()=>document.querySelectorAll('.menu.open').forEach(x=>x.classList.remove('open')));
document.querySelectorAll('.snack').forEach(el=>{setTimeout(()=>el.classList.add('out'),5200);setTimeout(()=>el.remove(),5700)});
function party(){const c=document.getElementById('confetti'),x=c.getContext('2d');c.width=innerWidth;c.height=innerHeight;
 const cols=['#ffc400','#7c3aed','#a78bfa','#ec4899','#06b6d4','#ffe066'];
 const p=Array.from({length:110},()=>({x:innerWidth/2,y:innerHeight*.4,vx:(Math.random()-.5)*16,vy:Math.random()*-13-4,s:(Math.random()*3|0)*3+7,c:cols[Math.random()*6|0]}));
 let f=0;(function d(){x.clearRect(0,0,c.width,c.height);p.forEach(q=>{q.x+=q.vx;q.y+=q.vy;q.vy+=.4;x.fillStyle=q.c;x.fillRect(Math.round(q.x/3)*3,Math.round(q.y/3)*3,q.s,q.s)});
 if(++f<90)requestAnimationFrame(d);else x.clearRect(0,0,c.width,c.height)})()}
if(document.querySelector('.snack[data-cat="party"]'))party();
function fmtLeft(s){const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),x=s%60;return d?d+'d '+h+'h':h?h+'h '+m+'m':m?m+'m '+x+'s':x+'s'}
function hpTick(){const now=Math.floor(Date.now()/1000);document.querySelectorAll('.hp').forEach(el=>{
 const e=+el.dataset.exp,st=+el.dataset.start,fill=el.querySelector('.hp-fill'),tx=el.querySelector('.hp-text'),card=el.closest('.card');
 if(!e){fill.style.width='100%';fill.className='hp-fill max';tx.textContent='FOREVER';return}
 const s=e-now,p=Math.max(0,Math.min(1,s/Math.max(1,e-st)));
 if(s<=0){tx.textContent='VANISHED';fill.style.width='0';if(card)card.classList.add('poof');return}
 fill.style.width=(p*100)+'%';fill.className='hp-fill '+(p>.5?'ok':p>.2?'mid':'low');
 tx.textContent=fmtLeft(s)+' left';if(card)card.classList.toggle('soon',s<3600)})}
hpTick();setInterval(hpTick,1000);
document.querySelectorAll('.card,.tile').forEach(el=>{
 el.addEventListener('mousemove',e=>{const r=el.getBoundingClientRect(),px=(e.clientX-r.left)/r.width-.5,py=(e.clientY-r.top)/r.height-.5;
  el.style.transform='perspective(800px) rotateY('+(px*12)+'deg) rotateX('+(-py*12)+'deg) translateZ(10px)';
  el.style.setProperty('--gx',(px+.5)*100+'%');el.style.setProperty('--gy',(py+.5)*100+'%')});
 el.addEventListener('mouseleave',()=>{el.style.transform=''})});
(function(){const f=document.getElementById('floaters');
 if(!f||(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches))return;
 const cols=['#ffc400','#7c3aed','#a78bfa','#ffe066','#ec4899'];
 for(let i=0;i<9;i++){const s=22+Math.random()*34,w=document.createElement('div');w.className='fl';
  w.style.cssText='left:'+Math.random()*94+'%;top:'+Math.random()*90+'%;--d:'+(6+Math.random()*6)+'s';
  const m=document.createElement('div');m.className='mini';m.style.cssText='--s:'+s+'px;--t:'+(10+Math.random()*14)+'s';
  for(let k=0;k<6;k++){const e=document.createElement('i');e.style.background=cols[(i+k)%cols.length];m.appendChild(e)}
  w.appendChild(m);f.appendChild(w)}})();
</script>
</body></html>
"""

HOME = """
<section class="start"><div class="wrap">
 {{ cube() }}
 <h2>Start a new document</h2>
 <div class="hint">Pick how long it lives. When time is up, it vanishes.</div>
 <div class="lane"><div class="runner">
  <svg viewBox="0 0 32 32"><use href="#s-pac"/></svg>
  <svg viewBox="0 0 32 32" style="color:#ef4444"><use href="#s-ghost"/></svg>
  <svg viewBox="0 0 32 32" style="color:#ec4899"><use href="#s-ghost"/></svg>
 </div></div>
  <div class="tiles">
  <button class="tile" data-amount="{{ default_hours }}" data-unit="hours" onclick="openUpload(this)">
   <div class="ico"><svg viewBox="0 0 32 32"><use href="#s-pac"/></svg></div>
   <div class="tile-name">New upload</div><div class="tile-sub">Your default time</div></button>
  <button class="tile" data-amount="1" data-unit="hours" onclick="openUpload(this)">
   <div class="ico"><svg viewBox="0 0 32 32"><use href="#s-bolt"/></svg></div>
   <div class="tile-name">Quick share</div><div class="tile-sub">Vanishes in 1 hour</div></button>
  <button class="tile" data-amount="7" data-unit="days" onclick="openUpload(this)">
   <div class="ico"><svg viewBox="0 0 32 32"><use href="#s-cherry"/></svg></div>
   <div class="tile-name">This week</div><div class="tile-sub">Vanishes in 7 days</div></button>
  <button class="tile" data-forever="1" onclick="openUpload(this)">
   <div class="ico">&#8734;</div>
   <div class="tile-name">Forever vault</div><div class="tile-sub">Never auto-deleted</div></button>
 </div>
</div></section>

<section class="wrap recent">
 <div class="recent-head"><h2>Recent documents</h2>
  <span class="score">{{ docs|length }} document{{ "" if docs|length == 1 else "s" }}</span>
  <select id="owner" onchange="applyFilter()"><option value="all">Owned by anyone</option><option value="me">Owned by me</option><option value="other">Not owned by me</option></select>
  <button class="icon-btn" id="viewbtn" title="Toggle list view" onclick="toggleView()">&#9776;</button>
 </div>
 {% if docs %}
 <div class="grid" id="grid">
 {% for d in docs %}
  <div class="card" data-name="{{ d.filename|lower }}" data-owner="{{ 'me' if d.owner == user else 'other' }}" style="animation-delay:{{ loop.index0 * 60 }}ms">
   <a class="thumb" href="/download/{{ d.doc_id }}" title="Download">
    <span class="badge">{{ ftype(d.filename) }}</span>
    {% if d.pw_hash %}<span class="badge lock">LOCKED</span>{% endif %}
    <svg viewBox="0 0 32 32" style="color:{{ ghost(d.doc_id) }}"><use href="#s-ghost"/></svg></a>
   <div class="meta">
    <div class="title" title="{{ d.filename }}">{{ d.filename }}</div>
    <div class="owner">Owner: {{ 'you' if d.owner == user else d.owner }}</div>
    <div class="hp" data-start="{{ d.starts_at or d.created_at or 0 }}" data-exp="{{ d.expires_at or 0 }}">
     <span class="hp-label">TIME</span><div class="hp-bar"><div class="hp-fill"></div></div><div class="hp-text"></div></div>
    <button class="icon-btn dots" onclick="toggleMenu(event,'m{{ loop.index }}')">&#8942;</button>
    <div class="menu" id="m{{ loop.index }}" style="right:8px;top:44px">
     <a href="/download/{{ d.doc_id }}">Download</a>
     {% if d.owner == user %}<a href="/manage/{{ d.doc_id }}">Share and settings</a>{% endif %}
    </div>
   </div>
  </div>
 {% endfor %}
 </div>
 <div class="empty" id="none" style="display:none"><p>No matches. Try another search.</p></div>
 {% else %}
 <div class="empty"><svg viewBox="0 0 32 32" style="color:#06b6d4"><use href="#s-ghost"/></svg>
  <p>Nothing here yet.<br>Drop in a document and it'll be guarded.</p></div>
 {% endif %}
</section>

<dialog id="up"><form class="dlg dbox" method="post" action="/upload" enctype="multipart/form-data">{{ csrf }}
 <h2>Upload a document</h2>
 <label class="drop" id="drop"><input type="file" name="file" id="file" required hidden onchange="picked()">
  <svg viewBox="0 0 32 32"><use href="#s-up"/></svg><br><span id="dropt">Drop a file here or click to browse (max 10 MB)</span></label>

 <label class="l">How long should it live?</label>
 <div class="chips" id="chips">
  <button type="button" class="pill" data-a="30" data-u="minutes">30 min</button>
  <button type="button" class="pill" data-a="1" data-u="hours">1 hour</button>
  <button type="button" class="pill" data-a="6" data-u="hours">6 hours</button>
  <button type="button" class="pill" data-a="1" data-u="days">1 day</button>
  <button type="button" class="pill" data-a="7" data-u="days">1 week</button>
  <button type="button" class="pill" data-a="30" data-u="days">30 days</button>
 </div>
 <div class="row" id="custom">
  <input class="in" type="number" min="1" name="amount" id="amount" value="{{ default_hours }}" oninput="clearPills()">
  <select class="in" name="unit" id="unit" onchange="clearPills()">
   <option value="minutes">minutes</option><option value="hours" selected>hours</option><option value="days">days</option><option value="weeks">weeks</option>
  </select>
 </div>
 <label class="sw"><input type="checkbox" name="forever" id="forever" onchange="foreverToggle()"> <span>Keep forever (never auto-delete)</span></label>

 <label class="l">Share with (usernames or emails, comma separated)</label>
 <input class="in" name="allowed" placeholder="alice, bob@gmail.com">
 <div class="row">
  <div><label class="l">Access starts (blank = now)</label><input class="in" type="datetime-local" name="starts"></div>
  <div><label class="l">Max downloads (0 = unlimited)</label><input class="in" type="number" min="0" name="max_dl" value="0"></div>
 </div>
 <label class="l">Password lock (optional, great for IDs and forever docs)</label>
 <input class="in" type="password" name="password" autocomplete="new-password">
 <div class="actions"><button type="button" class="btn text" onclick="up.close()">Cancel</button><button class="btn">Upload</button></div>
</form></dialog>

<script>
const up=document.getElementById('up'),grid=document.getElementById('grid');
function setPill(a,u){document.querySelectorAll('#chips .pill').forEach(p=>p.classList.toggle('on',p.dataset.a==a&&p.dataset.u==u))}
function clearPills(){document.querySelectorAll('#chips .pill').forEach(p=>p.classList.remove('on'))}
function foreverToggle(){const f=document.getElementById('forever').checked;
 document.getElementById('custom').style.opacity=f?.35:1;document.getElementById('chips').style.opacity=f?.35:1;
 document.getElementById('amount').disabled=f;document.getElementById('unit').disabled=f}
document.querySelectorAll('#chips .pill').forEach(p=>p.onclick=()=>{amount.value=p.dataset.a;unit.value=p.dataset.u;forever.checked=false;foreverToggle();setPill(p.dataset.a,p.dataset.u)});
function openUpload(t){const f=!!t.dataset.forever;forever.checked=f;
 if(!f){amount.value=t.dataset.amount;unit.value=t.dataset.unit;setPill(t.dataset.amount,t.dataset.unit)}
 foreverToggle();up.showModal()}
function picked(){const f=document.getElementById('file').files[0];if(f)document.getElementById('dropt').textContent='Ready: '+f.name}
const drop=document.getElementById('drop');
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,()=>drop.classList.remove('over')));
drop.addEventListener('drop',ev=>{ev.preventDefault();document.getElementById('file').files=ev.dataTransfer.files;picked()});
function applyFilter(){const q=document.getElementById('q').value.toLowerCase(),o=document.getElementById('owner').value;let n=0;
 document.querySelectorAll('.card').forEach(c=>{const ok=c.dataset.name.includes(q)&&(o==='all'||c.dataset.owner===o);c.style.display=ok?'':'none';if(ok)n++});
 const none=document.getElementById('none');if(none)none.style.display=n?'none':'block'}
function toggleView(){if(!grid)return;grid.classList.toggle('list');try{localStorage.setItem('cra-view',grid.classList.contains('list')?'list':'grid')}catch(e){}}
try{if(localStorage.getItem('cra-view')==='list'&&grid)grid.classList.add('list')}catch(e){}
</script>
"""

LOGIN = """
<div class="auth"><div class="stack">
 <div class="title-screen">
  {{ cube() }}
  <div class="marquee"><div class="chase">
   <svg viewBox="0 0 32 32"><use href="#s-pac"/></svg>
   <svg viewBox="0 0 32 32" style="color:#ef4444"><use href="#s-ghost"/></svg>
   <svg viewBox="0 0 32 32" style="color:#ec4899"><use href="#s-ghost"/></svg>
   <svg viewBox="0 0 32 32" style="color:#06b6d4"><use href="#s-ghost"/></svg>
  </div></div>
  <h1>CRADOCS</h1>
  <div class="press">{{ prompt }}</div>
 </div>
 <form class="box dbox" method="post">{{ csrf }}
  <h2>{{ title }}</h2>
  <div class="stat">{{ subtitle }}</div>
  {% if google %}
  <a class="gbtn" href="/auth/google">
   <svg width="20" height="20" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z"/><path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.9 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/></svg>
   Continue with Google</a>
  <div class="or"><span>or</span></div>
  {% endif %}
  <label class="l">Username</label><input class="in" name="username" required {% if not google %}autofocus{% endif %}>
  <label class="l">Password</label><input class="in" type="password" name="password" required>
  {% if register %}<label class="l">Default auto-delete time for your uploads (hours)</label>
  <input class="in" type="number" name="default_hours" value="24" min="1">{% endif %}
  <div class="actions" style="justify-content:space-between">
   <a class="btn text" href="{{ alt_url }}">{{ alt_text }}</a><button class="btn">{{ cta }}</button></div>
 </form>
</div></div>
"""

MANAGE = """
<div class="auth"><div class="stack" style="width:min(660px,100%)">
 <div class="box dbox">
  <svg class="sprite-big" viewBox="0 0 32 32" style="color:{{ ghost(d.doc_id) }}"><use href="#s-ghost"/></svg>
  <h2 style="text-align:center">{{ d.filename }}</h2>
  <div class="stat" style="text-align:center">Owner: you &middot; Downloads used: {{ d.downloads or 0 }}</div>
  <div class="hp card-hp" style="margin-top:12px" data-start="{{ d.starts_at or d.created_at or 0 }}" data-exp="{{ d.expires_at or 0 }}">
   <span class="hp-label" style="color:#111">TIME</span><div class="hp-bar"><div class="hp-fill"></div></div><div class="hp-text" style="color:#111"></div></div>
  <form method="post">{{ csrf }}<input type="hidden" name="action" value="save">
   <label class="l">People with access (comma separated; remove a name to revoke)</label>
   <input class="in" name="allowed" value="{{ d.allowed_users|join(', ') }}">
   <label class="l">Change how long it lives (counted from now)</label>
   <div class="row"><input class="in" type="number" min="1" name="amount" placeholder="leave blank to keep current">
    <select class="in" name="unit"><option value="minutes">minutes</option><option value="hours" selected>hours</option><option value="days">days</option><option value="weeks">weeks</option></select></div>
   <label class="sw"><input type="checkbox" name="forever" {% if not d.expires_at %}checked{% endif %}> <span>Keep forever</span></label>
   <label class="l">Max downloads (0 = unlimited)</label>
   <input class="in" type="number" min="0" name="max_dl" value="{{ d.max_downloads or 0 }}">
   {% if d.pw_hash %}<label class="l">Document password (needed to save or delete)</label>
   <input class="in" type="password" name="password" required>{% endif %}
   <div class="actions"><a class="btn text" href="/">Back</a><button class="btn">Save</button></div>
  </form>
  <hr style="border:0;border-top:4px dashed #888;margin:24px 0">
  <form method="post" onsubmit="return confirm('Delete this document for good?')">{{ csrf }}
   <input type="hidden" name="action" value="delete">
   {% if d.pw_hash %}<label class="l">Document password</label><input class="in" type="password" name="password" required>{% endif %}
   <div class="actions"><button class="btn danger">Delete now</button></div>
  </form>
 </div>
</div></div>
"""

PASSWORD = """
<div class="auth"><form class="box dbox stack" method="post">{{ csrf }}
 <svg class="sprite-big" viewBox="0 0 32 32"><use href="#s-lock"/></svg>
 <h2 style="text-align:center">Password required</h2>
 <div class="stat" style="text-align:center">{{ filename }}</div>
 <input class="in" type="password" name="password" autofocus required style="margin-top:14px">
 <div class="actions"><a class="btn text" href="/">Cancel</a><button class="btn">Unlock and download</button></div>
</form></div>
"""


# ---------------------------------------------------------------- helpers --
def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M") if ts else "Never"


def ftype(name):
    ext = name.rsplit(".", 1)[-1] if "." in name else "file"
    return ext[:4].upper()


def ghost(doc_id):
    return GHOSTS[int(doc_id[:6], 16) % len(GHOSTS)]


CUBE = (
    '<div class="hero3d scene" aria-hidden="true"><div class="cube">'
    '<div class="face f1"><svg viewBox="0 0 32 32"><use href="#s-pac"/></svg></div>'
    '<div class="face f2"><svg viewBox="0 0 32 32" style="color:#7c3aed"><use href="#s-ghost"/></svg></div>'
    '<div class="face f3"><svg viewBox="0 0 32 32"><use href="#s-bolt"/></svg></div>'
    '<div class="face f4"><svg viewBox="0 0 32 32"><use href="#s-cherry"/></svg></div>'
    '<div class="face f5">&#8734;</div>'
    '<div class="face f6"><svg viewBox="0 0 32 32"><use href="#s-lock"/></svg></div>'
    '</div><div class="cube-shadow"></div></div>'
)


def cube():
    return Markup(CUBE)


app.jinja_env.globals.update(fmt=fmt, ftype=ftype, ghost=ghost, cube=cube)


@app.context_processor
def inject_csrf():
    return {"csrf": Markup('<input type="hidden" name="csrf" value="%s">' % session.get("csrf", ""))}


@app.before_request
def csrf_protect():
    if "csrf" not in session:
        session["csrf"] = uuid.uuid4().hex
    if request.method == "POST" and request.form.get("csrf") != session["csrf"]:
        abort(400, "Bad CSRF token")


def page(body_template, **ctx):
    body = render_template_string(body_template, **ctx)
    return render_template_string(LAYOUT, body=Markup(body))


def me():
    return session.get("user")


def need_login():
    return None if me() else redirect(url_for("login"))


def parse_duration(form):
    """Seconds the doc should live, or None for 'keep forever'."""
    if "forever" in form:
        return None
    amount = max(1, int(form.get("amount") or 1))
    return amount * UNITS[form.get("unit", "hours")]


def check_access(doc, user, password=None):
    """Return (ok, reason). reason == 'password' means a password prompt is needed."""
    now = int(time.time())
    if doc.get("expires_at") and now >= doc["expires_at"]:
        return False, "This document has expired."
    if user != doc["owner"]:
        if user not in doc.get("allowed_users", []):
            return False, "You don't have access to this document."
        if doc.get("starts_at") and now < doc["starts_at"]:
            return False, f"Access starts {fmt(doc['starts_at'])}."
    limit = doc.get("max_downloads", 0)
    if limit and doc.get("downloads", 0) >= limit:
        return False, "Download limit reached."
    if doc.get("pw_hash") and not (password and check_password_hash(doc["pw_hash"], password)):
        return False, "password"
    return True, ""


def parse_users(text):
    return sorted({u.strip().lower() for u in (text or "").split(",") if u.strip()})


# ----------------------------------------------------------------- routes --
@app.route("/")
def index():
    if need_login():
        return need_login()
    run_cleanup(store)  # safety net; the scheduled Lambda does the real work on AWS
    docs = [d for d in store.list_docs()
            if d["owner"] == me() or me() in d.get("allowed_users", [])]
    docs.sort(key=lambda d: d.get("created_at", 0), reverse=True)
    default_hours = (store.get_user(me()) or {}).get("default_hours", 24)
    return page(HOME, docs=docs, user=me(), default_hours=default_hours)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        if not username or len(password) < 4:
            flash("Enter a username and a password of at least 4 characters.")
        elif "@" in username:  # '@' is reserved for Google accounts (username = verified email)
            flash("Usernames can't contain '@'. Use 'Continue with Google' for email sign-in.")
        elif store.create_user({
            "username": username,
            "pw_hash": generate_password_hash(password),
            "default_hours": max(1, int(request.form.get("default_hours") or 24)),
        }):
            session["user"] = username
            flash("You're in. Welcome to CraDocs!", "party")
            return redirect(url_for("index"))
        else:
            flash("That username is taken.")
    return page(LOGIN, title="Create account", subtitle="Set up your private document vault.",
                prompt="Your private vault", register=True, google=GOOGLE_ENABLED, alt_url="/login",
                alt_text="Sign in instead", cta="Create account")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = store.get_user(request.form["username"].strip().lower())
        # Google-only accounts have no password hash, so they can't sign in here.
        if user and user.get("pw_hash") and check_password_hash(user["pw_hash"], request.form["password"]):
            session["user"] = user["username"]
            return redirect(url_for("index"))
        flash("Invalid username or password.")
    return page(LOGIN, title="Sign in", subtitle="Share it when you need it. It disappears when you don't.",
                prompt="Your private vault", register=False, google=GOOGLE_ENABLED,
                alt_url="/register", alt_text="Create account", cta="Next")


@app.route("/auth/google")
def google_login():
    if not GOOGLE_ENABLED:
        abort(404)
    return oauth.google.authorize_redirect(url_for("google_callback", _external=True))


@app.route("/auth/google/callback")
def google_callback():
    if not GOOGLE_ENABLED:
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash("Google sign-in was cancelled or failed. Please try again.")
        return redirect(url_for("login"))
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    if not email or not info.get("email_verified"):
        flash("Your Google email isn't verified.")
        return redirect(url_for("login"))
    if not store.get_user(email):
        store.create_user({"username": email, "pw_hash": None, "default_hours": 24, "provider": "google"})
        flash("You're in. Welcome to CraDocs!", "party")
    session["user"] = email
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/upload", methods=["POST"])
def upload():
    if need_login():
        return need_login()
    f = request.files.get("file")
    password = request.form.get("password", "")
    if not f or not f.filename:
        flash("Choose a file first.")
        return redirect(url_for("index"))
    now = int(time.time())
    try:
        starts = request.form.get("starts")
        starts_at = int(datetime.fromisoformat(starts).timestamp()) if starts else now
        duration = parse_duration(request.form)
        max_dl = max(0, int(request.form.get("max_dl") or 0))
    except (ValueError, KeyError):
        flash("Invalid date, time or number.")
        return redirect(url_for("index"))
    forever = duration is None
    doc = {
        "doc_id": uuid.uuid4().hex,
        "owner": me(),
        "filename": secure_filename(f.filename) or "document",
        "allowed_users": parse_users(request.form.get("allowed")),
        "created_at": now,
        "starts_at": starts_at,
        "expires_at": None if forever else starts_at + duration,
        "max_downloads": max_dl,
        "downloads": 0,
        "permanent": forever,
        "pw_hash": generate_password_hash(password) if password else None,
    }
    store.save_file(doc["doc_id"], f.stream)
    store.put_doc(doc)
    flash("Nice, document stored. " + ("It stays until you delete it." if forever else "It will vanish when its time is up."), "party")
    return redirect(url_for("index"))


@app.route("/download/<doc_id>", methods=["GET", "POST"])
def download(doc_id):
    if need_login():
        return need_login()
    doc = store.get_doc(doc_id)
    if not doc:
        abort(404)
    ok, reason = check_access(doc, me(), request.form.get("password"))
    if not ok and reason == "password":
        if request.method == "POST":
            flash("Wrong password. Try again.")
        return page(PASSWORD, filename=doc["filename"])
    if not ok:
        flash(reason)
        return redirect(url_for("index"))
    if not store.claim_download(doc_id):
        flash("Download limit reached.")
        return redirect(url_for("index"))
    url = store.download_url(doc_id, doc["filename"])
    if url:
        return redirect(url)
    return send_file(store.local_path(doc_id), as_attachment=True, download_name=doc["filename"])


@app.route("/manage/<doc_id>", methods=["GET", "POST"])
def manage(doc_id):
    if need_login():
        return need_login()
    doc = store.get_doc(doc_id)
    if not doc or doc["owner"] != me():
        abort(404)
    if request.method == "POST":
        if doc.get("pw_hash") and not check_password_hash(doc["pw_hash"], request.form.get("password", "")):
            flash("Wrong document password.")
            return redirect(url_for("manage", doc_id=doc_id))
        if request.form.get("action") == "delete":
            store.delete_file(doc_id)
            store.delete_doc(doc_id)
            flash("Poof. Document deleted.")
            return redirect(url_for("index"))
        try:
            doc["allowed_users"] = parse_users(request.form.get("allowed"))
            doc["max_downloads"] = max(0, int(request.form.get("max_dl") or 0))
            if "forever" in request.form:
                doc["expires_at"], doc["permanent"] = None, True
            elif request.form.get("amount"):
                doc["expires_at"] = int(time.time()) + parse_duration(request.form)
                doc["permanent"] = False
            elif doc.get("permanent"):  # unticked forever, no new time given
                flash("Pick how long it should live, or keep it forever.")
                return redirect(url_for("manage", doc_id=doc_id))
        except (ValueError, KeyError):
            flash("Invalid number.")
            return redirect(url_for("manage", doc_id=doc_id))
        store.put_doc(doc)
        flash("Saved.")
        return redirect(url_for("manage", doc_id=doc_id))
    return page(MANAGE, d=doc)


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")

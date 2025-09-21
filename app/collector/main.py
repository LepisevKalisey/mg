import asyncio
import logging
import os
import secrets
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv
from telethon.errors import SessionPasswordNeededError
from telethon import __version__ as telethon_version

# Подхватим .env из корня проекта при локальном запуске
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

from .config import settings
from .storage import ensure_dirs
from .telegram_client import TelegramMonitor


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("collector.main")

app = FastAPI(title="MediaGenerator Collector", version="0.2.1")

monitor = TelegramMonitor()
startup_task = None

# --- QR login configuration (can be overridden via env) ---
QR_PER_TOKEN_TIMEOUT = int(os.getenv("QR_PER_TOKEN_TIMEOUT", "70"))
QR_MAX_ATTEMPTS = int(os.getenv("QR_MAX_ATTEMPTS", "5"))

# In-memory sessions for QR authorization
_qr_sessions: Dict[str, Dict[str, Any]] = {}
# Code-based auth sessions
_code_sessions: Dict[str, Dict[str, Any]] = {}


def _mask_value(val: Optional[str], keep: int = 4) -> str:
    if not val:
        return "<none>"
    if len(val) <= keep:
        return "*" * len(val)
    return val[:keep] + "*" * (len(val) - keep)


def _mask_phone(phone: Optional[str]) -> str:
    if not phone:
        return "<none>"
    digits = "".join([c for c in phone if c.isdigit()])
    tail = digits[-4:] if len(digits) >= 4 else digits
    return f"+***{tail}"


def _mask_url(url: Optional[str]) -> str:
    if not url:
        return "<none>"
    try:
        prefix = url.split("?", 1)[0]
        return f"{prefix}?token=<hidden>"
    except Exception:
        return "<hidden>"


async def _ensure_client_connected() -> None:
    # Гарантируем подключение клиента Telethon, используем экземпляр из TelegramMonitor
    if not monitor.client.is_connected():
        await monitor.client.connect()


async def _qr_runner(sid: str) -> None:
    sess = _qr_sessions.get(sid)
    if not sess:
        return

    try:
        await _ensure_client_connected()

        # По актуальной схеме Telethon держим один объект qr_login и по таймауту вызываем recreate(),
        # чтобы обновить токен и URL без переинициализации клиента
        qr_login = await monitor.client.qr_login()
        attempt = 1
        # Поставим начальные данные (URL может быть уже доступен)
        sess.update({"status": "waiting", "attempt": attempt, "url": getattr(qr_login, "url", None)})
        logger.info("QR[%s] attempt %s/%s url=%s", sid, attempt, QR_MAX_ATTEMPTS, _mask_url(sess.get("url")))

        while attempt <= QR_MAX_ATTEMPTS:
            try:
                # важно: ожидание должно выполняться, пока QR сканируют
                await asyncio.wait_for(qr_login.wait(), timeout=QR_PER_TOKEN_TIMEOUT)
                logger.info("QR[%s] accepted", sid)
                # Проверим, авторизовались ли без 2FA
                if await monitor.client.is_user_authorized():
                    monitor._authorized = True
                    sess.update({"status": "done", "authorized": True})
                else:
                    sess.update({"status": "2fa_required", "authorized": False})
                return
            except asyncio.TimeoutError:
                # Токен истёк, обновим его без пересоздания клиента
                attempt += 1
                if attempt > QR_MAX_ATTEMPTS:
                    break
                logger.warning(
                    "QR[%s] token expired after %ss, recreating token (attempt %s/%s)...",
                    sid, QR_PER_TOKEN_TIMEOUT, attempt, QR_MAX_ATTEMPTS,
                )
                try:
                    await qr_login.recreate()
                except Exception as e:
                    logger.exception("QR[%s] recreate() failed: %s", sid, e)
                    sess.update({"status": "error", "error": str(e)})
                    return
                # Обновим URL
                url = getattr(qr_login, "url", None)
                sess.update({"status": "waiting", "attempt": attempt, "url": url})
                logger.info("QR[%s] new url=%s", sid, _mask_url(url))
            except SessionPasswordNeededError:
                sess.update({"status": "2fa_required", "authorized": False})
                return
            except Exception as e:
                logger.exception("QR[%s] error during wait: %s", sid, e)
                sess.update({"status": "error", "error": str(e)})
                return

        sess.update({"status": "expired"})
    except Exception as e:
        logger.exception("QR[%s] runner failed: %s", sid, e)
        sess.update({"status": "error", "error": str(e)})


@app.on_event("startup")
async def on_startup():
    ensure_dirs(settings.DATA_DIR, settings.PENDING_DIR, settings.APPROVED_DIR, settings.SESSIONS_DIR)
    # Стартуем мониторинг (если уже авторизованы). Если не авторизованы — просто запустится API, а мониторинг пропустим
    await monitor.start()


@app.on_event("shutdown")
async def on_shutdown():
    await monitor.stop()


@app.get("/health")
async def health():
    status = "ok" if monitor.authorized else "unauthorized"
    return JSONResponse({
        "service": "collector",
        "status": status,
        "authorized": monitor.authorized,
        "channels": settings.MONITORING_CHANNELS,
        "data_dirs": {
            "data": settings.DATA_DIR,
            "pending": settings.PENDING_DIR,
            "approved": settings.APPROVED_DIR,
            "sessions": settings.SESSIONS_DIR,
        }
    })


# ----------------- Web UI for QR Authorization -----------------
QR_HTML = """
<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Telegram QR Login</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#0b1220; color:#e7ecf3; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
    .card { background:#111a2b; border:1px solid #22304a; border-radius:16px; padding:24px; width: min(520px, 92vw); box-shadow: 0 12px 32px rgba(0,0,0,0.45); }
    h1 { font-size: 20px; margin: 0 0 12px; }
    .muted { color:#92a1b3; font-size: 14px; }
    #qrcode { display:flex; align-items:center; justify-content:center; background:#0b1220; border-radius:12px; padding:16px; margin:16px 0; min-height:260px; }
    a.link { color:#5cc8ff; text-decoration: none; }
    .status { margin-top:8px; font-size:14px; color:#9fb3c8; }
    .ok { color:#7ce38b; }
    .warn { color:#ffcc66; }
    .err { color:#ff6b6b; }
    .row { display:flex; gap:12px; align-items:center; }
    input[type=password] { flex:1; padding:10px 12px; border-radius:8px; border:1px solid #2b3b58; background:#0b1220; color:#e7ecf3; }
    button { padding:10px 14px; border-radius:8px; border:1px solid #2b3b58; background:#1a2740; color:#e7ecf3; cursor:pointer; }
    button:hover { background:#223556; }
    code { background:#0b1220; padding:2px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>Вход в Telegram по QR</h1>
    <div class=\"muted\">Откройте Telegram на телефоне → Настройки → Устройства → Подключить устройство → Сканируйте QR ниже.</div>
    <div id=\"qrcode\">Генерация QR…</div>
    <div id=\"link\"></div>
    <div class=\"status\" id=\"status\">Ожидание…</div>
    <div id=\"twofa\" style=\"display:none;\">
      <div class=\"status warn\">Включена двухэтапная аутентификация. Введите пароль, чтобы завершить вход.</div>
      <div class=\"row\" style=\"margin-top:8px;\">
        <input id=\"pwd\" type=\"password\" placeholder=\"Пароль 2FA\" />
        <button onclick=\"send2fa()\">Отправить</button>
      </div>
      <div class=\"status err\" id=\"twofa_status\"></div>
    </div>
  </div>

  <script>
    // Minimal QR generator (uses Canvas) – QRCode.js (MIT) embedded
    /*! qrcode.js v1.0.0 (MIT) */
    // Tiny subset to render QR to canvas
    /* eslint-disable */
    var QR8bitByte=function(t){this.mode=1,this.data=t,this.parsedData=[];for(var e=0,n=this.data.length;e<n;e++){var r=[],i=this.data.charCodeAt(e);i>65536?(r[0]=240|(1835008&i)>>>18,r[1]=128|(258048&i)>>>12,r[2]=128|(4032&i)>>>6,r[3]=128|63&i):i>2048?(r[0]=224|(61440&i)>>>12,r[1]=128|(4032&i)>>>6,r[2]=128|63&i):i>128?(r[0]=192|(1984&i)>>>6,r[1]=128|63&i):r[0]=i,this.parsedData.push(r)}this.parsedData=Array.prototype.concat.apply([],this.parsedData)};QR8bitByte.prototype={getLength:function(){return this.parsedData.length},write:function(t){for(var e=0,n=this.parsedData.length;e<n;e++)t.put(this.parsedData[e],8)}};var QRUtil={PATTERN_POSITION_TABLE:[[],[6,18],[6,22],[6,26],[6,30],[6,34]],G15:1335,G18:7973,G15_MASK:21522,getBCHDigit:function(t){for(var e=0;0!=t;)e++,t>>>=1;return e},getBCHTypeInfo:function(t){for(var e=t<<10;QRUtil.getBCHDigit(e)-QRUtil.getBCHDigit(QRUtil.G15)>=0;)e^=QRUtil.G15<<QRUtil.getBCHDigit(e)-QRUtil.getBCHDigit(QRUtil.G15);return(t<<10|e)^QRUtil.G15_MASK}};var QRMath={glog:function(t){if(t<1)throw new Error("glog("+t+")");return QRMath.LOG_TABLE[t]},gexp:function(t){for(;t<0;)t+=255;for(;t>=256;)t-=255;return QRMath.EXP_TABLE[t]},EXP_TABLE:new Array(256),LOG_TABLE:new Array(256)};for(var i=0;i<8;i++)QRMath.EXP_TABLE[i]=1<<i;for(i=8;i<256;i++)QRMath.EXP_TABLE[i]=QRMath.EXP_TABLE[i-4]^QRMath.EXP_TABLE[i-5]^QRMath.EXP_TABLE[i-6]^QRMath.EXP_TABLE[i-8];for(i=0;i<255;i++)QRMath.LOG_TABLE[QRMath.EXP_TABLE[i]]=i;function QRPolynomial(t,e){if(null==t.length)throw new Error(t.length+"/"+e);for(var n=0;n<t.length&&0==t[n];)n++;this.num=new Array(t.length-n+e);for(var r=0;r<t.length-n;r++)this.num[r]=t[r+n]}QRPolynomial.prototype={get:function(t){return this.num[t]},getLength:function(){return this.num.length},multiply:function(t){for(var e=new Array(this.getLength()+t.getLength()-1),n=0;n<this.getLength();n++)for(var r=0;r<t.getLength();r++)e[n+r]^=QRMath.gexp(QRMath.glog(this.get(n))+QRMath.glog(t.get(r)));return new QRPolynomial(e,0)},mod:function(t){if(this.getLength()-t.getLength()<0)return this;for(var e=QRMath.glog(this.get(0))-QRMath.glog(t.get(0)),n=new Array(this.getLength()),r=0;r<this.getLength();r++)n[r]=this.get(r);for(r=0;r<t.getLength();r++)n[r]^=QRMath.gexp(QRMath.glog(t.get(r))+e);return new QRPolynomial(n,0).mod(t)}};var QRRSBlock={RS_BLOCK_TABLE:[[1,26,19],[1,44,34],[1,70,55],[1,100,80],[1,134,108]],getRSBlocks:function(t){return[ new QRRSBlock(1,26,19), new QRRSBlock(1,44,34), new QRRSBlock(1,70,55), new QRRSBlock(1,100,80), new QRRSBlock(1,134,108) ]}};function QRRSBlock(t,e,n){this.totalCount=t,this.dataCount=n}var QRBitBuffer=function(){this.buffer=[],this.length=0};QRBitBuffer.prototype={get:function(t){return 1==(this.buffer[Math.floor(t/8)]>>>7-t%8&1)},put:function(t,e){for(var n=0;n<e;n++)this.putBit(1==(t>>>e-n-1&1))},putBit:function(t){var e=Math.floor(this.length/8);this.buffer.length<=e&&this.buffer.push(0),t&&(this.buffer[e]|=128>>>this.length%8),this.length++}};var QRCode=function(){this.typeNumber=1,this.errorCorrectLevel=0,this.modules=null,this.moduleCount=0,this.dataList=[]};QRCode.prototype={addData:function(t){this.dataList.push(new QR8bitByte(t))},make:function(){this.typeNumber=4,this.moduleCount=33,this.modules=new Array(this.moduleCount);for(var t=0;t<this.moduleCount;t++){this.modules[t]=new Array(this.moduleCount);for(var e=0;e<this.moduleCount;e++)this.modules[t][e]=null}this.setupPositionProbePattern(0,0),this.setupPositionProbePattern(this.moduleCount-7,0),this.setupPositionProbePattern(0,this.moduleCount-7),this.mapData(this.createData())},setupPositionProbePattern:function(t,e){for(var n=-1;n<=7;n++)if(!(t+n<=-1||this.moduleCount<=t+n))for(var r=-1;r<=7;r++)e+r<=-1||this.moduleCount<=e+r||(this.modules[t+n][e+r]=n>=0&&n<=6&&(0==r||6==r)||r>=0&&r<=6&&(0==n||6==n)||n>=2&&n<=4&&r>=2&&r<=4)},mapData:function(t){for(var e=-1,n=this.moduleCount-1,r=7,i=0;n>0;n-=2){for(6==n&&n--;!0;){for(var o=0;o<2;o++)null==this.modules[n-o][i]&&(this.modules[n-o][i]=1==(t.get(i)>>>r&1));if((i+=e)<0||this.moduleCount<=i){i-=e,e=-e;break} }if((r--)<0&&(r=7,t=t.length>0?t.shift():new QRBitBuffer(),0==t.length))break}},createData:function(){for(var t=[],e=new QRBitBuffer(),n=0;n<this.dataList.length;n++)e.put(4,4),e.put(this.dataList[n].getLength(),8),this.dataList[n].write(e);for(;e.length+4<=8;)e.put(0,4);for(;e.length%8!=0;)e.putBit(!1);for(var r=0;r<QRRSBlock.getRSBlocks(this.typeNumber).length;r++){var i=QRRSBlock.getRSBlocks(this.typeNumber)[r].dataCount;for(n=0;n<i;n++)t.push(0)}return[t,e]}};function drawQR(t){var e=document.createElement('canvas');e.width=256;e.height=256;var n=e.getContext('2d');n.fillStyle='#fff',n.fillRect(0,0,256,256);var r=new QRCode;r.addData(t),r.make();var i=r.modules.length,o=256/(i+8);n.fillStyle='#000';for(var a=0;a<i;a++)for(var s=0;s<i;s++)r.modules[a][s]&&(n.fillRect(Math.round((s+4)*o),Math.round((a+4)*o),Math.ceil(o),Math.ceil(o)));return e}

    let sid = null;
    let lastUrl = null;
    let timer = null;

    async function start() {
      const resp = await fetch('/auth/qr/start', {method:'POST'});
      const data = await resp.json();
      sid = data.sid;
      poll();
      timer = setInterval(poll, 2000);
    }

    async function poll() {
      if (!sid) return;
      const resp = await fetch('/auth/qr/status?sid=' + encodeURIComponent(sid));
      const data = await resp.json();
      const statusEl = document.getElementById('status');
      const linkEl = document.getElementById('link');
      if (data.status === 'waiting' && data.url) {
        if (data.url !== lastUrl) {
          lastUrl = data.url;
          const cont = document.getElementById('qrcode');
          cont.innerHTML = '';
          cont.appendChild(drawQR(data.url));
          linkEl.innerHTML = '<a class="link" href="'+data.url+'">Открыть в Telegram</a>';
          statusEl.textContent = 'Ожидание подтверждения на другом устройстве…';
        }
      } else if (data.status === '2fa_required') {
        document.getElementById('twofa').style.display = 'block';
        statusEl.textContent = 'Требуется пароль двухэтапной аутентификации';
      } else if (data.status === 'done') {
        statusEl.innerHTML = '<span class="ok">Готово! Сессия авторизована.</span>';
        clearInterval(timer);
      } else if (data.status === 'expired') {
        statusEl.innerHTML = '<span class="warn">QR истёк. Обновите страницу для новой попытки.</span>';
        clearInterval(timer);
      } else if (data.status === 'error') {
        statusEl.innerHTML = '<span class="err">Ошибка: '+(data.error || 'unknown')+'</span>';
        clearInterval(timer);
      } else if (data.status === 'init') {
        statusEl.textContent = 'Подключение к Telegram…';
      }
    }

    async function send2fa() {
      const pwd = (document.getElementById('pwd').value || '').trim();
      if (!pwd) return;
      const resp = await fetch('/auth/qr/2fa', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({sid, password: pwd})});
      const data = await resp.json();
      const twofaStatus = document.getElementById('twofa_status');
      if (data.ok) {
        document.getElementById('status').innerHTML = '<span class="ok">Готово! Сессия авторизована.</span>';
        twofaStatus.textContent = '';
        clearInterval(timer);
      } else {
        twofaStatus.textContent = data.error || 'Неверный пароль или другая ошибка';
      }
    }

    window.onload = start;
  </script>
</body>
</html>
"""


AUTH_HTML = """
<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Авторизация Telegram — диагностика и вход</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#0b1220; color:#e7ecf3; margin:0; padding:24px; }
    .wrap { max-width: 920px; margin: 0 auto; }
    h1 { margin: 0 0 12px; font-size: 24px; }
    h2 { margin: 20px 0 8px; font-size: 18px; }
    .card { background:#111a2b; border:1px solid #22304a; border-radius:16px; padding:20px; margin:16px 0; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
    .row { display:flex; gap:12px; align-items:center; }
    .muted { color:#9fb3c8; font-size:14px; }
    .ok { color:#7ce38b; }
    .err { color:#ff6b6b; }
    .warn { color:#ffcc66; }
    input[type=text], input[type=number], input[type=password] { width:100%; padding:10px 12px; border-radius:8px; border:1px solid #2b3b58; background:#0b1220; color:#e7ecf3; }
    button { padding:10px 14px; border-radius:8px; border:1px solid #2b3b58; background:#1a2740; color:#e7ecf3; cursor:pointer; }
    button:hover { background:#223556; }
    a { color:#5cc8ff; text-decoration:none; }
    .kv { display:grid; grid-template-columns: 220px 1fr; gap:8px; align-items:center; }
    code { background:#0b1220; padding:2px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Авторизация Telegram</h1>
    <div class=\"card\">
      <div class=\"muted\">На этой странице собраны все данные, используемые для генерации и авторизации (API, телефон и др.). Здесь же можно выбрать способ входа: по QR или по коду из Telegram.</div>
    </div>

    <div class=\"grid\">
      <div class=\"card\">
        <h2>Данные и статус</h2>
        <div id=\"diag\" class=\"kv\">
          <div>API ID</div><div id=\"api_id\">—</div>
          <div>API HASH</div><div id=\"api_hash\">—</div>
          <div>Телефон</div><div id=\"phone_label\">—</div>
          <div>Telethon</div><div id=\"ver\">—</div>
          <div>Клиент</div><div id=\"conn\">—</div>
          <div>Авторизация</div><div id=\"auth\">—</div>
          <div>Файл сессии</div><div id=\"sess\">—</div>
          <div>QR timeout</div><div id=\"qt\">—</div>
          <div>QR attempts</div><div id=\"qa\">—</div>
        </div>
        <div style=\"margin-top:8px\" class=\"muted\">Дополнительно: <a href=\"/auth/qr/debug\" target=\"_blank\">/auth/qr/debug</a> · <a href=\"/auth/qr\">войти по QR</a></div>
      </div>

      <div class=\"card\">
        <h2>Вход по коду</h2>
        <div class=\"muted\">Отправим код в Telegram и подтвердим его тут. При включённой 2FA потребуется пароль.</div>
        <div class=\"row\" style=\"margin:8px 0;\">
          <input id=\"phone\" type=\"text\" placeholder=\"Телефон, напр. +79990000000\" />
          <button onclick=\"sendCode()\">Отправить код</button>
        </div>
        <div id=\"send_status\" class=\"muted\"></div>
        <div id=\"code_block\" style=\"display:none;\">
          <div class=\"row\" style=\"margin:8px 0;\">
            <input id=\"code\" type=\"text\" placeholder=\"Код из Telegram\" />
            <button onclick=\"verifyCode()\">Подтвердить</button>
          </div>
          <div id=\"verify_status\" class=\"muted\"></div>
        </div>
        <div id=\"twofa_block\" style=\"display:none;\">
          <div class=\"row\" style=\"margin:8px 0;\">
            <input id=\"pwd\" type=\"password\" placeholder=\"Пароль 2FA\" />
            <button onclick=\"send2FA()\">Отправить</button>
          </div>
          <div id=\"twofa_status\" class=\"muted\"></div>
        </div>
      </div>
    </div>
  </div>
  <script>
    let codeSid = null;
    async function loadDiag() {
      try {
        const r = await fetch('/auth/debug');
        const d = await r.json();
        document.getElementById('api_id').textContent = d.api_id ?? '—';
        document.getElementById('api_hash').textContent = d.api_hash_masked ?? '—';
        document.getElementById('phone').value = d.phone || '';
        document.getElementById('phone_label').textContent = d.phone_masked || '—';
        document.getElementById('ver').textContent = d.telethon_version ?? '—';
        document.getElementById('conn').textContent = d.client_connected ? 'подключён' : 'отключён';
        document.getElementById('auth').textContent = d.authorized ? 'авторизован' : 'не авторизован';
        document.getElementById('sess').textContent = d.session_exists ? d.session_file : '(нет)';
        document.getElementById('qt').textContent = d.qr_timeout ?? '-';
        document.getElementById('qa').textContent = d.qr_max_attempts ?? '-';
      } catch (e) { console.error(e); }
    }
    async function sendCode() {
      const phone = (document.getElementById('phone').value || '').trim();
      const r = await fetch('/auth/code/send', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({phone})});
      const d = await r.json();
      const el = document.getElementById('send_status');
      if (d.ok) {
        codeSid = d.sid;
        el.textContent = 'Код отправлен. Проверьте Telegram и введите код ниже.';
        document.getElementById('code_block').style.display = 'block';
      } else {
        el.textContent = 'Ошибка: ' + (d.error || 'send_code_failed');
      }
    }
    async function verifyCode() {
      const code = (document.getElementById('code').value || '').trim();
      const r = await fetch('/auth/code/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({sid: codeSid, code})});
      const d = await r.json();
      const el = document.getElementById('verify_status');
      if (d.ok) {
        el.textContent = 'Готово! Сессия авторизована.';
        document.getElementById('twofa_block').style.display = 'none';
      } else if (d.twofa_required) {
        el.textContent = 'Требуется пароль 2FA.';
        document.getElementById('twofa_block').style.display = 'block';
      } else {
        el.textContent = 'Ошибка: ' + (d.error || 'verify_failed');
      }
    }
    async function send2FA() {
      const password = (document.getElementById('pwd').value || '').trim();
      const r = await fetch('/auth/code/2fa', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({sid: codeSid, password})});
      const d = await r.json();
      const el = document.getElementById('twofa_status');
      if (d.ok) {
        el.textContent = 'Готово! Сессия авторизована.';
      } else {
        el.textContent = 'Ошибка: ' + (d.error || '2fa_failed');
      }
    }
    window.onload = loadDiag;
  </script>
</body>
</html>
"""


# @app.get("/auth", response_class=HTMLResponse)
# async def auth_page():
#     return HTMLResponse(AUTH_HTML)


# @app.get("/auth/qr", response_class=HTMLResponse)
async def auth_qr_page():
    return HTMLResponse(QR_HTML)


# @app.post("/auth/qr/start")
async def auth_qr_start():
    sid = secrets.token_urlsafe(12)
    _qr_sessions[sid] = {"status": "init"}
    asyncio.create_task(_qr_runner(sid))
    return JSONResponse({"sid": sid})


# @app.get("/auth/qr/status")
async def auth_qr_status(sid: str):
    sess = _qr_sessions.get(sid)
    if not sess:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({
        "sid": sid,
        "status": sess.get("status"),
        "url": sess.get("url"),
        "attempt": sess.get("attempt")
    })


# @app.post("/auth/qr/2fa")
async def auth_qr_2fa(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    sid = (body or {}).get("sid")
    password = (body or {}).get("password")
    sess = _qr_sessions.get(str(sid)) if sid else None
    if not sess:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
    if not password:
        return JSONResponse({"ok": False, "error": "password_required"}, status_code=400)
    try:
        await _ensure_client_connected()
        await monitor.client.sign_in(password=password)
        monitor._authorized = True
        sess.update({"status": "done", "authorized": True})
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception("2FA sign_in failed: %s", e)
        return JSONResponse({"ok": False, "error": "2fa_failed"}, status_code=400)


# ===== CODE AUTH API =====
# @app.post("/auth/code/send")
async def auth_code_send(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    phone = (body or {}).get("phone") or settings.PHONE_NUMBER
    if not phone:
        return JSONResponse({"ok": False, "error": "phone_required"}, status_code=400)
    try:
        await _ensure_client_connected()
        result = await monitor.client.send_code_request(phone)
        sid = secrets.token_urlsafe(12)
        _code_sessions[sid] = {
            "status": "code_sent",
            "phone": phone,
            "phone_code_hash": getattr(result, 'phone_code_hash', None),
        }
        logger.info("Code auth started for %s (sid %s)", _mask_phone(phone), sid)
        return JSONResponse({"ok": True, "sid": sid})
    except Exception as e:
        logger.exception("send_code_request failed: %s", e)
        return JSONResponse({"ok": False, "error": "send_code_failed"}, status_code=400)


# @app.post("/auth/code/verify")
async def auth_code_verify(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    sid = (body or {}).get("sid")
    code = (body or {}).get("code")
    sess = _code_sessions.get(str(sid)) if sid else None
    if not sess:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
    if not code:
        return JSONResponse({"ok": False, "error": "code_required"}, status_code=400)
    try:
        await _ensure_client_connected()
        try:
            await monitor.client.sign_in(phone=sess["phone"], code=code)
        except SessionPasswordNeededError:
            sess.update({"status": "2fa_required"})
            return JSONResponse({"ok": False, "twofa_required": True})
        monitor._authorized = True
        sess.update({"status": "done"})
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception("code sign_in failed: %s", e)
        return JSONResponse({"ok": False, "error": "verify_failed"}, status_code=400)


# @app.post("/auth/code/2fa")
async def auth_code_2fa(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    sid = (body or {}).get("sid")
    password = (body or {}).get("password")
    sess = _code_sessions.get(str(sid)) if sid else None
    if not sess:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
    if not password:
        return JSONResponse({"ok": False, "error": "password_required"}, status_code=400)
    try:
        await _ensure_client_connected()
        await monitor.client.sign_in(password=password)
        monitor._authorized = True
        sess.update({"status": "done"})
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception("code 2FA sign_in failed: %s", e)
        return JSONResponse({"ok": False, "error": "2fa_failed"}, status_code=400)


# ===== Diagnostics =====
# @app.get("/auth/debug")
async def auth_debug():
    try:
        connected = monitor.client.is_connected()
    except Exception:
        connected = False
    try:
        authorized = await monitor.client.is_user_authorized()
    except Exception:
        authorized = False
    session_file = os.path.join(settings.SESSIONS_DIR, "mtproto.session")
    return JSONResponse({
        "api_id": settings.API_ID,
        "api_hash_masked": _mask_value(settings.API_HASH, keep=3),
        "phone": settings.PHONE_NUMBER,
        "phone_masked": _mask_phone(settings.PHONE_NUMBER),
        "telethon_version": telethon_version,
        "client_connected": connected,
        "authorized": authorized,
        "session_file": session_file,
        "session_exists": os.path.exists(session_file),
        "qr_timeout": QR_PER_TOKEN_TIMEOUT,
        "qr_max_attempts": QR_MAX_ATTEMPTS,
    })


# @app.get("/auth/qr/debug")
async def auth_qr_debug():
    try:
        connected = monitor.client.is_connected()
    except Exception:
        connected = False
    session_path = os.path.join(settings.SESSIONS_DIR, "mtproto.session")
    return JSONResponse({
        "api_id_present": bool(settings.API_ID),
        "api_hash_present": bool(settings.API_HASH),
        "client_connected": connected,
        "session_dir": settings.SESSIONS_DIR,
        "session_file_exists": os.path.exists(session_path),
        "qr_sessions_active": len(_qr_sessions),
        "qr_timeout": QR_PER_TOKEN_TIMEOUT,
        "qr_max_attempts": QR_MAX_ATTEMPTS,
    })
from __future__ import annotations
import json, os, re, shutil, threading, urllib.request, urllib.parse, urllib.error, webbrowser, secrets, hashlib
from datetime import date, datetime, timedelta, timezone
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for, session, Response
import core
import finance

BASE=os.path.dirname(os.path.abspath(__file__))
DATA_DIR=os.environ.get('PIPI_DATA_DIR', BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB=os.path.join(DATA_DIR,core.DB_NAME); core.init_db(DB)
_tmp=core.connect(DB); finance.init_db(_tmp); _tmp.close()
app=Flask(__name__)
# Cloud authentication supports either Railway environment variables or a persistent
# password configured once from the web UI and stored as a salted hash in /data.
PIPI_CLOUD=(os.environ.get('PIPI_CLOUD','0')=='1' or bool(os.environ.get('RAILWAY_ENVIRONMENT')) or bool(os.environ.get('RAILWAY_SERVICE_NAME')))
ENV_PASSWORD=(os.environ.get('PIPI_PASSWORD','').strip() or os.environ.get('APP_PASSWORD','').strip())
ENV_PASSWORD_SOURCE='PIPI_PASSWORD' if os.environ.get('PIPI_PASSWORD','').strip() else ('APP_PASSWORD' if os.environ.get('APP_PASSWORD','').strip() else '')
AUTH_FILE=os.path.join(DATA_DIR,'pipi_auth.json')

def _load_file_auth():
    try:
        with open(AUTH_FILE,'r',encoding='utf-8') as fp:
            obj=json.load(fp)
        if obj.get('salt') and obj.get('password_hash') and obj.get('session_secret'):
            return obj
    except Exception:
        pass
    return None

FILE_AUTH=_load_file_auth()
AUTH_CONFIGURED=bool(ENV_PASSWORD or FILE_AUTH)
PIPI_PASSWORD_SOURCE=ENV_PASSWORD_SOURCE or ('DATA_VOLUME' if FILE_AUTH else '')

def _verify_password(candidate: str) -> bool:
    if ENV_PASSWORD:
        return secrets.compare_digest(candidate, ENV_PASSWORD)
    if FILE_AUTH:
        try:
            salt=bytes.fromhex(FILE_AUTH['salt'])
            test=hashlib.pbkdf2_hmac('sha256',candidate.encode('utf-8'),salt,260000).hex()
            return secrets.compare_digest(test,FILE_AUTH['password_hash'])
        except Exception:
            return False
    return False

def _save_password_to_volume(password: str):
    global FILE_AUTH, AUTH_CONFIGURED, PIPI_PASSWORD_SOURCE, AUTH_VERSION
    salt=secrets.token_bytes(16)
    obj={
        'salt':salt.hex(),
        'password_hash':hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,260000).hex(),
        'session_secret':secrets.token_hex(32),
        'created_at':datetime.now(timezone.utc).isoformat(),
    }
    tmp=AUTH_FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as fp:
        json.dump(obj,fp,ensure_ascii=False)
    os.replace(tmp,AUTH_FILE)
    FILE_AUTH=obj
    AUTH_CONFIGURED=True
    PIPI_PASSWORD_SOURCE='DATA_VOLUME'
    AUTH_VERSION=obj['password_hash'][:16]
    app.secret_key=obj['session_secret']

app=Flask(__name__)
_secret=os.environ.get('PIPI_SECRET_KEY','').strip()
if not _secret:
    if FILE_AUTH:
        _secret=FILE_AUTH['session_secret']
    elif ENV_PASSWORD:
        _secret=hashlib.sha256(ENV_PASSWORD.encode('utf-8')+b'|session-key').hexdigest()
    else:
        # Temporary only until the first password is configured.
        _secret=hashlib.sha256(b'pipi-invest-v4.3-first-setup').hexdigest()
app.secret_key=_secret
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=(PIPI_CLOUD or os.environ.get('PIPI_HTTPS','0')=='1'),
)
if ENV_PASSWORD:
    AUTH_VERSION=hashlib.sha256(ENV_PASSWORD.encode('utf-8')).hexdigest()[:16]
elif FILE_AUTH:
    AUTH_VERSION=FILE_AUTH['password_hash'][:16]
else:
    AUTH_VERSION=''

# Safe startup diagnostics: never print any password value.
print(
    '[PIPI AUTH] '+
    f'cloud={"ON" if PIPI_CLOUD else "OFF"} '+
    f'auth={"SET" if AUTH_CONFIGURED else "MISSING"} '+
    f'source={PIPI_PASSWORD_SOURCE or "NONE"} '+
    f'data_dir={DATA_DIR}',
    flush=True,
)

PID_FILE=os.path.join(BASE,'vr7.pid')

# Safe startup diagnostics: never print the password value.
print(
    '[PIPI AUTH] '+
    f'cloud={"ON" if PIPI_CLOUD else "OFF"} '+
    f'password={"SET" if PIPI_PASSWORD else "MISSING"} '+
    f'source={PIPI_PASSWORD_SOURCE or "NONE"} '+
    f'length={len(PIPI_PASSWORD)} '+
    f'data_dir={DATA_DIR}',
    flush=True,
)

@app.get('/auth-status')
def auth_status():
    return jsonify({
        'cloud': bool(PIPI_CLOUD),
        'password_status': 'SET' if AUTH_CONFIGURED else 'MISSING',
        'password_source': PIPI_PASSWORD_SOURCE or 'NONE',
        'data_dir': DATA_DIR,
        'auth_file_exists': os.path.exists(AUTH_FILE),
        'railway_service_detected': bool(os.environ.get('RAILWAY_SERVICE_NAME')),
        'version': '4.3',
    })

@app.before_request
def _auth_gate():
    if request.endpoint in {'login','setup_password','manifest','service_worker','auth_status'} or request.path.startswith('/static/'):
        return None
    if PIPI_CLOUD and not AUTH_CONFIGURED:
        return redirect(url_for('setup_password'))
    if not AUTH_CONFIGURED:
        return None
    if session.get('pipi_auth') is True and session.get('auth_version') == AUTH_VERSION:
        return None
    session.clear()
    next_url=request.full_path if request.query_string else request.path
    return redirect(url_for('login', next=next_url))

@app.route('/setup-password',methods=['GET','POST'])
def setup_password():
    if AUTH_CONFIGURED:
        return redirect(url_for('login'))
    if not PIPI_CLOUD:
        return redirect(url_for('dashboard_page'))
    if request.method=='POST':
        pw=request.form.get('password','')
        pw2=request.form.get('password_confirm','')
        if len(pw)<6:
            flash('비밀번호는 6자 이상으로 설정해 주세요.','err')
        elif pw!=pw2:
            flash('비밀번호 확인이 일치하지 않습니다.','err')
        else:
            try:
                _save_password_to_volume(pw)
                session.clear()
                flash('로그인 비밀번호가 설정되었습니다.','ok')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'비밀번호 저장 실패: {e}','err')
    return render_template('setup_password.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if PIPI_CLOUD and not AUTH_CONFIGURED:
        return redirect(url_for('setup_password'))
    if not AUTH_CONFIGURED:
        return redirect(url_for('dashboard_page'))
    if request.method=='POST':
        pw=request.form.get('password','')
        if _verify_password(pw):
            session.clear()
            session['pipi_auth']=True
            session['auth_version']=AUTH_VERSION
            nxt=request.args.get('next') or url_for('dashboard_page')
            if not nxt.startswith('/') or nxt.startswith('//'):
                nxt=url_for('dashboard_page')
            return redirect(nxt)
        flash('비밀번호가 맞지 않습니다.','err')
    return render_template('login.html')

@app.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.get('/manifest.webmanifest')
def manifest():
    return send_file(os.path.join(BASE,'static','manifest.webmanifest'), mimetype='application/manifest+json')

@app.get('/sw.js')
def service_worker():
    # Root scope is required so the installed PWA controls every page.
    resp=send_file(os.path.join(BASE,'static','sw.js'), mimetype='application/javascript')
    resp.headers['Service-Worker-Allowed']='/'
    resp.headers['Cache-Control']='no-cache'
    return resp

def _write_pid_file():
    try:
        with open(PID_FILE,'w',encoding='ascii') as fp:
            fp.write(str(os.getpid()))
    except Exception:
        pass

def _remove_pid_file():
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE,'r',encoding='ascii') as fp:
                saved=fp.read().strip()
            if saved==str(os.getpid()):
                os.remove(PID_FILE)
    except Exception:
        pass
def db(): return core.connect(DB)
def f(name, default=None):
    x=request.form.get(name,'').strip()
    return default if x=='' else float(x)



def _num(text):
    return float(str(text).replace(',', '').replace('원','').replace('주','').strip())

def _nh_trade_date(raw_date: str):
    m=re.search(r'(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일', raw_date or '')
    if not m: raise ValueError('주문일자를 읽지 못했습니다.')
    y=int(m.group(1)) if m.group(1) else date.today().year
    mo=int(m.group(2)); d=int(m.group(3))
    candidate=date(y,mo,d)
    # Year omitted in broker texts. Around New Year, choose the sensible previous year.
    if not m.group(1) and candidate > date.today()+timedelta(days=45):
        candidate=date(y-1,mo,d)
    return candidate.isoformat()

def parse_nh_trade_message(text: str):
    text=(text or '').strip()
    if not text: raise ValueError('NH 체결문자를 붙여넣어 주세요.')
    def grab(pattern, label, flags=0):
        m=re.search(pattern,text,flags)
        if not m: raise ValueError(f'{label} 항목을 찾지 못했습니다.')
        return m.group(1).strip()
    kind=grab(r'주문종류\s*:\s*(매수|매도)', '주문종류')
    date_text=grab(r'주문일자\s*:\s*([^\r\n]+)', '주문일자')
    order_no=grab(r'주문번호\s*:\s*([0-9]+)', '주문번호')
    name=grab(r'종목명\s*:\s*([^\r\n]+)', '종목명')
    order_amount_text=grab(r'주문금액\s*:\s*([0-9,]+)원', '주문금액')
    fill=re.search(r'체결금액\(수량\)\s*:\s*([0-9,]+)원\s*\(\s*([0-9.]+)주\s*\)',text)
    if not fill: raise ValueError('체결금액(수량) 항목을 찾지 못했습니다.')
    price_text=grab(r'체결가격\s*:\s*([0-9,]+(?:\.[0-9]+)?)', '체결가격')
    clean_name=re.sub(r'\s*소수점\s*$', '', name).strip()
    alias_symbol=None; alias_name=clean_name
    if '현대자동차2우' in clean_name or '현대차2우' in clean_name:
        alias_symbol='005387'; alias_name='현대차2우B'
    return {
        'side':'BUY' if kind=='매수' else 'SELL',
        'side_label':kind,
        'trade_date':_nh_trade_date(date_text),
        'order_no':order_no,
        'raw_name':name,
        'name':alias_name,
        'symbol_hint':alias_symbol,
        'order_amount':_num(order_amount_text),
        'fill_amount':_num(fill.group(1)),
        'qty':_num(fill.group(2)),
        'price':_num(price_text),
    }

def match_nh_security(con, parsed):
    if parsed.get('symbol_hint'):
        row=con.execute('SELECT * FROM securities WHERE upper(symbol)=? ORDER BY id LIMIT 1',(parsed['symbol_hint'].upper(),)).fetchone()
        if row: return row['id']
    target=re.sub(r'[^0-9A-Za-z가-힣]','',parsed.get('name','')).replace('현대자동차','현대차')
    for row in con.execute('SELECT * FROM securities ORDER BY id'):
        nm=re.sub(r'[^0-9A-Za-z가-힣]','',row['name']).replace('현대자동차','현대차').replace('소수점','')
        if nm==target or target in nm or nm in target:
            return row['id']
    return None


def _parse_ymd(text: str):
    m=re.search(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})', text or '')
    if not m: raise ValueError('날짜를 읽지 못했습니다.')
    return date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()

def parse_nh_dividend_message(text: str):
    text=(text or '').strip()
    if not text: raise ValueError('NH 배당 안내 문자를 붙여넣어 주세요.')
    # 국내 배당금 입금 안내
    if '배당금 입금 안내' in text and '세전금액' in text and '입금일' in text:
        def grab(pattern,label):
            m=re.search(pattern,text,re.M)
            if not m: raise ValueError(f'{label} 항목을 찾지 못했습니다.')
            return m.group(1).strip()
        raw_name=grab(r'종목명\s*:\s*([^\r\n]+)','종목명')
        base_date=_parse_ymd(grab(r'기준일\s*:\s*([^\r\n]+)','기준일'))
        pay_date=_parse_ymd(grab(r'입금일\s*:\s*([^\r\n]+)','입금일'))
        gross=_num(grab(r'세전금액\s*:\s*([0-9,]+)원','세전금액'))
        net=_num(grab(r'세후금액\s*:\s*([0-9,]+)원','세후금액'))
        tax=_num(grab(r'세금합계\s*:\s*([0-9,]+)원','세금합계'))
        clean_name=raw_name.strip()
        symbol_hint=None; name=clean_name
        if '현대자동차2우선주' in clean_name or '현대자동차2우' in clean_name or '현대차2우' in clean_name:
            symbol_hint='005387'; name='현대차2우B'
        key=f"KR|{symbol_hint or name}|{base_date}|{pay_date}|{gross:.4f}|{net:.4f}"
        return {'kind':'KR','kind_label':'국내주식 배당','currency':'KRW','raw_name':raw_name,'name':name,'symbol_hint':symbol_hint,
                'base_date':base_date,'pay_date':pay_date,'gross':gross,'tax':tax,'net':net,'fee':0.0,'source_key':key,
                'extra_note':f'기준일 {base_date}'}
    # 해외증권 권리발생 안내
    if '해외증권 권리발생 안내' in text and '권리유형' in text:
        rights=re.search(r'권리유형\s*:\s*([^\r\n]+)',text)
        if not rights or '배당' not in rights.group(1):
            raise ValueError('배당 권리 안내가 아닙니다.')
        m=re.search(r'종목\s*:\s*\[([^\]]+)\]\s*([^\r\n]+)',text)
        if not m: raise ValueError('해외 종목 항목을 찾지 못했습니다.')
        symbol=m.group(1).strip().upper(); raw_name=m.group(2).strip()
        def val(label, pattern=r'([0-9,.]+)'):
            mm=re.search(re.escape(label)+r'\s*:\s*'+pattern,text)
            if not mm: raise ValueError(f'{label} 항목을 찾지 못했습니다.')
            return mm.group(1).strip()
        currency=val('통화코드',r'([A-Za-z]+)').upper()
        gross=_num(val('외화배정금액'))
        foreign_tax=_num(val('외화세액'))
        fee=_num(val('수수료'))
        net=_num(val('외화실지급액'))
        krw_tax=_num(val('원화세액',r'([0-9,]+)원'))
        pay_date=date.today().isoformat()
        key=f"US|{symbol}|{pay_date}|{gross:.6f}|{net:.6f}|{foreign_tax:.6f}|{fee:.6f}"
        return {'kind':'US','kind_label':'해외주식 배당','currency':currency,'raw_name':raw_name,'name':raw_name,'symbol_hint':symbol,
                'base_date':'','pay_date':pay_date,'gross':gross,'tax':foreign_tax,'net':net,'fee':fee,'krw_tax':krw_tax,'source_key':key,
                'extra_note':f'원화세액 {krw_tax:,.0f}원 / 수수료 {fee:.4f}{currency}'}
    raise ValueError('지원하는 NH 국내/해외 배당 안내 형식을 찾지 못했습니다.')

def get_tqqq_close(target_date: str):
    """Return (close, actual_market_date). Falls back to the latest trading day on/before target_date."""
    d=date.fromisoformat(target_date)
    start=d-timedelta(days=7)
    end=d+timedelta(days=2)
    p1=int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    p2=int(datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    url=(f'https://query1.finance.yahoo.com/v8/finance/chart/TQQQ?period1={p1}&period2={p2}'
         '&interval=1d&events=history&includeAdjustedClose=true')
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=8) as r:
        obj=json.loads(r.read().decode())
    result=(obj.get('chart',{}).get('result') or [None])[0]
    if not result:
        raise ValueError('TQQQ 종가를 조회하지 못했습니다.')
    timestamps=result.get('timestamp') or []
    closes=((result.get('indicators',{}).get('quote') or [{}])[0].get('close') or [])
    candidates=[]
    for ts, close in zip(timestamps, closes):
        if close is None: continue
        md=datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if md <= d:
            candidates.append((md,float(close)))
    if not candidates:
        raise ValueError('해당 기준일 이전의 TQQQ 종가를 찾지 못했습니다.')
    md, close=max(candidates,key=lambda x:x[0])
    return round(close,4), md.isoformat()



def _quote_candidates(sec):
    """Return likely Yahoo symbols in preferred order.

    Korean securities need an exchange suffix on Yahoo.  If the user already
    stored a quote_symbol we always try that first, then sensible fallbacks.
    """
    raw=(sec['symbol'] or '').strip().upper()
    quote=(sec['quote_symbol'] or '').strip().upper()
    market=(sec['market'] or '').strip().upper()
    out=[]
    def add(x):
        x=(x or '').strip().upper()
        if x and x not in out: out.append(x)
    add(quote)
    if market=='KR' or (raw.isdigit() and len(raw)==6):
        # KOSPI first, then KOSDAQ.  The raw symbol is a last-resort fallback.
        if raw:
            add(raw+'.KS')
            add(raw+'.KQ')
            add(raw)
    else:
        add(raw)
    return out

def _fetch_yahoo_chart(symbol: str):
    q=urllib.parse.quote(symbol, safe='')
    last_error=None
    # Yahoo occasionally returns a transient 404/crumb-style error on one host.
    # Try both chart hosts before giving up.
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        url=f'https://{host}/v8/finance/chart/{q}?range=5d&interval=1d&includePrePost=false&events=div%2Csplits'
        req=urllib.request.Request(url,headers={
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36',
            'Accept':'application/json,text/plain,*/*',
            'Referer':'https://finance.yahoo.com/'
        })
        try:
            with urllib.request.urlopen(req,timeout=10) as r:
                obj=json.loads(r.read().decode('utf-8'))
            result=(obj.get('chart',{}).get('result') or [None])[0]
            if not result:
                last_error='조회 결과 없음'
                continue
            meta=result.get('meta',{}) or {}
            price=meta.get('regularMarketPrice')
            if price is None:
                closes=((result.get('indicators',{}).get('quote') or [{}])[0].get('close') or [])
                price=next((x for x in reversed(closes) if x is not None),None)
            if price is not None:
                return round(float(price),4)
            last_error='가격 데이터 없음'
        except urllib.error.HTTPError as e:
            last_error=f'HTTP {e.code}'
        except Exception as e:
            last_error=type(e).__name__
    raise ValueError(f'{symbol} 조회 실패 ({last_error or "응답 없음"})')

def get_yahoo_latest_for_security(sec):
    candidates=_quote_candidates(sec)
    if not candidates:
        raise ValueError('자동조회 심볼이 없습니다.')
    errors=[]
    for symbol in candidates:
        try:
            return _fetch_yahoo_chart(symbol), symbol
        except Exception as e:
            errors.append(f'{symbol}: {e}')
    tried=', '.join(candidates)
    raise ValueError(f'현재가 자동조회 실패. 조회심볼을 확인해 주세요. (시도: {tried})')

@app.get('/dashboard')
def dashboard_page():
    con=db()
    try:
        fs=finance.finance_settings(con)
        # First dashboard visit: try to seed a live FX rate once. Failure is harmless.
        if fs and not fs['fx_updated_at']:
            try:
                finance.save_usd_krw(con,_fetch_yahoo_chart('USDKRW=X'))
            except Exception:
                pass
        return render_template('dashboard.html',**finance.asset_dashboard(con))
    finally:
        con.close()

@app.post('/dashboard/fx')
def dashboard_fx():
    con=db()
    try:
        finance.save_usd_krw(con,f('usd_krw'))
        flash('USD/KRW 환율을 적용했습니다.','ok')
    except Exception as e:
        flash(str(e),'err')
    finally:
        con.close()
    return redirect(url_for('dashboard_page'))

@app.post('/dashboard/fx/refresh')
def dashboard_fx_refresh():
    con=db()
    try:
        rate=_fetch_yahoo_chart('USDKRW=X')
        finance.save_usd_krw(con,rate)
        flash(f'USD/KRW 환율 {rate:,.2f}원을 자동 반영했습니다.','ok')
    except Exception as e:
        flash(f'환율 자동조회 실패: {e}','err')
    finally:
        con.close()
    return redirect(url_for('dashboard_page'))

@app.get('/')
def index():
    con=db()
    try: return render_template('index.html',**core.dashboard(con))
    finally: con.close()

@app.route('/settings',methods=['GET','POST'])
def settings():
    con=db()
    try:
        s=core.settings(con)
        if request.method=='POST':
            d={'start_date':request.form['start_date'],'initial_pool':f('initial_pool',100),'initial_shares':f('initial_shares',0),'initial_net_trade_cost':f('initial_net_trade_cost',0),'initial_invested':f('initial_invested',100),'contribution':f('contribution',100),'interval_days':int(f('interval_days',14)),'default_g':f('default_g',10),'lower_mult':f('lower_mult',0.85),'upper_mult':f('upper_mult',1.15),'plan_start_date':request.form.get('plan_start_date') or request.form['start_date'],'plan_end_week':int(f('plan_end_week',269))}
            core.save_settings(con,d); flash('설정을 저장하고 전체 주차를 다시 계산했습니다.','ok'); return redirect(url_for('index'))
        return render_template('settings.html',s=s)
    except Exception as e: flash(str(e),'err'); return redirect(url_for('settings'))
    finally: con.close()

@app.post('/cycle/add')
def cycle_add():
    con=db()
    try:
        close_date=request.form['close_date']; price=f('close_price')
        if price is None: price,_=get_tqqq_close(close_date)
        core.add_cycle(con,int(f('week_no',0)),close_date,f('v_value'),f('g_value'),price,f('v_min'),f('v_max'),f('dividend',0),f('contribution'),request.form.get('note','').strip())
        flash('주차를 저장했습니다. 이제 이 주차에 실제 매매를 입력하면 POOL/평가금/다음 V가 자동 재계산됩니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('index'))

@app.route('/cycle/<int:cid>/edit',methods=['GET','POST'])
def cycle_edit(cid):
    con=db()
    try:
        c=con.execute('SELECT * FROM cycles WHERE id=?',(cid,)).fetchone()
        if not c: return redirect(url_for('index'))
        if request.method=='POST':
            close_date=request.form['close_date']; price=f('close_price')
            if price is None: price,_=get_tqqq_close(close_date)
            core.edit_cycle(con,cid,week_no=int(f('week_no',0)),close_date=close_date,v_value=f('v_value'),g_value=f('g_value'),close_price=price,v_min=request.form.get('v_min','').strip(),v_max=request.form.get('v_max','').strip(),dividend=f('dividend',0),contribution=f('contribution',100),note=request.form.get('note','').strip())
            flash('주차를 수정했습니다.','ok'); return redirect(url_for('index'))
        return render_template('cycle_edit.html',c=c)
    except Exception as e: flash(str(e),'err'); return redirect(url_for('index'))
    finally: con.close()

@app.post('/cycle/<int:cid>/delete')
def cycle_delete(cid):
    con=db()
    try: core.delete_cycle(con,cid); flash('주차를 삭제했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('index'))

@app.post('/trade/add')
def trade_add():
    con=db()
    try: core.add_trade(con,int(request.form['cycle_id']),request.form['side'],f('qty'),f('price'),f('fee',0),request.form.get('note','').strip()); flash('매매를 반영했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('index'))

@app.route('/trade/<int:tid>/edit',methods=['GET','POST'])
def trade_edit(tid):
    con=db()
    try:
        t=con.execute('SELECT t.*,c.week_no FROM trades t JOIN cycles c ON c.id=t.cycle_id WHERE t.id=?',(tid,)).fetchone()
        if not t: return redirect(url_for('index'))
        if request.method=='POST': core.edit_trade(con,tid,request.form['side'],f('qty'),f('price'),f('fee',0),request.form.get('note','').strip()); flash('매매를 수정했습니다.','ok'); return redirect(url_for('index'))
        return render_template('trade_edit.html',t=t)
    except Exception as e: flash(str(e),'err'); return redirect(url_for('index'))
    finally: con.close()

@app.post('/trade/<int:tid>/delete')
def trade_delete(tid):
    con=db()
    try: core.delete_trade(con,tid); flash('매매를 삭제했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('index'))

@app.get('/api/quote')
def quote():
    try:
        target=(request.args.get('date') or '').strip()
        if target:
            price, actual_date=get_tqqq_close(target)
            return jsonify(ok=True,price=price,actual_date=actual_date,requested_date=target)
        req=urllib.request.Request('https://query1.finance.yahoo.com/v8/finance/chart/TQQQ?range=5d&interval=1d',headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=8) as r: obj=json.loads(r.read().decode())
        result=obj['chart']['result'][0]; price=result.get('meta',{}).get('regularMarketPrice')
        if not price:
            price=next(x for x in reversed(result['indicators']['quote'][0]['close']) if x is not None)
        return jsonify(ok=True,price=round(float(price),4),actual_date=None)
    except Exception as e:
        return jsonify(ok=False,error=f'TQQQ 종가 자동조회 실패: {e}'),500

@app.get('/backup')
def backup():
    p=os.path.join(DATA_DIR,'vr7_backup.db')
    shutil.copy2(DB,p)
    return send_file(p,as_attachment=True,download_name='vr7_backup.db')

@app.route('/restore', methods=['GET','POST'])
def restore_db():
    if request.method=='GET':
        return render_template('restore.html')
    up=request.files.get('db_file')
    if not up or not up.filename:
        flash('복원할 vr7.db 파일을 선택해 주세요.','err')
        return redirect(url_for('restore_db'))
    if not up.filename.lower().endswith('.db'):
        flash('DB 파일(.db)만 복원할 수 있습니다.','err')
        return redirect(url_for('restore_db'))
    tmp=os.path.join(DATA_DIR,'vr7_restore_upload.tmp')
    safety=os.path.join(DATA_DIR,'vr7_before_restore.db')
    try:
        up.save(tmp)
        import sqlite3
        test=sqlite3.connect(tmp)
        required={'settings','cycles','trades'}
        tables={r[0] for r in test.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        test.close()
        if not required.issubset(tables):
            raise ValueError('PIPI VR7 DB 형식이 아닙니다.')
        if os.path.exists(DB):
            shutil.copy2(DB,safety)
        os.replace(tmp,DB)
        core.init_db(DB)
        con=core.connect(DB); finance.init_db(con); con.close()
        flash('DB 복원이 완료되었습니다. 기존 클라우드 DB는 vr7_before_restore.db로 백업했습니다.','ok')
        return redirect(url_for('dashboard_page'))
    except Exception as e:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception: pass
        flash(f'DB 복원 실패: {e}','err')
        return redirect(url_for('restore_db'))


def _render_portfolio(con, nh_preview=None, nh_raw=''):
    data=finance.portfolio_dashboard(con)
    return render_template('portfolio.html',**data,today=date.today().isoformat(),nh_preview=nh_preview,nh_raw=nh_raw)

@app.route('/portfolio')
def portfolio():
    con=db()
    try:
        return _render_portfolio(con)
    finally: con.close()

@app.post('/portfolio/nh/preview')
def portfolio_nh_preview():
    con=db(); raw=request.form.get('nh_text','')
    try:
        parsed=parse_nh_trade_message(raw)
        parsed['matched_security_id']=match_nh_security(con,parsed)
        duplicate=con.execute("SELECT 1 FROM portfolio_trades WHERE source='NH' AND order_no=?",(parsed['order_no'],)).fetchone()
        parsed['duplicate']=bool(duplicate)
        if duplicate: flash(f"이미 등록된 NH 주문번호입니다: {parsed['order_no']}",'err')
        return _render_portfolio(con,parsed,raw)
    except Exception as e:
        flash(str(e),'err'); return _render_portfolio(con,None,raw)
    finally: con.close()

@app.post('/portfolio/nh/save')
def portfolio_nh_save():
    con=db()
    try:
        sid=int(request.form['security_id'])
        order_no=request.form.get('order_no','').strip()
        note=f"NH 체결문자 / 주문번호 {order_no}"
        finance.add_trade(con,sid,request.form['trade_date'],request.form['side'],f('qty'),f('price'),0,note,source='NH',order_no=order_no,cash_amount=f('fill_amount'))
        flash('NH 체결문자를 포트폴리오에 기록했습니다.','ok')
    except Exception as e:
        flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

@app.post('/portfolio/security/add')
def portfolio_security_add():
    con=db()
    try:
        finance.add_security(con,request.form.get('account_name'),request.form.get('market'),request.form.get('symbol'),request.form.get('name'),request.form.get('currency'),request.form.get('quote_symbol'),f('current_price',0))
        flash('포트폴리오 종목을 추가했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

@app.route('/portfolio/security/<int:sid>/edit',methods=['GET','POST'])
def portfolio_security_edit(sid):
    con=db()
    try:
        sec=con.execute('SELECT * FROM securities WHERE id=?',(sid,)).fetchone()
        if not sec: return redirect(url_for('portfolio'))
        if request.method=='POST':
            finance.edit_security(con,sid,request.form.get('account_name'),request.form.get('market'),request.form.get('symbol'),request.form.get('name'),request.form.get('currency'),request.form.get('quote_symbol'),f('current_price',0))
            flash('종목 정보를 수정했습니다.','ok'); return redirect(url_for('portfolio'))
        return render_template('security_edit.html',sec=sec)
    except Exception as e: flash(str(e),'err'); return redirect(url_for('portfolio'))
    finally: con.close()

@app.post('/portfolio/security/<int:sid>/price')
def portfolio_price(sid):
    con=db()
    try:
        finance.set_current_price(con,sid,f('current_price',0)); flash('현재가를 반영했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

@app.post('/portfolio/security/<int:sid>/refresh')
def portfolio_refresh(sid):
    con=db()
    try:
        sec=con.execute('SELECT * FROM securities WHERE id=?',(sid,)).fetchone()
        if not sec: raise ValueError('종목을 찾을 수 없습니다.')
        price, used_symbol=get_yahoo_latest_for_security(sec)
        finance.set_current_price(con,sid,price)
        # If no explicit quote symbol existed, remember the successful Yahoo symbol.
        if not (sec['quote_symbol'] or '').strip():
            con.execute('UPDATE securities SET quote_symbol=?,updated_at=? WHERE id=?',(used_symbol,finance.now(),sid))
            con.commit()
        flash(f"{sec['name']} 현재가 {price:,.4f} 반영 완료 · {used_symbol}",'ok')
    except Exception as e:
        flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

@app.post('/portfolio/security/<int:sid>/delete')
def portfolio_security_delete(sid):
    con=db()
    try: finance.delete_security(con,sid); flash('종목을 삭제했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

@app.post('/portfolio/trade/add')
def portfolio_trade_add():
    con=db()
    try:
        finance.add_trade(con,int(request.form['security_id']),request.form['trade_date'],request.form['side'],f('qty'),f('price'),f('fee',0),request.form.get('note','').strip()); flash('거래를 기록했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

@app.route('/portfolio/trade/<int:tid>/edit',methods=['GET','POST'])
def portfolio_trade_edit(tid):
    con=db()
    try:
        t=con.execute('''SELECT t.*,s.name,s.symbol,s.currency FROM portfolio_trades t JOIN securities s ON s.id=t.security_id WHERE t.id=?''',(tid,)).fetchone()
        if not t: return redirect(url_for('portfolio'))
        if request.method=='POST':
            finance.edit_trade(con,tid,request.form['trade_date'],request.form['side'],f('qty'),f('price'),f('fee',0),request.form.get('note','').strip()); flash('거래를 수정했습니다.','ok'); return redirect(url_for('portfolio'))
        return render_template('portfolio_trade_edit.html',t=t)
    except Exception as e: flash(str(e),'err'); return redirect(url_for('portfolio'))
    finally: con.close()

@app.post('/portfolio/trade/<int:tid>/delete')
def portfolio_trade_delete(tid):
    con=db()
    try: finance.delete_trade(con,tid); flash('거래를 삭제했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('portfolio'))

def _render_dividends(con, year=None, month=None, nh_preview=None, nh_raw=''):
    return render_template('dividends.html',**finance.dividend_dashboard(con,year,month),today=date.today().isoformat(),nh_preview=nh_preview,nh_raw=nh_raw)

@app.route('/dividends')
def dividends():
    con=db()
    try:
        year=request.args.get('year',type=int); month=request.args.get('month',type=int)
        return _render_dividends(con,year,month)
    finally: con.close()

@app.post('/dividends/nh/preview')
def dividends_nh_preview():
    con=db(); raw=request.form.get('nh_text','')
    try:
        parsed=parse_nh_dividend_message(raw)
        parsed['matched_security_id']=match_nh_security(con,parsed)
        dup=con.execute("SELECT 1 FROM dividends WHERE source='NH' AND source_key=?",(parsed['source_key'],)).fetchone()
        parsed['duplicate']=bool(dup)
        if dup: flash('이미 등록된 NH 배당 안내입니다.','err')
        return _render_dividends(con,nh_preview=parsed,nh_raw=raw)
    except Exception as e:
        flash(str(e),'err'); return _render_dividends(con,nh_raw=raw)
    finally: con.close()

@app.post('/dividends/nh/save')
def dividends_nh_save():
    con=db()
    try:
        sid=int(request.form['security_id']); pay_date=request.form['pay_date']
        base_date=request.form.get('base_date','').strip()
        qty=finance.security_qty_on(con,sid,base_date or pay_date)
        gross=f('gross',0); tax=f('tax',0); net=f('net',0); fee=f('fee',0)
        ps=(gross/qty) if qty and gross is not None else 0
        note=request.form.get('extra_note','').strip()
        if fee:
            note=(note+' / ' if note else '')+f'수수료 {fee}'
        finance.add_dividend(con,sid,pay_date,qty,ps,gross,tax,net,note,source='NH',source_key=request.form.get('source_key','').strip())
        flash('NH 배당 안내를 배당금 가계부에 기록했습니다.','ok')
        y=int(pay_date[:4]); m=int(pay_date[5:7])
        return redirect(url_for('dividends',year=y,month=m))
    except Exception as e:
        flash(str(e),'err'); return redirect(url_for('dividends'))
    finally: con.close()

@app.post('/dividends/add')
def dividend_add():
    con=db()
    pay_date=request.form.get('pay_date','')
    try:
        finance.add_dividend(con,int(request.form['security_id']),pay_date,request.form.get('shares','').strip(),request.form.get('per_share','').strip(),request.form.get('gross','').strip(),request.form.get('tax','').strip(),request.form.get('net','').strip(),request.form.get('note','').strip()); flash('배당금을 기록했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    y=int(pay_date[:4]) if len(pay_date)>=7 else date.today().year
    m=int(pay_date[5:7]) if len(pay_date)>=7 else date.today().month
    return redirect(url_for('dividends',year=y,month=m))

@app.route('/dividends/<int:did>/edit',methods=['GET','POST'])
def dividend_edit(did):
    con=db()
    try:
        d=con.execute('SELECT * FROM dividends WHERE id=?',(did,)).fetchone(); secs=list(con.execute('SELECT * FROM securities ORDER BY account_name,name'))
        if not d: return redirect(url_for('dividends'))
        if request.method=='POST':
            finance.edit_dividend(con,did,int(request.form['security_id']),request.form['pay_date'],request.form.get('shares','').strip(),request.form.get('per_share','').strip(),request.form.get('gross','').strip(),request.form.get('tax','').strip(),request.form.get('net','').strip(),request.form.get('note','').strip()); flash('배당기록을 수정했습니다.','ok'); return redirect(url_for('dividends',year=int(request.form['pay_date'][:4]),month=int(request.form['pay_date'][5:7])))
        return render_template('dividend_edit.html',d=d,securities=secs)
    except Exception as e: flash(str(e),'err'); return redirect(url_for('dividends'))
    finally: con.close()

@app.post('/dividends/<int:did>/delete')
def dividend_delete(did):
    con=db(); d=None
    try:
        d=con.execute('SELECT * FROM dividends WHERE id=?',(did,)).fetchone(); finance.delete_dividend(con,did); flash('배당기록을 삭제했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    if d: return redirect(url_for('dividends',year=int(d['pay_date'][:4]),month=int(d['pay_date'][5:7])))
    return redirect(url_for('dividends'))

@app.post('/dividends/target')
def dividend_target():
    con=db()
    try: finance.save_dividend_target(con,f('target_krw',300000)); flash('월 배당 목표를 저장했습니다.','ok')
    except Exception as e: flash(str(e),'err')
    finally: con.close()
    return redirect(url_for('dividends'))

if __name__=='__main__':
    import atexit
    _write_pid_file()
    atexit.register(_remove_pid_file)
    port=int(os.environ.get('PORT','5002'))
    if os.environ.get('PIPI_CLOUD','0')!='1':
        threading.Timer(1.0,lambda:webbrowser.open(f'http://127.0.0.1:{port}/dashboard')).start()
    try:
        app.run(host='0.0.0.0',port=port,debug=False,use_reloader=False)
    finally:
        _remove_pid_file()

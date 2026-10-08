from __future__ import annotations
import sqlite3
from datetime import date, datetime

SCHEMA = '''
CREATE TABLE IF NOT EXISTS finance_settings(
 id INTEGER PRIMARY KEY CHECK(id=1),
 dividend_target_krw REAL NOT NULL DEFAULT 300000,
 usd_krw REAL NOT NULL DEFAULT 1400,
 fx_updated_at TEXT,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS securities(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_name TEXT NOT NULL DEFAULT '일반',
 market TEXT NOT NULL DEFAULT 'KR',
 symbol TEXT NOT NULL,
 name TEXT NOT NULL,
 currency TEXT NOT NULL DEFAULT 'KRW',
 quote_symbol TEXT,
 current_price REAL NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL,
 UNIQUE(account_name, symbol)
);
CREATE TABLE IF NOT EXISTS portfolio_trades(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 security_id INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
 trade_date TEXT NOT NULL,
 side TEXT NOT NULL CHECK(side IN('BUY','SELL')),
 qty REAL NOT NULL,
 price REAL NOT NULL,
 fee REAL NOT NULL DEFAULT 0,
 cash_amount REAL,
 source TEXT NOT NULL DEFAULT 'MANUAL',
 order_no TEXT,
 note TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dividends(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 security_id INTEGER REFERENCES securities(id) ON DELETE SET NULL,
 pay_date TEXT NOT NULL,
 account_name TEXT NOT NULL,
 symbol TEXT NOT NULL,
 name TEXT NOT NULL,
 currency TEXT NOT NULL,
 shares REAL NOT NULL DEFAULT 0,
 per_share REAL NOT NULL DEFAULT 0,
 gross REAL NOT NULL DEFAULT 0,
 tax REAL NOT NULL DEFAULT 0,
 net REAL NOT NULL DEFAULT 0,
 source TEXT NOT NULL DEFAULT 'MANUAL',
 source_key TEXT,
 note TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfolio_trades_sec_date ON portfolio_trades(security_id,trade_date,id);
CREATE INDEX IF NOT EXISTS idx_dividends_date ON dividends(pay_date,id);
'''

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def init_db(con: sqlite3.Connection):
    con.executescript(SCHEMA)
    # v2.6 migration: keep old vr7.db files compatible.
    cols={r[1] for r in con.execute('PRAGMA table_info(portfolio_trades)')}
    if 'cash_amount' not in cols:
        con.execute('ALTER TABLE portfolio_trades ADD COLUMN cash_amount REAL')
    if 'source' not in cols:
        con.execute("ALTER TABLE portfolio_trades ADD COLUMN source TEXT NOT NULL DEFAULT 'MANUAL'")
    if 'order_no' not in cols:
        con.execute('ALTER TABLE portfolio_trades ADD COLUMN order_no TEXT')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_trades_source_order ON portfolio_trades(source,order_no) WHERE order_no IS NOT NULL AND order_no<>''")
    fscols={r[1] for r in con.execute('PRAGMA table_info(finance_settings)')}
    if 'usd_krw' not in fscols:
        con.execute('ALTER TABLE finance_settings ADD COLUMN usd_krw REAL NOT NULL DEFAULT 1400')
    if 'fx_updated_at' not in fscols:
        con.execute('ALTER TABLE finance_settings ADD COLUMN fx_updated_at TEXT')
    dcols={r[1] for r in con.execute('PRAGMA table_info(dividends)')}
    if 'source_key' not in dcols:
        con.execute('ALTER TABLE dividends ADD COLUMN source_key TEXT')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dividends_source_key ON dividends(source,source_key) WHERE source_key IS NOT NULL AND source_key<>''")
    if not con.execute('SELECT 1 FROM finance_settings WHERE id=1').fetchone():
        con.execute('INSERT INTO finance_settings(id,dividend_target_krw,updated_at) VALUES(1,300000,?)',(now(),))
    con.commit()

def finance_settings(con):
    return con.execute('SELECT * FROM finance_settings WHERE id=1').fetchone()

def save_dividend_target(con, amount):
    amount=max(0.0,float(amount or 0))
    con.execute('UPDATE finance_settings SET dividend_target_krw=?,updated_at=? WHERE id=1',(amount,now()))
    con.commit()

def save_usd_krw(con, rate):
    rate=float(rate or 0)
    if rate<=0: raise ValueError('USD/KRW 환율은 0보다 커야 합니다.')
    ts=now()
    con.execute('UPDATE finance_settings SET usd_krw=?,fx_updated_at=?,updated_at=? WHERE id=1',(rate,ts,ts))
    con.commit()

def asset_dashboard(con):
    # Core VR account + portfolio holdings, all normalized to KRW.
    try:
        import core
        core.recompute(con)
    except Exception:
        pass
    fs=finance_settings(con)
    fx=float(fs['usd_krw'] or 0) if fs else 0.0
    if fx<=0: fx=1400.0
    assets=[]
    latest=con.execute('SELECT * FROM cycles ORDER BY week_no DESC,close_date DESC,id DESC LIMIT 1').fetchone()
    if latest and latest['account_total'] is not None:
        usd=float(latest['account_total'] or 0)
        if usd>0:
            assets.append({'key':'vr7','name':'VR7기','currency':'USD','original_value':usd,'krw_value':usd*fx,'detail':f"{int(latest['week_no'])}주차 · TQQQ 평가금 ${float(latest['valuation'] or 0):,.2f} + Pool ${float(latest['next_pool'] or 0):,.2f}"})
    for s in con.execute('SELECT * FROM securities ORDER BY account_name,name,id'):
        h=_calc_security(con,s['id'])
        mv=float(h['market_value'] or 0)
        if mv<=0: continue
        cur=(s['currency'] or 'KRW').upper()
        krw=mv if cur=='KRW' else mv*fx
        assets.append({'key':f"sec-{s['id']}",'name':s['name'],'currency':cur,'original_value':mv,'krw_value':krw,'detail':f"[{s['account_name']}] {s['symbol']} · {h['qty']:,.4f}주"})
    total=sum(a['krw_value'] for a in assets)
    for a in assets:
        a['percent']=(a['krw_value']/total*100) if total>0 else 0.0
    assets.sort(key=lambda x:x['krw_value'],reverse=True)
    return {'assets':assets,'total_krw':total,'usd_krw':fx,'fx_updated_at':(fs['fx_updated_at'] if fs and 'fx_updated_at' in fs.keys() else None)}

def add_security(con, account_name, market, symbol, name, currency, quote_symbol='', current_price=0):
    account=(account_name or '일반').strip() or '일반'
    market=(market or 'KR').strip().upper()
    symbol=(symbol or '').strip().upper()
    name=(name or '').strip()
    currency=(currency or 'KRW').strip().upper()
    quote_symbol=(quote_symbol or '').strip().upper()
    price=float(current_price or 0)
    if not symbol or not name:
        raise ValueError('종목코드와 종목명을 입력해 주세요.')
    if currency not in ('KRW','USD'):
        raise ValueError('통화는 KRW 또는 USD만 사용할 수 있습니다.')
    try:
        con.execute('''INSERT INTO securities(account_name,market,symbol,name,currency,quote_symbol,current_price,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)''',(account,market,symbol,name,currency,quote_symbol,price,now()))
        con.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f'{account} 계좌에 {symbol} 종목이 이미 있습니다.')

def edit_security(con, sid, account_name, market, symbol, name, currency, quote_symbol='', current_price=0):
    sec=con.execute('SELECT * FROM securities WHERE id=?',(sid,)).fetchone()
    if not sec: raise ValueError('종목을 찾을 수 없습니다.')
    account=(account_name or '일반').strip() or '일반'; market=(market or 'KR').strip().upper(); symbol=(symbol or '').strip().upper(); name=(name or '').strip(); currency=(currency or 'KRW').strip().upper(); quote_symbol=(quote_symbol or '').strip().upper(); price=float(current_price or 0)
    if not symbol or not name: raise ValueError('종목코드와 종목명을 입력해 주세요.')
    if currency not in ('KRW','USD'): raise ValueError('통화는 KRW 또는 USD만 사용할 수 있습니다.')
    try:
        con.execute('''UPDATE securities SET account_name=?,market=?,symbol=?,name=?,currency=?,quote_symbol=?,current_price=?,updated_at=? WHERE id=?''',(account,market,symbol,name,currency,quote_symbol,price,now(),sid))
        # Keep duplicated dividend labels aligned with the security.
        con.execute('UPDATE dividends SET account_name=?,symbol=?,name=?,currency=?,updated_at=? WHERE security_id=?',(account,symbol,name,currency,now(),sid))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback(); raise ValueError(f'{account} 계좌에 {symbol} 종목이 이미 있습니다.')

def set_current_price(con, sid, price):
    price=float(price or 0)
    if price < 0: raise ValueError('현재가는 0 이상이어야 합니다.')
    con.execute('UPDATE securities SET current_price=?,updated_at=? WHERE id=?',(price,now(),sid)); con.commit()

def delete_security(con, sid):
    n1=con.execute('SELECT COUNT(*) FROM portfolio_trades WHERE security_id=?',(sid,)).fetchone()[0]
    n2=con.execute('SELECT COUNT(*) FROM dividends WHERE security_id=?',(sid,)).fetchone()[0]
    if n1 or n2: raise ValueError('거래 또는 배당 기록이 있는 종목은 먼저 관련 기록을 삭제해야 합니다.')
    con.execute('DELETE FROM securities WHERE id=?',(sid,)); con.commit()

def _calc_security(con, sid, through_date=None):
    sec=con.execute('SELECT * FROM securities WHERE id=?',(sid,)).fetchone()
    if not sec: raise ValueError('종목을 찾을 수 없습니다.')
    sql='SELECT * FROM portfolio_trades WHERE security_id=?'
    params=[sid]
    if through_date:
        sql+=' AND trade_date<=?'; params.append(through_date)
    sql+=' ORDER BY trade_date,id'
    qty=0.0; avg=0.0; realized=0.0; buys=0.0; sells=0.0
    for t in con.execute(sql,params):
        q=float(t['qty']); p=float(t['price']); fee=float(t['fee'] or 0)
        if t['side']=='BUY':
            cash=t['cash_amount'] if 'cash_amount' in t.keys() else None
            cost=(float(cash) if cash is not None else q*p)+fee
            new_qty=qty+q
            avg=((qty*avg)+cost)/new_qty if new_qty>1e-12 else 0.0
            qty=new_qty; buys+=cost
        else:
            if q>qty+1e-9:
                raise ValueError(f"{sec['name']} {t['trade_date']} 매도수량이 당시 보유수량을 초과합니다.")
            cash=t['cash_amount'] if 'cash_amount' in t.keys() else None
            proceeds=(float(cash) if cash is not None else q*p)-fee
            realized += q*(p-avg)-fee
            qty-=q; sells+=proceeds
            if qty<=1e-12: qty=0.0; avg=0.0
    cp=float(sec['current_price'] or 0)
    value=qty*cp
    basis=qty*avg
    unrealized=value-basis if cp>0 else 0.0
    ret=(unrealized/basis*100) if basis>0 and cp>0 else 0.0
    return {'security':sec,'qty':qty,'avg_price':avg,'realized':realized,'buy_amount':buys,'sell_amount':sells,'current_price':cp,'market_value':value,'cost_basis':basis,'unrealized':unrealized,'return_pct':ret}

def security_qty_on(con, sid, d):
    return _calc_security(con,sid,d)['qty']

def add_trade(con, sid, trade_date, side, qty, price, fee=0, note='', source='MANUAL', order_no=None, cash_amount=None):
    side=(side or '').upper(); qty=float(qty); price=float(price); fee=float(fee or 0)
    source=(source or 'MANUAL').strip().upper() or 'MANUAL'
    order_no=(str(order_no).strip() if order_no not in (None,'') else None)
    cash_amount=(None if cash_amount in (None,'') else float(cash_amount))
    if cash_amount is not None and cash_amount < 0: raise ValueError('체결금액을 확인해 주세요.')
    if side not in ('BUY','SELL') or qty<=0 or price<=0 or fee<0: raise ValueError('거래값을 확인해 주세요.')
    if order_no and con.execute('SELECT 1 FROM portfolio_trades WHERE source=? AND order_no=?',(source,order_no)).fetchone():
        raise ValueError(f'이미 등록된 {source} 주문번호입니다: {order_no}')
    try:
        con.execute('BEGIN')
        con.execute('''INSERT INTO portfolio_trades(security_id,trade_date,side,qty,price,fee,cash_amount,source,order_no,note,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(sid,trade_date,side,qty,price,fee,cash_amount,source,order_no,note,now(),now()))
        _calc_security(con,sid)
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        if order_no:
            raise ValueError(f'이미 등록된 {source} 주문번호입니다: {order_no}') from e
        raise
    except Exception:
        con.rollback(); raise

def edit_trade(con, tid, trade_date, side, qty, price, fee=0, note=''):
    row=con.execute('SELECT * FROM portfolio_trades WHERE id=?',(tid,)).fetchone()
    if not row: raise ValueError('거래기록을 찾을 수 없습니다.')
    side=(side or '').upper(); qty=float(qty); price=float(price); fee=float(fee or 0)
    if side not in ('BUY','SELL') or qty<=0 or price<=0 or fee<0: raise ValueError('거래값을 확인해 주세요.')
    try:
        con.execute('BEGIN')
        con.execute('UPDATE portfolio_trades SET trade_date=?,side=?,qty=?,price=?,fee=?,cash_amount=NULL,note=?,updated_at=? WHERE id=?',(trade_date,side,qty,price,fee,note,now(),tid))
        _calc_security(con,row['security_id'])
        con.commit()
    except Exception:
        con.rollback(); raise

def delete_trade(con, tid):
    row=con.execute('SELECT * FROM portfolio_trades WHERE id=?',(tid,)).fetchone()
    if not row: return
    try:
        con.execute('BEGIN'); con.execute('DELETE FROM portfolio_trades WHERE id=?',(tid,)); _calc_security(con,row['security_id']); con.commit()
    except Exception:
        con.rollback(); raise

def portfolio_dashboard(con):
    secs=list(con.execute('SELECT * FROM securities ORDER BY account_name,name,id'))
    holdings=[]; totals={}
    for s in secs:
        h=_calc_security(con,s['id']); holdings.append(h)
        cur=s['currency']; t=totals.setdefault(cur,{'market_value':0.0,'cost_basis':0.0,'unrealized':0.0,'realized':0.0})
        t['market_value']+=h['market_value']; t['cost_basis']+=h['cost_basis']; t['unrealized']+=h['unrealized']; t['realized']+=h['realized']
    trades=list(con.execute('''SELECT t.*,s.name,s.symbol,s.currency,s.account_name FROM portfolio_trades t JOIN securities s ON s.id=t.security_id ORDER BY t.trade_date DESC,t.id DESC LIMIT 200'''))
    return {'securities':secs,'holdings':holdings,'totals':totals,'trades':trades}

def add_dividend(con, sid, pay_date, shares=None, per_share=None, gross=None, tax=None, net=None, note='', source='MANUAL', source_key=None):
    sec=con.execute('SELECT * FROM securities WHERE id=?',(sid,)).fetchone()
    if not sec: raise ValueError('종목을 선택해 주세요.')
    qty=security_qty_on(con,sid,pay_date) if shares in (None,'') else float(shares)
    ps=0.0 if per_share in (None,'') else float(per_share)
    g=None if gross in (None,'') else float(gross)
    tx=None if tax in (None,'') else float(tax)
    nt=None if net in (None,'') else float(net)
    if g is None:
        if ps<=0: raise ValueError('주당배당금 또는 세전 총액 중 하나를 입력해 주세요.')
        g=qty*ps
    if g<0: raise ValueError('배당금은 0 이상이어야 합니다.')
    if ps<=0 and qty>0: ps=g/qty
    if tx is None and nt is not None: tx=max(0.0,g-nt)
    if tx is None:
        rate=0.154 if sec['currency']=='KRW' else 0.15
        tx=g*rate
    if nt is None: nt=g-tx
    if tx<0 or nt<0: raise ValueError('세금/세후금액을 확인해 주세요.')
    source=(source or 'MANUAL').strip().upper() or 'MANUAL'
    source_key=(str(source_key).strip() if source_key not in (None,'') else None)
    if source_key and con.execute('SELECT 1 FROM dividends WHERE source=? AND source_key=?',(source,source_key)).fetchone():
        raise ValueError('이미 등록된 배당 안내입니다.')
    try:
        con.execute('''INSERT INTO dividends(security_id,pay_date,account_name,symbol,name,currency,shares,per_share,gross,tax,net,source,source_key,note,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(sid,pay_date,sec['account_name'],sec['symbol'],sec['name'],sec['currency'],qty,ps,g,tx,nt,source,source_key,note,now(),now()))
        con.commit()
    except sqlite3.IntegrityError as e:
        con.rollback()
        if source_key:
            raise ValueError('이미 등록된 배당 안내입니다.') from e
        raise

def edit_dividend(con, did, sid, pay_date, shares=None, per_share=None, gross=None, tax=None, net=None, note=''):
    row=con.execute('SELECT * FROM dividends WHERE id=?',(did,)).fetchone()
    if not row: raise ValueError('배당기록을 찾을 수 없습니다.')
    sec=con.execute('SELECT * FROM securities WHERE id=?',(sid,)).fetchone()
    if not sec: raise ValueError('종목을 선택해 주세요.')
    qty=security_qty_on(con,sid,pay_date) if shares in (None,'') else float(shares)
    ps=0.0 if per_share in (None,'') else float(per_share)
    g=None if gross in (None,'') else float(gross); tx=None if tax in (None,'') else float(tax); nt=None if net in (None,'') else float(net)
    if g is None:
        if ps<=0: raise ValueError('주당배당금 또는 세전 총액 중 하나를 입력해 주세요.')
        g=qty*ps
    if ps<=0 and qty>0: ps=g/qty
    if tx is None and nt is not None: tx=max(0.0,g-nt)
    if tx is None: tx=g*(0.154 if sec['currency']=='KRW' else 0.15)
    if nt is None: nt=g-tx
    con.execute('''UPDATE dividends SET security_id=?,pay_date=?,account_name=?,symbol=?,name=?,currency=?,shares=?,per_share=?,gross=?,tax=?,net=?,note=?,updated_at=? WHERE id=?''',(sid,pay_date,sec['account_name'],sec['symbol'],sec['name'],sec['currency'],qty,ps,g,tx,nt,note,now(),did)); con.commit()

def delete_dividend(con, did):
    con.execute('DELETE FROM dividends WHERE id=?',(did,)); con.commit()

def dividend_dashboard(con, year=None, month=None):
    today=date.today(); year=int(year or today.year); month=int(month or today.month)
    if month<1 or month>12: month=today.month
    rows=list(con.execute('SELECT * FROM dividends WHERE substr(pay_date,1,4)=? ORDER BY pay_date DESC,id DESC',(str(year),)))
    month_rows=[r for r in rows if int(r['pay_date'][5:7])==month]
    monthly={m:{'KRW':0.0,'USD':0.0} for m in range(1,13)}
    annual={'KRW':{'gross':0.0,'tax':0.0,'net':0.0},'USD':{'gross':0.0,'tax':0.0,'net':0.0}}
    for r in rows:
        cur=r['currency']; m=int(r['pay_date'][5:7]); monthly[m][cur]+=float(r['net'])
        for k in ('gross','tax','net'): annual[cur][k]+=float(r[k])
    month_total={'KRW':0.0,'USD':0.0}
    for r in month_rows: month_total[r['currency']]+=float(r['net'])
    yrs={today.year,year}
    for r in con.execute("SELECT DISTINCT substr(pay_date,1,4) y FROM dividends WHERE pay_date<>''"):
        try: yrs.add(int(r['y']))
        except: pass
    elapsed=12 if year<today.year else (today.month if year==today.year else 1)
    avg_krw=annual['KRW']['net']/max(1,elapsed)
    fs=finance_settings(con); target=float(fs['dividend_target_krw'] or 0)
    progress=(avg_krw/target*100) if target>0 else 0.0
    securities=list(con.execute('SELECT * FROM securities ORDER BY account_name,name,id'))
    dividend_chart={'krw':[monthly[m]['KRW'] for m in range(1,13)],'usd':[monthly[m]['USD'] for m in range(1,13)]}
    return {'year':year,'month':month,'years':sorted(yrs,reverse=True),'rows':month_rows,'all_year_rows':rows,'monthly':monthly,'annual':annual,'month_total':month_total,'avg_krw':avg_krw,'target_krw':target,'progress':progress,'securities':securities,'dividend_chart':dividend_chart}

from __future__ import annotations
import math, sqlite3
from datetime import date, datetime, timedelta

DB_NAME='vr7.db'

def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def connect(path):
    con=sqlite3.connect(path)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

SCHEMA='''
CREATE TABLE IF NOT EXISTS settings(
 id INTEGER PRIMARY KEY CHECK(id=1),
 start_date TEXT NOT NULL,
 initial_pool REAL NOT NULL DEFAULT 100,
 initial_shares REAL NOT NULL DEFAULT 0,
 initial_net_trade_cost REAL NOT NULL DEFAULT 0,
 initial_invested REAL NOT NULL DEFAULT 100,
 contribution REAL NOT NULL DEFAULT 100,
 interval_days INTEGER NOT NULL DEFAULT 14,
 default_g REAL NOT NULL DEFAULT 10,
 lower_mult REAL NOT NULL DEFAULT 0.85,
 upper_mult REAL NOT NULL DEFAULT 1.15,
 plan_start_date TEXT,
 plan_end_week INTEGER NOT NULL DEFAULT 269,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cycles(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 week_no INTEGER NOT NULL UNIQUE,
 close_date TEXT NOT NULL,
 v_value REAL NOT NULL,
 g_value REAL NOT NULL,
 close_price REAL NOT NULL,
 v_min REAL NOT NULL,
 v_max REAL NOT NULL,
 band_manual INTEGER NOT NULL DEFAULT 0,
 dividend REAL NOT NULL DEFAULT 0,
 contribution REAL NOT NULL DEFAULT 100,
 note TEXT,
 first_pool REAL NOT NULL DEFAULT 0,
 trade_cashflow REAL NOT NULL DEFAULT 0,
 last_pool REAL NOT NULL DEFAULT 0,
 next_pool REAL NOT NULL DEFAULT 0,
 shares_snapshot REAL NOT NULL DEFAULT 0,
 valuation REAL NOT NULL DEFAULT 0,
 avg_price REAL NOT NULL DEFAULT 0,
 account_total REAL NOT NULL DEFAULT 0,
 invested REAL NOT NULL DEFAULT 0,
 profit REAL NOT NULL DEFAULT 0,
 return_pct REAL NOT NULL DEFAULT 0,
 next_v REAL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 cycle_id INTEGER NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
 side TEXT NOT NULL CHECK(side IN('BUY','SELL')),
 qty REAL NOT NULL,
 price REAL NOT NULL,
 fee REAL NOT NULL DEFAULT 0,
 note TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS planned_weeks(
 week_no INTEGER PRIMARY KEY,
 planned_date TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cycles_order ON cycles(week_no, close_date, id);
CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id,id);
'''

def _ensure_column(con, table, name, ddl):
    cols={r[1] for r in con.execute(f'PRAGMA table_info({table})')}
    if name not in cols:
        con.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')

def settings(con):
    return con.execute('SELECT * FROM settings WHERE id=1').fetchone()

def sync_planned_weeks(con):
    s=settings(con)
    start_txt=s['plan_start_date'] or s['start_date']
    start=date.fromisoformat(start_txt)
    end_week=int(s['plan_end_week'] or 269)
    if end_week < 1: end_week=1
    if end_week % 2 == 0: end_week -= 1
    interval=int(s['interval_days'])
    con.execute('DELETE FROM planned_weeks')
    ts=now()
    rows=[]
    for w in range(1,end_week+1,2):
        idx=(w-1)//2
        d=(start+timedelta(days=idx*interval)).isoformat()
        rows.append((w,d,ts))
    con.executemany('INSERT INTO planned_weeks(week_no,planned_date,created_at) VALUES(?,?,?)',rows)
    con.commit()

def init_db(path):
    con=connect(path)
    try:
        con.executescript(SCHEMA)
        _ensure_column(con,'settings','plan_start_date','TEXT')
        _ensure_column(con,'settings','plan_end_week','INTEGER NOT NULL DEFAULT 269')
        if not con.execute('SELECT 1 FROM settings WHERE id=1').fetchone():
            today=date.today().isoformat()
            con.execute('''INSERT INTO settings(id,start_date,initial_pool,initial_shares,initial_net_trade_cost,initial_invested,contribution,interval_days,default_g,lower_mult,upper_mult,plan_start_date,plan_end_week,updated_at)
                           VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (today,100,0,0,100,100,14,10,0.85,1.15,today,269,now()))
        else:
            con.execute('UPDATE settings SET plan_start_date=COALESCE(plan_start_date,start_date), plan_end_week=COALESCE(plan_end_week,269) WHERE id=1')
        con.commit()
        sync_planned_weeks(con)
    finally:
        con.close()

def save_settings(con, d):
    keys=['start_date','initial_pool','initial_shares','initial_net_trade_cost','initial_invested','contribution','interval_days','default_g','lower_mult','upper_mult','plan_start_date','plan_end_week']
    vals=[d[k] for k in keys]
    con.execute('UPDATE settings SET '+','.join(k+'=?' for k in keys)+',updated_at=? WHERE id=1', vals+[now()])
    con.commit()
    sync_planned_weeks(con)
    recompute(con)

def suggested(con):
    s=settings(con)
    plan=con.execute('''SELECT p.week_no,p.planned_date
                        FROM planned_weeks p
                        LEFT JOIN cycles c ON c.week_no=p.week_no
                        WHERE c.id IS NULL
                        ORDER BY p.week_no LIMIT 1''').fetchone()
    last=con.execute('SELECT * FROM cycles ORDER BY week_no DESC,close_date DESC,id DESC LIMIT 1').fetchone()
    if plan:
        w=int(plan['week_no']); d=plan['planned_date']
    elif last:
        lw=int(last['week_no'])
        w=lw+2 if lw%2 else lw+1
        d=(date.fromisoformat(last['close_date'])+timedelta(days=int(s['interval_days']))).isoformat()
    else:
        w=1; d=s['plan_start_date'] or s['start_date']
    if last:
        v=float(last['next_v']) if last['next_v'] is not None else float(last['v_value'])
        first_pool=float(last['next_pool']) if last['next_pool'] is not None else float(s['initial_pool'])
    else:
        v=0.0; first_pool=float(s['initial_pool'])
    return {'week_no':w,'close_date':d,'v_value':v,'g_value':float(s['default_g']),'first_pool':first_pool}

def add_cycle(con, week_no, close_date, v_value, g_value, close_price, v_min=None, v_max=None, dividend=0, contribution=None, note=''):
    s=settings(con)
    week_no=int(week_no); v=float(v_value); g=float(g_value); p=float(close_price)
    if week_no<0: raise ValueError('주차는 0 이상이어야 합니다.')
    if con.execute('SELECT 1 FROM cycles WHERE week_no=?',(week_no,)).fetchone(): raise ValueError(f'{week_no}주차가 이미 있습니다.')
    if v<=0 or g<=0 or p<=0: raise ValueError('V, G, TQQQ 종가는 0보다 커야 합니다.')
    manual=(v_min is not None and v_max is not None)
    lo=float(v_min) if manual else v*float(s['lower_mult'])
    hi=float(v_max) if manual else v*float(s['upper_mult'])
    if lo<=0 or hi<=0 or lo>=hi: raise ValueError('V최소/V최대 범위를 확인해 주세요.')
    c=float(s['contribution']) if contribution is None else float(contribution)
    ts=now()
    cur=con.execute('''INSERT INTO cycles(week_no,close_date,v_value,g_value,close_price,v_min,v_max,band_manual,dividend,contribution,note,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (week_no,close_date,v,g,p,lo,hi,1 if manual else 0,float(dividend or 0),c,note,ts,ts))
    con.commit(); recompute(con); return cur.lastrowid

def edit_cycle(con,cid,**kw):
    c=con.execute('SELECT * FROM cycles WHERE id=?',(cid,)).fetchone()
    if not c: raise ValueError('주차를 찾을 수 없습니다.')
    week_no=int(kw['week_no']); v=float(kw['v_value']); g=float(kw['g_value']); p=float(kw['close_price'])
    if week_no<0: raise ValueError('주차는 0 이상이어야 합니다.')
    if con.execute('SELECT 1 FROM cycles WHERE week_no=? AND id<>?',(week_no,cid)).fetchone(): raise ValueError(f'{week_no}주차가 이미 있습니다.')
    s=settings(con)
    vmin=kw.get('v_min'); vmax=kw.get('v_max')
    manual=vmin not in (None,'') and vmax not in (None,'')
    lo=float(vmin) if manual else v*float(s['lower_mult'])
    hi=float(vmax) if manual else v*float(s['upper_mult'])
    con.execute('''UPDATE cycles SET week_no=?,close_date=?,v_value=?,g_value=?,close_price=?,v_min=?,v_max=?,band_manual=?,dividend=?,contribution=?,note=?,updated_at=? WHERE id=?''',
                (week_no,kw['close_date'],v,g,p,lo,hi,1 if manual else 0,float(kw.get('dividend') or 0),float(kw.get('contribution')),kw.get('note',''),now(),cid))
    con.commit(); recompute(con)

def delete_cycle(con,cid):
    con.execute('DELETE FROM cycles WHERE id=?',(cid,)); con.commit(); recompute(con)

def add_trade(con,cid,side,qty,price,fee=0,note=''):
    if not con.execute('SELECT 1 FROM cycles WHERE id=?',(cid,)).fetchone(): raise ValueError('주차를 찾을 수 없습니다.')
    side=side.upper(); qty=float(qty); price=float(price); fee=float(fee or 0)
    if side not in ('BUY','SELL') or qty<=0 or price<=0 or fee<0: raise ValueError('체결값을 확인해 주세요.')
    ts=now()
    cur=con.execute('INSERT INTO trades(cycle_id,side,qty,price,fee,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(cid,side,qty,price,fee,note,ts,ts))
    con.commit(); recompute(con); return cur.lastrowid

def edit_trade(con,tid,side,qty,price,fee=0,note=''):
    side=side.upper(); qty=float(qty); price=float(price); fee=float(fee or 0)
    if side not in ('BUY','SELL') or qty<=0 or price<=0 or fee<0: raise ValueError('체결값을 확인해 주세요.')
    con.execute('UPDATE trades SET side=?,qty=?,price=?,fee=?,note=?,updated_at=? WHERE id=?',(side,qty,price,fee,note,now(),tid))
    con.commit(); recompute(con)

def delete_trade(con,tid):
    con.execute('DELETE FROM trades WHERE id=?',(tid,)); con.commit(); recompute(con)

def recompute(con):
    s=settings(con)
    shares=float(s['initial_shares']); pool=float(s['initial_pool']); net_trade_cost=float(s['initial_net_trade_cost']); invested=float(s['initial_invested'])
    cycles=list(con.execute('SELECT * FROM cycles ORDER BY week_no,close_date,id'))
    for c in cycles:
        first_pool=pool
        trade_cashflow=0.0
        for t in con.execute('SELECT * FROM trades WHERE cycle_id=? ORDER BY id',(c['id'],)):
            qty=float(t['qty']); pr=float(t['price']); fee=float(t['fee'])
            if t['side']=='BUY':
                cash=qty*pr+fee
                if cash>pool+1e-8: raise ValueError(f"{c['week_no']}주차 매수금이 POOL을 초과합니다.")
                shares+=qty; pool-=cash; trade_cashflow-=cash; net_trade_cost+=cash
            else:
                if qty>shares+1e-8: raise ValueError(f"{c['week_no']}주차 매도수량이 보유수량을 초과합니다.")
                proceeds=qty*pr-fee
                shares-=qty; pool+=proceeds; trade_cashflow+=proceeds; net_trade_cost-=proceeds
        div=float(c['dividend'] or 0); pool+=div
        last_pool=pool
        valuation=shares*float(c['close_price'])
        avg=(net_trade_cost/shares) if shares>1e-12 else 0.0
        g=float(c['g_value']); v=float(c['v_value']); contrib=float(c['contribution'])
        next_v=v + last_pool/g + (valuation-v)/(2*math.sqrt(g)) + contrib
        pool+=contrib
        next_pool=pool
        invested+=contrib
        account_total=valuation+next_pool
        profit=account_total-invested
        ret=(profit/invested*100) if invested else 0.0
        con.execute('''UPDATE cycles SET first_pool=?,trade_cashflow=?,last_pool=?,next_pool=?,shares_snapshot=?,valuation=?,avg_price=?,account_total=?,invested=?,profit=?,return_pct=?,next_v=?,updated_at=? WHERE id=?''',
                    (first_pool,trade_cashflow,last_pool,next_pool,shares,valuation,avg,account_total,invested,profit,ret,next_v,now(),c['id']))
    con.commit()

def _project_future_bands(con, cycles, plan_rows, s):
    projections={}
    if not cycles:
        return projections
    latest=cycles[-1]
    next_v=float(latest['next_v']) if latest['next_v'] is not None else float(latest['v_value'])
    ref_pool=float(latest['next_pool']) if latest['next_pool'] is not None else float(s['initial_pool'])
    g=float(s['default_g'])
    contrib=float(s['contribution'])
    lo_mult=float(s['lower_mult'])
    hi_mult=float(s['upper_mult'])
    if g <= 0:
        return projections
    actual_weeks={int(c['week_no']) for c in cycles}
    for r in plan_rows:
        w=int(r['week_no'])
        if w <= int(latest['week_no']) or w in actual_weeks:
            continue
        v=next_v
        projections[w]={'v_value':v,'v_min':v*lo_mult,'v_max':v*hi_mult}
        # Neutral projected centerline: E == V. The latest confirmed next Pool
        # is held as the reference until a real trade/cycle changes it.
        next_v=v + ref_pool/g + contrib
    return projections



def _loc_order_plan(latest, upcoming, s, max_rows=8):
    """Build the LOC ladder for the *next trading period*.

    Luna/VR logic uses the band that will be traded during the upcoming period,
    not the band from the just-finished confirmed row.

      BUY  price = upcoming Vmin / shares_before_fill
      SELL price = upcoming Vmax / shares_before_fill

    The starting Pool is the previous confirmed row's next_pool (i.e. after the
    scheduled contribution has been added). Each row assumes a one-share fill.
    """
    if not latest or not upcoming:
        return None

    shares=float(latest['shares_snapshot'] or 0)
    pool=float(upcoming.get('first_pool') or 0)
    v=float(upcoming.get('v_value') or 0)
    vmin=v*float(s['lower_mult'])
    vmax=v*float(s['upper_mult'])
    contrib=float(s['contribution'] or 0)

    # Luna sheet: 풀 제한 = sign(적립/인출)*25% + 50%
    # + contribution -> 75%, 0 -> 50%, - contribution -> 25%.
    if contrib > 0:
        pool_limit=0.75
    elif contrib < 0:
        pool_limit=0.25
    else:
        pool_limit=0.50
    reserve_floor=max(0.0, pool*(1.0-pool_limit))

    buys=[]
    running_pool=pool
    if shares > 1e-12 and vmin > 0:
        for i in range(int(max_rows)):
            shares_before=shares+i
            if shares_before <= 1e-12:
                break
            price=vmin/shares_before
            after=running_pool-price
            buys.append({
                'seq':i+1,
                'qty':1.0,
                'shares_before':shares_before,
                'target_shares':shares_before+1.0,
                'price':price,
                'pool_after':after,
            })
            running_pool=after
            # Luna creates the first level, then checks the pool floor before
            # producing another lower buy level.
            if running_pool < reserve_floor-1e-12:
                break

    sells=[]
    running_pool=pool
    remaining=shares
    for i in range(int(max_rows)):
        if remaining <= 1e-12 or vmax <= 0:
            break
        qty=1.0 if remaining >= 1.0-1e-12 else remaining
        price=vmax/remaining
        after=running_pool+qty*price
        sells.append({
            'seq':i+1,
            'qty':qty,
            'shares_before':remaining,
            'target_shares':max(0.0, remaining-qty),
            'price':price,
            'pool_after':after,
        })
        running_pool=after
        remaining=max(0.0, remaining-qty)

    try:
        start=date.fromisoformat(str(upcoming.get('close_date') or ''))
        interval=max(1,int(s['interval_days'] or 14))
        start_txt=start.strftime('%m.%d')
        end_txt=(start+timedelta(days=interval-1)).strftime('%m.%d')
    except Exception:
        start_txt=str(upcoming.get('close_date') or '')
        end_txt=''

    return {
        'week_no':int(upcoming.get('week_no') or 0),
        'v_value':v,
        'v_min':vmin,
        'v_max':vmax,
        'shares':shares,
        'buys':buys,
        'sells':sells,
        'pool':pool,
        'reserve_floor':reserve_floor,
        'pool_limit_pct':pool_limit*100.0,
        'period_start':start_txt,
        'period_end':end_txt,
        'first_buy':buys[0] if buys else None,
        'first_sell':sells[0] if sells else None,
    }

def dashboard(con):
    try: recompute(con)
    except Exception: pass
    s=settings(con)
    cycles=list(con.execute('SELECT * FROM cycles ORDER BY week_no,close_date,id'))
    latest=cycles[-1] if cycles else None
    trades=list(con.execute("SELECT t.*,c.week_no FROM trades t JOIN cycles c ON c.id=t.cycle_id ORDER BY c.week_no DESC,t.id DESC LIMIT 50"))
    sug=suggested(con)
    plan_rows=list(con.execute("SELECT p.week_no,p.planned_date,c.id AS cycle_id,c.close_date AS actual_date,c.v_value,c.g_value,c.valuation,c.last_pool,c.next_v FROM planned_weeks p LEFT JOIN cycles c ON c.week_no=p.week_no ORDER BY p.week_no"))
    plan_total=len(plan_rows)
    plan_done=sum(1 for r in plan_rows if r['cycle_id'] is not None)

    projections=_project_future_bands(con,cycles,plan_rows,s)
    actual_by_week={int(c['week_no']):c for c in cycles}
    axis_weeks=sorted(set(actual_by_week) | {int(r['week_no']) for r in plan_rows})
    labels=[]; valuation=[]; vmin=[]; vmax=[]
    for w in axis_weeks:
        labels.append(f'{w}주차')
        c=actual_by_week.get(w)
        if c is not None:
            valuation.append(round(float(c['valuation']),4))
            vmin.append(round(float(c['v_min']),4))
            vmax.append(round(float(c['v_max']),4))
        else:
            valuation.append(None)
            pr=projections.get(w)
            vmin.append(round(float(pr['v_min']),4) if pr else None)
            vmax.append(round(float(pr['v_max']),4) if pr else None)

    chart={
        'labels':labels,
        'valuation':valuation,
        'vmin':vmin,
        'vmax':vmax,
        'actual_labels':[f"{c['week_no']}주차" for c in cycles],
        'account':[round(float(c['account_total']),4) for c in cycles],
        'invested':[round(float(c['invested']),4) for c in cycles]
    }

    plan_view=[]
    for r in plan_rows:
        d=dict(r)
        pr=projections.get(int(r['week_no']))
        if d['cycle_id'] is None and pr:
            d['projected_v']=pr['v_value']
            d['projected_min']=pr['v_min']
            d['projected_max']=pr['v_max']
        else:
            d['projected_v']=None
            d['projected_min']=None
            d['projected_max']=None
        plan_view.append(d)

    pool_pct=tqqq_pct=0.0
    if latest and float(latest['account_total'])>0:
        pool_pct=float(latest['next_pool'])/float(latest['account_total'])*100
        tqqq_pct=float(latest['valuation'])/float(latest['account_total'])*100
    loc_orders=_loc_order_plan(latest,sug,s)
    return {'settings':s,'cycles':cycles,'latest':latest,'trades':trades,'suggested':sug,'chart':chart,'pool_pct':pool_pct,'tqqq_pct':tqqq_pct,'plan_rows':plan_view,'plan_total':plan_total,'plan_done':plan_done,'loc_orders':loc_orders}

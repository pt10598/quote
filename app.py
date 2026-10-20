"""Plano procurement pilot. Standard-library WSGI backend; demo data only."""
import os, json, sqlite3, secrets, hashlib, hmac, time
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server
from datetime import datetime, timezone

ROOT = Path(__file__).parent
DB = os.environ.get('DATABASE_PATH', str(ROOT / 'pilot.sqlite3'))
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if os.environ.get('DYNO') and not DATABASE_URL:
    raise RuntimeError('Heroku requires DATABASE_URL. Attach PostgreSQL before deploying.')
PRICE_TTL = int(os.environ.get('PRICE_TTL_SECONDS', '3600'))
STOCK_TTL = int(os.environ.get('STOCK_TTL_SECONDS', '900'))
DEMO = os.environ.get('DEMO_MODE', '1') == '1'
STORES = [dict(id='lowes-0505', name="Lowe’s · E. Plano #0505", address='5001 Central Expy, Plano, TX 75023', url='https://www.lowes.com/store/TX-Plano/0505'),dict(id='hd-6833',name='Home Depot · Central Plano #6833',address='1801 W Parker Rd, Plano, TX 75023',url='https://www.homedepot.com/l/Central-Plano/TX/Plano/75023/6833')]
PRODUCTS = [dict(id='ball-valve',name='Brass ball valve',spec='1/2 in · threaded · 1 each',category='Valves'),dict(id='pvc-elbow',name='PVC 90° elbow',spec='1/2 in · Schedule 40 · 1 each',category='Fittings'),dict(id='pvc-coupling',name='PVC coupling',spec='1/2 in · Schedule 40 · 1 each',category='Fittings'),dict(id='ptfe-tape',name='PTFE thread seal tape',spec='1/2 in × 260 in · 1 roll',category='Consumables'),dict(id='supply-line',name='Braided faucet supply line',spec='3/8 in comp × 1/2 in FIP · 20 in · 1 each',category='Supply lines'),dict(id='p-trap',name='Tubular P-trap kit',spec='1-1/2 in · polypropylene · 1 kit',category='Drain repair')]

class PostgresConnection:
    def __init__(self):
        import psycopg2
        self.connection=psycopg2.connect(DATABASE_URL, sslmode=os.environ.get('PGSSLMODE','require'), connect_timeout=10)
    def execute(self,sql,params=()):
        from psycopg2.extras import DictCursor
        sql=sql.replace('?', '%s')
        if 'INSERT OR IGNORE INTO' in sql:
            sql=sql.replace('INSERT OR IGNORE INTO','INSERT INTO')+' ON CONFLICT DO NOTHING'
        cursor=self.connection.cursor(cursor_factory=DictCursor);cursor.execute(sql,params);return cursor
    def executescript(self,sql):
        sql=sql.replace('INTEGER PRIMARY KEY','BIGSERIAL PRIMARY KEY').replace(' REAL',' DOUBLE PRECISION')
        for statement in sql.split(';'):
            if statement.strip():self.execute(statement)
    def __enter__(self):return self
    def __exit__(self,typ,value,tb):
        try:
            if typ:self.connection.rollback()
            else:self.connection.commit()
        finally:self.connection.close()

def db():
    if DATABASE_URL:return PostgresConnection()
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c

INTEGRITY_ERRORS=(sqlite3.IntegrityError,)
if DATABASE_URL:
    import psycopg2
    INTEGRITY_ERRORS+=(psycopg2.IntegrityError,)

def init():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,password TEXT,admin INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,csrf TEXT,expires REAL);
        CREATE TABLE IF NOT EXISTS lists(id INTEGER PRIMARY KEY,user_id INTEGER,name TEXT,zip TEXT,items TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS offers(product TEXT,store TEXT,price REAL,stock INTEGER,observed REAL,PRIMARY KEY(product,store));
        CREATE TABLE IF NOT EXISTS attempts(ip TEXT,at REAL);
        CREATE TABLE IF NOT EXISTS verified_quotes(product TEXT,store TEXT,payload TEXT,observed REAL,PRIMARY KEY(product,store));''')
        if DEMO:
            for i,p in enumerate(PRODUCTS):
                for j,s in enumerate(STORES):
                    c.execute('INSERT OR IGNORE INTO offers VALUES(?,?,?,?,?)',(p['id'],s['id'],round([12.98,0.89,0.69,1.49,7.98,9.98][i]*(1+(.12 if i%2==0 else -.08)*j),2),[14,32,8,0,19,6][i]+j*2,time.time()))
        admin_email=os.environ.get('ADMIN_EMAIL','').strip().lower(); admin_pass=os.environ.get('ADMIN_PASSWORD','')
        if admin_email and len(admin_pass)>=12:
            c.execute('INSERT OR IGNORE INTO users(email,password,admin) VALUES(?,?,1)',(admin_email,hash_password(admin_pass)))

def hash_password(p):
    salt=secrets.token_hex(16); return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),260000).hex()
def verify(p,stored):
    salt,value=stored.split(':'); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),260000).hex(),value)
def session(env):
    cookie=SimpleCookie()
    try: cookie.load(env.get('HTTP_COOKIE',''))
    except Exception: return None
    token=cookie.get('plano_session')
    if not token:return None
    with db() as c:
        row=c.execute('SELECT s.*,u.email,u.admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=? AND expires>?',(token.value,time.time())).fetchone()
    return dict(row) if row else None

def application(env,start):
    path=env.get('PATH_INFO','/'); method=env['REQUEST_METHOD']; user=session(env)
    def reply(data,status='200 OK',headers=None):
        raw=json.dumps(data).encode(); start(status,[('Content-Type','application/json'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]+(headers or [])); return [raw]
    if path=='/' and method=='GET':
        start('200 OK',[('Content-Type','text/html; charset=utf-8'),('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")]);return [(ROOT/'index.html').read_bytes()]
    if path=='/health':return reply({'ok':True,'mode':'demo' if DEMO else 'no-provider'})
    if not path.startswith('/api/'):return reply({'error':'Not found'},'404 Not Found')
    data={}
    if method=='POST':
        origin=env.get('HTTP_ORIGIN')
        if origin:
            from urllib.parse import urlparse
            if urlparse(origin).netloc != env.get('HTTP_HOST'):return reply({'error':'Origin rejected'},'403 Forbidden')
        try:
            length=int(env.get('CONTENT_LENGTH') or 0)
            if length>65536:return reply({'error':'Request too large'},'413 Payload Too Large')
            data=json.loads(env['wsgi.input'].read(length) or b'{}')
            if not isinstance(data,dict):raise ValueError()
        except (ValueError,TypeError):return reply({'error':'Invalid JSON'},'400 Bad Request')
        if path not in ('/api/login','/api/register') and (not user or not hmac.compare_digest(env.get('HTTP_X_CSRF_TOKEN',''),user['csrf'])):
            return reply({'error':'Sign in again'},'403 Forbidden')
    if path=='/api/me':return reply({'user':{'email':user['email'],'admin':bool(user['admin']),'csrf':user['csrf']} if user else None})
    if path in ('/api/register','/api/login') and method=='POST':
        email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
        if len(email)>254 or '@' not in email or len(password)<12 or len(password)>256:return reply({'error':'Enter an email and a password of 12–256 characters.'},'400 Bad Request')
        ip=env.get('REMOTE_ADDR','unknown')
        with db() as c:
            c.execute('DELETE FROM attempts WHERE at<?',(time.time()-900,))
            if c.execute('SELECT count(*) FROM attempts WHERE ip=?',(ip,)).fetchone()[0]>=15:return reply({'error':'Too many attempts. Try again in 15 minutes.'},'429 Too Many Requests')
            c.execute('INSERT INTO attempts VALUES(?,?)',(ip,time.time()))
        with db() as c:
            if path=='/api/register':
                try:c.execute('INSERT INTO users(email,password) VALUES(?,?)',(email,hash_password(password)))
                except INTEGRITY_ERRORS:return reply({'error':'Unable to register. Try signing in.'},'400 Bad Request')
            row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not row or not verify(password,row['password']):return reply({'error':'Invalid credentials'},'401 Unauthorized')
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,row['id'],csrf,time.time()+86400))
        secure='; Secure' if os.environ.get('COOKIE_SECURE')=='1' or os.environ.get('DYNO') else ''
        return reply({'ok':True},headers=[('Set-Cookie',f'plano_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400{secure}')])
    if path=='/api/logout' and method=='POST':
        with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(user['token'],))
        return reply({'ok':True},headers=[('Set-Cookie','plano_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax')])
    if path=='/api/catalog':
        products=PRODUCTS;stores=STORES
        with db() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM offers')] if DEMO else [json.loads(r[0]) for r in c.execute('SELECT payload FROM verified_quotes')]
        if not DEMO:
            products=list({r['product']:{'id':r['product'],'name':r['name'],'spec':r['spec'],'category':r.get('category','Plumbing')} for r in rows}.values())
            stores=list({r['store']:{'id':r['store'],'name':r['store_name'],'address':r['store_address'],'url':r['source_url']} for r in rows}.values())
        for r in rows:
            age=time.time()-r['observed'];r['price_stale']=age>PRICE_TTL;r['stock_stale']=age>STOCK_TTL
            r['observed_at']=datetime.fromtimestamp(r['observed'],timezone.utc).isoformat();r['source']='SIMULATED — NOT SUPPLIER DATA' if DEMO else r['source_type']
        return reply({'products':products,'stores':stores,'offers':rows,'demo':DEMO,'policy':{'price_seconds':PRICE_TTL,'stock_seconds':STOCK_TTL},'full_access':bool(user)})
    if path=='/api/lists':
        if not user:return reply({'error':'Sign in to save lists'},'401 Unauthorized')
        with db() as c:
            if method=='POST':
                items=data.get('items',[]); zipcode=str(data.get('zip',''))
                if zipcode not in ('75023','75024','75025','75074','75075','75093','75094'):return reply({'error':'Choose a supported Plano ZIP code'},'400 Bad Request')
                ids={p['id'] for p in PRODUCTS} if DEMO else {r[0] for r in c.execute('SELECT DISTINCT product FROM verified_quotes')}
                if not isinstance(items,list) or not 1<=len(items)<=50:return reply({'error':'Add 1–50 items'},'400 Bad Request')
                if any(not isinstance(x,dict) or x.get('id') not in ids or type(x.get('qty')) is not int or not 1<=x['qty']<=999 for x in items):return reply({'error':'Invalid items'},'400 Bad Request')
                c.execute('INSERT INTO lists(user_id,name,zip,items,created) VALUES(?,?,?,?,?)',(user['user_id'],str(data.get('name','My list'))[:100],zipcode,json.dumps(items),time.time()))
            rows=[dict(r) for r in c.execute('SELECT id,name,zip,items FROM lists WHERE user_id=? ORDER BY id DESC',(user['user_id'],))]
        for r in rows:r['items']=json.loads(r['items'])
        return reply({'lists':rows})
    if path=='/api/admin':
        if not user or not user['admin']:return reply({'error':'Admin access required'},'403 Forbidden')
        with db() as c:counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('users','lists','offers')}
        return reply({'counts':counts,'providers':[{'name':s['name'],'status':'Not connected — authorization pending'} for s in STORES],'price_ttl':PRICE_TTL,'stock_ttl':STOCK_TTL,'billing':'Not connected','email_otp':'Not connected; pilot uses password login'})
    return reply({'error':'Not found'},'404 Not Found')

if os.environ.get('SKIP_DB_INIT') != '1':
    init()
if __name__=='__main__':
    port=int(os.environ.get('PORT','8000')); print(f'Plano pilot: http://127.0.0.1:{port}')
    with make_server('127.0.0.1',port,application) as server:server.serve_forever()

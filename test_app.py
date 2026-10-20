import io,json,os,tempfile,unittest
_tmp=tempfile.TemporaryDirectory();os.environ['DATABASE_PATH']=_tmp.name+'/test.sqlite3'
import app
class Tests(unittest.TestCase):
 def call(self,path,body=None,cookie='',csrf=''):
  raw=json.dumps(body).encode() if body is not None else b'';r={}
  env={'PATH_INFO':path,'REQUEST_METHOD':'POST' if body is not None else 'GET','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_HOST':'localhost','HTTP_ORIGIN':'http://localhost','HTTP_COOKIE':cookie,'HTTP_X_CSRF_TOKEN':csrf,'REMOTE_ADDR':'127.0.0.1'}
  def start(s,h):r.update(status=int(s.split()[0]),headers=dict(h))
  raw=b''.join(app.application(env,start));r['body']=json.loads(raw) if path!='/' else raw;return r
 def account(self,email):
  r=self.call('/api/register',{'email':email,'password':'test-password-1234'});self.assertEqual(r['status'],200)
  c=r['headers']['Set-Cookie'].split(';')[0];return c,self.call('/api/me',cookie=c)['body']['user']['csrf']
 def test_demo_staleness(self):
  j=self.call('/api/catalog')['body'];self.assertTrue(j['demo']);self.assertEqual(len(j['offers']),12)
  with app.db() as c:c.execute('UPDATE offers SET observed=0')
  self.assertTrue(all(o['stock_stale'] for o in self.call('/api/catalog')['body']['offers']))
 def test_user_isolation_and_csrf(self):
  a,ca=self.account('a@example.test');b,cb=self.account('b@example.test');p={'name':'Job','zip':'75023','items':[{'id':'ball-valve','qty':3}]}
  self.assertEqual(self.call('/api/lists',p,a)['status'],403)
  self.assertEqual(self.call('/api/lists',p,a,ca)['status'],200)
  self.assertEqual(len(self.call('/api/lists',cookie=b)['body']['lists']),0)
  self.assertEqual(len(self.call('/api/lists',cookie=a)['body']['lists']),1)
  self.assertEqual(self.call('/api/admin',cookie=a)['status'],403)
  self.assertEqual(self.call('/api/lists',{**p,'zip':'10001'},a,ca)['status'],400)
  self.assertEqual(self.call('/api/lists',{**p,'items':[{'id':'ball-valve','qty':-1}]},a,ca)['status'],400)
  self.call('/api/logout',{},a,ca);self.assertIsNone(self.call('/api/me',cookie=a)['body']['user'])
 def test_invalid_login(self):self.assertEqual(self.call('/api/login',{'email':'none@example.test','password':'bad-password-123'})['status'],401)
 def test_page(self):self.assertIn(b'DEMO PILOT',self.call('/')['body'])
if __name__=='__main__':unittest.main()

class RealQuoteTests(unittest.TestCase):
 def test_live_excludes_demo_and_validates_identity(self):
  from import_quotes import import_rows
  old=app.DEMO;app.DEMO=False
  try:
   t=Tests();self.assertEqual(t.call('/api/catalog')['body']['offers'],[])
   row={'product':'verified-valve','name':'Verified valve','spec':'1/2 in threaded','model':'TEST-MODEL','store':'test-store','store_name':'Test store','store_address':'Plano test fixture','source_url':'https://example.com/valve','source_type':'api','match_key':'TEST-MODEL-1','currency':'USD','price_basis':'public','store_verified':True,'pack_quantity':1,'price':9.99,'stock':None,'observed_at':'2026-01-01T00:00:00Z'}
   with self.assertRaises(ValueError):import_rows([{**row,'store_verified':False}])
   self.assertEqual(import_rows([row]),1)
   result=t.call('/api/catalog')['body'];self.assertEqual(len(result['offers']),1);self.assertEqual(result['offers'][0]['price'],9.99);self.assertFalse(result['demo'])
   with self.assertRaises(ValueError):import_rows([{**row,'store':'other','model':'DIFFERENT'}])
  finally:app.DEMO=old

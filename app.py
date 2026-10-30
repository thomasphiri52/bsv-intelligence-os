"""BSV Intelligence OS V14 - Streamlit deployment entry point.

Run locally: streamlit run app.py
This is a prototype. See README.md before using real client data.
"""
import os, sqlite3, hashlib, secrets, hmac, io
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get('BSV_DB_PATH', str(BASE_DIR / 'bsv_intelligence.db'))
PLANS = {'Starter': 75000, 'Professional': 150000, 'Enterprise': 220000}

st.set_page_config(page_title='BSV Intelligence OS', page_icon='📊', layout='wide', initial_sidebar_state='expanded')


def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180000).hex()
    return salt + '$' + digest


def verify_password(password, stored):
    try:
        salt, digest = stored.split('$', 1)
        candidate = hash_password(password, salt).split('$', 1)[1]
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def init_db():
    con = connect()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,slug TEXT UNIQUE NOT NULL,plan TEXT NOT NULL DEFAULT 'Starter',subscription_status TEXT NOT NULL DEFAULT 'Trial',onboarding_status TEXT NOT NULL DEFAULT 'Pending',contact_email TEXT DEFAULT '',industry TEXT DEFAULT '',created_at TEXT DEFAULT '',next_billing_date TEXT DEFAULT '',monthly_fee REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'viewer',FOREIGN KEY(tenant_id) REFERENCES tenants(id));
    CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,name TEXT NOT NULL,company TEXT,email TEXT,phone TEXT,source TEXT,status TEXT DEFAULT 'New',value REAL DEFAULT 0,created_at TEXT NOT NULL,FOREIGN KEY(tenant_id) REFERENCES tenants(id));
    CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,name TEXT NOT NULL,channel TEXT,spend REAL DEFAULT 0,leads INTEGER DEFAULT 0,conversions INTEGER DEFAULT 0,status TEXT DEFAULT 'Active',created_at TEXT NOT NULL,FOREIGN KEY(tenant_id) REFERENCES tenants(id));
    CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,title TEXT NOT NULL,detail TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,user_id INTEGER,action TEXT NOT NULL,detail TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,title TEXT NOT NULL,owner TEXT,due_date TEXT,status TEXT DEFAULT 'Open',priority TEXT DEFAULT 'Normal',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,quote_number TEXT NOT NULL,customer TEXT NOT NULL,description TEXT,amount REAL DEFAULT 0,status TEXT DEFAULT 'Draft',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS automations(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,name TEXT NOT NULL,trigger_name TEXT NOT NULL,action_name TEXT NOT NULL,enabled INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS integrations(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,provider TEXT NOT NULL,status TEXT DEFAULT 'Not connected',notes TEXT);
    CREATE TABLE IF NOT EXISTS subscription_events(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,event_type TEXT NOT NULL,plan TEXT,amount REAL DEFAULT 0,note TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS onboarding_steps(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id INTEGER NOT NULL,step_key TEXT NOT NULL,completed INTEGER DEFAULT 0,updated_at TEXT NOT NULL,UNIQUE(tenant_id,step_key));
    ''')
    # Add V12 columns when upgrading a V1-V13 database.
    cols = {r['name'] for r in con.execute('PRAGMA table_info(tenants)').fetchall()}
    for col, definition in {'plan':"TEXT NOT NULL DEFAULT 'Starter'",'subscription_status':"TEXT NOT NULL DEFAULT 'Trial'",'onboarding_status':"TEXT NOT NULL DEFAULT 'Pending'",'contact_email':"TEXT DEFAULT ''",'industry':"TEXT DEFAULT ''",'created_at':"TEXT DEFAULT ''",'next_billing_date':"TEXT DEFAULT ''",'monthly_fee':'REAL DEFAULT 0'}.items():
        if col not in cols: con.execute(f'ALTER TABLE tenants ADD COLUMN {col} {definition}')
    if con.execute('SELECT COUNT(*) FROM tenants').fetchone()[0] == 0:
        con.execute("INSERT INTO tenants(name,slug,plan,subscription_status,created_at) VALUES('BSV Telecoms','bsv','Enterprise','Active',?)", (date.today().isoformat(),))
        con.execute("INSERT INTO tenants(name,slug,created_at) VALUES('Demo Client Ltd','demo-client',?)", (date.today().isoformat(),))
        bsv = con.execute("SELECT id FROM tenants WHERE slug='bsv'").fetchone()[0]
        client = con.execute("SELECT id FROM tenants WHERE slug='demo-client'").fetchone()[0]
        con.execute('INSERT INTO users(tenant_id,name,email,password_hash,role) VALUES(?,?,?,?,?)',(bsv,'BSV Administrator','admin@bsv.local',hash_password('ChangeMe123!'),'admin'))
        con.execute('INSERT INTO users(tenant_id,name,email,password_hash,role) VALUES(?,?,?,?,?)',(client,'Client Administrator','client@demo.local',hash_password('ChangeMe123!'),'admin'))
        for tenant, name, company, source, status, value in [(bsv,'Lerato Mokoena','Mokoena Holdings','Website','Qualified',85000),(bsv,'Sipho Dlamini','Dlamini Logistics','Referral','Proposal',125000),(client,'Jordan Smith','Acme Services','Website','Qualified',56000)]:
            con.execute('INSERT INTO leads(tenant_id,name,company,source,status,value,created_at) VALUES(?,?,?,?,?,?,?)',(tenant,name,company,source,status,value,date.today().isoformat()))
        con.execute('INSERT INTO campaigns(tenant_id,name,channel,spend,leads,conversions,status,created_at) VALUES(?,?,?,?,?,?,?,?)',(bsv,'Q4 Growth Campaign','Google Ads',12500,84,19,'Active',date.today().isoformat()))
    con.commit(); con.close()

init_db()


def query(sql, params=()):
    con=connect()
    try: return pd.read_sql_query(sql, con, params=params)
    finally: con.close()


def execute(sql, params=()):
    con=connect()
    try: con.execute(sql, params); con.commit()
    finally: con.close()


def is_platform_admin(user):
    return user['email'] == 'admin@bsv.local' and user['tenant_name'] == 'BSV Telecoms'


def money(v): return f'R{float(v or 0):,.2f}'


def login_screen():
    st.markdown('<div class="hero"><div class="eyebrow">BSV TELECOMS · BUSINESS INTELLIGENCE</div><h1>Intelligence OS</h1><p>Turn business data into measurable growth.</p></div>', unsafe_allow_html=True)
    with st.form('login_form'):
        email=st.text_input('Email', placeholder='you@company.com')
        password=st.text_input('Password', type='password')
        submitted=st.form_submit_button('Sign in', use_container_width=True)
    if submitted:
        u=query('SELECT users.*,tenants.name tenant_name FROM users JOIN tenants ON tenants.id=users.tenant_id WHERE lower(users.email)=lower(?)',(email.strip(),))
        if not u.empty and verify_password(password, u.iloc[0]['password_hash']):
            st.session_state.user={k:u.iloc[0][k] for k in ['id','tenant_id','name','email','role','tenant_name']}
            st.rerun()
        else: st.error('Email or password is incorrect.')
    st.caption('Demo: admin@bsv.local / ChangeMe123! · client@demo.local / ChangeMe123!')

st.markdown('''<style>
:root{color-scheme:dark} .stApp{background:radial-gradient(circle at 15% 0%,#142c50 0,#071426 38%,#050b16 100%);color:#edf6ff}
[data-testid="stSidebar"]{background:#08182b;border-right:1px solid #17456a} .block-container{padding-top:2rem;max-width:1500px}
.hero{padding:28px;border:1px solid #1b6488;border-radius:18px;background:linear-gradient(120deg,#0d2542,#0a172b);margin-bottom:24px}.hero h1{font-size:2.5rem;color:#e8f8ff;margin:8px 0}.hero p,.eyebrow{color:#71dfff}.eyebrow{letter-spacing:3px;font-size:.75rem}
[data-testid="stMetric"]{background:#0d2038;border:1px solid #174568;padding:16px;border-radius:14px}.stButton>button,.stDownloadButton>button{border:1px solid #21bce8;background:#10314e;color:#e9faff;border-radius:10px}.stButton>button:hover{border-color:#80eaff;color:white}.stTabs [data-baseweb="tab"]{color:#9fdcf2}
</style>''', unsafe_allow_html=True)

if 'user' not in st.session_state:
    login_screen(); st.stop()
user=st.session_state.user; tid=int(user['tenant_id']); platform_admin=is_platform_admin(user)
with st.sidebar:
    st.markdown('## ◈ BSV INTELLIGENCE OS')
    st.caption(f"{user['tenant_name']} · {user['role'].title()}")
    page=st.radio('WORKSPACE', ['Executive Dashboard','Leads & CRM','Campaign Intelligence','AI Business Advisor','Forecasting','Reports & Exports','Client Portal','Workspace Settings'] + (['Super Admin'] if platform_admin else []))
    if st.button('Sign out',use_container_width=True):
        del st.session_state.user; st.rerun()
    st.caption('V14 · AI Business Intelligence')

st.title(page)
st.caption(f"Welcome, {user['name']} · {date.today().strftime('%d %B %Y')}")
leads=query('SELECT * FROM leads WHERE tenant_id=? ORDER BY id DESC',(tid,))
campaigns=query('SELECT * FROM campaigns WHERE tenant_id=? ORDER BY id DESC',(tid,))

if page=='Executive Dashboard':
    total=len(leads); pipeline=leads.loc[~leads.status.isin(['Won','Lost']),'value'].sum() if total else 0
    won=int((leads.status=='Won').sum()) if total else 0; active=int((campaigns.status=='Active').sum()) if len(campaigns) else 0
    a,b,c,d=st.columns(4); a.metric('Total leads',total); b.metric('Open pipeline',money(pipeline)); c.metric('Won deals',won); d.metric('Active campaigns',active)
    st.subheader('Business performance')
    l,r=st.columns(2)
    with l:
        st.markdown('#### Lead pipeline');
        if total: st.bar_chart(leads.groupby('status').size())
        else: st.info('Add leads to see pipeline performance.')
    with r:
        st.markdown('#### Campaign spend');
        if len(campaigns): st.bar_chart(campaigns.groupby('channel')['spend'].sum())
        else: st.info('Add campaigns to see spend by channel.')
    st.markdown('#### Recent opportunities'); st.dataframe(leads.head(8),use_container_width=True,hide_index=True)

elif page=='Leads & CRM':
    with st.expander('＋ Add a lead',expanded=True):
        with st.form('new_lead'):
            x1,x2=st.columns(2); name=x1.text_input('Contact name'); company=x2.text_input('Company'); email=x1.text_input('Email'); phone=x2.text_input('Phone'); source=x1.selectbox('Source',['Website','Referral','Google Ads','Meta Ads','LinkedIn','Other']); status=x2.selectbox('Stage',['New','Qualified','Proposal','Won','Lost']); value=st.number_input('Opportunity value (ZAR)',min_value=0.0,step=1000.0)
            if st.form_submit_button('Save lead'):
                if name.strip(): execute('INSERT INTO leads(tenant_id,name,company,email,phone,source,status,value,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(tid,name,company,email,phone,source,status,value,date.today().isoformat())); st.success('Lead saved.'); st.rerun()
                else: st.error('Contact name is required.')
    st.dataframe(leads,use_container_width=True,hide_index=True)
    if len(leads): st.download_button('Export leads CSV',leads.to_csv(index=False).encode(), 'bsv_leads.csv','text/csv')

elif page=='Campaign Intelligence':
    with st.expander('＋ Add campaign',expanded=True):
        with st.form('new_campaign'):
            name=st.text_input('Campaign name'); channel=st.selectbox('Channel',['Google Ads','Meta Ads','LinkedIn','Email','Other']); x,y,z=st.columns(3); spend=x.number_input('Spend (ZAR)',min_value=0.0); nleads=y.number_input('Leads',min_value=0,step=1); conv=z.number_input('Conversions',min_value=0,step=1)
            if st.form_submit_button('Save campaign'):
                if name.strip(): execute('INSERT INTO campaigns(tenant_id,name,channel,spend,leads,conversions,status,created_at) VALUES(?,?,?,?,?,?,?,?)',(tid,name,channel,spend,int(nleads),int(conv),'Active',date.today().isoformat())); st.success('Campaign saved.'); st.rerun()
                else: st.error('Campaign name is required.')
    if len(campaigns):
        campaigns=campaigns.copy(); campaigns['cost_per_conversion']=campaigns.apply(lambda r:r.spend/r.conversions if r.conversions else None,axis=1)
        st.dataframe(campaigns,use_container_width=True,hide_index=True); st.bar_chart(campaigns.set_index('name')[['spend','leads','conversions']])
    else: st.info('No campaign data yet.')

elif page=='AI Business Advisor':
    st.info('V14 decision support uses transparent calculations and business rules. It is not a connected generative AI model.')
    insights=[]; total=len(leads); qualified=int(leads.status.isin(['Qualified','Proposal']).sum()) if total else 0; spend=float(campaigns.spend.sum()) if len(campaigns) else 0; conv=int(campaigns.conversions.sum()) if len(campaigns) else 0
    if total==0: insights.append(('Start capturing demand','Add your first leads so the platform can establish a baseline.'))
    elif qualified/total<.25: insights.append(('Improve lead quality',f'Only {qualified/total:.0%} of recorded leads are qualified or at proposal stage. Review targeting and qualification.'))
    else: insights.append(('Protect sales momentum',f'{qualified/total:.0%} of leads are qualified or at proposal stage. Prioritise follow-up on high-value opportunities.'))
    if spend and conv: insights.append(('Review acquisition efficiency',f'Current recorded cost per conversion is {money(spend/conv)}. Compare this with gross profit per new customer.'))
    elif spend: insights.append(('Check conversion tracking',f'{money(spend)} in campaign spend is recorded but there are no conversions. Validate tracking before raising budgets.'))
    if total: insights.append(('Pipeline concentration',f'The average recorded opportunity value is {money(leads.value.mean())}. Review unusually large opportunities individually.'))
    for title,body in insights: st.markdown(f'### ✦ {title}'); st.write(body)
    st.caption('Recommendations are based only on the data entered in this workspace; they are not guaranteed forecasts.')

elif page=='Forecasting':
    st.subheader('Sales pipeline outlook')
    if len(leads):
        open_leads=leads[~leads.status.isin(['Won','Lost'])]; weighted=float(open_leads.value.sum())
        st.metric('Unweighted open pipeline',money(weighted)); st.metric('Qualified/proposal value',money(open_leads.loc[open_leads.status.isin(['Qualified','Proposal']),'value'].sum()))
        st.write('Pipeline by stage'); st.bar_chart(open_leads.groupby('status').value.sum())
        st.warning('This is a pipeline snapshot, not a time-series prediction. Reliable forecasting needs dated historical sales and conversion outcomes.')
    else: st.info('Add opportunity records before forecasting.')

elif page=='Reports & Exports':
    st.subheader('Workspace performance report')
    st.metric('Recorded opportunity value',money(leads.value.sum() if len(leads) else 0)); st.metric('Campaign investment',money(campaigns.spend.sum() if len(campaigns) else 0))
    st.write('Lead status');
    if len(leads): st.dataframe(leads.groupby('status').agg(records=('id','count'),opportunity_value=('value','sum')).reset_index(),use_container_width=True,hide_index=True)
    st.write('Campaign channel');
    if len(campaigns): st.dataframe(campaigns.groupby('channel').agg(campaigns=('id','count'),spend=('spend','sum'),leads=('leads','sum'),conversions=('conversions','sum')).reset_index(),use_container_width=True,hide_index=True)
    if len(leads): st.download_button('Download lead report',leads.to_csv(index=False).encode(),'lead_report.csv','text/csv')
    if len(campaigns): st.download_button('Download campaign report',campaigns.to_csv(index=False).encode(),'campaign_report.csv','text/csv')

elif page=='Client Portal':
    st.subheader('Your workspace at a glance'); st.write(f"**Workspace:** {user['tenant_name']}")
    st.write(f"**Account role:** {user['role'].title()}")
    st.write('Your portal data is filtered to the signed-in workspace.'); st.dataframe(leads.head(10),use_container_width=True,hide_index=True)

elif page=='Workspace Settings':
    st.write('Change your account password')
    with st.form('change_password'):
        old=st.text_input('Current password',type='password'); new=st.text_input('New password',type='password'); confirm=st.text_input('Confirm new password',type='password')
        if st.form_submit_button('Update password'):
            rec=query('SELECT password_hash FROM users WHERE id=?',(user['id'],))
            if not rec.empty and verify_password(old,rec.iloc[0].password_hash) and len(new)>=12 and new==confirm:
                execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(new),user['id'])); st.success('Password updated.')
            else: st.error('Check your current password; new passwords must match and contain at least 12 characters.')
    st.caption('For production, configure managed secrets, HTTPS, MFA, rate limiting, backups and a privacy review.')

elif page=='Super Admin':
    if not platform_admin: st.error('Platform owner access required.'); st.stop()
    tenants=query('SELECT t.*,COUNT(DISTINCT u.id) users,(SELECT COUNT(*) FROM leads l WHERE l.tenant_id=t.id) leads FROM tenants t LEFT JOIN users u ON u.tenant_id=t.id GROUP BY t.id ORDER BY t.id')
    active=int((tenants.subscription_status=='Active').sum()); mrr=float(tenants.loc[tenants.subscription_status=='Active','monthly_fee'].sum())
    a,b,c=st.columns(3); a.metric('Client workspaces',len(tenants)); b.metric('Active subscriptions',active); c.metric('Indicative MRR',money(mrr))
    st.dataframe(tenants,use_container_width=True,hide_index=True)
    st.markdown('#### Update client subscription')
    with st.form('subscription'):
        opts={f"{r['name']} (#{r['id']})":int(r['id']) for _,r in tenants.iterrows()}; chosen=st.selectbox('Workspace',list(opts)); plan=st.selectbox('Plan',list(PLANS)); status=st.selectbox('Status',['Trial','Active','Past due','Suspended','Cancelled']); fee=st.number_input('Monthly fee (ZAR)',min_value=0.0,step=500.0)
        if st.form_submit_button('Save subscription record'):
            tenant_id=opts[chosen]; execute('UPDATE tenants SET plan=?,subscription_status=?,monthly_fee=? WHERE id=?',(plan,status,fee,tenant_id)); execute('INSERT INTO subscription_events(tenant_id,event_type,plan,amount,note,created_at) VALUES(?,?,?,?,?,?)', (tenant_id,'Admin update',plan,fee,'Updated through Streamlit V14',datetime.now().isoformat(timespec='seconds'))); st.success('Subscription record updated. No payment was collected.'); st.rerun()
    st.caption('Subscription records are administrative only. No payment gateway or automated billing is connected.')

st.divider()
st.caption('BSV Intelligence OS V14 · Streamlit edition · Prototype — validate security and runtime before production deployment.')

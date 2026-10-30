import os, csv, io, sqlite3, hashlib, secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, g

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BSV_DB_PATH", os.path.join(APP_DIR, "bsv_intelligence.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("BSV_SECRET_KEY", "CHANGE-THIS-SECRET-KEY-BEFORE-DEPLOYMENT")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def pw_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()
    return salt + "$" + digest

def pw_ok(password, stored):
    try:
        salt, digest = stored.split("$", 1)
        return secrets.compare_digest(pw_hash(password, salt).split("$", 1)[1], digest)
    except Exception:
        return False

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS tenants (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'viewer',
      FOREIGN KEY(tenant_id) REFERENCES tenants(id)
    );
    CREATE TABLE IF NOT EXISTS leads (
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, name TEXT NOT NULL,
      company TEXT, email TEXT, phone TEXT, source TEXT, status TEXT DEFAULT 'New',
      value REAL DEFAULT 0, created_at TEXT NOT NULL,
      FOREIGN KEY(tenant_id) REFERENCES tenants(id)
    );
    CREATE TABLE IF NOT EXISTS campaigns (
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, name TEXT NOT NULL,
      channel TEXT, spend REAL DEFAULT 0, leads INTEGER DEFAULT 0, conversions INTEGER DEFAULT 0,
      status TEXT DEFAULT 'Active', created_at TEXT NOT NULL,
      FOREIGN KEY(tenant_id) REFERENCES tenants(id)
    );
    CREATE TABLE IF NOT EXISTS activities (
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, title TEXT NOT NULL,
      detail TEXT, created_at TEXT NOT NULL, FOREIGN KEY(tenant_id) REFERENCES tenants(id)
    );
    """)
    if con.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0:
        con.execute("INSERT INTO tenants(name,slug) VALUES (?,?)", ("BSV Telecoms", "bsv"))
        con.execute("INSERT INTO tenants(name,slug) VALUES (?,?)", ("Demo Client Ltd", "demo-client"))
        bsv = con.execute("SELECT id FROM tenants WHERE slug='bsv'").fetchone()[0]
        client = con.execute("SELECT id FROM tenants WHERE slug='demo-client'").fetchone()[0]
        con.execute("INSERT INTO users(tenant_id,name,email,password_hash,role) VALUES (?,?,?,?,?)",
                    (bsv,"BSV Administrator","admin@bsv.local",pw_hash("ChangeMe123!"),"admin"))
        con.execute("INSERT INTO users(tenant_id,name,email,password_hash,role) VALUES (?,?,?,?,?)",
                    (client,"Client Administrator","client@demo.local",pw_hash("ChangeMe123!"),"admin"))
        today = date.today().isoformat()
        sample_leads = [
          (bsv,"Lerato Mokoena","Mokoena Holdings","lerato@example.com","0710000001","Website","Qualified",85000),
          (bsv,"Sipho Dlamini","Dlamini Logistics","sipho@example.com","0710000002","Referral","Proposal",125000),
          (bsv,"Amara Nkosi","Nkosi Retail","amara@example.com","0710000003","Google Ads","New",42000),
          (client,"Jordan Smith","Acme Services","jordan@example.com","0720000001","Website","Qualified",56000),
        ]
        for row in sample_leads:
            con.execute("""INSERT INTO leads(tenant_id,name,company,email,phone,source,status,value,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""", (row[0],*row[1:],today))
        sample_campaigns = [
          (bsv,"Q4 Growth Campaign","Google Ads",12500,84,19,"Active"),
          (bsv,"Brand Awareness","LinkedIn",6800,42,7,"Active"),
          (client,"Lead Generation Sprint","Meta Ads",4500,31,8,"Active"),
        ]
        for row in sample_campaigns:
            con.execute("""INSERT INTO campaigns(tenant_id,name,channel,spend,leads,conversions,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?)""", (row[0],*row[1:],today))
        con.commit()
    con.close()

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def current_user():
    if not session.get("user_id"):
        return None
    return db().execute("""SELECT users.*, tenants.name AS tenant_name FROM users
                           JOIN tenants ON tenants.id=users.tenant_id WHERE users.id=?""",
                        (session["user_id"],)).fetchone()

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and pw_ok(password, user["password_hash"]):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    u = current_user()
    tid = u["tenant_id"]
    leads = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=?", (tid,)).fetchone()["n"]
    pipeline = db().execute("SELECT COALESCE(SUM(value),0) n FROM leads WHERE tenant_id=? AND status NOT IN ('Won','Lost')", (tid,)).fetchone()["n"]
    campaigns = db().execute("SELECT COUNT(*) n FROM campaigns WHERE tenant_id=? AND status='Active'", (tid,)).fetchone()["n"]
    won = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=? AND status='Won'", (tid,)).fetchone()["n"]
    total = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=?", (tid,)).fetchone()["n"]
    conversion = (won / total * 100) if total else 0
    recent = db().execute("SELECT * FROM leads WHERE tenant_id=? ORDER BY id DESC LIMIT 5", (tid,)).fetchall()
    channel_rows = db().execute("SELECT channel, SUM(spend) spend, SUM(leads) leads FROM campaigns WHERE tenant_id=? GROUP BY channel", (tid,)).fetchall()
    return render_template("dashboard.html", leads=leads, pipeline=pipeline, campaigns=campaigns,
                           conversion=conversion, recent=recent, channels=channel_rows)

@app.route("/leads", methods=["GET","POST"])
@login_required
def leads():
    tid = current_user()["tenant_id"]
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if name:
            db().execute("""INSERT INTO leads(tenant_id,name,company,email,phone,source,status,value,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                         (tid,name,request.form.get("company",""),request.form.get("email",""),
                          request.form.get("phone",""),request.form.get("source","Other"),
                          request.form.get("status","New"),float(request.form.get("value") or 0),date.today().isoformat()))
            db().commit()
            flash("Lead added successfully.", "success")
        return redirect(url_for("leads"))
    rows = db().execute("SELECT * FROM leads WHERE tenant_id=? ORDER BY id DESC", (tid,)).fetchall()
    return render_template("leads.html", leads=rows)

@app.route("/leads/<int:lead_id>/status", methods=["POST"])
@login_required
def lead_status(lead_id):
    db().execute("UPDATE leads SET status=? WHERE id=? AND tenant_id=?",
                 (request.form.get("status"),lead_id,current_user()["tenant_id"]))
    db().commit()
    return redirect(url_for("leads"))

@app.route("/campaigns", methods=["GET","POST"])
@login_required
def campaigns():
    tid = current_user()["tenant_id"]
    if request.method == "POST":
        db().execute("""INSERT INTO campaigns(tenant_id,name,channel,spend,leads,conversions,status,created_at)
                        VALUES (?,?,?,?,?,?,?,?)""",
                     (tid,request.form.get("name","Campaign"),request.form.get("channel","Other"),
                      float(request.form.get("spend") or 0),int(request.form.get("leads") or 0),
                      int(request.form.get("conversions") or 0),request.form.get("status","Active"),date.today().isoformat()))
        db().commit()
        flash("Campaign saved.", "success")
        return redirect(url_for("campaigns"))
    rows = db().execute("SELECT * FROM campaigns WHERE tenant_id=? ORDER BY id DESC", (tid,)).fetchall()
    return render_template("campaigns.html", campaigns=rows)

@app.route("/advisor")
@login_required
def advisor():
    tid = current_user()["tenant_id"]
    total = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=?", (tid,)).fetchone()["n"]
    qualified = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=? AND status IN ('Qualified','Proposal')", (tid,)).fetchone()["n"]
    spend = db().execute("SELECT COALESCE(SUM(spend),0) n FROM campaigns WHERE tenant_id=?", (tid,)).fetchone()["n"]
    conv = db().execute("SELECT COALESCE(SUM(conversions),0) n FROM campaigns WHERE tenant_id=?", (tid,)).fetchone()["n"]
    insights = []
    if total == 0:
        insights.append("Add your first lead to begin building a useful sales picture.")
    if total and qualified / total < .25:
        insights.append("Fewer than 25% of recorded leads are qualified. Review lead targeting and qualification criteria.")
    if spend > 0 and conv == 0:
        insights.append("Campaign spend is recorded but no conversions are entered. Verify tracking before increasing budget.")
    elif spend > 0 and conv > 0:
        insights.append(f"Recorded campaign cost per conversion is R{spend/conv:,.2f}. Compare this with your customer acquisition target.")
    if total and qualified / total >= .25:
        insights.append("Your qualified/proposal lead share is at least 25%. Prioritise follow-up on high-value opportunities.")
    insights.append("These are rule-based prototype insights, not generated AI predictions. Connect verified data and an approved AI provider for advanced analysis.")
    return render_template("advisor.html", insights=insights)

@app.route("/reports")
@login_required
def reports():
    tid = current_user()["tenant_id"]
    lead_stats = db().execute("SELECT COUNT(*) total, COALESCE(SUM(value),0) value, SUM(CASE WHEN status='Won' THEN 1 ELSE 0 END) won, SUM(CASE WHEN status='Qualified' OR status='Proposal' THEN 1 ELSE 0 END) qualified FROM leads WHERE tenant_id=?", (tid,)).fetchone()
    campaign_stats = db().execute("SELECT COUNT(*) campaigns, COALESCE(SUM(spend),0) spend, COALESCE(SUM(leads),0) leads, COALESCE(SUM(conversions),0) conversions FROM campaigns WHERE tenant_id=?", (tid,)).fetchone()
    return render_template("reports.html", tid=tid, lead_stats=lead_stats, campaign_stats=campaign_stats)

@app.route("/portal")
@login_required
def client_portal():
    """Self-service workspace portal: users see only their own tenant's data."""
    u = current_user(); tid = u['tenant_id']
    tenant = db().execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    leads = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=?", (tid,)).fetchone()['n']
    pipeline = db().execute("SELECT COALESCE(SUM(value),0) n FROM leads WHERE tenant_id=? AND status NOT IN ('Won','Lost')", (tid,)).fetchone()['n']
    won = db().execute("SELECT COUNT(*) n FROM leads WHERE tenant_id=? AND status='Won'", (tid,)).fetchone()['n']
    campaigns = db().execute("SELECT * FROM campaigns WHERE tenant_id=? ORDER BY id DESC LIMIT 6", (tid,)).fetchall()
    recent = db().execute("SELECT * FROM leads WHERE tenant_id=? ORDER BY id DESC LIMIT 6", (tid,)).fetchall()
    return render_template('portal.html', tenant=tenant, leads=leads, pipeline=pipeline, won=won, campaigns=campaigns, recent=recent)

@app.route("/export/campaigns.csv")
@login_required
def export_campaigns():
    rows = db().execute("SELECT name,channel,spend,leads,conversions,status,created_at FROM campaigns WHERE tenant_id=? ORDER BY id", (current_user()['tenant_id'],)).fetchall()
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(['name','channel','spend','leads','conversions','status','created_at'])
    writer.writerows([tuple(r) for r in rows])
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=bsv_campaigns_export.csv'})

@app.route("/export/leads.csv")
@login_required
def export_leads():
    rows = db().execute("SELECT name,company,email,phone,source,status,value,created_at FROM leads WHERE tenant_id=? ORDER BY id",
                        (current_user()["tenant_id"],)).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["name","company","email","phone","source","status","value","created_at"])
    writer.writerows([tuple(r) for r in rows])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=bsv_leads_export.csv"})

@app.route("/import/leads", methods=["POST"])
@login_required
def import_leads():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Choose a CSV file.", "error")
        return redirect(url_for("leads"))
    try:
        content = f.stream.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            name = (row.get("name") or row.get("Name") or "").strip()
            if not name:
                continue
            db().execute("""INSERT INTO leads(tenant_id,name,company,email,phone,source,status,value,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                         (current_user()["tenant_id"],name,row.get("company",""),row.get("email",""),
                          row.get("phone",""),row.get("source","CSV"),row.get("status","New"),
                          float(row.get("value") or 0),date.today().isoformat()))
        db().commit()
        flash("CSV import completed.", "success")
    except Exception as e:
        db().rollback()
        flash("Import failed. Check the CSV columns and numeric value field.", "error")
    return redirect(url_for("leads"))

@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        password = request.form.get("password","")
        if name:
            db().execute("UPDATE users SET name=? WHERE id=?", (name,session["user_id"]))
        if password:
            if len(password) < 10:
                flash("Use a password of at least 10 characters.", "error")
                return redirect(url_for("settings"))
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash(password),session["user_id"]))
        db().commit()
        flash("Account settings updated.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html")


# V2-V11 extension schema. Safe to run repeatedly against an existing V1 database.
def init_extended_schema():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, user_id INTEGER, action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, title TEXT NOT NULL, owner TEXT, due_date TEXT, status TEXT DEFAULT 'Open', priority TEXT DEFAULT 'Normal', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, quote_number TEXT NOT NULL, customer TEXT NOT NULL, description TEXT, amount REAL DEFAULT 0, status TEXT DEFAULT 'Draft', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS automations(id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, name TEXT NOT NULL, trigger_name TEXT NOT NULL, action_name TEXT NOT NULL, enabled INTEGER DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS integrations(id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, provider TEXT NOT NULL, status TEXT DEFAULT 'Not connected', notes TEXT);
    """)
    for tid, provider in con.execute("SELECT id, 'Google Ads' FROM tenants UNION SELECT id, 'Meta Ads' FROM tenants UNION SELECT id, 'Email' FROM tenants").fetchall():
        if not con.execute("SELECT 1 FROM integrations WHERE tenant_id=? AND provider=?", (tid,provider)).fetchone():
            con.execute("INSERT INTO integrations(tenant_id,provider,status,notes) VALUES (?,?,?,?)", (tid,provider,'Not connected','Connector setup required'))
    con.commit(); con.close()

init_extended_schema()

# V12 SaaS administration schema (safe to run on existing installations).
def init_v12_schema():
    con = sqlite3.connect(DB_PATH)
    cols = {r[1] for r in con.execute("PRAGMA table_info(tenants)")}
    migrations = {
        "plan": "TEXT NOT NULL DEFAULT 'Starter'",
        "subscription_status": "TEXT NOT NULL DEFAULT 'Trial'",
        "onboarding_status": "TEXT NOT NULL DEFAULT 'Pending'",
        "contact_email": "TEXT DEFAULT ''",
        "industry": "TEXT DEFAULT ''",
        "created_at": "TEXT DEFAULT ''",
        "next_billing_date": "TEXT DEFAULT ''",
        "monthly_fee": "REAL DEFAULT 0"
    }
    for col, definition in migrations.items():
        if col not in cols:
            con.execute(f"ALTER TABLE tenants ADD COLUMN {col} {definition}")
    con.execute("UPDATE tenants SET created_at=? WHERE created_at IS NULL OR created_at=''", (date.today().isoformat(),))
    con.executescript("""
    CREATE TABLE IF NOT EXISTS subscription_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL,
      event_type TEXT NOT NULL, plan TEXT, amount REAL DEFAULT 0,
      note TEXT, created_at TEXT NOT NULL,
      FOREIGN KEY(tenant_id) REFERENCES tenants(id)
    );
    CREATE TABLE IF NOT EXISTS onboarding_steps(
      id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL,
      step_key TEXT NOT NULL, completed INTEGER DEFAULT 0,
      updated_at TEXT NOT NULL, UNIQUE(tenant_id,step_key),
      FOREIGN KEY(tenant_id) REFERENCES tenants(id)
    );
    """)
    con.execute("UPDATE tenants SET plan='Enterprise', subscription_status='Active' WHERE slug='bsv' AND plan='Starter'")
    con.commit(); con.close()

init_v12_schema()

@app.before_request
def v12_csrf_guard():
    if request.method == 'POST':
        token = session.get('_csrf_token')
        supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
        if not token or not supplied or not secrets.compare_digest(token, supplied):
            return 'Security token missing or invalid. Refresh the page and try again.', 400

@app.context_processor
def inject_csrf():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return {'csrf_token': session['_csrf_token']}

app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

def log_action(action, detail=''):
    u = current_user()
    if u:
        db().execute("INSERT INTO audit_logs(tenant_id,user_id,action,detail,created_at) VALUES (?,?,?,?,?)",
                     (u['tenant_id'],u['id'],action,detail,datetime.now().isoformat(timespec='seconds')))
        db().commit()

def admin_required():
    u = current_user()
    if not u or u['role'] not in ('admin','owner'):
        flash('Administrator permission is required.', 'error')
        return False
    return True

@app.route('/roadmap')
@login_required
def roadmap():
    stages = [
      ('V1','Intelligence Core','Dashboard, CRM, campaigns, CSV data and workspace login','Delivered'),
      ('V2','Multi-client Workspace','Tenant-aware client workspaces and client provisioning','Prototype'),
      ('V3','People & Permissions','Team accounts, roles and access management','Prototype'),
      ('V4','Governance & Audit','Activity history and accountability logs','Prototype'),
      ('V5','Workflow Management','Tasks, owners, due dates and priorities','Prototype'),
      ('V6','Commercial Operations','Quotes, proposal values and deal tracking','Prototype'),
      ('V7','Revenue Intelligence','Revenue records, pipeline and campaign cost metrics','Foundation'),
      ('V8','Integration Hub','Connector catalogue and connection readiness','Foundation'),
      ('V9','AI Decision Support','Rule-based insights with an AI integration path','Prototype'),
      ('V10','Automation Centre','Configurable automation rules and workflow triggers','Prototype'),
      ('V11','Enterprise Control','Platform health, tenant governance and SaaS readiness','Foundation'),
      ('V12','Super Admin & SaaS Management','Platform command centre, subscription controls, onboarding and security foundations','Prototype'),
      ('V13','Client Portal & Reporting','Self-service workspace portal, KPI summaries and campaign exports','Prototype')]
    return render_template('roadmap.html', stages=stages)

@app.route('/clients', methods=['GET','POST'])
@login_required
def clients():
    u=current_user()
    if u['tenant_name'] != 'BSV Telecoms' or u['role'] not in ('admin','owner'):
        flash('Only the BSV platform administrator can provision client workspaces.', 'error')
        return redirect(url_for('dashboard'))
    if request.method=='POST':
        name=request.form.get('name','').strip(); slug=request.form.get('slug','').strip().lower().replace(' ','-')
        if name and slug:
            try:
                db().execute('INSERT INTO tenants(name,slug) VALUES (?,?)',(name,slug)); db().commit()
                tid=db().execute('SELECT id FROM tenants WHERE slug=?',(slug,)).fetchone()['id']
                db().execute('INSERT INTO users(tenant_id,name,email,password_hash,role) VALUES (?,?,?,?,?)',
                             (tid,request.form.get('admin_name','Client Admin'),request.form.get('email','').lower(),pw_hash(request.form.get('password','ChangeMe123!')),'admin'))
                db().commit(); log_action('Client workspace created',name); flash('Client workspace and administrator created.','success')
            except sqlite3.IntegrityError:
                db().rollback(); flash('Workspace slug or email already exists.','error')
        return redirect(url_for('clients'))
    rows=db().execute('SELECT tenants.*, COUNT(users.id) user_count FROM tenants LEFT JOIN users ON users.tenant_id=tenants.id GROUP BY tenants.id ORDER BY tenants.id').fetchall()
    return render_template('management.html', title='Client workspaces', subtitle='Provision and oversee customer environments.', mode='clients', rows=rows)

@app.route('/team', methods=['GET','POST'])
@login_required
def team():
    if not admin_required(): return redirect(url_for('dashboard'))
    tid=current_user()['tenant_id']
    if request.method=='POST':
        try:
            db().execute('INSERT INTO users(tenant_id,name,email,password_hash,role) VALUES (?,?,?,?,?)',
                         (tid,request.form.get('name',''),request.form.get('email','').lower(),pw_hash(request.form.get('password','ChangeMe123!')),request.form.get('role','viewer')))
            db().commit(); log_action('Team member created',request.form.get('email','')); flash('Team member created. Share the temporary password securely.','success')
        except sqlite3.IntegrityError:
            db().rollback(); flash('That email address is already registered.','error')
        return redirect(url_for('team'))
    rows=db().execute('SELECT id,name,email,role FROM users WHERE tenant_id=? ORDER BY id',(tid,)).fetchall()
    return render_template('management.html',title='Team & permissions',subtitle='Manage accounts in your workspace.',mode='team',rows=rows)

@app.route('/tasks', methods=['GET','POST'])
@login_required
def tasks():
    tid=current_user()['tenant_id']
    if request.method=='POST':
        db().execute('INSERT INTO tasks(tenant_id,title,owner,due_date,status,priority,created_at) VALUES (?,?,?,?,?,?,?)',
                     (tid,request.form.get('title',''),request.form.get('owner',''),request.form.get('due_date',''),request.form.get('status','Open'),request.form.get('priority','Normal'),date.today().isoformat()))
        db().commit(); log_action('Task created',request.form.get('title','')); flash('Task created.','success'); return redirect(url_for('tasks'))
    rows=db().execute('SELECT * FROM tasks WHERE tenant_id=? ORDER BY id DESC',(tid,)).fetchall()
    return render_template('management.html',title='Workflow & tasks',subtitle='Turn business priorities into assigned work.',mode='tasks',rows=rows)

@app.route('/quotes', methods=['GET','POST'])
@login_required
def quotes():
    tid=current_user()['tenant_id']
    if request.method=='POST':
        n='BSV-Q-'+datetime.now().strftime('%y%m%d%H%M%S')
        db().execute('INSERT INTO quotes(tenant_id,quote_number,customer,description,amount,status,created_at) VALUES (?,?,?,?,?,?,?)',
                     (tid,n,request.form.get('customer',''),request.form.get('description',''),float(request.form.get('amount') or 0),request.form.get('status','Draft'),date.today().isoformat()))
        db().commit(); log_action('Quote created',n); flash('Quote record saved. This is not yet a tax invoice or legally approved quote document.','success'); return redirect(url_for('quotes'))
    rows=db().execute('SELECT * FROM quotes WHERE tenant_id=? ORDER BY id DESC',(tid,)).fetchall()
    return render_template('management.html',title='Quotes & commercial records',subtitle='Record indicative customer proposals and quote values.',mode='quotes',rows=rows)

@app.route('/integrations', methods=['GET','POST'])
@login_required
def integrations():
    tid=current_user()['tenant_id']
    if request.method=='POST':
        provider=request.form.get('provider','')
        db().execute("UPDATE integrations SET status='Setup requested', notes=? WHERE tenant_id=? AND provider=?",(request.form.get('notes','Connector credentials and authorization still required'),tid,provider))
        db().commit(); log_action('Integration setup requested',provider); flash('Setup request recorded. No external account has been connected.','success'); return redirect(url_for('integrations'))
    rows=db().execute('SELECT * FROM integrations WHERE tenant_id=? ORDER BY provider',(tid,)).fetchall()
    return render_template('management.html',title='Integration hub',subtitle='Track planned connections. API access is not enabled in this prototype.',mode='integrations',rows=rows)

@app.route('/automations', methods=['GET','POST'])
@login_required
def automations():
    tid=current_user()['tenant_id']
    if request.method=='POST':
        db().execute('INSERT INTO automations(tenant_id,name,trigger_name,action_name,enabled,created_at) VALUES (?,?,?,?,1,?)',
                     (tid,request.form.get('name',''),request.form.get('trigger_name',''),request.form.get('action_name',''),date.today().isoformat()))
        db().commit(); log_action('Automation rule drafted',request.form.get('name','')); flash('Automation rule saved in draft catalogue. It does not execute external actions yet.','success'); return redirect(url_for('automations'))
    rows=db().execute('SELECT * FROM automations WHERE tenant_id=? ORDER BY id DESC',(tid,)).fetchall()
    return render_template('management.html',title='Automation centre',subtitle='Define trigger-to-action workflows for future activation.',mode='automations',rows=rows)

@app.route('/audit')
@login_required
def audit():
    rows=db().execute('SELECT audit_logs.*, users.name actor FROM audit_logs LEFT JOIN users ON users.id=audit_logs.user_id WHERE audit_logs.tenant_id=? ORDER BY audit_logs.id DESC LIMIT 100',(current_user()['tenant_id'],)).fetchall()
    return render_template('management.html',title='Audit trail',subtitle='Recent recorded actions in this workspace.',mode='audit',rows=rows)

@app.route('/enterprise')
@login_required
def enterprise():
    u=current_user(); tid=u['tenant_id']
    stats={
      'users':db().execute('SELECT COUNT(*) n FROM users WHERE tenant_id=?',(tid,)).fetchone()['n'],
      'tasks':db().execute('SELECT COUNT(*) n FROM tasks WHERE tenant_id=?',(tid,)).fetchone()['n'],
      'quotes':db().execute('SELECT COUNT(*) n FROM quotes WHERE tenant_id=?',(tid,)).fetchone()['n'],
      'rules':db().execute('SELECT COUNT(*) n FROM automations WHERE tenant_id=?',(tid,)).fetchone()['n']}
    return render_template('enterprise.html',stats=stats)


# V12: platform-level controls are restricted to the seeded BSV platform owner.
def super_admin_required():
    u = current_user()
    if not u or u['email'] != 'admin@bsv.local' or u['tenant_name'] != 'BSV Telecoms':
        flash('This area is restricted to the BSV platform administrator.', 'error')
        return False
    return True

@app.route('/super-admin', methods=['GET','POST'])
@login_required
def super_admin():
    if not super_admin_required(): return redirect(url_for('dashboard'))
    if request.method == 'POST':
        tenant_id = request.form.get('tenant_id', type=int)
        plan = request.form.get('plan', 'Starter')
        status = request.form.get('subscription_status', 'Trial')
        fee = request.form.get('monthly_fee', type=float) or 0
        allowed_plans = {'Starter','Professional','Enterprise'}
        allowed_status = {'Trial','Active','Past due','Suspended','Cancelled'}
        if plan not in allowed_plans or status not in allowed_status or fee < 0:
            flash('Check the selected plan, status and monthly fee.', 'error')
        else:
            row = db().execute('SELECT id FROM tenants WHERE id=?', (tenant_id,)).fetchone()
            if row:
                db().execute('UPDATE tenants SET plan=?,subscription_status=?,monthly_fee=? WHERE id=?', (plan,status,fee,tenant_id))
                db().execute('INSERT INTO subscription_events(tenant_id,event_type,plan,amount,note,created_at) VALUES (?,?,?,?,?,?)',
                             (tenant_id,'Plan/status updated',plan,fee,'Manually updated by platform administrator',datetime.now().isoformat(timespec='seconds')))
                db().commit(); log_action('SaaS subscription updated', f'Tenant {tenant_id}: {plan} / {status}')
                flash('Workspace subscription settings updated. No payment was collected.', 'success')
        return redirect(url_for('super_admin'))
    tenants = db().execute("SELECT t.*, COUNT(DISTINCT u.id) user_count, (SELECT COUNT(*) FROM leads l WHERE l.tenant_id=t.id) lead_count FROM tenants t LEFT JOIN users u ON u.tenant_id=t.id GROUP BY t.id ORDER BY t.id").fetchall()
    stats = {
      'tenants': db().execute('SELECT COUNT(*) n FROM tenants').fetchone()['n'],
      'active': db().execute("SELECT COUNT(*) n FROM tenants WHERE subscription_status='Active'").fetchone()['n'],
      'trial': db().execute("SELECT COUNT(*) n FROM tenants WHERE subscription_status='Trial'").fetchone()['n'],
      'mrr': db().execute("SELECT COALESCE(SUM(monthly_fee),0) n FROM tenants WHERE subscription_status='Active'").fetchone()['n']}
    return render_template('super_admin.html', tenants=tenants, stats=stats)

@app.route('/onboarding', methods=['GET','POST'])
@login_required
def onboarding():
    u=current_user(); tid=u['tenant_id']
    if u['role'] not in ('admin','owner'):
        flash('Workspace administrator access is required.', 'error')
        return redirect(url_for('dashboard'))
    steps = [('profile','Confirm company profile'),('team','Invite or confirm your team'),('data','Add your first leads or campaigns'),('review','Review workspace settings')]
    if request.method == 'POST':
        if request.form.get('action') == 'profile':
            name=request.form.get('name','').strip()
            email=request.form.get('contact_email','').strip()
            industry=request.form.get('industry','').strip()
            if name and email:
                db().execute('UPDATE tenants SET name=?,contact_email=?,industry=? WHERE id=?',(name,email,industry,tid))
                db().execute("INSERT OR REPLACE INTO onboarding_steps(tenant_id,step_key,completed,updated_at) VALUES (?,?,1,?)",(tid,'profile',datetime.now().isoformat(timespec='seconds')))
                db().commit(); flash('Company profile saved.','success')
            else: flash('Company name and contact email are required.','error')
        elif request.form.get('step') in ('team','data','review'):
            key=request.form.get('step')
            db().execute('INSERT OR REPLACE INTO onboarding_steps(tenant_id,step_key,completed,updated_at) VALUES (?,?,?,?)',(tid,key,1 if request.form.get('completed')=='yes' else 0,datetime.now().isoformat(timespec='seconds')))
            db().commit()
            flash('Onboarding progress updated.','success')
        done=db().execute('SELECT COUNT(*) n FROM onboarding_steps WHERE tenant_id=? AND completed=1',(tid,)).fetchone()['n']
        db().execute('UPDATE tenants SET onboarding_status=? WHERE id=?',('Complete' if done>=4 else 'In progress',tid)); db().commit()
        return redirect(url_for('onboarding'))
    tenant=db().execute('SELECT * FROM tenants WHERE id=?',(tid,)).fetchone()
    completed={r['step_key']:bool(r['completed']) for r in db().execute('SELECT * FROM onboarding_steps WHERE tenant_id=?',(tid,)).fetchall()}
    return render_template('onboarding.html',tenant=tenant,steps=steps,completed=completed)

@app.route('/subscription-events')
@login_required
def subscription_events():
    if not super_admin_required(): return redirect(url_for('dashboard'))
    rows=db().execute('SELECT e.*,t.name tenant_name FROM subscription_events e JOIN tenants t ON t.id=e.tenant_id ORDER BY e.id DESC LIMIT 100').fetchall()
    return render_template('management.html',title='Subscription history',subtitle='Manual plan and billing administration events. No payment gateway is connected.',mode='subscription_events',rows=rows)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)

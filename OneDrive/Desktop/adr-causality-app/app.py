"""
ADR Causality Assessment System - Flask Backend
Mobile PWA for Adverse Drug Reaction reporting and causality assessment.
Supports OCR scanning of IPC ADR forms via Google Cloud Vision + Gemini.
"""
import os
import json
import base64
import tempfile
import traceback
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
print("DEBUG: Environment variables loaded. GEMINI_API_KEY present:", bool(os.environ.get('GEMINI_API_KEY')))

from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, send_file, flash, session
from flask_cors import CORS
from flask_login import LoginManager, current_user, login_user, login_required, logout_user
from sqlalchemy import inspect, or_, text
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from database.models import User, AdminActionLog

# Google Cloud credentials from environment variable (for Render deployment)
google_creds_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if google_creds_json:
    creds_dict = json.loads(google_creds_json)
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(creds_dict, tmp)
    tmp.close()
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = tmp.name

from config import Config
from database import db, init_db
from database.models import ADRReport, SuspectedMedication, ConcomitantMedication, ModelTrainingLog, ReportAttachment, UserActivityLog, LoginAttempt, ReportRevision
from ml.naranjo import calculate_naranjo_score, NARANJO_QUESTIONS, extract_naranjo_features_from_report
from ml.who_umc import assess_who_umc, assess_from_api_payload, WHO_UMC_CATEGORIES, run_assessment

# Configure Gemini (new google.genai SDK)
try:
    from google import genai
    from google.genai import types
    gemini_client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY', ''))
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False
    gemini_client = None

# Configure Google Cloud Vision (Disabled in favor of Gemini Multimodal OCR)
VISION_AVAILABLE = False


app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'


@app.after_request
def add_no_store_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def _is_admin_user(user):
    return bool(user and getattr(user, 'role', '').lower() == 'admin')


def admin_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapped(*args, **kwargs):
        if not _is_admin_user(current_user):
            return render_template('403.html'), 403
        return view_function(*args, **kwargs)

    return wrapped

# Initialize database
init_db(app)


def _ensure_user_schema():
    inspector = inspect(db.engine)
    if 'users' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('users')}
    dialect_name = db.engine.dialect.name
    alter_statements = []

    if 'email' not in existing_columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN email VARCHAR(120)')
    if 'role' not in existing_columns:
        if dialect_name == 'postgresql':
            alter_statements.append("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'")
        else:
            alter_statements.append("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
    if 'created_at' not in existing_columns:
        if dialect_name == 'postgresql':
            alter_statements.append('ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP')
        else:
            alter_statements.append('ALTER TABLE users ADD COLUMN created_at DATETIME')
    if 'last_login' not in existing_columns:
        if dialect_name == 'postgresql':
            alter_statements.append('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP')
        else:
            alter_statements.append('ALTER TABLE users ADD COLUMN last_login DATETIME')

    for statement in alter_statements:
        db.session.execute(text(statement))
    if alter_statements:
        db.session.commit()

    # Backfill legacy records so login and duplicate checks remain safe.
    db.session.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''"))
    db.session.execute(text("UPDATE users SET email = username || '@local.invalid' WHERE email IS NULL OR email = ''"))
    db.session.commit()


def _ensure_report_schema():
    """Add user_id FK column to adr_reports if missing, backfill existing rows."""
    inspector = inspect(db.engine)
    if 'adr_reports' not in inspector.get_table_names():
        return

    existing_columns = {column['name'] for column in inspector.get_columns('adr_reports')}
    dialect_name = db.engine.dialect.name

    if 'user_id' not in existing_columns:
        if dialect_name == 'postgresql':
            db.session.execute(text('ALTER TABLE adr_reports ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)'))
        else:
            db.session.execute(text('ALTER TABLE adr_reports ADD COLUMN user_id INTEGER REFERENCES users(id)'))
        db.session.commit()

        # Backfill: assign orphan reports to the first admin user
        admin_user = User.query.filter_by(role='admin').first()
        if admin_user:
            db.session.execute(text(f'UPDATE adr_reports SET user_id = {admin_user.id} WHERE user_id IS NULL'))
            db.session.commit()


def _bootstrap_admin_account():
    print("[BOOTSTRAP] Starting admin account bootstrapping...")
    admin_username = app.config.get('ADMIN_USERNAME')
    admin_email = app.config.get('ADMIN_EMAIL')
    admin_password = app.config.get('ADMIN_PASSWORD')
    admin_password_hash = app.config.get('ADMIN_PASSWORD_HASH')

    print(f"[BOOTSTRAP] Config retrieved: Username={admin_username}, Email={admin_email}, HasPassword={bool(admin_password)}, HasPasswordHash={bool(admin_password_hash)}")

    if not admin_username or (not admin_password and not admin_password_hash):
        print("[BOOTSTRAP] Skipping admin bootstrap: missing username or password/hash in environment.")
        return

    if not admin_email:
        admin_email = f'{admin_username}@local.invalid'

    try:
        admin_user = User.query.filter((User.username == admin_username) | (User.email == admin_email)).first()
        if admin_user:
            print(f"[BOOTSTRAP] Admin user found in DB: ID={admin_user.id}, Username={admin_user.username}, Email={admin_user.email}, Role={admin_user.role}")
            changed = False
            if admin_user.role != 'admin':
                print(f"[BOOTSTRAP] Promoting user role from '{admin_user.role}' to 'admin'")
                admin_user.role = 'admin'
                changed = True
            if not admin_user.email:
                admin_user.email = admin_email
                changed = True
            # Always re-sync password from env so Render restarts pick up changes
            if admin_password_hash:
                if admin_user.password_hash != admin_password_hash:
                    print("[BOOTSTRAP] Updating password hash from ADMIN_PASSWORD_HASH env var.")
                    admin_user.password_hash = admin_password_hash
                    changed = True
            elif admin_password:
                if not admin_user.check_password(admin_password):
                    print("[BOOTSTRAP] Password check failed for existing user. Updating password hash from ADMIN_PASSWORD env var.")
                    admin_user.password_hash = generate_password_hash(admin_password)
                    changed = True
            if changed:
                db.session.commit()
                print("[BOOTSTRAP] Existing admin user details updated and committed successfully.")
            else:
                print("[BOOTSTRAP] No changes needed for existing admin user.")
            return

        print(f"[BOOTSTRAP] Admin user '{admin_username}' does not exist. Creating new admin user...")
        admin_user = User(
            username=admin_username,
            email=admin_email,
            display_name=app.config.get('ADMIN_DISPLAY_NAME', 'ADR Administrator'),
            department=app.config.get('ADMIN_DEPARTMENT', 'Pharmacovigilance Unit'),
            role='admin',
        )
        if admin_password_hash:
            admin_user.password_hash = admin_password_hash
        else:
            admin_user.password_hash = generate_password_hash(admin_password)

        db.session.add(admin_user)
        db.session.commit()
        print("[BOOTSTRAP] New admin user created and committed successfully.")
    except Exception as e:
        print(f"[BOOTSTRAP] Error bootstrapping admin account: {e}")
        import traceback
        traceback.print_exc()


def _get_user_by_identifier(identifier):
    if not identifier:
        return None
    normalized = identifier.strip()
    return User.query.filter((User.username == normalized) | (User.email == normalized)).first()


def _login_user_and_redirect(user, next_url):
    login_user(user, remember=True)
    session.permanent = True
    user.last_login = datetime.utcnow()
    try:
        attempt = LoginAttempt(
            identifier=user.username,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            is_successful=True
        )
        db.session.add(attempt)
    except Exception as e:
        print(f"Error logging login attempt: {e}")
    db.session.commit()
    flash('Signed in successfully.', 'success')
    return redirect(_safe_next_url(next_url))

# Ensure directories exist
os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)

# Invite link serializer (48-hour expiry)
invite_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

with app.app_context():
    _ensure_user_schema()
    _bootstrap_admin_account()
    _ensure_report_schema()


def _safe_next_url(next_url):
    if next_url and next_url.startswith('/'):
        return next_url
    return url_for('index')


def log_activity(action, report_id=None, details=None):
    """Log user activity to database for auditing."""
    try:
        user_id = current_user.id if (current_user and current_user.is_authenticated) else None
        if not user_id:
            return
        log = UserActivityLog(
            user_id=user_id,
            action=action,
            report_id=report_id,
            details=details,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Failed to log activity: {e}")


# ==================== PAGE ROUTES ====================


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    error_message = None
    if request.method == 'POST':
        identifier = (request.form.get('identifier') or request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        next_url = request.form.get('next') or request.args.get('next')

        user = _get_user_by_identifier(identifier)
        if user and user.check_password(password):
            if not user.password_hash.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                user.set_password(password)
                db.session.commit()
            return _login_user_and_redirect(user, next_url)

        # Log failed attempt
        try:
            attempt = LoginAttempt(
                identifier=identifier,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                is_successful=False
            )
            db.session.add(attempt)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error logging failed login attempt: {e}")

        error_message = 'Invalid username or password.'
        flash(error_message, 'error')

    return render_template('login.html', error_message=error_message, active_tab='login')


@app.route('/register', methods=['GET'])
def register_page():
    return render_template('login.html', active_tab='signup')


@app.route('/signup', methods=['POST'])
def signup():

    display_name = (request.form.get('display_name') or '').strip()
    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    department = (request.form.get('department') or '').strip()
    password = request.form.get('password') or ''

    if not all([display_name, username, email, department, password]):
        flash('All fields are required.', 'error')
        return redirect(url_for('register_page'))

    if len(password) < 4:
        flash('Password must be at least 4 characters.', 'error')
        return redirect(url_for('register_page'))

    existing_username = User.query.filter_by(username=username).first()
    if existing_username:
        flash('Username already exists. Please choose another.', 'error')
        return redirect(url_for('register_page'))

    existing_email = User.query.filter_by(email=email).first()
    if existing_email:
        flash('Email already exists. Please use another email.', 'error')
        return redirect(url_for('register_page'))

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        display_name=display_name,
        department=department,
        role='user',  # SECURITY: public signup NEVER creates admins
    )
    db.session.add(user)
    db.session.commit()

    flash('Account created successfully. Please sign in.', 'success')
    return redirect(url_for('login', tab='login'))


@app.route('/logout')
def logout():
    if current_user and current_user.is_authenticated:
        log_activity('logout')
    session.clear()
    logout_user()
    return redirect(url_for('login'))


@app.errorhandler(403)
def forbidden(_error):
    return render_template('403.html'), 403

@app.route('/')
@login_required
def index():
    """Dashboard / Home page."""
    log_activity('view_dashboard')
    today_date = datetime.utcnow().date()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if current_user.is_admin:
        total_reports = ADRReport.query.count()
        serious_reports = ADRReport.query.filter_by(is_serious=True).count()
        recent_reports = ADRReport.query.order_by(ADRReport.created_at.desc()).limit(7).all()
        who_certain_count = ADRReport.query.filter_by(who_umc_category='Certain').count()
        naranjo_probable_count = ADRReport.query.filter_by(naranjo_category='Probable').count()
        this_month_count = ADRReport.query.filter(ADRReport.created_at >= month_start).count()
    else:
        total_reports = ADRReport.query.filter_by(user_id=current_user.id).count()
        serious_reports = ADRReport.query.filter_by(user_id=current_user.id, is_serious=True).count()
        recent_reports = ADRReport.query.filter_by(user_id=current_user.id).order_by(ADRReport.created_at.desc()).limit(7).all()
        who_certain_count = ADRReport.query.filter_by(user_id=current_user.id, who_umc_category='Certain').count()
        naranjo_probable_count = ADRReport.query.filter_by(user_id=current_user.id, naranjo_category='Probable').count()
        this_month_count = ADRReport.query.filter_by(user_id=current_user.id).filter(ADRReport.created_at >= month_start).count()

    return render_template('index.html',
                           total_reports=total_reports,
                           serious_reports=serious_reports,
                           who_certain_count=who_certain_count,
                           naranjo_probable_count=naranjo_probable_count,
                           this_month_count=this_month_count,
                           today_date=today_date,
                           yesterday_date=today_date - timedelta(days=1),
                           recent_reports=recent_reports)


@app.route('/form')
@login_required
def adr_form():
    """ADR Reporting Form page."""
    return render_template('form.html')


@app.route('/reports')
@login_required
def reports_list():
    """View ADR reports — scoped by ownership."""
    page = request.args.get('page', 1, type=int)
    scope = request.args.get('scope', 'mine')  # 'mine' or 'all'
    per_page = 20
    log_activity('view_reports', details=f"scope={scope}")

    if scope == 'all' and current_user.is_admin:
        query = ADRReport.query
    else:
        scope = 'mine'
        query = ADRReport.query.filter_by(user_id=current_user.id)

    reports = query.order_by(ADRReport.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('reports.html', reports=reports, scope=scope)


@app.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    """View a single ADR report with causality assessment."""
    report = ADRReport.query.get_or_404(report_id)
    log_activity('view_report', report_id=report_id)
    if not (current_user.is_admin or report.user_id == current_user.id):
        from flask import abort
        abort(403)
    can_modify = current_user.is_admin or report.user_id == current_user.id
    return render_template('report_detail.html', report=report, can_modify=can_modify)


@app.route('/report/<int:report_id>/edit')
@login_required
def edit_report_page(report_id):
    """Edit report page."""
    report = ADRReport.query.get_or_404(report_id)
    if not (current_user.is_admin or report.user_id == current_user.id):
        from flask import abort
        abort(403)
    return render_template('form.html', edit_report_id=report_id)


@app.route('/analytics')
@login_required
def analytics():
    """Analytics dashboard."""
    return render_template('analytics.html')


@app.route('/naranjo')
@login_required
def naranjo_page():
    """Naranjo scale calculator page."""
    return render_template('naranjo.html', questions=NARANJO_QUESTIONS)


@app.route('/capture')
@login_required
def capture():
    """Camera capture page for scanning ADR forms."""
    return render_template('capture.html')


@app.route('/admin')
@admin_required
def admin_dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    recent_reports = ADRReport.query.order_by(ADRReport.created_at.desc()).limit(10).all()

    # Per-user report counts
    report_count_rows = db.session.query(
        ADRReport.user_id, db.func.count(ADRReport.id)
    ).group_by(ADRReport.user_id).all()
    report_counts = {uid: cnt for uid, cnt in report_count_rows}

    # Audit logs
    audit_logs = AdminActionLog.query.order_by(AdminActionLog.performed_at.desc()).limit(30).all()
    user_activity_logs = UserActivityLog.query.order_by(UserActivityLog.timestamp.desc()).limit(30).all()
    login_attempts = LoginAttempt.query.order_by(LoginAttempt.attempted_at.desc()).limit(30).all()

    invite_url = session.pop('invite_url', None)

    return render_template(
        'admin_dashboard.html',
        users=users,
        recent_reports=recent_reports,
        total_users=len(users),
        admin_users=len([user for user in users if user.role == 'admin']),
        regular_users=len([user for user in users if user.role != 'admin']),
        report_counts=report_counts,
        audit_logs=audit_logs,
        user_activity_logs=user_activity_logs,
        login_attempts=login_attempts,
        invite_url=invite_url
    )


@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
@admin_required
def update_user_role(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return render_template('403.html'), 403

    # SECURITY: require admin's own password to confirm privilege changes
    admin_password = (request.form.get('admin_password') or '').strip()
    if not admin_password or not current_user.check_password(admin_password):
        flash('Incorrect admin password. Role change denied.', 'error')
        return redirect(url_for('admin_dashboard'))

    new_role = (request.form.get('role') or '').strip().lower()
    if new_role not in {'user', 'admin'}:
        flash('Invalid role selected.', 'error')
        return redirect(url_for('admin_dashboard'))

    if user.id == current_user.id:
        flash('You cannot change your own role from this page.', 'error')
        return redirect(url_for('admin_dashboard'))

    old_role = user.role
    user.role = new_role

    # Audit log
    action = 'grant_admin' if new_role == 'admin' else 'revoke_admin'
    log_entry = AdminActionLog(
        admin_user_id=current_user.id,
        action=action,
        target_user_id=user.id,
        details=f'Role changed from {old_role} to {new_role}',
    )
    db.session.add(log_entry)
    db.session.commit()
    flash(f'Updated {user.display_name} to {new_role} role.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/invite', methods=['POST'])
@admin_required
def admin_invite():
    """Generate a time-limited invite link to grant admin role."""
    target_email = (request.form.get('invite_email') or '').strip().lower()
    admin_password = (request.form.get('admin_password') or '').strip()

    if not target_email:
        flash('Email address is required.', 'error')
        return redirect(url_for('admin_dashboard'))

    if not admin_password or not current_user.check_password(admin_password):
        flash('Incorrect admin password. Invite denied.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Generate signed token (48hr expiry)
    token = invite_serializer.dumps({'email': target_email, 'inviter_id': current_user.id}, salt='admin-invite')
    invite_url = url_for('accept_admin_invite', token=token, _external=True)

    # Audit log
    log_entry = AdminActionLog(
        admin_user_id=current_user.id,
        action='invite_sent',
        target_email=target_email,
        details=f'Admin invite link generated for {target_email}',
    )
    db.session.add(log_entry)
    db.session.commit()

    flash(f'Invite link generated for {target_email}. Share it securely — expires in 48 hours.', 'success')
    session['invite_url'] = invite_url
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/accept-invite/<token>')
@login_required
def accept_admin_invite(token):
    """Accept an admin invite link — promotes the logged-in user."""
    try:
        data = invite_serializer.loads(token, salt='admin-invite', max_age=48 * 3600)  # 48hr expiry
    except SignatureExpired:
        flash('This invite link has expired (48-hour limit).', 'error')
        return redirect(url_for('index'))
    except BadSignature:
        flash('Invalid invite link.', 'error')
        return redirect(url_for('index'))

    invited_email = data.get('email', '').lower()
    if current_user.email.lower() != invited_email:
        flash(f'This invite was issued for {invited_email}. Please log in with that account.', 'error')
        return redirect(url_for('index'))

    if current_user.role == 'admin':
        flash('You already have admin privileges.', 'info')
        return redirect(url_for('admin_dashboard'))

    current_user.role = 'admin'

    # Audit log
    log_entry = AdminActionLog(
        admin_user_id=data.get('inviter_id', current_user.id),
        action='invite_accepted',
        target_user_id=current_user.id,
        target_email=invited_email,
        details=f'{current_user.display_name} accepted admin invite',
    )
    db.session.add(log_entry)
    db.session.commit()

    flash('You have been promoted to admin! Welcome.', 'success')
    return redirect(url_for('admin_dashboard'))


# ==================== API ROUTES ====================

@app.route('/api/submit-report', methods=['POST'])
@login_required
def submit_report():
    """Submit a new ADR report."""
    try:
        data = request.get_json()

        # Create main report (linked to current user)
        report = ADRReport(
            user_id=current_user.id,
            case_type=data.get('case_type'),
            reg_no=data.get('reg_no'),
            amc_report_no=data.get('amc_report_no'),
            worldwide_unique_no=data.get('worldwide_unique_no'),
            patient_initials=data.get('patient_initials'),
            patient_age=data.get('patient_age'),
            patient_dob=data.get('patient_dob'),
            gender=data.get('gender'),
            weight_kg=float(data['weight_kg']) if data.get('weight_kg') else None,
            reaction_start_date=data.get('reaction_start_date'),
            reaction_stop_date=data.get('reaction_stop_date'),
            reaction_description=data.get('reaction_description'),
            relevant_investigations=data.get('relevant_investigations'),
            medical_history=data.get('medical_history'),
            is_serious=data.get('is_serious', False),
            seriousness_death=data.get('seriousness_death', False),
            seriousness_death_date=data.get('seriousness_death_date'),
            seriousness_life_threatening=data.get('seriousness_life_threatening', False),
            seriousness_hospitalization=data.get('seriousness_hospitalization', False),
            seriousness_congenital_anomaly=data.get('seriousness_congenital_anomaly', False),
            seriousness_disability=data.get('seriousness_disability', False),
            seriousness_other=data.get('seriousness_other', False),
            outcome=data.get('outcome'),
            additional_info=data.get('additional_info'),
            reporter_name=data.get('reporter_name'),
            reporter_address=data.get('reporter_address'),
            reporter_pin=data.get('reporter_pin'),
            reporter_email=data.get('reporter_email'),
            reporter_contact=data.get('reporter_contact'),
            reporter_occupation=data.get('reporter_occupation'),
            report_date=data.get('report_date'),
        )

        # Add suspected medications
        for med_data in data.get('medications', []):
            med = SuspectedMedication(
                serial_no=med_data.get('serial_no'),
                drug_name=med_data.get('drug_name'),
                manufacturer=med_data.get('manufacturer'),
                batch_no=med_data.get('batch_no'),
                expiry_date=med_data.get('expiry_date'),
                dose=med_data.get('dose'),
                route=med_data.get('route'),
                frequency=med_data.get('frequency'),
                therapy_start_date=med_data.get('therapy_start_date'),
                therapy_stop_date=med_data.get('therapy_stop_date'),
                indication=med_data.get('indication'),
                action_taken=med_data.get('action_taken'),
                reintroduction_result=med_data.get('reintroduction_result'),
                reintroduction_dose=med_data.get('reintroduction_dose'),
                causality_assessment=med_data.get('causality_assessment'),
            )
            report.medications.append(med)

        # Add concomitant medications
        for con_data in data.get('concomitant_medications', []):
            con = ConcomitantMedication(
                serial_no=con_data.get('serial_no'),
                drug_name=con_data.get('drug_name'),
                dose=con_data.get('dose'),
                route=con_data.get('route'),
                frequency=con_data.get('frequency'),
                therapy_start_date=con_data.get('therapy_start_date'),
                therapy_stop_date=con_data.get('therapy_stop_date'),
                indication=con_data.get('indication'),
            )
            report.concomitant_medications.append(con)

        # Auto-assess causality for each medication individually and save per-drug details
        severity_order = [
            "Certain",
            "Probable/Likely",
            "Possible",
            "Unlikely",
            "Conditional/Unclassified",
            "Unassessable/Unclassifiable",
        ]
        naranjo_order = ["Definite", "Probable", "Possible", "Doubtful"]

        best_who_category = "Unassessable/Unclassifiable"
        best_who_rank = len(severity_order)
        
        best_naranjo_score = -10
        best_naranjo_category = "Doubtful"
        best_naranjo_rank = len(naranjo_order)

        report_dict = data.copy()

        for idx, med in enumerate(report.medications):
            if not med.drug_name:
                continue
            
            # 1. WHO-UMC causality
            who_res = run_assessment(report_dict, med.drug_name)
            who_cat = who_res.get('category', 'Unassessable/Unclassifiable')
            who_score = who_res.get('score', 0)
            
            # 2. Naranjo causality
            if idx == 0 and data.get('naranjo_answers'):
                naranjo_answers = data.get('naranjo_answers')
            else:
                naranjo_answers = extract_naranjo_features_from_report(report_dict, med.drug_name)
                
            naranjo_res = calculate_naranjo_score(naranjo_answers)
            n_cat = naranjo_res.get('category', 'Doubtful')
            n_score = naranjo_res.get('score', 0)
            
            # Save on SuspectedMedication model
            med.causality_assessment = f"WHO-UMC: {who_cat} (Score: {who_score}) | Naranjo: {n_cat} (Score: {n_score})"
            
            # Track best/worst-case WHO-UMC
            who_rank = severity_order.index(who_cat) if who_cat in severity_order else len(severity_order)
            if who_rank < best_who_rank:
                best_who_rank = who_rank
                best_who_category = who_cat
                
            # Track best/worst-case Naranjo
            n_rank = naranjo_order.index(n_cat) if n_cat in naranjo_order else len(naranjo_order)
            if n_rank < best_naranjo_rank:
                best_naranjo_rank = n_rank
                best_naranjo_category = n_cat
            if n_score > best_naranjo_score:
                best_naranjo_score = n_score

        # Save the worst-case summary on the report level
        report.who_umc_category = best_who_category
        report.naranjo_score = best_naranjo_score if best_naranjo_score != -10 else None
        report.naranjo_category = best_naranjo_category

        db.session.add(report)

        # Link attachment if present
        attachment_id = data.get('attachment_id')
        if attachment_id:
            attachment = ReportAttachment.query.get(attachment_id)
            if attachment and attachment.uploaded_by_id == current_user.id:
                attachment.report = report

        db.session.commit()

        # Log creation
        log_activity('create_report', report_id=report.id)

        return jsonify({
            'success': True,
            'report_id': report.id,
            'who_umc_category': report.who_umc_category,
            'naranjo_score': report.naranjo_score,
            'naranjo_category': report.naranjo_category,
        })

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/reports', methods=['GET'])
@login_required
def get_reports():
    """Get all reports as JSON."""
    log_activity('view_reports_api')
    if current_user.is_admin:
        reports = ADRReport.query.order_by(ADRReport.created_at.desc()).all()
    else:
        reports = ADRReport.query.filter_by(user_id=current_user.id).order_by(ADRReport.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reports])


@app.route('/api/report/<int:report_id>', methods=['GET'])
@login_required
def get_report(report_id):
    """Get a single report."""
    report = ADRReport.query.get_or_404(report_id)
    if not (current_user.is_admin or report.user_id == current_user.id):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    log_activity('view_report_api', report_id=report_id)
    return jsonify(report.to_dict())


@app.route('/api/report/<int:report_id>', methods=['PUT'])
@login_required
def update_report(report_id):
    """Update an existing ADR report, creating a revision history log."""
    report = ADRReport.query.get_or_404(report_id)
    if not (current_user.is_admin or report.user_id == current_user.id):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    try:
        data = request.get_json()

        # Step 1: Capture previous state as JSON
        previous_state_dict = report.to_dict()
        previous_state_json = json.dumps(previous_state_dict)

        # Step 2: Determine what fields changed for the change summary
        changes = []
        
        # Simple fields mapping
        fields = [
            'case_type', 'reg_no', 'amc_report_no', 'worldwide_unique_no',
            'patient_initials', 'patient_age', 'gender', 'weight_kg',
            'reaction_start_date', 'reaction_stop_date', 'reaction_description',
            'relevant_investigations', 'medical_history', 'is_serious',
            'seriousness_death', 'seriousness_life_threatening', 'seriousness_hospitalization',
            'seriousness_congenital_anomaly', 'seriousness_disability', 'seriousness_other',
            'outcome', 'additional_info', 'reporter_name', 'reporter_address',
            'reporter_pin', 'reporter_email', 'reporter_contact', 'reporter_occupation',
            'report_date'
        ]
        
        for field in fields:
            if field in data:
                new_val = data[field]
                if field == 'weight_kg' and new_val is not None:
                    try:
                        new_val = float(new_val)
                    except ValueError:
                        new_val = None
                old_val = getattr(report, field)
                if old_val != new_val:
                    setattr(report, field, new_val)
                    changes.append(field)

        # Update suspected medications
        if 'medications' in data:
            old_med_names = [m.drug_name for m in report.medications if m.drug_name]
            
            # Delete old suspected medications
            for med in list(report.medications):
                db.session.delete(med)
            
            for med_data in data['medications']:
                med = SuspectedMedication(
                    serial_no=med_data.get('serial_no'),
                    drug_name=med_data.get('drug_name'),
                    manufacturer=med_data.get('manufacturer'),
                    batch_no=med_data.get('batch_no'),
                    expiry_date=med_data.get('expiry_date'),
                    dose=med_data.get('dose'),
                    route=med_data.get('route'),
                    frequency=med_data.get('frequency'),
                    therapy_start_date=med_data.get('therapy_start_date'),
                    therapy_stop_date=med_data.get('therapy_stop_date'),
                    indication=med_data.get('indication'),
                    action_taken=med_data.get('action_taken'),
                    reintroduction_result=med_data.get('reintroduction_result'),
                    reintroduction_dose=med_data.get('reintroduction_dose'),
                )
                report.medications.append(med)
            
            new_med_names = [m.drug_name for m in report.medications if m.drug_name]
            if set(old_med_names) != set(new_med_names):
                changes.append('medications')

        # Update concomitant medications
        if 'concomitant_medications' in data:
            for con in list(report.concomitant_medications):
                db.session.delete(con)
                
            for con_data in data['concomitant_medications']:
                con = ConcomitantMedication(
                    serial_no=con_data.get('serial_no'),
                    drug_name=con_data.get('drug_name'),
                    dose=con_data.get('dose'),
                    route=con_data.get('route'),
                    frequency=con_data.get('frequency'),
                    therapy_start_date=con_data.get('therapy_start_date'),
                    therapy_stop_date=con_data.get('therapy_stop_date'),
                    indication=con_data.get('indication'),
                )
                report.concomitant_medications.append(con)
            changes.append('concomitant_medications')

        # Recalculate causality for suspected medications
        severity_order = [
            "Certain",
            "Probable/Likely",
            "Possible",
            "Unlikely",
            "Conditional/Unclassified",
            "Unassessable/Unclassifiable",
        ]
        naranjo_order = ["Definite", "Probable", "Possible", "Doubtful"]

        best_who_category = "Unassessable/Unclassifiable"
        best_who_rank = len(severity_order)
        
        best_naranjo_score = -10
        best_naranjo_category = "Doubtful"
        best_naranjo_rank = len(naranjo_order)

        report_dict = data.copy()

        for idx, med in enumerate(report.medications):
            if not med.drug_name:
                continue
            
            # WHO-UMC causality
            who_res = run_assessment(report_dict, med.drug_name)
            who_cat = who_res.get('category', 'Unassessable/Unclassifiable')
            who_score = who_res.get('score', 0)
            
            # Naranjo causality
            if idx == 0 and data.get('naranjo_answers'):
                naranjo_answers = data.get('naranjo_answers')
            else:
                naranjo_answers = extract_naranjo_features_from_report(report_dict, med.drug_name)
                
            naranjo_res = calculate_naranjo_score(naranjo_answers)
            n_cat = naranjo_res.get('category', 'Doubtful')
            n_score = naranjo_res.get('score', 0)
            
            med.causality_assessment = f"WHO-UMC: {who_cat} (Score: {who_score}) | Naranjo: {n_cat} (Score: {n_score})"
            
            who_rank = severity_order.index(who_cat) if who_cat in severity_order else len(severity_order)
            if who_rank < best_who_rank:
                best_who_rank = who_rank
                best_who_category = who_cat
                
            n_rank = naranjo_order.index(n_cat) if n_cat in naranjo_order else len(naranjo_order)
            if n_rank < best_naranjo_rank:
                best_naranjo_rank = n_rank
                best_naranjo_category = n_cat
            if n_score > best_naranjo_score:
                best_naranjo_score = n_score

        report.who_umc_category = best_who_category
        report.naranjo_score = best_naranjo_score if best_naranjo_score != -10 else None
        report.naranjo_category = best_naranjo_category

        # Step 3: Create Revision History record if something changed
        if changes:
            change_summary = f"Updated: {', '.join(changes)}"
            revision = ReportRevision(
                report_id=report.id,
                revised_by_id=current_user.id,
                previous_state=previous_state_json,
                change_summary=change_summary
            )
            db.session.add(revision)
            
            # Link attachment if passed and not already linked
            attachment_id = data.get('attachment_id')
            if attachment_id:
                attachment = ReportAttachment.query.get(attachment_id)
                if attachment and attachment.uploaded_by_id == current_user.id:
                    attachment.report = report

            db.session.commit()
            log_activity('edit_report', report_id=report.id, details=change_summary)
        else:
            db.session.commit()

        return jsonify({
            'success': True,
            'report_id': report.id,
            'who_umc_category': report.who_umc_category,
            'naranjo_score': report.naranjo_score,
            'naranjo_category': report.naranjo_category,
        })

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/report/<int:report_id>', methods=['DELETE'])
@login_required
def delete_report(report_id):
    """Delete a report."""
    report = ADRReport.query.get_or_404(report_id)
    # Check ownership or admin role
    if not (current_user.role == 'admin' or report.user_id == current_user.id):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    log_activity('delete_report', report_id=report_id, details=f"Report of patient {report.patient_initials} deleted")
    db.session.delete(report)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/naranjo/calculate', methods=['POST'])
@login_required
def calculate_naranjo():
    """Calculate Naranjo score from answers."""
    data = request.get_json()
    answers = data.get('answers', [])
    try:
        result = calculate_naranjo_score(answers)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/who-umc/assess', methods=['POST'])
@login_required
def assess_who():
    """Assess causality using WHO-UMC scale."""
    data = request.get_json()
    try:
        result = assess_who_umc(data)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/ocr', methods=['POST'])
@login_required
def ocr_form():
    """
    OCR endpoint: receives a base64 image from the phone camera,
    sends it directly to Gemini using multimodal generation to extract
    structured ADR fields, and returns JSON.
    """
    data = request.get_json()
    image_data = data.get('image')  # base64 string sent from phone camera

    if not image_data:
        return jsonify({'error': 'No image data provided'}), 400

    # Remove data URL prefix if present (e.g. "data:image/jpeg;base64,...")
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    try:
        image_bytes = base64.b64decode(image_data)
    except Exception:
        return jsonify({'error': 'Invalid base64 image data'}), 400

    # Save attachment to disk and database
    try:
        import uuid
        file_uuid = uuid.uuid4().hex
        filename = f"adr_scan_{file_uuid}.jpg"
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
            
        attachment = ReportAttachment(
            filename=filename,
            storage_url=f"/uploads/{filename}",
            uploaded_by_id=current_user.id
        )
        db.session.add(attachment)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': f'Failed to store uploaded attachment: {str(e)}'}), 500

    if not GEMINI_AVAILABLE:
        return jsonify({'error': 'Gemini API is not configured. Set GEMINI_API_KEY environment variable.'}), 503

    try:
        # Step 1 & 2: Use Gemini Multimodal to extract fields directly from the image bytes
        extracted = parse_adr_fields_from_image_with_gemini(image_bytes)
        
        # Log activity
        log_activity('upload_attachment', details=f"Uploaded {filename} for OCR scanning")
        
        # Inject attachment_id into extracted dictionary
        if isinstance(extracted, dict):
            extracted['attachment_id'] = attachment.id
            
        return jsonify(extracted)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'OCR processing failed: {str(e)}'}), 500


@app.route('/uploads/<filename>')
@login_required
def serve_upload(filename):
    """Serve uploaded images securely."""
    attachment = ReportAttachment.query.filter_by(filename=filename).first_or_404()
    if not current_user.is_admin:
        if attachment.uploaded_by_id != current_user.id:
            if not attachment.report or attachment.report.user_id != current_user.id:
                from flask import abort
                abort(403)
                
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
    return send_file(os.path.join(upload_folder, filename))


def parse_adr_fields_from_image_with_gemini(image_bytes):
    """
    Use Gemini Multimodal to parse a handwritten/scanned IPC ADR form image
    directly into structured JSON fields matching the ADR report model.
    """
    prompt = """
You are analyzing an image of an IPC ADR (Adverse Drug Reaction) reporting form.
Read the form contents carefully, perform OCR, extract ALL fields, and return ONLY a valid JSON object. No explanation, no markdown, no extra text.
If a field is not found, use null. Read handwritten text carefully.

IMPORTANT: The form may contain MULTIPLE suspected medications (up to 4 rows in Section C).
Extract ALL of them as an array in the "medications" field.

Fields to extract:

TOP SECTION:
- case_type (string — "initial" if Initial Case is ticked, "follow_up" if Follow-up Case is ticked)
- reg_no (string or null — Reg. No. / IPD / OPD / CR No. from the AMC/NCC section)
- amc_report_no (string or null — AMC Report No.)
- worldwide_unique_no (string or null — Worldwide Unique No.)

A. PATIENT INFORMATION:
- patient_initials (string — field 1)
- patient_age (string, e.g. "35 Years" — field 2)
- gender (string: "male", "female", or "other" — field 3)
- weight_kg (number or null — field 4)

B. SUSPECTED ADVERSE REACTION:
- reaction_start_date (string — field 5, in DD/MM/YYYY format)
- reaction_stop_date (string — field 6, in DD/MM/YYYY format)
- reaction_description (string — field 7, transcribe the FULL handwritten text exactly as written)
- relevant_investigations (string or null — field 12)
- medical_history (string or null — field 13, transcribe full handwritten text)
- is_serious (boolean — field 14, true if "Yes" is ticked)
- seriousness_death (boolean — true if "Death" is ticked in field 14)
- seriousness_death_date (string or null — death date if mentioned, DD/MM/YYYY)
- seriousness_life_threatening (boolean — true if "Life threatening" is ticked)
- seriousness_hospitalization (boolean — true if "Hospitalization/Prolonged" is ticked)
- seriousness_disability (boolean — true if "Disability" is ticked)
- seriousness_congenital_anomaly (boolean — true if "Congenital anomaly" is ticked)
- seriousness_other (boolean — true if "Other Medically important" is ticked)
- outcome (string — field 15: one of "recovered", "recovering", "not_recovered", "fatal", "recovered_with_sequelae", "unknown")

C. SUSPECTED MEDICATION(S):
- medications (array of objects — extract ALL filled rows from field 8 table. Each object must have):
    - drug_name (string — brand or generic name, column 8)
    - manufacturer (string or null — "Manufacturer" column)
    - batch_no (string or null — "Batch No. / Lot No." column)
    - expiry_date (string or null — "Expiry Date" column)
    - dose (string — e.g. "200mg", "40mg", "5mg")
    - route (string — e.g. "ORAL", "IV", "IM")
    - frequency (string — e.g. "OD", "BD", "TDS", "Once daily")
    - therapy_start_date (string or null — "Date Started" column, DD/MM/YYYY)
    - therapy_stop_date (string or null — "Date Stopped" column, DD/MM/YYYY)
    - indication (string or null — "Indication" column, e.g. "POST OP", "PROPHYLAXIS")
    - action_taken (string or null — from field 9 table for this row: one of "drug_withdrawn", "dose_increased", "dose_reduced", "dose_not_changed", "not_applicable", "unknown")
    - reintroduction_result (string or null — from field 10 table for this row: "yes" if reaction reappeared, "no" if no recurrence, "effect_unknown" if effect unknown)
    - reintroduction_dose (string or null — dose if re-introduced, from field 10)

FIELD 11 - CONCOMITANT MEDICATIONS:
- concomitant_medications (array of objects or null — from field 11 table, each with):
    - drug_name (string)
    - dose (string or null)
    - route (string or null)
    - frequency (string or null)
    - therapy_start_date (string or null)
    - therapy_stop_date (string or null)
    - indication (string or null)

ADDITIONAL INFO & SIGNATURES:
- additional_info (string or null — "Additional Information" section)
- receiving_personnel (string or null — "Signature and Name of Receiving Personnel")

D. REPORTER DETAILS:
- reporter_name (string or null — name from field 16)
- reporter_address (string or null — address from field 16, including institution/hospital name)
- reporter_pin (string or null — Pin Code)
- reporter_designation (string or null — Occupation/Designation)
- reporter_email (string or null — Email ID)
- reporter_contact (string or null — Contact No.)
- report_date (string or null — field 17, DD/MM/YYYY)
"""
    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type='image/jpeg'
    )
    models_to_try = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-flash-lite-latest']
    response = None
    last_error = None

    for model_name in models_to_try:
        try:
            print(f"DEBUG: Attempting OCR extraction with model {model_name}...")
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=[image_part, prompt]
            )
            print(f"DEBUG: OCR extraction succeeded with model {model_name}.")
            break
        except Exception as e:
            last_error = e
            print(f"WARNING: Model {model_name} failed: {e}. Trying fallback model...")

    if response is None:
        raise last_error

    text = response.text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


@app.route('/api/analytics/stats', methods=['GET'])
@login_required
def get_analytics_stats():
    """Get analytics statistics."""
    try:
        if current_user.is_admin:
            total = ADRReport.query.count()
            serious = ADRReport.query.filter_by(is_serious=True).count()
            male = ADRReport.query.filter_by(gender='M').count()
            female = ADRReport.query.filter_by(gender='F').count()
            other_gender = ADRReport.query.filter(ADRReport.gender.notin_(['M', 'F'])).count()

            outcomes = db.session.query(
                ADRReport.outcome, db.func.count(ADRReport.id)
            ).group_by(ADRReport.outcome).all()

            who_dist = db.session.query(
                ADRReport.who_umc_category, db.func.count(ADRReport.id)
            ).group_by(ADRReport.who_umc_category).all()

            naranjo_dist = db.session.query(
                ADRReport.naranjo_category, db.func.count(ADRReport.id)
            ).group_by(ADRReport.naranjo_category).all()
        else:
            total = ADRReport.query.filter_by(user_id=current_user.id).count()
            serious = ADRReport.query.filter_by(user_id=current_user.id, is_serious=True).count()
            male = ADRReport.query.filter_by(user_id=current_user.id, gender='M').count()
            female = ADRReport.query.filter_by(user_id=current_user.id, gender='F').count()
            other_gender = ADRReport.query.filter_by(user_id=current_user.id).filter(ADRReport.gender.notin_(['M', 'F'])).count()

            outcomes = db.session.query(
                ADRReport.outcome, db.func.count(ADRReport.id)
            ).filter(ADRReport.user_id == current_user.id).group_by(ADRReport.outcome).all()

            who_dist = db.session.query(
                ADRReport.who_umc_category, db.func.count(ADRReport.id)
            ).filter(ADRReport.user_id == current_user.id).group_by(ADRReport.who_umc_category).all()

            naranjo_dist = db.session.query(
                ADRReport.naranjo_category, db.func.count(ADRReport.id)
            ).filter(ADRReport.user_id == current_user.id).group_by(ADRReport.naranjo_category).all()

        # Recent reports by month — handle both SQLite and PostgreSQL
        db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if 'sqlite' in db_url:
            month_col = db.func.strftime('%Y-%m', ADRReport.created_at)
        else:
            month_col = db.func.to_char(ADRReport.created_at, 'YYYY-MM')

        rbm_query = db.session.query(
            month_col,
            db.func.count(ADRReport.id)
        )
        if not current_user.is_admin:
            rbm_query = rbm_query.filter(ADRReport.user_id == current_user.id)
        reports_by_month = rbm_query.group_by(month_col).order_by(month_col).limit(12).all()

        # Top drugs
        td_query = db.session.query(
            SuspectedMedication.drug_name, db.func.count(SuspectedMedication.id)
        ).filter(SuspectedMedication.drug_name.isnot(None))
        if not current_user.is_admin:
            td_query = td_query.join(ADRReport).filter(ADRReport.user_id == current_user.id)
        top_drugs = td_query.group_by(
            SuspectedMedication.drug_name
        ).order_by(db.func.count(SuspectedMedication.id).desc()).limit(10).all()

        return jsonify({
            'total_reports': total,
            'serious_reports': serious,
            'gender_distribution': {
                'male': male, 'female': female, 'other': other_gender
            },
            'outcome_distribution': {str(k or 'Unknown'): v for k, v in outcomes},
            'who_umc_distribution': {str(k or 'N/A'): v for k, v in who_dist},
            'naranjo_distribution': {str(k or 'N/A'): v for k, v in naranjo_dist},
            'reports_by_month': {str(k): v for k, v in reports_by_month},
            'top_drugs': {str(k): v for k, v in top_drugs},
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/admin-stats', methods=['GET'])
@admin_required
def get_admin_analytics_stats():
    """Get extended per-user analytics for admins."""
    try:
        users = User.query.all()
        user_list = []
        for u in users:
            report_count = ADRReport.query.filter_by(user_id=u.id).count()
            user_list.append({
                'id': u.id,
                'username': u.username,
                'display_name': u.display_name,
                'role': u.role,
                'department': u.department,
                'last_login': u.last_login.strftime('%d/%m/%Y %I:%M %p') if u.last_login else 'Never',
                'created_at': u.created_at.strftime('%d/%m/%Y') if u.created_at else 'N/A',
                'report_count': report_count
            })
        return jsonify({'users': user_list})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


import re

def get_age_group(age_str):
    if not age_str:
        return 'Unknown'
    # Try to find a number in the age string
    match = re.search(r'\d+', str(age_str))
    if not match:
        return 'Unknown'
    try:
        age_val = int(match.group())
        if age_val <= 12:
            return 'Pediatric (0-12)'
        elif age_val <= 19:
            return 'Adolescent (13-19)'
        elif age_val <= 59:
            return 'Adult (20-59)'
        else:
            return 'Geriatric (60+)'
    except:
        return 'Unknown'

@app.route('/api/analytics/dose-age')
@login_required
def api_dose_age():
    try:
        da_query = db.session.query(
            SuspectedMedication.drug_name,
            SuspectedMedication.dose,
            ADRReport.patient_age
        ).join(ADRReport, SuspectedMedication.report_id == ADRReport.id)
        if not current_user.is_admin:
            da_query = da_query.filter(ADRReport.user_id == current_user.id)
        results = da_query.all()
        
        data = {}
        for drug, dose, age_str in results:
            if not drug:
                continue
            drug_clean = drug.strip().upper()
            dose_clean = (dose or 'Unknown').strip()
            
            if drug_clean not in data:
                data[drug_clean] = {}
            if dose_clean not in data[drug_clean]:
                data[drug_clean][dose_clean] = {
                    'count': 0,
                    'age_groups': {
                        'Pediatric (0-12)': 0,
                        'Adolescent (13-19)': 0,
                        'Adult (20-59)': 0,
                        'Geriatric (60+)': 0,
                        'Unknown': 0
                    }
                }
            
            group = get_age_group(age_str)
            data[drug_clean][dose_clean]['count'] += 1
            data[drug_clean][dose_clean]['age_groups'][group] += 1
            
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/export-excel')
@login_required
def api_export_excel():
    log_activity('export_excel')
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from io import BytesIO
        
        wb = Workbook()
        ws_reports = wb.active
        ws_reports.title = "ADR Reports"
        
        # Headers for reports
        headers_reports = [
            "Report ID", "Created At", "Case Type", "Patient Initials", "Age", "Gender", "Weight (kg)",
            "Reaction Start", "Reaction Stop", "Reaction Description", "Is Serious",
            "Seriousness Reasons", "Outcome", "Relevant Investigations", "Medical History",
            "Naranjo Score", "Naranjo Category", "WHO-UMC Category",
            "Reporter Name", "Reporter Occupation", "Reporter Contact"
        ]
        
        ws_reports.append(headers_reports)
        
        # Style headers
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="8B1A1A", end_color="8B1A1A", fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='DDDDDD'),
            right=Side(style='thin', color='DDDDDD'),
            top=Side(style='thin', color='DDDDDD'),
            bottom=Side(style='thin', color='DDDDDD')
        )
        
        for col_idx in range(1, len(headers_reports) + 1):
            cell = ws_reports.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
            
        if current_user.is_admin:
            reports = ADRReport.query.order_by(ADRReport.id.desc()).all()
        else:
            reports = ADRReport.query.filter_by(user_id=current_user.id).order_by(ADRReport.id.desc()).all()
        for r in reports:
            ser_list = []
            if r.seriousness_death: ser_list.append("Death")
            if r.seriousness_life_threatening: ser_list.append("Life Threatening")
            if r.seriousness_hospitalization: ser_list.append("Hospitalization")
            if r.seriousness_disability: ser_list.append("Disability")
            if r.seriousness_congenital_anomaly: ser_list.append("Congenital Anomaly")
            if r.seriousness_other: ser_list.append("Other Medically Important")
            ser_str = ", ".join(ser_list) if ser_list else ("Yes" if r.is_serious else "No")
            
            created_str = r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''
            
            row_data = [
                r.id, created_str, r.case_type, r.patient_initials, r.patient_age, r.gender, r.weight_kg,
                r.reaction_start_date, r.reaction_stop_date, r.reaction_description,
                "Yes" if r.is_serious else "No", ser_str, r.outcome, r.relevant_investigations, r.medical_history,
                r.naranjo_score, r.naranjo_category, r.who_umc_category,
                r.reporter_name, r.reporter_occupation, r.reporter_contact
            ]
            ws_reports.append(row_data)
            
        # Sheet 2: Suspected Medications
        ws_meds = wb.create_sheet(title="Suspected Medications")
        headers_meds = [
            "Medication ID", "Report ID", "Patient Initials", "Drug Name", "Manufacturer", "Batch No",
            "Expiry Date", "Dose", "Route", "Frequency", "Therapy Start", "Therapy Stop", "Indication",
            "Action Taken", "Reintroduction Result"
        ]
        ws_meds.append(headers_meds)
        
        for col_idx in range(1, len(headers_meds) + 1):
            cell = ws_meds.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
            
        meds_query = SuspectedMedication.query.join(ADRReport)
        if not current_user.is_admin:
            meds_query = meds_query.filter(ADRReport.user_id == current_user.id)
        meds = meds_query.order_by(SuspectedMedication.report_id.desc()).all()
        for m in meds:
            row_data = [
                m.id, m.report_id, m.report.patient_initials if m.report else '', m.drug_name, m.manufacturer, m.batch_no,
                m.expiry_date, m.dose, m.route, m.frequency, m.therapy_start_date, m.therapy_stop_date, m.indication,
                m.action_taken, m.reintroduction_result
            ]
            ws_meds.append(row_data)
            
        # Auto-adjust column widths
        for ws in [ws_reports, ws_meds]:
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    val_str = str(cell.value or '')
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 40)
                
        # Style all data rows
        data_font = Font(name="Arial", size=10)
        data_align = Alignment(vertical="center")
        for ws in [ws_reports, ws_meds]:
            for r_idx in range(2, ws.max_row + 1):
                for c_idx in range(1, ws.max_column + 1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    cell.font = data_font
                    cell.alignment = data_align
                    cell.border = thin_border
                    
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="adr_reports_export.xlsx"
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/report/<int:report_id>/export-excel')
@login_required
def api_export_single_report_excel(report_id):
    log_activity('export_single_report_excel', report_id=report_id)
    try:
        report = ADRReport.query.get_or_404(report_id)
        if not (current_user.is_admin or report.user_id == current_user.id):
            return jsonify({'error': 'Unauthorized'}), 403

        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from io import BytesIO

        wb = Workbook()
        ws_report = wb.active
        ws_report.title = f"Report #{report.id}"

        headers_reports = [
            "Report ID", "Created At", "Case Type", "Patient Initials", "Age", "Gender", "Weight (kg)",
            "Reaction Start", "Reaction Stop", "Reaction Description", "Is Serious",
            "Seriousness Reasons", "Outcome", "Relevant Investigations", "Medical History",
            "Naranjo Score", "Naranjo Category", "WHO-UMC Category",
            "Reporter Name", "Reporter Occupation", "Reporter Contact"
        ]
        ws_report.append(headers_reports)

        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="8B1A1A", end_color="8B1A1A", fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin', color='DDDDDD'),
            right=Side(style='thin', color='DDDDDD'),
            top=Side(style='thin', color='DDDDDD'),
            bottom=Side(style='thin', color='DDDDDD')
        )

        for col_idx in range(1, len(headers_reports) + 1):
            cell = ws_report.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        ser_list = []
        if report.seriousness_death: ser_list.append("Death")
        if report.seriousness_life_threatening: ser_list.append("Life Threatening")
        if report.seriousness_hospitalization: ser_list.append("Hospitalization")
        if report.seriousness_disability: ser_list.append("Disability")
        if report.seriousness_congenital_anomaly: ser_list.append("Congenital Anomaly")
        if report.seriousness_other: ser_list.append("Other Medically Important")
        ser_str = ", ".join(ser_list) if ser_list else ("Yes" if report.is_serious else "No")
        created_str = report.created_at.strftime('%Y-%m-%d %H:%M') if report.created_at else ''

        row_data = [
            report.id, created_str, report.case_type, report.patient_initials, report.patient_age, report.gender, report.weight_kg,
            report.reaction_start_date, report.reaction_stop_date, report.reaction_description,
            "Yes" if report.is_serious else "No", ser_str, report.outcome, report.relevant_investigations, report.medical_history,
            report.naranjo_score, report.naranjo_category, report.who_umc_category,
            report.reporter_name, report.reporter_occupation, report.reporter_contact
        ]
        ws_report.append(row_data)

        # Sheet 2: Suspected Medications
        ws_meds = wb.create_sheet(title="Suspected Medications")
        headers_meds = [
            "Medication ID", "Report ID", "Drug Name", "Manufacturer", "Batch No",
            "Expiry Date", "Dose", "Route", "Frequency", "Therapy Start", "Therapy Stop", "Indication",
            "Action Taken", "Reintroduction Result", "Causality"
        ]
        ws_meds.append(headers_meds)

        for col_idx in range(1, len(headers_meds) + 1):
            cell = ws_meds.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        for m in (report.medications or []):
            med_data = [
                m.id, report.id, m.drug_name, m.manufacturer, m.batch_no,
                m.expiry_date, m.dose, m.route, m.frequency, m.therapy_start_date, m.therapy_stop_date, m.indication,
                m.action_taken, m.reintroduction_result, m.causality_assessment
            ]
            ws_meds.append(med_data)

        for ws in [ws_report, ws_meds]:
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    val_str = str(cell.value or '')
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 40)

        data_font = Font(name="Arial", size=10)
        data_align = Alignment(vertical="center")
        for ws in [ws_report, ws_meds]:
            for r_idx in range(2, ws.max_row + 1):
                for c_idx in range(1, ws.max_column + 1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    cell.font = data_font
                    cell.alignment = data_align
                    cell.border = thin_border

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"adr_report_{report.id}.xlsx"
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)

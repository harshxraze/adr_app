"""
Database models for the ADR Causality Assessment System.
Models map to the IPC/PvPI ADR Reporting Form fields.
"""
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


class ADRReport(db.Model):
    """Main ADR Report - corresponds to one filled form submission."""
    __tablename__ = 'adr_reports'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Case type
    case_type = db.Column(db.String(20))  # 'initial' or 'follow_up'

    # AMC/NCC fields
    reg_no = db.Column(db.String(100))
    amc_report_no = db.Column(db.String(100))
    worldwide_unique_no = db.Column(db.String(100))

    # Section A: Patient Information
    patient_initials = db.Column(db.String(20))
    patient_age = db.Column(db.String(50))
    patient_dob = db.Column(db.String(20))
    gender = db.Column(db.String(10))  # 'M', 'F', 'Other'
    weight_kg = db.Column(db.Float)

    # Section B: Suspected Adverse Reaction
    reaction_start_date = db.Column(db.String(20))
    reaction_stop_date = db.Column(db.String(20))
    reaction_description = db.Column(db.Text)

    # Relevant investigations
    relevant_investigations = db.Column(db.Text)

    # Medical/Medication history
    medical_history = db.Column(db.Text)

    # Seriousness
    is_serious = db.Column(db.Boolean, default=False)
    seriousness_death = db.Column(db.Boolean, default=False)
    seriousness_death_date = db.Column(db.String(20))
    seriousness_life_threatening = db.Column(db.Boolean, default=False)
    seriousness_hospitalization = db.Column(db.Boolean, default=False)
    seriousness_congenital_anomaly = db.Column(db.Boolean, default=False)
    seriousness_disability = db.Column(db.Boolean, default=False)
    seriousness_other = db.Column(db.Boolean, default=False)

    # Outcome
    outcome = db.Column(db.String(50))

    # Additional info
    additional_info = db.Column(db.Text)

    # Section D: Reporter Details
    reporter_name = db.Column(db.String(200))
    reporter_address = db.Column(db.Text)
    reporter_pin = db.Column(db.String(10))
    reporter_email = db.Column(db.String(100))
    reporter_contact = db.Column(db.String(20))
    reporter_occupation = db.Column(db.String(100))
    report_date = db.Column(db.String(20))

    # Causality Assessment Results
    naranjo_score = db.Column(db.Integer)
    naranjo_category = db.Column(db.String(50))
    who_umc_category = db.Column(db.String(50))
    who_umc_differential_note = db.Column(db.Text, nullable=True)
    ml_prediction = db.Column(db.String(50))
    ml_confidence = db.Column(db.Float)

    # Relationships
    medications = db.relationship('SuspectedMedication', backref='report', lazy=True, cascade='all, delete-orphan')
    concomitant_medications = db.relationship('ConcomitantMedication', backref='report', lazy=True, cascade='all, delete-orphan')
    author = db.relationship('User', backref='reports', lazy=True, foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'case_type': self.case_type,
            'reg_no': self.reg_no,
            'amc_report_no': self.amc_report_no,
            'worldwide_unique_no': self.worldwide_unique_no,
            'patient_initials': self.patient_initials,
            'patient_age': self.patient_age,
            'patient_dob': self.patient_dob,
            'gender': self.gender,
            'weight_kg': self.weight_kg,
            'reaction_start_date': self.reaction_start_date,
            'reaction_stop_date': self.reaction_stop_date,
            'reaction_description': self.reaction_description,
            'relevant_investigations': self.relevant_investigations,
            'medical_history': self.medical_history,
            'is_serious': self.is_serious,
            'seriousness_death': self.seriousness_death,
            'seriousness_death_date': self.seriousness_death_date,
            'seriousness_life_threatening': self.seriousness_life_threatening,
            'seriousness_hospitalization': self.seriousness_hospitalization,
            'seriousness_congenital_anomaly': self.seriousness_congenital_anomaly,
            'seriousness_disability': self.seriousness_disability,
            'seriousness_other': self.seriousness_other,
            'outcome': self.outcome,
            'additional_info': self.additional_info,
            'reporter_name': self.reporter_name,
            'reporter_address': self.reporter_address,
            'reporter_pin': self.reporter_pin,
            'reporter_email': self.reporter_email,
            'reporter_contact': self.reporter_contact,
            'reporter_occupation': self.reporter_occupation,
            'report_date': self.report_date,
            'naranjo_score': self.naranjo_score,
            'naranjo_category': self.naranjo_category,
            'who_umc_category': self.who_umc_category,
            'who_umc_differential_note': self.who_umc_differential_note,
            'ml_prediction': self.ml_prediction,
            'ml_confidence': self.ml_confidence,
            'user_id': self.user_id,
            'author_name': self.author.display_name if self.author else None,
            'medications': [m.to_dict() for m in self.medications],
            'concomitant_medications': [c.to_dict() for c in self.concomitant_medications],
        }


class SuspectedMedication(db.Model):
    """Section C: Suspected Medications table."""
    __tablename__ = 'suspected_medications'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_id = db.Column(db.Integer, db.ForeignKey('adr_reports.id'), nullable=False)
    serial_no = db.Column(db.Integer)

    drug_name = db.Column(db.String(200))
    manufacturer = db.Column(db.String(200))
    batch_no = db.Column(db.String(100))
    expiry_date = db.Column(db.String(20))
    dose = db.Column(db.String(100))
    route = db.Column(db.String(50))
    frequency = db.Column(db.String(50))
    therapy_start_date = db.Column(db.String(20))
    therapy_stop_date = db.Column(db.String(20))
    indication = db.Column(db.String(200))

    # Action taken (Q9)
    action_taken = db.Column(db.String(50))  # drug_withdrawn, dose_increased, dose_reduced, dose_not_changed, not_applicable, unknown

    # Reaction reappeared after reintroduction (Q10)
    reintroduction_result = db.Column(db.String(50))  # yes, no, effect_unknown
    reintroduction_dose = db.Column(db.String(100))

    # Causality assessment per drug
    causality_assessment = db.Column(db.String(100))

    def to_dict(self):
        return {
            'id': self.id,
            'serial_no': self.serial_no,
            'drug_name': self.drug_name,
            'manufacturer': self.manufacturer,
            'batch_no': self.batch_no,
            'expiry_date': self.expiry_date,
            'dose': self.dose,
            'route': self.route,
            'frequency': self.frequency,
            'therapy_start_date': self.therapy_start_date,
            'therapy_stop_date': self.therapy_stop_date,
            'indication': self.indication,
            'action_taken': self.action_taken,
            'reintroduction_result': self.reintroduction_result,
            'reintroduction_dose': self.reintroduction_dose,
            'causality_assessment': self.causality_assessment,
        }


class ConcomitantMedication(db.Model):
    """Section 11: Concomitant medications."""
    __tablename__ = 'concomitant_medications'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_id = db.Column(db.Integer, db.ForeignKey('adr_reports.id'), nullable=False)
    serial_no = db.Column(db.Integer)

    drug_name = db.Column(db.String(200))
    dose = db.Column(db.String(100))
    route = db.Column(db.String(50))
    frequency = db.Column(db.String(50))
    therapy_start_date = db.Column(db.String(20))
    therapy_stop_date = db.Column(db.String(20))
    indication = db.Column(db.String(200))

    def to_dict(self):
        return {
            'id': self.id,
            'serial_no': self.serial_no,
            'drug_name': self.drug_name,
            'dose': self.dose,
            'route': self.route,
            'frequency': self.frequency,
            'therapy_start_date': self.therapy_start_date,
            'therapy_stop_date': self.therapy_stop_date,
            'indication': self.indication,
        }


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    @property
    def avatar(self):
        source = self.display_name or self.username or 'U'
        return source[:1].upper()

    @property
    def is_admin(self):
        return (self.role or '').lower() == 'admin'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False

        # Legacy-safe fallback for pre-hash records during migration.
        if self.password_hash.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
            return check_password_hash(self.password_hash, password)
        return self.password_hash == password

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'email': self.email,
            'display_name': self.display_name,
            'department': self.department,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ModelTrainingLog(db.Model):
    """Track ML model training runs."""
    __tablename__ = 'model_training_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    trained_at = db.Column(db.DateTime, default=datetime.utcnow)
    model_type = db.Column(db.String(50))  # 'random_forest', 'gradient_boosting', etc.
    accuracy = db.Column(db.Float)
    precision_score = db.Column(db.Float)
    recall = db.Column(db.Float)
    f1_score = db.Column(db.Float)
    dataset_size = db.Column(db.Integer)
    feature_count = db.Column(db.Integer)
    model_path = db.Column(db.String(500))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'trained_at': self.trained_at.isoformat() if self.trained_at else None,
            'model_type': self.model_type,
            'accuracy': self.accuracy,
            'precision_score': self.precision_score,
            'recall': self.recall,
            'f1_score': self.f1_score,
            'dataset_size': self.dataset_size,
            'feature_count': self.feature_count,
            'is_active': self.is_active,
            'notes': self.notes,
        }


class AdminActionLog(db.Model):
    """Audit trail for admin privilege changes — hospital compliance."""
    __tablename__ = 'admin_action_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    performed_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # 'grant_admin', 'revoke_admin', 'invite_sent', 'invite_accepted'
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    target_email = db.Column(db.String(120), nullable=True)
    details = db.Column(db.Text, nullable=True)

    admin_user = db.relationship('User', foreign_keys=[admin_user_id], backref='admin_actions_performed')
    target_user = db.relationship('User', foreign_keys=[target_user_id], backref='admin_actions_received')


class ReportAttachment(db.Model):
    """Clinical files/images scanned for OCR or attached to reports."""
    __tablename__ = 'report_attachments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_id = db.Column(db.Integer, db.ForeignKey('adr_reports.id'), nullable=True)
    filename = db.Column(db.String(256), nullable=False)
    storage_url = db.Column(db.String(512), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User', backref='attachments')
    report = db.relationship('ADRReport', backref='attachments')

    def to_dict(self):
        return {
            'id': self.id,
            'report_id': self.report_id,
            'filename': self.filename,
            'storage_url': self.storage_url,
            'uploaded_by_id': self.uploaded_by_id,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }


class UserActivityLog(db.Model):
    """Detailed patient data access logs for clinical compliance (HIPAA)."""
    __tablename__ = 'user_activity_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # 'create_report', 'delete_report', 'view_report', 'view_reports', 'export_excel', 'view_dashboard'
    report_id = db.Column(db.Integer, db.ForeignKey('adr_reports.id'), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)

    user = db.relationship('User', backref='activity_logs')
    report = db.relationship('ADRReport', backref='activity_logs')

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'user_id': self.user_id,
            'action': self.action,
            'report_id': self.report_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent
        }


class LoginAttempt(db.Model):
    """Forensic logs of all successful and failed authentication attempts."""
    __tablename__ = 'login_attempts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)
    identifier = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)
    is_successful = db.Column(db.Boolean, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'attempted_at': self.attempted_at.isoformat() if self.attempted_at else None,
            'identifier': self.identifier,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'is_successful': self.is_successful
        }


class ReportRevision(db.Model):
    """Tracks historical changes/revisions made to clinical ADR reports."""
    __tablename__ = 'report_revisions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_id = db.Column(db.Integer, db.ForeignKey('adr_reports.id', ondelete='CASCADE'), nullable=False)
    revised_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    revised_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Store the full previous state of the report as JSON to allow differential tracking or restoration
    previous_state = db.Column(db.Text, nullable=False)
    
    # Human-readable change summary, e.g. "Updated patient age and suspected medication dosage"
    change_summary = db.Column(db.Text, nullable=True)

    revised_by = db.relationship('User', backref='report_revisions')
    report = db.relationship('ADRReport', backref=db.backref('revisions', cascade='all, delete-orphan', passive_deletes=True))

    def to_dict(self):
        return {
            'id': self.id,
            'report_id': self.report_id,
            'revised_by': self.revised_by.display_name if self.revised_by else 'Unknown',
            'revised_at': self.revised_at.isoformat() if self.revised_at else None,
            'change_summary': self.change_summary
        }

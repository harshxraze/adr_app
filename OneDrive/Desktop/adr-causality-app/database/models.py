"""
Database models for the ADR Causality Assessment System.
Models map to the IPC/PvPI ADR Reporting Form fields.
"""
from datetime import datetime
from database import db


class ADRReport(db.Model):
    """Main ADR Report - corresponds to one filled form submission."""
    __tablename__ = 'adr_reports'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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
    ml_prediction = db.Column(db.String(50))
    ml_confidence = db.Column(db.Float)

    # Relationships
    medications = db.relationship('SuspectedMedication', backref='report', lazy=True, cascade='all, delete-orphan')
    concomitant_medications = db.relationship('ConcomitantMedication', backref='report', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'case_type': self.case_type,
            'reg_no': self.reg_no,
            'amc_report_no': self.amc_report_no,
            'patient_initials': self.patient_initials,
            'patient_age': self.patient_age,
            'gender': self.gender,
            'weight_kg': self.weight_kg,
            'reaction_start_date': self.reaction_start_date,
            'reaction_stop_date': self.reaction_stop_date,
            'reaction_description': self.reaction_description,
            'relevant_investigations': self.relevant_investigations,
            'medical_history': self.medical_history,
            'is_serious': self.is_serious,
            'seriousness_death': self.seriousness_death,
            'seriousness_life_threatening': self.seriousness_life_threatening,
            'seriousness_hospitalization': self.seriousness_hospitalization,
            'seriousness_congenital_anomaly': self.seriousness_congenital_anomaly,
            'seriousness_disability': self.seriousness_disability,
            'seriousness_other': self.seriousness_other,
            'outcome': self.outcome,
            'additional_info': self.additional_info,
            'reporter_name': self.reporter_name,
            'reporter_occupation': self.reporter_occupation,
            'report_date': self.report_date,
            'naranjo_score': self.naranjo_score,
            'naranjo_category': self.naranjo_category,
            'who_umc_category': self.who_umc_category,
            'ml_prediction': self.ml_prediction,
            'ml_confidence': self.ml_confidence,
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

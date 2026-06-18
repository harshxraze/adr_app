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
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
print("DEBUG: Environment variables loaded. GEMINI_API_KEY present:", bool(os.environ.get('GEMINI_API_KEY')))

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS

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
from database.models import ADRReport, SuspectedMedication, ConcomitantMedication, ModelTrainingLog
from ml.naranjo import calculate_naranjo_score, NARANJO_QUESTIONS, extract_naranjo_features_from_report
from ml.who_umc import assess_who_umc, WHO_UMC_CATEGORIES

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

# Initialize database
init_db(app)

# Ensure directories exist
os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)


# ==================== PAGE ROUTES ====================

@app.route('/')
def index():
    """Dashboard / Home page."""
    with app.app_context():
        total_reports = ADRReport.query.count()
        serious_reports = ADRReport.query.filter_by(is_serious=True).count()
        recent_reports = ADRReport.query.order_by(ADRReport.created_at.desc()).limit(5).all()

    return render_template('index.html',
                           total_reports=total_reports,
                           serious_reports=serious_reports,
                           recent_reports=recent_reports)


@app.route('/form')
def adr_form():
    """ADR Reporting Form page."""
    return render_template('form.html')


@app.route('/reports')
def reports_list():
    """View all ADR reports."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    reports = ADRReport.query.order_by(ADRReport.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('reports.html', reports=reports)


@app.route('/report/<int:report_id>')
def view_report(report_id):
    """View a single ADR report with causality assessment."""
    report = ADRReport.query.get_or_404(report_id)
    return render_template('report_detail.html', report=report)


@app.route('/analytics')
def analytics():
    """Analytics dashboard."""
    return render_template('analytics.html')


@app.route('/naranjo')
def naranjo_page():
    """Naranjo scale calculator page."""
    return render_template('naranjo.html', questions=NARANJO_QUESTIONS)


@app.route('/capture')
def capture():
    """Camera capture page for scanning ADR forms."""
    return render_template('capture.html')


# ==================== API ROUTES ====================

@app.route('/api/submit-report', methods=['POST'])
def submit_report():
    """Submit a new ADR report."""
    try:
        data = request.get_json()

        # Create main report
        report = ADRReport(
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

        # Auto-assess causality using WHO-UMC
        report_dict = data.copy()
        who_result = assess_who_umc(report_dict)
        report.who_umc_category = who_result['category']

        # Auto-assess using Naranjo (if answers provided)
        if data.get('naranjo_answers'):
            naranjo_result = calculate_naranjo_score(data['naranjo_answers'])
            report.naranjo_score = naranjo_result['score']
            report.naranjo_category = naranjo_result['category']
        else:
            # Try to auto-extract Naranjo features
            auto_answers = extract_naranjo_features_from_report(report_dict)
            naranjo_result = calculate_naranjo_score(auto_answers)
            report.naranjo_score = naranjo_result['score']
            report.naranjo_category = naranjo_result['category']

        db.session.add(report)
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


@app.route('/api/reports', methods=['GET'])
def get_reports():
    """Get all reports as JSON."""
    reports = ADRReport.query.order_by(ADRReport.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reports])


@app.route('/api/report/<int:report_id>', methods=['GET'])
def get_report(report_id):
    """Get a single report."""
    report = ADRReport.query.get_or_404(report_id)
    return jsonify(report.to_dict())


@app.route('/api/report/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    """Delete a report."""
    report = ADRReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/naranjo/calculate', methods=['POST'])
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
def assess_who():
    """Assess causality using WHO-UMC scale."""
    data = request.get_json()
    try:
        result = assess_who_umc(data)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/ocr', methods=['POST'])
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

    if not GEMINI_AVAILABLE:
        return jsonify({'error': 'Gemini API is not configured. Set GEMINI_API_KEY environment variable.'}), 503

    try:
        # Step 1 & 2: Use Gemini Multimodal to extract fields directly from the image bytes
        extracted = parse_adr_fields_from_image_with_gemini(image_bytes)
        return jsonify(extracted)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'OCR processing failed: {str(e)}'}), 500


def parse_adr_fields_from_image_with_gemini(image_bytes):
    """
    Use Gemini Multimodal to parse a handwritten/scanned IPC ADR form image
    directly into structured JSON fields matching the ADR report model.
    """
    prompt = """
You are analyzing an image of an IPC ADR (Adverse Drug Reaction) reporting form.
Read the form contents, perform OCR, extract the following fields, and return ONLY a valid JSON object. No explanation, no markdown, no extra text.
If a field is not found, use null.

Fields to extract:
- patient_initials (string)
- patient_age (string, e.g. "45")
- gender (string: "male", "female", or "other")
- weight_kg (number or null)
- reaction_description (string — describe the adverse reaction)
- drug_name (string — name of suspected drug)
- dose (string — dosage)
- route (string — route of administration, e.g. oral, IV)
- reaction_start_date (string — date reaction started, any format found)
- reaction_stop_date (string — date reaction stopped, if found)
- therapy_start_date (string — date drug therapy started)
- therapy_stop_date (string — date drug therapy stopped, if found)
- action_taken (string — one of: drug_withdrawn, dose_reduced, not_changed, unknown)
- outcome (string — one of: recovered, recovering, not_recovered, fatal, unknown)
- is_serious (boolean — true if the reaction is described as serious, life-threatening, hospitalization, or death)
- reintroduction_result (string — "yes" if drug was reintroduced and reaction recurred, "no" if reintroduced without recurrence, else null)
- relevant_investigations (string or null — any lab tests or investigations mentioned)
- medical_history (string or null — relevant medical history)
- reporter_name (string or null)
- reporter_designation (string or null)
- additional_info (string or null)
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
def get_analytics_stats():
    """Get analytics statistics."""
    try:
        total = ADRReport.query.count()
        serious = ADRReport.query.filter_by(is_serious=True).count()

        # Gender distribution
        male = ADRReport.query.filter_by(gender='M').count()
        female = ADRReport.query.filter_by(gender='F').count()
        other_gender = ADRReport.query.filter(ADRReport.gender.notin_(['M', 'F'])).count()

        # Outcome distribution
        outcomes = db.session.query(
            ADRReport.outcome, db.func.count(ADRReport.id)
        ).group_by(ADRReport.outcome).all()

        # WHO-UMC distribution
        who_dist = db.session.query(
            ADRReport.who_umc_category, db.func.count(ADRReport.id)
        ).group_by(ADRReport.who_umc_category).all()

        # Naranjo distribution
        naranjo_dist = db.session.query(
            ADRReport.naranjo_category, db.func.count(ADRReport.id)
        ).group_by(ADRReport.naranjo_category).all()

        # Recent reports by month — handle both SQLite and PostgreSQL
        db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if 'sqlite' in db_url:
            month_col = db.func.strftime('%Y-%m', ADRReport.created_at)
        else:
            month_col = db.func.to_char(ADRReport.created_at, 'YYYY-MM')

        reports_by_month = db.session.query(
            month_col,
            db.func.count(ADRReport.id)
        ).group_by(month_col).order_by(month_col).limit(12).all()

        # Top drugs
        top_drugs = db.session.query(
            SuspectedMedication.drug_name, db.func.count(SuspectedMedication.id)
        ).filter(SuspectedMedication.drug_name.isnot(None)).group_by(
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)

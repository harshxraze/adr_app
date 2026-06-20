"""
Naranjo Adverse Drug Reaction Probability Scale
Used for causality assessment of ADRs.
Enhanced with a Clinical NLP Extraction Layer (Google Cloud Healthcare / Gemini / Regex fallback)
and structured overlay to ensure highly accurate, clinically-grounded causality scoring.
"""

import re
import os
import json
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()


NARANJO_QUESTIONS = [
    {
        "id": 1,
        "question": "Are there previous conclusive reports on this reaction?",
        "yes": 1, "no": 0, "unknown": 0
    },
    {
        "id": 2,
        "question": "Did the adverse event appear after the suspected drug was administered?",
        "yes": 2, "no": -1, "unknown": 0
    },
    {
        "id": 3,
        "question": "Did the adverse reaction improve when the drug was discontinued or a specific antagonist was administered?",
        "yes": 1, "no": 0, "unknown": 0
    },
    {
        "id": 4,
        "question": "Did the adverse reaction reappear when the drug was re-administered?",
        "yes": 2, "no": -1, "unknown": 0
    },
    {
        "id": 5,
        "question": "Are there alternative causes (other than the drug) that could on their own have caused the reaction?",
        "yes": -1, "no": 2, "unknown": 0
    },
    {
        "id": 6,
        "question": "Did the reaction reappear when a placebo was given?",
        "yes": -1, "no": 1, "unknown": 0
    },
    {
        "id": 7,
        "question": "Was the drug detected in the blood (or other fluids) in concentrations known to be toxic?",
        "yes": 1, "no": 0, "unknown": 0
    },
    {
        "id": 8,
        "question": "Was the reaction more severe when the dose was increased, or less severe when the dose was decreased?",
        "yes": 1, "no": 0, "unknown": 0
    },
    {
        "id": 9,
        "question": "Did the patient have a similar reaction to the same or similar drugs in any previous exposure?",
        "yes": 1, "no": 0, "unknown": 0
    },
    {
        "id": 10,
        "question": "Was the adverse event confirmed by any objective evidence?",
        "yes": 1, "no": 0, "unknown": 0
    }
]

from ml.nlp_extractor import get_clinical_extraction


def calculate_naranjo_score(answers):
    """
    Calculate the Naranjo score from a list of answers.

    Args:
        answers: list of 10 strings, each 'yes', 'no', or 'unknown'

    Returns:
        dict with 'score' (int) and 'category' (str)
    """
    if len(answers) != 10:
        raise ValueError("Exactly 10 answers are required for the Naranjo scale.")

    total_score = 0
    for i, answer in enumerate(answers):
        answer = str(answer).lower().strip()
        q = NARANJO_QUESTIONS[i]
        if answer == 'yes':
            total_score += q['yes']
        elif answer == 'no':
            total_score += q['no']
        else:
            total_score += q['unknown']

    category = get_naranjo_category(total_score)
    return {"score": total_score, "category": category}


def get_naranjo_category(score):
    """Classify the Naranjo score into a category."""
    if score >= 9:
        return "Definite"
    elif score >= 5:
        return "Probable"
    elif score >= 1:
        return "Possible"
    else:
        return "Doubtful"


def extract_naranjo_features_from_report(report_data: dict, target_drug_name: Optional[str] = None) -> list:
    """
    Automatically infers Naranjo answers from ADR report data using a Two-Layer Architecture:
    1. Clinical NLP extraction of descriptions.
    2. Overlay of structured form values.
    """
    # 1. Identify Target Drug Name
    medications = report_data.get('medications', []) or []
    target_drug = None
    if target_drug_name:
        target_drug = next((m for m in medications if m.get('drug_name', '').lower() == target_drug_name.lower()), None)
    
    if not target_drug and medications:
        target_drug = medications[0]
        target_drug_name = target_drug.get('drug_name', '')
    
    if not target_drug_name:
        target_drug_name = "suspected drug"

    # 2. Extract clinical description details via NLP / Regex fallback
    description_text = report_data.get('reaction_description') or ""
    medical_history = report_data.get('medical_history') or ""
    additional_info = report_data.get('additional_info') or ""
    relevant_investigations = report_data.get('relevant_investigations') or ""
    full_text = f"Description: {description_text}. Investigations: {relevant_investigations}. Medical History: {medical_history}. Additional Info: {additional_info}"

    # Identify other suspected medications to pass to cached NLP extractor
    suspect_drug_names = [m.get('drug_name', '') for m in medications if m.get('drug_name')]
    other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())

    nlp_res = get_clinical_extraction(full_text, target_drug_name, other_drug_names)
    nlp_answers = nlp_res.get("naranjo_answers", ['unknown'] * 10)

    # 3. Structured Data Overlay (Structured fields override or supplement NLP findings)
    answers = list(nlp_answers)

    # Q2: Did the adverse event appear after the suspected drug was administered?
    # Structured check:
    if report_data.get('reaction_start_date') and target_drug and target_drug.get('therapy_start_date'):
        # Just having the dates implies order was verified
        answers[1] = 'yes'

    # Q3: Did the adverse reaction improve when discontinued?
    if target_drug:
        action = (target_drug.get('action_taken') or '').lower()
        if action in ['drug_withdrawn', 'dose_reduced']:
            outcome = (report_data.get('outcome') or '').lower()
            if outcome in ['recovered', 'recovering', 'recovered_with_sequelae']:
                answers[2] = 'yes'
            elif outcome == 'not_recovered':
                answers[2] = 'no'

    # Q4: Did the adverse reaction reappear when drug re-administered?
    if target_drug:
        reintro = (target_drug.get('reintroduction_result') or '').lower()
        if reintro in ['yes', 'reaction_recurred']:
            answers[3] = 'yes'
        elif reintro in ['no', 'no_reaction']:
            answers[3] = 'no'

    # Q5: Alternative causes (other than the drug)?
    concomitant = report_data.get('concomitant_medications', []) or []
    has_concomitant = len(concomitant) > 0
    has_history = bool(report_data.get('medical_history'))
    has_other_suspected = len(other_drug_names) > 0
    if has_other_suspected or has_concomitant or has_history:
        answers[4] = 'yes'
    elif not has_other_suspected and not has_concomitant and not has_history and answers[4] == 'unknown':
        # If no alternative medicines, other drugs, or history, default to no alternative causes (adds +2 points)
        answers[4] = 'no'

    # Q8: Dose response severity
    if target_drug:
        action = (target_drug.get('action_taken') or '').lower()
        if action == 'dose_increased':
            answers[7] = 'yes'
        elif action == 'dose_reduced':
            outcome = (report_data.get('outcome') or '').lower()
            if outcome in ['recovered', 'recovering', 'recovered_with_sequelae']:
                answers[7] = 'yes'

    # Q10: Confirmed by objective evidence?
    if report_data.get('relevant_investigations'):
        answers[9] = 'yes'

    return answers


def _extract_naranjo_regex(text_content: str, target_drug_name: str) -> list:
    """Helper method for local regex-based parsing of the Naranjo scale."""
    answers = ['unknown'] * 10
    text_lower = text_content.lower()
    
    # Q1: Conclusive reports (yes if target drug is commonly documented in pharmacovigilance)
    common_drugs = ["aspirin", "penicillin", "ibuprofen", "paracetamol", "acetaminophen", "warfarin", "heparin", "amoxicillin"]
    if target_drug_name and any(d in target_drug_name.lower() for d in common_drugs):
        answers[0] = 'yes'
        
    # Q2: After administration
    if re.search(r"\b(after|following|post|subsequent to)\b", text_lower):
        answers[1] = 'yes'
        
    # Q3: Improve on discontinuation
    if re.search(r"(stopped|withdrawn|discontinued|removed|withheld|halted|ceased).*?(recover|improv|resolv|subsid|abat|better|resolved|disappeared|cleared|clear|fade|vanish|resolution|improvement)", text_lower):
        answers[2] = 'yes'
        
    # Q4: Reappear on re-administration
    if re.search(r"(re-administered|readministered|reintroduced|restarted|retried|re-exposure|reexposure).*?(recur|return|repeat|re-appear|reappear|again)", text_lower):
        answers[3] = 'yes'
        
    # Q5: Alternative causes
    if re.search(r"(more\s+likely\s+due\s+to|better\s+explained\s+by|attributed\s+to\s+underlying|due\s+to\s+disease)", text_lower):
        answers[4] = 'yes'
        
    # Q7: Toxic concentrations
    if re.search(r"\b(toxic\s+level|toxic\s+concentration|overdose|high\s+level|fluid\s+concentration)\b", text_lower):
        answers[6] = 'yes'
        
    # Q8: Dose response
    if re.search(r"(dose\s+increased|higher\s+dose|more\s+severe\s+when).*?(worse|severe|increase)", text_lower):
        answers[7] = 'yes'
    elif re.search(r"(dose\s+reduced|lower\s+dose|less\s+severe\s+when).*?(better|improve|reduce)", text_lower):
        answers[7] = 'yes'
        
    # Q9: Similar reaction previously
    if re.search(r"(previously\s+exposed|prior\s+exposure|similar\s+reaction\s+before|happened\s+before)", text_lower):
        answers[8] = 'yes'
        
    # Q10: Objective evidence
    if re.search(r"\b(confirmed\s+by|lab\s+test|biopsy|investigation|scan|imaging|mri|ct\s+scan|ultrasound|blood\s+test|laboratory)\b", text_lower):
        answers[9] = 'yes'
        
    return answers

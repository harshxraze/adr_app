"""
Strict WHO-UMC Causality Assessment System with Healthcare NLP.
Implements the official WHO-UMC causality algorithm using a two-layer architecture:
1. Extraction Layer (Google Cloud Healthcare NLP / Gemini fallback / local regex heuristics).
2. Logic Layer (Strict Boolean logic categorical classification tree).
"""

import re
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()


WHO_UMC_CATEGORIES = {
    "Certain": "Event with plausible time relationship; cannot be explained by disease or other drugs; response to withdrawal plausible; event definitive; rechallenge satisfactory if performed.",
    "Probable/Likely": "Event with reasonable time relationship; unlikely to be attributed to disease or other drugs; response to withdrawal clinically reasonable; rechallenge not required.",
    "Possible": "Event with reasonable time relationship; could also be explained by disease or other drugs; information on drug withdrawal may be lacking or unclear.",
    "Unlikely": "Event with a time to drug intake that makes a relationship improbable; disease or other drugs provide plausible explanations.",
    "Conditional/Unclassified": "More data for proper assessment needed.",
    "Unassessable/Unclassifiable": "Information is insufficient or contradictory; data cannot be supplemented."
}

_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"]

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value: return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None

# ==========================================
# Initialize Clients & NLP
# ==========================================

from ml.nlp_extractor import get_clinical_extraction, classify_drug_risk


# ==========================================
# Layer 1: Clinical Description NLP Extraction
# ==========================================

def analyze_clinical_description(description_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
    """
    Parses free-text clinical description to extract context and relationships.
    Uses the unified cached clinical NLP extractor.
    """
    nlp_res = get_clinical_extraction(description_text, target_drug_name, other_drugs)
    return {
        "alternative_is_more_likely": nlp_res["alternative_is_more_likely"],
        "pharmacologically_definitive": nlp_res["pharmacologically_definitive"],
        "nlp_positive_dechallenge": nlp_res["nlp_positive_dechallenge"]
    }



# ==========================================
# Layer 2: Strict WHO-UMC Logic Engine
# ==========================================

def assess_who_umc(form_payload: dict, nlp_context: Optional[dict] = None, target_drug_name: str = "") -> dict:
    """
    Evaluates causality using a strict, Boolean-based categorical logic tree.
    """
    suspect_drugs = form_payload.get("medications", []) or []
    target_drug = None

    # Retrieve target drug object
    if target_drug_name:
        target_drug = next((d for d in suspect_drugs if d.get("drug_name", "").lower() == target_drug_name.lower()), None)
    
    # Fallback matches
    if not target_drug:
        target_drug = form_payload.get("suspected_drug")
    if not target_drug and suspect_drugs:
        target_drug = suspect_drugs[0]
        if not target_drug_name:
            target_drug_name = target_drug.get("drug_name", "")
            
    if not target_drug:
        target_drug = {}

    # Load/Generate NLP context if not provided
    if nlp_context is None:
        description_text = form_payload.get("reaction_description") or ""
        medical_history = form_payload.get("medical_history") or ""
        additional_info = form_payload.get("additional_info") or ""
        relevant_investigations = form_payload.get("relevant_investigations") or ""
        full_text = f"Description: {description_text}. Investigations: {relevant_investigations}. Medical History: {medical_history}. Additional Info: {additional_info}"
        
        suspect_drug_names = [d.get("drug_name", "") for d in suspect_drugs if d.get("drug_name")]
        other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())
        
        nlp_context = analyze_clinical_description(full_text, target_drug_name, other_drug_names)

    # 1. Unassessable & Conditional Checks (Pre-tree filters)
    if form_payload.get("unverifiable_or_contradictory", False):
        return {"category": "Unassessable/Unclassifiable", "reason": "Data cannot be supplemented or verified."}
    if form_payload.get("data_being_actively_collected", False):
        return {"category": "Conditional/Unclassified", "reason": "Additional data currently under examination."}

    # 2. Calculate Temporal Status
    reaction_start = _parse_date(form_payload.get("reaction_start_date"))
    therapy_start = _parse_date(target_drug.get("therapy_start_date"))
    
    temporal_status = "absent"
    if reaction_start and therapy_start:
        days_diff = (reaction_start - therapy_start).days
        if days_diff < 0:
            temporal_status = "improbable"
        elif 0 <= days_diff <= 3:
            temporal_status = "plausible"
        else:
            temporal_status = "reasonable"
    else:
        # Fallback to NLP temporal relationship if dates are missing
        nlp_temp = nlp_context.get("temporal_relationship", "unknown")
        if nlp_temp in ["plausible", "reasonable", "improbable"]:
            temporal_status = nlp_temp
        else:
            temporal_status = "reasonable"  # Clinical fallback default if unknown but not improbable

    # 3. Calculate Dechallenge & Rechallenge
    action_taken = (target_drug.get("action_taken") or "").lower()
    outcome = (form_payload.get("outcome") or "").lower()
    reintro = (target_drug.get("reintroduction_result") or "").lower()
    
    # NLP-derived rechallenge from Naranjo Q4
    nlp_rechallenge = False
    if nlp_context and nlp_context.get("naranjo_answers") and len(nlp_context["naranjo_answers"]) > 3:
        if nlp_context["naranjo_answers"][3] == 'yes':
            nlp_rechallenge = True
            
    rechallenge = "lacking"
    if reintro == "yes" or nlp_rechallenge:
        rechallenge = "positive"
    elif reintro == "no":
        rechallenge = "negative"
    
    # Determine concurrent withdrawals of high-risk drugs
    withdrawn_high_risk = []
    for d in suspect_drugs:
        act = (d.get("action_taken") or "").lower()
        if act in ["drug_withdrawn", "dose_reduced"]:
            if classify_drug_risk(d.get("drug_name", "")) == 'high_risk':
                stop_date = d.get("therapy_stop_date") or "unknown"
                withdrawn_high_risk.append(stop_date)
                
    is_ambiguous = len(withdrawn_high_risk) > 1
    
    dechallenge = "lacking"
    if action_taken in ["drug_withdrawn", "dose_reduced"]:
        if outcome in ["recovered", "recovering", "recovered_with_sequelae"]:
            if is_ambiguous:
                dechallenge = "ambiguous"
            else:
                dechallenge = "positive"
        elif outcome == "not_recovered":
            dechallenge = "negative"
            
    # NLP fallback if structured fields are blank
    if dechallenge == "lacking" and nlp_context.get("nlp_positive_dechallenge"):
        dechallenge = "positive"

    # Implied positive dechallenge via positive rechallenge
    if rechallenge == "positive":
        dechallenge = "positive"

    # 4. Calculate Alternative Causes
    has_concomitant = len(form_payload.get("concomitant_medications", []) or []) > 0
    has_history = bool(form_payload.get("medical_history"))
    
    # Classify other suspect drugs to check if there are other high-risk alternative causes
    other_high_risk = []
    for d in suspect_drugs:
        d_name = d.get("drug_name", "")
        if d_name and d_name.lower() != target_drug_name.lower():
            if classify_drug_risk(d_name) == 'high_risk':
                other_high_risk.append(d_name)
                
    has_multiple_suspects_high_risk = len(other_high_risk) > 0
    
    alt_causes = "none"
    if nlp_context.get("alternative_is_more_likely"):
        alt_causes = "plausible"
    elif has_multiple_suspects_high_risk or has_concomitant or has_history:
        alt_causes = "possible"
        
    # Implied override: positive rechallenge on this drug rules out alternative explanations
    if rechallenge == "positive":
        alt_causes = "none"

    # 5. Classification Tree Evaluation (Strict Order)
    
    # CERTAIN: Temporal plausible AND Alternatives none AND Dechallenge positive AND (pharmacologically_definitive is True OR rechallenge is positive)
    if (temporal_status == "plausible" and 
        alt_causes == "none" and 
        dechallenge == "positive" and 
        (nlp_context.get("pharmacologically_definitive") is True or rechallenge == "positive")):
        return {
            "category": "Certain", 
            "reason": "Event with plausible time relationship; cannot be explained by disease or other drugs; response to withdrawal positive; event is pharmacologically definitive or confirmed by positive rechallenge."
        }
        
    # PROBABLE/LIKELY: Temporal plausible/reasonable AND Alternatives none AND Dechallenge positive
    if (temporal_status in ["plausible", "reasonable"] and 
        alt_causes == "none" and 
        dechallenge == "positive"):
        return {
            "category": "Probable/Likely", 
            "reason": "Event with reasonable time relationship; unlikely to be attributed to disease or other drugs; response to withdrawal positive."
        }
        
    # UNLIKELY: Temporal improbable OR Temporal absent OR Alternatives plausible (via NLP override)
    if (temporal_status == "improbable" or 
        temporal_status == "absent" or 
        alt_causes == "plausible"):
        return {
            "category": "Unlikely", 
            "reason": "Event with time to drug intake making relationship improbable, or alternative explanations are highly plausible based on clinical NLP analysis."
        }
        
    # POSSIBLE: Temporal plausible/reasonable AND (Alternatives possible OR Dechallenge lacking/ambiguous/negative)
    if (temporal_status in ["plausible", "reasonable"] and 
        (alt_causes == "possible" or dechallenge in ["lacking", "ambiguous", "negative"])):
        return {
            "category": "Possible", 
            "reason": "Event with reasonable time relationship; could also be explained by disease or other drugs; response to withdrawal lacks confirmation."
        }

    # Failsafe fallback: Unassessable/Unclassifiable
    return {
        "category": "Unassessable/Unclassifiable", 
        "reason": "Information is insufficient, contradictory, or cannot be categorized."
    }


# ==========================================
# Payload Mapper — Per-drug assessment
# ==========================================

def run_assessment(form_data: dict, target_drug_name: str) -> dict:
    """
    Maps raw form data to the specific drug being evaluated.
    Uses Layer 1 extraction and executes Layer 2 Logic Tree.
    """
    suspect_drugs = form_data.get("medications", []) or []
    target_drug = next((d for d in suspect_drugs if d.get("drug_name", "").lower() == target_drug_name.lower()), None)
    
    if not target_drug:
        return {"category": "Unassessable/Unclassifiable", "reason": "Target drug not found in payload."}

    # Extract NLP clinical context
    description_text = form_data.get("reaction_description") or ""
    medical_history = form_data.get("medical_history") or ""
    additional_info = form_data.get("additional_info") or ""
    full_text = f"Description: {description_text}. Medical History: {medical_history}. Additional Info: {additional_info}"
    
    suspect_drug_names = [d.get("drug_name", "") for d in suspect_drugs if d.get("drug_name")]
    other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())
    
    nlp_context = analyze_clinical_description(full_text, target_drug_name, other_drug_names)
    
    # Assess causality using Logic Tree
    return assess_who_umc(form_data, nlp_context, target_drug_name)


# ==========================================
# assess_from_api_payload — called by app.py
# ==========================================

def assess_from_api_payload(form_data: dict) -> dict:
    """
    Evaluates each suspected medication individually and returns
    the overall assessment (worst-case/strongest category across all drugs).
    """
    suspect_drugs = form_data.get("medications", []) or []
    if not suspect_drugs:
        return {"category": "Unassessable/Unclassifiable", "reason": "No suspected medications found."}

    # Severity ordering for picking the strongest category
    severity_order = [
        "Certain",
        "Probable/Likely",
        "Possible",
        "Unlikely",
        "Conditional/Unclassified",
        "Unassessable/Unclassifiable",
    ]

    best_result = None
    best_rank = len(severity_order)

    for drug in suspect_drugs:
        drug_name = drug.get("drug_name", "")
        if not drug_name:
            continue
        result = run_assessment(form_data, drug_name)
        rank = severity_order.index(result["category"]) if result["category"] in severity_order else len(severity_order)
        if rank < best_rank:
            best_rank = rank
            best_result = result

    if best_result is None:
        return {"category": "Unassessable/Unclassifiable", "reason": "Could not evaluate any suspected medication."}

    return best_result
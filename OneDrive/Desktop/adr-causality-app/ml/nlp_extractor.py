"""
Unified Clinical NLP and Multi-Criteria Causality Extractor.
Implements the WHO-UMC Criteria-Based Scoring Scale and Naranjo Algorithm
by synthesizing all ADR report fields (patient demographics, clinical narrative,
investigations, medical history, full drug regimens, dechallenge & rechallenge).
"""

import re
import os
import json
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()

# Initialize Gemini Client
gemini_client = None
try:
    from google import genai
    from google.genai import types
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if api_key:
        gemini_client = genai.Client(api_key=api_key)
except Exception:
    pass


def classify_drug_risk(drug_name: str) -> str:
    """Classifies drug name into high_risk, low_risk, or unknown."""
    if not drug_name:
        return 'unknown'
    name_lower = drug_name.lower().strip()
    
    # Common high-risk drug groups: Antibiotics, NSAIDs/Analgesics, Anticonvulsants, Gout meds, Chemo
    high_risk_keywords = [
        # Antibiotics
        "cef", "taxim", "antibiotic", "penicillin", "amoxicillin", "ampicillin", 
        "cipro", "levo", "moxi", "sulfa", "bactrim", "gentamicin", "linezolid", 
        "ofloxacin", "norfloxacin", "azithromycin", "clarithromycin", "erythromycin",
        "metronidazole", "tinidazole", "doxycycline", "tetracycline", "clav", "podoxim",
        "meropenem", "vancomycin", "piperacillin", "tazobactam", "amikacin",
        # NSAIDs / Analgesics
        "aceclo", "zerodol", "ibuprofen", "paracetamol", "acetaminophen", "diclofenac", 
        "aspirin", "naproxen", "ketorolac", "mefenamic", "nsaid", "analgesic", "nimesulide", 
        "piroxicam", "meloxicam", "pcm", "trolka", "dynapar", "tramadol", "combiflam",
        # Anticonvulsants & Antiepileptics
        "phenytoin", "carbamazepine", "allopurinol", "valproate", "phenobarbital", "lamotrigine",
        "levetiracetam", "oxcarbazepine",
        # Cardiovascular & Anticoagulants
        "warfarin", "heparin", "enoxaparin", "dabigatran", "amiodarone", "digoxin"
    ]
    # Common low-risk supportive/prophylactic drug groups: PPIs, H2 blockers, Antispasmodics, Vitamins, Antacids
    low_risk_keywords = [
        # PPIs & H2 blockers
        "pantoprazole", "pantocid", "pan", "somiraz", "somira", "somra", "sompraz", 
        "omeprazole", "rabeprazole", "esomeprazole", "ppi", "ranitidine", "famotidine", 
        "lansoprazole", "dexrabeprazole",
        # Antacids & Gastroprotectants
        "gelusil", "antacid", "sucralfate", "mucaine", "digene",
        # Antispasmodics & Prokinetics
        "gldicet", "glidicet", "glidi", "dicyclomine", "spasm", "drotaverine", "mebeverine",
        "domperidone", "itopride", "metoclopramide",
        # Vitamins & Supplements
        "vit", "calcium", "zinc", "folic", "multivitamin", "supplement", "b-complex", 
        "neurobion", "folvite", "becosules", "shelcal"
    ]
    
    for kw in high_risk_keywords:
        if kw in name_lower:
            return 'high_risk'
            
    for kw in low_risk_keywords:
        if kw in name_lower:
            return 'low_risk'
            
    return 'unknown'


def build_clinical_dossier(report_data: dict, target_drug_name: str) -> str:
    """
    Constructs a comprehensive, standardized clinical dossier string from all report fields.
    """
    lines = []
    lines.append(f"=== ADR CLINICAL CASE REPORT (Target Drug: {target_drug_name}) ===")
    
    # 1. Patient Demographics
    patient_info = []
    if report_data.get('patient_initials'): patient_info.append(f"Initials: {report_data['patient_initials']}")
    if report_data.get('patient_age'): patient_info.append(f"Age: {report_data['patient_age']}")
    if report_data.get('gender'): patient_info.append(f"Gender: {report_data['gender']}")
    if report_data.get('weight_kg'): patient_info.append(f"Weight: {report_data['weight_kg']} kg")
    lines.append(f"Patient Profile: {', '.join(patient_info) if patient_info else 'Not provided'}")

    # 2. Reaction Profile
    lines.append(f"Reaction Narrative: {report_data.get('reaction_description') or 'None'}")
    lines.append(f"Reaction Start Date: {report_data.get('reaction_start_date') or 'Unknown'}")
    lines.append(f"Reaction Stop Date: {report_data.get('reaction_stop_date') or 'Ongoing/Unknown'}")
    
    # Seriousness & Outcome
    seriousness_reasons = []
    if report_data.get('seriousness_death'): seriousness_reasons.append("Death")
    if report_data.get('seriousness_life_threatening'): seriousness_reasons.append("Life Threatening")
    if report_data.get('seriousness_hospitalization'): seriousness_reasons.append("Hospitalization")
    if report_data.get('seriousness_disability'): seriousness_reasons.append("Disability")
    if report_data.get('seriousness_congenital_anomaly'): seriousness_reasons.append("Congenital Anomaly")
    if report_data.get('seriousness_other'): seriousness_reasons.append("Other Medically Important")
    
    is_serious = report_data.get('is_serious', False)
    ser_str = f"Yes ({', '.join(seriousness_reasons)})" if seriousness_reasons else ("Yes" if is_serious else "No")
    lines.append(f"Serious Event: {ser_str}")
    lines.append(f"Clinical Outcome: {report_data.get('outcome') or 'Unknown'}")
    lines.append(f"Relevant Diagnostic Investigations & Lab Tests: {report_data.get('relevant_investigations') or 'None reported'}")
    lines.append(f"Medical & Medication History / Underlying Diseases: {report_data.get('medical_history') or 'None reported'}")

    # 3. Target Drug Specifics
    meds = report_data.get('medications', []) or []
    target_drug = next((m for m in meds if m.get('drug_name', '').lower() == target_drug_name.lower()), None)
    if not target_drug and meds:
        target_drug = meds[0]
    
    if target_drug:
        lines.append("\n--- Target Suspected Drug Details ---")
        lines.append(f"Drug Name: {target_drug.get('drug_name', target_drug_name)}")
        lines.append(f"Dose & Frequency: {target_drug.get('dose', '—')} {target_drug.get('frequency', '')} via {target_drug.get('route', '—')}")
        lines.append(f"Therapy Dates: {target_drug.get('therapy_start_date', 'Unknown')} to {target_drug.get('therapy_stop_date', 'Ongoing/Unknown')}")
        lines.append(f"Indication for Use: {target_drug.get('indication', '—')}")
        lines.append(f"Action Taken Following Reaction: {target_drug.get('action_taken', 'Unknown')}")
        lines.append(f"Rechallenge / Re-exposure Result: {target_drug.get('reintroduction_result', 'Not done')} (Dose: {target_drug.get('reintroduction_dose', 'N/A')})")

    # 4. Other Suspected Medications
    other_suspects = [m for m in meds if m.get('drug_name', '').lower() != target_drug_name.lower() and m.get('drug_name')]
    if other_suspects:
        lines.append("\n--- Other Concurrently Suspected Medications ---")
        for m in other_suspects:
            lines.append(f"- {m.get('drug_name')}: Dose {m.get('dose', '—')}, Action Taken: {m.get('action_taken', '—')}, Start: {m.get('therapy_start_date', '—')}, Stop: {m.get('therapy_stop_date', '—')}")

    # 5. Concomitant Medications
    concomitant = report_data.get('concomitant_medications', []) or []
    if concomitant:
        lines.append("\n--- Concomitant / Non-Suspect Medications & Supplements ---")
        for c in concomitant:
            lines.append(f"- {c.get('drug_name')}: Dose {c.get('dose', '—')}, Indication: {c.get('indication', '—')}, Dates: {c.get('therapy_start_date', '—')} to {c.get('therapy_stop_date', '—')}")

    # 6. Additional Notes
    if report_data.get('additional_info'):
        lines.append(f"\nAdditional Clinical Information: {report_data['additional_info']}")

    return "\n".join(lines)


@lru_cache(maxsize=128)
def get_clinical_extraction(dossier_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
    """
    Evaluates the clinical case against the WHO-UMC Criteria-Based Scoring Scale
    and Naranjo ADR Probability Scale using Gemini API with intelligent fallback.
    """
    if not dossier_text or not dossier_text.strip():
        return _extract_deterministic_who_and_naranjo(dossier_text, target_drug_name, other_drugs)

    res = None

    if gemini_client:
        try:
            prompt = f"""
You are an expert pharmacovigilance clinical assessment AI implementing the official WHO-UMC Criteria-Based Scoring Scale and Naranjo Algorithm.

Analyze this complete clinical ADR case dossier for the target drug "{target_drug_name}":

{dossier_text}

Evaluate the case according to these EXACT criteria:

### 1. WHO-UMC Criteria-Based Scoring Scale:
- Criteria 1 (Time relationship to drug intake):
  * "Yes" (+3): Timing between drug start and reaction onset is pharmacologically and clinically plausible (e.g. onset minutes to days after starting, or expected latency).
  * "Maybe" (+2): Timing is reasonable but less immediate or less clear.
  * "No" (-2): Reaction onset preceded drug administration or latency is biologically incompatible.

- Criteria 2 (Alternative etiologies - disease or other drugs):
  * "Cannot be explained by disease or other drugs" (+3): No underlying disease or other concurrent medication can explain the event.
  * "Unlikely to be attributed to disease or other drugs" (+2): Alternative causes are present but unlikely to explain the clinical picture compared to the target drug.
  * "Could also be explained by disease or other drugs" (+1): Other suspected drugs (e.g. concurrent antibiotics/NSAIDs) or underlying condition (e.g. viral illness) could reasonably explain the event.
  * "Disease or other drugs provide plausible explanations" (-2): An alternative etiology (another high-risk drug or active pathology) is the primary plausible cause.

- Criteria 3 (Response to withdrawal / Dechallenge):
  * "Plausible (pharmacologically, pathologically)" (+3): Clear improvement/resolution after drug withdrawal or dose reduction, consistent with pharmacology.
  * "Clinically reasonable" (+2): Patient recovered/improved after withdrawal, but with standard clinical lag or supportive care.
  * "Information on drug withdrawal lacking or unclear" (0): Drug was not stopped, patient died, reaction ongoing, or withdrawal data unknown.
  * "No improvement / Negative dechallenge" (-2): Drug was withdrawn but reaction persisted without improvement.

- Criteria 4 (Rechallenge outcome):
  * "Satisfactory (positive rechallenge, if necessary)" (+2): Reaction recurred upon deliberate re-exposure or prior identical exposure.
  * "Rechallenge not required / Not done" (0): Rechallenge was not performed or not clinically necessary.
  * "Negative rechallenge (reaction did not recur)" (-2): Drug was re-administered and the reaction did NOT recur.

- Criteria 5 (Phenomenological / Pharmacological nature):
  * "Yes" (+2): The event is a definitive pharmacological or phenomenological reaction (e.g. anaphylaxis, SJS/TEN, drug-induced liver injury, specific known ADR mechanism, toxic blood level).
  * "No / Non-specific clinical event" (0): Non-specific or subjective clinical symptom (e.g. mild nausea, headache, malaise).

- Criteria 6 (Data completeness and validity):
  * "Sufficient data available for evaluation" (score: 0, flag: "None")
  * "More data needed or under examination" (flag: "Conditional")
  * "Insufficient or contradictory data that cannot be supplemented/verified" (flag: "Unassessable")

### 2. Naranjo Algorithm (10 Questions):
Provide a list of 10 answers ('yes', 'no', 'unknown') for:
Q1: Previous conclusive reports in literature for this drug-reaction pair?
Q2: Adverse event appeared after the suspected drug was administered?
Q3: Adverse reaction improved when drug discontinued or specific antagonist given?
Q4: Adverse reaction reappeared when drug re-administered?
Q5: Alternative causes (other drugs, underlying disease) that could have caused the reaction?
Q6: Reaction reappeared when placebo given?
Q7: Drug detected in blood/fluids in toxic concentrations?
Q8: Reaction more severe with increased dose, or less severe with decreased dose?
Q9: Similar reaction to same or similar drugs in previous exposure?
Q10: Confirmed by objective evidence (lab test, biopsy, clinical photos)?

Output a JSON object with this exact structure:
{{
  "who_umc": {{
    "time_relationship": {{
      "criterion": "Yes" | "Maybe" | "No",
      "score": 3 | 2 | -2,
      "reason": "Brief clinical rationale"
    }},
    "alternative_etiologies": {{
      "criterion": "Cannot be explained by disease or other drugs" | "Unlikely to be attributed to disease or other drugs" | "Could also be explained by disease or other drugs" | "Disease or other drugs provide plausible explanations",
      "score": 3 | 2 | 1 | -2,
      "reason": "Brief clinical rationale"
    }},
    "dechallenge": {{
      "criterion": "Plausible (pharmacologically, pathologically)" | "Clinically reasonable" | "Information on drug withdrawal lacking or unclear" | "No improvement / Negative dechallenge",
      "score": 3 | 2 | 0 | -2,
      "reason": "Brief clinical rationale"
    }},
    "rechallenge": {{
      "criterion": "Satisfactory (positive rechallenge, if necessary)" | "Rechallenge not required / Not done" | "Negative rechallenge (reaction did not recur)",
      "score": 2 | 0 | -2,
      "reason": "Brief clinical rationale"
    }},
    "phenomenological_nature": {{
      "criterion": "Yes" | "No / Non-specific clinical event",
      "score": 2 | 0,
      "reason": "Brief clinical rationale"
    }},
    "data_completeness": {{
      "status": "sufficient" | "conditional" | "unassessable",
      "flag": "None" | "Conditional" | "Unassessable",
      "reason": "Brief explanation"
    }}
  }},
  "naranjo_answers": ["yes"|"no"|"unknown", ... (10 elements)],
  "clinical_summary": "Brief 1-sentence synthesis"
}}
"""
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            data = json.loads(text.strip())
            
            who = data.get("who_umc", {})
            naranjo = data.get("naranjo_answers", ["unknown"] * 10)
            if len(naranjo) < 10:
                naranjo.extend(["unknown"] * (10 - len(naranjo)))
            naranjo = [str(a).lower().strip() for a in naranjo[:10]]

            res = {
                "who_umc": who,
                "naranjo_answers": naranjo,
                "clinical_summary": data.get("clinical_summary", "")
            }
        except Exception as e:
            print(f"[Causality NLP] Gemini API error: {e}. Falling back to deterministic clinical rules.")
            pass

    if not res:
        res = _extract_deterministic_who_and_naranjo(dossier_text, target_drug_name, other_drugs)

    return res


def _extract_deterministic_who_and_naranjo(dossier_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
    """
    Deterministic rule-based clinical scoring fallback when Gemini API is offline.
    Implements all 6 WHO-UMC criteria and Naranjo questions.
    """
    text_lower = (dossier_text or "").lower()
    target_lower = (target_drug_name or "").lower()

    # 1. Timeline / Time Relationship
    time_score = 2
    time_criterion = "Maybe"
    time_reason = "Timeline between drug initiation and reaction onset is clinically reasonable."
    
    if re.search(r"\b(before\s+taking|prior\s+to\s+starting|preceded\s+drug)\b", text_lower):
        time_score = -2
        time_criterion = "No"
        time_reason = "Reaction onset preceded or is incompatible with drug administration timeline."
    elif re.search(r"\b(immediate|within\s+(minutes|hours|24\s+hours|1\s+day|2\s+days|3\s+days)|same\s+day|shortly\s+after)\b", text_lower):
        time_score = 3
        time_criterion = "Yes"
        time_reason = "Yes — plausible and immediate temporal onset following drug intake."

    # 2. Alternative Etiologies
    alt_score = 2
    alt_criterion = "Unlikely to be attributed to disease or other drugs"
    alt_reason = "Unlikely to be attributed solely to concurrent disease or low-risk therapies."

    target_risk = classify_drug_risk(target_drug_name)
    other_high_risk = [d for d in other_drugs if classify_drug_risk(d) == 'high_risk']

    if target_risk == 'low_risk' and other_high_risk:
        alt_score = -2
        alt_criterion = "Disease or other drugs provide plausible explanations"
        alt_reason = f"Other co-administered high-risk agents ({', '.join(other_high_risk)}) provide a much more plausible explanation."
    elif len(other_drugs) > 0 or "history" in text_lower or "concomitant" in text_lower:
        alt_score = 1
        alt_criterion = "Could also be explained by disease or other drugs"
        alt_reason = "Concurrent medications or medical history could also contribute to the reaction."
    elif "no alternative" in text_lower or len(other_drugs) == 0:
        alt_score = 3
        alt_criterion = "Cannot be explained by disease or other drugs"
        alt_reason = "No concurrent disease or other medications can explain the clinical manifestation."

    # 3. Dechallenge
    dech_score = 0
    dech_criterion = "Information on drug withdrawal lacking or unclear"
    dech_reason = "Drug cessation data or improvement status is unconfirmed or not recorded."

    if re.search(r"\b(action\s+taken.*?(withdrawn|reduced|stopped|discontinued))\b", text_lower) or \
       re.search(r"\b(stopped|withdrawn|discontinued|halted)\b", text_lower):
        if re.search(r"\b(outcome.*?(recovered|recovering|resolved|improved|better|cleared))\b", text_lower) or \
           re.search(r"\b(resolved|improved|subsided|abated|recovered|cleared\s+up)\b", text_lower):
            dech_score = 3 if time_score == 3 else 2
            dech_criterion = "Plausible (pharmacologically, pathologically)" if time_score == 3 else "Clinically reasonable"
            dech_reason = "Symptoms resolved or improved substantially following drug withdrawal."
        elif "not recovered" in text_lower or "fatal" in text_lower:
            dech_score = -2
            dech_criterion = "No improvement / Negative dechallenge"
            dech_reason = "Reaction persisted without improvement despite drug withdrawal."

    # 4. Rechallenge
    rech_score = 0
    rech_criterion = "Rechallenge not required / Not done"
    rech_reason = "Drug rechallenge was not performed or not clinically indicated."

    if re.search(r"\b(reintroduction.*?(yes|reappeared|recurred))\b", text_lower) or \
       re.search(r"\b(recurred\s+on\s+re-exposure|reappeared\s+on\s+rechallenge|positive\s+rechallenge)\b", text_lower):
        rech_score = 2
        rech_criterion = "Satisfactory (positive rechallenge, if necessary)"
        rech_reason = "Reaction confirmed to recur upon drug re-administration."
    elif re.search(r"\b(reintroduction.*?(no|no\s+recurrence))\b", text_lower):
        rech_score = -2
        rech_criterion = "Negative rechallenge (reaction did not recur)"
        rech_reason = "Reaction did not recur upon drug re-exposure."

    # 5. Phenomenological / Pharmacological Nature
    phen_score = 0
    phen_criterion = "No / Non-specific clinical event"
    phen_reason = "Clinical manifestation is non-specific or subjective."

    if re.search(r"\b(anaphylaxis|anaphylactic|sjs|stevens-johnson|toxic\s+epidermal|angioedema|dili|hepatotoxicity|nephrotoxicity|agranulocytosis|fixed\s+drug\s+eruption|urticaria|erythema\s+multiforme|rash|toxic\s+level)\b", text_lower):
        phen_score = 2
        phen_criterion = "Yes"
        phen_reason = "Event is a recognized, definitive pharmacological or immunological ADR phenotype."

    # 6. Data completeness
    comp_status = "sufficient"
    comp_flag = "None"
    comp_reason = "Sufficient clinical data available for causality assessment."

    if not dossier_text or len(dossier_text.strip()) < 20:
        comp_status = "unassessable"
        comp_flag = "Unassessable"
        comp_reason = "Insufficient data to establish causality."

    who_dict = {
        "time_relationship": {"criterion": time_criterion, "score": time_score, "reason": time_reason},
        "alternative_etiologies": {"criterion": alt_criterion, "score": alt_score, "reason": alt_reason},
        "dechallenge": {"criterion": dech_criterion, "score": dech_score, "reason": dech_reason},
        "rechallenge": {"criterion": rech_criterion, "score": rech_score, "reason": rech_reason},
        "phenomenological_nature": {"criterion": phen_criterion, "score": phen_score, "reason": phen_reason},
        "data_completeness": {"status": comp_status, "flag": comp_flag, "reason": comp_reason}
    }

    # Naranjo Answers
    naranjo_answers = ["unknown"] * 10
    
    # Q1: Known literature reaction
    common_high_adr = ["aspirin", "amoxicillin", "penicillin", "ibuprofen", "paracetamol", "phenytoin", "ciprofloxacin", "carbamazepine", "diclofenac"]
    if any(d in target_lower for d in common_high_adr):
        naranjo_answers[0] = "yes"

    # Q2: Appeared after drug
    if time_score > 0:
        naranjo_answers[1] = "yes"
    elif time_score < 0:
        naranjo_answers[1] = "no"

    # Q3: Improved on dechallenge
    if dech_score > 0:
        naranjo_answers[2] = "yes"
    elif dech_score < 0:
        naranjo_answers[2] = "no"

    # Q4: Reappeared on rechallenge
    if rech_score > 0:
        naranjo_answers[3] = "yes"
    elif rech_score < 0:
        naranjo_answers[3] = "no"

    # Q5: Alternative causes
    if alt_score <= 1:
        naranjo_answers[4] = "yes"
    elif alt_score == 3:
        naranjo_answers[4] = "no"

    # Q7: Toxic concentrations
    if "toxic level" in text_lower or "overdose" in text_lower:
        naranjo_answers[6] = "yes"

    # Q8: Dose response
    if "dose increased" in text_lower or "dose reduced" in text_lower:
        naranjo_answers[7] = "yes"

    # Q9: Previous exposure reaction
    if "previous" in text_lower and "reaction" in text_lower:
        naranjo_answers[8] = "yes"

    # Q10: Objective evidence
    if "investigation" in text_lower or "biopsy" in text_lower or "lab test" in text_lower or phen_score > 0:
        naranjo_answers[9] = "yes"

    return {
        "who_umc": who_dict,
        "naranjo_answers": naranjo_answers,
        "clinical_summary": f"Deterministic rule-based evaluation completed for {target_drug_name}."
    }

"""
Unified Clinical NLP Extractor.
Performs a single, cached Gemini API call to extract both WHO-UMC signals
and Naranjo scale answers, reducing API latency by 50% or more.
"""

import re
import os
import json
from functools import lru_cache
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
    
    # Common high-risk drug groups: Antibiotics, NSAIDs/Analgesics, Anticonvulsants, Gout meds
    high_risk_keywords = [
        # Antibiotics
        "cef", "taxim", "antibiotic", "penicillin", "amoxicillin", "ampicillin", 
        "cipro", "levo", "moxi", "sulfa", "bactrim", "gentamicin", "linezolid", 
        "ofloxacin", "norfloxacin", "azithromycin", "clarithromycin", "erythromycin",
        "metronidazole", "tinidazole", "doxycycline", "tetracycline", "clav", "podoxim",
        # NSAIDs / Analgesics
        "aceclo", "zerodol", "ibuprofen", "paracetamol", "acetaminophen", "diclofenac", 
        "aspirin", "naproxen", "ketorolac", "mefenamic", "nsaid", "analgesic", "nimesulide", 
        "piroxicam", "meloxicam", "pcm", "trolka", "dynapar",
        # Anticonvulsants & others
        "phenytoin", "carbamazepine", "allopurinol", "valproate", "phenobarbital", "lamotrigine"
    ]
    # Common low-risk supportive/prophylactic drug groups: PPIs, H2 blockers, Antispasmodics, Vitamins/Supplements, Antacids
    low_risk_keywords = [
        # PPIs & H2 blockers
        "pantoprazole", "pantocid", "pan", "somiraz", "somira", "somra", "sompraz", 
        "omeprazole", "rabeprazole", "esomeprazole", "ppi", "ranitidine", "famotidine", 
        "lansoprazole", "dexrabeprazole",
        # Antacids & Gastroprotectants
        "gelusil", "antacid", "sucralfate", "mucaine",
        # Antispasmodics & Prokinetics
        "gldicet", "glidicet", "glidi", "dicyclomine", "spasm", "drotaverine", "mebeverine",
        "domperidone", "itopride", "metoclopramide",
        # Vitamins & Supplements
        "vit", "calcium", "zinc", "folic", "multivitamin", "supplement", "b-complex", 
        "neurobion", "folvite"
    ]
    
    for kw in high_risk_keywords:
        if kw in name_lower:
            return 'high_risk'
            
    for kw in low_risk_keywords:
        if kw in name_lower:
            return 'low_risk'
            
    return 'unknown'


@lru_cache(maxsize=128)
def get_clinical_extraction(description_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
    """
    Extracts all clinical features (WHO-UMC and Naranjo) in a single cached call.
    Supports other suspected drugs to run clinical override guardrails.
    """
    # Default fallback values
    fallback_result = {
        "alternative_is_more_likely": False,
        "pharmacologically_definitive": False,
        "nlp_positive_dechallenge": False,
        "temporal_relationship": "unknown",
        "naranjo_answers": ["unknown"] * 10
    }

    if not description_text or not description_text.strip():
        return fallback_result

    res = None

    # Try Gemini extraction
    if gemini_client:
        try:
            other_drugs_str = ", ".join(other_drugs) if other_drugs else "None"
            prompt = f"""
You are an expert pharmacovigilance clinical NLP engine.
Your task is to analyze the following ADR description text:
"{description_text}"

For the target drug: "{target_drug_name}"
Other drugs patient was taking: {other_drugs_str}

Extract the clinical details and return a JSON object with exactly these keys:
1. "alternative_is_more_likely" (boolean): True ONLY if there is another drug or medical condition mentioned in the text that is a more likely cause of the symptom than the target drug.
2. "pharmacologically_definitive" (boolean): True if the event is a definitive pharmacological/immunological reaction (e.g. anaphylaxis, Stevens-Johnson syndrome, toxic drug level).
3. "nlp_positive_dechallenge" (boolean): True if the symptom resolved, improved, or abated after stopping or reducing the target drug.
4. "temporal_relationship" (string): 'plausible', 'reasonable', 'improbable', or 'unknown'. Extract this based on the clinical narrative (e.g., if the reaction occurred within 0-3 days of starting the drug, return 'plausible'; if after 3 days, return 'reasonable'; if it occurred before the drug or is unrelated, return 'improbable').
5. "naranjo_answers" (list of exactly 10 strings): answers ('yes', 'no', or 'unknown') for these Naranjo questions:
   - Q1: Conclusive reports in literature? (Answer 'yes' if this is a common ADR for the target drug like Aspirin causing rash/bleed, otherwise 'unknown').
   - Q2: Event after administration?
   - Q3: Improved on discontinuation/antagonist?
   - Q4: Reappeared on re-administration?
   - Q5: Alternative causes? (Answer 'yes' if there are other suspected drugs mentioned).
   - Q6: Reappeared when placebo given?
   - Q7: Toxic concentrations?
   - Q8: Dose response severity?
   - Q9: Similar reaction previously?
   - Q10: Confirmed by objective evidence?

Your output must be a valid JSON object. Return ONLY the raw JSON, with no markdown formatting or extra text.
"""
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            text = response.text.strip()
            # Clean up markdown formatting if returned
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            nlp_result = json.loads(text.strip())
            
            # Map Naranjo answers list
            naranjo = nlp_result.get("naranjo_answers", ["unknown"] * 10)
            if len(naranjo) < 10:
                naranjo.extend(["unknown"] * (10 - len(naranjo)))
            naranjo = [str(ans).lower().strip() for ans in naranjo[:10]]
            
            res = {
                "alternative_is_more_likely": bool(nlp_result.get("alternative_is_more_likely", False)),
                "pharmacologically_definitive": bool(nlp_result.get("pharmacologically_definitive", False)),
                "nlp_positive_dechallenge": bool(nlp_result.get("nlp_positive_dechallenge", False)),
                "temporal_relationship": str(nlp_result.get("temporal_relationship", "unknown")).lower().strip(),
                "naranjo_answers": naranjo
            }
        except Exception:
            pass

    # Regex heuristic fallback if Gemini failed or is not configured
    if not res:
        res = _extract_regex_fallbacks(description_text, target_drug_name, other_drugs)

    # Apply clinical override guardrail (High-risk vs Low-risk classes)
    target_risk = classify_drug_risk(target_drug_name)
    has_high_risk_other = any(classify_drug_risk(d) == 'high_risk' for d in other_drugs)
    if target_risk == 'low_risk' and has_high_risk_other:
        res["alternative_is_more_likely"] = True
        res["naranjo_answers"][4] = 'yes'

    return res


def _extract_regex_fallbacks(description_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
    """Helper method for local regex-based parsing of both scales."""
    nlp_positive_dechallenge = False
    alternative_is_more_likely = False
    pharmacologically_definitive = False
    temporal_relationship = 'reasonable'
    
    text_lower = description_text.lower()
    
    # WHO-UMC / Naranjo Dechallenge patterns (bidirectional support)
    dechallenge_patterns = [
        r"(stopped|withdrawn|discontinued|removed|withheld|halted|ceased|stopping|discontinuing|withdrawal|withdrawing).*?(recover|improv|resolv|subsid|abat|better|resolved|disappeared|cleared|clear|fade|vanish|resolution|improvement)",
        r"(recover|improv|resolv|subsid|abat|better|resolved|disappeared|cleared|clear|fade|vanish|resolution|improvement).*?(stopped|withdrawn|discontinued|removed|withheld|halted|ceased|stopping|discontinuing|withdrawal|withdrawing)"
    ]
    for pattern in dechallenge_patterns:
        if re.search(pattern, text_lower):
            nlp_positive_dechallenge = True
            break
            
    # Pharmacologically definitive signals
    definitive_patterns = [
        r"\b(anaphylaxis|anaphylactic|sjs|stevens-johnson|toxic\s+epidermal\s+necrolysis|ten|angioedema|drug-induced\s+liver\s+injury|dili|biopsy\s+confirmed)\b"
    ]
    for pattern in definitive_patterns:
        if re.search(pattern, text_lower):
            pharmacologically_definitive = True
            break
            
    # Alternative causes signals
    alt_patterns = [
        r"(more\s+likely\s+due\s+to|better\s+explained\s+by|attributed\s+to\s+underlying|due\s+to\s+disease)",
        r"alternative\s+cause",
    ]
    for pattern in alt_patterns:
        if re.search(pattern, text_lower):
            alternative_is_more_likely = True
            break

    # Clinical alternative explanation: diabetic patient on insulin/hypoglycemics developing hypoglycemia symptoms
    is_hypoglycemic_symptom = any(s in text_lower for s in ["sweating", "weakness", "giddiness", "hypoglycemia", "cold sweat", "tremor", "shaking", "palpitations", "anxiety"])
    is_diabetic_patient = any(d in text_lower for d in ["diabetic", "diabetes", "insulin", "actrapid", "metformin", "glimepiride", "gliclazide"])
    is_target_diabetes_drug = any(d in target_drug_name.lower() for d in ["insulin", "actrapid", "metformin", "glimepiride", "gliclazide", "glidi", "gldicet", "somiraz"])
    
    if is_diabetic_patient and is_hypoglycemic_symptom and not is_target_diabetes_drug:
        alternative_is_more_likely = True

    # Heuristics for temporal relationship
    if re.search(r"\b(immediate|same day|within\s+(a\s+)?day|within\s+24\s+hours|1\s+day\s+later|2\s+days\s+later|two\s+days\s+later)\b", text_lower):
        temporal_relationship = 'plausible'
    elif re.search(r"\b(before\s+starting|prior\s+to\s+taking|before\s+taking)\b", text_lower):
        temporal_relationship = 'improbable'

    # Apply clinical override logic to alternative causes
    target_risk = classify_drug_risk(target_drug_name)
    has_high_risk_other = any(classify_drug_risk(d) == 'high_risk' for d in other_drugs)
    if target_risk == 'low_risk' and has_high_risk_other:
        alternative_is_more_likely = True

    # Naranjo list construction
    naranjo_answers = ['unknown'] * 10
    
    # Q1: Conclusive reports
    common_drugs = ["aspirin", "penicillin", "ibuprofen", "paracetamol", "acetaminophen", "warfarin", "heparin", "amoxicillin"]
    if target_drug_name and any(d in target_drug_name.lower() for d in common_drugs):
        naranjo_answers[0] = 'yes'
        
    # Q2: After administration
    if re.search(r"\b(after|following|post|subsequent to)\b", text_lower):
        naranjo_answers[1] = 'yes'
        
    # Q3: Improve on discontinuation
    if nlp_positive_dechallenge:
        naranjo_answers[2] = 'yes'
        
    # Q4: Reappear on re-administration (including similar episode patterns)
    has_rechallenge = False
    if re.search(r"\b(re-administered|readministered|reintroduced|restarted|retried|re-exposure|reexposure|readministration|reintroduction)\b", text_lower) and re.search(r"\b(recur|return|repeat|re-appear|reappear|again|recurred|reappeared)\b", text_lower):
        has_rechallenge = True
    elif re.search(r"\b(similar\s+episode|similar\s+reaction|similar\s+event|same\s+reaction)\s+(happened|occurred|repeated|reappeared|recurred)\b", text_lower):
        has_rechallenge = True
        
    if has_rechallenge:
        naranjo_answers[3] = 'yes'
        
    # Q5: Alternative causes
    if alternative_is_more_likely:
        naranjo_answers[4] = 'yes'
        
    # Q7: Toxic concentrations
    if re.search(r"\b(toxic\s+level|toxic\s+concentration|overdose|high\s+level|fluid\s+concentration)\b", text_lower):
        naranjo_answers[6] = 'yes'
        
    # Q8: Dose response
    if re.search(r"(dose\s+increased|higher\s+dose|more\s+severe\s+when).*?(worse|severe|increase)", text_lower):
        naranjo_answers[7] = 'yes'
    elif re.search(r"(dose\s+reduced|lower\s+dose|less\s+severe\s+when).*?(better|improve|reduce)", text_lower):
        naranjo_answers[7] = 'yes'
        
    # Q9: Similar reaction previously
    if re.search(r"(previously\s+exposed|prior\s+exposure|similar\s+reaction\s+before|happened\s+before)", text_lower):
        naranjo_answers[8] = 'yes'
        
    # Q10: Objective evidence
    if re.search(r"\b(confirmed\s+by|lab\s+test|biopsy|investigation|scan|imaging|mri|ct\s+scan|ultrasound|blood\s+test|laboratory)\b", text_lower):
        naranjo_answers[9] = 'yes'

    return {
        "alternative_is_more_likely": alternative_is_more_likely,
        "pharmacologically_definitive": pharmacologically_definitive,
        "nlp_positive_dechallenge": nlp_positive_dechallenge,
        "temporal_relationship": temporal_relationship,
        "naranjo_answers": naranjo_answers
    }

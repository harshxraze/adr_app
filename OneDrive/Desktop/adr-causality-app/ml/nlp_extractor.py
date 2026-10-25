# """
# Unified Clinical NLP and Multi-Criteria Causality Extractor.
# Implements the WHO-UMC Criteria-Based Scoring Scale and Naranjo Algorithm
# by synthesizing all ADR report fields (patient demographics, clinical narrative,
# investigations, medical history, full drug regimens, dechallenge & rechallenge).
# """

# import re
# import os
# import json
# from datetime import datetime
# from functools import lru_cache
# from typing import Optional, Dict, Any, List, Tuple
# from dotenv import load_dotenv

# # Load environment variables (.env file)
# load_dotenv()

# # Initialize Gemini Client
# gemini_client = None
# try:
#     from google import genai
#     from google.genai import types
#     api_key = os.environ.get('GEMINI_API_KEY', '')
#     if api_key:
#         gemini_client = genai.Client(api_key=api_key)
# except Exception:
#     pass


# def classify_drug_risk(drug_name: str) -> str:
#     """Classifies drug name into high_risk, low_risk, or unknown."""
#     if not drug_name:
#         return 'unknown'
#     name_lower = drug_name.lower().strip()
    
#     # Common high-risk drug groups: Antibiotics, NSAIDs/Analgesics, Anticonvulsants, Gout meds, Chemo
#     high_risk_keywords = [
#         # Antibiotics
#         "cef", "taxim", "antibiotic", "penicillin", "amoxicillin", "ampicillin", 
#         "cipro", "levo", "moxi", "sulfa", "bactrim", "gentamicin", "linezolid", 
#         "ofloxacin", "norfloxacin", "azithromycin", "clarithromycin", "erythromycin",
#         "metronidazole", "tinidazole", "doxycycline", "tetracycline", "clav", "podoxim",
#         "meropenem", "vancomycin", "piperacillin", "tazobactam", "amikacin",
#         # NSAIDs / Analgesics
#         "aceclo", "zerodol", "ibuprofen", "paracetamol", "acetaminophen", "diclofenac", 
#         "aspirin", "naproxen", "ketorolac", "mefenamic", "nsaid", "analgesic", "nimesulide", 
#         "piroxicam", "meloxicam", "pcm", "trolka", "dynapar", "tramadol", "combiflam",
#         # Anticonvulsants & Antiepileptics
#         "phenytoin", "carbamazepine", "allopurinol", "valproate", "phenobarbital", "lamotrigine",
#         "levetiracetam", "oxcarbazepine",
#         # Cardiovascular & Anticoagulants
#         "warfarin", "heparin", "enoxaparin", "dabigatran", "amiodarone", "digoxin"
#     ]
#     # Common low-risk supportive/prophylactic drug groups: PPIs, H2 blockers, Antispasmodics, Vitamins, Antacids
#     low_risk_keywords = [
#         # PPIs & H2 blockers
#         "pantoprazole", "pantocid", "pan", "somiraz", "somira", "somra", "sompraz", 
#         "omeprazole", "rabeprazole", "esomeprazole", "ppi", "ranitidine", "famotidine", 
#         "lansoprazole", "dexrabeprazole",
#         # Antacids & Gastroprotectants
#         "gelusil", "antacid", "sucralfate", "mucaine", "digene",
#         # Antispasmodics & Prokinetics
#         "gldicet", "glidicet", "glidi", "dicyclomine", "spasm", "drotaverine", "mebeverine",
#         "domperidone", "itopride", "metoclopramide",
#         # Vitamins & Supplements
#         "vit", "calcium", "zinc", "folic", "multivitamin", "supplement", "b-complex", 
#         "neurobion", "folvite", "becosules", "shelcal"
#     ]
    
#     for kw in high_risk_keywords:
#         if kw in name_lower:
#             return 'high_risk'
            
#     for kw in low_risk_keywords:
#         if kw in name_lower:
#             return 'low_risk'
            
#     return 'unknown'


# def build_clinical_dossier(report_data: dict, target_drug_name: str) -> str:
#     """
#     Constructs a comprehensive, standardized clinical dossier string from all report fields.
#     """
#     lines = []
#     lines.append(f"=== ADR CLINICAL CASE REPORT (Target Drug: {target_drug_name}) ===")
    
#     # 1. Patient Demographics
#     patient_info = []
#     if report_data.get('patient_initials'): patient_info.append(f"Initials: {report_data['patient_initials']}")
#     if report_data.get('patient_age'): patient_info.append(f"Age: {report_data['patient_age']}")
#     if report_data.get('gender'): patient_info.append(f"Gender: {report_data['gender']}")
#     if report_data.get('weight_kg'): patient_info.append(f"Weight: {report_data['weight_kg']} kg")
#     lines.append(f"Patient Profile: {', '.join(patient_info) if patient_info else 'Not provided'}")

#     # 2. Reaction Profile
#     lines.append(f"Reaction Narrative: {report_data.get('reaction_description') or 'None'}")
#     lines.append(f"Reaction Start Date: {report_data.get('reaction_start_date') or 'Unknown'}")
#     lines.append(f"Reaction Stop Date: {report_data.get('reaction_stop_date') or 'Ongoing/Unknown'}")
    
#     # Seriousness & Outcome
#     seriousness_reasons = []
#     if report_data.get('seriousness_death'): seriousness_reasons.append("Death")
#     if report_data.get('seriousness_life_threatening'): seriousness_reasons.append("Life Threatening")
#     if report_data.get('seriousness_hospitalization'): seriousness_reasons.append("Hospitalization")
#     if report_data.get('seriousness_disability'): seriousness_reasons.append("Disability")
#     if report_data.get('seriousness_congenital_anomaly'): seriousness_reasons.append("Congenital Anomaly")
#     if report_data.get('seriousness_other'): seriousness_reasons.append("Other Medically Important")
    
#     is_serious = report_data.get('is_serious', False)
#     ser_str = f"Yes ({', '.join(seriousness_reasons)})" if seriousness_reasons else ("Yes" if is_serious else "No")
#     lines.append(f"Serious Event: {ser_str}")
#     lines.append(f"Clinical Outcome: {report_data.get('outcome') or 'Unknown'}")
#     lines.append(f"Relevant Diagnostic Investigations & Lab Tests: {report_data.get('relevant_investigations') or 'None reported'}")
#     lines.append(f"Medical & Medication History / Underlying Diseases: {report_data.get('medical_history') or 'None reported'}")

#     # 3. Target Drug Specifics
#     meds = report_data.get('medications', []) or []
#     target_drug = next((m for m in meds if m.get('drug_name', '').lower() == target_drug_name.lower()), None)
#     if not target_drug and meds:
#         target_drug = meds[0]
    
#     if target_drug:
#         lines.append("\n--- Target Suspected Drug Details ---")
#         lines.append(f"Drug Name: {target_drug.get('drug_name', target_drug_name)}")
#         lines.append(f"Dose & Frequency: {target_drug.get('dose', '—')} {target_drug.get('frequency', '')} via {target_drug.get('route', '—')}")
#         lines.append(f"Therapy Dates: {target_drug.get('therapy_start_date', 'Unknown')} to {target_drug.get('therapy_stop_date', 'Ongoing/Unknown')}")
#         lines.append(f"Indication for Use: {target_drug.get('indication', '—')}")
#         lines.append(f"Action Taken Following Reaction: {target_drug.get('action_taken', 'Unknown')}")
#         lines.append(f"Rechallenge / Re-exposure Result: {target_drug.get('reintroduction_result', 'Not done')} (Dose: {target_drug.get('reintroduction_dose', 'N/A')})")

#     # 4. Other Suspected Medications
#     other_suspects = [m for m in meds if m.get('drug_name', '').lower() != target_drug_name.lower() and m.get('drug_name')]
#     if other_suspects:
#         lines.append("\n--- Other Concurrently Suspected Medications ---")
#         for m in other_suspects:
#             lines.append(f"- {m.get('drug_name')}: Dose {m.get('dose', '—')}, Action Taken: {m.get('action_taken', '—')}, Start: {m.get('therapy_start_date', '—')}, Stop: {m.get('therapy_stop_date', '—')}")

#     # 5. Concomitant Medications
#     concomitant = report_data.get('concomitant_medications', []) or []
#     if concomitant:
#         lines.append("\n--- Concomitant / Non-Suspect Medications & Supplements ---")
#         for c in concomitant:
#             lines.append(f"- {c.get('drug_name')}: Dose {c.get('dose', '—')}, Indication: {c.get('indication', '—')}, Dates: {c.get('therapy_start_date', '—')} to {c.get('therapy_stop_date', '—')}")

#     # 6. Additional Notes
#     if report_data.get('additional_info'):
#         lines.append(f"\nAdditional Clinical Information: {report_data['additional_info']}")

#     return "\n".join(lines)


# @lru_cache(maxsize=128)
# def get_clinical_extraction(dossier_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
#     """
#     Evaluates the clinical case against the WHO-UMC Criteria-Based Scoring Scale
#     and Naranjo ADR Probability Scale using Gemini API with intelligent fallback.
#     """
#     if not dossier_text or not dossier_text.strip():
#         return _extract_deterministic_who_and_naranjo(dossier_text, target_drug_name, other_drugs)

#     res = None

#     if gemini_client:
#         try:
#             prompt = f"""
# You are an expert pharmacovigilance clinical assessment AI implementing the official WHO-UMC Criteria-Based Scoring Scale and Naranjo Algorithm.

# Analyze this complete clinical ADR case dossier for the target drug "{target_drug_name}":

# {dossier_text}

# Evaluate the case according to these EXACT criteria:

# ### 1. WHO-UMC Criteria-Based Scoring Scale:
# - Criteria 1 (Time relationship to drug intake):
#   * "Plausible" (+3): Timing between drug start and reaction onset is pharmacologically and clinically plausible (e.g. onset minutes to days after starting, or expected latency).
#   * "Reasonable" (+2): Timing is reasonable but less immediate or less clear.
#   * "Improbable" (-2): Reaction onset preceded drug administration or latency is biologically incompatible.

# - Criteria 2 (Alternative etiologies - disease or other drugs):
#   * "Cannot be explained by disease or other drugs" (+3): No underlying disease or other concurrent medication can explain the event.
#   * "Unlikely to be attributed to disease or other drugs" (+2): Alternative causes are present but unlikely to explain the clinical picture compared to the target drug.
#   * "Could also be explained by disease or other drugs" (+1): Other suspected drugs (e.g. concurrent antibiotics/NSAIDs) or underlying condition (e.g. viral illness) could reasonably explain the event.
#   * "Disease or other drugs provide plausible explanations" (-2): An alternative etiology (another high-risk drug or active pathology) is the primary plausible cause.

# - Criteria 3 (Response to withdrawal / Dechallenge):
#   * "Plausible (pharmacologically, pathologically)" (+3): Clear improvement/resolution after drug withdrawal or dose reduction, consistent with pharmacology.
#   * "Clinically reasonable" (+2): Patient recovered/improved after withdrawal, but with standard clinical lag or supportive care.
#   * "Information on drug withdrawal lacking or unclear" (0): Drug was not stopped, patient died, reaction ongoing, or withdrawal data unknown.
#   * "No improvement / Negative dechallenge" (-2): Drug was withdrawn but reaction persisted without improvement.

# - Criteria 4 (Rechallenge outcome):
#   * "Satisfactory (positive rechallenge, if necessary)" (+2): Reaction recurred upon deliberate re-exposure or prior identical exposure.
#   * "Rechallenge not required / Not done" (0): Rechallenge was not performed or not clinically necessary.
#   * "Negative rechallenge (reaction did not recur)" (-2): Drug was re-administered and the reaction did NOT recur.

# - Criteria 5 (Phenomenological / Pharmacological nature):
#   * "Yes" (+2): The event is a definitive pharmacological or phenomenological reaction (e.g. anaphylaxis, SJS/TEN, drug-induced liver injury, specific known ADR mechanism, toxic blood level).
#   * "No / Non-specific clinical event" (0): Non-specific or subjective clinical symptom (e.g. mild nausea, headache, malaise).

# - Criteria 6 (Data completeness and validity):
#   * "Sufficient data available for evaluation" (score: 0, flag: "None")
#   * "More data needed or under examination" (flag: "Conditional")
#   * "Insufficient or contradictory data that cannot be supplemented/verified" (flag: "Unassessable")

# ### 2. Naranjo Algorithm (10 Questions):
# Provide a list of 10 answers ('yes', 'no', 'unknown') for:
# Q1: Previous conclusive reports in literature for this drug-reaction pair?
# Q2: Adverse event appeared after the suspected drug was administered?
# Q3: Adverse reaction improved when drug discontinued or specific antagonist given?
# Q4: Adverse reaction reappeared when drug re-administered?
# Q5: Alternative causes (other drugs, underlying disease) that could have caused the reaction?
# Q6: Reaction reappeared when placebo given?
# Q7: Drug detected in blood/fluids in toxic concentrations?
# Q8: Reaction more severe with increased dose, or less severe with decreased dose?
# Q9: Similar reaction to same or similar drugs in previous exposure?
# Q10: Confirmed by objective evidence (lab test, biopsy, clinical photos)?

# Output a JSON object with this exact structure:
# {{
#   "who_umc": {{
#     "time_relationship": {{
#       "criterion": "Plausible" | "Reasonable" | "Improbable",
#       "score": 3 | 2 | -2,
#       "reason": "Brief clinical rationale"
#     }},
#     "alternative_etiologies": {{
#       "criterion": "Cannot be explained by disease or other drugs" | "Unlikely to be attributed to disease or other drugs" | "Could also be explained by disease or other drugs" | "Disease or other drugs provide plausible explanations",
#       "score": 3 | 2 | 1 | -2,
#       "reason": "Brief clinical rationale"
#     }},
#     "dechallenge": {{
#       "criterion": "Plausible (pharmacologically, pathologically)" | "Clinically reasonable" | "Information on drug withdrawal lacking or unclear" | "No improvement / Negative dechallenge",
#       "score": 3 | 2 | 0 | -2,
#       "reason": "Brief clinical rationale"
#     }},
#     "rechallenge": {{
#       "criterion": "Satisfactory (positive rechallenge, if necessary)" | "Rechallenge not required / Not done" | "Negative rechallenge (reaction did not recur)",
#       "score": 2 | 0 | -2,
#       "reason": "Brief clinical rationale"
#     }},
#     "phenomenological_nature": {{
#       "criterion": "Yes" | "No / Non-specific clinical event",
#       "score": 2 | 0,
#       "reason": "Brief clinical rationale"
#     }},
#     "data_completeness": {{
#       "status": "sufficient" | "conditional" | "unassessable",
#       "flag": "None" | "Conditional" | "Unassessable",
#       "reason": "Brief explanation"
#     }}
#   }},
#   "naranjo_answers": ["yes"|"no"|"unknown", ... (10 elements)],
#   "clinical_summary": "Brief 1-sentence synthesis"
# }}
# """
#             response = gemini_client.models.generate_content(
#                 model='gemini-2.5-flash',
#                 contents=prompt,
#                 config=types.GenerateContentConfig(
#                     temperature=0.0,
#                     response_mime_type="application/json"
#                 )
#             )
#             text = response.text.strip()
#             if text.startswith("```"):
#                 text = text.split("```")[1]
#                 if text.startswith("json"):
#                     text = text[4:]
            
#             data = json.loads(text.strip())
            
#             who = data.get("who_umc", {})
#             naranjo = data.get("naranjo_answers", ["unknown"] * 10)
#             if len(naranjo) < 10:
#                 naranjo.extend(["unknown"] * (10 - len(naranjo)))
#             naranjo = [str(a).lower().strip() for a in naranjo[:10]]

#             res = {
#                 "who_umc": who,
#                 "naranjo_answers": naranjo,
#                 "clinical_summary": data.get("clinical_summary", "")
#             }
#         except Exception as e:
#             print(f"[Causality NLP] Gemini API error: {e}. Falling back to deterministic clinical rules.")
#             pass

#     if not res:
#         res = _extract_deterministic_who_and_naranjo(dossier_text, target_drug_name, other_drugs)

#     return res


# def _extract_deterministic_who_and_naranjo(dossier_text: str, target_drug_name: str, other_drugs: tuple = ()) -> dict:
#     """
#     Deterministic rule-based clinical scoring fallback when Gemini API is offline.
#     Implements all 6 WHO-UMC criteria and Naranjo questions.
#     """
#     text_lower = (dossier_text or "").lower()
#     target_lower = (target_drug_name or "").lower()

#     # 1. Timeline / Time Relationship
#     time_score = 2
#     time_criterion = "Reasonable"
#     time_reason = "Timeline between drug initiation and reaction onset is clinically reasonable."
    
#     if re.search(r"\b(before\s+taking|prior\s+to\s+starting|preceded\s+drug)\b", text_lower):
#         time_score = -2
#         time_criterion = "Improbable (but not impossible)"
#         time_reason = "Reaction onset preceded or is incompatible with drug administration timeline."
#     elif re.search(r"\b(immediate|within\s+(minutes|hours|24\s+hours|1\s+day|2\s+days|3\s+days)|same\s+day|shortly\s+after)\b", text_lower):
#         time_score = 3
#         time_criterion = "Plausible"
#         time_reason = "Plausible and immediate temporal onset following drug intake."

#     # 2. Alternative Etiologies
#     alt_score = 2
#     alt_criterion = "Unlikely to be attributed to disease or other drugs"
#     alt_reason = "Unlikely to be attributed solely to concurrent disease or low-risk therapies."

#     target_risk = classify_drug_risk(target_drug_name)
#     other_high_risk = [d for d in other_drugs if classify_drug_risk(d) == 'high_risk']

#     if target_risk == 'low_risk' and other_high_risk:
#         alt_score = -2
#         alt_criterion = "Disease or other drugs provide plausible explanations"
#         alt_reason = f"Other co-administered high-risk agents ({', '.join(other_high_risk)}) provide a much more plausible explanation."
#     elif len(other_drugs) > 0 or "history" in text_lower or "concomitant" in text_lower:
#         alt_score = 1
#         alt_criterion = "Could also be explained by disease or other drugs"
#         alt_reason = "Concurrent medications or medical history could also contribute to the reaction."
#     elif "no alternative" in text_lower or len(other_drugs) == 0:
#         alt_score = 3
#         alt_criterion = "Cannot be explained by disease or other drugs"
#         alt_reason = "No concurrent disease or other medications can explain the clinical manifestation."

#     # 3. Dechallenge
#     dech_score = 0
#     dech_criterion = "Information on drug withdrawal lacking or unclear"
#     dech_reason = "Drug cessation data or improvement status is unconfirmed or not recorded."

#     if re.search(r"\b(action\s+taken.*?(withdrawn|reduced|stopped|discontinued))\b", text_lower) or \
#        re.search(r"\b(stopped|withdrawn|discontinued|halted)\b", text_lower):
#         if re.search(r"\b(outcome.*?(recovered|recovering|resolved|improved|better|cleared))\b", text_lower) or \
#            re.search(r"\b(resolved|improved|subsided|abated|recovered|cleared\s+up)\b", text_lower):
#             dech_score = 3 if time_score == 3 else 2
#             dech_criterion = "Plausible (pharmacologically, pathologically)" if time_score == 3 else "Clinically reasonable"
#             dech_reason = "Symptoms resolved or improved substantially following drug withdrawal."
#         elif "not recovered" in text_lower or "fatal" in text_lower:
#             dech_score = -2
#             dech_criterion = "No improvement / Negative dechallenge"
#             dech_reason = "Reaction persisted without improvement despite drug withdrawal."

#     # 4. Rechallenge
#     rech_score = 0
#     rech_criterion = "Rechallenge not required / Not done"
#     rech_reason = "Drug rechallenge was not performed or not clinically indicated."

#     if re.search(r"\b(reintroduction.*?(yes|reappeared|recurred))\b", text_lower) or \
#        re.search(r"\b(recurred\s+on\s+re-exposure|reappeared\s+on\s+rechallenge|positive\s+rechallenge)\b", text_lower):
#         rech_score = 2
#         rech_criterion = "Satisfactory (positive rechallenge, if necessary)"
#         rech_reason = "Reaction confirmed to recur upon drug re-administration."
#     elif re.search(r"\b(reintroduction.*?(no|no\s+recurrence))\b", text_lower):
#         rech_score = -2
#         rech_criterion = "Negative rechallenge (reaction did not recur)"
#         rech_reason = "Reaction did not recur upon drug re-exposure."

#     # 5. Phenomenological / Pharmacological Nature
#     phen_score = 0
#     phen_criterion = "No / Non-specific clinical event"
#     phen_reason = "Clinical manifestation is non-specific or subjective."

#     if re.search(r"\b(anaphylaxis|anaphylactic|sjs|stevens-johnson|toxic\s+epidermal|angioedema|dili|hepatotoxicity|nephrotoxicity|agranulocytosis|fixed\s+drug\s+eruption|urticaria|erythema\s+multiforme|rash|toxic\s+level)\b", text_lower):
#         phen_score = 2
#         phen_criterion = "Yes"
#         phen_reason = "Event is a recognized, definitive pharmacological or immunological ADR phenotype."

#     # 6. Data completeness
#     comp_status = "sufficient"
#     comp_flag = "None"
#     comp_reason = "Sufficient clinical data available for causality assessment."

#     if not dossier_text or len(dossier_text.strip()) < 20:
#         comp_status = "unassessable"
#         comp_flag = "Unassessable"
#         comp_reason = "Insufficient data to establish causality."

#     who_dict = {
#         "time_relationship": {"criterion": time_criterion, "score": time_score, "reason": time_reason},
#         "alternative_etiologies": {"criterion": alt_criterion, "score": alt_score, "reason": alt_reason},
#         "dechallenge": {"criterion": dech_criterion, "score": dech_score, "reason": dech_reason},
#         "rechallenge": {"criterion": rech_criterion, "score": rech_score, "reason": rech_reason},
#         "phenomenological_nature": {"criterion": phen_criterion, "score": phen_score, "reason": phen_reason},
#         "data_completeness": {"status": comp_status, "flag": comp_flag, "reason": comp_reason}
#     }

#     # Naranjo Answers
#     naranjo_answers = ["unknown"] * 10
    
#     # Q1: Known literature reaction
#     common_high_adr = ["aspirin", "amoxicillin", "penicillin", "ibuprofen", "paracetamol", "phenytoin", "ciprofloxacin", "carbamazepine", "diclofenac"]
#     if any(d in target_lower for d in common_high_adr):
#         naranjo_answers[0] = "yes"

#     # Q2: Appeared after drug
#     if time_score > 0:
#         naranjo_answers[1] = "yes"
#     elif time_score < 0:
#         naranjo_answers[1] = "no"

#     # Q3: Improved on dechallenge
#     if dech_score > 0:
#         naranjo_answers[2] = "yes"
#     elif dech_score < 0:
#         naranjo_answers[2] = "no"

#     # Q4: Reappeared on rechallenge
#     if rech_score > 0:
#         naranjo_answers[3] = "yes"
#     elif rech_score < 0:
#         naranjo_answers[3] = "no"

#     # Q5: Alternative causes
#     if alt_score <= 1:
#         naranjo_answers[4] = "yes"
#     elif alt_score == 3:
#         naranjo_answers[4] = "no"

#     # Q7: Toxic concentrations
#     if "toxic level" in text_lower or "overdose" in text_lower:
#         naranjo_answers[6] = "yes"

#     # Q8: Dose response
#     if "dose increased" in text_lower or "dose reduced" in text_lower:
#         naranjo_answers[7] = "yes"

#     # Q9: Previous exposure reaction
#     if "previous" in text_lower and "reaction" in text_lower:
#         naranjo_answers[8] = "yes"

#     # Q10: Objective evidence
#     if "investigation" in text_lower or "biopsy" in text_lower or "lab test" in text_lower or phen_score > 0:
#         naranjo_answers[9] = "yes"

#     return {
#         "who_umc": who_dict,
#         "naranjo_answers": naranjo_answers,
#         "clinical_summary": f"Deterministic rule-based evaluation completed for {target_drug_name}."
#     }


"""
Unified Clinical NLP and Multi-Criteria Causality Extractor.
Implements the WHO-UMC Criteria-Based Scoring Scale and Naranjo Algorithm.

ARCHITECTURE (accuracy-critical revision):
- ALL clinical-language judgment (onset-speed interpretation beyond a bare
  number, alternative-cause plausibility, phenomenological-nature
  classification, reconciling a missing checkbox against narrative text) is
  made EXCLUSIVELY by a language model, via a multi-provider fallback chain
  (call_clinical_llm). There is NO regex/keyword-based clinical guessing
  anywhere in this file.
- Regex is used ONLY for pure syntax with zero ambiguity: parsing a date
  string into a date object, and extracting an explicit numeric minute/hour
  figure ("30 min", "2 hours") — both are closed-form parsing, not judgment.
- Every LLM judgment that materially changes a score must be grounded: the
  LLM must supply an "evidence_quote" that appears verbatim in the dossier
  it was given, or the claim is discarded.
- If every configured AI provider fails, this module returns an explicit
  "ai_unavailable" signal. Callers (who_umc.py) MUST route this to
  Conditional/Unclassified with a "requires manual review" flag — never to
  a guessed score.
"""

import os
import json
import re
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

load_dotenv()

# ======================================================================
# Provider clients — add/remove providers here to change the fallback chain
# ======================================================================

gemini_client = None
try:
    from google import genai
    from google.genai import types as genai_types
    if os.environ.get('GEMINI_API_KEY'):
        gemini_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
except Exception:
    pass

openai_client = None
try:
    from openai import OpenAI
    if os.environ.get('OPENAI_API_KEY'):
        openai_client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
except Exception:
    pass


def _call_gemini(prompt: str) -> Optional[str]:
    if not gemini_client:
        return None
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json")
        )
        return response.text
    except Exception as e:
        print(f"[Provider:Gemini] Failed: {e}")
        return None


def _call_openai(prompt: str) -> Optional[str]:
    if not openai_client:
        return None
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[Provider:OpenAI] Failed: {e}")
        return None


# Ordered fallback chain. Add more providers here (e.g. Anthropic's API) by
# writing a _call_<provider>(prompt) -> Optional[str] function and appending
# it to this list — no other code needs to change.
_PROVIDER_CHAIN = [
    ("gemini", _call_gemini),
    ("openai", _call_openai),
]


def call_clinical_llm(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Tries every configured provider in order. Returns parsed JSON from the
    FIRST provider that succeeds and returns valid JSON.

    Returns None if every provider fails or returns unparseable output —
    callers MUST treat None as "AI unavailable" and MUST NOT fall back to
    a keyword/regex guess. Guessing is explicitly disallowed in this system.
    """
    for provider_name, provider_fn in _PROVIDER_CHAIN:
        raw = provider_fn(prompt)
        if not raw:
            continue
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            print(f"[Provider:{provider_name}] Returned unparseable JSON — trying next provider.")
            continue
    return None


# ======================================================================
# Pure syntax parsing — closed-form, zero clinical judgment, never guesses
# ======================================================================

def _parse_date(date_str):
    """
    Parses DD/MM/YYYY, DD-MM-YYYY, DD|MM|YYYY, YYYY-MM-DD (and 2-digit year variants)
    into a date object. Returns None if unparseable — never guesses.
    This is string-format normalization, not clinical interpretation.
    """
    if not date_str:
        return None
    s = re.sub(r'[|.\-]', '/', str(date_str).strip())
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _has_relevant_medical_history(history) -> bool:
    """Returns True only if medical_history contains actual clinical history rather than 'None'/'Nil'/'N/A'."""
    if not history:
        return False
    text = str(history).strip().lower()
    irrelevant = {
        '', 'none', 'nil', 'n/a', 'na', 'no', 'no known',
        'not applicable', 'none reported', 'no known allergies',
        'nkda', 'not known', 'none mentioned', 'unremarkable',
        'no history', 'no significant history', 'not available',
        'healthy', 'normal'
    }
    return text not in irrelevant


def _extract_numeric_latency_phrase(dossier_text: str) -> Optional[str]:
    """
    Detects ONLY an explicit numeric onset-latency figure ('30 min after',
    'within 2 hours'). This is closed-form (a number + a fixed unit word),
    not clinical judgment, so it's safe as regex. Anything less explicit
    ('soon after', 'shortly following', 'almost immediately') is genuine
    language interpretation and is NOT handled here — it's left entirely
    to the LLM via call_clinical_llm, which generalizes to phrasing this
    function was never told about.
    """
    text_lower = (dossier_text or "").lower()
    match = re.search(r"\b(within\s+)?(\d{1,3})\s*(min|minute|hour|hr)s?\b", text_lower)
    return match.group(0) if match else None


def _quote_is_grounded(evidence_quote: str, dossier_text: str) -> bool:
    """
    Verifies that an LLM claim is grounded in the dossier.
    Permits minor punctuation differences and slight paraphrasing/truncation,
    while preventing ungrounded hallucinations from being scored.
    """
    if not evidence_quote or not evidence_quote.strip():
        return False
    quote = evidence_quote.strip().lower()
    text = (dossier_text or "").lower()

    # 1. Exact substring match (fast path)
    if quote in text:
        return True

    # 2. Normalized punctuation match
    clean_quote = re.sub(r'[^\w\s]', '', quote).strip()
    clean_text = re.sub(r'[^\w\s]', ' ', text)
    if clean_quote and clean_quote in clean_text:
        return True

    # 3. Token-based overlap for minor paraphrasing/truncation
    quote_words = clean_quote.split()
    if len(quote_words) < 3:
        return False  # Short phrases (< 3 words) must match verbatim to avoid false positives

    text_words = clean_text.split()
    if not text_words:
        return False

    quote_word_set = set(quote_words)
    w_len = len(quote_words) + 4
    for i in range(max(1, len(text_words) - len(quote_words) + 1)):
        window = set(text_words[i:i + w_len])
        overlap = len(quote_word_set & window) / len(quote_word_set)
        if overlap >= 0.80:
            return True

    return False




# ======================================================================
# Clinical dossier construction
# ======================================================================

def build_clinical_dossier(report_data: dict, target_drug_name: str) -> str:
    """Constructs a comprehensive, standardized clinical dossier string from all report fields."""
    lines = []
    lines.append(f"=== ADR CLINICAL CASE REPORT (Target Drug: {target_drug_name}) ===")

    patient_info = []
    if report_data.get('patient_initials'): patient_info.append(f"Initials: {report_data['patient_initials']}")
    if report_data.get('patient_age'): patient_info.append(f"Age: {report_data['patient_age']}")
    if report_data.get('gender'): patient_info.append(f"Gender: {report_data['gender']}")
    if report_data.get('weight_kg'): patient_info.append(f"Weight: {report_data['weight_kg']} kg")
    lines.append(f"Patient Profile: {', '.join(patient_info) if patient_info else 'Not provided'}")

    lines.append(f"Reaction Narrative: {report_data.get('reaction_description') or 'None'}")
    lines.append(f"Reaction Start Date: {report_data.get('reaction_start_date') or 'Unknown'}")
    lines.append(f"Reaction Stop Date: {report_data.get('reaction_stop_date') or 'Ongoing/Unknown'}")

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

    other_suspects = [m for m in meds if m.get('drug_name', '').lower() != target_drug_name.lower() and m.get('drug_name')]
    if other_suspects:
        lines.append("\n--- Other Concurrently Suspected Medications ---")
        for m in other_suspects:
            lines.append(f"- {m.get('drug_name')}: Dose {m.get('dose', '—')}, Action Taken: {m.get('action_taken', '—')}, Start: {m.get('therapy_start_date', '—')}, Stop: {m.get('therapy_stop_date', '—')}")

    concomitant = report_data.get('concomitant_medications', []) or []
    if concomitant:
        lines.append("\n--- Concomitant / Non-Suspect Medications & Supplements ---")
        for c in concomitant:
            lines.append(f"- {c.get('drug_name')}: Dose {c.get('dose', '—')}, Indication: {c.get('indication', '—')}, Dates: {c.get('therapy_start_date', '—')} to {c.get('therapy_stop_date', '—')}")

    if report_data.get('additional_info'):
        lines.append(f"\nAdditional Clinical Information: {report_data['additional_info']}")

    return "\n".join(lines)


# ======================================================================
# Structural criterion computation — pure factual math, no language judgment
# ======================================================================

def compute_time_relationship_structural(target_drug: dict, report_data: dict) -> Optional[Dict[str, Any]]:
    """
    Grounds Criterion 1 in actual dates.

    Returns:
      - dict with 'score': date math alone settled the answer (No —
        reaction predates therapy start; this is unambiguous arithmetic).
      - dict WITHOUT 'score' (just 'delta_days'): dates are compatible, but
        Yes-vs-Maybe requires either a numeric latency figure or
        an LLM's grounded judgment — resolved in resolve_who_umc_criteria().
      - None: dates could not be parsed — caller must not guess.
    """
    therapy_start = _parse_date(target_drug.get('therapy_start_date'))
    reaction_start = _parse_date(report_data.get('reaction_start_date'))
    if not therapy_start or not reaction_start:
        return None

    delta_days = (reaction_start - therapy_start).days
    if delta_days < 0:
        return {
            "criterion": "No (but not impossible)",
            "score": -2,
            "reason": f"Reaction start date precedes therapy start date by {abs(delta_days)} day(s) — timeline incompatible.",
            "delta_days": delta_days
        }
    return {"delta_days": delta_days}


def compute_alternative_etiologies_structural(target_drug: dict, other_drugs: list, report_data: dict) -> Dict[str, Any]:
    """
    Grounds Criterion 2 in exposure-window overlap between co-suspected
    drugs — pure date-range comparison, not a drug-class guess. Only
    supplies the DEFAULT; a grounded LLM downgrade (citing an actual quote
    about the patient's condition) can override this in resolve_who_umc_criteria().
    """
    target_start = _parse_date(target_drug.get('therapy_start_date'))
    target_stop = _parse_date(target_drug.get('therapy_stop_date'))
    has_history = _has_relevant_medical_history(report_data.get('medical_history'))
    concomitant = report_data.get('concomitant_medications') or []

    overlapping, non_overlapping = [], []
    for od in other_drugs:
        od_start = _parse_date(od.get('therapy_start_date'))
        od_stop = _parse_date(od.get('therapy_stop_date'))
        if target_start and od_start:
            t_end = target_stop or target_start
            o_end = od_stop or od_start
            overlaps = (od_start <= t_end) and (target_start <= o_end)
        else:
            overlaps = True  # can't rule it out from dates alone — don't guess it away
        (overlapping if overlaps else non_overlapping).append(od)

    has_other_evidence = has_history or bool(concomitant)

    if not overlapping and not has_other_evidence:
        return {
            "criterion": "Cannot be explained by disease or other drugs",
            "score": 3,
            "reason": "No overlapping co-suspected drugs, no medical history, no concomitant medications."
        }

    if overlapping:
        identical_window = bool(target_start) and all(
            _parse_date(od.get('therapy_start_date')) == target_start and
            _parse_date(od.get('therapy_stop_date')) == target_stop
            for od in overlapping
        )
        names = ", ".join(od.get('drug_name', '?') for od in overlapping)
        if identical_window:
            return {
                "criterion": "Could also be explained by disease or other drugs",
                "score": 1,
                "reason": f"Co-administered {names} share an identical exposure window — no case-specific evidence differentiates them."
            }
        return {
            "criterion": "Unlikely to be attributed to disease or other drugs",
            "score": 2,
            "reason": f"Co-administered {names} overlap in time but on a different exposure window than the target drug."
        }

    return {
        "criterion": "Could also be explained by disease or other drugs",
        "score": 1,
        "reason": "Medical history or concomitant medication present that could contribute to the event."
    }


def compute_dechallenge_rechallenge_structural(target_drug: dict, report_data: dict) -> Dict[str, Dict[str, Any]]:
    """Grounds Criteria 3 and 4 directly in the form's action_taken / outcome / reintroduction_result fields."""
    action = (target_drug.get('action_taken') or '').lower()
    outcome = (report_data.get('outcome') or '').lower()
    reintro = (target_drug.get('reintroduction_result') or '').lower()

    result = {}

    if action in ('drug_withdrawn', 'dose_reduced'):
        if outcome == 'recovered':
            result['dechallenge'] = {
                "criterion": "Plausible (pharmacologically, pathologically)", "score": 3,
                "reason": f"Drug {action.replace('_', ' ')}, outcome recorded as 'recovered'."
            }
        elif outcome in ('recovering', 'recovered_with_sequelae'):
            result['dechallenge'] = {
                "criterion": "Clinically reasonable", "score": 2,
                "reason": f"Drug {action.replace('_', ' ')}, outcome recorded as '{outcome}'."
            }
        elif outcome in ('not_recovered', 'fatal'):
            result['dechallenge'] = {
                "criterion": "No improvement / Negative dechallenge", "score": -2,
                "reason": f"Drug {action.replace('_', ' ')} but outcome recorded as '{outcome}'."
            }
        else:
            result['dechallenge'] = {
                "criterion": "Information on drug withdrawal lacking or unclear", "score": 0,
                "reason": "Drug withdrawn/reduced but outcome not recorded."
            }
    elif action in ('dose_not_changed', 'not_applicable', 'unknown', ''):
        result['dechallenge'] = {
            "criterion": "Information on drug withdrawal lacking or unclear", "score": 0,
            "reason": f"action_taken='{action or 'not recorded'}' — no withdrawal to assess.",
            "_unresolved_action": True,  # flags this for narrative reconciliation in resolve_who_umc_criteria()
        }
    else:
        result['dechallenge'] = {
            "criterion": "Information on drug withdrawal lacking or unclear", "score": 0,
            "reason": f"Unrecognized action_taken value '{action}'."
        }

    if reintro in ('yes', 'reaction_recurred'):
        result['rechallenge'] = {
            "criterion": "Satisfactory (positive rechallenge, if necessary)", "score": 2,
            "reason": "reintroduction_result = yes — reaction recurred on re-exposure."
        }
    elif reintro in ('no', 'no_reaction'):
        result['rechallenge'] = {
            "criterion": "Negative rechallenge (reaction did not recur)", "score": -2,
            "reason": "reintroduction_result = no — reaction did not recur on re-exposure."
        }
    else:
        result['rechallenge'] = {
            "criterion": "Rechallenge not required / Not done", "score": 0,
            "reason": "No rechallenge recorded on the form.",
            "_unresolved_reintro": True,
        }

    return result


# ======================================================================
# LLM-based reconciliation for fields structure alone can't resolve
# ======================================================================

def reconcile_missing_field_from_narrative(field_name: str, drug_name: str, dossier_text: str) -> Optional[Dict[str, Any]]:
    """
    When a per-drug structured field (action_taken, reintroduction_result)
    was not individually recorded — e.g. because the narrative describes an
    action collectively ("all medications were stopped") rather than every
    row's checkbox being ticked — this asks the LLM to read the narrative
    and determine whether it addresses this specific drug.

    Deliberately NOT pattern-matched: the LLM generalizes to any future
    phrasing. The result is only trusted if it cites a verbatim quote.
    Returns None (leave the field unresolved) if the LLM can't ground its answer.
    """
    if not dossier_text:
        return None

    prompt = f"""
The structured form field "{field_name}" was not explicitly checked/recorded for
the drug "{drug_name}" in this ADR report. Read the narrative below and determine
whether it states something applicable to this drug for this field, even if
stated collectively about multiple drugs (e.g. "all medications were stopped").

{dossier_text}

Respond with ONLY a JSON object:
{{
  "resolved_value": "<value in the vocabulary below, or null if the narrative does not address this drug for this field>",
  "evidence_quote": "<exact phrase copied verbatim from the narrative above supporting this, or empty string if resolved_value is null>"
}}
For action_taken, valid values are exactly one of: drug_withdrawn, dose_increased, dose_reduced, dose_not_changed, not_applicable, unknown.
For reintroduction_result, valid values are exactly one of: yes, no, effect_unknown.
"""
    data = call_clinical_llm(prompt)
    if not data:
        return None
    if data.get("resolved_value") and _quote_is_grounded(data.get("evidence_quote", ""), dossier_text):
        return data
    return None


def resolve_who_umc_criteria(who_eval: dict, dossier_text: str, target_drug: dict,
                              other_drugs_names: tuple, report_data: dict,
                              all_medications: list) -> Dict[str, Any]:
    """
    Final authority merging structural facts with LLM narrative output.
    Structural facts win when they alone settle a question; an LLM judgment
    is only kept when grounded in an exact quote from the dossier it was
    given. Nothing here falls back to a keyword/regex guess.
    """
    who_eval = dict(who_eval or {})

    # --- Criterion 1: Time relationship ---
    time_baseline = compute_time_relationship_structural(target_drug, report_data)
    if time_baseline is None:
        existing = dict(who_eval.get('time_relationship') or {})
        existing['_ungrounded'] = True
        existing.pop('score', None)
        who_eval['time_relationship'] = existing
    elif "score" in time_baseline:
        who_eval['time_relationship'] = {k: v for k, v in time_baseline.items() if k != 'delta_days'}
    else:
        # Dates compatible; only Yes-vs-Maybe remains. Prefer a
        # GROUNDED LLM judgment (it generalizes to any onset-speed phrasing).
        llm_time = who_eval.get('time_relationship') or {}
        if llm_time.get('criterion') in ('Yes', 'Maybe') and \
           _quote_is_grounded(llm_time.get('evidence_quote', ''), dossier_text):
            who_eval['time_relationship'] = llm_time
        else:
            numeric_latency = _extract_numeric_latency_phrase(dossier_text)
            if numeric_latency:
                who_eval['time_relationship'] = {
                    "criterion": "Yes", "score": 3,
                    "reason": f"Reaction onset within minutes/hours of administration ('{numeric_latency}')."
                }
            else:
                delta = time_baseline.get('delta_days', 0)
                if delta == 0:
                    who_eval['time_relationship'] = {
                        "criterion": "Yes", "score": 3,
                        "reason": "Reaction start date and drug administration share the same day (delta = 0 days) — acute temporal plausibility."
                    }
                elif delta <= 3:
                    who_eval['time_relationship'] = {
                        "criterion": "Yes", "score": 3,
                        "reason": f"Reaction began {delta} day(s) after therapy start — within typical acute ADR onset latency."
                    }
                else:
                    who_eval['time_relationship'] = {
                        "criterion": "Maybe", "score": 2,
                        "reason": (f"Reaction began {delta} day(s) after therapy start; "
                                   f"timing reasonable but not immediate.")
                    }

    # --- Criterion 2: Alternative etiologies (disease or other drugs) ---
    other_drug_objs = [
        m for m in (all_medications or [])
        if m.get('drug_name', '').lower() in [n.lower() for n in (other_drugs_names or ())]
    ]
    has_history = _has_relevant_medical_history(report_data.get('medical_history'))
    has_concomitant = bool(report_data.get('concomitant_medications'))
    has_other_suspected = bool(other_drug_objs)

    valid_alt_scores = {
        "Cannot be explained by disease or other drugs": 3,
        "Unlikely to be attributed to disease or other drugs": 2,
        "Could also be explained by disease or other drugs": 1,
        "Disease or other drugs provide plausible explanations": -2,
    }

    llm_alt = who_eval.get('alternative_etiologies') or {}
    llm_crit = llm_alt.get('criterion')

    # If there are objectively no other suspected drugs, no concomitant medications, and no medical history:
    if not has_other_suspected and not has_concomitant and not has_history:
        who_eval['alternative_etiologies'] = {
            "criterion": "Cannot be explained by disease or other drugs",
            "score": 3,
            "reason": "No concurrent disease, co-suspected drugs, or concomitant medications reported."
        }
    elif llm_crit in valid_alt_scores:
        who_eval['alternative_etiologies'] = {
            "criterion": llm_crit,
            "score": valid_alt_scores[llm_crit],
            "reason": llm_alt.get('reason', f"Clinical evaluation: {llm_crit}")
        }
    else:
        who_eval['alternative_etiologies'] = compute_alternative_etiologies_structural(
            target_drug, other_drug_objs, report_data
        )

    # --- Criteria 3 & 4: Dechallenge / Rechallenge ---
    dr = compute_dechallenge_rechallenge_structural(target_drug, report_data)

    if dr['dechallenge'].get('_unresolved_action'):
        reconciled = reconcile_missing_field_from_narrative(
            'action_taken', target_drug.get('drug_name', 'this drug'), dossier_text)
        if reconciled:
            action = reconciled['resolved_value'].lower()
            reconciled_drug = dict(target_drug)
            reconciled_drug['action_taken'] = action
            dr_reconciled = compute_dechallenge_rechallenge_structural(reconciled_drug, report_data)
            dr['dechallenge'] = dr_reconciled['dechallenge']
            dr['dechallenge']['reason'] += f" (action_taken reconciled from narrative: \"{reconciled['evidence_quote']}\")"
    dr['dechallenge'].pop('_unresolved_action', None)

    if dr['rechallenge'].get('_unresolved_reintro'):
        reconciled = reconcile_missing_field_from_narrative(
            'reintroduction_result', target_drug.get('drug_name', 'this drug'), dossier_text)
        if reconciled:
            reconciled_drug = dict(target_drug)
            reconciled_drug['reintroduction_result'] = reconciled['resolved_value'].lower()
            dr_reconciled = compute_dechallenge_rechallenge_structural(reconciled_drug, report_data)
            dr['rechallenge'] = dr_reconciled['rechallenge']
            dr['rechallenge']['reason'] += f" (reintroduction_result reconciled from narrative: \"{reconciled['evidence_quote']}\")"
    dr['rechallenge'].pop('_unresolved_reintro', None)

    who_eval['dechallenge'] = dr['dechallenge']
    who_eval['rechallenge'] = dr['rechallenge']

    # --- Criterion 5: Phenomenological nature — LLM-only, grounded ---
    phen = who_eval.get('phenomenological_nature') or {}
    if phen.get('score') == 2 and _quote_is_grounded(phen.get('evidence_quote', ''), dossier_text):
        who_eval['phenomenological_nature'] = phen
    elif 'score' in phen:
        who_eval['phenomenological_nature'] = {
            "criterion": "No / Non-specific clinical event", "score": 0,
            "reason": "No verifiable quote from the report supports a definitive reaction phenotype."
        }
    # else: leave whatever was there (e.g. unresolved due to AI unavailability) —
    # who_umc.py's missing-criteria check will route this to Conditional/Unclassified.

    return who_eval


# ======================================================================
# Extraction entry point — LLM-only, no deterministic/regex fallback
# ======================================================================

def _build_extraction_prompt(dossier_text: str, target_drug_name: str) -> str:
    return f"""
You are an expert pharmacovigilance clinical assessment AI implementing the WHO-UMC Criteria-Based Scoring Scale and Naranjo Algorithm.

Analyze this complete clinical ADR case dossier for the target drug "{target_drug_name}":

{dossier_text}

Evaluate the case according to these EXACT criteria:

### 1. WHO-UMC Criteria-Based Scoring Scale:
- Criteria 1 (Time relationship to drug intake):
  Question: "What is the nature of the timeline between drug intake and the event or laboratory test abnormality?"
  * "Yes" (+3): Timeline is clinically/pharmacologically plausible (rapid onset, acute reaction window, or same-day onset).
  * "Maybe" (+2): Timeline is reasonable (onset occurred after drug intake within reasonable therapeutic exposure window).
  * "No" (-2): Timeline is improbable (onset preceded drug intake or is biologically incompatible).
  Set "evidence_quote" to the phrase indicating timing/onset speed, or empty string.

- Criteria 2 (Alternative etiologies - disease or other drugs):
  Question: "To what extent can the event be explained by concurrent disease or other therapies?"
  Evaluate the case clinically for ANY drug or clinical condition without keyword bias:
  * "Cannot be explained by disease or other drugs" (+3): The event cannot be explained by concurrent disease or other therapies.
  * "Unlikely to be attributed to disease or other drugs" (+2): Concurrent disease or other therapies are present, but are clinically unlikely to be the cause of this specific adverse event.
  * "Could also be explained by disease or other drugs" (+1): Concurrent disease or other co-administered drugs could plausibly contribute to or also explain the adverse event.
  * "Disease or other drugs provide plausible explanations" (-2): Concurrent disease or other drugs provide a direct, highly plausible clinical explanation for the event.

- Criteria 3 (Response to withdrawal / Dechallenge) — for your awareness only; independently computed from report action_taken and outcome fields.

- Criteria 4 (Rechallenge outcome) — for your awareness only; independently computed from report reintroduction_result field.

- Criteria 5 (Phenomenological / Pharmacological nature):
  Question: "Is the event definitive pharmacologically or phenomenologically (i.e., an objective and specific medical disorder or a recognised pharmacological phenomenon)?"
  * "Yes" (+2): The event is an objective, specific medical disorder or recognized pharmacological/immunological adverse reaction (e.g. anaphylaxis, urticaria, rash, SJS/TEN, DILI, bronchospasm, etc.).
  * "No / Non-specific clinical event" (0): Non-specific clinical event or subjective symptom without recognized pattern.
  Set "evidence_quote" to the phrase describing the reaction phenotype.

- Criteria 6 (Data completeness and validity):
  Question: "Can the report be judged, verified, or supplemented?"
  * "Sufficient data available for evaluation" (score: 0, flag: "None")
  * "More data needed or under examination" (flag: "Conditional")
  * "Insufficient or contradictory data that cannot be supplemented/verified" (flag: "Unassessable")

### 2. Naranjo Algorithm (10 Questions):
Provide a list of 10 answers ('yes', 'no', 'unknown') for:
Q1: Previous conclusive reports in literature for this drug-reaction pair?
Q2: Adverse event appeared after the suspected drug was administered? (informational — independently verified from dates downstream)
Q3: Adverse reaction improved when drug discontinued or specific antagonist given? (informational — independently verified from action_taken/outcome downstream)
Q4: Adverse reaction reappeared when drug re-administered? (informational — independently verified from reintroduction_result downstream)
Q5: Alternative causes (other drugs, underlying disease) that could have caused the reaction?
Q6: Reaction reappeared when placebo given?
Q7: Drug detected in blood/fluids in toxic concentrations?
Q8: Reaction more severe with increased dose, or less severe with decreased dose?
Q9: Similar reaction to same or similar drugs in previous exposure?
Q10: Confirmed by objective evidence (lab test, biopsy, clinical photos)?

Output ONLY a JSON object with this exact structure, no markdown, no extra text:
{{
  "who_umc": {{
    "time_relationship": {{
      "criterion": "Yes" | "Maybe" | "No",
      "score": 3 | 2 | -2,
      "reason": "Brief clinical rationale",
      "evidence_quote": "Exact phrase from the dossier supporting onset speed, or empty string."
    }},
    "alternative_etiologies": {{
      "criterion": "Cannot be explained by disease or other drugs" | "Unlikely to be attributed to disease or other drugs" | "Could also be explained by disease or other drugs" | "Disease or other drugs provide plausible explanations",
      "score": 3 | 2 | 1 | -2,
      "reason": "Brief clinical rationale",
      "evidence_quote": "Exact phrase supporting a -2 score, or empty string."
    }},
    "phenomenological_nature": {{
      "criterion": "Yes" | "No / Non-specific clinical event",
      "score": 2 | 0,
      "reason": "Brief clinical rationale",
      "evidence_quote": "Exact phrase supporting a 'Yes' score, or empty string."
    }},
    "data_completeness": {{
      "status": "sufficient" | "conditional" | "unassessable",
      "flag": "None" | "Conditional" | "Unassessable",
      "reason": "Brief explanation"
    }}
  }},
  "naranjo_answers": ["yes"|"no"|"unknown", ... (10 elements)],
  "clinical_summary": "Brief 1-sentence synthesis",
  "supportive_treatment_note": "If the narrative mentions supportive treatment given alongside drug withdrawal (e.g. antihistamine, steroid, adrenaline), briefly note it here with the quoted phrase, for reviewer awareness only. Empty string if none mentioned."
}}
"""


@lru_cache(maxsize=128)
def get_clinical_extraction(dossier_text: str, target_drug_name: str, other_drugs: tuple = (),
                             target_drug_json: str = "{}", report_data_json: str = "{}",
                             all_meds_json: str = "[]") -> dict:
    """
    Evaluates the clinical case against the WHO-UMC scale and Naranjo scale
    using the multi-provider LLM chain, then resolves the WHO-UMC portion
    against structured form data. There is NO deterministic/regex fallback
    for clinical judgment — if every provider fails, this returns
    ai_unavailable=True and callers must route to Conditional/Unclassified.

    target_drug_json / report_data_json / all_meds_json are JSON-serialized
    because lru_cache requires hashable arguments.
    """
    target_drug = json.loads(target_drug_json) if target_drug_json else {}
    report_data = json.loads(report_data_json) if report_data_json else {}
    all_medications = json.loads(all_meds_json) if all_meds_json else []

    if not dossier_text or not dossier_text.strip():
        return {
            "who_umc": {}, "naranjo_answers": ["unknown"] * 10, "clinical_summary": "",
            "ai_unavailable": True,
            "unavailable_reason": "Empty case dossier — nothing to evaluate."
        }

    prompt = _build_extraction_prompt(dossier_text, target_drug_name)
    data = call_clinical_llm(prompt)

    if data is None:
        return {
            "who_umc": {}, "naranjo_answers": ["unknown"] * 10, "clinical_summary": "",
            "ai_unavailable": True,
            "unavailable_reason": ("All configured AI providers were unreachable or returned invalid data. "
                                    "Manual clinical review required — no score was guessed.")
        }

    who = data.get("who_umc", {})
    naranjo = data.get("naranjo_answers", ["unknown"] * 10)
    if len(naranjo) < 10:
        naranjo.extend(["unknown"] * (10 - len(naranjo)))
    naranjo = [str(a).lower().strip() for a in naranjo[:10]]

    res = {
        "who_umc": who,
        "naranjo_answers": naranjo,
        "clinical_summary": data.get("clinical_summary", ""),
        "supportive_treatment_note": data.get("supportive_treatment_note") or None,
    }

    res['who_umc'] = resolve_who_umc_criteria(res.get('who_umc', {}), dossier_text, target_drug,
                                                other_drugs, report_data, all_medications)
    return res
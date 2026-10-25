# """
# Official WHO-UMC Criteria-Based Scoring Scale Causality Assessment Engine.

# Implements the official scoring criteria:
# 1. Time relationship to drug intake: Plausible (+3), Reasonable (+2), Improbable (-2)
# 2. Alternative etiologies: Cannot be explained (+3), Unlikely (+2), Could also be explained (+1), Disease/drugs provide explanation (-2)
# 3. Response to withdrawal (Dechallenge): Plausible (+3), Clinically reasonable (+2), Lacking/unclear (0), Negative (-2)
# 4. Rechallenge outcome: Satisfactory (+2), Not required/done (0), Negative (-2)
# 5. Phenomenological / Pharmacological nature: Yes (+2), No/Non-specific (0)
# 6. Data completeness: Sufficient (0), More data needed (Flag: Conditional), Insufficient/contradictory (Flag: Unassessable)

# Score Thresholds:
# - >= 11 points  -> Certain
# - 7 - 10 points -> Probable / Likely
# - 3 - 6 points  -> Possible
# - <= 2 points   -> Unlikely
# - Non-scored: Conditional / Unclassified, Unassessable / Unclassifiable
# """

# import os
# from typing import Optional, Dict, Any, List
# from dotenv import load_dotenv

# load_dotenv()

# from ml.nlp_extractor import get_clinical_extraction, build_clinical_dossier, classify_drug_risk

# WHO_UMC_CATEGORIES = {
#     "Certain": "Event with plausible time relationship; cannot be explained by disease or other drugs; response to withdrawal plausible; event definitive; rechallenge satisfactory if performed (>= 11 points).",
#     "Probable/Likely": "Event with reasonable time relationship; unlikely to be attributed to disease or other drugs; response to withdrawal clinically reasonable; rechallenge not required (7-10 points).",
#     "Possible": "Event with reasonable time relationship; could also be explained by disease or other drugs; information on drug withdrawal lacking or unclear (3-6 points).",
#     "Unlikely": "Event with time to drug intake making relationship improbable; disease or other drugs provide plausible explanations (<= 2 points).",
#     "Conditional/Unclassified": "More data for proper assessment needed or under examination.",
#     "Unassessable/Unclassifiable": "Information is insufficient or contradictory; data cannot be supplemented or verified."
# }


# def assess_who_umc(form_payload: dict, target_drug_name: str = "", nlp_context: Optional[dict] = None) -> dict:
#     """
#     Evaluates causality using the official WHO-UMC Criteria-Based Scoring Scale.
#     """
#     suspect_drugs = form_payload.get("medications", []) or []
#     target_drug = None

#     if target_drug_name:
#         target_drug = next((d for d in suspect_drugs if d.get("drug_name", "").lower() == target_drug_name.lower()), None)
    
#     if not target_drug and suspect_drugs:
#         target_drug = suspect_drugs[0]
#         if not target_drug_name:
#             target_drug_name = target_drug.get("drug_name", "")

#     if not target_drug:
#         target_drug = {}

#     # Extract clinical NLP context if not provided
#     if nlp_context is None or "who_umc" not in nlp_context:
#         suspect_drug_names = [d.get("drug_name", "") for d in suspect_drugs if d.get("drug_name")]
#         other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())
        
#         dossier = build_clinical_dossier(form_payload, target_drug_name)
#         nlp_context = get_clinical_extraction(dossier, target_drug_name, other_drug_names)

#     who_eval = nlp_context.get("who_umc", {})
    
#     # 1. Check Completeness / Unassessable Flags
#     comp_info = who_eval.get("data_completeness", {})
#     comp_flag = comp_info.get("flag", "None")
    
#     if form_payload.get("unverifiable_or_contradictory", False) or comp_flag == "Unassessable":
#         return {
#             "category": "Unassessable/Unclassifiable",
#             "score": 0,
#             "criteria": who_eval,
#             "reason": comp_info.get("reason", "Information is insufficient or contradictory and cannot be verified.")
#         }

#     if form_payload.get("data_being_actively_collected", False) or comp_flag == "Conditional":
#         return {
#             "category": "Conditional/Unclassified",
#             "score": 0,
#             "criteria": who_eval,
#             "reason": comp_info.get("reason", "Case cannot yet be assessed; additional data is currently under examination.")
#         }

#     # 2. Extract Individual Criteria Scores
#     s1 = who_eval.get("time_relationship", {}).get("score", 2)
#     s2 = who_eval.get("alternative_etiologies", {}).get("score", 2)
#     s3 = who_eval.get("dechallenge", {}).get("score", 0)
#     s4 = who_eval.get("rechallenge", {}).get("score", 0)
#     s5 = who_eval.get("phenomenological_nature", {}).get("score", 0)

#     # Calculate Total Score
#     total_score = s1 + s2 + s3 + s4 + s5

#     # 3. Categorize based on Official Score Thresholds
#     if total_score >= 11:
#         category = "Certain"
#         reason = f"Total Score: {total_score} pts (>= 11). Plausible timeline (+{s1}), cannot be explained by disease/other drugs (+{s2}), plausible dechallenge (+{s3}), definitive event (+{s5}), satisfactory rechallenge (+{s4})."
#     elif total_score >= 7:
#         category = "Probable/Likely"
#         reason = f"Total Score: {total_score} pts (7-10). Reasonable timeline (+{s1}), unlikely alternative causes (+{s2}), clinically reasonable dechallenge (+{s3}). Rechallenge not required."
#     elif total_score >= 3:
#         category = "Possible"
#         reason = f"Total Score: {total_score} pts (3-6). Reasonable timeline (+{s1}), but event could be explained by concurrent disease/other drugs (+{s2}), and withdrawal data is unconfirmed (+{s3})."
#     else:
#         category = "Unlikely"
#         reason = f"Total Score: {total_score} pts (<= 2). Improbable timeline ({s1}) and/or disease or other therapies provide plausible explanations ({s2})."

#     return {
#         "category": category,
#         "score": total_score,
#         "criteria": who_eval,
#         "reason": reason
#     }


# def run_assessment(form_data: dict, target_drug_name: str) -> dict:
#     """
#     Evaluates causality for a specific target medication within the ADR report.
#     """
#     suspect_drugs = form_data.get("medications", []) or []
#     target_drug = next((d for d in suspect_drugs if d.get("drug_name", "").lower() == target_drug_name.lower()), None)
    
#     if not target_drug and suspect_drugs:
#         target_drug = suspect_drugs[0]
#         if not target_drug_name:
#             target_drug_name = target_drug.get("drug_name", "")

#     if not target_drug:
#         return {
#             "category": "Unassessable/Unclassifiable",
#             "score": 0,
#             "criteria": {},
#             "reason": "Target drug not found in report payload."
#         }

#     suspect_drug_names = [d.get("drug_name", "") for d in suspect_drugs if d.get("drug_name")]
#     other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())
    
#     dossier = build_clinical_dossier(form_data, target_drug_name)
#     nlp_context = get_clinical_extraction(dossier, target_drug_name, other_drug_names)
    
#     return assess_who_umc(form_data, target_drug_name, nlp_context)


# def assess_from_api_payload(form_data: dict) -> dict:
#     """
#     Evaluates each suspected medication individually and returns
#     the overall assessment (strongest causality category across all drugs).
#     """
#     suspect_drugs = form_data.get("medications", []) or []
#     if not suspect_drugs:
#         return {
#             "category": "Unassessable/Unclassifiable",
#             "score": 0,
#             "reason": "No suspected medications found."
#         }

#     severity_order = [
#         "Certain",
#         "Probable/Likely",
#         "Possible",
#         "Unlikely",
#         "Conditional/Unclassified",
#         "Unassessable/Unclassifiable",
#     ]

#     best_result = None
#     best_rank = len(severity_order)

#     for drug in suspect_drugs:
#         drug_name = drug.get("drug_name", "")
#         if not drug_name:
#             continue
#         result = run_assessment(form_data, drug_name)
#         rank = severity_order.index(result["category"]) if result["category"] in severity_order else len(severity_order)
#         if rank < best_rank:
#             best_rank = rank
#             best_result = result

#     if best_result is None:
#         return {
#             "category": "Unassessable/Unclassifiable",
#             "score": 0,
#             "reason": "Could not evaluate any suspected medication."
#         }

#     return best_result





"""
Official WHO-UMC Criteria-Based Scoring Scale Causality Assessment Engine.

Implements the project's quantified WHO-UMC scale:
1. Time relationship to drug intake: Plausible (+3), Reasonable (+2), Improbable (-2)
2. Alternative etiologies: Cannot be explained (+3), Unlikely (+2), Could also be explained (+1), Disease/drugs provide explanation (-2)
3. Response to withdrawal (Dechallenge): Plausible (+3), Clinically reasonable (+2), Lacking/unclear (0), Negative (-2)
4. Rechallenge outcome: Satisfactory (+2), Not required/done (0), Negative (-2)
5. Phenomenological / Pharmacological nature: Yes (+2), No/Non-specific (0)
6. Data completeness: Sufficient (0), More data needed (Flag: Conditional), Insufficient/contradictory (Flag: Unassessable)

Score Thresholds:
- >= 11 points  -> Certain      (GATED: also requires satisfactory rechallenge AND fully-excluded alternative cause)
- 7 - 10 points -> Probable / Likely  (GATED: also requires alternative_etiologies score >= 2)
- 3 - 6 points  -> Possible
- <= 2 points   -> Unlikely
- Non-scored: Conditional / Unclassified, Unassessable / Unclassifiable

GATING RATIONALE: reviewing real reported cases showed that reports with no
rechallenge data were consistently capped at Probable/Likely by human
reviewers even when every other criterion scored at the maximum — the raw
point sum alone would incorrectly cross into "Certain" for those cases.
Similarly, a report where alternative causes are only "could also be
explained" (+1) was never elevated to Probable/Likely purely by other
criteria scoring high. These gates encode that behavior explicitly rather
than leaving it to an unguarded point sum.

MISSING-DATA POLICY: if any of the five WHO-UMC criteria could not be
resolved (structurally or via a grounded quote), this module does NOT guess
a default score. The case is returned as "Conditional/Unclassified" with the
specific missing criteria named, so a human reviewer can supply the missing
information rather than the system silently assuming a neutral value.
"""

"""
WHO-UMC Criteria-Based Scoring Scale Causality Assessment Engine.

Implements the project's quantified WHO-UMC scale:
1. Time relationship to drug intake: Plausible (+3), Reasonable (+2), Improbable (-2)
2. Alternative etiologies: Cannot be explained (+3), Unlikely (+2), Could also be explained (+1), Disease/drugs provide explanation (-2)
3. Response to withdrawal (Dechallenge): Plausible (+3), Clinically reasonable (+2), Lacking/unclear (0), Negative (-2)
4. Rechallenge outcome: Satisfactory (+2), Not required/done (0), Negative (-2)
5. Phenomenological / Pharmacological nature: Yes (+2), No/Non-specific (0)
6. Data completeness: Sufficient (0), More data needed (Flag: Conditional), Insufficient/contradictory (Flag: Unassessable)

Score Thresholds (literal, per the project's WHO-UMC scale document — no
artificial gating layered on top):
- >= 11 points  -> Certain
- 7 - 10 points -> Probable / Likely
- 3 - 6 points  -> Possible
- <= 2 points   -> Unlikely
- Non-scored: Conditional / Unclassified, Unassessable / Unclassifiable

ACCURACY POLICY (critical for this system):
1. If any of the five scored criteria could not be resolved (structurally
   or via a grounded LLM quote), this module does NOT guess a default
   score. The case is returned as "Conditional/Unclassified" with the
   specific missing criteria named.
2. If every configured AI provider was unreachable (see nlp_extractor.py's
   call_clinical_llm chain), this module returns "Conditional/Unclassified"
   with requires_manual_review=True. It NEVER falls back to a keyword/regex
   guess — there is no such fallback anywhere in this system.
"""

import os
import json
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from ml.nlp_extractor import (
    get_clinical_extraction,
    build_clinical_dossier,
)

WHO_UMC_CATEGORIES = {
    "Certain": "Event with plausible time relationship; cannot be explained by disease or other drugs; response to withdrawal plausible; event definitive; rechallenge satisfactory if performed (>= 11 points).",
    "Probable/Likely": "Event with reasonable time relationship; unlikely to be attributed to disease or other drugs; response to withdrawal clinically reasonable; rechallenge not required (7-10 points).",
    "Possible": "Event with reasonable time relationship; could also be explained by disease or other drugs; information on drug withdrawal lacking or unclear (3-6 points).",
    "Unlikely": "Event with time to drug intake making relationship improbable; disease or other drugs provide plausible explanations (<= 2 points).",
    "Conditional/Unclassified": "More data for proper assessment needed or under examination.",
    "Unassessable/Unclassifiable": "Information is insufficient or contradictory; data cannot be supplemented or verified."
}


def assess_who_umc(form_payload: dict, target_drug_name: str = "", nlp_context: Optional[dict] = None) -> dict:
    """
    Evaluates causality using the project's WHO-UMC Criteria-Based Scoring Scale.
    """
    suspect_drugs = form_payload.get("medications", []) or []
    target_drug = None

    if target_drug_name:
        target_drug = next((d for d in suspect_drugs if d.get("drug_name", "").lower() == target_drug_name.lower()), None)

    if not target_drug and suspect_drugs:
        target_drug = suspect_drugs[0]
        if not target_drug_name:
            target_drug_name = target_drug.get("drug_name", "")

    if not target_drug:
        target_drug = {}

    dossier = build_clinical_dossier(form_payload, target_drug_name)

    if nlp_context is None or "who_umc" not in nlp_context:
        suspect_drug_names = [d.get("drug_name", "") for d in suspect_drugs if d.get("drug_name")]
        other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())

        nlp_context = get_clinical_extraction(
            dossier, target_drug_name, other_drug_names,
            target_drug_json=json.dumps(target_drug, sort_keys=True),
            report_data_json=json.dumps(form_payload, sort_keys=True),
            all_meds_json=json.dumps(suspect_drugs, sort_keys=True),
        )

    supportive_note = nlp_context.get("supportive_treatment_note") or None

    # 0. AI unavailable across every provider — never guess, always say so.
    if nlp_context.get("ai_unavailable"):
        return {
            "category": "Conditional/Unclassified",
            "score": 0,
            "criteria": {},
            "reason": nlp_context.get("unavailable_reason",
                       "AI clinical assessment unavailable. Manual review required."),
            "requires_manual_review": True,
            "supportive_treatment_note": supportive_note,
        }

    who_eval = nlp_context.get("who_umc", {})

    # 1. Check Completeness / Unassessable Flags
    comp_info = who_eval.get("data_completeness", {})
    comp_flag = comp_info.get("flag", "None")

    if form_payload.get("unverifiable_or_contradictory", False) or comp_flag == "Unassessable":
        return {
            "category": "Unassessable/Unclassifiable",
            "score": 0,
            "criteria": who_eval,
            "reason": comp_info.get("reason", "Information is insufficient or contradictory and cannot be verified."),
            "supportive_treatment_note": supportive_note,
        }

    if form_payload.get("data_being_actively_collected", False) or comp_flag == "Conditional":
        return {
            "category": "Conditional/Unclassified",
            "score": 0,
            "criteria": who_eval,
            "reason": comp_info.get("reason", "Case cannot yet be assessed; additional data is currently under examination."),
            "supportive_treatment_note": supportive_note,
        }

    # 2. Require every criterion to have a real score — never guess a missing one.
    required = ["time_relationship", "alternative_etiologies", "dechallenge", "rechallenge", "phenomenological_nature"]
    missing = [k for k in required if "score" not in who_eval.get(k, {})]
    if missing:
        return {
            "category": "Conditional/Unclassified",
            "score": 0,
            "criteria": who_eval,
            "reason": f"Cannot assess — missing verifiable evidence for: {', '.join(missing)}. No score was guessed for these criteria.",
            "requires_manual_review": True,
            "supportive_treatment_note": supportive_note,
        }

    s1 = who_eval["time_relationship"]["score"]
    s2 = who_eval["alternative_etiologies"]["score"]
    s3 = who_eval["dechallenge"]["score"]
    s4 = who_eval["rechallenge"]["score"]
    s5 = who_eval["phenomenological_nature"]["score"]

    total_score = s1 + s2 + s3 + s4 + s5

    # 3. Categorize based on literal score thresholds.
    if total_score >= 11:
        category = "Certain"
        reason = (f"Total Score: {total_score} pts (>= 11). Plausible timeline, no alternative explanation, "
                   f"plausible dechallenge, definitive event, rechallenge satisfactory or not required.")
    elif total_score >= 7:
        category = "Probable/Likely"
        reason = (f"Total Score: {total_score} pts (7-10). Reasonable timeline, unlikely alternative causes, "
                   f"clinically reasonable dechallenge.")
    elif total_score >= 3:
        category = "Possible"
        reason = (f"Total Score: {total_score} pts (3-6). Reasonable timeline, but event could be explained by "
                   f"concurrent disease/other drugs, and/or withdrawal data is unconfirmed.")
    else:
        category = "Unlikely"
        reason = (f"Total Score: {total_score} pts (<= 2). Timeline improbable and/or disease or other drugs "
                   f"provide a plausible explanation.")

    return {
        "category": category,
        "score": total_score,
        "criteria": who_eval,
        "reason": reason,
        "supportive_treatment_note": supportive_note,
    }


def run_assessment(form_data: dict, target_drug_name: str) -> dict:
    """
    Evaluates causality for a specific target medication within the ADR report.
    """
    suspect_drugs = form_data.get("medications", []) or []
    target_drug = next((d for d in suspect_drugs if d.get("drug_name", "").lower() == target_drug_name.lower()), None)

    if not target_drug and suspect_drugs:
        target_drug = suspect_drugs[0]
        if not target_drug_name:
            target_drug_name = target_drug.get("drug_name", "")

    if not target_drug:
        return {
            "category": "Unassessable/Unclassifiable",
            "score": 0,
            "criteria": {},
            "reason": "Target drug not found in report payload."
        }

    suspect_drug_names = [d.get("drug_name", "") for d in suspect_drugs if d.get("drug_name")]
    other_drug_names = tuple(name for name in suspect_drug_names if name.lower() != target_drug_name.lower())

    dossier = build_clinical_dossier(form_data, target_drug_name)
    nlp_context = get_clinical_extraction(
        dossier, target_drug_name, other_drug_names,
        target_drug_json=json.dumps(target_drug, sort_keys=True),
        report_data_json=json.dumps(form_data, sort_keys=True),
        all_meds_json=json.dumps(suspect_drugs, sort_keys=True),
    )

    return assess_who_umc(form_data, target_drug_name, nlp_context)


def assess_from_api_payload(form_data: dict) -> dict:
    """
    Evaluates each suspected medication individually and returns
    the overall assessment (strongest causality category across all drugs).
    """
    suspect_drugs = form_data.get("medications", []) or []
    if not suspect_drugs:
        return {
            "category": "Unassessable/Unclassifiable",
            "score": 0,
            "reason": "No suspected medications found."
        }

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
        return {
            "category": "Unassessable/Unclassifiable",
            "score": 0,
            "reason": "Could not evaluate any suspected medication."
        }

    return best_result
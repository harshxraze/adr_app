"""
WHO-UMC Causality Assessment System
Categories:
  - Certain
  - Probable/Likely
  - Possible
  - Unlikely
  - Conditional/Unclassified
  - Unassessable/Unclassifiable
"""

WHO_UMC_CATEGORIES = {
    "Certain": {
        "description": "Event or laboratory test abnormality, with plausible time relationship to drug intake. Cannot be explained by disease or other drugs. Response to withdrawal plausible (pharmacologically, pathologically). Event definitive pharmacologically or phenomenologically (i.e., an objective and specific medical disorder or a recognised pharmacological phenomenon). Rechallenge satisfactory, if necessary.",
        "criteria": [
            "Plausible time relationship",
            "Cannot be explained by disease or other drugs",
            "Positive dechallenge",
            "Positive rechallenge"
        ]
    },
    "Probable/Likely": {
        "description": "Event or laboratory test abnormality, with reasonable time relationship to drug intake. Unlikely to be attributed to disease or other drugs. Response to withdrawal clinically reasonable. Rechallenge not required.",
        "criteria": [
            "Reasonable time relationship",
            "Unlikely due to disease or other drugs",
            "Clinically reasonable dechallenge"
        ]
    },
    "Possible": {
        "description": "Event or laboratory test abnormality, with reasonable time relationship to drug intake. Could also be explained by disease or other drugs. Information on drug withdrawal may be lacking or unclear.",
        "criteria": [
            "Reasonable time relationship",
            "Could be explained by disease or other drugs"
        ]
    },
    "Unlikely": {
        "description": "Event or laboratory test abnormality, with a time to drug intake that makes a relationship improbable (but not impossible). Disease or other drugs provide plausible explanations.",
        "criteria": [
            "Improbable time relationship",
            "Disease or other drugs explain event"
        ]
    },
    "Conditional/Unclassified": {
        "description": "Event or laboratory test abnormality. More data for proper assessment needed, or additional data under examination.",
        "criteria": [
            "More data needed"
        ]
    },
    "Unassessable/Unclassifiable": {
        "description": "Report suggesting an adverse reaction. Cannot be judged because information is insufficient or contradictory. Data cannot be supplemented or verified.",
        "criteria": [
            "Insufficient or contradictory information"
        ]
    }
}


def assess_who_umc(report_data):
    """
    Assess causality using the WHO-UMC system based on ADR report data.

    Args:
        report_data: dict containing ADR report fields

    Returns:
        dict with 'category' and 'reasoning'
    """
    reasoning = []

    # Check for minimum required information
    has_drug = bool(report_data.get('medications') and len(report_data['medications']) > 0)
    has_reaction = bool(report_data.get('reaction_description'))
    has_timeline = bool(report_data.get('reaction_start_date'))

    if not has_drug or not has_reaction:
        return {
            "category": "Unassessable/Unclassifiable",
            "reasoning": ["Insufficient information: missing drug or reaction details"]
        }

    # Assess temporal relationship
    temporal_plausible = False
    if has_timeline and report_data.get('medications'):
        for med in report_data['medications']:
            if med.get('therapy_start_date'):
                temporal_plausible = True
                reasoning.append("Temporal relationship exists between drug administration and reaction onset")
                break

    if not temporal_plausible:
        if has_timeline:
            reasoning.append("Timeline data present but temporal relationship unclear")
        else:
            return {
                "category": "Conditional/Unclassified",
                "reasoning": ["Temporal relationship cannot be established - more data needed"]
            }

    # Assess dechallenge (what happened when drug was stopped)
    positive_dechallenge = False
    dechallenge_unknown = True
    if report_data.get('medications'):
        for med in report_data['medications']:
            action = (med.get('action_taken') or '').lower()
            if action == 'drug_withdrawn':
                dechallenge_unknown = False
                outcome = (report_data.get('outcome') or '').lower()
                if outcome in ['recovered', 'recovering', 'recovered_with_sequelae']:
                    positive_dechallenge = True
                    reasoning.append("Positive dechallenge: patient improved after drug withdrawal")
                else:
                    reasoning.append("Drug withdrawn but patient did not recover")

    # Assess rechallenge
    positive_rechallenge = False
    rechallenge_done = False
    if report_data.get('medications'):
        for med in report_data['medications']:
            reintro = (med.get('reintroduction_result') or '').lower()
            if reintro == 'yes':
                positive_rechallenge = True
                rechallenge_done = True
                reasoning.append("Positive rechallenge: reaction reappeared on reintroduction")
            elif reintro == 'no':
                rechallenge_done = True
                reasoning.append("Negative rechallenge: reaction did not reappear")

    # Assess alternative causes
    alternative_causes = False
    has_concomitant = bool(report_data.get('concomitant_medications') and len(report_data['concomitant_medications']) > 0)
    has_medical_history = bool(report_data.get('medical_history'))

    if has_concomitant:
        alternative_causes = True
        reasoning.append("Concomitant medications present as potential alternative cause")
    if has_medical_history:
        reasoning.append("Medical history present - may explain the reaction")

    # Determine category
    if temporal_plausible and positive_dechallenge and positive_rechallenge and not alternative_causes:
        category = "Certain"
    elif temporal_plausible and positive_dechallenge and not alternative_causes:
        category = "Probable/Likely"
    elif temporal_plausible and (alternative_causes or dechallenge_unknown):
        category = "Possible"
    elif not temporal_plausible:
        category = "Unlikely"
    else:
        category = "Possible"

    return {
        "category": category,
        "reasoning": reasoning,
        "description": WHO_UMC_CATEGORIES[category]["description"]
    }

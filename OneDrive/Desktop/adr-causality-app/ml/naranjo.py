"""
Naranjo Adverse Drug Reaction Probability Scale
Used for causality assessment of ADRs.
Score interpretation:
  >= 9  : Definite
  5 - 8 : Probable
  1 - 4 : Possible
  <= 0  : Doubtful
"""


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
        answer = answer.lower().strip()
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


def extract_naranjo_features_from_report(report_data):
    """
    Attempt to automatically infer Naranjo answers from ADR report data.
    This is a heuristic approach - returns best-guess answers.

    Args:
        report_data: dict containing ADR report fields

    Returns:
        list of 10 answers ('yes', 'no', 'unknown')
    """
    answers = ['unknown'] * 10

    # Q2: Did the adverse event appear after the suspected drug was administered?
    if report_data.get('reaction_start_date') and report_data.get('medications'):
        for med in report_data['medications']:
            if med.get('therapy_start_date'):
                answers[1] = 'yes'
                break

    # Q3: Did the adverse reaction improve when the drug was discontinued?
    if report_data.get('medications'):
        for med in report_data['medications']:
            action = (med.get('action_taken') or '').lower()
            if action == 'drug_withdrawn':
                outcome = (report_data.get('outcome') or '').lower()
                if outcome in ['recovered', 'recovering']:
                    answers[2] = 'yes'
                elif outcome in ['not_recovered']:
                    answers[2] = 'no'
                break

    # Q4: Did the adverse reaction reappear when the drug was re-administered?
    if report_data.get('medications'):
        for med in report_data['medications']:
            reintro = (med.get('reintroduction_result') or '').lower()
            if reintro == 'yes':
                answers[3] = 'yes'
            elif reintro == 'no':
                answers[3] = 'no'
            break

    # Q5: Are there alternative causes?
    if report_data.get('concomitant_medications') and len(report_data['concomitant_medications']) > 0:
        answers[4] = 'yes'
    elif report_data.get('medical_history'):
        answers[4] = 'unknown'

    # Q8: Was the reaction more severe when dose was increased?
    if report_data.get('medications'):
        for med in report_data['medications']:
            action = (med.get('action_taken') or '').lower()
            if action == 'dose_increased':
                answers[7] = 'yes'
            elif action == 'dose_reduced':
                outcome = (report_data.get('outcome') or '').lower()
                if outcome in ['recovered', 'recovering']:
                    answers[7] = 'yes'

    # Q10: Was the adverse event confirmed by objective evidence?
    if report_data.get('relevant_investigations'):
        answers[9] = 'yes'

    return answers

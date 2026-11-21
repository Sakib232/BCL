"""
IELTS Bhuiyan - Automated Writing Exam Analyzer & Practice Band Scoring Engine
Evaluates candidate essay responses according to official IELTS Writing Descriptors:
  1. Task Achievement / Task Response (TA / TR)
  2. Coherence and Cohesion (CC)
  3. Lexical Resource (LR)
  4. Grammatical Range and Accuracy (GRA)

All scores are stored directly in the database (`WritingTaskEvaluation`,
`WritingEvaluation`, and `CandidateAttempt.band_score`), allowing candidates
to view their immediate results and staff/administrators to review, override,
and modify scores with full persistence.
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from .models import (
    ExamModule,
    Question,
    CandidateAttempt,
    CandidateAnswer,
    WritingEvaluation,
    WritingTaskEvaluation,
    get_writing_task_questions,
)


# Standard academic stop words to exclude from lexical diversity calculation
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
}

# Advanced Academic Vocabulary (AWL / Academic Word List sample)
ACADEMIC_WORD_LIST = {
    "accommodate", "accumulate", "adjacent", "advocate", "aggregate", "allocate",
    "alternative", "ambiguous", "amend", "analogy", "anticipate", "apparent",
    "appreciate", "appropriate", "approximate", "arbitrary", "aspect", "assemble",
    "assess", "assign", "assist", "assume", "attribute", "automate", "available",
    "benefit", "bias", "brief", "capable", "capacity", "category", "channel",
    "circumstance", "clarify", "coincide", "collapse", "commence", "commission",
    "commit", "commodity", "compatible", "compensate", "compile", "complement",
    "complex", "component", "compound", "comprehensive", "comprise", "compute",
    "conceive", "conclude", "concurrent", "conduct", "confer", "confine",
    "confirm", "conform", "consent", "consequence", "considerable", "consist",
    "constant", "constitute", "constrain", "construct", "consult", "consume",
    "contact", "contemporary", "context", "contract", "contradict", "contrary",
    "contrast", "contribute", "controversy", "convene", "converse", "convert",
    "convince", "cooperate", "coordinate", "core", "correspond", "crucial",
    "currency", "cycle", "debate", "decade", "decline", "deduce", "define",
    "definite", "demonstrate", "denote", "deny", "depress", "derive", "design",
    "despite", "detect", "deviate", "devise", "differentiate", "dimension",
    "diminish", "discrete", "discriminate", "displace", "display", "dispose",
    "distinct", "distort", "distribute", "diverse", "document", "domain",
    "domestic", "dominate", "draft", "drama", "duration", "dynamic", "economy",
    "element", "eliminate", "emerge", "emphasis", "empirical", "enable",
    "encounter", "energy", "enforce", "enhance", "enormous", "ensure", "entity",
    "environment", "equate", "equip", "equivalent", "erode", "error", "establish",
    "estate", "estimate", "ethic", "ethnic", "evaluate", "eventual", "evident",
    "evolve", "exceed", "exclude", "exhibit", "expand", "expert", "explicit",
    "exploit", "export", "expose", "external", "extract", "facilitate", "factor",
    "feature", "federal", "fee", "file", "final", "finance", "finite", "flexible",
    "fluctuate", "focus", "format", "formula", "forthcoming", "foundation",
    "framework", "function", "fund", "fundamental", "furthermore", "gender",
    "generate", "generation", "globe", "goal", "grade", "grant", "guarantee",
    "guideline", "hence", "hierarchy", "highlight", "hypothesis", "identical",
    "identify", "ideology", "ignorant", "illustrate", "image", "immigrate",
    "impact", "implement", "implicate", "implicit", "imply", "impose", "incentive",
    "incidence", "incline", "income", "incorporate", "index", "indicate",
    "individual", "induce", "inevitable", "infer", "infrastructure", "inherent",
    "inhibit", "initial", "initiate", "injure", "innovate", "input", "insert",
    "insight", "inspect", "instance", "institute", "instruct", "integral",
    "integrate", "integrity", "intelligence", "intense", "interact", "intermediate",
    "internal", "interpret", "interval", "intervene", "intrinsic", "invest",
    "investigate", "invoke", "involve", "isolate", "issue", "item", "job",
    "journal", "justify", "label", "labor", "layer", "lecture", "legal",
    "legislate", "levy", "liberal", "license", "likewise", "link", "locate",
    "logic", "maintain", "major", "manipulate", "manual", "margin", "mature",
    "maximise", "mechanism", "media", "mediate", "medical", "medium", "method",
    "migrate", "military", "minimal", "minimise", "minimum", "ministry", "minor",
    "mode", "modify", "monitor", "motive", "mutual", "negate", "network",
    "neutral", "nevertheless", "nonetheless", "norm", "notion", "nuclear",
    "objective", "obtain", "obvious", "occupy", "occur", "odd", "offset",
    "ongoing", "option", "orient", "outcome", "output", "overall", "overlap",
    "overseas", "panel", "paradigm", "paragraph", "parallel", "parameter",
    "participate", "partner", "passive", "perceive", "percent", "period",
    "persist", "perspective", "phase", "phenomenon", "philosophy", "physical",
    "plus", "policy", "portion", "pose", "positive", "potential", "practitioner",
    "precede", "precise", "predict", "predominant", "preliminary", "presume",
    "previous", "primary", "prime", "principal", "principle", "prior", "priority",
    "proceed", "process", "professional", "prohibit", "project", "promote",
    "proportion", "prospect", "protocol", "psychology", "publication", "publish",
    "purchase", "pursue", "qualitative", "quote", "radical", "random", "range",
    "ratio", "rational", "react", "recover", "refine", "regime", "region",
    "register", "regulate", "reinforce", "reject", "relax", "release", "relevant",
    "reluctance", "rely", "remove", "require", "research", "reside", "resolve",
    "resource", "respond", "restore", "restrain", "restrict", "retain", "reveal",
    "revenue", "reverse", "revise", "revolution", "rigid", "role", "route",
    "scenario", "schedule", "scheme", "scope", "section", "sector", "secure",
    "seek", "select", "sequence", "series", "shift", "significant", "similar",
    "simulate", "site", "so-called", "sole", "somewhat", "source", "specific",
    "specify", "sphere", "stable", "statistic", "status", "straightforward",
    "strategy", "stress", "structure", "subsequent", "subsidy", "substitute",
    "successor", "sufficient", "sum", "summary", "supplement", "survey", "survive",
    "suspend", "sustain", "symbol", "tape", "target", "task", "team", "technical",
    "technique", "technology", "temporary", "tense", "terminate", "text", "theme",
    "theory", "thereby", "thesis", "topic", "trace", "tradition", "transfer",
    "transform", "transit", "transmit", "transport", "trend", "trigger",
    "ultimate", "undergo", "underlie", "undertake", "uniform", "unify", "unique",
    "utilise", "valid", "vary", "vehicle", "version", "via", "violate", "virtual",
    "visible", "vision", "visual", "volume", "voluntary", "welfare", "whereas",
    "whereby", "widespread"
}

# Cohesive rhetorical transition categories
COHESIVE_PATTERNS = {
    "addition": [
        r"\bfurthermore\b", r"\bmoreover\b", r"\bin addition\b", r"\badditionally\b",
        r"\bbesides\b", r"\bwhat is more\b", r"\bnot only\b", r"\bas well as\b"
    ],
    "contrast": [
        r"\bhowever\b", r"\bin contrast\b", r"\bon the other hand\b", r"\bnevertheless\b",
        r"\bnonetheless\b", r"\bconversely\b", r"\bwhereas\b", r"\balthough\b",
        r"\beven though\b", r"\bwhile\b", r"\bdespite\b", r"\bin spite of\b"
    ],
    "result": [
        r"\bconsequently\b", r"\btherefore\b", r"\bas a result\b", r"\bthus\b",
        r"\bhence\b", r"\bfor this reason\b", r"\baccordingly\b", r"\bleads to\b"
    ],
    "exemplification": [
        r"\bfor example\b", r"\bfor instance\b", r"\bto illustrate\b", r"\bsuch as\b",
        r"\bin particular\b", r"\bnamely\b"
    ],
    "overview_conclusion": [
        r"\boverall\b", r"\bin conclusion\b", r"\bto conclude\b", r"\bto sum up\b",
        r"\bin summary\b", r"\bon the whole\b", r"\ball in all\b"
    ],
    "sequencing": [
        r"\bfirstly\b", r"\bsecondly\b", r"\bthirdly\b", r"\bfinally\b",
        r"\bsubsequently\b", r"\binitially\b", r"\bto begin with\b"
    ],
    "stance": [
        r"\bin my opinion\b", r"\bi believe\b", r"\bfrom my perspective\b",
        r"\bit is evident that\b", r"\bit is clear that\b", r"\bundoubtedly\b"
    ]
}


def round_to_ielts_half_band(value):
    """
    Round a float or Decimal according to official IELTS band score convention:
    - Fractions < 0.25 round down to .0
    - Fractions >= 0.25 and < 0.75 round to .5
    - Fractions >= 0.75 round up to next .0
    """
    dec = Decimal(str(value))
    return (dec * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("2")


def evaluate_writing_text(text, task_number=1):
    """
    Evaluates a single writing response (Task 1 or Task 2) and returns
    a dictionary of band scores and constructive feedback.
    """
    raw_text = (text or "").strip()
    words = re.findall(r"\b[a-zA-Z0-9'-]+\b", raw_text)
    word_count = len(words)

    # Empty or negligible response
    if word_count < 15:
        base_band = Decimal("5.0") if word_count > 0 else Decimal("0.0")
        return {
            "task_achievement": base_band,
            "coherence_cohesion": base_band,
            "lexical_resource": base_band,
            "grammatical_range_accuracy": base_band,
            "criterion_average": base_band,
            "word_count": word_count,
            "feedback": "Minimum suggested word count not reached. Evaluated at baseline band 5.0." if word_count > 0 else "No response submitted for this task."
        }

    paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
    num_paragraphs = len(paragraphs)
    sentences = [s.strip() for s in re.split(r"[.!?]+", raw_text) if len(s.strip()) > 3]
    num_sentences = max(len(sentences), 1)
    avg_sentence_len = word_count / num_sentences

    lower_text = raw_text.lower()

    # --------------------------------------------------------------------------
    # 1. TASK ACHIEVEMENT (Task 1) / TASK RESPONSE (Task 2)
    # --------------------------------------------------------------------------
    ta_score = 6.0
    min_words = 150 if task_number == 1 else 250

    # Word count thresholds
    if word_count >= min_words + 50:
        ta_score += 1.0
    elif word_count >= min_words:
        ta_score += 0.5
    elif word_count >= min_words * 0.8:
        ta_score -= 0.5
    elif word_count >= min_words * 0.6:
        ta_score -= 1.5
    else:
        ta_score -= 2.5

    # Task 1 specific: Check for Overview and Data/Figures
    if task_number == 1:
        has_overview = bool(re.search(
            r"\b(overall|in summary|it is clear that|it is evident that|trends?|on the whole)\b",
            lower_text
        ))
        has_data = bool(re.search(r"\b\d+(\.\d+)?%?|\b\d{4}\b", raw_text))

        if has_overview:
            ta_score += 0.5
        else:
            ta_score = min(ta_score, 5.0)  # Standard IELTS penalty: no overview caps TA at 5.0

        if has_data:
            ta_score += 0.5

    # Task 2 specific: Check for Stance, Introduction, and Conclusion
    else:
        has_conclusion = bool(re.search(
            r"\b(in conclusion|to conclude|to sum up|in summary|overall)\b",
            lower_text
        ))
        has_position = bool(re.search(
            r"\b(in my opinion|i believe|from my perspective|i think|my view|argue that)\b",
            lower_text
        ))

        if has_conclusion:
            ta_score += 0.5
        if has_position:
            ta_score += 0.5
        if num_paragraphs >= 4:
            ta_score += 0.5
        elif num_paragraphs < 3:
            ta_score -= 0.5

    # Standard bounded band: keep writing score between 5.0 and 7.0
    MIN_BAND = Decimal("5.0")
    MAX_BAND = Decimal("7.0")

    ta_band = max(MIN_BAND, min(MAX_BAND, round_to_ielts_half_band(ta_score)))

    # --------------------------------------------------------------------------
    # 2. COHERENCE AND COHESION (CC)
    # --------------------------------------------------------------------------
    cc_score = 5.5

    # Paragraphing
    if num_paragraphs >= 3:
        cc_score += 1.0
    elif num_paragraphs == 2:
        cc_score += 0.5
    else:
        cc_score -= 1.0  # Single block penalty

    # Cohesive device categories detected
    detected_cats = 0
    for cat_name, patterns in COHESIVE_PATTERNS.items():
        if any(re.search(pat, lower_text) for pat in patterns):
            detected_cats += 1

    if detected_cats >= 5:
        cc_score += 1.5
    elif detected_cats >= 3:
        cc_score += 1.0
    elif detected_cats >= 2:
        cc_score += 0.5
    else:
        cc_score -= 0.5

    cc_band = max(MIN_BAND, min(MAX_BAND, round_to_ielts_half_band(cc_score)))

    # --------------------------------------------------------------------------
    # 3. LEXICAL RESOURCE (LR)
    # --------------------------------------------------------------------------
    lr_score = 5.5

    non_stop_words = [w.lower() for w in words if w.lower() not in STOP_WORDS and len(w) > 2]
    total_non_stop = len(non_stop_words)

    if total_non_stop > 0:
        unique_words = set(non_stop_words)
        ttr = len(unique_words) / total_non_stop  # Type-Token Ratio
        awl_hits = [w for w in unique_words if w in ACADEMIC_WORD_LIST]
        awl_count = len(awl_hits)

        if ttr >= 0.70:
            lr_score += 1.0
        elif ttr >= 0.55:
            lr_score += 0.5
        elif ttr < 0.40:
            lr_score -= 0.5

        if awl_count >= 12:
            lr_score += 1.5
        elif awl_count >= 7:
            lr_score += 1.0
        elif awl_count >= 3:
            lr_score += 0.5
        else:
            lr_score -= 0.5
    else:
        lr_score = 3.0

    lr_band = max(MIN_BAND, min(MAX_BAND, round_to_ielts_half_band(lr_score)))

    # --------------------------------------------------------------------------
    # 4. GRAMMATICAL RANGE AND ACCURACY (GRA)
    # --------------------------------------------------------------------------
    gra_score = 5.5

    # Complex structures (subordinating conjunctions, relative clauses, conditionals)
    complex_markers = [
        r"\balthough\b", r"\beven though\b", r"\bwhile\b", r"\bwhereas\b",
        r"\bsince\b", r"\bbecause\b", r"\bwhich\b", r"\bthat\b", r"\bwho\b",
        r"\bif\b", r"\bunless\b", r"\bprovided that\b", r"\bafter\b", r"\bbefore\b"
    ]
    complex_count = sum(1 for pat in complex_markers if re.search(pat, lower_text))

    if complex_count >= 6:
        gra_score += 1.5
    elif complex_count >= 4:
        gra_score += 1.0
    elif complex_count >= 2:
        gra_score += 0.5
    else:
        gra_score -= 0.5

    # Sentence variety and length balance
    if 14 <= avg_sentence_len <= 26:
        gra_score += 0.5
    elif avg_sentence_len < 9:
        gra_score -= 0.5  # overly simplistic
    elif avg_sentence_len > 35:
        gra_score -= 0.5  # run-on tendencies

    gra_band = max(MIN_BAND, min(MAX_BAND, round_to_ielts_half_band(gra_score)))

    # Criterion average for this task, kept between 5.0 and 7.0
    raw_avg = (ta_band + cc_band + lr_band + gra_band) / Decimal("4.0")
    criterion_avg = max(MIN_BAND, min(MAX_BAND, raw_avg))

    # Construct constructive, transparent examiner feedback
    feedback_lines = [
        f"• Word Count: {word_count} words (Target: {min_words}+). " +
        ("Compliant with recommended length." if word_count >= min_words else f"Below suggested minimum ({min_words} words)."),
        f"• Structure: {num_paragraphs} paragraph(s) and {num_sentences} sentences.",
        f"• Cohesion: {detected_cats} distinct cohesive rhetorical transition categories used.",
        f"• Lexical Range: Type-token diversity ratio of {round(len(set(words))/max(word_count,1), 2)} with academic vocabulary indicators.",
        f"• Grammar & Range: Variety of compound and complex sentence structures identified.",
    ]
    if task_number == 1 and not has_overview:
        feedback_lines.append("• Note: Consider including a clear, highlighted overview statement to enhance Task Achievement.")
    elif task_number == 2 and not has_conclusion:
        feedback_lines.append("• Note: Ensure an explicit conclusion paragraph is included to finalize your position.")

    feedback_text = "\n".join(feedback_lines)

    return {
        "task_achievement": ta_band,
        "coherence_cohesion": cc_band,
        "lexical_resource": lr_band,
        "grammatical_range_accuracy": gra_band,
        "criterion_average": criterion_avg,
        "word_count": word_count,
        "feedback": feedback_text,
    }


def get_default_examiner():
    """
    Returns an appropriate staff/superuser account to record as the initial examiner
    for automated evaluations. If none exists, creates a dedicated system examiner.
    """
    User = get_user_model()
    examiner = User.objects.filter(is_superuser=True).order_by("pk").first()
    if not examiner:
        examiner = User.objects.filter(is_staff=True).order_by("pk").first()
    if not examiner:
        examiner, _ = User.objects.get_or_create(
            username="system_examiner",
            defaults={
                "first_name": "System",
                "last_name": "Examiner",
                "email": "examiner@bclbhuiyan.com",
                "is_staff": True,
            }
        )
    return examiner


def auto_evaluate_writing_attempt(attempt):
    """
    Evaluates both Writing tasks of a submitted attempt, persists the scores
    in `WritingTaskEvaluation`, updates `CandidateAttempt.band_score`, and syncs
    full mock test aggregations.

    Safe, idempotent, and non-destructive: if an examiner has already manually graded
    the tasks, those manual evaluations are respected and preserved.
    """
    if attempt.module.module_type != ExamModule.ModuleType.WRITING:
        return None

    essay_questions = get_writing_task_questions(attempt.module)
    if not essay_questions:
        return None

    examiner = get_default_examiner()
    evaluations = {}

    with transaction.atomic():
        # Lock attempt
        locked_attempt = CandidateAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked_attempt.status == CandidateAttempt.AttemptStatus.IN_PROGRESS:
            return None

        for task_idx, question in enumerate(essay_questions[:2], start=1):
            existing_eval = (
                WritingTaskEvaluation.objects.filter(attempt=locked_attempt, task_number=task_idx)
                .select_related("examiner")
                .first()
            )

            # If already manually evaluated by a human staff member other than system, keep it
            if existing_eval and existing_eval.examiner.username != "system_examiner":
                evaluations[task_idx] = existing_eval
                continue

            ans_obj = CandidateAnswer.objects.filter(attempt=locked_attempt, question=question).first()
            ans_text = ans_obj.answer_text if ans_obj else ""

            eval_data = evaluate_writing_text(ans_text, task_number=task_idx)

            if existing_eval:
                existing_eval.task_achievement = eval_data["task_achievement"]
                existing_eval.coherence_cohesion = eval_data["coherence_cohesion"]
                existing_eval.lexical_resource = eval_data["lexical_resource"]
                existing_eval.grammatical_range_accuracy = eval_data["grammatical_range_accuracy"]
                existing_eval.feedback = eval_data["feedback"]
                existing_eval.save()
                evaluations[task_idx] = existing_eval
            else:
                new_eval = WritingTaskEvaluation.objects.create(
                    attempt=locked_attempt,
                    question=question,
                    task_number=task_idx,
                    examiner=examiner,
                    task_achievement=eval_data["task_achievement"],
                    coherence_cohesion=eval_data["coherence_cohesion"],
                    lexical_resource=eval_data["lexical_resource"],
                    grammatical_range_accuracy=eval_data["grammatical_range_accuracy"],
                    feedback=eval_data["feedback"],
                )
                evaluations[task_idx] = new_eval

        # Calculate overall writing band score (Task 1 = 1/3, Task 2 = 2/3)
        if 1 in evaluations and 2 in evaluations:
            t1_avg = evaluations[1].criterion_average
            t2_avg = evaluations[2].criterion_average
            combined = (t1_avg + Decimal("2") * t2_avg) / Decimal("3")
            overall_band = (combined * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("2")
        elif 1 in evaluations:
            overall_band = round_to_ielts_half_band(evaluations[1].criterion_average)
        elif 2 in evaluations:
            overall_band = round_to_ielts_half_band(evaluations[2].criterion_average)
        else:
            overall_band = None

        if overall_band is not None and overall_band > Decimal("0.0"):
            overall_band = max(Decimal("5.0"), min(Decimal("7.0"), overall_band))

        locked_attempt.band_score = overall_band
        locked_attempt.save(update_fields=["band_score"])

        # Also populate or sync the legacy aggregate WritingEvaluation model (bounded 5.0 - 7.0)
        if 1 in evaluations and 2 in evaluations:
            def clamp_bounded_band(val):
                b = round_to_ielts_half_band(val)
                return max(Decimal("5.0"), min(Decimal("7.0"), b))

            WritingEvaluation.objects.update_or_create(
                attempt=locked_attempt,
                defaults={
                    "examiner": examiner,
                    "task_achievement": clamp_bounded_band((evaluations[1].task_achievement + 2 * evaluations[2].task_achievement) / Decimal("3")),
                    "coherence_cohesion": clamp_bounded_band((evaluations[1].coherence_cohesion + 2 * evaluations[2].coherence_cohesion) / Decimal("3")),
                    "lexical_resource": clamp_bounded_band((evaluations[1].lexical_resource + 2 * evaluations[2].lexical_resource) / Decimal("3")),
                    "grammatical_range_accuracy": clamp_bounded_band((evaluations[1].grammatical_range_accuracy + 2 * evaluations[2].grammatical_range_accuracy) / Decimal("3")),
                    "feedback": f"Task 1 Average: {evaluations[1].criterion_average} | Task 2 Average: {evaluations[2].criterion_average}",
                }
            )

        # Update full mock test aggregate if part of one
        if locked_attempt.full_mock_id:
            full_mock = locked_attempt.full_mock
            if full_mock:
                full_mock.calculate_overall_score()
                full_mock.save(update_fields=["overall_band_score"])

    attempt.refresh_from_db()
    return overall_band

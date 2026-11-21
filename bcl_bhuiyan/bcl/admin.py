import html
import re
from decimal import Decimal
from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models import Count, Q
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    QuestionOption,
    CandidateAttempt,
    CandidateAnswer,
    WritingEvaluation,
    FullMockAttempt,
    CandidateProfile,
    MockFromOption,
    SubAdminProfile,
    is_main_admin,
    is_subadmin,
    get_subadmin_mock_from,
    can_manage_mock_tests,
)
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin


# ==============================================================================
# ADMIN SITE BRANDING
# ==============================================================================

admin.site.site_header = "BCL_Bhuiyan — Exam Portal Administration"
admin.site.site_title = "BCL_Bhuiyan Admin"
admin.site.index_title = "Exam Management & Question Setting Dashboard"


# ==============================================================================
# BASE MODEL ADMIN (SHARED ASSETS)
# ==============================================================================

class QuestionSetterBaseAdmin(admin.ModelAdmin):
    """Base Admin providing ergonomic CSS for badges, textareas, and guidance cards."""
    class Media:
        css = {
            "all": ("css/admin_question_setter.css",)
        }


class MockTestManagementAdmin(QuestionSetterBaseAdmin):
    """Base Admin restricting Mock Test & Question management to superusers or authorized SubAdmins."""
    def has_module_permission(self, request):
        return can_manage_mock_tests(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_mock_tests(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_mock_tests(request.user)

    def has_add_permission(self, request):
        return can_manage_mock_tests(request.user)

    def has_delete_permission(self, request, obj=None):
        return can_manage_mock_tests(request.user)


class ScopedCandidateDataAdmin(QuestionSetterBaseAdmin):
    """Restricts candidate data (attempts, evaluations, answers) to the subadmin's branch."""
    def has_module_permission(self, request):
        if is_subadmin(request.user):
            return True
        return super().has_module_permission(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            if branch:
                if hasattr(self.model, "candidate"):
                    return qs.filter(candidate__candidate_profile__Mock_from=branch)
                elif hasattr(self.model, "attempt"):
                    return qs.filter(attempt__candidate__candidate_profile__Mock_from=branch)
        return qs

    def has_view_permission(self, request, obj=None):
        if is_subadmin(request.user):
            if obj is not None:
                branch = get_subadmin_mock_from(request.user)
                cand = getattr(obj, "candidate", None) or getattr(getattr(obj, "attempt", None), "candidate", None)
                cand_branch = getattr(getattr(cand, "candidate_profile", None), "Mock_from", "")
                if branch and cand_branch != branch:
                    return False
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            cand = getattr(obj, "candidate", None) or getattr(getattr(obj, "attempt", None), "candidate", None)
            cand_branch = getattr(getattr(cand, "candidate_profile", None), "Mock_from", "")
            if branch and cand_branch != branch:
                return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            cand = getattr(obj, "candidate", None) or getattr(getattr(obj, "attempt", None), "candidate", None)
            cand_branch = getattr(getattr(cand, "candidate_profile", None), "Mock_from", "")
            if branch and cand_branch != branch:
                return False
        return super().has_delete_permission(request, obj)


# ==============================================================================
# 1. FORMS & FORMSETS
# ==============================================================================

class IELTSMockTestAdminForm(forms.ModelForm):
    class Meta:
        model = IELTSMockTest
        fields = "__all__"
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "e.g. Cambridge IELTS 18 - Academic Test 1",
                "style": "width: 100%; max-width: 600px;",
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Optional summary or operational notes about this mock test.",
                "style": "width: 100%; max-width: 800px; box-sizing: border-box;",
            }),
        }


class ExamModuleAdminForm(forms.ModelForm):
    class Meta:
        model = ExamModule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "audio_file" in self.fields:
            self.fields["audio_file"].help_text = (
                "Continuous master audio for the entire Listening module (covers Parts 1–4 and all questions). "
                "If uploaded, this single file plays continuously across all parts. "
                "If left empty, you can upload individual audio files for each section/part below."
            )
        if "listening_html_file" in self.fields:
            self.fields["listening_html_file"].help_text = (
                "Upload the complete HTML listening test for this module. "
                "It is used automatically when the module has no database sections."
            )
        if "module_file" in self.fields:
            self.fields["module_file"].help_text = (
                "Optional file for Listening, Reading, or Writing. "
                "Any extension is accepted and browser-supported formats are displayed to candidates."
            )
        if "duration_minutes" in self.fields:
            self.fields["duration_minutes"].help_text = (
                "Standard module durations: Reading = 60 min, Listening = 30 min (or 40 min), Writing = 60 min."
            )


class ExamSectionInlineFormSet(BaseInlineFormSet):
    """Ensure automated sequential ordering when adding multiple sections."""
    def clean(self):
        super().clean()
        used_orders = set(self.queryset.values_list("order", flat=True))
        next_order = max(used_orders, default=0) + 1
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            instance = form.instance
            if instance._state.adding and instance.order in used_orders:
                instance.order = next_order
                form.cleaned_data["order"] = next_order
                used_orders.add(next_order)
                next_order += 1
            else:
                used_orders.add(instance.order)


class ExamSectionAdminForm(forms.ModelForm):
    class Meta:
        model = ExamSection
        fields = "__all__"
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "e.g. Passage 1: The Secret Life of Bees  OR  Part 1: Accommodation Inquiry",
                "style": "width: 100%; max-width: 650px;",
            }),
            "passage": forms.Textarea(attrs={
                "rows": 16,
                "class": "passage-textarea",
                "placeholder": "Paste or write the full reading passage, text, or essay prompt here...",
            }),
            "passage_instructions": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": 'Introductory text shown directly above the passage (e.g. "You should spend about 20 minutes on Questions 1–13...")',
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "instructions": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": 'Instructions shown above the questions panel on the right (e.g. "Questions 1–6: Choose the correct letter, A, B, C or D.")',
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instructions"].label = "Question Pane Instructions"
        self.fields["instructions"].help_text = "Instructions shown above the question items in the right-hand panel."
        self.fields["passage_instructions"].label = "Passage Header Note"
        if "audio_file" in self.fields:
            self.fields["audio_file"].help_text = (
                "Individual audio for this specific part/section. "
                "Only used if the parent module does not have a continuous master audio file."
            )

    def clean_order(self):
        order = self.cleaned_data["order"]
        module = self.cleaned_data.get("module")
        if (
            module
            and self.instance._state.adding
            and ExamSection.objects.filter(module=module, order=order).exists()
        ):
            return (
                ExamSection.objects.filter(module=module)
                .order_by("-order")
                .values_list("order", flat=True)
                .first()
                + 1
            )
        return order


class QuestionInlineFormSet(BaseInlineFormSet):
    """Ensure automated sequential ordering when adding multiple questions."""
    def clean(self):
        super().clean()
        used_orders = set(self.queryset.values_list("order", flat=True))
        next_order = max(used_orders, default=0) + 1
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            instance = form.instance
            if instance._state.adding and instance.order in used_orders:
                instance.order = next_order
                form.cleaned_data["order"] = next_order
                used_orders.add(next_order)
                next_order += 1
            else:
                used_orders.add(instance.order)


def parse_option_line(line):
    """
    Parses a single line of an option string.
    Supports formats like:
      - 'A. Option text'
      - 'B) Option text *'
      - 'C. Option text [correct]'
      - 'TRUE) TRUE [correct]'
      - 'NOT GIVEN) NOT GIVEN'
      - 'iv. Matching heading *'
      - 'Key | Text | 1'
    """
    line = (line or "").strip()
    if not line:
        return None
    is_correct = False
    if re.search(r"\[\s*correct\s*\]|\(\s*correct\s*\)", line, re.IGNORECASE):
        is_correct = True
        line = re.sub(r"\[\s*correct\s*\]|\(\s*correct\s*\)", "", line, flags=re.IGNORECASE).strip()
    if line.endswith("*"):
        is_correct = True
        line = line[:-1].strip()

    if "|" in line:
        parts = [p.strip() for p in line.split("|")]
        key = parts[0]
        text = parts[1] if len(parts) > 1 else parts[0]
        if len(parts) > 2 and parts[2].lower() in ("1", "true", "yes", "correct"):
            is_correct = True
    else:
        m = re.match(r"^([A-Za-z0-9\s_\-]+?)[\)\.\:\-]\s*(.*)$", line)
        if m:
            key = m.group(1).strip()
            text = m.group(2).strip()
        else:
            key = ""
            text = line.strip()

    return {
        "key": key,
        "text": text,
        "is_correct": is_correct,
    }


def sync_quick_options(question, quick_text):
    """
    Synchronizes multiline or JSON quick options into QuestionOption database records
    and keeps question.correct_answer in sync.
    """
    if not question or not question.pk:
        return []

    import json
    parsed_items = []
    correct_keys = []
    raw = (quick_text or "").strip()

    if raw.startswith("[") and raw.endswith("]"):
        try:
            data = json.loads(raw)
            for idx, item in enumerate(data, start=1):
                key = str(item.get("key") or (chr(ord("A") + idx - 1) if idx <= 26 else str(idx))).strip()
                text = str(item.get("text") or key).strip()
                is_cor = bool(item.get("is_correct"))
                if is_cor:
                    correct_keys.append(key)
                parsed_items.append({
                    "key": key,
                    "text": text,
                    "order": int(item.get("order") or idx),
                    "is_correct": is_cor,
                })
        except Exception:
            pass

    if not parsed_items:
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        for idx, line in enumerate(lines, start=1):
            parsed = parse_option_line(line)
            if not parsed:
                continue
            key = parsed["key"] or (chr(ord("A") + idx - 1) if idx <= 26 else str(idx))
            text = parsed["text"] or key
            is_cor = parsed["is_correct"]
            if is_cor:
                correct_keys.append(key)
            parsed_items.append({
                "key": key,
                "text": text,
                "order": idx,
                "is_correct": is_cor,
            })

    kept_keys = [item["key"] for item in parsed_items]
    if kept_keys:
        question.options.exclude(option_key__in=kept_keys).delete()
    else:
        question.options.all().delete()

    saved_options = []
    for item in parsed_items:
        opt, _ = QuestionOption.objects.update_or_create(
            question=question,
            option_key=item["key"],
            defaults={
                "option_text": item["text"],
                "order": item["order"],
                "is_correct": item["is_correct"],
            },
        )
        saved_options.append(opt)

    if correct_keys:
        question.correct_answer = ", ".join(correct_keys)
        question.save(update_fields=["correct_answer"])

    return saved_options


class QuestionOptionsTabularWidget(forms.Widget):
    """
    Renders the exact TabularInline table for options directly inside the Section Question inline,
    so non-technical and technical users have the exact same familiar tabular interface as the Question page.
    """
    def render(self, name, value, attrs=None, renderer=None):
        raw_value = value or ""
        raw_str = str(raw_value).strip()
        parsed_rows = []

        if raw_str.startswith("[") and raw_str.endswith("]"):
            try:
                import json
                data = json.loads(raw_str)
                for idx, item in enumerate(data, start=1):
                    parsed_rows.append({
                        "order": int(item.get("order") or idx),
                        "key": str(item.get("key") or (chr(ord("A") + idx - 1) if idx <= 26 else str(idx))),
                        "text": str(item.get("text") or ""),
                        "is_correct": bool(item.get("is_correct")),
                    })
            except Exception:
                pass

        if not parsed_rows:
            lines = [l.strip() for l in raw_str.splitlines() if l.strip()]
            for idx, line in enumerate(lines, start=1):
                p = parse_option_line(line)
                if p:
                    parsed_rows.append({
                        "order": idx,
                        "key": p["key"] or (chr(ord("A") + idx - 1) if idx <= 26 else str(idx)),
                        "text": p["text"],
                        "is_correct": p["is_correct"],
                    })

        if not parsed_rows:
            parsed_rows = [
                {"order": 1, "key": "A", "text": "", "is_correct": False},
                {"order": 2, "key": "B", "text": "", "is_correct": False},
                {"order": 3, "key": "C", "text": "", "is_correct": False},
                {"order": 4, "key": "D", "text": "", "is_correct": False},
            ]

        rows_html = []
        for r in parsed_rows:
            checked_attr = 'checked="checked"' if r["is_correct"] else ""
            escaped_text = html.escape(r["text"])
            escaped_key = html.escape(r["key"])
            rows_html.append(f"""
              <tr class="mcq-table-row" style="border-bottom: 1px solid rgba(255,255,255,0.08);">
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="number" class="mcq-field-order" value="{r['order']}" min="1" max="99" style="width: 50px; text-align: center; padding: 6px 4px; border-radius: 4px; font-weight: 600; background: #1e293b; color: #f8fafc; border: 1px solid #475569;" />
                </td>
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="text" class="mcq-field-key" value="{escaped_key}" placeholder="e.g. A" style="width: 100px; text-align: center; padding: 6px 8px; font-weight: 700; text-transform: uppercase; border-radius: 4px; background: #1e293b; color: #38bdf8; border: 1px solid #475569;" />
                </td>
                <td style="padding: 8px 6px;">
                  <input type="text" class="mcq-field-text" value="{escaped_text}" placeholder="Enter choice text..." style="width: 100%; box-sizing: border-box; padding: 7px 10px; border-radius: 4px; background: #1e293b; color: #ffffff; border: 1px solid #475569;" />
                </td>
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="checkbox" class="mcq-field-correct" {checked_attr} style="width: 18px; height: 18px; cursor: pointer; accent-color: #22c55e;" title="Mark as correct answer" />
                </td>
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="checkbox" class="mcq-field-delete" style="width: 18px; height: 18px; cursor: pointer; accent-color: #ef4444;" title="Delete this option" />
                </td>
              </tr>
            """)

        all_rows_str = "\n".join(rows_html)
        escaped_raw = html.escape(raw_value)

        return mark_safe(f"""
        <div class="mcq-tabular-wrapper" style="margin: 8px 0 16px 0; border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; overflow: hidden; background: #182234; box-shadow: 0 2px 8px rgba(0,0,0,0.25);">
          <!-- Header Bar styled exactly like Django TabularInline -->
          <div style="background: #1e3a5f; color: #ffffff; padding: 10px 14px; font-weight: 700; font-size: 13px; letter-spacing: 0.5px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <span>⬇ OPTIONS / CHOICES (MCQ · MATCHING · MULTI-SELECT · TFNG · YNNG)</span>
            <div style="display: flex; gap: 6px; align-items: center;">
              <button type="button" class="btn-mcq-preset" data-preset="abcd" style="background: #0f172a; color: #cbd5e1; border: 1px solid #475569; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer;">⚡ A, B, C, D</button>
              <button type="button" class="btn-mcq-preset" data-preset="tfng" style="background: #0f172a; color: #cbd5e1; border: 1px solid #475569; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer;">⚡ TRUE / FALSE / NOT GIVEN</button>
              <button type="button" class="btn-mcq-preset" data-preset="ynng" style="background: #0f172a; color: #cbd5e1; border: 1px solid #475569; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer;">⚡ YES / NO / NOT GIVEN</button>
            </div>
          </div>

          <table class="mcq-options-table" style="width: 100%; border-collapse: collapse; background: #0f172a;">
            <thead>
              <tr style="background: #131d2e; border-bottom: 1px solid rgba(255,255,255,0.1);">
                <th style="padding: 8px 10px; font-size: 11px; text-transform: uppercase; color: #94a3b8; width: 70px; text-align: center;">ORDER</th>
                <th style="padding: 8px 10px; font-size: 11px; text-transform: uppercase; color: #94a3b8; width: 120px; text-align: center;">OPTION KEY</th>
                <th style="padding: 8px 10px; font-size: 11px; text-transform: uppercase; color: #94a3b8; text-align: left;">OPTION TEXT</th>
                <th style="padding: 8px 10px; font-size: 11px; text-transform: uppercase; color: #94a3b8; width: 110px; text-align: center;">IS CORRECT</th>
                <th style="padding: 8px 10px; font-size: 11px; text-transform: uppercase; color: #94a3b8; width: 80px; text-align: center;">DELETE?</th>
              </tr>
            </thead>
            <tbody class="mcq-table-tbody">
              {all_rows_str}
            </tbody>
          </table>

          <div style="padding: 10px 14px; background: #131d2e; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <a href="javascript:void(0)" class="btn-mcq-add-row" style="color: #22c55e; font-weight: 700; font-size: 13px; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
              + Add another Option / Choice
            </a>
            <span style="font-size: 11.5px; color: #64748b;">
              Tick <b>IS CORRECT</b> for the right answer. Saved automatically into Question Options.
            </span>
          </div>

          <!-- Hidden raw textarea for standard Django form submission -->
          <textarea name="{name}" class="mcq-raw-textarea" style="display: none;">{escaped_raw}</textarea>
        </div>
        """)


class QuestionAdminForm(forms.ModelForm):
    quick_options = forms.CharField(
        label="⬇ Options / Choices",
        required=False,
        widget=QuestionOptionsTabularWidget(),
        help_text="Edit choices directly in the table above. Options are automatically saved into Question Options.",
    )

    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "question_text": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": (
                    "Enter the question text or prompt statement.\n"
                    "★ FOR FILL-IN-THE-BLANKS: Type three underscores (___) where candidate types their answer.\n"
                    "Example: The conference registration fee is ___ dollars."
                ),
                "style": "width: 100%; max-width: 850px; font-size: 13.5px; box-sizing: border-box;",
            }),
            "question_instructions": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": (
                    "Optional instructions shown directly above this question group.\n"
                    "Example: Questions 1–5: Complete the notes below. Write NO MORE THAN TWO WORDS AND/OR A NUMBER."
                ),
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "correct_answer": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": (
                    "Canonical correct answer key(s).\n"
                    "• Fill in the blanks: ans1 / alt1 ;;; ans2 / alt2\n"
                    "• Multiple Choice: A (or B, C, D)\n"
                    "• Multi-Select: A, C\n"
                    "• True/False/Not Given: TRUE or FALSE or NOT GIVEN\n"
                    "• Writing Task: Leave blank (evaluated manually)"
                ),
                "style": "width: 100%; max-width: 850px; font-family: Consolas, monospace; font-size: 13px; box-sizing: border-box;",
            }),
            "table_content": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Optional HTML or Markdown table for structured question tables.",
                "style": "width: 100%; max-width: 850px; font-family: monospace; font-size: 12.5px; box-sizing: border-box;",
            }),
            "explanation": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": (
                    "Explanation shown to candidates on their test result page.\n"
                    "• Single question: Enter the explanation text.\n"
                    "• Multiple blanks in one question: Wrap each blank's explanation in double quotes \"...\" \"...\" or separate with ;;; or prefix with Q{num} headers (e.g. Q23: ... Q24: ...)."
                ),
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "passage_excerpt": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Exact passage excerpt/sentence to highlight in the passage on review.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "what_question_asks": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Key requirements or keywords of what the question asks.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "what_passage_says": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "What the passage states related to this question.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "why_answer": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Detailed justification of why this answer is correct.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
            "paraphrase": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": "e.g. question: 'unique to the island' -> passage: 'six are found only there'",
                "style": "width: 100%; max-width: 850px; font-family: monospace; box-sizing: border-box;",
            }),
            "tip": forms.Textarea(attrs={
                "rows": 2,
                "placeholder": "Exam tip or trap warning for this question.",
                "style": "width: 100%; max-width: 850px; box-sizing: border-box;",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            opts = list(self.instance.options.order_by("order", "id"))
            if opts and not self.initial.get("quick_options"):
                lines = [
                    f"{o.option_key}) {o.option_text}{' [correct]' if o.is_correct else ''}"
                    for o in opts
                ]
                self.initial["quick_options"] = "\n".join(lines)

    def save(self, commit=True):
        instance = super().save(commit=commit)

        def sync_options():
            if not instance.pk:
                return
            cleaned = getattr(self, "cleaned_data", {})
            quick = (cleaned.get("quick_options") or "").strip()
            if quick:
                sync_quick_options(instance, quick)

        if commit:
            sync_options()
        else:
            old_save_m2m = getattr(self, "save_m2m", None)
            def new_save_m2m():
                if old_save_m2m:
                    old_save_m2m()
                sync_options()
            self.save_m2m = new_save_m2m

        return instance


# Question types that use selectable options (MCQ, matching, multi-select)
MCQ_OPTION_TYPES = (
    Question.QuestionType.MCQ,
    Question.QuestionType.MATCHING,
    Question.QuestionType.MATCHING_INFORMATION,
    Question.QuestionType.MULTI_SELECT,
    Question.QuestionType.TRUE_FALSE_NOT_GIVEN,
    Question.QuestionType.YES_NO_NOT_GIVEN,
)


# ==============================================================================
# 2. INLINES
# ==============================================================================

class ExamModuleInline(admin.TabularInline):
    model = ExamModule
    extra = 0
    show_change_link = True
    fields = (
        "module_type",
        "duration_minutes",
        "sections_summary",
        "is_active",
        "quick_actions",
    )
    readonly_fields = ("sections_summary", "quick_actions")

    @admin.display(description="Sections & Content")
    def sections_summary(self, obj):
        if not obj.pk:
            return "Save first"
        s_count = obj.sections.count()
        q_count = sum(s.questions.count() for s in obj.sections.all())
        url = reverse("admin:bcl_examsection_changelist") + f"?module__id__exact={obj.pk}"
        return format_html(
            '<a class="admin-action-link" href="{}" style="font-weight:600;">{} sections ({} Qs) ➔</a>',
            url,
            s_count,
            q_count,
        )

    @admin.display(description="Direct Action")
    def quick_actions(self, obj):
        if not obj.pk:
            return "Save first"
        change_url = reverse("admin:bcl_exammodule_change", args=[obj.pk])
        add_sec_url = reverse("admin:bcl_examsection_add") + f"?module={obj.pk}"
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(obj.module_type, "📝")
        return format_html(
            '<div style="display:flex;gap:6px;align-items:center;">'
            '<a class="button" href="{}" style="padding:4px 10px;background:#4f46e5;color:white;border-radius:5px;text-decoration:none;font-weight:600;font-size:12px;">'
            '{} Edit {} ➔</a>'
            '<a class="button" href="{}" style="padding:4px 10px;background:#059669;color:white;border-radius:5px;text-decoration:none;font-weight:600;font-size:12px;">'
            '➕ Add Section</a>'
            '</div>',
            change_url,
            icon,
            obj.get_module_type_display(),
            add_sec_url,
        )


class ExamSectionInline(admin.StackedInline):
    model = ExamSection
    form = ExamSectionAdminForm
    formset = ExamSectionInlineFormSet
    extra = 0
    show_change_link = True
    classes = ("collapse",)
    fields = (
        "order",
        "title",
        "quick_section_editor",
        "instructions",
        "passage_instructions",
        "passage",
        "audio_file",
        "image",
    )
    readonly_fields = ("quick_section_editor",)

    @admin.display(description="Question Setter Studio")
    def quick_section_editor(self, obj):
        if not obj or not obj.pk:
            return "Save section first to launch full question editor."
        url = reverse("admin:bcl_examsection_change", args=[obj.pk])
        q_count = obj.questions.count()
        return format_html(
            '<div style="margin: 6px 0;">'
            '<a class="button" href="{}" style="padding:6px 14px;background:#0284c7;color:white;border-radius:6px;text-decoration:none;font-weight:700;font-size:13px;">'
            '📝 Open Section Editor (Passage + Questions + Options — {} Qs) ➔</a>'
            '</div>',
            url,
            q_count,
        )


class QuestionOptionInlineForQuestion(admin.TabularInline):
    """Options inline used inside the standalone Question admin page."""
    model = QuestionOption
    extra = 4
    fields = ("order", "option_key", "option_text", "is_correct")
    verbose_name = "Option / Choice"
    verbose_name_plural = "⬇ Options / Choices  (MCQ · Matching · Multi-Select · TFNG · YNNG)"
    formfield_overrides = {
        models.CharField: {"widget": forms.TextInput(attrs={"size": "6"})},
    }

    def get_extra(self, request, obj=None, **kwargs):
        """Pre-populate 4 rows for new MCQ questions; 0 for existing that already have options."""
        if obj and obj.pk and obj.options.exists():
            return 1
        return 4


# Pre-built A/B/C/D option form for MCQ questions created from ExamSection inline
class MCQOptionInlineForSection(admin.TabularInline):
    """Lightweight options inline shown when editing a Question directly (not nested)."""
    model = QuestionOption
    extra = 4
    max_num = 8
    fields = ("order", "option_key", "option_text", "is_correct")
    verbose_name = "MCQ Option"
    verbose_name_plural = "⬇ MCQ / Matching Options  — fill in A, B, C, D and tick the correct one"
    formfield_overrides = {
        models.CharField: {"widget": forms.TextInput(attrs={"size": "6"})},
    }


# Keep old name as alias so nothing else breaks
QuestionOptionInline = QuestionOptionInlineForQuestion


class QuestionInline(admin.StackedInline):
    model = Question
    form = QuestionAdminForm
    formset = QuestionInlineFormSet
    extra = 0
    show_change_link = True
    classes = ("collapse",)
    fieldsets = (
        (
            "1. Question Details & Prompt",
            {
                "fields": (
                    ("order", "question_type", "marks"),
                    "question_instructions",
                    "question_text",
                ),
            },
        ),
        (
            "2. Options / Choices (MCQ · Matching · Multi-Select · TFNG · YNNG)",
            {
                "fields": ("quick_options",),
                "description": (
                    "Options / Choices: Fill in the options table below (Order, Option Key, Option Text, and tick Is Correct). "
                    "Options are automatically saved directly into Question Options!"
                ),
            },
        ),
        (
            "3. Answer Key, Explanation & Highlights",
            {
                "fields": (
                    "correct_answer",
                    "explanation",
                    ("answer_location", "passage_excerpt"),
                ),
                "description": (
                    "• Correct Answer: Enter A, B, C, D, TRUE/FALSE, or word for fill-in-blanks.\n"
                    "• Explanation: Detailed reason shown on candidate's result page.\n"
                    "• Answer Location: e.g. 'Paragraph 2, Line 4'.\n"
                    "• Passage Excerpt: Exact text in the passage to highlight on candidate result page."
                ),
            },
        ),
        (
            "4. Additional Explanations & Diagnostic Aids (Optional)",
            {
                "fields": (
                    ("what_question_asks", "what_passage_says"),
                    ("why_answer", "paraphrase"),
                    "tip",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "5. Diagrams, Images & Tables (Optional)",
            {
                "fields": (
                    ("image", "table_content"),
                ),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ()

    @admin.display(description="MCQ Options (saved in DB)")
    def options_preview(self, obj):
        """Show existing MCQ options inline so setter can verify without leaving ExamSection."""
        if not obj or not obj.pk:
            return format_html(
                '<span style="color:#64748b;font-size:12px;">'
                "Enter Option A, B, C, D above and click <b>Save</b> to store options."
                "</span>"
            )
        if obj.question_type not in MCQ_OPTION_TYPES:
            return format_html(
                '<span style="color:#64748b;font-size:12px;">'
                "No options needed for {} questions."
                "</span>",
                obj.get_question_type_display(),
            )
        opts = list(obj.options.order_by("order", "option_key"))
        if not opts:
            return format_html(
                '<span style="color:#d97706;font-weight:600;">'
                "Type Option A, B, C, D in the boxes above and click Save!"
                "</span>"
            )
        rows = []
        for o in opts:
            badge_color = "#16a34a" if o.is_correct else "#64748b"
            tick = " ✓" if o.is_correct else ""
            rows.append(
                format_html(
                    '<span style="display:inline-block;margin:2px 6px 2px 0;padding:2px 10px;'
                    'border-radius:4px;background:#f1f5f9;border:1px solid #e2e8f0;'
                    'font-size:12.5px;color:{};font-weight:600;">'
                    "{}: {}{}"
                    "</span>",
                    badge_color,
                    o.option_key,
                    o.option_text or "(no text)",
                    tick,
                )
            )
        return mark_safe("".join(str(r) for r in rows))


# ==============================================================================
# 3. IELTS MOCK TEST ADMIN
# ==============================================================================

@admin.register(IELTSMockTest)
class IELTSMockTestAdmin(MockTestManagementAdmin):
    form = IELTSMockTestAdminForm

    list_display = (
        "test_number",
        "title",
        "modules_overview",
        "total_questions_count",
        "is_published",
        "created_at",
    )
    list_display_links = ("test_number", "title")
    list_filter = (
        "is_published",
        "created_at",
    )
    search_fields = (
        "title",
        "description",
    )
    ordering = ("test_number",)
    list_editable = ("is_published",)
    inlines = [ExamModuleInline]

    def get_deleted_objects(self, objs, request):
        """Allow this admin to remove historical attempts with their mock test."""
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request
        )
        return deleted_objects, model_count, set(), []

    def delete_model(self, request, obj):
        with transaction.atomic():
            FullMockAttempt.objects.filter(mock_test=obj).delete()
            CandidateAttempt.objects.filter(module__mock_test=obj).delete()
            obj.delete()

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset:
                self.delete_model(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Automatically initialize the 3 standard IELTS modules if they don't exist yet
        for m_type, dur in [
            (ExamModule.ModuleType.LISTENING, 40),
            (ExamModule.ModuleType.READING, 60),
            (ExamModule.ModuleType.WRITING, 60),
        ]:
            ExamModule.objects.get_or_create(
                mock_test=obj,
                module_type=m_type,
                defaults={"duration_minutes": dur, "is_active": True}
            )

    fieldsets = (
        (
            "Mock Test Identification",
            {
                "fields": (
                    "test_number",
                    "title",
                    "is_published",
                ),
                "description": "General identification for the full IELTS test.",
            },
        ),
        (
            "Overview & Description",
            {
                "fields": ("description",),
                "description": "Optional administrative summary or candidate-facing description.",
            },
        ),
    )

    @admin.display(description="Modules Status")
    def modules_overview(self, obj):
        modules = list(obj.modules.all())
        if not modules:
            return format_html('<span class="admin-badge badge-draft">No modules</span>')
        badges = []
        for m in sorted(modules, key=lambda x: {"listening": 1, "reading": 2, "writing": 3}.get(x.module_type, 99)):
            m_type = m.get_module_type_display()
            sec_count = m.sections.count()
            css_class = f"badge-{m.module_type}"
            change_url = reverse("admin:bcl_exammodule_change", args=[m.pk])
            badges.append(
                format_html(
                    '<a href="{}" title="Edit {} Module" style="text-decoration:none;">'
                    '<span class="admin-badge {}">{} ({} parts)</span></a>',
                    change_url,
                    m_type,
                    css_class,
                    m_type,
                    sec_count,
                )
            )
        return mark_safe(" ".join(badges))

    @admin.display(description="Total Questions")
    def total_questions_count(self, obj):
        count = Question.objects.filter(section__module__mock_test=obj).count()
        return format_html("<b>{}</b> Qs", count)

    @admin.display(description="Publication")
    def status_badge(self, obj):
        if obj.is_published:
            return format_html('<span class="admin-badge badge-published">● Published</span>')
        return format_html('<span class="admin-badge badge-draft">○ Draft</span>')


# ==============================================================================
# 4. EXAM MODULE ADMIN
# ==============================================================================

@admin.register(ExamModule)
class ExamModuleAdmin(MockTestManagementAdmin):
    form = ExamModuleAdminForm

    list_display = (
        "id",
        "mock_test_link",
        "module_type_badge",
        "duration_minutes",
        "sections_link",
        "audio_status",
        "is_active",
    )
    list_display_links = ("id", "module_type_badge")
    list_filter = (
        "mock_test",
        "module_type",
        "is_active",
    )
    search_fields = (
        "mock_test__title",
        "instructions",
        "module_type",
    )
    autocomplete_fields = ["mock_test"]
    list_select_related = ("mock_test",)
    inlines = [ExamSectionInline]

    fieldsets = (
        (
            "Module Setup",
            {
                "fields": (
                    "mock_test",
                    "module_type",
                    "duration_minutes",
                    "is_active",
                ),
            },
        ),
        (
            "Module File",
            {
                "fields": ("module_file",),
                "description": (
                    "Optional file for any module type. Any extension is accepted. "
                    "HTML, PDF, images, text, audio, and other browser-supported formats "
                    "are displayed automatically; unsupported formats remain downloadable."
                ),
            },
        ),
        (
            "Module Instructions",
            {
                "fields": ("instructions",),
                "classes": ("collapse",),
                "description": "Optional instructions shown at module start.",
            },
        ),
    )

    @admin.display(description="Mock Test")
    def mock_test_link(self, obj):
        url = reverse("admin:bcl_ieltsmocktest_change", args=[obj.mock_test.pk])
        return format_html('<a href="{}"><b>{}</b></a>', url, obj.mock_test.title)

    @admin.display(description="Module Type")
    def module_type_badge(self, obj):
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(obj.module_type, "")
        return format_html(
            '<span class="admin-badge badge-{}">{} {}</span>',
            obj.module_type,
            icon,
            obj.get_module_type_display(),
        )

    @admin.display(description="Sections & Parts")
    def sections_link(self, obj):
        count = obj.sections.count()
        q_count = sum(s.questions.count() for s in obj.sections.all())
        url = reverse("admin:bcl_examsection_changelist") + f"?module__id__exact={obj.pk}"
        return format_html(
            '<a class="admin-action-link" href="{}"><b>{} sections</b> ({} Qs) ➔</a>',
            url,
            count,
            q_count,
        )

    @admin.display(description="Audio Mode")
    def audio_status(self, obj):
        if obj.module_type != "listening":
            return "—"
        if obj.audio_file:
            return format_html('<span class="admin-badge badge-published">🎵 Master Audio OK</span>')
        return format_html('<span class="admin-badge badge-draft">Part-by-part audio</span>')


# ==============================================================================
# 5. EXAM SECTION ADMIN
# ==============================================================================

@admin.register(ExamSection)
class ExamSectionAdmin(MockTestManagementAdmin):
    form = ExamSectionAdminForm

    list_display = (
        "order",
        "title",
        "mock_test_title",
        "module_badge",
        "questions_link",
        "has_passage_badge",
        "has_audio_badge",
        "has_image_badge",
    )
    list_display_links = ("order", "title")
    list_filter = (
        "module__mock_test",
        "module__module_type",
    )
    search_fields = (
        "title",
        "passage",
        "instructions",
        "passage_instructions",
        "module__mock_test__title",
    )
    autocomplete_fields = ["module"]
    list_select_related = (
        "module",
        "module__mock_test",
    )
    inlines = [QuestionInline]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        module_id = request.GET.get("module")
        if module_id:
            try:
                mod = ExamModule.objects.get(pk=module_id)
                initial["module"] = mod
                max_order = ExamSection.objects.filter(module=mod).aggregate(m=models.Max("order"))["m"] or 0
                initial["order"] = max_order + 1
            except (ExamModule.DoesNotExist, ValueError):
                pass
        return initial

    fieldsets = (
        (
            "Section Placement",
            {
                "fields": (
                    "module",
                    "order",
                    "title",
                ),
                "description": "Select the parent module and set the sequential order (e.g. Part 1, Part 2, Passage 1).",
            },
        ),
        (
            "Reading Passage & Visual Context (Left-Side Screen)",
            {
                "fields": (
                    "passage_instructions",
                    "passage",
                    "image",
                ),
                "description": (
                    "Content displayed in the left-hand panel during the exam. "
                    "For Reading, paste the full passage text here. "
                    "For Writing Task 1, upload the chart/diagram in Image and write the task prompt in Passage."
                ),
            },
        ),
        (
            "Questions Header (Right-Side Screen)",
            {
                "fields": ("instructions",),
                "description": "Instructions shown above questions in the right-hand panel (e.g. 'Questions 1–6: Choose True, False or Not Given').",
            },
        ),
        (
            "Section Audio (Listening Only)",
            {
                "fields": ("audio_file",),
                "description": (
                    "Upload audio specific to this section if the parent Listening module "
                    "does not have a continuous master audio recording."
                ),
            },
        ),
    )

    @admin.display(description="Mock Test")
    def mock_test_title(self, obj):
        url = reverse("admin:bcl_ieltsmocktest_change", args=[obj.module.mock_test.pk])
        return format_html('<a href="{}">{}</a>', url, obj.module.mock_test.title)

    @admin.display(description="Module")
    def module_badge(self, obj):
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(obj.module.module_type, "")
        return format_html(
            '<span class="admin-badge badge-{}">{} {}</span>',
            obj.module.module_type,
            icon,
            obj.module.get_module_type_display(),
        )

    @admin.display(description="Questions")
    def questions_link(self, obj):
        count = obj.questions.count()
        url = reverse("admin:bcl_question_changelist") + f"?section__id__exact={obj.pk}"
        return format_html(
            '<a class="admin-action-link" href="{}"><b>{} questions</b> ➔</a>',
            url,
            count,
        )

    @admin.display(description="Passage")
    def has_passage_badge(self, obj):
        if obj.passage:
            words = len(obj.passage.split())
            return format_html('<span class="admin-badge badge-reading">✓ {} words</span>', words)
        return format_html('<span class="admin-badge badge-draft">—</span>')

    @admin.display(description="Audio")
    def has_audio_badge(self, obj):
        if obj.audio_file:
            return format_html('<span class="admin-badge badge-listening">🎵 Audio</span>')
        return "—"

    @admin.display(description="Image")
    def has_image_badge(self, obj):
        if obj.image:
            return format_html('<span class="admin-badge badge-neutral">🖼 Image</span>')
        return "—"


# ==============================================================================
# 6. QUESTION ADMIN
# ==============================================================================

@admin.register(Question)
class QuestionAdmin(MockTestManagementAdmin):
    form = QuestionAdminForm

    list_display = (
        "order",
        "mock_test_title",
        "module_badge",
        "section_link",
        "question_type_badge",
        "short_question",
        "options_summary",
        "correct_answer_preview",
        "marks",
    )
    list_display_links = ("order", "short_question")
    list_filter = (
        "section__module__mock_test",
        "section__module__module_type",
        "question_type",
        "section",
    )
    search_fields = (
        "question_text",
        "question_instructions",
        "correct_answer",
        "explanation",
        "section__title",
        "section__module__mock_test__title",
    )
    autocomplete_fields = ["section"]
    list_select_related = (
        "section",
        "section__module",
        "section__module__mock_test",
    )
    inlines = [QuestionOptionInline]

    fieldsets = (
        (
            "1. Question Hierarchy & Type",
            {
                "fields": (
                    "section",
                    "order",
                    "question_type",
                    "marks",
                    "answer_count",
                ),
                "description": "Select the section, the question number (order), type, and marks.",
            },
        ),
        (
            "2. Question Prompt & Instructions",
            {
                "fields": (
                    "question_instructions",
                    "question_text",
                ),
                "description": (
                    "Instructions: Optional note shown directly above this question item (e.g. 'Questions 1–5'). "
                    "Question Text: The prompt or sentence. For Fill in Blanks, type '___' (3 underscores) for each blank."
                ),
            },
        ),
        (
            "3. Media, Tables & Structured Diagrams (Optional)",
            {
                "fields": ("image", "table_content"),
                "classes": ("collapse",),
                "description": (
                    "Optional diagram/map image or HTML table structure. "
                    "Each question can include an image, table, or both."
                ),
            },
        ),
        (
            "4. Answer Key & Scoring Guide",
            {
                "fields": ("correct_answer", "explanation"),
                "description": (
                    "★ ANSWER KEY FORMATTING GUIDE:\n"
                    "• FILL IN THE BLANK: Separate multiple blanks with ';;;' and alternative acceptable answers with '/' or '||' (e.g. 9:00 am / 9 am ;;; 25 / twenty-five).\n"
                    "• MULTIPLE CHOICE: Enter the correct key (e.g. A or B) here, OR mark 'Is correct' in the Options below.\n"
                    "• MULTI-SELECT: Enter comma-separated keys (e.g. A, C).\n"
                    "• TRUE / FALSE / NOT GIVEN: Enter TRUE, FALSE, or NOT GIVEN.\n"
                    "• YES / NO / NOT GIVEN: Enter YES, NO, or NOT GIVEN.\n"
                    "• MATCHING / MATCHING INFO: Enter the matching option key (e.g. B or iv).\n"
                    "• WRITING / ESSAY: Leave blank (evaluated manually by staff examiner)."
                ),
            },
        ),
        (
            "5. Detailed Explanation & Passage Highlighting (Optional)",
            {
                "fields": (
                    "answer_location",
                    "passage_excerpt",
                    "what_question_asks",
                    "what_passage_says",
                    "why_answer",
                    "paraphrase",
                    "tip",
                ),
                "classes": ("collapse",),
                "description": (
                    "Structured explanation fields for interactive candidate review. "
                    "When provided, 'passage_excerpt' is automatically highlighted in the reading passage."
                ),
            },
        ),
    )

    @admin.display(description="Question Prompt")
    def short_question(self, obj):
        text = obj.question_text.strip().replace("\n", " ")
        if len(text) > 75:
            return text[:75] + "…"
        return text or "—"

    @admin.display(description="Mock Test")
    def mock_test_title(self, obj):
        return obj.section.module.mock_test.title

    @admin.display(description="Module")
    def module_badge(self, obj):
        m_type = obj.section.module.module_type
        icon = {"listening": "🎧", "reading": "📖", "writing": "✍️"}.get(m_type, "")
        return format_html(
            '<span class="admin-badge badge-{}">{} {}</span>',
            m_type,
            icon,
            obj.section.module.get_module_type_display(),
        )

    @admin.display(description="Section")
    def section_link(self, obj):
        url = reverse("admin:bcl_examsection_change", args=[obj.section.pk])
        return format_html('<a href="{}">{}</a>', url, obj.section.title)

    @admin.display(description="Type")
    def question_type_badge(self, obj):
        return format_html(
            '<span class="admin-badge badge-qtype">{}</span>',
            obj.get_question_type_display(),
        )

    @admin.display(description="Options")
    def options_summary(self, obj):
        opts = list(obj.options.all())
        if not opts:
            return "—"
        correct = [o.option_key for o in opts if o.is_correct]
        corr_text = f" (Correct: {', '.join(correct)})" if correct else ""
        return format_html('<span class="admin-badge badge-neutral">{} choices{}</span>', len(opts), corr_text)

    @admin.display(description="Answer Key")
    def correct_answer_preview(self, obj):
        if not obj.correct_answer:
            return format_html('<span style="color:#94a3b8;">Manual / None</span>')
        ans = obj.correct_answer.strip()
        if len(ans) > 40:
            ans = ans[:40] + "…"
        return format_html('<code class="code-preview">{}</code>', ans)


# ==============================================================================
# 7. QUESTION OPTION ADMIN
# ==============================================================================

@admin.register(QuestionOption)
class QuestionOptionAdmin(MockTestManagementAdmin):
    list_display = (
        "id",
        "mock_test_title",
        "question_link",
        "option_key",
        "option_text",
        "is_correct_badge",
        "order",
    )
    list_display_links = ("id", "option_key")
    list_filter = (
        "question__section__module__mock_test",
        "question__section__module__module_type",
        "is_correct",
    )
    search_fields = (
        "option_text",
        "option_key",
        "question__question_text",
    )
    autocomplete_fields = ["question"]
    list_select_related = (
        "question",
        "question__section",
        "question__section__module",
        "question__section__module__mock_test",
    )

    @admin.display(description="Mock Test")
    def mock_test_title(self, obj):
        return obj.question.section.module.mock_test.title

    @admin.display(description="Question")
    def question_link(self, obj):
        url = reverse("admin:bcl_question_change", args=[obj.question.pk])
        short = obj.question.question_text[:50]
        return format_html('<a href="{}">Q{}: {}</a>', url, obj.question.order, short)

    @admin.display(description="Correct?")
    def is_correct_badge(self, obj):
        if obj.is_correct:
            return format_html('<span class="admin-badge badge-published">✓ Correct</span>')
        return format_html('<span style="color:#94a3b8;">✗</span>')


# ==============================================================================
# 8. CANDIDATE ATTEMPTS & EVALUATION ADMIN (AUDIT & READONLY)
# ==============================================================================

@admin.register(FullMockAttempt)
class FullMockAttemptAdmin(ScopedCandidateDataAdmin):
    list_display = (
        "id",
        "candidate",
        "mock_test",
        "status",
        "current_step",
        "overall_band_score",
        "submitted_at",
        "view_result_btn",
        "export_pdf_btn",
        "export_docx_btn",
    )
    list_filter = (
        "status",
        "current_step",
        "started_at",
    )
    search_fields = (
        "candidate__username",
        "candidate__email",
        "mock_test__title",
    )
    readonly_fields = (
        "candidate",
        "mock_test",
        "status",
        "current_step",
        "reading_attempt",
        "listening_attempt",
        "writing_attempt",
        "overall_band_score",
        "started_at",
        "submitted_at",
        "result_actions_card",
    )
    list_select_related = (
        "candidate",
        "mock_test",
        "reading_attempt",
        "listening_attempt",
        "writing_attempt",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Result")
    def view_result_btn(self, obj):
        url = reverse("bcl:full_mock_result", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #0284c7; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">👁️ Result</a>',
            url,
        )

    @admin.display(description="PDF")
    def export_pdf_btn(self, obj):
        url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "pdf"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #dc2626; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📄 PDF</a>',
            url,
        )

    @admin.display(description="DOCX")
    def export_docx_btn(self, obj):
        url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "docx"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #2563eb; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📝 DOCX</a>',
            url,
        )

    @admin.display(description="Result Actions & Exports")
    def result_actions_card(self, obj):
        if not obj or not obj.pk:
            return "-"
        result_url = reverse("bcl:full_mock_result", args=[obj.pk])
        pdf_url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "pdf"])
        docx_url = reverse("bcl:export_full_mock_attempt", args=[obj.pk, "docx"])
        return format_html(
            '<div style="display: flex; gap: 10px; align-items: center; padding: 6px 0;">'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #0284c7; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">👁️ View Full Mock Result</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #dc2626; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📄 Export Official PDF</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #2563eb; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📝 Export Word DOCX</a>'
            '</div>',
            result_url, pdf_url, docx_url,
        )


@admin.register(CandidateAttempt)
class CandidateAttemptAdmin(ScopedCandidateDataAdmin):
    list_display = (
        "id",
        "candidate",
        "module",
        "full_mock",
        "status",
        "submitted_at",
        "raw_score",
        "band_score",
        "view_result_btn",
        "export_pdf_btn",
        "export_docx_btn",
    )
    list_filter = (
        "status",
        "module__module_type",
        "started_at",
    )
    search_fields = (
        "candidate__username",
        "candidate__email",
        "module__mock_test__title",
    )
    readonly_fields = (
        "candidate",
        "module",
        "full_mock",
        "status",
        "started_at",
        "expires_at",
        "submitted_at",
        "violation_count",
        "raw_score",
        "band_score",
        "result_actions_card",
        "listening_answers_breakdown",
    )
    list_select_related = (
        "candidate",
        "module",
        "module__mock_test",
        "full_mock",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Result")
    def view_result_btn(self, obj):
        url = reverse("bcl:exam_result", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #0284c7; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">👁️ Result</a>',
            url,
        )

    @admin.display(description="PDF")
    def export_pdf_btn(self, obj):
        url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "pdf"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #dc2626; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📄 PDF</a>',
            url,
        )

    @admin.display(description="DOCX")
    def export_docx_btn(self, obj):
        url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "docx"])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="padding: 2px 7px; font-size: 11px; background: #2563eb; color: white; border-radius: 4px; text-decoration: none; font-weight: 600;">📝 DOCX</a>',
            url,
        )

    @admin.display(description="Result Actions & Exports")
    def result_actions_card(self, obj):
        if not obj or not obj.pk:
            return "-"
        result_url = reverse("bcl:exam_result", args=[obj.pk])
        pdf_url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "pdf"])
        docx_url = reverse("bcl:export_candidate_attempt", args=[obj.pk, "docx"])
        review_button_html = ""
        if obj.module.module_type == ExamModule.ModuleType.WRITING:
            review_url = reverse("bcl:writing_review_detail", args=[obj.pk])
            review_button_html = f'<a class="button" href="{review_url}" target="_blank" style="padding: 6px 14px; background: #d97706; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">✍️ Writing Review</a>'

        return format_html(
            '<div style="display: flex; gap: 10px; align-items: center; padding: 6px 0;">'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #0284c7; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">👁️ View Result</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #dc2626; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📄 Export PDF</a>'
            '<a class="button" href="{}" target="_blank" style="padding: 6px 14px; background: #2563eb; color: white; border-radius: 5px; text-decoration: none; font-weight: 600;">📝 Export DOCX</a>'
            '{}'
            '</div>',
            result_url, pdf_url, docx_url, mark_safe(review_button_html),
        )

    @admin.display(description="Listening Answers Breakdown (40 Questions)")
    def listening_answers_breakdown(self, obj):
        if not obj or not obj.pk or obj.module.module_type != ExamModule.ModuleType.LISTENING:
            return "N/A (Non-Listening module)"
        payload = obj.answers_payload or {}
        answers = payload.get("answers", {})
        if not answers:
            return format_html("<em>No detailed answers payload recorded for this attempt.</em>")

        rows = []
        keys = sorted(answers.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)
        for k in keys:
            item = answers[k]
            u_ans = item.get("user_answer", "") or "-"
            c_ans = item.get("correct_answer", "") or "-"
            is_cor = bool(item.get("is_correct", False))
            status_badge = (
                '<span style="color:#059669; font-weight:700;">&#10003; Correct</span>'
                if is_cor else
                '<span style="color:#dc2626; font-weight:700;">&#10007; Incorrect</span>'
            )
            rows.append(
                f"<tr>"
                f"<td style='padding:6px 12px; border:1px solid #e2e8f0; font-weight:bold;'>{k}</td>"
                f"<td style='padding:6px 12px; border:1px solid #e2e8f0;'>{u_ans}</td>"
                f"<td style='padding:6px 12px; border:1px solid #e2e8f0; font-weight:bold;'>{c_ans}</td>"
                f"<td style='padding:6px 12px; border:1px solid #e2e8f0;'>{status_badge}</td>"
                f"</tr>"
            )
        table_html = (
            "<div style='max-height:450px; overflow-y:auto; border:1px solid #cbd5e1; border-radius:6px;'>"
            "<table style='border-collapse:collapse; width:100%; font-size:13px;'>"
            "<thead><tr style='background:#f1f5f9; text-align:left; position:sticky; top:0; z-index:2;'>"
            "<th style='padding:8px 12px; border:1px solid #cbd5e1;'>Q#</th>"
            "<th style='padding:8px 12px; border:1px solid #cbd5e1;'>Candidate Answer</th>"
            "<th style='padding:8px 12px; border:1px solid #cbd5e1;'>Correct Answer</th>"
            "<th style='padding:8px 12px; border:1px solid #cbd5e1;'>Result</th>"
            "</tr></thead><tbody>"
            + "".join(rows) +
            "</tbody></table></div>"
        )
        return mark_safe(table_html)


@admin.register(CandidateAnswer)
class CandidateAnswerAdmin(ScopedCandidateDataAdmin):
    list_display = (
        "id",
        "attempt",
        "question",
        "is_flagged",
        "is_correct",
        "awarded_marks",
        "saved_at",
    )
    list_filter = (
        "is_flagged",
        "is_correct",
    )
    search_fields = (
        "attempt__candidate__username",
        "question__question_text",
    )
    readonly_fields = (
        "attempt",
        "question",
        "answer_text",
        "is_flagged",
        "is_correct",
        "awarded_marks",
        "saved_at",
    )
    list_select_related = (
        "attempt",
        "attempt__candidate",
        "question",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WritingEvaluation)
class WritingEvaluationAdmin(ScopedCandidateDataAdmin):
    list_display = (
        "id",
        "attempt",
        "examiner",
        "task_achievement",
        "coherence_cohesion",
        "lexical_resource",
        "grammatical_range_accuracy",
        "evaluated_at",
    )
    list_filter = (
        "evaluated_at",
    )
    search_fields = (
        "attempt__candidate__username",
        "examiner__username",
    )
    readonly_fields = ("evaluated_at",)
    list_select_related = (
        "attempt",
        "attempt__candidate",
        "examiner",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.examiner = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is None:
            fields.append("examiner")
        else:
            fields.append("attempt")
            fields.append("examiner")
        return fields


@admin.register(MockFromOption)
class MockFromOptionAdmin(QuestionSetterBaseAdmin):
    list_display = ("name", "logo_preview", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name",)
    list_editable = ("is_active",)
    readonly_fields = ("logo_preview",)

    @admin.display(description="Logo / Favicon")
    def logo_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="height:32px;max-width:120px;object-fit:contain;border-radius:4px;border:1px solid #cbd5e1;background:#fff;padding:2px;" alt="{}" />',
                obj.image.url,
                obj.name,
            )
        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:6px;color:#64748b;font-size:12px;">'
            '<img src="/static/images/bcl.jpg" style="height:24px;width:auto;border-radius:4px;opacity:0.7;" alt="Default" />'
            'Default BCL Logo</span>'
        )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "image",
                    "logo_preview",
                    "is_active",
                ),
                "description": "Upload a custom branch logo/image. It is used as the navbar header logo and favicon for candidates and subadmins of this Mock_from branch. If left empty, the default BCL logo is used.",
            },
        ),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class CandidateProfileAddForm(forms.ModelForm):
    """
    Direct registration/sign up form from the Candidate Approvals admin.
    Creates both the auth.User and CandidateProfile in one atomic operation.
    Neither status nor rejection_reason is displayed during creation.
    Mock_from is visible only to main admin (hidden from sub-admin).
    """
    username = forms.CharField(
        max_length=150,
        required=True,
        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": "vTextField"}),
        required=True,
        help_text="Required. Set a strong password for this candidate.",
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        label="First Name",
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        label="Last Name",
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    email = forms.EmailField(
        required=False,
        label="Email Address",
        widget=forms.EmailInput(attrs={"class": "vTextField"}),
    )
    is_active = forms.BooleanField(
        label="Account Active (Can log in)",
        initial=True,
        required=False,
        help_text="Designates whether this candidate account can log in immediately.",
    )
    Mock_from = forms.ChoiceField(
        label="Mock From",
        required=False,
    )

    class Meta:
        model = CandidateProfile
        fields = []

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        is_sub = bool(self.request and not self.request.user.is_superuser and is_subadmin(self.request.user))
        if is_sub:
            # Sub-admin: Mock_from is NOT visible at all
            if "Mock_from" in self.fields:
                del self.fields["Mock_from"]
        else:
            # Main admin: can choose any option
            self.fields["Mock_from"].choices = MockFromOption.get_choices()
            self.fields["Mock_from"].initial = "BCL_Bhuiyan"
            self.fields["Mock_from"].help_text = "Select institution or branch for this candidate."

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(f"A user with username '{username}' already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(f"A user with email '{email}' already exists.")
        return email

    def clean_Mock_from(self):
        if self.request and not self.request.user.is_superuser:
            branch = get_subadmin_mock_from(self.request.user)
            if branch:
                return branch
        return self.cleaned_data.get("Mock_from") or "BCL_Bhuiyan"

    def save(self, commit=True):
        profile = super().save(commit=False)
        username = self.cleaned_data["username"]
        password = self.cleaned_data["password"]
        first_name = self.cleaned_data.get("first_name", "")
        last_name = self.cleaned_data.get("last_name", "")
        email = self.cleaned_data.get("email", "")
        is_active = self.cleaned_data.get("is_active", True)
        status = CandidateProfile.ApprovalStatus.APPROVED if is_active else CandidateProfile.ApprovalStatus.PENDING

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        user.set_password(password)
        user.is_active = is_active
        user._syncing_status = True
        user.save()
        user._syncing_status = False

        profile.user = user
        profile.Mock_from = self.clean_Mock_from()
        profile.status = status
        if status == CandidateProfile.ApprovalStatus.APPROVED:
            profile.reviewed_by = self.request.user if self.request else None
            profile.reviewed_at = timezone.now()

        if commit:
            profile.save()
        return profile


class CandidateProfileChangeForm(forms.ModelForm):
    """
    Form used when editing an existing CandidateProfile in admin.
    Surfaces is_active and locks Mock_from for subadmins.
    """
    is_active = forms.BooleanField(
        label="Account Active (is_active)",
        required=False,
        help_text="Designates whether this candidate account is active and can log in.",
    )

    class Meta:
        model = CandidateProfile
        fields = [
            "Mock_from",
            "status",
            "rejection_reason",
        ]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and getattr(self.instance, "user", None):
            self.fields["is_active"].initial = self.instance.user.is_active

        subadmin_branch = (
            get_subadmin_mock_from(self.request.user)
            if (self.request and not self.request.user.is_superuser)
            else None
        )
        if subadmin_branch:
            self.fields["Mock_from"].choices = [(subadmin_branch, subadmin_branch)]
            self.fields["Mock_from"].initial = subadmin_branch
            self.fields["Mock_from"].widget.attrs["readonly"] = "readonly"
            self.fields["Mock_from"].widget.attrs["disabled"] = "disabled"
            self.fields["Mock_from"].required = False
            self.fields["Mock_from"].help_text = f"Locked to your branch: {subadmin_branch} (cannot be switched)."
        else:
            self.fields["Mock_from"].choices = MockFromOption.get_choices()

    def clean_Mock_from(self):
        subadmin_branch = (
            get_subadmin_mock_from(self.request.user)
            if (self.request and not self.request.user.is_superuser)
            else None
        )
        if subadmin_branch:
            return subadmin_branch
        return self.cleaned_data.get("Mock_from") or (self.instance.Mock_from if self.instance else "BCL_Bhuiyan")

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.Mock_from = self.clean_Mock_from()

        is_active = self.cleaned_data.get("is_active")
        if profile.user:
            if profile.status == CandidateProfile.ApprovalStatus.APPROVED:
                profile.user.is_active = True if is_active is None else is_active
            elif profile.status in [CandidateProfile.ApprovalStatus.PENDING, CandidateProfile.ApprovalStatus.REJECTED]:
                profile.user.is_active = False
            profile.user._syncing_status = True
            profile.user.save(update_fields=["is_active"])
            profile.user._syncing_status = False

        if commit:
            profile.save()
        return profile


@admin.register(CandidateProfile)
class CandidateProfileAdmin(QuestionSetterBaseAdmin):
    list_display = (
        "user_username",
        "user_full_name",
        "user_email",
        "Mock_from",
        "status_badge",
        "is_active_badge",
        "created_at",
        "reviewed_by",
        "reviewed_at",
        "action_buttons",
    )
    list_filter = (
        "Mock_from",
        "status",
        "created_at",
        "reviewed_at",
    )
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "Mock_from",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "reviewed_at",
        "reviewed_by",
    )
    actions = ["approve_selected", "reject_selected"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            form_class = CandidateProfileAddForm
        else:
            form_class = CandidateProfileChangeForm

        class FormWithRequest(form_class):
            def __init__(sub_self, *f_args, **f_kwargs):
                f_kwargs.setdefault("request", request)
                super().__init__(*f_args, **f_kwargs)

        return FormWithRequest

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            if request.user.is_superuser:
                return (
                    (
                        "User Account (Registration / Sign Up)",
                        {
                            "fields": (
                                "username",
                                "password",
                                ("first_name", "last_name"),
                                "email",
                                "is_active",
                            ),
                            "description": "Register a new candidate user directly from admin.",
                        },
                    ),
                    (
                        "Candidate Branch",
                        {
                            "fields": (
                                "Mock_from",
                            ),
                        },
                    ),
                )
            else:
                # Sub-admin: Mock_from is NOT visible; neither status nor rejection_reason appears.
                return (
                    (
                        "User Account (Registration / Sign Up)",
                        {
                            "fields": (
                                "username",
                                "password",
                                ("first_name", "last_name"),
                                "email",
                                "is_active",
                            ),
                            "description": "Register a new candidate user directly from admin.",
                        },
                    ),
                )
        return (
            (
                "Candidate User Details",
                {
                    "fields": (
                        "user",
                        "is_active",
                    ),
                },
            ),
            (
                "Branch & Approval Status",
                {
                    "fields": (
                        "Mock_from",
                        "status",
                        "rejection_reason",
                    ),
                },
            ),
            (
                "Audit Information",
                {
                    "fields": (
                        ("reviewed_by", "reviewed_at"),
                        ("created_at", "updated_at"),
                    ),
                    "classes": ("collapse",),
                },
            ),
        )

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj is not None:
            ro.append("user")
            if not request.user.is_superuser:
                ro.append("Mock_from")
        return ro

    def has_add_permission(self, request):
        if is_subadmin(request.user) or request.user.is_superuser:
            return True
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if is_subadmin(request.user):
            if obj is not None:
                branch = get_subadmin_mock_from(request.user)
                if branch and obj.Mock_from != branch:
                    return False
            return True
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        user = obj.user
        super().delete_model(request, obj)
        if user and not getattr(user, "_is_being_deleted", False):
            user._is_being_deleted = True
            try:
                from .models import CandidateAttempt, FullMockAttempt
                FullMockAttempt.objects.filter(candidate=user).delete()
                CandidateAttempt.objects.filter(candidate=user).delete()
                user.delete()
            except Exception:
                pass

    def delete_queryset(self, request, queryset):
        users = [p.user for p in queryset if p.user]
        super().delete_queryset(request, queryset)
        for user in users:
            if not getattr(user, "_is_being_deleted", False):
                user._is_being_deleted = True
                try:
                    from .models import CandidateAttempt, FullMockAttempt
                    FullMockAttempt.objects.filter(candidate=user).delete()
                    CandidateAttempt.objects.filter(candidate=user).delete()
                    user.delete()
                except Exception:
                    pass

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            if branch:
                obj.Mock_from = branch
        super().save_model(request, obj, form, change)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "Mock_from":
            if not request.user.is_superuser:
                branch = get_subadmin_mock_from(request.user)
                if branch:
                    return forms.ChoiceField(
                        label="Mock From",
                        choices=[(branch, branch)],
                        initial=branch,
                        required=False,
                    )
            return forms.ChoiceField(
                label="Mock From",
                choices=MockFromOption.get_choices(),
                initial="BCL_Bhuiyan",
                required=False,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Active", boolean=True)
    def is_active_badge(self, obj):
        return obj.user.is_active if (obj and obj.user) else False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("user", "reviewed_by")
        if not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            if branch:
                qs = qs.filter(Mock_from=branch)
        return qs

    def has_module_permission(self, request):
        if is_subadmin(request.user):
            return True
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if is_subadmin(request.user):
            if obj is not None:
                branch = get_subadmin_mock_from(request.user)
                if branch and obj.Mock_from != branch:
                    return False
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if is_subadmin(request.user):
            if obj is not None:
                branch = get_subadmin_mock_from(request.user)
                if branch and obj.Mock_from != branch:
                    return False
            return True
        return super().has_change_permission(request, obj)

    @admin.display(description="Username", ordering="user__username")
    def user_username(self, obj):
        return obj.user.username

    @admin.display(description="Full Name", ordering="user__first_name")
    def user_full_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or "—"

    @admin.display(description="Email", ordering="user__email")
    def user_email(self, obj):
        return obj.user.email or "—"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        if obj.status == CandidateProfile.ApprovalStatus.APPROVED:
            return format_html(
                '<span style="background-color:#dcfce7;color:#15803d;padding:3px 10px;border-radius:9999px;font-weight:700;font-size:12px;display:inline-block;">Approved</span>'
            )
        elif obj.status == CandidateProfile.ApprovalStatus.REJECTED:
            return format_html(
                '<span style="background-color:#fee2e2;color:#b91c1c;padding:3px 10px;border-radius:9999px;font-weight:700;font-size:12px;display:inline-block;">Rejected</span>'
            )
        return format_html(
            '<span style="background-color:#fef3c7;color:#b45309;padding:3px 10px;border-radius:9999px;font-weight:700;font-size:12px;display:inline-block;">Pending Approval</span>'
        )

    @admin.display(description="Actions")
    def action_buttons(self, obj):
        approve_url = reverse("admin:bcl_candidateprofile_approve", args=[obj.pk])
        reject_url = reverse("admin:bcl_candidateprofile_reject", args=[obj.pk])
        buttons = []
        if obj.status != CandidateProfile.ApprovalStatus.APPROVED:
            buttons.append(
                f'<a href="{approve_url}" style="background-color:#16a34a;color:white;padding:4px 10px;border-radius:6px;font-weight:600;font-size:11px;text-decoration:none;margin-right:6px;display:inline-block;">Approve</a>'
            )
        if obj.status != CandidateProfile.ApprovalStatus.REJECTED:
            buttons.append(
                f'<a href="{reject_url}" style="background-color:#dc2626;color:white;padding:4px 10px;border-radius:6px;font-weight:600;font-size:11px;text-decoration:none;display:inline-block;">Reject</a>'
            )
        return mark_safe("".join(buttons))

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:profile_id>/approve/",
                self.admin_site.admin_view(self.approve_candidate_view),
                name="bcl_candidateprofile_approve",
            ),
            path(
                "<int:profile_id>/reject/",
                self.admin_site.admin_view(self.reject_candidate_view),
                name="bcl_candidateprofile_reject",
            ),
        ]
        return custom_urls + urls

    def approve_candidate_view(self, request, profile_id):
        profile = self.get_object(request, profile_id)
        if profile:
            if not request.user.is_superuser:
                branch = get_subadmin_mock_from(request.user)
                if branch and profile.Mock_from != branch:
                    self.message_user(request, "Permission denied. You can only approve candidates in your assigned branch.", messages.ERROR)
                    return redirect("admin:bcl_candidateprofile_changelist")
            profile.approve(admin_user=request.user)
            self.message_user(
                request,
                f"Candidate {profile.user.username} has been APPROVED. They can now log in.",
                messages.SUCCESS,
            )
        return redirect("admin:bcl_candidateprofile_changelist")

    def reject_candidate_view(self, request, profile_id):
        profile = self.get_object(request, profile_id)
        if profile:
            if not request.user.is_superuser:
                branch = get_subadmin_mock_from(request.user)
                if branch and profile.Mock_from != branch:
                    self.message_user(request, "Permission denied. You can only reject candidates in your assigned branch.", messages.ERROR)
                    return redirect("admin:bcl_candidateprofile_changelist")
            profile.reject(admin_user=request.user)
            self.message_user(
                request,
                f"Candidate {profile.user.username} has been REJECTED. Their account is disabled.",
                messages.WARNING,
            )
        return redirect("admin:bcl_candidateprofile_changelist")

    @admin.action(description="Approve selected candidates")
    def approve_selected(self, request, queryset):
        if not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            if branch:
                queryset = queryset.filter(Mock_from=branch)
        count = 0
        for profile in queryset:
            profile.approve(admin_user=request.user)
            count += 1
        self.message_user(request, f"{count} candidate(s) approved successfully.", messages.SUCCESS)

    @admin.action(description="Reject selected candidates")
    def reject_selected(self, request, queryset):
        if not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            if branch:
                queryset = queryset.filter(Mock_from=branch)
        count = 0
        for profile in queryset:
            profile.reject(admin_user=request.user)
            count += 1
        self.message_user(request, f"{count} candidate(s) rejected.", messages.WARNING)


# ==============================================================================
# 9. SUBADMIN MANAGEMENT (MAIN ADMIN ONLY)
# ==============================================================================

class SubAdminCreationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, required=True, help_text="Required. 150 characters or fewer.")
    password = forms.CharField(widget=forms.PasswordInput, required=True, help_text="Password for subadmin login.")
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    is_active = forms.BooleanField(initial=True, required=False, label="Active account")

    class Meta:
        model = SubAdminProfile
        fields = ("username", "password", "first_name", "last_name", "email", "Mock_from", "can_manage_mocks", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["Mock_from"].widget = forms.Select(choices=MockFromOption.get_choices())

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def save(self, commit=True):
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data["username"],
            email=data.get("email", ""),
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            is_staff=True,
            is_superuser=False,
            is_active=data.get("is_active", True),
        )
        profile = super().save(commit=False)
        profile.user = user
        if commit:
            profile.save()
        return profile


class SubAdminChangeForm(forms.ModelForm):
    new_password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        label="Set New Password",
        help_text="Leave blank to keep the current password.",
    )
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    is_active = forms.BooleanField(required=False, label="Active account")

    class Meta:
        model = SubAdminProfile
        fields = ("first_name", "last_name", "email", "new_password", "Mock_from", "can_manage_mocks", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
            self.fields["email"].initial = self.instance.user.email
            self.fields["is_active"].initial = self.instance.user.is_active
        self.fields["Mock_from"].widget = forms.Select(choices=MockFromOption.get_choices())

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        data = self.cleaned_data
        user.first_name = data.get("first_name", "")
        user.last_name = data.get("last_name", "")
        user.email = data.get("email", "")
        user.is_active = data.get("is_active", True)
        user.is_staff = True
        user.is_superuser = False
        if data.get("new_password"):
            user.set_password(data["new_password"])
        user.save()
        return profile


@admin.register(SubAdminProfile)
class SubAdminProfileAdmin(QuestionSetterBaseAdmin):
    """
    Subadmin configuration center strictly reserved for Main Admin (superuser).
    Allows Main Admin to create subadmins with their assigned Mock_from branch
    and grant or revoke the privilege to view/modify IELTS Mock Tests.
    """
    add_form = SubAdminCreationForm
    form = SubAdminChangeForm

    list_display = (
        "user_username",
        "user_full_name",
        "user_email",
        "Mock_from",
        "can_manage_mocks_badge",
        "is_active_badge",
        "created_at",
    )
    list_filter = (
        "Mock_from",
        "can_manage_mocks",
        "user__is_active",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "Mock_from",
    )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            return self.add_form
        return self.form

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description="Username", ordering="user__username")
    def user_username(self, obj):
        return obj.user.username

    @admin.display(description="Full Name", ordering="user__first_name")
    def user_full_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or "—"

    @admin.display(description="Email", ordering="user__email")
    def user_email(self, obj):
        return obj.user.email or "—"

    @admin.display(description="Mock Management")
    def can_manage_mocks_badge(self, obj):
        if obj.can_manage_mocks:
            return format_html(
                '<span style="background-color:#dcfce7;color:#15803d;padding:3px 10px;border-radius:9999px;font-weight:700;font-size:12px;">Authorized (View &amp; Edit)</span>'
            )
        return format_html(
            '<span style="background-color:#fee2e2;color:#b91c1c;padding:3px 10px;border-radius:9999px;font-weight:700;font-size:12px;">Restricted (No Access)</span>'
        )

    @admin.display(description="Account Status")
    def is_active_badge(self, obj):
        if obj.user.is_active:
            return format_html('<span style="color:#16a34a;font-weight:700;">Active</span>')
        return format_html('<span style="color:#dc2626;font-weight:700;">Disabled</span>')


# ==============================================================================
# 10. SCOPED USER ADMIN (HIDES MAIN ADMIN & OTHER BRANCHES FROM SUBADMINS)
# ==============================================================================

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class ScopedUserAdmin(UserAdmin):
    """
    UserAdmin that ensures subadmins can ONLY view candidates from their assigned Mock_from branch.
    Superusers and other staff accounts are completely hidden from subadmins.
    """
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            branch = get_subadmin_mock_from(request.user)
            if branch:
                return qs.filter(
                    is_superuser=False,
                    is_staff=False,
                    candidate_profile__Mock_from=branch,
                )
            return qs.none()
        return qs

    def has_module_permission(self, request):
        if is_subadmin(request.user):
            return True
        return super().has_module_permission(request)

    def has_add_permission(self, request):
        if not request.user.is_superuser:
            return False
        return super().has_add_permission(request)

    def has_view_permission(self, request, obj=None):
        if is_subadmin(request.user):
            if obj is not None:
                if obj.is_superuser or obj.is_staff:
                    return False
                branch = get_subadmin_mock_from(request.user)
                cand_branch = getattr(getattr(obj, "candidate_profile", None), "Mock_from", "")
                if branch and cand_branch != branch:
                    return False
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            if obj.is_superuser or obj.is_staff:
                return False
            branch = get_subadmin_mock_from(request.user)
            cand_branch = getattr(getattr(obj, "candidate_profile", None), "Mock_from", "")
            if branch and cand_branch != branch:
                return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            if obj.is_superuser or obj.is_staff:
                return False
            branch = get_subadmin_mock_from(request.user)
            cand_branch = getattr(getattr(obj, "candidate_profile", None), "Mock_from", "")
            if branch and cand_branch != branch:
                return False
        return super().has_delete_permission(request, obj)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not request.user.is_superuser:
            # Subadmins cannot see or edit Permissions section (is_staff, is_superuser, groups)
            fieldsets = [
                (name, data) for (name, data) in fieldsets
                if name not in ("Permissions", "Important dates")
            ]
        return fieldsets


# ==============================================================================
# 11. ENHANCED ADMIN DASHBOARD CONTEXT WITH BRANCH SCOPING
# ==============================================================================

_orig_admin_index = admin.site.index


def custom_admin_index(request, extra_context=None):
    extra_context = extra_context or {}
    User = get_user_model()
    user = request.user

    is_sub = is_subadmin(user)
    sub_branch = get_subadmin_mock_from(user) if is_sub else None
    can_mocks = can_manage_mock_tests(user)

    user_filter = Q(is_staff=False, is_superuser=False)
    attempt_filter = ~Q(status=CandidateAttempt.AttemptStatus.IN_PROGRESS)
    full_mock_filter = ~Q(status=FullMockAttempt.AttemptStatus.IN_PROGRESS)
    profile_filter = Q()

    if is_sub and sub_branch:
        user_filter &= Q(candidate_profile__Mock_from=sub_branch)
        attempt_filter &= Q(candidate__candidate_profile__Mock_from=sub_branch)
        full_mock_filter &= Q(candidate__candidate_profile__Mock_from=sub_branch)
        profile_filter &= Q(Mock_from=sub_branch)

    total_students = User.objects.filter(user_filter).count()
    total_mock_tests = IELTSMockTest.objects.count() if can_mocks else 0
    total_module_attempts = CandidateAttempt.objects.filter(attempt_filter).count()
    total_full_mocks = FullMockAttempt.objects.filter(full_mock_filter).count()

    pending_writing_qs = (
        CandidateAttempt.objects.filter(module__module_type=ExamModule.ModuleType.WRITING)
        .filter(attempt_filter)
        .annotate(graded_tasks=Count("task_evaluations", distinct=True))
        .filter(graded_tasks__lt=2)
    )
    pending_writing = pending_writing_qs.count()

    recent_student_results = (
        CandidateAttempt.objects.filter(attempt_filter)
        .select_related("candidate", "module", "module__mock_test")
        .prefetch_related("task_evaluations")
        .order_by("-submitted_at", "-started_at")[:30]
    )

    recent_full_mocks = (
        FullMockAttempt.objects.filter(full_mock_filter)
        .select_related("candidate", "mock_test", "reading_attempt", "listening_attempt", "writing_attempt")
        .order_by("-submitted_at", "-started_at")[:20]
    )

    pending_registrations = (
        CandidateProfile.objects.filter(status=CandidateProfile.ApprovalStatus.PENDING)
        .filter(profile_filter)
        .count()
    )

    mock_studio_items = []
    if can_mocks:
        mocks_qs = (
            IELTSMockTest.objects.prefetch_related("modules__sections__questions")
            .order_by("test_number")
        )
        for m in mocks_qs:
            mods = {mod.module_type: mod for mod in m.modules.all()}
            mock_studio_items.append({
                "mock": m,
                "listening": mods.get(ExamModule.ModuleType.LISTENING),
                "reading": mods.get(ExamModule.ModuleType.READING),
                "writing": mods.get(ExamModule.ModuleType.WRITING),
            })

    extra_context.update({
        "is_subadmin": is_sub,
        "subadmin_branch": sub_branch,
        "can_manage_mocks": can_mocks,
        "total_students": total_students,
        "total_mock_tests": total_mock_tests,
        "total_module_attempts": total_module_attempts,
        "total_full_mocks": total_full_mocks,
        "pending_registrations": pending_registrations,
        "pending_writing": pending_writing,
        "recent_student_results": recent_student_results,
        "recent_full_mocks": recent_full_mocks,
        "mock_studio_items": mock_studio_items,
    })

    return _orig_admin_index(request, extra_context=extra_context)


admin.site.index = custom_admin_index

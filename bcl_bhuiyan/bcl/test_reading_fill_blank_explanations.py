from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    IELTSMockTest, ExamModule, ExamSection, Question,
    CandidateAttempt, CandidateAnswer
)

User = get_user_model()


class ReadingFillBlankExplanationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reading_student",
            email="reading_student@example.com",
            password="Pass#2026Strong"
        )
        self.client.force_login(self.user)

        self.mock_test = IELTSMockTest.objects.create(
            title="MOCK-READING-01",
            test_number=1,
            is_published=True,
        )

        self.module = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
        )

        self.section = ExamSection.objects.create(
            module=self.module,
            title="Reading Passage 1",
            order=1,
            passage="Reading passage text here...",
        )

    def test_single_blank_explanation_with_double_and_single_quotes(self):
        full_explanation = (
            'According to paragraph 2, the author notes that "climate change" was accelerating. '
            'This explains why \'adaptation\' was considered crucial for survival.'
        )

        q1 = Question.objects.create(
            section=self.section,
            question_type=Question.QuestionType.FILL_BLANK,
            question_text="The species survived due to rapid _____ in response to climate shifts.",
            correct_answer="adaptation",
            explanation=full_explanation,
            order=1,
            marks=1,
        )

        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user,
            module=self.module,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now,
            expires_at=now + timedelta(minutes=60),
            submitted_at=now + timedelta(minutes=30),
        )

        CandidateAnswer.objects.create(
            attempt=attempt,
            question=q1,
            answer_text="adaptation"
        )

        response = self.client.get(reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)

        from django.utils.html import escape
        self.assertContains(
            response,
            '<template class="fb-raw-explanation">' + escape(full_explanation) + '</template>',
            html=False
        )

        # Ensure splitExplanations does not break on quotes in JS script definition
        content = response.content.decode("utf-8")
        self.assertNotIn('const quoteRegex = /["\u201c]([\\s\\S]*?)["\u201d]/g;', content)
        self.assertIn('function splitExplanations(rawExp, globalNum, totalBlanks)', content)
        self.assertIn('if (!totalBlanks || totalBlanks <= 1) {\n            return [text];\n        }', content)

    def test_multi_blank_with_semicolon_delimiter_and_quotes(self):
        exp1 = 'Paragraph 1: "first quote" indicates energy.'
        exp2 = 'Paragraph 2: "second quote" refers to temperature.'
        multi_exp = f"{exp1} ;;; {exp2}"

        q2 = Question.objects.create(
            section=self.section,
            question_type=Question.QuestionType.FILL_BLANK,
            question_text="Sources include _____ and _____. ",
            correct_answer="energy ;;; temperature",
            explanation=multi_exp,
            order=2,
            marks=2,
        )

        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user,
            module=self.module,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now,
            expires_at=now + timedelta(minutes=60),
            submitted_at=now + timedelta(minutes=30),
        )

        CandidateAnswer.objects.create(
            attempt=attempt,
            question=q2,
            answer_text="energy ;;; temperature"
        )

        response = self.client.get(reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)
        from django.utils.html import escape
        self.assertContains(response, '<template class="fb-raw-explanation">' + escape(multi_exp) + '</template>', html=False)

    def test_fill_blank_with_all_rich_explanation_fields(self):
        q3 = Question.objects.create(
            section=self.section,
            question_type=Question.QuestionType.FILL_BLANK,
            question_text="Megafires burn _____ the size of typical fires.",
            correct_answer="10 times",
            order=3,
            marks=1,
            answer_location="Paragraph C",
            passage_excerpt="Megafires are 10 times the size of average fires.",
            what_question_asks="What is the scale of the fires?",
            what_passage_says="Paragraph C states megafires burn 10 times the size.",
            why_answer="10 times directly answers the size comparison.",
            paraphrase="10x = ten times",
            tip="Pay attention to number words.",
        )

        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user,
            module=self.module,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now,
            expires_at=now + timedelta(minutes=60),
            submitted_at=now + timedelta(minutes=30),
        )

        CandidateAnswer.objects.create(
            attempt=attempt,
            question=q3,
            answer_text="10 times"
        )

        response = self.client.get(reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)

        # Verify all rich explanation parts are present inside the template
        self.assertContains(response, '<template class="fb-rich-explanation">')
        self.assertContains(response, "Answer location &mdash; Paragraph C")
        self.assertContains(response, "Megafires are 10 times the size of average fires.")
        self.assertContains(response, "What the question asks")
        self.assertContains(response, "What is the scale of the fires?")
        self.assertContains(response, "What the passage says")
        self.assertContains(response, "Paragraph C states megafires burn 10 times the size.")
        self.assertContains(response, "Why this is the answer")
        self.assertContains(response, "10 times directly answers the size comparison.")
        self.assertContains(response, "Paraphrase")
        self.assertContains(response, "10x = ten times")
        self.assertContains(response, "Tip")
        self.assertContains(response, "Pay attention to number words.")
        self.assertContains(response, "Highlight in passage &rarr;")

        # Verify JS template cloning logic
        content = response.content.decode("utf-8")
        self.assertIn("if (richTemplate) {", content)
        self.assertIn("expBox.innerHTML = richTemplate.innerHTML;", content)

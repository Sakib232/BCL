import os
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings
from bcl.models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    CandidateAttempt,
    CandidateAnswer,
    WritingTaskEvaluation,
    WritingEvaluation,
)
from bcl.writing_analyzer import (
    evaluate_writing_text,
    auto_evaluate_writing_attempt,
    round_to_ielts_half_band,
)

User = get_user_model()


class WritingAnalyzerIntegrationTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(
            username="test_writing_candidate",
            email="candidate@example.com",
            password="Password123!"
        )
        self.staff_examiner = User.objects.create_user(
            username="test_examiner",
            email="examiner@example.com",
            password="Password123!",
            is_staff=True,
            is_superuser=True
        )

        self.mock_test = IELTSMockTest.objects.create(
            title="Writing Scoring Mock Test",
            test_number=999,
            is_published=True
        )
        self.writing_module = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
            is_active=True
        )

        # Task 1 Section & Question
        self.sec1 = ExamSection.objects.create(
            module=self.writing_module,
            order=1,
            title="Writing Task 1"
        )
        self.q1 = Question.objects.create(
            section=self.sec1,
            question_type=Question.QuestionType.ESSAY,
            order=1,
            question_text="The chart below shows energy consumption in 2020. Summarize the information.",
            marks=1
        )

        # Task 2 Section & Question
        self.sec2 = ExamSection.objects.create(
            module=self.writing_module,
            order=2,
            title="Writing Task 2"
        )
        self.q2 = Question.objects.create(
            section=self.sec2,
            question_type=Question.QuestionType.ESSAY,
            order=2,
            question_text="Some people think universities should be free. Discuss both views.",
            marks=1
        )

        # Candidate Attempt & Answers
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.candidate,
            module=self.writing_module,
            started_at=now - timedelta(minutes=55),
            expires_at=now + timedelta(minutes=5),
            submitted_at=now,
            status=CandidateAttempt.AttemptStatus.SUBMITTED
        )
        self.ans1 = CandidateAnswer.objects.create(
            attempt=self.attempt,
            question=self.q1,
            answer_text=(
                "The provided line graph illustrates renewable energy production trends between 2010 and 2020. "
                "Overall, it is evident that solar and wind power increased significantly throughout the decade, "
                "whereas traditional fossil fuels experienced a noticeable decline.\n\n"
                "In 2010, hydroelectric power was the predominant renewable source, contributing approximately 45% "
                "of total green energy. Throughout the decade, this figure remained relatively stable with minor "
                "fluctuations. Furthermore, wind power generation rose steadily from 20% in 2012 to over 35% by 2019.\n\n"
                "In contrast, solar power recorded the most dramatic growth over the period, expanding from a modest 5% "
                "at the beginning of the period to nearly 30% by 2020. Consequently, aggregate renewable electricity "
                "surpassed conventional generation targets ahead of projected deadlines."
            )
        )
        self.ans2 = CandidateAnswer.objects.create(
            attempt=self.attempt,
            question=self.q2,
            answer_text=(
                "In contemporary society, an increasing proportion of people believe higher education should be free for all students.\n\n"
                "On the one hand, government funding creates equal access regardless of socioeconomic background. "
                "Furthermore, a highly educated workforce stimulates economic growth and innovation across multiple sectors.\n\n"
                "On the other hand, free university education places an enormous financial burden on public revenue. "
                "Consequently, some argue that individuals should contribute to their personal qualifications.\n\n"
                "In conclusion, although state financial support is valuable, a shared funding model remains more sustainable."
            )
        )

    def test_evaluator_rubric_logic(self):
        result_t1 = evaluate_writing_text(self.ans1.answer_text, task_number=1)
        self.assertGreaterEqual(result_t1["task_achievement"], Decimal("5.0"))
        self.assertLessEqual(result_t1["task_achievement"], Decimal("7.0"))
        self.assertGreaterEqual(result_t1["coherence_cohesion"], Decimal("5.0"))
        self.assertLessEqual(result_t1["coherence_cohesion"], Decimal("7.0"))
        self.assertGreaterEqual(result_t1["lexical_resource"], Decimal("5.0"))
        self.assertLessEqual(result_t1["lexical_resource"], Decimal("7.0"))
        self.assertGreaterEqual(result_t1["grammatical_range_accuracy"], Decimal("5.0"))
        self.assertLessEqual(result_t1["grammatical_range_accuracy"], Decimal("7.0"))
        self.assertIn("Word Count", result_t1["feedback"])

        result_t2 = evaluate_writing_text(self.ans2.answer_text, task_number=2)
        self.assertGreaterEqual(result_t2["task_achievement"], Decimal("5.0"))
        self.assertLessEqual(result_t2["task_achievement"], Decimal("7.0"))
        self.assertIn("Cohesion", result_t2["feedback"])

    def test_automated_writing_scoring_stored_in_database(self):
        band = auto_evaluate_writing_attempt(self.attempt)
        self.attempt.refresh_from_db()

        self.assertIsNotNone(self.attempt.band_score)
        self.assertEqual(self.attempt.band_score, band)
        self.assertGreaterEqual(self.attempt.band_score, Decimal("5.0"))
        self.assertLessEqual(self.attempt.band_score, Decimal("7.0"))

        evals = list(WritingTaskEvaluation.objects.filter(attempt=self.attempt).order_by("task_number"))
        self.assertEqual(len(evals), 2)
        self.assertEqual(evals[0].task_number, 1)
        self.assertEqual(evals[1].task_number, 2)
        for ev in evals:
            self.assertGreaterEqual(ev.criterion_average, Decimal("5.0"))
            self.assertLessEqual(ev.criterion_average, Decimal("7.0"))

    def test_student_views_score_on_result_page(self):
        auto_evaluate_writing_attempt(self.attempt)
        self.attempt.refresh_from_db()

        client = Client()
        client.force_login(self.candidate)
        url = reverse("bcl:exam_result", args=[self.attempt.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(response.context["is_evaluated"])
        content = response.content.decode("utf-8")
        self.assertIn(f"Band {self.attempt.band_score}", content)
        self.assertIn("Task Achievement", content)
        self.assertIn("Coherence & Cohesion", content)
        self.assertIn("Lexical Resource", content)

    def test_examiner_can_review_and_modify_scores_in_database(self):
        auto_evaluate_writing_attempt(self.attempt)
        self.attempt.refresh_from_db()
        initial_band = self.attempt.band_score

        client = Client()
        client.force_login(self.staff_examiner)
        url = reverse("bcl:writing_review_detail", args=[self.attempt.pk])

        # GET review page
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        # POST updated scores for Task 1 (e.g. examiner overrides score to 8.0)
        post_data = {
            "task_number": "1",
            "task1-task_achievement": "8.0",
            "task1-coherence_cohesion": "8.0",
            "task1-lexical_resource": "8.0",
            "task1-grammatical_range_accuracy": "8.0",
            "task1-feedback": "Superb Task 1 response adjusted by head examiner.",
        }
        post_response = client.post(url, post_data)
        self.assertEqual(post_response.status_code, 302)

        # Verify updated in database
        t1_eval = WritingTaskEvaluation.objects.get(attempt=self.attempt, task_number=1)
        self.assertEqual(t1_eval.task_achievement, Decimal("8.0"))
        self.assertEqual(t1_eval.examiner, self.staff_examiner)
        self.assertEqual(t1_eval.feedback, "Superb Task 1 response adjusted by head examiner.")

        # Verify overall attempt band score recalculated and updated
        self.attempt.refresh_from_db()
        self.assertGreaterEqual(self.attempt.band_score, initial_band)

    def test_media_file_serving_route(self):
        client = Client()
        test_file_path = os.path.join(settings.MEDIA_ROOT, "test_diagram.png")
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        with open(test_file_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest_data")

        try:
            response = client.get("/media/test_diagram.png")
            self.assertEqual(response.status_code, 200)
            content = b"".join(response.streaming_content)
            response.close()
            self.assertEqual(content, b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest_data")
        finally:
            if os.path.exists(test_file_path):
                os.remove(test_file_path)

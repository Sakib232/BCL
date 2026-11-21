import re
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from bcl.models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption
from bcl.admin import sync_quick_options, parse_option_line

User = get_user_model()

class AdminUXMockBuilderTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="ux_admin",
            email="uxadmin@example.com",
            password="adminpassword123"
        )
        self.client.force_login(self.admin_user)

        self.mock_test = IELTSMockTest.objects.create(
            title="IELTS Test UX Builder",
            test_number=201,
            is_published=True
        )
        self.module = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type="reading",
            duration_minutes=60,
            is_active=True
        )
        self.section = ExamSection.objects.create(
            module=self.module,
            order=1,
            title="Passage 1: Wildlife in New Zealand",
            passage="A New Zealand is home to many unique flightless birds..."
        )

    def test_parse_option_line_formats(self):
        # Letters with dot
        p1 = parse_option_line("A. First option")
        self.assertEqual(p1["key"], "A")
        self.assertEqual(p1["text"], "First option")
        self.assertFalse(p1["is_correct"])

        # Letters with asterisk at end
        p2 = parse_option_line("B. Second option *")
        self.assertEqual(p2["key"], "B")
        self.assertEqual(p2["text"], "Second option")
        self.assertTrue(p2["is_correct"])

        # Letters with [correct]
        p3 = parse_option_line("C) Third option [correct]")
        self.assertEqual(p3["key"], "C")
        self.assertEqual(p3["text"], "Third option")
        self.assertTrue(p3["is_correct"])

        # Lowercase roman numerals for matching headings
        p4 = parse_option_line("iv. Flora biodiversity *")
        self.assertEqual(p4["key"], "iv")
        self.assertEqual(p4["text"], "Flora biodiversity")
        self.assertTrue(p4["is_correct"])

    def test_sync_quick_options_creates_and_updates_question_options(self):
        q = Question.objects.create(
            section=self.section,
            order=1,
            question_type=Question.QuestionType.MCQ,
            question_text="What is discussed in the passage?"
        )

        quick_text = (
            "A. Kiwi bird habitat\n"
            "B. Kakapo conservation *\n"
            "C. Marine life\n"
            "D. Reptiles"
        )
        sync_quick_options(q, quick_text)

        options = list(q.options.order_by("order"))
        self.assertEqual(len(options), 4)
        self.assertEqual(options[0].option_key, "A")
        self.assertEqual(options[0].option_text, "Kiwi bird habitat")
        self.assertFalse(options[0].is_correct)

        self.assertEqual(options[1].option_key, "B")
        self.assertEqual(options[1].option_text, "Kakapo conservation")
        self.assertTrue(options[1].is_correct)

        # Question correct_answer synced
        q.refresh_from_db()
        self.assertEqual(q.correct_answer, "B")

        # Update: remove D, change B to unselected, mark C correct
        updated_text = (
            "A. Kiwi bird habitat\n"
            "B. Kakapo conservation\n"
            "C. Marine life [correct]"
        )
        sync_quick_options(q, updated_text)
        options = list(q.options.order_by("order"))
        self.assertEqual(len(options), 3)
        self.assertFalse(options[1].is_correct)
        self.assertTrue(options[2].is_correct)

    def test_exam_section_change_view_includes_option_and_explanation_fields(self):
        response = self.client.get(reverse("admin:bcl_examsection_change", args=[self.section.pk]))
        self.assertEqual(response.status_code, 200)

        # Quick options field in question inline
        self.assertContains(response, "quick_options")
        self.assertContains(response, "Options / Choices")

        # Rich explanation fields present in section page question inline
        self.assertContains(response, "answer_location")
        self.assertContains(response, "passage_excerpt")
        self.assertContains(response, "what_question_asks")
        self.assertContains(response, "what_passage_says")
        self.assertContains(response, "why_answer")
        self.assertContains(response, "paraphrase")
        self.assertContains(response, "tip")

        # Media JS for quick templates is included
        self.assertIn("admin_question_setter", response.content.decode("utf-8"))

    def test_add_section_pre_selects_module_and_calculates_next_order(self):
        url = reverse("admin:bcl_examsection_add") + f"?module={self.module.pk}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Module is selected
        self.assertContains(response, f'value="{self.module.pk}" selected')
        # Section order 2 is pre-calculated because order 1 exists
        self.assertContains(response, 'value="2"')

    def test_mock_test_page_has_add_section_links(self):
        response = self.client.get(reverse("admin:bcl_ieltsmocktest_change", args=[self.mock_test.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "➕ Add Section")
        self.assertContains(response, f"module={self.module.pk}")

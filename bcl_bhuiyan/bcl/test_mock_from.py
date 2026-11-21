from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from bcl.models import CandidateProfile, MockFromOption
from bcl.forms import CandidateRegistrationForm

User = get_user_model()

class MockFromFeatureTests(TestCase):
    def setUp(self):
        MockFromOption.objects.all().delete()
        MockFromOption.objects.create(name="BCL_Bhuiyan", is_active=True)
        MockFromOption.objects.create(name="Dhanmondi Branch", is_active=True)
        MockFromOption.objects.create(name="Uttara Branch", is_active=True)
        MockFromOption.objects.create(name="Inactive Branch", is_active=False)

    def test_mock_from_choices(self):
        choices = MockFromOption.get_choices()
        choice_values = [c[0] for c in choices]
        self.assertIn("BCL_Bhuiyan", choice_values)
        self.assertIn("Dhanmondi Branch", choice_values)
        self.assertIn("Uttara Branch", choice_values)
        self.assertNotIn("Inactive Branch", choice_values)

    def test_default_profile_mock_from(self):
        user = User.objects.create_user(username="teststud1", password="password123")
        profile = CandidateProfile.objects.create(user=user)
        self.assertEqual(profile.Mock_from, "BCL_Bhuiyan")
        self.assertEqual(profile.mock_from, "BCL_Bhuiyan")

    def test_registration_form_with_default_mock_from(self):
        form_data = {
            "first_name": "Test",
            "last_name": "User",
            "username": "candidate_default",
            "email": "cand_def@example.com",
            "Mock_from": "BCL_Bhuiyan",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        form = CandidateRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(hasattr(user, "candidate_profile"))
        self.assertEqual(user.candidate_profile.Mock_from, "BCL_Bhuiyan")

    def test_registration_form_with_custom_branch(self):
        form_data = {
            "first_name": "Rahim",
            "last_name": "Khan",
            "username": "candidate_dhanmondi",
            "email": "rahim@example.com",
            "Mock_from": "Dhanmondi Branch",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        form = CandidateRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.candidate_profile.Mock_from, "Dhanmondi Branch")

    def test_candidate_registration_view_post(self):
        client = Client()
        register_url = reverse("bcl:register")
        response = client.post(register_url, {
            "first_name": "Karim",
            "last_name": "Ahmed",
            "username": "karim_uttara",
            "email": "karim@example.com",
            "Mock_from": "Uttara Branch",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="karim_uttara")
        self.assertEqual(user.candidate_profile.Mock_from, "Uttara Branch")

    def test_dashboard_navbar_brand_uses_mock_from_and_removes_heading(self):
        # Create approved user in Dhanmondi branch
        user = User.objects.create_user(username="rahim_dhan", password="Password123!")
        CandidateProfile.objects.create(user=user, Mock_from="Dhanmondi Branch", status=CandidateProfile.ApprovalStatus.APPROVED)
        client = Client()
        client.force_login(user)

        res = client.get(reverse("bcl:dashboard"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        # 1. Navbar brand must display user's Mock_from
        self.assertIn("Dhanmondi Branch", content)
        # 2. Logo must remain intact
        self.assertIn("images/bcl.", content)
        # 3. Red marked heading 'Available BCL_Bhuiyan Tests' must be removed
        self.assertNotIn("Available BCL_Bhuiyan Tests", content)
        self.assertNotIn("Available Dhanmondi Branch Tests", content)

    def test_dashboard_navbar_brand_defaults_to_bcl_bhuiyan(self):
        user = User.objects.create_user(username="rahim_def", password="Password123!")
        CandidateProfile.objects.create(user=user, Mock_from="BCL_Bhuiyan", status=CandidateProfile.ApprovalStatus.APPROVED)
        client = Client()
        client.force_login(user)

        res = client.get(reverse("bcl:dashboard"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        self.assertIn("BCL_Bhuiyan", content)
        self.assertIn("images/bcl.", content)
        self.assertNotIn("Available BCL_Bhuiyan Tests", content)

    def test_mock_from_custom_logo_in_navbar_and_meta(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        # 1x1 transparent PNG
        dummy_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        logo_file = SimpleUploadedFile("branch_logo.png", dummy_png, content_type="image/png")
        branch_opt = MockFromOption.objects.create(name="Oxford Academy", image=logo_file, is_active=True)

        user = User.objects.create_user(username="oxford_student", password="Password123!")
        CandidateProfile.objects.create(user=user, Mock_from="Oxford Academy", status=CandidateProfile.ApprovalStatus.APPROVED)

        client = Client()
        client.force_login(user)

        res = client.get(reverse("bcl:dashboard"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        # Custom logo URL is rendered in dashboard navbar
        self.assertIn("Oxford Academy", content)
        self.assertIn(branch_opt.image.name, content)

        # Cleanup uploaded file
        if branch_opt.image and branch_opt.image.storage.exists(branch_opt.image.name):
            branch_opt.image.storage.delete(branch_opt.image.name)

    def test_login_page_no_password_toggler(self):
        client = Client()
        res = client.get(reverse("bcl:login"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertNotIn("eye-toggle", content)
        self.assertNotIn("togglePassword", content)
        self.assertNotIn("eye-icon", content)
        self.assertNotIn("password-wrapper", content)

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

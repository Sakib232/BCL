from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from bcl.models import CandidateProfile, MockFromOption, SubAdminProfile

User = get_user_model()


class AdminCandidateCreationAndSignalTests(TestCase):
    def setUp(self):
        MockFromOption.objects.get_or_create(name="BCL_Bhuiyan", defaults={"is_active": True})
        MockFromOption.objects.get_or_create(name="Dhanmondi Branch", defaults={"is_active": True})
        MockFromOption.objects.get_or_create(name="Uttara Branch", defaults={"is_active": True})

        # Main Admin (Superuser)
        self.super_user = User.objects.create_superuser(
            username="super_admin", email="super@example.com", password="SuperPassword123!"
        )

        # Sub Admin
        self.sub_user = User.objects.create_user(
            username="dhanmondi_subadmin", email="sub@example.com", password="SubPassword123!", is_staff=True
        )
        self.sub_profile = SubAdminProfile.objects.create(
            user=self.sub_user, Mock_from="Dhanmondi Branch", can_manage_mocks=False
        )

    def test_main_admin_can_create_candidate_with_any_mock_from(self):
        client = Client()
        client.force_login(self.super_user)

        add_url = reverse("admin:bcl_candidateprofile_add")
        res = client.get(add_url)
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        # 1. Main admin can view Mock From field
        self.assertIn("Mock From", content)
        # 2. Status and Rejection reason MUST NOT appear while creating account
        self.assertNotIn('name="status"', content)
        self.assertNotIn('name="rejection_reason"', content)

        post_data = {
            "username": "candidate_uttara",
            "password": "CandidatePass123!",
            "first_name": "Uttara",
            "last_name": "Student",
            "email": "uttara.student@example.com",
            "Mock_from": "Uttara Branch",
            "is_active": "on",
        }
        post_res = client.post(add_url, post_data, follow=True)
        self.assertEqual(post_res.status_code, 200)

        # Verify User and CandidateProfile exist
        user = User.objects.filter(username="candidate_uttara").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("CandidatePass123!"))

        profile = CandidateProfile.objects.filter(user=user).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.Mock_from, "Uttara Branch")
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.APPROVED)
        self.assertEqual(profile.reviewed_by, self.super_user)

    def test_subadmin_creates_candidate_locked_to_assigned_mock_from_and_fields_hidden(self):
        client = Client()
        client.force_login(self.sub_user)

        add_url = reverse("admin:bcl_candidateprofile_add")
        res = client.get(add_url)
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        # 1. Mock from is NOT visible to sub-admin while creating account
        self.assertNotIn('name="Mock_from"', content)
        # 2. Status and Rejection reason MUST NOT appear while creating account
        self.assertNotIn('name="status"', content)
        self.assertNotIn('name="rejection_reason"', content)

        post_data = {
            "username": "candidate_dhan",
            "password": "CandidatePass123!",
            "first_name": "Dhan",
            "last_name": "Student",
            "email": "dhan.student@example.com",
            "is_active": "on",
        }
        post_res = client.post(add_url, post_data, follow=True)
        self.assertEqual(post_res.status_code, 200)

        # Verify backend strictly set Dhanmondi Branch
        user = User.objects.filter(username="candidate_dhan").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)

        profile = CandidateProfile.objects.filter(user=user).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.Mock_from, "Dhanmondi Branch")
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.APPROVED)

    def test_status_and_rejection_reason_appear_when_editing(self):
        user = User.objects.create_user(
            username="stud_edit_test", password="Password123!", is_active=True
        )
        profile = CandidateProfile.objects.create(
            user=user, Mock_from="Dhanmondi Branch", status=CandidateProfile.ApprovalStatus.APPROVED
        )

        client = Client()
        client.force_login(self.sub_user)

        change_url = reverse("admin:bcl_candidateprofile_change", args=[profile.pk])
        res = client.get(change_url)
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        # When editing, status and rejection reason DO appear
        self.assertIn('name="status"', content)
        self.assertIn('name="rejection_reason"', content)

    def test_subadmin_cannot_switch_mock_from_on_existing_candidate(self):
        user = User.objects.create_user(
            username="stud_existing", password="Password123!", is_active=True
        )
        profile = CandidateProfile.objects.create(
            user=user, Mock_from="Dhanmondi Branch", status=CandidateProfile.ApprovalStatus.APPROVED
        )

        client = Client()
        client.force_login(self.sub_user)

        change_url = reverse("admin:bcl_candidateprofile_change", args=[profile.pk])
        res = client.get(change_url)
        self.assertEqual(res.status_code, 200)

        # Subadmin attempts to switch Mock_from to "BCL_Bhuiyan"
        post_data = {
            "Mock_from": "BCL_Bhuiyan",
            "status": CandidateProfile.ApprovalStatus.APPROVED,
            "is_active": "on",
        }
        client.post(change_url, post_data, follow=True)

        profile.refresh_from_db()
        self.assertEqual(profile.Mock_from, "Dhanmondi Branch")

    def test_subadmin_can_delete_candidate_approval_and_triggers_user_deletion(self):
        user = User.objects.create_user(
            username="candidate_to_delete", password="Password123!", is_active=True
        )
        profile = CandidateProfile.objects.create(
            user=user, Mock_from="Dhanmondi Branch", status=CandidateProfile.ApprovalStatus.APPROVED
        )

        client = Client()
        client.force_login(self.sub_user)

        # Subadmin can access delete confirmation page
        delete_url = reverse("admin:bcl_candidateprofile_delete", args=[profile.pk])
        get_res = client.get(delete_url)
        self.assertEqual(get_res.status_code, 200)

        # Subadmin confirms delete
        post_res = client.post(delete_url, {"post": "yes"}, follow=True)
        self.assertEqual(post_res.status_code, 200)

        # CandidateProfile must be deleted
        self.assertFalse(CandidateProfile.objects.filter(pk=profile.pk).exists())
        # Corresponding main User must also be deleted
        self.assertFalse(User.objects.filter(username="candidate_to_delete").exists())

    def test_delete_candidate_profile_orm_triggers_user_deletion(self):
        user = User.objects.create_user(
            username="orm_del_user", password="Password123!", is_active=True
        )
        profile = CandidateProfile.objects.create(
            user=user, Mock_from="BCL_Bhuiyan", status=CandidateProfile.ApprovalStatus.APPROVED
        )

        # Deleting profile triggers deleting user via signal
        profile.delete()
        self.assertFalse(User.objects.filter(username="orm_del_user").exists())

    def test_subadmin_cannot_delete_candidate_from_another_branch(self):
        other_user = User.objects.create_user(
            username="uttara_stud", password="Password123!", is_active=True
        )
        other_profile = CandidateProfile.objects.create(
            user=other_user, Mock_from="Uttara Branch", status=CandidateProfile.ApprovalStatus.APPROVED
        )

        client = Client()
        client.force_login(self.sub_user)

        delete_url = reverse("admin:bcl_candidateprofile_delete", args=[other_profile.pk])
        res = client.get(delete_url)
        # Should be 302 Redirect (permission denied message), 403 Forbidden, or 404 Not Found
        self.assertIn(res.status_code, [302, 403, 404])

        # Candidate and user remain intact
        self.assertTrue(CandidateProfile.objects.filter(pk=other_profile.pk).exists())
        self.assertTrue(User.objects.filter(username="uttara_stud").exists())

    def test_signal_triggers_candidate_profile_when_user_created(self):
        new_user = User.objects.create_user(
            username="signal_cand", password="Password123!", is_active=True
        )
        profile = getattr(new_user, "candidate_profile", None)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.Mock_from, "BCL_Bhuiyan")
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.APPROVED)

    def test_signal_syncs_is_active_when_candidate_profile_status_changes(self):
        user = User.objects.create_user(
            username="sync_cand1", password="Password123!", is_active=False
        )
        profile = user.candidate_profile
        self.assertFalse(user.is_active)
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.PENDING)

        profile.status = CandidateProfile.ApprovalStatus.APPROVED
        profile.save()

        user.refresh_from_db()
        self.assertTrue(user.is_active)

        profile.status = CandidateProfile.ApprovalStatus.REJECTED
        profile.save()

        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_signal_syncs_status_when_user_is_active_changes(self):
        user = User.objects.create_user(
            username="sync_cand2", password="Password123!", is_active=True
        )
        profile = user.candidate_profile
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.APPROVED)

        user.is_active = False
        user.save()

        profile.refresh_from_db()
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.PENDING)

        user.is_active = True
        user.save()

        profile.refresh_from_db()
        self.assertEqual(profile.status, CandidateProfile.ApprovalStatus.APPROVED)

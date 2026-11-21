from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from bcl.models import (
    CandidateProfile,
    MockFromOption,
    SubAdminProfile,
    IELTSMockTest,
    ExamModule,
    CandidateAttempt,
    can_manage_mock_tests,
    is_subadmin,
    get_subadmin_mock_from,
)
from bcl.test_helpers import force_verified_staff

User = get_user_model()


class SubAdminAccessTests(TestCase):
    def setUp(self):
        MockFromOption.objects.all().delete()
        MockFromOption.objects.create(name="BCL_Bhuiyan", is_active=True)
        MockFromOption.objects.create(name="Dhanmondi Branch", is_active=True)
        MockFromOption.objects.create(name="Uttara Branch", is_active=True)

        # 1. Main Admin (superuser)
        self.super_admin = User.objects.create_superuser(
            username="main_admin",
            email="main@example.com",
            password="SuperPassword123!",
        )

        # 2. SubAdmin 1: Dhanmondi (Mock Management = False)
        self.subadmin_dhanmondi = User.objects.create_user(
            username="sub_dhanmondi",
            email="dhan@example.com",
            password="SubPassword123!",
            is_staff=True,
            is_superuser=False,
        )
        self.profile_dhanmondi = SubAdminProfile.objects.create(
            user=self.subadmin_dhanmondi,
            Mock_from="Dhanmondi Branch",
            can_manage_mocks=False,
        )

        # 3. SubAdmin 2: Uttara (Mock Management = True)
        self.subadmin_uttara = User.objects.create_user(
            username="sub_uttara",
            email="uttara@example.com",
            password="SubPassword123!",
            is_staff=True,
            is_superuser=False,
        )
        self.profile_uttara = SubAdminProfile.objects.create(
            user=self.subadmin_uttara,
            Mock_from="Uttara Branch",
            can_manage_mocks=True,
        )

        # 4. Students
        # Student Dhanmondi
        self.student_dhanmondi = User.objects.create_user(
            username="stud_dhanmondi", password="Pass123!Password"
        )
        CandidateProfile.objects.create(
            user=self.student_dhanmondi, Mock_from="Dhanmondi Branch"
        )

        # Student Uttara
        self.student_uttara = User.objects.create_user(
            username="stud_uttara", password="Pass123!Password"
        )
        CandidateProfile.objects.create(
            user=self.student_uttara, Mock_from="Uttara Branch"
        )

        # Student Main Branch
        self.student_bcl = User.objects.create_user(
            username="stud_bcl", password="Pass123!Password"
        )
        CandidateProfile.objects.create(
            user=self.student_bcl, Mock_from="BCL_Bhuiyan"
        )

        # 5. Mock Test & Attempts
        self.mock_test = IELTSMockTest.objects.create(
            test_number=99,
            title="Test Mock Subadmin 99",
            is_published=True,
        )
        self.writing_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
        )
        now = timezone.now()
        self.attempt_dhanmondi = CandidateAttempt.objects.create(
            candidate=self.student_dhanmondi,
            module=self.writing_mod,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now - timedelta(minutes=45),
            submitted_at=now,
            expires_at=now + timedelta(hours=1),
        )
        self.attempt_uttara = CandidateAttempt.objects.create(
            candidate=self.student_uttara,
            module=self.writing_mod,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now - timedelta(minutes=45),
            submitted_at=now,
            expires_at=now + timedelta(hours=1),
        )

    def test_subadmin_detection_helpers(self):
        self.assertTrue(is_subadmin(self.subadmin_dhanmondi))
        self.assertFalse(is_subadmin(self.super_admin))
        self.assertEqual(get_subadmin_mock_from(self.subadmin_dhanmondi), "Dhanmondi Branch")
        self.assertIsNone(get_subadmin_mock_from(self.super_admin))
        self.assertFalse(can_manage_mock_tests(self.subadmin_dhanmondi))
        self.assertTrue(can_manage_mock_tests(self.subadmin_uttara))
        self.assertTrue(can_manage_mock_tests(self.super_admin))

    def test_subadmin_cannot_access_subadmin_profile_admin(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)
        url = reverse("admin:bcl_subadminprofile_changelist")
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_access_subadmin_profile_admin(self):
        client = Client()
        force_verified_staff(client, self.super_admin)
        url = reverse("admin:bcl_subadminprofile_changelist")
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_mock_test_management_restriction(self):
        client = Client()
        # Subadmin without authorization cannot view/edit mock tests
        force_verified_staff(client, self.subadmin_dhanmondi)
        res = client.get(reverse("admin:bcl_ieltsmocktest_changelist"))
        self.assertEqual(res.status_code, 403)

        # Subadmin with authorization CAN view/edit mock tests
        client2 = Client()
        force_verified_staff(client2, self.subadmin_uttara)
        res2 = client2.get(reverse("admin:bcl_ieltsmocktest_changelist"))
        self.assertEqual(res2.status_code, 200)

    def test_admin_results_hub_branch_scoping(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)
        res = client.get(reverse("bcl:admin_results_hub"))
        self.assertEqual(res.status_code, 200)
        attempts = list(res.context["attempts"])
        # Should only contain Dhanmondi attempt
        self.assertIn(self.attempt_dhanmondi, attempts)
        self.assertNotIn(self.attempt_uttara, attempts)

    def test_admin_attempt_review_branch_restriction(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)

        # Allowed for own branch
        res_own = client.get(reverse("bcl:admin_attempt_review", args=[self.attempt_dhanmondi.id]))
        self.assertEqual(res_own.status_code, 200)

        # Denied (403) for other branch
        res_other = client.get(reverse("bcl:admin_attempt_review", args=[self.attempt_uttara.id]))
        self.assertEqual(res_other.status_code, 403)

    def test_writing_review_list_branch_scoping(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)
        res = client.get(reverse("bcl:writing_review_list"))
        self.assertEqual(res.status_code, 200)
        attempts = list(res.context["attempts"])
        self.assertIn(self.attempt_dhanmondi, attempts)
        self.assertNotIn(self.attempt_uttara, attempts)

    def test_writing_review_detail_branch_restriction(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)

        # Allowed for own branch
        res_own = client.get(reverse("bcl:writing_review_detail", args=[self.attempt_dhanmondi.id]))
        self.assertEqual(res_own.status_code, 200)

        # Denied (403) for other branch
        res_other = client.get(reverse("bcl:writing_review_detail", args=[self.attempt_uttara.id]))
        self.assertEqual(res_other.status_code, 403)

    def test_admin_attempt_delete_branch_restriction(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)

        # Attempt to delete Uttara student's attempt -> Denied 403
        res = client.post(reverse("bcl:admin_attempt_delete", args=[self.attempt_uttara.id]))
        self.assertEqual(res.status_code, 403)
        self.assertTrue(CandidateAttempt.objects.filter(id=self.attempt_uttara.id).exists())

    def test_user_admin_scoped_for_subadmin(self):
        client = Client()
        force_verified_staff(client, self.subadmin_dhanmondi)
        res = client.get(reverse("admin:auth_user_changelist"))
        self.assertEqual(res.status_code, 200)
        user_list = list(res.context["cl"].queryset)
        # Should only see their branch student
        self.assertIn(self.student_dhanmondi, user_list)
        # Should NEVER see main admin or other branch students
        self.assertNotIn(self.super_admin, user_list)
        self.assertNotIn(self.student_uttara, user_list)
        self.assertNotIn(self.student_bcl, user_list)

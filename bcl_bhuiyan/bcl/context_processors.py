from django.conf import settings


def platform_branding(request):
    default_brand = getattr(settings, "APP_NAME", "BCL_Bhuiyan")
    user_branch = default_brand
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        cand_prof = getattr(user, "candidate_profile", None)
        if cand_prof and getattr(cand_prof, "Mock_from", None):
            user_branch = cand_prof.Mock_from
        else:
            sub_prof = getattr(user, "subadmin_profile", None)
            if sub_prof and getattr(sub_prof, "Mock_from", None):
                user_branch = sub_prof.Mock_from

    return {
        "platform_name": user_branch or default_brand,
        "brand_name": user_branch or default_brand,
        "user_mock_from": user_branch or default_brand,
        "default_platform_name": default_brand,
    }

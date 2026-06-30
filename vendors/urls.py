from django.urls import path

from vendors import views

urlpatterns = [
    path("otp/send/", views.send_vendor_otp, name="vendor-otp-send"),
    path("otp/verify/", views.verify_vendor_otp, name="vendor-otp-verify"),
    path("profile/", views.save_vendor_profile, name="vendor-profile-save"),
    path("courses/", views.create_vendor_course, name="vendor-course-create"),
    path("courses/<int:course_id>/", views.vendor_course_detail, name="vendor-course-detail"),
    path("courses/<int:course_id>/matches/", views.vendor_course_matches, name="vendor-course-matches"),
]

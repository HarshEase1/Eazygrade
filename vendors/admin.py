from django.contrib import admin

from vendors.models import VendorCourse, VendorInstitute


class VendorCourseInline(admin.TabularInline):
    model = VendorCourse
    extra = 0


@admin.register(VendorInstitute)
class VendorInstituteAdmin(admin.ModelAdmin):
    inlines = [VendorCourseInline]
    list_display = ["name", "official_email", "provider_type", "city", "state", "is_email_verified"]
    list_filter = ["provider_type", "state", "is_email_verified"]
    search_fields = ["name", "official_email", "city", "state"]


@admin.register(VendorCourse)
class VendorCourseAdmin(admin.ModelAdmin):
    list_display = ["title", "vendor", "level", "mode", "duration"]
    list_filter = ["level", "mode"]
    search_fields = ["title", "vendor__name", "subjects", "syllabus"]

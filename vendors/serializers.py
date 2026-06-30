from rest_framework import serializers

from vendors.models import VendorCourse, VendorInstitute


class VendorCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorCourse
        fields = [
            "id",
            "title",
            "level",
            "mode",
            "duration",
            "subjects",
            "seats",
            "fees",
            "syllabus",
            "ideal_student",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class VendorInstituteSerializer(serializers.ModelSerializer):
    courses = VendorCourseSerializer(many=True, read_only=True)

    class Meta:
        model = VendorInstitute
        fields = [
            "id",
            "official_email",
            "is_email_verified",
            "name",
            "provider_type",
            "website",
            "city",
            "state",
            "contact_name",
            "contact_phone",
            "description",
            "image_url",
            "courses",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

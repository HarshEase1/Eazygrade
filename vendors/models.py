from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField


class VendorInstitute(models.Model):
    official_email = models.EmailField(unique=True, db_index=True)
    is_email_verified = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    provider_type = models.CharField(max_length=100)
    website = models.URLField(max_length=1000, blank=True, default="")
    city = models.CharField(max_length=150)
    state = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=150, blank=True, default="")
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    description = models.TextField()
    image_url = models.URLField(max_length=1000, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.official_email}"


class VendorCourse(models.Model):
    vendor = models.ForeignKey(
        VendorInstitute,
        on_delete=models.CASCADE,
        related_name="courses",
    )
    title = models.CharField(max_length=255)
    level = models.CharField(max_length=100)
    mode = models.CharField(max_length=100)
    duration = models.CharField(max_length=100, blank=True, default="")
    subjects = models.TextField()
    seats = models.CharField(max_length=50, blank=True, default="")
    fees = models.CharField(max_length=100, blank=True, default="")
    syllabus = models.TextField()
    ideal_student = models.TextField(blank=True, default="")
    search_vector = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["level"]),
            models.Index(fields=["mode"]),
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.vendor.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        VendorCourse.objects.filter(pk=self.pk).update(
            search_vector=(
                SearchVector("title", weight="A")
                + SearchVector("subjects", weight="A")
                + SearchVector("syllabus", weight="B")
                + SearchVector("ideal_student", weight="C")
            )
        )

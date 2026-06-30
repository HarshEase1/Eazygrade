from django.db import models
from django.utils.text import slugify
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField

class UniversityType(models.TextChoices):
    CENTRAL = "central", "Central University"
    STATE = "state", "State University"
    DEEMED = "deemed", "Deemed to be University"
    PRIVATE = "private", "State Private University"
    FAKE = "fake", "Fake University"
    UNKNOWN = "unknown", "Unknown"


class DataSource(models.TextChoices):
    UGC = "ugc", "University Grants Commission"
    AISHE = "aishe", "All India Survey on Higher Education"
    UGC_DEB = "ugc_deb", "UGC Distance Education Bureau"
    NIRF = "nirf", "National Institutional Ranking Framework"
    
class University(models.Model):
    name = models.CharField(max_length=500)

    slug = models.SlugField(
        max_length=600,
        db_index=True,
        blank=True,
    )

    university_type = models.CharField(
        max_length=30,
        choices=UniversityType.choices,
        default=UniversityType.UNKNOWN,
        db_index=True,
    )

    address = models.TextField(blank=True, default="")
    state = models.CharField(max_length=150, blank=True, default="", db_index=True)
    zip_code = models.CharField(max_length=100, blank=True, default="")

    ugc_status = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Example: 2(f), 12(B), Section-III etc.",
    )

    website_url = models.URLField(max_length=1000, blank=True, default="")

    source = models.CharField(
        max_length=50,
        choices=DataSource.choices,
        default=DataSource.UGC,
        db_index=True,
    )

    source_url = models.URLField(max_length=1000, blank=True, default="")
    source_sr_no = models.PositiveIntegerField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    aishe_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
    )

    district = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
    )

    aishe_website = models.URLField(
        max_length=1000,
        blank=True,
        default="",
    )

    year_of_establishment = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )

    location = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Example: Rural / Urban",
    )
    is_active = models.BooleanField(default=True)
    is_fake = models.BooleanField(default=False, db_index=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["state"]),
            models.Index(fields=["university_type"]),
            models.Index(fields=["source"]),
            models.Index(fields=["is_fake"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["name", "state", "university_type"],
                name="unique_university_name_state_type",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.state}-{self.university_type}")[:600]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    

class UGCDEBProgramme(models.Model):
    year = models.CharField(max_length=20, db_index=True)
    session = models.CharField(max_length=100, blank=True, default="")

    mode = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
        help_text="Example: Online (Entitled), ODL (Recognised)",
    )

    hei_name = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Higher Education Institution name from UGC-DEB",
    )

    hei_type = models.CharField(max_length=150, blank=True, default="")
    state = models.CharField(max_length=150, blank=True, default="", db_index=True)

    program_name = models.CharField(max_length=500, db_index=True)

    level = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="UG / PG",
    )

    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deb_programmes",
        help_text="Matched University from UGC master data, if found",
    )

    source = models.CharField(max_length=50, default="ugc_deb", db_index=True)
    source_file = models.CharField(max_length=255, blank=True, default="")
    raw_data = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["year"]),
            models.Index(fields=["mode"]),
            models.Index(fields=["state"]),
            models.Index(fields=["level"]),
            models.Index(fields=["hei_name"]),
            models.Index(fields=["program_name"]),
            models.Index(fields=["university"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["year", "mode", "hei_name", "state", "program_name", "level"],
                name="unique_ugc_deb_programme",
            )
        ]

    def __str__(self):
        return f"{self.program_name} - {self.hei_name}"
    
class NIRFCategory(models.TextChoices):
    OVERALL = "overall", "Overall"
    UNIVERSITY = "university", "University"
    COLLEGE = "college", "College"
    ENGINEERING = "engineering", "Engineering"
    MANAGEMENT = "management", "Management"
    MEDICAL = "medical", "Medical"
    LAW = "law", "Law"
    PHARMACY = "pharmacy", "Pharmacy"


class NIRFRanking(models.Model):
    year = models.PositiveIntegerField(db_index=True, default=2025)

    category = models.CharField(
        max_length=50,
        choices=NIRFCategory.choices,
        db_index=True,
    )

    institute_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Example: IR-O-U-0456",
    )

    name = models.CharField(max_length=500, db_index=True)

    city = models.CharField(max_length=150, blank=True, default="", db_index=True)
    state = models.CharField(max_length=150, blank=True, default="", db_index=True)

    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        db_index=True,
    )

    rank = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text="Can be normal rank like 1 or rank-band like 101-150",
    )

    tlr_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rpc_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    go_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    oi_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    perception_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    pdf_url = models.URLField(max_length=1000, blank=True, default="")
    graph_url = models.URLField(max_length=1000, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")

    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nirf_rankings",
        help_text="Matched University from UGC/AISHE master data, if found",
    )

    raw_data = models.JSONField(default=dict, blank=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["year"]),
            models.Index(fields=["category"]),
            models.Index(fields=["institute_id"]),
            models.Index(fields=["name"]),
            models.Index(fields=["state"]),
            models.Index(fields=["city"]),
            models.Index(fields=["score"]),
            models.Index(fields=["rank"]),
            models.Index(fields=["university"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["year", "category", "institute_id"],
                name="unique_nirf_year_category_institute",
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.category} - {self.rank}"
    

class SearchEntityType(models.TextChoices):
    UNIVERSITY = "university", "University"
    UGC_DEB_PROGRAMME = "ugc_deb_programme", "UGC-DEB Programme"
    NIRF_RANKING = "nirf_ranking", "NIRF Ranking"


class SearchDocument(models.Model):
    entity_type = models.CharField(
        max_length=50,
        choices=SearchEntityType.choices,
        db_index=True,
    )

    source_id = models.PositiveBigIntegerField(db_index=True)

    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_documents",
    )

    ugc_deb_programme = models.ForeignKey(
        UGCDEBProgramme,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_documents",
    )

    nirf_ranking = models.ForeignKey(
        NIRFRanking,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_documents",
    )

    title = models.CharField(max_length=700, db_index=True)
    subtitle = models.CharField(max_length=1000, blank=True, default="")
    body = models.TextField(blank=True, default="")

    state = models.CharField(max_length=150, blank=True, default="", db_index=True)
    district = models.CharField(max_length=150, blank=True, default="", db_index=True)
    city = models.CharField(max_length=150, blank=True, default="", db_index=True)

    category = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Example: nirf overall, ugc university, ugc-deb online programme",
    )

    level = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text="Example: UG / PG",
    )

    mode = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
        help_text="Example: Online / ODL / Regular",
    )

    year = models.CharField(max_length=20, blank=True, default="", db_index=True)

    rank = models.CharField(max_length=50, blank=True, default="", db_index=True)
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        db_index=True,
    )

    source = models.CharField(max_length=100, blank=True, default="", db_index=True)
    source_url = models.URLField(max_length=1000, blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)

    search_vector = SearchVectorField(null=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            GinIndex(fields=["search_vector"], name="search_document_vector_gin_idx"),
            models.Index(fields=["entity_type", "source_id"]),
            models.Index(fields=["state"]),
            models.Index(fields=["city"]),
            models.Index(fields=["category"]),
            models.Index(fields=["mode"]),
            models.Index(fields=["level"]),
            models.Index(fields=["year"]),
            models.Index(fields=["rank"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "source_id"],
                name="unique_search_document_entity_source",
            )
        ]

    def __str__(self):
        return f"{self.entity_type}: {self.title}"
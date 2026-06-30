from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recommendations", "0002_alter_rankedcourserecommendation_match_percentage"),
    ]

    operations = [
        migrations.CreateModel(
            name="DemoProgramme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("program_name", models.CharField(max_length=180, unique=True)),
                ("provider", models.CharField(db_index=True, max_length=180)),
                ("degree_type", models.CharField(db_index=True, max_length=40)),
                ("duration", models.CharField(db_index=True, max_length=80)),
                ("fee_range", models.CharField(max_length=120)),
                ("min_fee", models.PositiveIntegerField(db_index=True, default=0)),
                ("max_fee", models.PositiveIntegerField(db_index=True, default=0)),
                ("mode", models.CharField(db_index=True, max_length=80)),
                ("career_tags", models.JSONField(blank=True, default=list)),
                ("background_tags", models.JSONField(blank=True, default=list)),
                ("degree_tags", models.JSONField(blank=True, default=list)),
                ("duration_years", models.DecimalField(decimal_places=1, default=3, max_digits=4)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["program_name"],
            },
        ),
        migrations.AddIndex(
            model_name="demoprogramme",
            index=models.Index(fields=["degree_type", "mode"], name="recommendat_degree__0c4628_idx"),
        ),
        migrations.AddIndex(
            model_name="demoprogramme",
            index=models.Index(fields=["is_active", "program_name"], name="recommendat_is_acti_0166f4_idx"),
        ),
    ]

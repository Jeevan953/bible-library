from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bible", "0003_tamildictionaryentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="HitchcockName",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source_id",
                    models.CharField(max_length=64, unique=True),
                ),
                (
                    "name",
                    models.CharField(
                        db_index=True,
                        max_length=200,
                    ),
                ),
                ("definition", models.TextField()),
            ],
            options={
                "verbose_name": "Hitchcock Bible name",
                "verbose_name_plural": "Hitchcock Bible names",
                "ordering": ["name", "source_id"],
            },
        ),
    ]

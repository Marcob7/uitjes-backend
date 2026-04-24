# Generated manually for phase 1 backend expansion.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0006_event_address_event_latitude_event_longitude_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
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
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(unique=True)),
                ("kind", models.CharField(blank=True, max_length=32, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Tag",
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
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(unique=True)),
                (
                    "facet",
                    models.CharField(
                        choices=[
                            ("audience", "Audience"),
                            ("moment", "Moment"),
                            ("vibe", "Vibe"),
                            ("weather", "Weather"),
                            ("feature", "Feature"),
                            ("theme", "Theme"),
                        ],
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["facet", "name"],
            },
        ),
        migrations.AddField(
            model_name="city",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="city",
            name="hero_image_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="city",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="venue",
            name="postal_code",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="venue",
            name="slug",
            field=models.SlugField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="venue",
            name="venue_type",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="venue",
            name="website",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="events",
                to="events.category",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="editor_rating",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="image_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="indoor_outdoor",
            field=models.CharField(
                blank=True,
                choices=[
                    ("indoor", "Binnen"),
                    ("outdoor", "Buiten"),
                    ("both", "Binnen & buiten"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="is_featured",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="event",
            name="is_hidden_gem",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="event",
            name="kind",
            field=models.CharField(
                choices=[
                    ("event", "Event"),
                    ("activity", "Activity"),
                    ("festival", "Festival"),
                    ("place", "Place"),
                    ("food_drink", "Food & Drink"),
                ],
                default="event",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="opening_hours_text",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="price_max",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="price_note",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="raw_date_text",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="slug",
            field=models.SlugField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="status_override",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="summary",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="events", to="events.tag"),
        ),
        migrations.AddField(
            model_name="event",
            name="ticket_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="weather_suitability",
            field=models.CharField(
                blank=True,
                choices=[
                    ("all", "All weather"),
                    ("sun", "Good weather"),
                    ("rain", "Rain proof"),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]

from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0008_phase1_seed_and_slugs"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsletterSignup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("preferred_city", models.CharField(blank=True, max_length=120)),
                ("source", models.CharField(blank=True, max_length=80)),
                ("is_active", models.BooleanField(default=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("unsubscribed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="newslettersignup",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="uniq_newsletter_signup_email_lower",
            ),
        ),
    ]

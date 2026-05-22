from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0009_newslettersignup"),
    ]

    operations = [
        migrations.AddField(
            model_name="newslettersignup",
            name="frequency",
            field=models.CharField(
                choices=[
                    ("weekly", "Wekelijks"),
                    ("weekend", "Alleen weekendtips"),
                    ("monthly", "Maandelijks"),
                ],
                default="weekly",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="newslettersignup",
            name="interests",
            field=models.JSONField(blank=True, default=list),
        ),
    ]

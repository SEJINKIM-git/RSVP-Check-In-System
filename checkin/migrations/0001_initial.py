from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="GuestParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("unid", models.CharField(blank=True, max_length=100)),
                ("major", models.CharField(blank=True, max_length=255)),
                ("checked_in", models.BooleanField(default=True)),
                ("checkin_time", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-checkin_time", "-created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="RegisteredParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("submission_order", models.PositiveIntegerField()),
                ("name", models.CharField(max_length=255)),
                ("unid", models.CharField(max_length=100, unique=True)),
                ("major", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("checked_in", models.BooleanField(default=False)),
                ("checkin_time", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["submission_order", "id"],
            },
        ),
    ]

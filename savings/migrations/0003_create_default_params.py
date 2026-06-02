from django.db import migrations

def create_default_params(apps, schema_editor):
    Parameter = apps.get_model("savings", "Parameter")

    defaults = [
        {
            "key": "min_initial_deposit",
            "value": "1000000",
        },
        {
            "key": "min_additional_deposit",
            "value": "100000",
        },
        {
            "key": "min_deposit_days_flexible",
            "value": "15",
        },
    ]

    for item in defaults:
        Parameter.objects.get_or_create(
            key=item["key"],
            defaults={
                "value": item["value"]
            }
        )

class Migration(migrations.Migration):

    dependencies = [
        ("savings", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_params),
    ]
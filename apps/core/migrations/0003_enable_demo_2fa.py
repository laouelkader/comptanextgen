from django.db import migrations


DEMO_EMAILS = [
    "admin@comptanextgen.fr",
    "gerant.alpha@alpha.fr",
    "comptable.alpha@alpha.fr",
    "collab.alpha@alpha.fr",
    "gerant.beta@beta.fr",
    "comptable.beta@beta.fr",
    "gerant.gamma@gamma.fr",
    "comptable.gamma@gamma.fr",
]


def enable_demo_2fa(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(email__in=DEMO_EMAILS).update(two_factor_enabled=True)


def disable_demo_2fa(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(email__in=DEMO_EMAILS).update(two_factor_enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_demo_accounts"),
    ]

    operations = [
        migrations.RunPython(enable_demo_2fa, disable_demo_2fa),
    ]

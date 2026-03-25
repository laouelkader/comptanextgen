# Comptes de démonstration — mot de passe commun : Aa!234567

from django.contrib.auth.hashers import make_password
from django.db import migrations

DEMO_PASSWORD = "Aa!234567"

COMPANIES = ("Alpha SARL", "Beta SAS", "Gamma EURL")


def _create(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    User = apps.get_model("core", "User")

    by_name = {}
    for nom in COMPANIES:
        company, _ = Company.objects.get_or_create(nom=nom, defaults={"is_active": True})
        by_name[nom] = company

    pwd = make_password(DEMO_PASSWORD)

    specs = [
        (
            "admin@comptanextgen.fr",
            {
                "role": "CABINET_ADMIN",
                "company": None,
                "is_staff": True,
                "is_superuser": True,
            },
        ),
        ("gerant.alpha@alpha.fr", {"role": "MANAGER", "company": by_name["Alpha SARL"]}),
        ("comptable.alpha@alpha.fr", {"role": "ACCOUNTANT", "company": by_name["Alpha SARL"]}),
        ("collab.alpha@alpha.fr", {"role": "COLLABORATOR", "company": by_name["Alpha SARL"]}),
        ("gerant.beta@beta.fr", {"role": "MANAGER", "company": by_name["Beta SAS"]}),
        ("comptable.beta@beta.fr", {"role": "ACCOUNTANT", "company": by_name["Beta SAS"]}),
        ("gerant.gamma@gamma.fr", {"role": "MANAGER", "company": by_name["Gamma EURL"]}),
        ("comptable.gamma@gamma.fr", {"role": "ACCOUNTANT", "company": by_name["Gamma EURL"]}),
    ]

    for email, extra in specs:
        company = extra.get("company")
        defaults = {
            "username": "",
            "password": pwd,
            "is_active": True,
            "is_staff": extra.get("is_staff", False),
            "is_superuser": extra.get("is_superuser", False),
            "role": extra["role"],
            "company": company,
            "two_factor_enabled": False,
        }
        User.objects.update_or_create(email=email, defaults=defaults)


def _remove(apps, schema_editor):
    User = apps.get_model("core", "User")
    Company = apps.get_model("core", "Company")

    emails = [
        "admin@comptanextgen.fr",
        "gerant.alpha@alpha.fr",
        "comptable.alpha@alpha.fr",
        "collab.alpha@alpha.fr",
        "gerant.beta@beta.fr",
        "comptable.beta@beta.fr",
        "gerant.gamma@gamma.fr",
        "comptable.gamma@gamma.fr",
    ]
    User.objects.filter(email__in=emails).delete()
    Company.objects.filter(nom__in=COMPANIES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_create, _remove),
    ]

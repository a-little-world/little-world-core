from cookie_consent.models import Cookie, CookieGroup
from django.core.management.base import BaseCommand

from management.tasks import (
    ANALYTICS_COOKIE_DESCRIPTIONS,
    ANALYTICS_GROUP_DESCRIPTION,
)


class Command(BaseCommand):
    help = (
        "Update the descriptions of the default analytics cookie group and its cookies, "
        "matching create_default_cookie_groups(). Safe to re-run."
    )

    def handle(self, *args, **options):
        updated = 0

        group = CookieGroup.objects.filter(varname="analytics").first()
        if group is None:
            self.stdout.write(self.style.WARNING("No 'analytics' cookie group found."))
            self.stdout.write(self.style.SUCCESS(f"Done, {updated} description(s) updated."))
            return

        if group.description != ANALYTICS_GROUP_DESCRIPTION:
            group.description = ANALYTICS_GROUP_DESCRIPTION
            group.save(update_fields=["description"])
            updated += 1
            self.stdout.write("Updated analytics cookie group description.")
        else:
            self.stdout.write("Analytics cookie group description already up to date.")

        for name, description in ANALYTICS_COOKIE_DESCRIPTIONS.items():
            cookie = Cookie.objects.filter(cookiegroup=group, name=name).first()
            if cookie is None:
                self.stdout.write(self.style.WARNING(f"No '{name}' found in the analytics group."))
            elif cookie.description != description:
                cookie.description = description
                cookie.save(update_fields=["description"])
                updated += 1
                self.stdout.write(f"Updated {name} description.")
            else:
                self.stdout.write(f"{name} description already up to date.")

        self.stdout.write(self.style.SUCCESS(f"Done, {updated} description(s) updated."))

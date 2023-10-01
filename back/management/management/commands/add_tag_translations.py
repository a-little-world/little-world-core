from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, **options):
        import polib
        import string
        import glob

        all_locale = [a for a in glob.glob(
            f"./*/locale/*/*/*") if a.endswith(".po")]
        print("Updated: ", all_locale)
        # Now this smartly auto populates the 'tag' language
        # This will use pgettext(context, string) everywher where we wan't a context tag!
        # For all these translations we can auto detemine the 'tag'
        for pofile in all_locale:
            if f"/locale/tag" in pofile:
                print("Parsing: ", pofile)
                po = polib.pofile(pofile)
                valid_entries = [e for e in po if not e.obsolete]
                for entry in valid_entries:
                    if hasattr(entry, "msgctxt") and entry.msgctxt is not None:
                        #print(entry.msgctxt, entry.msgid, entry.msgstr)
                        # There might be python formaters in the string!
                        # We could ignore them, but I'll just patch them in!
                        format_opts = list(string.Formatter().parse(entry.msgid))
                        #print("ALL FORMAT OPTS: \n", format_opts)
                        formattable_args = [arg[1] for arg in format_opts if (arg[1] != "" and (not (arg[1] is None)))]
                        
                        if entry.msgstr.startswith("\n"):
                            print("SLASH N FOUND!!\n\n")
                        entry.msgstr = entry.msgctxt

                        if len(formattable_args) > 0:
                            entry.msgstr += "|" + ",".join([ f"{{{arg}}}" for arg in formattable_args])

                        print("---> ", entry.msgctxt, entry.msgid, entry.msgstr, "\n\n", format_opts, "\n", formattable_args)
                po.save()
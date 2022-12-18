# merges all fixtures files into one file
import json
ALL_FIXTURES = []
fixture_files = [
    "old_db_fixtures/user_management_models.json",
    "old_db_fixtures/messages_and_dialogs_db.json",
    "old_db_fixtures/cookie_consent_and_log_items.json"
]

COMPLETE_OUTPUT_FIXTURE = "old_db_fixtures/complete_fixture.json"

for f in fixture_files:
    with open(f) as f:
        ALL_FIXTURES += json.load(f)

with open(COMPLETE_OUTPUT_FIXTURE, "w") as f:
    json.dump(ALL_FIXTURES, f)

import datetime as DT
from tracking.models import Event

_filter = "resetpw/confirm"
today = DT.date.today()
week_ago = today - DT.timedelta(days=4)

events = Event.objects.filter(
    time__gte=week_ago
)
c = events.count()
print("C", c)

f = []
for e in events:
    c -= 1
    print(c)
    if _filter in str(e.metadata):
        f.append(e)

for _f in f:
    print(_f.metadata)

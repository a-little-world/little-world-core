import json
from dataclasses import dataclass
from typing import OrderedDict


@dataclass
class EmailConfigEmail:
    id: str
    sender_id: str
    category_id: str
    subject: str
    template: str
    theme: str

    def to_dict(self):
        return {"sender_id": self.sender_id, "category_id": self.category_id, "subject": self.subject, "template": self.template, "theme": self.theme}


@dataclass
class EmailConfigCategory:
    id: str
    name: str
    description: str
    unsubscribe: bool


@dataclass
class EmailConfigParameter:
    id: str
    lookup: str
    depends_on: "list[str]"


@dataclass
class EmailConfigDependency:
    id: str
    query_id_field: str


@dataclass
class EmailsConfig:
    categories: OrderedDict[str, EmailConfigCategory]
    emails: OrderedDict[str, EmailConfigEmail]
    senders: OrderedDict[str, str]
    parameters: OrderedDict[str, EmailConfigParameter]
    dependencies: OrderedDict[str, EmailConfigDependency]

    def from_dict(data):
        return EmailsConfig(
            categories=OrderedDict({k: EmailConfigCategory(**v) for k, v in data.get("categories", {}).items()}),
            emails=OrderedDict({k: EmailConfigEmail(**v) for k, v in data.get("emails", {}).items()}),
            senders=OrderedDict(data.get("senders", {})),
            parameters=OrderedDict({k: EmailConfigParameter(**v) for k, v in data.get("parameters", {}).items()}),
            dependencies=OrderedDict({k: EmailConfigDependency(**v) for k, v in data.get("dependencies", {}).items()}),
        )

    def to_dict(self):
        return {"categories": {k: v.__dict__ for k, v in self.categories.items()}, "emails": {k: v.__dict__ for k, v in self.emails.items()}, "senders": self.senders, "parameters": {k: v.__dict__ for k, v in self.parameters.items()}, "dependencies": {k: v.__dict__ for k, v in self.dependencies.items()}}


EMAILS_CONFIG = {}
with open("emails/emails.json", "r") as f:
    EMAILS_CONFIG = json.load(f)


EMAILS_CONFIG = EmailsConfig.from_dict(EMAILS_CONFIG)

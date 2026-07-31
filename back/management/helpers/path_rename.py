import os
from uuid import uuid4

from django.utils.deconstruct import deconstructible


@deconstructible
class PathRename(object):
    def __init__(self, path, unique=False):
        self.sub_path = path
        # When True, always use a UUID filename so replacements do not overwrite
        # the same object key (important for S3/MinIO with long Cache-Control).
        self.unique = unique

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1]

        if self.unique or not instance.pk:
            filename = "{}.{}".format(uuid4().hex, ext)
        else:
            filename = "{}.{}".format(instance.pk, ext)
        return os.path.join(self.sub_path, filename)

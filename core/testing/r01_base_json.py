"""Exact temporal JSON, registered only by the isolated R-01 Base settings."""
from datetime import datetime, time

from django.core.serializers.json import (
    Deserializer, DjangoJSONEncoder, Serializer as DjangoJSONSerializer,
)
from django.utils.timezone import is_aware


class ExactTemporalEncoder(DjangoJSONEncoder):
    def default(self, value):
        if isinstance(value, datetime):
            return value.isoformat(timespec="microseconds")
        if isinstance(value, time):
            if is_aware(value):
                raise ValueError("JSON cannot represent timezone-aware times.")
            return value.isoformat(timespec="microseconds")
        return super().default(value)


class Serializer(DjangoJSONSerializer):
    def _init_options(self):
        super()._init_options()
        # This format must never silently fall back to the millisecond encoder.
        self.json_kwargs["cls"] = ExactTemporalEncoder

"""
NEXUS IoT - Input Validation Schemas
Batch 8: + Bulk import schema
"""
import math
import re

from marshmallow import Schema, fields, validate, ValidationError

# UID kartu RFID: hex (boleh dengan awalan 0x seperti contoh firmware "0x010dd605"),
# titik dua / dash sebagai pemisah. Huruf besar/kecil dipertahankan apa adanya
# agar tetap cocok dengan data kartu yang sudah terdaftar.
UID_PATTERN = re.compile(r'^(0[xX])?[0-9A-Fa-f:\-]{4,32}$')
SENSOR_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_]{1,32}$')
SENSOR_TYPE_PATTERN = re.compile(r'^[A-Za-z0-9_\-]{1,32}$')
MAX_SENSOR_KEYS = 32
MAX_SENSOR_STRING_LEN = 64


def normalize_uid(value):
    """Return UID (string, sudah di-strip) bila valid, selain itu None.

    Hanya string yang diterima; angka (mis. 123) ditolak.
    """
    if not isinstance(value, str):
        return None
    uid = value.strip()
    return uid if UID_PATTERN.match(uid) else None


def validate_sensor_data(data):
    """`data` harus dict datar: key aman, nilai angka finite / bool / string pendek."""
    if not isinstance(data, dict):
        raise ValidationError('data harus berupa object')
    if len(data) > MAX_SENSOR_KEYS:
        raise ValidationError(f'data maksimal {MAX_SENSOR_KEYS} key')
    for key, value in data.items():
        if not isinstance(key, str) or not SENSOR_KEY_PATTERN.match(key):
            raise ValidationError(
                'Key data hanya boleh huruf, angka, underscore (1-32 karakter)')
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValidationError(f"Nilai '{key}' harus angka yang valid (bukan NaN/Infinity)")
            continue
        if isinstance(value, str):
            if len(value) > MAX_SENSOR_STRING_LEN:
                raise ValidationError(
                    f"Nilai '{key}' maksimal {MAX_SENSOR_STRING_LEN} karakter")
            continue
        raise ValidationError(f"Nilai '{key}' harus angka, boolean, atau string pendek")


class DeviceCreateSchema(Schema):
    device_id = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=64),
            validate.Regexp(r'^[a-zA-Z0-9_\-]+$',
                            error='Device ID hanya boleh huruf, angka, dash, dan underscore')
        ]
    )
    device_name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    device_type = fields.Str(load_default='ESP32', validate=validate.Length(max=32))
    location = fields.Str(load_default='', validate=validate.Length(max=255))
    description = fields.Str(load_default='', validate=validate.Length(max=1000))
    firmware_version = fields.Str(load_default='', validate=validate.Length(max=64))
    expected_interval = fields.Int(load_default=60, validate=validate.Range(min=10, max=86400))
    offline_timeout = fields.Raw(load_default=None, allow_none=True)
    offline_alert_severity = fields.Str(
        load_default='danger',
        validate=validate.OneOf(['info', 'warning', 'danger'])
    )
    alert_rules = fields.Dict(load_default=None, allow_none=True)


class DeviceUpdateSchema(Schema):
    device_name = fields.Str(validate=validate.Length(min=1, max=128))
    device_type = fields.Str(validate=validate.Length(max=32))
    location = fields.Str(validate=validate.Length(max=255))
    description = fields.Str(validate=validate.Length(max=1000))
    firmware_version = fields.Str(validate=validate.Length(max=64))
    latitude = fields.Float(validate=validate.Range(min=-90, max=90))
    longitude = fields.Float(validate=validate.Range(min=-180, max=180))
    # None = kembali ke mode otomatis (auto-detect)
    expected_interval = fields.Int(allow_none=True, validate=validate.Range(min=10, max=86400))
    offline_timeout = fields.Raw(allow_none=True)
    offline_alert_severity = fields.Str(validate=validate.OneOf(['info', 'warning', 'danger']))
    alert_rules = fields.Dict(allow_none=True)


class SensorDataSchema(Schema):
    device_id = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    api_key = fields.Str(required=True, validate=validate.Length(min=32, max=128))
    sensor_type = fields.Str(
        required=True,
        validate=validate.Regexp(
            SENSOR_TYPE_PATTERN,
            error='sensor_type hanya boleh huruf, angka, dash, underscore (1-32 karakter)')
    )
    wifi_ssid = fields.Str(load_default='', validate=validate.Length(max=64))
    uptime_seconds = fields.Int(load_default=0, validate=validate.Range(min=0, max=10**10))
    data = fields.Dict(required=True, validate=validate_sensor_data)


class BulkImportItemSchema(Schema):
    device_id = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=64),
            validate.Regexp(r'^[a-zA-Z0-9_\-]+$',
                            error='Device ID hanya boleh huruf, angka, dash, dan underscore')
        ]
    )
    device_name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    device_type = fields.Str(load_default='ESP32', validate=validate.Length(max=32))
    location = fields.Str(load_default='', validate=validate.Length(max=255))
    description = fields.Str(load_default='', validate=validate.Length(max=1000))
    firmware_version = fields.Str(load_default='', validate=validate.Length(max=64))
    offline_timeout = fields.Raw(load_default=None, allow_none=True)
    offline_alert_severity = fields.Str(
        load_default='danger',
        validate=validate.OneOf(['info', 'warning', 'danger'])
    )


device_create_schema = DeviceCreateSchema()
device_update_schema = DeviceUpdateSchema()
sensor_data_schema = SensorDataSchema()
bulk_import_item_schema = BulkImportItemSchema()
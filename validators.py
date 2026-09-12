"""
NEXUS IoT - Input Validation dengan Marshmallow
"""
from marshmallow import Schema, fields, validate, ValidationError


class DeviceCreateSchema(Schema):
    device_id = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=64),
            validate.Regexp(
                r'^[a-zA-Z0-9_\-]+$',
                error='Device ID hanya boleh huruf, angka, dash, dan underscore'
            )
        ]
    )
    device_name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    device_type = fields.Str(
        load_default='ESP32',
        validate=validate.Length(max=32)
    )
    location = fields.Str(load_default='', validate=validate.Length(max=255))
    description = fields.Str(load_default='', validate=validate.Length(max=1000))


class DeviceUpdateSchema(Schema):
    device_name = fields.Str(validate=validate.Length(min=1, max=128))
    device_type = fields.Str(validate=validate.Length(max=32))
    location = fields.Str(validate=validate.Length(max=255))
    description = fields.Str(validate=validate.Length(max=1000))
    latitude = fields.Float(validate=validate.Range(min=-90, max=90))
    longitude = fields.Float(validate=validate.Range(min=-180, max=180))


class SensorDataSchema(Schema):
    device_id = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    api_key = fields.Str(required=True, validate=validate.Length(min=32, max=128))
    sensor_type = fields.Str(required=True, validate=validate.Length(min=1, max=32))
    wifi_ssid = fields.Str(load_default='', validate=validate.Length(max=64))
    uptime_seconds = fields.Int(load_default=0, validate=validate.Range(min=0, max=10**10))
    data = fields.Dict(required=True)


class LoginSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    password = fields.Str(required=True, validate=validate.Length(min=1, max=128))


device_create_schema = DeviceCreateSchema()
device_update_schema = DeviceUpdateSchema()
sensor_data_schema = SensorDataSchema()
login_schema = LoginSchema()
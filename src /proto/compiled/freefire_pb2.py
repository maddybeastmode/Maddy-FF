# -*- coding: utf-8 -*-
"""
Free Fire Protobuf Definitions
Dynamically built using protobuf descriptor API.
Contains: PlatformRegisterReq, PlatformRegisterResp, LikeProfileReq, LikeProfileResp
"""

from google.protobuf import descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database

_sym_db = _symbol_database.Default()

# Build PlatformRegisterReq descriptor
req_fields = [
    descriptor_pb2.FieldDescriptorProto(
        name="uid", number=1, type=4,  # TYPE_UINT64
        label=1,  # LABEL_OPTIONAL
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="password", number=2, type=12,  # TYPE_BYTES
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="region", number=3, type=9,  # TYPE_STRING
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="version", number=4, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="device_id", number=5, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="platform", number=6, type=5,  # TYPE_INT32
        label=1,
    ),
]

req_desc = descriptor_pb2.DescriptorProto(
    name="PlatformRegisterReq",
    field=req_fields,
)

# Build PlatformRegisterResp descriptor
resp_fields = [
    descriptor_pb2.FieldDescriptorProto(
        name="status", number=1, type=5,  # TYPE_INT32
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="message", number=2, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="token_data", number=3, type=12,  # TYPE_BYTES
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="server_url", number=4, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="region", number=5, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="expiry", number=6, type=3,  # TYPE_INT64
        label=1,
    ),
]

resp_desc = descriptor_pb2.DescriptorProto(
    name="PlatformRegisterResp",
    field=resp_fields,
)

# Build LikeProfileReq descriptor
like_req_fields = [
    descriptor_pb2.FieldDescriptorProto(
        name="target_uid", number=1, type=4,  # TYPE_UINT64
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="region", number=2, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="timestamp", number=3, type=3,  # TYPE_INT64
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="nonce", number=4, type=12,  # TYPE_BYTES
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="source_uid", number=5, type=4,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="client_version", number=6, type=9,
        label=1,
    ),
]

like_req_desc = descriptor_pb2.DescriptorProto(
    name="LikeProfileReq",
    field=like_req_fields,
)

# Build LikeProfileResp descriptor
like_resp_fields = [
    descriptor_pb2.FieldDescriptorProto(
        name="status", number=1, type=5,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="message", number=2, type=9,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="new_like_count", number=3, type=5,
        label=1,
    ),
    descriptor_pb2.FieldDescriptorProto(
        name="daily_like_count", number=4, type=5,
        label=1,
    ),
]

like_resp_desc = descriptor_pb2.DescriptorProto(
    name="LikeProfileResp",
    field=like_resp_fields,
)

# Build file descriptor
file_desc = descriptor_pb2.FileDescriptorProto(
    name="freefire.proto",
    package="freefire",
    message_type=[req_desc, resp_desc, like_req_desc, like_resp_desc],
)

# Add to pool
pool = _descriptor_pool.DescriptorPool()
pool.Add(file_desc)

# Create message classes
PlatformRegisterReq = _reflection.GeneratedProtocolMessageType(
    "PlatformRegisterReq",
    (_message.Message,),
    {"DESCRIPTOR": pool.FindMessageTypeByName("freefire.PlatformRegisterReq"), "__module__": "freefire_pb2"},
)
_sym_db.RegisterMessage(PlatformRegisterReq)

PlatformRegisterResp = _reflection.GeneratedProtocolMessageType(
    "PlatformRegisterResp",
    (_message.Message,),
    {"DESCRIPTOR": pool.FindMessageTypeByName("freefire.PlatformRegisterResp"), "__module__": "freefire_pb2"},
)
_sym_db.RegisterMessage(PlatformRegisterResp)

LikeProfileReq = _reflection.GeneratedProtocolMessageType(
    "LikeProfileReq",
    (_message.Message,),
    {"DESCRIPTOR": pool.FindMessageTypeByName("freefire.LikeProfileReq"), "__module__": "freefire_pb2"},
)
_sym_db.RegisterMessage(LikeProfileReq)

LikeProfileResp = _reflection.GeneratedProtocolMessageType(
    "LikeProfileResp",
    (_message.Message,),
    {"DESCRIPTOR": pool.FindMessageTypeByName("freefire.LikeProfileResp"), "__module__": "freefire_pb2"},
)
_sym_db.RegisterMessage(LikeProfileResp)

__all__ = [
    "PlatformRegisterReq",
    "PlatformRegisterResp", 
    "LikeProfileReq",
    "LikeProfileResp",
]

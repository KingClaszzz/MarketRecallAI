"""Sui gRPC client over Tatum, built from server reflection (no generated stubs)."""
from __future__ import annotations

import threading
import time

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc

RETRYABLE = {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.RESOURCE_EXHAUSTED, grpc.StatusCode.DEADLINE_EXCEEDED}
LEDGER = "sui.rpc.v2.LedgerService"


class SuiGrpcClient:
    def __init__(
        self,
        host: str,
        api_key: str,
        timeout: float = 20.0,
        retries: int = 4,
        min_interval_s: float = 0.4,
    ) -> None:
        self._channel = grpc.secure_channel(host, grpc.ssl_channel_credentials())
        self._metadata = [("x-api-key", api_key)]
        self._timeout = timeout
        self._retries = retries
        self._min_interval_s = min_interval_s
        self._last_call = 0.0
        self._lock = threading.Lock()
        self._pool = descriptor_pool.DescriptorPool()
        self._loaded: set[str] = set()

    def _throttle(self) -> None:
        # Tatum rate-limits bursts with HTTP 429, so space calls out.
        with self._lock:
            wait = self._min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _reflect(self, request: reflection_pb2.ServerReflectionRequest) -> reflection_pb2.ServerReflectionResponse:
        stub = reflection_pb2_grpc.ServerReflectionStub(self._channel)
        for attempt in range(self._retries + 1):
            self._throttle()
            try:
                responses = stub.ServerReflectionInfo(iter([request]), metadata=self._metadata, timeout=self._timeout)
                return next(iter(responses))
            except grpc.RpcError as exc:
                if exc.code() not in RETRYABLE or attempt == self._retries:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def _add_files(self, serialized: list[bytes]) -> None:
        protos = {}
        for raw in serialized:
            proto = descriptor_pb2.FileDescriptorProto.FromString(raw)
            protos[proto.name] = proto

        def add(name: str) -> None:
            if name in self._loaded:
                return
            proto = protos.get(name)
            if proto is None:
                response = self._reflect(reflection_pb2.ServerReflectionRequest(file_by_filename=name))
                for raw in response.file_descriptor_response.file_descriptor_proto:
                    p = descriptor_pb2.FileDescriptorProto.FromString(raw)
                    protos[p.name] = p
                proto = protos[name]
            for dep in proto.dependency:
                add(dep)
            self._pool.Add(proto)
            self._loaded.add(name)

        for name in list(protos):
            add(name)

    def _service(self, service: str):
        try:
            return self._pool.FindServiceByName(service)
        except KeyError:
            response = self._reflect(reflection_pb2.ServerReflectionRequest(file_containing_symbol=service))
            self._add_files(list(response.file_descriptor_response.file_descriptor_proto))
            return self._pool.FindServiceByName(service)

    def call(self, service: str, method: str, request: dict | None = None, read_mask: list[str] | None = None) -> dict:
        method_desc = self._service(service).FindMethodByName(method)
        request_cls = message_factory.GetMessageClass(method_desc.input_type)
        response_cls = message_factory.GetMessageClass(method_desc.output_type)
        rpc = self._channel.unary_unary(
            f"/{service}/{method}",
            request_serializer=lambda m: m.SerializeToString(),
            response_deserializer=response_cls.FromString,
        )
        message = json_format.ParseDict(request or {}, request_cls())
        if read_mask:
            message.read_mask.paths.extend(read_mask)
        for attempt in range(self._retries + 1):
            self._throttle()
            try:
                response = rpc(message, metadata=self._metadata, timeout=self._timeout)
                return json_format.MessageToDict(response, preserving_proto_field_name=True)
            except grpc.RpcError as exc:
                if exc.code() not in RETRYABLE or attempt == self._retries:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def describe(self, service: str, method: str) -> tuple[list[str], list[str]]:
        method_desc = self._service(service).FindMethodByName(method)
        return [f.name for f in method_desc.input_type.fields], [f.name for f in method_desc.output_type.fields]

    def close(self) -> None:
        self._channel.close()

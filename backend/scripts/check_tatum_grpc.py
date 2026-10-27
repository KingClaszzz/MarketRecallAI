"""Read-only Tatum Sui gRPC check: list services exposed via server reflection."""
import os
import sys
from pathlib import Path

import grpc
from dotenv import load_dotenv
from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def main() -> int:
    channel = grpc.secure_channel(os.environ["TATUM_SUI_GRPC_HOST"], grpc.ssl_channel_credentials())
    stub = reflection_pb2_grpc.ServerReflectionStub(channel)
    metadata = [("x-api-key", os.environ["TATUM_API_KEY"])]
    request = reflection_pb2.ServerReflectionRequest(list_services="")
    try:
        for response in stub.ServerReflectionInfo(iter([request]), metadata=metadata, timeout=20):
            for service in response.list_services_response.service:
                print(service.name)
    except grpc.RpcError as exc:
        print(f"FAILED: {exc.code()}: {exc.details()}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

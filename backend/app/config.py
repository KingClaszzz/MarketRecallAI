from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    tatum_api_key: str
    tatum_data_api_url: str = "https://api.tatum.io"
    tatum_sui_grpc_host: str = "sui-mainnet-grpc.gateway.tatum.io:443"

    coingecko_api_key: str = ""
    coingecko_api_url: str = "https://api.coingecko.com/api/v3"

    binance_api_url: str = "https://data-api.binance.vision"

    memwal_private_key: str = ""
    memwal_account_id: str = ""
    memwal_agent_id: str = ""
    memwal_server_url: str = "https://relayer.memory.walrus.xyz"
    memwal_max_writes_per_day: int = 150

    llm_base_url: str = "https://api.yjs.im/v1"
    llm_api_key: str = ""
    llm_model: str = "agnes-3.0-flash"

    assets: list[str] = ["SUI", "WAL", "CETUS"]
    forecast_horizon_h: int = 4
    recall_n_min: int = 8
    admin_token: str = ""

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'marketrecall.db').as_posix()}"
    scheduler_enabled: bool = True

    cors_origins: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://localhost:5180",
    ]
    app_domain: str = "localhost:5173"  # shown in the sign-in message
    expose_docs: bool = False
    trust_proxy: bool = False  # use X-Forwarded-For for the client IP
    proxy_hops: int = 1  # proxies in front of the app that append to X-Forwarded-For


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""应用配置管理"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Stockfish
    stockfish_path: str = "stockfish"
    stockfish_depth: int = 18
    stockfish_threads: int = 2
    stockfish_hash: int = 64

    # Server
    port: int = 8080

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

"""应用配置管理"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Stockfish
    stockfish_path: str = "stockfish"
    stockfish_depth: int = 18
    stockfish_threads: int = 2
    stockfish_hash: int = 64

    # Server
    backend_port: int = 8000
    frontend_port: int = 8501

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

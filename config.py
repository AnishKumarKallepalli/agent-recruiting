from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AgentPhone
    agentphone_api_key: str = ""
    agentphone_base_url: str = "https://api.agentphone.ai/v1"
    agentphone_agent_id: str = ""
    agentphone_number_id: str = ""
    agentphone_phone_number: str = ""

    # AgentMail
    agentmail_api_key: str = ""
    agentmail_base_url: str = "https://api.agentmail.to"
    agentmail_inbox_id: str = "recagent@agentmail.to"

    # Gemini
    gemini_api_key: str = ""

    # Browser Use
    browser_use_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    webhook_base_url: str = ""


settings = Settings()

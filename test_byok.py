"""Verify BYOK provider builds correctly."""
from dotenv import load_dotenv
load_dotenv()

from agents.copilot_sdk_agent import _build_byok_provider, create_copilot_sdk_implementer

provider = _build_byok_provider()
print(f"Provider type: {provider['type']}")
print(f"Base URL: {provider['base_url']}")
print(f"API version: {provider['azure']['api_version']}")
print(f"Has bearer_token: {'bearer_token' in provider}")
print(f"Has api_key: {'api_key' in provider}")

agent = create_copilot_sdk_implementer()
print(f"Agent type: {type(agent).__name__}")

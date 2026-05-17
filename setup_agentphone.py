"""
Run once to:
1. Create the Ava agent on AgentPhone
2. Provision a phone number
3. Attach the number to the agent
4. Register the webhook

Then copy the IDs into your .env file.

Usage: python setup_agentphone.py
"""
from services.agentphone import create_agent, provision_number, attach_number, register_webhook
from config import settings

print("=== AgentPhone Setup ===\n")

# 1. Create agent
print("1. Creating Ava agent...")
agent = create_agent("Ava")
agent_id = agent.get("id") or agent.get("agent_id")
print(f"   Agent ID: {agent_id}")

# 2. Provision number
print("2. Provisioning phone number...")
number = provision_number()
number_id = number.get("id") or number.get("number_id")
phone = number.get("number") or number.get("phone_number")
print(f"   Number ID: {number_id}")
print(f"   Phone: {phone}")

# 3. Attach
print("3. Attaching number to agent...")
attach_number(agent_id, number_id)
print("   Done.")

# 4. Webhook
webhook_url = f"{settings.webhook_base_url}/webhooks/agentphone"
print(f"4. Registering webhook: {webhook_url}")
wh = register_webhook(webhook_url)
print(f"   Webhook: {wh}")

print("\n=== Copy these into your .env ===")
print(f"AGENTPHONE_AGENT_ID={agent_id}")
print(f"AGENTPHONE_NUMBER_ID={number_id}")
print(f"AGENTPHONE_PHONE_NUMBER={phone}")

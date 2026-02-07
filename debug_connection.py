import os
import sys
sys.path.insert(0, '/home/zuhair/Desktop/Projects/Openpoke')

from dotenv import load_dotenv
load_dotenv('/home/zuhair/Desktop/Projects/Openpoke/.env')

from composio import Composio

client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

user_id = "web-ec60756ee3ea490daabc7a16062d86d8"

print("=== Checking Connected Accounts ===\n")

# Try different ways to get accounts
print("1. With toolkit_slugs=['JIRA']:")
try:
    accounts = client.connected_accounts.list(
        user_ids=[user_id],
        toolkit_slugs=["JIRA"],
        statuses=["ACTIVE"]
    )
    print(f"   Result: {accounts}")
    data = getattr(accounts, "data", None) or (accounts.get("data") if isinstance(accounts, dict) else None)
    print(f"   Data: {data}")
    print(f"   Length: {len(data) if data else 0}")
except Exception as e:
    print(f"   Error: {e}")

print("\n2. Without toolkit_slugs filter:")
try:
    accounts = client.connected_accounts.list(
        user_ids=[user_id],
        statuses=["ACTIVE"]
    )
    data = getattr(accounts, "data", None) or (accounts.get("data") if isinstance(accounts, dict) else None)
    print(f"   Found {len(data) if data else 0} accounts")
    if data:
        for acc in data:
            app_name = getattr(acc, 'appName', None) or (acc.get('appName') if isinstance(acc, dict) else None)
            print(f"   - App: {app_name}")
except Exception as e:
    print(f"   Error: {e}")

print("\n3. Check if it's 'jira' lowercase:")
try:
    accounts = client.connected_accounts.list(
        user_ids=[user_id],
        toolkit_slugs=["jira"],
        statuses=["ACTIVE"]
    )
    data = getattr(accounts, "data", None) or (accounts.get("data") if isinstance(accounts, dict) else None)
    print(f"   Found {len(data) if data else 0} accounts")
except Exception as e:
    print(f"   Error: {e}")

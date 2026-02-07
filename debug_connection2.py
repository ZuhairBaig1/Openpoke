import os
import sys
sys.path.insert(0, '/home/zuhair/Desktop/Projects/Openpoke')

from dotenv import load_dotenv
load_dotenv('/home/zuhair/Desktop/Projects/Openpoke/.env')

from server.services.jira.client import _get_composio_client

client = _get_composio_client()
user_id = "web-ec60756ee3ea490daabc7a16062d86d8"

print("=== Using Same Client as client.py ===\n")

items = client.connected_accounts.list(user_ids=[user_id], toolkit_slugs=["JIRA"], statuses=["ACTIVE"])
print(f"Items type: {type(items)}")
print(f"Items: {items}")

data = getattr(items, "data", None) or (items.get("data") if isinstance(items, dict) else None)
print(f"\nData: {data}")
print(f"Data length: {len(data) if data else 0}")

if data:
    account = data[0]
    print(f"\nAccount type: {type(account)}")
    print(f"Account: {account}")
    
    # Try to get access token
    access_token = getattr(account, 'accessToken', None) or (account.get('accessToken') if isinstance(account, dict) else None)
    print(f"\nAccess token found: {bool(access_token)}")
    
else:
    print("\n❌ No data found - trying without filters...")
    items2 = client.connected_accounts.list(user_ids=[user_id])
    data2 = getattr(items2, "data", None) or (items2.get("data") if isinstance(items2, dict) else None)
    print(f"Without filters - found {len(data2) if data2 else 0} accounts")
    
    if data2:
        for acc in data2:
            app = getattr(acc, 'appName', None) or (acc.get('appName') if isinstance(acc, dict) else 'unknown')
            print(f"  - {app}")

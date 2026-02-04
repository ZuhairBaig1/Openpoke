from composio import ComposioToolSet
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
toolset = ComposioToolSet(api_key=api_key)

user_id = "test-check-v3"

try:
    print("--- Testing initiate and status ---")
    req = toolset.initiate_connection(
        app="gmail",
        entity_id=user_id
    )
    acc_id = req.connectedAccountId
    print(f"Created account ID: {acc_id}")
    
    # Check status
    account = toolset.get_connected_account(connection_id=acc_id)
    print(f"Account Status: {account.status}")
    print(f"Account ID from get: {account.id}")
except Exception as e:
    print(f"Error: {e}")

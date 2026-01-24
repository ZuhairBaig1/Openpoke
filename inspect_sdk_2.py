
import inspect
from composio import Composio

print("Inspecting initiate annotations:")
try:
    client = Composio(api_key="TEST")
    sig = inspect.signature(client.connected_accounts.initiate)
    config_type = sig.parameters['config'].annotation
    print(f"Config Type: {config_type}")
    
    # Try to resolve the string forward ref if valid
    # or just look for the module
    
    # Try to import 'connected_account_create_params'
    try:
         from composio.core.models import connected_account_create_params
         print("\nFound module composio.core.models.connected_account_create_params")
         print(f"ConnectionState fields: {connected_account_create_params.ConnectionState.__annotations__}")
    except ImportError:
         pass

    try:
         from composio_client.types import connected_account_create_params
         print("\nFound module composio_client.types.connected_account_create_params")
         print(f"ConnectionState fields: {connected_account_create_params.ConnectionState.__annotations__}")
    except ImportError:
         print("\nCould not find module path blindly")

except Exception as e:
    print(f"Error: {e}")

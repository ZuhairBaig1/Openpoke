import os
import sys
from pathlib import Path

# Simple .env loader to avoid dependencies
def load_env_file():
    env_path = Path(__file__).parent / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                key, value = key.strip(), value.strip().strip("'\"")
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass

load_env_file()

from composio import ComposioToolSet

def inspect_connected_accounts():
    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        print("Error: COMPOSIO_API_KEY not found in environment.")
        return

    print(f"Using API Key: {api_key[:5]}...")
    
    try:
        toolset = ComposioToolSet(api_key=api_key)
        accounts = toolset.get_connected_accounts()
        
        print(f"Found {len(accounts)} connected accounts.")
        
        if accounts:
            first_account = accounts[0]
            print("\nType of first account:", type(first_account))
            
            # Print all attributes that don't start with _
            print("\nPublic attributes:")
            for attr in dir(first_account):
                if not attr.startswith('_'):
                    try:
                        val = getattr(first_account, attr)
                        if not callable(val):
                            print(f"  {attr}: {val}")
                    except Exception:
                        pass
            
            # specifically check for what we are looking for
            print("\nDirect check:")
            check_attrs = ['app_slug', 'app_name', 'appName', 'provider', 'provider_id', 'appId']
            for name in check_attrs:
                has_it = hasattr(first_account, name)
                val = getattr(first_account, name, "N/A") if has_it else "N/A"
                print(f"  {name}: {has_it} -> {val}")

    except Exception as e:
        print(f"Error inspecting accounts: {e}")
        # import traceback
        # traceback.print_exc()

if __name__ == "__main__":
    inspect_connected_accounts()

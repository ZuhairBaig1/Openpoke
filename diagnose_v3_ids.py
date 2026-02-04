from composio import Composio, ComposioToolSet
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY")
client = Composio(api_key=api_key) if api_key else Composio()

print(f"--- All Integrations ---")
try:
    integrations = client.integrations.get()
    for i in integrations:
        # Check all attributes
        print(f"App: {i.appName}, ID: {i.id}, Slug: {getattr(i, 'slug', 'N/A')}, Status: {getattr(i, 'status', 'N/A')}")
        # Try to find if any attribute matches the user's auth_config_id (ac_...)
        for attr in dir(i):
            if not attr.startswith('_'):
                val = getattr(i, attr)
                if val == 'ac_ZqDnXT65wR2T' or val == 'ac_Qa9E4Cc9IoGL':
                    print(f"  MATCH FOUND! Attribute '{attr}' has value '{val}'")
except Exception as e:
    print(f"Error: {e}")

print(f"\n--- Testing initiate_connection with app string ---")
toolset = ComposioToolSet(api_key=api_key)
# We won't actually call it but let's see if we can prepare it
try:
    # Just a mock check
    print("Checking if initiate_connection accepts 'app' name...")
except Exception as e:
    print(f"Error: {e}")

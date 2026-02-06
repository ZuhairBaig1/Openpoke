import os
import sys
sys.path.insert(0, '/home/zuhair/Desktop/Projects/Openpoke')

from dotenv import load_dotenv
load_dotenv('/home/zuhair/Desktop/Projects/Openpoke/.env')

from composio import Composio

client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

print("=== Checking Tools API ===")
try:
    # In v1.0.0-rc2, it seems to be client.tools
    tools_api = client.tools
    print(f"Tools API type: {type(tools_api)}")
    print(f"Tools API methods: {[m for m in dir(tools_api) if not m.startswith('_')]}\n")
    
    # Try to get Jira tools
    if hasattr(tools_api, 'get'):
        print("Trying tools.get()...")
        try:
            tool = tools_api.get(name="JIRA_SEARCH_FOR_ISSUES_USING_JQL_POST")
            print(f"Got tool: {tool}")
            print(f"Tool attributes: {[a for a in dir(tool) if not a.startswith('_')]}")
        except Exception as e:
            print(f"Error with get(): {e}")
            
    # Try execute to see the actual error
    print("\n=== Testing Actual Execution ===")
    if hasattr(tools_api, 'execute'):
        try:
            # This will fail but show us the endpoint being used
            result = tools_api.execute(
                "JIRA_SEARCH_FOR_ISSUES_USING_JQL_POST",
                user_id="test",
                arguments={"jql": "project = TEST"}
            )
        except Exception as e:
            error_msg = str(e)
            print(f"Execution error: {error_msg}")
            if "410" in error_msg or "/rest/api/3/search" in error_msg:
                print("\n✗ CONFIRMED: Composio is using the deprecated /rest/api/3/search endpoint")
                print("✗ This is a Composio SDK bug - they haven't updated to /rest/api/3/search/jql")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\n\n=== SOLUTION OPTIONS ===")
print("1. Wait for Composio to fix their SDK (check https://github.com/ComposioHQ/composio/issues)")
print("2. Use Jira REST API directly (bypass Composio for search)")
print("3. Try older Composio SDK version that might work")
print("4. File a bug report with Composio")

from __future__ import annotations
import requests
from typing import Dict, Any, Optional, List
from ...logging_config import logger
from .client import _get_composio_client

def get_jira_credentials(user_id: str) -> Optional[Dict[str, Any]]:
    """Extract credentials by scanning the entire account model."""
    try:
        client = _get_composio_client()
        response = client.connected_accounts.list(
            user_ids=[user_id],
            toolkit_slugs=["jira"], 
            statuses=["ACTIVE"]
        )
        
        accounts = getattr(response, "items", [])
        if not accounts:
            logger.warning(f"No active Jira connection found for user {user_id}")
            return None
            
        account = accounts[0]
        
        # Convert the Pydantic model to a standard dictionary
        # This handles 'data', 'state', and 'auth_config' all at once
        account_dict = account.model_dump() if hasattr(account, 'model_dump') else account.dict()
        
        def find_value(d: Any, target_keys: list[str]) -> Optional[Any]:
            """Recursively search for specific keys in a nested dictionary."""
            if not isinstance(d, dict):
                return None
            # Check current level
            for k, v in d.items():
                if any(tk.lower() in k.lower() for tk in target_keys) and v:
                    # Ignore keys that are just metadata about the key name
                    if isinstance(v, (str, int)) and v != "REDACTED":
                        return v
            # Dive deeper
            for v in d.values():
                if isinstance(v, dict):
                    res = find_value(v, target_keys)
                    if res: return res
                elif isinstance(v, list):
                    for item in v:
                        res = find_value(item, target_keys)
                        if res: return res
            return None

        # Search for the Token
        access_token = find_value(account_dict, ["accessToken", "access_token", "token"])
        
        # Search for the Cloud ID
        cloud_id = find_value(account_dict, ["cloudId", "cloud_id", "instanceId"])

        if not cloud_id:
            logger.warning(f"No Cloud ID found in stored metadata for user {user_id}")


        if not access_token:
            # Fallback for some specific SDK versions where it's in account.state.val
            state_obj = getattr(account, 'state', None)
            if state_obj and hasattr(state_obj, 'val'):
                access_token = state_obj.val.get('access_token') if isinstance(state_obj.val, dict) else state_obj.val

        if not access_token:
            logger.error(f"STILL NO TOKEN. Full object dump for debugging: {account_dict}")
            return None

        logger.info(f"Successfully extracted token (starts with: {str(access_token)[:5]}...)")
            
        return {
            'access_token': access_token,
            'cloud_id': cloud_id
        }
        
    except Exception as e:
        logger.exception(f"Credential extraction failed: {str(e)}")
        return None

def search_issues_jql(user_id: str, jql: str, **kwargs) -> Dict[str, Any]:
    """Directly calls the mandatory /search/jql endpoint with enhanced discovery logs."""
    creds = get_jira_credentials(user_id)
    if not creds:
        return {"successful": False, "error": "Could not retrieve valid Jira credentials"}
        
    token = creds['access_token']
    cloud_id = creds.get('cloud_id')
    
    # --- ENHANCED DISCOVERY BLOCK ---
    if not cloud_id:
        logger.info("Cloud ID not found in metadata. Attempting discovery via Atlassian...")
        try:
            res = requests.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if res.status_code != 200:
                logger.error(f"Discovery failed with status {res.status_code}: {res.text}")
                return {"successful": False, "error": f"Atlassian Discovery Error: {res.status_code}"}
            
            resources = res.json()
            logger.info(f"Atlassian returned {len(resources)} resources: {resources}")
            
            if resources and isinstance(resources, list):
                # We pick the first Jira site found
                
                jira_sites = [r for r in resources if r.get("scopes") and "read:jira-work" in r.get("scopes", [])]

                if not jira_sites:
                    return {"successful": False, "error": "No Jira Cloud site found for this token"}

                cloud_id = jira_sites[0]["id"]

                logger.info(f"Discovered Cloud ID: {cloud_id}")
            else:
                return {"successful": False, "error": "Cloud ID missing: No accessible Jira resources found for this token."}
                
        except Exception as e:
            logger.exception("Exception during Cloud ID discovery")
            return {"successful": False, "error": f"Discovery Exception: {str(e)}"}

    # --- API CALL BLOCK ---
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/search/jql"
    logger.info(f"Executing JQL Search at: {url}")
    
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json={
                "jql": jql, 
                "maxResults": kwargs.get('max_results', 50),
                "fields": kwargs.get('fields', ["summary", "status", "assignee", "updated"])
            },
            timeout=30
        )
        
        if response.status_code == 401:
            return {"successful": False, "error": "Unauthorized: Access token may be expired."}
            
        response.raise_for_status()
        return {"successful": True, "data": response.json()}
        
    except Exception as e:
        logger.error(f"Direct API call failed: {str(e)}")
        return {"successful": False, "error": str(e)}
# OpenPoke 🌴

OpenPoke is a simplified, open-source take on [Interaction Company’s](https://interaction.co/about) [Poke](https://poke.com/) assistant—built to show how a multi-agent orchestration stack can feel genuinely useful. It keeps the handful of things Poke is great at (email triage, reminders, and persistent agents) while staying easy to spin up locally.

- Multi-agent FastAPI backend that mirrors Poke's interaction/execution split, powered by [OpenRouter](https://openrouter.ai/).
- Gmail tooling via [Composio](https://composio.dev/) for drafting/replying/forwarding without leaving chat.
- Jira tooling via [Composio](https://composio.dev/) for creating/updating/listing jira issues from openpoke dashboard.
- Google calendar tooling via [Composio](https://composio.dev/) for scheduling/modifying/deleting events from openpoke dashboard.
- Trigger scheduler and background watchers for reminders and "important email" alerts.
- Next.js web UI that proxies everything through the shared `.env`, so plugging in API keys is the only setup.

## Requirements
- Python 3.10+
- Node.js 18+
- npm 9+

## Quickstart
1. **Clone and enter the repo.**
   ```bash
   git clone https://github.com/shlokkhemani/OpenPoke
   cd OpenPoke
   ```
2. **Create a shared env file.** Copy the template and open it in your editor:
   ```bash
   cp .env.example .env
   ```
3. **Get your API keys and add them to `.env`:**
   
   **OpenRouter (Required)**
   - Create an account at [openrouter.ai](https://openrouter.ai/)
   - Generate an API key
   - Replace `your_openrouter_api_key_here` with your actual key in `.env`
   
   **Composio (Required for Gmail, Jira & Google Calendar)**
   - Sign in at composio.dev
   - Create an API key
   - Set up integrations for Gmail, Jira, and Google Calendar, and get the auth config ID for each
   - Replace the following in .env:
     - COMPOSIO_API_KEY → your Composio API key
     - COMPOSIO_GMAIL_AUTH_CONFIG_ID → your Gmail auth config ID
     - COMPOSIO_JIRA_AUTH_CONFIG_ID → your Jira auth config ID
     - COMPOSIO_GOOGLECALENDAR_AUTH_CONFIG_ID → your Google Calendar auth config ID
    
4. **Jira OAuth2 Setup**
   To enable Jira integration, you need to create an OAuth 2.0 app in the Atlassian Developer Console and configure it in Composio.

   - Create an Atlassian App: Go to developer.atlassian.com/console/myapps, click Create → OAuth 2.0 integration, and give it a name (e.g., "OpenPoke").

   - Configure Scopes: Under your app's Permissions tab, add the following scopes for Jira API and Jira Service Management API:
      - read:jira-user, manage:jira-webhook, manage:jira-data-provider,
      - read:servicedesk-request, manage:servicedesk-customer, write:servicedesk-request,
      - read:servicemanagement-insight-objects, offline_access,
      - read:sprint:jira-software, write:sprint:jira-software,
      - read:board-scope:jira-software, write:board-scope:jira-software,
      - read:project:jira, read:issue-type-scheme:jira,
      - manage:jira-configuration, manage:jira-project,
      - write:jira-work, read:jira-work, read:me, read:account
   - Get Credentials: Under your app's Settings, copy the Client ID and Client Secret. Under Authorization → OAuth 2.0 (3LO), add the Callback URL provided by Composio (found in your Composio integration settings).

   - Configure Composio: On composio.dev, navigate to your Jira integration, enter the Client ID, Client Secret, and Redirect URL from your Atlassian app. Under Manage Scopes, ensure the same scopes listed above are enabled so Composio requests the correct permissions during the OAuth flow.
       
5. **(Required) Create and activate a Python 3.10+ virtualenv:**
   ```bash
   # Ensure you're using Python 3.10+
   python3.10 -m venv .venv
   source .venv/bin/activate
   
   # Verify Python version (should show 3.10+)
   python --version
   ```
   On Windows (PowerShell):
   ```powershell
   # Use Python 3.10+ (adjust path as needed)
   python3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   
   # Verify Python version
   python --version
   ```

6. **Install backend dependencies:**
   ```bash
   pip install -r server/requirements.txt
   ```
7. **Install frontend dependencies:**
   ```bash
   npm install --prefix web
   ```
8. **Start the FastAPI server:**
   ```bash
   python -m server.server --reload
   ```
9. **Start the Next.js app (new terminal):**
   ```bash
   npm run dev --prefix web
   ```
10. **Connect integrations for full functionality:** With both services running, open http://localhost:3000 and head to Settings to complete the Composio OAuth flow for each service:
- Gmail → Required for email drafting, replies, and the important-email monitor.
- Jira → Required for issue management, comments, and real-time webhook notifications. When prompted during OAuth, select the appropriate Jira subdomain (e.g., yourteam.atlassian.net) for the correct workspace.
- Google Calendar → Required for creating, searching, and managing calendar events.

The web app proxies API calls to the Python server using the values in `.env`, so keeping both processes running is required for end-to-end flows.

## Project Layout
- `server/` – FastAPI application and agents
- `web/` – Next.js app
- `server/data/` – runtime data (ignored by git)

## License
MIT — see [LICENSE](LICENSE).

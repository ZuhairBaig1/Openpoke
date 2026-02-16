
from pathlib import Path
from typing import List, Optional, Dict, Any

from ...services.execution import get_execution_agent_logs
from ...services.timezone_store import get_timezone_store
from ...logging_config import logger
from datetime import datetime
from zoneinfo import ZoneInfo


_prompt_path = Path(__file__).parent / "system_prompt.md"
if _prompt_path.exists():
    SYSTEM_PROMPT_TEMPLATE = _prompt_path.read_text(encoding="utf-8").strip()
else:
    SYSTEM_PROMPT_TEMPLATE = """You are an execution agent responsible for completing specific tasks using available tools.

Agent Name: {agent_name}
Purpose: {agent_purpose}

Instructions:
[TO BE FILLED IN BY USER]

You have access to Gmail tools to help complete your tasks. When given instructions:
1. Analyze what needs to be done
2. Use the appropriate tools to complete the task
3. Provide clear status updates on your actions

Be thorough, accurate, and efficient in your execution."""


class ExecutionAgent:
    def __init__(
        self,
        name: str,
        conversation_limit: Optional[int] = None
    ):
       
        self.name = name
        self.conversation_limit = conversation_limit
        self._log_store = get_execution_agent_logs()

    def build_system_prompt(self) -> str:
        logger.info(f"Inside build_system_prompt in execution_agent agent, agent name = {self.name}")
        agent_purpose = f"Handle tasks related to: {self.name}"

        # Fetch actual timezone and time from user preference
        tz_name = get_timezone_store().get_timezone()
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        offset = now.strftime("%z")
        # Format offset as HH:MM (+0530 -> +05:30)
        formatted_offset = f"{offset[:3]}:{offset[3:]}" if len(offset) >= 5 else offset
        current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"Injecting timezone: {tz_name} ({formatted_offset}), current_time: {current_time_str}")

        prompt = SYSTEM_PROMPT_TEMPLATE.replace("{agent_name}", self.name)
        prompt = prompt.replace("{agent_purpose}", agent_purpose)
        prompt = prompt.replace("{timezone_name}", tz_name)
        prompt = prompt.replace("{timezone_offset}", formatted_offset)
        prompt = prompt.replace("{current_time}", current_time_str)
        
        return prompt

    def build_system_prompt_with_history(self) -> str:
        
        logger.info("Inside build_system_prompt_with_history in execution_agent agent")
        base_prompt = self.build_system_prompt()
        logger.info("Created base prompt, in execution_agent agent")

        logger.info("Loading transcript (execution agent logs), in execution_agent agents")
        transcript = self._log_store.load_transcript(self.name)
        logger.info("Loaded transcript (execution agent logs), in execution_agent agents")

        if transcript:
            logger.info("Transcripts exists, in execution_agent agents")
            if self.conversation_limit and self.conversation_limit > 0:
                lines = transcript.split('\n')
                request_count = sum(1 for line in lines if '<agent_request' in line)

                if request_count > self.conversation_limit:
                    kept_requests = 0
                    cutoff_index = len(lines)
                    for i in range(len(lines) - 1, -1, -1):
                        if '<agent_request' in lines[i]:
                            kept_requests += 1
                            if kept_requests == self.conversation_limit:
                                cutoff_index = i
                                break
                    transcript = '\n'.join(lines[cutoff_index:])

            return f"{base_prompt}\n\n# Execution History\n\n{transcript}"

        logger.info("Did not load transcripts, or does not exist, in execution_agent agents")
        return base_prompt

    def build_messages_for_llm(self, current_instruction: str) -> List[Dict[str, str]]:
        
        return [
            {"role": "user", "content": current_instruction}
        ]
    def record_response(self, response: str) -> None:
        self._log_store.record_agent_response(self.name, response)

    def record_tool_execution(self, tool_name: str, arguments: str, result: str) -> None:
        self._log_store.record_action(self.name, f"Calling {tool_name} with: {arguments[:200]}")
        self._log_store.record_tool_response(self.name, tool_name, result[:500])

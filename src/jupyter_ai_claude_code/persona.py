from typing import Dict, Any, List, Optional, AsyncIterator
import datetime

from jupyter_ai.personas.base_persona import BasePersona, PersonaDefaults
from jupyterlab_chat.models import Message, NewMessage

from claude_code_sdk import (
    query, ClaudeCodeOptions, AssistantMessage, TextBlock, ToolUseBlock,
    UserMessage, SystemMessage
)

from .templates import (
    ClaudeCodeTemplateManager
)





class ClaudeCodePersona(BasePersona):
    """Claude Code persona for Jupyter AI integration."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template_mgr = ClaudeCodeTemplateManager(self)

    @property
    def defaults(self) -> PersonaDefaults:
        """Return default configuration for the Claude Code persona."""
        system_prompt = ("I am Claude Code, an AI assistant with access to development tools. "
                        "When formatting responses, I use **bold text** for emphasis and section headers instead of markdown headings (# ## ###). "
                        "I keep formatting clean and readable without large headers. "
                        "For complex tasks requiring multiple steps (3+ actions), I proactively create a todo list using TodoWrite to track progress and keep the user informed of my plan.")
        
        return PersonaDefaults(
            name="Claude",
            avatar_path="/files/.jupyter/claude.svg",
            description="Claude Code persona",
            system_prompt=system_prompt,
        )
    
    async def _process_response_message(self, message_iterator) -> AsyncIterator[str]:
        """Process response messages with template updates."""
        has_content = False
        template_was_used = False
        
        async for message in message_iterator:
            self.log.info(str(message))
            if isinstance(message, AssistantMessage):
                result = await self.template_mgr.claude_message_to_str(message)
                # Template now handles everything - never stream individual components
                if self.template_mgr.active:
                    template_was_used = True
                elif result is not None:
                    # Only for messages without any tool usage (rare)
                    has_content = True
                    yield result + '\n\n'
        
        # Complete template if active
        if self.template_mgr.active:
            await self.template_mgr.complete()
            template_was_used = True
        
        # Always yield something to complete the stream
        if template_was_used:
            yield ""  # Empty yield to signal completion when template handled everything
        elif not has_content:
            yield ""  # Ensure stream completes for empty responses

    def _generate_prompt(self, message: Message) -> str:
        attachment_ids = message.attachments
        if attachment_ids is None:
            return message.body
        attachments = self.ychat.get_attachments()
        msg_attachments = (attachments[aid] for aid in attachment_ids)
        prompt = f"{message.body}\n\n"
        prompt += f"The user has attached the following files and may be referring to them in the above prompt:\n\n"
        for a in msg_attachments:
            if a['type'] == 'file':
                prompt += f"file_path={a['value']}"
            elif a['type'] == 'notebook':
                cells = list(c['id'] for c in a['cells'])
                # Claude Code's notebook tools only understand a single cell_id
                prompt += f"notebook_path={a['value']} cell_id={cells[0]}"
        self.log.info(prompt)
        return prompt

    def _get_system_prompt(self):
        """Get the system prompt for Claude Code options."""
        return ("I am Claude Code, an AI assistant with access to development tools. "
               "When formatting responses, I use **bold text** for emphasis and section headers instead of markdown headings (# ## ###). "
               "I keep formatting clean and readable without large headers. "
               "For complex tasks requiring multiple steps (3+ actions), I proactively create a todo list using TodoWrite to track progress and keep the user informed of my plan.")

    async def process_message(self, message: Message) -> None:
        """Process incoming message and stream Claude Code response."""
        # Always set writing state at the start
        self.awareness.set_local_state_field("isWriting", True)
        
        self.template_mgr.reset()
        
        try:
            # Configure Claude Code - use workspace dir for better working directory detection
            chat_dir = self.get_chat_dir()
            workspace_dir = self.get_workspace_dir()
            
            # Prefer workspace dir if available, fallback to chat dir
            working_dir = chat_dir if chat_dir else workspace_dir
            
            self.log.info(f"Chat directory: {chat_dir}")
            self.log.info(f"Workspace directory: {workspace_dir}")
            self.log.info(f"Using working directory: {working_dir}")
            
            options = {
                'max_turns': 20,
                'cwd': working_dir,
                'permission_mode': 'bypassPermissions',
                'system_prompt': self._get_system_prompt()
            }
            
            # Generate prompt from current message
            user_prompt = self._generate_prompt(message)
            
            # Stream response directly with prompt
            async_gen = query(prompt=user_prompt, options=ClaudeCodeOptions(**options))
            
            # Use stream_message to handle the streaming
            await self.stream_message(self._process_response_message(async_gen))
            
        except Exception as e:
            self.log.error(f"Error: {e}")
            if self.template_mgr.active:
                await self.template_mgr.complete()
            
            try:
                await self.send_message(f"Sorry, error: {e}")
            except TypeError:
                self.send_message(f"Sorry, error: {e}")
        finally:
            # Always clear writing state when done
            self.awareness.set_local_state_field("isWriting", False)

from typing import Dict, Any, List, Optional, AsyncIterator

from jupyter_ai.personas.base_persona import BasePersona, PersonaDefaults
from jupyterlab_chat.models import Message

from claude_code_sdk import (
    query, ClaudeCodeOptions,
    Message, SystemMessage, AssistantMessage, ResultMessage,
    TextBlock, ToolUseBlock
)


OMIT_INPUT_ARGS = ['content']

TOOL_PARAM_MAPPING = {
    'Task': 'description',
    'Bash': 'command',
    'Glob': 'pattern',
    'Grep': 'pattern',
    'LS': 'path',
    'Read': 'file_path',
    'Edit': 'file_path',
    'MultiEdit': 'file_path',
    'Write': 'file_path',
    'NotebookRead': 'notebook_path',
    'NotebookWrite': 'notebook_path',
    'WebFetch': 'url',
    'WebSearch': 'query',
}

PROMPT_TEMPLATE = """
{{body}}

The user has selected the following files as attachements:


"""

def input_dict_to_str(d: Dict[str, Any]) -> str:
    """Convert input dictionary to string representation, omitting specified args."""
    args = []
    for k, v in d.items():
        if k not in OMIT_INPUT_ARGS:
            args.append(f"{k}={v}")
    return ', '.join(args)


def tool_to_str(block: ToolUseBlock, persona_instance=None) -> str:
    """Convert a ToolUseBlock to its string representation."""
    results = []
    
    if block.name == 'TodoWrite':
        block_id = block.id if hasattr(block, 'id') else str(hash(str(block.input)))
        
        if persona_instance and block_id in persona_instance._printed_todowrite_blocks:
            return ""
        
        if persona_instance:
            persona_instance._printed_todowrite_blocks.add(block_id)
        
        todos = block.input.get('todos', [])
        results.append('TodoWrite()')
        for todo in todos:
            content = todo.get('content')
            if content:
                results.append(f"* {content}")
    elif block.name in TOOL_PARAM_MAPPING:
        param_key = TOOL_PARAM_MAPPING[block.name]
        param_value = block.input.get(param_key, '')
        results.append(f"🛠️ {block.name}({param_value})")
    else:
        results.append(f"🛠️ {block.name}({input_dict_to_str(block.input)})")
    
    return '\n'.join(results)


def claude_message_to_str(message, persona_instance=None) -> Optional[str]:
    """Convert a Claude Message to a string by extracting text content."""
    text_parts = []
    for block in message.content:
        if isinstance(block, TextBlock):
            text_parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            tool_str = tool_to_str(block, persona_instance)
            if tool_str:
                text_parts.append(tool_str)
        else:
            text_parts.append(str(block))
    return '\n'.join(text_parts) if text_parts else None


class ClaudeCodePersona(BasePersona):
    """Claude Code persona for Jupyter AI integration."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._printed_todowrite_blocks = set()

    @property
    def defaults(self) -> PersonaDefaults:
        """Return default configuration for the Claude Code persona."""
        return PersonaDefaults(
            name="Claude",
            avatar_path="/files/.jupyter/claude.svg",
            description="Claude Code",
            system_prompt="...",
        )
    
    async def _process_response_message(self, message_iterator) -> AsyncIterator[str]:
        """Process response messages from Claude Code SDK."""
        async for response_message in message_iterator:
            self.log.info(str(response_message))
            if isinstance(response_message, AssistantMessage):
                msg_str = claude_message_to_str(response_message, self)
                if msg_str is not None:
                    yield msg_str + '\n\n'

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

    async def process_message(self, message: Message) -> None:
        """Process incoming message and stream Claude Code response."""
        self._printed_todowrite_blocks.clear()
        async_gen = None
        prompt = self._generate_prompt(message)
        try:
            async_gen = query(
                prompt=prompt,
                options=ClaudeCodeOptions(
                    max_turns=20,
                    cwd=self.get_workspace_dir(),
                    permission_mode='bypassPermissions'
                )
            )
            await self.stream_message(self._process_response_message(async_gen))
        except Exception as e:
            self.log.error(f"Error in process_message: {e}")
            await self.send_message(f"Sorry, I have had an internal error while working on that: {e}")
        finally:
            if async_gen is not None:
                await async_gen.aclose()

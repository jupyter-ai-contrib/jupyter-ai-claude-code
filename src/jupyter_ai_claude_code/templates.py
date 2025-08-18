"""Message template management for Claude Code persona."""

from typing import Dict, Any, List, Optional
import datetime
from jinja2 import Template
from jupyterlab_chat.models import Message, NewMessage
from claude_code_sdk import TextBlock, ToolUseBlock


# Template for rendering todo lists with progress
TODO_TEMPLATE = Template("""
{%- if todos %}
#### Task Progress

{%- for todo in todos %}
{%- if todo.status == 'completed' %}
- [x] ~~{{ todo.content }}~~
{%- elif todo.status == 'in_progress' %}
- [ ] **{{ todo.content }}** *(in progress)*
{%- else %}
- [ ] {{ todo.content }}
{%- endif %}
{%- endfor %}

{%- endif %}

{%- if current_action %}
#### Current Action
{{ current_action }}

{%- endif %}

{%- if previous_actions %}
<details>
<summary>Previous Actions ({{ previous_actions|length }})</summary>

{%- for action in previous_actions %}
{{ loop.index }}. {{ action }}
{%- endfor %}

</details>

{%- endif %}

{%- if response_text %}
{{ response_text }}
{%- endif %}
""".strip())


class TemplateManager:
    """Manages in-place template message updates."""
    
    def __init__(self, persona):
        self.persona = persona
        self.message_id = None
        self.todos = []
        self.action = None
        self.previous_actions = []
        self.text_parts = []
        self.active = False

    def _same_todo_list(self, new_todos):
        """Check if this is the same todo list (just status updates)."""
        if not self.todos:
            return False
        old_ids = {t['id'] for t in self.todos}
        new_ids = {t['id'] for t in new_todos}
        return old_ids == new_ids

    async def update_todos(self, todos):
        """Update todo list, creating or updating message as needed."""
        if self._same_todo_list(todos) and self.active:
            self.todos = todos
            await self._update_message()
        else:
            # New todo list - create new message
            self.todos = todos
            self.active = True
            await self._create_message()
        return ""

    async def update_action(self, action):
        """Update current action in template."""
        if self.active:
            # Move current action to previous actions if it exists
            if self.action and self.action != action:
                self.previous_actions.append(self.action)
            
            self.action = action
            await self._update_message()
            return ""
        return action

    async def update_text(self, text):
        """Add text to template response."""
        if self.active:
            self.text_parts.append(text)
            await self._update_message()
            return ""
        return text

    async def _create_message(self):
        """Create new template message."""
        # Don't override main persona's writing state - it's already set
        content = self._render_template()
        new_msg = NewMessage(body=content, sender=self.persona.id)
        self.message_id = self.persona.ychat.add_message(new_msg)

    async def _update_message(self):
        """Update existing template message."""
        if not self.message_id:
            return
        
        # Update awareness to show writing to specific message
        self.persona.awareness.set_local_state_field("isWriting", self.message_id)
        content = self._render_template()
        
        msg = Message(
            id=self.message_id,
            time=datetime.datetime.now().timestamp(),
            body=content,
            sender=self.persona.id
        )
        self.persona.ychat.update_message(msg, append=False)

    def _render_template(self):
        """Render current template state."""
        return TODO_TEMPLATE.render(
            todos=self.todos,
            current_action=self.action,
            previous_actions=self.previous_actions if len(self.previous_actions) > 0 else None,
            response_text='\n'.join(self.text_parts) if self.text_parts else None
        )

    async def complete(self):
        """Complete template - move current action to history and clear it."""
        if self.active and self.message_id:
            # Move current action to previous actions if it exists
            if self.action:
                self.previous_actions.append(self.action)
                self.action = None  # Clear current action
            
            # Do final template update to show completed state
            await self._update_message()
        
        # Don't reset here - preserve the completed state
        # Just mark as inactive and clear message ID
        self.message_id = None
        self.active = False

    def reset(self):
        """Reset for new conversation."""
        self.message_id = None
        self.todos = []
        self.action = None
        self.previous_actions = []
        self.text_parts = []
        self.active = False


# Tool parameter mapping for display formatting
TOOL_PARAM_MAPPING = {
    'Task': 'description', 'Bash': 'command', 'Glob': 'pattern', 'Grep': 'pattern',
    'LS': 'path', 'Read': 'file_path', 'Edit': 'file_path', 'MultiEdit': 'file_path', 
    'Write': 'file_path', 'NotebookRead': 'notebook_path', 'NotebookWrite': 'notebook_path',
    'WebFetch': 'url', 'WebSearch': 'query'
}


def format_tool_input(tool_name, tool_input):
    """Format tool input for display."""
    if tool_name in TOOL_PARAM_MAPPING:
        key = TOOL_PARAM_MAPPING[tool_name]
        return tool_input.get(key, '')
    
    # Format remaining args (excluding content)
    args = [f"{k}={v}" for k, v in tool_input.items() if k != 'content']
    return ', '.join(args)


async def process_message_block(block, template_mgr=None):
    """Process a single message block (text or tool)."""
    if isinstance(block, TextBlock):
        if template_mgr and template_mgr.active:
            await template_mgr.update_text(block.text)
            return None  # Template handles display, don't stream
        return block.text
    
    elif isinstance(block, ToolUseBlock):
        if block.name == 'TodoWrite' and template_mgr:
            todos = block.input.get('todos', [])
            await template_mgr.update_todos(todos)
            return None  # Template handles display, don't stream
        
        # Regular tool display
        tool_display = f"🛠️ {block.name}({format_tool_input(block.name, block.input)})"
        
        if template_mgr and template_mgr.active:
            await template_mgr.update_action(tool_display)
            return None  # Template handles display, don't stream
        return tool_display
    
    return str(block)


async def claude_message_to_str(message, template_mgr=None) -> Optional[str]:
    """Convert Claude Message to string, handling template updates."""
    text_parts = []
    for block in message.content:
        result = await process_message_block(block, template_mgr)
        if result is not None:  # Only add non-None results
            text_parts.append(result)
    return '\n'.join(text_parts) if text_parts else None
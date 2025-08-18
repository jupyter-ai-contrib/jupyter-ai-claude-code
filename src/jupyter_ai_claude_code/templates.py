"""Claude Code message template management for Jupyter AI persona."""

from typing import Dict, Any, List, Optional
import datetime
import os
import re
from dataclasses import dataclass, field
from jinja2 import Template
from jupyterlab_chat.models import Message, NewMessage
from claude_code_sdk import TextBlock, ToolUseBlock, ToolResultBlock, AssistantMessage


@dataclass
class MessageData:
    """Dataclass containing all data needed for message template rendering."""
    todos: List[Dict[str, Any]] = field(default_factory=list)
    current_action: Dict[str, str] = None
    completed_actions: List[str] = field(default_factory=list)
    current_result: str = None
    initial_text: str = None
    final_text: str = None


# Template for rendering consolidated actions and final response
TODO_TEMPLATE = Template("""
{%- if data.initial_text %}
{{ data.initial_text }}

{%- endif %}

{% if data.todos %}
**Task Progress:**

{%- for todo in data.todos %}
{%- if todo.status == 'completed' %}
- [x] ~~{{ todo.content }}~~
{%- elif todo.status == 'in_progress' %}
- [ ] **{{ todo.content }}** *(in progress)*
{%- else %}
- [ ] {{ todo.content }}
{%- endif %}
{%- endfor %}

{%- endif %}

{%- if data.current_action %}

**Current Tool:**  
{{ data.current_action.tool_call }}  
⎿  Executing...

{%- endif %}

{% if data.completed_actions and data.completed_actions|length > 0 %}

**Tools Called:**
<details>
<summary>See details ({{ data.completed_actions|length }})</summary>

{%- for action in data.completed_actions %}

{{ action }}  
⎿  Completed
{%- endfor %}

</details>
<br>
{% endif %}

{% if data.current_result or data.final_text %}
**Response:**
{% if data.current_result %}
{{ data.current_result }}
{% endif %}
{% if data.final_text %}
{{ data.final_text }}
{% endif %}
{% endif %}
""".strip())


class ClaudeCodeTemplateManager:
    """Manages in-place template message updates for Claude Code SDK messages."""
    
    # Constants
    MAX_TOOL_VALUE_LENGTH = 60
    MAX_ARG_LENGTH = 30
    
    # Tool parameter mapping for display formatting
    TOOL_PARAM_MAPPING = {
        'Task': 'description', 'Bash': 'command', 'Glob': 'pattern', 'Grep': 'pattern',
        'LS': 'path', 'Read': 'file_path', 'Edit': 'file_path', 'MultiEdit': 'file_path', 
        'Write': 'file_path', 'NotebookRead': 'notebook_path', 'NotebookWrite': 'notebook_path',
        'WebFetch': 'url', 'WebSearch': 'query'
    }
    
    # Tools that should have clickable file links
    FILE_LINK_TOOLS = {'Read', 'Edit', 'MultiEdit', 'Write'}
    
    def __init__(self, persona):
        self.persona = persona
        self.message_id = None
        self.message_data = MessageData()  # Single dataclass for all template data
        self.active = False
        self.turn_active = False  # Track if we're in an active Claude turn
        self.has_actions = False  # Track if we've seen any tool calls
        self.in_final_phase = False  # Track if we're in final summary phase

    def _same_todo_list(self, new_todos):
        """Check if this is the same todo list (just status updates)."""
        if not self.message_data.todos:
            return False
        old_ids = {t['id'] for t in self.message_data.todos}
        new_ids = {t['id'] for t in new_todos}
        return old_ids == new_ids

    async def _ensure_message_exists(self):
        """Ensure a message exists, creating one if needed."""
        if not self.message_id:
            await self._create_message()
        else:
            await self._update_message()

    async def update_todos(self, todos):
        """Update todo list, creating or updating message as needed."""
        self.message_data.todos = todos
        
        # Always ensure template is active when we have todos
        if not self.active:
            self.active = True
        
        await self._ensure_message_exists()
        return ""

    async def update_action(self, action):
        """Start a new action - show it as current action."""
        if self.active:
            # Complete previous action if it exists (just add tool call to completed)
            if self.message_data.current_action:
                self.message_data.completed_actions.append(self.message_data.current_action['tool_call'])
            
            # Mark that we've seen actions
            self.has_actions = True
            
            # Always start template if not active yet
            if not self.turn_active:
                self.turn_active = True
                if not self.message_id:
                    await self._create_message()
            
            # Set new current action
            self.message_data.current_action = {
                'tool_call': action,
                'result': 'Executing...'
            }
            
            # Reset final phase when we start a new action
            self.in_final_phase = False
            
            await self._ensure_message_exists()
            return ""
        return action

    async def update_action_result(self, result):
        """Update the result of the current action."""
        if self.active and self.message_data.current_action:
            # Update the current action's result (just escape markdown, no aggressive path linking)
            self.message_data.current_action['result'] = self._escape_markdown(result)
            
            # Set this as the current result (just the result text, no tool call)
            self.message_data.current_result = self.message_data.current_action['result']
            
            # After receiving a result, the action is complete
            # Move just the tool call to completed actions
            self.message_data.completed_actions.append(self.message_data.current_action['tool_call'])
            self.message_data.current_action = None
            self.in_final_phase = True  # Now any subsequent text should go to final_text
            
            await self._ensure_message_exists()
            return ""
        return result

    async def update_text(self, text):
        """Add text to template response."""
        if self.active:
            # If we haven't seen actions yet, add to initial text
            if not self.has_actions:
                if self.message_data.initial_text:
                    self.message_data.initial_text += '\n' + text
                else:
                    self.message_data.initial_text = text
            elif self.message_data.current_action and not self.in_final_phase:
                # If we have a current action and not in final phase, treat this text as its result
                # This handles cases where tool results come as text blocks
                if self.message_data.current_action['result'] == 'Executing...':
                    self.message_data.current_action['result'] = text
                    # Update current result display (just the result text)
                    self.message_data.current_result = text
                else:
                    # Append to existing result if already has content
                    self.message_data.current_action['result'] += '\n' + text
                    self.message_data.current_result = self.message_data.current_action['result']
            else:
                # No current action or we're in final phase - this is final summary text
                # This should appear after the horizontal rule
                if self.message_data.final_text:
                    self.message_data.final_text += '\n' + text
                else:
                    self.message_data.final_text = text
                self.in_final_phase = True  # Mark that we're now in final phase
            
            # Create or update message
            await self._ensure_message_exists()
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
        return TODO_TEMPLATE.render(data=self.message_data)

    async def complete(self):
        """Complete template - move current action to completed actions."""
        if self.active and self.message_id:
            # Move current action to completed actions if it exists
            if self.message_data.current_action:
                self.message_data.completed_actions.append(self.message_data.current_action['tool_call'])
                self.message_data.current_action = None
            
            # Mark that we're now in final phase - any subsequent text should go to final_text
            self.in_final_phase = True
            
            # Do final template update to show completed state
            await self._ensure_message_exists()
        elif self.active:
            # Still mark final phase even without message_id
            self.in_final_phase = True
        
        # Keep template active but mark turn as inactive
        # This allows final text to still be processed
        self.turn_active = False

    def _escape_markdown(self, text):
        """Escape markdown characters in text to prevent formatting issues."""
        # Escape common markdown characters that could cause formatting problems
        escapes = {
            '*': '\\*',
            '_': '\\_', 
            '`': '\\`',
            '#': '\\#',
            '[': '\\[',
            ']': '\\]',
            '(': '\\(',
            ')': '\\)',
            '{': '\\{',
            '}': '\\}',
            '\\': '\\\\'
        }
        result = str(text)
        for char, escape in escapes.items():
            result = result.replace(char, escape)
        return result

    def _make_jupyter_file_link(self, file_path, tool_name=None):
        """Convert file path to clickable JupyterLab file link if path exists or will be created."""
        server_root_reference = self._get_server_root_reference()
        relative_path = self._resolve_relative_path(file_path, server_root_reference)
        
        # Always create links for Write tools (file will be created)
        # For other tools, only create link if file exists
        should_create_link = (
            tool_name == 'Write' or 
            self._path_exists_on_server(relative_path, server_root_reference)
        )
        
        if should_create_link:
            return f"[{file_path}](/files/{relative_path})"
        else:
            # Return plain text if path doesn't exist and it's not a Write operation
            return str(file_path)
    
    def _get_server_root_reference(self):
        """Get server root directory reference from persona."""
        try:
            workspace_dir = getattr(self.persona, 'get_workspace_dir', lambda: None)()
            chat_dir = getattr(self.persona, 'get_chat_dir', lambda: None)()
            return workspace_dir or chat_dir
        except Exception:
            return None
    
    def _resolve_relative_path(self, file_path, server_root_reference):
        """Resolve file path to be relative to server root."""
        if not file_path.startswith('/') or not server_root_reference:
            return file_path.lstrip('/')
        
        try:
            relative_path = os.path.relpath(file_path, start=server_root_reference)
            # If path goes outside server root, use basename only
            return os.path.basename(file_path) if relative_path.startswith('..') else relative_path
        except (ValueError, OSError):
            return os.path.basename(file_path)
    
    def _path_exists_on_server(self, relative_path, server_root_reference):
        """Check if the relative path exists on the server."""
        if not server_root_reference or not relative_path:
            return False
        
        try:
            # Construct full path from server root
            full_path = os.path.join(server_root_reference, relative_path)
            # Normalize path to handle any .. or . components
            normalized_path = os.path.normpath(full_path)
            
            # Security check: ensure normalized path is still within server root
            if not normalized_path.startswith(os.path.normpath(server_root_reference)):
                return False
            
            # Check if file exists
            return os.path.exists(normalized_path)
        except Exception:
            return False

    def format_tool_input(self, tool_name, tool_input):
        """Format tool input for Claude Code CLI style display."""
        if tool_name in self.TOOL_PARAM_MAPPING:
            key = self.TOOL_PARAM_MAPPING[tool_name]
            value = tool_input.get(key, '')
            
            # Make file paths clickable for file-related tools
            if tool_name in self.FILE_LINK_TOOLS and value:
                if len(str(value)) > self.MAX_TOOL_VALUE_LENGTH:
                    truncated = str(value)[:self.MAX_TOOL_VALUE_LENGTH] + '…'
                    return self._make_jupyter_file_link(truncated, tool_name)
                return self._make_jupyter_file_link(str(value), tool_name)
            else:
                # For other tools, just escape markdown
                if len(str(value)) > self.MAX_TOOL_VALUE_LENGTH:
                    return self._escape_markdown(str(value)[:self.MAX_TOOL_VALUE_LENGTH] + '…')
                return self._escape_markdown(str(value))
        
        # Format remaining args (excluding content)
        args = []
        for k, v in tool_input.items():
            if k != 'content':
                val_str = str(v)
                if len(val_str) > self.MAX_ARG_LENGTH:
                    val_str = val_str[:self.MAX_ARG_LENGTH] + '…'
                args.append(f"{k}={self._escape_markdown(val_str)}")
        return ', '.join(args)

    async def process_message_block(self, block):
        """Process a single Claude SDK message block (text or tool)."""
        if isinstance(block, TextBlock):
            # Always capture text in template during active turn
            if not self.active:
                # Start template on first content
                self.active = True
                await self.update_text(block.text)
                return None
            else:
                await self.update_text(block.text)
                return None  # Template handles all display
        
        elif isinstance(block, ToolUseBlock):
            if block.name == 'TodoWrite':
                todos = block.input.get('todos', [])
                await self.update_todos(todos)
                return None  # Template handles display, don't stream
            
            # Regular tool display - always capture in template
            tool_display = f"{block.name}({self.format_tool_input(block.name, block.input)})"
            await self.update_action(tool_display)
            return None  # Template handles all display
        
        elif isinstance(block, ToolResultBlock):
            # Handle tool result - always capture in template
            result_text = str(block.content) if hasattr(block, 'content') else str(block)
            await self.update_action_result(result_text)
            return None  # Template handles all display
        
        return None  # Don't stream anything - template handles all

    async def claude_message_to_str(self, message) -> Optional[str]:
        """Convert Claude SDK Message to string, handling template updates."""
        text_parts = []
        for block in message.content:
            result = await self.process_message_block(block)
            if result is not None:  # Only add non-None results
                text_parts.append(result)
        return '\n'.join(text_parts) if text_parts else None

    def reset(self):
        """Reset for new conversation."""
        self.message_id = None
        self.message_data = MessageData()  # Reset to new dataclass instance
        self.active = False
        self.turn_active = False
        self.has_actions = False
        self.in_final_phase = False



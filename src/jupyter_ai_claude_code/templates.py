"""Claude Code message template management for Jupyter AI persona."""

from typing import Dict, Any, List, Optional
import datetime
from jinja2 import Template
from jupyterlab_chat.models import Message, NewMessage
from claude_code_sdk import TextBlock, ToolUseBlock, ToolResultBlock, AssistantMessage


# Template for rendering consolidated actions and final response
TODO_TEMPLATE = Template("""
{%- if initial_text %}
{{ initial_text }}

{%- endif %}

{% if todos %}
**Task Progress:**

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

**Current Tool:**  
{{ current_action.tool_call }}  
⎿  Executing...

{%- endif %}

{% if completed_actions %}

**Tools Called:**
<details>
<summary>See details ({{ completed_actions|length }})</summary>

{%- for action in completed_actions %}

{{ action }}  
⎿  Completed
{%- endfor %}

</details>
<br>
{% endif %}

{% if current_result or final_text %}
**Response:**
{% if current_result %}
{{ current_result }}
{% endif %}
{% if final_text %}
{{ final_text }}
{% endif %}
{% endif %}
""".strip())


class ClaudeCodeTemplateManager:
    """Manages in-place template message updates for Claude Code SDK messages."""
    
    # Tool parameter mapping for display formatting
    TOOL_PARAM_MAPPING = {
        'Task': 'description', 'Bash': 'command', 'Glob': 'pattern', 'Grep': 'pattern',
        'LS': 'path', 'Read': 'file_path', 'Edit': 'file_path', 'MultiEdit': 'file_path', 
        'Write': 'file_path', 'NotebookRead': 'notebook_path', 'NotebookWrite': 'notebook_path',
        'WebFetch': 'url', 'WebSearch': 'query'
    }
    
    def __init__(self, persona):
        self.persona = persona
        self.message_id = None
        self.todos = []
        self.current_action = None  # Currently executing action
        self.completed_actions = []  # List of tool calls (without results)
        self.current_result = None   # Current result message (replaces previous)
        self.initial_text_parts = []  # Text before any tool calls
        self.final_text_parts = []    # Text after tool calls
        self.active = False
        self.turn_active = False  # Track if we're in an active Claude turn
        self.has_actions = False  # Track if we've seen any tool calls
        self.in_final_phase = False  # Track if we're in final summary phase

    def _same_todo_list(self, new_todos):
        """Check if this is the same todo list (just status updates)."""
        if not self.todos:
            return False
        old_ids = {t['id'] for t in self.todos}
        new_ids = {t['id'] for t in new_todos}
        return old_ids == new_ids

    async def update_todos(self, todos):
        """Update todo list, creating or updating message as needed."""
        self.todos = todos
        
        # Always ensure template is active when we have todos
        if not self.active:
            self.active = True
            await self._create_message()
        else:
            await self._update_message()
        return ""

    async def update_action(self, action):
        """Start a new action - show it as current action."""
        if self.active:
            # Complete previous action if it exists (just add tool call to completed)
            if self.current_action:
                self.completed_actions.append(self.current_action['tool_call'])
            
            # Mark that we've seen actions
            self.has_actions = True
            
            # Always start template if not active yet
            if not self.turn_active:
                self.turn_active = True
                await self._create_message()
            
            # Set new current action
            self.current_action = {
                'tool_call': action,
                'result': 'Executing...'
            }
            
            # Reset final phase when we start a new action
            self.in_final_phase = False
            
            await self._update_message()
            return ""
        return action

    async def update_action_result(self, result):
        """Update the result of the current action."""
        if self.active and self.current_action:
            # Update the current action's result
            self.current_action['result'] = self._escape_markdown(result)
            
            # Set this as the current result (just the result text, no tool call)
            self.current_result = self.current_action['result']
            
            # After receiving a result, the action is complete
            # Move just the tool call to completed actions
            self.completed_actions.append(self.current_action['tool_call'])
            self.current_action = None
            self.in_final_phase = True  # Now any subsequent text should go to final_text
            
            await self._update_message()
            return ""
        return result

    async def update_text(self, text):
        """Add text to template response."""
        if self.active:
            # If we haven't seen actions yet, add to initial text
            if not self.has_actions:
                self.initial_text_parts.append(text)
            elif self.current_action and not self.in_final_phase:
                # If we have a current action and not in final phase, treat this text as its result
                # This handles cases where tool results come as text blocks
                if self.current_action['result'] == 'Executing...':
                    self.current_action['result'] = text
                    # Update current result display (just the result text)
                    self.current_result = text
                else:
                    # Append to existing result if already has content
                    self.current_action['result'] += '\\n' + text
                    self.current_result = self.current_action['result']
            else:
                # No current action or we're in final phase - this is final summary text
                # This should appear after the horizontal rule
                self.final_text_parts.append(text)
                self.in_final_phase = True  # Mark that we're now in final phase
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
            current_action=self.current_action,
            completed_actions=self.completed_actions if len(self.completed_actions) > 0 else None,
            current_result=self.current_result,
            initial_text='\n'.join(self.initial_text_parts) if self.initial_text_parts else None,
            final_text='\n'.join(self.final_text_parts) if self.final_text_parts else None
        )

    async def complete(self):
        """Complete template - move current action to completed actions."""
        if self.active and self.message_id:
            # Move current action to completed actions if it exists
            if self.current_action:
                self.completed_actions.append(self.current_action)
                self.current_action = None
            
            # Mark that we're now in final phase - any subsequent text should go to final_text
            self.in_final_phase = True
            
            # Do final template update to show completed state
            await self._update_message()
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

    def format_tool_input(self, tool_name, tool_input):
        """Format tool input for Claude Code CLI style display."""
        if tool_name in self.TOOL_PARAM_MAPPING:
            key = self.TOOL_PARAM_MAPPING[tool_name]
            value = tool_input.get(key, '')
            # For long values, truncate with ellipsis
            if len(str(value)) > 60:
                return self._escape_markdown(str(value)[:60] + '…')
            return self._escape_markdown(str(value))
        
        # Format remaining args (excluding content)
        args = []
        for k, v in tool_input.items():
            if k != 'content':
                val_str = str(v)
                if len(val_str) > 30:
                    val_str = val_str[:30] + '…'
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
        self.todos = []
        self.current_action = None
        self.completed_actions = []
        self.current_result = None
        self.initial_text_parts = []
        self.final_text_parts = []
        self.active = False
        self.turn_active = False
        self.has_actions = False
        self.in_final_phase = False



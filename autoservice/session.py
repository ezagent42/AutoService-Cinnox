"""
Session management for skill domains.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from autoservice.core import ensure_dir
from autoservice.config import get_domain_config


# Domain type prefixes
DOMAIN_PREFIXES = {
    'customer-service': 'cs',
    'marketing': 'mk'
}


def get_claude_session_id() -> str:
    """Auto-detect the current Claude Code session ID.

    Walks up the process tree to find the parent Claude Code process PID,
    then uses `lsof` to find the open `.claude/tasks/{session_uuid}` directory
    which Claude Code keeps open for the duration of the session.

    Raises:
        RuntimeError: If Claude Code process or session ID cannot be detected.

    Returns:
        The current Claude Code session ID (UUID string).
    """
    import subprocess

    claude_pid = _find_claude_pid()
    if not claude_pid:
        raise RuntimeError(
            "Cannot detect Claude Code parent process. / 无法检测到 Claude Code 父进程。"
            "Please confirm this script is running inside a Claude Code session. / "
            "请确认此脚本在 Claude Code 会话中运行。"
        )

    session_id = _detect_session_from_pid(claude_pid)
    if not session_id:
        raise RuntimeError(
            f"Cannot detect session ID from Claude Code process (PID={claude_pid}). / "
            f"无法从 Claude Code 进程 (PID={claude_pid}) 检测到会话 ID。"
            "Please confirm your Claude Code version supports .claude/tasks/ directory. / "
            "请确认 Claude Code 版本支持 .claude/tasks/ 目录。"
        )

    return session_id


def _find_claude_pid() -> Optional[int]:
    """Walk up the process tree to find the Claude Code parent process PID."""
    import subprocess

    pid = os.getpid()
    for _ in range(20):  # Max depth to prevent infinite loop
        result = subprocess.run(
            ['ps', '-o', 'ppid=', '-p', str(pid)],
            capture_output=True, text=True, timeout=5
        )
        ppid = result.stdout.strip()
        if not ppid or ppid == '0':
            break
        pid = int(ppid)

        # Check if this process is Claude Code
        cmd_result = subprocess.run(
            ['ps', '-o', 'command=', '-p', str(pid)],
            capture_output=True, text=True, timeout=5
        )
        command = cmd_result.stdout.strip()
        if command.startswith('claude ') or command == 'claude':
            return pid
    return None


def _detect_session_from_pid(claude_pid: int) -> Optional[str]:
    """Detect session ID by finding the .claude/tasks/{uuid} dir open by Claude.

    Tries lsof first, then falls back to scanning ~/.claude/tasks/ for the
    most recently modified session directory.
    """
    import subprocess

    # Method 1: lsof
    result = subprocess.run(
        ['lsof', '-p', str(claude_pid)],
        capture_output=True, text=True, timeout=10
    )
    uuid_pattern = re.compile(
        r'\.claude/tasks/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    )
    match = uuid_pattern.search(result.stdout)
    if match:
        return match.group(1)

    # Method 2: Fallback — scan ~/.claude/tasks/ for the most recent session dir
    tasks_dir = Path.home() / '.claude' / 'tasks'
    if tasks_dir.exists():
        uuid_dir_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        )
        candidates = [
            d for d in tasks_dir.iterdir()
            if d.is_dir() and uuid_dir_pattern.match(d.name)
        ]
        if candidates:
            # Pick the most recently modified directory
            latest = max(candidates, key=lambda d: d.stat().st_mtime)
            return latest.name

    return None


def init_session(domain: str, config: Optional[dict] = None) -> tuple[str, Path]:
    """Initialize a session: detect ID, generate session name, create directory.

    Call this at the START of a skill session (before the conversation begins)
    so that any detection failure is caught immediately.

    Args:
        domain: Domain name ('marketing', 'customer-service')
        config: Optional domain configuration

    Raises:
        RuntimeError: If Claude Code session ID cannot be detected.

    Returns:
        Tuple of (session_id, session_dir_path).
    """
    if config is None:
        config = get_domain_config(domain)

    session_id = generate_session_id(domain, config=config)
    base_dir = Path(config['database_path'])
    history_dir = ensure_dir(base_dir / 'history')
    session_dir = ensure_dir(history_dir / session_id)

    return session_id, session_dir


def generate_session_id(
    domain: str,
    claude_session_id: Optional[str] = None,
    config: Optional[dict] = None
) -> str:
    """Generate a unified session ID.

    Format: {type}_{YYYYMMDD}_{seq}_{claude_session_id}
    Example: cs_20260125_001_abc123

    Args:
        domain: Domain name ('marketing', 'customer-service')
        claude_session_id: Claude Code conversation session ID.
            If None, auto-detected from the current Claude Code session.
        config: Optional domain configuration

    Returns:
        Generated session ID string
    """
    if claude_session_id is None:
        claude_session_id = get_claude_session_id()

    if config is None:
        config = get_domain_config(domain)

    # Get type prefix
    prefix = DOMAIN_PREFIXES.get(domain, domain[:2])

    # Get date
    date_str = datetime.now().strftime("%Y%m%d")

    # Calculate sequence number based on existing sessions
    base_dir = Path(config['database_path'])
    history_dir = base_dir / 'history'

    seq = 1
    if history_dir.exists():
        # Pattern: {prefix}_{date}_{seq}_{claude_id}
        pattern = re.compile(rf"^{prefix}_{date_str}_(\d{{3}})_")
        for item in history_dir.iterdir():
            if item.is_dir():
                match = pattern.match(item.name)
                if match:
                    existing_seq = int(match.group(1))
                    seq = max(seq, existing_seq + 1)

    # Format session ID
    session_id = f"{prefix}_{date_str}_{seq:03d}_{claude_session_id}"

    return session_id


def save_session(
    domain: str,
    session_id: str,
    product: str,
    customer: str,
    operator: str,
    conversation: list,
    review: dict,
    config: Optional[dict] = None
) -> Path:
    """Save a session with conversation and review to history.

    Args:
        domain: Domain name ('marketing', 'customer-service')
        session_id: Unique session identifier
        product: Product/service name
        customer: Customer persona name
        operator: Strategy/operator name
        conversation: List of conversation messages
        review: Review/evaluation dictionary
        config: Optional domain configuration

    Returns:
        Path to the created session directory
    """
    if config is None:
        config = get_domain_config(domain)

    base_dir = Path(config['database_path'])
    history_dir = ensure_dir(base_dir / 'history')
    session_dir = ensure_dir(history_dir / session_id)

    # Get role labels from config
    roles = config.get('roles', {})
    assistant_role = roles.get('assistant', 'assistant')
    user_role = roles.get('user', 'user')
    assistant_label = roles.get('assistant_label', 'Assistant')
    user_label = roles.get('user_label', 'User')

    session_config = config.get('session', {})
    title_prefix = session_config.get('title_prefix', f'{domain.title()} Session')

    # Build session data
    session_data = {
        'session_id': session_id,
        'product': product,
        'customer': customer,
        'operator': operator,
        'timestamp': datetime.now().isoformat(),
        'conversation': conversation or [],
        'review': review
    }

    # Save JSON
    with open(session_dir / 'session.json', 'w', encoding='utf-8') as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)

    # Save readable markdown
    with open(session_dir / 'README.md', 'w', encoding='utf-8') as f:
        f.write(f"# {title_prefix}: {session_id}\n\n")
        f.write(f"**Date**: {session_data['timestamp']}\n\n")
        f.write(f"**Product**: {product}\n\n")
        f.write(f"**Customer**: {customer}\n\n")
        f.write(f"**Operator/Strategy**: {operator}\n\n")

        # Write conversation
        f.write("## Conversation\n\n")
        if conversation:
            for turn in conversation:
                role = turn.get('role', 'unknown')
                content = turn.get('content', '')

                # Map role to label
                if role in (assistant_role, 'salesperson', 'agent'):
                    f.write(f"**{assistant_label}**: {content}\n\n")
                elif role in (user_role, 'customer'):
                    f.write(f"**{user_label}**: {content}\n\n")
                else:
                    f.write(f"**{role}**: {content}\n\n")
        else:
            f.write("(No conversation recorded)\n\n")

        # Write review
        f.write("---\n\n## Review\n\n")
        if isinstance(review, dict):
            for key, value in review.items():
                f.write(f"### {key.replace('_', ' ').title()}\n\n")
                if isinstance(value, list):
                    for item in value:
                        f.write(f"- {item}\n")
                else:
                    f.write(f"{value}\n")
                f.write("\n")
        else:
            f.write(str(review))

    print(f"Session saved to: {session_dir}")
    return session_dir

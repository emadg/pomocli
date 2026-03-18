import os
from pathlib import Path
from typing import Tuple, Optional
from git import Repo, InvalidGitRepositoryError

def get_git_context() -> Tuple[Optional[str], Optional[str]]:
    """Returns (repo_name, branch_name) if in a git repository."""
    try:
        repo = Repo(Path.cwd(), search_parent_directories=True)
        repo_name = Path(repo.working_tree_dir).name
        branch_name = repo.active_branch.name
        return repo_name, branch_name
    except (InvalidGitRepositoryError, TypeError, ValueError):
        return None, None

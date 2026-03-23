#!/usr/bin/env python3
"""
Seed a test SQLite database with realistic data for development.
Run with: POMOCLI_DB_PATH=test_pomocli.db python scripts/seed_test_db.py
Then use it with: POMOCLI_DB_PATH=test_pomocli.db pomo report quarter
"""

import os
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Ensure we can import pomocli
sys.path.insert(0, str(Path(__file__).parent.parent))

from pomocli.db.connection import init_db, DB_PATH

def generate_data():
    print(f"Seeding test database at: {DB_PATH}")
    
    # Remove existing test DB if it exists to start fresh
    if DB_PATH.exists():
        DB_PATH.unlink()
        
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    projects = ["pomocli", "website", "backend-api", None]
    tasks = [
        "Write README", "Fix auth bug", "Setup CI/CD", "Design database",
        "Refactor timer", "Add reporting", "Code review", "Update dependencies"
    ]
    tags_pool = ["focus", "deep-work", "bugfix", "planning", "review", "admin"]
    repos = ["emad/pomocli", "emad/website", "emad/backend"]
    branches = ["main", "dev", "feature/auth", "fix/timer"]
    
    now = datetime.now()
    
    # Insert tasks
    task_ids = []
    for t in tasks:
        proj = random.choice(projects)
        est = random.choice([None, 30, 60, 120, 240])
        cursor.execute(
            "INSERT INTO tasks (project_name, task_name, estimated_minutes) VALUES (?, ?, ?)",
            (proj, t, est)
        )
        task_ids.append(cursor.lastrowid)
        
    # Generate sessions over the last 90 days
    for day_offset in range(90, -1, -1):
        # 0 to 5 sessions per day
        num_sessions = random.randint(0, 5)
        
        current_date = now - timedelta(days=day_offset)
        
        for _ in range(num_sessions):
            task_id = random.choice(task_ids)
            
            # Random start time between 9 AM and 5 PM
            hour = random.randint(9, 17)
            minute = random.randint(0, 59)
            start_time = current_date.replace(hour=hour, minute=minute, second=0)
            
            duration_mins = random.choice([15, 25, 25, 25, 50, 60])
            duration_secs = duration_mins * 60
            
            end_time = start_time + timedelta(minutes=duration_mins)
            
            status = random.choices(["completed", "stopped", "killed"], weights=[0.8, 0.15, 0.05])[0]
            
            repo = random.choice(repos) if random.random() > 0.3 else None
            branch = random.choice(branches) if repo else None
            
            cursor.execute("""
                INSERT INTO sessions (task_id, start_time, end_time, duration_logged, status, git_repo, git_branch)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, 
                start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time.strftime("%Y-%m-%d %H:%M:%S") if status != "killed" else None,
                duration_secs if status != "killed" else duration_secs // 2,
                status,
                repo,
                branch
            ))
            session_id = cursor.lastrowid
            
            # Add tags
            if random.random() > 0.5:
                num_tags = random.randint(1, 3)
                session_tags = random.sample(tags_pool, num_tags)
                for tag in session_tags:
                    cursor.execute("INSERT INTO tags (session_id, tag_name) VALUES (?, ?)", (session_id, tag))
                    
            # Add distractions
            if random.random() > 0.7:
                num_distractions = random.randint(1, 3)
                for _ in range(num_distractions):
                    distract_time = start_time + timedelta(minutes=random.randint(1, duration_mins - 1))
                    desc = random.choice(["Slack message", "Email", "Phone call", "Coworker", None])
                    cursor.execute(
                        "INSERT INTO distractions (session_id, timestamp, description) VALUES (?, ?, ?)",
                        (session_id, distract_time.strftime("%Y-%m-%d %H:%M:%S"), desc)
                    )
                    
    conn.commit()
    conn.close()
    print("Test database seeded successfully!")
    print(f"Run: POMOCLI_DB_PATH={DB_PATH} pomo report quarter")

if __name__ == "__main__":
    generate_data()

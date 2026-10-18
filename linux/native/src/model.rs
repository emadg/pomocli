use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct Completion {
    pub sequence: u64,
    pub session_id: Option<i64>,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(default)]
pub struct Snapshot {
    pub connected: bool,
    pub state: String,
    pub timer_mode: String,
    pub time_left: i64,
    pub elapsed_seconds: i64,
    pub session_id: Option<i64>,
    pub task_name: String,
    pub project_name: Option<String>,
    pub daemon_instance: Option<String>,
    pub completion_event: Option<Completion>,
    pub pause_source: Option<String>,
    pub feedback: bool,
}
impl Default for Snapshot {
    fn default() -> Self {
        Self {
            connected: false,
            state: "stopped".into(),
            timer_mode: "countdown".into(),
            time_left: 0,
            elapsed_seconds: 0,
            session_id: None,
            task_name: String::new(),
            project_name: None,
            daemon_instance: None,
            completion_event: None,
            pause_source: None,
            feedback: false,
        }
    }
}
impl Snapshot {
    pub fn from_data(mut data: Value) -> anyhow::Result<Self> {
        // Older daemons may return a null task name when idle.
        if data.get("task_name").is_some_and(Value::is_null) {
            data["task_name"] = json!("");
        }
        let mut snapshot: Self = serde_json::from_value(data)?;
        snapshot.connected = true;
        Ok(snapshot)
    }
    pub fn active(&self) -> bool {
        self.connected
            && self.session_id.is_some()
            && matches!(self.state.as_str(), "running" | "paused")
    }
    pub fn timer(&self) -> String {
        let seconds = if self.timer_mode == "elapsed" {
            self.elapsed_seconds
        } else {
            self.time_left
        }
        .max(0);
        if seconds >= 3600 {
            format!(
                "{}:{:02}:{:02}",
                seconds / 3600,
                seconds / 60 % 60,
                seconds % 60
            )
        } else {
            format!("{:02}:{:02}", seconds / 60, seconds % 60)
        }
    }
    pub fn title(&self) -> String {
        if !self.connected {
            "PomoCLI — disconnected".into()
        } else if self.feedback {
            "PomoCLI — distraction logged".into()
        } else if self.active() {
            format!(
                "{}{} — {}",
                if self.state == "paused" {
                    "Paused · "
                } else {
                    ""
                },
                self.timer(),
                self.task_name
            )
        } else {
            "PomoCLI — ready".into()
        }
    }
    pub fn completion_description(&self, previous: &Self) -> String {
        let completed = self
            .completion_event
            .as_ref()
            .and_then(|event| event.session_id);
        if completed.is_some() && self.session_id == completed && !self.task_name.is_empty() {
            self.task_name.clone()
        } else if completed.is_some()
            && previous.session_id == completed
            && !previous.task_name.is_empty()
        {
            previous.task_name.clone()
        } else {
            "Your focus session is complete.".into()
        }
    }
    pub fn guards(&self) -> Value {
        json!({ "expected_session_id": self.session_id, "expected_state": self.state, "expected_daemon_instance": self.daemon_instance })
    }
}
#[derive(Default)]
pub struct CompletionTracker {
    instance: Option<String>,
    sequence: Option<u64>,
    initialized: bool,
}
impl CompletionTracker {
    /// Baseline on initial connection or daemon replacement, never replay history.
    pub fn observe(&mut self, snapshot: &Snapshot) -> bool {
        let sequence = snapshot
            .completion_event
            .as_ref()
            .map(|event| event.sequence);
        if !self.initialized || self.instance != snapshot.daemon_instance {
            self.initialized = true;
            self.instance = snapshot.daemon_instance.clone();
            self.sequence = sequence;
            return false;
        }
        let completed = sequence.is_some_and(|new| new > self.sequence.unwrap_or(0));
        self.sequence = sequence;
        completed
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AutomaticPause {
    pub instance: String,
    pub session_id: i64,
    pub source: String,
}
impl AutomaticPause {
    pub fn from_running(snapshot: &Snapshot, source: &str) -> Option<Self> {
        if snapshot.state != "running" {
            return None;
        }
        Some(Self {
            instance: snapshot.daemon_instance.clone()?,
            session_id: snapshot.session_id?,
            source: source.into(),
        })
    }
    pub fn matches(&self, snapshot: &Snapshot) -> bool {
        snapshot.connected
            && snapshot.daemon_instance.as_deref() == Some(&self.instance)
            && snapshot.session_id == Some(self.session_id)
            && snapshot.state == "paused"
            && snapshot.pause_source.as_deref() == Some(&self.source)
    }
    pub fn guards(&self) -> Value {
        json!({ "expected_session_id": self.session_id, "expected_state": "paused", "expected_pause_source": self.source, "expected_daemon_instance": self.instance })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn maps_idle_and_elapsed_status() {
        let s = Snapshot::from_data(json!({"state":"stopped", "task_name":null})).unwrap();
        assert!(!s.active());
        assert!(s.connected);
        let s = Snapshot::from_data(
            json!({"state":"running","session_id":2,"timer_mode":"elapsed","elapsed_seconds":3661}),
        )
        .unwrap();
        assert_eq!(s.timer(), "1:01:01");
    }
    #[test]
    fn completion_baseline_deduplicates_and_survives_reconnect() {
        let mut tracker = CompletionTracker::default();
        let mut s = Snapshot {
            daemon_instance: Some("one".into()),
            completion_event: Some(Completion {
                sequence: 0,
                session_id: None,
            }),
            ..Snapshot::default()
        };
        assert!(!tracker.observe(&s));
        s.completion_event.as_mut().unwrap().sequence = 1;
        assert!(tracker.observe(&s));
        assert!(!tracker.observe(&s));
        s.daemon_instance = Some("two".into());
        s.completion_event = None;
        assert!(!tracker.observe(&s));
        s.completion_event = Some(Completion {
            sequence: 1,
            session_id: Some(3),
        });
        assert!(tracker.observe(&s));
    }
    #[test]
    fn automatic_pause_cannot_resume_manual_or_replaced_session() {
        let mut s = Snapshot {
            connected: true,
            state: "running".into(),
            session_id: Some(3),
            daemon_instance: Some("one".into()),
            ..Snapshot::default()
        };
        let pause = AutomaticPause::from_running(&s, "idle").unwrap();
        s.state = "paused".into();
        s.pause_source = Some("idle".into());
        assert!(pause.matches(&s));
        s.pause_source = Some("manual".into());
        assert!(!pause.matches(&s));
        s.pause_source = Some("idle".into());
        s.session_id = Some(4);
        assert!(!pause.matches(&s));
    }
    #[test]
    fn completion_description_never_uses_the_next_sessions_name() {
        let previous = Snapshot {
            session_id: Some(1),
            task_name: "First task".into(),
            ..Snapshot::default()
        };
        let mut next = Snapshot {
            session_id: Some(2),
            task_name: "Next task".into(),
            completion_event: Some(Completion {
                sequence: 1,
                session_id: Some(1),
            }),
            ..Snapshot::default()
        };
        assert_eq!(next.completion_description(&previous), "First task");
        next.completion_event.as_mut().unwrap().session_id = Some(3);
        assert_eq!(
            next.completion_description(&previous),
            "Your focus session is complete."
        );
    }
}

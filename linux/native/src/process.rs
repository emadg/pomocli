//! Own an on-demand helper and its short-lived CLI children as a process group.
//! Python's timer daemon deliberately detaches into its own session and survives.
use anyhow::{Context, Result};
use std::{
    process::{Output, Stdio},
    time::Duration,
};
use tokio::{process::Command, sync::oneshot, task::JoinHandle};

pub struct ManagedChild {
    cancel: Option<oneshot::Sender<()>>,
    join: JoinHandle<()>,
}
fn signal_group(pid: u32, signal: i32) {
    // Only a PID obtained from our freshly spawned process_group(0) is used.
    // Negative pid addresses that owned group, never the desktop's process group.
    unsafe {
        libc::kill(-(pid as libc::pid_t), signal);
    }
}
impl ManagedChild {
    pub fn spawn(mut command: Command, done: impl FnOnce(Result<Output>) + Send + 'static) -> Self {
        let (cancel, cancelled) = oneshot::channel();
        let join = tokio::spawn(async move {
            command
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .process_group(0)
                .kill_on_drop(true);
            let result = async {
                let child = command
                    .spawn()
                    .context("Cannot start desktop dialog helper")?;
                let pid = child.id().context("Dialog helper has no process ID")?;
                let output = child.wait_with_output();
                tokio::pin!(output);
                let result = tokio::select! {
                    result = &mut output => result,
                    _ = cancelled => {
                        signal_group(pid, libc::SIGTERM);
                        match tokio::time::timeout(Duration::from_secs(1), &mut output).await {
                            Ok(result) => result,
                            Err(_) => { signal_group(pid, libc::SIGKILL); output.await }
                        }
                    }
                };
                // A closed GTK window can leave a still-running prefill child.
                // No one-shot CLI process is allowed to outlive its helper.
                signal_group(pid, libc::SIGKILL);
                result.context("Cannot wait for desktop dialog helper")
            }
            .await;
            done(result);
        });
        Self {
            cancel: Some(cancel),
            join,
        }
    }
    pub async fn stop(mut self) {
        if let Some(cancel) = self.cancel.take() {
            let _ = cancel.send(());
        }
        let _ = (&mut self.join).await;
    }
}
impl Drop for ManagedChild {
    fn drop(&mut self) {
        // Cancellation remains best effort during runtime teardown. The normal
        // companion quit path always calls stop() and waits before exiting.
        if let Some(cancel) = self.cancel.take() {
            let _ = cancel.send(());
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn cancelling_helper_terminates_its_cli_child() {
        let path = std::env::temp_dir().join(format!("pomo-child-cleanup-{}", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let mut command = Command::new("/bin/sh");
        command
            .arg("-c")
            .arg("sleep 60 & echo $! > \"$1\"; wait")
            .arg("pomo-test")
            .arg(&path);
        let job = ManagedChild::spawn(command, |_| {});
        let child_pid = tokio::time::timeout(Duration::from_secs(2), async {
            loop {
                if let Ok(text) = std::fs::read_to_string(&path) {
                    if let Ok(pid) = text.trim().parse::<u32>() {
                        break pid;
                    }
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        job.stop().await;
        // An orphan can briefly remain a zombie while init reaps it; it must
        // never remain a live child that can perform work after companion quit.
        tokio::time::timeout(Duration::from_secs(2), async {
            loop {
                let status = std::fs::read_to_string(format!("/proc/{child_pid}/stat"));
                if status
                    .as_ref()
                    .map_or(true, |text| text.split_whitespace().nth(2) == Some("Z"))
                {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        let _ = std::fs::remove_file(path);
    }
}

/// Stop a one-shot CLI and descendants that remain in its process group. A
/// deliberately detached Python daemon is excluded because it owns a new group.
pub fn terminate_cli(pid: u32) {
    fn descendants(pid: u32, group: libc::pid_t, found: &mut Vec<u32>) {
        if let Ok(children) = std::fs::read_to_string(format!("/proc/{pid}/task/{pid}/children")) {
            for child in children
                .split_whitespace()
                .filter_map(|value| value.parse::<u32>().ok())
            {
                if unsafe { libc::getpgid(child as libc::pid_t) } == group {
                    descendants(child, group, found);
                    found.push(child);
                }
            }
        }
    }
    let group = unsafe { libc::getpgid(pid as libc::pid_t) };
    if group < 0 {
        return;
    }
    let mut children = Vec::new();
    descendants(pid, group, &mut children);
    for child in children {
        unsafe {
            libc::kill(child as libc::pid_t, libc::SIGKILL);
        }
    }
    unsafe {
        libc::kill(pid as libc::pid_t, libc::SIGKILL);
    }
}

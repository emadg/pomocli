use anyhow::{bail, Context, Result};
use serde::Deserialize;
use serde_json::{json, Value};
use std::{path::Path, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::UnixStream,
};

const MAX_RESPONSE: usize = 64 * 1024;
#[derive(Debug, Deserialize)]
pub struct Response {
    pub status: String,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub data: Value,
}
impl Response {
    pub fn ensure_ok(self) -> Result<Self> {
        if self.status != "ok" {
            bail!(
                "{}",
                self.message.as_deref().unwrap_or("Daemon rejected command")
            );
        }
        Ok(self)
    }
}
pub async fn request(path: &Path, command: &str, args: Value) -> Result<Response> {
    tokio::time::timeout(Duration::from_secs(2), async {
        let mut stream = UnixStream::connect(path)
            .await
            .context("Timer daemon is unavailable")?;
        stream
            .write_all(&serde_json::to_vec(
                &json!({"command":command,"args":args}),
            )?)
            .await?;
        // The server closes each command socket after replying. read_to_end handles
        // fragmented UTF-8 and JSON without assuming a single recv is a message.
        let mut response = Vec::new();
        (&mut stream)
            .take((MAX_RESPONSE + 1) as u64)
            .read_to_end(&mut response)
            .await?;
        if response.len() > MAX_RESPONSE {
            bail!("Daemon response exceeds 64 KiB");
        }
        let parsed: Response =
            serde_json::from_slice(&response).context("Invalid daemon response")?;
        parsed.ensure_ok()
    })
    .await
    .context("Timer daemon timed out")?
}
#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::UnixListener;
    #[tokio::test]
    async fn fragmented_json_and_errors() {
        let path = std::env::temp_dir().join(format!("pomo-wire-{}", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let server = UnixListener::bind(&path).unwrap();
        let task = tokio::spawn(async move {
            let (mut connection, _) = server.accept().await.unwrap();
            let mut buffer = [0; 1024];
            connection.read(&mut buffer).await.unwrap();
            connection.write_all(b"{\"status\":\"ok\",").await.unwrap();
            tokio::task::yield_now().await;
            connection
                .write_all(b"\"data\":{\"task_name\":\"caf\xc3\xa9\"}}")
                .await
                .unwrap();
        });
        assert_eq!(
            request(&path, "status", json!({})).await.unwrap().data["task_name"],
            "café"
        );
        task.await.unwrap();
        std::fs::remove_file(&path).unwrap();
        let rejected: Response =
            serde_json::from_value(json!({"status":"error","message":"stale"})).unwrap();
        assert!(rejected
            .ensure_ok()
            .unwrap_err()
            .to_string()
            .contains("stale"));
    }
    #[tokio::test]
    async fn rejects_malformed_and_oversized_messages() {
        for (index, payload) in [b"not-json".to_vec(), vec![b'x'; MAX_RESPONSE + 1]]
            .into_iter()
            .enumerate()
        {
            let path =
                std::env::temp_dir().join(format!("pomo-wire-bad-{}-{index}", std::process::id()));
            let _ = std::fs::remove_file(&path);
            let server = UnixListener::bind(&path).unwrap();
            let task = tokio::spawn(async move {
                let (mut connection, _) = server.accept().await.unwrap();
                let mut buffer = [0; 1024];
                connection.read(&mut buffer).await.unwrap();
                let _ = connection.write_all(&payload).await;
            });
            assert!(request(&path, "status", json!({})).await.is_err());
            task.await.unwrap();
            std::fs::remove_file(&path).unwrap();
        }
    }
}

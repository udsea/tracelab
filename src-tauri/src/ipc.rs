//! One stdout reader routes concurrent replies. Request expiry never kills the process.
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::oneshot,
};

#[derive(Default)]
struct Router {
    closed: bool,
    waiters: HashMap<u64, oneshot::Sender<Value>>,
}
type Pending = Arc<Mutex<Router>>;

pub struct Sidecar {
    pub child: Child,
    input: ChildStdin,
    pending: Pending,
}

pub struct Response {
    id: u64,
    pending: Pending,
    receiver: oneshot::Receiver<Value>,
}

impl Drop for Response {
    fn drop(&mut self) {
        // Covers timeout, completed replies, write failure and cancelled callers.
        self.pending
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .waiters
            .remove(&self.id);
    }
}

impl Response {
    pub async fn wait(mut self, timeout: Duration) -> Result<Value, String> {
        match tokio::time::timeout(timeout, &mut self.receiver).await {
            Ok(Ok(reply)) if !reply["error"].is_null() => Err(reply["error"]["message"]
                .as_str().unwrap_or("Backend request failed").into()),
            Ok(Ok(reply)) => Ok(reply["result"].clone()),
            Ok(Err(_)) => Err("Backend closed the IPC channel".into()),
            Err(_) => Err("Backend request timed out. The backend is still running; check Activity before retrying a job-starting action.".into()),
        }
    }
}

fn spawn_reader(output: ChildStdout, pending: Pending) {
    tokio::spawn(async move {
        let mut lines = BufReader::new(output).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            let Ok(reply) = serde_json::from_str::<Value>(&line) else {
                eprintln!("Invalid backend protocol message");
                continue;
            };
            let waiter = reply["id"].as_u64().and_then(|id| {
                pending
                    .lock()
                    .unwrap_or_else(|e| e.into_inner())
                    .waiters
                    .remove(&id)
            });
            // Late replies have no waiter; they cannot become another request's answer.
            if let Some(tx) = waiter {
                let _ = tx.send(reply);
            }
        }
        let mut router = pending.lock().unwrap_or_else(|e| e.into_inner());
        router.closed = true;
        router.waiters.clear();
    });
}

impl Sidecar {
    pub fn spawn(command: &mut Command) -> Result<Self, String> {
        let mut child = command
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::inherit())
            .kill_on_drop(true)
            .spawn()
            .map_err(|e| format!("Could not start the Python backend: {e}"))?;
        let input = child.stdin.take().ok_or("Missing backend stdin")?;
        let output = child.stdout.take().ok_or("Missing backend stdout")?;
        let pending = Arc::new(Mutex::new(Router::default()));
        spawn_reader(output, pending.clone());
        Ok(Self {
            child,
            input,
            pending,
        })
    }

    pub fn closed(&self) -> bool {
        self.pending
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .closed
    }

    pub async fn send(&mut self, id: u64, method: &str, params: Value) -> Result<Response, String> {
        let (tx, receiver) = oneshot::channel();
        {
            let mut router = self.pending.lock().unwrap_or_else(|e| e.into_inner());
            if router.closed {
                return Err("Backend closed the IPC channel".into());
            }
            router.waiters.insert(id, tx);
        }
        let response = Response {
            id,
            pending: self.pending.clone(),
            receiver,
        };
        let request = json!({ "id": id, "method": method, "params": params }).to_string() + "\n";
        self.input
            .write_all(request.as_bytes())
            .await
            .map_err(|e| e.to_string())?;
        self.input.flush().await.map_err(|e| e.to_string())?;
        Ok(response)
    }

    pub async fn stop(self) {
        let Self {
            mut child,
            input,
            pending,
        } = self;
        {
            let mut router = pending.lock().unwrap_or_else(|e| e.into_inner());
            router.closed = true;
            router.waiters.clear();
        }
        drop(input);
        if tokio::time::timeout(Duration::from_secs(3), child.wait())
            .await
            .is_err()
        {
            let _ = child.kill().await;
        }
    }
}

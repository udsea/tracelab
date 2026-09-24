use super::*;
use serde_json::json;
use std::sync::Arc;

fn fake() -> Sidecar {
    let mut command = Command::new("python3");
    command
        .arg("-u")
        .arg(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../tests/fixtures/ipc_sidecar.py"));
    Sidecar::spawn(&mut command).unwrap()
}
fn backend() -> Arc<Backend> {
    Arc::new(Backend {
        process: Mutex::new(Some(fake())),
        next_id: AtomicU64::new(0),
        data_dir: PathBuf::new(),
        resource_dir: PathBuf::new(),
    })
}
fn run(future: impl std::future::Future<Output = ()>) {
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap()
        .block_on(future);
}
const DEADLINE: Duration = Duration::from_secs(2);

#[test]
fn health_returns_before_slow_request() {
    run(async {
        let b = backend();
        let other = b.clone();
        let slow =
            tokio::spawn(
                async move { other.call("sleep", json!({"seconds": 1.2}), DEADLINE).await },
            );
        tokio::time::sleep(Duration::from_millis(30)).await;
        let health = b
            .call("health", json!({"tag": "fast"}), Duration::from_millis(700))
            .await
            .unwrap();
        assert_eq!(health["method"], "health");
        assert!(
            !slow.is_finished(),
            "a health request waited behind the slow request"
        );
        assert_eq!(slow.await.unwrap().unwrap()["method"], "sleep");
        b.stop().await;
    });
}

#[test]
fn timeout_discards_late_reply_and_preserves_pid_and_jobs() {
    run(async {
        let b = backend();
        let before = b.call("health", json!({}), DEADLINE).await.unwrap();
        let other = b.clone();
        let job = tokio::spawn(async move {
            other
                .call("sleep", json!({"seconds": 0.35, "tag": "job"}), DEADLINE)
                .await
        });
        let error = b
            .call("sleep", json!({"seconds": 0.15}), Duration::from_millis(20))
            .await
            .unwrap_err();
        assert!(error.contains("still running"));
        let fast = b
            .call("health", json!({"tag": "after timeout"}), DEADLINE)
            .await
            .unwrap();
        assert_eq!(fast["pid"], before["pid"]);
        let completed = job.await.unwrap().unwrap();
        assert_eq!(completed["params"]["tag"], "job");
        let after = b
            .call("health", json!({"tag": "after late reply"}), DEADLINE)
            .await
            .unwrap();
        assert_eq!(after["pid"], before["pid"]);
        assert_eq!(after["params"]["tag"], "after late reply");
        assert!(after["id"].as_u64().unwrap() > fast["id"].as_u64().unwrap());
        b.stop().await;
    });
}

#[test]
fn crash_fails_all_pending_calls_promptly_and_ids_survive_restart() {
    run(async {
        let b = backend();
        let before = b.call("health", json!({}), DEADLINE).await.unwrap();
        let mut pending = Vec::new();
        for _ in 0..3 {
            let other = b.clone();
            pending.push(tokio::spawn(async move {
                other
                    .call("sleep", json!({"seconds": 5}), Duration::from_secs(120))
                    .await
            }));
        }
        tokio::time::sleep(Duration::from_millis(30)).await;
        assert!(b.call("crash", json!({}), DEADLINE).await.is_err());
        for task in pending {
            assert!(tokio::time::timeout(Duration::from_secs(1), task)
                .await
                .unwrap()
                .unwrap()
                .unwrap_err()
                .contains("closed"));
        }
        *b.process.lock().await = Some(fake());
        let after = b.call("health", json!({}), DEADLINE).await.unwrap();
        assert_ne!(before["pid"], after["pid"]);
        assert!(after["id"].as_u64().unwrap() > before["id"].as_u64().unwrap());
        b.stop().await;
    });
}

#[test]
fn cancelled_waiter_and_invalid_line_do_not_poison_next_reply() {
    run(async {
        let b = backend();
        let other = b.clone();
        let pending =
            tokio::spawn(
                async move { other.call("sleep", json!({"seconds": 0.1}), DEADLINE).await },
            );
        tokio::time::sleep(Duration::from_millis(30)).await;
        pending.abort();
        let _ = pending.await;
        assert_eq!(
            b.call("malformed", json!({}), DEADLINE).await.unwrap()["method"],
            "malformed"
        );
        tokio::time::sleep(Duration::from_millis(150)).await;
        assert_eq!(
            b.call("health", json!({}), DEADLINE).await.unwrap()["method"],
            "health"
        );
        b.stop().await;
    });
}

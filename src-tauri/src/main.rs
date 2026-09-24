#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod ipc;
use ipc::Sidecar;
use serde_json::Value;
use std::{
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::Duration,
};
use tauri::{Manager, State};
use tokio::{process::Command, sync::Mutex};

struct Backend {
    process: Mutex<Option<Sidecar>>,
    next_id: AtomicU64,
    data_dir: PathBuf,
    resource_dir: PathBuf,
}

impl Backend {
    async fn stop(&self) {
        let process = self.process.lock().await.take();
        if let Some(process) = process {
            process.stop().await;
        }
    }
    async fn call(&self, method: &str, params: Value, timeout: Duration) -> Result<Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed) + 1;
        let response = {
            let mut lock = self.process.lock().await;
            if lock.is_none() {
                *lock = Some(self.spawn()?);
            }
            let process = lock.as_mut().unwrap();
            if process.closed()
                || process
                    .child
                    .try_wait()
                    .map_err(|e| e.to_string())?
                    .is_some()
            {
                *lock = None;
                return Err("Python backend stopped. Retry to restart it; interrupted jobs will be marked failed.".into());
            }
            process.send(id, method, params).await?
        }; // Only writing is serialized. Waiting for the reply never holds this lock.
        response.wait(timeout).await
    }
    fn spawn(&self) -> Result<Sidecar, String> {
        let mut command;
        if cfg!(debug_assertions) {
            let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend");
            let python = root.join(if cfg!(windows) {
                ".venv/Scripts/python.exe"
            } else {
                ".venv/bin/python"
            });
            command = Command::new(python);
            command.arg("-m").arg("tracelab").current_dir(root);
        } else {
            let binary = self.resource_dir.join("backend").join(if cfg!(windows) {
                "tracelab-backend.exe"
            } else {
                "tracelab-backend"
            });
            command = Command::new(binary);
        }
        command
            .arg("--stdio")
            .arg("--data-dir")
            .arg(&self.data_dir)
            .env("PYTHONUNBUFFERED", "1");
        Sidecar::spawn(&mut command)
    }
}

#[tauri::command]
async fn rpc(backend: State<'_, Backend>, method: String, params: Value) -> Result<Value, String> {
    backend
        .call(&method, params, Duration::from_secs(120))
        .await
}

#[cfg(all(test, unix))]
mod ipc_tests;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let data_dir = app.path().app_local_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;
            app.manage(Backend {
                process: Mutex::new(None),
                next_id: AtomicU64::new(0),
                data_dir,
                resource_dir: app.path().resource_dir()?,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![rpc])
        .build(tauri::generate_context!())
        .expect("Unable to initialize TraceLab")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let backend = app.state::<Backend>();
                tauri::async_runtime::block_on(backend.stop());
            }
        });
}

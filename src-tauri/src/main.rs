#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{path::PathBuf, time::Duration};
use tauri::{Manager, State};
use tokio::{io::{AsyncBufReadExt, AsyncWriteExt, BufReader}, process::{Child, ChildStdin, ChildStdout, Command}, sync::Mutex};

struct Sidecar { child: Child, input: ChildStdin, output: BufReader<ChildStdout>, serial: u64 }
struct Backend { process: Mutex<Option<Sidecar>>, data_dir: PathBuf, resource_dir: PathBuf }

impl Backend {
    async fn stop(&self) {
        if let Some(process) = self.process.lock().await.take() {
            let Sidecar { mut child, input, output, .. } = process;
            drop(input);
            drop(output);
            if tokio::time::timeout(Duration::from_secs(3), child.wait()).await.is_err() {
                let _ = child.kill().await;
            }
        }
    }
    fn spawn(&self) -> Result<Sidecar, String> {
        let mut command;
        if cfg!(debug_assertions) {
            let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend");
            let python = root.join(if cfg!(windows) { ".venv/Scripts/python.exe" } else { ".venv/bin/python" });
            command = Command::new(python);
            command.arg("-m").arg("tracelab").current_dir(root);
        } else {
            let binary = self.resource_dir.join("backend").join(if cfg!(windows) { "tracelab-backend.exe" } else { "tracelab-backend" });
            command = Command::new(binary);
        }
        let mut child = command.arg("--stdio").arg("--data-dir").arg(&self.data_dir)
            .env("PYTHONUNBUFFERED", "1")
            .stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::inherit()).kill_on_drop(true)
            .spawn().map_err(|e| format!("Could not start the Python backend: {e}. Run uv sync --project backend for development, or rebuild the packaged sidecar."))?;
        let input = child.stdin.take().ok_or("Missing backend stdin")?;
        let output = BufReader::new(child.stdout.take().ok_or("Missing backend stdout")?);
        Ok(Sidecar { child, input, output, serial: 0 })
    }
}

#[tauri::command]
async fn rpc(backend: State<'_, Backend>, method: String, params: Value) -> Result<Value, String> {
    let mut lock = backend.process.lock().await;
    if lock.is_none() { *lock = Some(backend.spawn()?); }
    let process = lock.as_mut().unwrap();
    if process.child.try_wait().map_err(|e| e.to_string())?.is_some() {
        *lock = None;
        return Err("Python backend stopped. Retry to restart it; interrupted jobs will be marked failed.".into());
    }
    process.serial += 1;
    let id = process.serial;
    let request = json!({ "id": id, "method": method, "params": params }).to_string() + "\n";
    let result = tokio::time::timeout(Duration::from_secs(120), async {
        process.input.write_all(request.as_bytes()).await.map_err(|e| e.to_string())?;
        process.input.flush().await.map_err(|e| e.to_string())?;
        let mut line = String::new();
        if process.output.read_line(&mut line).await.map_err(|e| e.to_string())? == 0 { return Err("Backend closed the IPC channel".to_string()); }
        let reply: Value = serde_json::from_str(&line).map_err(|e| format!("Invalid backend response: {e}"))?;
        if reply["id"] != id { return Err("Backend response ID mismatch".into()); }
        Ok(reply)
    }).await;
    match result {
        Ok(Ok(reply)) => {
            if !reply["error"].is_null() { Err(reply["error"]["message"].as_str().unwrap_or("Backend request failed").into()) }
            else { Ok(reply["result"].clone()) }
        }
        other => {
            // A timed out read must not be consumed as the next request's response.
            *lock = None;
            match other { Ok(Err(e)) => Err(e), _ => Err("Backend request timed out; the sidecar was stopped to preserve IPC consistency.".into()) }
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init()).plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let data_dir = app.path().app_local_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;
            app.manage(Backend { process: Mutex::new(None), data_dir, resource_dir: app.path().resource_dir()? });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![rpc])
        .build(tauri::generate_context!()).expect("Unable to initialize TraceLab")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let backend = app.state::<Backend>();
                tauri::async_runtime::block_on(backend.stop());
            }
        });
}

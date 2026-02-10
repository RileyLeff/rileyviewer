use std::fs;
use std::io::{Read, Write};
use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use base64::Engine;
use clap::{Parser, Subcommand};
use rv_config::Config;
use rv_server::{start_server_with, ServerConfig};
use serde::{Deserialize, Serialize};

#[derive(Parser)]
#[command(name = "rileyviewer", about = "RileyViewer - Plot viewer for Python")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Start the viewer server
    Serve {
        /// Host to bind (overrides config file)
        #[arg(long)]
        host: Option<String>,
        /// Port to bind (overrides config file)
        #[arg(long)]
        port: Option<u16>,
        /// Authentication token (auto-generated if not specified)
        #[arg(long)]
        token: Option<String>,
        /// Path to web dist directory (for development)
        #[arg(long)]
        dist_dir: Option<String>,
        /// Open browser automatically (overrides config file)
        #[arg(long)]
        open_browser: Option<bool>,
        /// Maximum plots to keep in history (overrides config file)
        #[arg(long)]
        history_limit: Option<usize>,
    },
    /// Check if server is running
    Status,
    /// Stop the running server
    Stop,
    /// Open browser for running server
    Open,
    /// Send a file or stdin to the viewer
    Send {
        /// File to send (reads stdin if omitted)
        file: Option<PathBuf>,
        /// Content type override: png, svg, plotly, vega, html
        #[arg(long, value_name = "TYPE")]
        r#type: Option<String>,
    },
}

#[derive(Serialize, Deserialize)]
struct ServerState {
    pid: u32,
    addr: String,
    token: Option<String>,
}

fn state_dir() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("rileyviewer")
}

fn state_file() -> PathBuf {
    state_dir().join("server.json")
}

fn read_state() -> Option<ServerState> {
    let path = state_file();
    let mut file = fs::File::open(&path).ok()?;
    let mut contents = String::new();
    file.read_to_string(&mut contents).ok()?;
    serde_json::from_str(&contents).ok()
}

fn write_state(state: &ServerState) -> Result<()> {
    let dir = state_dir();
    fs::create_dir_all(&dir).context("failed to create state directory")?;
    let path = state_file();
    let tmp_path = dir.join("server.json.tmp");
    let mut file = fs::File::create(&tmp_path).context("failed to create temp state file")?;
    let json = serde_json::to_string_pretty(state)?;
    file.write_all(json.as_bytes())?;
    file.sync_all().context("failed to flush state file to disk")?;
    drop(file);
    fs::rename(&tmp_path, &path).context("failed to atomically move state file")?;
    Ok(())
}

fn remove_state() {
    let _ = fs::remove_file(state_file());
}

fn check_server_running(addr: &str) -> bool {
    let url = format!("http://{}/health", addr);
    ureq::get(&url)
        .timeout(std::time::Duration::from_millis(500))
        .call()
        .is_ok()
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let config = Config::load();

    match cli.command {
        Command::Serve { host, port, token, dist_dir, open_browser, history_limit } => {
            // CLI flags override config file values
            let host = host.unwrap_or(config.server.host);
            let port = port.unwrap_or(config.server.port);
            let open_browser = open_browser.unwrap_or(config.server.open_browser);
            let history_limit = history_limit.unwrap_or(config.server.history_limit);
            serve(host, port, token, dist_dir, open_browser, history_limit).await?
        }
        Command::Status => status()?,
        Command::Stop => stop()?,
        Command::Open => open()?,
        Command::Send { file, r#type } => send(file, r#type)?,
    }
    Ok(())
}

fn generate_token() -> String {
    uuid::Uuid::new_v4().simple().to_string()
}

async fn serve(host: String, port: u16, token: Option<String>, dist_dir: Option<String>, open_browser: bool, history_limit: usize) -> Result<()> {
    // Check if already running
    if let Some(state) = read_state() {
        if check_server_running(&state.addr) {
            println!("Server already running at http://{}", state.addr);
            return Ok(());
        }
        // Stale state file, remove it
        remove_state();
    }

    // Generate token upfront if not provided
    let token = token.or_else(|| Some(generate_token()));

    let handle = match start_server_with(ServerConfig {
        host: host.clone(),
        port,
        token: token.clone(),
        dist_dir,
        history_limit,
    })
    .await
    {
        Ok(h) => h,
        Err(e) => {
            return Err(e);
        }
    };

    let addr: SocketAddr = handle.addr();

    // Write state file AFTER server binds successfully, using actual bound address
    write_state(&ServerState {
        pid: std::process::id(),
        addr: addr.to_string(),
        token: token.clone(),
    })?;

    println!("RileyViewer server started");
    println!("  Address: http://{}", addr);
    let url = if let Some(ref t) = token {
        println!("  Token: {}", t);
        let url = format!("http://{}/?token={}", addr, t);
        println!("  URL: {}", url);
        url
    } else {
        format!("http://{}/", addr)
    };

    if open_browser {
        let url_clone = url.clone();
        std::thread::spawn(move || {
            // Small delay to ensure server is fully ready
            std::thread::sleep(std::time::Duration::from_millis(100));
            if let Err(e) = webbrowser::open(&url_clone) {
                eprintln!("Failed to open browser: {}", e);
            }
        });
    }

    println!();
    println!("Press Ctrl+C to stop.");

    tokio::signal::ctrl_c().await?;
    println!("\nShutting down...");
    handle.shutdown().await?;
    remove_state();
    Ok(())
}

fn status() -> Result<()> {
    match read_state() {
        Some(state) => {
            if check_server_running(&state.addr) {
                println!("Server running");
                println!("  PID: {}", state.pid);
                println!("  Address: http://{}", state.addr);
                if let Some(ref t) = state.token {
                    println!("  Token: {}", t);
                    println!("  URL: http://{}/?token={}", state.addr, t);
                }
            } else {
                println!("Server not running (stale state file)");
                remove_state();
            }
        }
        None => {
            println!("Server not running");
        }
    }
    Ok(())
}

fn stop() -> Result<()> {
    match read_state() {
        Some(state) => {
            if check_server_running(&state.addr) {
                let url = format!("http://{}/api/shutdown", state.addr);
                let body = if let Some(ref token) = state.token {
                    format!(r#"{{"token":"{}"}}"#, token)
                } else {
                    "{}".to_string()
                };

                match ureq::post(&url)
                    .set("Content-Type", "application/json")
                    .send_string(&body)
                {
                    Ok(_) => {
                        println!("Shutdown signal sent");
                        // Wait for server to actually stop
                        for _ in 0..50 {
                            std::thread::sleep(std::time::Duration::from_millis(100));
                            if !check_server_running(&state.addr) {
                                remove_state();
                                println!("Server stopped");
                                return Ok(());
                            }
                        }
                        println!("Server may still be shutting down");
                    }
                    Err(e) => {
                        println!("Failed to send shutdown request: {}", e);
                    }
                }
            } else {
                println!("Server not running");
                remove_state();
            }
        }
        None => {
            println!("No server state found");
        }
    }
    Ok(())
}

fn open() -> Result<()> {
    match read_state() {
        Some(state) => {
            if check_server_running(&state.addr) {
                let url = if let Some(ref t) = state.token {
                    format!("http://{}/?token={}", state.addr, t)
                } else {
                    format!("http://{}/", state.addr)
                };
                println!("Opening {}", url);
                if let Err(e) = webbrowser::open(&url) {
                    eprintln!("Failed to open browser: {}", e);
                }
            } else {
                println!("Server not running");
                remove_state();
            }
        }
        None => {
            println!("No server running. Start one with: rileyviewer serve");
        }
    }
    Ok(())
}

fn send(file: Option<PathBuf>, type_override: Option<String>) -> Result<()> {
    let state = read_state().context("No server running. Start one with: rileyviewer serve")?;
    if !check_server_running(&state.addr) {
        bail!("Server not running at {}. Start one with: rileyviewer serve", state.addr);
    }

    // Read input
    let (data, source_name) = match file {
        Some(ref path) => {
            let data = fs::read(path)
                .with_context(|| format!("failed to read {}", path.display()))?;
            (data, path.display().to_string())
        }
        None => {
            let mut data = Vec::new();
            std::io::stdin()
                .read_to_end(&mut data)
                .context("failed to read stdin")?;
            (data, "stdin".to_string())
        }
    };

    if data.is_empty() {
        bail!("No data to send");
    }

    // Detect content type
    let content_type = if let Some(ref t) = type_override {
        t.to_lowercase()
    } else if let Some(ref path) = file {
        detect_from_extension(path, &data)
    } else {
        detect_from_content(&data)
    };

    // Build content JSON
    let content_json = match content_type.as_str() {
        "png" => {
            let encoded = base64::engine::general_purpose::STANDARD.encode(&data);
            format!(r#"{{"type":"Png","data":"{}"}}"#, encoded)
        }
        "svg" => {
            let text = String::from_utf8(data)
                .context("SVG data is not valid UTF-8")?;
            let escaped = serde_json::to_string(&text)?;
            format!(r#"{{"type":"Svg","data":{}}}"#, escaped)
        }
        "plotly" => {
            let text = String::from_utf8(data)
                .context("Plotly JSON is not valid UTF-8")?;
            // Validate it's JSON
            serde_json::from_str::<serde_json::Value>(&text)
                .context("Plotly data is not valid JSON")?;
            let escaped = serde_json::to_string(&text)?;
            format!(r#"{{"type":"Plotly","data":{}}}"#, escaped)
        }
        "vega" => {
            let text = String::from_utf8(data)
                .context("Vega JSON is not valid UTF-8")?;
            serde_json::from_str::<serde_json::Value>(&text)
                .context("Vega data is not valid JSON")?;
            let escaped = serde_json::to_string(&text)?;
            format!(r#"{{"type":"Vega","data":{}}}"#, escaped)
        }
        "html" => {
            let text = String::from_utf8(data)
                .context("HTML data is not valid UTF-8")?;
            let escaped = serde_json::to_string(&text)?;
            format!(r#"{{"type":"Html","data":{}}}"#, escaped)
        }
        other => bail!("Unknown content type: '{}'. Use: png, svg, plotly, vega, html", other),
    };

    // Build full payload
    let payload = if let Some(ref token) = state.token {
        let token_escaped = serde_json::to_string(token)?;
        format!(r#"{{"token":{},"content":{}}}"#, token_escaped, content_json)
    } else {
        format!(r#"{{"content":{}}}"#, content_json)
    };

    let url = format!("http://{}/api/publish", state.addr);
    let resp = ureq::post(&url)
        .set("Content-Type", "application/json")
        .send_string(&payload)
        .context("failed to send to server")?;

    let resp_text = resp.into_string()
        .context("failed to read server response")?;
    let body: serde_json::Value = serde_json::from_str(&resp_text)
        .context("failed to parse server response")?;

    if let Some(id) = body.get("id").and_then(|v: &serde_json::Value| v.as_str()) {
        println!("Sent {} as {} (id: {})", source_name, content_type, id);
    } else {
        println!("Sent {} as {}", source_name, content_type);
    }

    Ok(())
}

fn detect_from_extension(path: &PathBuf, data: &[u8]) -> String {
    match path.extension().and_then(|e| e.to_str()).map(|e| e.to_lowercase()).as_deref() {
        Some("png") => "png",
        Some("svg") => "svg",
        Some("html" | "htm") => "html",
        Some("json") => return detect_json_type(data),
        _ => "png", // default for unknown extensions
    }.to_string()
}

fn detect_from_content(data: &[u8]) -> String {
    // PNG magic bytes
    if data.starts_with(&[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A]) {
        return "png".to_string();
    }

    // Try as UTF-8 text
    if let Ok(text) = std::str::from_utf8(data) {
        let trimmed = text.trim_start();
        if trimmed.starts_with("<svg") || (trimmed.starts_with("<?xml") && trimmed.contains("<svg")) {
            return "svg".to_string();
        }
        if trimmed.starts_with('<') {
            return "html".to_string();
        }
        if trimmed.starts_with('{') || trimmed.starts_with('[') {
            return detect_json_type(data);
        }
    }

    "png".to_string() // binary fallback
}

fn detect_json_type(data: &[u8]) -> String {
    if let Ok(text) = std::str::from_utf8(data) {
        if let Ok(val) = serde_json::from_str::<serde_json::Value>(text) {
            // Vega/Vega-Lite specs have $schema
            if let Some(schema) = val.get("$schema").and_then(|s| s.as_str()) {
                if schema.contains("vega") {
                    return "vega".to_string();
                }
            }
            // Plotly has data+layout pattern
            if val.get("data").is_some() && val.get("layout").is_some() {
                return "plotly".to_string();
            }
            // Vega specs typically have mark, encoding, or layer
            if val.get("mark").is_some()
                || val.get("encoding").is_some()
                || val.get("layer").is_some()
                || val.get("vconcat").is_some()
                || val.get("hconcat").is_some()
            {
                return "vega".to_string();
            }
        }
    }
    "vega".to_string() // default JSON → Vega
}

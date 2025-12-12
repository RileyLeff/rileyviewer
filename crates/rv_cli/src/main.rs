use std::fs;
use std::io::{Read, Write};
use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::{Context, Result};
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
    let mut file = fs::File::create(&path).context("failed to create state file")?;
    let json = serde_json::to_string_pretty(state)?;
    file.write_all(json.as_bytes())?;
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
    let addr_str = format!("{}:{}", host, port);

    // Write state file BEFORE starting server to eliminate race condition
    // By the time /health returns 200, clients can rely on this file existing
    write_state(&ServerState {
        pid: std::process::id(),
        addr: addr_str.clone(),
        token: token.clone(),
    })?;

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
            // Server failed to start, clean up state file
            remove_state();
            return Err(e);
        }
    };

    let addr: SocketAddr = handle.addr();

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
                // Send kill signal to the process
                #[cfg(unix)]
                {
                    use nix::sys::signal::{kill, Signal};
                    use nix::unistd::Pid;
                    let pid = Pid::from_raw(state.pid as i32);
                    if kill(pid, Signal::SIGTERM).is_ok() {
                        println!("Sent stop signal to server (PID {})", state.pid);
                        // Wait a moment and verify
                        std::thread::sleep(std::time::Duration::from_millis(500));
                        if !check_server_running(&state.addr) {
                            remove_state();
                            println!("Server stopped");
                        } else {
                            println!("Server still running, may need manual kill");
                        }
                    } else {
                        println!("Failed to send signal to PID {}", state.pid);
                    }
                }
                #[cfg(windows)]
                {
                    println!("Stop not implemented on Windows yet. Kill PID {} manually.", state.pid);
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

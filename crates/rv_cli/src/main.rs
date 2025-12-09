use std::net::SocketAddr;

use anyhow::Result;
use clap::{Parser, Subcommand};
use rv_server::start_server;

#[derive(Parser)]
#[command(name = "rv", about = "RileyViewer helper CLI")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Start a local viewer server (placeholder for future tunnel tooling)
    Serve {
        /// Host to bind (use 0.0.0.0 for remote/headless)
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
        /// Port to bind (use 0 for ephemeral)
        #[arg(long, default_value_t = 8080)]
        port: u16,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Serve { host, port } => serve(host, port).await?,
    }
    Ok(())
}

async fn serve(host: String, port: u16) -> Result<()> {
    let handle = start_server(&host, port).await?;
    let addr: SocketAddr = handle.addr();
    println!("Serving RileyViewer at http://{addr}");
    if let Some(token) = handle.token() {
        println!("Auth token: {token}");
        println!("Open: http://{addr}/?token={token}");
    }
    if std::env::var("DISPLAY").is_err() {
        let local_port = addr.port();
        println!(
            "Headless? Tunnel example: ssh -L {local_port}:localhost:{local_port} <user>@<host>"
        );
    }
    println!("Press Ctrl+C to stop.");
    tokio::signal::ctrl_c().await?;
    handle.shutdown().await?;
    Ok(())
}

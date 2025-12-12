use std::{
    net::SocketAddr,
    sync::{Arc, Mutex},
};

use anyhow::Context;
use axum::{
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    extract::{DefaultBodyLimit, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use rv_core::PlotMessage;
use tokio::{
    net::TcpListener,
    sync::{broadcast, oneshot, RwLock},
    task::JoinHandle,
};
use tower_http::services::{ServeDir, ServeFile};
#[cfg(feature = "embed-assets")]
use {
    axum::body::Body,
    axum::http::{header, Uri},
    rust_embed::RustEmbed,
    tower_http::services::ServeFile,
};
use tracing::{debug, warn};
use uuid::Uuid;

#[derive(Clone)]
struct PlotState {
    history: Arc<RwLock<Vec<PlotMessage>>>,
    tx: broadcast::Sender<PlotMessage>,
    history_limit: usize,
}

impl PlotState {
    fn new(history_limit: usize) -> Self {
        let (tx, _) = broadcast::channel(64);
        Self {
            history: Arc::new(RwLock::new(Vec::new())),
            tx,
            history_limit,
        }
    }

    async fn push(&self, msg: PlotMessage) {
        {
            let mut history = self.history.write().await;
            history.push(msg.clone());
            if history.len() > self.history_limit {
                let overflow = history.len() - self.history_limit;
                history.drain(0..overflow);
            }
        }
        // Log if broadcast fails (no receivers) - this is expected when no clients are connected
        if let Err(e) = self.tx.send(msg) {
            debug!("No WebSocket clients connected to receive plot: {}", e.0.id);
        }
    }
}

struct InnerHandle {
    state: PlotState,
    shutdown_tx: Mutex<Option<oneshot::Sender<()>>>,
    task: Mutex<Option<JoinHandle<anyhow::Result<()>>>>,
    addr: SocketAddr,
    token: Option<String>,
}

#[derive(Clone)]
pub struct ServerHandle {
    inner: Arc<InnerHandle>,
}

impl ServerHandle {
    pub fn addr(&self) -> SocketAddr {
        self.inner.addr
    }

    pub fn token(&self) -> Option<String> {
        self.inner.token.clone()
    }

    pub async fn publish(&self, msg: PlotMessage) {
        self.inner.state.push(msg).await;
    }

    pub async fn shutdown(&self) -> anyhow::Result<()> {
        // Use unwrap_or_else to handle poisoned mutex gracefully - if another thread
        // panicked while holding the lock, we still want to attempt shutdown
        if let Some(tx) = self
            .inner
            .shutdown_tx
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .take()
        {
            let _ = tx.send(());
        }
        if let Some(task) = self
            .inner
            .task
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .take()
        {
            task.await??;
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub host: String,
    pub port: u16,
    pub token: Option<String>,
    pub dist_dir: Option<String>,
    pub history_limit: usize,
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            host: rv_config::DEFAULT_HOST.to_string(),
            port: rv_config::DEFAULT_PORT,
            token: None,
            dist_dir: None,
            history_limit: rv_config::DEFAULT_HISTORY_LIMIT,
        }
    }
}

pub async fn start_server(host: &str, port: u16) -> anyhow::Result<ServerHandle> {
    start_server_with(ServerConfig {
        host: host.to_string(),
        port,
        ..Default::default()
    })
    .await
}

pub async fn start_server_with(config: ServerConfig) -> anyhow::Result<ServerHandle> {
    let token = config
        .token
        .clone()
        .or_else(|| Some(Uuid::new_v4().simple().to_string()));

    let state = PlotState::new(config.history_limit);
    let router = build_router(state.clone(), token.clone(), config.dist_dir.clone());
    let bind_addr: SocketAddr = format!("{}:{}", config.host, config.port)
        .parse()
        .with_context(|| format!("invalid host/port: {}:{}", config.host, config.port))?;
    let listener = TcpListener::bind(bind_addr)
        .await
        .with_context(|| format!("failed binding to {bind_addr}"))?;
    let addr = listener.local_addr().context("failed to get local address")?;

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let task = tokio::spawn(async move {
        axum::serve(listener, router)
            .with_graceful_shutdown(async move {
                let _ = shutdown_rx.await;
            })
            .await
            .context("server error")?;
        Ok(())
    });

    Ok(ServerHandle {
        inner: Arc::new(InnerHandle {
            state,
            shutdown_tx: Mutex::new(Some(shutdown_tx)),
            task: Mutex::new(Some(task)),
            addr,
            token,
        }),
    })
}

fn build_router(state: PlotState, token: Option<String>, dist_dir: Option<String>) -> Router {
    #[cfg(feature = "embed-assets")]
    let spa = embedded_assets_service();

    #[cfg(not(feature = "embed-assets"))]
    let spa = {
        let dist = dist_dir
            .map(std::path::PathBuf::from)
            .unwrap_or_else(default_dist_dir);
        let index_path = dist.join("index.html");
        let serve_dir = ServeDir::new(&dist).fallback(ServeFile::new(index_path));
        Router::new().nest_service("/", serve_dir)
    };
    Router::new()
        .route("/health", get(health))
        .route("/ws", get(ws_handler))
        .route("/api/publish", post(publish_handler))
        .layer(DefaultBodyLimit::max(50 * 1024 * 1024)) // 50MB for animations
        .with_state((state, token))
        .merge(spa)
}

async fn health() -> &'static str {
    "ok"
}

#[derive(Deserialize)]
struct WsQuery {
    token: Option<String>,
}

async fn ws_handler(
    State((state, token)): State<(PlotState, Option<String>)>,
    Query(query): Query<WsQuery>,
    ws: WebSocketUpgrade,
) -> Response {
    if !token_valid(&token, query.token.as_deref()) {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    ws.on_upgrade(move |socket| handle_socket(state, socket))
}

async fn handle_socket(state: PlotState, mut socket: WebSocket) {
    // send history first
    let history = state.history.read().await.clone();
    let history_count = history.len();
    if let Err(e) = send_history(history, &mut socket).await {
        warn!("Failed to send {} history items to new WebSocket client: {}", history_count, e);
        return;
    }
    debug!("Sent {} history items to new WebSocket client", history_count);

    let mut rx = state.tx.subscribe();
    while let Ok(msg) = rx.recv().await {
        match serde_json::to_string(&msg) {
            Ok(text) => {
                if let Err(e) = socket.send(Message::Text(text)).await {
                    debug!("WebSocket client disconnected: {}", e);
                    break;
                }
            }
            Err(e) => {
                warn!("Failed to serialize plot message {}: {}", msg.id, e);
            }
        }
    }
}

async fn send_history(
    history: Vec<PlotMessage>,
    socket: &mut WebSocket,
) -> Result<(), axum::Error> {
    for msg in history {
        match serde_json::to_string(&msg) {
            Ok(text) => socket.send(Message::Text(text)).await?,
            Err(e) => warn!("Failed to serialize history message {}: {}", msg.id, e),
        }
    }
    Ok(())
}

fn token_valid(expected: &Option<String>, provided: Option<&str>) -> bool {
    match (expected, provided) {
        (None, _) => true,
        (Some(_), None) => false,
        (Some(exp), Some(p)) => exp == p,
    }
}

#[derive(Deserialize)]
struct PublishRequest {
    token: Option<String>,
    content: rv_core::PlotContent,
}

#[derive(Serialize)]
struct PublishResponse {
    id: String,
}

async fn publish_handler(
    State((state, expected_token)): State<(PlotState, Option<String>)>,
    Json(req): Json<PublishRequest>,
) -> Response {
    if !token_valid(&expected_token, req.token.as_deref()) {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    let msg = PlotMessage::new(req.content);
    let id = msg.id.clone();
    state.push(msg).await;
    Json(PublishResponse { id }).into_response()
}

fn default_dist_dir() -> std::path::PathBuf {
    let manifest_dir = std::env!("CARGO_MANIFEST_DIR");
    std::path::Path::new(manifest_dir)
        .join("../../web/dist")
        .to_path_buf()
}

#[cfg(feature = "embed-assets")]
#[derive(RustEmbed)]
#[folder = "../../web/dist"]
struct EmbeddedAssets;

#[cfg(feature = "embed-assets")]
fn embedded_assets_service() -> Router {
    // Serve embedded files and fall back to index.html for SPA
    Router::new().route(
        "/*path",
        get(|uri: Uri| async move {
            let path = uri.path().trim_start_matches('/');
            let asset_path = if path.is_empty() { "index.html" } else { path };

            if let Some(file) = EmbeddedAssets::get(asset_path) {
                let body = Body::from(file.data.to_vec());
                let mime = mime_guess::from_path(asset_path).first_or_octet_stream();
                return Response::builder()
                    .header(header::CONTENT_TYPE, mime.as_ref())
                    .body(body)
                    .expect("valid response with content-type header");
            }

            // SPA fallback: if the path doesn't look like an asset, serve index.html
            if !asset_path.contains('.') {
                if let Some(index) = EmbeddedAssets::get("index.html") {
                    let body = Body::from(index.data.to_vec());
                    return Response::builder()
                        .header(header::CONTENT_TYPE, "text/html")
                        .body(body)
                        .expect("valid response with text/html content-type");
                }
            }

            Response::builder()
                .status(StatusCode::NOT_FOUND)
                .body(Body::from("404"))
                .expect("valid 404 response")
        }),
    )
}

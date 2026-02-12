use std::{
    net::SocketAddr,
    sync::{Arc, Mutex},
};

/// Shared shutdown trigger. The oneshot sender is taken once to initiate graceful shutdown.
type ShutdownTx = Arc<Mutex<Option<oneshot::Sender<()>>>>;

use anyhow::Context;
use axum::{
    body::Bytes,
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    extract::{DefaultBodyLimit, Path, Query, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    routing::{delete, get, patch, post},
    Json, Router,
};
use flate2::{read::GzDecoder, write::GzEncoder, Compression};
use serde::{Deserialize, Serialize};
use rv_core::{PlotMessage, Snapshot};
use tokio::{
    net::TcpListener,
    sync::{broadcast, oneshot, RwLock},
    task::JoinHandle,
};
#[cfg(not(feature = "embed-assets"))]
use tower_http::services::{ServeDir, ServeFile};
#[cfg(feature = "embed-assets")]
use {
    axum::body::Body,
    axum::http::Uri,
    rust_embed::RustEmbed,
};
use futures::{SinkExt, StreamExt};
use tracing::{debug, warn};
use uuid::Uuid;

#[derive(Clone)]
struct PlotState {
    history: Arc<RwLock<Vec<PlotMessage>>>,
    /// Pre-serialized JSON strings are broadcast so we serialize once for N clients.
    tx: broadcast::Sender<String>,
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
        let json = serde_json::to_string(&msg).unwrap_or_else(|e| {
            warn!("Failed to serialize plot message {}: {}", msg.id, e);
            return String::new();
        });
        {
            let mut history = self.history.write().await;
            history.push(msg);
            if history.len() > self.history_limit {
                let overflow = history.len() - self.history_limit;
                history.drain(0..overflow);
            }
        }
        if !json.is_empty() {
            if let Err(_) = self.tx.send(json) {
                debug!("No WebSocket clients connected to receive plot");
            }
        }
    }

    /// Update metadata fields on an existing plot and broadcast the change.
    /// Returns the updated PlotMessage, or None if not found.
    async fn update_metadata(
        &self,
        id: &str,
        title: Option<Option<String>>,
        notes: Option<Option<String>>,
        tags: Option<Vec<String>>,
    ) -> Option<PlotMessage> {
        let mut history = self.history.write().await;
        let plot = history.iter_mut().find(|p| p.id == id)?;

        if let Some(t) = title {
            plot.title = t;
        }
        if let Some(n) = notes {
            plot.notes = n;
        }
        if let Some(t) = tags {
            plot.tags = t;
        }

        let updated = plot.clone();

        // Broadcast a metadata update notification (not the full plot content)
        #[derive(Serialize)]
        struct MetadataUpdateBroadcast {
            kind: &'static str,
            id: String,
            title: Option<String>,
            notes: Option<String>,
            tags: Vec<String>,
        }
        let broadcast_msg = MetadataUpdateBroadcast {
            kind: "metadata_update",
            id: updated.id.clone(),
            title: updated.title.clone(),
            notes: updated.notes.clone(),
            tags: updated.tags.clone(),
        };
        if let Ok(json) = serde_json::to_string(&broadcast_msg) {
            let _ = self.tx.send(json);
        }

        Some(updated)
    }

    /// Remove a single plot by ID and broadcast the deletion.
    /// Returns true if the plot was found and removed.
    async fn remove(&self, id: &str) -> bool {
        let mut history = self.history.write().await;
        let len_before = history.len();
        history.retain(|p| p.id != id);
        let removed = history.len() < len_before;
        if removed {
            #[derive(Serialize)]
            struct DeleteBroadcast {
                kind: &'static str,
                id: String,
            }
            let msg = DeleteBroadcast { kind: "delete", id: id.to_string() };
            if let Ok(json) = serde_json::to_string(&msg) {
                let _ = self.tx.send(json);
            }
        }
        removed
    }

    /// Replace all history with the contents of a snapshot and broadcast changes.
    async fn load_snapshot(&self, plots: Vec<PlotMessage>) {
        self.clear().await;
        for plot in plots {
            self.push(plot).await;
        }
    }

    /// Clear all plots and broadcast the clear event.
    async fn clear(&self) {
        {
            let mut history = self.history.write().await;
            history.clear();
        }
        #[derive(Serialize)]
        struct ClearBroadcast {
            kind: &'static str,
        }
        let msg = ClearBroadcast { kind: "clear" };
        if let Ok(json) = serde_json::to_string(&msg) {
            let _ = self.tx.send(json);
        }
    }
}

struct InnerHandle {
    state: PlotState,
    shutdown_tx: ShutdownTx,
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

    pub async fn delete(&self, id: &str) -> bool {
        self.inner.state.remove(id).await
    }

    pub async fn clear(&self) {
        self.inner.state.clear().await;
    }

    pub async fn load_snapshot(&self, plots: Vec<PlotMessage>) {
        self.inner.state.load_snapshot(plots).await;
    }

    pub async fn shutdown(&self) -> anyhow::Result<()> {
        trigger_shutdown(&self.inner.shutdown_tx);
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
    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    let shutdown = Arc::new(Mutex::new(Some(shutdown_tx)));
    let router = build_router(state.clone(), token.clone(), shutdown.clone(), config.dist_dir.clone());
    let bind_str = format!("{}:{}", config.host, config.port);
    let listener = TcpListener::bind(&bind_str)
        .await
        .with_context(|| format!("failed binding to {bind_str}"))?;
    let addr = listener.local_addr().context("failed to get local address")?;

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
            shutdown_tx: shutdown,
            task: Mutex::new(Some(task)),
            addr,
            token,
        }),
    })
}

fn build_router(state: PlotState, token: Option<String>, shutdown: ShutdownTx, dist_dir: Option<String>) -> Router {
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
    // Snapshot routes get a larger body limit (100MB) for big sessions
    let snapshot_routes = Router::new()
        .route("/api/snapshot", get(snapshot_save_handler).post(snapshot_load_handler))
        .layer(DefaultBodyLimit::max(100 * 1024 * 1024));

    Router::new()
        .route("/health", get(health))
        .route("/ws", get(ws_handler))
        .route("/api/publish", post(publish_handler))
        .route("/api/plots/:id/metadata", patch(update_metadata_handler))
        .route("/api/plots", delete(clear_all_handler))
        .route("/api/plots/:id", delete(delete_plot_handler))
        .route("/api/shutdown", post(shutdown_handler))
        .layer(DefaultBodyLimit::max(10 * 1024 * 1024)) // 10MB
        .merge(snapshot_routes)
        .with_state((state, token, shutdown))
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
    State((state, token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Query(query): Query<WsQuery>,
    ws: WebSocketUpgrade,
) -> Response {
    if !token_valid(&token, query.token.as_deref()) {
        warn!("WebSocket connection rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    ws.on_upgrade(move |socket| handle_socket(state, socket))
}

async fn handle_socket(state: PlotState, socket: WebSocket) {
    // Subscribe BEFORE reading history to avoid missing plots published in between.
    // The client deduplicates by ID, so overlap between history and live messages is fine.
    let mut rx = state.tx.subscribe();

    let (mut sender, mut receiver) = socket.split();

    // Serialize history once and send to this client
    let history = state.history.read().await.clone();
    let history_count = history.len();
    for msg in history {
        match serde_json::to_string(&msg) {
            Ok(text) => {
                if let Err(e) = sender.send(Message::Text(text)).await {
                    warn!("Failed to send history to new WebSocket client: {}", e);
                    return;
                }
            }
            Err(e) => warn!("Failed to serialize history message {}: {}", msg.id, e),
        }
    }
    debug!("Sent {} history items to new WebSocket client", history_count);

    // Concurrently read from both the broadcast channel and the client socket.
    // Broadcast sends pre-serialized JSON strings so we forward directly.
    loop {
        tokio::select! {
            msg = rx.recv() => {
                match msg {
                    Ok(text) => {
                        if let Err(e) = sender.send(Message::Text(text)).await {
                            debug!("WebSocket client disconnected: {}", e);
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(n)) => {
                        warn!("WebSocket client lagged, skipped {} messages", n);
                    }
                    Err(broadcast::error::RecvError::Closed) => {
                        debug!("Broadcast channel closed");
                        break;
                    }
                }
            }
            ws_msg = receiver.next() => {
                match ws_msg {
                    Some(Ok(Message::Close(_))) | None => {
                        debug!("WebSocket client closed connection");
                        break;
                    }
                    Some(Ok(_)) => {} // ignore pings, pongs, text from client
                    Some(Err(e)) => {
                        debug!("WebSocket client error: {}", e);
                        break;
                    }
                }
            }
        }
    }
}

/// Take the oneshot sender and fire it to trigger graceful shutdown.
fn trigger_shutdown(shutdown: &ShutdownTx) {
    if let Some(tx) = shutdown
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .take()
    {
        let _ = tx.send(());
    }
}

#[derive(Deserialize)]
struct ShutdownRequest {
    token: Option<String>,
}

async fn shutdown_handler(
    State((_state, expected_token, shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Json(req): Json<ShutdownRequest>,
) -> Response {
    if !token_valid(&expected_token, req.token.as_deref()) {
        warn!("Shutdown request rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    debug!("Shutdown requested via API");
    trigger_shutdown(&shutdown);
    StatusCode::OK.into_response()
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
    #[serde(default)]
    title: Option<String>,
    #[serde(default)]
    notes: Option<String>,
    #[serde(default)]
    tags: Vec<String>,
}

#[derive(Serialize)]
struct PublishResponse {
    id: String,
}

async fn publish_handler(
    State((state, expected_token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Json(req): Json<PublishRequest>,
) -> Response {
    if !token_valid(&expected_token, req.token.as_deref()) {
        warn!("Publish request rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    let msg = PlotMessage::with_metadata(req.content, req.title, req.notes, req.tags);
    let id = msg.id.clone();
    state.push(msg).await;
    Json(PublishResponse { id }).into_response()
}

#[derive(Deserialize)]
struct MetadataUpdateRequest {
    token: Option<String>,
    #[serde(default)]
    title: Option<Option<String>>,
    #[serde(default)]
    notes: Option<Option<String>>,
    #[serde(default)]
    tags: Option<Vec<String>>,
}

#[derive(Serialize)]
struct MetadataUpdateResponse {
    id: String,
    title: Option<String>,
    notes: Option<String>,
    tags: Vec<String>,
}

async fn update_metadata_handler(
    State((state, expected_token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Path(plot_id): Path<String>,
    Json(req): Json<MetadataUpdateRequest>,
) -> Response {
    if !token_valid(&expected_token, req.token.as_deref()) {
        warn!("Metadata update rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    match state.update_metadata(&plot_id, req.title, req.notes, req.tags).await {
        Some(updated) => Json(MetadataUpdateResponse {
            id: updated.id,
            title: updated.title,
            notes: updated.notes,
            tags: updated.tags,
        })
        .into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

#[derive(Deserialize)]
struct DeletePlotRequest {
    token: Option<String>,
}

async fn delete_plot_handler(
    State((state, expected_token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Path(plot_id): Path<String>,
    Json(req): Json<DeletePlotRequest>,
) -> Response {
    if !token_valid(&expected_token, req.token.as_deref()) {
        warn!("Delete request rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    if state.remove(&plot_id).await {
        StatusCode::OK.into_response()
    } else {
        StatusCode::NOT_FOUND.into_response()
    }
}

#[derive(Deserialize)]
struct ClearAllRequest {
    token: Option<String>,
}

async fn clear_all_handler(
    State((state, expected_token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Json(req): Json<ClearAllRequest>,
) -> Response {
    if !token_valid(&expected_token, req.token.as_deref()) {
        warn!("Clear request rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    state.clear().await;
    StatusCode::OK.into_response()
}

async fn snapshot_save_handler(
    State((state, expected_token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Query(query): Query<WsQuery>,
) -> Response {
    if !token_valid(&expected_token, query.token.as_deref()) {
        warn!("Snapshot save rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }
    let history = state.history.read().await.clone();
    let snapshot = Snapshot::from_plots(history);

    let json = match serde_json::to_vec(&snapshot) {
        Ok(j) => j,
        Err(e) => {
            warn!("Failed to serialize snapshot: {}", e);
            return StatusCode::INTERNAL_SERVER_ERROR.into_response();
        }
    };

    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    if std::io::Write::write_all(&mut encoder, &json).is_err() {
        return StatusCode::INTERNAL_SERVER_ERROR.into_response();
    }
    let compressed = match encoder.finish() {
        Ok(c) => c,
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    };

    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "application/x-rileyviewer-snapshot")
        .header(
            header::CONTENT_DISPOSITION,
            "attachment; filename=\"session.rvw\"",
        )
        .body(axum::body::Body::from(compressed))
        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

async fn snapshot_load_handler(
    State((state, expected_token, _shutdown)): State<(PlotState, Option<String>, ShutdownTx)>,
    Query(query): Query<WsQuery>,
    body: Bytes,
) -> Response {
    if !token_valid(&expected_token, query.token.as_deref()) {
        warn!("Snapshot load rejected: invalid or missing token");
        return StatusCode::UNAUTHORIZED.into_response();
    }

    let mut decoder = GzDecoder::new(&body[..]);
    let mut json_bytes = Vec::new();
    if std::io::Read::read_to_end(&mut decoder, &mut json_bytes).is_err() {
        return (StatusCode::BAD_REQUEST, "Invalid gzip data").into_response();
    }

    let snapshot: Snapshot = match serde_json::from_slice(&json_bytes) {
        Ok(s) => s,
        Err(_) => return (StatusCode::BAD_REQUEST, "Invalid snapshot JSON").into_response(),
    };

    if snapshot.version > Snapshot::CURRENT_VERSION {
        return (
            StatusCode::BAD_REQUEST,
            "Snapshot version too new; update rileyviewer",
        )
            .into_response();
    }

    let count = snapshot.plots.len();
    state.load_snapshot(snapshot.plots).await;

    #[derive(Serialize)]
    struct LoadResponse {
        loaded: usize,
    }
    Json(LoadResponse { loaded: count }).into_response()
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
    async fn serve_embedded(uri: Uri) -> Response<Body> {
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
    }

    // Both "/" and "/*path" are needed — the wildcard doesn't match bare root
    Router::new()
        .route("/", get(serve_embedded))
        .route("/*path", get(serve_embedded))
}

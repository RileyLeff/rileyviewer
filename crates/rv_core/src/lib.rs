use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum PlotContent {
    Png(String),   // base64-encoded PNG
    Svg(String),   // raw SVG
    Plotly(String), // JSON payload
    Vega(String),  // JSON payload (Vega/Vega-Lite)
    Html(String),      // raw HTML fallback
    ArrowIpc(String),  // base64-encoded Arrow IPC streaming format
    Csv(String),       // raw CSV text
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlotMessage {
    pub id: String,
    /// Unix timestamp in milliseconds (safe for JavaScript Number)
    pub timestamp: u64,
    pub content: PlotContent,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub notes: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tags: Vec<String>,
}

impl PlotMessage {
    pub fn new(content: PlotContent) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            timestamp: (OffsetDateTime::now_utc().unix_timestamp_nanos() / 1_000_000) as u64,
            content,
            title: None,
            notes: None,
            tags: Vec::new(),
        }
    }

    pub fn with_metadata(
        content: PlotContent,
        title: Option<String>,
        notes: Option<String>,
        tags: Vec<String>,
    ) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            timestamp: (OffsetDateTime::now_utc().unix_timestamp_nanos() / 1_000_000) as u64,
            content,
            title,
            notes,
            tags,
        }
    }
}

/// A session snapshot containing all plots and metadata.
/// Serialized as JSON, stored as gzip-compressed `.rvw` files.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    /// Format version for forward compatibility.
    pub version: u32,
    /// Unix timestamp in milliseconds when the snapshot was created.
    pub created_at: u64,
    /// Number of plots (redundant with plots.len(), useful for quick inspection).
    pub plot_count: usize,
    /// All plots in chronological order.
    pub plots: Vec<PlotMessage>,
}

impl Snapshot {
    pub const CURRENT_VERSION: u32 = 1;

    pub fn from_plots(plots: Vec<PlotMessage>) -> Self {
        Self {
            version: Self::CURRENT_VERSION,
            created_at: (OffsetDateTime::now_utc().unix_timestamp_nanos() / 1_000_000) as u64,
            plot_count: plots.len(),
            plots,
        }
    }
}

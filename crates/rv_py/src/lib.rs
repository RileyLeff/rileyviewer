use base64::{engine::general_purpose, Engine as _};
use once_cell::sync::OnceCell;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use rv_core::{PlotContent, PlotMessage};
use rv_server::{start_server_with, ServerConfig, ServerHandle};
use tokio::runtime::Runtime;

static RUNTIME: OnceCell<Runtime> = OnceCell::new();

fn runtime() -> &'static Runtime {
    RUNTIME.get_or_init(|| Runtime::new().expect("failed to start tokio runtime"))
}

#[pyclass(name = "RustViewer")]
pub struct PyViewer {
    handle: ServerHandle,
}

#[pymethods]
impl PyViewer {
    #[new]
    #[pyo3(signature = (host=None, port=None, token=None))]
    fn new(host: Option<String>, port: Option<u16>, token: Option<String>) -> PyResult<Self> {
        let host = host.unwrap_or_else(|| "127.0.0.1".to_string());
        let port = port.unwrap_or(0);
        let handle = runtime()
            .block_on(start_server_with(ServerConfig {
                host,
                port,
                token,
                dist_dir: None,
            }))
            .map_err(to_py_err)?;

        Ok(Self { handle })
    }

    #[getter]
    fn addr(&self) -> String {
        self.handle.addr().to_string()
    }

    #[getter]
    fn token(&self) -> Option<String> {
        self.handle.token()
    }

    fn send_png(&self, data: &[u8]) -> PyResult<String> {
        let encoded = general_purpose::STANDARD.encode(data);
        self.enqueue(PlotContent::Png(encoded))
    }

    fn send_svg(&self, svg: &str) -> PyResult<String> {
        self.enqueue(PlotContent::Svg(svg.to_string()))
    }

    fn send_plotly_json(&self, json: &str) -> PyResult<String> {
        self.enqueue(PlotContent::Plotly(json.to_string()))
    }

    fn send_vega_json(&self, json: &str) -> PyResult<String> {
        self.enqueue(PlotContent::Vega(json.to_string()))
    }

    fn send_html(&self, html: &str) -> PyResult<String> {
        self.enqueue(PlotContent::Html(html.to_string()))
    }

    fn shutdown(&self) -> PyResult<()> {
        runtime()
            .block_on(self.handle.shutdown())
            .map_err(to_py_err)
    }
}

impl PyViewer {
    fn enqueue(&self, content: PlotContent) -> PyResult<String> {
        let msg = PlotMessage::new(content);
        let id = msg.id.clone();
        let handle = self.handle.clone();
        runtime().spawn(async move {
            handle.publish(msg).await;
        });
        Ok(id)
    }
}

#[pymodule]
fn _core(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyViewer>()?;
    Ok(())
}

fn to_py_err(err: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(err.to_string())
}

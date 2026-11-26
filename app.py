import os

os.environ.setdefault("HF_HOME", "/tmp/huggingface")
os.environ.setdefault("TORCH_HOME", "/tmp/torch")
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "/tmp/sentence_transformers")

import gradio as gr
import uvicorn
from fastapi.responses import RedirectResponse
from backend.app.main import app

if not any(getattr(r, "path", None) == "/" for r in app.routes):
    @app.get("/", include_in_schema=False)
    def _root_redirect():
        return RedirectResponse(url="/ui/")

with gr.Blocks(title="Production RAG Service") as demo:
    gr.Markdown("## Production RAG Service\nOpen the full 3-column workspace at `/ui/` or Swagger API docs at `/docs`.")

app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)

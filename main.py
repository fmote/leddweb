from sanic import Sanic
from sanic.response import json
from sanic.exceptions import NotFound
from sanic.response import file
from pathlib import Path

app = Sanic("Ledd")
BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"

@app.route("/")
async def test(request):
    return json({"hello": "world"})




## handle 404
@app.exception(NotFound)
async def handle_404(request, exc):
    return json({
        "error": "Not Found",
        "path": request.path,
        "method": request.method,
    }, status=404)

# Serve static HTML pages from /pages/<filename>
@app.get("/pages/<name:str>")
async def serve_page(request, name: str):
    candidate = PAGES_DIR / name
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".html")
    if candidate.is_file():
        return await file(candidate)
    raise NotFound(f"Page not found: {name}")

# Direct route alias for /fmote
@app.get("/fmote")
async def fmote(request):
    candidate = PAGES_DIR / "fmote.html"
    if candidate.is_file():
        return await file(candidate)
    raise NotFound("fmote page not found")

if __name__ == "__main__":
    # Enable auto-reload so changes to this file (like adding routes) restart the server automatically
    app.run(host="0.0.0.0", port=3000, auto_reload=True)
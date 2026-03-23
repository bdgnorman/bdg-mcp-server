import os
import json
import asyncio
import httpx
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://api.signal.bdg.io")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
DEFAULT_ACCOUNT_ID = os.getenv("DEFAULT_ACCOUNT_ID", "7c634307-06b4-48fd-b75a-0b3c8900bf66")
DEPLOY_SECRET = os.getenv("DEPLOY_SECRET", "bdgsignal-deploy-2026")
MCP_API_KEY = os.getenv("MCP_API_KEY", "")

sessions = {}

def check_auth(request):
    if not MCP_API_KEY: return True
    key = request.headers.get("Authorization", "").replace("Bearer ", "").strip() or request.query_params.get("api_key", "")
    return key == MCP_API_KEY

ALL_TOOLS = [
    {"name": "metrics_query", "description": "Query marketing metrics (sessions, email stats, ad performance).", "inputSchema": {"type": "object", "properties": {"metric_type": {"type": "string", "enum": ["website", "email", "paid", "organic", "leads"]}, "date_range": {"type": "string", "enum": ["7d", "30d", "90d", "ytd"]}}, "required": ["metric_type"]}},
    {"name": "goals_status", "description": "Get goal progress and targets.", "inputSchema": {"type": "object", "properties": {"goal_type": {"type": "string", "enum": ["leads", "mqls", "revenue", "all"]}, "period": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]}}}},
    {"name": "insights_list", "description": "List AI insights.", "inputSchema": {"type": "object", "properties": {"dashboard_context": {"type": "string"}, "limit": {"type": "integer", "default": 10}}}},
    {"name": "memory_search", "description": "Search knowledge base.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}}, "required": ["query"]}},
    {"name": "schema_describe", "description": "Describe database schema.", "inputSchema": {"type": "object", "properties": {"category": {"type": "string"}}}},
    {"name": "contacts_create", "description": "Create a new contact. REQUIRES confirmed=true.", "inputSchema": {"type": "object", "properties": {"email": {"type": "string"}, "first_name": {"type": "string"}, "last_name": {"type": "string"}, "company_name": {"type": "string"}, "confirmed": {"type": "boolean", "default": False}}, "required": ["email"]}},
    {"name": "contacts_update", "description": "Update a contact. REQUIRES confirmed=true.", "inputSchema": {"type": "object", "properties": {"contact_id": {"type": "string"}, "updates": {"type": "object"}, "confirmed": {"type": "boolean", "default": False}}}},
    {"name": "campaigns_create", "description": "Create email campaign as DRAFT. REQUIRES confirmed=true.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "subject": {"type": "string"}, "html_content": {"type": "string"}, "confirmed": {"type": "boolean", "default": False}}, "required": ["name", "subject"]}},
    {"name": "memory_save", "description": "Save to knowledge base. REQUIRES confirmed=true.", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "memory_type": {"type": "string"}, "confirmed": {"type": "boolean", "default": False}}, "required": ["content"]}},
    {"name": "deploy_staging", "description": "Deploy latest code to Staging (staging.signal.bdg.io). Requires confirmed=true.", "inputSchema": {"type": "object", "properties": {"confirmed": {"type": "boolean", "default": False}}}},
    {"name": "deploy_production", "description": "Deploy latest code to Production (signal.bdg.io). USE WITH CAUTION. Requires confirmed=true.", "inputSchema": {"type": "object", "properties": {"confirmed": {"type": "boolean", "default": False}}}}
]

TOOL_TO_FUNCTION = {
    "metrics_query": "ai-metrics-query",
    "goals_status": "ai-goals-status",
    "insights_list": "ai-insights-list",
    "contacts_create": "ai-contacts-create",
    "contacts_update": "ai-contacts-update",
    "campaigns_create": "ai-campaigns-create",
    "memory_search": "ai-memory-search",
    "memory_save": "ai-memory-save",
    "schema_describe": "ai-schema-describe",
}


async def call_edge_function(function_name: str, params: dict) -> dict:
    params.setdefault("account_id", DEFAULT_ACCOUNT_ID)
    url = f"{SUPABASE_URL}/functions/v1/{function_name}"
    headers = {"Authorization": f"Bearer {SUPABASE_ANON_KEY}", "Content-Type": "application/json", "apikey": SUPABASE_ANON_KEY}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=params, headers=headers)
        return response.json()


def call_deploy_subprocess(environment: str) -> dict:
    import subprocess
    cmds = {
        "staging": "cd /var/www/bdgsignal-staging && git stash && git pull origin main && docker run --rm -v $(pwd):/app -w /app node:20-alpine sh -c \'npm install && npm run build -- --mode staging\' && docker restart bdgsignal-staging",
        "production": "cd /var/www/bdgsignal-production && git stash && git pull origin main && docker run --rm -v $(pwd):/app -w /app node:20-alpine sh -c \'npm install && cp .env.production .env && npm run build\' && docker restart bdgsignal-production"
    }
    cmd = cmds.get(environment)
    if not cmd:
        return {"success": False, "error": f"Unknown environment: {environment}"}
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output": r.stdout[-1000:]}
        return {"success": False, "error": r.stderr[-500:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_tool_call(tool_name: str, tool_args: dict) -> str:
    if tool_name == "deploy_staging":
        if not tool_args.get("confirmed"):
            return "Bitte mit confirmed=true bestätigen um Staging zu deployen."
        result = call_deploy_subprocess("staging")
        return f"✅ Staging deployed!" if result.get("success") else f"❌ Fehler: {result.get('error')}"

    if tool_name == "deploy_production":
        if not tool_args.get("confirmed"):
            return "Bitte mit confirmed=true bestätigen um Production zu deployen."
        result = call_deploy_subprocess("production")
        return f"✅ Production deployed!" if result.get("success") else f"❌ Fehler: {result.get('error')}"

    if tool_name in TOOL_TO_FUNCTION:
        result = await call_edge_function(TOOL_TO_FUNCTION[tool_name], tool_args)
        return json.dumps(result, ensure_ascii=False)

    return f"Unknown tool: {tool_name}"


def handle_mcp_message(body: dict):
    method = body.get("method", "")
    req_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "bdgSignal MCP", "version": "3.0.0"}}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": ALL_TOOLS}}

    if method in ["notifications/initialized", "notifications/cancelled"]:
        return None

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


@app.get("/sse")
async def sse_endpoint(request: Request):
    if not check_auth(request): return JSONResponse({"error":"Unauthorized"},status_code=401)
    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    sessions[session_id] = queue

    async def event_generator():
        yield {"event": "endpoint", "data": f"/message?sessionId={session_id}"}
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"event": "message", "data": json.dumps(message)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            sessions.pop(session_id, None)

    return EventSourceResponse(event_generator())


@app.post("/message")
async def message_endpoint(request: Request):
    session_id = request.query_params.get("sessionId")
    if not session_id or session_id not in sessions:
        return JSONResponse({"error": "Invalid session"}, status_code=400)

    try:
        body = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    queue = sessions[session_id]

    if body.get("method") == "tools/call":
        params = body.get("params", {})
        req_id = body.get("id")

        async def execute_and_respond():
            try:
                result = await handle_tool_call(params.get("name", ""), params.get("arguments", {}))
                await queue.put({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result}]}})
            except Exception as e:
                await queue.put({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}})

        asyncio.create_task(execute_and_respond())
        return JSONResponse({"status": "accepted"})

    response = handle_mcp_message(body)
    if response:
        await queue.put(response)
    return JSONResponse({"status": "ok"})


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0", "tools": len(ALL_TOOLS)}


@app.post("/mcp")
async def mcp_legacy(request: Request):
    try:
        body = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if body.get("method") == "tools/call":
        params = body.get("params", {})
        req_id = body.get("id")
        try:
            result = await handle_tool_call(params.get("name", ""), params.get("arguments", {}))
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result}]}})
        except Exception as e:
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}})

    response = handle_mcp_message(body)
    if response is None:
        return JSONResponse({"status": "ok"})
    return JSONResponse(response)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

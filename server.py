import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ojsgvzqsqtlogrtviucn.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# Default account_id for LangSmith testing (bdg account)
DEFAULT_ACCOUNT_ID = "7bb67743-b7c8-4fb8-a9ca-e10cb4815fc4"

# ============================================================
# TOOL DEFINITIONS - READ TOOLS (no side effects)
# ============================================================
READ_TOOLS = [
    {
        "name": "metrics_query",
        "description": "Query marketing metrics (website sessions, email stats, ad performance). Use for: traffic data, open rates, click rates, conversions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account UUID (optional, uses default if not provided)"},
                "metric_type": {"type": "string", "enum": ["website", "email", "paid", "organic", "leads"]},
                "date_range": {"type": "string", "enum": ["7d", "30d", "90d", "ytd"]}
            },
            "required": ["metric_type"]
        }
    },
    {
        "name": "goals_status",
        "description": "Get goal progress and targets. Shows: lead goals, MQL targets, revenue objectives with current vs target.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "goal_type": {"type": "string", "enum": ["leads", "mqls", "revenue", "all"]},
                "period": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]}
            }
        }
    },
    {
        "name": "insights_list",
        "description": "List existing AI insights. Filter by dashboard context or status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "dashboard_context": {"type": "string", "enum": ["email", "website", "paid", "organic", "leads", "executive"]},
                "status": {"type": "string", "enum": ["new", "seen", "actioned"]},
                "limit": {"type": "integer", "default": 10}
            }
        }
    },
    {
        "name": "memory_search",
        "description": "Search knowledge base for historical data, past decisions, or context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "query": {"type": "string", "description": "Search query"},
                "category": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "schema_describe",
        "description": "Describe database schema and available data structures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "category": {"type": "string", "enum": ["marketing", "email", "contacts", "tracking", "goals"]}
            }
        }
    }
]

# ============================================================
# TOOL DEFINITIONS - WRITE TOOLS (require Human-in-Loop)
# ============================================================
WRITE_TOOLS = [
    {
        "name": "contacts_create",
        "description": "Create a new contact. REQUIRES CONFIRMATION before execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "email": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "company_name": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["email"]
        }
    },
    {
        "name": "contacts_update",
        "description": "Update an existing contact. REQUIRES CONFIRMATION.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "contact_id": {"type": "string"},
                "email": {"type": "string"},
                "updates": {"type": "object"}
            }
        }
    },
    {
        "name": "segments_create",
        "description": "Create a new contact segment. REQUIRES CONFIRMATION.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "rules": {"type": "object"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name"]
        }
    },
    {
        "name": "campaigns_create",
        "description": "Create email campaign as DRAFT. Never auto-sends. REQUIRES CONFIRMATION.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "name": {"type": "string"},
                "brand_id": {"type": "string"},
                "subject": {"type": "string"},
                "html_content": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name", "brand_id", "subject"]
        }
    },
    {
        "name": "workflows_create",
        "description": "Create automation workflow as DRAFT. REQUIRES CONFIRMATION.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "name": {"type": "string"},
                "brand_id": {"type": "string"},
                "trigger_type": {"type": "string"},
                "template": {"type": "string", "enum": ["welcome_series", "re_engagement", "lead_nurturing", "score_threshold"]},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name"]
        }
    },
    {
        "name": "insights_generate",
        "description": "Generate new AI insights based on current metrics. REQUIRES CONFIRMATION.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "dashboard_context": {"type": "string"},
                "focus_area": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False}
            }
        }
    },
    {
        "name": "memory_save",
        "description": "Save knowledge to memory. REQUIRES CONFIRMATION.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "memory_type": {"type": "string"},
                "category": {"type": "string"},
                "content": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["content"]
        }
    }
]

# ============================================================
# TOOL NAME TO EDGE FUNCTION MAPPING
# ============================================================
TOOL_TO_FUNCTION = {
    "metrics_query": "ai-metrics-query",
    "goals_status": "ai-goals-status",
    "insights_list": "ai-insights-list",
    "insights_generate": "ai-insights-generate",
    "memory_search": "ai-memory-search",
    "memory_save": "ai-memory-save",
    "schema_describe": "ai-schema-describe",
    "contacts_create": "ai-contacts-create",
    "contacts_update": "ai-contacts-update",
    "segments_create": "ai-segments-create",
    "campaigns_create": "ai-campaigns-create",
    "workflows_create": "ai-workflows-create",
}


async def call_edge_function(function_name: str, params: dict) -> dict:
    """Call Supabase Edge Function with account_id"""
    # Use provided account_id or default
    if "account_id" not in params or not params["account_id"]:
        params["account_id"] = DEFAULT_ACCOUNT_ID
    
    url = f"{SUPABASE_URL}/functions/v1/{function_name}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=params, headers=headers)
        return response.json()


async def handle_mcp_request(request: Request, tools: list):
    """Generic MCP request handler"""
    try:
        body = await request.json()
    except:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
    
    method = body.get("method", "")
    req_id = body.get("id")
    params = body.get("params", {})
    
    # Initialize
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bdgSignal MCP", "version": "2.0.0"}
            }
        })
    
    # List tools
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools}
        })
    
    # Call tool
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        
        if tool_name not in TOOL_TO_FUNCTION:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
            })
        
        try:
            result = await call_edge_function(TOOL_TO_FUNCTION[tool_name], tool_args)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
            })
        except Exception as e:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(e)}
            })
    
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    })


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "endpoints": ["/read", "/write"]}


@app.post("/read")
async def mcp_read(request: Request):
    """MCP endpoint for READ operations (no side effects)"""
    return await handle_mcp_request(request, READ_TOOLS)


@app.post("/write")
async def mcp_write(request: Request):
    """MCP endpoint for WRITE operations (require confirmation)"""
    return await handle_mcp_request(request, WRITE_TOOLS)


# Keep legacy endpoint for backwards compatibility
@app.post("/mcp")
async def mcp_legacy(request: Request):
    """Legacy endpoint - all tools (for backwards compatibility)"""
    all_tools = READ_TOOLS + WRITE_TOOLS
    return await handle_mcp_request(request, all_tools)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

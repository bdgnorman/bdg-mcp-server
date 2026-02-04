import os
import json
import httpx
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Any, Optional
import uuid

app = FastAPI(title="bdgSignal MCP Server")

# CORS für LangSmith
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ojsgvzqsqtlogrtviucn.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# Tool Definitions
TOOLS = [
    {
        "name": "metrics_query",
        "description": "Query marketing metrics (website, email, paid, leads)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metric_type": {"type": "string", "enum": ["email", "website", "paid", "organic", "leads"]},
                "date_range": {"type": "string", "enum": ["7d", "30d", "90d", "ytd"]},
                "brand_id": {"type": "string", "description": "Optional brand UUID"}
            },
            "required": ["metric_type", "date_range"]
        }
    },
    {
        "name": "goals_status",
        "description": "Get current goal progress and status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal_type": {"type": "string", "enum": ["leads", "mqls", "revenue"]},
                "period": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]}
            }
        }
    },
    {
        "name": "insights_list",
        "description": "List AI-generated insights for dashboard",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dashboard_context": {"type": "string", "enum": ["email", "website", "paid", "organic", "leads", "executive"]},
                "status": {"type": "string", "enum": ["new", "seen", "actioned"]},
                "limit": {"type": "integer", "default": 10}
            }
        }
    },
    {
        "name": "insights_generate",
        "description": "Generate new AI insights based on current metrics",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dashboard_context": {"type": "string"},
                "focus_area": {"type": "string"}
            },
            "required": ["dashboard_context"]
        }
    },
    {
        "name": "memory_search",
        "description": "Search historical knowledge and patterns",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_save",
        "description": "Save new knowledge to memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_type": {"type": "string"},
                "category": {"type": "string"},
                "content": {"type": "string"},
                "structured_data": {"type": "object"}
            },
            "required": ["memory_type", "content"]
        }
    },
    {
        "name": "schema_describe",
        "description": "Describe available data structures",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["marketing", "email", "contacts", "tracking", "goals"]}
            }
        }
    },
    {
        "name": "contacts_create",
        "description": "Create a new contact (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
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
        "description": "Update contact (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "email": {"type": "string"},
                "updates": {"type": "object"},
                "confirmed": {"type": "boolean", "default": False}
            }
        }
    },
    {
        "name": "segments_create",
        "description": "Create a new segment (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rules": {"type": "object"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name", "rules"]
        }
    },
    {
        "name": "campaigns_create",
        "description": "Create campaign as DRAFT (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "brand_id": {"type": "string"},
                "subject": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name", "brand_id", "subject"]
        }
    }
]

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
}


async def call_edge_function(tool_name: str, arguments: dict, jwt: str = None) -> dict:
    """Call Supabase Edge Function"""
    function_name = TOOL_TO_FUNCTION.get(tool_name)
    if not function_name:
        return {"error": f"Unknown tool: {tool_name}"}
    
    url = f"{SUPABASE_URL}/functions/v1/{function_name}"
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
    }
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=arguments, headers=headers)
            if response.status_code >= 400:
                return {"error": response.text, "status": response.status_code}
            return response.json()
        except Exception as e:
            return {"error": str(e)}


def create_jsonrpc_response(id: Any, result: Any = None, error: dict = None) -> dict:
    """Create JSON-RPC 2.0 response"""
    response = {"jsonrpc": "2.0", "id": id}
    if error:
        response["error"] = error
    else:
        response["result"] = result
    return response


async def handle_jsonrpc(request_data: dict) -> dict:
    """Handle JSON-RPC request"""
    method = request_data.get("method", "")
    params = request_data.get("params", {})
    req_id = request_data.get("id")
    
    # Initialize
    if method == "initialize":
        return create_jsonrpc_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False}
            },
            "serverInfo": {
                "name": "bdgSignal",
                "version": "1.0.0"
            }
        })
    
    # List tools
    elif method == "tools/list":
        return create_jsonrpc_response(req_id, {"tools": TOOLS})
    
    # Call tool
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name not in TOOL_TO_FUNCTION:
            return create_jsonrpc_response(req_id, error={
                "code": -32602,
                "message": f"Unknown tool: {tool_name}"
            })
        
        result = await call_edge_function(tool_name, arguments)
        
        return create_jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(result)}]
        })
    
    # Ping
    elif method == "ping":
        return create_jsonrpc_response(req_id, {})
    
    # Unknown method
    else:
        return create_jsonrpc_response(req_id, error={
            "code": -32601,
            "message": f"Method not found: {method}"
        })


@app.get("/")
async def root():
    return {"status": "ok", "service": "bdgSignal MCP Server", "protocol": "MCP"}


@app.api_route("/mcp", methods=["GET", "POST"])
async def mcp_endpoint(request: Request):
    """MCP Streamable HTTP endpoint"""
    
    if request.method == "GET":
        # SSE stream for server-initiated messages (not used for now)
        async def event_stream():
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    
    # POST - Handle JSON-RPC requests
    try:
        body = await request.json()
    except:
        return Response(
            content=json.dumps(create_jsonrpc_response(None, error={
                "code": -32700,
                "message": "Parse error"
            })),
            media_type="application/json"
        )
    
    # Handle batch or single request
    if isinstance(body, list):
        responses = [await handle_jsonrpc(req) for req in body]
        return Response(content=json.dumps(responses), media_type="application/json")
    else:
        response = await handle_jsonrpc(body)
        return Response(content=json.dumps(response), media_type="application/json")


@app.get("/health")
async def health():
    return {"status": "healthy"}

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()

# Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ojsgvzqsqtlogrtviucn.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# Default account_id für LangSmith Testing (bdg Account)
DEFAULT_ACCOUNT_ID = "7c634307-06b4-48fd-b75a-0b3c8900bf66"

# Tool Definitions mit account_id Parameter
TOOLS = [
    {
        "name": "metrics_query",
        "description": "Query marketing metrics (website, email, paid, leads)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "metric_type": {"type": "string", "enum": ["email", "website", "paid", "organic", "leads"]},
                "date_range": {"type": "string", "enum": ["7d", "30d", "90d", "ytd"]},
                "brand_id": {"type": "string", "description": "Optional brand filter"}
            },
            "required": ["metric_type"]
        }
    },
    {
        "name": "goals_status",
        "description": "Get goal progress and master funnel status (2,200 leads/year target)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "goal_type": {"type": "string", "enum": ["leads", "mqls", "revenue", "channel_specific"]},
                "period": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]}
            }
        }
    },
    {
        "name": "insights_list",
        "description": "List existing AI insights for dashboard",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
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
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "dashboard_context": {"type": "string", "enum": ["email", "website", "paid", "organic", "leads", "executive"]},
                "focus_area": {"type": "string"}
            },
            "required": ["dashboard_context"]
        }
    },
    {
        "name": "memory_search",
        "description": "Search knowledge base for historical context",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "query": {"type": "string", "description": "Search query"},
                "category": {"type": "string", "enum": ["email", "website", "paid", "goals", "insights"]},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_save",
        "description": "Save new knowledge to memory (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "memory_type": {"type": "string", "enum": ["metric_snapshot", "insight", "learning", "action_taken"]},
                "category": {"type": "string"},
                "content": {"type": "string"},
                "structured_data": {"type": "object"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["memory_type", "content"]
        }
    },
    {
        "name": "schema_describe",
        "description": "Describe available data structures in bdgSignal",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "table_name": {"type": "string"},
                "category": {"type": "string", "enum": ["marketing", "email", "contacts", "tracking", "goals"]}
            }
        }
    },
    {
        "name": "contacts_create",
        "description": "Create new contact (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "email": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "company_name": {"type": "string"},
                "source": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["email"]
        }
    },
    {
        "name": "contacts_update",
        "description": "Update existing contact (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "contact_id": {"type": "string"},
                "email": {"type": "string", "description": "Fallback lookup by email"},
                "updates": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                        "lifecycle_stage": {"type": "string"},
                        "lead_score_adjustment": {"type": "integer"},
                        "add_tags": {"type": "array", "items": {"type": "string"}},
                        "remove_tags": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["updates"]
        }
    },
    {
        "name": "segments_create",
        "description": "Create new segment (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
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
        "description": "Create email campaign as DRAFT (requires confirmation, never auto-sends)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "name": {"type": "string"},
                "brand_id": {"type": "string"},
                "subject": {"type": "string"},
                "preheader": {"type": "string"},
                "html_content": {"type": "string"},
                "segment_ids": {"type": "array", "items": {"type": "string"}},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name", "brand_id", "subject"]
        }
    },
    {
        "name": "workflows_create",
        "description": "Create automation workflow as DRAFT (requires confirmation)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Account ID (optional, defaults to test account)"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "brand_id": {"type": "string"},
                "trigger_type": {"type": "string"},
                "template": {"type": "string", "enum": ["welcome_series", "re_engagement", "lead_nurturing", "score_threshold"]},
                "confirmed": {"type": "boolean", "default": False}
            },
            "required": ["name"]
        }
    }
]

# Mapping Tool Name -> Edge Function
TOOL_ENDPOINTS = {
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
    "workflows_create": "ai-workflows-create"
}


@app.get("/health")
async def health():
    return {"status": "ok", "server": "bdg-mcp-server"}


@app.post("/mcp")
async def mcp_handler(request: Request):
    """JSON-RPC 2.0 Handler for MCP Protocol"""
    try:
        body = await request.json()
    except:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})
    
    jsonrpc = body.get("jsonrpc")
    method = body.get("method")
    params = body.get("params", {})
    req_id = body.get("id")
    
    if jsonrpc != "2.0":
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": req_id})
    
    # Handle MCP methods
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bdg-mcp-server", "version": "1.0.0"}
            }
        })
    
    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        })
    
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        if tool_name not in TOOL_ENDPOINTS:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
            })
        
        # Get account_id from args or use default
        account_id = tool_args.get("account_id") or DEFAULT_ACCOUNT_ID
        
        # Always include account_id in the request to Edge Function
        tool_args["account_id"] = account_id
        
        # Call Edge Function
        endpoint = TOOL_ENDPOINTS[tool_name]
        url = f"{SUPABASE_URL}/functions/v1/{endpoint}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    json=tool_args,
                    headers={
                        "Content-Type": "application/json",
                        "apikey": SUPABASE_ANON_KEY,
                        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
                    }
                )
                
                result_text = response.text
                try:
                    result_data = response.json()
                except:
                    result_data = {"raw": result_text}
                
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": str(result_data) if isinstance(result_data, dict) else result_text
                            }
                        ]
                    }
                })
                
            except Exception as e:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"Edge Function error: {str(e)}"}
                })
    
    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

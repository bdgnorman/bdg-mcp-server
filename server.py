import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import json

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

# Tool Definitions für MCP
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

# Tool name → Edge Function mapping
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


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict
    jwt: Optional[str] = None


@app.get("/")
async def root():
    return {"status": "ok", "service": "bdgSignal MCP Server"}


@app.get("/mcp/tools")
async def list_tools():
    """MCP: List available tools"""
    return {"tools": TOOLS}


@app.post("/mcp/call")
async def call_tool(request: ToolCallRequest):
    """MCP: Execute a tool"""
    tool_name = request.name
    arguments = request.arguments
    jwt = request.jwt
    
    if tool_name not in TOOL_TO_FUNCTION:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    function_name = TOOL_TO_FUNCTION[tool_name]
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
                return {
                    "error": True,
                    "status": response.status_code,
                    "message": response.text
                }
            
            return {
                "result": response.json()
            }
        except Exception as e:
            return {
                "error": True,
                "message": str(e)
            }


@app.get("/health")
async def health():
    return {"status": "healthy"}

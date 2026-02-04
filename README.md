# bdg-mcp-server

MCP Server for LangSmith Agent Builder connecting to bdgSignal Supabase Edge Functions.

## Tools Available

- `metrics_query` - Query marketing metrics
- `goals_status` - Get goal progress
- `insights_list` - List AI insights
- `insights_generate` - Generate new insights
- `memory_search` - Search knowledge base
- `memory_save` - Save to memory
- `schema_describe` - Describe data structures
- `contacts_create` - Create contacts (HITL)
- `contacts_update` - Update contacts (HITL)
- `segments_create` - Create segments (HITL)
- `campaigns_create` - Create campaigns as draft (HITL)

## Deployment

1. Set environment variable `SUPABASE_ANON_KEY`
2. Run with Docker:
```bash
   docker-compose up -d
```

## LangSmith Configuration

Add MCP Server in LangSmith Agent Builder:
- Name: `bdgSignal`
- URL: `http://your-server-ip:8000/mcp`
- Auth: Static Headers (optional)

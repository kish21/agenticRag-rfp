"""
MCP server — lets Claude Code query the app database directly in conversation.
Run: python .mcp/database-server.py
Requires: DATABASE_URL in .env
"""
import os
import psycopg2
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("database")

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

@mcp.tool()
def query_db(sql: str) -> str:
    """Run a read-only SQL query against the app database."""
    if any(kw in sql.upper() for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE"]):
        return "Error: only SELECT queries allowed"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return str([dict(zip(cols, row)) for row in rows[:50]])

@mcp.tool()
def list_tables() -> str:
    """List all tables in the database."""
    return query_db("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")

@mcp.tool()
def describe_table(table_name: str) -> str:
    """Show columns and types for a given table."""
    return query_db(
        f"SELECT column_name, data_type, is_nullable "
        f"FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' ORDER BY ordinal_position"
    )

if __name__ == "__main__":
    mcp.run()

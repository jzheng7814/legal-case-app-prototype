
import sys
import os
import json
import argparse
import asyncio
from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax
from dotenv import load_dotenv

# When running as module app.test_clearinghouse, __file__ is backend/app/test_clearinghouse.py
# .env is in backend/.env, so parents[1] from app/ is backend/
CUR_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CUR_DIR.parent
load_dotenv(BACKEND_ROOT / ".env")

from app.services.clearinghouse import ClearinghouseClient
from app.core.config import get_settings

def main():
    parser = argparse.ArgumentParser(description="Test Clearinghouse API")
    parser.add_argument("case_id", nargs="?", default="46094", help="Case ID to fetch")
    args = parser.parse_args()

    console = Console()
    settings = get_settings()
    
    # Check env var directly first just in case
    api_key = os.environ.get("CLEARINGHOUSE_API_KEY") or settings.clearinghouse_api_key
    
    if not api_key:
        console.print("[bold red]Error:[/] CLEARINGHOUSE_API_KEY not set env")
        sys.exit(1)

    console.print(f"[bold blue]Initializing ClearinghouseClient for Case {args.case_id}...[/]")
    client = ClearinghouseClient(api_key=api_key)

    # 1. Fetch Case Metadata
    console.print("\n[bold green]1. Fetching Case Metadata (_fetch_case)...[/]")
    try:
        case_data = client._fetch_case(args.case_id)
        if case_data:
            json_str = json.dumps(case_data, indent=2)
            console.print(Syntax(json_str, "json"))
        else:
            console.print("[yellow]No case data returned (or invalid format).[/]")
    except Exception as e:
        console.print(f"[bold red]Error fetching case:[/]\n{e}")

    # 2. Fetch Documents
    console.print("\n[bold green]2. Fetching Documents (_fetch_documents)...[/]")
    try:
        docs_data = client._fetch_documents(args.case_id)
        json_str = json.dumps(docs_data, indent=2)
        console.print(f"Found {len(docs_data)} documents.")
        # console.print(Syntax(json_str, "json"))
        
        # INVESTIGATION: Check for text_url and fetch it
        import httpx
        for doc in docs_data:
            doc_id = doc.get("id")
            title = doc.get("description") or doc.get("title") or "Untitled"
            has_text = doc.get("has_text")
            text_url = doc.get("text_url")
            
            console.print(f"Doc {doc_id}: {title} (has_text={has_text})")
            
            if has_text and text_url:
                console.print(f"   Fetching text from: {text_url}")
                # Use client headers but fetching absolute URL
                headers = client._headers()
                try:
                    # Note: text_url might need authentication
                    resp = httpx.get(text_url, headers=headers, timeout=30.0)
                    resp.raise_for_status()
                    
                    # Try to parse as JSON first (API often returns JSON wrapper), 
                    # or it might be raw text.
                    try:
                        data = resp.json()
                        text_content = data if isinstance(data, str) else json.dumps(data, indent=2)
                    except ValueError:
                        text_content = resp.text
                        
                    preview = text_content[:500].replace("\n", " ")
                    console.print(f"   [bold cyan]Content Preview:[/] {preview}...")
                except Exception as ex:
                    console.print(f"   [bold red]Failed to fetch text:[/] {ex}")
            else:
                console.print("   [dim]No text_url available.[/]")
                
    except Exception as e:
        console.print(f"[bold red]Error fetching documents:[/]\n{e}")

    # 3. Fetch Dockets
    console.print("\n[bold green]3. Fetching Dockets (_fetch_dockets)...[/]")
    try:
        dockets_data = client._fetch_dockets(args.case_id)
        json_str = json.dumps(dockets_data, indent=2)
        console.print(f"Found {len(dockets_data)} dockets.")
        console.print(Syntax(json_str, "json"))
    except Exception as e:
        console.print(f"[bold red]Error fetching dockets:[/]\n{e}")

    # 4. Verify Full Integration (fetch_case_documents)
    console.print("\n[bold green]4. Verifying Integration (fetch_case_documents)...[/]")
    try:
        documents, title = client.fetch_case_documents(args.case_id)
        console.print(f"Fetched {len(documents)} processed documents for '{title}'")
        
        for doc in documents:
            has_text_content = len(doc.content) > 200 and "No inline text" not in doc.content[:100]
            status_color = "green" if has_text_content else "yellow"
            console.print(f"Doc {doc.id}: {doc.title} - Content Len: {len(doc.content)} [{status_color}]Has Text: {has_text_content}[/]")
            if has_text_content:
                 console.print(f"   Preview: {doc.content[:100].replace(chr(10), ' ')}...")
                 
    except Exception as e:
        console.print(f"[bold red]Error in fetch_case_documents:[/]\n{e}")

if __name__ == "__main__":
    main()


import asyncio
import logging
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.agent.driver import AgentDriver
from app.core.config import get_settings
from app.services.llm import llm_service

# Configure detailed logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def main():
    settings = get_settings()
    print(f"\n=== Starting Extraction Run ===")
    print(f"Provider: {settings.model.provider}")
    if settings.model.ollama:
        print(f"Model: {settings.model.ollama.response_model}")
    print(f"Case ID: -1 (Local Documents)")
    print("===============================\n")

    # Initialize Driver
    # Case -1 is the default valid case in catalog.json
    driver = AgentDriver(case_id="-1", max_steps=15)
    
    try:
        result = await driver.run()
        
        print("\n\n=== Extraction Complete ===")
        print(json.dumps(result.model_dump(), indent=2, default=str))
        
    except Exception as e:
        logger.exception("Extraction failed")
        
    finally:
        await llm_service.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

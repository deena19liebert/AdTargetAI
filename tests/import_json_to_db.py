# scripts/import_json_to_db.py
import sys, os
sys.path.append(os.path.abspath(os.getcwd()))
import asyncio, json
from pathlib import Path
from app.db.session import AsyncSessionLocal
from app.crud import create_campaign

CAMPAIGN_DIR = Path("data/campaigns")

async def main():
    async with AsyncSessionLocal() as session:
        for f in CAMPAIGN_DIR.glob("*.json"):
            with open(f, "r", encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except Exception as e:
                    print("skip", f, e)
                    continue
                # only import if campaign_id exists
                if "campaign_id" not in data:
                    print("skip, no campaign_id", f)
                    continue
                await create_campaign(session, data)
                print("imported", f.name)

if __name__ == "__main__":
    asyncio.run(main())

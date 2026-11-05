import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panteon.core.database import engine, Base, async_session, init_db
from panteon.core.workspace import Workspace

WORKSPACES = [
    {
        "name": "Alien Inc",
        "slug": "alien-inc",
        "description": "Root group entity. Access layer for the full group.",
        "domain": "alieninc.tech",
        "workspace_type": "holding",
    },
    {
        "name": "Rousseau Holdings",
        "slug": "rousseau-holdings",
        "description": "Capital allocation parent. KMT reports, deal flow, and legal exceptions feed better capital allocation decisions.",
        "domain": "rousseau.alieninc.tech",
        "workspace_type": "company",
        "parent_slug": "alien-inc",
    },
    {
        "name": "Panteon",
        "slug": "panteon",
        "description": "Enterprise Data & AI Operating System. Central platform receiving data from Immanuel and Centra.",
        "domain": "panteon.alieninc.tech",
        "workspace_type": "platform",
        "parent_slug": "alien-inc",
    },
    {
        "name": "Centra",
        "slug": "centra",
        "description": "Vulnerability scanning engine. Feeds vulnerability data into Panteon automation platforms.",
        "domain": "centra.alieninc.tech",
        "workspace_type": "company",
        "parent_slug": "alien-inc",
    },
    {
        "name": "KMT Consulting Group",
        "slug": "kmt",
        "description": "Consulting. Reports, media signals, deal flow, and legal exceptions feed capital allocation.",
        "domain": "kmt.alieninc.tech",
        "workspace_type": "company",
        "parent_slug": "alien-inc",
    },
    {
        "name": "The Daily Art Cult",
        "slug": "thedailyartcult",
        "description": "Media and patron platform.",
        "domain": "thedailyartcult.lol",
        "workspace_type": "company",
        "parent_slug": "alien-inc",
    },
    {
        "name": "Immanuel",
        "slug": "immanuel",
        "description": "Always-on intelligence, enterprise platforms, and in-country security and medical teams across 190+ countries. Feeds real-time risk data to Panteon and Centra.",
        "domain": "immanuel.alieninc.tech",
        "workspace_type": "company",
        "parent_slug": "alien-inc",
    },
]

CROSS_COMPANY_FLOWS = [
    {"from": "immanuel", "to": "panteon", "type": "risk_data", "description": "Real-time risk data feeds into Panteon automation platforms"},
    {"from": "immanuel", "to": "centra", "type": "risk_data", "description": "Risk data feeds into Centra vulnerability scanning"},
    {"from": "centra", "to": "panteon", "type": "vulnerability_data", "description": "Vulnerability data feeds into Panteon automation platforms"},
    {"from": "kmt", "to": "rousseau-holdings", "type": "reports", "description": "Reports, media signals, deal flow feed capital allocation"},
]


async def seed():
    await init_db()

    async with async_session() as db:
        from sqlalchemy import select

        slug_to_id = {}
        for ws_data in WORKSPACES:
            result = await db.execute(select(Workspace).where(Workspace.slug == ws_data["slug"]))
            existing = result.scalar_one_or_none()
            if existing:
                slug_to_id[ws_data["slug"]] = existing.id
                print(f"  Workspace '{ws_data['name']}' already exists")
                continue

            parent_id = None
            if ws_data.get("parent_slug"):
                parent_id = slug_to_id.get(ws_data["parent_slug"])

            ws = Workspace(
                name=ws_data["name"],
                slug=ws_data["slug"],
                description=ws_data.get("description"),
                domain=ws_data.get("domain"),
                parent_workspace_id=parent_id,
                workspace_type=ws_data.get("workspace_type", "company"),
            )
            db.add(ws)
            await db.flush()
            slug_to_id[ws_data["slug"]] = ws.id
            print(f"  Created workspace '{ws_data['name']}'")

        await db.commit()

        from panteon.core.lineage_service import LineageService
        lineage = LineageService(db)

        for flow in CROSS_COMPANY_FLOWS:
            from_id = slug_to_id.get(flow["from"])
            to_id = slug_to_id.get(flow["to"])
            if not from_id or not to_id:
                print(f"  Skipping flow {flow['from']} -> {flow['to']} (workspace not found)")
                continue

            from_node = await lineage.get_or_create_node(
                node_type="workspace", node_id=flow["from"],
                name=flow["from"].replace("-", " ").title(),
            )
            to_node = await lineage.get_or_create_node(
                node_type="workspace", node_id=flow["to"],
                name=flow["to"].replace("-", " ").title(),
            )
            await lineage.create_edge(
                upstream_node_id=str(from_node.id),
                downstream_node_id=str(to_node.id),
                edge_type=flow["type"],
                description=flow["description"],
            )
            print(f"  Linked {flow['from']} -> {flow['to']} ({flow['type']})")

        await db.commit()
        print("\nDone. All workspaces and cross-company flows seeded.")


if __name__ == "__main__":
    asyncio.run(seed())

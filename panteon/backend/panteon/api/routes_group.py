import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user, require_role

router = APIRouter(prefix="/group", tags=["Group Operations"])

ECOSYSTEM_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "alieninc-ecosystem.json"))


def load_ecosystem() -> dict:
    try:
        with open(ECOSYSTEM_PATH) as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ecosystem data unavailable: {str(e)}")


class CompanySummary(BaseModel):
    id: str
    legalName: str
    brandName: str
    category: str
    headcount: int
    revenue2026F: int
    ebitda2026F: int
    margin: float
    revenuePerEmployee: int
    clientCount: int
    pipelineCount: int
    ictIncome: int
    ictSpend: int


@router.get("/overview")
async def group_overview(_user: SupabaseUser = Depends(get_current_user)):
    eco = load_ecosystem()
    companies = eco.get("companies", [])
    clients = eco.get("clientDatabase", [])
    pipeline = eco.get("majorProjectsPipeline", [])
    icts = eco.get("intercompanyTransactions2026F", [])
    rollup = eco.get("groupRollup", {})

    summaries = []
    for c in companies:
        cid = c["id"]
        rev = c["annualFinancials"][-1]["revenue"]
        ebitda = c["annualFinancials"][-1]["ebitda"]
        hc = c["headcount"]["2026F"]
        margin = round(ebitda / rev * 100, 1) if rev else 0
        rpe = rev // hc if hc else 0
        c_clients = [x for x in clients if x["companyId"] == cid]
        c_pipeline = [x for x in pipeline if x["companyId"] == cid]
        ict_in = sum(t["amount"] for t in icts if t["fromCompanyId"] == cid)
        ict_out = sum(t["amount"] for t in icts if t["toCompanyId"] == cid)

        summaries.append({
            "id": cid,
            "legalName": c["legalName"],
            "brandName": c["brandName"],
            "category": c["category"],
            "ownershipStatus": c.get("ownershipStatus", ""),
            "yearFounded": c.get("yearFounded"),
            "foundingDate": c.get("foundingDate"),
            "headcount": hc,
            "fullTime": c["headcount"].get("fullTime", 0),
            "contractors": c["headcount"].get("contractors", 0),
            "revenue2026F": rev,
            "operatingCosts2026F": c["annualFinancials"][-1]["operatingCosts"],
            "ebitda2026F": ebitda,
            "margin": margin,
            "revenuePerEmployee": rpe,
            "clientCount": len(c_clients),
            "pipelineCount": len(c_pipeline),
            "ictIncome": ict_in,
            "ictSpend": ict_out,
            "mission": c.get("mission", ""),
        })

    total_rev = sum(s["revenue2026F"] for s in summaries)
    total_ebitda = sum(s["ebitda2026F"] for s in summaries)
    total_hc = sum(s["headcount"] for s in summaries)

    external_rev = sum(
        c["annualFinancials"][-1]["revenue"]
        for c in companies if c["id"] in ("tdac", "alcantara")
    )
    internal_rev = total_rev - external_rev

    return {
        "metadata": eco.get("metadata", {}),
        "groupProfile": eco.get("groupProfile", {}),
        "companies": summaries,
        "groupTotals": {
            "totalRevenue": total_rev,
            "totalEbitda": total_ebitda,
            "totalHeadcount": total_hc,
            "groupMargin": round(total_ebitda / total_rev * 100, 1) if total_rev else 0,
            "externalRevenue": external_rev,
            "internalRevenue": internal_rev,
            "externalPct": round(external_rev / total_rev * 100, 1) if total_rev else 0,
            "internalPct": round(internal_rev / total_rev * 100, 1) if total_rev else 0,
        },
        "rollup": rollup,
    }


@router.get("/icts")
async def list_icts(
    from_company: Optional[str] = None,
    to_company: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
):
    eco = load_ecosystem()
    icts = eco.get("intercompanyTransactions2026F", [])

    result = []
    for t in icts:
        if from_company and t["fromCompanyId"] != from_company:
            continue
        if to_company and t["toCompanyId"] != to_company:
            continue
        result.append(t)

    total = sum(t["amount"] for t in result)
    return {"transactions": result, "count": len(result), "totalValue": total}


@router.get("/icts/flow-matrix")
async def ict_flow_matrix(_user: SupabaseUser = Depends(get_current_user)):
    eco = load_ecosystem()
    companies = eco.get("companies", [])
    icts = eco.get("intercompanyTransactions2026F", [])
    company_ids = [c["id"] for c in companies]

    matrix = {}
    for src in company_ids:
        matrix[src] = {}
        for dst in company_ids:
            flows = [t for t in icts if t["fromCompanyId"] == src and t["toCompanyId"] == dst]
            matrix[src][dst] = {
                "amount": sum(f["amount"] for f in flows),
                "count": len(flows),
                "services": [f["description"] for f in flows],
            }

    totals_by_provider = {}
    for src in company_ids:
        totals_by_provider[src] = sum(matrix[src][dst]["amount"] for dst in company_ids)

    totals_by_consumer = {}
    for dst in company_ids:
        totals_by_consumer[dst] = sum(matrix[src][dst]["amount"] for src in company_ids)

    return {
        "matrix": matrix,
        "companyIds": company_ids,
        "totalsByProvider": totals_by_provider,
        "totalsByConsumer": totals_by_consumer,
        "grandTotal": sum(totals_by_provider.values()),
    }


@router.get("/service-catalog")
async def service_catalog(_user: SupabaseUser = Depends(get_current_user)):
    eco = load_ecosystem()
    companies = eco.get("companies", [])
    icts = eco.get("intercompanyTransactions2026F", [])

    catalog = []
    for c in companies:
        cid = c["id"]
        services_offered = c.get("serviceOfferings", [])
        provided_to = {}
        for t in icts:
            if t["fromCompanyId"] == cid:
                dst = t["toCompanyId"]
                if dst not in provided_to:
                    provided_to[dst] = {"companyId": dst, "services": [], "totalAmount": 0}
                provided_to[dst]["services"].append({
                    "description": t["description"],
                    "amount": t["amount"],
                    "cadence": t["billingCadence"],
                })
                provided_to[dst]["totalAmount"] += t["amount"]

        catalog.append({
            "companyId": cid,
            "brandName": c["brandName"],
            "category": c["category"],
            "serviceOfferings": services_offered,
            "providedTo": list(provided_to.values()),
            "totalRevenueFromICTs": sum(t["amount"] for t in icts if t["fromCompanyId"] == cid),
        })

    return {"catalog": catalog}


@router.get("/billing/invoices")
async def generate_invoices(
    company_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
):
    eco = load_ecosystem()
    companies = {c["id"]: c for c in eco.get("companies", [])}
    icts = eco.get("intercompanyTransactions2026F", [])

    invoices = []
    for t in icts:
        if company_id and t["fromCompanyId"] != company_id:
            continue
        provider = companies.get(t["fromCompanyId"], {})
        consumer = companies.get(t["toCompanyId"], {})

        if t["billingCadence"] == "monthly":
            monthly_amount = t["amount"]
            annual_amount = t["amount"] * 12
        elif t["billingCadence"] == "quarterly":
            monthly_amount = round(t["amount"] / 3)
            annual_amount = t["amount"] * 4
        else:
            monthly_amount = 0
            annual_amount = t["amount"]

        invoices.append({
            "transactionId": t["transactionId"],
            "providerId": t["fromCompanyId"],
            "providerName": provider.get("brandName", t["fromCompanyId"]),
            "consumerId": t["toCompanyId"],
            "consumerName": consumer.get("brandName", t["toCompanyId"]),
            "description": t["description"],
            "contractAmount": t["amount"],
            "billingCadence": t["billingCadence"],
            "monthlyAmount": monthly_amount,
            "annualAmount": annual_amount,
            "status": t.get("status", "active"),
            "period": "2026-01-01 to 2026-12-31",
        })

    total_monthly = sum(i["monthlyAmount"] for i in invoices)
    total_annual = sum(i["annualAmount"] for i in invoices)

    return {
        "invoices": invoices,
        "count": len(invoices),
        "totalMonthly": total_monthly,
        "totalAnnual": total_annual,
    }


@router.get("/clients")
async def list_clients(
    company_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
):
    eco = load_ecosystem()
    clients = eco.get("clientDatabase", [])

    if company_id:
        clients = [c for c in clients if c["companyId"] == company_id]

    total_acv = sum(c["annualContractValue"] for c in clients if c["status"] in ("active", "renewal_due"))
    return {"clients": clients, "count": len(clients), "totalACV": total_acv}


@router.get("/pipeline")
async def list_pipeline(
    company_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
):
    eco = load_ecosystem()
    pipeline = eco.get("majorProjectsPipeline", [])

    if company_id:
        pipeline = [p for p in pipeline if p["companyId"] == company_id]

    total_value = sum(p["expectedRevenue"] for p in pipeline)
    weighted_value = sum(p["expectedRevenue"] * p["probability"] for p in pipeline)

    return {
        "projects": pipeline,
        "count": len(pipeline),
        "totalValue": total_value,
        "weightedValue": round(weighted_value),
    }


@router.get("/holdings")
async def holdings_and_capital(_user: SupabaseUser = Depends(get_current_user)):
    eco = load_ecosystem()
    return eco.get("holdingsAndCapitalFlow", {})


@router.get("/fund-centre")
async def fund_centre(_user: SupabaseUser = Depends(get_current_user)):
    eco = load_ecosystem()
    return eco.get("fundCentre", {})

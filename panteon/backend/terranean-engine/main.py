from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import (
    IngestRequest, ReconstructRequest, RootCauseRequest,
    CounterfactualRequest, InferPurposesRequest,
    ProjectTrajectoryRequest, LeveragePointsRequest,
)
from store import store
import etiology
import teleology

app = FastAPI(title="Terranean Engine", version="1.0.0", description="Dual-mode intelligence: Etiology (causal) + Teleology (purpose)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/ingest")
def ingest(req: IngestRequest):
    store.add_events(req.events)
    return {"ingested": len(req.events), "total": len(store.events)}


@app.post("/reconstruct")
def reconstruct(req: ReconstructRequest):
    events = store.get_events(scope=req.scope)
    G = etiology.build_causal_graph(events)
    return {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}


@app.get("/graph")
def graph():
    return etiology.get_graph()


@app.post("/root-cause")
def root_cause(req: RootCauseRequest):
    return {"target": req.target_id, "root_causes": etiology.find_root_causes(req.target_id, req.depth)}


@app.post("/counterfactual")
def counterfactual(req: CounterfactualRequest):
    return etiology.counterfactual(req.event_ids, req.intervention)


@app.post("/infer-purposes")
def infer_purposes(req: InferPurposesRequest):
    return {"purposes": teleology.infer_purposes(req.actor_scope)}


@app.get("/purposes")
def purposes():
    return {"purposes": teleology.get_purposes()}


@app.post("/project-trajectory")
def project_trajectory(req: ProjectTrajectoryRequest):
    return {"trajectories": teleology.project_trajectory(req.purpose_ids, req.horizon)}


@app.post("/leverage-points")
def leverage_points(req: LeveragePointsRequest):
    return {"leverage_points": teleology.find_leverage_points(req.trajectory_id, req.objective)}


@app.get("/health")
def health():
    return {"status": "healthy", "events": len(store.events), "purposes": len(store.purposes)}


@app.post("/reset")
def reset():
    store.clear()
    return {"status": "cleared"}

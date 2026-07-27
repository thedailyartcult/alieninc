from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import (
    IngestRequest, ReconstructRequest, RootCauseRequest,
    CounterfactualRequest, InferPurposesRequest,
    ProjectTrajectoryRequest, LeveragePointsRequest,
)
from store import store
import eteology
import teliology

app = FastAPI(title="Terranean Engine", version="1.0.0", description="Dual-mode intelligence: Eteology (causal) + Teliology (purpose)")

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
    G = eteology.build_causal_graph(events)
    return {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}


@app.get("/graph")
def graph():
    return eteology.get_graph()


@app.post("/root-cause")
def root_cause(req: RootCauseRequest):
    return {"target": req.target_id, "root_causes": eteology.find_root_causes(req.target_id, req.depth)}


@app.post("/counterfactual")
def counterfactual(req: CounterfactualRequest):
    return eteology.counterfactual(req.event_ids, req.intervention)


@app.post("/infer-purposes")
def infer_purposes(req: InferPurposesRequest):
    return {"purposes": teliology.infer_purposes(req.actor_scope)}


@app.get("/purposes")
def purposes():
    return {"purposes": teliology.get_purposes()}


@app.post("/project-trajectory")
def project_trajectory(req: ProjectTrajectoryRequest):
    return {"trajectories": teliology.project_trajectory(req.purpose_ids, req.horizon)}


@app.post("/leverage-points")
def leverage_points(req: LeveragePointsRequest):
    return {"leverage_points": teliology.find_leverage_points(req.trajectory_id, req.objective)}


@app.get("/health")
def health():
    return {"status": "healthy", "events": len(store.events), "purposes": len(store.purposes)}


@app.post("/reset")
def reset():
    store.clear()
    return {"status": "cleared"}

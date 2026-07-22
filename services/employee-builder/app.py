from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4
import json, os, re
import httpx, yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

DATA_FILE=Path("/data/employee-builder/instances.json")
TEMPLATE_DIR=Path("/app/templates")
STATIC_DIR=Path("/app/static")
EMPLOYEE_REGISTRY_URL=os.getenv("EMPLOYEE_REGISTRY_BASE_URL","http://employee-registry:8000")
app=FastAPI(title="LEOS Employee Builder",version="0.1.0")

class DefinitionRequest(BaseModel): definition: Dict[str,Any]
class YamlRequest(BaseModel): yaml: str
class InstanceCreateRequest(BaseModel): definition: Dict[str,Any]; status: str="draft"
class HireRequest(BaseModel): requested_by: str="admin"

def now(): return datetime.now(timezone.utc).isoformat()
def load_instances():
    if not DATA_FILE.exists(): return {}
    return json.loads(DATA_FILE.read_text())
def save_instances(data):
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    DATA_FILE.write_text(json.dumps(data,indent=2))
def slugify(v): return re.sub(r"[^a-z0-9]+","-",v.lower()).strip("-")
def template_files(): return sorted(TEMPLATE_DIR.glob("*.yaml"))
def load_template(p): return yaml.safe_load(p.read_text())
def validate_definition(d):
    errors=[]
    if d.get("kind")!="EmployeeInstance": errors.append("kind must be EmployeeInstance")
    if not d.get("template_id"): errors.append("template_id is required")
    i=d.get("identity",{})
    for f in ("display_name","role","department"):
        if not i.get(f): errors.append(f"identity.{f} is required")
    p=d.get("provider_policy",{})
    if p.get("mode") not in ("automatic","manual"): errors.append("provider_policy.mode must be automatic or manual")
    if not isinstance(p.get("prefer_local",True),bool): errors.append("provider_policy.prefer_local must be boolean")
    if not isinstance(p.get("allow_cloud",False),bool): errors.append("provider_policy.allow_cloud must be boolean")
    a=d.get("approval_policy",{})
    if a.get("default") not in ("automatic","required","denied"): errors.append("approval_policy.default must be automatic, required, or denied")
    return errors
def instance_to_employee(instance):
    d=instance["definition"];i=d["identity"];r=d.get("responsibilities",{});a=d.get("advanced",{})
    eid=instance.get("employee_id") or f"{slugify(i['display_name'])}-{slugify(i['department'])}"
    caps=[k for k,v in r.items() if v!="disabled"] or ["general.execute"]
    provider=d.get("provider_policy",{})
    model=provider.get("preferred_model")
    schedule=d.get("schedule",{}) if isinstance(d.get("schedule",{}),dict) else {}
    schedule_mode=schedule.get("mode","always")
    windows=schedule.get("windows",[])
    return {
      "contract_version":"leos.employee-definition.v2",
      "employee_id":eid,"name":i["display_name"],"version":"1.0.0",
      "description":i.get("description",i["role"]),"vendor":"User Created","license":"Open Source",
      "department":i["department"],"manager":i.get("manager"),"role":i["role"],
      "capabilities":caps,
      "priority":d.get("priority","normal"),
      "schedule":{"mode":schedule_mode,"timezone":"UTC","windows":windows},
      "model_preferences":[{"provider":"local" if provider.get("prefer_local",True) else "cloud","model":model,"priority":1}] if model else [],
      "resource_profile":{
        "resource_profile":{"cpu_cores_min":a.get("cpu_cores_min",1),"memory_mb_min":a.get("memory_mb_min",512),"gpu_required":a.get("gpu_required",False),"vram_mb_min":a.get("vram_mb_min",0),"gpu_uuid_preferences":a.get("gpu_uuid_preferences",[])},
        "execution_policy":{"max_concurrent_jobs":a.get("max_parallel_jobs",1),"reservation_ttl_seconds":a.get("reservation_ttl_seconds",3600),"queue_when_unavailable":True,"preemptible":True,"allow_preemption":False},
        "node_affinity":{"required_labels":a.get("required_node_labels",{}),"preferred_labels":a.get("preferred_node_labels",{})},
        "fallback_profiles":a.get("fallback_profiles",[])
      },
      "runtime":{"type":"managed","container":None,"endpoint":None,"execute_path":"/execute","health_path":"/health","timeout_seconds":a.get("max_runtime_seconds",300)},
      "limits":{"max_parallel_jobs":a.get("max_parallel_jobs",1),"max_runtime_seconds":a.get("max_runtime_seconds",300),"max_retries":a.get("max_retries",1)},
      "memory":{"namespace":f"{i['department']}.{slugify(i['display_name'])}","read":d.get("memory",{}).get("read",True),"write":d.get("memory",{}).get("write",True)},
      "permissions":{"network":a.get("internet",False),"internet":a.get("internet",False),"memory":True,"event_bus":True,"filesystem":{"read":[],"write":[f"/data/employees/{eid}"] if a.get("filesystem_write",False) else []}},
      "adapters":{"preferred":[]},
      "metadata":{"source":"employee-builder","instance_id":instance["instance_id"],"template_id":d.get("template_id"),"display_name":i["display_name"],"human_identity":True,
                  "approval_policy":d.get("approval_policy",{}),"knowledge_policy":d.get("knowledge",{}),"provider_policy":provider,
                  "integrations":d.get("integrations",{})}
    }

@app.get("/")
def root(): return RedirectResponse("/ui")
@app.get("/ui")
def ui(): return FileResponse(STATIC_DIR/"index.html")
@app.get("/health")
def health(): return {"ok":True,"service":"employee-builder","platform":"LEOS","version":"0.1.0","template_count":len(template_files()),"instance_count":len(load_instances()),"ui":"/ui","editor_modes":["visual","yaml"]}
@app.get("/templates")
def templates(): return [{"template_id":(t:=load_template(p))["template_id"],"name":t["name"],"description":t.get("description"),"category":t.get("category")} for p in template_files()]
@app.get("/templates/{template_id}")
def template(template_id):
    for p in template_files():
        t=load_template(p)
        if t.get("template_id")==template_id:return t
    raise HTTPException(404,"template not found")
@app.post("/yaml/render")
def render_yaml(r:DefinitionRequest): return {"ok":True,"yaml":yaml.safe_dump(r.definition,sort_keys=False,allow_unicode=True)}
@app.post("/yaml/parse")
def parse_yaml(r:YamlRequest):
    try:d=yaml.safe_load(r.yaml)
    except yaml.YAMLError as e:raise HTTPException(422,str(e))
    if not isinstance(d,dict):raise HTTPException(422,"YAML must contain an object")
    errors=validate_definition(d)
    if errors:raise HTTPException(422,errors)
    return {"ok":True,"definition":d}
@app.post("/validate")
def validate(r:DefinitionRequest):
    errors=validate_definition(r.definition)
    return {"ok":True,"valid":not errors,"errors":errors}
@app.post("/instances")
def create_instance(r:InstanceCreateRequest):
    errors=validate_definition(r.definition)
    if errors:raise HTTPException(422,errors)
    data=load_instances();iid=str(uuid4());inst={"instance_id":iid,"status":r.status,"definition":r.definition,"employee_id":None,"created_at":now(),"updated_at":now(),"hired_at":None,"history":[{"event_type":"employee.draft.created","created_at":now()}]}
    data[iid]=inst;save_instances(data);return {"ok":True,"instance":inst}
@app.get("/instances")
def instances(): return list(load_instances().values())
@app.get("/instances/{instance_id}")
def get_instance(instance_id):
    data=load_instances()
    if instance_id not in data:raise HTTPException(404,"instance not found")
    return data[instance_id]
@app.post("/instances/{instance_id}/hire")
async def hire(instance_id,r:HireRequest):
    data=load_instances()
    if instance_id not in data:raise HTTPException(404,"instance not found")
    inst=data[instance_id];errors=validate_definition(inst["definition"])
    if errors:raise HTTPException(422,errors)
    employee=instance_to_employee(inst)
    async with httpx.AsyncClient(timeout=30) as client:
        response=await client.post(f"{EMPLOYEE_REGISTRY_URL}/employees",json={"definition":employee,"actor":r.requested_by,"reason":"employee-builder-hire"})
        response.raise_for_status();created=response.json()
        response=await client.post(f"{EMPLOYEE_REGISTRY_URL}/employees/{employee['employee_id']}/validate",json={"actor":r.requested_by,"reason":"employee-builder-validation","metadata":{"instance_id":instance_id}})
        response.raise_for_status();validated=response.json()
        response=await client.post(f"{EMPLOYEE_REGISTRY_URL}/employees/{employee['employee_id']}/activate",json={"actor":r.requested_by,"reason":"employee-builder-hire","metadata":{"instance_id":instance_id}})
        response.raise_for_status();registry=response.json()
    inst["status"]="hired";inst["employee_id"]=employee["employee_id"];inst["hired_at"]=now();inst["updated_at"]=now()
    inst["history"].append({"event_type":"employee.hired","requested_by":r.requested_by,"created_at":now()})
    data[instance_id]=inst;save_instances(data)
    return {"ok":True,"instance":inst,"employee":employee,"registry_result":registry}

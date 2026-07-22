from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
import json, os, httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DATA_FILE = Path('/data/assignment-service/jobs.json')
EMPLOYEE_REGISTRY_URL = os.getenv('EMPLOYEE_REGISTRY_BASE_URL','http://employee-registry:8000')
EVENT_BUS_URL = os.getenv('EVENT_BUS_BASE_URL','http://event-bus:8000')
app = FastAPI(title='LEOS Assignment Service', version='0.1.0')

class JobCreate(BaseModel):
    title:str; objective:str; user_id:str='brett'; goal_id:Optional[str]=None
    department:Optional[str]=None; priority:int=5; required_capabilities:List[str]=Field(default_factory=list)
    context:Dict[str,Any]=Field(default_factory=dict); metadata:Dict[str,Any]=Field(default_factory=dict)

class JobPatch(BaseModel):
    status:Optional[str]=None; progress:Optional[float]=None; execution_id:Optional[str]=None
    result:Optional[Dict[str,Any]]=None; error:Optional[str]=None; metadata:Dict[str,Any]=Field(default_factory=dict)

class AssignRequest(BaseModel):
    job_id:str; employee_id:Optional[str]=None; force:bool=False; metadata:Dict[str,Any]=Field(default_factory=dict)

class ActionRequest(BaseModel):
    reason:str=''; metadata:Dict[str,Any]=Field(default_factory=dict)

def now(): return datetime.now(timezone.utc).isoformat()
def load():
    if not DATA_FILE.exists(): return {}
    return json.loads(DATA_FILE.read_text())
def save(data):
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    DATA_FILE.write_text(json.dumps(data,indent=2))
def terminal(s): return s in {'complete','failed','cancelled'}
def history(job,event,message,payload=None):
    job.setdefault('history',[]).append({'event_type':event,'message':message,'payload':payload or {},'created_at':now()})

async def emit(client,event,subject,user,payload):
    try:
        await client.post(f'{EVENT_BUS_URL}/events',json={'event_type':event,'source':'assignment-service','subject':subject,'user_id':user,'payload':payload,'metadata':{'phase':'6.0','platform':'LEOS'}},timeout=20)
    except Exception: pass

async def employee(client,eid):
    r=await client.get(f'{EMPLOYEE_REGISTRY_URL}/employees/{eid}',timeout=20)
    if r.status_code==404:return None
    r.raise_for_status(); return r.json()

async def employee_eligibility(client,eid):
    r=await client.get(f'{EMPLOYEE_REGISTRY_URL}/employees/{eid}/eligibility',timeout=20)
    if r.status_code==404:return None
    r.raise_for_status(); return r.json()

async def adjust_load(client,eid,delta):
    e=await employee(client,eid)
    if not e:return
    jobs=max(0,int(e.get('current_jobs',0))+delta)
    max_jobs=e.get('limits',{}).get('max_parallel_jobs',1)
    await client.patch(f'{EMPLOYEE_REGISTRY_URL}/employees/{eid}',json={'current_jobs':jobs,'operational_status':'busy' if jobs>=max_jobs else 'available','metadata':{'assignment_service_updated_at':now()}},timeout=20)

@app.get('/health')
def health():
    return {'ok':True,'service':'assignment-service','platform':'LEOS','version':'0.1.0','job_count':len(load()),'automatic_execution':False}

@app.post('/jobs')
async def create(req:JobCreate):
    data=load(); jid=str(uuid4())
    job={'job_id':jid,'goal_id':req.goal_id,'title':req.title,'objective':req.objective,'user_id':req.user_id,'department':req.department,'priority':req.priority,'status':'queued','required_capabilities':req.required_capabilities,'assigned_employee_id':None,'assignment_score':None,'execution_id':None,'progress':0.0,'context':req.context,'result':None,'error':None,'metadata':req.metadata,'created_at':now(),'updated_at':now(),'started_at':None,'finished_at':None,'history':[]}
    history(job,'job.created','Job created.')
    data[jid]=job; save(data)
    async with httpx.AsyncClient() as client: await emit(client,'job.created',jid,req.user_id,{'job_id':jid})
    return {'ok':True,'job':job}

@app.get('/jobs')
def jobs(status:Optional[str]=None,employee_id:Optional[str]=None,department:Optional[str]=None):
    items=list(load().values())
    if status: items=[j for j in items if j.get('status')==status]
    if employee_id: items=[j for j in items if j.get('assigned_employee_id')==employee_id]
    if department: items=[j for j in items if j.get('department')==department]
    return sorted(items,key=lambda j:(j.get('priority',5),j.get('created_at','')))

@app.get('/jobs/queue')
def queue(): return jobs(status='queued')

@app.get('/jobs/{job_id}')
def get_job(job_id:str):
    data=load()
    if job_id not in data: raise HTTPException(404,'job not found')
    return data[job_id]

@app.post('/assign')
async def assign(req:AssignRequest):
    data=load()
    if req.job_id not in data: raise HTTPException(404,'job not found')
    job=data[req.job_id]
    if terminal(job['status']): raise HTTPException(409,'terminal jobs cannot be assigned')
    async with httpx.AsyncClient() as client:
        if req.employee_id:
            e=await employee(client,req.employee_id)
            if not e: raise HTTPException(404,'employee not found')
            eligibility=await employee_eligibility(client,req.employee_id)
            if not eligibility: raise HTTPException(404,'employee eligibility not found')
            if not eligibility.get('eligible') and not req.force:
                raise HTTPException(409,{'message':'employee is not assignable','eligibility':eligibility})
            selected={'employee_id':e['employee_id'],'name':e['name'],'score':None,'eligibility':eligibility}
        else:
            r=await client.post(f'{EMPLOYEE_REGISTRY_URL}/resolve',json=job.get('required_capabilities',[]),timeout=20)
            r.raise_for_status(); selected=r.json().get('selected_employee')
            if not selected: raise HTTPException(409,'no assignable employee found')
        previous=job.get('assigned_employee_id')
        if previous and previous!=selected['employee_id']: await adjust_load(client,previous,-1)
        job['assigned_employee_id']=selected['employee_id']; job['assignment_score']=selected.get('score'); job['status']='assigned'; job['updated_at']=now(); job['metadata'].update(req.metadata)
        history(job,'job.assigned','Job assigned.',{'employee_id':selected['employee_id'],'score':selected.get('score')})
        data[req.job_id]=job; save(data)
        await adjust_load(client,selected['employee_id'],1)
        await emit(client,'job.assigned',req.job_id,job['user_id'],{'job_id':req.job_id,'employee_id':selected['employee_id']})
    return {'ok':True,'job':job,'employee':selected}

@app.patch('/jobs/{job_id}')
async def patch(job_id:str,req:JobPatch):
    data=load()
    if job_id not in data: raise HTTPException(404,'job not found')
    job=data[job_id]; old=job['status']; eid=job.get('assigned_employee_id')
    for k,v in req.model_dump(exclude_none=True).items():
        if k=='metadata': job.setdefault('metadata',{}).update(v)
        else: job[k]=v
    if job['status']=='running' and not job['started_at']: job['started_at']=now()
    if terminal(job['status']): job['finished_at']=now(); job['progress']=1.0 if job['status']=='complete' else job['progress']
    job['updated_at']=now(); history(job,'job.updated','Job updated.',req.model_dump(exclude_none=True)); data[job_id]=job; save(data)
    async with httpx.AsyncClient() as client:
        if eid and not terminal(old) and terminal(job['status']): await adjust_load(client,eid,-1)
        await emit(client,'job.updated',job_id,job['user_id'],{'job_id':job_id,'status':job['status']})
    return {'ok':True,'job':job}

@app.post('/jobs/{job_id}/pause')
async def pause(job_id:str,req:ActionRequest): return await patch(job_id,JobPatch(status='paused',metadata={'reason':req.reason,**req.metadata}))
@app.post('/jobs/{job_id}/resume')
async def resume(job_id:str,req:ActionRequest):
    current=get_job(job_id); target='assigned' if current.get('assigned_employee_id') else 'queued'
    return await patch(job_id,JobPatch(status=target,metadata={'reason':req.reason,**req.metadata}))
@app.post('/jobs/{job_id}/cancel')
async def cancel(job_id:str,req:ActionRequest): return await patch(job_id,JobPatch(status='cancelled',metadata={'reason':req.reason,**req.metadata}))
@app.get('/employees/{employee_id}/jobs')
def employee_jobs(employee_id:str): return jobs(employee_id=employee_id)

@app.get('/metrics')
def metrics():
    items=list(load().values()); by_status={}; by_employee={}; by_department={}
    for j in items:
        by_status[j['status']]=by_status.get(j['status'],0)+1
        if j.get('assigned_employee_id'): by_employee[j['assigned_employee_id']]=by_employee.get(j['assigned_employee_id'],0)+1
        if j.get('department'): by_department[j['department']]=by_department.get(j['department'],0)+1
    completed=sum(1 for j in items if j['status']=='complete'); failed=sum(1 for j in items if j['status']=='failed')
    return {'ok':True,'total_jobs':len(items),'by_status':by_status,'by_employee':by_employee,'by_department':by_department,'completed_jobs':completed,'failed_jobs':failed,'success_rate':round(completed/max(1,completed+failed),4)}

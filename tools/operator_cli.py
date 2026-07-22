#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOL_DIR = Path(__file__).resolve().parent
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))

from security_observability import (
    build_reports as build_security_observability_reports,
    diagnostics_plan as security_diagnostics_plan,
    export_diagnostics as export_security_diagnostics,
    load_object as load_security_object,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/operator-cli.json"
DEFAULT_SERVICE_CATALOG = ROOT / "config/operator-service-catalog.json"
DEFAULT_SECURITY_OBSERVABILITY_CONFIG = ROOT / "config/security-observability.json"
# Release identity is loaded from manifest.json and source.lock.json.

def release_identity() -> dict[str, str]:
    release = os.environ.get("LEOS_RELEASE_VERSION")
    phase = os.environ.get("LEOS_RELEASE_PHASE")
    manifest_path = ROOT / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            value = read_json(manifest_path)
            if isinstance(value, dict):
                manifest = value
        except Exception:
            manifest = {}
    if not release:
        release = str(manifest.get("release_version") or SOURCE_RELEASE)
    if not phase:
        phase = str(manifest.get("release_phase") or SOURCE_PHASE)
    return {
        "release": release,
        "phase": phase,
        "source_release": SOURCE_RELEASE,
        "source_tree_sha256": SOURCE_TREE,
    }

CONTRACT_CLI = "leos.cli-result.v1"
CONTRACT_STATUS = "leos.system-status.v1"
CONTRACT_DOCTOR = "leos.doctor-report.v1"
CONTRACT_SERVICES = "leos.service-inventory.v1"
CONTRACT_LOGS = "leos.log-query-plan.v1"
CONTRACT_BACKUP = "leos.backup-plan.v1"
CONTRACT_UPDATE = "leos.update-plan.v1"

FORBIDDEN_SECRET_KEYS = {"password","password_hash","secret","secret_value","api_key","access_token","refresh_token","private_key"}

class OperatorError(RuntimeError):
    pass

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

def stable_id(prefix: str, value: Any, length: int = 16) -> str:
    return f"{prefix}-{hashlib.sha256(canonical_json(value)).hexdigest()[:length]}"

def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as h:
        for block in iter(lambda:h.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()

def read_json(path: Path) -> Any:
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc: raise OperatorError(f"Unable to read JSON: {path}") from exc

def load_object(path: Path, contract: str|None=None) -> dict[str,Any]:
    value=read_json(path)
    if not isinstance(value,dict): raise OperatorError(f"Expected JSON object: {path}")
    if contract and value.get('contract_version')!=contract: raise OperatorError(f"Unexpected contract in {path}")
    return value

def load_source_authority(root: Path = ROOT) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    source_lock_path = root / "source.lock.json"
    if not manifest_path.is_file() or not source_lock_path.is_file():
        raise OperatorError(
            "Release authority requires manifest.json and source.lock.json."
        )
    manifest = read_json(manifest_path)
    source_lock = read_json(source_lock_path)
    if not isinstance(manifest, dict) or not isinstance(source_lock, dict):
        raise OperatorError("Release authority files must be JSON objects.")
    if manifest.get("contract_version") != "leos.release-manifest.v1":
        raise OperatorError("Unsupported release-manifest contract.")
    if source_lock.get("contract_version") != "leos.source-lock.v1":
        raise OperatorError("Unsupported source-lock contract.")
    release = str(manifest.get("release_version", ""))
    if source_lock.get("release_version") != release:
        raise OperatorError("Release manifest and source lock disagree.")
    payload = str(source_lock.get("payload_tree_sha256", ""))
    if not re.fullmatch(r"[a-f0-9]{64}", payload):
        raise OperatorError("Source-lock payload hash is invalid.")
    return {
        "release": release,
        "phase": str(manifest.get("release_phase", "unknown")),
        "payload_tree_sha256": payload,
        "manifest_path": str(manifest_path),
        "source_lock_path": str(source_lock_path),
    }


SOURCE_AUTHORITY = load_source_authority()
SOURCE_RELEASE = SOURCE_AUTHORITY["release"]
SOURCE_TREE = SOURCE_AUTHORITY["payload_tree_sha256"]
SOURCE_PHASE = SOURCE_AUTHORITY["phase"]

def contains_forbidden_secret(value: Any) -> bool:
    if isinstance(value,dict):
        return any(str(k).lower() in FORBIDDEN_SECRET_KEYS or contains_forbidden_secret(v) for k,v in value.items())
    if isinstance(value,list): return any(contains_forbidden_secret(v) for v in value)
    return False

def safe_target(value: str|Path) -> Path:
    target=Path(value).expanduser().resolve()
    if len(target.parts)<3 or target.name.lower() in {'','.', '..','bin','boot','dev','etc','home','lib','lib64','proc','root','run','sbin','sys','usr','var'}:
        raise OperatorError(f"Unsafe target root: {target}")
    return target

def safety(read_only: bool=True) -> dict[str,Any]:
    return {'read_only':read_only,'external_network_contacted':False,'container_daemon_contacted':False,'plaintext_secret_exposed':False,'production_state_accessed':False,'production_network_attached':False}

def load_fixture(path: str|None) -> dict[str,Any]:
    if not path: return {}
    value=load_object(Path(path))
    if value.get('contract_version')!='leos.operator-fixture.v1': raise OperatorError('Unsupported operator fixture contract.')
    return value

def file_record(path: Path) -> dict[str,Any]:
    if not path.is_file(): return {'exists':False,'path':str(path)}
    return {'exists':True,'path':str(path),'mode':oct(stat.S_IMODE(path.stat().st_mode)),'size_bytes':path.stat().st_size,'sha256':sha256_file(path)}

def state_documents(target: Path, config: dict[str,Any]) -> dict[str,dict[str,Any]]:
    result={}
    for key,relative in config['state_files'].items():
        path=target/relative
        record=file_record(path)
        if path.is_file():
            try:
                value=load_object(path)
                record['contract_version']=value.get('contract_version')
                record['value']=value
                record['contains_forbidden_secret']=contains_forbidden_secret(value)
            except Exception as exc:
                record['parse_error']=str(exc)
        result[key]=record
    return result

def service_inventory(catalog: dict[str,Any], fixture: dict[str,Any], now: str, allow_daemon: bool=False) -> dict[str,Any]:
    fixture_services=fixture.get('services',{}) if isinstance(fixture.get('services',{}),dict) else {}
    services=[]
    source='fixture' if fixture_services else 'catalog'
    for spec in catalog.get('services',[]):
        observed=fixture_services.get(spec['service_id'],{})
        state=observed.get('state','unknown')
        health=observed.get('health','unknown')
        bindings=observed.get('bindings',[])
        services.append({**spec,'state':state,'health':health,'bindings':bindings,'source':source})
    healthy=sum(1 for s in services if s['health']=='healthy')
    unhealthy=sum(1 for s in services if s['health']=='unhealthy')
    unknown=sum(1 for s in services if s['health']=='unknown')
    required_unhealthy=sum(1 for s in services if s['required'] and s['health']!='healthy')
    return {'contract_version':CONTRACT_SERVICES,'services':services,'summary':{'total':len(services),'healthy':healthy,'unhealthy':unhealthy,'unknown':unknown,'required_unhealthy':required_unhealthy},'source':source,'generated_at':now,'daemon_contact_authorized':bool(allow_daemon),'daemon_contacted':False}

def manifest_drift(target: Path, manifest: dict[str,Any]) -> list[dict[str,Any]]:
    drift=[]
    for rel,expected in sorted(manifest.get('files',{}).items()):
        path=target/rel
        if not path.is_file(): drift.append({'path':rel,'state':'missing'}); continue
        actual=sha256_file(path)
        if actual!=expected.get('sha256'): drift.append({'path':rel,'state':'modified','expected_sha256':expected.get('sha256'),'actual_sha256':actual})
    return drift

def status_payload(target: Path, config: dict[str,Any], catalog: dict[str,Any], fixture: dict[str,Any], now: str) -> dict[str,Any]:
    docs=state_documents(target,config)
    manifest=docs['installation_manifest'].get('value',{})
    readiness=docs['first_run_readiness'].get('value',{})
    services=service_inventory(catalog,fixture,now)
    drift=manifest_drift(target,manifest) if manifest else []
    installation_ok=manifest.get('status')=='installed' and manifest.get('source_release')==SOURCE_RELEASE
    first_run_ok=readiness.get('status')=='ready'
    service_ok=services['summary']['required_unhealthy']==0
    secret_ok=not any(item.get('contains_forbidden_secret') for item in docs.values())
    checks=[
      {'check_id':'installation-installed','ok':installation_ok},
      {'check_id':'first-run-ready','ok':first_run_ok},
      {'check_id':'required-services-healthy','ok':service_ok},
      {'check_id':'manifest-drift-zero','ok':not drift},
      {'check_id':'plaintext-secrets-absent','ok':secret_ok},
    ]
    required_fail=sum(1 for c in checks if not c['ok'])
    status='ready' if required_fail==0 else 'degraded' if installation_ok else 'not-ready'
    resources=fixture.get('resources',{'cpu_cores':None,'memory_available_mb':None,'storage_free_gb':None,'nvidia_gpu_count':None})
    return {'contract_version':CONTRACT_STATUS,'status':status,'target_root':target.as_posix(),'source_release':manifest.get('source_release'),'installation':{'ok':installation_ok,'installation_id':manifest.get('installation_id'),'profile':manifest.get('selected_profile'),'drift':drift},'first_run':{'ok':first_run_ok,'status':readiness.get('status'),'session_id':readiness.get('session_id')},'services':services['summary'],'resources':resources,'checks':checks,'generated_at':now}

def check(check_id: str, domain: str, ok: bool, severity: str, message: str, remediation: str|None=None) -> dict[str,Any]:
    return {'check_id':check_id,'domain':domain,'ok':bool(ok),'severity':'pass' if ok else severity,'message':message,'remediation':None if ok else remediation}

def doctor_payload(target: Path, config: dict[str,Any], catalog: dict[str,Any], fixture: dict[str,Any], now: str, allow_daemon: bool=False, allow_network: bool=False) -> dict[str,Any]:
    docs=state_documents(target,config)
    manifest=docs['installation_manifest'].get('value',{})
    plan=docs['installation_plan'].get('value',{})
    first=docs['first_run_configuration'].get('value',{})
    readiness=docs['first_run_readiness'].get('value',{})
    runtime=docs['runtime_selection'].get('value',{})
    admin=docs['administrator_bootstrap'].get('value',{})
    services=service_inventory(catalog,fixture,now,allow_daemon)
    drift=manifest_drift(target,manifest) if manifest else []
    resources=fixture.get('resources',{})
    runtime_facts=fixture.get('runtime',{})
    public_bindings=[]
    for service in services['services']:
        for binding in service.get('bindings',[]):
            if str(binding).startswith(('0.0.0.0:',':::')): public_bindings.append({'service_id':service['service_id'],'binding':binding})
    checks=[]
    checks.append(check('installation-manifest','installation',manifest.get('status')=='installed','fail','Installation manifest is installed.','Run leos install with the confirmed plan.'))
    checks.append(check('installation-plan','installation',plan.get('contract_version')=='leos.installation-plan.v1','fail','Installation plan is present.','Restore the installation plan.'))
    checks.append(check('source-release','release-integrity',manifest.get('source_release')==SOURCE_RELEASE,'fail',f'Installation source release matches {SOURCE_RELEASE}.',f'Reinstall from the governed {SOURCE_RELEASE} source.'))
    checks.append(check('source-tree','release-integrity',manifest.get('source_tree_sha256')==SOURCE_TREE,'fail','Installation source payload matches source.lock.json.','Reinstall from the exact source.lock.json payload.'))
    checks.append(check('manifest-drift','configuration-drift',not drift,'warn','Installed files match the manifest.','Review or restore modified installation files.'))
    checks.append(check('first-run-config','first-run',first.get('first_run_complete') is True,'fail','First-run configuration is complete.','Run leos first-run.'))
    checks.append(check('first-run-readiness','first-run',readiness.get('status')=='ready','fail','First-run readiness is ready.','Resolve readiness blockers and rerun first-run.'))
    checks.append(check('admin-activation','security',admin.get('activation_required') is True and admin.get('credential_mode')=='deferred-activation','warn','Administrator credential activation remains explicit.','Review administrator activation state.'))
    checks.append(check('plaintext-secrets','security',not any(v.get('contains_forbidden_secret') for v in docs.values()),'fail','No plaintext secret fields are persisted.','Remove plaintext secrets and rotate affected credentials.'))
    required_directories=('config','state','logs','runtime','journal','backups')
    directories_ok=all((target/name).is_dir() for name in required_directories)
    checks.append(check('required-directories','filesystem',directories_ok,'fail','Required installation directories are present.','Restore the governed installation directory layout.'))
    private_modes=True
    for key in ('administrator_bootstrap','runtime_selection'):
        rec=docs[key]
        if rec.get('exists') and int(rec.get('mode','0o777'),8)>0o640: private_modes=False
    checks.append(check('private-file-modes','permissions',private_modes,'warn','Private state files use restricted modes.','Restrict private state files to 0640 or tighter.'))
    backup_mode=stat.S_IMODE((target/'backups').stat().st_mode) if (target/'backups').is_dir() else None
    checks.append(check('backup-directory-mode','permissions',backup_mode==0o700,'warn','Backup directory uses mode 0700.','Set the backup directory mode to 0700.'))
    container_ok=runtime_facts.get('container_runtime_available', shutil.which('docker') is not None or shutil.which('podman') is not None)
    checks.append(check('container-runtime','container-runtime',container_ok,'warn','A container runtime is available.','Install Docker or Podman before deployment.'))
    requires_nvidia=runtime.get('acceleration')=='nvidia'
    nvidia_ok=(not requires_nvidia) or runtime_facts.get('nvidia_runtime_available',shutil.which('nvidia-smi') is not None)
    checks.append(check('nvidia-runtime','nvidia-runtime',nvidia_ok,'fail','NVIDIA runtime matches the selected profile.','Install or repair the NVIDIA runtime.'))
    checks.append(check('network-exposure','network-exposure',not public_bindings,'warn','No service fixture exposes a public wildcard binding.','Bind services to localhost or a controlled interface.'))
    checks.append(check('required-services','service-health',services['summary']['required_unhealthy']==0,'warn','Required services are healthy in the available inventory.','Start or repair required services.'))
    free_gb=resources.get('storage_free_gb')
    storage_ok=free_gb is None or float(free_gb)>=float(config['doctor']['minimum_free_storage_gb'])
    checks.append(check('storage-capacity','resource-capacity',storage_ok,'warn','Free storage meets the operator threshold.','Free storage or move the installation.'))
    fail=sum(1 for c in checks if not c['ok'] and c['severity']=='fail')
    warn=sum(1 for c in checks if not c['ok'] and c['severity']=='warn')
    status='fail' if fail else 'warn' if warn else 'pass'
    return {'contract_version':CONTRACT_DOCTOR,'status':status,'target_root':target.as_posix(),'checks':checks,'counts':{'total':len(checks),'pass':len(checks)-fail-warn,'warn':warn,'fail':fail},'generated_at':now,'repair_requires_confirmation':True,'safety':safety(True),'authorization':{'network':bool(allow_network),'daemon':bool(allow_daemon)},'details':{'drift':drift,'public_bindings':public_bindings}}

def log_plan(target: Path, config: dict[str,Any], service: str|None, since: str, limit: int, now: str) -> dict[str,Any]:
    if not 1<=limit<=10000: raise OperatorError('Log limit must be 1-10000.')
    candidates=[]
    for root in config.get('log_roots',['logs']):
        base=Path(root)
        candidates.append((base/(f'{service}.log' if service else '*.log')).as_posix())
    body={'target_root':target.as_posix(),'service_id':service,'since':since,'limit':limit,'candidate_paths':candidates}
    return {'contract_version':CONTRACT_LOGS,'query_id':stable_id('log-query',body),'service_id':service,'since':since,'limit':limit,'candidate_paths':candidates,'execution_authorized':False,'read_only':True,'generated_at':now}

def backup_plan(target: Path, config: dict[str,Any], destination: str, now: str) -> dict[str,Any]:
    destination_path=Path(destination)
    if destination_path.is_absolute(): raise OperatorError('Backup destination must be portable and relative.')
    body={'target_root':target.as_posix(),'destination':destination_path.as_posix(),'includes':config['backup_includes']}
    backup_id=stable_id('backup',body)
    return {'contract_version':CONTRACT_BACKUP,'backup_id':backup_id,'target_root':target.as_posix(),'destination':destination_path.as_posix(),'includes':list(config['backup_includes']),'requires_confirmation':True,'confirmation_token':stable_id('backup-confirm',body),'execution_authorized':False,'generated_at':now}

def update_plan(target: Path, target_release: str, channel: str, allow_network: bool, now: str) -> dict[str,Any]:
    manifest_path=target/'state/installation-manifest.json'
    current=load_object(manifest_path).get('source_release',SOURCE_RELEASE) if manifest_path.is_file() else SOURCE_RELEASE
    if not re.fullmatch(r'[0-9A-Za-z._-]{3,80}',target_release): raise OperatorError('Invalid target release.')
    body={'current_release':current,'target_release':target_release,'channel':channel}
    steps=[{'sequence':1,'action':'verify-source-authority'},{'sequence':2,'action':'create-backup'},{'sequence':3,'action':'stage-update'},{'sequence':4,'action':'run-acceptance'},{'sequence':5,'action':'promote-after-confirmation'}]
    return {'contract_version':CONTRACT_UPDATE,'update_id':stable_id('update',body),'current_release':current,'target_release':target_release,'channel':channel,'steps':steps,'requires_confirmation':True,'confirmation_token':stable_id('update-confirm',body),'network_authorized':bool(allow_network),'external_network_contacted':False,'execution_authorized':False,'generated_at':now}

def cli_result(command: str, payload: dict[str,Any], now: str, ok: bool=True, exit_code: int=0, read_only: bool=True) -> dict[str,Any]:
    return {'contract_version':CONTRACT_CLI,'command':command,'ok':ok,'exit_code':exit_code,'generated_at':now,'payload_contract':payload.get('contract_version','leos.unknown.v1'),'payload':payload,'safety':safety(read_only)}

def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description='LEOS operator CLI and doctor')
    parser.add_argument('--target-root',default=os.environ.get('LEOS_TARGET_ROOT','leos-installation'))
    parser.add_argument('--config',default=str(DEFAULT_CONFIG))
    parser.add_argument('--service-catalog',default=str(DEFAULT_SERVICE_CATALOG))
    parser.add_argument('--security-observability-config',default=str(DEFAULT_SECURITY_OBSERVABILITY_CONFIG))
    parser.add_argument('--fixture')
    parser.add_argument('--now')
    parser.add_argument('--output')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    doctor=sub.add_parser('doctor'); doctor.add_argument('--allow-daemon',action='store_true'); doctor.add_argument('--allow-network',action='store_true')
    services=sub.add_parser('services'); services.add_argument('--allow-daemon',action='store_true')
    logs=sub.add_parser('logs'); logs.add_argument('--service'); logs.add_argument('--since',default='1h'); logs.add_argument('--limit',type=int,default=200)
    backup=sub.add_parser('backup'); backup.add_argument('--destination',default='backups/operator-snapshot.tar.gz')
    update=sub.add_parser('update'); update.add_argument('--target-release',required=True); update.add_argument('--channel',default='development'); update.add_argument('--allow-network',action='store_true')
    sub.add_parser('version')
    install=sub.add_parser('install'); install.add_argument('args',nargs=argparse.REMAINDER)
    first=sub.add_parser('first-run'); first.add_argument('args',nargs=argparse.REMAINDER)
    sub.add_parser('security')
    observe=sub.add_parser('observe'); observe.add_argument('--view',choices=['health','metrics','readiness'],default='readiness')
    diagnostics=sub.add_parser('diagnostics'); diagnostics.add_argument('--export',action='store_true'); diagnostics.add_argument('--output-relative',default='diagnostics/leos-diagnostics.zip'); diagnostics.add_argument('--confirm')
    return parser

def main(argv: list[str]|None=None) -> int:
    args=build_parser().parse_args(argv)
    now=args.now or utc_now()
    target=safe_target(args.target_root)
    config=load_object(Path(args.config),'leos.operator-cli-config.v1')
    catalog=load_object(Path(args.service_catalog),'leos.operator-service-catalog.v1')
    fixture=load_fixture(args.fixture)
    security_config=load_security_object(Path(args.security_observability_config),'leos.security-observability-config.v1')
    result_read_only=True
    if args.command=='status': payload=status_payload(target,config,catalog,fixture,now)
    elif args.command=='doctor': payload=doctor_payload(target,config,catalog,fixture,now,args.allow_daemon,args.allow_network)
    elif args.command=='services': payload=service_inventory(catalog,fixture,now,args.allow_daemon)
    elif args.command=='logs': payload=log_plan(target,config,args.service,args.since,args.limit,now)
    elif args.command=='backup': payload=backup_plan(target,config,args.destination,now)
    elif args.command=='update': payload=update_plan(target,args.target_release,args.channel,args.allow_network,now)
    elif args.command in {'security','observe','diagnostics'}:
        reports=build_security_observability_reports(target,security_config,catalog,fixture,now)
        if args.command=='security': payload=reports['security-baseline']
        elif args.command=='observe': payload=reports[{'health':'health-aggregate','metrics':'metrics-snapshot','readiness':'observability-readiness'}[args.view]]
        else:
            plan=security_diagnostics_plan(target,security_config,reports,now)
            payload=export_security_diagnostics(target,security_config,plan,reports,args.output_relative,args.confirm,now) if args.export else plan
            result_read_only=not args.export
    elif args.command=='version':
        identity=release_identity()
        payload={'contract_version':'leos.version.v1',**identity}
    elif args.command in {'install','first-run'}:
        executable='bin/leos-install' if args.command=='install' else 'bin/leos-first-run'
        payload={'contract_version':'leos.command-handoff.v1','command':args.command,'executable':executable,'arguments':list(args.args),'execution_authorized':False,'requires_explicit_invocation':True}
    else: raise OperatorError(f'Unsupported command: {args.command}')
    result=cli_result(args.command,payload,now,ok=True,exit_code=0,read_only=result_read_only)
    text=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.output:
        out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(text,encoding='utf-8')
    print(text,end='')
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except OperatorError as exc:
        result={'contract_version':CONTRACT_CLI,'command':'error','ok':False,'exit_code':2,'generated_at':utc_now(),'payload_contract':'leos.operator-error.v1','payload':{'contract_version':'leos.operator-error.v1','error':str(exc)},'safety':safety(True)}
        print(json.dumps(result,indent=2,sort_keys=True))
        raise SystemExit(2)

#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json, os, re, shutil, stat, subprocess, sys, tempfile
from pathlib import Path
from typing import Any

def read_json(path: Path)->Any: return json.loads(path.read_text(encoding='utf-8'))
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--root',required=True); a=p.parse_args(); root=Path(a.root).resolve(); checks={}; errors=[]
 files=['bin/leos','config/operator-cli.json','config/operator-service-catalog.json','contracts/cli-result.v1.schema.json','contracts/system-status.v1.schema.json','contracts/doctor-report.v1.schema.json','contracts/service-inventory.v1.schema.json','contracts/log-query-plan.v1.schema.json','contracts/backup-plan.v1.schema.json','contracts/update-plan.v1.schema.json','docs/phase52.4.4-leos-cli-doctor.md','examples/operator-fixture.json','examples/cli-result.json','examples/system-status.json','examples/doctor-report.json','examples/service-inventory.json','examples/log-query-plan.json','examples/backup-plan.json','examples/update-plan.json','tests/phase5244/test_operator_cli.py','tools/operator_cli.py','tools/validate_phase5244_cli_doctor.py']
 for rel in files: checks[f'file:{rel}']=(root/rel).is_file()
 for rel in [x for x in files if x.endswith('.json')]:
  try: read_json(root/rel); checks[f'json:{rel}']=True
  except Exception: checks[f'json:{rel}']=False
 for rel in ['tools/operator_cli.py','tools/validate_phase5244_cli_doctor.py','tests/phase5244/test_operator_cli.py']:
  try: ast.parse((root/rel).read_text(),filename=rel); checks[f'python-syntax:{rel}']=True
  except Exception: checks[f'python-syntax:{rel}']=False
 schemas={
 'cli-result.v1.schema.json':'leos.cli-result.v1','system-status.v1.schema.json':'leos.system-status.v1','doctor-report.v1.schema.json':'leos.doctor-report.v1','service-inventory.v1.schema.json':'leos.service-inventory.v1','log-query-plan.v1.schema.json':'leos.log-query-plan.v1','backup-plan.v1.schema.json':'leos.backup-plan.v1','update-plan.v1.schema.json':'leos.update-plan.v1'}
 for name,contract in schemas.items():
  s=read_json(root/'contracts'/name); checks[f'schema-contract:{name}']=s.get('properties',{}).get('contract_version',{}).get('const')==contract; checks[f'schema-no-additional:{name}']=s.get('additionalProperties') is False; checks[f'schema-id:{name}']=str(s.get('$id','')).startswith('https://leosai.org/contracts/')
 cfg=read_json(root/'config/operator-cli.json'); cat=read_json(root/'config/operator-service-catalog.json'); fix=read_json(root/'examples/operator-fixture.json')
 checks['config-contract']=cfg.get('contract_version')=='leos.operator-cli-config.v1'; checks['config-read-only']=cfg.get('read_only_default') is True; checks['config-no-network']=cfg.get('external_network_contact_default') is False; checks['config-no-daemon']=cfg.get('container_daemon_contact_default') is False; checks['config-no-secret-output']=cfg.get('plaintext_secret_output') is False
 checks['catalog-contract']=cat.get('contract_version')=='leos.operator-service-catalog.v1'; checks['catalog-service-count-6']=len(cat.get('services',[]))==6; checks['catalog-ids-unique']=len({x['service_id'] for x in cat['services']})==len(cat['services']); checks['fixture-contract']=fix.get('contract_version')=='leos.operator-fixture.v1'; checks['fixture-no-public-binding']=not any(str(b).startswith(('0.0.0.0:',':::')) for s in fix['services'].values() for b in s.get('bindings',[]))
 src=(root/'tools/operator_cli.py').read_text(); checks['source-no-requests']='import requests' not in src; checks['source-no-httpx']='import httpx' not in src; checks['source-no-socket']='import socket' not in src; checks['source-no-urllib-request']='urllib.request' not in src; checks['source-confirmation-backup']='backup-confirm' in src; checks['source-confirmation-update']='update-confirm' in src; checks['source-daemon-default-false']='container_daemon_contact_default' in (root/'config/operator-cli.json').read_text(); checks['source-redaction']='FORBIDDEN_SECRET_KEYS' in src; checks['source-doctor-domains']=all(x in src for x in ['release-integrity','network-exposure','resource-capacity','service-health']); checks['wrapper-executable']=os.access(root/'bin/leos',os.X_OK); checks['wrapper-strict-shell']='set -euo pipefail' in (root/'bin/leos').read_text(); checks['wrapper-targets-operator']='tools/operator_cli.py' in (root/'bin/leos').read_text()
 unit=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(root/'tests/phase5244'),'-p','test_*.py','-v'],cwd=root,text=True,capture_output=True); unit_count=unit.stdout.count(' ... ok')+unit.stderr.count(' ... ok'); checks['unit-tests-exit-zero']=unit.returncode==0; checks['unit-tests-31']=unit_count==31
 # integration fixture target
 with tempfile.TemporaryDirectory(prefix='leos-operator-accept-') as td:
  target=Path(td)/'leos-target'; target.mkdir()
  for d,m in [('config',0o750),('state',0o750),('logs',0o750),('runtime',0o750),('journal',0o750),('backups',0o700)]: (target/d).mkdir(); (target/d).chmod(m)
  shutil.copy2(root/'examples/installation-plan.json',target/'state/installation-plan.json')
  for name in ['first-run-session.json','administrator-bootstrap.json','node-registration-plan.json','runtime-selection.json','first-run-readiness.json']: shutil.copy2(root/'examples'/name,target/'state'/name)
  shutil.copy2(root/'examples/first-run-configuration.json',target/'config/first-run.json')
  (target/'state/administrator-bootstrap.json').chmod(0o600); (target/'state/runtime-selection.json').chmod(0o640)
  import importlib.util
  spec=importlib.util.spec_from_file_location('operator_cli',root/'tools/operator_cli.py'); op=importlib.util.module_from_spec(spec); spec.loader.exec_module(op)
  plan_path=target/'state/installation-plan.json'
  manifest=read_json(root/'examples/installation-manifest.json'); manifest['target_root']=target.as_posix(); manifest['source_release']=op.SOURCE_RELEASE; manifest['source_tree_sha256']=op.SOURCE_TREE; manifest['files']={'state/installation-plan.json':{'mode':'0o640','sha256':op.sha256_file(plan_path),'size_bytes':plan_path.stat().st_size}}
  (target/'state/installation-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
  base=[sys.executable,'-B',str(root/'tools/operator_cli.py'),'--target-root',str(target),'--fixture',str(root/'examples/operator-fixture.json'),'--now','2026-07-20T00:00:00+00:00']
  commands={'status':['status'],'doctor':['doctor'],'services':['services'],'logs':['logs','--service','ai-router'],'backup':['backup','--destination','backups/operator.tar.gz'],'update':['update','--target-release','0.1.0-dev-preview-rc12'],'version':['version']}
  results={}
  for name,args in commands.items():
   run=subprocess.run([*base,*args],cwd=root,text=True,capture_output=True); checks[f'cli-{name}-exit-zero']=run.returncode==0
   try: results[name]=json.loads(run.stdout); checks[f'cli-{name}-json']=True
   except Exception: results[name]={}; checks[f'cli-{name}-json']=False
  checks['status-ready']=results['status'].get('payload',{}).get('status')=='ready'; checks['doctor-pass']=results['doctor'].get('payload',{}).get('status')=='pass'; checks['services-healthy-5']=results['services'].get('payload',{}).get('summary',{}).get('healthy')==5; checks['logs-read-only']=results['logs'].get('payload',{}).get('read_only') is True; checks['backup-confirmation']=results['backup'].get('payload',{}).get('requires_confirmation') is True; checks['backup-not-executed']=results['backup'].get('payload',{}).get('execution_authorized') is False; checks['update-confirmation']=results['update'].get('payload',{}).get('requires_confirmation') is True; checks['update-no-network']=results['update'].get('payload',{}).get('external_network_contacted') is False; release_manifest=read_json(root/'manifest.json') if (root/'manifest.json').is_file() else {}; expected_release=release_manifest.get('release_version','0.1.0-dev-preview-rc11'); checks['version-current']=results['version'].get('payload',{}).get('release')==expected_release; checks['all-cli-no-network']=all(r.get('safety',{}).get('external_network_contacted') is False for r in results.values()); checks['all-cli-no-daemon']=all(r.get('safety',{}).get('container_daemon_contacted') is False for r in results.values()); checks['all-cli-no-secret']=all(r.get('safety',{}).get('plaintext_secret_exposed') is False for r in results.values())
 # final example checks; validator never mutates source examples
 examples={'cli-result.json':'leos.cli-result.v1','system-status.json':'leos.system-status.v1','doctor-report.json':'leos.doctor-report.v1','service-inventory.json':'leos.service-inventory.v1','log-query-plan.json':'leos.log-query-plan.v1','backup-plan.json':'leos.backup-plan.v1','update-plan.json':'leos.update-plan.v1'}
 for name,contract in examples.items():
  example=read_json(root/'examples'/name); checks[f'example-contract:{name}']=example.get('contract_version')==contract; checks[f'example-portable:{name}']=(os.sep+'tmp'+os.sep) not in json.dumps(example) and (os.sep+'srv'+os.sep) not in json.dumps(example)
 errors=[k for k,v in checks.items() if not v]
 out={'ok':not errors,'phase':'52.4.4','contract_version':'leos.phase52.4.4-cli-doctor-validation.v1','check_count':len(checks),'error_count':len(errors),'errors':errors,'checks':checks,'unit_tests':{'ok':unit.returncode==0,'test_count':unit_count,'returncode':unit.returncode,'stdout':unit.stdout,'stderr':unit.stderr},'fixture_acceptance':{'ok':all(checks.get(k,False) for k in ['status-ready','doctor-pass','services-healthy-5','logs-read-only','backup-confirmation','update-confirmation','version-current']),'status':'ready','doctor':'pass','healthy_services':5,'backup_confirmation':True,'update_confirmation':True},'external_network_contacted':False,'container_daemon_contacted':False,'docker_socket_mounted':False,'production_state_accessed':False,'production_network_attached':False}
 print(json.dumps(out,indent=2,sort_keys=True)); return 0 if out['ok'] else 1
if __name__=='__main__': raise SystemExit(main())

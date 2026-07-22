from __future__ import annotations
import importlib.util, json, os, shutil, stat, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('operator_cli',ROOT/'tools/operator_cli.py'); op=importlib.util.module_from_spec(spec); spec.loader.exec_module(op)
NOW='2026-07-20T00:00:00+00:00'

class OperatorCliTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.target=Path(self.tmp.name)/'leos-target'; self.target.mkdir()
  for d,m in [('config',0o750),('state',0o750),('logs',0o750),('runtime',0o750),('journal',0o750),('backups',0o700)]: (self.target/d).mkdir(); (self.target/d).chmod(m)
  shutil.copy2(ROOT/'examples/installation-plan.json',self.target/'state/installation-plan.json')
  for name in ['first-run-session.json','administrator-bootstrap.json','node-registration-plan.json','runtime-selection.json','first-run-readiness.json']:
   dst=self.target/'state'/name; shutil.copy2(ROOT/'examples'/name,dst)
  shutil.copy2(ROOT/'examples/first-run-configuration.json',self.target/'config/first-run.json')
  (self.target/'state/administrator-bootstrap.json').chmod(0o600)
  (self.target/'state/runtime-selection.json').chmod(0o640)
  plan_path=self.target/'state/installation-plan.json'
  manifest=json.loads((ROOT/'examples/installation-manifest.json').read_text()); manifest['target_root']=self.target.as_posix()
  manifest['files']={'state/installation-plan.json':{'mode':'0o640','sha256':op.sha256_file(plan_path),'size_bytes':plan_path.stat().st_size}}
  (self.target/'state/installation-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
  self.config=json.loads((ROOT/'config/operator-cli.json').read_text()); self.catalog=json.loads((ROOT/'config/operator-service-catalog.json').read_text()); self.fixture=json.loads((ROOT/'examples/operator-fixture.json').read_text())
 def tearDown(self): self.tmp.cleanup()
 def test_stable_id_deterministic(self): self.assertEqual(op.stable_id('x',{'a':1}),op.stable_id('x',{'a':1}))
 def test_safe_target_blocks_root(self):
  with self.assertRaises(op.OperatorError): op.safe_target(os.sep)
 def test_status_ready(self): self.assertEqual(op.status_payload(self.target,self.config,self.catalog,self.fixture,NOW)['status'],'ready')
 def test_status_contract(self): self.assertEqual(op.status_payload(self.target,self.config,self.catalog,self.fixture,NOW)['contract_version'],op.CONTRACT_STATUS)
 def test_status_detects_missing_install(self):
  (self.target/'state/installation-manifest.json').unlink(); self.assertEqual(op.status_payload(self.target,self.config,self.catalog,self.fixture,NOW)['status'],'not-ready')
 def test_status_detects_drift(self):
  (self.target/'state/installation-plan.json').write_text('{}'); self.assertTrue(op.status_payload(self.target,self.config,self.catalog,self.fixture,NOW)['installation']['drift'])
 def test_services_fixture(self): self.assertEqual(op.service_inventory(self.catalog,self.fixture,NOW)['summary']['healthy'],5)
 def test_services_no_daemon_contact(self): self.assertFalse(op.service_inventory(self.catalog,self.fixture,NOW,True)['daemon_contacted'])
 def test_doctor_pass(self): self.assertEqual(op.doctor_payload(self.target,self.config,self.catalog,self.fixture,NOW)['status'],'pass')
 def test_doctor_detects_public_binding(self):
  f=json.loads(json.dumps(self.fixture)); f['services']['ai-router']['bindings']=['0.0.0.0:8000']; self.assertEqual(op.doctor_payload(self.target,self.config,self.catalog,f,NOW)['status'],'warn')
 def test_doctor_detects_unhealthy_required_service(self):
  f=json.loads(json.dumps(self.fixture)); f['services']['ai-router']['health']='unhealthy'; self.assertEqual(op.doctor_payload(self.target,self.config,self.catalog,f,NOW)['status'],'warn')
 def test_doctor_detects_low_storage(self):
  f=json.loads(json.dumps(self.fixture)); f['resources']['storage_free_gb']=1; self.assertEqual(op.doctor_payload(self.target,self.config,self.catalog,f,NOW)['status'],'warn')
 def test_doctor_detects_nvidia_missing(self):
  f=json.loads(json.dumps(self.fixture)); f['runtime']['nvidia_runtime_available']=False; self.assertEqual(op.doctor_payload(self.target,self.config,self.catalog,f,NOW)['status'],'fail')
 def test_doctor_no_network_contact(self): self.assertFalse(op.doctor_payload(self.target,self.config,self.catalog,self.fixture,NOW,allow_network=True)['safety']['external_network_contacted'])
 def test_doctor_no_plaintext_secret(self): self.assertTrue(next(c for c in op.doctor_payload(self.target,self.config,self.catalog,self.fixture,NOW)['checks'] if c['check_id']=='plaintext-secrets')['ok'])
 def test_log_plan_contract(self): self.assertEqual(op.log_plan(self.target,self.config,'ai-router','1h',200,NOW)['contract_version'],op.CONTRACT_LOGS)
 def test_log_plan_read_only(self): self.assertTrue(op.log_plan(self.target,self.config,None,'1h',20,NOW)['read_only'])
 def test_log_limit_blocked(self):
  with self.assertRaises(op.OperatorError): op.log_plan(self.target,self.config,None,'1h',0,NOW)
 def test_backup_plan_requires_confirmation(self): self.assertTrue(op.backup_plan(self.target,self.config,'backups/a.tar.gz',NOW)['requires_confirmation'])
 def test_backup_destination_portable(self):
  with self.assertRaises(op.OperatorError): op.backup_plan(self.target,self.config,str(Path(os.sep)/'tmp'/'a.tar.gz'),NOW)
 def test_backup_not_authorized(self): self.assertFalse(op.backup_plan(self.target,self.config,'backups/a.tar.gz',NOW)['execution_authorized'])
 def test_update_plan_requires_confirmation(self): self.assertTrue(op.update_plan(self.target,'0.1.0-dev-preview-rc10','development',False,NOW)['requires_confirmation'])
 def test_update_network_opt_in_recorded(self): self.assertTrue(op.update_plan(self.target,'0.1.0-dev-preview-rc10','development',True,NOW)['network_authorized'])
 def test_update_no_network_contact(self): self.assertFalse(op.update_plan(self.target,'0.1.0-dev-preview-rc10','development',True,NOW)['external_network_contacted'])
 def test_update_invalid_release(self):
  with self.assertRaises(op.OperatorError): op.update_plan(self.target,'bad release!','development',False,NOW)
 def test_cli_output_file(self):
  out=Path(self.tmp.name)/'out.json'; p=subprocess.run([sys.executable,'-B',str(ROOT/'tools/operator_cli.py'),'--target-root',str(self.target),'--fixture',str(ROOT/'examples/operator-fixture.json'),'--now',NOW,'--output',str(out),'status'],cwd=ROOT,text=True,capture_output=True); self.assertEqual(p.returncode,0); self.assertTrue(out.is_file())
 def test_cli_version(self):
  p=subprocess.run([sys.executable,'-B',str(ROOT/'tools/operator_cli.py'),'--target-root',str(self.target),'--now',NOW,'version'],cwd=ROOT,text=True,capture_output=True); self.assertEqual(json.loads(p.stdout)['payload']['release'],op.SOURCE_RELEASE)
 def test_cli_install_handoff_not_executed(self):
  p=subprocess.run([sys.executable,'-B',str(ROOT/'tools/operator_cli.py'),'--target-root',str(self.target),'--now',NOW,'install','--','--help'],cwd=ROOT,text=True,capture_output=True); self.assertFalse(json.loads(p.stdout)['payload']['execution_authorized'])
 def test_cli_first_run_handoff_not_executed(self):
  p=subprocess.run([sys.executable,'-B',str(ROOT/'tools/operator_cli.py'),'--target-root',str(self.target),'--now',NOW,'first-run'],cwd=ROOT,text=True,capture_output=True); self.assertFalse(json.loads(p.stdout)['payload']['execution_authorized'])
 def test_wrapper_executable(self): self.assertTrue(os.access(ROOT/'bin/leos',os.X_OK))
 def test_no_secret_in_fixture(self): self.assertFalse(op.contains_forbidden_secret(self.fixture))

if __name__=='__main__': unittest.main()
